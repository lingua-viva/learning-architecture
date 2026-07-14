"""
Assessment Generator — "Create an assessment for this unit."

Research (mandatory, ran before writing any IB-branded assessment logic):
  mc research "IB MYP assessment criteria: what are the four criteria per
  subject, how are achievement levels 1-8 structured, and how do teachers
  use criterion-referenced assessment in practice?"

Finding, and the honesty boundary it sets for this module: MYP subjects
are assessed against **four criteria per subject**, scored on
**achievement levels 0-8** (not 1-8 — 0 is a real, used level meaning
"does not meet even the lowest descriptor"), and assessment is
**criterion-referenced** (students judged against fixed descriptors, not
ranked against each other). But the *specific* criterion names and
strand wording differ by subject group (Language & Literature, Sciences,
Mathematics, Individuals & Societies, Arts, Design, PHE, Language
Acquisition), and no single open/verifiable source lists all of them —
that detail lives inside subscription-only IB subject guides this build
has no access to.

Because of that gap, this module implements the **structural mechanism**
IB MYP assessment actually uses (four criteria, 0-8 achievement bands,
criterion-referenced descriptors, same criteria applied across all
differentiation tiers) using GENERIC criterion labels (Knowing &
Understanding / Investigating / Communicating / Reflecting) rather than
claiming to reproduce a specific subject's official criterion wording.
The `ib_compliance_note` field on every generated `Assessment` says this
explicitly, so a teacher using this for a real IB report card knows to
swap in their subject's actual MYP guide criterion names before
submitting anything official. Presenting unverified subject-specific criteria
as if they were IB's real wording would violate the publication policy's
"claims must be traceable to evidence" rule — this module chooses
honesty over the appearance of completeness.

Criterion-referenced, not tier-referenced: all three tiers are assessed
against the SAME four criteria and the SAME 0-8 scale — differentiation
happens in task scaffolding and target achievement band, never in a
separate rubric per tier. That directly reflects "students are judged
against defined descriptors, not against each other" from the research.

Reuses Product B's tier tasks rather than inventing new prompts: each
tier's assessment task is literally the assessable task already produced
by `content_differentiator.py` (the `reflection`/`extended_writing`/
`comprehension_check` task, already trauma-safety-checked and already
carrying the personal-reflection opt-out where relevant) — zero-sum
complexity: this module adds grading structure around existing content
instead of generating a second, parallel task.

Adapted-content awareness (re-ground audit fix): `ContentPack.tiers[tier]
["tasks"]` has the identical shape whether the pack came from the
template path or the new adaptation path
(`content_differentiator._adapt_tier_from_source`), so `generate()`
needed no structural change to keep working. What DOES change is the
compliance disclosure: when `pack.source_mode == "adapted"`, the
assessable task is grounded in real ingested source material (not a
synthetic template), so the compliance note says that explicitly and the
Assessment carries `source_provenance` (source_file/section/page) through
from the pack — traceable, citable, matches the "safe way to share"
governance framing rather than an opaque AI output. The GENERIC
criteria/band-descriptor limitation from the original research is
unchanged either way — that gap is about IB's subject-specific rubric
wording, not about where the task content came from.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from src.education.content_differentiator import ContentPack, TIERS, _check_trauma_safety

GENERIC_CRITERIA = {
    "A": "Knowing and Understanding",
    "B": "Investigating / Inquiring",
    "C": "Communicating / Producing",
    "D": "Reflecting / Applying",
}

# Generic, subject-agnostic quality descriptors per achievement band.
# These describe the *shape* of response quality at each band (MYP's own
# general mechanism), not subject-specific content standards.
BAND_DESCRIPTORS = {
    "0": "Does not yet reach the standard described by band 1-2.",
    "1-2": "Limited: attempts the task with significant support; response is partial or unclear.",
    "3-4": "Adequate: completes the task with some support; response shows basic understanding.",
    "5-6": "Substantial: completes the task independently; response shows clear understanding with some depth.",
    "7-8": "Excellent: completes the task independently with sophistication; response shows deep understanding and original thinking.",
}

# Differentiation happens here: which band a tier's task is realistically
# scaffolded to reach, not a lower expectation on the same 0-8 scale.
TIER_TARGET_BAND = {
    "foundational": "1-2",
    "on_track": "3-4",
    "extended": "5-6",
}

IB_COMPLIANCE_NOTE = (
    "Criteria labels and band descriptors here are a GENERIC structural "
    "pattern (four criteria, 0-8 achievement levels, criterion-referenced "
    "descriptors) verified against IB MYP assessment mechanics via "
    "Perplexity research. They are NOT verified subject-specific IB "
    "criterion wording — that requires the official MYP subject guide for "
    "this subject, which this system does not have access to. Replace "
    "criterion labels and descriptors with your subject's official MYP "
    "guide language before using this for a real report card."
)

IB_COMPLIANCE_NOTE_ADAPTED = (
    "Criteria labels and band descriptors here are a GENERIC structural "
    "pattern (four criteria, 0-8 achievement levels, criterion-referenced "
    "descriptors) verified against IB MYP assessment mechanics via "
    "Perplexity research — NOT verified subject-specific IB criterion "
    "wording. The assessable task itself, however, is adapted from your "
    "own ingested source material (see Source Material below), not "
    "synthetically generated. Replace criterion labels and descriptors "
    "with your subject's official MYP guide language before using this "
    "for a real report card."
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TierAssessment:
    tier: str
    task_prompt: str
    task_type: str
    target_band: str
    opt_out_offered: bool


@dataclass
class Assessment:
    assessment_id: str
    pack_id: str
    lesson_title: str
    generated_at: str
    criteria: dict  # code -> label
    band_descriptors: dict
    tier_assessments: dict  # tier -> TierAssessment
    ib_compliance_note: str = IB_COMPLIANCE_NOTE
    source_provenance: Optional[list[dict]] = None

    def to_markdown(self) -> str:
        lines = [
            f"# Assessment: {self.lesson_title}",
            "",
            f"Content pack: `{self.pack_id}`",
            "",
            "## Criteria (generic structure — see compliance note)",
            "",
        ]
        for code, label in self.criteria.items():
            lines.append(f"- **Criterion {code}**: {label}")
        lines.append("")
        lines.append("## Achievement Bands (0-8 scale)")
        lines.append("")
        for band, descriptor in self.band_descriptors.items():
            lines.append(f"- **{band}**: {descriptor}")
        lines.append("")
        lines.append("## Differentiated Tasks")
        lines.append("")
        for tier in TIERS:
            ta = self.tier_assessments[tier]
            lines.append(f"### {tier.replace('_', ' ').title()} (target band {ta.target_band})")
            lines.append(ta.task_prompt)
            lines.append("")
        if self.source_provenance:
            lines.append("## Source Material")
            lines.append("")
            for prov in self.source_provenance:
                page_start = prov.get("page_start", "?")
                page_end = prov.get("page_end", page_start)
                loc = f"{prov.get('source_file', '?')} p.{page_start}"
                if page_end != page_start:
                    loc += f"-{page_end}"
                lines.append(f"- {loc} — {prov.get('section', '?')}")
            lines.append("")
        lines.append("---")
        lines.append("")
        lines.append(f"_{self.ib_compliance_note}_")
        return "\n".join(lines)


class AssessmentGenerator:
    def generate(self, pack: ContentPack) -> Assessment:
        tier_assessments = {}
        for tier in TIERS:
            tier_data = pack.tiers[tier]
            task = tier_data["tasks"][-1]  # the assessable task per Turn 4's design
            _check_trauma_safety(task["prompt"])
            tier_assessments[tier] = TierAssessment(
                tier=tier,
                task_prompt=task["prompt"],
                task_type=task["type"],
                target_band=TIER_TARGET_BAND[tier],
                opt_out_offered=task.get("opt_out_offered", False),
            )

        is_adapted = getattr(pack, "source_mode", "generated") == "adapted"

        return Assessment(
            assessment_id=f"assess-{pack.pack_id}",
            pack_id=pack.pack_id,
            lesson_title=pack.lesson.get("unit_title", pack.lesson.get("topic", "")),
            generated_at=_now_iso(),
            criteria=dict(GENERIC_CRITERIA),
            band_descriptors=dict(BAND_DESCRIPTORS),
            tier_assessments=tier_assessments,
            ib_compliance_note=IB_COMPLIANCE_NOTE_ADAPTED if is_adapted else IB_COMPLIANCE_NOTE,
            source_provenance=pack.source_provenance if is_adapted else None,
        )
