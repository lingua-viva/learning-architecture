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
POLL_TIMEOUT = 1800  # 30 minutes max wait


# ── Helpers ───────────────────────────────────────────────────────────────────

def run(cmd: str | list[str], cwd: str | Path | None = None,
        capture: bool = True, check: bool = True) -> subprocess.CompletedProcess:
    """Run a command, return result. Raises on non-zero unless check=False."""
    if isinstance(cmd, str):
        cmd = cmd.split()
    return subprocess.run(
        cmd, capture_output=capture, text=True, cwd=cwd,
        check=check, timeout=120,
    )


def run_quiet(cmd: str, cwd: str | Path | None = None) -> tuple[int, str]:
    """Run, return (exit_code, stdout). Never raises."""
    try:
        r = subprocess.run(
            cmd.split(), capture_output=True, text=True, cwd=cwd, timeout=120,
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
        self.gh_repo: str = ""  # owner/name for gh CLI
        self.has_auto_release: bool = False
        self.has_wizard_contract: bool = False
        self.desktop_dir: Path = Path(".")
        self.site_url: str = ""

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
        self.has_auto_release = (self.repo_root / ".github/workflows/auto-release.yml").exists()
        self.has_wizard_contract = (self.repo_root / "scripts/check_wizard_contract.py").exists()
        self.desktop_dir = self.repo_root / "desktop"
        self.site_url = "https://missioncanvas.ai"

    def _detect_lv(self):
        self.kind = "lingua-viva"
        self.remote = "origin"
        self.gh_repo = "lingua-viva/learning-architecture"
        self.has_auto_release = (self.repo_root / ".github/workflows/auto-release.yml").exists()
        self.has_wizard_contract = (self.repo_root / "scripts/check_wizard_contract.py").exists()
        self.desktop_dir = self.repo_root / "desktop"
        self.site_url = "https://linguaviva.art"

    def _detect_monorepo(self):
        self.kind = "mc-monorepo"
        self.remote = "mission-canvas"
        self.gh_repo = "pretendhome/mission-canvas"
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


def step_push(ctx: Context, dry_run: bool) -> bool:
    """Push to remote. Handles subtree push for monorepo context."""
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
            if "rejected" in r.stdout or "fetch first" in r.stdout:
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
            if "rejected" in r.stdout or "fetch first" in (r.stdout + r.stderr):
                info("Remote ahead — pulling...")
                run(["git", "pull", "--rebase", ctx.remote, ctx.branch],
                    cwd=ctx.repo_root, check=False)
                r = run(["git", "push", ctx.remote, ctx.branch],
                        cwd=ctx.repo_root, check=False)
            if r.returncode != 0:
                error(f"Push failed:\n{r.stdout[-300:]}\n{r.stderr[-300:]}")
                return False

    success("Pushed to remote.")
    return True


def step_trigger_release(ctx: Context, dry_run: bool) -> str | None:
    """Trigger the release. Returns the tag name if manual, or None for auto."""
    if ctx.has_auto_release:
        # Check if pushed paths will trigger auto-release
        code, diff = run_quiet(
            f"git diff --name-only HEAD~1 HEAD", cwd=ctx.repo_root
        )
        triggered = any(
            any(f.startswith(p) for p in MC_AUTO_RELEASE_PATHS)
            for f in diff.splitlines()
        )
        if triggered:
            success("Auto-release will trigger (pushed paths match filter).")
            return None
        else:
            info("Pushed paths don't match auto-release filter — triggering manually...")
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
            info(f"[dry-run] Would bump {current} → {new_version}, bump site pins, tag, push")
            return tag

        # Bump version
        pkg["version"] = new_version
        pkg_file.write_text(json.dumps(pkg, indent=2) + "\n")

        # Bump site download pins in the SAME commit. Root cause of the
        # 2026-07-25 staleness trap: desktop releases are prerelease-only, so
        # /releases/latest never serves them — the site pins literal tag
        # strings, and nothing bumped them (docs/index.html sat at 0.2.7
        # through two releases while "Shipped ✓" was reported).
        site_index = ctx.repo_root / "docs" / "index.html"
        pins_bumped = 0
        if site_index.exists():
            html = site_index.read_text(encoding="utf-8")
            new_html, pins_bumped = _bump_site_pins(html, tag)
            if pins_bumped:
                site_index.write_text(new_html, encoding="utf-8")
                info(f"Bumped {pins_bumped} site download pin(s) → {tag}")

        # Commit + tag + push
        run(["git", "add", str(pkg_file)], cwd=ctx.repo_root)
        if pins_bumped:
            run(["git", "add", str(site_index)], cwd=ctx.repo_root)
        run(["git", "commit", "-m",
             f"chore(desktop): bump version to {new_version} for release"],
            cwd=ctx.repo_root)
        run(["git", "tag", tag], cwd=ctx.repo_root)
        run(["git", "push", ctx.remote, ctx.branch, tag], cwd=ctx.repo_root)

        success(f"Tagged and pushed {tag}.")
        return tag


def step_poll_release(ctx: Context, skip: bool, dry_run: bool,
                      expected_tag: str | None = None) -> bool:
    """Poll until the release is live, or timeout."""
    if skip or dry_run:
        info("Skipping CI poll." if skip else "[dry-run] Would poll CI.")
        return True

    heading("Watching CI...")
    start = time.time()

    # Wait a moment for the run to appear
    time.sleep(15)

    while time.time() - start < POLL_TIMEOUT:
        code, out = run_quiet(
            f"gh run list --repo {ctx.gh_repo} --workflow=auto-release.yml "
            f"--limit 1 --json status,conclusion,databaseId"
        )
        if code != 0:
            # Might be LV with desktop-release.yml
            code, out = run_quiet(
                f"gh run list --repo {ctx.gh_repo} --workflow=desktop-release.yml "
                f"--limit 1 --json status,conclusion,databaseId"
            )

        if code == 0 and out.strip():
            try:
                runs = json.loads(out)
                if runs:
                    r = runs[0]
                    status = r.get("status", "")
                    conclusion = r.get("conclusion", "")
                    run_id = r.get("databaseId", "")

                    if status == "completed":
                        if conclusion == "success":
                            success(f"Release pipeline succeeded (run {run_id}).")
                            return _verify_live(ctx, expected_tag)
                        elif conclusion == "failure":
                            # Check if it's the live-verify cosmetic failure
                            # where the actual site IS pinned correctly
                            if _verify_live(ctx, expected_tag):
                                success(f"Pipeline reported failure but site is live and correct.")
                                return True
                            error(f"Release pipeline failed (run {run_id}).")
                            info(f"  Check: gh run view {run_id} --repo {ctx.gh_repo} --log-failed")
                            return False
                    else:
                        elapsed = int(time.time() - start)
                        print(f"\r  ⏳ {status}... ({elapsed}s elapsed)", end="", flush=True)
            except json.JSONDecodeError:
                pass

        time.sleep(POLL_INTERVAL)

    print()
    error("Timed out waiting for release pipeline.")
    return False


def _bump_site_pins(html: str, tag: str) -> tuple[str, int]:
    """Rewrite every desktop-vX.Y.Z pin in site HTML to the given tag.

    Returns (new_html, pin_count). Pure function so it's testable.
    """
    return re.subn(r"desktop-v\d+\.\d+\.\d+", tag, html)


def _check_site_pins(body: str, expected_tag: str) -> tuple[list[str], list[str]]:
    """Compare pins found in live-site HTML against the just-cut tag.

    Returns (served, stale): all distinct pins found, and those that differ
    from expected_tag. Pure function so it's testable.
    """
    served = sorted(set(re.findall(r"desktop-v\d+\.\d+\.\d+", body)))
    stale = [v for v in served if v != expected_tag]
    return served, stale


def _verify_live(ctx: Context, expected_tag: str | None = None) -> bool:
    """Verify the live site serves the release we just cut.

    Without expected_tag (MC auto-release path): informational only — report
    what's served, never fail. With expected_tag (LV manual tag-cut): "a
    version string is present" is NOT the same claim as "the version we just
    cut is live" — fail on any stale pin, and verify the actual download
    URLs resolve. This closes the 2026-07-25 gap where this function grepped
    for any desktop-v string and reported success over a two-release-stale
    site.
    """
    if not ctx.site_url:
        return True

    code, body = run_quiet(f"curl -sf {ctx.site_url}")
    if code != 0:
        info("Could not reach live site for verification.")
        return True  # Don't fail on network issues

    if expected_tag is None:
        m = re.search(r"desktop-v(\d+\.\d+\.\d+)", body)
        if m:
            success(f"Live site serving: desktop-v{m.group(1)}")
        else:
            info("No desktop-v tag found on live site (site may not have download links).")
        return True

    served, stale = _check_site_pins(body, expected_tag)
    if not served:
        error(f"Live site has no desktop-v pin at all — expected {expected_tag}.")
        return False
    if stale:
        error(f"Live site pin(s) STALE: {', '.join(stale)} (expected {expected_tag}).")
        info("The site HTML with the new pin hasn't deployed — do not report shipped.")
        return False
    success(f"Live site pinned to {expected_tag}.")

    # A correct pin doesn't prove the assets exist — check the download URLs.
    urls = [u for u in re.findall(r'href="([^"]*?/releases/download/[^"]*?)"', body)
            if expected_tag in u]
    for u in urls:
        code, status = run_quiet(
            f"curl -sI -o /dev/null -w %{{http_code}} -L {u}")
        if code != 0 or status.strip() != "200":
            error(f"Download URL not live ({status.strip() or 'unreachable'}): {u}")
            return False
    if urls:
        success(f"{len(urls)} download URL(s) verified live.")
    return True


def step_status(ctx: Context):
    """Just show current pipeline status — no push."""
    heading(f"Pipeline status: {ctx.gh_repo}")

    # Latest release
    code, out = run_quiet(f"gh release list --repo {ctx.gh_repo} --limit 1")
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


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    import argparse
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
    args = parser.parse_args()

    # Detect context
    ctx = Context().detect()

    heading(f"mc push — {ctx.kind}")
    info(f"Repo: {ctx.repo_root}")
    info(f"Remote: {ctx.remote}/{ctx.branch} → {ctx.gh_repo}")
    info(f"Auto-release: {'yes' if ctx.has_auto_release else 'no (manual tag-cut)'}")
    info(f"Wizard contract: {'yes' if ctx.has_wizard_contract else 'no'}")

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
        ("Rebuild desktop", lambda: step_rebuild_desktop(ctx, args.dry_run)),
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
    tag = step_trigger_release(ctx, args.dry_run)

    # Poll — pass the just-cut tag so live verification compares against it
    # instead of accepting any version string on the site.
    if not args.skip_poll:
        ok = step_poll_release(ctx, skip=False, dry_run=args.dry_run,
                               expected_tag=tag)
        if not ok:
            sys.exit(1)

    heading("Done")
    success("Shipped. ✓")


if __name__ == "__main__":
    main()
