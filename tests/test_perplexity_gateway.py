"""Perplexity gateway: fail-closed gating, outbound sanitization, library storage.

No real network calls anywhere — tests use dry_run or an injected transport.
All names are synthetic (publication-policy.md): "Nora Rossi" is an
established synthetic fixture name.
"""

from __future__ import annotations

import pytest

from src.lingua_viva import library, perplexity_gateway
from src.lingua_viva.perplexity_gateway import (
    ResearchBlockedError,
    ResearchDisabledError,
    is_enabled,
    research,
    sanitize_outbound_query,
)


@pytest.fixture()
def lv_state(monkeypatch, tmp_path):
    state = tmp_path / "lv-state"
    monkeypatch.setenv("LV_STATE_HOME", str(state))
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "students.db"))
    monkeypatch.setenv("LV_SANITIZER_DATA_DIR", str(tmp_path / "sanitizer-data"))
    return state


@pytest.fixture()
def research_enabled(monkeypatch):
    monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key-not-real")
    monkeypatch.setenv("LV_ALLOW_RESEARCH", "1")


def _seed_student(display_name: str) -> None:
    from src.education.student_lens import StudentLensStore

    store = StudentLensStore()
    try:
        store.create_lens(
            student_id="student-synthetic-1",
            display_name=display_name,
            campus="local",
            grade_level="G3",
            home_languages=["it"],
            rti_current_tier=1,
        )
    finally:
        store.close()


# ── fail-closed gate ────────────────────────────────────────────────────────

def test_disabled_when_no_flags(lv_state, monkeypatch):
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    monkeypatch.delenv("LV_ALLOW_RESEARCH", raising=False)
    enabled, reason = is_enabled()
    assert not enabled
    assert "disabled" in reason
    with pytest.raises(ResearchDisabledError):
        research("anything", dry_run=True)
    # Nothing was written to the library
    assert library.status()["doc_count"] == 0


def test_disabled_with_key_but_no_allow_flag(lv_state, monkeypatch):
    monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key-not-real")
    monkeypatch.delenv("LV_ALLOW_RESEARCH", raising=False)
    with pytest.raises(ResearchDisabledError, match="LV_ALLOW_RESEARCH"):
        research("anything", dry_run=True)


def test_disabled_with_allow_flag_but_no_key(lv_state, monkeypatch):
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    monkeypatch.setenv("LV_ALLOW_RESEARCH", "1")
    with pytest.raises(ResearchDisabledError, match="PERPLEXITY_API_KEY"):
        research("anything", dry_run=True)


def test_allow_flag_must_be_exactly_1(lv_state, monkeypatch):
    monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key-not-real")
    monkeypatch.setenv("LV_ALLOW_RESEARCH", "true")
    with pytest.raises(ResearchDisabledError):
        research("anything", dry_run=True)


def test_empty_query_refused(lv_state, research_enabled):
    with pytest.raises(ValueError):
        research("   ", dry_run=True)


# ── sanitization of the outbound query ──────────────────────────────────────

def test_sanitizer_strips_synthetic_student_name(lv_state, research_enabled):
    _seed_student("Nora Rossi")

    sent: list[str] = []

    def transport(query: str) -> tuple[str, list[str]]:
        sent.append(query)
        return "mocked external answer", []

    result = research(
        "How can I support Nora Rossi with dyslexia-friendly reading materials?",
        transport=transport,
    )

    assert sent, "injected transport should have been called"
    assert "Nora" not in sent[0]
    assert "Rossi" not in sent[0]
    assert perplexity_gateway.STUDENT_TOKEN in sent[0]
    assert "dyslexia" in sent[0]  # the pedagogical substance still goes out
    assert "Nora Rossi" in result["scrubbed_students"]
    # And the stored library doc never contains the name either
    assert "Nora" not in result["query_sent"]


def test_sanitizer_redacts_pii_patterns(lv_state, research_enabled):
    out = sanitize_outbound_query(
        "Contact family at nora.rossi@example.org about reading support"
    )
    assert "nora.rossi@example.org" not in out["text"]
    assert out["redactions"]


def test_private_runtime_context_blocked(lv_state, research_enabled):
    # PRIVATE_RUNTIME_PATTERNS match "student: <Name>" shapes → redacted;
    # an IEP reference is private runtime context and must never leave.
    out = sanitize_outbound_query("Summarize the IEP for student: Marco Bianchi")
    assert "Marco Bianchi" not in out["text"]


# ── dry-run + storage ───────────────────────────────────────────────────────

def test_dry_run_stores_result_without_network(lv_state, research_enabled):
    called = []

    def exploding_transport(query):  # pragma: no cover - must not run
        called.append(query)
        raise AssertionError("dry_run must never invoke a transport")

    result = research(
        "IB PYP unit of inquiry examples for grade 4 science",
        dry_run=True,
        transport=exploding_transport,
    )

    assert not called
    assert result["status"] == "ok"
    assert result["dry_run"] is True
    doc = result["doc"]
    assert doc["source"] == "perplexity"
    entries = library.load_index()
    assert len(entries) == 1
    assert entries[0]["doc_id"] == doc["doc_id"]
    # The stored research doc is classified like any ingest
    assert entries[0]["categories"]


def test_research_result_retrievable_from_library(lv_state, research_enabled):
    research("CEFR benchmarks for early readers", dry_run=True)
    hits = library.search("CEFR benchmarks")
    assert hits
    assert hits[0]["source"] == "perplexity"


# ── CLI surface ─────────────────────────────────────────────────────────────

def test_cli_research_fail_closed(lv_state, monkeypatch, capsys):
    from src.lingua_viva.cli import main

    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    monkeypatch.delenv("LV_ALLOW_RESEARCH", raising=False)
    code = main(["research", "anything at all"])
    out = capsys.readouterr().out
    assert code == 2
    assert "Refused" in out
    assert "LV_ALLOW_RESEARCH" in out


def test_cli_research_dry_run(lv_state, research_enabled, capsys):
    from src.lingua_viva.cli import main

    code = main(["research", "grade 3 assessment rubric ideas", "--dry-run"])
    out = capsys.readouterr().out
    assert code == 0
    assert "dry-run" in out
    assert library.status()["doc_count"] == 1


def test_cli_library_add_search_status(lv_state, tmp_path, capsys):
    from src.lingua_viva.cli import main

    doc = tmp_path / "catalogue.md"
    doc.write_text(
        "# Lesson catalogue\n\nUnit plan with central idea and lines of inquiry "
        "for the programme of inquiry.\n",
        encoding="utf-8",
    )
    assert main(["library", "add", str(doc)]) == 0
    assert "Ingested LIB-" in capsys.readouterr().out

    assert main(["library", "search", "central idea"]) == 0
    assert "LIB-" in capsys.readouterr().out

    assert main(["library", "status"]) == 0
    assert "Documents: 1" in capsys.readouterr().out
