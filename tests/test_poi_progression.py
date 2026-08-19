"""Tests for src/lingua_viva/poi_progression.py + the artifacts/PoI routes
(W3, 2026-08-09).

Synthetic students only (Nora Rossi, Rafael — established synthetic
fixture names per publication-policy.md), demonstrating a realistic
multi-iteration progression. SQLite goes to tmp_path via the hermetic
LV_STUDENT_DB_PATH from tests/conftest.py or an explicit db_path.
"""

from __future__ import annotations

import pytest

from src.lingua_viva.poi_progression import (
    PROGRESSION_PHASES,
    TRANSDISCIPLINARY_THEMES,
    PoIProgressionStore,
    default_units_for_year,
    phase_index,
)


@pytest.fixture()
def store(tmp_path):
    with PoIProgressionStore(db_path=tmp_path / "poi.db") as s:
        yield s


def _seed_nora(store: PoIProgressionStore) -> str:
    """Nora Rossi (synthetic): steady multi-iteration growth in oral
    communication across the 'Who we are' G3 unit — beginning →
    developing → developing → consolidating."""
    store.seed_default_units("G3")
    student_id = "stu-nora-rossi"
    steps = [
        ("act-1", "beginning", "Single words, needed prompting", "2026-05-04T09:00:00+00:00"),
        ("act-2", "developing", "Short phrases with support", "2026-05-18T09:00:00+00:00"),
        ("act-3", "developing", "Phrases, more spontaneous", "2026-06-01T09:00:00+00:00"),
        ("act-4", "consolidating", "Full sentences in pair talk", "2026-06-15T09:00:00+00:00"),
    ]
    for activity_id, tier, note, when in steps:
        store.record_iteration(
            student_id=student_id, unit_id="poi-g3-1",
            objective="oral_communication", activity_id=activity_id,
            tier_demonstrated=tier, evidence_note=note, recorded_at=when,
        )
    return student_id


def _seed_rafael(store: PoIProgressionStore) -> str:
    """Rafael (synthetic): plateau at 'developing' in written production
    for three iterations — the needs-consolidation case — plus healthy
    progress in reading comprehension."""
    store.seed_default_units("G3")
    student_id = "stu-rafael"
    for index, when in enumerate(
        ("2026-05-05T09:00:00+00:00", "2026-05-19T09:00:00+00:00", "2026-06-02T09:00:00+00:00")
    ):
        store.record_iteration(
            student_id=student_id, unit_id="poi-g3-3",
            objective="written_production", activity_id=f"act-w{index + 1}",
            tier_demonstrated="developing",
            evidence_note="Same sentence patterns, no new structures",
            recorded_at=when,
        )
    store.record_iteration(
        student_id=student_id, unit_id="poi-g3-3",
        objective="reading_comprehension", activity_id="act-r1",
        tier_demonstrated="developing", evidence_note="Understood main idea",
        recorded_at="2026-05-12T09:00:00+00:00",
    )
    store.record_iteration(
        student_id=student_id, unit_id="poi-g3-3",
        objective="reading_comprehension", activity_id="act-r2",
        tier_demonstrated="consolidating", evidence_note="Answered inference question",
        recorded_at="2026-06-09T09:00:00+00:00",
    )
    return student_id


# ── Structure ─────────────────────────────────────────────────────────────

def test_pyp_structure_constants():
    assert len(TRANSDISCIPLINARY_THEMES) == 6
    assert PROGRESSION_PHASES == ("beginning", "developing", "consolidating", "secure")
    assert phase_index("secure") == 3
    with pytest.raises(ValueError):
        phase_index("excellent")


def test_default_units_cover_all_six_themes(store):
    units = default_units_for_year("G3")
    assert len(units) == 6
    assert {u["theme"] for u in units} == set(TRANSDISCIPLINARY_THEMES)
    store.seed_default_units("3")  # numeric form normalizes to G3
    assert len(store.list_units("G3")) == 6
    unit = store.get_unit("poi-g3-1")
    assert unit["objectives"] == ["oral_communication", "reading_comprehension",
                                  "written_production"]


def test_register_unit_rejects_invalid_theme(store):
    with pytest.raises(ValueError):
        store.register_unit(unit_id="x", year_level="G3", theme="Not a theme",
                            title="Bad")


# ── Record → summary round trip ───────────────────────────────────────────

def test_record_and_round_trip_nora(store):
    student_id = _seed_nora(store)
    summary = store.objective_summary(student_id, "poi-g3-1", "oral_communication")
    assert summary["iteration_count"] == 4
    assert summary["current_level"] == "consolidating"
    assert summary["trend"] == "progressing"
    assert [h["tier_demonstrated"] for h in summary["history"]] == [
        "beginning", "developing", "developing", "consolidating",
    ]
    assert summary["history"][0]["evidence_note"] == "Single words, needed prompting"


def test_record_validates_tier_and_objective(store):
    store.seed_default_units("G3")
    with pytest.raises(ValueError):
        store.record_iteration(student_id="s", unit_id="poi-g3-1",
                               objective="oral_communication", activity_id="a",
                               tier_demonstrated="amazing")
    with pytest.raises(ValueError):
        store.record_iteration(student_id="s", unit_id="poi-g3-1",
                               objective="interpretive_dance", activity_id="a",
                               tier_demonstrated="beginning")
    with pytest.raises(ValueError):
        store.record_iteration(student_id="", unit_id="poi-g3-1",
                               objective="oral_communication", activity_id="a",
                               tier_demonstrated="beginning")


# ── Trend computation ─────────────────────────────────────────────────────

def test_trend_cases():
    trend = PoIProgressionStore._trend
    assert trend([0]) == "insufficient_data"
    assert trend([0, 1]) == "progressing"
    assert trend([0, 1, 1, 2]) == "progressing"
    assert trend([2, 1]) == "needs_consolidation"
    assert trend([1, 1]) == "plateauing"
    # Three flat iterations below consolidating → needs consolidation.
    assert trend([1, 1, 1]) == "needs_consolidation"
    # Flat at consolidating/secure is a healthy plateau.
    assert trend([2, 2, 2]) == "plateauing"
    assert trend([3, 3, 3, 3]) == "plateauing"


def test_rafael_plateau_flagged_for_consolidation(store):
    student_id = _seed_rafael(store)
    writing = store.objective_summary(student_id, "poi-g3-3", "written_production")
    assert writing["trend"] == "needs_consolidation"
    reading = store.objective_summary(student_id, "poi-g3-3", "reading_comprehension")
    assert reading["trend"] == "progressing"

    summary = store.student_summary(student_id)
    assert len(summary["objectives"]) == 2
    targets = [(c["unit_id"], c["objective"]) for c in summary["consolidate_next"]]
    assert ("poi-g3-3", "written_production") in targets
    assert ("poi-g3-3", "reading_comprehension") not in targets
    assert summary["consolidate_next"][0]["objective"] == "written_production"
    assert "How we express ourselves" in summary["themes_touched"]


def test_student_summary_empty_student(store):
    summary = store.student_summary("stu-nobody")
    assert summary["objectives"] == []
    assert summary["consolidate_next"] == []


def test_summaries_omit_history_in_student_summary(store):
    student_id = _seed_nora(store)
    summary = store.student_summary(student_id)
    for objective in summary["objectives"]:
        assert "history" not in objective


# ── Routes (TestClient) ───────────────────────────────────────────────────

@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "state" / "student_lenses.db"))
    from fastapi.testclient import TestClient
    from src.web import app
    return TestClient(app)


def test_route_poi_record_and_progression(client, tmp_path):
    with PoIProgressionStore() as store:
        store.seed_default_units("G3")
    response = client.post("/api/poi/record", json={
        "student_id": "stu-nora-rossi",
        "unit_id": "poi-g3-1",
        "objective": "oral_communication",
        "activity_id": "act-1",
        "tier_demonstrated": "developing",
        "evidence_note": "Short phrases with support",
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "recorded"
    assert body["summary"]["current_level"] == "developing"

    progression = client.get("/api/poi/progression/stu-nora-rossi")
    assert progression.status_code == 200
    data = progression.json()
    assert data["student_id"] == "stu-nora-rossi"
    assert data["objectives"][0]["objective"] == "oral_communication"


def test_route_poi_record_invalid_tier_422(client):
    response = client.post("/api/poi/record", json={
        "student_id": "s", "unit_id": "u", "objective": "o",
        "activity_id": "a", "tier_demonstrated": "wrong",
    })
    assert response.status_code == 422


def test_route_coursework_pack_and_list(client, tmp_path, seeded_curriculum):
    response = client.post("/api/artifacts/coursework-pack", json={
        "class_id": "G3", "unit_id": "g3-unit-1", "activities_per_unit": 1,
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "generated"
    assert {f["audience"] for f in body["files"]} == {"teacher", "student"}
    state = tmp_path / "state"
    for entry in body["files"]:
        assert entry["path"].startswith(str(state / "artifacts" / "coursework"))

    listing = client.get("/api/artifacts/list")
    assert listing.status_code == 200
    listed = listing.json()
    assert listed["count"] >= 2
    names = {f["name"] for f in listed["files"]}
    assert any(name.endswith("_teacher.pdf") for name in names)


def test_route_coursework_pack_unknown_class_404(client):
    response = client.post("/api/artifacts/coursework-pack",
                           json={"class_id": "G99"})
    assert response.status_code == 404
