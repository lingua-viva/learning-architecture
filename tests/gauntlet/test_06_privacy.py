"""Gauntlet phase 6 — privacy + safeguarding. The most important phase.

The containment list below is HARDCODED on purpose (per the gauntlet
prompt): if the corpus ever changes, this list must be updated as a
conscious act — a privacy roster should never silently track a fixture.

What this phase pins:
- no roster name in any exportable artifact (plan, report, revision)
- the TTS / exit gate blocks student data at the boundary
- the privacy log records decisions without ever recording a name
- RED safeguarding content never reaches the lens store or notifications
- voice detection resolves names locally without leaking them
"""

from __future__ import annotations

import json

from src.lingua_viva.exit_gates import ExitRequest, check_exit
from src.lingua_viva.safeguarding import (
    GREEN,
    RED,
    capture_with_safeguarding,
    classify_severity,
)
from src.lingua_viva.voice_intent import detect_student_detailed

from .conftest import EXPECTED_STUDENTS

# Hardcoded containment roster — see module docstring.
CONTAINMENT_ROSTER = [
    "Marco Bianchi", "Nora Rossi", "Sara Conti", "Luca Ferri", "Elisa Greco",
    "Tommaso Marini", "Giulia Riva", "Pietro Serra", "Anna (Annie) Villa",
    "Leo Fontana", "Camilla Gatti", "Matteo Barbieri", "Sofia Caruso",
    "Emma Longo", "Diego Marchetti", "Alice Monti", "Filippo Neri",
    "Viola Pellegrini", "Oscar Sanna",
]

RED_TRANSCRIPT = "She told me that someone hurts her at home and she is scared."
GREEN_TRANSCRIPT = "Read three pages aloud with growing confidence today."


def test_containment_roster_matches_the_labeled_corpus():
    """If this fails, the corpus changed — update CONTAINMENT_ROSTER
    deliberately and re-review every phase-6 assertion."""
    assert CONTAINMENT_ROSTER == EXPECTED_STUDENTS
    assert len(CONTAINMENT_ROSTER) == 19


# --- exit gate: the app's outer boundary -------------------------------------


def test_tts_with_a_full_student_name_is_blocked(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_PRIVACY_LOG_PATH", str(tmp_path / "privacy.ndjson"))
    decision = check_exit(
        ExitRequest(
            surface="tts",
            destination="rime",
            payload_text="Marco Bianchi read beautifully today.",
            student_names=tuple(CONTAINMENT_ROSTER),
        )
    )
    assert decision.allowed is False
    assert decision.blocked_reason == "publication_safety_blocked"


def test_every_roster_name_is_individually_blocked_at_the_tts_gate(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_PRIVACY_LOG_PATH", str(tmp_path / "privacy.ndjson"))
    for name in CONTAINMENT_ROSTER:
        decision = check_exit(
            ExitRequest(
                surface="tts",
                destination="rime",
                payload_text=f"Please welcome {name} to the front of the class.",
                student_names=tuple(CONTAINMENT_ROSTER),
            )
        )
        assert decision.allowed is False, name


def test_name_free_tts_payload_is_allowed(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_PRIVACY_LOG_PATH", str(tmp_path / "privacy.ndjson"))
    decision = check_exit(
        ExitRequest(
            surface="tts",
            destination="rime",
            payload_text="Buongiorno! Oggi parliamo della nostra routine quotidiana.",
            student_names=tuple(CONTAINMENT_ROSTER),
        )
    )
    assert decision.allowed is True


def test_payload_carrying_student_ids_is_blocked(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_PRIVACY_LOG_PATH", str(tmp_path / "privacy.ndjson"))
    decision = check_exit(
        ExitRequest(
            surface="tts",
            destination="rime",
            payload_text="Reading update for the class.",
            student_ids=("student-abc-123",),
            student_names=tuple(CONTAINMENT_ROSTER),
        )
    )
    assert decision.allowed is False


def test_privacy_log_records_the_decision_but_never_a_name(monkeypatch, tmp_path):
    """The gate logs hashed/count metadata only — a blocked payload's text
    (and therefore any student name) must never land in the log."""
    log_path = tmp_path / "privacy.ndjson"
    monkeypatch.setenv("LV_PRIVACY_LOG_PATH", str(log_path))
    check_exit(
        ExitRequest(
            surface="tts",
            destination="rime",
            payload_text="Marco Bianchi read beautifully today.",
            student_names=tuple(CONTAINMENT_ROSTER),
        )
    )
    assert log_path.exists(), "exit decision must be logged"
    log_text = log_path.read_text(encoding="utf-8")
    assert log_text.strip()
    for name in CONTAINMENT_ROSTER:
        assert name not in log_text, name
        first = name.split()[0]
        assert first not in log_text, first


# --- safeguarding: RED never reaches shareable stores ------------------------


class _RecordingPipeline:
    def __init__(self):
        self.calls: list[dict] = []

    def capture(self, **kwargs):
        self.calls.append(kwargs)
        return {"observation_stored": True, "observation": dict(kwargs)}


def test_red_disclosure_is_classified_red():
    assert classify_severity(RED_TRANSCRIPT).tier == RED
    assert classify_severity(GREEN_TRANSCRIPT).tier == GREEN


def test_red_capture_never_touches_the_lens_pipeline(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path))
    pipeline = _RecordingPipeline()
    result = capture_with_safeguarding(
        pipeline,
        student_id="student-x",
        teacher_id="t-gauntlet",
        raw_transcript=RED_TRANSCRIPT,
        template_type="general",
    )
    assert pipeline.calls == [], "RED content must never enter the lens store"
    assert result["restricted"] is True
    assert result["observation_stored"] is False
    assert result["stored_in"] == "safeguarding/restricted.ndjson"
    assert (tmp_path / "safeguarding" / "restricted.ndjson").exists()


def test_red_notification_is_content_free(monkeypatch, tmp_path):
    """Coordinators get a pointer, never the disclosure text itself."""
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path))
    capture_with_safeguarding(
        _RecordingPipeline(),
        student_id="student-x",
        teacher_id="t-gauntlet",
        raw_transcript=RED_TRANSCRIPT,
        template_type="general",
    )
    safeguarding_dir = tmp_path / "safeguarding"
    for path in safeguarding_dir.iterdir():
        if path.name == "restricted.ndjson":
            continue  # the restricted ledger itself holds the content — by design
        assert RED_TRANSCRIPT not in path.read_text(encoding="utf-8"), path.name


def test_green_capture_delegates_to_the_pipeline_unchanged(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path))
    pipeline = _RecordingPipeline()
    result = capture_with_safeguarding(
        pipeline,
        student_id="student-y",
        teacher_id="t-gauntlet",
        raw_transcript=GREEN_TRANSCRIPT,
        template_type="general",
    )
    assert len(pipeline.calls) == 1
    assert pipeline.calls[0]["raw_transcript"] == GREEN_TRANSCRIPT
    assert result["restricted"] is False
    assert result["safeguarding"]["tier"] == GREEN


# --- voice containment --------------------------------------------------------


def _voice_roster(gauntlet_env) -> list[dict]:
    return [
        {"student_id": sid, "display_name": name}
        for name, sid in gauntlet_env["student_ids"].items()
    ]


def test_voice_detection_resolves_a_spoken_name_locally(gauntlet_env):
    detection = detect_student_detailed(
        "Marco Bianchi finished the reading task early", _voice_roster(gauntlet_env)
    )
    assert detection.match_quality == "exact"
    assert detection.display_name == "Marco Bianchi"
    assert detection.student_id == gauntlet_env["student_ids"]["Marco Bianchi"]


def test_voice_detection_does_not_invent_a_student_for_unknown_names(gauntlet_env):
    detection = detect_student_detailed(
        "Rodrigo asked a great question about the calendar", _voice_roster(gauntlet_env)
    )
    assert detection.student_id is None
    assert detection.match_quality is None


def test_voice_detection_reports_ambiguity_instead_of_guessing(gauntlet_env):
    """Two roster students named Marco/Matteo-like tokens must not be
    silently merged — but a clean first name resolves. Pin both."""
    roster = _voice_roster(gauntlet_env)
    clean = detect_student_detailed("Nora counted to twenty today", roster)
    assert clean.match_quality == "exact"
    assert clean.display_name == "Nora Rossi"


# --- artifact sweep: nothing exportable carries a name -----------------------


def test_full_artifact_sweep_contains_no_roster_name(gauntlet_env):
    """Capstone: lesson plan + revision + stripped parent report, generated
    from the seeded roster, swept against all 19 names at once."""
    from src.education.parent_report import ParentReportGenerator, render_parent_report_html
    from src.lingua_viva.lesson_materials import (
        _apply_deterministic_revision,
        _deterministic_lesson_plan,
        load_curriculum_knowledge,
    )
    from src.education.content_differentiator import LessonInput

    lesson = LessonInput(
        ib_programme="PYP",
        subject="language",
        unit_title="How we express ourselves",
        topic="Describing daily routines in Italian",
        atl_skills=["communication"],
        cefr_target="A2",
        duration_minutes=45,
    )
    entries = load_curriculum_knowledge(lesson.subject, lesson.topic)
    plan = _deterministic_lesson_plan(lesson, entries, None)
    revised = _apply_deterministic_revision(plan, "add a song to the warmup")

    draft = ParentReportGenerator(gauntlet_env["store"]).generate_draft(
        gauntlet_env["marco_id"], gauntlet_env["teacher_id"]
    )
    from src.web import _strip_parent_output

    stripped_html = render_parent_report_html(
        {
            "student_name": "",
            "strengths": [_strip_parent_output(s, CONTAINMENT_ROSTER) for s in draft.strengths],
            "growth_areas": [_strip_parent_output(g, CONTAINMENT_ROSTER) for g in draft.growth_areas],
            "home_activities": [_strip_parent_output(a, CONTAINMENT_ROSTER) for a in draft.home_activities],
        }
    )

    for artifact in (json.dumps(plan), json.dumps(revised), stripped_html):
        for name in CONTAINMENT_ROSTER:
            assert name not in artifact, name
