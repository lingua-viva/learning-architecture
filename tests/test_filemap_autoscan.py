"""Filemap auto-scan on startup — Gap 2.

Spec: SPEC_LV_REMAINING_GAPS_2026-07-29.md Gap 2.

LV's scan already knew about education domains, student-data zones and
bilingual keywords. What it lacked was the automatic trigger: nothing ran
unless a teacher pressed a button, which makes "local-first" hollow.

The spec says to port MC's `auto_scan_on_startup()`. That symbol does not
exist in MC — `src/filemap.py` has no such function, and the cited line 516
is inside `generate_lens_claims` — so this is written for LV's shape instead.

The guard is the part worth testing hardest. Without it, a test run would
scan the developer's real home directory: slow, and reading personal files
that have nothing to do with the test. `LV_AGENT=1` is the documented
convention, but the pytest check is what makes the unsafe default
unreachable by forgetting an env var.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from src.lingua_viva import filemap

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def isolated_map(tmp_path, monkeypatch):
    monkeypatch.setenv("LV_FILE_MAP_PATH", str(tmp_path / "file_map.yaml"))
    filemap._set_scan_in_progress(False)
    yield
    filemap._set_scan_in_progress(False)


@pytest.fixture
def scan_home(request):
    """A scan root whose absolute path contains no privacy marker.

    pytest's tmp_path lives under /private/var/... on macOS, and "private" is
    both a PRIVACY_PATH_MARKER and a STUDENT_DATA_KEYWORD matched against the
    FULL absolute path — so a tree built there is classified as a student zone
    in its entirety and never scanned. That silently turned the student-zone
    assertion below green for the wrong reason (nothing was indexed, so no
    student folder was indexed either).

    Building under the repo directory keeps the marker matching honest. The
    underlying substring-on-absolute-path behaviour is a real latent issue —
    a teacher with ~/Documents/private/Teaching loses their whole tree — but
    fixing it means changing privacy-critical exclusion logic, which belongs
    in its own change, not smuggled into an auto-scan test.
    """
    base = REPO / ".pytest-scan-home" / request.node.name
    if base.exists():
        shutil.rmtree(base, ignore_errors=True)
    base.mkdir(parents=True)
    yield base
    shutil.rmtree(REPO / ".pytest-scan-home", ignore_errors=True)


def _tree(root):
    for folder in ("curriculum/G3", "assessment/rubrics", "Students/reports"):
        (root / folder).mkdir(parents=True, exist_ok=True)
    (root / "curriculum" / "G3" / "unit.pdf").write_text("x", encoding="utf-8")
    (root / "assessment" / "rubrics" / "rubric.pdf").write_text("x", encoding="utf-8")
    (root / "Students" / "reports" / "private.txt").write_text("x", encoding="utf-8")
    return root


# --- the guard --------------------------------------------------------------


def test_pytest_alone_is_enough_to_block_the_scan():
    """Load-bearing: a test that forgets LV_AGENT must still not scan $HOME."""
    assert "pytest" in sys.modules
    reason = filemap.auto_scan_disabled_reason()
    assert reason is not None
    assert "pytest" in reason


def test_lv_agent_blocks_the_scan(monkeypatch):
    monkeypatch.setenv("LV_AGENT", "1")
    reason = filemap.auto_scan_disabled_reason()
    assert reason is not None
    assert "LV_AGENT" in reason


def test_auto_scan_refuses_to_run_under_the_guard():
    result = filemap.auto_scan_on_startup()
    assert result["ran"] is False
    assert result["roots_scanned"] == []


def test_startup_hook_does_not_spawn_a_thread_when_guarded():
    """The hook checks the guard before creating the thread, so a blocked run
    costs nothing at startup."""
    import threading

    import asyncio

    from src.web import _startup_filemap_autoscan

    before = {t.name for t in threading.enumerate()}
    asyncio.run(_startup_filemap_autoscan())
    after = {t.name for t in threading.enumerate()}
    assert filemap.AUTO_SCAN_THREAD_NAME not in (after - before)


# --- behaviour, with the guard lifted ---------------------------------------


@pytest.fixture
def unguarded(monkeypatch):
    """Lift both guards so the scan logic itself can be exercised, pointed at
    a temp tree rather than a real home folder."""
    monkeypatch.delenv("LV_AGENT", raising=False)
    monkeypatch.setattr(filemap, "auto_scan_disabled_reason", lambda: None)


def test_first_launch_scans_and_populates(scan_home, monkeypatch, unguarded):
    home = _tree(scan_home)
    monkeypatch.setattr(filemap.Path, "home", staticmethod(lambda: home))

    assert filemap.load_map().roots == []
    result = filemap.auto_scan_on_startup(max_depth=4)

    assert result["ran"] is True
    assert result["reason"] == "first launch"
    current = filemap.load_map()
    assert current.roots, "a fresh launch must produce a file map with no teacher action"
    assert current.entries


def test_auto_scan_excludes_student_zones(scan_home, monkeypatch, unguarded):
    """Already-working behaviour, verified to still fire on the auto path."""
    home = _tree(scan_home)
    monkeypatch.setattr(filemap.Path, "home", staticmethod(lambda: home))

    filemap.auto_scan_on_startup(max_depth=4)
    current = filemap.load_map()

    assert current.student_zones, "Students/ should be detected as a student zone"
    scanned = " ".join(entry.path for entry in current.entries).lower()
    assert "students" not in scanned, "a student zone must not be indexed"


def test_auto_scan_tags_education_domains(scan_home, monkeypatch, unguarded):
    home = _tree(scan_home)
    monkeypatch.setattr(filemap.Path, "home", staticmethod(lambda: home))

    filemap.auto_scan_on_startup(max_depth=4)
    domains = {entry.inferred_domain for entry in filemap.load_map().entries}
    assert "curriculum" in domains
    assert "assessment" in domains


def test_second_launch_skips_unchanged_roots(scan_home, monkeypatch, unguarded):
    home = _tree(scan_home)
    monkeypatch.setattr(filemap.Path, "home", staticmethod(lambda: home))

    filemap.auto_scan_on_startup(max_depth=4)
    again = filemap.auto_scan_on_startup(max_depth=4)

    assert again["ran"] is False
    assert "up to date" in again["reason"]


def test_a_changed_root_is_rescanned(scan_home, monkeypatch, unguarded):
    home = _tree(scan_home)
    monkeypatch.setattr(filemap.Path, "home", staticmethod(lambda: home))
    filemap.auto_scan_on_startup(max_depth=4)

    # Push the recorded scan time into the past so the root reads as stale.
    current = filemap.load_map()
    current.roots[0].scanned_at = "2000-01-01T00:00:00+00:00"
    filemap.save_map(current)

    assert filemap.roots_needing_rescan()
    again = filemap.auto_scan_on_startup(max_depth=4)
    assert again["ran"] is True
    assert "changed" in again["reason"]


def test_a_missing_root_is_not_treated_as_stale(tmp_path, monkeypatch, unguarded):
    """An unplugged external drive must not delete its recorded entries."""
    root = filemap.ScanRoot(path=str(tmp_path / "gone"), scanned_at="2000-01-01T00:00:00+00:00")
    assert filemap._scan_root_is_stale(root) is False


def test_unparseable_scan_time_is_treated_as_stale(tmp_path):
    directory = tmp_path / "real"
    directory.mkdir()
    root = filemap.ScanRoot(path=str(directory), scanned_at="not-a-timestamp")
    assert filemap._scan_root_is_stale(root) is True


# --- progress state ---------------------------------------------------------


def test_scan_in_progress_is_false_when_idle():
    assert filemap.is_scan_in_progress() is False


def test_a_second_scan_is_refused_while_one_is_running(unguarded):
    filemap._set_scan_in_progress(True)
    try:
        result = filemap.auto_scan_on_startup()
        assert result["ran"] is False
        assert "already running" in result["reason"]
    finally:
        filemap._set_scan_in_progress(False)


def test_progress_flag_is_cleared_even_when_the_scan_fails(monkeypatch, unguarded):
    def boom(*args, **kwargs):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(filemap, "load_map", boom)
    result = filemap.auto_scan_on_startup()

    assert result["ran"] is False
    assert filemap.is_scan_in_progress() is False, "a failed scan must not wedge the flag"
