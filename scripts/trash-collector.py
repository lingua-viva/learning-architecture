#!/usr/bin/env python3
"""trash-collector — production-unreachable code, made visible.

ADVISORY. It never blocks a push and it never deletes anything. See
`dev/SPEC_TRASH_COLLECTOR_2026-09-01.md` §2 for why, with the numbers: a blocking
dead-code check needs zero effective false positives, ours measured 10.3%, and a
blocking check of this kind is trivially satisfiable without deleting anything —
add a call site in a dead branch, re-export the symbol, extend the allowlist. A
human feels shame doing that; an agent experiences it as the cheapest path to green.

THE CLASS IT DETECTS — three conditions, all required:
  1. defined in a module production imports
  2. exercised by a passing test
  3. zero production call sites reachable from a declared root

Every existing signal reads this as fine: import reachability says alive, coverage
says tested, the test passes, the code is correct — and the function never runs.
Nothing else here distinguishes *covered* from *reached*.

FOUR PROPERTIES, each load-bearing (spec §3):

  Roots are DECLARED, never inferred      config/reachability_roots.yaml
      One packaging entry point exists and 29 `__main__` blocks do. Neither set is
      the answer, and an inferred root set makes the verdict depend on a heuristic
      nobody agreed to. An undeclared entry point is a finding, not a default.

  Tests and their subject share one fate  (SCC)
      Excluding tests from the root set makes every tested-but-dead unit look alive.
      Google's Sensenmann binds unit and test into a strongly connected component so
      the test's own disposition falls out of the graph. Here that pairing is
      reported: a finding names the tests that hold it up, because they go together.

  NO public-symbol amnesty
      staticcheck: "all exported package-level identifiers will be considered used."
      rustc's dead_code covers "unexported" items only. Python has no `pub`, so a
      detector that exempts public names finds nothing and reports green — which
      would make it a fresh instance of the class it exists to detect.

  Resolved symbols, never bare names
      `print_report` is defined 13 times in src/. Under name matching one test
      touching any one of them marks all thirteen live. Definitions here are
      module-qualified, and every call site is resolved through the importing
      module's own namespace before it counts.

KNOWN OVER-APPROXIMATION, stated rather than hidden: a method call `x.foo()` cannot
be resolved to a receiver type by static analysis alone, so it links to every method
named `foo`. That direction is deliberate — it marks more code live, so the tool
UNDER-reports. A finding survived that bias; a non-finding did not prove anything.

    exit 0   checked, clean
    exit 1   checked, findings
    exit 2   CANNOT-TELL — no declared roots, undeclared entry points,
             unparseable modules, or blame unavailable in --since mode
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "config" / "reachability_roots.yaml"

SRC = "src"
TEST_DIR = "tests"
SKIP_PARTS = {"__pycache__", "node_modules"}

MOD = "<module>"          # the module body itself — runs on import


# ── model ────────────────────────────────────────────────────────────


def _rel(p: Path) -> str:
    return str(p.relative_to(ROOT)).replace("\\", "/")


def _py_files(sub: str) -> list[Path]:
    base = ROOT / sub
    if not base.is_dir():
        return []
    return [p for p in base.rglob("*.py")
            if not any(part in SKIP_PARTS for part in p.parts)]


def _module_name(rel: str) -> str:
    return rel[:-3].replace("/", ".")


_FRAMEWORK_REGISTRATION_ATTRS = {
    "get", "post", "put", "patch", "delete", "websocket", "on_event",
    "middleware", "exception_handler", "api_route", "head", "options",
}


def _is_framework_registration(dec: ast.AST) -> bool:
    """`@x.get(...)` / `@x.post(...)` / `@x.on_event(...)` / `@x.middleware(...)`:
    a decorator CALL whose attribute is a FastAPI/Starlette registration verb."""
    if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
        return dec.func.attr in _FRAMEWORK_REGISTRATION_ATTRS
    return False


class Analyzer:
    """Builds a module-qualified symbol graph over `src/`."""

    def __init__(self) -> None:
        self.defs: dict[str, dict[str, Any]] = {}     # symbol id -> info
        self.edges: dict[str, set[str]] = defaultdict(set)
        self.by_name: dict[str, list[str]] = defaultdict(list)
        self.module_of: dict[str, str] = {}           # module name -> rel path
        self.unparseable: list[str] = []

    # -- pass 1: every definition, module-qualified -------------------

    def collect_defs(self, files: list[Path]) -> None:
        for p in files:
            rel = _rel(p)
            mod = _module_name(rel)
            self.module_of[mod] = rel
            try:
                tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
            except SyntaxError:
                self.unparseable.append(rel)
                continue
            body_id = f"{mod}::{MOD}"
            self.defs[body_id] = dict(module=mod, file=rel, line=1, qual=MOD, kind="module")
            self._walk_defs(tree, mod, rel, prefix="")

    def _walk_defs(self, node: ast.AST, mod: str, rel: str, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                cid = f"{mod}::{prefix}{child.name}"
                self.defs[cid] = dict(module=mod, file=rel, line=child.lineno,
                                      qual=f"{prefix}{child.name}", kind="class",
                                      name=child.name, doc=(ast.get_docstring(child) or ""))
                self.by_name[child.name].append(cid)
                self._walk_defs(child, mod, rel, prefix=f"{prefix}{child.name}.")
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qual = f"{prefix}{child.name}"
                sid = f"{mod}::{qual}"
                self.defs[sid] = dict(module=mod, file=rel, line=child.lineno,
                                      qual=qual, kind="method" if prefix else "function",
                                      name=child.name,
                                      doc=(ast.get_docstring(child) or ""))
                self.by_name[child.name].append(sid)
                # nested defs belong to their enclosing function, not the module
                self._walk_defs(child, mod, rel, prefix=f"{prefix}{child.name}.")

    # -- pass 2: edges -----------------------------------------------

    def link_constructors(self) -> None:
        """`ClassName(...)` resolves to the class; the call that actually runs is
        `__init__`. Without this edge every constructor in the repo is flagged —
        70 of them were, 17% of all findings, before the link existed."""
        for sid in list(self.defs):
            if sid.endswith(".__init__"):
                self.edges[sid.rsplit(".__init__", 1)[0]].add(sid)

    def collect_edges(self, files: list[Path]) -> None:
        for p in files:
            rel = _rel(p)
            mod = _module_name(rel)
            try:
                tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
            except SyntaxError:
                continue
            imports = self._imports(tree, mod)
            self._edges_in(tree, mod, imports, owner=f"{mod}::{MOD}", prefix="")

    def _imports(self, tree: ast.AST, mod: str) -> dict[str, str]:
        """local name -> symbol id or module id it refers to."""
        out: dict[str, str] = {}
        pkg = mod.rsplit(".", 1)[0] if "." in mod else ""
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                target = node.module or ""
                if node.level and pkg:                       # relative import
                    target = f"{pkg}.{target}" if target else pkg
                for a in node.names:
                    local = a.asname or a.name
                    if f"{target}.{a.name}" in self.module_of:      # from pkg import module
                        out[local] = f"{target}.{a.name}::{MOD}"
                    else:
                        out[local] = f"{target}::{a.name}"
            elif isinstance(node, ast.Import):
                for a in node.names:
                    out[a.asname or a.name.split(".")[0]] = f"{a.name}::{MOD}"
        return out

    def _edges_in(self, node: ast.AST, mod: str, imports: dict[str, str],
                  owner: str, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                self._edges_in(child, mod, imports, owner, prefix=f"{prefix}{child.name}.")
                continue
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qual = f"{prefix}{child.name}"
                self._edges_in(child, mod, imports, owner=f"{mod}::{qual}",
                               prefix=f"{prefix}{child.name}.")
                # a decorator reference is a real edge from the enclosing scope
                for dec in child.decorator_list:
                    for t in self._targets(dec, mod, imports):
                        self.edges[owner].add(t)
                    # LV port (2026-09-03): FastAPI/Starlette register the DECORATED
                    # function as a handler at import time — `@app.get(...)`,
                    # `@router.post(...)`, `@app.on_event(...)`, `@app.middleware(...)`,
                    # `@app.exception_handler(...)`, `@app.websocket(...)`. Nothing
                    # ever names the handler again, so without this edge every
                    # route in web.py and the routers reads as unreached. Same
                    # class as MC's http.server `do_GET` convention, expressed as
                    # a graph edge instead of an allowlist so the handler's own
                    # callees are reached too.
                    if _is_framework_registration(dec):
                        self.edges[owner].add(f"{mod}::{qual}")
                # LV port (2026-09-03): a function NESTED in a function is live
                # when its parent is. LV's web surface passes closures to
                # `_with_student_store(do_x)` on nearly every route; a bare-name
                # lookup cannot resolve `do_x` to `handler.do_x`, so every store
                # call inside those closures read as unreached (set_initial_cefr,
                # delete_lens, ... all flagged while being the live path). Safe
                # direction: marks more live, so the tool under-reports.
                if owner != f"{mod}::{MOD}" and prefix:
                    self.edges[owner].add(f"{mod}::{qual}")
                continue
            self._reference_edges(child, mod, imports, owner)
            self._edges_in(child, mod, imports, owner, prefix)

    def _reference_edges(self, node: ast.AST, mod: str, imports: dict[str, str],
                         owner: str) -> None:
        for t in self._targets(node, mod, imports):
            self.edges[owner].add(t)

    def _targets(self, node: ast.AST, mod: str, imports: dict[str, str]) -> list[str]:
        """Resolve one node to the symbols it could reach."""
        out: list[str] = []
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name):
                out += self._resolve_name(f.id, mod, imports)
            elif isinstance(f, ast.Attribute):
                # receiver type is not statically known: over-approximate to every
                # method of that name. Biases toward "live", so we under-report.
                out += list(self.by_name.get(f.attr, []))
                if isinstance(f.value, ast.Name) and f.value.id in imports:
                    tgt = imports[f.value.id]
                    if tgt.endswith(f"::{MOD}"):
                        out.append(f"{tgt.split('::')[0]}::{f.attr}")
        elif isinstance(node, ast.Attribute):
            # A plain attribute READ reaches a @property getter: `lens.display_name`
            # never calls anything by name, so without this edge every property in
            # the repo is flagged. 38 of 55 were, including `constituent_ids`, which
            # a test in another lane asserts on directly. Same over-approximation as
            # method calls, and in the same safe direction — it marks more live.
            out += list(self.by_name.get(node.attr, []))
        elif isinstance(node, ast.Name):
            out += self._resolve_name(node.id, mod, imports)      # callback / alias
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for local, tgt in imports.items():
                if tgt in self.defs or tgt.endswith(f"::{MOD}"):
                    out.append(tgt)
        return [t for t in out if t in self.defs]

    def _resolve_name(self, name: str, mod: str, imports: dict[str, str]) -> list[str]:
        local = f"{mod}::{name}"
        if local in self.defs:
            return [local]
        if name in imports and imports[name] in self.defs:
            return [imports[name]]
        return []

    # -- reachability -------------------------------------------------

    def reachable(self, roots: list[str]) -> set[str]:
        seen: set[str] = set()
        stack = [r for r in roots if r in self.defs]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            # importing a module runs its body
            m = cur.split("::")[0]
            body = f"{m}::{MOD}"
            if body in self.defs and body not in seen:
                stack.append(body)
            stack.extend(self.edges.get(cur, ()))
        return seen


# ── test references ──────────────────────────────────────────────────


def test_references() -> dict[str, list[str]]:
    """symbol NAME -> test files referencing it. Names, deliberately: a test's
    reference is evidence the symbol is exercised, and pinning it to one definition
    is exactly what the SCC pairing reports rather than asserts."""
    refs: dict[str, set[str]] = defaultdict(set)
    for p in _py_files(TEST_DIR):
        rel = _rel(p)
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                refs[node.id].add(rel)
            elif isinstance(node, ast.Attribute):
                refs[node.attr].add(rel)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for a in node.names:
                    refs[a.name].add(rel)
    return {k: sorted(v) for k, v in refs.items()}


# ── the ratchet ──────────────────────────────────────────────────────


def introduced_after(file: str, line: int, ref: str) -> bool | None:
    """Was this line introduced outside `ref`'s history? None = blame unavailable.

    SCM-diff lineage rather than a committed baseline file: every documented
    baseline pathology — merge conflicts, regenerate-to-bypass, stale entries,
    churn that punishes improvement — belongs to the committed-file lineage, and
    this box carries 45 worktrees.
    """
    try:
        out = subprocess.run(
            ["git", "blame", "-L", f"{line},{line}", "--porcelain", "--", file],
            cwd=ROOT, capture_output=True, text=True, timeout=60,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return None
        sha = out.stdout.split()[0]
        anc = subprocess.run(["git", "merge-base", "--is-ancestor", sha, ref],
                             cwd=ROOT, capture_output=True, timeout=60)
        return anc.returncode != 0
    except (OSError, subprocess.SubprocessError):
        return None


# ── main ─────────────────────────────────────────────────────────────


def allow_category(sid: str, info: dict[str, Any], allow: list[dict]) -> str | None:
    """Which named allowlist category covers this symbol, if any.

    Allowed symbols are COUNTED and reported as a category total, never dropped in
    silence — an allowlist nobody can audit is how a detector goes quietly blind.
    """
    import re as _re
    rel_sid = f"{info['file']}::{info['qual']}"
    doc = (info.get("doc") or "").lower()
    for rule in allow:
        if any(rel_sid == s for s in (rule.get("symbols") or [])):
            return rule["category"]
        rx = rule.get("name_regex")
        if rx and _re.match(rx, info["name"]):
            return rule["category"]
        for marker in (rule.get("docstring_markers") or []):
            if marker.lower() in doc:
                return rule["category"]
    return None


def _root_id(symbol: str) -> str:
    """Manifest symbol -> graph node id.

    `module.py::__main__` means "the module body is the entry point" — a few
    surfaces build their server at import time and their `__main__` only calls
    `.run()`, so there is no function to name. That maps to the module-body node.
    """
    mod, _, qual = symbol.partition("::")
    return f"{_module_name(mod)}::{MOD if qual == '__main__' else qual}"


def load_manifest(path: Path | None = None) -> tuple[list[dict], list[str], str]:
    manifest = path or MANIFEST
    if not manifest.is_file():
        return [], [], f"no root manifest at {manifest}"
    try:
        import yaml
        data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    except Exception as exc:                                   # noqa: BLE001
        return [], [], f"manifest unreadable: {exc}"
    roots = data.get("roots") or []
    not_roots = [n.get("module") for n in (data.get("not_roots") or [])]
    load_manifest.allow = data.get("allow") or []
    if not roots:
        return [], not_roots, "manifest declares no roots"
    return roots, not_roots, ""


def undeclared_entry_points(roots: list[dict], not_roots: list[str]) -> list[str]:
    declared = {r["symbol"].split("::")[0] for r in roots} | set(not_roots)
    out = []
    for p in _py_files(SRC):
        try:
            if "__main__" in p.read_text(encoding="utf-8", errors="replace"):
                if _rel(p) not in declared:
                    out.append(_rel(p))
        except OSError:
            continue
    return sorted(out)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--roots", metavar="PATH", type=Path,
                    help="override the root manifest (used by the acceptance corpus "
                         "to prove a wrong/empty manifest exits 2, never 0)")
    ap.add_argument("--since", metavar="REF",
                    help="report only findings introduced outside REF's history "
                         "(SCM-diff ratchet; blame unavailable => CANNOT-TELL)")
    args = ap.parse_args(argv)

    roots_decl, not_roots, err = load_manifest(args.roots)
    if err:
        # targets=0 stated explicitly: an instrument that cannot name its
        # denominator has not measured anything, and zero targets is never a pass.
        print(f"CANNOT-TELL: {err}")
        print("  targets=0 (symbols_analysed=0, roots_declared=0) — nothing was checked.")
        print("  Reachability without declared roots is not a weaker measurement, "
              "it is a different one.")
        return 2

    undeclared = undeclared_entry_points(roots_decl, not_roots)

    an = Analyzer()
    files = _py_files(SRC)
    an.collect_defs(files)
    an.collect_edges(files)
    an.link_constructors()

    def root_ids(kind: str) -> list[str]:
        ids = []
        for r in roots_decl:
            if r.get("kind") != kind:
                continue
            ids.append(_root_id(r["symbol"]))
        return ids

    kinds = ("product", "eval", "script")
    reach = {k: an.reachable(root_ids(k)) for k in kinds}
    unresolved_roots = [r["symbol"] for r in roots_decl
                        if _root_id(r["symbol"]) not in an.defs]

    trefs = test_references()

    findings = []
    counts = defaultdict(int)
    allowed_by_cat = defaultdict(int)
    for sid, info in sorted(an.defs.items()):
        if info["qual"] == MOD or info["kind"] == "class":
            continue
        counts["analysed"] += 1
        if sid in reach["product"]:
            counts["product"] += 1
            continue
        if sid in reach["eval"]:
            counts["eval_only"] += 1
            continue
        if sid in reach["script"]:
            counts["script_only"] += 1
            continue
        tests = trefs.get(info["name"], [])
        if not tests:
            counts["unreferenced"] += 1        # plain dead code; a different class
            continue
        if info["name"].startswith("__") and info["name"].endswith("__"):
            # Invoked by protocol, never by name: `with` calls __enter__, `==` calls
            # __eq__, and instantiation calls __init__ through the class. No static
            # name graph can see those, so flagging them is the tool's blindness
            # rather than the codebase's defect.
            counts["protocol_dunder"] += 1
            continue
        cat = allow_category(sid, info, getattr(load_manifest, "allow", []))
        if cat:
            counts["allowed"] += 1
            allowed_by_cat[cat] += 1
            continue
        counts["finding"] += 1
        findings.append(dict(symbol=sid, file=info["file"], line=info["line"],
                             name=info["name"], kind=info["kind"], tests=tests))

    # Module granularity (census §5.2): reported per-symbol, the content-index
    # cluster reads as seven problems and ops/records as five, when the unit that
    # is actually wrong is the module. Two levels, and the difference between them
    # is what the graph can prove:
    #
    #   unwired  NO symbol of the module is reachable from any root — a verdict
    #   cluster  >=3 findings in one module, some symbols still reachable — a
    #            GROUPING for readability, not a claim that the module is dead
    #
    # The census's F1 says "no production entry point imports admissible_search".
    # This graph cannot confirm that: the module body resolves as reached, so the
    # weaker, provable statement is the one reported.
    reachable_any = reach["product"] | reach["eval"] | reach["script"]
    per_module: dict[str, list[dict]] = defaultdict(list)
    for f in findings:
        per_module[f["file"]].append(f)

    module_findings, clusters = [], []
    for mod_file, fs in sorted(per_module.items()):
        syms = [s for s, i in an.defs.items()
                if i["file"] == mod_file and i["qual"] != MOD]
        reached = [s for s in syms if s in reachable_any]
        if syms and not reached:
            module_findings.append(dict(file=mod_file, symbols=len(syms),
                                        flagged=len(fs),
                                        names=sorted(x["name"] for x in fs)))
        elif len(fs) >= 3:
            clusters.append(dict(file=mod_file, symbols=len(syms),
                                 flagged=len(fs), reached=len(reached),
                                 names=sorted(x["name"] for x in fs)))
    grouped = {m["file"] for m in module_findings} | {c["file"] for c in clusters}
    findings = [f for f in findings if f["file"] not in grouped]

    if args.since:
        kept, blame_failed = [], 0
        for f in findings:
            v = introduced_after(f["file"], f["line"], args.since)
            if v is None:
                blame_failed += 1
            elif v:
                kept.append(f)
        if blame_failed:
            print(f"CANNOT-TELL: git blame unavailable for {blame_failed} finding(s); "
                  f"a ratchet that cannot read history reports nothing clean.")
            return 2
        findings = kept

    result = dict(findings=findings, module_findings=module_findings,
                  clusters=clusters, counts=dict(counts),
                  allowed_by_category=dict(allowed_by_cat),
                  roots_declared=len(roots_decl),
                  unresolved_roots=unresolved_roots,
                  undeclared_entry_points=undeclared,
                  unparseable=an.unparseable)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        report(result)

    if counts.get("analysed", 0) == 0:
        print("\n  CANNOT-TELL: targets=0 — no symbols were analysed. "
              "An empty corpus cannot be clean.")
        return 2
    if unresolved_roots or undeclared or an.unparseable:
        return 2
    return 1 if (findings or module_findings or clusters) else 0


def report(r: dict[str, Any]) -> None:
    c = r["counts"]
    print("trash-collector — production-unreachable code (ADVISORY; deletes nothing)")
    print(f"  roots declared      : {r['roots_declared']}")
    print(f"  symbols analysed    : {c.get('analysed', 0)}   "
          f"targets={c.get('analysed', 0)}")
    print(f"    reached: product  : {c.get('product', 0)}")
    print(f"    reached: eval only: {c.get('eval_only', 0)}")
    print(f"    reached: script   : {c.get('script_only', 0)}")
    print(f"    no refs at all    : {c.get('unreferenced', 0)}  (plain dead code — a different class)")
    print(f"    protocol dunders  : {c.get('protocol_dunder', 0)}  "
          f"(__init__/__enter__/… — invoked by protocol, not by name)")
    print(f"    allowlisted       : {c.get('allowed', 0)}  " +
          (", ".join(f"{k}={v}" for k, v in sorted(r.get("allowed_by_category", {}).items()))
           or "none"))
    print(f"  FINDINGS            : {c.get('finding', 0)}  (tested, and never reached from a root)")
    nm, nc = r.get("module_findings", []), r.get("clusters", [])
    print(f"    grouped           : {sum(m['flagged'] for m in nm)} into {len(nm)} unwired module(s)"
          f" · {sum(c['flagged'] for c in nc)} into {len(nc)} cluster(s)")

    if r["unresolved_roots"]:
        print(f"\n  CANNOT-TELL — {len(r['unresolved_roots'])} declared root(s) do not resolve:")
        for s in r["unresolved_roots"]:
            print(f"    {s}")
    if r["undeclared_entry_points"]:
        print(f"\n  CANNOT-TELL — {len(r['undeclared_entry_points'])} undeclared entry point(s). "
              f"An undeclared entry point is a finding, not a default:")
        for s in r["undeclared_entry_points"]:
            print(f"    {s}")
    if r["unparseable"]:
        print(f"\n  CANNOT-TELL — {len(r['unparseable'])} module(s) did not parse:")
        for s in r["unparseable"]:
            print(f"    {s}")

    if not r["findings"]:
        print("\n  No findings.")
        return

    print("\n  Each finding is a TESTING DEFECT, not a deletion order. Usually the test")
    print("  reaches into a helper instead of exercising the path that should call it.")
    print("  Dispositions: MOUNT (wire the guarantee) · DELETE (remove code and test")
    print("  together) · PENDING (deliberately unreached, waiting on X — say what).\n")
    for f in sorted(r["findings"], key=lambda x: (x["file"], x["line"])):
        print(f"  {f['file']}:{f['line']} {f['name']}  [{f['kind']}]")
        print(f"      no production call site reachable from a declared root.")
        print(f"      Either delete it, or test it through the caller that should exist.")
        print(f"      held up by: {', '.join(f['tests'][:3])}"
              + (f" (+{len(f['tests']) - 3})" if len(f["tests"]) > 3 else ""))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
