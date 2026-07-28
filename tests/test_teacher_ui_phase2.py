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
    assert (
        "Google may show a broad Drive permission. Lingua Viva only checks folders "
        "you connect, and it does not download file contents until you choose to import."
    ) in html
    assert "Using Google Drive credentials set up by whoever installed Lingua Viva" in html
    assert "Sign in with Google again" in html
    # H1 (SPEC_LV_DRIVE_FINAL_HARDENING_2026-07-27): unverified-app
    # interstitial walkthrough, operator-approved wording. The button label
    # Google renders is "Go to <OAuth client name> (unsafe)" — the client
    # MUST be named "Lingua Viva" in the console for this copy to match.
    assert "Google will show a warning that it hasn't verified this app" in html
    assert "Go to Lingua Viva (unsafe)" in html
    assert "Nothing leaves this machine until you choose to share it." in html
    assert "student_lens_source" in html
    assert "curriculum_unit_source" in html
    assert "/api/admin/programme" in html
    assert "lvSchedule" in html
    assert "My Schedule" in html
    assert "Review before sending. No AI attribution in final message." in html
    assert "No external calls" in html
