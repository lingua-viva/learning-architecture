"""Multi-teacher triangulation tests.

SPEC_LV_MULTI_TEACHER_TRIANGULATION_2026-08-01: per-teacher observation
ledgers in the school's own shared Drive folder, append-only UUID merge with
provenance, deterministic convergence/divergence signals, and the teacher's
right to remove a colleague's imported data.

Hermetic: store-level tests use an explicit tmp db; pull/web tests use the
_isolate env pattern (tests/test_school_categories.py) plus monkeypatched
Drive helpers — no network, never the machine's real ~/.lingua-viva.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from src.education.student_lens import (
    NARRATION_NOT_SHARED,
    Observation,
    StudentLensStore,
    compute_triangulation,
)
from src.lingua_viva import drive_sync
from src.web import app


def _isolate(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "students.db"))
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("LV_PRIVACY_LOG_PATH", str(tmp_path / "privacy.ndjson"))
    monkeypatch.setenv("LV_REVISION_LOG_PATH", str(tmp_path / "revision.ndjson"))
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path / "config-home"))
    monkeypatch.delenv("LV_AUTH_MODE", raising=False)


def _days_ago(days: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _obs_row(student_id: str, teacher_id: str, **overrides) -> dict:
    row = Observation(
        student_id=student_id,
        teacher_id=teacher_id,
        template_type="literacy",
        raw_transcript="Read a full paragraph aloud with growing confidence.",
    ).to_row()
    row.update(overrides)
    return row


def _append_local(store: StudentLensStore, student_id: str, teacher_id: str = "t-local", **overrides):
    obs = Observation(
        student_id=student_id,
        teacher_id=teacher_id,
        template_type="literacy",
        raw_transcript="Local note about classroom reading.",
    )
    for key, value in overrides.items():
        setattr(obs, key, value)
    store.append_observation(obs)
    return obs


def _ledger_text(student_id: str, teacher_id: str, rows: list, schema: str = drive_sync.LEDGER_SCHEMA) -> str:
    header = {
        "schema": schema,
        "teacher_id": teacher_id,
        "student_id": student_id,
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }
    lines = [json.dumps(header)]
    for row in rows:
        lines.append(row if isinstance(row, str) else json.dumps(row))
    return "\n".join(lines) + "\n"


def _fake_drive(monkeypatch, files: dict[str, str]):
    """files: filename -> content. Patches the two Drive helpers pull uses."""
    listing = [{"id": f"f-{i}", "name": name} for i, name in enumerate(files)]
    contents = {f"f-{i}": text for i, text in enumerate(files.values())}
    monkeypatch.setattr(
        "src.lingua_viva.google_drive_integration.list_folder_files",
        lambda folder_id, **kwargs: listing,
    )
    monkeypatch.setattr(
        "src.lingua_viva.google_drive_integration.download_file_text",
        lambda file_id, **kwargs: contents[file_id],
    )


def _privacy_events(tmp_path: Path) -> list[dict]:
    path = tmp_path / "privacy.ndjson"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# 1. Append-only merge: idempotence + provenance
# ---------------------------------------------------------------------------

def test_import_is_append_only_and_idempotent(tmp_path):
    store = StudentLensStore(db_path=tmp_path / "s.db")
    sid = store.create_lens(display_name="Marco Bianchi")
    rows = [_obs_row(sid, "t-colleague-b"), _obs_row(sid, "t-colleague-b")]

    first = store.import_observation_rows(rows)
    assert first == {"imported": 2, "skipped": 0}

    # Double-import: every UUID is already known — nothing changes.
    second = store.import_observation_rows(rows)
    assert second == {"imported": 0, "skipped": 2}

    lens = store.export_lens(sid)
    assert len(lens["observations"]) == 2
    for obs in lens["observations"]:
        assert obs["origin"] == "imported"
        assert obs["teacher_id"] == "t-colleague-b"  # original author preserved
    store.close()


def test_import_skips_unknown_students_and_invalid_rows(tmp_path):
    store = StudentLensStore(db_path=tmp_path / "s.db")
    sid = store.create_lens(display_name="Marco Bianchi")
    rows = [
        _obs_row("no-such-student", "t-colleague-b"),
        {"nonsense": True},
        _obs_row(sid, "t-colleague-b", raw_transcript=""),  # fails Observation.validate()
        _obs_row(sid, "t-colleague-b"),
    ]
    result = store.import_observation_rows(rows)
    assert result == {"imported": 1, "skipped": 3}
    store.close()


def test_import_fans_out_support_at_imported_verified(tmp_path):
    store = StudentLensStore(db_path=tmp_path / "s.db")
    sid = store.create_lens(display_name="Marco Bianchi")
    row = _obs_row(
        sid,
        "t-colleague-b",
        support_category="communication_and_language",
        need_statement="Needs sentence starters for oral answers.",
    )
    assert store.import_observation_rows([row])["imported"] == 1

    lens = store.export_lens(sid)
    needs = lens["support_profile"]["categories"]["communication_and_language"]["needs"]
    assert len(needs) == 1
    assert needs[0]["confidence"] == "imported_verified"
    assert needs[0]["created_by"] == "t-colleague-b"
    store.close()


# ---------------------------------------------------------------------------
# 2. Remove a colleague's data — surgical
# ---------------------------------------------------------------------------

def test_remove_imported_is_surgical(tmp_path):
    store = StudentLensStore(db_path=tmp_path / "s.db")
    sid = store.create_lens(display_name="Marco Bianchi")
    _append_local(
        store, sid, "t-local",
        support_category="communication_and_language",
        need_statement="Local: needs vocabulary pre-teaching.",
    )
    store.import_observation_rows([
        _obs_row(sid, "t-colleague-b",
                 support_category="communication_and_language",
                 need_statement="Colleague B: needs sentence starters."),
        _obs_row(sid, "t-marco",
                 support_category="social_skills",
                 strength_statement="Marco: welcomes new students warmly."),
    ])

    result = store.remove_imported(sid, "t-colleague-b")
    assert result == {"removed": 1}

    lens = store.export_lens(sid)
    remaining_teachers = {o["teacher_id"] for o in lens["observations"]}
    assert remaining_teachers == {"t-local", "t-marco"}

    categories = lens["support_profile"]["categories"]
    needs_authors = {n["created_by"] for n in categories["communication_and_language"]["needs"]}
    assert needs_authors == {"t-local"}  # colleague B's fan-out gone, local untouched
    strength_authors = {s["created_by"] for s in categories["social_skills"]["strengths"]}
    assert strength_authors == {"t-marco"}  # other colleague untouched

    # Removing again is a no-op, not an error.
    assert store.remove_imported(sid, "t-colleague-b") == {"removed": 0}
    store.close()


# ---------------------------------------------------------------------------
# 3. Ledger export: local rows only (echo prevention), IDs never names
# ---------------------------------------------------------------------------

def test_ledger_exports_local_rows_only(tmp_path):
    store = StudentLensStore(db_path=tmp_path / "s.db")
    sid = store.create_lens(display_name="Marco Bianchi")
    local = _append_local(store, sid, "t-local")
    store.import_observation_rows([_obs_row(sid, "t-colleague-b")])

    assert store.local_teacher_ids(sid) == ["t-local"]

    ledger = drive_sync.build_ledger_ndjson(store, sid, "t-local")
    lines = [json.loads(line) for line in ledger.strip().splitlines()]
    header, rows = lines[0], lines[1:]
    assert header["schema"] == drive_sync.LEDGER_SCHEMA
    assert header["teacher_id"] == "t-local"
    assert header["student_id"] == sid
    # Imported colleague rows never re-export — no echo between machines.
    assert [r["observation_id"] for r in rows] == [local.observation_id]
    # The local provenance column never travels.
    assert all("origin" not in r for r in rows)
    store.close()


def test_ledger_rows_never_carry_raw_narration(tmp_path):
    """Lens Primitive DOES boundary (2026-08-04): raw_transcript is where a
    teacher's spoken/typed narration lives — exactly the surface where
    causal ("why") language about a student shows up. A colleague's
    ledger row must never carry it, by construction, regardless of what a
    teacher actually wrote."""
    store = StudentLensStore(db_path=tmp_path / "s.db")
    sid = store.create_lens(display_name="Marco Bianchi")
    _append_local(
        store,
        sid,
        "t-local",
        raw_transcript="His mother was hurt in the war and he still struggles with it.",
        teacher_edited_transcript="Edited: his mother was hurt in the war.",
    )

    ledger = drive_sync.build_ledger_ndjson(store, sid, "t-local")
    rows = [json.loads(line) for line in ledger.strip().splitlines()][1:]
    assert len(rows) == 1
    assert rows[0]["raw_transcript"] == NARRATION_NOT_SHARED
    assert "war" not in rows[0]["raw_transcript"]
    assert rows[0]["teacher_edited_transcript"] is None

    # The neutralized row still imports cleanly on the receiving side —
    # blanking narration must not silently break triangulation.
    other = StudentLensStore(db_path=tmp_path / "other.db")
    other.create_lens(student_id=sid, display_name="Marco Bianchi")
    result = other.import_observation_rows(rows)
    assert result == {"imported": 1, "skipped": 0}
    other.close()
    store.close()


def test_drive_markdown_never_renders_raw_observation_text(tmp_path, monkeypatch):
    """The Drive-bound markdown lens is a shared, cross-teacher artifact —
    it must only ever contain what we explicitly assemble for it. Raw
    observation narration must never appear, however it's spelled."""
    lens_data = {
        "display_name": "Marco Bianchi",
        "student_id": "stu-1",
        "grade_level": "G3",
        "cefr_trajectory": "progressing",
        "support_profile": {"categories": {}},
        "observations": [
            {
                "created_at": "2026-08-04T00:00:00Z",
                "raw_transcript": "His mother was hurt in the war and he still struggles with it.",
            }
        ],
        "recent_observations": [
            {
                "created_at": "2026-08-04T00:00:00Z",
                "text": "His mother was hurt in the war and he still struggles with it.",
            }
        ],
    }
    markdown = drive_sync.format_lens_markdown(lens_data)
    assert "war" not in markdown
    assert "Recent Observations" not in markdown
    assert "Privacy Boundary" in markdown


def test_drive_markdown_is_readable_and_omits_personal_context(tmp_path, monkeypatch):
    lens_data = {
        "display_name": "Marco Bianchi",
        "student_id": "stu-1",
        "grade_level": "G3",
        "rti_current_tier": 2,
        "cefr_trajectory_30d": {"speaking": "progressing"},
        "support_profile": {
            "categories": {
                "communication_and_language": {
                    "items": [
                        {
                            "need_statement": "Needs sentence starters for oral rehearsal.",
                            "confidence": "teacher_confirmed",
                        }
                    ]
                },
                "personal_context": {
                    "items": [
                        {
                            "need_statement": "Sensitive family detail must remain private.",
                            "confidence": "teacher_confirmed",
                        }
                    ]
                },
            }
        },
        "ethos_profile": {
            "traits": {
                "resilience": {
                    "level": "emerging",
                    "evidence": [
                        {"summary": "Returns to the task after feedback.", "confidence": "teacher_confirmed"}
                    ],
                }
            }
        },
        "observations": [{"observation_id": "obs-1", "created_at": "2026-08-04T00:00:00Z"}],
    }

    markdown = drive_sync.format_lens_markdown(lens_data)

    assert markdown.startswith("# Student Lens - Marco Bianchi")
    assert "## Support Profile" in markdown
    assert "Communication and Language" in markdown
    assert "Needs sentence starters" in markdown
    assert "Personal Context" in markdown
    assert "Sensitive family detail" not in markdown
    assert "obs-1" in markdown


def test_sync_uploads_id_only_ledger_filenames(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    drive_sync.set_sync_folder_id("folder-abc")
    store = StudentLensStore()
    sid = store.create_lens(display_name="Marco Bianchi")
    _append_local(store, sid, "t-local")
    store.close()

    uploads = []

    def fake_upload(folder_id, filename, content, mime_type="text/markdown", **kwargs):
        uploads.append({"folder_id": folder_id, "filename": filename, "content": content, "mime_type": mime_type})
        return {"id": "up-1", "name": filename}

    monkeypatch.setattr(
        "src.lingua_viva.google_drive_integration.upload_text_to_folder", fake_upload
    )
    assert asyncio.run(drive_sync.sync_lens_to_drive(sid)) is True

    ledger_uploads = [u for u in uploads if u["filename"].endswith(drive_sync.LEDGER_SUFFIX)]
    assert len(ledger_uploads) == 1
    assert ledger_uploads[0]["filename"] == f"{sid}.t-local{drive_sync.LEDGER_SUFFIX}"
    # IDs, never names, in ledger filenames (operator ruling 2026-08-01).
    assert "Marco" not in ledger_uploads[0]["filename"]
    assert json.loads(ledger_uploads[0]["content"].splitlines()[0])["schema"] == drive_sync.LEDGER_SCHEMA


def test_folder_map_round_trip(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)

    folder_map = drive_sync.set_sync_folder_map({
        "student_summaries": "folder-summary",
        "personal": "folder-personal",
    })

    assert folder_map == {
        "student_summaries": "folder-summary",
        "personal": "folder-personal",
    }
    assert drive_sync.get_sync_folder_id() == "folder-summary"
    assert drive_sync.get_sync_folder_id_for_category("Personal") == "folder-personal"


def test_personal_observation_is_excluded_from_shared_lens_and_ledger(tmp_path):
    store = StudentLensStore(db_path=tmp_path / "s.db")
    sid = store.create_lens(display_name="Marco Bianchi")
    _append_local(
        store,
        sid,
        "t-local",
        support_category="personal_context",
        need_statement="Family-only context should stay restricted.",
        evidence_summary="Restricted personal context.",
    )

    lens_data = store.export_lens(sid)
    markdown = drive_sync.format_lens_markdown(lens_data)
    ledger = drive_sync.build_ledger_ndjson(store, sid, "t-local")

    assert "Family-only context" not in markdown
    assert "Restricted personal context" not in markdown
    assert "personal_context" not in ledger
    assert "Family-only context" not in ledger
    store.close()


def test_personal_without_folder_is_queued_and_not_uploaded_elsewhere(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    drive_sync.set_sync_folder_map({"student_summaries": "folder-summary"})
    store = StudentLensStore()
    sid = store.create_lens(display_name="Marco Bianchi")
    _append_local(
        store,
        sid,
        "t-local",
        support_category="personal_context",
        need_statement="Restricted family context.",
        evidence_summary="Restricted family context.",
    )
    store.close()
    uploads = []

    def fake_upload(**kwargs):
        uploads.append(kwargs)
        return {"id": f"u-{len(uploads)}", "name": kwargs["filename"]}

    monkeypatch.setattr("src.lingua_viva.google_drive_integration.upload_text_to_folder", fake_upload)

    assert asyncio.run(drive_sync.sync_lens_to_drive(sid)) is True
    assert all(upload["folder_id"] == "folder-summary" for upload in uploads)
    assert not any(upload["filename"].endswith(".personal.md") for upload in uploads)
    ledger = drive_sync.read_sync_ledger()["students"][sid]
    assert ledger["last_status"] == "queued"
    assert ledger["last_category"] == "personal"
    assert "folder" in ledger["failure_reason"]


def test_personal_with_folder_uploads_only_to_personal_folder(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    drive_sync.set_sync_folder_map({
        "student_summaries": "folder-summary",
        "personal": "folder-personal",
    })
    store = StudentLensStore()
    sid = store.create_lens(display_name="Marco Bianchi")
    _append_local(
        store,
        sid,
        "t-local",
        support_category="personal_context",
        need_statement="Restricted family context.",
        evidence_summary="Restricted family context.",
    )
    store.close()
    uploads = []

    def fake_upload(**kwargs):
        uploads.append(kwargs)
        return {"id": f"u-{len(uploads)}", "name": kwargs["filename"]}

    monkeypatch.setattr("src.lingua_viva.google_drive_integration.upload_text_to_folder", fake_upload)

    assert asyncio.run(drive_sync.sync_lens_to_drive(sid)) is True
    personal_uploads = [upload for upload in uploads if upload["folder_id"] == "folder-personal"]
    shared_uploads = [upload for upload in uploads if upload["folder_id"] == "folder-summary"]
    assert [upload["filename"] for upload in personal_uploads] == [f"{sid}.personal.md"]
    assert all("Restricted family context" not in upload["content"] for upload in shared_uploads)


def test_scheduled_sync_queues_unapproved_lens(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    drive_sync.set_sync_folder_map({"student_summaries": "folder-summary"})
    store = StudentLensStore()
    sid = store.create_lens(display_name="Marco Bianchi")
    _append_local(store, sid, "t-local")
    store.close()

    uploads = []
    monkeypatch.setattr(
        "src.lingua_viva.google_drive_integration.upload_text_to_folder",
        lambda **kwargs: uploads.append(kwargs),
    )

    result = asyncio.run(drive_sync.sync_lenses_to_drive(scheduled=True))

    assert result["pushed"] == []
    assert result["queued"][0]["student_id"] == sid
    assert uploads == []
    ledger = drive_sync.read_sync_ledger()["students"][sid]
    assert ledger["last_status"] == "queued"
    assert "approval" in ledger["failure_reason"]


def test_manual_sync_approves_and_daily_sync_skips_until_due(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    drive_sync.set_sync_folder_map({"student_summaries": "folder-summary"})
    store = StudentLensStore()
    sid = store.create_lens(display_name="Marco Bianchi")
    _append_local(store, sid, "t-local")
    store.close()

    uploads = []

    def fake_upload(**kwargs):
        uploads.append(kwargs)
        return {"id": f"u-{len(uploads)}", "name": kwargs["filename"]}

    monkeypatch.setattr("src.lingua_viva.google_drive_integration.upload_text_to_folder", fake_upload)

    manual = asyncio.run(drive_sync.sync_lenses_to_drive(approve=True))
    assert manual["pushed"] == [{"student_id": sid}]
    assert sid in drive_sync.get_sync_approved_lenses()

    scheduled = asyncio.run(drive_sync.sync_lenses_to_drive(scheduled=True))
    assert scheduled["skipped"] == [{"student_id": sid, "reason": "not due"}]


def test_drive_sync_now_route_runs_manual_approval(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    drive_sync.set_sync_folder_map({"student_summaries": "folder-summary"})
    store = StudentLensStore()
    sid = store.create_lens(display_name="Marco Bianchi")
    _append_local(store, sid, "t-local")
    store.close()

    monkeypatch.setattr(
        "src.lingua_viva.google_drive_integration.upload_text_to_folder",
        lambda **kwargs: {"id": "u-1", "name": kwargs["filename"]},
    )

    response = TestClient(app).post("/api/drive/sync-now", json={"approve": True})

    assert response.status_code == 200
    assert response.json()["pushed"] == [{"student_id": sid}]


# ---------------------------------------------------------------------------
# 4. Deterministic triangulation signals
# ---------------------------------------------------------------------------

def test_compute_triangulation_corroborated_and_single_source(tmp_path):
    store = StudentLensStore(db_path=tmp_path / "s.db")
    sid = store.create_lens(display_name="Marco Bianchi")
    _append_local(
        store, sid, "t-local",
        support_category="communication_and_language",
        need_statement="Local: needs sentence starters.",
    )
    _append_local(
        store, sid, "t-local",
        support_category="executive_functioning",
        need_statement="Local: loses track of multi-step instructions.",
    )
    store.import_observation_rows([
        _obs_row(sid, "t-colleague-b",
                 support_category="communication_and_language",
                 need_statement="Colleague B: needs oral scaffolds."),
    ])

    tri = compute_triangulation(store.export_lens(sid))
    assert tri["local_teacher_ids"] == ["t-local"]
    by_id = {c["teacher_id"]: c for c in tri["colleagues"]}
    assert by_id["t-local"]["origin"] == "local"
    assert by_id["t-colleague-b"]["origin"] == "imported"
    assert tri["categories"]["communication_and_language"]["status"] == "corroborated"
    assert set(tri["categories"]["communication_and_language"]["teachers"]) == {"t-local", "t-colleague-b"}
    assert tri["categories"]["executive_functioning"]["status"] == "single_source"
    store.close()


def test_divergence_flagged_inside_30_day_window_only(tmp_path):
    store = StudentLensStore(db_path=tmp_path / "s.db")

    # 29 days apart, different teachers, opposing directions -> flagged.
    sid_a = store.create_lens(display_name="Student A")
    _append_local(store, sid_a, "t-local", cefr_direction="progressing", recorded_at=_days_ago(0))
    store.import_observation_rows(
        [_obs_row(sid_a, "t-colleague-b", cefr_direction="regressing", recorded_at=_days_ago(29))]
    )
    tri_a = compute_triangulation(store.export_lens(sid_a))
    assert len(tri_a["divergence"]) == 1
    flag = tri_a["divergence"][0]
    assert set(flag["teachers"]) == {"t-local", "t-colleague-b"}
    assert set(flag["directions"]) == {"progressing", "regressing"}

    # 31 days apart -> not flagged.
    sid_b = store.create_lens(display_name="Student B")
    _append_local(store, sid_b, "t-local", cefr_direction="progressing", recorded_at=_days_ago(0))
    store.import_observation_rows(
        [_obs_row(sid_b, "t-colleague-b", cefr_direction="regressing", recorded_at=_days_ago(31))]
    )
    assert compute_triangulation(store.export_lens(sid_b))["divergence"] == []

    # Same teacher disagreeing with themselves is not divergence.
    sid_c = store.create_lens(display_name="Student C")
    _append_local(store, sid_c, "t-local", cefr_direction="progressing", recorded_at=_days_ago(0))
    _append_local(store, sid_c, "t-local", cefr_direction="regressing", recorded_at=_days_ago(1))
    assert compute_triangulation(store.export_lens(sid_c))["divergence"] == []
    store.close()


# ---------------------------------------------------------------------------
# 5. Pull from the shared folder (hermetic, faked Drive)
# ---------------------------------------------------------------------------

def test_pull_merges_colleague_ledger_and_logs_privacy_events(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    drive_sync.set_sync_folder_id("folder-abc")
    store = StudentLensStore()
    sid = store.create_lens(display_name="Marco Bianchi")
    _append_local(store, sid, "t-local")
    store.close()

    ledger = _ledger_text(sid, "t-colleague-b", [_obs_row(sid, "t-colleague-b"), _obs_row(sid, "t-colleague-b")])
    _fake_drive(monkeypatch, {
        f"{sid}.t-colleague-b.ledger.ndjson": ledger,
        "Marco_Bianchi_lens.md": "# not a ledger",  # filtered by suffix
    })

    result = drive_sync.pull_shared_ledgers()
    assert result == {"files_seen": 1, "imported": 2, "skipped": 0, "errors": 0}

    events = [e["event_type"] for e in _privacy_events(tmp_path)]
    assert "ledger_pulled" in events
    assert "observations_imported" in events
    # Generic details only — never a student name or a colleague identifier.
    log_text = (tmp_path / "privacy.ndjson").read_text(encoding="utf-8")
    assert "Marco" not in log_text and "t-colleague-b" not in log_text

    # Idempotent second pull: same ledger, nothing new.
    again = drive_sync.pull_shared_ledgers()
    assert again["imported"] == 0
    assert again["skipped"] == 2


def test_pull_skips_own_ledger_by_attribution(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    drive_sync.set_sync_folder_id("folder-abc")
    store = StudentLensStore()
    sid = store.create_lens(display_name="Marco Bianchi")
    local = _append_local(store, sid, "t-local")
    store.close()

    ledger = _ledger_text(sid, "t-local", [_obs_row(sid, "t-local"), local.to_row()])
    _fake_drive(monkeypatch, {f"{sid}.t-local.ledger.ndjson": ledger})

    result = drive_sync.pull_shared_ledgers()
    assert result == {"files_seen": 1, "imported": 0, "skipped": 0, "errors": 0}


def test_pull_skips_unknown_schema_cleanly(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    drive_sync.set_sync_folder_id("folder-abc")
    store = StudentLensStore()
    sid = store.create_lens(display_name="Marco Bianchi")
    store.close()

    ledger = _ledger_text(sid, "t-colleague-b", [_obs_row(sid, "t-colleague-b")], schema="lv_ledger_v99")
    _fake_drive(monkeypatch, {f"{sid}.t-colleague-b.ledger.ndjson": ledger})

    result = drive_sync.pull_shared_ledgers()
    assert result == {"files_seen": 1, "imported": 0, "skipped": 0, "errors": 1}


def test_pull_tolerates_garbage_lines(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    drive_sync.set_sync_folder_id("folder-abc")
    store = StudentLensStore()
    sid = store.create_lens(display_name="Marco Bianchi")
    store.close()

    ledger = _ledger_text(sid, "t-colleague-b", [_obs_row(sid, "t-colleague-b"), "{not json", '["not a dict"]'])
    _fake_drive(monkeypatch, {f"{sid}.t-colleague-b.ledger.ndjson": ledger})

    result = drive_sync.pull_shared_ledgers()
    assert result["imported"] == 1
    assert result["skipped"] == 2
    assert result["errors"] == 0


def test_pull_without_configured_folder_is_a_noop(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    result = drive_sync.pull_shared_ledgers()
    assert result == {"files_seen": 0, "imported": 0, "skipped": 0, "errors": 0}
    assert _privacy_events(tmp_path) == []


# ---------------------------------------------------------------------------
# 6. Web wiring
# ---------------------------------------------------------------------------

def test_lens_endpoint_includes_triangulation_with_display_names(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    config_dir = tmp_path / "config-home" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "school_profile.json").write_text(
        json.dumps({"teacher_display_names": {"t-colleague-b": "Paula Colleague"}}),
        encoding="utf-8",
    )
    with TestClient(app) as client:
        created = client.post("/api/students", json={"display_name": "Marco Bianchi", "grade_level": "G3"})
        sid = created.json()["student_id"]

        store = StudentLensStore()
        store.import_observation_rows([_obs_row(sid, "t-colleague-b")])
        store.close()

        res = client.get(f"/api/students/{sid}/lens")
        assert res.status_code == 200
        tri = res.json()["triangulation"]
        by_id = {c["teacher_id"]: c for c in tri["colleagues"]}
        assert by_id["t-colleague-b"]["author_display"] == "Paula Colleague"
        assert by_id["t-colleague-b"]["origin"] == "imported"


def test_remove_colleague_endpoint(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        created = client.post("/api/students", json={"display_name": "Marco Bianchi", "grade_level": "G3"})
        sid = created.json()["student_id"]

        store = StudentLensStore()
        store.import_observation_rows([_obs_row(sid, "t-colleague-b")])
        store.close()

        missing = client.post(f"/api/students/{sid}/remove-colleague", json={})
        assert missing.status_code == 400

        res = client.post(f"/api/students/{sid}/remove-colleague", json={"teacher_id": "t-colleague-b"})
        assert res.status_code == 200
        assert res.json()["removed"] == 1

        lens = client.get(f"/api/students/{sid}/lens").json()
        assert all(o["teacher_id"] != "t-colleague-b" for o in lens["observations"])


def test_pull_shared_endpoint(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    drive_sync.set_sync_folder_id("folder-abc")
    with TestClient(app) as client:
        created = client.post("/api/students", json={"display_name": "Marco Bianchi", "grade_level": "G3"})
        sid = created.json()["student_id"]

        ledger = _ledger_text(sid, "t-colleague-b", [_obs_row(sid, "t-colleague-b")])
        _fake_drive(monkeypatch, {f"{sid}.t-colleague-b.ledger.ndjson": ledger})

        res = client.post("/api/drive/pull-shared", json={"student_id": sid})
        assert res.status_code == 200
        assert res.json()["imported"] == 1
