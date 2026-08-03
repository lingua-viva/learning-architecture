from __future__ import annotations

from src.education.student_lens import Observation, StudentLensStore
from src.lingua_viva.grounding.build import build_grounding_result
from src.lingua_viva.voice_tone import resolve_voice_tone
from src.lingua_viva.sources.ledger import compute_source_record_id, now_iso, upsert
from src.lingua_viva.sources.schema import SourceRecord


def test_grounding_uses_ledger_tier_and_blocks_external(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path))
    observed_at = now_iso()
    source_id = compute_source_record_id("drive", "folder", "container", "doc")
    upsert(SourceRecord(
        source_record_id=source_id,
        source_type="drive",
        source_id="folder",
        container="container",
        record_id="doc",
        title="Drive lesson",
        uri="gdrive://doc",
        retrieval_scope="content",
        created_at=observed_at,
        observed_at=observed_at,
        provenance="import",
    ))
    result = build_grounding_result(trace={"trace_id": "T1", "session_id": "S1"}, query_text="lesson", content="Use the lesson.")
    assert result.tier_used == "drive"
    assert result.sources_used[0].source_record_id == source_id
    assert result.tier_attempts[-1].tier == "external"
    assert result.tier_attempts[-1].status == "blocked"
    assert result.gir.score == 1.0


def test_grounding_gir_penalizes_unsupported_claims(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path))
    result = build_grounding_result(trace={"trace_id": "T2"}, query_text="x", content="This is certain. Maybe this is uncertain.")
    assert result.tier_used == "none"
    assert result.gir.total_claims == 2
    assert result.gir.unsupported_claims == 1
    assert result.gir.uncertainty_claims == 0


def test_grounding_floors_low_confidence_synthesis_even_with_citation(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path))
    result = build_grounding_result(
        trace={"trace_id": "T3", "source_citations": ["Manuale v1"]},
        query_text="How should I teach an Italian lesson?",
        content="Ollama appears to be down. Check if it is running, then try again.",
        synthesis_confidence=0.0,
    )
    assert result.tier_used == "knowledge"
    assert result.gir.total_claims == 2
    assert result.gir.unsupported_claims == 2
    assert result.gir.score == 0.0


def test_grounding_ignores_irrelevant_ledger_records(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path))
    observed_at = now_iso()
    upsert(SourceRecord(
        source_record_id=compute_source_record_id("drive", "folder", "container", "doc"),
        source_type="drive",
        source_id="folder",
        container="container",
        record_id="doc",
        title="Drive lesson",
        uri="gdrive://doc",
        retrieval_scope="content",
        created_at=observed_at,
        observed_at=observed_at,
        provenance="import",
        summary="Italian curriculum lesson material",
    ))
    result = build_grounding_result(
        trace={"trace_id": "T4"},
        query_text="Which bus route should a new family take tomorrow?",
        content="The bus route is number 42.",
    )
    assert result.tier_used == "none"
    assert result.sources_used == []
    assert result.gir.unsupported_claims == 1
    assert result.gir.score == 0.0


def test_grounding_does_not_treat_generic_manuale_as_universal_source(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path))
    result = build_grounding_result(
        trace={"trace_id": "T5", "source_citations": ["Manuale v1"]},
        query_text="What is the latest local train disruption near school?",
        content="The train is delayed.",
    )
    assert result.tier_used == "none"
    assert result.gir.score == 0.0


def test_gir_v2_flags_fabricated_observation_id_despite_relevant_source(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path))
    observed_at = now_iso()
    upsert(SourceRecord(
        source_record_id=compute_source_record_id("local", "lesson", "Marco notes", "doc"),
        source_type="local",
        source_id="lesson",
        container="Marco notes",
        record_id="doc",
        title="Marco observation evidence",
        uri="file://marco-observation.md",
        retrieval_scope="content",
        created_at=observed_at,
        observed_at=observed_at,
        provenance="scan",
        summary="Marco observation evidence for speaking practice",
    ))

    result = build_grounding_result(
        trace={"trace_id": "T6", "scope_student_name": "Marco"},
        query_text="Marco observation evidence",
        content="Marco should do speaking practice based on OBS-DOES-NOT-EXIST.",
    )

    assert result.tier_used == "local"
    assert result.gir.method == "claim_support_v2_linkage"
    assert result.gir.v1_score == 1.0, "v1 regression sentinel: one relevant source used to grant blanket support"
    assert result.gir.score < 0.5
    assert "OBS-DOES-NOT-EXIST" in result.gir.fabricated_identifiers
    assert resolve_voice_tone(result.gir.score)["tone"] != "plain"


def test_gir_v2_honest_zero_source_hedge_scores_at_least_as_well_as_fabrication(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path))
    observed_at = now_iso()
    upsert(SourceRecord(
        source_record_id=compute_source_record_id("local", "lesson", "Marco notes", "doc"),
        source_type="local",
        source_id="lesson",
        container="Marco notes",
        record_id="doc",
        title="Marco observation evidence",
        uri="file://marco-observation.md",
        retrieval_scope="content",
        created_at=observed_at,
        observed_at=observed_at,
        provenance="scan",
        summary="Marco observation evidence for speaking practice",
    ))
    fabricated = build_grounding_result(
        trace={"trace_id": "T7A", "scope_student_name": "Marco"},
        query_text="Marco observation evidence",
        content="Marco should do speaking practice based on OBS-DOES-NOT-EXIST.",
    )

    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "empty"))
    honest = build_grounding_result(
        trace={"trace_id": "T7B", "scope_student_name": "Marco"},
        query_text="Marco observations",
        content="I don't have observations for Marco yet. He may benefit from short speaking practice.",
    )

    assert fabricated.gir.v1_score == 1.0, "v1 regression sentinel: fabricated grounded answer scored perfectly"
    assert honest.tier_used == "none"
    assert honest.gir.score >= fabricated.gir.score
    assert honest.gir.uncertainty_claims == 0


def test_gir_v2_flags_wrong_student_observation_id(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path))
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "student_lenses.db"))
    store = StudentLensStore()
    try:
        marco_id = store.create_lens(student_id="student-marco", display_name="Marco")
        nora_id = store.create_lens(student_id="student-nora", display_name="Nora")
        store.append_observation(Observation(
            observation_id="OBS-NORA-REAL",
            student_id=nora_id,
            teacher_id="teacher-demo",
            template_type="cefr",
            raw_transcript="Nora used a sentence frame during partner work.",
            cefr_dimension="speaking",
            cefr_level_observed="A2",
        ))
    finally:
        store.close()

    result = build_grounding_result(
        trace={"trace_id": "T8", "scope_student_id": marco_id, "scope_student_name": "Marco"},
        query_text="Marco speaking support",
        content="Marco should use sentence frames based on OBS-NORA-REAL.",
    )

    assert result.gir.v1_score == 0.0, "v1 regression sentinel: with no source, wrong-student citation stayed unsupported only by accident"
    assert "OBS-NORA-REAL" in result.gir.fabricated_identifiers
    assert result.gir.unsupported_claims >= 1
