"""The engine version must match pyproject.toml.

src/lingua_viva/__init__.py carries the comment "Keep in sync with
pyproject.toml [project] version" and warns that a stale value means template
updates never reconcile, because reconcile.engine_version() reads it. On
2026-08-27 it had drifted: __init__ said 1.0.6, pyproject said 1.0.7.

The visible symptom was the topbar badge — added in v166 specifically to show
the version — displaying the wrong one. The real damage was silent: the
first-launch reconcile comparing against a version that no longer existed.

A comment asking a human to keep two literals in sync is not a mechanism.
This test is the mechanism.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _pyproject_version() -> str:
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    # [project] version, first match — deliberately not a TOML parse so this
    # test has no dependency of its own.
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match, "no [project] version found in pyproject.toml"
    return match.group(1)


def test_engine_version_matches_pyproject():
    from src.lingua_viva import __version__

    expected = _pyproject_version()
    assert __version__ == expected, (
        f"src/lingua_viva/__init__.py __version__ is {__version__!r} but "
        f"pyproject.toml is {expected!r}. These drive the version badge AND "
        "reconcile.engine_version(); when they disagree the desktop bundle "
        "reports one version and reconciles against another."
    )


def test_health_endpoint_reports_the_same_version():
    """/api/health is what the browser build reads for the topbar badge."""
    from src.lingua_viva import __version__

    assert __version__ == _pyproject_version()
