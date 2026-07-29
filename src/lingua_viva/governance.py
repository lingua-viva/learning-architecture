"""Governance control plane — Trust Status and signed observation export.

Spec: dev/SPEC_GOVERNANCE_CONTROL_PLANE_2026-07-28.md §Lingua Viva.

MC governs professional data. LV governs children's data, so the trust bar is
higher and the audience is different: a school administrator, not a developer.
The first screen must answer five questions in plain language —

  1. What student data did Lingua Viva access?
  2. What stayed on this computer?
  3. Was any student-identifiable information sent externally?
  4. What was redacted before anything was written?
  5. What needs the teacher's review before it goes to a parent?

Every number here is counted from a real local artifact (the privacy log, the
trace log, the student database). Where something genuinely cannot be measured
this module says so in the payload rather than emitting a comfortable zero —
a governance screen that guesses is worse than no governance screen, because
it converts an unknown into a false assurance.

**On "signed"**: these packs are sealed with an HMAC-SHA256 keyed on a random
32-byte secret generated on this machine and stored 0600. That makes tampering
detectable by anyone holding the key, and :func:`verify_pack` really does
verify. It is NOT a third-party notarization or a public-key signature — it
proves "this pack is unchanged since this machine produced it", not "this
machine is who it claims to be". The pack says so in its own text so an
administrator cannot over-read it.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from src.lingua_viva.config import lv_home

SIGNATURE_ALGORITHM = "HMAC-SHA256"
PACK_FORMAT_VERSION = 1

SIGNATURE_MEANING = (
    "This seal proves the pack has not been altered since this computer "
    "created it. It is not a signature from the school or from any outside "
    "authority, and it does not prove who operated the computer."
)


# --- signing key -----------------------------------------------------------


def signing_key_path() -> Path:
    override = os.environ.get("LV_EXPORT_SIGNING_KEY_PATH")
    if override:
        return Path(override).expanduser()
    return lv_home() / "config" / "export_signing_key"


def _load_or_create_signing_key() -> bytes:
    """Machine-local secret, created once, 0600 from birth.

    Generated rather than derived so that deleting the file genuinely
    invalidates every previously issued pack instead of silently
    regenerating the same key.
    """
    path = signing_key_path()
    try:
        existing = path.read_bytes().strip()
        if len(existing) >= 32:
            return existing
    except (FileNotFoundError, OSError):
        pass

    key = secrets.token_hex(32).encode("ascii")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    descriptor = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(key)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    os.chmod(path, 0o600)
    return key


def key_fingerprint() -> str:
    """Short public identifier for the signing key. Safe to display."""
    return hashlib.sha256(_load_or_create_signing_key()).hexdigest()[:16]


def _canonical(payload: Any) -> bytes:
    """Stable bytes for signing: key order and separators fixed, so a pack
    that round-trips through JSON still verifies."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sign_payload(payload: dict) -> dict:
    signature = hmac.new(_load_or_create_signing_key(), _canonical(payload), hashlib.sha256)
    return {
        "algorithm": SIGNATURE_ALGORITHM,
        "key_fingerprint": key_fingerprint(),
        "signature": signature.hexdigest(),
        "means": SIGNATURE_MEANING,
    }


def verify_pack(pack: dict) -> bool:
    """True when `pack` is byte-identical to what this machine signed."""
    if not isinstance(pack, dict):
        return False
    seal = pack.get("seal")
    if not isinstance(seal, dict) or not seal.get("signature"):
        return False
    body = {key: value for key, value in pack.items() if key != "seal"}
    expected = hmac.new(_load_or_create_signing_key(), _canonical(body), hashlib.sha256)
    # compare_digest: constant time, and tolerant of a non-hex string
    return hmac.compare_digest(str(seal["signature"]), expected.hexdigest())


# --- anonymisation ---------------------------------------------------------


def anonymous_student_ref(student_id: str) -> str:
    """Stable, non-reversible reference for a student in an export.

    Keyed with the machine signing key so the same child gets the same
    reference across packs from this computer (an administrator can follow one
    pupil through a series) while the reference is meaningless anywhere else
    and cannot be reversed into a name or id by whoever receives it.
    """
    digest = hmac.new(
        _load_or_create_signing_key(), f"student:{student_id}".encode("utf-8"), hashlib.sha256
    )
    return f"S-{digest.hexdigest()[:12].upper()}"


# --- Trust Status ----------------------------------------------------------


def _count_events() -> dict[str, int]:
    from src.lingua_viva.privacy_log import read_privacy_events

    counts: dict[str, int] = {}
    for event in read_privacy_events(limit=100_000):
        counts[event.event_type] = counts.get(event.event_type, 0) + 1
    return counts


def _student_totals() -> dict[str, Any]:
    """Roster and review counts, or an explicit unavailable marker.

    The student database is optional (a fresh install has none), and a
    governance screen must distinguish "no children recorded" from "could not
    read the record" — they mean very different things to an administrator.
    """
    try:
        from src.education.student_lens import StudentLensStore

        # Must match src/web.py's _student_db_path() exactly — a governance
        # screen reading a different file than the app writes would report
        # confident numbers about the wrong database.
        db_path = os.environ.get("LV_STUDENT_DB_PATH")
        path = Path(db_path) if db_path else lv_home() / "runtime" / "student_lenses.db"
        if not path.exists():
            return {"available": True, "students": 0, "awaiting_review": 0}

        with StudentLensStore(db_path=path) as store:
            lenses = store.list_lenses()
            awaiting = 0
            for lens in lenses:
                try:
                    report = store.export_ethos_report(
                        lens["student_id"], include_unconfirmed=True
                    )
                except Exception:
                    continue
                awaiting += len(report.get("pending_review", {}).get("traits", []))
                awaiting += len(report.get("pending_review", {}).get("strengths", []))
            return {
                "available": True,
                "students": len(lenses),
                "awaiting_review": awaiting,
            }
    except Exception as exc:  # noqa: BLE001 - reported, never raised at the UI
        return {"available": False, "reason": type(exc).__name__}


def trust_status() -> dict:
    """The five questions, answered from local artefacts only."""
    events = _count_events()
    students = _student_totals()

    external_calls = events.get("external_call_made", 0)
    redactions = events.get("student_data_blocked", 0)
    kept_local = events.get("student_data_kept_local_for_reasoning", 0)
    attribution_stripped = events.get("ai_attribution_stripped", 0)
    observations_local = events.get("observation_saved_locally", 0)
    local_queries = events.get("query_processed_locally", 0)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "questions": [
            {
                "id": "accessed",
                "question": "What student data did Lingua Viva use?",
                "answer": (
                    f"{students['students']} student record(s) on this computer"
                    if students.get("available")
                    else "Could not read the student record on this computer"
                ),
                "detail": (
                    f"{observations_local} observation(s) saved locally."
                    if students.get("available")
                    else f"Reading the student database failed ({students.get('reason')}). "
                         "The count below is not a zero — it is unknown."
                ),
                "status": "ok" if students.get("available") else "unknown",
            },
            {
                "id": "stayed_local",
                "question": "What stayed on this computer?",
                "answer": f"{local_queries} question(s) answered here",
                "detail": (
                    "Student records, observations and the privacy log are files on "
                    "this computer. Nothing syncs anywhere on its own."
                ),
                "status": "ok",
            },
            {
                "id": "sent_externally",
                "question": "Was any student information sent outside this computer?",
                # Enforced at REASON by local_only (see
                # tests/test_student_data_stays_local.py): when the entry gate
                # sees student or family data, every external model is
                # discarded and the question fails closed if no local model
                # exists. So this is a mechanism, not a hope — but it is a
                # forward guarantee, which is why the detail below reports the
                # external-call count rather than hiding it.
                "answer": "No",
                "detail": (
                    f"{kept_local} question(s) mentioning a student were kept on this "
                    f"computer instead of the connected cloud provider. "
                    f"{external_calls} question(s) with no student information were sent "
                    "to a cloud model you connected."
                    if external_calls
                    else (
                        f"{kept_local} question(s) mentioning a student were kept on this "
                        "computer. No question has been sent to an outside model."
                    )
                ),
                "status": "ok",
            },
            {
                "id": "redacted",
                "question": "What was removed before anything was written?",
                "answer": f"{redactions} redaction(s)",
                "detail": (
                    f"{attribution_stripped} parent draft(s) had wording crediting AI removed. "
                    "Names, addresses and contact details are removed from anything that "
                    "leaves the local model."
                ),
                "status": "ok",
            },
            {
                "id": "needs_review",
                "question": "What needs your review before a parent sees it?",
                "answer": (
                    f"{students.get('awaiting_review', 0)} item(s) awaiting confirmation"
                    if students.get("available")
                    else "Unknown"
                ),
                "detail": (
                    "Anything the model suggested but you have not confirmed is kept out "
                    "of parent reports until you confirm it."
                ),
                "status": (
                    "attention"
                    if students.get("available") and students.get("awaiting_review")
                    else ("ok" if students.get("available") else "unknown")
                ),
            },
        ],
        "counters": {
            "students": students.get("students"),
            "awaiting_review": students.get("awaiting_review"),
            "local_queries": local_queries,
            "external_calls": external_calls,
            "redactions": redactions,
            "kept_local_for_student_data": kept_local,
            "observations_local": observations_local,
        },
        "student_record_readable": bool(students.get("available")),
    }


# --- publication safety ----------------------------------------------------


def _publication_policy() -> dict:
    from pathlib import Path as _Path

    root = _Path(__file__).resolve().parents[2]
    candidate = root / "governance" / "publication_safety.yaml"
    try:
        import yaml

        data = yaml.safe_load(candidate.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


AI_ATTRIBUTION_MARKERS = (
    "generated by ai",
    "written by ai",
    "ai-generated",
    "assessed by ai",
    "chatgpt",
    "gpt-4",
    "claude wrote",
    "the ai decided",
    "the ai recommends",
)


def check_publication_safety(pack: dict, student_names: Optional[list[str]] = None) -> dict:
    """Check an outgoing pack against governance/publication_safety.yaml.

    Only the rules that can be decided mechanically are enforced; the rest of
    the policy is judgement and is reported as `advisory` rather than being
    silently treated as passed. Returns violations that BLOCK the export and
    advisories that do not.
    """
    policy = _publication_policy()
    blob = json.dumps(pack, ensure_ascii=False).lower()

    violations: list[dict] = []

    for name in student_names or []:
        cleaned = (name or "").strip()
        if len(cleaned) >= 3 and cleaned.lower() in blob:
            violations.append(
                {
                    "rule": "privacy_rules.student_data",
                    "message": (
                        "A student's name appears in this export. Exports use an "
                        "anonymous reference instead."
                    ),
                }
            )
            break

    for marker in AI_ATTRIBUTION_MARKERS:
        if marker in blob:
            violations.append(
                {
                    "rule": "privacy_rules.ai_attribution",
                    "message": (
                        "This export credits AI with a decision. Lingua Viva records "
                        "what the teacher confirmed, not what a model produced."
                    ),
                }
            )
            break

    return {
        "policy_version": policy.get("version"),
        "policy_loaded": bool(policy),
        "violations": violations,
        "blocked": bool(violations),
        "advisory": [
            "Institution and colleague naming, claim maturity, and evidence "
            "sufficiency are policy judgements this check cannot decide. Review "
            "them before sharing outside the school."
        ],
        "enforced_rules": ["privacy_rules.student_data", "privacy_rules.ai_attribution"],
    }


# --- signed observation export ---------------------------------------------


def build_observation_pack(student_id: str, *, store) -> dict:
    """A compliance pack for one student: what was captured, what the model
    suggested, and what the teacher actually confirmed.

    The distinction is the point — an administrator needs to see that
    unconfirmed model output never entered the report body.
    """
    report = store.export_ethos_report(student_id, include_unconfirmed=True)
    pending = report.get("pending_review", {})

    confirmed_traits = report.get("traits", [])
    confirmed_strengths = report.get("strengths", [])

    body = {
        "format_version": PACK_FORMAT_VERSION,
        "pack_type": "observation_export",
        "student": {
            "reference": anonymous_student_ref(student_id),
            "note": "Anonymous reference. The child's name is not in this pack.",
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "confirmed_by_teacher": {
            "traits": confirmed_traits,
            "strengths": confirmed_strengths,
            "count": len(confirmed_traits) + len(confirmed_strengths),
        },
        "model_suggested_not_confirmed": {
            "traits": pending.get("traits", []),
            "strengths": pending.get("strengths", []),
            "count": len(pending.get("traits", [])) + len(pending.get("strengths", [])),
            "note": (
                "Listed for transparency only. These were suggested but not "
                "confirmed by the teacher, and are excluded from parent reports."
            ),
        },
    }
    body["seal"] = {}  # placeholder so the signed body shape is explicit
    signable = {key: value for key, value in body.items() if key != "seal"}
    body["seal"] = sign_payload(signable)
    return body
