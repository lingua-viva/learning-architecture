"""Plan #6 — the SIR deployment profile: hide Home / Daily / Plan / Slack, boot to Students.

Olga's ruling (C4/SIR, 29 August walkthrough): the four surfaces confused her
teachers. A profile flag in the Tier-2 school profile — code kept, nothing
deleted — and both profiles must boot.

  deployment_profile: "la_scuola" (default, everything as today) | "sir"
  LV_DEPLOYMENT_PROFILE env wins over the file when it names a known profile
  (so an install can be cut for a school without touching config).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "students.db"))
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path / "config-home"))
    monkeypatch.delenv("LV_AUTH_MODE", raising=False)
    monkeypatch.delenv("LV_DEPLOYMENT_PROFILE", raising=False)
    from src.web import app

    return TestClient(app)


def test_default_profile_is_la_scuola_and_everything_stays(client):
    body = client.get("/api/school-profile").json()
    assert body["deployment_profile"] == "la_scuola"


def test_sir_profile_can_be_set_read_back_and_booted(client):
    r = client.post("/api/school-profile", json={"deployment_profile": "sir"})
    assert r.status_code == 200, r.text
    assert client.get("/api/school-profile").json()["deployment_profile"] == "sir"
    # both profiles boot: the shell is served and the backend is healthy under each
    assert client.get("/").status_code == 200
    assert client.get("/api/health").status_code == 200
    r = client.post("/api/school-profile", json={"deployment_profile": "la_scuola"})
    assert r.status_code == 200, r.text
    assert client.get("/").status_code == 200
    assert client.get("/api/school-profile").json()["deployment_profile"] == "la_scuola"


def test_unknown_profile_is_a_named_400_and_changes_nothing(client):
    r = client.post("/api/school-profile", json={"deployment_profile": "hogwarts"})
    assert r.status_code == 400 and "hogwarts" in r.json()["error"] and "sir" in r.json()["error"], r.text
    assert client.get("/api/school-profile").json()["deployment_profile"] == "la_scuola"


def test_env_override_names_the_profile_for_an_install(client, monkeypatch):
    monkeypatch.setenv("LV_DEPLOYMENT_PROFILE", "sir")
    assert client.get("/api/school-profile").json()["deployment_profile"] == "sir"
    monkeypatch.setenv("LV_DEPLOYMENT_PROFILE", "nonsense")
    assert client.get("/api/school-profile").json()["deployment_profile"] == "la_scuola", "an unknown env value must not break the boot"


def test_a_malformed_profile_file_still_boots_with_the_default(client, tmp_path):
    from src.lingua_viva.config import school_profile_path

    path = school_profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    assert client.get("/api/school-profile").json()["deployment_profile"] == "la_scuola"
    assert client.get("/").status_code == 200


def test_ui_hides_the_four_surfaces_and_boots_to_students_under_sir():
    html = (REPO / "static" / "index.html").read_text(encoding="utf-8")
    assert "deployment_profile" in html, "the UI never reads the profile"
    fn_start = html.index("function deploymentProfile()")
    block = html[fn_start: fn_start + 2500]
    for view in ("home", "daily", "plan"):
        assert f'"{view}"' in block, f"{view} is not in the SIR hidden set"
    assert '"slack"' in block, "Slack is not in the SIR hidden set"
    assert '"students"' in block, "SIR does not boot to Students"
    # the code is kept, the nav is filtered — Home still exists for La Scuola
    assert '["home", "Home", "🏠"]' in html
    # the shell is rendered only after the profile is known, or the first paint would be wrong
    boot = html[html.index("async function bootShell()"): html.index("async function bootShell()") + 800]
    assert "await ensureSchoolProfile()" in boot
