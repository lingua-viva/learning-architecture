from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_teacher_sidebar_contract():
    html = (ROOT / "static" / "index.html").read_text()

    for label in ["Home", "Plan", "Prepare", "Observe", "Students", "Assess", "Ask", "Parents"]:
        assert f'"{label}"' in html

    for label in ["Health", "Privacy", "Settings", "Reflect"]:
        assert f'"{label}"' in html

    assert "I am a coordinator" in html
    assert "I am a teacher" in html
    assert "/api/prepare/activity" in html
    assert "/api/observe/capture" in html
    assert "/api/observe/classify" in html
    assert "Support Profile Review" in html
    assert "support_entries" in html
    assert "data-support-field=\"support_category\"" in html
    assert "renderSupportProfileSummary" in html
    assert "/api/parents/recommendation" in html
    assert "/api/support-bundle" in html
    assert "Google Drive" in html
    assert "/api/google-drive/status" in html
    assert "/api/google-drive/list" in html
    assert "/api/google-drive/import" in html
    assert "List Drive Files" in html
    assert "Import Selected" in html
    assert "student_lens_source" in html
    assert "curriculum_unit_source" in html
    assert "/api/admin/programme" in html
    assert "lvSchedule" in html
    assert "My Schedule" in html
    assert "Review before sending. No AI attribution in final message." in html
    assert "No external calls" in html
