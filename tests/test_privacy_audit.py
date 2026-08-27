"""Privacy audit lock (SPEC_LV_IMPROVEMENT_CHECKLIST_2026-08-22 P0-SEC-002).

Student names must never reach exception text, log calls, or stdout —
those surfaces end up in stderr, crash reports, and CI logs. Names in the
teacher-facing UI responses and the local vault are by design and out of
scope here.

Class caught in the wild (2026-08-22): teacher_readiness.py raised
``RuntimeError(f"could not create student {name}: {data}")`` — a student
display name plus a raw API echo of it, straight into exception text. This
test locks the class with an AST scan: any f-string interpolating a
name-like identifier inside a ``raise``, a logging call, or ``print`` in
``src/`` fails the suite.
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Identifiers that hold (or plausibly hold) a student's name. Bare "name"
# is included on purpose — it is exactly what the real violation used.
NAME_FIELDS = {"name", "display_name", "student_name", "first_name", "surname", "full_name"}

LOG_METHOD_NAMES = {"debug", "info", "warning", "error", "exception", "critical", "warn"}

# Files where a bare `name` identifier can never hold student data.
# slack_credentials.py: `name` is always a config FIELD name
# (e.g. "LV_SLACK_BOT_TOKEN") — its docstring even promises "naming the
# field but never its content".
BARE_NAME_ALLOWLIST = {"src/lingua_viva/slack_credentials.py"}


def _interpolated_name_field(fstring: ast.JoinedStr) -> str | None:
    for node in ast.walk(fstring):
        if not isinstance(node, ast.FormattedValue):
            continue
        for inner in ast.walk(node.value):
            if isinstance(inner, ast.Name) and inner.id in NAME_FIELDS:
                return inner.id
            if isinstance(inner, ast.Attribute) and inner.attr in NAME_FIELDS:
                return inner.attr
    return None


def _leak_surfaces(tree: ast.AST):
    """Yield (lineno, kind, args) for every raise / log / print call."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
            yield node.lineno, "raise", node.exc.args
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "print":
                yield node.lineno, "print", node.args
            elif isinstance(func, ast.Attribute) and func.attr in LOG_METHOD_NAMES:
                yield node.lineno, f"log.{func.attr}", node.args


def test_no_student_name_interpolation_in_exceptions_logs_or_prints():
    violations = []
    for path in sorted((REPO / "src").rglob("*.py")):
        rel = path.relative_to(REPO).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for lineno, kind, args in _leak_surfaces(tree):
            for arg in args:
                if not isinstance(arg, ast.JoinedStr):
                    continue
                field = _interpolated_name_field(arg)
                if field is None:
                    continue
                if field == "name" and rel in BARE_NAME_ALLOWLIST:
                    continue
                violations.append(f"{rel}:{lineno} [{kind}] interpolates `{field}`")

    assert not violations, (
        "Student-name-like identifiers interpolated into exception/log/print "
        "text (use student_id, a hash, or a generic message instead):\n"
        + "\n".join(violations)
    )
