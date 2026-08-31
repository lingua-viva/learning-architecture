"""Fleet query engine — administrator questions over student lens vaults.

An administrator of several schools needs to ask questions across hundreds of
student lenses at once ("which students have documented needs but no strategy
trialed?", "which lenses are stale?"). This module answers them.

Design rules (inherited from admin_metrics.py and the signal doctrine):

- **Deterministic.** Counts, filters, distributions. No LLM anywhere in the
  query path — an administrator's number must be reproducible.
- **Absence is a verdict.** Every result carries explicit ``cannot_tell`` /
  ``empty_reason`` sections. A question we cannot answer for 12 students says
  so — it never renders as zero. CLI exit 2 = NOT-ENOUGH-DATA (0 = scored).
- **Students appear as ARON codes** by default (``governance.aron_ref``).
  These surfaces get projected in admin meetings. Display names appear only
  behind an explicit ``--names`` request.
- **Unreadable is reported, never zero-filled.** Invalid lens files are
  counted and named per school.

Fleet topology: one labeled vault root per school, declared in a fleet config
(JSON at ``$LV_FLEET_CONFIG`` or ``lv_home()/fleet.json``)::

    {"schools": [{"school": "...", "country": "...", "root": "/path/vault"}]}

With no config the local vault is the fleet (school="local") — the engine and
every query work identically at n=1 and n=9.

The 30 supported administrator questions live in QUESTION_MAP; each maps to a
query primitive + params, so ``lv fleet ask Q8`` is runnable and testable.

Name comparison reuses the hardened identity toolkit (normalize_name,
fold_text, Levenshtein) — the same class-closed matching the doc pipeline
uses, applied to duplicate detection and term search.
"""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from src.lingua_viva.config import lv_home
from src.lingua_viva.docpipe.identity import (
    _levenshtein,
    fold_text,
    normalize_name,
)
from src.lingua_viva.docpipe.lens import PROFILE_FIELDS, SUPPORT_CATEGORY_FIELDS
from src.lingua_viva.governance import aron_ref

LENS_SCHEMA = "docpipe.lens.v1"
EXIT_SCORED = 0
EXIT_NOT_ENOUGH_DATA = 2

STRENGTH_FIELDS = ("academic_strengths", "personal_strengths")


# ---------------------------------------------------------------------------
# Fleet loading
# ---------------------------------------------------------------------------


@dataclass
class LensRow:
    school: str
    country: str
    student_id: str
    aron: str
    display_name: str
    created_at: str
    updated_at: str
    # field_id -> list of evidence dicts (possibly empty)
    evidence: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    # field_id -> list of string values
    values: dict[str, list[str]] = field(default_factory=dict)
    source_ids: list[str] = field(default_factory=list)
    observation_ids: list[str] = field(default_factory=list)
    merge_events: list[dict[str, Any]] = field(default_factory=list)

    def populated_fields(self) -> set[str]:
        return {
            fid for fid in PROFILE_FIELDS
            if self.values.get(fid) and self.evidence.get(fid)
        }

    def ref(self, names: bool = False) -> dict[str, str]:
        out = {"aron": self.aron, "school": self.school}
        if names:
            out["display_name"] = self.display_name
        return out


@dataclass
class SchoolVault:
    school: str
    country: str
    root: Path
    rows: list[LensRow] = field(default_factory=list)
    unreadable: list[str] = field(default_factory=list)  # relative paths


@dataclass
class Fleet:
    schools: list[SchoolVault]

    @property
    def rows(self) -> list[LensRow]:
        return [row for school in self.schools for row in school.rows]

    @property
    def total_unreadable(self) -> int:
        return sum(len(s.unreadable) for s in self.schools)


def fleet_config_path() -> Path:
    override = os.environ.get("LV_FLEET_CONFIG")
    if override:
        return Path(override)
    return lv_home() / "fleet.json"


def _default_fleet_entries() -> list[dict[str, str]]:
    from src.lingua_viva.docpipe.vault import vault_root

    return [{"school": "local", "country": "", "root": str(vault_root())}]


def load_fleet(config_path: Optional[Path] = None) -> Fleet:
    path = config_path if config_path is not None else fleet_config_path()
    entries: list[dict[str, str]]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = [e for e in data.get("schools", []) if isinstance(e, dict)]
        if not entries:
            entries = _default_fleet_entries()
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        entries = _default_fleet_entries()

    schools: list[SchoolVault] = []
    for entry in entries:
        school = SchoolVault(
            school=str(entry.get("school") or "unnamed"),
            country=str(entry.get("country") or ""),
            root=Path(str(entry.get("root") or "")),
        )
        _load_school(school)
        schools.append(school)
    return Fleet(schools=schools)


def _load_school(school: SchoolVault) -> None:
    lens_dir = school.root / "lenses"
    if not lens_dir.is_dir():
        return
    for lens_json in sorted(lens_dir.glob("*/lens.json")):
        relative = lens_json.relative_to(school.root).as_posix()
        try:
            data = json.loads(lens_json.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            school.unreadable.append(relative)
            continue
        if not isinstance(data, dict) or data.get("schema_version") != LENS_SCHEMA:
            school.unreadable.append(relative)
            continue
        school.rows.append(_row_from_lens(data, school))


def _row_from_lens(data: dict[str, Any], school: SchoolVault) -> LensRow:
    student_id = str(data.get("student_id") or "")
    profile = data.get("profile") or {}
    evidence: dict[str, list[dict[str, Any]]] = {}
    values: dict[str, list[str]] = {}
    for fid in PROFILE_FIELDS:
        entry = profile.get(fid) or {}
        raw_evidence = entry.get("evidence")
        evidence[fid] = [e for e in raw_evidence if isinstance(e, dict)] \
            if isinstance(raw_evidence, list) else []
        values[fid] = _string_values(entry.get("value"))
    metadata = data.get("metadata") or {}
    return LensRow(
        school=school.school,
        country=school.country,
        student_id=student_id,
        aron=aron_ref(student_id),
        display_name=str(data.get("display_name") or ""),
        created_at=str(data.get("created_at") or ""),
        updated_at=str(data.get("updated_at") or ""),
        evidence=evidence,
        values=values,
        source_ids=[str(s) for s in metadata.get("source_ids") or []],
        observation_ids=[str(o) for o in metadata.get("observation_ids") or []],
        merge_events=[e for e in metadata.get("merge_events") or [] if isinstance(e, dict)],
    )


def _string_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    return [str(value)]


def _parse_ts(stamp: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _empty_fleet_result(query: str) -> dict[str, Any]:
    return {
        "query": query,
        "scored": False,
        "empty_reason": (
            "No student lenses found in any configured vault. This fills in "
            "as schools import documents and save observations."
        ),
    }


# ---------------------------------------------------------------------------
# Query primitives
# ---------------------------------------------------------------------------


def census(fleet: Fleet, *, names: bool = False) -> dict[str, Any]:
    """Q1/Q2/Q28/Q30 — who is in the fleet, what can't be read."""
    if not fleet.rows and fleet.total_unreadable == 0:
        return _empty_fleet_result("census")
    per_school = []
    for school in fleet.schools:
        last_updates = [
            ts for row in school.rows if (ts := _parse_ts(row.updated_at))
        ]
        per_school.append({
            "school": school.school,
            "country": school.country,
            "students": len(school.rows),
            "unreadable_lens_files": school.unreadable,
            "last_vault_update": (
                max(last_updates).isoformat() if last_updates else None
            ),
        })
    empty = [
        row.ref(names) for row in fleet.rows if not row.populated_fields()
    ]
    by_country: Counter[str] = Counter(
        row.country or "(unspecified)" for row in fleet.rows
    )
    return {
        "query": "census",
        "scored": True,
        "total_students": len(fleet.rows),
        "by_school": per_school,
        "by_country": dict(sorted(by_country.items())),
        "empty_lenses": empty,
        "empty_lens_count": len(empty),
        "unreadable_total": fleet.total_unreadable,
    }


def coverage(fleet: Fleet, *, names: bool = False) -> dict[str, Any]:
    """Q3/Q6 — which profile fields are actually populated, per school."""
    if not fleet.rows:
        return _empty_fleet_result("coverage")
    per_school = []
    for school in fleet.schools:
        if not school.rows:
            per_school.append({
                "school": school.school,
                "empty_reason": "No lenses in this school's vault.",
            })
            continue
        field_counts = {
            fid: sum(1 for row in school.rows if fid in row.populated_fields())
            for fid in PROFILE_FIELDS
        }
        populated_cells = sum(field_counts.values())
        per_school.append({
            "school": school.school,
            "students": len(school.rows),
            "field_population": field_counts,
            "populated_percent": round(
                100.0 * populated_cells / (len(school.rows) * len(PROFILE_FIELDS)), 1
            ),
        })
    return {
        "query": "coverage",
        "scored": True,
        "fields": list(PROFILE_FIELDS),
        "by_school": per_school,
    }


def support_needs(
    fleet: Fleet, *, min_categories: int = 3, names: bool = False
) -> dict[str, Any]:
    """Q6/Q7/Q10/Q11/Q12 — documented support needs, per category and school."""
    if not fleet.rows:
        return _empty_fleet_result("needs")
    by_school: dict[str, Counter[str]] = defaultdict(Counter)
    high_need = []
    for row in fleet.rows:
        populated = row.populated_fields() & SUPPORT_CATEGORY_FIELDS
        for fid in populated:
            by_school[row.school][fid] += 1
        if len(populated) >= min_categories:
            high_need.append({
                **row.ref(names),
                "categories": sorted(populated),
                "category_count": len(populated),
            })
    high_need.sort(key=lambda item: -item["category_count"])
    fleet_totals: Counter[str] = Counter()
    for counts in by_school.values():
        fleet_totals.update(counts)
    return {
        "query": "needs",
        "scored": True,
        "min_categories": min_categories,
        "fleet_totals": dict(sorted(fleet_totals.items())),
        "by_school": {
            school: dict(sorted(counts.items()))
            for school, counts in sorted(by_school.items())
        },
        "high_need_students": high_need,
        "physical_sensory": [
            row.ref(names) for row in fleet.rows
            if "physical_sensory_needs" in row.populated_fields()
        ],
        "attendance_engagement": [
            row.ref(names) for row in fleet.rows
            if "attendance_and_engagement" in row.populated_fields()
        ],
    }


def support_gap(fleet: Fleet, *, names: bool = False) -> dict[str, Any]:
    """Q8/Q13/Q25 — needs documented with no strategy trialed; balance."""
    if not fleet.rows:
        return _empty_fleet_result("gap")
    gap, needs_only, strengths_only = [], [], []
    balance: dict[str, dict[str, int]] = defaultdict(lambda: {"needs": 0, "strengths": 0})
    for row in fleet.rows:
        populated = row.populated_fields()
        need_fields = populated & SUPPORT_CATEGORY_FIELDS
        strength_fields = populated & set(STRENGTH_FIELDS)
        if need_fields:
            balance[row.school]["needs"] += 1
        if strength_fields:
            balance[row.school]["strengths"] += 1
        if need_fields and "strategies_trialed" not in populated:
            gap.append({**row.ref(names), "needs": sorted(need_fields)})
        if need_fields and not strength_fields:
            needs_only.append(row.ref(names))
        if strength_fields and not need_fields:
            strengths_only.append(row.ref(names))
    return {
        "query": "gap",
        "scored": True,
        "needs_without_strategies": gap,
        "needs_without_strategies_count": len(gap),
        "needs_but_no_strengths_documented": needs_only,
        "strengths_but_no_needs_documented": strengths_only,
        "school_balance": dict(sorted(balance.items())),
    }


def strategies(fleet: Fleet, *, names: bool = False) -> dict[str, Any]:
    """Q9 — which strategies are trialed, fleet-wide, by frequency."""
    if not fleet.rows:
        return _empty_fleet_result("strategies")
    counts: Counter[str] = Counter()
    for row in fleet.rows:
        for value in row.values.get("strategies_trialed", []):
            counts[value.strip()] += 1
    if not counts:
        return {
            "query": "strategies",
            "scored": True,
            "empty_reason": (
                "No strategies_trialed evidence anywhere in the fleet — "
                "cannot rank what has never been documented."
            ),
        }
    return {
        "query": "strategies",
        "scored": True,
        "strategies": [
            {"strategy": strategy, "students": count}
            for strategy, count in counts.most_common()
        ],
    }


def term_search(fleet: Fleet, term: str, *, names: bool = False) -> dict[str, Any]:
    """Q16/Q17 — accent-folded search over lens values, with citations."""
    if not fleet.rows:
        return _empty_fleet_result("search")
    folded_term = fold_text(term).strip()
    if not folded_term:
        return {"query": "search", "scored": False, "empty_reason": "Empty search term."}
    hits = []
    for row in fleet.rows:
        for fid in PROFILE_FIELDS:
            for value in row.values.get(fid, []):
                if folded_term in fold_text(value):
                    hits.append({
                        **row.ref(names),
                        "field": fid,
                        "value": value,
                        "citations": [
                            evidence.get("source_ref", {})
                            for evidence in row.evidence.get(fid, [])
                        ],
                    })
    return {
        "query": "search",
        "scored": True,
        "term": term,
        "matches": hits,
        "match_count": len(hits),
        "students_matched": len({h["aron"] for h in hits}),
    }


def staleness(fleet: Fleet, *, days: int = 60, names: bool = False) -> dict[str, Any]:
    """Q4/Q5 — stale and recent lenses. Unparseable timestamps are named."""
    if not fleet.rows:
        return _empty_fleet_result("staleness")
    cutoff = _now() - timedelta(days=days)
    stale, recent, cannot_tell = [], [], []
    for row in fleet.rows:
        updated = _parse_ts(row.updated_at)
        created = _parse_ts(row.created_at)
        if updated is None:
            cannot_tell.append(row.ref(names))
            continue
        if updated < cutoff:
            stale.append({**row.ref(names), "updated_at": row.updated_at})
        if created is not None and created >= cutoff:
            recent.append({**row.ref(names), "created_at": row.created_at})
    stale.sort(key=lambda item: item["updated_at"])
    return {
        "query": "staleness",
        "scored": True,
        "days": days,
        "stale": stale,
        "stale_count": len(stale),
        "recent_lenses": recent,
        "cannot_tell": cannot_tell,
        "cannot_tell_reason": (
            "Lens timestamps unparseable — staleness unknowable for these "
            "students." if cannot_tell else None
        ),
    }


def evidence_integrity(
    fleet: Fleet, *, low_confidence: float = 0.6, names: bool = False
) -> dict[str, Any]:
    """Q14/Q15/Q20-Q24 — how well-grounded the fleet's lenses actually are."""
    if not fleet.rows:
        return _empty_fleet_result("integrity")
    per_school_sources: dict[str, Counter[str]] = defaultdict(Counter)
    teacher_counts: Counter[str] = Counter()
    low_conf_only, single_source, multi_teacher = [], [], []
    evidence_per_student: dict[str, list[int]] = defaultdict(list)
    merge_by_month: dict[str, Counter[str]] = defaultdict(Counter)
    for row in fleet.rows:
        all_evidence = [e for fid in PROFILE_FIELDS for e in row.evidence.get(fid, [])]
        evidence_per_student[row.school].append(len(all_evidence))
        teachers = set()
        confidences = []
        for evidence in all_evidence:
            source_type = str((evidence.get("source_ref") or {}).get("type") or "UNKNOWN")
            per_school_sources[row.school][source_type] += 1
            added_by = str(evidence.get("added_by") or "")
            if added_by:
                teachers.add(added_by)
                teacher_counts[added_by] += 1
            try:
                confidences.append(float(evidence.get("confidence")))
            except (TypeError, ValueError):
                pass
        if confidences and max(confidences) < low_confidence:
            low_conf_only.append({
                **row.ref(names), "max_confidence": round(max(confidences), 2),
            })
        if all_evidence and len(set(row.source_ids)) == 1 and not row.observation_ids:
            single_source.append({**row.ref(names), "source_id": row.source_ids[0]})
        if len(teachers) > 1:
            multi_teacher.append({**row.ref(names), "teachers": len(teachers)})
        for event in row.merge_events:
            month = str(event.get("added_at") or "")[:7]
            if month:
                merge_by_month[row.school][month] += 1
    return {
        "query": "integrity",
        "scored": True,
        "low_confidence_threshold": low_confidence,
        "grounding_by_school": {
            school: dict(counts) for school, counts in sorted(per_school_sources.items())
        },
        "evidence_per_student": {
            school: {
                "min": min(counts), "max": max(counts),
                "mean": round(sum(counts) / len(counts), 1),
            }
            for school, counts in sorted(evidence_per_student.items())
        },
        "teacher_contributions": dict(teacher_counts.most_common()),
        "low_confidence_only": low_conf_only,
        "single_source_lenses": single_source,
        "multi_teacher_students": multi_teacher,
        "merge_events_by_month": {
            school: dict(sorted(counts.items()))
            for school, counts in sorted(merge_by_month.items())
        },
    }


def duplicate_risk(fleet: Fleet, *, names: bool = False) -> dict[str, Any]:
    """Q27 — same-school near-duplicate names (split-child risk).

    Uses the hardened comparators: normalized equality in either order, or
    Levenshtein distance <= 1 between normalized full names.
    """
    if not fleet.rows:
        return _empty_fleet_result("duplicates")
    pairs = []
    for school in fleet.schools:
        rows = school.rows
        for i, left in enumerate(rows):
            left_norm = normalize_name(left.display_name)
            left_rev = " ".join(reversed(left_norm.split()))
            for right in rows[i + 1:]:
                right_norm = normalize_name(right.display_name)
                if not left_norm or not right_norm:
                    continue
                if (
                    right_norm in (left_norm, left_rev)
                    or _levenshtein(left_norm, right_norm) <= 1
                    or _levenshtein(left_rev, right_norm) <= 1
                ):
                    pairs.append({
                        "school": school.school,
                        "students": [left.ref(names), right.ref(names)],
                    })
    return {
        "query": "duplicates",
        "scored": True,
        "near_duplicate_pairs": pairs,
        "pair_count": len(pairs),
    }


def dossier(
    fleet: Fleet, student: str, *, source_id: str = "", names: bool = False
) -> dict[str, Any]:
    """Q18/Q19 — one student's full evidence trail (by student_id or ARON)."""
    if not fleet.rows:
        return _empty_fleet_result("dossier")
    row = next(
        (r for r in fleet.rows if student in (r.student_id, r.aron)), None
    )
    if row is None:
        return {
            "query": "dossier",
            "scored": False,
            "empty_reason": f"No lens found for {student!r} in any school vault.",
        }
    fields = {}
    for fid in PROFILE_FIELDS:
        entries = row.evidence.get(fid, [])
        if source_id:
            entries = [
                e for e in entries
                if (e.get("source_ref") or {}).get("source_id") == source_id
                or e.get("source_id") == source_id
            ]
        if not row.values.get(fid) and not entries:
            continue
        fields[fid] = {"values": row.values.get(fid, []), "evidence": entries}
    return {
        "query": "dossier",
        "scored": True,
        **row.ref(names),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "source_ids": row.source_ids,
        "observation_count": len(row.observation_ids),
        "fields": fields,
        "source_filter": source_id or None,
    }


def hygiene(fleet: Fleet, *, names: bool = False) -> dict[str, Any]:
    """Q26/Q28 — identity queue and unreadable files.

    The identity queue is machine-local (ingest_review/identity.ndjson), not
    part of a vault export — for any school vault other than this machine's
    the open-queue count is honestly CANNOT_TELL, not zero.
    """
    from src.lingua_viva.docpipe.identity import list_open_items
    from src.lingua_viva.docpipe.vault import vault_root

    local_root = str(vault_root())
    per_school = []
    for school in fleet.schools:
        entry: dict[str, Any] = {
            "school": school.school,
            "unreadable_lens_files": school.unreadable,
        }
        if str(school.root) == local_root:
            entry["open_identity_queue"] = len(list_open_items())
        else:
            entry["open_identity_queue"] = None
            entry["cannot_tell_reason"] = (
                "Identity queue is machine-local and not part of this "
                "school's vault export."
            )
        per_school.append(entry)
    return {"query": "hygiene", "scored": True, "by_school": per_school}


# ---------------------------------------------------------------------------
# The 30 administrator questions — each mapped to a runnable query
# ---------------------------------------------------------------------------

QUESTION_MAP: list[dict[str, Any]] = [
    {"id": "Q1", "q": "How many students have lenses, per school and country?", "query": "census", "params": {}},
    {"id": "Q2", "q": "Which students have an empty lens (zero evidence anywhere)?", "query": "census", "params": {}},
    {"id": "Q3", "q": "What percent of the 10 profile fields are populated, per school?", "query": "coverage", "params": {}},
    {"id": "Q4", "q": "Which lenses are stale (no update in 60 days)?", "query": "staleness", "params": {"days": 60}},
    {"id": "Q5", "q": "Which students joined the fleet in the last 30 days?", "query": "staleness", "params": {"days": 30}},
    {"id": "Q6", "q": "How many students have documented needs per support category?", "query": "needs", "params": {}},
    {"id": "Q7", "q": "Which students show evidence in 3+ support categories?", "query": "needs", "params": {"min_categories": 3}},
    {"id": "Q8", "q": "Which students have documented needs but nothing in strategies_trialed?", "query": "gap", "params": {}},
    {"id": "Q9", "q": "What strategies are most frequently trialed fleet-wide?", "query": "strategies", "params": {}},
    {"id": "Q10", "q": "Which students have physical/sensory needs documented?", "query": "needs", "params": {}},
    {"id": "Q11", "q": "Which students have attendance/engagement concerns documented?", "query": "needs", "params": {}},
    {"id": "Q12", "q": "How does support-category prevalence compare across schools?", "query": "needs", "params": {}},
    {"id": "Q13", "q": "Which school has the best strengths-to-needs documentation balance?", "query": "gap", "params": {}},
    {"id": "Q14", "q": "What is the evidence-per-student distribution per school?", "query": "integrity", "params": {}},
    {"id": "Q15", "q": "What is merge-event volume per school over time?", "query": "integrity", "params": {}},
    {"id": "Q16", "q": "Which students' lenses mention a given term, with citations?", "query": "search", "params": {"term": "support"}},
    {"id": "Q17", "q": "Which students have a specific strategy trialed?", "query": "search", "params": {"term": "visual schedule"}},
    {"id": "Q18", "q": "Full evidence dossier for one student?", "query": "dossier", "params": {"student": ""}},
    {"id": "Q19", "q": "Which lens fields came from a given report-card import?", "query": "dossier", "params": {"student": "", "source_id": ""}},
    {"id": "Q20", "q": "What fraction of claims are document- vs observation-grounded, per school?", "query": "integrity", "params": {}},
    {"id": "Q21", "q": "Which lenses carry only low-confidence evidence?", "query": "integrity", "params": {"low_confidence": 0.6}},
    {"id": "Q22", "q": "Which lenses rest entirely on a single source document?", "query": "integrity", "params": {}},
    {"id": "Q23", "q": "Which teachers contribute the most and fewest observations?", "query": "integrity", "params": {}},
    {"id": "Q24", "q": "Which students have evidence from more than one teacher?", "query": "integrity", "params": {}},
    {"id": "Q25", "q": "Which students have strengths but no needs documented, and the reverse?", "query": "gap", "params": {}},
    {"id": "Q26", "q": "How many identity-queue items are unresolved, per school?", "query": "hygiene", "params": {}},
    {"id": "Q27", "q": "Which same-school students have near-duplicate names?", "query": "duplicates", "params": {}},
    {"id": "Q28", "q": "How many lens files are unreadable or invalid?", "query": "census", "params": {}},
    {"id": "Q29", "q": "For how many students can a given question NOT be answered?", "query": "staleness", "params": {"days": 60}},
    {"id": "Q30", "q": "When was each school's vault last updated at all?", "query": "census", "params": {}},
]

_QUERY_DISPATCH = {
    "census": census,
    "coverage": coverage,
    "needs": support_needs,
    "gap": support_gap,
    "strategies": strategies,
    "search": term_search,
    "staleness": staleness,
    "integrity": evidence_integrity,
    "duplicates": duplicate_risk,
    "dossier": dossier,
    "hygiene": hygiene,
}


def run_query(
    fleet: Fleet, query: str, *, names: bool = False, **params: Any
) -> dict[str, Any]:
    handler = _QUERY_DISPATCH.get(query)
    if handler is None:
        raise ValueError(
            f"unknown fleet query {query!r} — one of {sorted(_QUERY_DISPATCH)}"
        )
    if query == "search":
        return term_search(fleet, str(params.get("term") or ""), names=names)
    if query == "dossier":
        return dossier(
            fleet,
            str(params.get("student") or ""),
            source_id=str(params.get("source_id") or ""),
            names=names,
        )
    kwargs = {k: v for k, v in params.items() if k in {
        "min_categories", "days", "low_confidence"}}
    return handler(fleet, names=names, **kwargs)  # type: ignore[operator]


def run_question(
    fleet: Fleet, question_id: str, *, names: bool = False, **overrides: Any
) -> dict[str, Any]:
    entry = next((q for q in QUESTION_MAP if q["id"] == question_id.upper()), None)
    if entry is None:
        raise ValueError(f"unknown question id {question_id!r} (Q1..Q{len(QUESTION_MAP)})")
    params = {**entry["params"], **overrides}
    result = run_query(fleet, entry["query"], names=names, **params)
    return {"question": entry["q"], "question_id": entry["id"], **result}


def exit_code(result: dict[str, Any]) -> int:
    return EXIT_SCORED if result.get("scored") else EXIT_NOT_ENOUGH_DATA


def format_result(result: dict[str, Any]) -> str:
    """Human-readable rendering: verdict header, then the payload."""
    lines: list[str] = []
    if result.get("question_id"):
        lines.append(f"{result['question_id']}: {result.get('question', '')}")
    lines.append(f"query: {result.get('query', '?')}")
    lines.append(
        "verdict: SCORED" if result.get("scored") else "verdict: NOT-ENOUGH-DATA"
    )
    if result.get("empty_reason"):
        lines.append(f"empty_reason: {result['empty_reason']}")
    payload = {
        k: v
        for k, v in result.items()
        if k not in {"question_id", "question", "query", "scored", "empty_reason"}
    }
    if payload:
        lines.append(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    return "\n".join(lines)
