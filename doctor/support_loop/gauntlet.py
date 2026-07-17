from __future__ import annotations

import json
import subprocess

import yaml

from .paths import DEV_ROOT, LV_ROOT, STATE_DIR
from .privacy import path_risk_reason
from .schemas import CheckResult


def run_artifact_gauntlet() -> CheckResult:
    script = LV_ROOT / "doctor/lv_artifact_gauntlet.py"
    if not script.exists():
        return CheckResult("artifact_gauntlet", "FIXABLE", "Lingua Viva artifact gauntlet is missing.", str(script), "create_required_dirs")
    completed = subprocess.run(["python3", str(script)], cwd=LV_ROOT, text=True, capture_output=True, check=False)
    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
    if completed.returncode == 0:
        return CheckResult("artifact_gauntlet", "OK", "Lingua Viva artifact gauntlet passed.", output)
    return CheckResult("artifact_gauntlet", "BLOCKED", "Lingua Viva artifact gauntlet failed.", output)


def check_yaml_files() -> list[CheckResult]:
    checks: list[CheckResult] = []
    for rel in ("artifacts/inventory.yaml", "claims/evidence_register.yaml", "governance/publication_safety.yaml", "curriculum/lingua_viva_matrix.yaml", "dev/lv_deferred_candidates.yaml"):
        path = LV_ROOT / rel
        if not path.exists():
            checks.append(CheckResult(f"yaml:{rel}", "FIXABLE", f"Missing YAML file: {rel}", safe_fix="create_required_dirs"))
            continue
        try:
            with path.open(encoding="utf-8") as handle:
                yaml.safe_load(handle)
        except Exception as exc:
            checks.append(CheckResult(f"yaml:{rel}", "BLOCKED", f"YAML parse failed: {rel}", str(exc)))
        else:
            checks.append(CheckResult(f"yaml:{rel}", "OK", f"YAML parsed: {rel}"))
    return checks


def check_revision_log() -> CheckResult:
    path = LV_ROOT / "dev/lv_revision_log.ndjson"
    if not path.exists():
        return CheckResult("revision_log", "FIXABLE", "Revision log is missing.", safe_fix="create_required_dirs")
    try:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        for line in lines:
            json.loads(line)
    except Exception as exc:
        return CheckResult("revision_log", "BLOCKED", "Revision log has invalid NDJSON.", str(exc))
    if not lines:
        return CheckResult("revision_log", "WARN", "Revision log exists but is empty.")
    return CheckResult("revision_log", "OK", "Revision log parsed.")


def check_private_paths() -> CheckResult:
    risks: list[str] = []
    expected_exclusions: list[str] = []
    for path in LV_ROOT.rglob("*"):
        if ".lv_support" in path.parts:
            continue
        rel = path.relative_to(LV_ROOT)
        reason = path_risk_reason(rel)
        if reason:
            line = f"{rel}: {reason}"
            if path.suffix.lower() == ".docx":
                expected_exclusions.append(line)
            else:
                risks.append(line)
    if risks:
        return CheckResult("private_path_scan", "PRIVATE_RISK", "Private or non-bundle-safe paths are present; bundle content will exclude them.", "\n".join(risks[:50]))
    if expected_exclusions:
        return CheckResult("private_path_scan", "WARN", "Expected non-bundle-safe source files are present and will be excluded.", "\n".join(expected_exclusions[:50]))
    return CheckResult("private_path_scan", "OK", "No private-path risks found by filename scan.")


def run_local_gauntlet() -> list[CheckResult]:
    checks = [
        CheckResult("state_dir", "OK" if STATE_DIR.exists() else "FIXABLE", ".lv_support state directory present." if STATE_DIR.exists() else ".lv_support state directory is missing.", safe_fix=None if STATE_DIR.exists() else "create_state_dirs"),
        run_artifact_gauntlet(),
        check_revision_log(),
        check_private_paths(),
    ]
    checks.extend(check_yaml_files())
    return checks
