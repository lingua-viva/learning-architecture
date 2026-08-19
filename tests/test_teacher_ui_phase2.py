from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_teacher_sidebar_contract():
    html = (ROOT / "static" / "index.html").read_text()

    for label in ["Home", "Plan", "Prepare", "Observe", "Students", "Assess", "Ask", "Summaries"]:
        assert f'"{label}"' in html

    for label in ["Health", "Privacy", "Settings", "Reflect"]:
        assert f'"{label}"' in html

    assert "I am a coordinator" in html
    assert "I am a teacher" in html
    assert "/api/lesson-materials/generate" in html
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
    # Drive workspace (v36): teacher-language labels replaced the old
    # "List Drive Files"/"Import Selected" Settings-panel buttons.
    assert "Show files" in html
    assert "Bring selected files in" in html
    # In-app Google sign-in (SPEC_LV_DRIVE_SELF_SERVICE_AUTH_2026-07-27 §A):
    # sign-in lives in the Sources/Drive section, trust copy is verbatim,
    # env credentials shadow (and hide) the sign-in controls.
    assert "/api/google-drive/auth/start" in html
    assert "/api/google-drive/auth/disconnect" in html
    assert "Sign in with Google" in html
    # Per-file access (SPEC_LV_DRIVE_PER_FILE_ACCESS_2026-08-19): scope is
    # drive.file and the app is published, so Google shows NO unverified-app
    # interstitial and NO broad-permission screen. The old H1 walkthrough
    # ("Advanced" → "Go to Lingua Viva (unsafe)") and the "broad Drive
    # permission" line are obsolete and must NOT come back — they would
    # describe screens teachers never see.
    assert (
        "Google will ask permission for files this app creates or that you "
        "open with it"
    ) in html
    assert "upload them directly in the app" in html
    assert "Google will show a warning that it hasn't verified this app" not in html
    assert "Go to Lingua Viva (unsafe)" not in html
    assert "broad Drive permission" not in html
    assert "Using Google Drive credentials set up by whoever installed Lingua Viva" in html
    assert "Sign in with Google again" in html
    assert "Nothing leaves this machine until you choose to share it." in html
    assert "student_lens_source" in html
    assert "curriculum_unit_source" in html
    assert "/api/admin/programme" in html
    assert "lvSchedule" in html
    assert "My Schedule" in html
    assert "Review before sharing. No AI attribution in final message." in html
    # Was: assert "No external calls" in html. That string was rendered as the
    # label of the external-call COUNT, so a machine that had made three
    # external calls displayed "3 / No external calls". Slice 4 replaced it
    # with a label that reads correctly at any count, and moved the actual
    # local-vs-external answer to the Governance view, which measures it.
    assert "external calls" in html
    assert "<p>No external calls</p>" not in html, "the count must not be labelled as a zero"
