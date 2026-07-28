"""One-button update reconcile engine (SPEC_ONE_BUTTON_UPDATE_2026-07-27).

Covers spec §5 acceptance checks 1, 2, 3 (classification half), 4, 5, 6,
8 plus the research doc's #1-ranked pitfall (YAML reformat must not flip
hashes) and the unknown-file/decoy and symlink rules. The health WARN
half of check 3 lives in test_update_conflict_surface.py.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import pytest
import yaml

from src.lingua_viva import reconcile as rec


SEED_LENS = """name: observation-coach
description: "Forces structured observation."
rationale: >
  Observation capture is only useful if it is specific.
confidence_adjustment: 0.0
schema_version: 1
"""

SEED_MATRIX = """authority: non_authoritative
grades: [G1, G2, G3]
schema_version: 1
"""


@pytest.fixture()
def update_env(monkeypatch, tmp_path):
    """Fake seed tree + isolated update home + pinned engine version."""
    seed = tmp_path / "seed"
    (seed / "lenses" / "education").mkdir(parents=True)
    (seed / "curriculum").mkdir(parents=True)
    (seed / "lenses" / "education" / "observation-coach.yaml").write_text(SEED_LENS, encoding="utf-8")
    (seed / "lenses" / "education" / "README.md").write_text("# Lenses\n", encoding="utf-8")
    (seed / "curriculum" / "lingua_viva_matrix.yaml").write_text(SEED_MATRIX, encoding="utf-8")

    home = tmp_path / "update-home"
    monkeypatch.setenv("LV_SEED_ROOT", str(seed))
    monkeypatch.setenv("LV_UPDATE_HOME", str(home))
    monkeypatch.setenv("LV_ENGINE_VERSION", "1.0.0")
    return {"seed": seed, "home": home, "monkeypatch": monkeypatch}


def _bump_release(env, new_lens_body: str | None = None, version: str = "1.1.0") -> None:
    """Simulate installing a new app version: seed content and/or version."""
    if new_lens_body is not None:
        (env["seed"] / "lenses" / "education" / "observation-coach.yaml").write_text(
            new_lens_body, encoding="utf-8"
        )
    env["monkeypatch"].setenv("LV_ENGINE_VERSION", version)


# -- Hashing: pitfall #1 ---------------------------------------------------

def test_reformat_does_not_change_hash(tmp_path):
    """Key reorder + trailing-newline/quoting changes must hash identically
    — otherwise every pristine file reads as modified and auto-update
    silently dies (research pitfall #1)."""
    a = tmp_path / "a.yaml"
    b = tmp_path / "b.yaml"
    a.write_text("name: x\ndescription: hello\nconfidence_adjustment: 0.0\n", encoding="utf-8")
    b.write_text(
        'confidence_adjustment: 0.0\n"description": "hello"\nname: "x"',
        encoding="utf-8",
    )
    assert rec.canonical_hash(a) == rec.canonical_hash(b)


def test_version_tuple_handles_odd_version_strings():
    """Hardening iteration 11: 'v1.0.7' parsed as (0,0,7) — a v-prefixed
    engine version would trip the downgrade guard and silently disable
    reconcile forever. Odd strings must degrade safely, never raise."""
    vt = rec._version_tuple
    assert vt("v1.0.7") == (1, 0, 7)
    assert vt("1.0.10") > vt("1.0.9")
    assert vt("1.0.6-beta") == (1, 0, 6)
    assert vt("") == (0,)
    assert vt("abc") == (0,)
    assert not vt("1.0.6-beta") > vt("1.0.6")  # no false downgrade


def test_semantic_change_does_change_hash(tmp_path):
    a = tmp_path / "a.yaml"
    b = tmp_path / "b.yaml"
    a.write_text("name: x\n", encoding="utf-8")
    b.write_text("name: y\n", encoding="utf-8")
    assert rec.canonical_hash(a) != rec.canonical_hash(b)


def test_unparseable_yaml_falls_back_to_raw_bytes(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("{: not yaml ::", encoding="utf-8")
    assert rec.canonical_hash(bad)  # raw-bytes fallback, no exception


def test_yaml_alias_bomb_hashes_fast_via_raw_fallback(tmp_path):
    """Hardening iteration 1: a 419-byte billion-laughs alias bomb hung
    safe_load >15s pre-fix — startup reconcile would never finish. The
    no-alias loader must refuse it instantly and fall back to raw bytes
    (safe direction: false 'modified' preserves, never destroys)."""
    import time

    bomb = tmp_path / "bomb.yaml"
    lines = ['a: &a ["x","x","x","x","x","x","x","x","x"]']
    for prev, cur in zip("abcdefgh", "bcdefghi"):
        refs = ",".join(f"*{prev}" for _ in range(9))
        anchor = f"&{cur} " if cur != "i" else ""
        lines.append(f"{cur}: {anchor}[{refs}]")
    bomb.write_text("\n".join(lines) + "\n", encoding="utf-8")
    start = time.monotonic()
    digest = rec.canonical_hash(bomb)
    assert time.monotonic() - start < 2.0
    assert digest == hashlib.sha256(bomb.read_bytes()).hexdigest()  # raw fallback


def test_oversized_yaml_hashes_raw_without_parsing(tmp_path):
    """Files over the parse cap skip YAML entirely — raw-bytes hash."""
    big = tmp_path / "big.yaml"
    big.write_text("k: v\n" + "# pad\n" * 300_000, encoding="utf-8")
    assert big.stat().st_size > rec._MAX_PARSE_BYTES
    assert rec.canonical_hash(big) == hashlib.sha256(big.read_bytes()).hexdigest()


# -- Acceptance 1: fresh install + idempotent second launch ----------------

def test_fresh_install_materializes_and_second_run_noops(update_env):
    report = rec.reconcile()
    assert report["fresh_install"] is True
    assert "lenses/education/observation-coach.yaml" in report["materialized"]
    assert (rec.live_root() / "curriculum" / "lingua_viva_matrix.yaml").is_file()
    manifest = rec.load_manifest()
    assert manifest["last_run_engine_version"] == "1.0.0"
    assert set(manifest["artifacts"]) == {
        "lenses/education/observation-coach.yaml",
        "lenses/education/README.md",
        "curriculum/lingua_viva_matrix.yaml",
    }

    second = rec.reconcile()
    assert second["ran"] is False  # no-op fast path
    assert second["materialized"] == []


def test_noop_path_is_fast(update_env):
    rec.reconcile()
    start = time.perf_counter()
    rec.reconcile()
    elapsed = time.perf_counter() - start
    assert elapsed < 0.1, f"no-op reconcile took {elapsed:.3f}s (budget 100ms)"


# -- Acceptance 2: update with zero user edits ------------------------------

def test_update_zero_edits_upgrades_all_zero_pending(update_env):
    rec.reconcile()
    _bump_release(update_env, SEED_LENS.replace("specific", "specific and actionable"))

    report = rec.reconcile()
    assert report["ran"] is True
    assert "lenses/education/observation-coach.yaml" in report["upgraded"]
    assert report["staged_pending"] == []
    live = (rec.live_root() / "lenses" / "education" / "observation-coach.yaml").read_text(encoding="utf-8")
    assert "specific and actionable" in live
    assert rec.pending_count() == 0


# -- Acceptance 3 (classification half): edit preserved, update parked ------

def test_user_edit_preserved_byte_identical_and_pending_staged(update_env):
    rec.reconcile()
    live_path = rec.live_root() / "lenses" / "education" / "observation-coach.yaml"
    user_body = SEED_LENS + "teacher_note: my own tweak\n"
    live_path.write_text(user_body, encoding="utf-8")

    _bump_release(update_env, SEED_LENS.replace("specific", "razor-specific"))
    report = rec.reconcile()

    assert live_path.read_text(encoding="utf-8") == user_body  # byte-identical
    assert "lenses/education/observation-coach.yaml" in report["staged_pending"]
    staged = rec.pending_root() / "lenses" / "education" / "observation-coach.yaml"
    assert "razor-specific" in staged.read_text(encoding="utf-8")
    assert rec.pending_count() == 1


def test_reformat_only_user_touch_is_not_a_conflict(update_env):
    """A teacher's editor reformatting a pristine file must not park an
    update — canonical hashing classifies it unmodified."""
    rec.reconcile()
    live_path = rec.live_root() / "lenses" / "education" / "observation-coach.yaml"
    data = yaml.safe_load(live_path.read_text(encoding="utf-8"))
    live_path.write_text(yaml.safe_dump(data, sort_keys=True), encoding="utf-8")

    _bump_release(update_env, SEED_LENS.replace("specific", "hyper-specific"))
    report = rec.reconcile()
    assert "lenses/education/observation-coach.yaml" in report["upgraded"]
    assert rec.pending_count() == 0


# -- Acceptance 4: user deletion is not resurrected -------------------------

def test_user_deleted_template_not_resurrected(update_env):
    rec.reconcile()
    live_path = rec.live_root() / "lenses" / "education" / "observation-coach.yaml"
    live_path.unlink()

    _bump_release(update_env, SEED_LENS.replace("specific", "extra-specific"))
    report = rec.reconcile()
    assert not live_path.exists()
    assert "lenses/education/observation-coach.yaml" in report["deleted_not_resurrected"]


# -- Acceptance 5: namespace separation -------------------------------------

def test_new_shipped_artifact_colliding_with_user_file_both_survive(update_env):
    rec.reconcile()
    user_file = rec.live_root() / "lenses" / "education" / "my-lens.yaml"
    user_file.write_text("name: my-lens\nteacher: made this\n", encoding="utf-8")

    # Next release ships a template at the same path.
    (update_env["seed"] / "lenses" / "education" / "my-lens.yaml").write_text(
        "name: my-lens\nshipped: version\n", encoding="utf-8"
    )
    _bump_release(update_env, version="1.1.0")
    rec.reconcile()

    assert user_file.read_text(encoding="utf-8") == "name: my-lens\nteacher: made this\n"
    assert (rec.pending_root() / "lenses" / "education" / "my-lens.yaml").is_file()


def test_reserved_prefix_rejected_at_creation_time():
    ok, _ = rec.validate_user_artifact_id("my-cool-lens")
    assert ok
    for bad in ("lv-anything", "LV-CUR-999", "Lv-x"):
        ok, message = rec.validate_user_artifact_id(bad)
        assert not ok
        assert "reserved" in message


# -- Unknown files: never touched -------------------------------------------

def test_unknown_user_file_in_managed_dir_never_touched(update_env):
    rec.reconcile()
    decoy = rec.live_root() / "lenses" / "education" / "totally-mine.yaml"
    decoy.write_text("mine: true\n", encoding="utf-8")

    _bump_release(update_env, SEED_LENS.replace("specific", "even-more-specific"))
    rec.reconcile()

    assert decoy.read_text(encoding="utf-8") == "mine: true\n"
    manifest = rec.load_manifest()
    assert "lenses/education/totally-mine.yaml" not in manifest["artifacts"]
    assert "lenses/education/totally-mine.yaml" not in manifest["pending"]


# -- Symlinks: classify as modified, never touch -----------------------------

def test_symlink_in_live_layer_never_touched(update_env):
    rec.reconcile()
    live_path = rec.live_root() / "lenses" / "education" / "observation-coach.yaml"
    target = live_path.parent / "elsewhere.yaml"
    live_path.rename(target)
    live_path.symlink_to(target)

    _bump_release(update_env, SEED_LENS.replace("specific", "ultra-specific"))
    report = rec.reconcile()
    assert live_path.is_symlink()
    assert "lenses/education/observation-coach.yaml" in report["preserved_modified"]
    assert rec.pending_count() == 1


# -- Acceptance 6: interrupted reconcile converges ---------------------------

def test_kill_mid_reconcile_rerun_converges(update_env, monkeypatch):
    """Simulated interrupt: the process dies partway through the artifact
    pass, BEFORE the manifest write (which is last). Re-run must converge
    with no half-written artifact — temp+rename makes this provable."""
    real_write = rec._atomic_write_bytes
    calls = {"n": 0}

    def dying_write(target, data):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise KeyboardInterrupt("simulated kill -9")
        real_write(target, data)

    monkeypatch.setattr(rec, "_atomic_write_bytes", dying_write)
    with pytest.raises(KeyboardInterrupt):
        rec.reconcile()

    # Manifest (the commit point) never landed; no temp droppings.
    assert rec.load_manifest() is None
    leftovers = [p for p in rec.live_root().rglob(".*") if p.is_file()]
    assert leftovers == []

    monkeypatch.setattr(rec, "_atomic_write_bytes", real_write)
    report = rec.reconcile()
    assert report["fresh_install"] is True
    manifest = rec.load_manifest()
    assert len(manifest["artifacts"]) == 3
    for rel in manifest["artifacts"]:
        assert (rec.live_root() / rel).is_file()


def test_manifest_loss_preserves_edits_and_readopts_pristine(update_env):
    """Hardening iteration 13 (pin, no defect found): if the manifest is
    lost (deleted / partial restore), the rerun is a fresh-install pass —
    teacher-edited files must be preserved + parked, pristine files
    silently re-adopted."""
    rec.reconcile()
    edited = rec.live_root() / "lenses" / "education" / "observation-coach.yaml"
    edited.write_text(SEED_LENS + "teacher_note: mine\n", encoding="utf-8")
    rec.manifest_path().unlink()

    report = rec.reconcile()
    assert report["fresh_install"] is True
    assert "teacher_note: mine" in edited.read_text(encoding="utf-8")
    assert "lenses/education/observation-coach.yaml" in report["preserved_modified"]
    assert [i["path"] for i in rec.list_pending()] == ["lenses/education/observation-coach.yaml"]


def test_one_bad_artifact_never_blocks_the_rest(update_env, monkeypatch):
    """Hardening iteration 2: pre-fix, the per-artifact catch was
    OSError-only — a ValueError from one artifact aborted the whole pass
    (zero files materialized on fresh install, no manifest). Any Exception
    in one artifact must be recorded and the rest must land."""
    real_hash = rec.canonical_hash

    def poisoned(path):
        if path.name == "observation-coach.yaml":
            raise ValueError("boom")
        return real_hash(path)

    monkeypatch.setattr(rec, "canonical_hash", poisoned)
    report = rec.reconcile()

    assert report["ran"] is True
    assert any(e["path"].endswith("observation-coach.yaml") for e in report["errors"])
    manifest = rec.load_manifest()
    assert manifest is not None  # commit point still reached
    assert len(manifest["artifacts"]) == 2  # the other two landed
    for rel in manifest["artifacts"]:
        assert (rec.live_root() / rel).is_file()


# -- Acceptance 8: downgrade guard ------------------------------------------

def test_downgrade_is_read_only(update_env):
    rec.reconcile()
    manifest_before = (rec.manifest_path()).read_bytes()

    update_env["monkeypatch"].setenv("LV_ENGINE_VERSION", "0.9.0")
    _bump_release(update_env, SEED_LENS.replace("specific", "older-specific"), version="0.9.0")
    report = rec.reconcile()

    assert report["downgrade"] is True
    assert report["ran"] is False
    assert rec.manifest_path().read_bytes() == manifest_before  # no manifest write
    live_path = rec.live_root() / "lenses" / "education" / "observation-coach.yaml"
    assert "older-specific" not in live_path.read_text(encoding="utf-8")  # no artifact writes
    assert rec.downgrade_detected() == {
        "last_run_engine_version": "1.0.0",
        "engine_version": "0.9.0",
    }


# -- Conflict resolution API -------------------------------------------------

def _park_one(update_env) -> str:
    rec.reconcile()
    live_path = rec.live_root() / "lenses" / "education" / "observation-coach.yaml"
    live_path.write_text(SEED_LENS + "teacher_note: mine\n", encoding="utf-8")
    _bump_release(update_env, SEED_LENS.replace("specific", "new-ship-specific"))
    rec.reconcile()
    return "lenses/education/observation-coach.yaml"


def test_resolve_keep_mine_stops_asking_for_this_ship(update_env):
    rel = _park_one(update_env)
    result = rec.resolve_pending(rel, "keep_mine")
    assert result["status"] == "resolved"
    assert rec.pending_count() == 0
    live_path = rec.live_root() / rel
    assert "teacher_note: mine" in live_path.read_text(encoding="utf-8")
    # Same release reconciled again → does not re-park the same version.
    rec.reconcile(force=True)
    assert rec.pending_count() == 0


def test_resolve_take_new_archives_before_replacing(update_env):
    rel = _park_one(update_env)
    result = rec.resolve_pending(rel, "take_new")
    assert result["status"] == "resolved"
    assert result["archived_to"], "teacher's copy must be archived, never destroyed"
    archived = Path(result["archived_to"])
    assert archived.is_file()
    assert "teacher_note: mine" in archived.read_text(encoding="utf-8")
    live_path = rec.live_root() / rel
    assert "new-ship-specific" in live_path.read_text(encoding="utf-8")
    assert rec.pending_count() == 0


def test_pending_diff_shows_both_sides(update_env):
    rel = _park_one(update_env)
    diff = rec.pending_diff(rel)
    assert diff
    assert "teacher_note: mine" in diff
    assert "new-ship-specific" in diff


def test_pending_diff_is_capped_for_huge_files(update_env):
    """Hardening iteration 10: a huge live file produced a 41MB diff
    string straight into the browser DOM. The surface caps its response;
    the files themselves are untouched."""
    rel = _park_one(update_env)
    live_path = rec.live_root() / rel
    live_path.write_text(
        "".join(f"line-{i}: value\n" for i in range(50_000)), encoding="utf-8"
    )
    diff = rec.pending_diff(rel)
    assert diff
    assert len(diff) < 250_000
    assert "diff truncated" in diff


def test_resolve_rejects_unknown_action_and_path(update_env):
    rel = _park_one(update_env)
    assert rec.resolve_pending(rel, "merge")["status"] == "error"
    assert rec.resolve_pending("lenses/education/nope.yaml", "take_new")["status"] == "error"


def test_poisoned_manifest_rel_cannot_escape_managed_roots(update_env):
    """Hardening iteration 3: the manifest lives in teacher-writable space.
    Pre-fix, a hand-poisoned '../evil' pending rel let take_new write one
    level above live_root(). Every manifest-consuming surface must refuse
    unsafe rels: traversal, absolute, backslash, unmanaged prefix."""
    rec.reconcile()
    manifest = rec.load_manifest()
    evil_rels = [
        "../OUTSIDE.txt",
        "curriculum/../../OUTSIDE.txt",
        "/etc/passwd",
        "curriculum\\evil.yaml",
        "src/web.py",  # unmanaged prefix
    ]
    for rel in evil_rels:
        manifest["pending"][rel] = {"new_hash": "x", "shipped_in": "9.9.9", "staged_path": "x"}
    rec._write_manifest(manifest)

    assert rec.list_pending() == []  # unsafe rels never surface to the UI
    for rel in evil_rels:
        assert rec.pending_diff(rel) is None
        result = rec.resolve_pending(rel, "take_new")
        assert result["status"] == "error", rel
    escaped = rec.update_home() / "OUTSIDE.txt"
    assert not escaped.exists()


def test_corrupt_manifest_shapes_degrade_to_nothing_pending(update_env):
    """Hardening iteration 4: non-dict pending entries raised
    AttributeError (route 500, Settings panel dead) and a string-valued
    pending map made pending_count() return its string length (Doctor
    warned '7 updates waiting' on the corrupt word). All conflict-surface
    reads must degrade to 'nothing pending'."""
    rec.reconcile()
    manifest = rec.load_manifest()
    manifest["pending"]["curriculum/x.yaml"] = "oops-not-a-dict"
    manifest["pending"]["curriculum/y.yaml"] = 42
    rec._write_manifest(manifest)

    assert rec.list_pending() == []
    assert rec.pending_count() == 0
    assert rec.pending_diff("curriculum/x.yaml") is None
    assert rec.resolve_pending("curriculum/x.yaml", "keep_mine")["status"] == "error"

    manifest["pending"] = "corrupt"
    rec._write_manifest(manifest)
    assert rec.list_pending() == []
    assert rec.pending_count() == 0
    assert rec.resolve_pending("curriculum/x.yaml", "take_new")["status"] == "error"


def test_take_new_refuses_to_replace_a_symlink(update_env, tmp_path):
    """Hardening iteration 5: reconcile never touches symlinks, but
    take_new silently replaced one with a regular file — destroying the
    teacher's link structure. It must refuse; keep_mine still works."""
    rec.reconcile()
    rel = "lenses/education/observation-coach.yaml"
    live_path = rec.live_root() / rel
    external = tmp_path / "external.yaml"
    external.write_text("teacher: linked\n", encoding="utf-8")
    live_path.unlink()
    live_path.symlink_to(external)

    _bump_release(update_env, SEED_LENS.replace("specific", "more-specific"), version="1.1.0")
    rec.reconcile()
    assert any(item["path"] == rel for item in rec.list_pending())

    result = rec.resolve_pending(rel, "take_new")
    assert result["status"] == "error"
    assert "link" in result["error"]
    assert live_path.is_symlink()  # untouched
    assert external.read_text(encoding="utf-8") == "teacher: linked\n"

    assert rec.resolve_pending(rel, "keep_mine")["status"] == "resolved"
    assert live_path.is_symlink()


def test_take_new_file_errors_return_error_dict_and_keep_pending(update_env):
    """Hardening iteration 6: an unreadable staged file raised
    PermissionError through the route (500). Must return an error dict,
    keep the pending entry, and leave the teacher's live copy untouched."""
    rel = _park_one(update_env)
    staged = rec.pending_root() / rel
    live_path = rec.live_root() / rel
    live_before = live_path.read_bytes()
    os.chmod(staged, 0o000)
    try:
        result = rec.resolve_pending(rel, "take_new")
    finally:
        os.chmod(staged, 0o644)
    assert result["status"] == "error"
    assert rec.pending_count() == 1  # still pending — retry possible
    assert live_path.read_bytes() == live_before

    # After permissions recover, the same resolve succeeds.
    assert rec.resolve_pending(rel, "take_new")["status"] == "resolved"


# -- Managed set boundaries ---------------------------------------------------

def test_engine_owned_dirs_are_not_managed(update_env):
    seed = update_env["seed"]
    (seed / "ontology").mkdir()
    (seed / "ontology" / "schema.yaml").write_text("engine: owned\n", encoding="utf-8")
    rels = rec.managed_artifacts()
    assert all(r.startswith(("lenses/education/", "curriculum/")) for r in rels)
    rec.reconcile()
    assert not (rec.live_root() / "ontology").exists()


def test_manifest_records_tombstone_and_rename_mechanisms(update_env):
    rec.reconcile()
    manifest = rec.load_manifest()
    assert manifest["tombstones"] == []
    assert manifest["renamed_from"] == {}


# -- Startup wiring -----------------------------------------------------------

def test_backend_startup_runs_reconcile(update_env):
    """The reconcile runs on app startup — identically for desktop,
    `lv serve`, and source installs (all boot this FastAPI app)."""
    from fastapi.testclient import TestClient

    from src.web import app

    assert rec.load_manifest() is None
    with TestClient(app):
        pass
    manifest = rec.load_manifest()
    assert manifest is not None
    assert manifest["last_run_engine_version"] == "1.0.0"
    assert (rec.live_root() / "lenses" / "education" / "observation-coach.yaml").is_file()

# -- Phase 4: schema versioning + creation-time namespace gate ---------------

def test_all_shipped_artifacts_carry_schema_version():
    """Every real shipped YAML template in the repo's managed set must
    declare schema_version (Phase 4: shipped seeds migrate at build time)."""
    repo = Path(__file__).resolve().parents[1]
    rels = rec.managed_artifacts(repo)
    yaml_rels = [r for r in rels if r.endswith((".yaml", ".yml"))]
    assert yaml_rels, "managed set unexpectedly empty"
    for rel in yaml_rels:
        data = yaml.safe_load((repo / rel).read_text(encoding="utf-8"))
        assert isinstance(data, dict) and data.get("schema_version") == 1, rel


def test_schema_migration_runs_on_user_copy(update_env, monkeypatch):
    """A registered 1→2 hook migrates a user-MODIFIED live copy in place
    while the byte-level conflict still parks the new ship as pending."""
    rec.reconcile()
    live_path = rec.live_root() / "lenses" / "education" / "observation-coach.yaml"
    live_path.write_text(SEED_LENS + "teacher_note: mine\n", encoding="utf-8")

    def to_v2(data: dict) -> dict:
        data["migrated_marker"] = True
        return data

    monkeypatch.setitem(rec.SCHEMA_MIGRATIONS, 1, to_v2)
    _bump_release(
        update_env,
        SEED_LENS.replace("schema_version: 1", "schema_version: 2") + "new_field: shipped\n",
    )
    rec.reconcile()

    migrated = yaml.safe_load(live_path.read_text(encoding="utf-8"))
    assert migrated["schema_version"] == 2
    assert migrated["migrated_marker"] is True
    assert migrated["teacher_note"] == "mine"          # user data survives
    assert "new_field" not in migrated                  # ship content stays parked
    assert [p["path"] for p in rec.list_pending()] == [
        "lenses/education/observation-coach.yaml"
    ]


def test_create_lens_rejects_reserved_prefix(tmp_path):
    from src.education.student_lens import ObservationValidationError, StudentLensStore

    store = StudentLensStore(db_path=tmp_path / "gate.db")
    with pytest.raises(ObservationValidationError, match="reserved"):
        store.create_lens(student_id="lv-shipped-thing", display_name="X")
    with pytest.raises(ObservationValidationError, match="reserved"):
        store.create_lens(student_id="LV-CUR-999", display_name="X")  # casefold
    ok_id = store.create_lens(student_id="student-marco", display_name="Marco")
    assert ok_id == "student-marco"
    auto_id = store.create_lens(display_name="Auto")  # generated IDs unaffected
    assert auto_id and not auto_id.startswith("lv-")
