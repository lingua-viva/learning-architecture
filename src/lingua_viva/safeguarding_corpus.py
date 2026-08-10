from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from src.lingua_viva import safeguarding as sg


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CORPUS_PATH = REPO_ROOT / "tests" / "fixtures" / "safeguarding_corpus.yaml"


@dataclass(frozen=True)
class SafeguardingCorpusVerdict:
    must_flag: int
    must_stay_green: int
    under_classified: list[dict[str, Any]]
    over_classified: list[dict[str, Any]]

    @property
    def ok(self) -> bool:
        return not self.under_classified and not self.over_classified

    def as_evidence(self) -> dict[str, Any]:
        return {
            "must_flag": self.must_flag,
            "must_stay_green": self.must_stay_green,
            "under_classified": self.under_classified,
            "over_classified": self.over_classified,
        }


def load_safeguarding_corpus(path: Path = DEFAULT_CORPUS_PATH) -> dict[str, list[dict[str, Any]]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    must_flag = data.get("must_flag") or []
    must_stay_green = data.get("must_stay_green") or []
    if not isinstance(must_flag, list) or not isinstance(must_stay_green, list):
        raise ValueError("safeguarding corpus must contain list sections: must_flag, must_stay_green")
    return {
        "must_flag": [dict(item) for item in must_flag],
        "must_stay_green": [dict(item) for item in must_stay_green],
    }


def evaluate_safeguarding_corpus(path: Path = DEFAULT_CORPUS_PATH) -> SafeguardingCorpusVerdict:
    corpus = load_safeguarding_corpus(path)
    under_classified: list[dict[str, Any]] = []
    over_classified: list[dict[str, Any]] = []

    for entry in corpus["must_flag"]:
        phrase = str(entry.get("phrase") or "")
        expected = str(entry.get("minimum_tier") or "")
        result = sg.classify_severity(phrase)
        if sg._TIER_RANK.get(result.tier, -1) < sg._TIER_RANK.get(expected, 99):
            under_classified.append(
                {
                    "phrase": phrase,
                    "expected": expected,
                    "got": result.tier,
                    "rationale": result.rationale,
                }
            )

    for entry in corpus["must_stay_green"]:
        phrase = str(entry.get("phrase") or "")
        result = sg.classify_severity(phrase)
        if result.tier != sg.GREEN:
            over_classified.append(
                {
                    "phrase": phrase,
                    "expected": sg.GREEN,
                    "got": result.tier,
                    "rationale": result.rationale,
                }
            )

    return SafeguardingCorpusVerdict(
        must_flag=len(corpus["must_flag"]),
        must_stay_green=len(corpus["must_stay_green"]),
        under_classified=under_classified,
        over_classified=over_classified,
    )
