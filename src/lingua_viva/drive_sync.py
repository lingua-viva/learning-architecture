"""
Drive Sync — automatic lens-to-Drive push after any lens mutation.

When a sync folder is configured, any lens update (observation save, extraction
write, manual edit) triggers an async push of the updated lens file to Drive.

Sync is fire-and-forget: failures are logged but never block the save.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.lingua_viva.config import lv_home

logger = logging.getLogger(__name__)

SYNC_CONFIG_KEY = "drive_sync_folder_id"
PENDING_SYNCS_FILE = "pending_drive_syncs.json"

# Multi-teacher triangulation (SPEC_LV_MULTI_TEACHER_TRIANGULATION_2026-08-01):
# machine-readable per-teacher observation ledgers ride alongside the Markdown
# lens in the school's own shared folder. IDs, never names, in filenames —
# Drive filenames are the most-leaked surface (breadcrumbs, notifications,
# search). Schema is versioned from day one; an unknown version is skipped.
LEDGER_SCHEMA = "lv_ledger_v1"
LEDGER_SUFFIX = ".ledger.ndjson"

# Pull cadence throttle: the lens view fires a fire-and-forget pull, but a
# teacher clicking through their roster must not hammer Drive. Manual pulls
# bypass this (throttled=False).
_PULL_MIN_INTERVAL_SECONDS = 300.0
_last_pull_at: dict = {}


def get_sync_folder_id() -> Optional[str]:
    """Read the configured sync folder ID from config."""
    config_path = lv_home() / "config" / "settings.json"
    if not config_path.exists():
        return None
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        folder_id = data.get(SYNC_CONFIG_KEY)
        return str(folder_id).strip() if folder_id else None
    except (json.JSONDecodeError, OSError):
        return None


def set_sync_folder_id(folder_id: str) -> None:
    """Write the sync folder ID to config."""
    config_dir = lv_home() / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "settings.json"
    data = {}
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    data[SYNC_CONFIG_KEY] = folder_id.strip()
    config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def format_lens_markdown(student_data: dict) -> str:
    """Format a student lens as a readable Markdown file for Drive export."""
    name = student_data.get("display_name", "Unknown Student")
    grade = student_data.get("grade_level", "")
    student_id = student_data.get("student_id", "")
    trajectory = student_data.get("cefr_trajectory", "unknown")
    support_tier = student_data.get("support_tier", "")
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        f"# Student Lens: {name}",
        "",
        f"**Student ID**: {student_id}",
        f"**Grade**: {grade}" if grade else "",
        f"**CEFR trajectory**: {trajectory}",
        f"**Support tier**: {support_tier}" if support_tier else "",
        f"**Last updated**: {updated}",
        "",
    ]

    # Support profile
    support = student_data.get("support_profile", {})
    if support:
        lines.append("## Support Profile")
        lines.append("")
        categories = support.get("categories", {})
        for cat_id, cat_data in categories.items():
            if isinstance(cat_data, dict):
                label = cat_data.get("label", cat_id)
                lines.append(f"### {label}")
                strengths = cat_data.get("strengths", [])
                if strengths:
                    for s in strengths:
                        lines.append(f"- ✓ {s}")
                needs = cat_data.get("needs", [])
                if needs:
                    for n in needs:
                        lines.append(f"- ⚠ {n}")
                strategies = cat_data.get("strategies", [])
                if strategies:
                    for st in strategies:
                        lines.append(f"- → {st}")
                lines.append("")

    # Recent observations
    observations = student_data.get("observations", student_data.get("recent_observations", []))
    if observations:
        lines.append("## Recent Observations")
        lines.append("")
        for obs in observations[:10]:
            date = obs.get("created_at", "")[:10] if obs.get("created_at") else ""
            text = obs.get("raw_transcript", obs.get("text", ""))
            level = obs.get("observed_level", "")
            lines.append(f"- [{date}] {text}" + (f" (CEFR {level})" if level else ""))
        lines.append("")

    # Grouping notes
    grouping = student_data.get("grouping", {})
    if grouping:
        avoid = grouping.get("avoid_pairing_notes", "")
        if avoid:
            lines.append(f"## Grouping Notes")
            lines.append(f"Avoid-pairing: {avoid}")
            lines.append("")

    lines.append("---")
    lines.append(f"*Generated by Lingua Viva · {updated}*")
    return "\n".join(line for line in lines if line is not None)


def _safe_filename(name: str) -> str:
    """Create a Drive-safe filename from a student name."""
    safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in name)
    return safe.strip()[:50] or "student"


async def sync_lens_to_drive(student_id: str) -> bool:
    """Push a student lens to the configured Drive sync folder.

    Returns True if sync succeeded, False if it failed or was skipped.
    This function is designed to be called via asyncio.create_task() —
    it never raises.
    """
    try:
        folder_id = get_sync_folder_id()
        if not folder_id:
            return False

        # Load the student lens (full export includes observations) and this
        # machine's per-teacher ledgers while the store is open.
        from src.education.student_lens import StudentLensStore

        store = StudentLensStore()
        try:
            lens_data = store.export_lens(student_id)
            if not lens_data:
                return False
            ledgers = {
                teacher_id: build_ledger_ndjson(store, student_id, teacher_id)
                for teacher_id in store.local_teacher_ids(student_id)
            }
        finally:
            store.close()

        # Format as markdown
        content = format_lens_markdown(lens_data)
        display_name = lens_data.get("display_name", student_id)
        filename = f"{_safe_filename(display_name)}_lens.md"

        # Upload to Drive
        from src.lingua_viva.google_drive_integration import (
            upload_text_to_folder,
        )

        await asyncio.to_thread(
            upload_text_to_folder,
            folder_id=folder_id,
            filename=filename,
            content=content,
            mime_type="text/markdown",
        )

        # Machine-readable ledger alongside the human-readable lens: same
        # data class, same destination — full-state overwrite each sync,
        # ID-only filename.
        for teacher_id, ledger in ledgers.items():
            await asyncio.to_thread(
                upload_text_to_folder,
                folder_id=folder_id,
                filename=f"{student_id}.{teacher_id}{LEDGER_SUFFIX}",
                content=ledger,
                mime_type="application/x-ndjson",
            )
        logger.info(f"Synced lens for {student_id} to Drive folder {folder_id}")
        return True

    except Exception as exc:
        logger.warning(f"Drive sync failed for {student_id}: {exc}")
        _record_pending_sync(student_id)
        return False


def build_ledger_ndjson(store, student_id: str, teacher_id: str) -> str:
    """One teacher's observation ledger for one student, as NDJSON.

    Header row carries the versioned schema + attribution; each following
    row is one Observation-schema dict authored by this teacher on this
    machine (origin='local' only — imported colleague rows never re-export,
    so ledgers cannot echo back and forth between machines).

    TODO(Spec 2 evidence records): row-based evidence attachments would be
    appended here when a row-level evidence store exists; today's evidence
    lives inside the support-profile JSON and already rides in the rollups.
    """
    header = {
        "schema": LEDGER_SCHEMA,
        "teacher_id": teacher_id,
        "student_id": student_id,
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }
    lines = [json.dumps(header, ensure_ascii=True)]
    for row in store.local_observation_rows(student_id, teacher_id):
        lines.append(json.dumps(row, ensure_ascii=True))
    return "\n".join(lines) + "\n"


def pull_shared_ledgers(student_id: Optional[str] = None) -> dict:
    """Pull colleagues' observation ledgers from the shared sync folder and
    merge them append-only into the local store.

    Never raises — a failed pull never blocks or corrupts, and partial
    imports are safe because the merge is idempotent (known UUID -> skip).
    Own-teacher ledgers are skipped by attribution; a self-ledger that
    slips through is harmless (every UUID already exists locally).
    """
    result = {"files_seen": 0, "imported": 0, "skipped": 0, "errors": 0}
    try:
        folder_id = get_sync_folder_id()
        if not folder_id:
            return result

        from src.education.student_lens import StudentLensStore
        from src.lingua_viva.google_drive_integration import (
            download_file_text,
            list_folder_files,
        )

        files = [
            f for f in list_folder_files(folder_id)
            if f.get("name", "").endswith(LEDGER_SUFFIX)
        ]
        store = StudentLensStore()
        try:
            own_teacher_ids = set(store.local_teacher_ids())
            for item in files:
                result["files_seen"] += 1
                try:
                    text = download_file_text(item["id"])
                    lines = [line for line in text.splitlines() if line.strip()]
                    if not lines:
                        continue
                    header = json.loads(lines[0])
                    if not isinstance(header, dict) or header.get("schema") != LEDGER_SCHEMA:
                        logger.warning(
                            f"Skipping ledger {item.get('name')}: unknown schema "
                            f"{header.get('schema') if isinstance(header, dict) else '?'}"
                        )
                        result["errors"] += 1
                        continue
                    if str(header.get("teacher_id") or "") in own_teacher_ids:
                        continue
                    if student_id and str(header.get("student_id") or "") != student_id:
                        continue
                    rows = []
                    for line in lines[1:]:
                        try:
                            row = json.loads(line)
                        except json.JSONDecodeError:
                            result["skipped"] += 1
                            continue
                        if isinstance(row, dict):
                            rows.append(row)
                        else:
                            result["skipped"] += 1
                    merge = store.import_observation_rows(rows)
                    result["imported"] += merge["imported"]
                    result["skipped"] += merge["skipped"]
                except Exception as exc:
                    logger.warning(f"Ledger pull failed for {item.get('name')}: {exc}")
                    result["errors"] += 1
        finally:
            store.close()

        # Privacy events: counts + ids only, no names (the log renders a
        # generic detail line by design).
        from src.lingua_viva.privacy_log import log_event

        log_event("ledger_pulled")
        if result["imported"]:
            log_event("observations_imported")
    except Exception as exc:
        logger.warning(f"Shared-ledger pull failed: {exc}")
        result["errors"] += 1
    return result


def trigger_pull(student_id: str) -> None:
    """Fire-and-forget pull trigger, mirroring trigger_sync. Throttled per
    student so roster browsing doesn't hammer Drive; safe in any context."""
    now = time.monotonic()
    last = _last_pull_at.get(student_id)
    if last is not None and (now - last) < _PULL_MIN_INTERVAL_SECONDS:
        return
    _last_pull_at[student_id] = now
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(asyncio.to_thread(pull_shared_ledgers, student_id))
    except RuntimeError:
        # No running loop — skip pull (happens in test/CLI contexts)
        pass


def _record_pending_sync(student_id: str) -> None:
    """Record a failed sync so it can be retried later."""
    pending_path = lv_home() / PENDING_SYNCS_FILE
    pending: list = []
    if pending_path.exists():
        try:
            pending = json.loads(pending_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    # Add if not already pending
    if student_id not in pending:
        pending.append(student_id)
        # Keep bounded
        pending = pending[-50:]
    try:
        pending_path.write_text(json.dumps(pending), encoding="utf-8")
    except OSError:
        pass


async def retry_pending_syncs() -> int:
    """Retry any pending syncs. Returns count of successful retries."""
    pending_path = lv_home() / PENDING_SYNCS_FILE
    if not pending_path.exists():
        return 0
    try:
        pending = json.loads(pending_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return 0
    if not pending:
        return 0

    succeeded = []
    for student_id in list(pending):
        if await sync_lens_to_drive(student_id):
            succeeded.append(student_id)

    # Remove succeeded from pending
    remaining = [s for s in pending if s not in succeeded]
    try:
        pending_path.write_text(json.dumps(remaining), encoding="utf-8")
    except OSError:
        pass
    return len(succeeded)


def trigger_sync(student_id: str) -> None:
    """Fire-and-forget sync trigger. Safe to call from any context."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(sync_lens_to_drive(student_id))
    except RuntimeError:
        # No running loop — skip sync (happens in test/CLI contexts)
        pass
