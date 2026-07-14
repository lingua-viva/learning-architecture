"""
Content Differentiation Engine — Product B core

Teacher inputs an IB unit (subject, topic, ATL skills, duration, CEFR
band). This engine generates three tiered content packs — foundational,
on_track, extended — plus a teacher guide, using a deterministic,
rule-based Template & Rules Engine (no LLM call, no cache-miss fallback
to a cloud model). This matches content-differentiation.md's own
architecture ("Template & Rules Engine... Local Model Runtime used only
on cache miss") simplified for the Friday vertical slice: this build
ships the rule-based tier always, with no model-runtime fallback yet.

Schemas (LessonInput, tier structure) follow
architecture/content-differentiation.md Section 3, trimmed to what a
first pilot needs. `StudentLens` reuses the dict shape returned by
`student_lens.StudentLensStore.get_lens()` rather than re-declaring a
parallel type — RTI tier data flows from the same lens Product A writes.

RESEARCH (mandatory per build rules before writing any student-facing
content generation logic): ran
  mc research "Trauma-informed pedagogy for refugee students: what
  language patterns should be avoided in educational AI systems, and
  what frameworks exist for safe assessment?"
Findings (with citations, see BUILD_JOURNAL.md Turn 4) — avoid: vague or
threatening ambiguity, forced disclosure/personalization of the
student's own history, labeling/outing students as "refugee" or
"trauma survivor," pathologizing/deficit-focused/diagnostic language.
Favor: safety, transparency, choice (explicit opt-out / alternative-topic
options on any personal-reflection task), and affirming, strengths-based
framing. TRAUMA_SAFE_RULES below encodes these as generation-time checks,
not just documentation.

ADAPTATION, NOT GENERATION (re-ground audit, post-meeting fix): Still I
Rise teachers were explicit that this engine's real job is taking an
EXISTING IB module/document a teacher already has and adapting it to
three levels — not inventing new material from a topic string. Ran:
  mc research "How do teachers currently adapt IB unit materials for
  differentiated instruction? What does 'same concept, three levels'
  look like in practice for a mixed-ability IB MYP classroom?"
Finding: no IB-authored "three-level" template exists; the real practice
teachers report is holding the same key concept/statement of inquiry/
criteria constant across levels while varying text complexity, scaffolds,
and output demands. That is exactly what `_adapt_tier_from_source` below
does — same source material at every tier, varying only how much of it a
student reads, how it's chunked, and what scaffold/task wraps it.

`generate(lesson, source_chunks=...)` is the new adaptation path:
source_chunks come from `document_retrieval.DocumentRetriever` /
`document_store.DocumentStore` (this build's own governed-RAG stack,
built the same session before the meeting reframed its purpose) — i.e.
an existing ingested IB PDF/module, not a generated string. When
source_chunks is omitted, `generate()` is byte-for-byte the original
template path (`_generate_tier`) — every existing caller and test is
unaffected. `generate_from_documents()` is the convenience wrapper that
does retrieval + adaptation in one call, with graceful fallback to
template generation if nothing has been ingested yet (an empty document
store must never block a teacher from getting a pack).

Deterministic, no LLM call: adaptation is sentence-splitting, existing
`_simplify_sentence` reuse, and excerpt-length tiering — the same
no-hallucination-risk pattern already used everywhere else in this
codebase (teacher_guide.py, trend_analysis.py, weekly_recommendation.py).
Tier-assignment logic (`assign_tier_for_student`) and the trauma-safety
guardrails below are unchanged — audit found both sound and reusable.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional

CEFR_ORDER = ["A1", "A1+", "A2", "A2+", "B1", "B1+", "B2", "C1", "C2"]

TIERS = ("foundational", "on_track", "extended")

# Trauma-informed guardrails, grounded in Perplexity research (see module
# docstring + BUILD_JOURNAL.md Turn 4). Any generated task that invites
# personal reflection must carry an explicit alternative/opt-out; no
# generated text may use these labels or phrasings.
TRAUMA_UNSAFE_LABELS = (
    "refugee student", "refugee children", "trauma survivor",
    "traumatized", "displaced child", "your trauma", "what happened to you",
)
PERSONAL_REFLECTION_OPT_OUT = (
    "You may write about your own experience, or choose a fictional "
    "story or a general/news example instead — whichever feels right to you."
)

# Foundational-tier sentence-length ceiling, per content-differentiation.md
# Stage 2 Language Adaptation ("simplified syntax for A1/A2, < 10-word
# sentences").
FOUNDATIONAL_MAX_SENTENCE_WORDS = 10


class TraumaSafetyError(ValueError):
    """Raised if generated content violates a trauma-informed guardrail.
    This should never trigger from the templates below — it exists as a
    hard check so future template edits can't silently reintroduce
    unsafe language."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cache_key(lesson: "LessonInput") -> str:
    raw = "|".join(
        [
            lesson.subject,
            lesson.unit_title,
            lesson.topic,
            lesson.cefr_target,
            ",".join(sorted(lesson.atl_skills)),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _check_trauma_safety(text: str) -> None:
    lowered = text.lower()
    for label in TRAUMA_UNSAFE_LABELS:
        if label in lowered:
            raise TraumaSafetyError(f"Unsafe label detected in generated content: {label!r}")


@dataclass
class LessonInput:
    """
    Product B input schema. Mirrors content-differentiation.md
    Section 3.1 LessonInput, trimmed of fields the offline vertical
    slice doesn't need yet (id/created_at auto-generated).
    """

    ib_programme: str  # "MYP" | "DP" | "PYP"
    subject: str
    unit_title: str
    topic: str
    atl_skills: list[str]
    cefr_target: str  # CEFRBand, e.g. "B1"
    duration_minutes: int
    language_of_instruction: str = "en"
    created_by: str = ""
    created_at: str = field(default_factory=_now_iso)

    def validate(self) -> list[str]:
        errors = []
        if self.ib_programme not in ("MYP", "DP", "PYP"):
            errors.append("ib_programme must be one of MYP, DP, PYP")
        if not self.subject.strip():
            errors.append("subject is required")
        if not self.unit_title.strip():
            errors.append("unit_title is required")
        if not self.topic.strip():
            errors.append("topic is required")
        if self.cefr_target not in CEFR_ORDER:
            errors.append(f"cefr_target must be one of {CEFR_ORDER}")
        if self.duration_minutes <= 0:
            errors.append("duration_minutes must be positive")
        return errors


def _cefr_shift(band: str, steps: int) -> str:
    """Move a CEFR band up/down by `steps` positions, clamped to range."""
    idx = CEFR_ORDER.index(band) if band in CEFR_ORDER else CEFR_ORDER.index("B1")
    new_idx = max(0, min(len(CEFR_ORDER) - 1, idx + steps))
    return CEFR_ORDER[new_idx]


def _simplify_sentence(sentence: str, max_words: int) -> str:
    words = sentence.split()
    if len(words) <= max_words:
        return sentence
    return " ".join(words[:max_words]).rstrip(",.;:") + "."


def _extract_key_terms(topic: str, max_terms: int = 5) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z\-]+", topic)
    seen: list[str] = []
    for w in words:
        lw = w.lower()
        if lw in ("the", "and", "of", "a", "an", "to", "in", "for") or len(lw) < 4:
            continue
        if lw not in [s.lower() for s in seen]:
            seen.append(w)
    return seen[:max_terms]


def _split_sentences(text: str) -> list[str]:
    """Deterministic sentence splitter — good enough for excerpt-length
    tiering, no NLP dependency. Collapses whitespace/newlines first since
    parsed document text can carry mid-sentence line breaks."""
    collapsed = re.sub(r"\s+", " ", text or "").strip()
    if not collapsed:
        return []
    parts = re.split(r"(?<=[.!?])\s+", collapsed)
    return [p.strip() for p in parts if p.strip()]


def _generate_tier(
    tier: str, lesson: LessonInput, key_terms: list[str]
) -> dict:
    tier_cefr = {
        "foundational": _cefr_shift(lesson.cefr_target, -1),
        "on_track": lesson.cefr_target,
        "extended": _cefr_shift(lesson.cefr_target, +1),
    }[tier]

    objective_verb = {
        "foundational": "identify and describe",
        "on_track": "explain and analyze",
        "extended": "evaluate and construct an argument about",
    }[tier]
    learning_objective = f"Students will {objective_verb} {lesson.topic.lower()}."
    if tier == "foundational":
        learning_objective = _simplify_sentence(
            learning_objective, FOUNDATIONAL_MAX_SENTENCE_WORDS
        )

    vocabulary_list = [
        {
            "term": term,
            "tier_definition_style": (
                "one simple sentence, visual support recommended"
                if tier == "foundational"
                else "standard definition"
                if tier == "on_track"
                else "definition + example of use in argument"
            ),
        }
        for term in key_terms
    ]

    if tier == "foundational":
        tasks = [
            {
                "type": "guided_practice",
                "prompt": f"Look at the pictures and words about {lesson.topic.lower()}. "
                "Point to or say one word you know.",
                "chunk_minutes": min(10, lesson.duration_minutes),
                "opt_out_offered": False,
            },
            {
                "type": "comprehension_check",
                "prompt": "Choose the picture that matches the sentence.",
                "chunk_minutes": min(10, lesson.duration_minutes),
                "opt_out_offered": False,
            },
        ]
    elif tier == "on_track":
        tasks = [
            {
                "type": "guided_practice",
                "prompt": f"In pairs, discuss what you already know about {lesson.topic.lower()}.",
                "chunk_minutes": min(15, lesson.duration_minutes),
                "opt_out_offered": False,
            },
            {
                "type": "reflection",
                "prompt": f"Write 3-4 sentences connecting {lesson.topic.lower()} to a story, "
                "article, or example you know. " + PERSONAL_REFLECTION_OPT_OUT,
                "chunk_minutes": min(15, lesson.duration_minutes),
                "opt_out_offered": True,
            },
        ]
    else:  # extended
        tasks = [
            {
                "type": "open_inquiry",
                "prompt": f"Formulate a research question about {lesson.topic.lower()} "
                "and outline what evidence would answer it.",
                "chunk_minutes": min(20, lesson.duration_minutes),
                "opt_out_offered": False,
            },
            {
                "type": "extended_writing",
                "prompt": f"Write an argument essay about {lesson.topic.lower()}, using at "
                "least two pieces of evidence. " + PERSONAL_REFLECTION_OPT_OUT,
                "chunk_minutes": min(25, lesson.duration_minutes),
                "opt_out_offered": True,
            },
        ]

    for task in tasks:
        _check_trauma_safety(task["prompt"])
    _check_trauma_safety(learning_objective)

    return {
        "tier": tier,
        "cefr_target": tier_cefr,
        "learning_objective": learning_objective,
        "vocabulary_list": vocabulary_list,
        "tasks": tasks,
    }


def _adapt_tier_from_source(
    tier: str, lesson: LessonInput, combined_text: str, key_terms: list[str]
) -> dict:
    """
    Adapt EXISTING source material (already-ingested document text) to
    one tier, instead of generating a task from a hardcoded template.
    Same key concept/objective at every tier (source text is identical);
    what varies by tier is how much of it a student reads, how it's
    chunked, and the scaffold/task wrapped around it — matching the
    "same concept, three levels" pattern from the research call above.
    """
    tier_cefr = {
        "foundational": _cefr_shift(lesson.cefr_target, -1),
        "on_track": lesson.cefr_target,
        "extended": _cefr_shift(lesson.cefr_target, +1),
    }[tier]

    objective_verb = {
        "foundational": "identify and describe",
        "on_track": "explain and analyze",
        "extended": "evaluate and construct an argument about",
    }[tier]
    learning_objective = (
        f"Students will {objective_verb} {lesson.topic.lower()}, using the provided material."
    )
    if tier == "foundational":
        learning_objective = _simplify_sentence(
            learning_objective, FOUNDATIONAL_MAX_SENTENCE_WORDS
        )

    vocabulary_list = [
        {
            "term": term,
            "tier_definition_style": (
                "one simple sentence, visual support recommended"
                if tier == "foundational"
                else "standard definition"
                if tier == "on_track"
                else "definition + example of use in argument"
            ),
        }
        for term in key_terms
    ]

    sentences = _split_sentences(combined_text)
    focus_term = key_terms[0] if key_terms else lesson.topic.lower()

    if tier == "foundational":
        excerpt_sentences = sentences[:3]
        simplified = [
            _simplify_sentence(s, FOUNDATIONAL_MAX_SENTENCE_WORDS) for s in excerpt_sentences
        ]
        source_excerpt = " ".join(simplified)
        tasks = [
            {
                "type": "guided_reading",
                "prompt": f'Read this together: "{source_excerpt}" Point to or say one word you know.',
                "chunk_minutes": min(10, lesson.duration_minutes),
                "opt_out_offered": False,
            },
            {
                "type": "comprehension_check",
                "prompt": f"Which sentence tells you about {focus_term}? Point to it.",
                "chunk_minutes": min(10, lesson.duration_minutes),
                "opt_out_offered": False,
            },
        ]
    elif tier == "on_track":
        excerpt_sentences = sentences[:6]
        source_excerpt = " ".join(excerpt_sentences)
        tasks = [
            {
                "type": "guided_reading",
                "prompt": f'Read the following material and discuss with a partner: "{source_excerpt}"',
                "chunk_minutes": min(15, lesson.duration_minutes),
                "opt_out_offered": False,
            },
            {
                "type": "reflection",
                "prompt": "Write 3-4 sentences summarizing what you read, in your own words. "
                + PERSONAL_REFLECTION_OPT_OUT,
                "chunk_minutes": min(15, lesson.duration_minutes),
                "opt_out_offered": True,
            },
        ]
    else:  # extended
        source_excerpt = " ".join(sentences) if sentences else combined_text
        tasks = [
            {
                "type": "open_inquiry",
                "prompt": f'Read the full material below and formulate a research question that '
                f'goes beyond what it covers:\n\n"{source_excerpt}"',
                "chunk_minutes": min(20, lesson.duration_minutes),
                "opt_out_offered": False,
            },
            {
                "type": "extended_writing",
                "prompt": "Write an argument essay that evaluates the material above, using at "
                "least two pieces of evidence from it. " + PERSONAL_REFLECTION_OPT_OUT,
                "chunk_minutes": min(25, lesson.duration_minutes),
                "opt_out_offered": True,
            },
        ]

    for task in tasks:
        _check_trauma_safety(task["prompt"])
    _check_trauma_safety(learning_objective)

    return {
        "tier": tier,
        "cefr_target": tier_cefr,
        "learning_objective": learning_objective,
        "vocabulary_list": vocabulary_list,
        "tasks": tasks,
        "source_excerpt": source_excerpt,
    }


@dataclass
class ContentPack:
    pack_id: str
    lesson: dict
    generated_at: str
    content_version: str
    tiers: dict  # {"foundational": {...}, "on_track": {...}, "extended": {...}}
    source_mode: str = "generated"  # "generated" | "adapted"
    source_provenance: Optional[list[dict]] = None  # [{source_file, section, page_start, page_end}]

    def to_dict(self) -> dict:
        return asdict(self)


class ContentDifferentiator:
    """
    Generates 3-tier content packs from a validated LessonInput.
    Pure function of the input — no external calls, no randomness,
    same lesson always produces the same pack (cache-key stable, per
    content-differentiation.md's SHA256(subject|unit|topic|cefr|atl)
    cache key design).
    """

    CONTENT_VERSION = "0.1.0"

    def generate(
        self, lesson: LessonInput, source_chunks: Optional[list[dict]] = None
    ) -> ContentPack:
        """
        Generate a 3-tier ContentPack.

        source_chunks=None (default): the original template path — same
        behavior as before this fix, unchanged for every existing caller.

        source_chunks=[...]: adapt EXISTING material (chunks as returned
        by document_store.DocumentStore.search() / document_retrieval
        .DocumentRetriever.retrieve() — dicts with a "text" key, plus
        source_file/section/page_start/page_end for provenance) to three
        tiers instead of generating from a template. Falls back to the
        template path if source_chunks is an empty list or every chunk's
        text is blank — adaptation needs something to adapt.
        """
        errors = lesson.validate()
        if errors:
            raise ValueError(f"Invalid LessonInput: {errors}")

        key_terms = _extract_key_terms(lesson.topic)

        combined_text = ""
        if source_chunks:
            combined_text = "\n\n".join(
                c.get("text", "") for c in source_chunks if c.get("text")
            ).strip()

        if combined_text:
            tiers = {
                tier: _adapt_tier_from_source(tier, lesson, combined_text, key_terms)
                for tier in TIERS
            }
            source_mode = "adapted"
            source_provenance = [
                {
                    "source_file": c.get("source_file"),
                    "section": c.get("section"),
                    "page_start": c.get("page_start"),
                    "page_end": c.get("page_end"),
                }
                for c in source_chunks
            ]
        else:
            tiers = {tier: _generate_tier(tier, lesson, key_terms) for tier in TIERS}
            source_mode = "generated"
            source_provenance = None

        return ContentPack(
            pack_id=_cache_key(lesson),
            lesson=asdict(lesson),
            generated_at=_now_iso(),
            content_version=self.CONTENT_VERSION,
            tiers=tiers,
            source_mode=source_mode,
            source_provenance=source_provenance,
        )

    def generate_from_documents(
        self,
        lesson: LessonInput,
        retriever,
        domain: str,
        query: Optional[str] = None,
        k: int = 5,
    ) -> ContentPack:
        """
        The demo path: "adapt this existing module for my three groups."

        Retrieves matching chunks from an already-ingested document store
        via a DocumentRetriever (duck-typed — same pattern as
        Pipeline.document_retriever, no hard import of document_retrieval
        here) and adapts them. `domain` must match one of the retriever's
        configured ontology domains (e.g. "curriculum") or retrieval
        returns []. Falls back to template generation
        (self.generate(lesson)) if nothing was retrieved — an empty or
        not-yet-populated document store must never block a teacher from
        getting a pack.
        """
        search_query = query or lesson.topic
        chunks = retriever.retrieve(search_query, domain=domain, k=k)
        return self.generate(lesson, source_chunks=chunks or None)

    def assign_tier_for_student(self, student_lens: dict) -> str:
        """
        Map a student's lens (as returned by
        student_lens.StudentLensStore.get_lens()) to a content tier.
        RTI tier is the primary signal per rti-tiers.md (RTI tiers are
        the intervention-intensity axis; CEFR is the parallel language
        spine that can pull a student up/down within that).
        """
        rti_tier = student_lens.get("rti_current_tier", 1)
        cefr_snapshot = student_lens.get("cefr_snapshot", {})
        levels = [v for v in cefr_snapshot.values() if v]
        weakest = min(
            levels, key=lambda lvl: CEFR_ORDER.index(lvl) if lvl in CEFR_ORDER else 0
        ) if levels else None

        if rti_tier == 3:
            return "foundational"
        if rti_tier == 2:
            # Tier 2 students get foundational unless CEFR evidence shows
            # they're keeping pace (B1+), in which case on_track.
            if weakest and CEFR_ORDER.index(weakest) >= CEFR_ORDER.index("B1"):
                return "on_track"
            return "foundational"
        # RTI tier 1 (universal): CEFR decides between on_track / extended
        if weakest and CEFR_ORDER.index(weakest) >= CEFR_ORDER.index("B2"):
            return "extended"
        return "on_track"

    def assign_packs_for_roster(
        self, pack: ContentPack, roster: list[dict]
    ) -> dict[str, str]:
        """Given a content pack and a roster of student lens dicts,
        return {student_id: tier}."""
        return {
            student["student_id"]: self.assign_tier_for_student(student)
            for student in roster
        }
