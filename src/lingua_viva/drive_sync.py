"""
Drive Sync — automatic lens-to-Drive push after any lens mutation.

When a sync folder is configured, any lens update (observation save, extraction
write, manual edit) triggers an async push of the updated lens file to Drive.

Sync is fire-and-forget: failures are logged but never block the save.

DOES boundary (Lens Primitive, 2026-08-04): everything this module writes to
Drive is a shared, cross-teacher/cross-school artifact, so it may only ever
carry what we explicitly choose to include. A student's name is not the
sensitive element here (support-need lenses are meant to be shared and
reused across similar students) — the causal/etiological narrative behind a
need is. `format_lens_markdown()` never renders raw observation narration,
and `local_observation_rows()` (student_lens.py) always neutralizes
raw_transcript / teacher_edited_transcript before a row can reach a ledger.
See dev/SPEC_LENS_PRIMITIVE_2026-08-04.md.
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

from src.lingua_viva.config import UNPROVISIONED_TEACHER_ID, lv_home
from src.lingua_viva.runtime_paths import runtime_data_dir

logger = logging.getLogger(__name__)

SYNC_CONFIG_KEY = "drive_sync_folder_id"
SYNC_FOLDER_MAP_KEY = "drive_sync_folder_map"
PENDING_SYNCS_FILE = "pending_drive_syncs.json"
SYNC_LEDGER_FILE = "drive_sync_ledger.json"

FOLDER_CATEGORIES = {
    "student_summaries": "Student Summaries",
    "student_evidence": "Student Evidence",
    "teacher_artifacts": "Teacher Artifacts",
    "assigned": "Assigned Coursework",
    "personal": "Personal",
}
DEFAULT_SHARED_CATEGORY = "student_summaries"
PERSONAL_CATEGORY = "personal"
PERSONAL_SUPPORT_CATEGORIES = {"personal_context", "personal", "confidential", "private"}

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
    return get_sync_folder_map().get(DEFAULT_SHARED_CATEGORY)


def _settings_path() -> Path:
    return lv_home() / "config" / "settings.json"


def _read_settings() -> dict:
    config_path = _settings_path()
    if not config_path.exists():
        return {}
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_settings(data: dict) -> None:
    config_path = _settings_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = config_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    os.replace(tmp, config_path)


def normalize_folder_category(category: str) -> str:
    key = str(category or "").strip().lower().replace("-", "_")
    if key == "general":
        return DEFAULT_SHARED_CATEGORY
    if key in {"confidential", "private", "personal_context"}:
        return PERSONAL_CATEGORY
    if key in FOLDER_CATEGORIES:
        return key
    raise ValueError(f"unknown Drive sync folder category: {category}")


def is_personal_support_category(category: str) -> bool:
    return str(category or "").strip().lower().replace("-", "_") in PERSONAL_SUPPORT_CATEGORIES


def get_sync_folder_map() -> dict[str, str]:
    data = _read_settings()
    raw = data.get(SYNC_FOLDER_MAP_KEY)
    folder_map: dict[str, str] = {}
    if isinstance(raw, dict):
        for category, folder_id in raw.items():
            try:
                normalized = normalize_folder_category(str(category))
            except ValueError:
                continue
            if isinstance(folder_id, str) and folder_id.strip():
                folder_map[normalized] = folder_id.strip()
    legacy = data.get(SYNC_CONFIG_KEY)
    if isinstance(legacy, str) and legacy.strip():
        folder_map.setdefault(DEFAULT_SHARED_CATEGORY, legacy.strip())
    return folder_map


def set_sync_folder_map(folder_map: dict[str, str]) -> dict[str, str]:
    cleaned: dict[str, str] = {}
    for category, folder_id in (folder_map or {}).items():
        normalized = normalize_folder_category(str(category))
        value = str(folder_id or "").strip()
        if value:
            cleaned[normalized] = value
    data = _read_settings()
    data[SYNC_FOLDER_MAP_KEY] = cleaned
    if cleaned.get(DEFAULT_SHARED_CATEGORY):
        data[SYNC_CONFIG_KEY] = cleaned[DEFAULT_SHARED_CATEGORY]
    elif SYNC_CONFIG_KEY in data:
        data.pop(SYNC_CONFIG_KEY, None)
    _write_settings(data)
    return cleaned


def get_sync_folder_id_for_category(category: str = DEFAULT_SHARED_CATEGORY) -> Optional[str]:
    folder_map = get_sync_folder_map()
    return folder_map.get(normalize_folder_category(category))


def set_sync_folder_id(folder_id: str) -> None:
    """Write the sync folder ID to config."""
    data = _read_settings()
    value = folder_id.strip()
    if value:
        data[SYNC_CONFIG_KEY] = value
        folder_map = data.get(SYNC_FOLDER_MAP_KEY) if isinstance(data.get(SYNC_FOLDER_MAP_KEY), dict) else {}
        folder_map[DEFAULT_SHARED_CATEGORY] = value
        data[SYNC_FOLDER_MAP_KEY] = folder_map
    else:
        data.pop(SYNC_CONFIG_KEY, None)
        folder_map = data.get(SYNC_FOLDER_MAP_KEY)
        if isinstance(folder_map, dict):
            folder_map.pop(DEFAULT_SHARED_CATEGORY, None)
            data[SYNC_FOLDER_MAP_KEY] = folder_map
    _write_settings(data)


def _sync_ledger_path() -> Path:
    return runtime_data_dir("drive_sync") / SYNC_LEDGER_FILE


def read_sync_ledger() -> dict:
    path = _sync_ledger_path()
    if not path.exists():
        return {"schema_version": 1, "students": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"schema_version": 1, "students": {}}
    if not isinstance(data, dict):
        return {"schema_version": 1, "students": {}}
    if not isinstance(data.get("students"), dict):
        data["students"] = {}
    data.setdefault("schema_version", 1)
    return data


def _write_sync_ledger(data: dict) -> None:
    path = _sync_ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def record_sync_attempt(student_id: str, *, status: str, category: str, reason: str = "") -> None:
    data = read_sync_ledger()
    students = data.setdefault("students", {})
    row = students.setdefault(student_id, {"history": []})
    now = datetime.now(timezone.utc).isoformat()
    row.update({
        "student_id": student_id,
        "last_attempt_at": now,
        "last_status": status,
        "last_category": category,
        "failure_reason": reason,
    })
    history = row.setdefault("history", [])
    if isinstance(history, list):
        history.append({
            "attempted_at": now,
            "status": status,
            "category": category,
            "reason": reason,
        })
        row["history"] = history[-20:]
    _write_sync_ledger(data)


def format_lens_markdown(student_data: dict) -> str:
    """Format a student lens as a readable Markdown file for Drive export."""
    from src.education.student_lens import (
        REPORT_GRADE_CONFIDENCE,
        SUPPORT_CATEGORY_LABELS,
    )
    from src.education.ethos import get_trait, load_ethos

    name = student_data.get("display_name", "Unknown Student")
    grade = student_data.get("grade_level", "")
    student_id = student_data.get("student_id", "")
    trajectory = student_data.get("cefr_trajectory_30d", "insufficient_data")
    rti_tier = student_data.get("rti_current_tier", "")
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    def active_report_items(items: object, text_key: str = "text") -> list[dict]:
        if not isinstance(items, list):
            return []
        kept = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("active", True) is False:
                continue
            if item.get("confidence", "teacher_confirmed") not in REPORT_GRADE_CONFIDENCE:
                continue
            text = str(
                item.get(text_key)
                or item.get("summary")
                or item.get("need_statement")
                or ""
            ).strip()
            if not text:
                continue
            kept.append({**item, "_text": text})
        return kept

    def is_personal_observation(obs: dict) -> bool:
        return is_personal_support_category(str(obs.get("support_category") or ""))

    try:
        ethos_taxonomy = load_ethos()
    except Exception:
        ethos_taxonomy = {"traits": []}

    strengths = student_data.get("strengths_profile", {}) or {}
    academic_strengths = active_report_items(strengths.get("academic_strengths"))
    personal_strengths = active_report_items(strengths.get("personal_strengths"))

    lines = [
        f"# Student Lens - {name}",
        "",
        "## Overview",
        "",
        f"- Student ID: `{student_id}`",
        f"- Grade: {grade or 'not set'}",
        f"- Current RTI tier: {rti_tier or 'not set'}",
        f"- CEFR trajectory: {trajectory}",
        f"- Last updated: {updated}",
        "",
        "## Strengths",
        "",
    ]

    if academic_strengths or personal_strengths:
        if academic_strengths:
            lines.append("### Academic Strengths")
            lines.extend(f"- {item['_text']}" for item in academic_strengths[:8])
            lines.append("")
        if personal_strengths:
            lines.append("### Personal Strengths")
            lines.extend(f"- {item['_text']}" for item in personal_strengths[:8])
            lines.append("")
    else:
        lines.append("- No teacher-confirmed strengths recorded yet.")
        lines.append("")

    support = student_data.get("support_profile", {})
    categories = support.get("categories", {}) if isinstance(support, dict) else {}
    lines.append("## Support Profile")
    lines.append("")
    wrote_support = False
    for cat_id, cat_data in categories.items():
        if cat_id == "personal_context":
            continue
        if not isinstance(cat_data, dict):
            continue
        needs = active_report_items(cat_data.get("needs"))
        legacy_items = active_report_items(cat_data.get("items"), text_key="need_statement")
        cat_strengths = active_report_items(cat_data.get("strengths"))
        worked = active_report_items(cat_data.get("strategies_worked"))
        not_worked = active_report_items(cat_data.get("strategies_not_worked"))
        questions = active_report_items(cat_data.get("open_questions"))
        evidence = active_report_items(cat_data.get("evidence"), text_key="summary")
        if not any((needs, legacy_items, cat_strengths, worked, not_worked, questions, evidence)):
            continue
        wrote_support = True
        lines.append(f"### {SUPPORT_CATEGORY_LABELS.get(cat_id, cat_id)}")
        for label, items in (
            ("Needs", needs or legacy_items),
            ("Strengths", cat_strengths),
            ("Strategies that worked", worked),
            ("Strategies to reconsider", not_worked),
            ("Open questions", questions),
            ("Evidence", evidence),
        ):
            if not items:
                continue
            lines.append(f"**{label}**")
            lines.extend(f"- {item['_text']}" for item in items[:6])
            lines.append("")
    if not wrote_support:
        lines.append("- No teacher-confirmed support entries recorded yet.")
        lines.append("")

    ethos_profile = student_data.get("ethos_profile", {}) or {}
    traits = ethos_profile.get("traits", {}) if isinstance(ethos_profile, dict) else {}
    lines.append("## Still I Rise Traits")
    lines.append("")
    wrote_traits = False
    if isinstance(traits, dict):
        for trait_id, trait_data in traits.items():
            if not isinstance(trait_data, dict):
                continue
            evidence = active_report_items(trait_data.get("evidence"), text_key="summary")
            if not evidence:
                continue
            wrote_traits = True
            trait = get_trait(ethos_taxonomy, trait_id) or {}
            lines.append(f"### {trait.get('label') or trait_id}")
            lines.extend(f"- {item['_text']}" for item in evidence[:6])
            lines.append("")
    if not wrote_traits:
        lines.append("- No teacher-confirmed trait evidence recorded yet.")
        lines.append("")

    observations = student_data.get("observations") if isinstance(student_data.get("observations"), list) else []
    observations = [obs for obs in observations if isinstance(obs, dict) and not is_personal_observation(obs)]
    if observations:
        lines.append("## Observation Log")
        lines.append("")
        lines.append(f"- {len(observations)} observation(s) recorded locally.")
        recent = observations[-5:]
        for obs in recent:
            if not isinstance(obs, dict):
                continue
            parts = [
                str(obs.get("recorded_at") or "")[:10],
                str(obs.get("template_type") or "observation"),
            ]
            cefr = "/".join(
                str(obs.get(field) or "")
                for field in ("cefr_dimension", "cefr_level_observed", "cefr_direction")
                if obs.get(field)
            )
            if cefr:
                parts.append(cefr)
            lines.append(f"- `{obs.get('observation_id')}` - " + " | ".join(p for p in parts if p))
        lines.append("")

    # DOES boundary (Lens Primitive, 2026-08-04): this file is uploaded to a
    # shared Drive folder, so it may only ever contain what we explicitly
    # choose to put here. Raw observation narration (raw_transcript /
    # teacher_edited_transcript) is deliberately never rendered below —
    # that free-text narration is where causal ("why") language about a
    # student actually appears. The Support Profile section above already
    # carries the categorized, shareable "what helps" content. See
    # dev/SPEC_LENS_PRIMITIVE_2026-08-04.md.

    lines.append("## Privacy Boundary")
    lines.append("")
    lines.append("- Raw observation narration is device-local and is not included in this shared lens.")
    lines.append("- Personal Context / safeguarding evidence is omitted from this shared lens.")
    lines.append("- Model-suggested or unconfirmed evidence is omitted.")
    lines.append("")

    lines.append("---")
    lines.append(f"*Generated by Lingua Viva · {updated}*")
    return "\n".join(line for line in lines if line is not None)


def _safe_filename(name: str) -> str:
    """Create a Drive-safe filename from a student name."""
    safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in name)
    return safe.strip()[:50] or "student"


def _personal_observation_markdown(student_id: str, observations: list[dict]) -> str:
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# Personal Observation Records - {student_id}",
        "",
        "These records are routed only to the mapped Personal folder.",
        "",
    ]
    for obs in observations:
        lines.extend([
            f"## {obs.get('observation_id')}",
            "",
            f"- Student ID: `{student_id}`",
            f"- Recorded: {str(obs.get('recorded_at') or '')}",
            f"- Category: Personal",
            f"- Template: {str(obs.get('template_type') or 'observation')}",
            "",
        ])
        summary = str(obs.get("evidence_summary") or obs.get("need_statement") or "").strip()
        if summary:
            lines.extend(["### Whitewashed Summary", "", f"- {summary}", ""])
    lines.extend([
        "## Privacy Boundary",
        "",
        "- Raw narration is device-local and is not included.",
        "- This artifact must stay in the restricted Personal Drive folder.",
        "",
        f"*Generated by Lingua Viva · {updated}*",
    ])
    return "\n".join(lines)


def _personal_observations(lens_data: dict) -> list[dict]:
    observations = lens_data.get("observations")
    if not isinstance(observations, list):
        return []
    kept = []
    for obs in observations:
        if not isinstance(obs, dict):
            continue
        category = str(obs.get("support_category") or "").strip()
        if is_personal_support_category(category):
            kept.append(obs)
    return kept


async def sync_lens_to_drive(student_id: str) -> bool:
    """Push a student lens to the configured Drive sync folder.

    Returns True if sync succeeded, False if it failed or was skipped.
    This function is designed to be called via asyncio.create_task() —
    it never raises.
    """
    try:
        folder_map = get_sync_folder_map()
        folder_id = folder_map.get(DEFAULT_SHARED_CATEGORY)
        if not folder_id:
            record_sync_attempt(
                student_id,
                status="queued",
                category=DEFAULT_SHARED_CATEGORY,
                reason="student summaries folder is not configured",
            )
            return False

        # Load the student lens (full export includes observations) and this
        # machine's per-teacher ledgers while the store is open.
        from src.education.student_lens import StudentLensStore

        store = StudentLensStore()
        try:
            lens_data = store.export_lens(student_id)
            if not lens_data:
                return False
            # Un-provisioned identity guard (teacher-identity P1, 2026-08-02):
            # every fresh install authors rows as "local-teacher", so two
            # machines exporting under that id would produce the SAME ledger
            # filename and silently overwrite each other in Drive. Ledgers
            # for the sentinel id are never exported — the markdown lens
            # still syncs, and Settings → Teacher identity unlocks sharing.
            ledgers = {
                teacher_id: build_ledger_ndjson(store, student_id, teacher_id)
                for teacher_id in store.local_teacher_ids(student_id)
                if teacher_id != UNPROVISIONED_TEACHER_ID
            }
        finally:
            store.close()

        # Format as markdown
        content = format_lens_markdown(lens_data)
        display_name = lens_data.get("display_name", student_id)
        filename = f"{_safe_filename(display_name)}_lens.md"
        personal_obs = _personal_observations(lens_data)
        personal_folder_id = folder_map.get(PERSONAL_CATEGORY)

        # Upload to Drive
        from src.lingua_viva.google_drive_integration import (
            upload_text_to_folder,
        )
        from src.lingua_viva.privacy import assert_safe_for_external_output

        assert_safe_for_external_output(content)

        await asyncio.to_thread(
            upload_text_to_folder,
            folder_id=folder_id,
            filename=filename,
            content=content,
            mime_type="text/markdown",
        )
        record_sync_attempt(student_id, status="pushed", category=DEFAULT_SHARED_CATEGORY)

        # Machine-readable ledger alongside the human-readable lens: same
        # data class, same destination — full-state overwrite each sync,
        # ID-only filename.
        for teacher_id, ledger in ledgers.items():
            assert_safe_for_external_output(ledger)
            await asyncio.to_thread(
                upload_text_to_folder,
                folder_id=folder_id,
                filename=f"{student_id}.{teacher_id}{LEDGER_SUFFIX}",
                content=ledger,
                mime_type="application/x-ndjson",
            )
        if personal_obs:
            if not personal_folder_id:
                record_sync_attempt(
                    student_id,
                    status="queued",
                    category=PERSONAL_CATEGORY,
                    reason="personal folder is not configured",
                )
                logger.warning("Personal observations for %s were not synced: no Personal folder configured", student_id)
            else:
                personal_content = _personal_observation_markdown(student_id, personal_obs)
                assert_safe_for_external_output(personal_content)
                await asyncio.to_thread(
                    upload_text_to_folder,
                    folder_id=personal_folder_id,
                    filename=f"{student_id}.personal.md",
                    content=personal_content,
                    mime_type="text/markdown",
                )
                record_sync_attempt(student_id, status="pushed", category=PERSONAL_CATEGORY)
        logger.info(f"Synced lens for {student_id} to Drive folder {folder_id}")
        return True

    except Exception as exc:
        logger.warning(f"Drive sync failed for {student_id}: {exc}")
        record_sync_attempt(
            student_id,
            status="failed",
            category=DEFAULT_SHARED_CATEGORY,
            reason=type(exc).__name__,
        )
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
        category = str(row.get("support_category") or "").strip()
        if is_personal_support_category(category):
            continue
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
                    header_teacher = str(header.get("teacher_id") or "")
                    # Never import a ledger authored under the un-provisioned
                    # sentinel: it is un-attributable (any number of machines
                    # share that id), and importing it would misattribute a
                    # colleague's rows as one ambiguous author. Such ledgers
                    # can only exist as stale artifacts from builds that
                    # pre-date the identity guard.
                    if header_teacher == UNPROVISIONED_TEACHER_ID:
                        result["skipped"] += 1
                        continue
                    if header_teacher in own_teacher_ids:
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
