"""Conflict surface for parked template updates (SPEC_ONE_BUTTON_UPDATE
2026-07-27 Phase 3).

Covers the health-WARN half of spec §5 acceptance check 3 (the reconcile
half lives in test_reconcile.py) plus the three teacher-facing routes:
GET /api/updates/pending, GET /api/updates/diff, POST /api/updates/resolve.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.lingua_viva import reconcile as rec
from src.web import app


SEED_LENS = """name: observation-coach
description: "Forces structured observation."
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
    (seed / "curriculum" / "lingua_viva_matrix.yaml").write_text(SEED_MATRIX, encoding="utf-8")

    home = tmp_path / "update-home"
    monkeypatch.setenv("LV_SEED_ROOT", str(seed))
    monkeypatch.setenv("LV_UPDATE_HOME", str(home))
    monkeypatch.setenv("LV_ENGINE_VERSION", "1.0.0")
    return {"seed": seed, "home": home, "monkeypatch": monkeypatch}


def _park_one(update_env) -> str:
    """First run, teacher edit, shipped change → one parked update."""
    rec.reconcile()
    live_path = rec.live_root() / "lenses" / "education" / "observation-coach.yaml"
    live_path.write_text(SEED_LENS + "teacher_note: mine\n", encoding="utf-8")
    update_env["seed"].joinpath("lenses", "education", "observation-coach.yaml").write_text(
        SEED_LENS.replace("structured", "richly structured"), encoding="utf-8"
    )
    update_env["monkeypatch"].setenv("LV_ENGINE_VERSION", "1.1.0")
    rec.reconcile()
    return "lenses/education/observation-coach.yaml"


# -- Doctor health surface (spec §5 check 3, WARN half) ----------------------

def test_doctor_warns_on_pending_never_fails(update_env):
    from doctor.support_loop.doctor import check_updates_pending

    rel = _park_one(update_env)
    result = check_updates_pending()
    assert result.status == "warn"  # WARN, never FAIL — preserved work is by design
    assert "preserved" in result.message
    assert "1 template update waiting" in result.message
    assert rel in (result.detail or "")


def test_doctor_passes_with_no_pending(update_env):
    from doctor.support_loop.doctor import check_updates_pending

    rec.reconcile()
    result = check_updates_pending()
    assert result.status == "pass"


def test_doctor_warns_on_downgrade(update_env):
    from doctor.support_loop.doctor import check_update_downgrade

    rec.reconcile()
    update_env["monkeypatch"].setenv("LV_ENGINE_VERSION", "0.9.0")
    result = check_update_downgrade()
    assert result.status == "warn"
    assert "older" in result.message
    assert "1.0.0" in (result.detail or "")


def test_doctor_downgrade_passes_normally(update_env):
    from doctor.support_loop.doctor import check_update_downgrade

    rec.reconcile()
    result = check_update_downgrade()
    assert result.status == "pass"


def test_doctor_checks_registered_in_run_doctor():
    """The checks must actually be wired into the doctor run list —
    a check that exists but never runs is the pacdiff failure mode."""
    import inspect

    from doctor.support_loop import doctor as doc

    source = inspect.getsource(doc.run_doctor)
    assert "check_updates_pending" in source
    assert "check_update_downgrade" in source


# -- Routes ------------------------------------------------------------------

def test_updates_pending_route(update_env):
    rel = _park_one(update_env)
    with TestClient(app) as client:
        res = client.get("/api/updates/pending")
    assert res.status_code == 200
    body = res.json()
    paths = [item["path"] for item in body["pending"]]
    assert rel in paths
    assert body["downgrade"] is None or body["downgrade"] == {}


def test_updates_pending_route_empty(update_env):
    rec.reconcile()
    with TestClient(app) as client:
        res = client.get("/api/updates/pending")
    assert res.status_code == 200
    assert res.json()["pending"] == []


def test_updates_diff_route(update_env):
    rel = _park_one(update_env)
    with TestClient(app) as client:
        res = client.get("/api/updates/diff", params={"path": rel})
        missing = client.get("/api/updates/diff", params={"path": "lenses/education/nope.yaml"})
    assert res.status_code == 200
    diff = res.json()["diff"]
    assert "richly structured" in diff
    assert "teacher_note" in diff
    assert missing.status_code == 404


def test_updates_resolve_keep_mine_route(update_env):
    rel = _park_one(update_env)
    live_path = rec.live_root() / "lenses" / "education" / "observation-coach.yaml"
    before = live_path.read_bytes()
    with TestClient(app) as client:
        res = client.post("/api/updates/resolve", json={"path": rel, "action": "keep_mine"})
    assert res.status_code == 200
    assert res.json()["status"] == "resolved"
    assert live_path.read_bytes() == before  # teacher file untouched
    assert rec.list_pending() == []  # stops asking


def test_updates_resolve_take_new_archives_first(update_env):
    rel = _park_one(update_env)
    live_path = rec.live_root() / "lenses" / "education" / "observation-coach.yaml"
    teacher_bytes = live_path.read_bytes()
    with TestClient(app) as client:
        res = client.post("/api/updates/resolve", json={"path": rel, "action": "take_new"})
    assert res.status_code == 200
    assert "richly structured" in live_path.read_text(encoding="utf-8")
    archived = list(rec.archive_root().rglob("observation-coach.yaml.*"))
    assert len(archived) == 1
    assert archived[0].read_bytes() == teacher_bytes  # nothing destroyed


def test_updates_resolve_rejects_bad_input(update_env):
    rel = _park_one(update_env)
    with TestClient(app) as client:
        no_path = client.post("/api/updates/resolve", json={"action": "keep_mine"})
        bad_action = client.post("/api/updates/resolve", json={"path": rel, "action": "delete_it"})
        not_pending = client.post(
            "/api/updates/resolve",
            json={"path": "curriculum/lingua_viva_matrix.yaml", "action": "keep_mine"},
        )
    assert no_path.status_code == 400
    assert bad_action.status_code == 400
    assert not_pending.status_code == 400
