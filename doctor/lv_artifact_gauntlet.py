#!/usr/bin/env python3
"""Lingua Viva publication/accountability checker."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = [
    "README.md",
    "Manuale_Italiano_Laboratorio_Linguistico_G1-G5.docx",
    "dev/specs/LV_PUBLICATION_READINESS_AUDIT_2026-07-16.md",
    "artifacts/inventory.yaml",
    "claims/evidence_register.yaml",
    "governance/publication_safety.yaml",
    "curriculum/lingua_viva_matrix.yaml",
    "dev/lv_revision_log.ndjson",
    "dev/lv_deferred_candidates.yaml",
    "references/CEFR_Young_Learners.pdf",
    "references/CEFR_can_do_lists.pdf",
    "references/Criteri_Fondanti_Curricolo_Italiano_K-5.pages",
    "references/Criteri_Fondanti_Curricolo_Italiano_K-5.pdf",
    "references/Criteri_Fondanti_Curricolo_Italiano_K-5_v2.pdf",
    "references/D.M.211-2025-GU-26012026-Nuove-Indicazioni-nazionali.pdf",
]
REQUIRED_CLAIMS = {
    "lv-claim-four-framework-integration",
    "lv-claim-cefr-a1-b1-progression",
    "lv-claim-transferability",
    "lv-claim-global-uniqueness",
    "lv-claim-editorial-publication",
    "lv-claim-measurable-outcomes",
    "lv-claim-three-year-timeline",
    "lv-claim-50-50-model",
    "lv-claim-tool-surfaces",
}
REQUIRED_REVISION_LOG_KEYS = {
    "timestamp",
    "revision_id",
    "artifact_id",
    "artifact_path",
    "defect_class",
    "origin",
    "instrument_that_found_it",
    "instrument_touched",
    "independent_cross_check",
    "decision",
    "proof",
    "reviewer",
    "teacher_contribution_involved",
    "privacy_review",
}
FORBIDDEN_README_PATTERNS = [
    r"unique globally",
    r"no existing curriculum integrates",
    r"students achieve CEFR",
    r"students reach CEFR",
    r"validated outcomes",
    r"publication is guaranteed",
]


def load_yaml(rel: str) -> dict:
    with (ROOT / rel).open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{rel} must be a YAML mapping")
    return data


def check_required_files(errors: list[str]) -> None:
    for rel in REQUIRED_FILES:
        if not (ROOT / rel).exists():
            errors.append(f"missing required file: {rel}")


def check_inventory(errors: list[str]) -> None:
    inventory = load_yaml("artifacts/inventory.yaml")
    artifacts = inventory.get("artifacts", [])
    ids = {item.get("id") for item in artifacts if isinstance(item, dict)}
    required = {
        "lv-artifact-readme",
        "lv-artifact-manual-docx",
        "lv-ref-cefr-young-learners",
        "lv-ref-cefr-can-do",
        "lv-ref-criteri-pages",
        "lv-ref-criteri-pdf",
        "lv-ref-criteri-v2-pdf",
        "lv-ref-indicazioni",
        "lv-artifact-palette-imported",
        "lv-artifact-import-palette",
    }
    missing = sorted(required - ids)
    if missing:
        errors.append(f"inventory missing artifact ids: {', '.join(missing)}")
    source = inventory.get("source_of_truth", {})
    if source.get("authoritative_current_draft") != "../Manuale_Italiano_Laboratorio_Linguistico_G1-G5.docx":
        errors.append("inventory must keep .docx as authoritative current draft")


def check_claims(errors: list[str]) -> None:
    claims = load_yaml("claims/evidence_register.yaml").get("claims", [])
    by_id = {claim.get("id"): claim for claim in claims if isinstance(claim, dict)}
    missing = sorted(REQUIRED_CLAIMS - set(by_id))
    if missing:
        errors.append(f"evidence register missing claim ids: {', '.join(missing)}")
    if by_id.get("lv-claim-global-uniqueness", {}).get("classification") != "unsupported":
        errors.append("global uniqueness claim must remain unsupported until external evidence is added")
    cefr_wording = by_id.get("lv-claim-cefr-a1-b1-progression", {}).get("publication_safe_wording", "")
    if "designed to target" not in cefr_wording:
        errors.append("CEFR claim must use designed-to target wording")


def check_governance(errors: list[str]) -> None:
    rules = load_yaml("governance/publication_safety.yaml").get("privacy_rules", {})
    if "No raw student work" not in rules.get("student_data", ""):
        errors.append("student data boundary missing")
    if "No public Lingua Viva artifact may attribute" not in rules.get("ai_attribution", ""):
        errors.append("AI attribution boundary missing")


def check_matrix(errors: list[str]) -> None:
    matrix = load_yaml("curriculum/lingua_viva_matrix.yaml")
    if matrix.get("authority") != "non_authoritative":
        errors.append("matrix must remain non-authoritative until promoted")
    if matrix.get("promotion_status", {}).get("current_decision") != "Do not promote yet.":
        errors.append("matrix must have explicit non-promotion decision")
    grades = {row.get("grade") for row in matrix.get("grade_bands", []) if isinstance(row, dict)}
    if grades != {"G1", "G2", "G3", "G4", "G5"}:
        errors.append("matrix must include G1-G5 grade bands")


def check_readme(errors: list[str]) -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for pattern in FORBIDDEN_README_PATTERNS:
        if re.search(pattern, readme, flags=re.IGNORECASE):
            errors.append(f"README contains forbidden pattern: {pattern}")
    if "designed to integrate" not in readme:
        errors.append("README must use designed-to integration wording")
    if "Assessment coherence" not in readme:
        errors.append("README must use assessment coherence wording")


def check_revision_log(errors: list[str]) -> None:
    lines = (ROOT / "dev/lv_revision_log.ndjson").read_text(encoding="utf-8").splitlines()
    if not lines:
        errors.append("revision log must not be empty")
    for idx, line in enumerate(lines, 1):
        if not line.strip():
            continue
        entry = json.loads(line)
        missing = sorted(REQUIRED_REVISION_LOG_KEYS - set(entry))
        if missing:
            errors.append(f"revision log line {idx} missing keys: {', '.join(missing)}")
        if not isinstance(entry.get("instrument_touched"), bool):
            errors.append(f"revision log line {idx} instrument_touched must be boolean")
        if not isinstance(entry.get("teacher_contribution_involved"), bool):
            errors.append(f"revision log line {idx} teacher_contribution_involved must be boolean")


def main() -> int:
    errors: list[str] = []
    for check in (check_required_files, check_inventory, check_claims, check_governance, check_matrix, check_readme, check_revision_log):
        try:
            check(errors)
        except Exception as exc:
            errors.append(f"{check.__name__} crashed: {exc}")
    if errors:
        print("Lingua Viva artifact gauntlet: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Lingua Viva artifact gauntlet: PASS")
    print(f"Checked {len(REQUIRED_FILES)} files and 7 gates.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
