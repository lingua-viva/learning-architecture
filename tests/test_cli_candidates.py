"""
`lv candidates` — read-only candidate listing (Track A item 3,
REPORT_LV_EXTERNAL_FEEDBACK_TRANSFER_2026-07-25.md).

Contract: visibility only. The command must list candidates without
evaluating, promoting, discarding, or mutating any candidate file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ontology.proposals.candidate import CandidateStore
from src.lingua_viva.cli import main


@pytest.fixture
def store_dir(tmp_path, monkeypatch):
    """Point CandidateStore's default dir at a temp proposals dir."""
    def _init(self, proposals_dir=None):
        self._dir = tmp_path
        self._dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(CandidateStore, "__init__", _init)
    return tmp_path


def _seed(tmp_path: Path) -> None:
    store = CandidateStore(tmp_path)
    store.create(
        query="how do I plan a G3 phonics rotation",
        query_hash="hash-1",
        fallback_node="EDU-FALLBACK",
        fallback_confidence=0.31,
        signals=["phonics", "rotation", "small group"],
        domain="literacy",
    )


def test_candidates_empty(store_dir, capsys):
    assert main(["candidates"]) == 0
    out = capsys.readouterr().out
    assert "No active candidates" in out


def test_candidates_lists_active(store_dir, capsys):
    _seed(store_dir)
    assert main(["candidates"]) == 0
    out = capsys.readouterr().out
    assert "CAND-" in out
    assert "CREATED" in out
    assert "phonics" in out
    assert "literacy" in out


def test_candidates_is_read_only(store_dir, capsys):
    _seed(store_dir)
    files = sorted(store_dir.glob("CAND-*.yaml"))
    before = [(f.name, f.read_text(encoding="utf-8")) for f in files]
    assert main(["candidates"]) == 0
    after = [(f.name, f.read_text(encoding="utf-8")) for f in sorted(store_dir.glob("CAND-*.yaml"))]
    assert before == after, "listing must not mutate candidate files"


def test_candidates_hides_discarded_by_default(store_dir, capsys):
    _seed(store_dir)
    store = CandidateStore(store_dir)
    cand = list(store.list_active())[0]
    cand.status = "DISCARDED"
    cand.resolution = "discarded:single_use"
    store._save(cand)

    assert main(["candidates"]) == 0
    out = capsys.readouterr().out
    assert "No active candidates" in out

    assert main(["candidates", "--all"]) == 0
    out = capsys.readouterr().out
    assert "DISCARDED" in out
    assert "discarded:single_use" in out
