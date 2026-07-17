from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]


class PublicationService:
    """Read governance/publication_safety.yaml and claims/evidence_register.yaml."""

    def __init__(self, root: Path | str = ROOT):
        self.root = Path(root)

    def get_status(self) -> dict[str, Any]:
        governance = self._load_yaml("governance/publication_safety.yaml")
        evidence = self._load_yaml("claims/evidence_register.yaml")
        claims = evidence.get("claims", [])
        safe: list[dict[str, Any]] = []
        needs_evidence: list[dict[str, Any]] = []
        blocked: list[dict[str, Any]] = []

        for claim in claims:
            if not isinstance(claim, dict):
                continue
            classification = str(claim.get("classification", ""))
            maturity = str(claim.get("maturity_label", ""))
            record = {
                "id": claim.get("id"),
                "classification": classification,
                "maturity_label": maturity,
                "publication_safe_wording": claim.get("publication_safe_wording"),
                "required_action": claim.get("required_action"),
            }
            if classification == "unsupported":
                blocked.append(record)
            elif maturity in {"proposed", "aspirational"} or "evidence" in str(claim.get("required_action", "")).lower():
                needs_evidence.append(record)
            else:
                safe.append(record)

        return {
            "status": governance.get("status"),
            "source_audit": governance.get("source_audit"),
            "safe_to_claim": safe,
            "needs_evidence": needs_evidence,
            "blocked": blocked,
            "release_checklist": governance.get("release_checklist", []),
            "privacy_rules": governance.get("privacy_rules", {}),
            "claim_rules": governance.get("claim_rules", {}),
            "claim_count": len([claim for claim in claims if isinstance(claim, dict)]),
            "not_publication_ready": bool(blocked or needs_evidence),
        }

    def _load_yaml(self, rel: str) -> dict[str, Any]:
        with (self.root / rel).open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        return data if isinstance(data, dict) else {}
