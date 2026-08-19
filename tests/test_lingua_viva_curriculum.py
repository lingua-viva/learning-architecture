import pytest
from fastapi.testclient import TestClient

from src.lingua_viva.curriculum import (
    CurriculumService,
    add_unit,
    delete_unit,
    update_unit,
)
from src.web import app


client = TestClient(app)


def test_curriculum_overview_reports_grade_bands_and_source_status(seeded_curriculum):
    overview = CurriculumService().get_overview()

    assert overview["source_status"]["badge"] == "Authoritative source: Manuale v1"
    assert len(overview["grade_bands"]) >= 5
    assert overview["grade_bands"][2]["grade"] == "G3"
    assert overview["grade_bands"][2]["unit_count"] >= 1


def test_curriculum_grade_units_use_designed_to_language(seeded_curriculum):
    units = CurriculumService().get_grade("3")

    assert units
    assert units[0]["grade"] == "G3"
    assert units[0]["cefr_language"].startswith("Designed")
    assert "achieve" not in units[0]["cefr_language"].lower()
    assert "Manuale" in units[0]["source_citation"]


def test_fresh_install_has_no_units():
    """Issue 5: no fabricated starter-theme units. An empty matrix means an
    empty curriculum — teachers create units themselves."""
    service = CurriculumService()

    assert service.get_grade("G3") == []
    overview = service.get_overview()
    assert all(band["unit_count"] == 0 for band in overview["grade_bands"])


def test_add_update_delete_unit_roundtrip():
    unit = add_unit("3", "Il mio quartiere", focus="Places vocabulary", cefr_target="A2 consolidation")
    assert unit["unit_id"] == "g3-il-mio-quartiere"
    assert unit["grade"] == "G3"
    assert unit["source_status"] == "teacher_created"
    assert unit["cefr_language"] == "Designed to target A2 consolidation"

    # Visible through the read service (live matrix wins).
    assert CurriculumService().get_unit(unit["unit_id"])["title"] == "Il mio quartiere"

    updated = update_unit(unit["unit_id"], {"title": "Il quartiere", "cefr_target": ""})
    assert updated["title"] == "Il quartiere"
    assert updated["cefr_language"] == ""

    delete_unit(unit["unit_id"])
    with pytest.raises(KeyError):
        CurriculumService().get_unit(unit["unit_id"])


def test_add_unit_validates_grade_and_title():
    with pytest.raises(ValueError):
        add_unit("G99", "Ghost unit")
    with pytest.raises(ValueError):
        add_unit("G3", "   ")


def test_add_unit_dedupes_slug():
    first = add_unit("G3", "Ripasso")
    second = add_unit("G3", "Ripasso")
    assert first["unit_id"] == "g3-ripasso"
    assert second["unit_id"] == "g3-ripasso-2"


def test_update_unit_position_reorders_within_grade():
    a = add_unit("G3", "Unit A")
    b = add_unit("G3", "Unit B")
    other = add_unit("G2", "Other grade")

    update_unit(b["unit_id"], {"position": 0})

    g3_ids = [u["unit_id"] for u in CurriculumService().get_grade("G3")]
    assert g3_ids == [b["unit_id"], a["unit_id"]]
    # Other grades untouched.
    assert [u["unit_id"] for u in CurriculumService().get_grade("G2")] == [other["unit_id"]]


def test_unit_crud_routes():
    created = client.post("/api/curriculum/unit", json={
        "grade": "G3", "title": "Le stagioni", "focus": "Weather", "cefr_target": "A2",
    })
    assert created.status_code == 200, created.text
    unit_id = created.json()["unit_id"]
    assert unit_id == "g3-le-stagioni"

    fetched = client.get(f"/api/curriculum/unit/{unit_id}")
    assert fetched.status_code == 200
    assert fetched.json()["title"] == "Le stagioni"

    updated = client.put(f"/api/curriculum/unit/{unit_id}", json={"focus": "Seasons and weather"})
    assert updated.status_code == 200
    assert updated.json()["focus"] == "Seasons and weather"

    deleted = client.delete(f"/api/curriculum/unit/{unit_id}")
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True, "unit_id": unit_id}
    assert client.get(f"/api/curriculum/unit/{unit_id}").status_code == 404


def test_unit_crud_routes_reject_bad_input():
    assert client.post("/api/curriculum/unit", json={"grade": "G99", "title": "x"}).status_code == 400
    assert client.post("/api/curriculum/unit", json={"grade": "G3", "title": ""}).status_code == 400
    assert client.put("/api/curriculum/unit/nope", json={"title": "x"}).status_code == 404
    assert client.delete("/api/curriculum/unit/nope").status_code == 404
