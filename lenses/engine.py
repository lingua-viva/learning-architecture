"""
Lens Engine

Lenses are the interpretive layer — they change HOW the ontology processes
a query without changing the query or the ontology. A lens is a semantic
filter that applies domain expertise before classification.

Lenses are composable. Each lens has a rationale field that the model
can surface to the user on request.

Activation rules:
  - User selection (explicit)
  - Ontology classification (auto-applied by domain)
  - Confidence threshold (low confidence triggers precision or critique)
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml


class Lens:
    """A single interpretive lens."""

    def __init__(self, data: dict):
        self.name: str = data.get("name", "unknown")
        self.description: str = data.get("description", "")
        self.rationale: str = data.get("rationale", "")
        self.activation_rules: dict = data.get("activation", {})
        self.system_prompt_modifier: str = data.get("system_prompt_modifier", "")
        self.confidence_adjustment: float = data.get("confidence_adjustment", 0.0)
        self.query_rewrite_rules: list[dict] = data.get("query_rewrite_rules", [])

    def should_activate(
        self,
        intent: Optional[str] = None,
        domain: Optional[str] = None,
        confidence: float = 1.0,
        user_requested: bool = False,
        query: Optional[str] = None,
    ) -> bool:
        """Determine if this lens should activate given the context."""
        if user_requested:
            return True
        rules = self.activation_rules
        if intent and rules.get("on_intent") == intent:
            return True
        on_domain = rules.get("on_domain")
        if domain and on_domain:
            # on_domain may be a single domain string or a list of domains —
            # list form covers lenses whose subject matter spans more than
            # one ontology domain (e.g. differentiation-coach activates on
            # both "curriculum" and "teacher" nodes).
            domains = on_domain if isinstance(on_domain, list) else [on_domain]
            if domain in domains:
                return True
        threshold = rules.get("on_confidence_below")
        if threshold and confidence < threshold:
            return True
        keywords = rules.get("on_signal_keywords")
        if keywords and query:
            lowered = query.lower()
            if any(kw.lower() in lowered for kw in keywords):
                return True
        return False

    def apply_to_prompt(self, base_prompt: str) -> str:
        """Inject lens modifier into the system prompt."""
        if self.system_prompt_modifier:
            return f"{self.system_prompt_modifier}\n\n{base_prompt}"
        return base_prompt


class LensEngine:
    """Manages and applies lenses."""

    def __init__(self, lenses_dir: Optional[Path] = None):
        self.lenses: dict[str, Lens] = {}
        if lenses_dir is None:
            lenses_dir = Path(__file__).parent
        self._load_lenses(lenses_dir)

    def _load_lenses(self, lenses_dir: Path) -> None:
        for subdir in ["core", "professional", "education"]:
            dir_path = lenses_dir / subdir
            if not dir_path.exists():
                continue
            for yaml_file in sorted(dir_path.glob("*.yaml")):
                with open(yaml_file, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if data:
                    lens = Lens(data)
                    self.lenses[lens.name] = lens

    def get_active_lenses(
        self,
        intent: Optional[str] = None,
        domain: Optional[str] = None,
        confidence: float = 1.0,
        user_requested: Optional[list[str]] = None,
        query: Optional[str] = None,
    ) -> list[Lens]:
        """Get all lenses that should be active for this context."""
        active = []
        requested = set(user_requested or [])
        for name, lens in self.lenses.items():
            if lens.should_activate(
                intent=intent,
                domain=domain,
                confidence=confidence,
                user_requested=(name in requested),
                query=query,
            ):
                active.append(lens)
        return active

    def apply_lenses(
        self,
        base_prompt: str,
        lenses: list[Lens],
    ) -> str:
        """Apply multiple lenses to a base prompt. Lenses compose."""
        prompt = base_prompt
        for lens in lenses:
            prompt = lens.apply_to_prompt(prompt)
        return prompt

    def get_lens(self, name: str) -> Optional[Lens]:
        return self.lenses.get(name)
