"""Lens query — administrator questions over the STUDENT LENS STORE, through the contract.

UX U18 (dev/UX_MATRIX_AND_ACTION_LIST_2026-09-03.md): "Admin: query across
lenses". Item 13 of the hard list: cheap AFTER the field contract, expensive
before — over four disagreeing vocabularies a query surface special-cases
each one; over a declared registry it is a projection. This is that projection.

Why a second engine when `fleet_query.py` already answers 30 questions:
`fleet_query` reads `*/lens.json` — the docpipe.lens.v1 VAULT (fleet_query.py:159).
Ruling A (2026-09-03) made the SQLite store the contract and docpipe a
producer; the report-card path, Observe, and the teacher's own edits write to
the STORE and never touch the vault. An administrator asking the vault
"which students have needs but no strategy" gets an answer over data the
product does not write. This module asks the store, and every field it reads
is a path `lens_field_contract` declares.

Design rules (inherited from fleet_query / admin_metrics and the signal doctrine):
- Deterministic. Counts, filters, distributions. No LLM anywhere.
- Absence is a verdict. Every result carries `scored`, `targets`,
  `cannot_tell` and `empty_reason`. Zero students is never a clean zero.
- Students appear as ARON codes (`governance.aron_ref`) unless `names=True`.
- Only declared paths are read. A question that would need an undeclared
  field is a LensContractError at import, not a silent None at runtime.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from src.education.student_lens import (
    SUPPORT_CATEGORY_IDS,
    VALID_CEFR_DIMENSIONS,
    VALID_SUPPORT_BUCKETS,
    StudentLensStore,
)
from src.lingua_viva.governance import aron_ref
from src.lingua_viva.lens_field_contract import LensContractError, resolve, writable_paths

EXIT_SCORED = 0
EXIT_NOT_ENOUGH_DATA = 2

STRATEGY_BUCKETS = ("strategies_worked", "strategies_not_worked", "open_questions")
NEED_BUCKETS = ("needs", "evidence")

# Every path this module reads. Validated at import against the registry so a
# renamed field fails here, loudly, not as a KeyError in an admin meeting.
_PATHS_READ: tuple[str, ...] = (
    "student_id", "display_name", "grade_level", "campus", "updated_at", "created_at",
    "rti_current_tier", "cefr_snapshot", "support_profile", "strengths_profile",
    "academic_strengths", "personal_strengths",
    *[f"cefr_snapshot.{d}" for d in VALID_CEFR_DIMENSIONS],
    *[f"support_profile.categories.{c}.{b}" for c in SUPPORT_CATEGORY_IDS
      for b in list(VALID_SUPPORT_BUCKETS) + ["evidence"]],
)

QUESTIONS: list[dict[str, Any]] = [
    {"id": "L1", "q": "How many students have lenses (per grade, per campus)?", "query": "census", "params": {}},
    {"id": "L2", "q": "Which lenses are empty — no support entries, no strengths, no CEFR, no observations?", "query": "census", "params": {}},
    {"id": "L3", "q": "What percent of declared writable lens fields are populated, per field?", "query": "coverage", "params": {}},
    {"id": "L4", "q": "Which lenses are stale (no update in N days)?", "query": "staleness", "params": {"days": 60}},
    {"id": "L5", "q": "How many students have documented needs per support category?", "query": "needs", "params": {}},
    {"id": "L6", "q": "Which students show evidence in 3+ support categories?", "query": "needs", "params": {"min_categories": 3}},
    {"id": "L7", "q": "Which students have documented needs but no strategy recorded (worked / not worked / open)?", "query": "gap", "params": {}},
    {"id": "L8", "q": "What is the CEFR level distribution per dimension?", "query": "cefr", "params": {}},
    {"id": "L9", "q": "Which students have no CEFR evidence in any dimension?", "query": "cefr", "params": {}},
    {"id": "L10", "q": "Which students are at RTI tier 2 or 3?", "query": "rti", "params": {}},
    {"id": "L11", "q": "Which lenses mention a given term, with entry citations?", "query": "search", "params": {"term": ""}},
    {"id": "L12", "q": "Full lens dossier for one student, over declared paths only?", "query": "dossier", "params": {"student": ""}},
]


def _validate_paths() -> None:
    bad = [p for p in _PATHS_READ if resolve(p) is None]
    if bad:
        raise LensContractError(f"lens_query reads undeclared paths: {bad}")


_validate_paths()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _ref(lens: dict, names: bool) -> str:
    sid = str(lens.get("student_id") or "")
    if names:
        return str(lens.get("display_name") or sid)
    return aron_ref(sid)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: Any) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _categories(lens: dict) -> dict:
    return ((lens.get("support_profile") or {}).get("categories") or {})


def _active(items: Any) -> list[dict]:
    return [i for i in (items or []) if isinstance(i, dict) and i.get("active", True) is not False]


def _has_needs(cat: dict) -> bool:
    return any(_active(cat.get(b)) for b in NEED_BUCKETS)


def _has_strategy(cat: dict) -> bool:
    return any(_active(cat.get(b)) for b in STRATEGY_BUCKETS)


def field_present(lens: dict, path: str) -> bool:
    """Is a declared path populated on this lens dict (from get_lens)?"""
    parts = path.split(".")
    if parts[0] == "cefr_snapshot" and len(parts) == 2:
        return bool((lens.get("cefr_snapshot") or {}).get(parts[1]))
    if parts[0] == "support_profile" and len(parts) == 4:
        return bool(_active(_categories(lens).get(parts[2], {}).get(parts[3])))
    if path in ("academic_strengths", "personal_strengths"):
        return bool(_active((lens.get("strengths_profile") or {}).get(path)))
    if parts[0] == "ethos_profile":
        return False  # open segment; not enumerated here
    value = lens.get(path)
    return value not in (None, "", [], {}, 0, False)


def _result(query: str, lenses: list[dict], **payload: Any) -> dict[str, Any]:
    out = {
        "query": query,
        "targets": len(lenses),
        "scored": bool(lenses),
        "empty_reason": None if lenses else "No student lenses in the store.",
        "cannot_tell": [],
    }
    out.update(payload)
    return out


# ---------------------------------------------------------------------------
# queries
# ---------------------------------------------------------------------------

def census(store: StudentLensStore, lenses: list[dict], *, names: bool = False, **_: Any) -> dict:
    by_grade = Counter(str(l.get("grade_level") or "(none)") for l in lenses)
    by_campus = Counter(str(l.get("campus") or "(none)") for l in lenses)
    empty = []
    for lens in lenses:
        has_support = any(_has_needs(c) or _has_strategy(c) or _active(c.get("strengths"))
                          for c in _categories(lens).values())
        has_strengths = any(field_present(lens, p) for p in ("academic_strengths", "personal_strengths"))
        has_cefr = any(field_present(lens, f"cefr_snapshot.{d}") for d in VALID_CEFR_DIMENSIONS)
        has_obs = bool(store.export_lens(lens["student_id"]).get("observations"))
        if not (has_support or has_strengths or has_cefr or has_obs):
            empty.append(_ref(lens, names))
    return _result("census", lenses, by_grade=dict(by_grade), by_campus=dict(by_campus),
                   empty_lenses=empty, empty_count=len(empty))


def coverage(store: StudentLensStore, lenses: list[dict], **_: Any) -> dict:
    paths = [p for p in writable_paths() if not p.startswith("ethos_profile") and p != "trauma_flag"]
    per_field = {}
    for p in paths:
        n = sum(1 for l in lenses if field_present(l, p))
        per_field[p] = {"populated": n, "of": len(lenses),
                        "pct": round(100.0 * n / len(lenses), 1) if lenses else None}
    populated_any = [p for p, v in per_field.items() if v["populated"]]
    return _result("coverage", lenses, declared_fields=len(paths),
                   fields_populated_somewhere=len(populated_any), per_field=per_field)


def staleness(store: StudentLensStore, lenses: list[dict], *, days: int = 60, names: bool = False, **_: Any) -> dict:
    cutoff = _now() - timedelta(days=int(days))
    stale, recent, cannot = [], [], []
    for lens in lenses:
        dt = _parse_iso(lens.get("updated_at"))
        if dt is None:
            cannot.append(_ref(lens, names))
        elif dt < cutoff:
            stale.append({"student": _ref(lens, names), "updated_at": lens.get("updated_at")})
        else:
            recent.append(_ref(lens, names))
    out = _result("staleness", lenses, days=int(days), stale=stale, stale_count=len(stale),
                  recent_count=len(recent))
    out["cannot_tell"] = cannot
    if cannot:
        out["cannot_tell_reason"] = "updated_at unreadable for these students."
    return out


def needs(store: StudentLensStore, lenses: list[dict], *, min_categories: int = 0, names: bool = False, **_: Any) -> dict:
    per_category: Counter = Counter()
    multi = []
    for lens in lenses:
        cats = [c for c, v in _categories(lens).items() if _has_needs(v)]
        for c in cats:
            per_category[c] += 1
        if min_categories and len(cats) >= int(min_categories):
            multi.append({"student": _ref(lens, names), "categories": sorted(cats)})
    payload: dict[str, Any] = {"per_category": {c: per_category.get(c, 0) for c in SUPPORT_CATEGORY_IDS}}
    if min_categories:
        payload.update(min_categories=int(min_categories), students=multi, count=len(multi))
    return _result("needs", lenses, **payload)


def gap(store: StudentLensStore, lenses: list[dict], *, names: bool = False, **_: Any) -> dict:
    """Needs documented, no strategy in any bucket of the SAME category.
    Note the declared re-home: classifier `strategies_trialed` entries land in
    learning_and_cognition.open_questions (lens_field_contract), so
    open_questions counts as 'a strategy recorded' here, and says so."""
    rows = []
    for lens in lenses:
        missing = [c for c, v in _categories(lens).items() if _has_needs(v) and not _has_strategy(v)]
        if missing:
            rows.append({"student": _ref(lens, names), "categories_without_strategy": sorted(missing)})
    return _result("gap", lenses, students=rows, count=len(rows),
                   strategy_buckets_counted=list(STRATEGY_BUCKETS),
                   note="open_questions counts: strategies_trialed re-homes there (ruling A, 2026-09-03)")


def cefr(store: StudentLensStore, lenses: list[dict], *, names: bool = False, **_: Any) -> dict:
    dist: dict[str, Counter] = {d: Counter() for d in VALID_CEFR_DIMENSIONS}
    none_at_all = []
    for lens in lenses:
        snap = lens.get("cefr_snapshot") or {}
        any_level = False
        for d in VALID_CEFR_DIMENSIONS:
            level = snap.get(d)
            if level:
                dist[d][str(level)] += 1
                any_level = True
        if not any_level:
            none_at_all.append(_ref(lens, names))
    return _result("cefr", lenses, distribution={d: dict(c) for d, c in dist.items()},
                   no_cefr_evidence=none_at_all, no_cefr_count=len(none_at_all))


def rti(store: StudentLensStore, lenses: list[dict], *, names: bool = False, **_: Any) -> dict:
    tiers = Counter(int(l.get("rti_current_tier") or 1) for l in lenses)
    elevated = [{"student": _ref(l, names), "tier": int(l.get("rti_current_tier") or 1)}
                for l in lenses if int(l.get("rti_current_tier") or 1) >= 2]
    return _result("rti", lenses, distribution={str(k): v for k, v in sorted(tiers.items())},
                   elevated=elevated, elevated_count=len(elevated))


def search(store: StudentLensStore, lenses: list[dict], *, term: str = "", names: bool = False, **_: Any) -> dict:
    term = (term or "").strip().lower()
    if not term:
        out = _result("search", lenses)
        out.update(scored=False, empty_reason="Empty search term.", hits=[])
        return out
    hits = []
    for lens in lenses:
        cites = []
        for cat_id, cat in _categories(lens).items():
            for bucket in list(VALID_SUPPORT_BUCKETS) + ["evidence"]:
                for item in _active(cat.get(bucket)):
                    text = str(item.get("text") or item.get("summary") or "")
                    if term in text.lower():
                        cites.append({"path": f"support_profile.categories.{cat_id}.{bucket}",
                                      "entry_id": item.get("id"), "source_ref_ids": item.get("source_ref_ids") or []})
        for kind in ("academic_strengths", "personal_strengths"):
            for item in _active((lens.get("strengths_profile") or {}).get(kind)):
                if term in str(item.get("text") or "").lower():
                    cites.append({"path": kind, "entry_id": item.get("id"),
                                  "source_ref_ids": item.get("source_ref_ids") or []})
        if cites:
            hits.append({"student": _ref(lens, names), "citations": cites})
    return _result("search", lenses, term=term, hits=hits, count=len(hits))


def dossier(store: StudentLensStore, lenses: list[dict], *, student: str = "", names: bool = False, **_: Any) -> dict:
    student = (student or "").strip()
    match = None
    for lens in lenses:
        if student and (lens.get("student_id") == student or aron_ref(str(lens.get("student_id"))) == student
                        or str(lens.get("display_name") or "").lower() == student.lower()):
            match = lens
            break
    if match is None:
        out = _result("dossier", lenses)
        out.update(scored=False, empty_reason=f"No lens found for {student!r}." if student else "No student given.")
        return out
    full = store.export_lens(match["student_id"])
    fields = {p: field_present(full, p) for p in writable_paths() if not p.startswith("ethos_profile")}
    return _result("dossier", lenses, student=_ref(match, names),
                   declared_fields_present=sorted(p for p, ok in fields.items() if ok),
                   declared_fields_absent=sorted(p for p, ok in fields.items() if not ok),
                   cefr_snapshot=full.get("cefr_snapshot"), rti_current_tier=full.get("rti_current_tier"),
                   observation_count=len(full.get("observations") or []),
                   support_profile=full.get("support_profile") if names else "(omitted without names=True)",
                   strengths_profile=full.get("strengths_profile") if names else "(omitted without names=True)")


_HANDLERS: dict[str, Callable[..., dict]] = {
    "census": census, "coverage": coverage, "staleness": staleness, "needs": needs,
    "gap": gap, "cefr": cefr, "rti": rti, "search": search, "dossier": dossier,
}


# ---------------------------------------------------------------------------
# entry points
# ---------------------------------------------------------------------------

def run_query(store: StudentLensStore, query: str, *, names: bool = False, **params: Any) -> dict[str, Any]:
    handler = _HANDLERS.get(query)
    if handler is None:
        raise ValueError(f"unknown query {query!r}; one of {sorted(_HANDLERS)}")
    lenses = store.list_lenses()
    return handler(store, lenses, names=names, **params)


def run_question(store: StudentLensStore, question_id: str, *, names: bool = False, **overrides: Any) -> dict[str, Any]:
    entry = next((q for q in QUESTIONS if q["id"] == question_id.upper()), None)
    if entry is None:
        raise ValueError(f"unknown question id {question_id!r} (L1..L{len(QUESTIONS)})")
    params = {**entry["params"], **overrides}
    result = run_query(store, entry["query"], names=names, **params)
    return {"question_id": entry["id"], "question": entry["q"], **result}


def exit_code(result: dict[str, Any]) -> int:
    return EXIT_SCORED if result.get("scored") else EXIT_NOT_ENOUGH_DATA
