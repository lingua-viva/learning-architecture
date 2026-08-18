#!/usr/bin/env python3
"""mc push — ship code to production in one command.

Encodes the full push-to-production sequence that was manually executed
dozens of times between 2026-07-05 and 2026-07-23, and automated on
2026-07-24. This script is the human-friendly interface to that automation.

Supports three contexts:
  1. mission-canvas standalone repo (has auto-release.yml)
  2. ~/fde monorepo with mission-canvas/ subtree prefix
  3. learning-architecture / Lingua Viva (manual tag-cut)

Usage:
  python3 scripts/mc_push.py              # interactive, confirms before pushing
  python3 scripts/mc_push.py --yes        # skip confirmations
  python3 scripts/mc_push.py --dry-run    # show plan without executing
  python3 scripts/mc_push.py --skip-poll  # push and exit without watching CI
  python3 scripts/mc_push.py --status     # just check current auto-release status

The Definition of Pushed (AGENTS.md §"THE Definition of 'Pushed'"):
  A stranger can click the download button on the live site right now
  and get an app that contains your change. Not "on main." Not "CI is
  green." Not "tag exists." That bar, and only that bar.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path


# ── Constants ─────────────────────────────────────────────────────────────────

MC_AUTO_RELEASE_PATHS = [
    "desktop/", "src/", "ontology/", "memory/", "sanitizer/",
    "knowledge/", "lenses/", "actions/", "static/", "templates/",
]

POLL_INTERVAL = 30  # seconds between CI status checks

# 90 minutes. Was 1800 (30 min), which was shorter than the chain has ever
# taken: the `test-gate` job ALONE measured 31m53s / 37m37s / 45m34s on
# 2026-08-03..06, before build (~5m), Pages deploy, and live-verify. The old
# value meant `mc push` reported "Timed out waiting for release pipeline" on
# every HEALTHY release, training the operator to ignore its verdict.
POLL_TIMEOUT = 5400


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolve_exe(cmd: list[str]) -> list[str]:
    """Windows (2026-08-09, PC 1): npm/npx are npm.cmd — raw CreateProcess
    cannot resolve them and dies with WinError 2 ('file not found'), which
    is how this script crashed at `npm run build` on its first real run on
    this box. shutil.which honours PATHEXT, so the launcher scripts resolve
    everywhere; a command which is genuinely absent stays as-is and fails
    with the same error it always did."""
    if cmd and os.name == "nt":
        # Explicit .cmd/.exe first: nodejs ships an EXTENSIONLESS `npm`
        # (a POSIX sh script) beside npm.cmd, and bare which() can return
        # it — CreateProcess then dies with WinError 193 (not a valid
        # Win32 application). Order matters more than existence.
        found = (shutil.which(cmd[0] + ".exe")
                 or shutil.which(cmd[0] + ".cmd")
                 or shutil.which(cmd[0] + ".bat"))
        if found:
            cmd = [found] + list(cmd[1:])
    return cmd


def run(cmd: str | list[str], cwd: str | Path | None = None,
        capture: bool = True, check: bool = True,
        timeout: int = 600) -> subprocess.CompletedProcess:
    """Run a command, return result. Raises on non-zero unless check=False.

    timeout default raised 120s→600s (2026-08-09): `npm run build` on a
    cold cache exceeded two minutes on PC 1 — a build killed by its
    wrapper's own timer read as a build failure.
    """
    if isinstance(cmd, str):
        cmd = cmd.split()
    return subprocess.run(
        _resolve_exe(cmd), capture_output=capture, text=True, cwd=cwd,
        check=check, timeout=timeout,
    )


def run_quiet(cmd: str, cwd: str | Path | None = None) -> tuple[int, str]:
    """Run, return (exit_code, stdout). Never raises."""
    try:
        r = subprocess.run(
            _resolve_exe(cmd.split()), capture_output=True, text=True,
            cwd=cwd, timeout=120,
        )
        return r.returncode, r.stdout.strip()
    except Exception as e:
        return 1, str(e)


def confirm(msg: str) -> bool:
    """Ask user for y/n confirmation."""
    try:
        return input(f"\n  {msg} [y/N] ").strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


def info(msg: str):
    print(f"  → {msg}")


def success(msg: str):
    print(f"  ✓ {msg}")


def error(msg: str):
    print(f"  ✗ {msg}", file=sys.stderr)


def warn(msg: str):
    print(f"  ! {msg}")


def heading(msg: str):
    print(f"\n{'─' * 60}")
    print(f"  {msg}")
    print(f"{'─' * 60}")


# ── Context Detection ─────────────────────────────────────────────────────────

class Context:
    """Detected push context."""
    def __init__(self):
        self.repo_root: Path = Path.cwd()
        self.kind: str = "unknown"  # "mc-standalone" | "mc-monorepo" | "lingua-viva"
        self.remote: str = "origin"
        self.branch: str = "main"
        self.gh_repo: str = ""  # owner/name for gh CLI (code repo — workflows, commits)
        self.release_repo: str = ""  # owner/name for release assets (may differ from code repo)
        self.has_auto_release: bool = False
        self.has_wizard_contract: bool = False
        self.desktop_dir: Path = Path(".")
        self.site_url: str = ""
        # Captured by step_push() immediately BEFORE pushing, because after
        # the push `@{u}..HEAD` is empty and the range is unrecoverable.
        self.pushed_files: list[str] = []
        self.head_sha: str = ""

    def detect(self) -> "Context":
        """Walk up from cwd to find the repo root and classify it."""
        # Find git root
        code, root = run_quiet("git rev-parse --show-toplevel")
        if code != 0:
            error("Not inside a git repository.")
            sys.exit(1)
        self.repo_root = Path(root)

        # Check for identifying markers
        pkg = self.repo_root / "desktop" / "package.json"
        if pkg.exists():
            name = json.loads(pkg.read_text()).get("name", "")
            if "mission-canvas" in name:
                self._detect_mc()
            elif "lingua-viva" in name:
                self._detect_lv()
            else:
                # Check if we're in the monorepo
                mc_pkg = self.repo_root / "mission-canvas" / "desktop" / "package.json"
                if mc_pkg.exists():
                    self._detect_monorepo()
                else:
                    error(f"Unrecognized desktop package: {name}")
                    sys.exit(1)
        else:
            # Maybe we're in the monorepo root
            mc_pkg = self.repo_root / "mission-canvas" / "desktop" / "package.json"
            if mc_pkg.exists():
                self._detect_monorepo()
            else:
                error("Cannot detect repo context — no desktop/package.json found.")
                sys.exit(1)

        return self

    def _detect_mc(self):
        self.kind = "mc-standalone"
        self.remote = "origin"
        self.gh_repo = "pretendhome/mission-canvas"
        self.release_repo = "pretendhome/missioncanvas.ai"
        self.has_auto_release = (self.repo_root / ".github/workflows/auto-release.yml").exists()
        self.has_wizard_contract = (self.repo_root / "scripts/check_wizard_contract.py").exists()
        self.desktop_dir = self.repo_root / "desktop"
        self.site_url = "https://missioncanvas.ai"

    def _detect_lv(self):
        self.kind = "lingua-viva"
        self.remote = "origin"
        self.gh_repo = "lingua-viva/learning-architecture"
        self.release_repo = "lingua-viva/learning-architecture"
        self.has_auto_release = (self.repo_root / ".github/workflows/auto-release.yml").exists()
        self.has_wizard_contract = (self.repo_root / "scripts/check_wizard_contract.py").exists()
        self.desktop_dir = self.repo_root / "desktop"
        self.site_url = "https://linguaviva.art"

    def _detect_monorepo(self):
        self.kind = "mc-monorepo"
        self.remote = "mission-canvas"
        self.gh_repo = "pretendhome/mission-canvas"
        self.release_repo = "pretendhome/missioncanvas.ai"
        self.has_auto_release = True
        self.has_wizard_contract = (self.repo_root / "mission-canvas/scripts/check_wizard_contract.py").exists()
        self.desktop_dir = self.repo_root / "mission-canvas" / "desktop"
        self.site_url = "https://missioncanvas.ai"


# ── Core Steps ────────────────────────────────────────────────────────────────

def step_check_clean(ctx: Context) -> bool:
    """Verify working tree is clean (or only has untracked files)."""
    code, out = run_quiet("git status --porcelain")
    dirty = [l for l in out.splitlines() if l and not l.startswith("??")]
    if dirty:
        for line in dirty[:10]:
            print(f"    {line}")
        if len(dirty) > 10:
            print(f"    ... and {len(dirty) - 10} more")
        error("Working tree has uncommitted changes — commit or stash first.")
        return False
    success("Working tree clean.")
    return True


def step_check_release_window(ctx: Context, allow_concurrent: bool) -> bool:
    """Refuse to push while a release run is holding `main`.

    THE root-cause guard, added 2026-08-06. `auto-release.yml`'s
    `version-bump-and-tag` job pushes a commit to `main`, which makes `main`
    a resource the release chain HOLDS for the whole test gate (31-45 min in
    practice). Any commit landing inside that window rejects the bump push
    non-fast-forward and kills the chain — no tag, no build, no site pin, no
    alert. That is precisely what happened on 2026-08-06: run 31111278241
    validated fead3238 for 31m53s, b3ea136b landed at 14:39Z, the bump was
    rejected at 15:04Z, and 48 commits stayed stranded behind desktop-v0.2.28
    while every other surface reported green.

    The workflow now defends itself too (`concurrency:` group + a
    rebase-and-retry bump), but the cheapest fix is not to walk into the
    window in the first place.
    """
    if not ctx.has_auto_release:
        return True

    code, out = run_quiet(
        f"gh run list --repo {ctx.gh_repo} --workflow=auto-release.yml "
        f"--limit 10 --json status,databaseId,headSha,createdAt"
    )
    if code != 0:
        info("Could not query CI for in-flight releases (gh unavailable) — continuing.")
        return True
    try:
        runs = json.loads(out) or []
    except json.JSONDecodeError:
        return True

    active = [r for r in runs
              if r.get("status") in ("queued", "in_progress", "waiting",
                                     "requested", "pending")]
    if not active:
        success("No release in flight — the window is open.")
        return True

    for r in active:
        error(f"Release IN FLIGHT: run {r.get('databaseId')} on "
              f"{str(r.get('headSha', ''))[:8]} "
              f"({r.get('status')}, started {str(r.get('createdAt', '?'))[:19]}Z)")
    error("Pushing now can reject that run's version bump and strand the release.")
    if allow_concurrent:
        info("--allow-concurrent-release set — proceeding anyway.")
        return True
    info("Wait for it to finish, or re-run with --allow-concurrent-release.")
    info(f"  Watch: gh run watch {active[-1].get('databaseId')} --repo {ctx.gh_repo}")
    return False


def step_rebuild_desktop(ctx: Context, dry_run: bool) -> bool:
    """Rebuild desktop bundle if source files are newer than built output."""
    desktop = ctx.desktop_dir
    if not (desktop / "package.json").exists():
        info("No desktop/package.json — skipping rebuild.")
        return True

    # Check if node_modules exists
    if not (desktop / "node_modules").exists():
        info("Installing desktop dependencies...")
        if not dry_run:
            r = run("npm install", cwd=desktop, check=False)
            if r.returncode != 0:
                error(f"npm install failed:\n{r.stderr[-500:]}")
                return False

    info("Rebuilding desktop bundle...")
    if dry_run:
        info("[dry-run] Would run: npm run build")
        return True

    r = run("npm run build", cwd=desktop, check=False)
    if r.returncode != 0:
        error(f"Desktop build failed:\n{r.stderr[-500:]}")
        return False

    success("Desktop bundle rebuilt.")
    return True


def _mc_root(ctx: Context) -> Path:
    """Directory containing the `mc` CLI entry point for this context."""
    if ctx.kind == "mc-monorepo":
        return ctx.repo_root / "mission-canvas"
    return ctx.repo_root


def step_electron_gate(ctx: Context, dry_run: bool, allow_app_reality_high: bool) -> bool:
    """Electron delivery gate (spec §7.8): before commit/push, verify the
    desktop app actually delivers what the catalog promises — not just that
    it compiles.

    Type-checks and rebuilds the desktop bundle, then refreshes the three
    static-analysis passes (`mc app scan --deep`, `mc eval app-reality`,
    `mc eval app-surface`) so their dev/evals/ result files are current for
    downstream consumers (mc improve, mc app check). Only app-reality
    critical/high findings can block the push, per the spec's acceptance
    criteria — app scan and app-surface are refreshed, not gated, here.
    """
    if ctx.kind not in ("mc-standalone", "mc-monorepo"):
        info("Not a Mission Canvas repo — skipping Electron delivery gate.")
        return True

    desktop = ctx.desktop_dir
    if not (desktop / "package.json").exists():
        info("No desktop/package.json — skipping Electron delivery gate.")
        return True

    mc_root = _mc_root(ctx)

    if dry_run:
        info("[dry-run] Would run: npm run typecheck && npm run build")
        info("[dry-run] Would run: ./mc app scan --deep --json")
        info("[dry-run] Would run: ./mc eval app-reality --json")
        info("[dry-run] Would run: ./mc eval app-surface --json")
        return True

    info("Type-checking desktop bundle...")
    r = run("npm run typecheck", cwd=desktop, check=False)
    if r.returncode != 0:
        error(f"Typecheck failed:\n{r.stderr[-500:]}")
        return False

    info("Rebuilding desktop bundle for gate verification...")
    r = run("npm run build", cwd=desktop, check=False)
    if r.returncode != 0:
        error(f"Desktop build failed:\n{r.stderr[-500:]}")
        return False

    # `./mc` is a POSIX sh wrapper around `python src/mc_cli.py` — Windows
    # CreateProcess dies on it (WinError 193, found live 2026-08-09).
    # Invoke the same entry point through the interpreter running THIS
    # script; identical behavior on every platform.
    _mc = [sys.executable, str(Path(mc_root) / "src" / "mc_cli.py")]

    info("Scanning experience matrix vs catalog (mc app scan --deep)...")
    r = run(_mc + ["app", "scan", "--deep", "--json"], cwd=mc_root, check=False)
    if r.returncode not in (0, 1):
        error(f"mc app scan crashed:\n{r.stderr[-500:]}")
        return False
    success("app scan result refreshed (dev/evals/).")

    info("Running app-reality eval...")
    r = run(_mc + ["eval", "app-reality", "--json"], cwd=mc_root, check=False)
    if r.returncode not in (0, 1):
        error(f"mc eval app-reality crashed:\n{r.stderr[-500:]}")
        return False
    try:
        ar_result = json.loads(r.stdout)
    except json.JSONDecodeError:
        error("Could not parse app-reality JSON output.")
        return False

    by_sev = ar_result.get("by_severity", {})
    blocking = by_sev.get("critical", 0) + by_sev.get("high", 0)
    if blocking:
        findings = [f for f in ar_result.get("findings", [])
                    if f.get("severity") in ("critical", "high")]
        error(f"app-reality has {blocking} critical/high finding(s):")
        for f in findings:
            print(f"    [{f.get('severity')}] {f.get('id')} — {f.get('title')}")
        if allow_app_reality_high:
            info("--allow-app-reality-high set — overriding, findings printed above.")
        else:
            error("Refusing to push. Fix these findings or re-run with "
                  "--allow-app-reality-high to override explicitly.")
            return False
    else:
        success("app-reality: 0 critical/high findings.")

    info("Running app-surface eval...")
    r = run(_mc + ["eval", "app-surface", "--json"], cwd=mc_root, check=False)
    if r.returncode not in (0, 1):
        error(f"mc eval app-surface crashed:\n{r.stderr[-500:]}")
        return False
    success("app-surface result refreshed (dev/evals/).")

    return True


def step_wizard_contract(ctx: Context, dry_run: bool) -> bool:
    """Check and bump wizard contract if protected files changed."""
    if not ctx.has_wizard_contract:
        return True

    if ctx.kind == "mc-monorepo":
        script = ctx.repo_root / "mission-canvas/scripts/check_wizard_contract.py"
        cwd = ctx.repo_root / "mission-canvas"
    else:
        script = ctx.repo_root / "scripts/check_wizard_contract.py"
        cwd = ctx.repo_root

    # Check
    code, out = run_quiet(f"{sys.executable} {script} --check", cwd=cwd)
    if code == 0:
        success("Wizard contract OK — no bump needed.")
        return True

    info("Wizard contract violated — bumping...")
    if dry_run:
        info("[dry-run] Would run: check_wizard_contract.py --bump")
        return True

    code, out = run_quiet(f"{sys.executable} {script} --bump", cwd=cwd)
    if code != 0:
        error(f"Contract bump failed: {out}")
        return False

    # Extract new version
    m = re.search(r"bumped to v(\d+)", out)
    new_version = int(m.group(1)) if m else None
    success(f"Wizard contract bumped to v{new_version}.")

    # Update the test assertion
    if new_version:
        _update_version_test(ctx, new_version, dry_run)

    return True


def _update_version_test(ctx: Context, version: int, dry_run: bool):
    """Update the wizard contract version assertion in the test file."""
    if ctx.kind == "mc-monorepo":
        test_file = ctx.repo_root / "mission-canvas/tests/test_capability_ux.py"
    else:
        test_file = ctx.repo_root / "tests/test_capability_ux.py"

    if not test_file.exists():
        return

    content = test_file.read_text()
    # Match the assertion line regardless of current version
    pattern = r'assert self\._contract\(\)\["version"\] == \d+'
    replacement = f'assert self._contract()["version"] == {version}'

    if re.search(pattern, content):
        new_content = re.sub(pattern, replacement, content)
        if new_content != content:
            if not dry_run:
                test_file.write_text(new_content)
            info(f"Updated test assertion to v{version}.")


def step_commit_assets(ctx: Context, dry_run: bool) -> bool:
    """Commit rebuilt assets + contract bump if anything changed."""
    if ctx.kind == "mc-monorepo":
        cwd = ctx.repo_root
        prefix = "mission-canvas/"
    else:
        cwd = ctx.repo_root
        prefix = ""

    # Check for changes
    code, status = run_quiet("git status --porcelain", cwd=cwd)
    changed = [l for l in status.splitlines() if l.strip() and not l.startswith("??")]
    if not changed:
        info("No changes to commit — source was already up to date.")
        return True

    info(f"Staging {len(changed)} changed file(s)...")
    if dry_run:
        for line in changed[:10]:
            print(f"    {line}")
        info("[dry-run] Would commit these changes.")
        return True

    # Stage relevant files
    paths_to_add = [
        f"{prefix}static/", f"{prefix}contracts/",
        f"{prefix}tests/test_capability_ux.py",
        f"{prefix}desktop/dist/",
    ]
    for p in paths_to_add:
        full = Path(cwd) / p
        if full.exists():
            run(f"git add {p}", cwd=cwd, check=False)

    # Also add any other tracked-but-modified files from the build
    run("git add -u", cwd=cwd, check=False)

    # git add -u only re-stages already-tracked files — it silently skips
    # brand-new source files (e.g. a new desktop/src/assets.d.ts). Stage new
    # (untracked, "??") files under the watched Electron/app paths
    # explicitly so a new file from this build never ships stranded outside
    # git's view. Deliberately untracked-only: staging whole directories
    # wholesale would risk sweeping in a concurrent editor's in-progress
    # work in this shared repo (see dev/HANDOFF_BUILD_TO_ELECTRON_APP_DELIVERY_2026-07-30.md).
    watched = [f"{prefix}{p}" for p in MC_AUTO_RELEASE_PATHS]
    code, status = run_quiet("git status --porcelain", cwd=cwd)
    new_untracked = [
        line[3:] for line in status.splitlines()
        if line.startswith("?? ") and any(line[3:].startswith(w) for w in watched)
    ]
    for p in new_untracked:
        run(["git", "add", p], cwd=cwd, check=False)
    if new_untracked:
        info(f"Staged {len(new_untracked)} new untracked file(s) under watched app paths.")

    # Check if staging produced anything
    code, diff = run_quiet("git diff --cached --stat", cwd=cwd)
    if not diff.strip():
        info("Nothing new to commit after staging.")
        return True

    # Commit
    msg = "chore: rebuild desktop bundle + bump wizard contract"
    r = run(["git", "commit", "-m", msg], cwd=cwd, check=False)
    if r.returncode != 0:
        if "nothing to commit" in r.stdout:
            info("Nothing to commit.")
            return True
        error(f"Commit failed: {r.stdout}\n{r.stderr}")
        return False

    success("Committed rebuilt assets.")
    return True


def _capture_push_range(ctx: Context) -> None:
    """Record exactly which files this push carries, before pushing.

    `step_trigger_release()` used to answer "will auto-release fire?" from
    `git diff HEAD~1 HEAD` — the LAST COMMIT ONLY. Push three commits where
    an earlier one touches `src/` and the last touches only `dev/`, and the
    two sides disagree: GitHub's paths filter sees the whole push and starts
    a run, while mc push sees no match and fires a `workflow_dispatch` as
    well. Two runs, both deriving the same `PATCH + 1`, racing to push a bump
    to `main` — the tool causing the very failure it exists to prevent.
    """
    code, _ = run_quiet(f"git fetch {ctx.remote} {ctx.branch}", cwd=ctx.repo_root)
    code, base = run_quiet(f"git rev-parse {ctx.remote}/{ctx.branch}",
                           cwd=ctx.repo_root)
    _, ctx.head_sha = run_quiet("git rev-parse HEAD", cwd=ctx.repo_root)
    if code != 0 or not base.strip():
        ctx.pushed_files = []
        return
    code, files = run_quiet(f"git diff --name-only {base.strip()}..HEAD",
                            cwd=ctx.repo_root)
    ctx.pushed_files = [f.strip() for f in files.splitlines() if f.strip()] if code == 0 else []


def step_push(ctx: Context, dry_run: bool) -> bool:
    """Push to remote. Handles subtree push for monorepo context."""
    if not dry_run:
        _capture_push_range(ctx)
    if dry_run:
        if ctx.kind == "mc-monorepo":
            info("[dry-run] Would run: git subtree push --prefix=mission-canvas mission-canvas main")
        else:
            info(f"[dry-run] Would run: git push {ctx.remote} {ctx.branch}")
        return True

    if ctx.kind == "mc-monorepo":
        info("Pushing via subtree (this takes a moment)...")
        r = run(
            ["git", "subtree", "push", "--prefix=mission-canvas", "mission-canvas", "main"],
            cwd=ctx.repo_root, check=False,
        )
        if r.returncode != 0:
            combined = r.stdout + r.stderr
            if "rejected" in combined or "fetch first" in combined:
                info("Remote has new commits (auto-release bumps). Pulling...")
                run(
                    ["git", "subtree", "pull", "--prefix=mission-canvas",
                     "mission-canvas", "main", "-m", "subtree: pull auto-release bumps"],
                    cwd=ctx.repo_root, check=False,
                )
                # Retry push
                r = run(
                    ["git", "subtree", "push", "--prefix=mission-canvas", "mission-canvas", "main"],
                    cwd=ctx.repo_root, check=False,
                )
            if r.returncode != 0:
                error(f"Subtree push failed:\n{r.stdout[-300:]}\n{r.stderr[-300:]}")
                return False
    else:
        info(f"Pushing to {ctx.remote}/{ctx.branch}...")
        r = run(["git", "push", ctx.remote, ctx.branch], cwd=ctx.repo_root, check=False)
        if r.returncode != 0:
            combined = r.stdout + r.stderr
            if "rejected" in combined or "fetch first" in combined:
                # Changed 2026-08-06: this used to `git pull --rebase` and
                # retry, silently. In a repo with several concurrent agent
                # windows, "the remote moved" is not noise to auto-resolve —
                # it means someone else's work just landed, possibly a release
                # bump, and rebasing onto it without looking is how you end up
                # reporting a push that shipped something you never saw. Show
                # the operator what arrived and let them decide.
                run(["git", "fetch", ctx.remote, ctx.branch],
                    cwd=ctx.repo_root, check=False)
                code, incoming = run_quiet(
                    f"git log --oneline HEAD..{ctx.remote}/{ctx.branch}",
                    cwd=ctx.repo_root,
                )
                error(f"Push rejected — {ctx.remote}/{ctx.branch} moved since you started.")
                if code == 0 and incoming.strip():
                    info("Commits that landed while you were working:")
                    for line in incoming.splitlines()[:15]:
                        print(f"    {line}")
                info("Review them, reconcile deliberately, then re-run.")
                info(f"  git log --oneline HEAD..{ctx.remote}/{ctx.branch}")
                return False
            error(f"Push failed:\n{r.stdout[-300:]}\n{r.stderr[-300:]}")
            return False

    success("Pushed to remote.")
    return True


def step_trigger_release(ctx: Context, dry_run: bool) -> str | None:
    """Trigger the release. Returns the tag name if manual, or None for auto."""
    if ctx.has_auto_release:
        # Decide from the FULL pushed range (captured pre-push), not just the
        # last commit — see _capture_push_range(). Exactly one of these two
        # branches may fire; dispatching alongside a push-triggered run is
        # what creates two racing releases.
        triggered = any(
            any(f.startswith(p) for p in MC_AUTO_RELEASE_PATHS)
            for f in ctx.pushed_files
        )
        if triggered:
            matched = sorted({f.split("/")[0] for f in ctx.pushed_files
                              if any(f.startswith(p) for p in MC_AUTO_RELEASE_PATHS)})
            success(f"Auto-release will trigger on the push ({', '.join(matched)}).")
            info("NOT sending a workflow_dispatch — a second run would race this one.")
            return None
        if not ctx.pushed_files:
            info("Could not determine the pushed range; dispatching explicitly to be safe.")
        else:
            info("Pushed paths don't match the auto-release filter — dispatching manually.")
        if not dry_run:
            run(
                ["gh", "workflow", "run", "auto-release.yml",
                 "--repo", ctx.gh_repo, "--ref", "main"],
                check=False,
            )
        success("Manual workflow_dispatch sent.")
        return None
    else:
        # Manual tag-cut (Lingua Viva pattern)
        pkg_file = ctx.desktop_dir / "package.json"
        pkg = json.loads(pkg_file.read_text())
        current = pkg["version"]
        parts = current.split(".")
        parts[-1] = str(int(parts[-1]) + 1)
        new_version = ".".join(parts)
        tag = f"desktop-v{new_version}"

        info(f"No auto-release — cutting tag: {tag}")
        if dry_run:
            info(f"[dry-run] Would bump {current} → {new_version}, tag, push")
            return tag

        # Bump version
        pkg["version"] = new_version
        pkg_file.write_text(json.dumps(pkg, indent=2) + "\n")

        # Commit + tag + push
        run(["git", "add", str(pkg_file)], cwd=ctx.repo_root)
        run(["git", "commit", "-m",
             f"chore(desktop): bump version to {new_version} for release"],
            cwd=ctx.repo_root)
        run(["git", "tag", tag], cwd=ctx.repo_root)
        run(["git", "push", ctx.remote, ctx.branch, tag], cwd=ctx.repo_root)

        success(f"Tagged and pushed {tag}.")
        return tag


def step_poll_release(ctx: Context, skip: bool, dry_run: bool,
                      head_sha: str = "") -> bool:
    """Poll OUR release run, then prove the app actually shipped.

    Two defects fixed here on 2026-08-06:

    1. `--limit 1` took whichever auto-release run was newest, with no
       correlation to the push being made. This repo runs several agent
       windows concurrently, so that is routinely somebody else's run and
       this function would report their verdict as yours. The workflow's own
       `wait-for-build-and-pin-site` job already correlates properly (by
       `headBranch == NEW_TAG`) — the tool wrapping it did not.

    2. A `conclusion == "failure"` run was reported as SUCCESS whenever
       `_verify_live()` returned True — which, before today, it always did.
       A failed pipeline is a failed push. There is no "failed but fine".

    Success now requires BOTH a green pipeline AND a live download that
    actually contains `main`. Green CI that ships nothing is the exact
    failure this file exists to prevent.
    """
    if skip or dry_run:
        info("Skipping CI poll." if skip else "[dry-run] Would poll CI.")
        return True

    heading("Watching CI...")
    start = time.time()

    # Wait a moment for the run to appear
    time.sleep(15)

    fields = "status,conclusion,databaseId,headSha,createdAt"
    while time.time() - start < POLL_TIMEOUT:
        code, out = run_quiet(
            f"gh run list --repo {ctx.gh_repo} --workflow=auto-release.yml "
            f"--limit 20 --json {fields}"
        )
        if code != 0:
            # Might be LV with desktop-release.yml
            code, out = run_quiet(
                f"gh run list --repo {ctx.gh_repo} --workflow=desktop-release.yml "
                f"--limit 20 --json {fields}"
            )

        runs = []
        if code == 0 and out.strip():
            try:
                runs = json.loads(out) or []
            except json.JSONDecodeError:
                runs = []

        # Correlate to our own push.
        mine = [r for r in runs if r.get("headSha") == head_sha] if head_sha else runs
        mine.sort(key=lambda r: r.get("createdAt", ""))

        elapsed = int(time.time() - start)
        if not mine:
            print(f"\r  ⏳ waiting for a run on {head_sha[:8] or 'main'}... ({elapsed}s)",
                  end="", flush=True)
        else:
            r = mine[-1]
            status = r.get("status", "")
            conclusion = r.get("conclusion", "")
            run_id = r.get("databaseId", "")

            if status == "completed":
                print()
                if conclusion == "success":
                    success(f"Release pipeline succeeded (run {run_id}).")
                    stale, msg = _stale_vs_main(ctx)
                    if stale:
                        error("Pipeline was green but the app did NOT ship.")
                        error(f"  {msg}")
                        return False
                    info(msg)
                    return True
                error(f"Release pipeline failed (run {run_id}, conclusion={conclusion}).")
                info(f"  Check: gh run view {run_id} --repo {ctx.gh_repo} --log-failed")
                stale, msg = _stale_vs_main(ctx)
                info(f"  Live download: {msg}")
                return False
            print(f"\r  ⏳ {status}... run {run_id} ({elapsed}s elapsed)",
                  end="", flush=True)

        time.sleep(POLL_INTERVAL)

    print()
    error(f"Timed out after {POLL_TIMEOUT // 60} min waiting for the release pipeline.")
    return False


def _verify_live(ctx: Context, expected_tag: str | None = None,
                 attempts: int = 12, delay: int = 15) -> bool:
    """Verify the live site actually serves `expected_tag`.

    Rewritten 2026-08-06. The previous implementation had four `return`
    statements and ALL FOUR returned True — no network, unreachable site,
    any tag found, no tag found. It was structurally incapable of failing,
    and it never compared what the site served against what was just
    shipped. Combined with the caller below (which treated a *failed*
    pipeline as success whenever this returned True), `mc push` would print
    "Shipped. ✓" over a release that never happened. On 2026-08-06 that is
    exactly the state the repo was in: 48 commits stranded behind the live
    tag, every surface reporting green.

    This is the same bug `_defer_to_repo_local()` below documents being
    fixed in learning-architecture on 2026-07-27 ("printed 'Live site
    serving: desktop-v0.2.10' as a success line"). That fix added a
    deferral so this stale copy stops running against LV — it never
    repaired the check itself. This does.

    `expected_tag=None` keeps the old "just report what's live" behaviour
    for `--status`, but still fails when the site serves no tag at all,
    because that means the download buttons are broken.
    """
    if not ctx.site_url:
        return True

    for i in range(1, attempts + 1):
        code, body = run_quiet(f"curl -sf {ctx.site_url}")
        if code != 0:
            info(f"  [{i}/{attempts}] could not reach {ctx.site_url}")
        else:
            tags = sorted(set(re.findall(r"desktop-v\d+\.\d+\.\d+", body)))
            if expected_tag is None:
                if tags:
                    success(f"Live site serving: {', '.join(tags)}")
                    return True
                error("No desktop-v tag on the live site — download buttons are broken.")
                return False
            # Every pinned href must be the new tag. A mixed page means the
            # site-pin sed only caught some of the 4 occurrences.
            if tags == [expected_tag]:
                success(f"Live site serving {expected_tag}.")
                return True
            if tags:
                info(f"  [{i}/{attempts}] site shows {', '.join(tags)} — waiting for {expected_tag}")
            else:
                info(f"  [{i}/{attempts}] site shows no desktop-v tag yet")
        if i < attempts:
            time.sleep(delay)

    if expected_tag:
        error(f"Live site never served {expected_tag} after ~{attempts * delay}s.")
    else:
        error(f"Could not verify the live site after ~{attempts * delay}s.")
    return False


FRESHNESS_FILE = Path.home() / ".mission-canvas" / "data" / "freshness.json"

# The whole vocabulary. `unknown` is the safe default, never `fresh`.
FRESHNESS_STATES = ("fresh", "stale", "unknown")

_LAST_FRESHNESS = ""  # in-process verdict, so the CLI never re-reads the file


def _record_freshness(state: str, message: str) -> tuple[bool, str]:
    """Store the DL-81 verdict where ignition can read it, and pass it through.

    Verdict-not-reconstruction (AGENTS.md): the real comparison happens here,
    in the only code path that holds both the live tag and `main`. Ignition
    reads the stored verdict rather than re-deriving freshness from a proxy —
    and rather than making a network call at the front door.

    Three states, because two would relearn the defect this file exists to
    catch: `unknown` (the site or gh was unreachable) must never render as
    `fresh`. The boolean return keeps the caller contract byte-identical —
    only `stale` is truthy, so exit codes are unchanged.
    """
    global _LAST_FRESHNESS
    # A typo'd state must not become a fourth state on disk. Anything not in
    # the vocabulary degrades to `unknown` — the safe direction, since only
    # `fresh` grants a green tick downstream.
    if state not in FRESHNESS_STATES:
        message = f"{message} (unrecognised verdict {state!r})"
        state = "unknown"
    _LAST_FRESHNESS = state
    try:
        FRESHNESS_FILE.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({
            "state": state,
            "message": message,
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
        # Atomic: a reader must never see a half-written verdict. Two pushes
        # racing here is ordinary on this box, and a torn file would read as
        # "verdict unreadable" — noise that looks like a real fault.
        tmp = FRESHNESS_FILE.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, FRESHNESS_FILE)
    except OSError:
        pass  # observability only — never block a push on a write failure
    return state == "stale", message


def _stale_vs_main(ctx: Context) -> tuple[bool, str]:
    """Is the live download missing release-relevant commits from main?

    THE check this whole file exists to make unnecessary, and the one thing
    nothing in the repo verified before 2026-08-06: every other gate compares
    the SITE to the RELEASE. This compares the RELEASE to `main`.

    Returns (is_stale, human_message). Every exit also records a three-state
    verdict via _record_freshness so the front door can tell "current" from
    "could not check" — see that docstring.
    """
    code, body = run_quiet(f"curl -sf {ctx.site_url}")
    if code != 0:
        return _record_freshness(
            "unknown", "could not reach the live site to check staleness")
    m = re.search(r"desktop-v\d+\.\d+\.\d+", body)
    if not m:
        return _record_freshness(
            "stale", "live site serves no desktop-v tag at all")
    live_tag = m.group(0)

    code, out = run_quiet(
        f"gh api repos/{ctx.gh_repo}/compare/{live_tag}...main "
        f"--jq {{\"ahead\":.ahead_by,\"files\":[.files[]?.filename]}}"
    )
    if code != 0:
        return _record_freshness(
            "unknown", f"could not compare {live_tag}...main via gh")
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return _record_freshness(
            "unknown", f"could not parse compare output for {live_tag}...main")

    ahead = data.get("ahead", 0)
    if not ahead:
        return _record_freshness(
            "fresh", f"live download ({live_tag}) is current with main")

    touched = sorted({
        f.split("/")[0] for f in data.get("files") or []
        if any(f.startswith(p) for p in MC_AUTO_RELEASE_PATHS)
    })
    if not touched:
        return _record_freshness("fresh", (
            f"main is {ahead} commit(s) ahead of {live_tag}, none touching "
            f"release paths — no release needed"
        ))
    return _record_freshness("stale", (
        f"live download is {live_tag} but main is {ahead} commit(s) ahead, "
        f"touching {', '.join(touched)} — users cannot download this work"
    ))


def step_status(ctx: Context):
    """Just show current pipeline status — no push."""
    heading(f"Pipeline status: {ctx.gh_repo}")

    # Latest release
    code, out = run_quiet(f"gh release list --repo {ctx.release_repo} --limit 1")
    if code == 0 and out:
        info(f"Latest release: {out.splitlines()[0]}")

    # Latest auto-release run
    code, out = run_quiet(
        f"gh run list --repo {ctx.gh_repo} --workflow=auto-release.yml "
        f"--limit 3 --json databaseId,status,conclusion,createdAt,headSha"
    )
    if code == 0 and out:
        try:
            runs = json.loads(out)
            for r in runs:
                status = r.get("status", "?")
                conclusion = r.get("conclusion", "")
                created = r.get("createdAt", "?")[:19]
                sha = r.get("headSha", "?")[:8]
                state = f"{status}/{conclusion}" if conclusion else status
                print(f"    {created}  {sha}  {state}")
        except json.JSONDecodeError:
            pass

    # Live site
    if ctx.site_url:
        code, body = run_quiet(f"curl -sf {ctx.site_url}")
        if code == 0:
            m = re.search(r"desktop-v(\d+\.\d+\.\d+)", body)
            if m:
                success(f"Live site: desktop-v{m.group(1)}")

    # The question `--status` never answered, and the reason a five-day build
    # sat invisible: is what users can download actually current with main?
    stale, msg = _stale_vs_main(ctx)
    if stale:
        error(f"STALE — {msg}")
    else:
        success(msg)


# ── Main ──────────────────────────────────────────────────────────────────────

def _defer_to_repo_local() -> None:
    """If the repo being pushed carries its own scripts/mc_push.py, run THAT.

    Root cause 2026-07-27: this MC copy was invoked against
    learning-architecture, which had a newer repo-local mc_push.py (site-pin
    bump in the release commit + hard live-pin verification, commit 2e620b5).
    The stale MC copy shipped desktop-v0.2.11, left the site pinned to
    0.2.10, and printed "Live site serving: desktop-v0.2.10" as a success
    line. Repo-local copies are authoritative for their repo — always defer.
    """
    code, root = run_quiet("git rev-parse --show-toplevel")
    if code != 0 or not root:
        return
    local = Path(root) / "scripts" / "mc_push.py"
    try:
        if local.exists() and not local.samefile(Path(__file__)):
            # flush=True: execv replaces the process image immediately, so
            # buffered stdout would be silently dropped.
            print(f"  → Repo-local mc_push.py found — deferring to {local}", flush=True)
            os.execv(sys.executable, [sys.executable, str(local)] + sys.argv[1:])
    except OSError:
        pass  # samefile/execv edge cases: fall through to this copy


def main():
    import argparse
    _defer_to_repo_local()
    parser = argparse.ArgumentParser(
        prog="mc push",
        description="Ship code to production. One command, no memory required.",
    )
    parser.add_argument("--yes", "-y", action="store_true",
                        help="Skip confirmations")
    parser.add_argument("--dry-run", "-n", action="store_true",
                        help="Show plan without executing")
    parser.add_argument("--skip-poll", action="store_true",
                        help="Push and exit without watching CI")
    parser.add_argument("--status", "-s", action="store_true",
                        help="Show pipeline status without pushing")
    parser.add_argument("--allow-app-reality-high", action="store_true",
                        help="Override the Electron delivery gate's refusal to push "
                             "when app-reality has critical/high findings")
    parser.add_argument("--allow-concurrent-release", action="store_true",
                        help="Push even while a release run is holding main "
                             "(can strand that release — see step_check_release_window)")
    parser.add_argument("--check-stale", action="store_true",
                        help="Only report whether the live download is missing "
                             "release-relevant commits from main, then exit")
    args = parser.parse_args()

    # Detect context
    ctx = Context().detect()

    heading(f"mc push — {ctx.kind}")
    info(f"Repo: {ctx.repo_root}")
    info(f"Remote: {ctx.remote}/{ctx.branch} → {ctx.gh_repo}")
    info(f"Auto-release: {'yes' if ctx.has_auto_release else 'no (manual tag-cut)'}")
    info(f"Wizard contract: {'yes' if ctx.has_wizard_contract else 'no'}")

    if args.check_stale:
        heading("Live download vs main")
        stale, msg = _stale_vs_main(ctx)
        if stale:
            error(msg)
            sys.exit(1)
        # "could not check" is not "current". It printed a green tick before
        # 2026-08-08, which is the same cannot-tell-reads-as-fine inversion
        # this check exists to catch. Exit code deliberately unchanged —
        # promoting unknown to non-zero is an operator call (see the report).
        if _LAST_FRESHNESS == "unknown":
            warn(f"{msg} — freshness UNKNOWN, not verified current")
            return
        success(msg)
        return

    if args.status:
        step_status(ctx)
        return

    # Confirm intent
    if not args.yes and not args.dry_run:
        if not confirm("Push to production?"):
            info("Aborted.")
            return

    # Execute steps
    steps = [
        ("Check working tree", lambda: step_check_clean(ctx)),
        ("Check release window", lambda: step_check_release_window(
            ctx, args.allow_concurrent_release)),
        ("Rebuild desktop", lambda: step_rebuild_desktop(ctx, args.dry_run)),
        ("Electron delivery gate", lambda: step_electron_gate(
            ctx, args.dry_run, args.allow_app_reality_high)),
        ("Wizard contract", lambda: step_wizard_contract(ctx, args.dry_run)),
        ("Commit assets", lambda: step_commit_assets(ctx, args.dry_run)),
        ("Push", lambda: step_push(ctx, args.dry_run)),
    ]

    for name, fn in steps:
        heading(name)
        result = fn()
        if result is False:
            error(f"Failed at step: {name}")
            sys.exit(1)

    # Trigger release (returns tag or None, not a bool)
    heading("Trigger release")
    step_trigger_release(ctx, args.dry_run)

    # Poll
    if not args.skip_poll:
        ok = step_poll_release(ctx, skip=False, dry_run=args.dry_run,
                               head_sha=ctx.head_sha.strip())
        if not ok:
            sys.exit(1)

    heading("Done")
    if args.skip_poll or args.dry_run:
        # Never claim the bar in this file's docstring was cleared when we
        # deliberately did not watch. "Pushed to main" is not "shipped".
        success("Pushed. Release NOT verified (--skip-poll/--dry-run).")
        info("Confirm with: python3 scripts/mc_push.py --check-stale")
    else:
        success("Shipped — pipeline green and the live download contains main. ✓")


if __name__ == "__main__":
    main()
