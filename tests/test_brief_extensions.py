"""Daily-brief extensions (2026-08-09 wave): absence escalations, knowledge
library, coursework artifacts — and the safeguarding containment guarantee."""

from datetime import date, timedelta

import pytest


@pytest.fixture()
def state_home(tmp_path, monkeypatch):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path))
    return tmp_path


def _widget(widgets, wid):
    matches = [w for w in widgets if w["id"] == wid]
    assert matches, f"widget {wid} missing from {[w['id'] for w in widgets]}"
    return matches[0]


def test_extra_widgets_present_and_empty_state(state_home):
    from src.lingua_viva.brief_extensions import extra_widgets

    widgets = extra_widgets(7)
    assert _widget(widgets, "absence_escalations")["count"] == 0
    assert _widget(widgets, "knowledge_library")["count"] == 0
    assert _widget(widgets, "coursework_artifacts")["count"] == 0
    for w in widgets:
        assert w["status"] in ("ok", "attention")


def test_absence_escalation_surfaces_anonymously(state_home):
    from src.lingua_viva.absence_escalation import record_absence
    from src.lingua_viva.brief_extensions import extra_widgets

    # Three consecutive school days -> escalation. Use a synthetic student.
    day = date(2026, 8, 5)  # Wednesday
    for offset in range(3):
        record_absence("stu-nora-rossi", day - timedelta(days=offset))

    widget = _widget(extra_widgets(7), "absence_escalations")
    assert widget["count"] >= 1
    assert widget["status"] == "attention"
    # Staff-room safety: raw student ids never appear, only aron references.
    assert all("stu-nora-rossi" != ref for ref in widget["students"])


def test_coursework_artifacts_counts_recent_pdfs(state_home):
    from src.lingua_viva.brief_extensions import extra_widgets
    from src.lingua_viva.pdf_generator import artifacts_dir

    out = artifacts_dir("coursework")
    (out / "sample_pack_teacher.pdf").write_bytes(b"%PDF-1.4 test")
    widget = _widget(extra_widgets(7), "coursework_artifacts")
    assert widget["count"] == 1


def test_red_safeguarding_never_reaches_brief_widgets(state_home):
    """Containment: a RED capture lands only in the restricted ledger, so no
    brief widget may ever carry its content."""
    from src.lingua_viva import safeguarding
    from src.lingua_viva.brief_extensions import extra_widgets

    class FailIfCalledPipeline:
        def capture(self, *args, **kwargs):  # pragma: no cover - must not run
            raise AssertionError("RED must never reach the normal pipeline")

    result = safeguarding.capture_with_safeguarding(
        FailIfCalledPipeline(),
        student_id="stu-synthetic-red",
        teacher_id="teacher-1",
        raw_transcript="The student disclosed that an adult at home hits them.",
        template_type="observation",
    )
    assert result["safeguarding"]["tier"] == "RED"

    flat = repr(extra_widgets(7))
    assert "hits them" not in flat
    assert "stu-synthetic-red" not in flat


def test_extensions_fail_soft(state_home, monkeypatch):
    """A broken extension degrades its widget only — never the whole brief."""
    import src.lingua_viva.brief_extensions as be

    monkeypatch.setattr(
        be, "_library_widget", lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    ids = [w["id"] for w in be.extra_widgets(7)]
    assert "knowledge_library" not in ids
    assert "absence_escalations" in ids
    assert "coursework_artifacts" in ids
