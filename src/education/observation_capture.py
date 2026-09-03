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

import re
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ontology.engine import OntologyEngine, ClassificationResult  # noqa: E402
from src.education.student_lens import Observation, StudentLensStore  # noqa: E402


# ---------------------------------------------------------------------------
# Support-category suggestion (SPEC_LV_BASE_LENS_SCHOOL_CATEGORIES_2026-08-01)
#
# Deterministic keyword/regex signals per category — same mechanics as
# voice_intent.py's OBSERVATION_SIGNALS: (pattern, weight) summed per
# category. No LLM. Suggestions are NEVER silently written into a category
# bucket: below CATEGORY_SUGGESTION_THRESHOLD the obligatory-routing rule
# sends the entry to open_questions as model_suggested instead of guessing.
# ---------------------------------------------------------------------------

CATEGORY_SUGGESTION_THRESHOLD = 0.5  # matches voice_intent.WRITE_INTENT_THRESHOLD

CATEGORY_SIGNALS: dict[str, list[tuple[str, float]]] = {
    "learning_and_cognition": [
        (r"\b(understand|understood|comprehension|concept|grasp(ed)?)\b", 0.4),
        (r"\b(remember(ed|s)?|recall(ed)?|retain(ed)?|memory)\b", 0.4),
        (r"\b(confus(ed|ing)|lost the thread|mixed up|couldn'?t follow)\b", 0.4),
        (r"\b(problem[- ]solving|reasoning|abstract)\b", 0.3),
    ],
    "communication_and_language": [
        (r"\b(vocabulary|word[- ]finding|find(ing)? (the )?words?)\b", 0.4),
        (r"\b(pronunciation|articulat(e|ed|ion)|stutter(ed|ing)?)\b", 0.4),
        (r"\b(express (himself|herself|themselves|ideas)|verbal(ly)?)\b", 0.4),
        (r"\b(communicat(e|ed|ion|ing))\b", 0.3),
        (r"\b(gestur(e|ed|es|ing)|nonverbal|non-verbal)\b", 0.3),
    ],
    "executive_functioning": [
        (r"\b(stay(ing)? on task|on[- ]task|off[- ]task)\b", 0.5),
        (r"\b(focus(ed|ing)?|distract(ed|ion|ible)?|attention)\b", 0.4),
        (r"\b(finish(ed|ing)?|complet(e|ed|ing)) (the |a |his |her |their )?(task|work|assignment|activity)\b", 0.4),
        (r"\b(organiz(e|ed|ation|ing)|plan(ned|ning)|time management)\b", 0.4),
        (r"\b(forgot (his|her|their) (materials|book|homework)|transition(s|ing)?)\b", 0.3),
        (r"\b(impulsiv(e|ity)|started before (the )?instructions)\b", 0.3),
    ],
    "social_skills": [
        (r"\b(friend(s|ship)?|peer(s)?|classmate(s)?)\b", 0.3),
        (r"\b(shar(e|ed|ing)|tak(e|ing) turns|turn[- ]taking|took turns)\b", 0.4),
        (r"\b(group work|in (the )?group|cooperat(e|ed|ion|ive)|collaborat(e|ed|ion|ive))\b", 0.3),
        (r"\b(conflict|argu(ed|ment|ing)|teas(ed|ing)|excluded)\b", 0.4),
        (r"\b(social(ly)?|interact(s|ed|ion|ing)?)\b", 0.3),
    ],
    "emotional_regulation": [
        (r"\b(upset|cry(ing)?|cried|tears|meltdown|tantrum|outburst)\b", 0.5),
        (r"\b(frustrat(ed|ion)|angry|anger|furious)\b", 0.4),
        (r"\b(calm(ed)? (down|himself|herself|themselves)|self[- ]regulat(e|ed|ion))\b", 0.4),
        (r"\b(anxious|anxiety|worried|overwhelmed|shut(s)? down)\b", 0.4),
    ],
    "physical_sensory_needs": [
        (r"\b(nois(e|y)|loud|headphones|ear (defenders|muffs))\b", 0.4),
        (r"\b(sensory|fidget(s|ed|ing)?|seating|wobble (stool|cushion))\b", 0.4),
        (r"\b(handwriting|pencil grip|fine motor|gross motor|motor skills)\b", 0.4),
        (r"\b(tired|fatigue(d)?|vision|glasses|hearing aid)\b", 0.3),
        (r"\b(light(ing)? (bother|hurt)|covers (his|her|their) ears)\b", 0.4),
    ],
    "attendance_and_engagement": [
        (r"\b(absent|absence(s)?|missed (school|class|the lesson)|didn'?t (come|show))\b", 0.5),
        (r"\b(late|tardy|arriv(ed|ing) late)\b", 0.4),
        (r"\b(disengag(ed|ement)|not engag(ed|ing)|stopped participating|withdrawn from class)\b", 0.4),
        (r"\b(refus(es|ed|ing) to (come|attend|join))\b", 0.4),
    ],
    "advanced_enrichment": [
        (r"\b(finish(ed|es)? (early|first|quickly))\b", 0.4),
        (r"\b(too easy|bored|not challenged|needs? (a |more )?challenge)\b", 0.5),
        (r"\b(advanced|ahead of|beyond (the )?(class|level)|gifted)\b", 0.4),
        (r"\b(extension|enrichment)\b", 0.4),
    ],
    "personal_context": [
        (r"\b(safeguarding|child protection|mandated report|cps|personal context)\b", 0.6),
        (r"\b(home situation|family situation|living situation|housing|shelter)\b", 0.5),
        (r"\b(abuse|neglect|domestic violence|unsafe at home)\b", 0.6),
        (r"\b(bereavement|grief|family emergency|caregiver)\b", 0.5),
        # Italian equivalents, added 2026-09-03. These signals are consumed by
        # safeguarding.classify_severity as a SECONDARY signal that rounds
        # GREEN up to AMBER. Being English-only meant that round-up could never
        # fire for an Italian classroom — the product's actual language.
        # This suggester is advisory and weighted; it is deliberately NOT
        # rewired to the shared RED taxonomy, which gates rather than scores.
        # NOTE: "segnalazione" and "abuso" are BOTH deliberately narrowed, for
        # the reason written into safeguarding_indicators.py: a bare match fires
        # on "segnalazione per il proiettore rotto" (a maintenance report) and
        # on "abuso di sostanze" in a science lesson. A first draft of these
        # very lines used the bare terms and turned three control cases AMBER.
        (r"\b(tutela dei minori|protezione dell'infanzia)\b", 0.6),
        (r"\bsegnalazione\b[^.!?\n]{0,30}\b(servizi sociali|tribunale|minor\w*|maltrattament\w*|abus\w*)\b", 0.6),
        (r"\b(situazione (familiare|abitativa|a casa)|contesto familiare|alloggio)\b", 0.5),
        (r"\b(maltrattament\w*|trascuratezz\w*|violenza domestica|non al sicuro a casa)\b", 0.6),
        (r"\b(?:ha|hanno) subit[oa]\s+(?:degli\s+|dei\s+)?abus\w*\b|\bvittima di abus\w*\b", 0.6),
        (r"\b(lutto|dolore familiare|emergenza familiare|caregiver|chi se ne prende cura)\b", 0.5),
    ],
}


def suggest_support_categories(transcript: str) -> list[dict]:
    """Score a transcript against every support category's signal list.

    Returns [{"category_id", "confidence", "matched_signals"}, ...] sorted
    by confidence (desc), zero-score categories omitted, confidence capped
    at 1.0. Purely advisory — callers decide what (if anything) to write,
    gated by CATEGORY_SUGGESTION_THRESHOLD.
    """
    lowered = str(transcript or "").lower()
    suggestions = []
    for category_id, signals in CATEGORY_SIGNALS.items():
        total = 0.0
        matched: list[str] = []
        for pattern, weight in signals:
            if re.search(pattern, lowered):
                total += weight
                matched.append(pattern)
        if total > 0:
            suggestions.append(
                {
                    "category_id": category_id,
                    "confidence": round(min(1.0, total), 2),
                    "matched_signals": matched,
                }
            )
    suggestions.sort(key=lambda item: item["confidence"], reverse=True)
    return suggestions


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
        ethos_trait_id: Optional[str] = None,
        duplicate_window_seconds: int = 0,
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

        result = self.store.append_observation(
            observation, duplicate_window_seconds=duplicate_window_seconds
        )
        if result.get("duplicate"):
            result.setdefault("ethos_trait_suggestions", [])
            result.setdefault("category_suggestions", [])
            result.setdefault("strategy_outcome_parsed", {})
            return result
        result["ethos_trait_suggestions"] = self._record_ethos_trait_mapping(
            student_id=student_id,
            teacher_id=teacher_id,
            observation_id=observation.observation_id,
            text=text_for_classification,
            explicit_trait_id=ethos_trait_id,
        )
        result["category_suggestions"] = suggest_support_categories(
            text_for_classification
        )
        result["strategy_outcome_parsed"] = self._autofile_strategy_outcome(
            observation, result["category_suggestions"]
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

    def _trait_summary(self, text: str) -> str:
        cleaned = " ".join(str(text or "").split())
        return cleaned[:240] or "Observation evidence"

    def _record_ethos_trait_mapping(
        self,
        *,
        student_id: str,
        teacher_id: str,
        observation_id: str,
        text: str,
        explicit_trait_id: Optional[str],
    ) -> list[dict]:
        suggestions = self._suggest_ethos_traits(text)
        if suggestions and suggestions[0].get("status") == "taxonomy_error":
            return suggestions
        summary = self._trait_summary(text)
        explicit_trait_id = str(explicit_trait_id or "").strip() or None
        if explicit_trait_id:
            self.store.add_ethos_evidence(
                student_id,
                explicit_trait_id,
                summary,
                teacher_id,
                source_observation_id=observation_id,
                confidence="teacher_confirmed",
            )
            return [{
                "trait_id": explicit_trait_id,
                "confidence": "teacher_confirmed",
                "status": "teacher_confirmed",
            }]
        written = []
        for suggestion in suggestions:
            trait_id = suggestion.get("trait_id")
            if not trait_id:
                continue
            self.store.add_ethos_evidence(
                student_id,
                trait_id,
                summary,
                teacher_id,
                source_observation_id=observation_id,
                confidence="model_suggested",
            )
            written.append({**suggestion, "status": "inferred_pending_review"})
        return written

    def _autofile_strategy_outcome(
        self, observation: Observation, suggestions: list[dict]
    ) -> dict:
        """Place a narrated strategy outcome ("tried X and it helped") into
        the support profile as model_suggested — never teacher_confirmed.

        Obligatory-routing rule: the category bucket write only happens when
        the top category suggestion clears CATEGORY_SUGGESTION_THRESHOLD.
        Below threshold the entry lands in that category's open_questions
        instead — low confidence gates the write; it never guesses. With no
        category signal at all there is nothing to hang the entry on, so
        nothing is written (the parse still returns in the response for the
        teacher to act on).

        Skipped entirely when the teacher already supplied explicit support
        entries or a strategy statement — that data flows through the
        teacher_confirmed form path and must not be double-written.
        """
        from src.lingua_viva.voice_intent import parse_strategy_outcome

        parsed = parse_strategy_outcome(
            observation.teacher_edited_transcript or observation.raw_transcript
        )
        parsed["autofiled"] = None
        if parsed["outcome"] is None or not parsed["strategy_statement"]:
            return parsed
        if observation.support_entries or observation.strategy_statement:
            return parsed
        if not suggestions:
            return parsed

        top = suggestions[0]
        if top["confidence"] >= CATEGORY_SUGGESTION_THRESHOLD:
            bucket = (
                "strategies_worked"
                if parsed["outcome"] == "worked"
                else "strategies_not_worked"
            )
            text = parsed["strategy_statement"]
        else:
            bucket = "open_questions"
            outcome_label = (
                "worked" if parsed["outcome"] == "worked" else "did not work"
            )
            text = (
                f'Strategy "{parsed["strategy_statement"]}" reported as '
                f"{outcome_label} — category unconfirmed"
            )
        self.store.add_support_entry(
            student_id=observation.student_id,
            category_id=top["category_id"],
            bucket=bucket,
            text=text,
            created_by=observation.teacher_id,
            source_observation_id=observation.observation_id,
            confidence="model_suggested",
        )
        parsed["autofiled"] = {"category_id": top["category_id"], "bucket": bucket}
        return parsed

    def _suggest_ethos_traits(self, text: str) -> list[dict]:
        """Deterministic (keyword-based, no LLM) school-ethos trait
        suggestions for an observation. The caller records these as
        model_suggested evidence pending teacher review; explicit teacher
        picks are recorded as teacher_confirmed evidence. A broken/invalid
        local ethos.yaml must not break the capture write path, so taxonomy
        problems degrade to zero suggestions with a note instead of raising."""
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
