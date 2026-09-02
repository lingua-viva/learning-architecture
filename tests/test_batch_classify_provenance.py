"""Locking tests for P0-1 and P0-2 in the batched sentence classifier
(SPEC_ENTITY_LENS_DOCPIPE_RECIPE_2026-09-01, evidence: Claudia's 0a6c2ad).

P0-1 — silent truncation: the original batch classifier capped at
`sentences[:40]` and DROPPED sentence 41+ with no warning. Now: paging in
_BATCH_SIZE batches up to _MAX_BATCHES calls, and anything beyond that
budget is reported as a skipped count the caller surfaces in
unresolved_questions. Loss may happen; silent loss may not.

P0-2 — lost chunk provenance: batched fields carried
supporting_chunk_ids=[] and a post-hoc fallback could attribute them to
the wrong chunk (relevant_chunks[0]). Now: the caller computes a
deterministic sentence→chunk mapping and every batched field cites the
chunk its sentence actually came from.
"""
from __future__ import annotations

import asyncio
import json
import re
from types import SimpleNamespace

import pytest

import src.lingua_viva.reasoning as reasoning
from src.lingua_viva.docpipe.lens_extract import (
    _BATCH_SIZE,
    _MAX_BATCHES,
    _batch_classify_sentences,
    _classify_one_batch,
    extract_for_lens_update,
)


class _StubEngine:
    """Echo classifier: routes every numbered sentence to a real field with
    the sentence's own words as the phrase (passes the grounding check)."""

    def __init__(self):
        self.calls: list[str] = []

    async def reason(self, prompt, **kwargs):
        self.calls.append(prompt)
        items = []
        for line in prompt.splitlines():
            match = re.match(r"^(\d+)\.\s+(.*)$", line)
            if match:
                items.append({
                    "n": int(match.group(1)),
                    "f": "learning_and_cognition",
                    "p": match.group(2)[:60],
                })
        return SimpleNamespace(
            model_used="stub", error=None, content=json.dumps(items)
        )


@pytest.fixture()
def stub_engine(monkeypatch):
    engine = _StubEngine()
    # _batch_classify_sentences replaces anything that isn't a
    # ReasoningEngine — make the stub pass that gate.
    monkeypatch.setattr(reasoning, "ReasoningEngine", _StubEngine)
    return engine


def _sentences(count: int) -> list[str]:
    return [
        f"Sentence number {i:03d} describes steady progress in mathematics."
        for i in range(count)
    ]


# ---------------------------------------------------------------------------
# P0-1 — paging, and visible (never silent) budget overflow
# ---------------------------------------------------------------------------


def test_sentences_beyond_40_are_paged_not_dropped(stub_engine):
    fields, skipped = asyncio.run(
        _batch_classify_sentences(_sentences(100), stub_engine)
    )
    assert len(stub_engine.calls) == 3  # 40 + 40 + 20
    assert len(fields) == 100
    assert skipped == 0


def test_budget_overflow_is_counted_never_silent(stub_engine):
    budget = _BATCH_SIZE * _MAX_BATCHES
    total = budget + 50
    fields, skipped = asyncio.run(
        _batch_classify_sentences(_sentences(total), stub_engine)
    )
    assert len(stub_engine.calls) == _MAX_BATCHES
    assert len(fields) == budget
    assert skipped == 50


def test_single_small_batch_stays_one_call(stub_engine):
    # The original fix's win must not regress: a report card = ONE call.
    fields, skipped = asyncio.run(
        _batch_classify_sentences(_sentences(30), stub_engine)
    )
    assert len(stub_engine.calls) == 1
    assert len(fields) == 30
    assert skipped == 0


def test_exactly_40_sentences_is_one_batch(stub_engine):
    fields, skipped = asyncio.run(
        _batch_classify_sentences(_sentences(40), stub_engine)
    )
    assert len(stub_engine.calls) == 1
    assert len(fields) == 40
    assert skipped == 0


def test_41_sentences_page_into_two_batches(stub_engine):
    # The exact boundary the original bug silently dropped: sentence 41.
    fields, skipped = asyncio.run(
        _batch_classify_sentences(_sentences(41), stub_engine)
    )
    assert len(stub_engine.calls) == 2
    assert len(fields) == 41
    assert skipped == 0


# ---------------------------------------------------------------------------
# P0-2 — chunk provenance survives batching, including across page offsets
# ---------------------------------------------------------------------------


def test_batched_fields_carry_their_sentence_chunk_ids(stub_engine):
    sentences = _sentences(3)
    mapping = [["doc-0000"], ["doc-0001"], ["doc-0002"]]
    fields, _ = asyncio.run(
        _batch_classify_sentences(sentences, stub_engine, mapping)
    )
    assert [f.supporting_chunk_ids for f in fields] == mapping


def test_chunk_ids_stay_aligned_across_batch_boundaries(stub_engine):
    # Sentence 45 lives in batch 2 — its LOCAL index is 5, its global
    # index is 45. The mapping must be read at the global index.
    count = 50
    sentences = _sentences(count)
    mapping = [[f"doc-{i:04d}"] for i in range(count)]
    fields, _ = asyncio.run(
        _batch_classify_sentences(sentences, stub_engine, mapping)
    )
    assert len(fields) == count
    assert fields[45].supporting_chunk_ids == ["doc-0045"]


# ---------------------------------------------------------------------------
# P0-3 — a failed batch loses its sentences VISIBLY, never silently
# ---------------------------------------------------------------------------


class _FlakyEngine(_StubEngine):
    """Fails exactly one call (1-based); every other call succeeds."""

    def __init__(self, fail_on_call: int = 2):
        super().__init__()
        self.fail_on_call = fail_on_call

    async def reason(self, prompt, **kwargs):
        if len(self.calls) + 1 == self.fail_on_call:
            self.calls.append(prompt)
            raise TimeoutError("simulated mid-document LLM failure")
        return await super().reason(prompt, **kwargs)


def test_failed_middle_batch_is_classify_failed_never_silent(stub_engine, monkeypatch):
    # THE P0-3 locking test: batch 2 of 3 fails → batches 1+3 classified
    # normally, every batch-2 sentence classify_failed, zero sentences lost.
    engine = _FlakyEngine(fail_on_call=2)
    count = 100  # 40 + 40 + 20
    mapping = [[f"doc-{i:04d}"] for i in range(count)]
    fields, skipped = asyncio.run(
        _batch_classify_sentences(_sentences(count), engine, mapping)
    )
    assert len(engine.calls) == 3  # the failure did not stop paging
    assert len(fields) == count  # zero silent loss
    assert skipped == 0

    failed = [f for f in fields if f.status == "classify_failed"]
    ok = [f for f in fields if f.status != "classify_failed"]
    assert len(failed) == 40  # exactly batch 2
    assert len(ok) == 60  # batches 1 + 3
    for field in failed:
        assert field.field_path == "unclassified"
        assert field.confidence == 0.0
        # Provenance survives even through failure (P0-2 holds under P0-3)
        assert field.supporting_chunk_ids, field.value
    # The failed fields are batch 2's sentences (indices 40-79)
    failed_chunks = {cid for f in failed for cid in f.supporting_chunk_ids}
    assert failed_chunks == {f"doc-{i:04d}" for i in range(40, 80)}


def test_error_result_also_fails_visibly(stub_engine, monkeypatch):
    # Engine returns error result (not an exception) — same contract.
    class _ErrorEngine(_StubEngine):
        async def reason(self, prompt, **kwargs):
            self.calls.append(prompt)
            return SimpleNamespace(model_used="none", error="quota", content="")

    engine = _ErrorEngine()
    fields, skipped = asyncio.run(
        _batch_classify_sentences(_sentences(10), engine)
    )
    assert len(fields) == 10
    assert all(f.status == "classify_failed" for f in fields)
    assert skipped == 0


def test_control_chars_in_model_json_do_not_fail_the_batch(stub_engine):
    # Live catch (09-01): qwen3 emitted a raw control character inside a
    # JSON string and strict parsing threw the whole batch away. Lenient
    # parsing is safe — every phrase is still grounding-checked.
    class _ControlCharEngine(_StubEngine):
        async def reason(self, prompt, **kwargs):
            self.calls.append(prompt)
            content = ('[{"n": 1, "f": "learning_and_cognition", '
                       '"p": "Sentence number\t000"}]')
            return SimpleNamespace(model_used="stub", error=None, content=content)

    engine = _ControlCharEngine()
    fields, skipped = asyncio.run(
        _batch_classify_sentences(_sentences(2), engine)
    )
    assert skipped == 0
    assert not any(f.status == "classify_failed" for f in fields)
    assert len(fields) == 1  # parsed, not discarded


def test_classify_failed_survives_dedup_individually():
    from src.lingua_viva.docpipe.lens_extract import _deduplicate_fields
    from src.lingua_viva.data_in_contracts import ExtractedField

    fields = [
        ExtractedField(field_path="learning_and_cognition", value="a",
                       confidence=0.5, supporting_chunk_ids=["doc-0000"],
                       status="needs_confirmation"),
        ExtractedField(field_path="learning_and_cognition", value="b",
                       confidence=0.9, supporting_chunk_ids=["doc-0001"],
                       status="needs_confirmation"),
    ] + [
        ExtractedField(field_path="unclassified", value=f"failed sentence {i}",
                       confidence=0.0, supporting_chunk_ids=[f"doc-{i:04d}"],
                       status="classify_failed")
        for i in range(3)
    ]
    result = _deduplicate_fields(fields)
    # Normal dedup still works (best of the two same-path fields)...
    normal = [f for f in result if f.status != "classify_failed"]
    assert len(normal) == 1 and normal[0].value == "b"
    # ...but classify_failed fields (all sharing field_path "unclassified")
    # must NOT collapse into one row.
    failed = [f for f in result if f.status == "classify_failed"]
    assert len(failed) == 3


def test_classify_failed_excluded_from_synthesis(stub_engine):
    from src.lingua_viva.docpipe.lens_extract import _run_synthesis_repass
    from src.lingua_viva.data_in_contracts import ExtractedField

    # 3 classify_failed share field_path "unclassified" — without the
    # guard they'd group together and be sent to the LLM to "synthesize"
    # (the model authoring from unverified sentences).
    fields = [
        ExtractedField(field_path="unclassified", value=f"failed sentence {i}",
                       confidence=0.0, supporting_chunk_ids=[],
                       status="classify_failed")
        for i in range(3)
    ]
    result = asyncio.run(_run_synthesis_repass(fields, stub_engine))
    assert stub_engine.calls == []  # no LLM call over failed sentences
    assert len(result) == 3
    assert all(f.status == "classify_failed" for f in result)


def test_classify_failed_never_written_to_lens(tmp_path):
    from src.education.student_lens import StudentLensStore
    from src.lingua_viva.data_in_contracts import (
        ExtractedField, ExtractionResult, write_student_lens,
    )

    with StudentLensStore(db_path=tmp_path / "p03.db") as store:
        sid = store.create_lens(display_name="Guard Test")
        failed = ExtractedField(
            field_path="unclassified",
            value="This raw sentence never got classified.",
            confidence=0.0,
            supporting_chunk_ids=["doc-0000"],
            status="classify_failed",
        )
        res = ExtractionResult(
            target_schema_id="student_lens",
            fields=[failed],
            unresolved_questions=[],
            source_files=["test.txt"],
            chunks_used=[],
        )
        write_res = write_student_lens(
            res, hint={"assigned_student_id": sid}, store=store
        )
        assert write_res["written_fields"] == []
        # Visible, content-free note — sentence text never leaks into it.
        notes = write_res["unresolved_questions"]
        assert any("could not be classified" in n for n in notes), notes
        assert all("raw sentence" not in n for n in notes)


# ---------------------------------------------------------------------------
# Invariant 1 — model routes, never authors (phrase substring lock)
# ---------------------------------------------------------------------------


def test_fabricated_phrase_replaced_by_source_sentence():
    """Locking test: if the LLM returns a phrase that is NOT a substring of the
    source sentence, the pipeline replaces it with the source sentence's own text
    (truncated to 80 chars). The model never authors — it can only point."""

    class _FabricatingEngine:
        async def reason(self, prompt, **kwargs):
            # Return a fabricated phrase that is NOT in the source sentence
            return SimpleNamespace(
                model_used="stub", error=None,
                content=json.dumps([
                    {"n": 1, "f": "learning_and_cognition", "p": "INVENTED PHRASE NOT IN SOURCE"},
                ]),
            )

    source_sentence = "Maria shows strong reading comprehension and analytical thinking."
    batch = [source_sentence]
    engine = _FabricatingEngine()

    fields = asyncio.run(_classify_one_batch(batch, engine, offset=0, sentence_chunk_ids=None))
    assert fields is not None
    assert len(fields) == 1

    # The fabricated phrase must NOT survive — it should be replaced
    assert fields[0].value != "INVENTED PHRASE NOT IN SOURCE", (
        "Fabricated LLM phrase was accepted without substring verification — "
        "invariant 1 (model routes, never authors) is broken"
    )
    # Instead, it should contain text from the actual source sentence
    assert fields[0].value in source_sentence or source_sentence.startswith(fields[0].value)


# ---------------------------------------------------------------------------
# End-to-end through extract_for_lens_update
# ---------------------------------------------------------------------------


def _document(paragraph_count: int) -> bytes:
    paras = [
        f"Luca Rossi explored topic {i:03d} with growing independence and asked thoughtful questions about topic {i:03d}."
        for i in range(paragraph_count)
    ]
    return ("Luca Rossi\n\n" + "\n\n".join(paras)).encode("utf-8")


def test_e2e_overflow_surfaces_in_unresolved_questions(stub_engine):
    budget = _BATCH_SIZE * _MAX_BATCHES
    results = asyncio.run(extract_for_lens_update(
        _document(budget + 30),
        "report",
        [{"student_id": "stu-luca", "display_name": "Luca Rossi"}],
        engine=stub_engine,
    ))
    warnings = results["stu-luca"].unresolved_questions
    assert any("classification budget" in w for w in warnings), warnings


def test_e2e_batched_fields_resolve_to_real_chunks(stub_engine):
    results = asyncio.run(extract_for_lens_update(
        _document(10),
        "report",
        [{"student_id": "stu-luca", "display_name": "Luca Rossi"}],
        engine=stub_engine,
    ))
    result = results["stu-luca"]
    valid_ids = {c.chunk_id for c in result.chunks_used}
    batched = [f for f in result.fields if f.confidence == 0.72]
    assert batched, "expected at least one batched (LLM-routed) field"
    for field in batched:
        assert field.supporting_chunk_ids, field.value
        for chunk_id in field.supporting_chunk_ids:
            assert chunk_id in valid_ids
        # The cited chunk must actually contain the field's phrase —
        # provenance that doesn't resolve is provenance that lies.
        cited = [c for c in result.chunks_used if c.chunk_id in field.supporting_chunk_ids]
        assert any(str(field.value) in c.text for c in cited), field.value


def test_e2e_no_overflow_warning_below_budget(stub_engine):
    results = asyncio.run(extract_for_lens_update(
        _document(5),
        "report",
        [{"student_id": "stu-luca", "display_name": "Luca Rossi"}],
        engine=stub_engine,
    ))
    warnings = results["stu-luca"].unresolved_questions
    assert not any("classification budget" in w for w in warnings), warnings
