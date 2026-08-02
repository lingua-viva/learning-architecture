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
