"""Fleet query engine — locking tests over a synthetic 3-school fleet.

All students are fictional. The fleet exercises every verdict class:
scored answers, per-school empty_reason, cannot_tell (bad timestamps,
non-local identity queues), unreadable lens files, and the empty-fleet
NOT-ENOUGH-DATA exit. The parametrized test at the bottom locks all 30
QUESTION_MAP entries as runnable.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.lingua_viva.fleet_query import (
    EXIT_NOT_ENOUGH_DATA,
    EXIT_SCORED,
    QUESTION_MAP,
    exit_code,
    format_result,
    load_fleet,
    run_query,
    run_question,
)
from src.lingua_viva.governance import aron_ref

NOW = datetime.now(timezone.utc)
FRESH = NOW.isoformat()
RECENT = (NOW - timedelta(days=5)).isoformat()
STALE = "2025-01-01T00:00:00+00:00"


def _evidence(source_id: str, *, confidence: float = 0.9,
              added_by: str = "teacher-a", obs: bool = False) -> dict:
    ref = (
        {"type": "OBSERVATION", "obs_id": source_id}
        if obs else
        {"type": "DOCUMENT", "source_id": source_id, "path": f"/docs/{source_id}.pdf"}
    )
    return {
        "source_ref": ref,
        "confidence": confidence,
        "added_at": RECENT,
        "added_by": added_by,
    }


def _lens(student_id: str, display_name: str, profile: dict, *,
          created_at: str = RECENT, updated_at: str = FRESH,
          source_ids: list | None = None, observation_ids: list | None = None,
          merge_events: list | None = None) -> dict:
    return {
        "schema_version": "docpipe.lens.v1",
        "student_id": student_id,
        "display_name": display_name,
        "created_at": created_at,
        "updated_at": updated_at,
        "profile": profile,
        "metadata": {
            "source_ids": source_ids or [],
            "observation_ids": observation_ids or [],
            "merge_events": merge_events or [],
        },
    }


def _write_lens(root: Path, lens: dict) -> None:
    lens_dir = root / "lenses" / lens["student_id"]
    lens_dir.mkdir(parents=True, exist_ok=True)
    (lens_dir / "lens.json").write_text(
        json.dumps(lens, ensure_ascii=False), encoding="utf-8"
    )


@pytest.fixture()
def fleet(tmp_path: Path):
    roma = tmp_path / "roma"
    lyon = tmp_path / "lyon"
    berlin = tmp_path / "berlin"

    # --- Scuola Roma (IT) --------------------------------------------------
    _write_lens(roma, _lens(
        "stu-luca", "Lucà Rossi",
        {
            "learning_and_cognition": {
                "value": ["Needs support with reading fluency"],
                "evidence": [_evidence("src-report-1"),
                             _evidence("obs-11", added_by="teacher-b", obs=True)],
            },
            "emotional_regulation": {
                "value": ["Calms with quiet corner"],
                "evidence": [_evidence("src-report-1")],
            },
            "strategies_trialed": {
                "value": ["visual schedule", "peer reading"],
                "evidence": [_evidence("obs-11", obs=True)],
            },
            "academic_strengths": {
                "value": ["Progressi in matematica"],
                "evidence": [_evidence("src-report-1")],
            },
        },
        source_ids=["src-report-1"], observation_ids=["obs-11"],
        merge_events=[{"added_at": "2026-08-01T09:00:00+00:00"}],
    ))
    # Support gap + low confidence + single source + stale
    _write_lens(roma, _lens(
        "stu-marco", "Marco Bianchi",
        {
            "emotional_regulation": {
                "value": ["Escalates during transitions"],
                "evidence": [_evidence("src-report-2", confidence=0.4)],
            },
            "executive_functioning": {
                "value": ["Loses materials daily"],
                "evidence": [_evidence("src-report-2", confidence=0.3)],
            },
        },
        updated_at=STALE, created_at=STALE,
        source_ids=["src-report-2"],
    ))
    # Empty lens — zero evidence anywhere
    _write_lens(roma, _lens("stu-empty", "Sofia Verdi", {}))

    # --- École Lyon (FR) ---------------------------------------------------
    _write_lens(lyon, _lens(
        "stu-noemi", "Noëmi Villa",
        {
            "communication_and_language": {
                "value": ["Grande progresso in matematica orale"],
                "evidence": [_evidence("src-bulletin-1", added_by="teacher-c")],
            },
        },
        source_ids=["src-bulletin-1"], observation_ids=["obs-21"],
    ))
    # Duplicate-risk pair: same name, reversed order
    _write_lens(lyon, _lens("stu-anna1", "Anna Chang", {}))
    _write_lens(lyon, _lens("stu-anna2", "Chang Anna", {}))
    # Unparseable timestamp — staleness cannot_tell
    _write_lens(lyon, _lens(
        "stu-badts", "Elio Bruni", {}, updated_at="not-a-date",
    ))

    # --- Berlin (DE): no valid lenses, one unreadable file -----------------
    bad = berlin / "lenses" / "stu-corrupt"
    bad.mkdir(parents=True)
    (bad / "lens.json").write_text("{ this is not json", encoding="utf-8")

    config = tmp_path / "fleet.json"
    config.write_text(json.dumps({"schools": [
        {"school": "Scuola Roma", "country": "IT", "root": str(roma)},
        {"school": "École Lyon", "country": "FR", "root": str(lyon)},
        {"school": "Berlin International", "country": "DE", "root": str(berlin)},
    ]}), encoding="utf-8")
    return load_fleet(config)


# ---------------------------------------------------------------------------
# Census, coverage
# ---------------------------------------------------------------------------


def test_census_counts_per_school_and_country(fleet):
    result = run_query(fleet, "census")
    assert result["scored"] is True
    assert result["total_students"] == 7
    by_school = {s["school"]: s for s in result["by_school"]}
    assert by_school["Scuola Roma"]["students"] == 3
    assert by_school["École Lyon"]["students"] == 4
    assert by_school["Berlin International"]["students"] == 0
    assert result["by_country"] == {"IT": 3, "FR": 4}
    assert exit_code(result) == EXIT_SCORED


def test_census_empty_lenses_and_unreadable(fleet):
    result = run_query(fleet, "census")
    empty_arons = {e["aron"] for e in result["empty_lenses"]}
    assert aron_ref("stu-empty") in empty_arons
    assert aron_ref("stu-luca") not in empty_arons
    assert result["unreadable_total"] == 1
    by_school = {s["school"]: s for s in result["by_school"]}
    assert by_school["Berlin International"]["unreadable_lens_files"] == [
        "lenses/stu-corrupt/lens.json"
    ]


def test_census_hides_names_by_default(fleet):
    result = run_query(fleet, "census")
    assert all("display_name" not in e for e in result["empty_lenses"])
    named = run_query(fleet, "census", names=True)
    assert any(e.get("display_name") == "Sofia Verdi" for e in named["empty_lenses"])


def test_coverage_reports_empty_school_as_reason_not_zero(fleet):
    result = run_query(fleet, "coverage")
    assert result["scored"] is True
    by_school = {s["school"]: s for s in result["by_school"]}
    assert "empty_reason" in by_school["Berlin International"]
    assert "populated_percent" not in by_school["Berlin International"]
    assert by_school["Scuola Roma"]["field_population"]["learning_and_cognition"] == 1


# ---------------------------------------------------------------------------
# Support needs, gap, strategies
# ---------------------------------------------------------------------------


def test_support_needs_counts_and_high_need(fleet):
    result = run_query(fleet, "needs", min_categories=2)
    assert result["fleet_totals"]["emotional_regulation"] == 2
    high = {h["aron"] for h in result["high_need_students"]}
    # Both Roma students have 2+ populated support categories
    assert aron_ref("stu-luca") in high
    assert aron_ref("stu-marco") in high


def test_support_gap_detects_needs_without_strategies(fleet):
    result = run_query(fleet, "gap")
    gap_arons = {g["aron"] for g in result["needs_without_strategies"]}
    assert aron_ref("stu-marco") in gap_arons      # needs, no strategies
    assert aron_ref("stu-luca") not in gap_arons   # needs AND strategies
    needs_only = {r["aron"] for r in result["needs_but_no_strengths_documented"]}
    assert aron_ref("stu-marco") in needs_only


def test_strategies_ranked_by_frequency(fleet):
    result = run_query(fleet, "strategies")
    assert result["scored"] is True
    strategies = {s["strategy"]: s["students"] for s in result["strategies"]}
    assert strategies == {"visual schedule": 1, "peer reading": 1}


# ---------------------------------------------------------------------------
# Search, staleness
# ---------------------------------------------------------------------------


def test_term_search_is_accent_insensitive_with_citations(fleet):
    result = run_query(fleet, "search", term="MATEMÀTICA")
    assert result["scored"] is True
    assert result["students_matched"] == 2  # stu-luca strength + stu-noemi value
    fields = {m["field"] for m in result["matches"]}
    assert fields == {"academic_strengths", "communication_and_language"}
    # Citations carry the source_ref for grounding
    assert any(
        c.get("source_id") == "src-bulletin-1"
        for m in result["matches"] for c in m["citations"]
    )


def test_term_search_empty_term_is_not_enough_data(fleet):
    result = run_query(fleet, "search", term="   ")
    assert result["scored"] is False
    assert exit_code(result) == EXIT_NOT_ENOUGH_DATA


def test_staleness_stale_recent_and_cannot_tell(fleet):
    result = run_query(fleet, "staleness", days=60)
    stale = {s["aron"] for s in result["stale"]}
    assert stale == {aron_ref("stu-marco")}
    recent = {r["aron"] for r in result["recent_lenses"]}
    assert aron_ref("stu-luca") in recent
    cannot = {c["aron"] for c in result["cannot_tell"]}
    assert cannot == {aron_ref("stu-badts")}
    assert result["cannot_tell_reason"]


# ---------------------------------------------------------------------------
# Evidence integrity, duplicates
# ---------------------------------------------------------------------------


def test_integrity_grounding_teachers_confidence_sources(fleet):
    result = run_query(fleet, "integrity")
    roma = result["grounding_by_school"]["Scuola Roma"]
    assert roma["DOCUMENT"] == 5 and roma["OBSERVATION"] == 2
    assert result["teacher_contributions"]["teacher-a"] >= 4
    low = {r["aron"] for r in result["low_confidence_only"]}
    assert low == {aron_ref("stu-marco")}  # max confidence 0.4 < 0.6
    single = {r["aron"] for r in result["single_source_lenses"]}
    assert aron_ref("stu-marco") in single
    assert aron_ref("stu-luca") not in single  # has an observation too
    multi = {r["aron"] for r in result["multi_teacher_students"]}
    assert multi == {aron_ref("stu-luca")}  # teacher-a + teacher-b
    assert result["merge_events_by_month"]["Scuola Roma"] == {"2026-08": 1}


def test_duplicate_risk_flags_reversed_name_pair_same_school_only(fleet):
    result = run_query(fleet, "duplicates")
    assert result["pair_count"] == 1
    pair = result["near_duplicate_pairs"][0]
    assert pair["school"] == "École Lyon"
    arons = {s["aron"] for s in pair["students"]}
    assert arons == {aron_ref("stu-anna1"), aron_ref("stu-anna2")}


# ---------------------------------------------------------------------------
# Dossier, hygiene
# ---------------------------------------------------------------------------


def test_dossier_by_id_by_aron_and_source_filter(fleet):
    result = run_query(fleet, "dossier", student="stu-luca")
    assert result["scored"] is True
    assert set(result["fields"]) == {
        "learning_and_cognition", "emotional_regulation",
        "strategies_trialed", "academic_strengths",
    }
    by_aron = run_query(fleet, "dossier", student=aron_ref("stu-luca"))
    assert by_aron["aron"] == aron_ref("stu-luca")
    filtered = run_query(
        fleet, "dossier", student="stu-luca", source_id="src-report-1"
    )
    assert filtered["fields"]["strategies_trialed"]["evidence"] == []
    assert filtered["fields"]["learning_and_cognition"]["evidence"]


def test_dossier_unknown_student_is_not_enough_data(fleet):
    result = run_query(fleet, "dossier", student="stu-nobody")
    assert result["scored"] is False
    assert "No lens found" in result["empty_reason"]
    assert exit_code(result) == EXIT_NOT_ENOUGH_DATA


def test_hygiene_nonlocal_identity_queue_is_cannot_tell_never_zero(fleet):
    result = run_query(fleet, "hygiene")
    for entry in result["by_school"]:
        assert entry["open_identity_queue"] is None
        assert "cannot_tell_reason" in entry


# ---------------------------------------------------------------------------
# Empty fleet, formatting, question map lock
# ---------------------------------------------------------------------------


def test_empty_fleet_is_not_enough_data(tmp_path):
    config = tmp_path / "fleet.json"
    (tmp_path / "empty-vault").mkdir()
    config.write_text(json.dumps({"schools": [
        {"school": "New School", "country": "PT",
         "root": str(tmp_path / "empty-vault")},
    ]}), encoding="utf-8")
    empty = load_fleet(config)
    result = run_query(empty, "census")
    assert result["scored"] is False
    assert "No student lenses" in result["empty_reason"]
    assert exit_code(result) == EXIT_NOT_ENOUGH_DATA


def test_format_result_shows_verdict(fleet):
    scored = format_result(run_query(fleet, "census"))
    assert "verdict: SCORED" in scored
    empty = format_result(run_query(fleet, "dossier", student="stu-nobody"))
    assert "verdict: NOT-ENOUGH-DATA" in empty
    assert "No lens found" in empty


def test_unknown_query_raises(fleet):
    with pytest.raises(ValueError):
        run_query(fleet, "everything")


@pytest.mark.parametrize("entry", QUESTION_MAP, ids=[q["id"] for q in QUESTION_MAP])
def test_every_administrator_question_executes(fleet, entry):
    """Locking test: all 30 questions map to a runnable query and return a
    verdict-carrying dict. A question that cannot be answered must say so
    (scored False + empty_reason), never crash or silently zero-fill."""
    result = run_question(fleet, entry["id"])
    assert isinstance(result, dict)
    assert result["question_id"] == entry["id"]
    assert "scored" in result
    if not result["scored"]:
        assert result.get("empty_reason") or result.get("cannot_tell")
    assert exit_code(result) in (EXIT_SCORED, EXIT_NOT_ENOUGH_DATA)
