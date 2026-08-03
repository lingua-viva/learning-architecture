from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from sanitizer.app import sanitize
from src.lingua_viva import teacher_readiness as tr


def test_placeholder_regex_catches_teacher_surface_stub():
    text = "Answer: [Local reasoning for LV-STU-002 - no model available]"
    assert tr.PLACEHOLDER_RE.search(text)


def test_firewall_log_records_content_free_trace_id(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_SANITIZER_DATA_DIR", str(tmp_path))
    sanitize(
        "Marco Bianchi has synthetic medical note content.",
        context="education",
        block_signals=["medical note"],
        trace_id="trace-teacher-readiness",
    )
    log = tmp_path / "firewall_log.ndjson"
    record = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
    assert record["trace_id"] == "trace-teacher-readiness"
    assert record["input_length"] > 0
    assert "Marco" not in json.dumps(record)
    assert "medical note content" not in json.dumps(record)


def test_report_counts_expected_failures():
    report = tr.ReadinessReport(
        started_at="2026-08-03T00:00:00Z",
        git_sha="abc123",
        duration_ms=10,
        checks=[
            tr.ReadinessCheck("C1", "placeholder", "PASS"),
            tr.ReadinessCheck("DR", "dual routing", "FAIL", severity="P0", expected_fail=True),
        ],
        report_path="dev/reports/TEACHER_READINESS.md",
        json_path="dev/reports/TEACHER_READINESS.json",
    )
    assert report.total == 2
    assert report.passed == 1
    assert report.failed == 1
    assert report.highest_severity == "P0"
    assert report.readiness_percent == 50.0


def test_teacher_readiness_cli_dispatch(monkeypatch):
    called = {}

    class FakeReport:
        def as_dict(self):
            return {"ok": True}

    def fake_run():
        called["run"] = True
        return FakeReport()

    monkeypatch.setattr(tr, "run_teacher_readiness", fake_run)
    monkeypatch.setattr(tr, "print_summary", lambda report: "summary")

    import src.lingua_viva.cli as cli

    monkeypatch.setattr("src.lingua_viva.teacher_readiness.run_teacher_readiness", fake_run)
    monkeypatch.setattr("src.lingua_viva.teacher_readiness.print_summary", lambda report: "summary")
    assert cli._eval(Namespace(eval_command="teacher-readiness", json=False)) == 0
    assert called["run"] is True


def test_write_reports_overwrites(monkeypatch, tmp_path):
    md = tmp_path / "TEACHER_READINESS.md"
    js = tmp_path / "TEACHER_READINESS.json"
    monkeypatch.setattr(tr, "REPORT_MD", md)
    monkeypatch.setattr(tr, "REPORT_JSON", js)
    report = tr.ReadinessReport(
        started_at="2026-08-03T00:00:00Z",
        git_sha="abc123",
        duration_ms=1,
        checks=[tr.ReadinessCheck("C1", "placeholder", "PASS", chain="observe_ask")],
        report_path=str(md),
        json_path=str(js),
    )
    md.write_text("old content", encoding="utf-8")
    tr._write_reports(report)
    assert "old content" not in md.read_text(encoding="utf-8")
    assert json.loads(js.read_text(encoding="utf-8"))["summary"]["passed"] == 1


def test_frozen_corpus_exists_and_uses_synthetic_names_only():
    assert tr.CORPUS_PATH.exists()
    text = tr.CORPUS_PATH.read_text(encoding="utf-8")
    assert "Marco Bianchi" in text
    assert "Nora Rossi" in text
    assert "San Francisco" not in text
    assert "school" not in text.lower()
