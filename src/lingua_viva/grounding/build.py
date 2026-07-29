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


def _count_claims(content: str) -> tuple[int, int]:
    fragments = [f.strip() for f in _SENTENCE_SPLIT_RE.split(content or "") if f.strip()]
    uncertain = sum(1 for f in fragments if any(marker in f.lower() for marker in _UNCERTAINTY_MARKERS))
    return len(fragments), uncertain


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


def build_grounding_result(
    *,
    trace: Any = None,
    classification: Any = None,
    content: str = "",
    query_text: str = "",
    query_hash: str = "",
    session_id: str = "",
    intent: str = "",
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
    tier_used = "none"
    for tier in ("local", "drive", "slack"):
        records = grouped.get(tier, [])[:5]
        ids = [str(r.get("source_record_id") or "") for r in records if r.get("source_record_id")]
        status = "hit" if records else "miss"
        tier_attempts.append(TierAttempt(tier=tier, status=status, reason="records_found" if records else "no_records", source_record_ids=ids, count=len(records)))
        if records and tier_used == "none":
            tier_used = tier
            sources_used = [
                SourceUsed(
                    source_record_id=str(r.get("source_record_id") or ""),
                    source_type=str(r.get("source_type") or tier),
                    title=str(r.get("title") or ""),
                    retrieval_scope=str(r.get("retrieval_scope") or "snippet"),
                    sensitivity_hint=str(r.get("sensitivity_hint") or "unknown"),
                )
                for r in records
            ]

    knowledge_hit = bool(_get(trace, "source_citations", None) or _get(trace, "sources", None))
    tier_attempts.append(TierAttempt(tier="knowledge", status="hit" if knowledge_hit else "miss", reason="citations_present" if knowledge_hit else "no_entries", count=1 if knowledge_hit else 0))
    if tier_used == "none" and knowledge_hit:
        tier_used = "knowledge"
    tier_attempts.append(TierAttempt(tier="external", status="blocked", reason="local_first_policy"))

    total_claims, uncertainty_claims = _count_claims(content)
    grounded = bool(sources_used or knowledge_hit)
    unsupported_claims = max(total_claims - uncertainty_claims, 0) if total_claims and not grounded else 0
    score = 1.0 - ((unsupported_claims + uncertainty_claims) / max(total_claims, 1))

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
        gir=GIR(score=round(score, 4), total_claims=total_claims, unsupported_claims=unsupported_claims, uncertainty_claims=uncertainty_claims),
    )
