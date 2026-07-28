"""P0 — Reflection-log rescue (SPEC_ONE_BUTTON_UPDATE_2026-07-27).

Teacher private reflections were appended inside the app bundle
(LV_ROOT/dev/lv_revision_log.ndjson) — updater-owned territory, erased on
every desktop update. These tests pin the two halves of the rescue:

1. The write path: reflection POSTs land under lv_home(), never LV_ROOT.
2. The migration: legacy entries are rescued exactly once (sentinel +
   revision_id dedupe), only teacher reflections move (the committed dev
   audit trail in a source checkout is repo history, not teacher state),
   and the legacy file is never written.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

import src.web as web
from src.web import app


client = TestClient(app)


def _reflection_entry(revision_id: str, note: str = "a private note") -> dict:
    return {
        "timestamp": "2026-07-25T10:00:00+00:00",
        "revision_id": revision_id,
        "artifact_id": "lv-private-teacher-reflection",
        "artifact_path": "dev/lv_revision_log.ndjson",
        "defect_class": "teacher_reflection",
        "origin": "teacher_input",
        "instrument_that_found_it": "reflect_view",
        "instrument_touched": False,
        "independent_cross_check": "private_teacher_note_no_external_sync",
        "decision": "Record private teacher reflection locally.",
        "proof": note,
        "reviewer": "teacher",
        "teacher_contribution_involved": True,
        "privacy_review": "private_local_only",
        "private": True,
    }


def _dev_audit_entry(revision_id: str) -> dict:
    entry = _reflection_entry(revision_id)
    entry["artifact_id"] = "lv-doctor-branch-gate"
    entry["defect_class"] = "doctor_gate"
    entry["origin"] = "dev_audit"
    del entry["private"]
    return entry


def _write_ndjson(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(entry) + "\n" for entry in entries), encoding="utf-8"
    )


def _read_ids(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [
        json.loads(line)["revision_id"]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_default_revision_log_path_is_under_lv_home(monkeypatch, tmp_path):
    monkeypatch.delenv("LV_REVISION_LOG_PATH", raising=False)
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path / "home"))
    path = web._revision_log_path()
    assert path == tmp_path / "home" / "dev" / "lv_revision_log.ndjson"
    assert web.LV_ROOT not in path.parents


def test_desktop_reflect_post_writes_only_under_lv_home(monkeypatch, tmp_path):
    """Acceptance check 7: reflection POST in desktop mode writes only
    under lv_home(); the bundle (LV_ROOT) stays byte-identical."""
    monkeypatch.setenv("LV_DESKTOP", "1")
    monkeypatch.delenv("LV_REVISION_LOG_PATH", raising=False)
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path / "home"))

    legacy = web._legacy_revision_log_path()
    legacy_before = legacy.read_bytes() if legacy.exists() else None

    response = client.post("/api/reflect/note", json={"note": "Checklist worked."})
    assert response.status_code == 200

    new_log = tmp_path / "home" / "dev" / "lv_revision_log.ndjson"
    assert new_log.exists(), "reflection must land under lv_home()"
    entry = json.loads(new_log.read_text(encoding="utf-8").splitlines()[0])
    assert entry["private"] is True

    legacy_after = legacy.read_bytes() if legacy.exists() else None
    assert legacy_after == legacy_before, "the bundle-side log must never be written"


def test_migration_rescues_only_teacher_reflections(monkeypatch, tmp_path):
    fake_bundle = tmp_path / "bundle"
    monkeypatch.setattr(web, "LV_ROOT", fake_bundle)
    new_log = tmp_path / "state" / "lv_revision_log.ndjson"
    monkeypatch.setenv("LV_REVISION_LOG_PATH", str(new_log))

    _write_ndjson(
        fake_bundle / "dev" / "lv_revision_log.ndjson",
        [
            _reflection_entry("teacher-reflection-1"),
            _dev_audit_entry("dev-audit-1"),
            _reflection_entry("teacher-reflection-2"),
        ],
    )

    migrated = web._migrate_legacy_revision_log()
    assert migrated == 2
    assert _read_ids(new_log) == ["teacher-reflection-1", "teacher-reflection-2"]

    sentinel = new_log.with_name(new_log.name + ".migrated")
    assert sentinel.exists()
    assert json.loads(sentinel.read_text(encoding="utf-8"))["migrated_entries"] == 2


def test_migration_is_idempotent_via_sentinel(monkeypatch, tmp_path):
    """Run twice → no duplicates (spec P0: 'run twice, no duplicates')."""
    fake_bundle = tmp_path / "bundle"
    monkeypatch.setattr(web, "LV_ROOT", fake_bundle)
    new_log = tmp_path / "state" / "lv_revision_log.ndjson"
    monkeypatch.setenv("LV_REVISION_LOG_PATH", str(new_log))
    _write_ndjson(
        fake_bundle / "dev" / "lv_revision_log.ndjson",
        [_reflection_entry("teacher-reflection-1")],
    )

    assert web._migrate_legacy_revision_log() == 1
    assert web._migrate_legacy_revision_log() == 0
    assert _read_ids(new_log) == ["teacher-reflection-1"]


def test_migration_is_idempotent_without_sentinel(monkeypatch, tmp_path):
    """Crash between append and sentinel-write must not duplicate on retry:
    dedupe by revision_id is the second idempotency layer."""
    fake_bundle = tmp_path / "bundle"
    monkeypatch.setattr(web, "LV_ROOT", fake_bundle)
    new_log = tmp_path / "state" / "lv_revision_log.ndjson"
    monkeypatch.setenv("LV_REVISION_LOG_PATH", str(new_log))
    _write_ndjson(
        fake_bundle / "dev" / "lv_revision_log.ndjson",
        [_reflection_entry("teacher-reflection-1"), _reflection_entry("teacher-reflection-2")],
    )

    assert web._migrate_legacy_revision_log() == 2
    # Simulate the crash: sentinel never landed.
    new_log.with_name(new_log.name + ".migrated").unlink()
    assert web._migrate_legacy_revision_log() == 0
    assert _read_ids(new_log) == ["teacher-reflection-1", "teacher-reflection-2"]


def test_migration_legacy_absent_is_clean(monkeypatch, tmp_path):
    fake_bundle = tmp_path / "bundle"
    fake_bundle.mkdir()
    monkeypatch.setattr(web, "LV_ROOT", fake_bundle)
    new_log = tmp_path / "state" / "lv_revision_log.ndjson"
    monkeypatch.setenv("LV_REVISION_LOG_PATH", str(new_log))

    assert web._migrate_legacy_revision_log() == 0
    assert not new_log.exists()
    assert new_log.with_name(new_log.name + ".migrated").exists()


def test_migration_never_writes_legacy_file(monkeypatch, tmp_path):
    fake_bundle = tmp_path / "bundle"
    monkeypatch.setattr(web, "LV_ROOT", fake_bundle)
    legacy = fake_bundle / "dev" / "lv_revision_log.ndjson"
    new_log = tmp_path / "state" / "lv_revision_log.ndjson"
    monkeypatch.setenv("LV_REVISION_LOG_PATH", str(new_log))
    _write_ndjson(legacy, [_reflection_entry("teacher-reflection-1")])
    before = legacy.read_bytes()

    web._migrate_legacy_revision_log()
    assert legacy.read_bytes() == before


def test_migration_dedupes_within_legacy_file_and_skips_garbage(monkeypatch, tmp_path):
    """Hardening iteration 7: a revision_id duplicated WITHIN the legacy
    file migrated twice (existing_ids was only seeded from the new file).
    Garbage lines (non-JSON, non-dict JSON, blanks) must be skipped."""
    fake_bundle = tmp_path / "bundle"
    monkeypatch.setattr(web, "LV_ROOT", fake_bundle)
    new_log = tmp_path / "state" / "lv_revision_log.ndjson"
    monkeypatch.setenv("LV_REVISION_LOG_PATH", str(new_log))
    legacy = fake_bundle / "dev" / "lv_revision_log.ndjson"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(
        json.dumps(_reflection_entry("teacher-reflection-1")) + "\n"
        + "NOT JSON {{{\n"
        + json.dumps(["a", "list"]) + "\n"
        + "\n"
        + json.dumps(_reflection_entry("teacher-reflection-1")) + "\n"  # intra-file dupe
        + json.dumps(_reflection_entry("teacher-reflection-2")) + "\n",
        encoding="utf-8",
    )

    assert web._migrate_legacy_revision_log() == 2
    assert _read_ids(new_log) == ["teacher-reflection-1", "teacher-reflection-2"]


def test_migration_keeps_distinct_same_second_reflections(monkeypatch, tmp_path):
    """Review finding 2: pre-uuid builds stamped revision_id with
    int(time.time()) — two DISTINCT reflections saved in the same second
    shared an ID and the second was silently dropped by the id-only
    dedupe. The (revision_id, content-hash) key must migrate both, while
    a byte-identical double-submit still dedupes."""
    fake_bundle = tmp_path / "bundle"
    monkeypatch.setattr(web, "LV_ROOT", fake_bundle)
    new_log = tmp_path / "state" / "lv_revision_log.ndjson"
    monkeypatch.setenv("LV_REVISION_LOG_PATH", str(new_log))

    first = _reflection_entry("teacher-reflection-1753600000", "note about reading")
    second = _reflection_entry("teacher-reflection-1753600000", "note about maths")
    _write_ndjson(
        fake_bundle / "dev" / "lv_revision_log.ndjson",
        [first, second, dict(first)],  # third = identical double-submit
    )

    assert web._migrate_legacy_revision_log() == 2
    notes = [
        json.loads(line)["proof"]
        for line in new_log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert notes == ["note about reading", "note about maths"]


def test_new_reflection_ids_are_collision_free(monkeypatch, tmp_path):
    """Review finding 2, write side: revision_id now uses uuid4 — two
    POSTs in the same second must get distinct ids."""
    monkeypatch.delenv("LV_REVISION_LOG_PATH", raising=False)
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path / "home"))
    log = tmp_path / "home" / "dev" / "lv_revision_log.ndjson"

    assert client.post("/api/reflect/note", json={"note": "first"}).status_code == 200
    assert client.post("/api/reflect/note", json={"note": "second"}).status_code == 200
    ids = _read_ids(log)
    assert len(ids) == 2
    assert ids[0] != ids[1]


def test_migration_non_utf8_legacy_retries_without_raising(monkeypatch, tmp_path):
    """Hardening iteration 7: a non-UTF8 legacy file raised
    UnicodeDecodeError past the OSError catch. Must return 0, not raise,
    and leave the sentinel unwritten so the next launch retries."""
    fake_bundle = tmp_path / "bundle"
    monkeypatch.setattr(web, "LV_ROOT", fake_bundle)
    new_log = tmp_path / "state" / "lv_revision_log.ndjson"
    monkeypatch.setenv("LV_REVISION_LOG_PATH", str(new_log))
    legacy = fake_bundle / "dev" / "lv_revision_log.ndjson"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"\xff\xfe garbage \x80\x81\n")

    assert web._migrate_legacy_revision_log() == 0
    assert not new_log.with_name(new_log.name + ".migrated").exists()


def test_startup_runs_migration(monkeypatch, tmp_path):
    """The migration is wired into app startup, not just importable."""
    fake_bundle = tmp_path / "bundle"
    monkeypatch.setattr(web, "LV_ROOT", fake_bundle)
    new_log = tmp_path / "state" / "lv_revision_log.ndjson"
    monkeypatch.setenv("LV_REVISION_LOG_PATH", str(new_log))
    _write_ndjson(
        fake_bundle / "dev" / "lv_revision_log.ndjson",
        [_reflection_entry("teacher-reflection-1")],
    )

    with TestClient(app):
        pass

    assert _read_ids(new_log) == ["teacher-reflection-1"]
