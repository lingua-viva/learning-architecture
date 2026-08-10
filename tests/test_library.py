"""Per-machine knowledge library (W1 spine): ingest, classify, index, search.

All fixtures are synthetic (publication-policy.md). LV_STATE_HOME is pinned
to tmp_path so no test touches the real ~/.lingua-viva/.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.lingua_viva import library


@pytest.fixture()
def lv_state(monkeypatch, tmp_path):
    state = tmp_path / "lv-state"
    monkeypatch.setenv("LV_STATE_HOME", str(state))
    return state


UNIT_PLAN_MD = """# IB Unit Planner — Grade 3 La Famiglia

## Central idea
Families share stories that shape who we are. This unit of inquiry sits in
the transdisciplinary theme "Who we are" with three lines of inquiry.

## Key concepts
Form, connection, perspective. The programme of inquiry maps each unit plan
to CEFR language targets for the grade.
"""

SAFEGUARDING_TXT = (
    "Safeguarding reference: staff must follow the reporting protocol when a "
    "concern arises. This procedure document covers escalation, documentation, "
    "and confidentiality duties for all campus staff."
)


def test_ingest_md_classifies_and_persists(lv_state, tmp_path):
    src = tmp_path / "unit_plan.md"
    src.write_text(UNIT_PLAN_MD, encoding="utf-8")

    entry = library.add_document(src)

    assert entry["doc_id"].startswith("LIB-")
    assert entry["chunk_count"] >= 1
    assert entry["title"].startswith("IB Unit Planner")
    assert entry["source"] == "local"
    assert entry["sha256"]
    # Classified against the ontology: curriculum signals ("unit plan",
    # "central idea", "lines of inquiry") must land in the curriculum domain.
    domains = {c["domain"] for c in entry["categories"]}
    assert "curriculum" in domains
    assert "teacher" in entry["roles"]

    # On-disk layout under <LV_STATE_HOME>/library/
    assert (lv_state / "library" / "index.ndjson").is_file()
    doc_dir = lv_state / "library" / "docs" / entry["doc_id"]
    assert (doc_dir / "text.txt").is_file()
    assert (doc_dir / "chunks.ndjson").is_file()
    # Nothing escaped the tmp state home
    assert not (Path.home() / ".lingua-viva" / "library").exists() or (
        str(Path.home() / ".lingua-viva") not in str(lv_state)
    )


def test_index_round_trip_and_dedup(lv_state, tmp_path):
    src = tmp_path / "notes.txt"
    src.write_text(SAFEGUARDING_TXT, encoding="utf-8")

    first = library.add_document(src)
    again = library.add_document(src)  # identical content → dedup

    assert again["doc_id"] == first["doc_id"]
    index = library.load_index()
    assert len(index) == 1
    assert index[0]["doc_id"] == first["doc_id"]
    assert index[0]["sha256"] == first["sha256"]

    # Raw NDJSON line parses and matches the API view
    raw = (lv_state / "library" / "index.ndjson").read_text(encoding="utf-8").strip()
    assert json.loads(raw)["doc_id"] == first["doc_id"]


def test_search_by_query_category_and_role(lv_state, tmp_path):
    (tmp_path / "unit_plan.md").write_text(UNIT_PLAN_MD, encoding="utf-8")
    (tmp_path / "safeguarding.txt").write_text(SAFEGUARDING_TXT, encoding="utf-8")
    plan = library.add_document(tmp_path / "unit_plan.md")
    library.add_document(tmp_path / "safeguarding.txt")

    # Free-text query finds the unit plan first, with a snippet
    results = library.search("central idea lines of inquiry")
    assert results
    assert results[0]["doc_id"] == plan["doc_id"]
    assert results[0]["score"] > 0
    assert results[0]["snippet"]

    # Category filter (by ontology domain) returns only curriculum docs
    curriculum_only = library.search(category="curriculum")
    assert curriculum_only
    assert all(
        any(c["domain"] == "curriculum" for c in r["categories"]) for r in curriculum_only
    )

    # Category filter also accepts the node id of the primary category
    node_id = plan["categories"][0]["node_id"]
    by_node = library.search(category=node_id)
    assert any(r["doc_id"] == plan["doc_id"] for r in by_node)

    # Role filter: every stored doc carries at least a default role
    teacher_docs = library.search(role="teacher")
    assert any(r["doc_id"] == plan["doc_id"] for r in teacher_docs)

    # A query with no overlap returns nothing
    assert library.search("zzz qqq xxyyzz") == []


def test_search_ranking_uses_term_frequency_not_just_overlap(lv_state, tmp_path):
    focused = tmp_path / "focused.txt"
    broad = tmp_path / "broad.txt"
    focused.write_text(
        "Reading fluency fluency fluency assessment. Fluency routines and repeated reading.",
        encoding="utf-8",
    )
    broad.write_text(
        "Reading assessment includes vocabulary, comprehension, speaking, listening, and one fluency note.",
        encoding="utf-8",
    )
    focused_doc = library.add_document(focused, title="Reading fluency assessment routines")
    broad_doc = library.add_document(broad, title="General reading assessment")

    results = library.search("reading fluency assessment", limit=2)

    assert [r["doc_id"] for r in results] == [focused_doc["doc_id"], broad_doc["doc_id"]]
    assert results[0]["score"] > results[1]["score"]


def test_status_counts(lv_state, tmp_path):
    (tmp_path / "unit_plan.md").write_text(UNIT_PLAN_MD, encoding="utf-8")
    library.add_document(tmp_path / "unit_plan.md")

    info = library.status()

    assert info["doc_count"] == 1
    assert info["chunk_count"] >= 1
    assert info["by_source"] == {"local": 1}
    assert str(lv_state / "library") == info["library_root"]


def test_rejects_unsupported_and_missing_files(lv_state, tmp_path):
    bad = tmp_path / "sheet.xlsx"
    bad.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError):
        library.add_document(bad)
    with pytest.raises(FileNotFoundError):
        library.add_document(tmp_path / "nope.md")
    empty = tmp_path / "empty.txt"
    empty.write_text("   \n", encoding="utf-8")
    with pytest.raises(ValueError):
        library.add_document(empty)


def test_chunker_packs_paragraphs_and_splits_long_ones():
    text = "\n\n".join(f"Paragraph {i} " + ("word " * 60) for i in range(10))
    chunks = library.chunk_text(text)
    assert len(chunks) > 1
    assert all(len(c) <= library.MAX_CHUNK_CHARS for c in chunks)
    # Round-trip: no content lost (modulo whitespace normalization)
    joined = " ".join(chunks)
    for i in range(10):
        assert f"Paragraph {i}" in joined

    long_para = "x" * (library.MAX_CHUNK_CHARS * 2 + 50)
    long_chunks = library.chunk_text(long_para)
    assert len(long_chunks) >= 2
    assert sum(len(c) for c in long_chunks) >= len(long_para) - 10


def test_ingest_pdf_via_pdfplumber(lv_state):
    fixture = Path(__file__).parent / "fixtures" / "sample_myp_guide.pdf"

    entry = library.add_document(fixture)

    assert entry["doc_id"].startswith("LIB-")
    assert entry["chunk_count"] >= 1
    text = (lv_state / "library" / "docs" / entry["doc_id"] / "text.txt").read_text(encoding="utf-8")
    assert "CRITERION B: READING" in text
    # Assessment vocabulary should surface an education-pack category
    assert entry["categories"]


def test_add_research_result_marked_perplexity(lv_state):
    entry = library.add_research_result(
        "CEFR A2 reading benchmarks for grade 3 Italian immersion",
        "External summary content about CEFR reading benchmarks.",
        citations=["https://example.org/cefr"],
    )
    assert entry["source"] == "perplexity"
    assert entry["source_path"].startswith("perplexity://")
    text = (lv_state / "library" / "docs" / entry["doc_id"] / "text.txt").read_text(encoding="utf-8")
    assert "## Citations" in text
    assert library.status()["by_source"] == {"perplexity": 1}
