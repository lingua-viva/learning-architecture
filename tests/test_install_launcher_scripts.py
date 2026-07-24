"""L-4 (SPEC_INSTALL_RELEASE_PIPELINE_HARDENING_2026-07-20.md, S4): the
native-launcher heredocs embedded in install.sh (`lv-launch`) and
install.ps1 (`lv-launch.ps1`) had zero test coverage of any kind before
this file -- confirmed via `grep -rn "install\\.sh\\|install\\.ps1\\|lv-launch"
tests/`, which only turned up test_project_metadata.py reading the outer
installers as text, never the embedded launcher content, and never
executing either.

Environment constraints, named explicitly rather than implied:
- No `shellcheck` binary is installed on this machine (confirmed absent).
- No `pwsh`/`powershell` binary is installed on this machine (confirmed
  absent) -- lv-launch.ps1 cannot be executed or even PowerShell-parsed
  here. Its coverage below is limited to structural presence checks
  against the extracted text, not execution or syntax validation. A real
  Windows or `pwsh`-equipped CI runner would be needed to go further.

What IS available on this machine: /bin/sh (dash). lv-launch is a POSIX
`sh` script, so it can be both syntax-checked (`sh -n`) AND actually
executed under a sandboxed HOME with stubbed `curl`/`nc`/`lv` on PATH --
real behavioral coverage, not just a static check.
"""
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALL_SH = ROOT / "install.sh"
INSTALL_PS1 = ROOT / "install.ps1"


def _extract_between(text: str, start_marker: str, end_marker: str) -> str:
    start = text.index(start_marker) + len(start_marker)
    end = text.index(end_marker, start)
    return text[start:end]


def _extract_lv_launch_sh() -> str:
    text = INSTALL_SH.read_text(encoding="utf-8")
    return _extract_between(text, "<< 'LAUNCHEOF'\n", "\nLAUNCHEOF")


def _extract_lv_launch_ps1() -> str:
    text = INSTALL_PS1.read_text(encoding="utf-8")
    return _extract_between(text, "    @'\n", "\n'@ | Set-Content -Path $launcherPath")


def _write_stub(bin_dir: Path, name: str, body: str) -> None:
    path = bin_dir / name
    path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def test_lv_launch_sh_extractable_and_nonempty():
    script = _extract_lv_launch_sh()
    assert "#!/bin/sh" in script
    assert "Test-PortOpen" not in script  # sanity: didn't grab the ps1 block by mistake
    assert "HEALTH_URL=" in script


def test_lv_launch_sh_passes_posix_shell_syntax_check():
    script = _extract_lv_launch_sh()
    # `sh -n` (dash on this system) parses without executing -- a genuine,
    # if partial, static check in place of the unavailable shellcheck.
    proc = subprocess.run(["sh", "-n", "-c", script], capture_output=True, text=True)
    assert proc.returncode == 0, f"lv-launch heredoc has a shell syntax error: {proc.stderr}"


def test_lv_launch_sh_opens_browser_when_already_healthy(tmp_path):
    """Real behavioral exercise: health endpoint reports {"status":"healthy"}
    -> the launcher must exit 0 without attempting to start a second server."""
    script_path = tmp_path / "lv-launch"
    script_path.write_text(_extract_lv_launch_sh(), encoding="utf-8")
    script_path.chmod(script_path.stat().st_mode | stat.S_IEXEC)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # Stub curl: any invocation with the health URL returns a healthy body;
    # this covers both the notify-check call and (should it ever be
    # reached) the startup poll.
    _write_stub(bin_dir, "curl", 'echo \'{"status":"healthy"}\'')
    # If the script tried to start a real server it would look for `lv` or
    # python -- neither should be invoked in this path. Provide a stub `lv`
    # that fails loudly if called, to prove the early-exit branch is taken.
    _write_stub(bin_dir, "lv", 'echo "lv should not have been invoked" >&2; exit 1')

    env = dict(os.environ)
    env["HOME"] = str(tmp_path)
    env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"

    proc = subprocess.run(["sh", str(script_path)], capture_output=True, text=True, env=env, timeout=10)
    assert proc.returncode == 0, f"expected exit 0 on already-healthy port, got {proc.returncode}: {proc.stderr}"
    log = (tmp_path / ".lingua-viva" / "launch.log").read_text(encoding="utf-8")
    assert "already running" in log


def test_lv_launch_sh_fails_loudly_when_nothing_to_start(tmp_path):
    """No `lv` binary, no cloned source, no server running: the launcher
    must fail with a clear log message and non-zero exit, not silently
    report success (the F-1/F-2 failure shape, checked here too)."""
    script_path = tmp_path / "lv-launch"
    script_path.write_text(_extract_lv_launch_sh(), encoding="utf-8")
    script_path.chmod(script_path.stat().st_mode | stat.S_IEXEC)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # curl: health check fails (nothing is listening); nc: port is free.
    _write_stub(bin_dir, "curl", "exit 1")
    _write_stub(bin_dir, "nc", "exit 1")  # -z: non-zero means port closed

    env = dict(os.environ)
    env["HOME"] = str(tmp_path)
    # Keep only system directories after the stubs. Developer machines may
    # have a real `lv` on PATH; this test needs the no-binary branch.
    env["PATH"] = f"{bin_dir}:/usr/bin:/bin"

    proc = subprocess.run(["/bin/sh", str(script_path)], capture_output=True, text=True, env=env, timeout=10)
    assert proc.returncode == 1
    log = (tmp_path / ".lingua-viva" / "launch.log").read_text(encoding="utf-8")
    assert "re-running the installer" in log


def test_lv_launch_ps1_extractable_and_has_required_structure():
    """pwsh/powershell is not installed on this machine (confirmed), so
    lv-launch.ps1 cannot be executed or syntax-checked here -- this is a
    structural presence check only, not a behavioral test. Acknowledged
    gap: a Windows or pwsh-equipped CI runner is needed for real coverage
    of this file (see L-5 in the hardening report)."""
    script = _extract_lv_launch_ps1()
    assert "Test-PortOpen" in script
    assert "$healthUrl" in script
    assert script.count("{") == script.count("}")


def test_no_shellcheck_or_pwsh_available_here_documented():
    """Documents the acknowledged tooling gap this file works around, so a
    future run on a machine WITH these tools knows to extend coverage
    rather than assume it's already maximal."""
    import shutil

    assert shutil.which("shellcheck") is None, (
        "shellcheck is now available -- extend test coverage for install.sh/"
        "install.ps1 with real static analysis instead of sh -n only."
    )
    assert shutil.which("pwsh") is None and shutil.which("powershell") is None, (
        "A PowerShell runtime is now available -- extend "
        "test_lv_launch_ps1_extractable_and_has_required_structure into a "
        "real execution test."
    )
