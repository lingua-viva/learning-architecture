from __future__ import annotations

import hashlib
import re
from typing import Any

from src.lingua_viva.grounding.schema import (
    GIR,
    TIERS,
    Classification,
    GroundingResult,
    Routing,
    SourceUsed,
    TierAttempt,
)

_SENTENCE_SPLIT_RE = re.compile(r"[.!?]+")
_UNCERTAINTY_MARKERS = ("might", "may ", "maybe", "possibly", "unclear", "unknown", "uncertain", "probably", "likely")
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_OBS_ID_RE = re.compile(r"\bOBS-[A-Za-z0-9_-]+\b")
_SRC_ID_RE = re.compile(r"\bSRC-[A-Za-z0-9_-]+\b")
_STOPWORDS = frozenset({
    "a", "about", "and", "are", "as", "at", "be", "by", "can", "do", "does", "for",
    "from", "give", "how", "i", "in", "is", "it", "me", "of", "on", "or", "our",
    "should", "student", "students", "tell", "that", "the", "their", "this", "to",
    "tomorrow", "what", "when", "where", "which", "with",
})
_MANUALE_RELEVANT_TERMS = frozenset({
    "beginner", "beginners", "cefr", "class", "classroom", "curriculum", "grade",
    "greetings", "independent", "italian", "language", "lesson", "listening",
    "manuale", "practice", "speaking", "unit",
})


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def compute_grounding_id(trace_id: str, query_hash: str) -> str:
    digest = hashlib.sha256(f"{trace_id}|{query_hash}".encode()).hexdigest()[:20]
    return f"GRD-{digest}"


def _query_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode()).hexdigest()[:20]


def _claim_fragments(content: str) -> list[str]:
    return [f.strip() for f in _SENTENCE_SPLIT_RE.split(content or "") if f.strip()]


def _count_claims(content: str) -> tuple[int, int]:
    fragments = _claim_fragments(content)
    uncertain = sum(1 for f in fragments if any(marker in f.lower() for marker in _UNCERTAINTY_MARKERS))
    return len(fragments), uncertain


def _tokens(text: str) -> set[str]:
    return {token for token in _TOKEN_RE.findall((text or "").lower()) if token not in _STOPWORDS and len(token) > 2}


def _record_relevant(record: dict, query_tokens: set[str]) -> bool:
    if not query_tokens:
        return False
    haystack = " ".join(
        str(record.get(field) or "")
        for field in ("title", "summary", "uri", "container")
    )
    record_tokens = _tokens(haystack)
    return bool(query_tokens & record_tokens)


def _record_tokens(record: dict) -> set[str]:
    haystack = " ".join(
        str(record.get(field) or "")
        for field in ("title", "summary", "uri", "container")
    )
    return _tokens(haystack)


def _citation_relevant(citation: str, query_tokens: set[str]) -> bool:
    citation_tokens = _tokens(citation)
    if query_tokens & citation_tokens:
        return True
    generic_manuale = (citation or "").strip().lower() in {"manuale", "manuale v1"}
    return generic_manuale and bool(query_tokens & _MANUALE_RELEVANT_TERMS)


def _records_by_type() -> dict[str, list[dict]]:
    try:
        from src.lingua_viva.sources.ledger import read_records

        records = read_records(limit=500)
    except Exception:
        records = []
    grouped: dict[str, list[dict]] = {tier: [] for tier in TIERS}
    for record in records:
        source_type = str(record.get("source_type") or "")
        if source_type in grouped:
            grouped[source_type].append(record)
    return grouped


def _source_record_ids(records_by_type: dict[str, list[dict]]) -> set[str]:
    ids: set[str] = set()
    for records in records_by_type.values():
        ids.update(str(record.get("source_record_id") or "") for record in records if record.get("source_record_id"))
    return ids


def _trace_values(trace: Any, *names: str) -> list[str]:
    values: list[str] = []
    for name in names:
        raw = _get(trace, name, None)
        if raw is None:
            continue
        if isinstance(raw, (list, tuple, set)):
            values.extend(str(item).strip() for item in raw if str(item).strip())
        elif isinstance(raw, dict):
            values.extend(str(item).strip() for item in raw.values() if str(item).strip())
        elif str(raw).strip():
            values.append(str(raw).strip())
    return values


def _student_scope(trace: Any, query_text: str) -> tuple[set[str], set[str]]:
    student_ids = set(_trace_values(trace, "student_id", "scope_student_id", "student_ids", "scope_student_ids"))
    student_names = set(_trace_values(trace, "student_name", "scope_student_name", "student_names", "scope_student_names"))

    try:
        from src.education.student_lens import StudentLensStore

        store = StudentLensStore()
        try:
            roster = store.list_lenses()
            query_tokens = _tokens(query_text)
            for lens in roster:
                sid = str(lens.get("student_id") or "").strip()
                display = str(lens.get("display_name") or "").strip()
                display_tokens = _tokens(display)
                if sid in student_ids or display in student_names or (display_tokens and display_tokens & query_tokens):
                    if sid:
                        student_ids.add(sid)
                    if display:
                        student_names.add(display)
        finally:
            store.close()
    except Exception:
        pass
    return student_ids, student_names


def _observation_student_id(observation_id: str) -> str | None:
    try:
        from src.education.student_lens import StudentLensStore

        store = StudentLensStore()
        try:
            row = store._conn.execute(
                "SELECT student_id FROM observations WHERE observation_id = ?",
                (observation_id,),
            ).fetchone()
            return str(row["student_id"]) if row else None
        finally:
            store.close()
    except Exception:
        return None


def _fabricated_identifiers(
    *,
    content: str,
    source_record_ids: set[str],
    student_ids_in_scope: set[str],
    student_names_in_scope: set[str],
) -> list[str]:
    fabricated: list[str] = []

    for obs_id in _OBS_ID_RE.findall(content or ""):
        owner = _observation_student_id(obs_id)
        if owner is None or (student_ids_in_scope and owner not in student_ids_in_scope):
            fabricated.append(obs_id)

    for source_id in _SRC_ID_RE.findall(content or ""):
        if source_id not in source_record_ids:
            fabricated.append(source_id)

    if student_names_in_scope:
        lowered = content.lower()
        for name in student_names_in_scope:
            if name.lower() not in lowered:
                continue
            # In-scope student names are allowed; this branch exists so the
            # linkage rule is explicit without logging unrelated roster names.
    return sorted(set(fabricated))


def _fragment_supported(fragment: str, support_token_sets: list[set[str]]) -> bool:
    fragment_tokens = _tokens(fragment)
    if not fragment_tokens:
        return False
    return any(fragment_tokens & support_tokens for support_tokens in support_token_sets)


def _score_v1(total_claims: int, uncertainty_claims: int, grounded: bool, low_synthesis_confidence: bool) -> tuple[int, float]:
    if low_synthesis_confidence:
        return total_claims, 0.0
    unsupported_claims = max(total_claims - uncertainty_claims, 0) if total_claims and not grounded else 0
    score = 1.0 - ((unsupported_claims + uncertainty_claims) / max(total_claims, 1))
    return unsupported_claims, max(0.0, min(1.0, score))


def build_grounding_result(
    *,
    trace: Any = None,
    classification: Any = None,
    content: str = "",
    query_text: str = "",
    query_hash: str = "",
    session_id: str = "",
    intent: str = "",
    synthesis_confidence: float | None = None,
) -> GroundingResult:
    trace_id = _get(trace, "trace_id", "") or ""
    resolved_session_id = session_id or _get(trace, "session_id", "") or ""
    resolved_query_hash = query_hash or _get(trace, "query_hash", "") or _query_hash(query_text)
    node_id = _get(classification, "riu_id", "") or _get(classification, "node", "") or _get(trace, "domain", "")
    domain = _get(classification, "domain", "") or _get(trace, "domain", "")
    confidence = float(_get(classification, "confidence", 0.0) or 0.0)

    grouped = _records_by_type()
    tier_attempts: list[TierAttempt] = []
    sources_used: list[SourceUsed] = []
    source_records_used: list[dict] = []
    tier_used = "none"
    query_tokens = _tokens(query_text)

    for tier in ("local", "drive", "slack"):
        records = grouped.get(tier, [])[:5]
        relevant_records = [record for record in records if _record_relevant(record, query_tokens)]
        ids = [str(r.get("source_record_id") or "") for r in records if r.get("source_record_id")]
        status = "hit" if records else "miss"
        tier_attempts.append(TierAttempt(tier=tier, status=status, reason="records_found" if records else "no_records", source_record_ids=ids, count=len(records)))
        if relevant_records and tier_used == "none":
            tier_used = tier
            source_records_used = relevant_records
            sources_used = [
                SourceUsed(
                    source_record_id=str(r.get("source_record_id") or ""),
                    source_type=str(r.get("source_type") or tier),
                    title=str(r.get("title") or ""),
                    retrieval_scope=str(r.get("retrieval_scope") or "snippet"),
                    sensitivity_hint=str(r.get("sensitivity_hint") or "unknown"),
                )
                for r in relevant_records
            ]

    citation_values = list(_get(trace, "source_citations", None) or _get(trace, "sources", None) or [])
    knowledge_hit = any(_citation_relevant(str(citation), query_tokens) for citation in citation_values)
    tier_attempts.append(TierAttempt(tier="knowledge", status="hit" if knowledge_hit else "miss", reason="citations_present" if knowledge_hit else "no_entries", count=1 if knowledge_hit else 0))
    if tier_used == "none" and knowledge_hit:
        tier_used = "knowledge"
    tier_attempts.append(TierAttempt(tier="external", status="blocked", reason="local_first_policy"))

    fragments = _claim_fragments(content)
    total_claims = len(fragments)
    raw_uncertainty_claims = sum(1 for f in fragments if any(marker in f.lower() for marker in _UNCERTAINTY_MARKERS))
    grounded = bool(sources_used or knowledge_hit)
    low_synthesis_confidence = synthesis_confidence is not None and synthesis_confidence < 0.1
    _v1_unsupported_claims, v1_score = _score_v1(total_claims, raw_uncertainty_claims, grounded, low_synthesis_confidence)
    if low_synthesis_confidence:
        unsupported_claims = total_claims
        uncertainty_claims = 0
        fabricated = []
        score = 0.0
    else:
        support_token_sets = [_record_tokens(record) for record in source_records_used]
        if knowledge_hit:
            support_token_sets.extend(_tokens(str(citation)) for citation in citation_values)
        source_ids = _source_record_ids(grouped)
        student_ids_in_scope, student_names_in_scope = _student_scope(trace, query_text)
        fabricated = _fabricated_identifiers(
            content=content,
            source_record_ids=source_ids,
            student_ids_in_scope=student_ids_in_scope,
            student_names_in_scope=student_names_in_scope,
        )
        unsupported_claims = len(fabricated)
        uncertainty_claims = 0
        for fragment in fragments:
            supported = _fragment_supported(fragment, support_token_sets)
            uncertain = any(marker in fragment.lower() for marker in _UNCERTAINTY_MARKERS)
            if supported:
                if uncertain:
                    uncertainty_claims += 1
                continue
            if uncertain and tier_used == "none":
                continue
            unsupported_claims += 1
        score = 1.0 - ((unsupported_claims + uncertainty_claims) / max(total_claims, 1))
        score = max(0.0, min(1.0, score))

    return GroundingResult(
        grounding_id=compute_grounding_id(trace_id, resolved_query_hash),
        trace_id=trace_id,
        session_id=resolved_session_id,
        query_hash=resolved_query_hash,
        intent=intent or _get(classification, "default_intent", "") or "",
        classification=Classification(node_id=node_id, domain=domain, confidence=confidence, blocks_external=True),
        routing=Routing(selected_provider=_get(trace, "model_used", "") or "", external_called=False),
        tier_attempts=tier_attempts,
        tier_used=tier_used,
        sources_used=sources_used,
        gir=GIR(
            score=round(score, 4),
            total_claims=total_claims,
            unsupported_claims=unsupported_claims,
            uncertainty_claims=uncertainty_claims,
            fabricated_identifiers=fabricated,
            v1_score=round(v1_score, 4),
            v1_delta=round(score - v1_score, 4),
        ),
    )
