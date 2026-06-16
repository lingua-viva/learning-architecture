"""
Self-Improving Signal Weights

Weights learn from path outcomes. No manual curation.
Everything we build must compound from usage.

After each successful path (confidence_at_exit > 0.80):
  - Boost signals that fired by +0.01 (cap at 2.0)
After each failed path (confidence_at_exit < 0.50):
  - Reduce signals that fired by -0.01 (floor at 0.3)

Persisted in ontology/learned_weights.yaml.
Health check reports signals that drifted most from 1.0.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml

from memory.schema.path import PathRecord


DEFAULT_WEIGHT = 1.0
MAX_WEIGHT = 2.0
MIN_WEIGHT = 0.3
BOOST_SUCCESS = 0.01
PENALTY_FAILURE = 0.01
SUCCESS_THRESHOLD = 0.80
FAILURE_THRESHOLD = 0.50


class LearnedWeights:
    """Self-improving signal weights driven by path outcomes."""

    def __init__(self, weights_path: Optional[Path] = None):
        self._path = weights_path or Path(__file__).parent / "learned_weights.yaml"
        self._weights: dict[str, dict[str, float]] = {}  # node_id -> {signal: weight}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            with open(self._path) as f:
                data = yaml.safe_load(f) or {}
            self._weights = data.get("weights", {})

    def _save(self) -> None:
        data = {"weights": self._weights, "description": "Auto-learned from path outcomes. Do not edit manually."}
        with open(self._path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    def get_weight(self, node_id: str, signal: str) -> float:
        """Get the learned weight for a signal at a node."""
        return self._weights.get(node_id, {}).get(signal.lower(), DEFAULT_WEIGHT)

    def update_from_path(self, path_record: PathRecord, signals_matched: list[str]) -> None:
        """
        Update weights based on path outcome.

        Successful paths boost signal weights. Failed paths reduce them.
        The system learns which signals are reliable indicators.
        """
        if not signals_matched:
            return

        node_id = path_record.entry_node
        if node_id not in self._weights:
            self._weights[node_id] = {}

        if path_record.confidence_at_exit >= SUCCESS_THRESHOLD:
            # Success: boost
            for signal in signals_matched:
                key = signal.lower()
                current = self._weights[node_id].get(key, DEFAULT_WEIGHT)
                self._weights[node_id][key] = min(current + BOOST_SUCCESS, MAX_WEIGHT)
        elif path_record.confidence_at_exit < FAILURE_THRESHOLD:
            # Failure: penalize
            for signal in signals_matched:
                key = signal.lower()
                current = self._weights[node_id].get(key, DEFAULT_WEIGHT)
                self._weights[node_id][key] = max(current - PENALTY_FAILURE, MIN_WEIGHT)

        self._save()

    def most_drifted(self, limit: int = 10) -> list[tuple[str, str, float]]:
        """Signals that have drifted most from 1.0 (for health check transparency)."""
        drifted = []
        for node_id, signals in self._weights.items():
            for signal, weight in signals.items():
                drift = abs(weight - DEFAULT_WEIGHT)
                if drift > 0.01:
                    drifted.append((node_id, signal, weight))
        drifted.sort(key=lambda x: abs(x[2] - DEFAULT_WEIGHT), reverse=True)
        return drifted[:limit]
