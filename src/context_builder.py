"""
Context Builder — The bridge between pipeline data and model prompts.

This is the critical piece: RIU + Knowledge Library + Perplexity + prior paths
become the context that any model uses to reason. The model never starts from
zero — it starts from a known position on a known map with all available evidence.

The context builder produces TWO things:
  1. system_prompt — the agent prompt + lens modifier + structured context
  2. user_message — the original query with inline annotations

The format is designed to reduce model anxiety:
  - Tell the model WHERE it is (classification)
  - Tell it WHAT it already knows (knowledge entries)
  - Tell it WHAT others found (Perplexity research, if called)
  - Tell it WHAT has worked before (prior paths)
  - Tell it WHAT it cannot do (governance rules)

Gap logging:
  - If an RIU has zero knowledge entries → gap signal
  - If Perplexity found something not in KL → proposal signal
  - If classification confidence < 0.5 → weak classification signal
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional


class ContextBuilder:
    """
    Builds the full context that goes to the model.

    The context is the product. Everything the system knows about this query —
    classification, knowledge, research, prior paths, governance — compressed
    into a prompt that makes the model's job as clear as possible.
    """

    def __init__(self, agents_dir: Optional[Path] = None):
        self._agents_dir = agents_dir or Path(__file__).parent.parent / "agents"
        self._prompt_cache: dict[str, str] = {}

    def build(
        self,
        query: str,
        classification: dict,
        knowledge_entries: list[dict],
        prior_paths: list[dict],
        research_result: Optional[dict] = None,
        lens_modifier: Optional[str] = None,
        document_entries: Optional[list[dict]] = None,
    ) -> tuple[str, str, list[str]]:
        """
        Build system prompt and user message for the model.

        Returns:
            (system_prompt, user_message, gap_signals)

        gap_signals are issues found during context assembly:
          - "no_knowledge_at_node:{riu_id}" — RIU exists but KL is empty
          - "weak_classification:{confidence}" — classification is uncertain
          - "research_proposal:{summary}" — Perplexity found something worth storing
        """
        gap_signals = []
        intent = classification.get("default_intent", "RESEARCH")
        riu_id = classification.get("riu_id", "UNKNOWN")

        # 1. Load agent prompt
        agent_prompt = self._load_agent_prompt(intent)

        # 2. Build the context block
        context_block = self._build_context_block(
            classification, knowledge_entries, prior_paths,
            research_result, gap_signals, document_entries,
        )

        # 3. Assemble system prompt: lens + agent prompt + context
        parts = []
        if lens_modifier:
            parts.append(lens_modifier)
        parts.append(agent_prompt)
        parts.append(context_block)
        system_prompt = "\n\n".join(parts)

        # 4. Build user message (the query, clean)
        user_message = query

        # 5. Cache metadata — stable prefix (agent + lens) vs volatile suffix (context)
        import hashlib
        stable_prefix = "\n\n".join([p for p in [lens_modifier, agent_prompt] if p])
        cache_meta = {
            "stable_hash": hashlib.sha256(stable_prefix.encode()).hexdigest()[:16],
            "stable_chars": len(stable_prefix),
            "volatile_chars": len(context_block),
            "total_chars": len(system_prompt),
        }

        return system_prompt, user_message, gap_signals, cache_meta

    def _load_agent_prompt(self, intent: str) -> str:
        """Load the agent prompt.md for this intent."""
        if intent in self._prompt_cache:
            return self._prompt_cache[intent]

        intent_lower = intent.lower()
        prompt_path = self._agents_dir / intent_lower / "prompt.md"
        if prompt_path.exists():
            text = prompt_path.read_text().strip()
            self._prompt_cache[intent] = text
            return text

        # Fallback: minimal prompt
        fallback = f"You are in {intent} mode within Lingua Viva."
        self._prompt_cache[intent] = fallback
        return fallback

    def _build_context_block(
        self,
        classification: dict,
        knowledge_entries: list[dict],
        prior_paths: list[dict],
        research_result: Optional[dict],
        gap_signals: list[str],
        document_entries: Optional[list[dict]] = None,
    ) -> str:
        """
        Build the structured context block.

        This is what the model reads to understand its position.
        Every line reduces ambiguity. Ambiguity is the most expensive
        thing for an LLM — it burns context resolving it.
        """
        riu_id = classification.get("riu_id", "UNKNOWN")
        confidence = classification.get("confidence", 0.0)
        lines = []

        # --- Classification ---
        lines.append(f"[CONTEXT — {riu_id}]")
        lines.append(f"Classification: {classification.get('name', riu_id)}")
        lines.append(f"Domain: {classification.get('domain', 'unknown')}")
        lines.append(f"Confidence: {confidence:.0%}")
        lines.append(f"Signals matched: {', '.join(classification.get('signals_matched', [])) or 'none'}")

        # Governance
        if classification.get("blocks_external"):
            lines.append("Governance: EXTERNAL BLOCKED — all reasoning must be local.")
        elif classification.get("requires_local"):
            lines.append("Governance: local reasoning preferred, external available if needed.")
        else:
            lines.append("Governance: external research permitted.")

        # Weak classification warning
        if confidence < 0.5:
            lines.append(f"WARNING: Low classification confidence ({confidence:.0%}). Consider if the query belongs to a different node.")
            gap_signals.append(f"weak_classification:{confidence:.2f}")

        # --- Traversal Data (artifacts, failure modes, success criteria) ---
        # Injected from the ontology's traversal layer. Gives the model
        # structured guidance: what to produce, what fails, what success looks like.
        node_obj = classification.get("_node")
        if node_obj:
            if getattr(node_obj, "artifacts", None):
                lines.append(f"\n## Expected Artifacts")
                for a in node_obj.artifacts:
                    lines.append(f"  - {a}")

            if getattr(node_obj, "failure_modes", None):
                lines.append(f"\n## Known Failure Modes")
                for category, modes in node_obj.failure_modes.items():
                    if modes:
                        lines.append(f"  {category}: {'; '.join(modes)}")

            if getattr(node_obj, "success_conditions", None):
                lines.append(f"\n## Success Criteria")
                for dimension, criterion in node_obj.success_conditions.items():
                    lines.append(f"  {dimension}: {criterion}")

            if getattr(node_obj, "dependencies", None):
                lines.append(f"\n## Prerequisites")
                for dep_id in node_obj.dependencies:
                    lines.append(f"  - {dep_id}")

            if getattr(node_obj, "requires", None):
                lines.append(f"\n## Required Inputs (must exist before this node executes)")
                for req in node_obj.requires:
                    lines.append(f"  - {req}")

            if getattr(node_obj, "suggests_next", None):
                lines.append(f"\n## Suggested Next Steps")
                for sug_id in node_obj.suggests_next:
                    lines.append(f"  - {sug_id}")

            if getattr(node_obj, "reversibility", "two_way") == "one_way":
                lines.append(f"\n⚠ ONE-WAY DOOR: This decision cannot easily be undone.")

        # --- Knowledge ---
        if knowledge_entries:
            lines.append(f"\n## Known Facts ({len(knowledge_entries)} entries)")
            for entry in knowledge_entries:
                tier = entry.get("tier", 3)
                tier_label = {1: "primary", 2: "secondary", 3: "community"}.get(tier, "?")
                lines.append(f"  [{entry.get('id', '?')}] ({tier_label}) {entry.get('title', '?')}")
                # Include content for high-tier entries
                content = entry.get("content", "")
                if content and tier <= 2:
                    # Truncate to keep context manageable
                    truncated = content[:500] + "..." if len(content) > 500 else content
                    lines.append(f"    {truncated}")
                citations = entry.get("citations", [])
                if citations:
                    lines.append(f"    Sources: {'; '.join(citations[:3])}")
        else:
            lines.append("\n## No knowledge entries found for this node.")
            gap_signals.append(f"no_knowledge_at_node:{riu_id}")

        # --- Retrieved Documents ---
        # Chunks from ingested source documents (e.g. IB curriculum PDFs),
        # already PII-redacted by DocumentParser. A chunk flagged
        # needs_review means it contained a Layer-3-style signal word
        # (e.g. "confidential") and was redacted but not blocked — surface
        # that to the model so it treats the excerpt with appropriate care
        # rather than presenting it as fully verified.
        if document_entries:
            lines.append(f"\n## Retrieved Document Excerpts ({len(document_entries)} chunks)")
            for doc in document_entries:
                page_start = doc.get("page_start", "?")
                page_end = doc.get("page_end", page_start)
                loc = f"{doc.get('source_file', '?')} p.{page_start}"
                if page_end != page_start:
                    loc += f"-{page_end}"
                review_flag = " [NEEDS HUMAN REVIEW]" if doc.get("needs_review") else ""
                lines.append(f"  [{loc} — {doc.get('section', '?')}]{review_flag}")
                text = doc.get("text", "")
                truncated = text[:500] + "..." if len(text) > 500 else text
                lines.append(f"    {truncated}")

        # --- Prior Paths ---
        if prior_paths:
            lines.append(f"\n## Prior Paths ({len(prior_paths)} at this node)")
            for p in prior_paths[:5]:
                outcome = p.get("outcome", "?")
                conf = p.get("confidence", 0)
                path_str = " → ".join(p.get("path", [])[:5])
                lines.append(f"  {path_str} → {outcome} ({conf:.0%})")
        else:
            lines.append("\n## No prior paths at this node (first query of this type).")

        # --- External Research ---
        if research_result:
            content = research_result.get("content", "")
            citations = research_result.get("citations", [])
            lines.append(f"\n## External Research (Perplexity)")
            if content:
                # Truncate if very long
                if len(content) > 2000:
                    lines.append(content[:2000] + "\n[...truncated]")
                else:
                    lines.append(content)
            if citations:
                lines.append(f"\nSources: {'; '.join(str(c) for c in citations[:5])}")

            # Check for new knowledge that should be stored
            gaps = research_result.get("gaps", [])
            contradictions = research_result.get("contradictions", [])
            if contradictions:
                lines.append(f"\nWARNING: {len(contradictions)} contradiction(s) with local knowledge.")
                for c in contradictions:
                    lines.append(f"  - {c}")

        lines.append("\n[END CONTEXT]")
        return "\n".join(lines)
