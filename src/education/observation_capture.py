"""
Observation Capture Pipeline — Product A

Takes a teacher's observation text (already transcribed upstream — by the
Slack bot, a mobile app's on-device STT, or typed directly) and:

  1. Classifies it through the education ontology (LV-* nodes)
  2. Confirms the governance gate (blocks_external + requires_local) that
     PII-bearing education nodes must carry — see BUILD_JOURNAL.md Turn 1
  3. Runs it through the unified PII sanitizer as an audit/defense-in-depth
     check (the raw transcript itself is still what gets stored locally —
     sanitization here proves the check ran, it does not alter what a
     teacher's own local record says)
  4. Appends the observation to the student's lens (student_lens.py),
     which recalculates CEFR/RTI/SEL aggregates and evaluates RTI
     escalation rules A-E

This module never calls an external model or API. Per rti-tiers.md and
observation-capture.md, this pipeline is local-only end to end — matching
the build rule "PII is sacred... when in doubt, route local."

Offline: since this pipeline writes straight to the local SQLite-backed
StudentLensStore, capture always succeeds regardless of connectivity —
there is no cloud dependency in the write path itself. Every observation
is born with sync_status="pending" (see student_lens.py); the local
device store IS the offline queue. A device-to-school-server sync
(observation-capture.md Stage 4) is out of scope for the Friday vertical
slice — see BUILD_JOURNAL.md scope decision.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ontology.engine import OntologyEngine, ClassificationResult  # noqa: E402
from src.education.student_lens import Observation, StudentLensStore  # noqa: E402


class ExternalRoutingBlockedError(PermissionError):
    """Raised if any code path attempts to route blocks_external content
    externally. This should never be reachable in normal operation —
    it exists as a hard assertion, not a soft warning."""


class ObservationCapturePipeline:
    """
    The Product A capture path: raw teacher text -> classified,
    governance-checked, sanitized-audited, lens-updated observation.
    """

    def __init__(
        self,
        store: StudentLensStore,
        engine: Optional[OntologyEngine] = None,
    ):
        self.store = store
        self.engine = engine or OntologyEngine()
        from sanitizer.app import sanitize

        self._sanitize = sanitize

    def capture(
        self,
        student_id: str,
        teacher_id: str,
        raw_transcript: str,
        template_type: str,
        teacher_edited_transcript: Optional[str] = None,
        rti_tier: Optional[int] = None,
        cefr_dimension: Optional[str] = None,
        cefr_level_observed: Optional[str] = None,
        cefr_direction: Optional[str] = None,
        sel_domain: Optional[str] = None,
        sel_valence: Optional[str] = None,
        urgency_flag: bool = False,
        support_category: Optional[str] = None,
        need_statement: Optional[str] = None,
        strength_statement: Optional[str] = None,
        strategy_statement: Optional[str] = None,
        strategy_outcome: Optional[str] = None,
        evidence_summary: Optional[str] = None,
        source_type: Optional[str] = None,
        support_entries: Optional[list[dict]] = None,
        classification_guidance: Optional[dict] = None,
        teacher_feedback: Optional[dict] = None,
    ) -> dict:
        """
        Classify + govern + sanitize-audit + persist one observation.

        Tags (rti_tier, cefr_*, sel_*, urgency_flag, support_category, ...) mirror
        the teacher app's tap-to-confirm defaults (observation-capture.md Stage 1) —
        this pipeline accepts them as explicit values rather than
        inferring them with an LLM, per the build rule against guessing
        CEFR/RTI classifications. The ontology classification below is
        used to confirm routing/governance, not to invent clinical tags.
        """
        text_for_classification = teacher_edited_transcript or raw_transcript
        classification = self.engine.classify(text_for_classification)

        # IMPORTANT: classification is advisory here, not the PII gate.
        # Free-form teacher speech ("She read the passage but lost the
        # thread...") frequently does NOT contain the ontology's trigger
        # signals ("I noticed", "observation", "capture"...) and can land
        # on a low-confidence, non-guarded node like CORE-RESEARCH — this
        # was measured directly, not assumed (see BUILD_JOURNAL.md Turn 3).
        # The actual PII gate is structural: everything that enters through
        # ObservationCapturePipeline.capture() IS student data by
        # construction (the teacher explicitly opened a student's
        # observation entry), so this pipeline never routes anything
        # externally regardless of what classify() returns. governance_note
        # below is a visibility/audit signal about ontology tagging
        # accuracy, not a statement that data was ever at risk of leaking.
        governance_note = None
        if not (classification.blocks_external and classification.requires_local):
            governance_note = (
                f"{classification.riu_id} ({classification.name}) does not carry "
                "blocks_external=True + requires_local=True — ontology signal "
                "match was weak/absent for this text (confidence "
                f"{classification.confidence}). No leak risk: this pipeline has "
                "no external-routing code path at all. Recorded for classifier "
                "tuning visibility only."
            )

        sanitizer_result = self._sanitize(text_for_classification, context="education")

        observation = Observation(
            student_id=student_id,
            teacher_id=teacher_id,
            template_type=template_type,
            raw_transcript=raw_transcript,
            teacher_edited_transcript=teacher_edited_transcript,
            ontology_node=classification.riu_id,
            rti_tier=rti_tier,
            cefr_dimension=cefr_dimension,
            cefr_level_observed=cefr_level_observed,
            cefr_direction=cefr_direction,
            sel_domain=sel_domain,
            sel_valence=sel_valence,
            urgency_flag=urgency_flag,
            support_category=support_category,
            need_statement=need_statement,
            strength_statement=strength_statement,
            strategy_statement=strategy_statement,
            strategy_outcome=strategy_outcome,
            evidence_summary=evidence_summary,
            source_type=source_type,
            support_entries=support_entries or [],
            classification_guidance=classification_guidance,
            teacher_feedback=teacher_feedback,
        )

        result = self.store.append_observation(observation)
        result["ethos_trait_suggestions"] = self._suggest_ethos_traits(
            text_for_classification
        )
        result["classification"] = {
            "riu_id": classification.riu_id,
            "name": classification.name,
            "confidence": classification.confidence,
            "blocks_external": classification.blocks_external,
            "requires_local": classification.requires_local,
        }
        result["sanitizer_report"] = {
            "ok": sanitizer_result["ok"],
            "blocked": sanitizer_result["blocked"],
            "redaction_count": len(sanitizer_result["redactions"]),
        }
        result["governance_note"] = governance_note
        return result

    def _suggest_ethos_traits(self, text: str) -> list[dict]:
        """Deterministic (keyword-based, no LLM) school-ethos trait
        suggestions for an observation. Suggestions are NEVER auto-written
        to the student's ethos_profile — the teacher confirms each one via
        confirm_ethos_suggestion(). A broken/invalid local ethos.yaml must
        not break the capture write path, so taxonomy problems degrade to
        zero suggestions with a note instead of raising."""
        from src.education import ethos as ethos_mod

        try:
            taxonomy = ethos_mod.load_ethos()
        except Exception as exc:  # noqa: BLE001 — capture must never break:
            # EthosValidationError is the expected case, but an unreadable
            # file (OSError), bad encoding, etc. must degrade identically.
            return [
                {
                    "error": f"ethos taxonomy unavailable: {exc}",
                    "status": "taxonomy_error",
                }
            ]
        suggestions = []
        for trait_id in ethos_mod.match_traits(text, taxonomy):
            trait = ethos_mod.get_trait(taxonomy, trait_id) or {}
            suggestions.append(
                {
                    "trait_id": trait_id,
                    "label": trait.get("label", trait_id),
                    "descriptor": trait.get("descriptor", ""),
                    "confidence": "model_suggested",
                    "status": "pending_teacher_confirmation",
                }
            )
        return suggestions

    def confirm_ethos_suggestion(
        self,
        student_id: str,
        teacher_id: str,
        trait_id: str,
        summary: str,
        observation_id: Optional[str] = None,
    ) -> dict:
        """Teacher confirms an ethos trait suggestion (or records trait
        evidence directly). This is the ONLY path from an observation to
        the student's ethos_profile — written as teacher_confirmed because
        a teacher explicitly invoked it. Trait membership is validated
        against the active taxonomy inside add_ethos_evidence.

        If observation_id is given it must exist AND belong to this
        student — evidence claiming a grounding that does not exist must
        be rejected at write time, not discovered at report time."""
        if observation_id is not None:
            row = self.store._conn.execute(
                "SELECT student_id FROM observations WHERE observation_id = ?",
                (observation_id,),
            ).fetchone()
            if row is None or row["student_id"] != student_id:
                raise ValueError(
                    f"observation_id '{observation_id}' does not exist for "
                    f"student '{student_id}' — refusing to record evidence "
                    "with an unverifiable source."
                )
        return self.store.add_ethos_evidence(
            student_id=student_id,
            trait_id=trait_id,
            summary=summary,
            created_by=teacher_id,
            evidence_type="observation",
            source_observation_id=observation_id,
            confidence="teacher_confirmed",
        )

    def assert_never_external(self, classification: ClassificationResult) -> None:
        """
        Hard assertion for any future code path that might attempt to
        route observation content externally (e.g. a recommendation
        generator). Mirrors the short-circuit in
        src/pipeline.py::GatewayInterface.sanitize_query — blocks_external
        nodes never even reach the sanitizer's "safe to send" branch there.
        This makes the same guarantee explicit and independently testable
        at the education-module boundary.
        """
        if classification.blocks_external:
            raise ExternalRoutingBlockedError(
                f"{classification.riu_id} is blocks_external=True — "
                "student observation content must never route externally."
            )

    def pending_sync_count(self, student_id: Optional[str] = None) -> int:
        """Count of observations not yet synced to a school server. With
        no cloud sync target in this vertical slice, this will simply
        grow — it's wired for when Stage 4 Sync is built."""
        query = "SELECT COUNT(*) as c FROM observations WHERE sync_status = 'pending'"
        params: tuple = ()
        if student_id:
            query += " AND student_id = ?"
            params = (student_id,)
        row = self.store._conn.execute(query, params).fetchone()
        return row["c"]
