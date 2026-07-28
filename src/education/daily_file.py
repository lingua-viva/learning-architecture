"""
Daily File Engine — renders "Today - <Teacher>.md" from ops records.

Spec: dev/specs/SPEC_LV_SLACK_OPS_ASSISTANT_2026-07-27.md §3.4 (Lane C).

Design decisions (operator-locked 2026-07-27):
  - The North Star promise is literal: the bot's product is a FILE on the
    teacher's Desktop. Canonical state stays in OpsRecordStore; the file
    is a pure render of a store query (reproducible at any time — no
    state lives in the file itself).
  - Desktop resolution: explicit constructor arg wins, then the
    LV_OPS_DESKTOP_DIR env override, then ~/Desktop if it exists and is
    writable, else lv_home()/ops/daily/ (spec §3.4 fallback). Resolved
    once at construction.
  - Section layout (operator-approved shape): "# Today - <Display Name>"
    then "## Schedule Changes", "## Student Logistics", "## Coverage",
    "## Announcements", "## To Review". Empty sections are omitted
    EXCEPT Coverage, which always renders ("- No coverage assigned to
    you today." when empty) — a teacher must never wonder whether
    coverage info is missing or merely empty.
  - Category -> section mapping: the spec's five sections must hold all
    nine categories. schedule_change -> Schedule Changes;
    student_logistics -> Student Logistics; coverage_request /
    coverage_claim / absence -> Coverage (an absence is coverage-relevant
    context); announcement / reminder / facilities / other ->
    Announcements (general daily notices — spec §1 keeps facilities
    captured-but-workflowless in v1). Records flagged needs_review
    render ONLY in To Review, never duplicated into their category
    section (unresolved clarifications land in To Review, spec §3.5).
  - Body lines are plain, evidence-based phrasing from text_clean and
    end with a human-readable source reference "(Slack HH:MM)" in local
    time. Raw permalinks never appear in the visible body; when a
    source anchor exists it is kept in a trailing HTML comment per line
    so the file stays traceable without clutter.
  - Writes are atomic: temp file in the SAME directory + os.replace
    (same pattern as config.connect_provider), so a half-written file
    can never appear on the Desktop mid-render.
  - Daily reset (archive_if_new_day): a small JSON marker under
    lv_home()/ops/state.json (LV_OPS_STATE_PATH override — hermeticity
    seam addition, same pattern as LV_TRACE_PATH etc. since tests must
    not touch the operator's real ~/.lingua-viva) records the last
    rendered day. On the first call of a new day, every
    "Today - *.md" moves to "<desktop>/Daily Updates/<last_day> -
    <Display Name>.md". Idempotent: a second call the same day is a
    no-op returning False.
  - Local-only: no network, no external model, no student-lens access.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.education import ops_packs
from src.education.ops_packs import CompiledRuleSet
from src.education.ops_records import (
    OpsRecord,
    OpsRecordStore,
)


# v2 (SPEC_LV_SLACK_OPS_V2_WORKFLOW_PACKS_2026-07-27 §3.1): section order,
# category→section mapping, and the always-render rule derive from the
# pack registry. These module-level names keep their v1 values (from the
# v1-parity default compile) for existing call sites and tests; the
# engine itself reads through the CURRENT compile (injected rule_set or
# the process-wide swap seam) so disabled packs shrink the section list
# (spec §3.4).
SECTION_ORDER = ops_packs.default_rule_set().section_order

_CATEGORY_SECTIONS = dict(ops_packs.default_rule_set().category_sections)

_COVERAGE_EMPTY_LINE = "- No coverage assigned to you today."

_FILENAME_SAFE = re.compile(r"[^A-Za-z0-9 ._-]+")

# Charset allowed inside the trailing HTML source-anchor comment. Excludes
# ">" (and thus any early "-->" comment terminator), so an event-supplied
# channel/ts value can never break out of the comment and inject visible
# content into the daily file (hardening pass 1, 2026-07-27).
_COMMENT_SAFE = re.compile(r"^[A-Za-z0-9:/._@-]+$")


def sanitize_display_name(name: str) -> str:
    """Make a display name safe as a filename component.

    Keeps letters, digits, spaces, dots, underscores, hyphens; collapses
    everything else. Never returns an empty string (falls back to
    "Teacher") and strips leading/trailing dots so no hidden files.
    """
    cleaned = _FILENAME_SAFE.sub("_", name or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ._")
    return cleaned or "Teacher"


def state_path() -> Path:
    override = os.environ.get("LV_OPS_STATE_PATH")
    if override:
        return Path(override).expanduser()
    from src.lingua_viva.config import lv_home
    return lv_home() / "ops" / "state.json"


def _fallback_daily_dir() -> Path:
    from src.lingua_viva.config import lv_home
    return lv_home() / "ops" / "daily"


def resolve_desktop_dir(explicit: Optional[Path] = None) -> Path:
    """Spec §3.4 output-directory resolution (see module docstring)."""
    if explicit is not None:
        directory = Path(explicit).expanduser()
        directory.mkdir(parents=True, exist_ok=True)
        return directory
    override = os.environ.get("LV_OPS_DESKTOP_DIR")
    if override:
        directory = Path(override).expanduser()
        directory.mkdir(parents=True, exist_ok=True)
        return directory
    desktop = Path.home() / "Desktop"
    if desktop.is_dir() and os.access(desktop, os.W_OK):
        return desktop
    fallback = _fallback_daily_dir()
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def _source_time_label(record: OpsRecord) -> str:
    """Human-readable local HH:MM for the record's Slack message.

    Slack ts values are epoch seconds ("1721990400.123456"); fall back
    to the record's created_at (UTC ISO) converted to local time.
    """
    if record.source_ts:
        try:
            moment = datetime.fromtimestamp(float(record.source_ts)).astimezone()
            return moment.strftime("%H:%M")
        except (ValueError, OverflowError, OSError):
            pass
    try:
        created = datetime.fromisoformat(record.created_at)
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return created.astimezone().strftime("%H:%M")
    except ValueError:
        return "--:--"


def _render_line(record: OpsRecord) -> str:
    text = (record.text_clean or record.text_raw or "(no detail)").strip()
    text = re.sub(r"\s+", " ", text)
    line = f"- {text} (Slack {_source_time_label(record)})"
    ref = record.source_reference()
    if ref != "local" and _COMMENT_SAFE.match(ref):
        line += f" <!-- {ref} -->"
    return line


class DailyFileEngine:
    """Renders, writes, refreshes, and archives per-teacher daily files."""

    def __init__(
        self,
        store: OpsRecordStore,
        desktop_dir: Optional[Path] = None,
        teacher_map: Optional[dict] = None,
        rule_set: Optional[CompiledRuleSet] = None,
    ):
        self.store = store
        self.desktop_dir = resolve_desktop_dir(desktop_dir)
        # slack_user_id -> {"teacher_id": ..., "display_name": ...}
        self.teacher_map: dict = dict(teacher_map or {})
        # Explicit rule_set pins the compile (tests); None reads through
        # the process-wide current compile on every render, so a bot-spec
        # swap (spec v2 §3.2) takes effect without rebuilding the engine.
        self._rule_set = rule_set

    def _rules(self) -> CompiledRuleSet:
        return self._rule_set if self._rule_set is not None else ops_packs.current_rule_set()

    # ------------------------------------------------------------------
    # Rendering (pure function of store contents)
    # ------------------------------------------------------------------

    def render_markdown(self, teacher_id: str, display_name: str, date_iso: str) -> str:
        rules = self._rules()
        records = self.store.records_for_day(
            date_iso,
            teacher_id=teacher_id,
            broadcast_categories=rules.broadcast_categories,
        )
        sections: dict[str, list[str]] = {name: [] for name in rules.section_order}
        for record in records:
            if record.status == "resolved":
                # Dismissed/withdrawn items leave the daily file (the record
                # and its audit trail remain in the store).
                continue
            if record.needs_review:
                sections["To Review"].append(_render_line(record))
                continue
            section = rules.section_for(record.category)
            sections.setdefault(section, []).append(_render_line(record))

        lines = [f"# Today - {display_name}", ""]
        for name in rules.section_order:
            items = sections[name]
            always_render = name in rules.always_render
            if not items and not always_render:
                continue  # omit empty sections (Coverage always renders — pack rule)
            lines.append(f"## {name}")
            lines.extend(items or ([rules.always_render[name]] if always_render else []))
            lines.append("")
        return "\n".join(lines).rstrip("\n") + "\n"

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------

    def daily_file_path(self, display_name: str) -> Path:
        return self.desktop_dir / f"Today - {sanitize_display_name(display_name)}.md"

    def write_daily_file(self, teacher_id: str, display_name: str, date_iso: str) -> Path:
        content = self.render_markdown(teacher_id, display_name, date_iso)
        target = self.daily_file_path(display_name)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=".today-", suffix=".tmp", dir=str(target.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
            os.replace(tmp_name, target)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
        self._advance_marker(date_iso)
        return target

    def refresh_for_record(self, record: OpsRecord, today_iso: Optional[str] = None) -> list[Path]:
        """Re-write the daily files a record affects.

        Broadcast categories (announcement, schedule_change) touch every
        teacher in teacher_map; anything else touches only the record's
        teacher. Display names come from teacher_map; a record whose
        teacher is unmapped falls back to actor_name, then teacher_id.

        The file is always rendered for TODAY (hardening pass 5,
        2026-07-27): rendering record.date_for here let a future-dated
        absence ("I'm out tomorrow") overwrite today's Desktop file with
        tomorrow's — mostly empty — render AND advance the day marker
        past today, which silently killed the next morning's rotation.
        A future-dated record simply re-renders today's file unchanged;
        it surfaces on its own day via the rotation re-render below.
        """
        date_iso = today_iso or datetime.now().astimezone().date().isoformat()
        targets: list[tuple[str, str]] = []
        if record.category in self._rules().broadcast_categories:
            for info in self.teacher_map.values():
                targets.append(
                    (str(info.get("teacher_id") or ""), str(info.get("display_name") or ""))
                )
            if not targets and record.teacher_id:
                targets.append((record.teacher_id, self._display_for(record)))
        elif record.teacher_id:
            targets.append((record.teacher_id, self._display_for(record)))
        written = []
        for teacher_id, display_name in targets:
            if not teacher_id:
                continue
            written.append(self.write_daily_file(teacher_id, display_name, date_iso))
        return written

    def _display_for(self, record: OpsRecord) -> str:
        for info in self.teacher_map.values():
            if str(info.get("teacher_id") or "") == record.teacher_id:
                return str(info.get("display_name") or "") or record.teacher_id
        return record.actor_name or record.teacher_id

    # ------------------------------------------------------------------
    # Daily reset
    # ------------------------------------------------------------------

    def archive_if_new_day(self, today_iso: str) -> bool:
        """Archive yesterday's Today-files when a new day starts.

        Returns True only when an actual rotation happened. Idempotent:
        the marker advances to today_iso, so repeat calls the same day
        return False. The very first call (no marker yet) just seeds the
        marker — there is nothing attributable to a previous day.
        """
        state = self._read_state()
        last_day = state.get("last_day")
        if not last_day:
            self._write_state({"last_day": today_iso})
            return False
        if last_day >= today_iso:
            return False

        archive_dir = self.desktop_dir / "Daily Updates"
        archive_dir.mkdir(parents=True, exist_ok=True)
        for path in sorted(self.desktop_dir.glob("Today - *.md")):
            display = path.stem[len("Today - "):]
            os.replace(path, archive_dir / f"{last_day} - {display}.md")
        self._write_state({"last_day": today_iso})
        # Re-render fresh Today-files for the new day (hardening pass 13,
        # 2026-07-27): without this, rotation left the Desktop empty until
        # the day's first event, records logged in advance for today
        # (yesterday's "I'm out tomorrow") stayed invisible, and the
        # morning briefing's "Open daily file" pointed at a missing file.
        for info in self.teacher_map.values():
            teacher_id = str(info.get("teacher_id") or "")
            display_name = str(info.get("display_name") or "") or teacher_id
            if teacher_id:
                self.write_daily_file(teacher_id, display_name, today_iso)
        return True

    def _advance_marker(self, date_iso: str) -> None:
        state = self._read_state()
        last_day = state.get("last_day")
        if not last_day or date_iso > last_day:
            state["last_day"] = date_iso
            self._write_state(state)

    @staticmethod
    def _read_state() -> dict:
        try:
            with state_path().open(encoding="utf-8") as handle:
                data = json.load(handle)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _write_state(state: dict) -> None:
        path = state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(state, handle)
        os.replace(tmp, path)
