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
    assert "/api/parents/recommendation" in html
    assert "/api/support-bundle" in html
    assert "/api/admin/programme" in html
    assert "lvSchedule" in html
    assert "/api/teacher/today" in html or "My Schedule" in html
    assert "Review before sending. No AI attribution in final message." in html
    assert "No external calls" in html
