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
    """Manages and applies lenses.

    Live-layer overlay (SPEC_LIVE_LAYER_READ_PATH_2026-07-27): on default
    construction (no ``lenses_dir``), after the bundle lenses load, every
    ``*.yaml`` under ``live_root()/lenses/education/`` is overlaid — live
    wins by case-folded lens ``name``. This is what makes teacher edits
    preserved by the one-button update system actually change behavior.
    Explicit ``lenses_dir`` (tests) keeps exact bundle-only behavior.
    Every failure path lands on shipped-bundle behavior, never a crash.
    """

    def __init__(self, lenses_dir: Optional[Path] = None):
        self.lenses: dict[str, Lens] = {}
        # Live-overlay files skipped with a reason (bad parse, guard trip,
        # namespace collision). Doctor's live_templates check surfaces these
        # via scan_live_lens_issues() — a skip must never be a silent state.
        self.skipped_live: list[dict] = []
        # Case-folded names owned by bundle core/ and professional/ lenses.
        # The live education overlay may only shadow or add names outside
        # this set — a teacher file named "protection" must not hijack a
        # core lens via dict-key overwrite.
        self._protected_names: set[str] = set()
        overlay = lenses_dir is None
        if lenses_dir is None:
            lenses_dir = Path(__file__).parent
        self._load_lenses(lenses_dir)
        if overlay:
            self._overlay_live_lenses()

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
                    if subdir in ("core", "professional"):
                        self._protected_names.add(lens.name.casefold())

    def _overlay_live_lenses(self) -> None:
        """Overlay teacher-editable live-layer lenses over the bundle set.

        Failure direction is law: a broken update subsystem (ImportError),
        an unreadable dir, or any bad file must leave the engine exactly as
        the bundle loaded it — skip + record, never raise.
        """
        try:
            from src.lingua_viva.reconcile import _parse_yaml_guarded, live_root
        except Exception:
            # Update subsystem unavailable → bundle-only, today's behavior.
            return
        try:
            live_dir = live_root() / "lenses" / "education"
            if not live_dir.is_dir():
                return
            yaml_files = sorted(live_dir.glob("*.yaml"))
        except Exception:
            return
        for yaml_file in yaml_files:
            try:
                data = _parse_yaml_guarded(yaml_file.read_bytes())
            except Exception as exc:
                self.skipped_live.append({
                    "path": str(yaml_file),
                    "reason": f"could not be read: {exc}",
                })
                continue
            if not isinstance(data, dict) or not data:
                self.skipped_live.append({
                    "path": str(yaml_file),
                    "reason": "not a YAML mapping",
                })
                continue
            lens = Lens(data)
            folded = lens.name.casefold()
            if folded in self._protected_names:
                self.skipped_live.append({
                    "path": str(yaml_file),
                    "reason": (
                        f"name '{lens.name}' is owned by a core/professional "
                        "lens and cannot be shadowed from the live layer"
                    ),
                })
                continue
            # Live wins by case-folded name: drop a bundle entry whose name
            # differs only in case before registering the live copy.
            for existing in [k for k in self.lenses if k.casefold() == folded]:
                del self.lenses[existing]
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


def scan_live_lens_issues() -> list[dict]:
    """Recompute the live-overlay skip list for Doctor's live_templates check.

    Constructs a default engine (bundle + overlay, <100ms budget) and returns
    its ``skipped_live`` records: files that failed the guarded parse and
    files skipped by the core/professional namespace guard. The pacdiff
    lesson applied to the read path — a teacher edit silently not applying
    must be a visible health item.
    """
    return LensEngine().skipped_live
