"""Routing Memory tests (SPEC_LV_ROUTING_MEMORY_LOOP_2026-08-01).

Covers the spec's 7-point plan: schema/key-set (content-free proof),
correction pairing, append-only byte-stability, audit aggregation with a
hand-computed synthetic fixture, fire-and-forget under an unwritable path,
unknown-schema skipping, and hermeticity (LV_ROUTING_MEMORY_PATH -> tmp).

The correction HOOK matrix note: of the spec's four hooks, only the
category confirm-tap endpoint exists today (Spec 1); template-type edit,
student re-assignment, and clarification resolution have no endpoints yet
and are covered here at the record_correction unit level.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from src.lingua_viva.improvement_audit import (
    build_audit_report,
    build_routing_report,
    compute_delta,
    format_report,
    summary_record,
)
from src.lingua_viva.routing_memory import (
    ALLOWED_KEYS,
    SCHEMA,
    is_correction,
    read_memory,
    record_correction,
    record_decision,
    routing_memory_path,
)
from src.web import app


def _mem(monkeypatch, tmp_path: Path) -> Path:
    path = tmp_path / "routing_memory_v1.ndjson"
    monkeypatch.setenv("LV_ROUTING_MEMORY_PATH", str(path))
    return path


def _rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# Record / read unit tests
# ---------------------------------------------------------------------------

def test_decision_row_schema_and_exact_key_set(monkeypatch, tmp_path):
    path = _mem(monkeypatch, tmp_path)
    decision_id = record_decision(
        "intent", "observation", 0.7,
        signals_matched=["obs_sig"],
        subject_ref={"student_id": "student-1", "display_name": "LEAKED"},
        trace_id="trace-1",
    )
    rows = _rows(path)
    assert len(rows) == 1
    row = rows[0]
    assert row["schema"] == SCHEMA
    assert row["decision_id"] == decision_id
    assert row["corrected"] is None
    # Content-free proof: EXACT top-level key set, subject_ref ids only.
    assert set(row) == set(ALLOWED_KEYS)
    assert set(row["subject_ref"]) == {"student_id"}
    assert "LEAKED" not in path.read_text()


def test_correction_pairs_by_decision_id_and_strips_unknown_keys(monkeypatch, tmp_path):
    path = _mem(monkeypatch, tmp_path)
    decision_id = record_decision("intent", "observation", 0.7)
    record_correction(decision_id, {
        "type": "intent", "to": "question", "source": "template_type_edit",
        "transcript": "should never be stored",
    })
    rows = _rows(path)
    assert len(rows) == 2
    correction = rows[1]
    assert correction["decision_id"] == decision_id
    assert is_correction(correction)
    assert correction["corrected"] == {
        "type": "intent", "to": "question", "source": "template_type_edit"}
    assert "should never be stored" not in path.read_text()


def test_append_only_byte_stability(monkeypatch, tmp_path):
    path = _mem(monkeypatch, tmp_path)
    decision_id = record_decision("category_suggest", "social_skills", 0.4)
    before = path.read_bytes()
    record_correction(decision_id, {"type": "category_suggest", "positive": True})
    after = path.read_bytes()
    # Earlier bytes are never rewritten; the file only grows.
    assert after[: len(before)] == before
    assert len(after) > len(before)


def test_read_memory_skips_unknown_schema_and_malformed_with_count(monkeypatch, tmp_path):
    path = _mem(monkeypatch, tmp_path)
    record_decision("intent", "question", 0.5)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"schema": "lv_route_mem_v2", "decision_id": "x"}) + "\n")
        f.write("{not json\n")
        f.write(json.dumps(["not", "a", "dict"]) + "\n")
    rows, skipped = read_memory()
    assert len(rows) == 1
    assert skipped == 3


def test_read_memory_missing_file(monkeypatch, tmp_path):
    _mem(monkeypatch, tmp_path)
    assert read_memory() == ([], 0)


def test_fire_and_forget_unwritable_path_never_raises(monkeypatch, tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("a file where a directory must be")
    monkeypatch.setenv(
        "LV_ROUTING_MEMORY_PATH", str(blocker / "mem.ndjson"))
    decision_id = record_decision("intent", "question", 0.5)
    assert decision_id  # id still returned; dangling correction is harmless
    record_correction(decision_id, {"type": "intent", "to": "observation"})
    assert read_memory() == ([], 0)


def test_correction_without_decision_id_is_silent_noop(monkeypatch, tmp_path):
    path = _mem(monkeypatch, tmp_path)
    record_correction("", {"type": "intent", "to": "question"})
    assert not path.is_file() or _rows(path) == []


# ---------------------------------------------------------------------------
# Endpoint emission (end-to-end through /api/voice/act)
# ---------------------------------------------------------------------------

def _isolate(monkeypatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "students.db"))
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("LV_PRIVACY_LOG_PATH", str(tmp_path / "privacy.ndjson"))
    monkeypatch.setenv("LV_REVISION_LOG_PATH", str(tmp_path / "revision.ndjson"))
    monkeypatch.delenv("LV_AUTH_MODE", raising=False)
    return _mem(monkeypatch, tmp_path)


def _create_observed_student(client: TestClient, name: str, teacher_id: str = "teacher-a"):
    created = client.post("/api/students", json={"display_name": name, "grade_level": "G3"})
    assert created.status_code == 200
    student_id = created.json()["student_id"]
    obs = client.post(
        "/api/observe/capture",
        json={
            "student_id": student_id,
            "teacher_id": teacher_id,
            "transcript": "Private raw transcript phrase.",
            "template_type": "cefr",
            "cefr_dimension": "speaking",
            "cefr_level_observed": "A2",
            "cefr_direction": "progressing",
        },
    )
    assert obs.status_code == 200
    return student_id


def test_voice_act_emits_decisions_and_threads_ids(monkeypatch, tmp_path):
    mem = _isolate(monkeypatch, tmp_path)
    transcript = "Marco helped a classmate find the right page during group reading"
    with TestClient(app) as client:
        student_id = _create_observed_student(client, "Marco Bianchi")
        response = client.post(
            "/api/voice/act",
            json={"teacher_id": "teacher-a", "transcript": transcript},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["action_taken"] == "saved"
        ids = body["routing_decision_ids"]
        assert set(ids) == {"intent", "student_detect", "category_suggest"}

    rows, skipped = read_memory()
    assert skipped == 0
    by_id = {r["decision_id"]: r for r in rows if not is_correction(r)}
    # observe/capture (setup) emitted one category row; voice/act adds three.
    intent = by_id[ids["intent"]]
    assert intent["decision"] == "intent"
    assert intent["outcome"] == "observation"
    assert intent["signals_matched"]  # signal keys recorded
    detect = by_id[ids["student_detect"]]
    assert detect["outcome"] == "exact"
    assert detect["subject_ref"] == {"student_id": student_id}
    category = by_id[ids["category_suggest"]]
    assert category["subject_ref"]["observation_id"]
    assert category["subject_ref"]["student_id"] == student_id

    # Content-free proof at the file level: no transcript, no names.
    raw = mem.read_text()
    assert "Marco" not in raw and "Bianchi" not in raw
    assert "helped a classmate" not in raw


def test_voice_act_clarification_threads_ids_for_spec4_resolution(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        _create_observed_student(client, "Marco Bianchi")
        response = client.post(
            "/api/voice/act",
            json={
                "teacher_id": "teacher-a",
                "transcript": "The student struggled with the reading exercise today",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["action_taken"] == "needs_clarification"
        ids = body["routing_decision_ids"]
        assert set(ids) == {"intent", "student_detect"}
    rows, _ = read_memory()
    by_id = {r["decision_id"]: r for r in rows if not is_correction(r)}
    assert by_id[ids["student_detect"]]["outcome"] == "none"


def test_voice_act_survives_unwritable_routing_memory(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory")
    monkeypatch.setenv("LV_ROUTING_MEMORY_PATH", str(blocker / "mem.ndjson"))
    with TestClient(app) as client:
        _create_observed_student(client, "Marco Bianchi")
        response = client.post(
            "/api/voice/act",
            json={
                "teacher_id": "teacher-a",
                "transcript": "Marco helped a classmate find the right page during group reading",
            },
        )
        # Fire-and-forget proof: the save path is completely unaffected.
        assert response.status_code == 200
        assert response.json()["action_taken"] == "saved"


def test_observe_capture_emits_category_decision(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        _create_observed_student(client, "Nora Rossi")
    rows, _ = read_memory()
    decisions = [r for r in rows if not is_correction(r)]
    assert len(decisions) == 1
    assert decisions[0]["decision"] == "category_suggest"
    assert decisions[0]["subject_ref"]["observation_id"]


# ---------------------------------------------------------------------------
# Audit aggregation — hand-computed synthetic fixture
# ---------------------------------------------------------------------------

def _synthetic_memory(monkeypatch, tmp_path) -> None:
    """100 decision rows with hand-computable aggregates.

    intent: 60 rows (40 question / 15 observation / 5 generate);
      6 corrected (conf 0.4 each), the rest conf 0.8.
      signal "obs_sig" fires on 10 rows, 6 of them the corrected ones.
    category_suggest: 30 rows, all outcome executive_functioning;
      4 corrected (negative), 2 confirmed (positive).
    student_detect: 10 rows (8 exact / 2 none); 1 corrected.
    """
    _mem(monkeypatch, tmp_path)
    for i in range(60):
        outcome = "question" if i < 40 else ("observation" if i < 55 else "generate")
        # exactly 6 corrected: rows 40-45 (observation block)
        corrected = 40 <= i < 46
        signals = ["obs_sig"] if 40 <= i < 50 else []
        decision_id = record_decision(
            "intent", outcome, 0.4 if corrected else 0.8, signals_matched=signals)
        if corrected:
            record_correction(decision_id, {"type": "intent", "to": "question"})
    for i in range(30):
        decision_id = record_decision(
            "category_suggest", "executive_functioning", 0.5)
        if i < 4:
            record_correction(decision_id, {
                "type": "category_suggest", "category_id": "social_skills"})
        elif i < 6:
            record_correction(decision_id, {
                "type": "category_suggest", "positive": True,
                "category_id": "executive_functioning"})
    for i in range(10):
        matched = i < 8
        decision_id = record_decision(
            "student_detect", "exact" if matched else "none",
            1.0 if matched else 0.0)
        if i == 0:
            record_correction(decision_id, {
                "type": "student_detect", "student_id": "student-2"})


def test_routing_report_hand_computed(monkeypatch, tmp_path):
    _synthetic_memory(monkeypatch, tmp_path)
    rows, skipped = read_memory()
    report = build_routing_report(rows, skipped)

    intent = report["per_type"]["intent"]
    assert intent["volume"] == 60
    assert intent["corrected"] == 6
    assert intent["correction_rate"] == 0.1
    assert intent["confidence_corrected"] == 0.4
    assert intent["confidence_uncorrected"] == 0.8

    category = report["per_type"]["category_suggest"]
    assert category["volume"] == 30
    assert category["corrected"] == 4        # positives never count as corrections
    assert category["confirmed"] == 2
    assert category["correction_rate"] == round(4 / 30, 3)

    detect = report["per_type"]["student_detect"]
    assert detect["volume"] == 10
    assert detect["corrected"] == 1

    # Per-signal precision proxy: obs_sig fired 10x, 6 corrected -> 60%.
    obs_sig = next(s for s in report["per_signal"] if s["signal"] == "obs_sig")
    assert obs_sig["fired"] == 10
    assert obs_sig["corrected"] == 6
    assert obs_sig["precision_gap"] == 0.6
    # ...which crosses the proposal thresholds (fired>=5, rate>=0.5).
    assert any("obs_sig" in p for p in report["proposals"])

    # 40/60 top intent share = 67% -> no collapse flag.
    assert not any(f["type"] == "intent_collapse" for f in report["collapse_flags"])


def test_intent_collapse_flag_over_90_percent(monkeypatch, tmp_path):
    _mem(monkeypatch, tmp_path)
    for i in range(12):
        record_decision("intent", "question" if i < 11 else "generate", 0.5)
    rows, _ = read_memory()
    report = build_routing_report(rows)
    flags = [f for f in report["collapse_flags"] if f["type"] == "intent_collapse"]
    assert len(flags) == 1
    assert flags[0]["outcome"] == "question"
    assert flags[0]["volume"] == 12
    assert any("collapsed" in p for p in report["proposals"])


def test_category_never_fires_flag_needs_50_corrected(monkeypatch, tmp_path):
    _mem(monkeypatch, tmp_path)
    for _ in range(50):
        decision_id = record_decision("category_suggest", "social_skills", 0.5)
        record_correction(decision_id, {
            "type": "category_suggest", "category_id": "emotional_regulation"})
    rows, _ = read_memory()
    report = build_routing_report(rows)
    never = {f["category_id"] for f in report["collapse_flags"]
             if f["type"] == "category_never_fires"}
    assert "executive_functioning" in never
    assert "social_skills" not in never


def test_empty_memory_report(monkeypatch, tmp_path):
    _mem(monkeypatch, tmp_path)
    report = build_routing_report([], 0)
    assert report["per_type"] == {}
    assert report["collapse_flags"] == []
    assert report["proposals"] == []


# ---------------------------------------------------------------------------
# lv distill / lv audit integration
# ---------------------------------------------------------------------------

def _distill_env(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_GAP_SIGNALS_PATH", str(tmp_path / "gaps.ndjson"))
    monkeypatch.setenv("LV_REVISION_LOG_PATH", str(tmp_path / "rev.ndjson"))
    monkeypatch.setenv("LV_AUDIT_SUMMARY_PATH", str(tmp_path / "summary.ndjson"))
    return _mem(monkeypatch, tmp_path)


def test_distill_renders_routing_section_on_empty_memory(monkeypatch, tmp_path):
    _distill_env(monkeypatch, tmp_path)
    report = build_audit_report(classify_fn=None, candidates=[])
    text = format_report(report)
    assert "[6] ROUTING DECISIONS" in text
    assert "no routing memory on record" in text


def test_distill_renders_routing_numbers(monkeypatch, tmp_path):
    _distill_env(monkeypatch, tmp_path)
    decision_id = record_decision("intent", "observation", 0.7)
    record_correction(decision_id, {"type": "intent", "to": "question"})
    report = build_audit_report(classify_fn=None, candidates=[])
    assert report["routing"]["per_type"]["intent"]["corrected"] == 1
    text = format_report(report)
    assert "intent" in text and "corrected=  1 (100%)" in text


def test_summary_and_delta_carry_routing_movement(monkeypatch, tmp_path):
    _distill_env(monkeypatch, tmp_path)
    report = build_audit_report(classify_fn=None, candidates=[])
    prev = summary_record(report)
    assert prev["routing_decisions"] == 0

    decision_id = record_decision("intent", "observation", 0.7)
    record_correction(decision_id, {"type": "intent", "to": "question"})
    cur = summary_record(build_audit_report(classify_fn=None, candidates=[]))
    assert cur["routing_decisions"] == 1
    assert cur["routing_corrections"] == 1
    lines = compute_delta(prev, cur)
    assert any("routing decisions: 0 -> 1" in line for line in lines)

    # Baselines written BEFORE this spec lack routing keys — no crash, no line.
    legacy = {k: v for k, v in prev.items() if not k.startswith("routing_")}
    assert not any("routing" in line for line in compute_delta(legacy, cur))


def test_gap_audit_routing_block_is_informational(monkeypatch, tmp_path, capsys):
    from src.lingua_viva.gap_audit import run_audit

    _mem(monkeypatch, tmp_path)
    record_decision("intent", "question", 0.5)
    exit_code = run_audit(
        json_out=True,
        signals_file=tmp_path / "gaps.ndjson",
        summaries_file=tmp_path / "summaries.ndjson",
        firewall_file=tmp_path / "firewall.ndjson",
        proposals_dir=tmp_path / "proposals",
    )
    # Routing never gates: empty gap journal + 1 routing decision -> exit 0.
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["report"]["routing"]["decisions"] == 1
    assert payload["report"]["routing"]["corrections"] == 0


# ---------------------------------------------------------------------------
# Correction hook: category confirm-tap (the one hook endpoint that exists)
# ---------------------------------------------------------------------------

def test_confirm_endpoint_without_decision_id_skips_silently(monkeypatch, tmp_path):
    path = _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        student_id = _create_observed_student(client, "Marco Bianchi")
        # Invalid entry -> 400 path; the point is no correction row and no 500.
        response = client.post(
            f"/api/students/{student_id}/support-entry/confirm",
            json={"category_id": "social_skills", "bucket": "needs", "entry_id": "nope"},
        )
        assert response.status_code in (200, 400, 404)
    rows, _ = read_memory()
    assert not any(is_correction(r) for r in rows)


def test_confirm_endpoint_pairs_correction_server_side(monkeypatch, tmp_path):
    """The loop with NO client threading: capture persists its decision ids
    on the observation row (routing_decision_ids column); a later confirm-tap
    whose payload carries only category/bucket/entry ids — exactly what the
    shipped UI sends — resolves the decision id server-side through the
    entry's source observation and appends a positive correction row."""
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        created = client.post(
            "/api/students", json={"display_name": "Marco Bianchi", "grade_level": "G3"}
        )
        assert created.status_code == 200
        student_id = created.json()["student_id"]
        obs = client.post(
            "/api/observe/capture",
            json={
                "student_id": student_id,
                "teacher_id": "teacher-a",
                "transcript": (
                    "Marco struggled to stay on task so we tried a visual "
                    "timer and it worked"
                ),
                "template_type": "cefr",
                "cefr_dimension": "speaking",
                "cefr_level_observed": "A2",
                "cefr_direction": "progressing",
            },
        )
        assert obs.status_code == 200
        decision_id = obs.json()["routing_decision_ids"]["category_suggest"]
        autofiled = obs.json()["strategy_outcome_parsed"]["autofiled"]
        assert autofiled is not None
        lens = client.get(f"/api/students/{student_id}/lens").json()
        entry = lens["support_profile"]["categories"][autofiled["category_id"]][
            autofiled["bucket"]
        ][0]
        response = client.post(
            f"/api/students/{student_id}/support-entry/confirm",
            json={
                "category_id": autofiled["category_id"],
                "bucket": autofiled["bucket"],
                "entry_id": entry["id"],
            },
        )
        assert response.status_code == 200
    rows, _ = read_memory()
    corrections = [row for row in rows if is_correction(row)]
    assert len(corrections) == 1
    assert corrections[0]["decision_id"] == decision_id
    assert corrections[0]["corrected"]["positive"] is True
    assert corrections[0]["corrected"]["source"] == "support_entry_confirm"


# ---------------------------------------------------------------------------
# Hardening loop (2026-08-02): fire-and-forget completeness, content-free
# token guard, empty-correction drop, dangling counts, concurrency
# ---------------------------------------------------------------------------

def test_record_decision_never_raises_on_garbage_args(monkeypatch, tmp_path):
    path = _mem(monkeypatch, tmp_path)
    # Non-iterable signals, non-dict subject_ref: swallowed, id still returned.
    did = record_decision("intent", "observation", 0.5, signals_matched=42)
    assert isinstance(did, str) and did
    did2 = record_decision("intent", "observation", 0.5, subject_ref="not-a-dict")
    assert isinstance(did2, str) and did2
    # Whatever DID land must still be valid rows.
    for row in _rows(path):
        assert row["schema"] == SCHEMA


def test_unknown_decision_type_is_dropped_not_recorded(monkeypatch, tmp_path):
    path = _mem(monkeypatch, tmp_path)
    did = record_decision("free text transcript here", "observation", 0.5)
    assert isinstance(did, str) and did  # id still returned (fire-and-forget)
    assert _rows(path) == []


def test_non_finite_confidence_clamped_to_zero(monkeypatch, tmp_path):
    path = _mem(monkeypatch, tmp_path)
    record_decision("intent", "observation", float("nan"))
    record_decision("intent", "observation", float("inf"))
    rows = _rows(path)  # json.loads would choke on bare NaN in strict parsers
    assert [r["confidence"] for r in rows] == [0.0, 0.0]
    assert "NaN" not in path.read_text() and "Infinity" not in path.read_text()


def test_token_guard_blocks_free_text_in_every_string_field(monkeypatch, tmp_path):
    path = _mem(monkeypatch, tmp_path)
    leak = "Marco struggled with the past tense today"
    record_decision(
        "intent", leak, 0.5,
        signals_matched=[leak, "ok_sig"],
        subject_ref={"student_id": leak},
        trace_id=leak,
    )
    record_correction("d" * 200, {"type": "intent", "to": leak})
    record_correction("abc123", {"type": "intent", "to": leak})
    text = path.read_text()
    assert "Marco" not in text and "past tense" not in text
    rows = _rows(path)
    assert rows[0]["outcome"] == "invalid_token"
    assert rows[0]["signals_matched"] == ["invalid_token", "ok_sig"]
    assert rows[0]["subject_ref"]["student_id"] == "invalid_token"
    assert rows[0]["trace_id"] == "invalid_token"


def test_empty_correction_payload_is_not_appended(monkeypatch, tmp_path):
    path = _mem(monkeypatch, tmp_path)
    decision_id = record_decision("intent", "observation", 0.5)
    record_correction(decision_id, {"unknown_key": "x", "another": 1})
    record_correction(decision_id, {})
    record_correction(decision_id, None)
    rows = _rows(path)
    assert len(rows) == 1  # only the decision row
    # And the report must show zero corrections (empty dicts used to read
    # as NEGATIVE corrections and inflate correction_rate).
    report = build_routing_report(*read_memory())
    assert report["per_type"]["intent"]["corrected"] == 0


def test_dangling_corrections_counted_in_report(monkeypatch, tmp_path):
    _mem(monkeypatch, tmp_path)
    decision_id = record_decision("intent", "observation", 0.5)
    record_correction(decision_id, {"type": "intent", "to": "question"})
    record_correction("no-such-decision", {"type": "intent", "to": "question"})
    report = build_routing_report(*read_memory())
    assert report["dangling_corrections"] == 1
    assert report["per_type"]["intent"]["corrected"] == 1
    rendered = format_report(
        build_audit_report(classify_fn=lambda q: ("none", 0.0), candidates=[]))
    assert "dangling corrections: 1" in rendered


def test_negative_and_positive_corrections_on_same_decision(monkeypatch, tmp_path):
    _mem(monkeypatch, tmp_path)
    decision_id = record_decision("category_suggest", "cat_a", 0.5)
    record_correction(decision_id, {
        "type": "category_suggest", "positive": True, "category_id": "cat_a"})
    record_correction(decision_id, {
        "type": "category_suggest", "category_id": "cat_b",
        "source": "recategorize"})
    t = build_routing_report(*read_memory())["per_type"]["category_suggest"]
    assert t["volume"] == 1 and t["corrected"] == 1 and t["confirmed"] == 1


def test_concurrent_appends_produce_only_valid_rows(monkeypatch, tmp_path):
    import concurrent.futures

    path = _mem(monkeypatch, tmp_path)

    def burst(n: int) -> None:
        for i in range(25):
            record_decision("intent", f"outcome_{n}_{i}", 0.5,
                            signals_matched=[f"sig_{n}"])

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(burst, range(8)))

    rows, skipped = read_memory()
    assert skipped == 0
    assert len(rows) == 200
    assert all(r["schema"] == SCHEMA for r in rows)
    assert _rows(path) == rows  # every line independently parseable
