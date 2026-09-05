"""Real DOM + real API, synthetic workspace; no installed app or private data.

Run with a Python environment containing playwright and the app dependencies.
Uses local Edge on Windows; otherwise Playwright's installed Chromium.
"""
import os
import sys
import tempfile
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
            browser = playwright.chromium.launch(channel="msedge" if sys.platform == "win32" else None, headless=True)
            context = browser.new_context(service_workers="block")
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
            assert not errors, errors
            browser.close()
        print('PASS: draft -> review -> approve -> reload -> Sources -> reopen -> download; retired nav absent; no JavaScript errors')


if __name__ == '__main__':
    main()
