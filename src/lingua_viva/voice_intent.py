"""
Voice Intent Router — signal-based classification of teacher voice commands.
SPEC_LV_VOICE_INTENT_ROUTER_2026-08-01.

Three intents:
  - observation: teacher describing student behavior (write action)
  - generate: teacher requesting materials/plans (write action)
  - question: teacher asking for information (read-only, default)

No LLM. Pure regex signal matching with priority ordering
(observation > generation > question) — the router runs on every voice
input and must be instant. Write actions (observation, generation) need
their score threshold met; anything uncertain falls through to question,
which is read-only and safe.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# (pattern, weight) — scores are summed per intent, threshold 0.5 for the
# two write intents. Question is the default, not a threshold race.
OBSERVATION_SIGNALS = [
    (r"\b(he|she|they|the student|the learner)\s+\w+ed\b", 0.4),
    (r"\b(helped|read|wrote|said|showed|struggled|completed|participated|used|demonstrated|spoke|asked|answered)\b", 0.3),
    (r"\b(during|while|in class|this morning|today|at recess|in group|in reading|in math)\b", 0.2),
    (r"\b(i (noticed|observed|saw|heard))\b", 0.5),
    (r"\b(observation|note for)\b", 0.6),
]

GENERATION_SIGNALS = [
    (r"\b(create|generate|make|build|prepare|write|design)\b.*\b(worksheet|lesson|plan|exercise|material|activity|handout)\b", 0.7),
    (r"\b(worksheet|lesson plan|exercise|handout|activity|materials)\b.*\b(for|about|on|covering)\b", 0.5),
    (r"\b(differentiated|customized|adapted|tiered)\b", 0.3),
    (r"\b(for (my class|the class|tomorrow|next week|today))\b", 0.2),
]

QUESTION_SIGNALS = [
    (r"^(what|how|when|where|which|who|is|are|can|should|does|do|did|will|would)\b", 0.5),
    (r"\?\s*$", 0.6),
    (r"\b(tell me|explain|show me|describe|summarize)\b", 0.4),
    (r"\b(what (level|tier|progress|status))\b", 0.5),
]

WRITE_INTENT_THRESHOLD = 0.5

# Generic references that mark an observation about an unnamed student —
# enough to classify, not enough to save (safety rule: never guess).
GENERIC_STUDENT_REFERENCE = r"\b(he|she|they|the student|the learner|this student|one student)\b"

MATERIAL_TYPES = ("worksheet", "lesson plan", "exercise", "handout", "activity")

# "for X" targets that are scheduling/class words, not lesson topics.
NON_TOPIC_TARGETS = r"^(my class|the class|class|tomorrow|today|next week|this week|them|the group)\b"


@dataclass
class IntentClassification:
    intent: str                      # "observation" | "generate" | "question"
    confidence: float                # 0.0 - 1.0
    student_id: Optional[str] = None         # detected student (observations only)
    student_name: Optional[str] = None       # display name for confirmation
    needs_clarification: bool = False        # observation detected but no student
    observation_context: dict = field(default_factory=dict)
    generation_context: dict = field(default_factory=dict)
    matched_signals: list[str] = field(default_factory=list)


def _score(transcript_lower: str, signals: list[tuple[str, float]]) -> tuple[float, list[str]]:
    total = 0.0
    matched: list[str] = []
    for pattern, weight in signals:
        if re.search(pattern, transcript_lower):
            total += weight
            matched.append(pattern)
    return total, matched


def detect_student(transcript: str, roster: list[dict]) -> tuple[Optional[str], Optional[str]]:
    """Find which roster student the transcript refers to.

    Returns (student_id, display_name). Matches full display name first,
    then first name as a whole word (>2 chars, to avoid initials matching
    everywhere). No pronoun guessing — an unmatched observation asks for
    clarification instead.
    """
    transcript_lower = transcript.lower()
    for student in roster:
        display_name = str(student.get("display_name") or "")
        if not display_name:
            continue
        if display_name.lower() in transcript_lower:
            return student.get("student_id"), display_name
        first_name = display_name.split()[0].lower()
        if len(first_name) > 2 and re.search(rf"\b{re.escape(first_name)}\b", transcript_lower):
            return student.get("student_id"), display_name
    return None, None


def parse_observation_context(transcript: str) -> dict:
    """Best-effort extraction of CEFR dimension / level / direction hints
    from natural observation speech. Defaults are the same safe defaults
    the observation capture form uses."""
    lowered = transcript.lower()
    context = {"cefr_dimension": "speaking", "cefr_level_hint": "A1+", "direction": "progressing"}

    dimension_keywords = {
        "reading": ["read", "reading", "book", "text", "page", "passage"],
        "writing": ["wrote", "write", "writing", "sentence", "paragraph", "spelled"],
        "speaking": ["said", "spoke", "speaking", "oral", "pronunciation", "conversation", "discussed"],
        "listening": ["listened", "heard", "understood", "comprehension", "followed instructions"],
    }
    for dim, keywords in dimension_keywords.items():
        if any(kw in lowered for kw in keywords):
            context["cefr_dimension"] = dim
            break

    # Explicit CEFR mention beats keyword inference ("used A2-level Italian").
    explicit = re.search(r"\b(pre-a1|a1\+|a2\+|b1\+|a1|a2|b1|b2|c1|c2)\b", lowered)
    if explicit:
        raw = explicit.group(1)
        context["cefr_level_hint"] = "Pre-A1" if raw == "pre-a1" else raw.upper()
    else:
        level_keywords = {
            "Pre-A1": ["no words", "gesture only", "silent", "refused", "no attempt"],
            "A1": ["basic", "single words", "one word", "beginning to"],
            "A1+": ["short sentences", "simple", "helped", "starting to", "with support"],
            "A2": ["connected", "actively", "described", "participated", "independently"],
            "B1": ["fluently", "complex", "explained", "argued", "debated", "detailed"],
        }
        for level, keywords in level_keywords.items():
            if any(kw in lowered for kw in keywords):
                context["cefr_level_hint"] = level
                break

    if any(w in lowered for w in ["struggled", "difficulty", "refused", "silent", "no attempt"]):
        context["direction"] = "emerging"
    elif any(w in lowered for w in ["fluently", "complex", "independently", "confidently"]):
        context["direction"] = "secure"

    return context


def parse_generation_context(transcript: str) -> dict:
    """Extract lesson topic and material type from a generation request."""
    lowered = transcript.lower()
    context: dict = {}

    for material in MATERIAL_TYPES:
        if material in lowered:
            context["material_type"] = material
            break

    # Topic: prefer "about/on/covering X"; fall back to "for X" unless X is
    # a class/scheduling word rather than a topic.
    topic = ""
    match = re.search(r"\b(?:about|on|covering)\s+(.+)$", lowered)
    if match:
        topic = match.group(1)
    else:
        match = re.search(r"\bfor\s+(.+)$", lowered)
        if match and not re.match(NON_TOPIC_TARGETS, match.group(1)):
            topic = match.group(1)
    topic = topic.strip().rstrip(".!?,;: ")
    # "tomorrow's lesson on X" style: drop a leading scheduling fragment.
    topic = re.sub(r"^(tomorrow'?s?|today'?s?|next week'?s?)\s+(lesson|class|unit)\s+(on|about)\s+", "", topic)
    if topic:
        context["topic"] = topic
    return context


def classify_intent(transcript: str, roster: list[dict]) -> IntentClassification:
    """Classify a voice transcript into an actionable intent.

    Priority: observation > generation > question. Question is the default
    whenever neither write intent reaches its threshold — read-only is the
    safe failure mode.
    """
    transcript = str(transcript or "").strip()
    lowered = transcript.lower()

    obs_score, obs_matched = _score(lowered, OBSERVATION_SIGNALS)
    gen_score, gen_matched = _score(lowered, GENERATION_SIGNALS)
    question_score, question_matched = _score(lowered, QUESTION_SIGNALS)

    # A leading question word means the transcript is asking ABOUT behavior,
    # not reporting it ("What did Marco read today?") — question wins even
    # when past-tense observation verbs are present.
    is_question_shaped = bool(re.match(QUESTION_SIGNALS[0][0], lowered)) or lowered.endswith("?")

    if obs_score >= WRITE_INTENT_THRESHOLD and not is_question_shaped:
        student_id, student_name = detect_student(transcript, roster)
        has_generic_reference = bool(re.search(GENERIC_STUDENT_REFERENCE, lowered))
        if student_id is None and not has_generic_reference:
            # Behavior verbs but no student at all — not enough to act on.
            return IntentClassification(
                intent="question",
                confidence=min(1.0, question_score),
                matched_signals=question_matched,
            )
        return IntentClassification(
            intent="observation",
            confidence=min(1.0, obs_score),
            student_id=student_id,
            student_name=student_name,
            needs_clarification=student_id is None,
            observation_context=parse_observation_context(transcript),
            matched_signals=obs_matched,
        )

    if gen_score >= WRITE_INTENT_THRESHOLD and not is_question_shaped:
        return IntentClassification(
            intent="generate",
            confidence=min(1.0, gen_score),
            generation_context=parse_generation_context(transcript),
            matched_signals=gen_matched,
        )

    return IntentClassification(
        intent="question",
        confidence=min(1.0, question_score),
        matched_signals=question_matched,
    )
