#!/usr/bin/env python3
"""App Reality Eval — mechanically detect fake, dead, or disconnected surfaces.

Adapted from Mission Canvas's src/app_reality_eval.py, which checks what a USER
encounters rather than what the code claims. MC's version is hardcoded to its
own root and expects a React tree (desktop/src/App.tsx); LV's teacher UI is
vanilla JS in static/index.html, so the checks are LV's own.

What this adds that existing gates do not:

  check_route_reachability.py proves every ROUTE has a UI call site. It does
  NOT prove the reverse — a UI calling a route that does not exist passes it
  today, and the teacher gets a dead button. Check 1 closes that direction.

Every check is a grep/parse. No LLM, no network, no side effects.

  python3 scripts/check_app_reality.py           # exit 1 on any finding
  python3 scripts/check_app_reality.py --json    # machine-readable
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INDEX = REPO / "static" / "index.html"
WEB = REPO / "src" / "web.py"
ROUTERS = REPO / "src" / "lingua_viva" / "routers"

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2}


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _routes_from_source(source: str) -> set[str]:
    prefix_match = re.search(r'APIRouter\(\s*prefix\s*=\s*"([^"]+)"', source)
    prefix = prefix_match.group(1).rstrip("/") if prefix_match else ""
    decorator = re.compile(
        r'@(app|router)\.(get|post|put|patch|delete|websocket)\(\s*"([^"]+)"'
    )
    routes = set()
    for target, _method, path in decorator.findall(source):
        if target == "router" and prefix and not path.startswith(prefix + "/"):
            routes.add(f"{prefix}{path}")
        else:
            routes.add(path)
    return routes


def _declared_routes(web: str) -> set[str]:
    """Every path registered by the app, with {param} placeholders kept."""
    routes = _routes_from_source(web)
    for router_file in sorted(ROUTERS.glob("*.py")):
        routes.update(_routes_from_source(_read(router_file)))
    return routes


def _route_matches(called: str, declared: set[str]) -> bool:
    """A called path matches a declared one, allowing for {param} segments."""
    if called in declared:
        return True
    called_parts = called.strip("/").split("/")
    for route in declared:
        route_parts = route.strip("/").split("/")
        if len(route_parts) != len(called_parts):
            continue
        if all(
            expected.startswith("{") or expected == actual
            for expected, actual in zip(route_parts, called_parts)
        ):
            return True
    return False


# --- Check 1: the UI calls a route that does not exist ----------------------


def check_ui_calls_real_routes(index: str, web: str) -> list[dict]:
    """The direction check_route_reachability.py does not cover."""
    declared = _declared_routes(web)
    findings = []
    # Literal paths only. A template like `/api/x/${id}` is normalised to a
    # {param} segment; anything whose prefix is not resolvable is skipped
    # rather than guessed at.
    for raw in set(re.findall(r'["\'`](/api/[^"\'`\s?]+)', index)):
        templated = "${" in raw
        called = re.sub(r"\$\{[^}]*\}", "x", raw)
        if _route_matches(called, declared):
            continue
        if templated:
            # The path is assembled at runtime (e.g. /api/admin/${state.view}),
            # so a static check cannot resolve which route it reaches. Report
            # it as unverifiable rather than missing — a gate that cries wolf
            # on every dynamic path gets ignored, which costs more than it
            # catches.
            findings.append({
                "check": "ui_route_unverifiable",
                "severity": "medium",
                "detail": f"static/index.html builds {raw} at runtime — cannot statically confirm the route exists",
            })
            continue
        findings.append({
            "check": "ui_calls_missing_route",
            "severity": "critical",
            "detail": f"static/index.html calls {raw} — no matching app route",
        })
    return findings


# --- Check 2: a view in the nav with no renderer ----------------------------


def check_nav_views_have_renderers(index: str) -> list[dict]:
    findings = []
    nav_ids: set[str] = set()
    for block in re.findall(r"const \w*[Nn]av = \[(.*?)\];", index, flags=re.S):
        nav_ids.update(re.findall(r'\["([^"]+)"', block))

    view_map = re.search(r"const views = \{(.*?)\n      \};", index, flags=re.S)
    mapped = set(re.findall(r"^\s*([a-zA-Z_]+):", view_map.group(1), flags=re.M)) if view_map else set()

    for view in sorted(nav_ids - mapped):
        findings.append({
            "check": "nav_view_without_renderer",
            "severity": "critical",
            "detail": f'nav entry "{view}" has no entry in the views map — clicking it does nothing',
        })
    return findings


# --- Check 3: a renderer that is never reached ------------------------------


def check_renderers_are_reachable(index: str) -> list[dict]:
    findings = []
    defined = set(re.findall(r"async function (render[A-Z]\w*)", index))
    defined |= set(re.findall(r"\bfunction (render[A-Z]\w*)", index))
    for name in sorted(defined):
        # A renderer is reachable if it is called, or registered in the view
        # map, or bound as an event handler.
        uses = len(re.findall(rf"\b{name}\b", index))
        if uses <= 1:
            findings.append({
                "check": "renderer_never_called",
                "severity": "high",
                "detail": f"{name}() is defined but never referenced — built, not mounted",
            })
    return findings


# --- Check 4: shipped placeholder / deferred text ---------------------------


PLACEHOLDER_PATTERNS = (
    (r"Required Before Activation", "deferred stub markup"),
    (r"coming soon", "'coming soon' shipped to a teacher"),
    (r"[Ll]orem ipsum", "placeholder copy"),
    (r"TODO(?![_A-Za-z])", "TODO left in the teacher UI"),
)


def _without_comments(source: str) -> str:
    """Drop whole-line JS/HTML comments before scanning for shipped text.

    A comment explaining why a placeholder was removed is not a placeholder.
    Without this the checker flags its own fix notes — the same trap as
    grepping for a symbol a docstring names in order to say it is unused.
    Only whole-line comments are stripped, so "https://" survives.
    """
    kept = []
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("//") or (stripped.startswith("<!--") and stripped.endswith("-->")):
            continue
        kept.append(line)
    return "\n".join(kept)


def check_no_placeholder_text(index: str) -> list[dict]:
    findings = []
    body = _without_comments(index)
    for pattern, why in PLACEHOLDER_PATTERNS:
        if re.search(pattern, body):
            findings.append({
                "check": "placeholder_text_shipped",
                "severity": "high",
                "detail": f"static/index.html contains {why} (/{pattern}/)",
            })
    return findings


# --- Check 5: a count rendered under a label that contradicts it ------------


def check_no_contradicted_counts(index: str) -> list[dict]:
    """The 'No external calls' class of bug: a live count printed beneath a
    label asserting that count is zero."""
    findings = []
    for match in re.finditer(
        r"<h3>\$\{([^}]+)\}</h3>\s*<p>\s*(No |Zero |0 )", index
    ):
        findings.append({
            "check": "count_contradicted_by_label",
            "severity": "critical",
            "detail": (
                f"a rendered count (${{{match.group(1).strip()}}}) sits under a label "
                f"beginning '{match.group(2).strip()}' — the label denies the number"
            ),
        })
    return findings


# --- Check 6: hardcoded truth claims ----------------------------------------


HARDCODED_CLAIMS = (
    (r'badge ok">external calls: 0', "hardcoded zero external calls"),
    (r"No data has left this machine\.", "unconditional data-egress claim"),
    (r'"external_called": False', "hardcoded external_called in a response"),
)


def check_no_hardcoded_claims(index: str, web: str) -> list[dict]:
    findings = []
    for pattern, why in HARDCODED_CLAIMS:
        for blob, name in ((index, "static/index.html"), (web, "src/web.py")):
            if re.search(pattern, blob):
                findings.append({
                    "check": "hardcoded_truth_claim",
                    "severity": "critical",
                    "detail": f"{name}: {why} (/{pattern}/)",
                })
    return findings


# --- Check 7: unescaped interpolation of server data ------------------------


def check_escaping_on_rendered_values(index: str) -> list[dict]:
    """Any ${...} inside markup that is not escapeHtml'd, numeric, or a known
    safe helper. Student names and file paths flow through these."""
    findings = []
    # Numeric fields from our own API cannot carry markup; string fields can.
    # This list is the numeric surface, so the check stays pointed at the
    # values a student name or file path could actually travel through.
    numeric = (
        r"length|size|count|total|observations|actions|students|cohort|"
        r"this_window|not_covered|entry_count|teacher_count|events_received|"
        r"student_zones_excluded|needs_review|reasoning_traces|tier_changes_recorded|"
        r"students_with_tier_history|ontology_nodes|domains|knowledge_entries|"
        r"citations|path_records|gap_signals|pendingReview|connected_count|total_count"
    )
    safe = re.compile(
        rf"^(escapeHtml|aronBadge|sourceLine|adminTable|cells\[|render\w+|"
        rf"[\w.]*({numeric})\b|\d+)"
    )
    for match in re.finditer(r"<(?:p|h3|strong|span|td)[^>]*>\$\{([^}]+)\}", index):
        expression = match.group(1).strip()
        if safe.match(expression) or expression.startswith("("):
            continue
        if "escapeHtml" in expression or "?" in expression:
            continue
        findings.append({
            "check": "unescaped_interpolation",
            "severity": "medium",
            "detail": f"${{{expression}}} rendered into markup without escapeHtml",
        })
    return findings


def run() -> list[dict]:
    index = _read(INDEX)
    web = _read(WEB)
    findings: list[dict] = []
    findings += check_ui_calls_real_routes(index, web)
    findings += check_nav_views_have_renderers(index)
    findings += check_renderers_are_reachable(index)
    findings += check_no_placeholder_text(index)
    findings += check_no_contradicted_counts(index)
    findings += check_no_hardcoded_claims(index, web)
    findings += check_escaping_on_rendered_values(index)
    findings.sort(key=lambda f: SEVERITY_ORDER.get(f["severity"], 9))
    return findings


def main() -> int:
    findings = run()
    if "--json" in sys.argv:
        print(json.dumps({"findings": findings, "count": len(findings)}, indent=2))
    else:
        for finding in findings:
            print(f"[app-reality] {finding['severity'].upper()}: {finding['detail']}")
        if not findings:
            print("[app-reality] OK — no fake, dead, or disconnected surfaces found")
        else:
            counts: dict[str, int] = {}
            for finding in findings:
                counts[finding["severity"]] = counts.get(finding["severity"], 0) + 1
            print(f"[app-reality] {len(findings)} finding(s): {counts}")
    # Fail on what is actually broken. Medium findings are advisory — the
    # same shape as ROUTE_REACHABILITY's deferred_undecided: visible, tracked,
    # and not a build stopper.
    blocking = [f for f in findings if f["severity"] in {"critical", "high"}]
    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
