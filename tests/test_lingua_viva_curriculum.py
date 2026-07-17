from src.lingua_viva.curriculum import CurriculumService


def test_curriculum_overview_reports_grade_bands_and_source_status():
    overview = CurriculumService().get_overview()

    assert overview["source_status"]["badge"] == "Authoritative source: Manuale v1"
    assert len(overview["grade_bands"]) >= 5
    assert overview["grade_bands"][2]["grade"] == "G3"
    assert overview["grade_bands"][2]["unit_count"] >= 1


def test_curriculum_grade_units_use_designed_to_language():
    units = CurriculumService().get_grade("3")

    assert units
    assert units[0]["grade"] == "G3"
    assert units[0]["cefr_language"].startswith("Designed")
    assert "achieve" not in units[0]["cefr_language"].lower()
    assert "Manuale" in units[0]["source_citation"]
