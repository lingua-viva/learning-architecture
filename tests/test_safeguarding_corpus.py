from __future__ import annotations

from src.lingua_viva import safeguarding as sg
from src.lingua_viva.safeguarding_corpus import load_safeguarding_corpus


def test_safeguarding_corpus_shape_and_provenance():
    corpus = load_safeguarding_corpus()
    assert len(corpus["must_flag"]) >= 25
    assert len(corpus["must_stay_green"]) >= 10

    for section, entries in corpus.items():
        assert entries, f"{section} must not be empty"
        for entry in entries:
            assert entry.get("phrase"), f"{section} entry missing phrase: {entry}"
            assert entry.get("source"), f"{section} entry missing source: {entry}"
            assert entry.get("added"), f"{section} entry missing added: {entry}"
            if section == "must_flag":
                assert entry.get("minimum_tier") in {sg.AMBER, sg.RED}, (
                    f"must_flag entry has invalid minimum_tier: {entry}"
                )


def test_must_flag_phrases_meet_minimum_tier():
    corpus = load_safeguarding_corpus()
    for entry in corpus["must_flag"]:
        result = sg.classify_severity(entry["phrase"])
        expected = entry["minimum_tier"]
        assert sg._TIER_RANK[result.tier] >= sg._TIER_RANK[expected], (
            f"phrase={entry['phrase']!r} expected>={expected} got={result.tier} "
            f"rationale={result.rationale!r}"
        )


def test_must_stay_green_phrases_remain_green():
    corpus = load_safeguarding_corpus()
    for entry in corpus["must_stay_green"]:
        result = sg.classify_severity(entry["phrase"])
        assert result.tier == sg.GREEN, (
            f"phrase={entry['phrase']!r} expected=GREEN got={result.tier} "
            f"rationale={result.rationale!r}"
        )
