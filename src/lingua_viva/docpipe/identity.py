"""STEP 5 — identity resolution (SPEC_LV_UNIFIED_REAL_DATA_FIX_2026-08-19, L8).

`student_id = slug(display_name)` makes identity BE the spelling: "Marco B-R"
in a support file and "Marco Bianchi" in the class list silently become two
children. This module gives each child a canonical id plus a set of observed
SURFACE FORMS, and resolves new spellings against a class roster (~39 names,
never globally):

- **exact**    — the normalized spelling IS a roster student's display name or
  a surface form a human already ruled on → canonical student_id. Replaying a
  recorded ruling is deterministic, not a guess.
- **queue**    — the spelling plausibly matches roster students (first name
  exact + abbreviated-initial compatibility) → an unresolved queue for a
  human. Default per ruling §8-3: ALWAYS queue, NEVER auto-merge — confidence
  currently measures nothing (STEP 3 deleted the dead gate).
- **new**      — no plausible match → a genuinely new student.

The queue is the same NDJSON event-log pattern as ingest_review.py
(last-event-wins state). An "assigned" event is the `same_person_as` relation
of the MC lens precedent (DESIGN_LENS_SCHEMA_MC_LENS_V1_2026-08-10): a
relation between a spelling and an existing canonical record — never a new
entity type, never a coercive merge. Assigned events double as the
surface-form registry that future resolutions replay.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from src.lingua_viva.runtime_paths import runtime_data_dir


def identity_queue_path() -> Path:
    return runtime_data_dir("ingest_review") / "identity.ndjson"


def _now_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_name(name: str) -> str:
    """One normal form for spelling comparison: NFKD + strip accents,
    casefold, nickname parentheses dropped ("Anna (Annie) Villa" ==
    "Anna Villa"), whitespace collapsed. Never used to REWRITE a display
    name — only to compare."""
    text = unicodedata.normalize("NFKD", str(name or ""))
    # Strip combining marks (accents): è→e, ë→e, à→a, ù→u
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"\([^)]*\)", " ", text)
    return re.sub(r"\s+", " ", text).strip().casefold()


def fold_text(text: str) -> str:
    """Accent-fold + lowercase while PRESERVING length and character
    positions — unlike normalize_name, which collapses whitespace. Use this
    when the caller needs indices into the original text (e.g. splitting a
    document at a name's position). Each input char maps to exactly one
    output char."""
    out = []
    for ch in str(text or ""):
        decomposed = unicodedata.normalize("NFKD", ch)
        base = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
        base = (base[0] if base else ch).lower()
        out.append(base[0] if base else ch)
    return "".join(out)


def _levenshtein(s1: str, s2: str) -> int:
    """Pure-Python Levenshtein distance (no external dependency)."""
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            curr.append(min(
                prev[j + 1] + 1,
                curr[j] + 1,
                prev[j] + (c1 != c2),
            ))
        prev = curr
    return prev[-1]


# Common nickname → canonical name mappings for school context
_NICKNAME_MAP: dict[str, list[str]] = {
    "abby": ["abigail"],
    "abi": ["abigail"],
    "gail": ["abigail"],
    "alex": ["alexander", "alexandra", "alessandra", "alessandro"],
    "andy": ["andrew", "andrea"],
    "ben": ["benjamin"],
    "charlie": ["charles", "charlotte"],
    "chris": ["christopher", "christine", "cristina"],
    "dan": ["daniel", "daniele"],
    "dave": ["david", "davide"],
    "eli": ["elijah", "eliana", "elisabetta"],
    "em": ["emily", "emma", "emilia"],
    "frankie": ["francesco", "francesca", "frank"],
    "gigi": ["luigi", "luisa"],
    "jake": ["jacob"],
    "jenny": ["jennifer", "ginevra"],
    "joe": ["joseph", "giuseppe"],
    "kate": ["katherine", "caterina"],
    "leo": ["leonardo", "leon"],
    "liz": ["elizabeth", "elisabetta"],
    "matt": ["matthew", "matteo"],
    "max": ["maximilian", "massimo", "massimiliano"],
    "mike": ["michael", "michele"],
    "nat": ["natalie", "natalia"],
    "nick": ["nicholas", "nicola", "nicolò"],
    "sam": ["samuel", "samantha"],
    "seb": ["sebastian", "sebastiano"],
    "tom": ["thomas", "tommaso"],
    "tony": ["anthony", "antonio"],
    "vic": ["victor", "vittoria", "vittorio"],
    "will": ["william"],
}


def _name_tokens(name: str) -> list[str]:
    return [token for token in normalize_name(name).split(" ") if token]


def _initials(token: str) -> list[str]:
    """Initial letters carried by an abbreviated token: "b-r" → ["b", "r"],
    "b." → ["b"]. A token is abbreviation-shaped when every dash/dot part is
    a single letter."""
    parts = [part for part in re.split(r"[-.\u2010\u2011]", token) if part]
    if parts and all(len(part) == 1 for part in parts):
        return parts
    return []


def _compatible(detected_tokens: list[str], roster_tokens: list[str]) -> bool:
    """Plausible same-child match: first name exact, and every following
    detected token is either an exact roster token or an abbreviation whose
    initials all start roster tokens ("Marco B-R" ~ "Marco Bianchi-Rossi",
    and — one initial resolvable — "Marco B-R" ~ "Marco Bianchi")."""
    if not detected_tokens or not roster_tokens:
        return False
    # First token must match exactly, OR be an abbreviation whose initial
    # starts the roster's first token (handles "S." matching "Scala")
    if detected_tokens[0] != roster_tokens[0]:
        first_initials = _initials(detected_tokens[0])
        if not first_initials or not any(
            roster_tokens[0].startswith(initial) for initial in first_initials
        ):
            return False
    rest_roster = roster_tokens[1:]
    rest_detected = detected_tokens[1:]
    if not rest_detected or not rest_roster:
        # a bare first name against a roster child with that first name is
        # plausible — the human decides
        return True
    roster_initials = {token[0] for token in rest_roster}
    for token in rest_detected:
        if token in rest_roster:
            continue
        initials = _initials(token)
        if not initials:
            return False
        if not any(initial in roster_initials for initial in initials):
            return False
    return True


# ---------------------------------------------------------------------------
# Event log (clone of the ingest_review NDJSON pattern)
# ---------------------------------------------------------------------------


def _append_event(event: dict[str, Any]) -> dict[str, Any]:
    path = identity_queue_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "event_id": f"identity-{uuid.uuid4().hex}",
        "event_at": _now_z(),
        **event,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return payload


def read_events() -> list[dict[str, Any]]:
    try:
        lines = identity_queue_path().read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    events: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            events.append(data)
    return events


def _item_key(teacher_id: str, display_name: str) -> str:
    return f"{teacher_id}|{normalize_name(display_name)}"


def current_items() -> dict[str, dict[str, Any]]:
    """Last-event-wins queue state, keyed by (teacher, normalized spelling)."""
    state: dict[str, dict[str, Any]] = {}
    for event in read_events():
        key = _item_key(str(event.get("teacher_id") or ""),
                        str(event.get("display_name") or ""))
        if key.strip("|"):
            state[key] = event
    return state


def list_open_items(teacher_id: Optional[str] = None) -> list[dict[str, Any]]:
    items = [
        item for item in current_items().values()
        if item.get("status") == "open"
        and (not teacher_id or item.get("teacher_id") == teacher_id)
    ]
    return sorted(
        items,
        key=lambda item: str(item.get("queued_at") or item.get("event_at") or ""),
        reverse=True,
    )


def surface_forms() -> dict[str, str]:
    """The registry human rulings build: normalized spelling → canonical
    student_id, from every "assigned" event (the same_person_as relation).
    Later events win, so a corrected ruling replaces the old one."""
    forms: dict[str, str] = {}
    for event in read_events():
        if event.get("status") != "assigned":
            continue
        spelling = normalize_name(str(event.get("display_name") or ""))
        student_id = str(event.get("student_id") or "").strip()
        if spelling and student_id:
            forms[spelling] = student_id
    return forms


def enqueue_unresolved(
    *,
    teacher_id: str,
    display_name: str,
    source_id: str,
    candidates: list[dict[str, str]],
    job_id: str = "",
) -> dict[str, Any]:
    existing = current_items().get(_item_key(teacher_id, display_name))
    if existing and existing.get("status") == "open":
        return existing
    return _append_event({
        "status": "open",
        "queued_at": _now_z(),
        "teacher_id": teacher_id,
        "display_name": display_name,
        "source_id": source_id,
        "job_id": job_id,
        "candidates": [
            {
                "student_id": str(candidate.get("student_id") or ""),
                "display_name": str(candidate.get("display_name") or ""),
            }
            for candidate in candidates
        ],
    })


def mark_assigned(
    *,
    teacher_id: str,
    display_name: str,
    student_id: str,
    source_id: str = "",
) -> dict[str, Any]:
    """Record the same_person_as ruling: this spelling IS that student."""
    return _append_event({
        "status": "assigned",
        "assigned_at": _now_z(),
        "teacher_id": teacher_id,
        "display_name": display_name,
        "student_id": student_id,
        "source_id": source_id,
    })


def mark_created(*, teacher_id: str, display_name: str, student_id: str) -> dict[str, Any]:
    """The human ruled "genuinely new student" — closes the queue item."""
    return _append_event({
        "status": "created",
        "created_at": _now_z(),
        "teacher_id": teacher_id,
        "display_name": display_name,
        "student_id": student_id,
    })


def mark_dismissed(*, teacher_id: str, display_name: str) -> dict[str, Any]:
    return _append_event({
        "status": "dismissed",
        "dismissed_at": _now_z(),
        "teacher_id": teacher_id,
        "display_name": display_name,
    })


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def resolve(
    display_name: str,
    roster: list[dict[str, Any]],
) -> dict[str, Any]:
    """Resolve one detected spelling against a class roster.

    Returns {"status": "exact", "student_id": ...} |
            {"status": "queue", "candidates": [{student_id, display_name}]} |
            {"status": "new"}.
    Roster entries need student_id + display_name. Matching is scoped to the
    roster handed in — the caller passes the approving teacher's ~39, never
    the whole school.
    """
    spelling = normalize_name(display_name)
    if not spelling:
        return {"status": "new"}
    forms = surface_forms()
    if spelling in forms:
        return {"status": "exact", "student_id": forms[spelling]}
    detected_tokens = _name_tokens(display_name)
    # Also try reversed name order (handles "Abigail Chang" vs "Chang Abigail")
    reversed_spelling = " ".join(reversed(spelling.split()))
    reversed_tokens = list(reversed(detected_tokens))

    # Expand nicknames: "Abby" → also try "Abigail"
    expanded_first_names = set()
    if detected_tokens:
        first = detected_tokens[0]
        expanded_first_names.add(first)
        if first in _NICKNAME_MAP:
            expanded_first_names.update(_NICKNAME_MAP[first])
        # Reverse lookup: if first IS a canonical name, find its nicknames
        for nick, canonicals in _NICKNAME_MAP.items():
            if first in canonicals:
                expanded_first_names.add(nick)

    candidates: list[dict[str, str]] = []
    levenshtein_candidates: list[dict[str, str]] = []

    for entry in roster:
        roster_name = str(entry.get("display_name") or "")
        student_id = str(entry.get("student_id") or "")
        if not roster_name or not student_id:
            continue
        norm_roster = normalize_name(roster_name)
        roster_tokens = _name_tokens(roster_name)

        # Tier 1: Exact normalized match (both orders)
        if norm_roster == spelling or norm_roster == reversed_spelling:
            return {"status": "exact", "student_id": student_id}

        # Tier 2: Token-compatible match (abbreviation-aware)
        if _compatible(detected_tokens, roster_tokens) or _compatible(reversed_tokens, roster_tokens):
            candidates.append({"student_id": student_id, "display_name": roster_name})
            continue

        # Tier 3: First-name-only match (single token input)
        if len(detected_tokens) == 1 and roster_tokens:
            roster_first = roster_tokens[0] if len(roster_tokens) == 1 else roster_tokens[-1]
            roster_all = set(roster_tokens)
            if detected_tokens[0] in roster_all:
                candidates.append({"student_id": student_id, "display_name": roster_name})
                continue
            # Check nickname expansion
            if expanded_first_names & roster_all:
                candidates.append({"student_id": student_id, "display_name": roster_name})
                continue

        # Tier 4: Nickname match with surname (e.g. "Abby Chang" → "Chang Abigail")
        if len(detected_tokens) >= 2 and roster_tokens:
            det_surname_tokens = detected_tokens[1:]
            roster_surname_tokens = roster_tokens[:-1] if len(roster_tokens) > 1 else []
            roster_first_token = roster_tokens[-1] if len(roster_tokens) > 1 else roster_tokens[0]
            # Check if detected first name (or its expansion) matches roster first name
            if (expanded_first_names & {roster_first_token}
                    and (set(det_surname_tokens) & set(roster_surname_tokens)
                         or _levenshtein(" ".join(det_surname_tokens), " ".join(roster_surname_tokens)) <= 1)):
                candidates.append({"student_id": student_id, "display_name": roster_name})
                continue
            # Also try reversed detected tokens for nickname matching
            rev_first = reversed_tokens[0] if reversed_tokens else ""
            rev_expanded = {rev_first}
            if rev_first in _NICKNAME_MAP:
                rev_expanded.update(_NICKNAME_MAP[rev_first])
            for nick, canonicals in _NICKNAME_MAP.items():
                if rev_first in canonicals:
                    rev_expanded.add(nick)
            if rev_expanded & {roster_first_token}:
                candidates.append({"student_id": student_id, "display_name": roster_name})
                continue

        # Tier 5: Levenshtein fuzzy match (catches typos, accents)
        # Only for 2+ token names to avoid false positives
        if len(detected_tokens) >= 2:
            dist_fwd = _levenshtein(spelling, norm_roster)
            dist_rev = _levenshtein(reversed_spelling, norm_roster)
            min_dist = min(dist_fwd, dist_rev)
            # Threshold: max 2 edits for names ≤ 15 chars, max 3 for longer
            threshold = 2 if len(spelling) <= 15 else 3
            if min_dist <= threshold and min_dist > 0:
                levenshtein_candidates.append({
                    "student_id": student_id,
                    "display_name": roster_name,
                })

    # Return results by confidence tier
    if candidates:
        return {"status": "queue", "candidates": candidates}
    if levenshtein_candidates:
        return {"status": "queue", "candidates": levenshtein_candidates}
    return {"status": "new"}
