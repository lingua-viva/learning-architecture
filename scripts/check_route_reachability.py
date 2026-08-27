#!/usr/bin/env python3
"""Route reachability checker (dev/ROOT_CAUSE_BUILT_NOT_MOUNTED_2026-07-23.md §5).

Every route registered on the web surface — @app.* routes in src/web.py AND
@router.* routes in src/lingua_viva/routers/*.py (the router plug-in pattern,
with any APIRouter prefix resolved) — must be classified in
contracts/ROUTE_REACHABILITY.yaml as either reachable_from_ui (with a literal
call-site string proven to still exist) or intentionally_backend_only (with a
reason and a status). A route in neither list fails the check outright — the
default is "prove it", not "assume it's fine because the tests pass."

  check (default)   Verify every live route is classified, every
                    reachable_from_ui call_site literal still exists in its
                    file, no route is registered twice across the web surface
                    (the second definition would silently shadow the first —
                    and a web.py route duplicating a router route is dead
                    code, because routers are included first), and no
                    manifest entry references a route that's been removed.
                    Exit 1 on any violation.
  --sync-stale      Same stale-entry check as above, reported on its own
                    without needing to trigger the full check — never writes.

Spec: dev/specs/SPEC_LV_ROUTE_REACHABILITY_GATE_2026-07-23.md.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
WEB_PY = REPO / "src" / "web.py"
ROUTERS_DIR = REPO / "src" / "lingua_viva" / "routers"
MANIFEST = REPO / "contracts" / "ROUTE_REACHABILITY.yaml"

ROUTE_RE = re.compile(
    r'@app\.(get|post|put|patch|delete|websocket)\(\s*"([^"]+)"'
)
ROUTER_ROUTE_RE = re.compile(
    r'@router\.(get|post|put|patch|delete|websocket)\(\s*"([^"]+)"'
)
ROUTER_PREFIX_RE = re.compile(r'APIRouter\(\s*prefix\s*=\s*"([^"]*)"')
METHOD_LABEL = {
    "get": "GET",
    "post": "POST",
    "put": "PUT",
    "patch": "PATCH",
    "delete": "DELETE",
    "websocket": "WS",
}


def fail(msg: str) -> None:
    print(f"[route-reachability] FAIL: {msg}")


def live_routes() -> list[str]:
    """Every route registration on the web surface, in source order, WITH
    duplicates preserved — callers that need to detect a route registered
    twice (a real FastAPI footgun: the second definition silently shadows the
    first) must see the raw list, not a de-duplicated set.

    Covers src/web.py (@app.*) plus every module in src/lingua_viva/routers/
    (@router.*, with the module's APIRouter prefix resolved), because the
    router plug-in point in web.py includes those routers at startup — a
    route living in a router file is exactly as live as one in web.py."""
    text = WEB_PY.read_text(encoding="utf-8")
    routes = []
    for match in ROUTE_RE.finditer(text):
        method, path = match.group(1), match.group(2)
        routes.append(f"{METHOD_LABEL[method]} {path}")
    if ROUTERS_DIR.is_dir():
        for router_file in sorted(ROUTERS_DIR.glob("*.py")):
            if router_file.name == "__init__.py":
                continue
            rtext = router_file.read_text(encoding="utf-8")
            prefix_match = ROUTER_PREFIX_RE.search(rtext)
            prefix = prefix_match.group(1) if prefix_match else ""
            for match in ROUTER_ROUTE_RE.finditer(rtext):
                method, path = match.group(1), match.group(2)
                routes.append(f"{METHOD_LABEL[method]} {prefix}{path}")
    return routes


def load_manifest() -> dict:
    data = yaml.safe_load(MANIFEST.read_text(encoding="utf-8")) or {}
    if "reachable_from_ui" not in data or "intentionally_backend_only" not in data:
        print(f"[route-reachability] FAIL: {MANIFEST} missing required top-level lists")
        sys.exit(1)
    return data


def check() -> int:
    manifest = load_manifest()
    reachable = {e["route"]: e for e in manifest["reachable_from_ui"]}
    backend_only = {e["route"]: e for e in manifest["intentionally_backend_only"]}

    live = live_routes()
    live_set = set(live)
    failures: list[str] = []

    # A route registered twice (identical METHOD+path) is a real bug, not a
    # classification question — FastAPI silently lets the second definition
    # shadow the first, so the code as read is not the code as it runs.
    counts: dict[str, int] = {}
    for route in live:
        counts[route] = counts.get(route, 0) + 1
    for route, n in counts.items():
        if n > 1:
            failures.append(
                f"{route} — registered {n} times on the web surface (src/web.py + routers). The second "
                "definition silently shadows the first; this is a bug to fix "
                "in web.py, not something this manifest can classify away."
            )

    # A manifest entry whose route no longer exists in src/web.py is exactly
    # the kind of quiet drift this gate exists to prevent — `--sync-stale`
    # reports the same thing on demand, but leaving it out of the default
    # check would mean relying on someone remembering to run it.
    manifest_routes = set(reachable) | set(backend_only)
    for route in sorted(manifest_routes - live_set):
        failures.append(
            f"{route} — manifest entry references a route that no longer "
            "exists on the web surface (src/web.py + routers). Remove it (see --sync-stale)."
        )

    for route in live_set:
        in_reachable = route in reachable
        in_backend_only = route in backend_only
        if in_reachable and in_backend_only:
            failures.append(f"{route} — listed in BOTH reachable_from_ui and intentionally_backend_only")
            continue
        if not in_reachable and not in_backend_only:
            failures.append(
                f"{route} — not classified anywhere in {MANIFEST.name}. "
                "Add it to reachable_from_ui (with the exact UI call-site string) "
                "or intentionally_backend_only (with a reason and status)."
            )
            continue
        if in_reachable:
            entry = reachable[route]
            call_site = entry.get("call_site")
            if not call_site:
                failures.append(f"{route} — reachable_from_ui entry has no call_site")
                continue
            if call_site == "__root_document__":
                continue
            target_file = REPO / entry.get("file", "static/index.html")
            if not target_file.is_file():
                failures.append(f"{route} — target file missing: {target_file}")
                continue
            haystack = target_file.read_text(encoding="utf-8")
            if call_site not in haystack:
                failures.append(
                    f"{route} — call_site {call_site!r} no longer found in "
                    f"{target_file.relative_to(REPO)}. Either the UI call was "
                    "removed (route should be too, or reclassified) or the "
                    "manifest is stale."
                )
        if in_backend_only:
            entry = backend_only[route]
            if entry.get("status") not in ("permanent", "deferred_undecided"):
                failures.append(
                    f"{route} — intentionally_backend_only entry has an invalid "
                    f"status: {entry.get('status')!r} (must be 'permanent' or "
                    "'deferred_undecided')"
                )
            if not entry.get("reason"):
                failures.append(f"{route} — intentionally_backend_only entry has no reason")

    if failures:
        for f in failures:
            fail(f)
        print(f"[route-reachability] {len(failures)} violation(s) — see dev/ROOT_CAUSE_BUILT_NOT_MOUNTED_2026-07-23.md")
        return 1

    deferred = [r for r, e in backend_only.items() if e.get("status") == "deferred_undecided"]
    print(
        f"[route-reachability] OK — {len(live_set)} routes classified "
        f"({len(reachable)} reachable, {len(backend_only)} backend-only, "
        f"{len(deferred)} still deferred_undecided and awaiting an operator decision)"
    )
    return 0


def sync_stale() -> int:
    manifest = load_manifest()
    live_set = set(live_routes())
    all_manifest_routes = {e["route"] for e in manifest["reachable_from_ui"]} | {
        e["route"] for e in manifest["intentionally_backend_only"]
    }
    stale = sorted(all_manifest_routes - live_set)
    if not stale:
        print("[route-reachability] no stale manifest entries")
        return 0
    print(f"[route-reachability] {len(stale)} manifest entries reference routes no longer on the web surface (src/web.py + routers):")
    for route in stale:
        print(f"  - {route}")
    print("[route-reachability] remove these by hand — this command reports only, never writes.")
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["--sync-stale"]:
        sys.exit(sync_stale())
    sys.exit(check())
