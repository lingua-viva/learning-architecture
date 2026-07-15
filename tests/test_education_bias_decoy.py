"""
Education-domain routing bias decoy tests — Gap 5b, SPEC_ONE_CLICK_LOCAL_APP
_2026-07-14.md.

`ontology/engine.py::_rank_score()` now applies a `SIR_EDUCATION_BIAS` flat
additive boost (default 0.20 — see the TEMPORARY comment at the insertion
point) to any node whose id starts with "LV-", as a stopgap for the
documented `_rank_score()` coverage-bias bug that misrouted 2 of 3 Turn 21
demo queries (BUILD_JOURNAL.md). The fix must not trade "misses education
queries" for "wrongly claims everything is an education query" — this
suite proves the bias, applied at its shipped default, does not misroute
plainly non-education queries into an LV-* node.

Uses the real decoy entries already curated in tests/golden_education_v1.yaml
(the "Decoys: cross-domain and near-miss disambiguation" section) rather
than inventing new ones — EDU-DECOY-003 in particular is the exact
signal-collision case ("rubric" is a shared LV-ASS-001/legal-contract
token) that a coverage-bias-style boost could plausibly break.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml
import pytest

from ontology.engine import OntologyEngine

GOLDEN_PATH = Path(__file__).parent / "golden_education_v1.yaml"


@pytest.fixture(scope="module")
def engine():
    return OntologyEngine()


@pytest.fixture(scope="module")
def decoy_queries():
    data = yaml.safe_load(GOLDEN_PATH.read_text())
    return [q for q in data["queries"] if q.get("difficulty") == "decoy"]


def test_golden_file_has_decoy_queries(decoy_queries):
    """Guards against this test silently doing nothing if the golden file's
    decoy section is ever emptied or renamed."""
    assert len(decoy_queries) >= 5


def test_education_bias_defaults_to_020_when_unset(monkeypatch):
    monkeypatch.delenv("SIR_EDUCATION_BIAS", raising=False)
    from ontology.engine import OntologyEngine as _E
    e = _E()
    lv_node = next(n for n in e.nodes.values() if n.id.startswith("LV-"))
    score_with_default = e._rank_score(lv_node, ["x"], None, None)

    monkeypatch.setenv("SIR_EDUCATION_BIAS", "0")
    score_disabled = e._rank_score(lv_node, ["x"], None, None)

    assert score_with_default == pytest.approx(score_disabled + 0.20)


def test_bias_does_not_misroute_cross_domain_decoys_at_shipped_default(engine, decoy_queries, monkeypatch):
    """The core Gap 5b requirement: with the bias active at its shipped
    default (0.20, no env override), every non-education decoy must still
    resolve to its expected non-LV- node."""
    monkeypatch.delenv("SIR_EDUCATION_BIAS", raising=False)
    failures = []
    for q in decoy_queries:
        expected = q["expected_node"]
        if expected.startswith("LV-"):
            continue  # this decoy's correct answer IS an education node — not this test's concern
        result = engine.classify(q["query"])
        if result.riu_id.startswith("LV-"):
            failures.append(
                f"{q['id']}: {q['query']!r} misrouted to {result.riu_id} "
                f"(expected {expected}) — {q.get('note', '')}"
            )
    assert not failures, "Education bias misrouted decoys:\n" + "\n".join(failures)


def test_rubric_signal_collision_decoy_stays_legal_not_education(engine, monkeypatch):
    """EDU-DECOY-003 specifically: 'rubric' is a real signal on both
    LV-ASS-001 and this legal contract-review query's context. This is the
    single most plausible failure mode for a coverage-bias-style boost."""
    monkeypatch.delenv("SIR_EDUCATION_BIAS", raising=False)
    result = engine.classify("Can you review the rubric clause in the vendor contract renewal?")
    assert result.riu_id == "MC-LEGAL-004"
    assert not result.riu_id.startswith("LV-")


def test_no_signal_match_query_still_falls_back_cleanly(engine, monkeypatch):
    """EDU-DECOY-005: a query with no domain signal at all must not be
    dragged into an education node just because LV- nodes get a flat boost
    when they ARE candidates — the bias must never manufacture a candidacy
    that signal matching didn't produce."""
    monkeypatch.delenv("SIR_EDUCATION_BIAS", raising=False)
    result = engine.classify("What's the weather forecast for tomorrow's field trip?")
    assert not result.riu_id.startswith("LV-")
