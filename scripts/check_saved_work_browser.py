"""Real DOM + real API, synthetic workspace; no installed app or private data.

Run with a Python environment containing playwright and the app dependencies.
Uses local Edge on Windows; otherwise Playwright's installed Chromium.
"""
import os
import sys
import tempfile
import re
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    with tempfile.TemporaryDirectory(prefix="lv-browser-") as temporary:
        workspace = Path(temporary)
        for key in list(os.environ):
            if key.startswith(("LV_", "SIR_")):
                del os.environ[key]
        for key in ("LV_STATE_HOME", "LV_CONFIG_HOME", "LV_UPDATE_HOME"):
            os.environ[key] = str(workspace)
        os.environ["LV_STUDENT_DB_PATH"] = str(workspace / "students.db")
        from src.web import app, _with_student_store
        from fastapi.testclient import TestClient
        from playwright.sync_api import sync_playwright, expect

        def seed(store):
            store.create_lens(student_id="demo-1", display_name="Demo Learner", grade_level="G3")
            store.add_support_entry("demo-1", "learning_and_cognition", "strengths",
                                    "explains ideas to a partner before writing", "local-teacher",
                                    confidence="teacher_confirmed")
        _with_student_store(seed)
        client = TestClient(app)
        with sync_playwright() as playwright:
            args = []
            if '--microphone' in sys.argv:
                args = ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream',
                        '--use-file-for-fake-audio-capture=' + str(ROOT / 'tests/fixtures/assessment/synthetic-en.wav')]
            browser = playwright.chromium.launch(channel="msedge" if sys.platform == "win32" else None, headless=True, args=args)
            context = browser.new_context(service_workers="block", permissions=['microphone'])
            def dispatch(route):
                req = route.request
                url = urlsplit(req.url)
                if url.hostname != "127.0.0.1":
                    return route.abort()
                response = client.request(req.method, url.path + ("?" + url.query if url.query else ""),
                                          content=req.post_data_buffer, headers={k: v for k, v in req.headers.items() if k != "host"})
                route.fulfill(status=response.status_code, body=response.content,
                              headers={k: v for k, v in response.headers.items() if k.lower() not in {"content-length", "content-encoding"}})
            context.route("**/*", dispatch)
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.add_init_script("localStorage.setItem('lvRole', 'teacher')")
            page.goto("http://127.0.0.1:9876/")
            expect(page.locator('[data-view="students"]')).to_be_visible()
            for hidden in ("home", "daily", "plan", "slack"):
                expect(page.locator(f'[data-view="{hidden}"]')).to_have_count(0)
            page.locator('[data-view="parents"]').click()
            page.locator('#parent-student').select_option('demo-1')
            page.locator('#draft-parent').click()
            expect(page.locator('[data-parent-review-check]').first).to_be_visible()
            for checkbox in page.locator('[data-parent-review-check]').all():
                checkbox.check()
            page.locator('#parent-approve').click()
            expect(page.locator('#parent-review-status')).to_contain_text('Approved')
            page.reload()
            expect(page.locator('#view-title')).to_have_text('Students')
            page.locator('[data-view="sources"]').click()
            try:
                page.locator('[data-open-saved]').first.click(timeout=10000)
            except Exception:
                print(page.locator('#content').inner_text())
                print('Browser errors:', errors)
                print('Saved API:', client.get('/api/artifacts/saved').text)
                raise
            expect(page.locator('#saved-work-detail')).to_contain_text('explains ideas')
            with page.expect_download() as downloaded:
                page.locator('#saved-work-download').click()
            assert downloaded.value.suggested_filename.startswith('SAVED-')
            page.locator('[data-view="assess"]').click()
            page.locator('#diagnostic-student').select_option('demo-1')
            try:
                page.locator('#diagnostic-text').fill('Sono andato a scuola. Ho incontrato un amico.', timeout=10000)
            except Exception:
                print('ASSESS FAILURE:', page.locator('#content').inner_text(), 'ERRORS:', errors, flush=True)
                raise
            page.locator('#diagnostic-text-confirmed').check()
            page.locator('#diagnostic-use-model').uncheck()
            page.locator('#diagnostic-analyse').click()
            expect(page.locator('#diagnostic-review')).to_contain_text('Review the diagnostic')
            for checkbox in page.locator('[data-dimension-confirm]').all():
                checkbox.check()
            page.locator('#diagnostic-confirm').click()
            expect(page.locator('#diagnostic-final')).to_contain_text('Saved to the lens')
            page.locator('#diagnostic-undo').click()
            expect(page.locator('#diagnostic-final')).to_contain_text('Removed from the active lens')
            if '--sources' in sys.argv:
                from io import BytesIO
                from PIL import Image, ImageDraw, ImageFont
                photo = Image.new('RGB', (1100, 220), 'white')
                draw = ImageDraw.Draw(photo)
                font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 36) if sys.platform == 'win32' else ImageFont.load_default(size=36)
                draw.text((25, 55), 'Sono andato a scuola con un amico.', font=font, fill='black')
                png = BytesIO(); photo.save(png, format='PNG')
                from reportlab.pdfgen.canvas import Canvas
                from reportlab.lib.utils import ImageReader
                scanned = BytesIO(); canvas = Canvas(scanned)
                canvas.drawImage(ImageReader(png), 40, 600, width=520, height=104); canvas.save()
                fixtures = [('work.png', png.getvalue(), 'scuola'), ('scan.pdf', scanned.getvalue(), 'scuola')]
                for lang, term in [('en', 'school'), ('it', 'scuola')]:
                    fixtures.append((f'oral-{lang}.wav', (ROOT / f'tests/fixtures/assessment/synthetic-{lang}.wav').read_bytes(), term))
                for filename, content, term in fixtures:
                    page.locator('[data-view="assess"]').click()
                    page.locator('#diagnostic-student').select_option('demo-1')
                    page.locator('#diagnostic-language').select_option('it' if term == 'scuola' else 'en')
                    page.locator('#diagnostic-file').set_input_files({'name': filename, 'mimeType': 'application/octet-stream', 'buffer': content})
                    page.locator('#diagnostic-upload').click()
                    expect(page.locator('#diagnostic-text')).to_have_value(re.compile(term), timeout=180000)
                    page.locator('#diagnostic-text-confirmed').check()
                    page.locator('#diagnostic-use-model').uncheck()
                    page.locator('#diagnostic-analyse').click()
                    expect(page.locator('[data-dimension-confirm]').first).to_be_visible()
                    for checkbox in page.locator('[data-dimension-confirm]').all():
                        checkbox.check()
                    page.locator('#diagnostic-confirm').click()
                    expect(page.locator('#diagnostic-final')).to_contain_text('Saved to the lens')
                    print('PASS source -> correction -> diagnostic -> lens -> saved output:', filename, flush=True)
            if '--microphone' in sys.argv:
                page.locator('[data-view="assess"]').click()
                page.locator('#diagnostic-student').select_option('demo-1')
                page.locator('#diagnostic-language').select_option('en')
                page.locator('#diagnostic-text').fill('')
                page.locator('#diagnostic-record').click()
                expect(page.locator('#diagnostic-record')).to_have_text('Stop and transcribe')
                page.wait_for_timeout(6500)
                page.locator('#diagnostic-record').click()
                expect(page.locator('#diagnostic-text')).to_have_value(re.compile(r'\w+'), timeout=180000)
                page.locator('#diagnostic-text-confirmed').check()
                page.locator('#diagnostic-use-model').uncheck()
                page.locator('#diagnostic-analyse').click()
                expect(page.locator('[data-dimension-confirm]').first).to_be_visible()
                for checkbox in page.locator('[data-dimension-confirm]').all():
                    checkbox.check()
                page.locator('#diagnostic-confirm').click()
                expect(page.locator('#diagnostic-final')).to_contain_text('Saved to the lens')
                print('PASS: in-app microphone (synthetic device) -> transcription -> corrected review -> saved diagnostic', flush=True)
            if '--prepare' in sys.argv:
                page.locator('[data-view="prepare"]').click()
                page.locator('#lesson-file-input').set_input_files({'name': 'water-cycle.txt', 'mimeType': 'text/plain',
                    'buffer': b'The water cycle: Water evaporates when warmed by the sun. Water vapour cools and condenses into clouds. Rain returns water to rivers. Draw and label evaporation, condensation and precipitation.'})
                try:
                    expect(page.locator('#selected-lesson-line')).to_contain_text('water-cycle', timeout=30000)
                except Exception:
                    print('PREPARE FAILURE:', page.locator('#content').inner_text(), 'ERRORS:', errors, flush=True)
                    raise
                page.locator('#prep-topic').fill('The water cycle')
                page.locator('#generate-activity').click()
                expect(page.locator('#activity-output')).to_contain_text('Foundational', timeout=180000)
                assert 'template text' not in page.locator('#activity-output').inner_text(), 'Real local model generation did not complete'
                page.locator('#preview-lesson-packet').click()
                expect(page.locator('#approve-lesson-packet')).to_be_visible(timeout=180000)
                page.locator('#approve-lesson-packet').click()
                expect(page.locator('#lesson-packet-output')).to_contain_text('approved', timeout=30000)
                page.locator('[data-view="sources"]').click()
                page.locator('[data-open-saved]').first.click()
                expect(page.locator('#saved-work-detail')).to_contain_text('water cycle')
                expect(page.locator('#saved-work-print')).to_be_visible()
                print('PASS: uploaded coursework -> packet preview -> approved saved packet -> reopen/print control', flush=True)
            page.locator('#change-role').click()
            page.locator('[data-role="coordinator"]').click()
            page.locator('[data-view="lensquery"]').click()
            page.locator('#lens-query-run').click()
            expect(page.locator('#lens-query-result')).to_contain_text('Answer saved in Sources')
            with page.expect_download() as csv_download:
                page.locator('#lens-query-csv').click()
            assert csv_download.value.suggested_filename == 'lens-query.csv'
            assert not errors, errors
            browser.close()
        print('PASS: parent note -> review -> approve -> reload -> reopen -> download; assessment text -> review -> lens -> saved output -> undo; admin query -> saved CSV; retired nav absent; no JavaScript errors')


if __name__ == '__main__':
    main()
