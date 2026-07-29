from __future__ import annotations

from src.lingua_viva.grounding.build import build_grounding_result
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
    assert result.gir.uncertainty_claims == 1
