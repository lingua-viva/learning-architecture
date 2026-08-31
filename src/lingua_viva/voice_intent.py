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

import difflib
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

# (pattern, weight) — scores are summed per intent, threshold 0.5 for the
# two write intents. Question is the default, not a threshold race.
OBSERVATION_SIGNALS = [
    (r"\b(he|she|they|the student|the learner)\s+\w+ed\b", 0.4),
    (r"\b(helped|read|wrote|said|showed|struggled|completed|participated|used|demonstrated|spoke|asked|answered)\b", 0.3),
    (r"\b(is|are|was|were)\s+(beginning|starting|trying|learning|improving|struggling|showing)\b", 0.3),
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

# Student detection v2 (SPEC_LV_VOICE_STUDENT_DETECTION_V2_2026-08-01):
# fuzzy matching for STT garbling ("Marko" -> Marco). Threshold-gated, no
# guessing: a unique close match >= cutoff resolves (and is spoken back by
# name so a misresolution is audible); two candidates within cutoff ask.
# First names of <= 3 chars stay exact-only — fuzzy on "Al"/"Bo" is noise.
FUZZY_NAME_CUTOFF = 0.8
FUZZY_MIN_NAME_LEN = 4

# Third-person references that let conversational context resolve a
# follow-up observation ("he also asked for help") to the last-mentioned
# student. Deterministic regex — never inferred.
CONTEXT_PRONOUN_RE = re.compile(r"\b(he|she|they)\b", re.IGNORECASE)

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
    # Detection v2 (additive): how the student was matched, which transcript
    # token matched (for the pronoun-precedence rule), and the candidate set
    # when a fuzzy token is ambiguous between two roster names.
    match_quality: Optional[str] = None      # "exact" | "fuzzy" | "ambiguous" | None
    matched_token: Optional[str] = None
    candidates: list[dict] = field(default_factory=list)  # [{student_id, display_name}]


@dataclass
class StudentDetection:
    """Full detection outcome — internal to voice_intent + the voice/act
    handler. The public detect_student() tuple is a projection of this."""
    student_id: Optional[str] = None
    display_name: Optional[str] = None
    match_quality: Optional[str] = None      # "exact" | "fuzzy" | "ambiguous" | None
    matched_token: Optional[str] = None      # transcript token that matched (lowercase)
    candidates: list[dict] = field(default_factory=list)


def _fold_accents(text: str) -> str:
    """NFKD accent-fold for fuzzy name comparison only ("josé" -> "jose").
    Never applied on the exact-match paths — those stay byte-identical."""
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    )


def _score(transcript_lower: str, signals: list[tuple[str, float]]) -> tuple[float, list[str]]:
    total = 0.0
    matched: list[str] = []
    for pattern, weight in signals:
        if re.search(pattern, transcript_lower):
            total += weight
            matched.append(pattern)
    return total, matched


def detect_student_detailed(transcript: str, roster: list[dict]) -> StudentDetection:
    """Find which roster student the transcript refers to.

    Exact pass first (unchanged from v1): full display name substring, then
    first name as a whole word (>2 chars, to avoid initials matching
    everywhere). Only when exact finds nothing does the fuzzy pass run:
    difflib close-match per transcript token (possessives stripped) against
    roster first names of >= FUZZY_MIN_NAME_LEN chars, at
    FUZZY_NAME_CUTOFF. A unique hit resolves as "fuzzy"; two roster names
    within cutoff of the same token is "ambiguous" and must ask. No pronoun
    guessing here — conversational context is the caller's concern.
    """
    transcript_lower = transcript.lower()
    # Pass 1: full display name substring, EITHER order — rosters store
    # surname-first ("Chang Abigail") while teachers speak first-last
    # ("Abigail Chang"). Same fix family as 63d9631 in the doc pipeline.
    # Exact strings, no folding (exact paths stay byte-identical).
    for student in roster:
        display_name = str(student.get("display_name") or "")
        if not display_name:
            continue
        name_lower = display_name.lower()
        parts = display_name.split()
        reversed_lower = (
            (" ".join(parts[1:]) + " " + parts[0]).lower() if len(parts) >= 2 else ""
        )
        if name_lower in transcript_lower or (
            reversed_lower and reversed_lower in transcript_lower
        ):
            return StudentDetection(
                student_id=student.get("student_id"),
                display_name=display_name,
                match_quality="exact",
                matched_token=name_lower,
            )

    # Pass 2: a single name token as a whole word (>2 chars). Try BOTH the
    # first and last tokens of the display name — with surname-first rosters
    # the spoken given name is the LAST token. Two distinct students hitting
    # (siblings share a surname) -> ambiguous, never a silent pick.
    token_matches: list[tuple[dict, str]] = []
    for student in roster:
        display_name = str(student.get("display_name") or "")
        if not display_name:
            continue
        parts = display_name.split()
        name_tokens = {parts[0].lower()}
        if len(parts) >= 2:
            name_tokens.add(parts[-1].lower())
        for token in sorted(name_tokens):
            if len(token) > 2 and re.search(rf"\b{re.escape(token)}\b", transcript_lower):
                token_matches.append((student, token))
                break
    if len(token_matches) == 1:
        student, token = token_matches[0]
        return StudentDetection(
            student_id=student.get("student_id"),
            display_name=str(student.get("display_name") or ""),
            match_quality="exact",
            matched_token=token,
        )
    if len(token_matches) > 1:
        return StudentDetection(
            match_quality="ambiguous",
            matched_token=token_matches[0][1],
            candidates=[
                {
                    "student_id": str(s.get("student_id") or ""),
                    "display_name": str(s.get("display_name") or ""),
                }
                for s, _ in token_matches
            ],
        )

    # Fuzzy pass. Name-token lookup: short names are exact-only by design.
    # Keys are accent-FOLDED ("josé" -> "jose") because Whisper routinely
    # drops accents on international rosters and difflib treats é != e —
    # folding is confined to this fuzzy pass; exact paths above are
    # untouched. Both first and last display-name tokens are indexed
    # (surname-first rosters). Two roster names folding to the same key ride
    # the existing shared-name list -> ambiguous, never a silent pick.
    first_names: dict[str, list[dict]] = {}
    for student in roster:
        display_name = str(student.get("display_name") or "")
        if not display_name:
            continue
        parts = display_name.split()
        index_tokens = {parts[0].lower()}
        if len(parts) >= 2:
            index_tokens.add(parts[-1].lower())
        for raw_token in index_tokens:
            folded = _fold_accents(raw_token)
            if len(folded) >= FUZZY_MIN_NAME_LEN:
                first_names.setdefault(folded, []).append(student)
    if not first_names:
        return StudentDetection()

    # Possessive stripping: "marco's" -> "marco" (STT renders both).
    # Tokenizer accepts unicode letters ([^\W\d_] under re.UNICODE) so
    # accented transcript tokens ("José") reach the fold instead of being
    # split apart by an ascii-only character class.
    tokens = [
        token[:-2] if token.endswith("'s") else token
        for token in re.findall(r"[^\W\d_]+(?:'s)?", transcript_lower)
    ]
    for token in tokens:
        if len(token) < FUZZY_MIN_NAME_LEN:
            continue
        hits = difflib.get_close_matches(
            _fold_accents(token), list(first_names.keys()), n=2,
            cutoff=FUZZY_NAME_CUTOFF)
        if not hits:
            continue
        # Dedupe: one student can be indexed under both name tokens.
        matched_students = []
        seen_ids: set[str] = set()
        for name in hits:
            for s in first_names[name]:
                sid = str(s.get("student_id") or "")
                if sid not in seen_ids:
                    seen_ids.add(sid)
                    matched_students.append(s)
        if len(matched_students) == 1:
            student = matched_students[0]
            return StudentDetection(
                student_id=student.get("student_id"),
                display_name=str(student.get("display_name") or ""),
                match_quality="fuzzy",
                matched_token=token,
            )
        # Two roster names both within cutoff (Marco/Marko, or a shared
        # first name) — never pick; the caller asks with both candidates.
        return StudentDetection(
            match_quality="ambiguous",
            matched_token=token,
            candidates=[
                {
                    "student_id": str(s.get("student_id") or ""),
                    "display_name": str(s.get("display_name") or ""),
                }
                for s in matched_students
            ],
        )
    return StudentDetection()


def detect_student(
    transcript: str, roster: list[dict]
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Tuple projection of detect_student_detailed for internal callers:
    (student_id, display_name, match_quality). Ambiguity projects to
    (None, None, "ambiguous") — the detailed form carries the candidates."""
    detection = detect_student_detailed(transcript, roster)
    return detection.student_id, detection.display_name, detection.match_quality


def context_takes_precedence(transcript: str, matched_token: Optional[str]) -> bool:
    """Should the conversational-context student win over the detection?

    The subtlest rule in detection v2 (spec test 5): "he also helped Nora"
    — the pronoun is the subject, so a fresh context student (Marco) keeps
    attribution; Nora appearing as object must not steal it. Conversely
    "Nora struggled today" has no pronoun before the name, so Nora wins.

    True when a third-person pronoun appears in the transcript BEFORE the
    first detected roster-name token — or when a pronoun appears and no
    name was detected at all. False when there is no pronoun: a nameless,
    pronounless observation must never silently attach to context.
    """
    pronoun = CONTEXT_PRONOUN_RE.search(transcript)
    if not pronoun:
        return False
    if not matched_token:
        return True
    name = re.search(rf"\b{re.escape(matched_token)}", transcript, re.IGNORECASE)
    if not name:
        return True
    return pronoun.start() < name.start()


def parse_observation_context(transcript: str) -> dict:
    """Best-effort extraction of CEFR dimension / level / direction hints
    from natural observation speech.

    Evidence-only (BUG-5 sibling fix, 2026-08-02): keys are set ONLY when
    the transcript actually matched a signal. This used to seed
    speaking/A1+/progressing unconditionally — invented clinical data that
    the voice save path wrote straight into cefr_level_observed and that
    adaptive/cohort planning then consumed as if a teacher had judged it."""
    lowered = transcript.lower()
    context: dict = {}

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


# Strategy-outcome parsing (SPEC_LV_BASE_LENS_SCHOOL_CATEGORIES_2026-08-01):
# "Strategies trialed — successful or not" narrated naturally. not_worked
# markers are checked FIRST because "didn't work" contains "work".
STRATEGY_ATTEMPT_RE = re.compile(
    r"\b(?:tried|trialed|trialled|we tried|i tried)\s+(.+)$", re.IGNORECASE
)
STRATEGY_NOT_WORKED_RE = re.compile(
    r"\b(?:didn'?t help|did not help|didn'?t work|did not work|no difference|"
    r"still struggl\w*|shut(?:s)? down|got worse|refused|didn'?t stick|"
    r"made (?:it|things) worse|didn'?t click)\b",
    re.IGNORECASE,
)
STRATEGY_WORKED_RE = re.compile(
    r"\b(?:worked|helped|clicked|made a difference|went well|succeeded|"
    r"really working|big improvement)\b",
    re.IGNORECASE,
)
# Where the strategy statement ends and the outcome clause begins.
STRATEGY_CLAUSE_SPLIT_RE = re.compile(
    r"\s*(?:\band it\b|\band (?:he|she|they)\b|\bbut\b|\bwhich\b|,|—|;).*$",
    re.IGNORECASE,
)


def parse_strategy_outcome(transcript: str) -> dict:
    """Extract a trialed strategy and its narrated outcome.

    Returns {"strategy_statement": str|None, "outcome": "worked"|"not_worked"|None}.
    Both are None when no "tried X" clause is present; outcome is None when a
    strategy was mentioned but the transcript never states how it went — the
    caller must not guess an outcome bucket in that case.
    """
    text = str(transcript or "").strip()
    match = STRATEGY_ATTEMPT_RE.search(text)
    if not match:
        return {"strategy_statement": None, "outcome": None}

    rest = match.group(1)
    outcome: Optional[str] = None
    if STRATEGY_NOT_WORKED_RE.search(rest):
        outcome = "not_worked"
    elif STRATEGY_WORKED_RE.search(rest):
        outcome = "worked"

    statement = STRATEGY_CLAUSE_SPLIT_RE.sub("", rest).strip(" .!?,;:")
    return {
        "strategy_statement": statement or None,
        "outcome": outcome if statement else None,
    }


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

    # Boost: if a known student name appears alongside any observation verb,
    # this is almost certainly an observation ("Nora used full sentences").
    # The base signals only catch pronouns + verbs, not Name + verbs.
    roster_names_lower = [
        str(s.get("display_name", "")).lower() for s in roster if s.get("display_name")
    ]
    has_roster_name = any(name and name in lowered for name in roster_names_lower)
    if has_roster_name and obs_score > 0:
        obs_score += 0.3
        obs_matched.append("roster_name_with_verb_boost")
    question_score, question_matched = _score(lowered, QUESTION_SIGNALS)

    # A leading question word means the transcript is asking ABOUT behavior,
    # not reporting it ("What did Marco read today?") — question wins even
    # when past-tense observation verbs are present.
    is_question_shaped = bool(re.match(QUESTION_SIGNALS[0][0], lowered)) or lowered.endswith("?")

    if obs_score >= WRITE_INTENT_THRESHOLD and not is_question_shaped:
        detection = detect_student_detailed(transcript, roster)
        has_generic_reference = bool(re.search(GENERIC_STUDENT_REFERENCE, lowered))
        # An ambiguous fuzzy hit IS a student reference — the teacher named
        # someone; we just can't pick between two candidates without asking.
        if (detection.student_id is None and not has_generic_reference
                and detection.match_quality != "ambiguous"):
            # Behavior verbs but no student at all — not enough to act on.
            return IntentClassification(
                intent="question",
                confidence=min(1.0, question_score),
                matched_signals=question_matched,
            )
        return IntentClassification(
            intent="observation",
            confidence=min(1.0, obs_score),
            student_id=detection.student_id,
            student_name=detection.display_name,
            needs_clarification=detection.student_id is None,
            observation_context=parse_observation_context(transcript),
            matched_signals=obs_matched,
            match_quality=detection.match_quality,
            matched_token=detection.matched_token,
            candidates=detection.candidates,
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
