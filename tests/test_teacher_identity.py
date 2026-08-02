"""Teacher identity provisioning tests (teacher-identity P1, 2026-08-02).

Every machine used to author observations as the "local-teacher" default, so
two teachers on two machines exported the SAME ledger filename (silent
overwrite in Drive) and skipped each other's ledger on pull as "own" —
multi-machine triangulation was inert. This suite pins the fix end to end:

  1. config: own_teacher_id in school_profile.json, "local-teacher" reserved
  2. identity seam: configured_teacher_id / effective_teacher_id resolution
  3. backfill: rename_local_teacher is surgical (imported rows untouched)
  4. endpoint: POST /api/school-profile validation + backfill + display names
  5. drive guards: sentinel ledgers never exported, never imported
  6. two-machine round-trip with distinct provisioned identities

Hermetic per tests/test_triangulation.py's _isolate pattern — never reads
the machine's real ~/.lingua-viva.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from src.education.student_lens import (
    Observation,
    StudentLensStore,
    compute_triangulation,
)
from src.lingua_viva import drive_sync
from src.lingua_viva.access_roles import configured_teacher_id, effective_teacher_id
from src.lingua_viva.config import (
    UNPROVISIONED_TEACHER_ID,
    own_teacher_id,
    read_school_profile,
    school_profile_path,
)
from src.web import app


def _isolate(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "students.db"))
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("LV_PRIVACY_LOG_PATH", str(tmp_path / "privacy.ndjson"))
    monkeypatch.setenv("LV_REVISION_LOG_PATH", str(tmp_path / "revision.ndjson"))
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path / "config-home"))
    monkeypatch.delenv("LV_AUTH_MODE", raising=False)


def _write_profile(data: dict):
    path = school_profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _obs_row(student_id: str, teacher_id: str, **overrides) -> dict:
    row = Observation(
        student_id=student_id,
        teacher_id=teacher_id,
        template_type="literacy",
        raw_transcript="Read a full paragraph aloud with growing confidence.",
    ).to_row()
    row.update(overrides)
    return row


def _append_local(store: StudentLensStore, student_id: str, teacher_id: str, **overrides):
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


def _ledger_text(student_id: str, teacher_id: str, rows: list) -> str:
    header = {
        "schema": drive_sync.LEDGER_SCHEMA,
        "teacher_id": teacher_id,
        "student_id": student_id,
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }
    lines = [json.dumps(header)]
    for row in rows:
        lines.append(row if isinstance(row, str) else json.dumps(row))
    return "\n".join(lines) + "\n"


def _fake_drive(monkeypatch, files: dict[str, str]):
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


# ---------------------------------------------------------------------------
# 1. Config: own_teacher_id passthrough + reserved sentinel
# ---------------------------------------------------------------------------

def test_own_teacher_id_defaults_to_unprovisioned(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    assert own_teacher_id() == ""
    assert read_school_profile()["own_teacher_id"] == ""


def test_own_teacher_id_reads_config(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    _write_profile({"own_teacher_id": "  claudia-cf  "})
    assert own_teacher_id() == "claudia-cf"


def test_sentinel_in_config_file_stays_unprovisioned(monkeypatch, tmp_path):
    """A hand-edited file claiming the reserved id is never a real identity."""
    _isolate(monkeypatch, tmp_path)
    _write_profile({"own_teacher_id": UNPROVISIONED_TEACHER_ID})
    assert own_teacher_id() == ""


def test_invalid_own_teacher_id_type_degrades(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    _write_profile({"own_teacher_id": ["not", "a", "string"]})
    assert own_teacher_id() == ""


# ---------------------------------------------------------------------------
# 2. Identity seam: configured_teacher_id / effective_teacher_id (off mode)
# ---------------------------------------------------------------------------

def test_default_and_empty_ids_resolve_to_configured(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    _write_profile({"own_teacher_id": "claudia-cf"})
    assert configured_teacher_id(UNPROVISIONED_TEACHER_ID) == "claudia-cf"
    assert configured_teacher_id("") == "claudia-cf"


def test_explicit_id_wins_over_configured(monkeypatch, tmp_path):
    """Co-teachers sharing one machine can still attribute to themselves."""
    _isolate(monkeypatch, tmp_path)
    _write_profile({"own_teacher_id": "claudia-cf"})
    assert configured_teacher_id("marco-r") == "marco-r"


def test_unprovisioned_machine_passes_ids_through(monkeypatch, tmp_path):
    """Without a configured id nothing changes — the pre-identity behavior."""
    _isolate(monkeypatch, tmp_path)
    assert configured_teacher_id(UNPROVISIONED_TEACHER_ID) == UNPROVISIONED_TEACHER_ID
    assert configured_teacher_id("") == ""
    assert configured_teacher_id("marco-r") == "marco-r"


def test_effective_teacher_id_off_mode_uses_configured(monkeypatch, tmp_path):
    """The single seam behind every `or "local-teacher"` fallback in web.py."""
    _isolate(monkeypatch, tmp_path)
    _write_profile({"own_teacher_id": "claudia-cf"})
    assert effective_teacher_id(None, UNPROVISIONED_TEACHER_ID) == "claudia-cf"
    assert effective_teacher_id(None, "marco-r") == "marco-r"


# ---------------------------------------------------------------------------
# 3. Backfill: rename_local_teacher is surgical
# ---------------------------------------------------------------------------

def test_rename_local_teacher_renames_local_rows_only(tmp_path):
    store = StudentLensStore(db_path=tmp_path / "s.db")
    sid = store.create_lens(display_name="Marco Bianchi")
    local = _append_local(
        store, sid, UNPROVISIONED_TEACHER_ID,
        support_category="communication_and_language",
        need_statement="Needs vocabulary pre-teaching.",
    )
    store.import_observation_rows([
        _obs_row(sid, "t-colleague-b",
                 support_category="communication_and_language",
                 need_statement="Colleague B: needs sentence starters."),
    ])

    result = store.rename_local_teacher(UNPROVISIONED_TEACHER_ID, "claudia-cf")
    assert result == {"renamed": 1}

    lens = store.export_lens(sid)
    by_id = {o["observation_id"]: o for o in lens["observations"]}
    assert by_id[local.observation_id]["teacher_id"] == "claudia-cf"
    assert by_id[local.observation_id]["origin"] == "local"
    imported = [o for o in lens["observations"] if o["origin"] == "imported"]
    assert imported and all(o["teacher_id"] == "t-colleague-b" for o in imported)

    # Support-profile fan-out follows: local entry re-attributed, the
    # colleague's imported_verified entry untouched.
    needs = lens["support_profile"]["categories"]["communication_and_language"]["needs"]
    authors = {n["created_by"] for n in needs}
    assert authors == {"claudia-cf", "t-colleague-b"}
    assert UNPROVISIONED_TEACHER_ID not in authors
    store.close()


def test_rename_fixes_triangulation_authorship(tmp_path):
    """The point of the backfill: after provisioning, corroboration counts
    the local teacher under the real id, not the sentinel."""
    store = StudentLensStore(db_path=tmp_path / "s.db")
    sid = store.create_lens(display_name="Marco Bianchi")
    _append_local(
        store, sid, UNPROVISIONED_TEACHER_ID,
        support_category="communication_and_language",
        need_statement="Needs sentence starters.",
    )
    store.import_observation_rows([
        _obs_row(sid, "t-colleague-b",
                 support_category="communication_and_language",
                 need_statement="Colleague B: needs oral scaffolds."),
    ])
    store.rename_local_teacher(UNPROVISIONED_TEACHER_ID, "claudia-cf")

    tri = compute_triangulation(store.export_lens(sid))
    assert tri["local_teacher_ids"] == ["claudia-cf"]
    cat = tri["categories"]["communication_and_language"]
    assert cat["status"] == "corroborated"
    assert set(cat["teachers"]) == {"claudia-cf", "t-colleague-b"}
    store.close()


def test_rename_same_id_is_a_noop(tmp_path):
    store = StudentLensStore(db_path=tmp_path / "s.db")
    sid = store.create_lens(display_name="Marco Bianchi")
    _append_local(store, sid, "claudia-cf")
    assert store.rename_local_teacher("claudia-cf", "claudia-cf") == {"renamed": 0}
    store.close()


def test_rename_updates_ledger_export_identity(tmp_path):
    """After the backfill the machine's ledgers carry the real id — the
    filename collision between machines is gone."""
    store = StudentLensStore(db_path=tmp_path / "s.db")
    sid = store.create_lens(display_name="Marco Bianchi")
    _append_local(store, sid, UNPROVISIONED_TEACHER_ID)
    store.rename_local_teacher(UNPROVISIONED_TEACHER_ID, "claudia-cf")

    assert store.local_teacher_ids(sid) == ["claudia-cf"]
    ledger = drive_sync.build_ledger_ndjson(store, sid, "claudia-cf")
    header = json.loads(ledger.splitlines()[0])
    assert header["teacher_id"] == "claudia-cf"
    store.close()


# ---------------------------------------------------------------------------
# 4. POST /api/school-profile: validation, backfill, display names
# ---------------------------------------------------------------------------

def test_school_profile_post_rejects_bad_payloads(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        assert client.post("/api/school-profile", json={}).status_code == 400
        assert client.post(
            "/api/school-profile", json={"own_teacher_id": 42}
        ).status_code == 400
        assert client.post(
            "/api/school-profile", json={"own_teacher_id": "has spaces"}
        ).status_code == 400
        assert client.post(
            "/api/school-profile", json={"own_teacher_id": "   "}
        ).status_code == 400
        # The sentinel is reserved — claiming it would defeat the guard.
        reserved = client.post(
            "/api/school-profile", json={"own_teacher_id": UNPROVISIONED_TEACHER_ID}
        )
        assert reserved.status_code == 400
        assert "reserved" in reserved.json()["error"]
        # Category labels stay file-managed, never writable here.
        assert client.post(
            "/api/school-profile", json={"category_labels": {}}
        ).status_code == 400
        assert client.post(
            "/api/school-profile", json={"teacher_display_names": {"a": 1}}
        ).status_code == 400
        # Nothing was persisted by any of the rejected calls.
        assert read_school_profile()["own_teacher_id"] == ""


def test_school_profile_post_sets_identity_and_backfills(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        created = client.post(
            "/api/students", json={"display_name": "Marco Bianchi", "grade_level": "G3"}
        )
        sid = created.json()["student_id"]
        store = StudentLensStore()
        local = _append_local(store, sid, UNPROVISIONED_TEACHER_ID)
        store.close()

        res = client.post("/api/school-profile", json={"own_teacher_id": "claudia-cf"})
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "saved"
        assert body["own_teacher_id"] == "claudia-cf"
        assert body["renamed"] >= 1

        # Persisted: GET reflects it, and the sentinel row was re-attributed.
        assert client.get("/api/school-profile").json()["own_teacher_id"] == "claudia-cf"
        lens = client.get(f"/api/students/{sid}/lens").json()
        obs = next(o for o in lens["observations"] if o["observation_id"] == local.observation_id)
        assert obs["teacher_id"] == "claudia-cf"


def test_school_profile_post_preserves_unrelated_config(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    _write_profile({
        "category_labels": {"learning_and_cognition": "Learning & Cognition (IB)"},
        "hidden_categories": [],
    })
    with TestClient(app) as client:
        res = client.post("/api/school-profile", json={"own_teacher_id": "claudia-cf"})
        assert res.status_code == 200
    profile = read_school_profile()
    assert profile["own_teacher_id"] == "claudia-cf"
    assert profile["category_labels"] == {"learning_and_cognition": "Learning & Cognition (IB)"}
    assert profile["hidden_categories"] == []


def test_school_profile_post_display_names_roundtrip(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        res = client.post(
            "/api/school-profile",
            json={"teacher_display_names": {" marco-r ": " Marco Rossi ", "": "dropped"}},
        )
        assert res.status_code == 200
        assert res.json()["teacher_display_names"] == {"marco-r": "Marco Rossi"}
        assert res.json()["renamed"] == 0  # names alone never trigger a backfill

        cleared = client.post("/api/school-profile", json={"teacher_display_names": {}})
        assert cleared.status_code == 200
        assert cleared.json()["teacher_display_names"] == {}


def test_reprovisioning_renames_from_previous_id(monkeypatch, tmp_path):
    """Changing an already-set id migrates rows from the OLD id, not from
    the sentinel — previous_id is captured before the config write."""
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        created = client.post(
            "/api/students", json={"display_name": "Marco Bianchi", "grade_level": "G3"}
        )
        sid = created.json()["student_id"]
        assert client.post(
            "/api/school-profile", json={"own_teacher_id": "claudia"}
        ).status_code == 200
        store = StudentLensStore()
        local = _append_local(store, sid, "claudia")
        store.close()

        res = client.post("/api/school-profile", json={"own_teacher_id": "claudia-cf"})
        assert res.status_code == 200
        assert res.json()["renamed"] >= 1
        lens = client.get(f"/api/students/{sid}/lens").json()
        obs = next(o for o in lens["observations"] if o["observation_id"] == local.observation_id)
        assert obs["teacher_id"] == "claudia-cf"


# ---------------------------------------------------------------------------
# 5. Drive guards: the sentinel never travels
# ---------------------------------------------------------------------------

def test_sync_never_exports_unprovisioned_ledger(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    drive_sync.set_sync_folder_id("folder-abc")
    store = StudentLensStore()
    sid = store.create_lens(display_name="Marco Bianchi")
    _append_local(store, sid, UNPROVISIONED_TEACHER_ID)
    store.close()

    uploads = []

    def fake_upload(folder_id, filename, content, mime_type="text/markdown", **kwargs):
        uploads.append(filename)
        return {"id": "up-1", "name": filename}

    monkeypatch.setattr(
        "src.lingua_viva.google_drive_integration.upload_text_to_folder", fake_upload
    )
    assert asyncio.run(drive_sync.sync_lens_to_drive(sid)) is True
    # The markdown lens still syncs; the ambiguous ledger does not.
    assert uploads
    assert not any(name.endswith(drive_sync.LEDGER_SUFFIX) for name in uploads)


def test_sync_exports_ledger_once_provisioned(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    drive_sync.set_sync_folder_id("folder-abc")
    store = StudentLensStore()
    sid = store.create_lens(display_name="Marco Bianchi")
    _append_local(store, sid, UNPROVISIONED_TEACHER_ID)
    store.rename_local_teacher(UNPROVISIONED_TEACHER_ID, "claudia-cf")
    store.close()

    uploads = []

    def fake_upload(folder_id, filename, content, mime_type="text/markdown", **kwargs):
        uploads.append(filename)
        return {"id": "up-1", "name": filename}

    monkeypatch.setattr(
        "src.lingua_viva.google_drive_integration.upload_text_to_folder", fake_upload
    )
    assert asyncio.run(drive_sync.sync_lens_to_drive(sid)) is True
    ledgers = [n for n in uploads if n.endswith(drive_sync.LEDGER_SUFFIX)]
    assert ledgers == [f"{sid}.claudia-cf{drive_sync.LEDGER_SUFFIX}"]


def test_pull_skips_unprovisioned_ledger(monkeypatch, tmp_path):
    """Stale `*.local-teacher.ledger.ndjson` artifacts from pre-guard builds
    are un-attributable and must never import."""
    _isolate(monkeypatch, tmp_path)
    drive_sync.set_sync_folder_id("folder-abc")
    store = StudentLensStore()
    sid = store.create_lens(display_name="Marco Bianchi")
    store.close()

    ledger = _ledger_text(
        sid, UNPROVISIONED_TEACHER_ID, [_obs_row(sid, UNPROVISIONED_TEACHER_ID)]
    )
    _fake_drive(monkeypatch, {f"{sid}.{UNPROVISIONED_TEACHER_ID}.ledger.ndjson": ledger})

    result = drive_sync.pull_shared_ledgers()
    assert result == {"files_seen": 1, "imported": 0, "skipped": 1, "errors": 0}


# ---------------------------------------------------------------------------
# 6. Two-machine round-trip with provisioned identities
# ---------------------------------------------------------------------------

def test_two_provisioned_machines_triangulate(monkeypatch, tmp_path):
    """The P1 scenario, fixed: Anna's machine exports under her id, Marco's
    machine imports it as a colleague ledger and both authors triangulate."""
    # Machine A (Anna): provisioned late — backfill, then export.
    store_a = StudentLensStore(db_path=tmp_path / "machine-a.db")
    sid = store_a.create_lens(display_name="Marco Bianchi")
    _append_local(
        store_a, sid, UNPROVISIONED_TEACHER_ID,
        support_category="communication_and_language",
        need_statement="Anna: needs sentence starters.",
    )
    store_a.rename_local_teacher(UNPROVISIONED_TEACHER_ID, "t-anna")
    anna_ledger = drive_sync.build_ledger_ndjson(store_a, sid, "t-anna")
    store_a.close()

    # Machine B (Marco): same student id (school roster import), own id set.
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "machine-b.db"))
    drive_sync.set_sync_folder_id("folder-abc")
    store_b = StudentLensStore()
    assert store_b.create_lens(display_name="Marco Bianchi", student_id=sid) == sid
    _append_local(
        store_b, sid, "t-marco",
        support_category="communication_and_language",
        need_statement="Marco: needs oral scaffolds.",
    )
    store_b.close()

    _fake_drive(monkeypatch, {f"{sid}.t-anna{drive_sync.LEDGER_SUFFIX}": anna_ledger})
    result = drive_sync.pull_shared_ledgers()
    assert result["imported"] == 1
    assert result["errors"] == 0

    store_b = StudentLensStore()
    tri = compute_triangulation(store_b.export_lens(sid))
    assert tri["local_teacher_ids"] == ["t-marco"]
    by_id = {c["teacher_id"]: c for c in tri["colleagues"]}
    assert by_id["t-anna"]["origin"] == "imported"
    cat = tri["categories"]["communication_and_language"]
    assert cat["status"] == "corroborated"
    assert set(cat["teachers"]) == {"t-anna", "t-marco"}
    store_b.close()
