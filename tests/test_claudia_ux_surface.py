from pathlib import Path


HTML = Path("static/index.html").read_text(encoding="utf-8")


def test_home_has_next_best_action_surface():
    assert 'id="home-next-action"' in HTML
    assert "Start here:" in HTML
    assert 'id="home-next-action-go"' in HTML


def test_prepare_blocks_filler_generation_until_teacher_supplies_source():
    assert 'id="prepare-source-status"' in HTML
    assert "choose a file or topic first" in HTML
    assert "function updatePrepareActionState()" in HTML
    assert "button.disabled = !hasSource" in HTML


def test_observe_preserves_selected_learner_after_save():
    assert "function clearObserveForm(options = {})" in HTML
    assert "preserveStudent: true" in HTML
    assert 'if ($("obs-template")) $("obs-template").value = "general";' in HTML


def test_parent_summary_requires_teacher_review_before_copy_or_print():
    assert "Teacher review checklist" in HTML
    assert "data-parent-review-check" in HTML
    assert "function updateParentReviewActions()" in HTML
    assert 'id="parent-copy-final" type="button" disabled' in HTML
    assert "Complete the checklist to copy or print." in HTML


def test_privacy_verdict_is_log_driven_not_hardcoded_reassurance():
    assert "Privacy verdict" in HTML
    assert "const privacyVerdict = externalCalls > 0" in HTML
    assert "This verdict comes from the local log" in HTML
    assert "student data local" in HTML
