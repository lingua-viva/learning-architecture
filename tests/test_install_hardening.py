"""Regression coverage for dev/specs/SPEC_INSTALL_RELEASE_PIPELINE_HARDENING_2026-07-20.md.

F-1 and F-2 are the two confirmed findings; L-1/L-2/L-3 are candidate leads
resolved with a fix in that spec's sweep (L-4 has its own file,
test_install_launcher_scripts.py; L-5 was resolved as a named decision, not
a code change -- see the hardening report).
"""
import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALL_SH = ROOT / "install.sh"
INSTALL_PS1 = ROOT / "install.ps1"


def _write_stub(bin_dir: Path, name: str, body: str) -> None:
    path = bin_dir / name
    path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


# ---------------------------------------------------------------------------
# F-1: install.sh hardcoded ARCH="arm64" for every macOS host.
# ---------------------------------------------------------------------------

def _run_detection(tmp_path: Path, uname_s: str, uname_m: str) -> str:
    """Extract and run just the OS/ARCH detection header of install.sh
    (through the "Detected" echo) under a mocked `uname`, so the real
    release-download/install side effects never run."""
    text = INSTALL_SH.read_text(encoding="utf-8")
    start = text.index("# Detect OS and architecture")
    end = text.index('echo "  ✓ Detected: ${PLATFORM}-${ARCH}"') + len(
        'echo "  ✓ Detected: ${PLATFORM}-${ARCH}"'
    )
    snippet = text[start:end]

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_stub(
        bin_dir,
        "uname",
        f'case "$1" in -s) echo "{uname_s}" ;; -m) echo "{uname_m}" ;; esac',
    )
    script = tmp_path / "detect.sh"
    script.write_text(snippet, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)

    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
    proc = subprocess.run(["/bin/sh", str(script)], capture_output=True, text=True, env=env, timeout=10)
    return proc.stdout


def test_f1_intel_mac_is_detected_as_x86_64_not_hardcoded_arm64(tmp_path):
    out = _run_detection(tmp_path, "Darwin", "x86_64")
    assert "darwin-x86_64" in out, f"expected real x86_64 detection, got: {out!r}"
    assert "darwin-arm64" not in out


def test_f1_intel_mac_gets_explicit_no_binary_warning(tmp_path):
    out = _run_detection(tmp_path, "Darwin", "x86_64")
    assert "No published macOS binary for architecture: x86_64" in out


def test_f1_apple_silicon_mac_still_detected_as_arm64(tmp_path):
    out = _run_detection(tmp_path, "Darwin", "arm64")
    assert "darwin-arm64" in out
    assert "No published macOS binary" not in out


def test_f1_skip_binary_flag_set_only_for_unsupported_mac_arch():
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert 'SKIP_BINARY="1"' in text
    assert 'if [ -z "$SKIP_BINARY" ] && curl -fsSL "$URL"' in text


def test_f1_install_sh_still_passes_posix_syntax_check():
    proc = subprocess.run(["sh", "-n", str(INSTALL_SH)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


# ---------------------------------------------------------------------------
# F-2: install.ps1 downloaded straight to the final path with no
# tempfile-stage/validate step, unlike install.sh's own pattern.
#
# No PowerShell runtime exists on this machine (confirmed: no pwsh, no
# powershell), so this can't be executed here. Coverage is structural: the
# fixed source must contain the stage-then-validate-then-move shape, and
# must no longer contain the old direct-to-final-path write.
# ---------------------------------------------------------------------------

def test_f2_install_ps1_stages_download_to_tempfile_before_moving():
    text = INSTALL_PS1.read_text(encoding="utf-8")
    assert "Invoke-WebRequest -Uri $url -OutFile $tmpFile" in text
    assert "Move-Item -Path $tmpFile -Destination \"$installDir\\lv.exe\"" in text
    assert '$downloaded.Length -gt 0' in text
    # the old direct-to-final-destination write must be gone
    assert 'Invoke-WebRequest -Uri $url -OutFile "$installDir\\lv.exe"' not in text


def test_f2_tempfile_is_cleaned_up_in_finally_block():
    text = INSTALL_PS1.read_text(encoding="utf-8")
    assert "finally {" in text
    assert "Remove-Item $tmpFile -Force -ErrorAction SilentlyContinue" in text


# ---------------------------------------------------------------------------
# L-1: INSTALL_DIR was reused with two different meanings across install.sh's
# binary branch (~/.local/bin) and source-fallback branch (~/.lingua-viva).
# Confirmed genuinely unreachable in the same invocation (binary branch
# always `exit 0`s first) -- fixed anyway by renaming the source-fallback
# copy to SRC_INSTALL_DIR to remove the shadowing risk for future refactors.
# ---------------------------------------------------------------------------

def test_l1_source_fallback_uses_distinct_variable_name():
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert 'SRC_INSTALL_DIR="${HOME}/.lingua-viva"' in text
    # the binary branch's INSTALL_DIR must still exist, distinctly
    assert 'INSTALL_DIR="${HOME}/.local/bin"' in text
    # nothing after the source-fallback clone should still read the old name
    source_fallback_start = text.index('SRC_INSTALL_DIR="${HOME}/.lingua-viva"')
    tail = text[source_fallback_start:]
    assert "$INSTALL_DIR" not in tail


def test_l1_binary_branch_always_exits_before_source_fallback_reassignment():
    """Confirms the two branches are genuinely unreachable in the same
    invocation, the premise the L-1 write-up in the report relies on."""
    text = INSTALL_SH.read_text(encoding="utf-8")
    binary_branch_start = text.index('BINARY="lv-${PLATFORM}-${ARCH}"')
    source_fallback_start = text.index('SRC_INSTALL_DIR="${HOME}/.lingua-viva"')
    between = text[binary_branch_start:source_fallback_start]
    assert "exit 0" in between


# ---------------------------------------------------------------------------
# L-2: install.sh's post-install health check discarded stderr entirely.
# ---------------------------------------------------------------------------

def test_l2_health_check_stderr_is_logged_not_discarded():
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert 'python3 -m src.lv_cli health 2>/dev/null' not in text
    assert 'HEALTH_LOG="${HOME}/.lingua-viva/install-health-stderr.log"' in text
    assert 'python3 -m src.lv_cli health 2>"$HEALTH_LOG"' in text


# ---------------------------------------------------------------------------
# L-3: install.ps1 had two empty `catch {}` blocks around Start-Process for
# the web server, silently swallowing any failure to launch.
# ---------------------------------------------------------------------------

def test_l3_server_start_catch_blocks_are_no_longer_empty():
    """Scoped to the two Start-Process call sites L-3 named (binary path,
    source-fallback path) -- NOT the lv-launch.ps1 polling loop's `catch {}`
    around a per-second Invoke-WebRequest retry, which is a legitimate
    silent-retry-until-timeout pattern mirroring install.sh's own polling
    loop, not an unreported action failure."""
    text = INSTALL_PS1.read_text(encoding="utf-8")
    assert 'Start-Process -FilePath "$installDir\\lv.exe" -ArgumentList "serve"' in text
    assert 'Start-Process -FilePath "python" -ArgumentList "-m", "src.web"' in text
    binary_start = text.index('Start-Process -FilePath "$installDir\\lv.exe" -ArgumentList "serve"')
    binary_block = text[binary_start : binary_start + 200]
    assert "} catch {}" not in binary_block

    source_start = text.index('Start-Process -FilePath "python" -ArgumentList "-m", "src.web"')
    source_block = text[source_start : source_start + 200]
    assert "} catch {}" not in source_block


def test_l3_server_start_failures_surface_the_exception_message():
    text = INSTALL_PS1.read_text(encoding="utf-8")
    assert "Couldn't start lv.exe: $($_.Exception.Message)" in text
    assert "Couldn't start the web server: $($_.Exception.Message)" in text
