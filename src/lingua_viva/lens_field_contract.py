"""The lens field contract — the one declared answer to "what is a lens field".

SPEC: dev/SPEC_LENS_FIELD_CONTRACT_2026-09-03.md · BASELINE: dev/BASELINE_LENS_FIELD_CONTRACT_2026-09-03.md
Operator ruling A (2026-09-03, clearing kill gate K8): the STORE's field
namespace is the contract. docpipe.lens.v1 is a producer; its evidence
discipline is a requirement on producers, not a second storage shape. The
bridge's mapping is declared here as-is (see `strategies_trialed`).

Before this module, five lists each claimed to define a lens field and none
was authoritative (baseline B1); an extractor could invent a path the writer
did not implement and nothing was obliged to notice (baseline B4a: one path
still silently dropped, one uncaught exception). Now:

  * every path a producer may write is declared here, once, with its kind,
    origin, status, store operation, validator and sensitivity;
  * `resolve(field_path)` is the only way in — `student_lens_writer` dispatches
    on the resolved spec's `kind`, never on string prefixes;
  * the registry is validated at import time: a `writer` that names a store
    operation that does not exist raises `LensContractError` here, not an
    `AttributeError` at write time;
  * `requires(output_id)` is the OUT filter: each output declares the fields
    it consumes, resolved through the same registry, so an output can say
    what it did not have (spec §2.8).

Glass-box, not gatekeeping (Palette `integrity_gate.py`): an unresolvable
path refuses THAT FIELD by name with a reason; it never voids a document.

Where the five lists disagreed, both sides are recorded in `note`, never
unified silently (spec §2.3). `kind` is a STORAGE taxonomy; `governance_class`
is separate and is `subject` for every student-lens field (spec §2.7.2).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from src.education.student_lens import (
    SUPPORT_CATEGORY_IDS,
    VALID_CEFR_DIMENSIONS,
    VALID_CEFR_LEVELS,
    VALID_SUPPORT_BUCKETS,
    StudentLensStore,
)

__all__ = [
    "FieldSpec",
    "ResolvedField",
    "FieldRequirement",
    "LensContractError",
    "MissingEssentialFieldError",
    "REGISTRY",
    "STUDENT_COLUMNS",
    "LENS_SHAPES",
    "OUTPUT_REQUIREMENTS",
    "resolve",
    "requires",
    "read_for",
    "declared_paths",
    "writable_paths",
    "support_buckets",
]


class LensContractError(Exception):
    """The registry itself is inconsistent (raised at import time)."""


class MissingEssentialFieldError(Exception):
    """An output asked for a lens field it declared essential and the lens
    does not have it. The output must refuse to render, naming the field."""

    def __init__(self, output_id: str, missing: list[str]):
        self.output_id = output_id
        self.missing = list(missing)
        super().__init__(
            f"{output_id} cannot render: essential lens field(s) missing: "
            + ", ".join(self.missing)
        )


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

KINDS = ("scalar", "cefr", "support_profile", "strengths", "ethos_profile", "blob", "marker")
ORIGINS = ("authored", "derived", "projection")
STATUSES = ("writable", "declared_not_implemented", "read_only")
SENSITIVITIES = ("normal", "restricted")

# Every column of the `students` table, as created by StudentLensStore._init_schema.
# Pinned by tests/test_lens_field_contract.py against PRAGMA table_info.
STUDENT_COLUMNS: tuple[str, ...] = (
    "student_id", "display_name", "campus", "grade_level", "home_languages",
    "learning_differences", "trauma_flag", "avoid_pairing_with", "rti_current_tier",
    "rti_tier_history", "cefr_snapshot", "cefr_trajectory_30d", "sel_summary",
    "support_profile", "strengths_profile", "ethos_profile", "background_notes",
    "profile_version", "created_at", "updated_at", "deleted", "deleted_at",
)

# The evidence bucket is a peer of the five entry buckets inside a category.
SUPPORT_BUCKETS_ALL: tuple[str, ...] = tuple(VALID_SUPPORT_BUCKETS) + ("evidence",)

# Declared internal shape of each JSON blob (spec §2.6): the keys a consumer
# may rely on. Undeclared keys inside a blob are the same defect as undeclared
# paths outside it.
LENS_SHAPES: dict[str, dict[str, Any]] = {
    "cefr_snapshot": {dim: "level|null" for dim in VALID_CEFR_DIMENSIONS},
    "rti_tier_history": {"[]": {"tier": "int", "from": "iso", "to": "iso|null", "trigger": "str|null"}},
    "sel_summary": {
        "recent_concerns": "int", "recent_positives": "int",
        "dominant_domain": "str|null", "last_urgency_flag": "iso|null",
    },
    "support_profile": {
        "schema_version": 2,
        "categories": {cat: {b: "[]" for b in SUPPORT_BUCKETS_ALL} for cat in SUPPORT_CATEGORY_IDS},
        "last_reviewed_at": "iso|null", "last_reviewed_by": "str|null",
    },
    "strengths_profile": {
        "schema_version": 1, "academic_strengths": "[]", "personal_strengths": "[]",
        "last_reviewed_at": "iso|null", "last_reviewed_by": "str|null",
    },
    "ethos_profile": {"traits": {"{trait_id}": {"evidence": "[]"}}},
}


# ---------------------------------------------------------------------------
# FieldSpec
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FieldSpec:
    path: str                       # canonical path, or a pattern with {named} segments
    kind: str                       # storage taxonomy (KINDS)
    origin: str                     # authored | derived | projection
    status: str                     # writable | declared_not_implemented | read_only
    writer: Optional[str] = None    # "store:<StudentLensStore method>" | "column:<students column>" | None
    requires_sources: bool = False  # must carry supporting_chunk_ids
    validator: Optional[Callable[[Any, dict], Optional[str]]] = None  # returns a refusal reason or None
    sensitivity: str = "normal"
    note: str = ""                  # provenance of the declaration: which list, which ruling
    docpipe_field_id: Optional[str] = None   # the docpipe.lens.v1 field bridged onto this path, if any
    segments: dict[str, tuple[str, ...]] = field(default_factory=dict)  # allowed values per {segment}
    rehome: Optional[dict[str, str]] = None  # declared re-target (ruling A: the bridge's mapping, as-is)
    governance_class: str = "subject"

    @property
    def is_pattern(self) -> bool:
        return "{" in self.path

    def compile(self) -> re.Pattern[str]:
        pattern = "^" + re.sub(r"\{(\w+)\}", r"(?P<\1>[^.]+)", re.escape(self.path).replace(r"\{", "{").replace(r"\}", "}")) + "$"
        return re.compile(pattern)


@dataclass(frozen=True)
class ResolvedField:
    spec: FieldSpec
    path: str
    bound: dict[str, str]           # {segment_name: value} for pattern paths

    @property
    def writable(self) -> bool:
        return self.spec.status == "writable"


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

def _cefr_level(value: Any, bound: dict) -> Optional[str]:
    level = str(value or "").strip()
    if level not in VALID_CEFR_LEVELS:
        return f"'{level}' is not a recognised CEFR level."
    return None


def _non_empty_text(value: Any, bound: dict) -> Optional[str]:
    texts = value if isinstance(value, list) else [value]
    if not any(isinstance(t, str) and t.strip() for t in texts):
        return "value is empty."
    return None


def _string_list(value: Any, bound: dict) -> Optional[str]:
    if not (isinstance(value, list) and all(isinstance(x, str) for x in value)):
        return "value must be a list of strings."
    return None


def _free_text(value: Any, bound: dict) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        return "value must be non-empty text."
    if len(value) > 10_000:
        return "value must be 10000 characters or fewer."
    return None


# ---------------------------------------------------------------------------
# THE REGISTRY
# ---------------------------------------------------------------------------
# Notes name the list each entry came from (baseline B1): S = STUDENT_LENS_FIELDS,
# C = SUPPORT_CATEGORY_IDS, L = _LENS_FIELD_IDS (== docpipe PROFILE_FIELDS),
# U = UPDATABLE_PROFILE_FIELDS.

REGISTRY: tuple[FieldSpec, ...] = (
    # -- identity / scalars ------------------------------------------------
    FieldSpec("student_id", "scalar", "authored", "read_only",
              note="identity; set once by create_lens"),
    FieldSpec("display_name", "scalar", "authored", "read_only",
              note="S. Consumed by the writer to CREATE the lens (hint/display_name); "
                   "never updated by import. Baseline: was refused after being used."),
    FieldSpec("campus", "scalar", "authored", "writable", writer="store:update_profile",
              validator=_free_text, note="S, U"),
    FieldSpec("grade_level", "scalar", "authored", "writable", writer="store:update_profile",
              validator=_free_text, note="S, U"),
    FieldSpec("home_languages", "scalar", "authored", "writable", writer="store:update_profile",
              validator=_string_list, note="S, U. Baseline B4: refused by name though the store op existed; wired 2026-09-03 (ruling A)."),
    FieldSpec("learning_differences", "scalar", "authored", "writable", writer="store:update_profile",
              validator=_string_list, note="S, U. Baseline B4: same as home_languages."),
    FieldSpec("background_notes", "scalar", "authored", "writable", writer="store:update_profile",
              validator=_free_text, note="U only; no extractor emits it. Read by no consumer in src/ (baseline B9)."),
    FieldSpec("trauma_flag", "scalar", "authored", "writable", writer="column:trauma_flag",
              sensitivity="restricted",
              note="S. NEVER auto-written: lands in review_required unless the teacher confirmed it. "
                   "No store operation exists for it; the writer sets the column directly, declared here."),
    FieldSpec("avoid_pairing_with", "scalar", "authored", "read_only", writer="store:set_avoid_pairing_with",
              note="teacher-set roster fact (set_avoid_pairing_with); not an import target"),

    # -- derived (never punched directly) ------------------------------------
    FieldSpec("cefr_snapshot.{dimension}", "cefr", "derived", "writable",
              writer="store:append_observation", requires_sources=True, validator=_cefr_level,
              segments={"dimension": tuple(VALID_CEFR_DIMENSIONS)},
              note="S. DERIVED from the append-only observation log (set_initial_cefr docstring); "
                   "the writer appends a cefr observation, the projection updates. "
                   "The 2026-09-03 CEFR defect lived here."),
    FieldSpec("cefr_snapshot", "blob", "derived", "read_only",
              note="the projection itself (LENS_SHAPES); consumers read it, nothing writes it"),
    FieldSpec("rti_current_tier", "scalar", "derived", "read_only", writer="store:update_rti_tier",
              note="derived from rti_tier_history; update_rti_tier is the audited door"),
    FieldSpec("rti_tier_history", "blob", "derived", "read_only",
              note="append-only tier log (LENS_SHAPES)"),
    FieldSpec("cefr_trajectory_30d", "scalar", "derived", "read_only",
              note="computed by _compute_cefr_trajectory; not reconstructed as-of"),
    FieldSpec("sel_summary", "blob", "derived", "read_only",
              note="rolling counts over observations (LENS_SHAPES); read by no consumer in src/"),
    FieldSpec("profile_version", "scalar", "projection", "read_only", note="write counter"),
    FieldSpec("created_at", "scalar", "projection", "read_only", note="system timestamp, set by create_lens"),
    FieldSpec("updated_at", "scalar", "projection", "read_only", note="system timestamp, bumped by every write; staleness reads it"),
    FieldSpec("deleted", "scalar", "authored", "read_only", writer="store:delete_lens", note="soft tombstone (delete_lens)"),
    FieldSpec("deleted_at", "scalar", "projection", "read_only", note="set with the tombstone"),

    # -- support profile -----------------------------------------------------
    FieldSpec("support_profile", "blob", "authored", "read_only",
              note="the blob; written only through the category paths below. "
                   "B7 flag: append-only through store ops, NOT reconstructed as-of, and import "
                   "appends with no observation behind the entry — operator ruling pending."),
    FieldSpec("support_profile.categories.{category}.{bucket}", "support_profile", "authored", "writable",
              writer="store:add_support_entry", requires_sources=True, validator=_non_empty_text,
              segments={"category": tuple(SUPPORT_CATEGORY_IDS), "bucket": SUPPORT_BUCKETS_ALL},
              note="S declares 8 categories x 6 buckets; C declares 9 categories "
                   "(advanced_enrichment, personal_context are C-only; personal_context is absent from S). "
                   "The evidence bucket routes to add_support_evidence. Both lists kept; the union is declared."),
    FieldSpec("support_profile.categories.strategies_trialed.{bucket}", "support_profile", "authored", "writable",
              writer="store:add_support_entry", requires_sources=True, validator=_non_empty_text,
              segments={"bucket": SUPPORT_BUCKETS_ALL},
              docpipe_field_id="strategies_trialed",
              rehome={"category": "learning_and_cognition", "bucket": "open_questions"},
              note="L-only: strategies_trialed is a docpipe/classifier field with NO store category. "
                   "Baseline B4a: emitted at lens_extract.py:734 and SILENTLY DROPPED by the writer. "
                   "Ruling A (2026-09-03): the bridge's mapping (docpipe/lens.py:434-446 -> "
                   "learning_and_cognition, bucket by outcome else open_questions) is declared as-is; "
                   "the writer applies the same re-home and SAYS SO in the result."),

    # -- profile-level strengths --------------------------------------------
    FieldSpec("strengths_profile", "blob", "authored", "read_only",
              note="in none of the five lists (baseline B1); written only via the two paths below"),
    FieldSpec("academic_strengths", "strengths", "authored", "writable",
              writer="store:add_profile_strength", requires_sources=True, validator=_non_empty_text,
              docpipe_field_id="academic_strengths",
              note="L-only. Baseline B4: refused by name though add_profile_strength existed; wired 2026-09-03 (ruling A)."),
    FieldSpec("personal_strengths", "strengths", "authored", "writable",
              writer="store:add_profile_strength", requires_sources=True, validator=_non_empty_text,
              docpipe_field_id="personal_strengths",
              note="L-only. As academic_strengths."),

    # -- ethos ---------------------------------------------------------------
    FieldSpec("ethos_profile", "blob", "authored", "read_only",
              note="in none of the five lists; rollups derived from evidence_records"),
    FieldSpec("ethos_profile.traits.{trait}.evidence", "ethos_profile", "authored", "declared_not_implemented",
              writer="store:add_ethos_evidence", requires_sources=True,
              note="Emitted by lens_extract.py:225 (9 ethos.yaml traits), declared in NO list. "
                   "declared_not_implemented on purpose (spec §5.1.4): the store op exists but "
                   "ethos writes have their own review semantics and are a separate build. "
                   "Refuses by name. Deleting this entry to shrink the refusal count is kill criterion K4."),

    # -- markers -------------------------------------------------------------
    FieldSpec("unclassified", "marker", "authored", "declared_not_implemented",
              note="P0-3 carrier for classify_failed sentences (lens_extract.py:628). Never written; "
                   "refused with a content-free note that names the path, never the sentence."),
)


# ---------------------------------------------------------------------------
# Resolution — the only way in
# ---------------------------------------------------------------------------

_EXACT: dict[str, FieldSpec] = {}
_PATTERNS: list[tuple[re.Pattern[str], FieldSpec]] = []


def _index() -> None:
    _EXACT.clear()
    _PATTERNS.clear()
    for spec in REGISTRY:
        if spec.is_pattern:
            _PATTERNS.append((spec.compile(), spec))
        else:
            _EXACT[spec.path] = spec


def resolve(field_path: str) -> Optional[ResolvedField]:
    """Resolve a field path against the registry.

    Returns None when nothing declares the path. For a pattern path, every
    bound segment must be in the spec's allowed set — an unknown category or
    bucket resolves to None (the writer refuses it by name), never to a
    neighbouring spec.
    """
    if not isinstance(field_path, str) or not field_path:
        return None
    spec = _EXACT.get(field_path)
    if spec is not None:
        return ResolvedField(spec=spec, path=field_path, bound={})
    for pattern, spec in _PATTERNS:
        match = pattern.match(field_path)
        if not match:
            continue
        bound = match.groupdict()
        ok = all(
            name not in spec.segments or value in spec.segments[name]
            for name, value in bound.items()
        )
        if ok:
            return ResolvedField(spec=spec, path=field_path, bound=bound)
    return None


def declared_paths() -> list[str]:
    """Every concrete path the registry declares (patterns expanded)."""
    out: list[str] = []
    for spec in REGISTRY:
        if not spec.is_pattern:
            out.append(spec.path)
            continue
        names = re.findall(r"\{(\w+)\}", spec.path)
        if any(n not in spec.segments for n in names):
            continue  # open segment (e.g. ethos {trait}); enumerated by its taxonomy, not here
        combos = [[]]
        for n in names:
            combos = [c + [v] for c in combos for v in spec.segments[n]]
        for combo in combos:
            p = spec.path
            for n, v in zip(names, combo):
                p = p.replace("{" + n + "}", v)
            out.append(p)
    return out


def writable_paths() -> list[str]:
    return [p for p in declared_paths() if (r := resolve(p)) is not None and r.writable]


def support_buckets() -> tuple[str, ...]:
    return SUPPORT_BUCKETS_ALL


# ---------------------------------------------------------------------------
# OUT filter — outputs declare what they consume (spec §2.8)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FieldRequirement:
    path: str
    level: str  # "essential" | "enriching"


# Deliverable ids follow deliverables/schema.py DELIVERABLE_TYPES where one
# exists; `prepare` is content_differentiator's tiering step (UX U9).
OUTPUT_REQUIREMENTS: dict[str, tuple[FieldRequirement, ...]] = {
    # Prepare (content_differentiator.assign_tier_for_student): the RTI tier
    # is the primary signal and without it the tier is a guess — essential.
    # CEFR pulls a student up/down within the tier; its absence has a ruled
    # default (foundational, operator decision 2026-07-22) — enriching, and
    # the output SAYS it was missing.
    "prepare": (
        FieldRequirement("rti_current_tier", "essential"),
        FieldRequirement("cefr_snapshot", "enriching"),
    ),
    # Summaries (parent_report.generate_draft): the name is essential; the
    # rest enrich. support_profile and strengths_profile were NOT read before
    # 2026-09-04 — a report card's strengths and an Observe note never reached
    # the parent note (found by running the chain end to end).
    "parent_report": (
        FieldRequirement("display_name", "essential"),
        FieldRequirement("grade_level", "enriching"),
        FieldRequirement("home_languages", "enriching"),
        FieldRequirement("support_profile", "enriching"),
        FieldRequirement("strengths_profile", "enriching"),
    ),
}


def requires(output_id: str) -> tuple[FieldRequirement, ...]:
    if output_id not in OUTPUT_REQUIREMENTS:
        raise LensContractError(f"output '{output_id}' declares no lens requirements")
    return OUTPUT_REQUIREMENTS[output_id]


def _present(lens: dict, path: str) -> bool:
    value = lens.get(path)
    if value is None or value == "" or value == [] or value == {}:
        return False
    if path == "cefr_snapshot" and isinstance(value, dict):
        return any(v for v in value.values())
    return True


def read_for(output_id: str, lens: dict, *, strict: bool = True) -> dict:
    """Resolve an output's declared fields against a lens dict.

    Returns {"fields_used": {path: value}, "fields_missing": [path...],
    "fields_enriching_missing": [path...]}. With strict=True (the default) an
    absent ESSENTIAL field raises MissingEssentialFieldError — the output must
    refuse to render rather than produce a confident document with a hole in it.
    """
    used: dict[str, Any] = {}
    missing: list[str] = []
    enriching_missing: list[str] = []
    for req in requires(output_id):
        if _present(lens, req.path):
            used[req.path] = lens.get(req.path)
        elif req.level == "essential":
            missing.append(req.path)
        else:
            enriching_missing.append(req.path)
    if strict and missing:
        raise MissingEssentialFieldError(output_id, missing)
    return {
        "output_id": output_id,
        "fields_used": used,
        "fields_missing": missing,
        "fields_enriching_missing": enriching_missing,
    }


# ---------------------------------------------------------------------------
# Import-time validation — a registry nobody has watched reject something is
# a data structure, not a contract.
# ---------------------------------------------------------------------------

def _validate_registry() -> None:
    seen: set[str] = set()
    for spec in REGISTRY:
        if spec.path in seen:
            raise LensContractError(f"duplicate registry path {spec.path!r}")
        seen.add(spec.path)
        if spec.kind not in KINDS:
            raise LensContractError(f"{spec.path}: unknown kind {spec.kind!r}")
        if spec.origin not in ORIGINS:
            raise LensContractError(f"{spec.path}: unknown origin {spec.origin!r}")
        if spec.status not in STATUSES:
            raise LensContractError(f"{spec.path}: unknown status {spec.status!r}")
        if spec.sensitivity not in SENSITIVITIES:
            raise LensContractError(f"{spec.path}: unknown sensitivity {spec.sensitivity!r}")
        if spec.status == "writable" and not spec.writer:
            raise LensContractError(f"{spec.path}: writable but names no writer")
        if spec.writer:
            kind, _, target = spec.writer.partition(":")
            if kind == "store":
                if not callable(getattr(StudentLensStore, target, None)):
                    raise LensContractError(
                        f"{spec.path}: writer names StudentLensStore.{target}, which does not exist"
                    )
            elif kind == "column":
                if target not in STUDENT_COLUMNS:
                    raise LensContractError(f"{spec.path}: writer names column {target!r}, not in students")
            else:
                raise LensContractError(f"{spec.path}: writer {spec.writer!r} must be store:<op> or column:<name>")
        if spec.origin == "derived" and spec.status == "writable" and spec.writer != "store:append_observation":
            raise LensContractError(
                f"{spec.path}: derived fields may only be written through append_observation (the law)"
            )
        if spec.rehome:
            target = f"support_profile.categories.{spec.rehome['category']}.{spec.rehome['bucket']}"
            if resolve(target) is None:
                raise LensContractError(f"{spec.path}: rehome target {target!r} does not resolve")
    for output_id, reqs in OUTPUT_REQUIREMENTS.items():
        for req in reqs:
            if req.level not in ("essential", "enriching"):
                raise LensContractError(f"{output_id}: bad requirement level {req.level!r}")
            if resolve(req.path) is None:
                raise LensContractError(f"{output_id} requires {req.path!r}, which the registry does not declare")


_index()
_validate_registry()
