"""
Eval harness for src/lingua_viva/extraction_engine.py — SPEC_LV_EXTRACT_FILL_VERIFY_ENGINE_2026-07-22.md §5.

Runs extract() against synthetic fixtures with known ground truth
(tests/fixtures/data_in_eval/), reports precision/recall, and enforces the
one hard, zero-tolerance check: no fixture may ever produce a "verified"
field with a value outside its fixture's declared acceptable set. A
confidently wrong answer is treated as a harder failure than a missed one.

All fixture content is synthetic and invented — no real students, no real
school, no real curriculum documents.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.lingua_viva.extraction_engine import extract

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "data_in_eval"


def _load_fixtures(schema_dir: str) -> list[tuple[Path, dict]]:
    directory = FIXTURES_DIR / schema_dir
    fixtures = []
    for source_file in sorted(directory.glob("*.txt")):
        expected_file = source_file.with_suffix("").with_suffix(".expected.yaml")
        expected = yaml.safe_load(expected_file.read_text(encoding="utf-8")) or {}
        fixtures.append((source_file, expected))
    return fixtures


def _norm(text) -> str:
    return " ".join(str(text).strip().lower().split())


def _value_matches(value, acceptable_list) -> bool:
    """Substring-based, not exact-equality: the engine's own grounding check
    already guarantees a verified value is a literal excerpt of the source
    text, so this only needs to confirm the SUBSTANCE is right (e.g. the
    level "A2" is present), not that the model reproduced an identical
    phrase to what the fixture author happened to write."""
    if not acceptable_list:
        return False
    for candidate in acceptable_list:
        if isinstance(candidate, list) and isinstance(value, list):
            if sorted(candidate) == sorted(value):
                return True
            continue
        norm_candidate, norm_value = _norm(candidate), _norm(value)
        if norm_candidate == norm_value or norm_candidate in norm_value or norm_value in norm_candidate:
            return True
    return False


async def _run_eval(schema_dir: str, target_schema_id: str) -> dict:
    fixtures = _load_fixtures(schema_dir)
    assert fixtures, f"No fixtures found under {schema_dir}"

    total_must_verify = 0
    hit_must_verify = 0
    wrong_verified: list[str] = []  # hard-failure list: verified but value not acceptable
    hard_rule_violations: list[str] = []  # never_verify fields that came back verified

    for source_file, expected in fixtures:
        result = await extract([str(source_file)], target_schema_id)
        by_field = {f.field_path: f for f in result.fields}

        acceptable = expected.get("acceptable", {})
        for field_name in expected.get("must_verify", []):
            total_must_verify += 1
            field = by_field.get(field_name)
            if field and field.status == "verified":
                if _value_matches(field.value, acceptable.get(field_name, [])):
                    hit_must_verify += 1
                else:
                    wrong_verified.append(
                        f"{source_file.name}:{field_name} verified as {field.value!r}, "
                        f"not in acceptable set {acceptable.get(field_name, [])!r}"
                    )

        for field_name in expected.get("never_verify", []):
            field = by_field.get(field_name)
            if field and field.status == "verified":
                hard_rule_violations.append(
                    f"{source_file.name}:{field_name} was verified as {field.value!r} — "
                    "this field must never verify for this fixture"
                )

        # Any field marked verified must be in that fixture's acceptable set,
        # even if it wasn't in must_verify (a bonus correct field is fine; a
        # bonus WRONG field is the exact failure mode this harness exists for).
        for field_name, field in by_field.items():
            if field.status != "verified":
                continue
            if field_name in expected.get("never_verify", []):
                continue  # already captured above
            if field_name in acceptable and not _value_matches(field.value, acceptable[field_name]):
                wrong_verified.append(
                    f"{source_file.name}:{field_name} verified as {field.value!r}, "
                    f"not in acceptable set {acceptable[field_name]!r}"
                )

    recall = hit_must_verify / total_must_verify if total_must_verify else 1.0
    return {
        "recall": recall,
        "hit": hit_must_verify,
        "total": total_must_verify,
        "wrong_verified": wrong_verified,
        "hard_rule_violations": hard_rule_violations,
    }


@pytest.mark.asyncio
async def test_curriculum_eval_no_confidently_wrong_answers():
    report = await _run_eval("curriculum", "curriculum_unit")
    print(f"\n[curriculum eval] recall={report['recall']:.2f} ({report['hit']}/{report['total']})")
    assert not report["wrong_verified"], (
        "Confidently wrong verified field(s) — worse than a miss:\n" + "\n".join(report["wrong_verified"])
    )
    assert not report["hard_rule_violations"], (
        "Hard-rule violation(s):\n" + "\n".join(report["hard_rule_violations"])
    )


@pytest.mark.asyncio
async def test_student_lens_eval_no_confidently_wrong_answers():
    report = await _run_eval("student_lens", "student_lens")
    print(f"\n[student_lens eval] recall={report['recall']:.2f} ({report['hit']}/{report['total']})")
    assert not report["wrong_verified"], (
        "Confidently wrong verified field(s) — worse than a miss:\n" + "\n".join(report["wrong_verified"])
    )
    assert not report["hard_rule_violations"], (
        "Hard-rule violation(s):\n" + "\n".join(report["hard_rule_violations"])
    )


@pytest.mark.asyncio
async def test_trauma_flag_never_verified_even_when_clearly_stated():
    """The single most important safety test in this file. notes_sensitive.txt
    states a traumatic history plainly and unambiguously — a naive pipeline
    would have every reason to be "confident." trauma_flag must still never
    reach status="verified"."""
    fixture = FIXTURES_DIR / "student_lens" / "notes_sensitive.txt"
    result = await extract([str(fixture)], "student_lens")
    trauma_field = next((f for f in result.fields if f.field_path == "trauma_flag"), None)
    if trauma_field is not None:
        assert trauma_field.status != "verified", (
            "trauma_flag must never be status='verified' — it is hard-excluded "
            "in extraction_engine.NEVER_AUTO_VERIFY regardless of grounding."
        )


@pytest.mark.asyncio
async def test_sparse_files_do_not_invent_answers():
    """unit_sparse.txt and notes_ambiguous.txt have essentially no extractable
    signal. A pipeline that hallucinates confident answers from thin material
    fails here even if it never technically violates a hard rule."""
    curriculum_result = await extract(
        [str(FIXTURES_DIR / "curriculum" / "unit_sparse.txt")], "curriculum_unit"
    )
    verified = [f for f in curriculum_result.fields if f.status == "verified"]
    assert not verified, f"unit_sparse.txt should verify nothing; got {verified}"

    student_result = await extract(
        [str(FIXTURES_DIR / "student_lens" / "notes_ambiguous.txt")], "student_lens"
    )
    verified = [f for f in student_result.fields if f.status == "verified"]
    assert not verified, f"notes_ambiguous.txt should verify nothing; got {verified}"


@pytest.mark.asyncio
async def test_unreadable_file_produces_unresolved_question_not_a_crash():
    result = await extract(["/nonexistent/path/does-not-exist.txt"], "student_lens")
    assert result.fields == []
    assert result.unresolved_questions


@pytest.mark.asyncio
async def test_multi_file_aggregation():
    """A unit's real content is often spread across multiple files (topic
    notes in one, assessment plan in another). extract() must aggregate
    chunks across ALL given files, not just the first."""
    files = [
        str(FIXTURES_DIR / "curriculum" / "multifile" / "a.txt"),
        str(FIXTURES_DIR / "curriculum" / "multifile" / "b.txt"),
    ]
    result = await extract(files, "curriculum_unit")
    by_field = {f.field_path: f for f in result.fields}

    wrong = []
    if "grade" in by_field and by_field["grade"].status == "verified":
        if by_field["grade"].value != "G5":
            wrong.append(f"grade verified as {by_field['grade'].value!r}, expected G5")
    if "cefr_target" in by_field and by_field["cefr_target"].status == "verified":
        if "b1" not in by_field["cefr_target"].value.lower():
            wrong.append(f"cefr_target verified as {by_field['cefr_target'].value!r}, expected to mention B1")

    assert not wrong, "Confidently wrong field(s) in multi-file aggregation:\n" + "\n".join(wrong)
    # Provenance must span both files, not just one
    source_files = {c.file_path for c in result.chunks_used}
    assert len(source_files) == 2, f"Expected chunks from both files, got: {source_files}"
