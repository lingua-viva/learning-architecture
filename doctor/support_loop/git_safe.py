from __future__ import annotations

import subprocess

from pathlib import Path

from .paths import LV_ROOT, REPO_ROOT
from .privacy import redact_text


def run_git_read(args: list[str]) -> tuple[int, str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    return completed.returncode, redact_text(output.strip())


def status_short(path: Path | None = None) -> str:
    args = ["status", "--short", "--branch"]
    if path is not None:
        args.extend(["--", str(path.relative_to(REPO_ROOT))])
    code, output = run_git_read(args)
    if code != 0:
        return f"git status unavailable: {output}"
    return output


def lingua_viva_status_short() -> str:
    return status_short(LV_ROOT)


def current_branch() -> str:
    code, output = run_git_read(["branch", "--show-current"])
    if code != 0:
        return "unknown"
    return output.strip() or "detached"
