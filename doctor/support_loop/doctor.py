from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml

from .paths import DOCTOR_LOG, LV_ROOT, REPO_ROOT, STATE_DIR
from .privacy import matches_private_path, redact_text
from .schemas import CheckResult, utc_now, worst_status


EXPECTED_BRANCHES = ("main", "LINGUA-VIVA-UPDATE")
EXPECTED_BRANCH = EXPECTED_BRANCHES[0]
MANUAL_DOCX = "Manuale_Italiano_Laboratorio_Linguistico_G1-G5.docx"

REQUIRED_FILES = [
    "README.md",
    MANUAL_DOCX,
    "dev/specs/LV_PUBLICATION_READINESS_AUDIT_2026-07-16.md",
    "artifacts/inventory.yaml",
    "claims/evidence_register.yaml",
    "governance/publication_safety.yaml",
    "curriculum/lingua_viva_matrix.yaml",
    "doctor/lv_artifact_gauntlet.py",
    "dev/lv_revision_log.ndjson",
    "dev/lv_deferred_candidates.yaml",
]

YAML_FILES = [
    "artifacts/inventory.yaml",
    "claims/evidence_register.yaml",
    "governance/publication_safety.yaml",
    "curriculum/lingua_viva_matrix.yaml",
    "dev/lv_deferred_candidates.yaml",
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

REVISION_LOG_KEYS = {
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

ACTIVE_SURFACE_FILES = [
    "README.md",
    "dev/specs/LV_PUBLICATION_READINESS_AUDIT_2026-07-16.md",
    "artifacts/inventory.yaml",
    "claims/evidence_register.yaml",
    "governance/publication_safety.yaml",
    "curriculum/lingua_viva_matrix.yaml",
    "doctor/lv_artifact_gauntlet.py",
    "dev/lv_support.py",
]

MC_BLOAT_PATTERNS = [
    r"\bOntologyEngine\b",
    r"\bMemoryStore\b",
    r"\bKnowledgeStore\b",
    r"\bPipeline\b",
    r"mission-canvas/src",
    r"src/pipeline.py",
    r"mc_cli",
]


def _git(args: list[str]) -> tuple[int, str]:
    completed = subprocess.run(["git", *args], cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
    return completed.returncode, redact_text(output)


def _rel(path: str) -> str:
    return str((LV_ROOT / path).relative_to(REPO_ROOT))


def _check(status: str, check_id: str, message: str, severity: str = "required", detail: str = "", safe_fix: str | None = None) -> CheckResult:
    return CheckResult(
        id=check_id,
        status=status,
        message=message,
        detail=redact_text(detail),
        safe_fix=safe_fix,
        severity=severity,
    )


def _load_yaml(rel: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        with (LV_ROOT / rel).open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except Exception as exc:
        return None, str(exc)
    if not isinstance(data, dict):
        return None, "YAML root is not a mapping"
    return data, None


def check_branch() -> CheckResult:
    code, output = _git(["branch", "--show-current"])
    branch = output.strip() if code == 0 else "unknown"
    if branch in EXPECTED_BRANCHES:
        return _check("pass", "branch", f"Branch is allowed: {branch}.", detail=branch)
    expected = " or ".join(EXPECTED_BRANCHES)
    return _check("fail", "branch", f"Branch must be {expected}; current branch is {branch}.", detail=branch)


def check_required_files() -> list[CheckResult]:
    checks: list[CheckResult] = []
    for rel in REQUIRED_FILES:
        path = LV_ROOT / rel
        checks.append(_check("pass" if path.exists() else "fail", f"required_file:{rel}", f"Required file present: {rel}" if path.exists() else f"Required file missing: {rel}"))
    return checks


def check_lingua_viva_worktree() -> CheckResult:
    code, output = _git(["status", "--short", "--", _rel(".")])
    if code != 0:
        return _check("warn", "worktree_status", "Could not read Lingua Viva package git status.", "recommended", output)
    lines = [line for line in output.splitlines() if line.strip()]
    if not lines:
        return _check("pass", "worktree_status", "Lingua Viva package has no visible worktree changes.")
    return _check("warn", "worktree_status", "Lingua Viva package has local changes; review before update.", "recommended", "\n".join(lines[:40]))


def check_docx_not_modified() -> CheckResult:
    rel = _rel(MANUAL_DOCX)
    code, output = _git(["status", "--short", "--", rel])
    if code != 0:
        return _check("warn", "docx_no_diff", "Could not verify .docx git status.", "recommended", output)
    status_lines = [line for line in output.splitlines() if line.strip()]
    if status_lines:
        return _check("fail", "docx_no_diff", ".docx source appears modified or untracked; doctor will not proceed as healthy.", detail="\n".join(status_lines))
    if not (LV_ROOT / MANUAL_DOCX).exists():
        return _check("fail", "docx_no_diff", ".docx source is missing.")
    return _check("pass", "docx_no_diff", ".docx exists and has no git diff.")


def check_yaml_files() -> list[CheckResult]:
    checks: list[CheckResult] = []
    for rel in YAML_FILES:
        data, error = _load_yaml(rel)
        if error:
            checks.append(_check("fail", f"yaml:{rel}", f"YAML parse failed: {rel}", detail=error))
        else:
            checks.append(_check("pass", f"yaml:{rel}", f"YAML parsed: {rel}"))
    return checks


def check_revision_log_schema() -> CheckResult:
    path = LV_ROOT / "dev/lv_revision_log.ndjson"
    try:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not lines:
            return _check("fail", "revision_log_schema", "Revision log is empty.")
        for idx, line in enumerate(lines, 1):
            entry = json.loads(line)
            missing = sorted(REVISION_LOG_KEYS - set(entry))
            if missing:
                return _check("fail", "revision_log_schema", f"Revision log line {idx} is missing required keys.", detail=", ".join(missing))
            if not isinstance(entry.get("instrument_touched"), bool):
                return _check("fail", "revision_log_schema", f"Revision log line {idx} instrument_touched is not boolean.")
            if not isinstance(entry.get("teacher_contribution_involved"), bool):
                return _check("fail", "revision_log_schema", f"Revision log line {idx} teacher_contribution_involved is not boolean.")
    except Exception as exc:
        return _check("fail", "revision_log_schema", "Revision log parse/schema check failed.", detail=str(exc))
    return _check("pass", "revision_log_schema", "Revision log parses and includes the full schema.")


def check_artifact_gauntlet() -> CheckResult:
    script = LV_ROOT / "doctor/lv_artifact_gauntlet.py"
    completed = subprocess.run(["python3", str(script)], cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    output = redact_text("\n".join(part for part in (completed.stdout, completed.stderr) if part).strip())
    if completed.returncode == 0:
        return _check("pass", "lv_artifact_gauntlet", "Lingua Viva artifact gauntlet passed.", detail=output)
    return _check("fail", "lv_artifact_gauntlet", "Lingua Viva artifact gauntlet failed.", detail=output)


def check_matrix_authority() -> CheckResult:
    data, error = _load_yaml("curriculum/lingua_viva_matrix.yaml")
    if error or data is None:
        return _check("fail", "matrix_authority", "Could not read curriculum matrix authority.", detail=error or "")
    if data.get("authority") != "non_authoritative":
        return _check("fail", "matrix_authority", "Curriculum matrix authority is not non_authoritative.", detail=str(data.get("authority")))
    if data.get("promotion_status", {}).get("current_decision") != "Do not promote yet.":
        return _check("fail", "matrix_authority", "Curriculum matrix promotion decision changed.", detail=str(data.get("promotion_status")))
    return _check("pass", "matrix_authority", "Curriculum matrix remains non-authoritative.")


def check_claim_register() -> CheckResult:
    data, error = _load_yaml("claims/evidence_register.yaml")
    if error or data is None:
        return _check("fail", "claim_register", "Could not read claim register.", detail=error or "")
    claims = data.get("claims", [])
    ids = {claim.get("id") for claim in claims if isinstance(claim, dict)}
    missing = sorted(REQUIRED_CLAIMS - ids)
    if missing:
        return _check("fail", "claim_register", "Claim register is missing required claims.", detail=", ".join(missing))
    return _check("pass", "claim_register", "Claim register contains required claims.")


def check_publication_safety() -> CheckResult:
    data, error = _load_yaml("governance/publication_safety.yaml")
    if error or data is None:
        return _check("fail", "publication_safety", "Could not read publication safety rules.", detail=error or "")
    rules = data.get("privacy_rules", {})
    missing = [key for key in ("student_data", "teacher_contributions", "institution_data", "ai_attribution") if not rules.get(key)]
    if missing:
        return _check("fail", "publication_safety", "Publication safety rules are incomplete.", detail=", ".join(missing))
    return _check("pass", "publication_safety", "Publication safety rules are present.")


def check_readme_overclaims() -> CheckResult:
    readme_path = LV_ROOT / "README.md"
    if not readme_path.exists():
        return _check("pass", "readme_overclaims", "README not present in this build; skipped.")
    readme = readme_path.read_text(encoding="utf-8")
    hits = [pattern for pattern in FORBIDDEN_README_PATTERNS if re.search(pattern, readme, flags=re.IGNORECASE)]
    if hits:
        return _check("fail", "readme_overclaims", "README contains forbidden public overclaim patterns.", detail=", ".join(hits))
    return _check("pass", "readme_overclaims", "README forbidden overclaim scan passed.")


def check_active_surface_mc_bloat() -> CheckResult:
    hits: list[str] = []
    for rel in ACTIVE_SURFACE_FILES:
        path = LV_ROOT / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in MC_BLOAT_PATTERNS:
            if re.search(pattern, text):
                hits.append(f"{rel}: {pattern}")
    if hits:
        return _check("warn", "active_surface_mc_bloat", "Active Lingua Viva surfaces contain possible MC platform coupling.", "recommended", "\n".join(hits[:30]))
    return _check("pass", "active_surface_mc_bloat", "No obvious MC platform bloat found in active Lingua Viva surfaces.")


def check_privacy_paths() -> CheckResult:
    risks: list[str] = []
    expected_exclusions: list[str] = []
    for path in LV_ROOT.rglob("*"):
        rel = path.relative_to(LV_ROOT)
        if ".lv_support" in rel.parts or "__pycache__" in rel.parts:
            continue
        if matches_private_path(rel):
            if rel.suffix.lower() == ".docx":
                expected_exclusions.append(f"{rel}: docx private/source draft excluded from support output")
            else:
                risks.append(f"{rel}: private-path pattern")
    if risks:
        return _check("private_risk", "privacy_path_scan", "Possible private/student data path found. Contents were not read.", "privacy", "\n".join(risks[:40]))
    if expected_exclusions:
        return _check("warn", "privacy_path_scan", "Expected private-source exclusions are present and were not read.", "privacy", "\n".join(expected_exclusions))
    return _check("pass", "privacy_path_scan", "No private-risk paths found by filename scan.")


def _summary_for(status: str) -> str:
    return {
        "OK": "Everything looks healthy.",
        "WARN": "Something may need attention, but you can keep working.",
        "FIXABLE": "I found a safe fix, but I did not apply it.",
        "UPDATE_AVAILABLE": "An approved update is available.",
        "BLOCKED": "I cannot fix this safely on my own.",
        "PRIVATE_RISK": "I found a privacy risk and stopped.",
    }[status]


def run_doctor(write_log: bool = True) -> dict[str, Any]:
    checks: list[CheckResult] = [
        check_branch(),
        *check_required_files(),
        check_lingua_viva_worktree(),
        check_docx_not_modified(),
        *check_yaml_files(),
        check_revision_log_schema(),
        check_artifact_gauntlet(),
        check_matrix_authority(),
        check_claim_register(),
        check_publication_safety(),
        check_readme_overclaims(),
        check_active_surface_mc_bloat(),
        check_privacy_paths(),
    ]
    status = worst_status(checks)
    safe_actions = []
    if not STATE_DIR.exists():
        safe_actions.append({"id": "create_support_state_dir", "label": "Create local support state directory", "enabled": False, "phase": "deferred"})
        if status == "OK":
            status = "FIXABLE"
    result = {
        "status": status,
        "summary": _summary_for(status),
        "timestamp": utc_now(),
        "mode": "teacher",
        "branch_expected": EXPECTED_BRANCH,
        "branch_allowed": list(EXPECTED_BRANCHES),
        "repo_root": str(REPO_ROOT),
        "lingua_viva_root": str(LV_ROOT),
        "checks": [check.as_dict() for check in checks],
        "safe_actions": safe_actions,
        "blocked_actions": [
            "docx edits",
            "curriculum matrix promotion",
            "curriculum content rewrites",
            "destructive git commands",
            "student-data upload",
            "external support transmission",
        ],
        "privacy_notes": [
            "Doctor checks paths and metadata only for private-risk files.",
            "Raw student observations, IEPs, parent communications, and .docx contents are not included in output.",
        ],
        "support_bundle_available": True,
        "next_steps": ["Use the Health view to create a local redacted support bundle if you need help reviewing these findings."],
        "external_calls": False,
    }
    if write_log:
        STATE_DIR.mkdir(exist_ok=True)
        with DOCTOR_LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(result, ensure_ascii=True) + "\n")
    return result


def format_teacher_summary(result: dict[str, Any]) -> str:
    lines = [
        f"Lingua Viva Doctor: {result['status']}",
        result["summary"],
        "",
    ]
    for check in result["checks"]:
        if check["status"] != "pass":
            lines.append(f"- {check['status'].upper()}: {check['message']}")
    if len(lines) == 3:
        lines.append("No action needed.")
    if result.get("next_steps"):
        lines.append("")
        lines.extend(f"Next: {step}" for step in result["next_steps"])
    return "\n".join(lines)
