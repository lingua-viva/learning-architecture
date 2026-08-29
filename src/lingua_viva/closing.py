from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence


@dataclass(frozen=True)
class ClosingCheck:
    id: str
    label: str
    why: str
    command: tuple[str, ...]


ROOT = Path(__file__).resolve().parent.parent.parent

CLOSING_CHECKS: tuple[ClosingCheck, ...] = (
    ClosingCheck(
        id="gauntlet",
        label="Education gauntlet",
        why="Teacher/admin artifact behavior stays intact across the 81-test gauntlet.",
        command=(sys.executable, "-m", "pytest", "tests/gauntlet", "-q"),
    ),
    ClosingCheck(
        id="pipeline",
        label="Document-to-lens pipeline",
        why="Teacher imports and governed execution still produce usable learner/lens evidence.",
        command=(
            sys.executable,
            "-m",
            "pytest",
            "tests/test_document_to_lens.py",
            "tests/test_document_import_security.py",
            "tests/test_pipeline_education_execute_wiring.py",
            "tests/test_student_data_stays_local.py",
            "-q",
        ),
    ),
    ClosingCheck(
        id="artifacts",
        label="Grounded teacher artifacts",
        why="Lesson plans and parent reports remain grounded, redacted, and honest about missing evidence.",
        command=(
            sys.executable,
            "-m",
            "pytest",
            "tests/test_lesson_plan_artifact.py",
            "tests/test_parent_report.py",
            "tests/test_parent_report_safety_gate.py",
            "tests/test_parent_report_template.py",
            "-q",
        ),
    ),
    ClosingCheck(
        id="preflight",
        label="Structural preflight",
        why="Golden data, imports, ontology counts, route reachability, conflicts, and UI contract are current.",
        command=(sys.executable, "-m", "src.lv_cli", "preflight", "--json"),
    ),
)


CommandRunner = Callable[[Sequence[str], Path], subprocess.CompletedProcess[str]]


def _run_command(command: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True)


def _tail(text: str, *, lines: int = 24) -> str:
    entries = text.strip().splitlines()
    if len(entries) <= lines:
        return "\n".join(entries)
    return "\n".join(entries[-lines:])


def run_closing(
    *,
    only: set[str] | None = None,
    run_command: CommandRunner = _run_command,
) -> dict:
    selected = [check for check in CLOSING_CHECKS if only is None or check.id in only]
    unknown = sorted((only or set()) - {check.id for check in CLOSING_CHECKS})
    checks: list[dict] = []
    start = time.time()

    for check in selected:
        check_start = time.time()
        result = run_command(check.command, ROOT)
        checks.append({
            "id": check.id,
            "label": check.label,
            "why": check.why,
            "command": " ".join(check.command),
            "status": "PASS" if result.returncode == 0 else "FAIL",
            "returncode": result.returncode,
            "duration_seconds": round(time.time() - check_start, 3),
            "stdout_tail": _tail(result.stdout),
            "stderr_tail": _tail(result.stderr),
        })

    failed = [check for check in checks if check["status"] != "PASS"]
    verdict = "PASS" if checks and not failed and not unknown else "FAIL"
    return {
        "surface": "lv_closing",
        "verdict": verdict,
        "duration_seconds": round(time.time() - start, 3),
        "checks": checks,
        "unknown_checks": unknown,
    }


def format_report(report: dict) -> str:
    lines = [f"Lingua Viva closing: {report['verdict']}"]
    for check in report["checks"]:
        lines.append(f"- {check['id']}: {check['status']} ({check['duration_seconds']}s)")
        if check["status"] != "PASS":
            if check.get("stdout_tail"):
                lines.append(f"  stdout: {check['stdout_tail'].splitlines()[-1]}")
            if check.get("stderr_tail"):
                lines.append(f"  stderr: {check['stderr_tail'].splitlines()[-1]}")
    if report.get("unknown_checks"):
        lines.append(f"Unknown checks: {', '.join(report['unknown_checks'])}")
    return "\n".join(lines)
