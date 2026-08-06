"""
School Ethos Taxonomy — configurable traits/characteristics layer

A school's ethos is the set of characteristics and traits it deliberately
develops in students through lessons and projects (e.g. core values like
"Ambition, Bravery, Care", or an IB-style learner profile). Teachers record
feedback against these traits on student profiles and use the accumulated
evidence in student reports.

Design: ethos-as-data, lens-as-mechanism.
  - This module is the GENERIC mechanism and ships in the public repo.
  - The school-specific trait content is LOCAL DATA, loaded from
    ~/.lingua-viva/ethos.yaml (override: LV_ETHOS_PATH). Per
    publication-policy.md, proprietary school documents and school-specific
    ethos text must never be committed to this repository.
  - A built-in seed taxonomy (three generic core values + ten learner
    attributes paraphrased in our own words from the widely-published IB
    learner profile) makes the mechanism work out of the box; a school
    replaces it by writing its own ethos.yaml.

Storage seam mirrors student_lens.default_db_path(): env override first,
then lv_home(). Never resolve paths relative to __file__ — frozen
(PyInstaller) builds relocate __file__ into a bundle temp dir.

Ethos evidence itself is stored on the student lens (see student_lens.py
ethos_profile, schema v2.1) — this module only defines and validates the
trait taxonomy that evidence is keyed against.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

ETHOS_SCHEMA_VERSION = 1

VALID_TRAIT_GROUPS = ("value", "learner_attribute")

_TRAIT_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

MAX_TRAITS = 40
MAX_LABEL_LEN = 100
MAX_DESCRIPTOR_LEN = 500
MAX_KEYWORDS_PER_TRAIT = 12
MAX_KEYWORD_LEN = 100
MAX_ETHOS_FILE_BYTES = 1_000_000  # a taxonomy is ~KBs; 1MB+ is a wrong file


class EthosValidationError(Exception):
    """Raised when an ethos taxonomy fails structural validation."""


def default_ethos_path() -> Path:
    override = os.environ.get("LV_ETHOS_PATH")
    if override:
        return Path(override)
    from src.lingua_viva.config import lv_home
    return lv_home() / "ethos.yaml"


def ethos_seed() -> dict:
    """Built-in Still I Rise starter taxonomy.

    The active school can still replace this by writing its own
    ethos.yaml. This seed keeps a fresh local install aligned with the
    current Mission Canvas / Still I Rise student-profile language.
    """
    return {
        "schema_version": ETHOS_SCHEMA_VERSION,
        "ethos_name": "still_i_rise_seed",
        "source": "built_in_still_i_rise_seed_2026_08_06",
        "traits": [
            {
                "id": "self_worth",
                "label": "Self-Worth",
                "group": "value",
                "descriptor": (
                    "Recognizes personal value, voice, and belonging, and can "
                    "name strengths with growing confidence."
                ),
                "signal_keywords": ["self-worth", "self worth", "belonging", "confidence", "voice"],
            },
            {
                "id": "self_discipline",
                "label": "Self-Discipline",
                "group": "value",
                "descriptor": (
                    "Builds habits of focus, follow-through, and responsible "
                    "choice even when work is difficult."
                ),
                "signal_keywords": ["self-discipline", "self discipline", "follow-through", "focus", "responsible choice"],
            },
            {
                "id": "critical_thinking",
                "label": "Critical Thinking",
                "group": "learner_attribute",
                "descriptor": (
                    "Questions, reasons, evaluates evidence, and uses judgment "
                    "to solve problems."
                ),
                "signal_keywords": ["critical thinking", "reasoned", "evidence", "problem solving", "judgment"],
            },
            {
                "id": "emotional_intelligence",
                "label": "Emotional Intelligence",
                "group": "learner_attribute",
                "descriptor": (
                    "Recognizes emotions, regulates responses, and responds to "
                    "others with empathy."
                ),
                "signal_keywords": ["emotional intelligence", "empathy", "self-regulation", "regulated", "recognized emotions"],
            },
            {
                "id": "self_organization",
                "label": "Self-Organization",
                "group": "learner_attribute",
                "descriptor": (
                    "Plans, sequences, manages materials and time, and follows "
                    "through on learning routines."
                ),
                "signal_keywords": ["self-organization", "self organization", "organized", "planned", "time management"],
            },
            {
                "id": "grit",
                "label": "Grit",
                "group": "learner_attribute",
                "descriptor": (
                    "Persists through setbacks, keeps trying, and learns from "
                    "mistakes."
                ),
                "signal_keywords": ["grit", "persisted", "kept trying", "resilience", "setback"],
            },
            {
                "id": "social_intelligence",
                "label": "Social Intelligence",
                "group": "learner_attribute",
                "descriptor": (
                    "Reads social situations, collaborates constructively, and "
                    "builds respectful relationships."
                ),
                "signal_keywords": ["social intelligence", "collaborated", "peer", "relationship", "group work"],
            },
            {
                "id": "entrepreneurship",
                "label": "Entrepreneurship",
                "group": "learner_attribute",
                "descriptor": (
                    "Shows initiative, identifies opportunities, creates value, "
                    "and acts resourcefully."
                ),
                "signal_keywords": ["entrepreneurship", "initiative", "resourceful", "created value", "opportunity"],
            },
            {
                "id": "integrity",
                "label": "Integrity",
                "group": "learner_attribute",
                "descriptor": (
                    "Acts honestly, keeps commitments, takes responsibility, "
                    "and does what is right."
                ),
                "signal_keywords": ["integrity", "honest", "honesty", "fair", "responsibility"],
            },
        ],
    }


def validate_ethos(data: dict) -> None:
    """Validate an ethos taxonomy dict. Raises EthosValidationError."""
    if not isinstance(data, dict):
        raise EthosValidationError("ethos root must be a mapping")

    schema_version = data.get("schema_version")
    if schema_version != ETHOS_SCHEMA_VERSION:
        raise EthosValidationError(
            f"unsupported ethos schema_version {schema_version!r}; "
            f"expected {ETHOS_SCHEMA_VERSION}"
        )

    ethos_name = data.get("ethos_name")
    if not (isinstance(ethos_name, str) and ethos_name.strip()):
        raise EthosValidationError("ethos_name must be a non-empty string")

    traits = data.get("traits")
    if not (isinstance(traits, list) and traits):
        raise EthosValidationError("traits must be a non-empty list")
    if len(traits) > MAX_TRAITS:
        raise EthosValidationError(f"too many traits ({len(traits)} > {MAX_TRAITS})")

    seen_ids: set[str] = set()
    for i, trait in enumerate(traits):
        if not isinstance(trait, dict):
            raise EthosValidationError(f"traits[{i}] must be a mapping")
        trait_id = trait.get("id")
        if not (isinstance(trait_id, str) and _TRAIT_ID_RE.match(trait_id)):
            raise EthosValidationError(
                f"traits[{i}].id {trait_id!r} must match {_TRAIT_ID_RE.pattern}"
            )
        if trait_id in seen_ids:
            raise EthosValidationError(f"duplicate trait id '{trait_id}'")
        seen_ids.add(trait_id)

        label = trait.get("label")
        if not (isinstance(label, str) and label.strip() and len(label) <= MAX_LABEL_LEN):
            raise EthosValidationError(
                f"trait '{trait_id}' label must be a non-empty string "
                f"<= {MAX_LABEL_LEN} chars"
            )

        descriptor = trait.get("descriptor")
        if not (
            isinstance(descriptor, str)
            and descriptor.strip()
            and len(descriptor) <= MAX_DESCRIPTOR_LEN
        ):
            raise EthosValidationError(
                f"trait '{trait_id}' descriptor must be a non-empty string "
                f"<= {MAX_DESCRIPTOR_LEN} chars"
            )

        group = trait.get("group")
        if group not in VALID_TRAIT_GROUPS:
            raise EthosValidationError(
                f"trait '{trait_id}' group {group!r} must be one of "
                f"{VALID_TRAIT_GROUPS}"
            )

        keywords = trait.get("signal_keywords", [])
        if keywords is None:
            keywords = []
        if not isinstance(keywords, list) or not all(
            isinstance(kw, str) and kw.strip() and len(kw) <= MAX_KEYWORD_LEN
            for kw in keywords
        ):
            raise EthosValidationError(
                f"trait '{trait_id}' signal_keywords must be a list of "
                f"non-empty strings <= {MAX_KEYWORD_LEN} chars"
            )
        if len(keywords) > MAX_KEYWORDS_PER_TRAIT:
            raise EthosValidationError(
                f"trait '{trait_id}' has too many signal_keywords "
                f"({len(keywords)} > {MAX_KEYWORDS_PER_TRAIT})"
            )


def load_ethos(path: Path | None = None) -> dict:
    """Load the active ethos taxonomy.

    Missing file → built-in seed (mechanism works out of the box).
    Present-but-invalid file → EthosValidationError (fail loudly: a school
    that authored an ethos must never have it silently replaced by the
    seed — reports would carry the wrong traits).
    """
    if path is None:
        path = default_ethos_path()
    if not path.exists():
        return ethos_seed()
    size = path.stat().st_size
    if size > MAX_ETHOS_FILE_BYTES:
        raise EthosValidationError(
            f"ethos file {path} is {size} bytes "
            f"(> {MAX_ETHOS_FILE_BYTES}) — refusing to parse; "
            "a taxonomy file should be a few kilobytes"
        )
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise EthosValidationError(f"ethos file {path} is not valid YAML: {exc}") from exc
    if data is None:
        raise EthosValidationError(f"ethos file {path} is empty")
    validate_ethos(data)
    return data


def save_ethos(data: dict, path: Path | None = None) -> Path:
    """Validate and atomically write an ethos taxonomy to the local
    config path. Atomic (temp file + rename) so a crash mid-write can
    never leave a half-written taxonomy — load_ethos fails loudly on an
    invalid file rather than falling back to the seed, so a torn write
    would take the ethos layer down until manually repaired."""
    validate_ethos(data)
    if path is None:
        path = default_ethos_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
    os.replace(tmp_path, path)
    return path


def trait_ids(ethos: dict) -> tuple[str, ...]:
    return tuple(trait["id"] for trait in ethos.get("traits", []))


def get_trait(ethos: dict, trait_id: str) -> dict | None:
    for trait in ethos.get("traits", []):
        if trait.get("id") == trait_id:
            return trait
    return None


def ethos_signal_keywords(ethos: dict) -> dict[str, list[str]]:
    """Map trait_id -> lowercase signal keywords (label always included)."""
    result: dict[str, list[str]] = {}
    for trait in ethos.get("traits", []):
        keywords = [trait["label"].lower()]
        for kw in trait.get("signal_keywords") or []:
            lowered = kw.lower()
            if lowered not in keywords:
                keywords.append(lowered)
        result[trait["id"]] = keywords
    return result


def match_traits(text: str, ethos: dict) -> list[str]:
    """Return trait ids whose signal keywords appear in text as whole
    words/phrases (case-insensitive, word-boundary anchored — plain
    substring matching produced measured false positives: 'scared'
    contains 'care', 'goalkeeper' contains 'goal'). Suggestion signal
    only — a match is always model_suggested/teacher-reviewable, never
    auto-confirmed evidence."""
    lowered = text.lower()
    matched = []
    for trait_id, keywords in ethos_signal_keywords(ethos).items():
        for kw in keywords:
            if re.search(r"(?<!\w)" + re.escape(kw) + r"(?!\w)", lowered):
                matched.append(trait_id)
                break
    return matched


def match_trait_terms(text: str, ethos: dict) -> list[dict]:
    """Like match_traits, but returns which keyword hit:
    [{"trait_id": ..., "matched_term": ..., "label": ...}], first matching
    keyword per trait. Same word-boundary matching rules — suggestion
    signal only, always teacher-reviewable, never auto-confirmed."""
    lowered = text.lower()
    matches = []
    for trait_id, keywords in ethos_signal_keywords(ethos).items():
        for kw in keywords:
            if re.search(r"(?<!\w)" + re.escape(kw) + r"(?!\w)", lowered):
                trait = get_trait(ethos, trait_id) or {}
                matches.append(
                    {
                        "trait_id": trait_id,
                        "matched_term": kw,
                        "label": trait.get("label", trait_id),
                    }
                )
                break
    return matches


def format_traits_for_prompt(ethos: dict) -> str:
    """Render the taxonomy as a compact block for a lens system prompt."""
    lines = [f"School ethos taxonomy ({ethos.get('ethos_name', 'unnamed')}):"]
    for group, heading in (
        ("value", "Core values"),
        ("learner_attribute", "Learner attributes"),
    ):
        group_traits = [t for t in ethos.get("traits", []) if t.get("group") == group]
        if not group_traits:
            continue
        lines.append(f"{heading}:")
        for trait in group_traits:
            lines.append(f"  - {trait['label']} ({trait['id']}): {trait['descriptor']}")
    return "\n".join(lines)
