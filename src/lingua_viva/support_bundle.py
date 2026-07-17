from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from doctor.support_loop.doctor import run_doctor
from doctor.support_loop.privacy import matches_private_path, path_risk_reason, redact_text


ROOT = Path(__file__).resolve().parents[2]


class SupportBundleService:
    """Create a local, redacted support bundle when Doctor finds issues."""

    def __init__(self, repo_root: Path | str = ROOT, support_root: Path | str | None = None):
        self.repo_root = Path(repo_root)
        override = os.environ.get("LV_SUPPORT_DIR")
        self.support_root = Path(support_root or override or self.repo_root / ".lv_support")

    def create_bundle(self) -> dict:
        created_at = datetime.now(timezone.utc)
        bundle_id = f"lv-support-{created_at.strftime('%Y%m%dT%H%M%SZ')}"
        bundle_dir = self.support_root / "bundles" / bundle_id
        bundle_dir.mkdir(parents=True, exist_ok=False)

        doctor_result = self._redact_obj(run_doctor(write_log=False))
        gauntlet_output, gauntlet_code = self._run_command(["python3", "doctor/lv_artifact_gauntlet.py"])
        git_status = self._run_git_status()
        excluded = self._scan_exclusions()
        included: list[dict[str, str]] = []

        self._write_text(
            bundle_dir / "SUPPORT_SUMMARY.md",
            self._summary(bundle_id, created_at, doctor_result, gauntlet_code, excluded),
            included,
            "redacted_diagnostic",
        )
        self._write_json(bundle_dir / "DOCTOR_RESULT.json", doctor_result, included)
        self._write_text(bundle_dir / "GAUNTLET_OUTPUT.txt", gauntlet_output, included, "redacted_diagnostic")
        self._write_text(bundle_dir / "GIT_STATUS.txt", git_status, included, "redacted_metadata")
        self._write_text(bundle_dir / "REDACTION_REPORT.md", self._redaction_report(excluded), included, "privacy_report")

        manifest = {
            "bundle_id": bundle_id,
            "created_at": created_at.isoformat().replace("+00:00", "Z"),
            "created_by": "lv_support_phase_b",
            "repo_root": str(self.repo_root),
            "lingua_viva_root": str(self.repo_root),
            "external_calls": False,
            "included": included,
            "excluded": excluded,
            "redactions": [{"type": "doctor_support_loop_patterns", "count": "applied"}],
            "checks": {
                "student_data_included": False,
                "docx_content_included": False,
                "external_upload": False,
                "zip_created": False,
            },
        }
        self._write_json(bundle_dir / "MANIFEST.json", manifest, included)

        return {
            "status": "OK",
            "bundle_path": str(bundle_dir),
            "manifest_path": str(bundle_dir / "MANIFEST.json"),
            "summary": "Support bundle created. No student data was included. No files were uploaded.",
            "included_count": len(included),
            "excluded_count": len(excluded),
            "privacy_notes": [
                "Manual .docx contents excluded.",
                "Student observations, parent communications, private databases, and secrets excluded by rule.",
                "No upload was attempted.",
            ],
            "external_calls": False,
        }

    def _run_command(self, command: list[str]) -> tuple[str, int]:
        completed = subprocess.run(command, cwd=self.repo_root, text=True, capture_output=True, check=False)
        output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
        return redact_text(output), completed.returncode

    def _run_git_status(self) -> str:
        output, _code = self._run_command([
            "git",
            "status",
            "--short",
            "--",
            "src",
            "static",
            "doctor",
            "governance",
            "claims",
            "curriculum",
            "dev/specs",
        ])
        return output or "No relevant git status output."

    def _scan_exclusions(self) -> list[dict[str, str]]:
        excluded: list[dict[str, str]] = []
        ignored_dirs = {".git", "desktop/node_modules", "__pycache__"}
        for path in self.repo_root.rglob("*"):
            rel = path.relative_to(self.repo_root)
            rel_text = str(rel).replace("\\", "/")
            if any(rel_text == item or rel_text.startswith(item + "/") for item in ignored_dirs):
                continue
            reason = self._exclusion_reason(rel)
            if reason:
                excluded.append({"path": redact_text(rel_text), "reason": reason})
        return excluded

    def _exclusion_reason(self, rel: Path) -> str | None:
        rel_text = str(rel).replace("\\", "/")
        lowered = rel_text.lower()
        if rel.parts and rel.parts[0] == ".lv_support":
            return "support runtime state and existing bundles are never bundled"
        if rel.suffix.lower() == ".docx":
            return "docx source/private draft excluded; contents were not read"
        if any(token in lowered for token in ("student_lens", "observation", "iep", "progress_report", "parent_report", "individual_score")):
            return "student or family data pattern excluded"
        if any(token in lowered for token in (".db", ".sqlite", ".sqlite3")):
            return "private local database excluded"
        if any(token in lowered for token in (".env", "secret", "token", "api_key", "password", "oauth")):
            return "secret/token pattern excluded"
        if matches_private_path(rel):
            return path_risk_reason(rel) or "privacy pattern excluded"
        return None

    def _summary(self, bundle_id: str, created_at: datetime, doctor_result: dict[str, Any], gauntlet_code: int, excluded: list[dict[str, str]]) -> str:
        failed = [
            check for check in doctor_result.get("checks", [])
            if check.get("status") not in ("pass", "OK")
        ][:12]
        lines = [
            f"# Lingua Viva Support Bundle {bundle_id}",
            "",
            f"Created: {created_at.isoformat().replace('+00:00', 'Z')}",
            f"Doctor status: {doctor_result.get('status')}",
            f"Gauntlet exit code: {gauntlet_code}",
            "",
            "No student data was included. No files were uploaded. No zip was created.",
            "",
            "## Doctor Findings",
        ]
        if failed:
            for check in failed:
                lines.append(f"- {check.get('status')}: {check.get('id')} - {check.get('message')}")
        else:
            lines.append("- No non-pass Doctor findings.")
        lines.extend(["", "## Exclusions", f"{len(excluded)} files or paths matched exclusion rules."])
        return redact_text("\n".join(lines) + "\n")

    def _redaction_report(self, excluded: list[dict[str, str]]) -> str:
        lines = [
            "# Redaction Report",
            "",
            "The support bundle is a local directory. It was not uploaded and was not zipped.",
            "",
            "Excluded content classes:",
            "- .docx source/private drafts",
            "- student observations, IEPs, progress reports, individual scores",
            "- parent communications",
            "- private local databases",
            "- secrets, tokens, API keys, OAuth material",
            "- .lv_support runtime state and previous bundles",
            "",
            "Matched exclusions:",
        ]
        for item in excluded[:200]:
            lines.append(f"- {item['path']}: {item['reason']}")
        if len(excluded) > 200:
            lines.append(f"- ... {len(excluded) - 200} additional exclusions omitted from this report")
        return redact_text("\n".join(lines) + "\n")

    def _write_text(self, path: Path, content: str, included: list[dict[str, str]], privacy_class: str) -> None:
        path.write_text(redact_text(content), encoding="utf-8")
        included.append({"path": path.name, "source": "generated", "privacy_class": privacy_class})

    def _write_json(self, path: Path, data: dict[str, Any], included: list[dict[str, str]]) -> None:
        path.write_text(json.dumps(self._redact_obj(data), indent=2, ensure_ascii=True), encoding="utf-8")
        included.append({"path": path.name, "source": "generated", "privacy_class": "redacted_diagnostic"})

    def _redact_obj(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {redact_text(str(k)): self._redact_obj(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._redact_obj(item) for item in value]
        if isinstance(value, str):
            return redact_text(value)
        return value
