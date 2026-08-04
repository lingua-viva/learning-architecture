from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import src.web as web
from src.lingua_viva.exit_gates import (
    STUDENT_DATA_EXTERNAL_BLOCKED,
    UNSAFE_PATH_BLOCKED,
    ExitGate,
    ExitRequest,
)
from src.lingua_viva.reasoning import ReasoningEngine
from src.web import app

# Demo-roster seeding was removed from web.py (T9 / acceptance A6) —
# these tests exercise flows that need students on the roster, so they
# opt in to the explicit demo_roster fixture from conftest.py.
pytestmark = pytest.mark.usefixtures("demo_roster")



@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_exit_gate_allows_local_destination_with_student_text():
    decision = ExitGate().check(
        ExitRequest(
            surface="reasoning",
            destination="local",
            payload_text="student name: Marco needs help with liaison sounds",
        )
    )

    assert decision.allowed is True
    assert decision.external is False


def test_exit_gate_blocks_external_reasoning_for_known_student_name():
    decision = ExitGate().check(
        ExitRequest(
            surface="reasoning",
            destination="openai",
            payload_text="Please summarize Marco's parent report.",
            student_names=("Marco",),
        )
    )

    assert decision.allowed is False
    assert decision.blocked_reason == STUDENT_DATA_EXTERNAL_BLOCKED


def test_exit_gate_blocks_external_reasoning_when_local_only():
    decision = ExitGate().check(
        ExitRequest(
            surface="reasoning",
            destination="groq",
            payload_text="Safe curriculum question",
            metadata={"local_only": True},
        )
    )

    assert decision.allowed is False
    assert decision.blocked_reason == STUDENT_DATA_EXTERNAL_BLOCKED


def test_exit_gate_allows_safe_curriculum_text_to_external_reasoning():
    decision = ExitGate().check(
        ExitRequest(
            surface="reasoning",
            destination="mistral",
            payload_text="Explain a lesson sequence for passato prossimo.",
        )
    )

    assert decision.allowed is True


@pytest.mark.asyncio
async def test_reasoning_engine_does_not_urlopen_for_blocked_external_student_prompt(monkeypatch):
    called = False

    def fail_urlopen(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("urlopen should not be called after exit gate block")

    monkeypatch.setattr("src.lingua_viva.reasoning.request.urlopen", fail_urlopen)

    result = await ReasoningEngine().reason(
        "student name: Marco needs a parent report",
        model="openai/gpt-4o-mini",
        system_prompt="Write the parent report.",
    )

    assert called is False
    assert result.model_used == "none"


@pytest.mark.asyncio
async def test_reasoning_engine_blocks_known_student_name_without_label(monkeypatch):
    called = False

    def fail_urlopen(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("urlopen should not be called for a known student name")

    monkeypatch.setattr("src.lingua_viva.reasoning.request.urlopen", fail_urlopen)
    monkeypatch.setattr(ReasoningEngine, "_known_student_names", staticmethod(lambda: ["Marco"]))

    result = await ReasoningEngine().reason(
        "Marco needs help with liaison sounds",
        model="openai/gpt-4o-mini",
        system_prompt="Give the teacher advice.",
    )

    assert called is False
    assert result.model_used == "none"


@pytest.mark.asyncio
async def test_reasoning_engine_preserves_local_only_refusal_when_no_local_fallback(monkeypatch):
    monkeypatch.setattr(ReasoningEngine, "_resolve_best_model", lambda self: "kimi-k2.7-code:cloud")

    result = await ReasoningEngine().reason(
        "student name: Marco needs a parent report",
        model="openai/gpt-4o-mini",
        system_prompt="Write the parent report.",
        local_only=True,
    )

    assert "can only be answered by a model running on this computer" in result.content
    assert result.model_used == "none:local_only"


def test_tts_blocks_student_name_before_rime_key_or_network(client, monkeypatch):
    key_read = False

    def fail_key():
        nonlocal key_read
        key_read = True
        raise AssertionError("Rime key should not be read after exit gate block")

    monkeypatch.setattr(web, "_rime_api_key", fail_key)
    monkeypatch.setenv("RIME_API_KEY", "rime-test-key")
    client.get("/api/students")

    response = client.post("/api/voice/tts", json={"text": "Marco is ready."})

    assert response.status_code == 403
    assert response.json()["fallback"] == "local"
    assert key_read is False


def test_tts_allows_safe_text_to_mocked_rime_and_logs_events(client, monkeypatch):
    from src.lingua_viva.privacy_log import read_privacy_events

    captured: dict[str, str] = {}
    monkeypatch.setenv("RIME_API_KEY", "rime-test-key")

    def fake_audio(text, speaker, model_id, key):
        captured.update(text=text, speaker=speaker, model_id=model_id, key=key)
        return b"RIFF....WAVEfmt "

    monkeypatch.setattr(web, "_request_rime_audio", fake_audio)

    response = client.post("/api/voice/tts", json={"text": "Buongiorno a tutti"})

    assert response.status_code == 200
    assert captured["key"] == "rime-test-key"
    kinds = {event.event_type for event in read_privacy_events(limit=200)}
    assert "exit_gate_allowed" in kinds
    assert "voice_sent_to_external_tts" in kinds


def test_drive_upload_rejects_unsafe_paths_before_upload_helper(client, monkeypatch, tmp_path):
    from src.lingua_viva import google_drive_integration as drive

    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("LV_GOOGLE_DRIVE_EXPORT_DIR", str(tmp_path / "exports"))

    def fail_upload(*_args, **_kwargs):
        raise AssertionError("upload_paths should not run for unsafe paths")

    monkeypatch.setattr(drive, "upload_paths", fail_upload)

    response = client.post("/api/google-drive/upload", json={"file_paths": [str(outside)]})

    assert response.status_code == 200
    body = response.json()
    assert body["uploaded"] == []
    assert body["failed"][0]["status"] == "outside_shareable_area"
    assert "path_hash" in body["failed"][0]
    assert "local_path" not in body["failed"][0]
    assert str(outside) not in response.text
    assert body["exit_gate"]["blocked_reason"] == UNSAFE_PATH_BLOCKED


def test_drive_upload_success_still_returns_deliverable_and_audit_receipt(client, monkeypatch, tmp_path):
    from src.lingua_viva import google_drive_integration as drive

    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "state"))
    export_root = tmp_path / "exports"
    export_root.mkdir()
    safe_file = export_root / "teacher-summary.json"
    safe_file.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("LV_GOOGLE_DRIVE_EXPORT_DIR", str(export_root))

    def fake_upload_paths(file_paths, folder_id=""):
        return {
            "uploaded": [{
                "local_path": str(Path(file_paths[0])),
                "name": "teacher-summary.json",
                "drive_id": "drive-file-1",
                "folder_id": folder_id or "root-folder",
                "status": "uploaded",
            }],
            "failed": [],
        }

    monkeypatch.setattr(drive, "upload_paths", fake_upload_paths)

    response = client.post("/api/google-drive/upload", json={"file_paths": [str(safe_file)]})

    assert response.status_code == 200
    body = response.json()
    assert body["deliverable"]["type"] == "drive_export"
    assert body["audit_receipt"]["deliverable_ids"]


def test_governance_observation_export_refuses_unsafe_publication_pack(client, monkeypatch):
    unsafe_pack = {
        "pack_type": "observation_export",
        "student": {"reference": "S-123", "note": "Marco is named here."},
        "seal": {"signature": "not-used"},
    }

    monkeypatch.setattr(
        web,
        "_with_student_store",
        lambda callback: callback(type("Store", (), {"list_lenses": lambda self: [{"display_name": "Marco"}]})()),
    )
    monkeypatch.setattr(
        "src.lingua_viva.governance.build_observation_pack",
        lambda student_id, *, store: unsafe_pack,
    )

    response = client.post("/api/governance/observation-export", json={"student_id": "student-marco"})

    assert response.status_code == 422
    assert response.json()["publication_safety"]["blocked"] is True


def test_exit_gate_block_log_is_structural_without_raw_student_text(monkeypatch, tmp_path):
    from src.lingua_viva.exit_gates import check_exit
    from src.lingua_viva.privacy_log import privacy_log_path, read_privacy_events

    monkeypatch.setenv("LV_PRIVACY_LOG_PATH", str(tmp_path / "privacy.ndjson"))

    check_exit(
        ExitRequest(
            surface="reasoning",
            destination="openai",
            payload_text="student name: Marco needs a parent report",
        )
    )

    events = read_privacy_events(limit=20)
    assert events[0].event_type == "exit_gate_blocked"
    raw = privacy_log_path().read_text(encoding="utf-8")
    assert "Marco" not in raw
    assert "parent report" not in raw
