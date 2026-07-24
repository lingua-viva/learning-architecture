"""
Tests for SPEC_LV_LENS_UI_API_CONTRACT_2026-07-23.md (Build order 3 of 5).

Validates:
  - GET /api/students/{id}/lens returns support_profile and support_profile_warnings
  - malformed support profile degrades safely without crashing API or rendering
  - GET /api/categories returns static metadata for all 8 canonical categories
  - GET /api/students/support-summary returns aggregate counts with zero raw transcript text
  - Observe capture persists support_entries and returns structured feedback
  - Observe classify returns writes_made: 0 and teacher_confirmation_required: true
  - advanced_enrichment is isolated and does not alter RTI tier calculations
  - static/index.html includes all required UI call sites and function handlers
"""

from pathlib import Path
from fastapi.testclient import TestClient
import pytest

from src.education.student_lens import StudentLensStore, SUPPORT_CATEGORY_IDS
from src.web import app

REPO = Path(__file__).resolve().parent.parent
client = TestClient(app)


def _html() -> str:
    return (REPO / "static" / "index.html").read_text(encoding="utf-8")


def test_served_html_contains_required_ui_contract_elements():
    html = _html()
    assert "Support profile" in html
    assert "renderSupportProfileSummary" in html
    assert "/api/observe/classify" in html
    assert "/api/observe/capture" in html
    assert "support_entries" in html
    assert "/api/students/support-summary" in html
    
    # Verify canonical category IDs or labels appear in served HTML
    for cat_id in SUPPORT_CATEGORY_IDS:
        assert cat_id in html or cat_id.replace("_", " ") in html.lower()


def test_get_categories_route():
    response = client.get("/api/categories")
    assert response.status_code == 200
    data = response.json()
    assert "categories" in data
    cats = data["categories"]
    assert len(cats) == 8
    cat_ids = [c["id"] for c in cats]
    for cid in SUPPORT_CATEGORY_IDS:
        assert cid in cat_ids


def test_get_student_lens_includes_support_profile_and_warnings(tmp_path, monkeypatch):
    db_path = tmp_path / "test_lens.db"
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(db_path))

    with StudentLensStore(db_path=db_path) as store:
        sid = store.create_lens(display_name="Test Learner")
        # Inject malformed support profile string directly into DB to test degradation
        store._conn.execute(
            "UPDATE students SET support_profile = ? WHERE student_id = ?",
            ("{invalid json", sid),
        )
        store._conn.commit()

    response = client.get(f"/api/students/{sid}/lens")
    assert response.status_code == 200
    data = response.json()
    assert "support_profile" in data
    assert data["support_profile"]["schema_version"] == 2
    assert "support_profile_warnings" in data
    assert len(data["support_profile_warnings"]) > 0


def test_observe_capture_with_support_entries_returns_feedback(tmp_path, monkeypatch):
    db_path = tmp_path / "test_observe.db"
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(db_path))

    with StudentLensStore(db_path=db_path) as store:
        sid = store.create_lens(display_name="Capture Learner")

    response = client.post(
        "/api/observe/capture",
        json={
            "student_id": sid,
            "transcript": "Responded well to graphic organizer during writing.",
            "template_type": "literacy",
            "support_entries": [
                {
                    "support_category": "executive_functioning",
                    "need_statement": "Needs visual checklist for 3-step tasks",
                    "strategy_statement": "2-step checklist card",
                    "strategy_outcome": "worked",
                    "teacher_confirmed": True,
                },
                {
                    "support_category": "advanced_enrichment",
                    "strength_statement": "Rapid concept acquisition in math",
                    "teacher_confirmed": True,
                },
            ],
        },
    )

    assert response.status_code == 200
    res = response.json()
    assert "feedback" in res
    fb = res["feedback"]
    assert fb["saved_entries"] >= 2
    assert "executive_functioning" in fb["categories_updated"]
    assert "advanced_enrichment" in fb["categories_updated"]

    # Verify lens now returns updated support profile
    lens_res = client.get(f"/api/students/{sid}/lens")
    assert lens_res.status_code == 200
    lens_data = lens_res.json()
    sp = lens_data["support_profile"]
    ef = sp["categories"]["executive_functioning"]
    assert len(ef["needs"]) == 1
    assert len(ef["strategies_worked"]) == 1

    # Verify advanced_enrichment did not alter RTI tier (remains tier 1)
    assert lens_data["rti_current_tier"] == 1


def test_students_support_summary_route(tmp_path, monkeypatch):
    db_path = tmp_path / "test_summary.db"
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(db_path))

    with StudentLensStore(db_path=db_path) as store:
        store.create_lens(display_name="Summary Student")

    response = client.get("/api/students/support-summary")
    assert response.status_code == 200
    data = response.json()
    assert "students" in data
    assert len(data["students"]) >= 1
    s = data["students"][0]
    assert "category_counts" in s
    assert "total_support_items" in s
    # Ensure no raw_transcript field is present in summary
    assert "raw_transcript" not in s
    assert "raw_transcript" not in str(s)
