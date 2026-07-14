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
    ) -> dict:
        """
        Classify + govern + sanitize-audit + persist one observation.

        Tags (rti_tier, cefr_*, sel_*, urgency_flag) mirror the teacher
        app's tap-to-confirm defaults (observation-capture.md Stage 1) —
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
        )

        result = self.store.append_observation(observation)
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
