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
    """Built-in generic seed taxonomy.

    Three core values (generic ambition/bravery/care triad) plus ten
    learner attributes. Descriptors are original paraphrases written for
    this project — not quoted from any school's or organization's
    published materials.
    """
    return {
        "schema_version": ETHOS_SCHEMA_VERSION,
        "ethos_name": "seed",
        "source": "built_in_seed",
        "traits": [
            {
                "id": "ambition",
                "label": "Ambition",
                "group": "value",
                "descriptor": (
                    "Sets high personal goals and keeps working toward them, "
                    "even when progress is slow."
                ),
                "signal_keywords": ["ambition", "ambitious", "goal", "aims high"],
            },
            {
                "id": "bravery",
                "label": "Bravery",
                "group": "value",
                "descriptor": (
                    "Faces difficulty with courage — willing to try, to fail "
                    "in front of others, and to try again."
                ),
                "signal_keywords": ["brave", "bravery", "courage", "courageous"],
            },
            {
                "id": "care",
                "label": "Care",
                "group": "value",
                "descriptor": (
                    "Looks after themselves, other people, and the shared "
                    "community with kindness and respect."
                ),
                "signal_keywords": ["care", "caring", "kindness", "kind to"],
            },
            {
                "id": "inquirer",
                "label": "Inquirer",
                "group": "learner_attribute",
                "descriptor": (
                    "Shows curiosity — asks questions, investigates "
                    "independently, and enjoys the process of finding out."
                ),
                "signal_keywords": ["curious", "curiosity", "inquiry", "asks questions", "asked questions"],
            },
            {
                "id": "knowledgeable",
                "label": "Knowledgeable",
                "group": "learner_attribute",
                "descriptor": (
                    "Builds understanding across subjects and connects ideas "
                    "to issues in the wider world."
                ),
                "signal_keywords": ["knowledgeable", "connects ideas", "background knowledge"],
            },
            {
                "id": "thinker",
                "label": "Thinker",
                "group": "learner_attribute",
                "descriptor": (
                    "Reasons through problems, weighs options, and makes "
                    "thoughtful, defensible decisions."
                ),
                "signal_keywords": ["critical thinking", "reasoned", "problem solving"],
            },
            {
                "id": "communicator",
                "label": "Communicator",
                "group": "learner_attribute",
                "descriptor": (
                    "Expresses ideas clearly in more than one language or "
                    "mode, and listens carefully to others."
                ),
                "signal_keywords": ["communicator", "expresses", "listens", "presentation"],
            },
            {
                "id": "principled",
                "label": "Principled",
                "group": "learner_attribute",
                "descriptor": (
                    "Acts with honesty and fairness, and takes responsibility "
                    "for their own actions and their consequences."
                ),
                "signal_keywords": ["principled", "honest", "honesty", "fair", "integrity"],
            },
            {
                "id": "open_minded",
                "label": "Open-minded",
                "group": "learner_attribute",
                "descriptor": (
                    "Values their own culture and history while genuinely "
                    "considering other perspectives and traditions."
                ),
                "signal_keywords": ["open-minded", "open minded", "perspective", "other cultures"],
            },
            {
                "id": "caring",
                "label": "Caring",
                "group": "learner_attribute",
                "descriptor": (
                    "Shows empathy and compassion, and acts to make a "
                    "positive difference for others."
                ),
                "signal_keywords": ["empathy", "compassion", "helped a classmate"],
            },
            {
                "id": "risk_taker",
                "label": "Risk-taker",
                "group": "learner_attribute",
                "descriptor": (
                    "Approaches unfamiliar situations with resolve and tries "
                    "new strategies without fear of being wrong."
                ),
                "signal_keywords": ["risk-taker", "risk taker", "tried something new", "stepped up"],
            },
            {
                "id": "balanced",
                "label": "Balanced",
                "group": "learner_attribute",
                "descriptor": (
                    "Attends to intellectual, physical, and emotional "
                    "well-being — their own and other people's."
                ),
                "signal_keywords": ["balanced", "well-being", "wellbeing", "self-care"],
            },
            {
                "id": "reflective",
                "label": "Reflective",
                "group": "learner_attribute",
                "descriptor": (
                    "Thinks about their own learning and experience, and can "
                    "name strengths and areas to grow."
                ),
                "signal_keywords": ["reflective", "reflection", "self-assessed", "growth area"],
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
