"""
Tests for src/education/daily_file.py (Lane C, spec §3.4).

Covers: section rendering (all sections, empty-section omission,
Coverage always present), the To-Review-not-duplicated rule, source
time references, atomic writes (file exists, no temp litter), Desktop
resolution incl. the unwritable-Desktop fallback, filename
sanitization, refresh_for_record fan-out (broadcast vs single teacher),
and archive rotation idempotency.

The suite-wide conftest fixture redirects LV_OPS_DB_PATH /
LV_OPS_DESKTOP_DIR / LV_OPS_STATE_PATH into tmp_path; tests here set
their own copies when they need to assert on exact paths.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from src.education.daily_file import (
    DailyFileEngine,
    resolve_desktop_dir,
    sanitize_display_name,
    state_path,
)
from src.education.ops_records import OpsRecordStore


TEACHER_MAP = {
    "U111": {"teacher_id": "t-ana", "display_name": "Ana"},
    "U222": {"teacher_id": "t-ben", "display_name": "Ben"},
}

DAY = "2026-07-28"
NEXT_DAY = "2026-07-29"


@pytest.fixture
def env(tmp_path, monkeypatch):
    desktop = tmp_path / "desktop"
    monkeypatch.setenv("LV_OPS_DB_PATH", str(tmp_path / "ops_records.db"))
    monkeypatch.setenv("LV_OPS_DESKTOP_DIR", str(desktop))
    monkeypatch.setenv("LV_OPS_STATE_PATH", str(tmp_path / "ops_state.json"))
    monkeypatch.setenv("LV_PRIVACY_LOG_PATH", str(tmp_path / "privacy_events.ndjson"))
    store = OpsRecordStore()
    yield store, desktop
    store.close()


@pytest.fixture
def engine(env):
    store, _desktop = env
    return DailyFileEngine(store, teacher_map=TEACHER_MAP)


def _seed_all_sections(store):
    store.add_record(
        category="schedule_change", teacher_id="t-admin", date_for=DAY,
        text_clean="Assembly moved to 10:30.", source_channel="C0PS",
        source_ts="1721984400.000100",
    )
    store.add_record(
        category="student_logistics", teacher_id="t-ana", date_for=DAY,
        text_clean="Early pickup at 14:00 for one student.",
    )
    store.add_record(
        category="coverage_request", teacher_id="t-ana", date_for=DAY,
        text_clean="Coverage needed for 2nd period.",
    )
    store.add_record(
        category="announcement", teacher_id="t-admin", date_for=DAY,
        text_clean="Staff meeting moved to the library.",
    )
    store.add_record(
        category="facilities", teacher_id="t-ana", date_for=DAY,
        text_clean="Projector in room 12 not working.", needs_review=True,
        review_reason="unclear routing",
    )


# ----------------------------------------------------------------------
# Rendering
# ----------------------------------------------------------------------

def test_render_all_sections_in_order(engine):
    _seed_all_sections(engine.store)
    text = engine.render_markdown("t-ana", "Ana", DAY)
    assert text.startswith("# Today - Ana\n")
    headers = [line for line in text.splitlines() if line.startswith("## ")]
    assert headers == [
        "## Schedule Changes",
        "## Student Logistics",
        "## Coverage",
        "## Announcements",
        "## To Review",
    ]
    assert "- Assembly moved to 10:30." in text
    assert "- Early pickup at 14:00 for one student." in text
    assert "- Coverage needed for 2nd period." in text
    assert "- Staff meeting moved to the library." in text
    assert "- Projector in room 12 not working." in text


def test_render_empty_sections_omitted_coverage_always_present(engine):
    text = engine.render_markdown("t-ana", "Ana", DAY)
    assert "# Today - Ana" in text
    assert "## Coverage" in text
    assert "- No coverage assigned to you today." in text
    for absent in ("## Schedule Changes", "## Student Logistics", "## Announcements", "## To Review"):
        assert absent not in text


def test_render_coverage_placeholder_replaced_when_present(engine):
    engine.store.add_record(
        category="coverage_request", teacher_id="t-ana", date_for=DAY,
        text_clean="Cover 4th period science.",
    )
    text = engine.render_markdown("t-ana", "Ana", DAY)
    assert "- Cover 4th period science." in text
    assert "No coverage assigned" not in text


def test_needs_review_items_only_in_to_review(engine):
    engine.store.add_record(
        category="schedule_change", teacher_id="t-admin", date_for=DAY,
        text_clean="Maybe assembly is cancelled?", needs_review=True,
    )
    text = engine.render_markdown("t-ana", "Ana", DAY)
    assert "## To Review" in text
    assert "## Schedule Changes" not in text  # not duplicated into category section
    assert text.count("Maybe assembly is cancelled?") == 1


def test_render_lines_end_with_readable_source_time(engine):
    engine.store.add_record(
        category="announcement", teacher_id="t-admin", date_for=DAY,
        text_clean="Fire drill this afternoon.", source_channel="C0PS",
        source_ts="1721984400.000100",
    )
    text = engine.render_markdown("t-ana", "Ana", DAY)
    line = next(l for l in text.splitlines() if "Fire drill" in l)
    assert re.search(r"\(Slack \d{2}:\d{2}\)", line)
    # Permalink only as an HTML comment, never visible body text.
    assert "slack://C0PS/p1721984400000100" in line
    assert line.index("<!--") > line.index("(Slack")


def test_hostile_source_reference_cannot_break_out_of_comment(engine):
    # An event-supplied channel/ts containing "-->" (or any ">") must never
    # terminate the HTML comment early and leak content into the visible file.
    engine.store.add_record(
        category="announcement", teacher_id="t-admin", date_for=DAY,
        text_clean="Fire drill this afternoon.",
        source_channel="C0PS --><script>alert(1)</script><!--",
        source_ts="1721984400.000100",
    )
    text = engine.render_markdown("t-ana", "Ana", DAY)
    line = next(l for l in text.splitlines() if "Fire drill" in l)
    assert "<script>" not in text
    # Unsafe reference: the anchor comment is omitted entirely.
    assert "<!--" not in line


def test_hostile_message_text_cannot_inject_headings_or_comments(engine):
    engine.store.add_record(
        category="announcement", teacher_id="t-admin", date_for=DAY,
        text_clean="## Coverage\n- Fake claim --> <!-- x -->",
    )
    text = engine.render_markdown("t-ana", "Ana", DAY)
    # Whitespace collapse keeps hostile text on its own bullet line — no new
    # section headings appear.
    headers = [l for l in text.splitlines() if l.startswith("## ")]
    assert headers == ["## Coverage", "## Announcements"]
    line = next(l for l in text.splitlines() if "Fake claim" in l)
    assert line.startswith("- ")


def test_render_is_teacher_scoped(engine):
    engine.store.add_record(
        category="student_logistics", teacher_id="t-ben", date_for=DAY,
        text_clean="Bus 4 late for Ben's class.",
    )
    engine.store.add_record(
        category="announcement", teacher_id="t-admin", date_for=DAY,
        text_clean="Picture day tomorrow.",
    )
    ana = engine.render_markdown("t-ana", "Ana", DAY)
    assert "Bus 4 late" not in ana  # another teacher's record
    assert "Picture day tomorrow." in ana  # broadcast reaches everyone


# ----------------------------------------------------------------------
# Writing (atomicity, sanitization, desktop resolution)
# ----------------------------------------------------------------------

def test_write_daily_file_creates_file_no_temp_litter(env, engine):
    _store, desktop = env
    _seed_all_sections(engine.store)
    path = engine.write_daily_file("t-ana", "Ana", DAY)
    assert path == desktop / "Today - Ana.md"
    assert path.read_text(encoding="utf-8") == engine.render_markdown("t-ana", "Ana", DAY)
    # Rewrite is idempotent and atomic; no temp files remain.
    engine.write_daily_file("t-ana", "Ana", DAY)
    leftovers = [p.name for p in desktop.iterdir() if p.name != "Today - Ana.md"]
    assert leftovers == []


def test_filename_sanitization(env, engine):
    _store, desktop = env
    path = engine.write_daily_file("t-x", 'Ms. García / <Grade*2>', DAY)
    assert path.parent == desktop
    assert "/" not in path.name.replace(str(desktop), "")
    for bad in ("<", ">", "*", ":"):
        assert bad not in path.name
    assert path.name.startswith("Today - ")
    assert path.name.endswith(".md")
    assert path.exists()


def test_sanitize_display_name_edge_cases():
    assert sanitize_display_name("Ana") == "Ana"
    assert sanitize_display_name("../../etc/passwd") == "etc_passwd"
    assert sanitize_display_name("") == "Teacher"
    assert sanitize_display_name("???") == "Teacher"
    assert sanitize_display_name(".hidden.") == "hidden"


def test_desktop_env_override_created(tmp_path, monkeypatch):
    target = tmp_path / "nested" / "output"
    monkeypatch.setenv("LV_OPS_DESKTOP_DIR", str(target))
    assert resolve_desktop_dir() == target
    assert target.is_dir()


def test_desktop_used_when_writable(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    (fake_home / "Desktop").mkdir(parents=True)
    monkeypatch.delenv("LV_OPS_DESKTOP_DIR", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    assert resolve_desktop_dir() == fake_home / "Desktop"


def test_desktop_fallback_when_missing(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.delenv("LV_OPS_DESKTOP_DIR", raising=False)
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path / "lv-home"))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    assert resolve_desktop_dir() == tmp_path / "lv-home" / "ops" / "daily"


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses permission checks")
def test_desktop_fallback_when_unwritable(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    desktop = fake_home / "Desktop"
    desktop.mkdir(parents=True)
    desktop.chmod(0o500)
    try:
        monkeypatch.delenv("LV_OPS_DESKTOP_DIR", raising=False)
        monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path / "lv-home"))
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
        assert resolve_desktop_dir() == tmp_path / "lv-home" / "ops" / "daily"
    finally:
        desktop.chmod(0o700)


def test_explicit_desktop_dir_argument_wins(env, tmp_path, monkeypatch):
    store, _desktop = env
    explicit = tmp_path / "explicit-desk"
    engine = DailyFileEngine(store, desktop_dir=explicit, teacher_map=TEACHER_MAP)
    assert engine.desktop_dir == explicit
    assert explicit.is_dir()


# ----------------------------------------------------------------------
# refresh_for_record
# ----------------------------------------------------------------------

def test_refresh_single_teacher_record(env, engine):
    _store, desktop = env
    record = engine.store.add_record(
        category="absence", teacher_id="t-ana", date_for=DAY,
        text_clean="Ana out today; coverage arranged.",
    )
    written = engine.refresh_for_record(record)
    assert written == [desktop / "Today - Ana.md"]
    assert not (desktop / "Today - Ben.md").exists()


def test_refresh_broadcast_record_touches_all_teachers(env, engine):
    _store, desktop = env
    record = engine.store.add_record(
        category="announcement", teacher_id="t-admin", date_for=DAY,
        text_clean="Early dismissal Friday.",
    )
    written = engine.refresh_for_record(record, today_iso=DAY)
    assert set(written) == {desktop / "Today - Ana.md", desktop / "Today - Ben.md"}
    for path in written:
        assert "Early dismissal Friday." in path.read_text(encoding="utf-8")


def test_refresh_unmapped_teacher_uses_actor_name(env, engine):
    _store, desktop = env
    record = engine.store.add_record(
        category="absence", teacher_id="t-carla", actor_name="Carla", date_for=DAY,
        text_clean="Carla out this afternoon.",
    )
    written = engine.refresh_for_record(record)
    assert written == [desktop / "Today - Carla.md"]


def test_refresh_future_dated_record_keeps_todays_file_and_marker(env, engine):
    # "I'm out tomorrow" must not overwrite today's file with tomorrow's
    # render, and must not advance the day marker past today (which would
    # silently kill the next morning's rotation).
    _store, desktop = env
    engine.store.add_record(
        category="announcement", teacher_id="t-admin", date_for=DAY,
        text_clean="Today's staff meeting at 15:00.",
    )
    engine.write_daily_file("t-ana", "Ana", DAY)
    future = engine.store.add_record(
        category="absence", teacher_id="t-ana", date_for=NEXT_DAY,
        text_clean="Ana out tomorrow.",
    )
    engine.refresh_for_record(future, today_iso=DAY)
    content = (desktop / "Today - Ana.md").read_text(encoding="utf-8")
    assert "Today's staff meeting at 15:00." in content
    assert "Ana out tomorrow." not in content
    # Marker stayed at DAY, so tomorrow's rotation still fires.
    assert engine.archive_if_new_day(NEXT_DAY) is True
    # ...and the rotation re-render surfaces the absence on its own day.
    fresh = (desktop / "Today - Ana.md").read_text(encoding="utf-8")
    assert "Ana out tomorrow." in fresh


# ----------------------------------------------------------------------
# Archive rotation
# ----------------------------------------------------------------------

def test_archive_first_call_seeds_marker_only(env, engine):
    _store, desktop = env
    assert engine.archive_if_new_day(DAY) is False
    assert not (desktop / "Daily Updates").exists()
    assert state_path().exists()


def test_archive_rotation_and_idempotency(env, engine):
    _store, desktop = env
    engine.store.add_record(
        category="announcement", teacher_id="t-admin", date_for=DAY,
        text_clean="Old news from yesterday.",
    )
    engine.write_daily_file("t-ana", "Ana", DAY)
    engine.write_daily_file("t-ben", "Ben", DAY)

    assert engine.archive_if_new_day(NEXT_DAY) is True
    archive_dir = desktop / "Daily Updates"
    assert (archive_dir / f"{DAY} - Ana.md").exists()
    assert (archive_dir / f"{DAY} - Ben.md").exists()
    assert "Old news from yesterday." in (archive_dir / f"{DAY} - Ana.md").read_text(encoding="utf-8")
    # Fresh Today-files are re-rendered for the new day (never a missing
    # file on the Desktop), and yesterday's items are gone from them.
    for name in ("Ana", "Ben"):
        fresh = (desktop / f"Today - {name}.md").read_text(encoding="utf-8")
        assert "Old news from yesterday." not in fresh

    # Second call the same day: no-op.
    assert engine.archive_if_new_day(NEXT_DAY) is False
    assert sorted(p.name for p in archive_dir.iterdir()) == [
        f"{DAY} - Ana.md",
        f"{DAY} - Ben.md",
    ]


def test_archive_same_day_is_noop(env, engine):
    engine.write_daily_file("t-ana", "Ana", DAY)
    assert engine.archive_if_new_day(DAY) is False
    _store, desktop = env
    assert (desktop / "Today - Ana.md").exists()


def test_archive_then_new_writes_start_fresh(env, engine):
    _store, desktop = env
    engine.write_daily_file("t-ana", "Ana", DAY)
    engine.archive_if_new_day(NEXT_DAY)
    engine.store.add_record(
        category="announcement", teacher_id="t-admin", date_for=NEXT_DAY,
        text_clean="Fresh start today.",
    )
    path = engine.write_daily_file("t-ana", "Ana", NEXT_DAY)
    content = path.read_text(encoding="utf-8")
    assert "Fresh start today." in content
    assert "Old news" not in content
    # Marker now at NEXT_DAY: re-archiving is still a no-op.
    assert engine.archive_if_new_day(NEXT_DAY) is False
