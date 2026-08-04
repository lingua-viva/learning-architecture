"""T6 — Drive write-back sync queue (SPEC_T6_SYNC_2026-08-04)."""
from __future__ import annotations

import json
from pathlib import Path

from src.lingua_viva.docpipe import sync, vault
from src.lingua_viva.docpipe.contracts import LensRecord


def _grounded_lens(student_id: str = "student-nora-rossi", display_name: str = "Nora Rossi") -> dict:
    profile = {
        field_id: {"value": None, "evidence": []}
        for field_id in sync.PROFILE_LABELS
    }
    profile["academic_strengths"] = {
        "value": "Can extend the task by adding a second quotation.",
        "evidence": [{
            "source_ref": {"type": "DOCUMENT", "source_id": "SRC-1", "path": "extracted/SRC-1.json"},
            "span_id": "SPN-0006",
            "confidence": 0.9,
            "added_at": "2026-08-04T08:00:00Z",
            "added_by": "teacher:test",
        }],
    }
    return {
        "schema_version": "docpipe.lens.v1",
        "student_id": student_id,
        "display_name": display_name,
        "created_at": "2026-08-04T08:00:00Z",
        "updated_at": "2026-08-04T08:00:00Z",
        "profile": profile,
        "metadata": {"source_ids": ["SRC-1"], "observation_ids": [], "merge_events": []},
    }


def _seed_lens(root: Path) -> None:
    vault.put_lens(LensRecord(_grounded_lens()), root=root)


def test_enqueue_writes_persistent_queue(tmp_path):
    _seed_lens(tmp_path)
    entry = sync.enqueue_lens("student-nora-rossi", root=tmp_path)
    assert entry["status"] == "pending"
    raw = json.loads((tmp_path / "sync" / "queue.json").read_text(encoding="utf-8"))
    assert len(raw) == 1 and raw[0]["student_id"] == "student-nora-rossi"
    (tmp_path / "manifest.json").unlink()  # force a rebuild — manifest() serves the cached copy
    assert vault.manifest(root=tmp_path).data["sync"]["pending_count"] == 1


def test_enqueue_same_student_dedupes(tmp_path):
    _seed_lens(tmp_path)
    sync.enqueue_lens("student-nora-rossi", root=tmp_path)
    sync.enqueue_lens("student-nora-rossi", root=tmp_path)
    raw = json.loads((tmp_path / "sync" / "queue.json").read_text(encoding="utf-8"))
    assert len(raw) == 1


def test_drain_pushes_rendered_markdown(tmp_path):
    _seed_lens(tmp_path)
    sync.enqueue_lens("student-nora-rossi", root=tmp_path)
    pushed: list[tuple] = []

    def fake_push(local_path, destination_ref, *, mime=None):
        pushed.append((Path(local_path), destination_ref, mime))

    result = sync.drain(root=tmp_path, push=fake_push)
    assert result["pushed"] == 1 and result["pending"] == 0
    local_path, destination, mime = pushed[0]
    rendered = local_path.read_text(encoding="utf-8")
    assert "Nora Rossi" in rendered
    assert "Academic Strengths" in rendered
    assert "evidence: document SRC-1 span SPN-0006" in rendered
    assert "No evidence yet" in rendered  # empty categories listed honestly
    assert destination == "lens-exports" and mime == "text/markdown"
    assert sync.sync_status("student-nora-rossi", root=tmp_path)["status"] == "synced"


def test_failed_push_records_error_and_backs_off(tmp_path):
    _seed_lens(tmp_path)
    sync.enqueue_lens("student-nora-rossi", root=tmp_path)

    def failing_push(local_path, destination_ref, *, mime=None):
        raise OSError("drive unreachable")

    first = sync.drain(root=tmp_path, push=failing_push)
    assert first["failed_this_pass"] == 1 and first["pending"] == 1
    status = sync.sync_status("student-nora-rossi", root=tmp_path)
    assert status["status"] == "pending" and "unreachable" in status["last_error"]

    # Immediate second drain skips (backoff window not elapsed).
    calls: list[int] = []

    def counting_push(local_path, destination_ref, *, mime=None):
        calls.append(1)

    sync.drain(root=tmp_path, push=counting_push)
    assert calls == []
    # Time-travel past the backoff → retried and pushed.
    import time as time_module

    future = time_module.time() + 10 * 60
    result = sync.drain(root=tmp_path, now=future, push=counting_push)
    assert calls == [1] and result["pushed"] == 1


def test_restart_mid_queue_drains_once(tmp_path):
    _seed_lens(tmp_path)
    sync.enqueue_lens("student-nora-rossi", root=tmp_path)
    # "Restart": nothing in memory — a fresh drain reads the persisted queue.
    pushed: list[int] = []

    def fake_push(local_path, destination_ref, *, mime=None):
        pushed.append(1)

    sync.drain(root=tmp_path, push=fake_push)
    sync.drain(root=tmp_path, push=fake_push)  # already pushed → no duplicate
    assert pushed == [1]


def test_push_seam_unimplemented_holds_queue_honestly(tmp_path):
    """Current reality: drive.push_file is the frozen T1/T6 seam stub."""
    _seed_lens(tmp_path)
    sync.enqueue_lens("student-nora-rossi", root=tmp_path)
    result = sync.drain(root=tmp_path)  # default push = drive.push_file stub
    assert result["pushed"] == 0 and result["pending"] == 1
    status = sync.sync_status("student-nora-rossi", root=tmp_path)
    assert "not available" in status["last_error"]


def test_failed_status_after_repeated_attempts(tmp_path):
    _seed_lens(tmp_path)
    sync.enqueue_lens("student-nora-rossi", root=tmp_path)

    def failing_push(local_path, destination_ref, *, mime=None):
        raise OSError("still down")

    import time as time_module

    now = time_module.time()
    for attempt in range(3):
        sync.drain(root=tmp_path, now=now + attempt * 90 * 60, push=failing_push)
    assert sync.sync_status("student-nora-rossi", root=tmp_path)["status"] == "failed"
    overall = sync.sync_status(root=tmp_path)
    assert overall["pending"] == 1 and overall["failed"] == 1


def test_unknown_student_is_synced_noop(tmp_path):
    assert sync.sync_status("student-ghost", root=tmp_path)["status"] == "synced"
