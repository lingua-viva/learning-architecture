"""U18 — admin questions over the student lens STORE, through the contract.

Deterministic, no model. Every result says scored / targets / cannot_tell /
empty_reason. Fixture data is fictional and lives only here.
"""

from __future__ import annotations

import pytest

from src.education.student_lens import StudentLensStore
from src.lingua_viva import lens_query as lq
from src.lingua_viva.data_in_contracts import ExtractedField, ExtractionResult
from src.lingua_viva.lens_field_contract import resolve
from src.lingua_viva.student_lens_writer import write_student_lens


def _field(path, value, status="verified"):
    return ExtractedField(field_path=path, value=value, confidence=0.9,
                          supporting_chunk_ids=["c1"], status=status)


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path))
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "lenses.db"))
    s = StudentLensStore(db_path=tmp_path / "lenses.db")
    yield s
    s.close()


def _seed(store):
    a = store.create_lens(student_id="s-ada", display_name="Ada Test", grade_level="G3", campus="North")
    b = store.create_lens(student_id="s-ben", display_name="Ben Test", grade_level="G3", campus="North")
    c = store.create_lens(student_id="s-cai", display_name="Cai Test", grade_level="G4", campus="South")
    # Ada: needs + a strategy + CEFR + strengths
    write_student_lens(ExtractionResult("student_lens", [
        _field("support_profile.categories.learning_and_cognition.needs", "needs a visual schedule"),
        _field("support_profile.categories.learning_and_cognition.strategies_worked", "visual schedule helped"),
        _field("cefr_snapshot.reading", "A2"),
        _field("academic_strengths", "reading comprehension"),
    ], [], ["t.txt"]), store=store, hint={"student_id": a})
    # Ben: needs in two categories, NO strategy anywhere
    write_student_lens(ExtractionResult("student_lens", [
        _field("support_profile.categories.executive_functioning.needs", "loses the thread"),
        _field("support_profile.categories.social_skills.evidence", "needs reminders to take turns"),
    ], [], ["t.txt"]), store=store, hint={"student_id": b})
    store.update_rti_tier(b, 2, trigger="test")
    # Cai: empty
    return a, b, c


def test_every_path_the_engine_reads_is_declared():
    assert all(resolve(p) is not None for p in lq._PATHS_READ)


def test_zero_students_is_a_verdict_not_a_zero(store):
    out = lq.run_question(store, "L5")
    assert out["scored"] is False and out["targets"] == 0
    assert out["empty_reason"]
    assert lq.exit_code(out) == lq.EXIT_NOT_ENOUGH_DATA


def test_census_counts_and_names_empty_lenses(store):
    _seed(store)
    out = lq.run_question(store, "L2")
    assert out["scored"] and out["targets"] == 3
    assert out["by_grade"] == {"G3": 2, "G4": 1}
    assert out["empty_count"] == 1
    assert out["empty_lenses"] == [lq.aron_ref("s-cai")]     # ARON by default
    assert lq.run_question(store, "L2", names=True)["empty_lenses"] == ["Cai Test"]


def test_needs_per_category_and_gap(store):
    _seed(store)
    needs = lq.run_question(store, "L5")
    assert needs["per_category"]["learning_and_cognition"] == 1
    assert needs["per_category"]["executive_functioning"] == 1
    assert needs["per_category"]["social_skills"] == 1
    gap = lq.run_question(store, "L7", names=True)
    assert gap["count"] == 1
    assert gap["students"][0]["student"] == "Ben Test"
    assert set(gap["students"][0]["categories_without_strategy"]) == {"executive_functioning", "social_skills"}


def test_cefr_distribution_and_missing(store):
    _seed(store)
    out = lq.run_question(store, "L8", names=True)
    assert out["distribution"]["reading"] == {"A2": 1}
    assert set(out["no_cefr_evidence"]) == {"Ben Test", "Cai Test"}


def test_rti_elevated(store):
    _seed(store)
    out = lq.run_question(store, "L10", names=True)
    assert out["elevated"] == [{"student": "Ben Test", "tier": 2}]
    assert out["distribution"] == {"1": 2, "2": 1}


def test_coverage_is_over_declared_fields_only(store):
    _seed(store)
    out = lq.run_question(store, "L3")
    assert out["declared_fields"] > 50
    assert out["per_field"]["cefr_snapshot.reading"]["populated"] == 1
    assert out["per_field"]["academic_strengths"]["populated"] == 1
    assert all(resolve(p) is not None for p in out["per_field"])


def test_search_cites_entries(store):
    _seed(store)
    out = lq.run_question(store, "L11", names=True, term="visual schedule")
    assert out["count"] == 1 and out["hits"][0]["student"] == "Ada Test"
    paths = {c["path"] for c in out["hits"][0]["citations"]}
    assert "support_profile.categories.learning_and_cognition.needs" in paths
    assert "support_profile.categories.learning_and_cognition.strategies_worked" in paths
    empty = lq.run_question(store, "L11", term="")
    assert empty["scored"] is False and "Empty" in empty["empty_reason"]


def test_dossier_over_declared_paths(store):
    _seed(store)
    out = lq.run_question(store, "L12", names=True, student="Ada Test")
    assert out["scored"]
    assert "cefr_snapshot.reading" in out["declared_fields_present"]
    assert "cefr_snapshot.writing" in out["declared_fields_absent"]
    assert out["observation_count"] == 1
    missing = lq.run_question(store, "L12", student="nobody")
    assert missing["scored"] is False


def test_staleness_reports_unreadable_dates_as_cannot_tell(store):
    _seed(store)
    store._conn.execute("UPDATE students SET updated_at = 'garbage' WHERE student_id = 's-cai'")
    store._conn.commit()
    out = lq.run_question(store, "L4", names=True, days=0)
    assert out["cannot_tell"] == ["Cai Test"]
    assert out["stale_count"] + out["recent_count"] + len(out["cannot_tell"]) == 3


def test_unknown_question_is_an_error(store):
    with pytest.raises(ValueError):
        lq.run_question(store, "L99")
