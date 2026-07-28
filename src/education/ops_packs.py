"""
Ops Packs — workflow-pack loader, category registry, and compiled rule set
for the Slack Daily Operations Assistant (v2).

Spec: dev/specs/SPEC_LV_SLACK_OPS_V2_WORKFLOW_PACKS_2026-07-27.md §3, §5.

Design decisions (operator-ruled 2026-07-27, spec §3 "Architecture reality
check" — do not re-litigate):
  - Only vocabulary & routing are data (§3(a)): category cue regexes,
    category→section mapping, broadcast membership, review-required
    defaults, sample sentences. Interaction FLOWS stay code forever in v2
    (§3(b)) — a pack may only enable/disable and parameterize a
    code-backed capability, keyed by a stable `capability` id. Shared
    infrastructure (entity extraction, binary confidence, To Review
    machinery, daily-file mechanics, the `other` fallback) is core and
    is never owned or duplicated by a pack (§3(c)).
  - Shipped packs are READ-ONLY repo/bundle data at config/ops_packs/
    (the app never writes into LV_ROOT). One pack = one YAML file with a
    commented schema header.
  - The v1-parity default compile (all five launch packs enabled,
    facilities included — spec §3.1/§3.3) MUST reproduce v1's hardcoded
    behavior exactly: category set, priority order, section mapping,
    broadcast set, and regex behavior. The 168-test v1 ops suite plus a
    dedicated parity test pin this.
  - Priority order is load-bearing (spec §3.1): earlier wins. The
    registry carries an explicit integer priority per category; the
    compiled evaluation order is ascending priority. v1's actual
    evaluation order (ops_classifier v1 classify(): absence →
    coverage_claim → coverage_request → schedule_change →
    student_logistics → facilities → reminder → positional announcement)
    is what the launch packs encode.
  - `announcement` is positional, not lexical (spec §3.1): the ops-channel
    high-trust default bucket. Its pack entry says `channel_default: true`
    and carries NO vocabulary.
  - `other` is core, not a pack (spec §3.1): fallback + clarification +
    To Review; cannot be disabled. This module contributes it to every
    compile.
  - Disabled-pack semantics (spec §3.4): a message whose only matching
    category belongs to a disabled pack falls through to core `other` →
    clarification / To Review — never dropped. Section list, broadcast
    set, and the priority chain derive from ENABLED packs only.
  - YAML loading is yaml.safe_load-family with a size cap AND an
    alias-refusing loader (this repo already ate a 419-byte YAML
    alias-bomb startup hang in the one-button-update lane — see
    src/lingua_viva/reconcile.py). Malformed pack files fail closed:
    the pack is skipped with a warning, never half-applied.
  - The CURRENT compile is one module-level reference read through
    `current_rule_set()`; `install_rule_set()` swaps it atomically
    (one reference assignment — spec §3.2 reload ruling). The classifier,
    daily engine, and bot read through this seam. No file watchers.
  - Learned rules (spec §4) OR into their target category's vocabulary at
    that category's EXISTING priority slot; they can never reorder
    priorities and can never target core `other`. Enforced here at
    compile time.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKS_DIR = REPO_ROOT / "config" / "ops_packs"

# Core category (spec §3.1): fallback + clarification + To Review. Not a
# pack; cannot be disabled.
CORE_CATEGORY_OTHER = "other"

# Core sections contributed to every compile: `other` renders under
# Announcements (v1 daily_file mapping) and To Review always exists.
_CORE_SECTIONS = {"Announcements": 40, "To Review": 100}
_CORE_CATEGORY_SECTIONS = {CORE_CATEGORY_OTHER: "Announcements"}

# YAML guards (house pattern, see module docstring).
MAX_PACK_BYTES = 256 * 1024


class PackLoadError(ValueError):
    """A pack (or bot-spec fragment) failed to load safely."""


class _NoAliasLoader(yaml.SafeLoader):
    """safe_load that refuses YAML aliases outright (alias-bomb guard)."""

    def compose_node(self, parent, index):  # noqa: D102
        if self.check_event(yaml.events.AliasEvent):
            raise yaml.YAMLError("YAML aliases are not allowed in ops pack data")
        return super().compose_node(parent, index)


def load_yaml_guarded(raw: bytes, *, max_bytes: int = MAX_PACK_BYTES):
    """Parse YAML with size + alias guards. Raises PackLoadError on anything
    suspicious — callers fail closed (skip the file / fall back to parity)."""
    if len(raw) > max_bytes:
        raise PackLoadError(f"YAML exceeds parse cap ({len(raw)} > {max_bytes} bytes)")
    try:
        return yaml.load(raw.decode("utf-8"), Loader=_NoAliasLoader)
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
        raise PackLoadError(f"YAML parse failed: {type(exc).__name__}") from exc


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CategoryEntry:
    """One registry entry (spec §3.1): everything routing needs to know
    about a category, populated from pack data."""

    id: str
    priority: int
    section: str
    broadcast: bool = False
    review_required_default: bool = False
    capability: Optional[str] = None
    channel_default: bool = False
    patterns: tuple = ()          # compiled regexes (vocabulary)
    learned_patterns: tuple = ()  # compiled approved learned rules (spec §4)
    pack_id: str = ""

    def matches(self, text: str) -> bool:
        return any(p.search(text) for p in self.patterns) or any(
            p.search(text) for p in self.learned_patterns
        )


@dataclass(frozen=True)
class SectionEntry:
    name: str
    rank: int
    always_render: bool = False
    empty_line: str = ""


@dataclass(frozen=True)
class SampleSentence:
    """Pack/admin test-corpus sample (spec §7). Date expectations are
    RELATIVE ("+1d", "+0d") so they never rot."""

    text: str
    expect: dict
    pack_id: str = ""


@dataclass(frozen=True)
class OpsPack:
    id: str
    name: str
    description: str
    enabled_by_default: bool
    categories: tuple  # tuple[CategoryEntry]
    sections: tuple    # tuple[SectionEntry]
    samples: tuple     # tuple[SampleSentence]
    # Setup-panel hint only (spec §10 open question 3): pre-checked for a
    # NEW school's interview. Never consulted by the parity compile —
    # enabled_by_default is what preserves v1 behavior.
    default_for_new_schools: bool = True


@dataclass(frozen=True)
class CompiledRuleSet:
    """The single object classification/routing consults. Immutable —
    swapped atomically as one reference (spec §3.2)."""

    entries: tuple                    # CategoryEntry, ascending priority
    section_order: tuple              # section names, render order
    category_sections: dict           # category id -> section name (incl. other)
    broadcast_categories: frozenset   # enabled broadcast category ids
    always_render: dict               # section name -> empty line
    channel_default_category: Optional[str]
    review_required: frozenset = frozenset()   # settings gate (spec §6)
    period_alias_patterns: tuple = ()          # settings-fed core extension (§2.2)
    enabled_pack_ids: tuple = ()
    samples: tuple = ()

    def category_ids(self) -> tuple:
        return tuple(entry.id for entry in self.entries)

    def entry_for(self, category: str) -> Optional[CategoryEntry]:
        for entry in self.entries:
            if entry.id == category:
                return entry
        return None

    def capability_for(self, category: str) -> Optional[str]:
        entry = self.entry_for(category)
        return entry.capability if entry else None

    def section_for(self, category: str) -> str:
        return self.category_sections.get(category, "Announcements")

    def pattern_search(self, category: str, text: str) -> bool:
        entry = self.entry_for(category)
        return bool(entry and entry.matches(text))

    def match_category(self, text: str) -> Optional[str]:
        """First keyword-triggered category whose vocabulary matches,
        in priority order (earlier wins — spec §3.1)."""
        for entry in self.entries:
            if entry.channel_default:
                continue  # positional, never keyword-triggered
            if entry.matches(text):
                return entry.id
        return None


# ---------------------------------------------------------------------------
# Pack loading
# ---------------------------------------------------------------------------


def _require_str(value, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PackLoadError(f"{what} must be a non-empty string")
    return value.strip()


def _compile_patterns(patterns, what: str) -> tuple:
    compiled = []
    for pattern in patterns or []:
        if not isinstance(pattern, str) or not pattern.strip():
            raise PackLoadError(f"{what}: vocabulary entries must be strings")
        try:
            compiled.append(re.compile(pattern, re.IGNORECASE))
        except re.error as exc:
            raise PackLoadError(f"{what}: bad regex ({exc})") from exc
    return tuple(compiled)


def _parse_pack(data: dict, source: str) -> OpsPack:
    if not isinstance(data, dict):
        raise PackLoadError(f"{source}: pack file must be a YAML mapping")
    pack_id = _require_str(data.get("id"), f"{source}: id")
    name = _require_str(data.get("name"), f"{source}: name")
    description = str(data.get("description") or "").strip()
    enabled_by_default = bool(data.get("enabled_by_default", True))

    sections = []
    for raw in data.get("sections") or []:
        if not isinstance(raw, dict):
            raise PackLoadError(f"{source}: sections entries must be mappings")
        sections.append(
            SectionEntry(
                name=_require_str(raw.get("name"), f"{source}: section name"),
                rank=int(raw.get("rank", 50)),
                always_render=bool(raw.get("always_render", False)),
                empty_line=str(raw.get("empty_line") or ""),
            )
        )

    categories = []
    for raw in data.get("categories") or []:
        if not isinstance(raw, dict):
            raise PackLoadError(f"{source}: categories entries must be mappings")
        category_id = _require_str(raw.get("id"), f"{source}: category id")
        if category_id == CORE_CATEGORY_OTHER:
            raise PackLoadError(
                f"{source}: category 'other' is core and cannot be pack-defined"
            )
        channel_default = bool(raw.get("channel_default", False))
        patterns = _compile_patterns(
            raw.get("vocabulary"), f"{source}: {category_id}"
        )
        if channel_default and patterns:
            raise PackLoadError(
                f"{source}: {category_id} is channel_default (positional) and "
                f"must not carry vocabulary (spec §3.1)"
            )
        categories.append(
            CategoryEntry(
                id=category_id,
                priority=int(raw.get("priority", 50)),
                section=_require_str(raw.get("section"), f"{source}: {category_id} section"),
                broadcast=bool(raw.get("broadcast", False)),
                review_required_default=bool(raw.get("review_required_default", False)),
                capability=(str(raw["capability"]).strip() if raw.get("capability") else None),
                channel_default=channel_default,
                patterns=patterns,
                pack_id=pack_id,
            )
        )
    if not categories:
        raise PackLoadError(f"{source}: pack defines no categories")

    samples = []
    for raw in data.get("samples") or []:
        if not isinstance(raw, dict):
            raise PackLoadError(f"{source}: samples entries must be mappings")
        expect = raw.get("expect")
        if not isinstance(expect, dict) or not expect.get("category"):
            raise PackLoadError(f"{source}: sample expect must name a category")
        samples.append(
            SampleSentence(
                text=_require_str(raw.get("text"), f"{source}: sample text"),
                expect=dict(expect),
                pack_id=pack_id,
            )
        )

    return OpsPack(
        id=pack_id,
        name=name,
        description=description,
        enabled_by_default=enabled_by_default,
        categories=tuple(categories),
        sections=tuple(sections),
        samples=tuple(samples),
        default_for_new_schools=bool(
            data.get("default_for_new_schools", enabled_by_default)
        ),
    )


def load_packs(packs_dir: Optional[Path] = None) -> dict:
    """Load every shipped pack. Returns {pack_id: OpsPack}, skipping (with a
    warning) any file that fails the guards — a bad pack must never take the
    assistant down or half-apply."""
    directory = Path(packs_dir) if packs_dir else PACKS_DIR
    packs: dict = {}
    if not directory.is_dir():
        return packs
    for path in sorted(directory.glob("*.yaml")):
        try:
            data = load_yaml_guarded(path.read_bytes())
            pack = _parse_pack(data, path.name)
        except (PackLoadError, OSError) as exc:
            logger.warning("[ops-packs] skipping %s: %s", path.name, exc)
            continue
        if pack.id in packs:
            logger.warning("[ops-packs] duplicate pack id %r in %s — skipped", pack.id, path.name)
            continue
        packs[pack.id] = pack
    return packs


# ---------------------------------------------------------------------------
# Compilation
# ---------------------------------------------------------------------------


def compile_rule_set(
    enabled_pack_ids: Optional[list] = None,
    *,
    packs: Optional[dict] = None,
    review_required: Optional[set] = None,
    learned_rules: Optional[list] = None,
    period_alias_patterns: Optional[list] = None,
    extra_samples: Optional[list] = None,
) -> CompiledRuleSet:
    """Compile enabled packs (+ optional bot-spec inputs) into one immutable
    rule set. With defaults (all default-enabled packs, no extras) this is
    the v1-parity compile (spec §3.3).

    learned_rules: [{"category": ..., "pattern": ...}] — approved rules only
    (spec §4). They OR into the category's existing priority slot; unknown/
    disabled targets and core `other` are rejected.
    """
    all_packs = packs if packs is not None else load_packs()
    if enabled_pack_ids is None:
        enabled = [p for p in all_packs.values() if p.enabled_by_default]
    else:
        enabled = [all_packs[pid] for pid in enabled_pack_ids if pid in all_packs]

    entries: list = []
    sections: dict = dict(_CORE_SECTIONS)
    always_render: dict = {}
    samples: list = []
    for pack in enabled:
        for section in pack.sections:
            current = sections.get(section.name)
            sections[section.name] = min(current, section.rank) if current is not None else section.rank
            if section.always_render:
                always_render[section.name] = section.empty_line or f"- No {section.name.lower()} today."
        entries.extend(pack.categories)
        samples.extend(pack.samples)

    seen: set = set()
    for entry in entries:
        if entry.id in seen:
            raise PackLoadError(f"category {entry.id!r} defined by more than one enabled pack")
        seen.add(entry.id)

    # Learned rules OR into existing categories at existing priorities
    # (spec §4 precedence ruling). Never `other`, never a new category.
    learned_by_category: dict = {}
    for rule in learned_rules or []:
        target = str(rule.get("category") or "")
        pattern = str(rule.get("pattern") or "")
        if target == CORE_CATEGORY_OTHER or target not in seen or not pattern:
            logger.warning("[ops-packs] ignoring learned rule for %r (invalid target)", target)
            continue
        try:
            learned_by_category.setdefault(target, []).append(
                re.compile(pattern, re.IGNORECASE)
            )
        except re.error:
            logger.warning("[ops-packs] ignoring learned rule for %r (bad regex)", target)

    if learned_by_category:
        entries = [
            CategoryEntry(
                id=e.id,
                priority=e.priority,
                section=e.section,
                broadcast=e.broadcast,
                review_required_default=e.review_required_default,
                capability=e.capability,
                channel_default=e.channel_default,
                patterns=e.patterns,
                learned_patterns=tuple(learned_by_category.get(e.id, ())),
                pack_id=e.pack_id,
            )
            for e in entries
        ]

    entries.sort(key=lambda entry: (entry.priority, entry.id))

    category_sections = {entry.id: entry.section for entry in entries}
    category_sections.update(_CORE_CATEGORY_SECTIONS)
    for entry in entries:
        sections.setdefault(entry.section, 50)

    channel_default = None
    for entry in entries:
        if entry.channel_default:
            channel_default = entry.id
            break

    compiled_aliases = []
    for alias in period_alias_patterns or []:
        if isinstance(alias, str) and alias.strip():
            try:
                compiled_aliases.append(re.compile(alias, re.IGNORECASE))
            except re.error:
                logger.warning("[ops-packs] ignoring bad period alias pattern")

    return CompiledRuleSet(
        entries=tuple(entries),
        section_order=tuple(sorted(sections, key=lambda name: (sections[name], name))),
        category_sections=category_sections,
        broadcast_categories=frozenset(e.id for e in entries if e.broadcast),
        always_render=always_render,
        channel_default_category=channel_default,
        review_required=frozenset(review_required or ()),
        period_alias_patterns=tuple(compiled_aliases),
        enabled_pack_ids=tuple(pack.id for pack in enabled),
        samples=tuple(samples) + tuple(extra_samples or ()),
    )


def known_categories(packs: Optional[dict] = None) -> tuple:
    """Every category any shipped pack can produce, plus core `other`.
    The record STORE validates against this full catalog (not the enabled
    set) so historical records from since-disabled packs stay loadable."""
    all_packs = packs if packs is not None else load_packs()
    ids = []
    for pack in all_packs.values():
        for entry in pack.categories:
            if entry.id not in ids:
                ids.append(entry.id)
    ids.append(CORE_CATEGORY_OTHER)
    return tuple(ids)


# ---------------------------------------------------------------------------
# Current-compile seam (spec §3.2: atomic in-process swap)
# ---------------------------------------------------------------------------

_default_rule_set: Optional[CompiledRuleSet] = None
_current_rule_set: Optional[CompiledRuleSet] = None


def default_rule_set() -> CompiledRuleSet:
    """The v1-parity compile (all default-enabled shipped packs). Cached;
    also the fail-closed fallback when a bot-spec is malformed."""
    global _default_rule_set
    if _default_rule_set is None:
        _default_rule_set = compile_rule_set()
    return _default_rule_set


def current_rule_set() -> CompiledRuleSet:
    """What the classifier/daily engine/bot consult. Defaults to the
    v1-parity compile until a bot-spec is installed."""
    return _current_rule_set if _current_rule_set is not None else default_rule_set()


def install_rule_set(rule_set: Optional[CompiledRuleSet]) -> None:
    """Atomic swap (one reference assignment). None resets to parity."""
    global _current_rule_set
    _current_rule_set = rule_set
