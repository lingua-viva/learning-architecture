from __future__ import annotations

import json

from src.lingua_viva import improve_surface as surface


def test_measurement_manifest_flags_active_internal_only():
    findings = []
    summary = surface._measurement_value(findings)

    assert summary["instruments"] >= 5
    assert "measurement_distillation" in summary["needs_value_review"]
    assert any(f.finding_id == "measurement_value:internal_only_active" for f in findings)


def test_production_surface_reads_single_local_desktop_pin_without_live_network():
    findings = []
    summary = surface._production_surface(findings, live=False)

    assert summary["live_checked"] is False
    assert summary["pinned_desktop_tag"].startswith("desktop-v")
    assert "LinguaViva.dmg" in summary["desktop_assets"]
    assert "LinguaViva-Setup.exe" in summary["desktop_assets"]
    assert "LinguaViva.AppImage" in summary["desktop_assets"]


def test_build_report_can_skip_expensive_readiness(monkeypatch):
    monkeypatch.setattr(surface, "_route_reachability", lambda findings: {"status": "PASS"})
    monkeypatch.setattr(surface, "_admin_metrics", lambda findings: {"status": "PASS"})
    monkeypatch.setattr(surface, "_production_surface", lambda findings, live: {"status": "PASS"})
    monkeypatch.setattr(surface, "_measurement_value", lambda findings: {"status": "PASS"})

    report = surface.build_report(run_readiness=False, live=False)

    assert report["sections"]["teacher_readiness"]["status"] == "SKIPPED"
    assert report["verdict"] == "READY"


def test_improve_cli_dispatches_json(monkeypatch, capsys):
    from src.lingua_viva import cli

    monkeypatch.setattr(
        "src.lingua_viva.improve_surface.build_report",
        lambda run_readiness, live: {
            "verdict": "READY",
            "summary": {"findings": 0, "p0": 0, "p1": 0, "p2": 0, "p3": 0},
            "sections": {},
            "findings": [],
        },
    )

    assert cli.main(["improve", "--no-readiness", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["verdict"] == "READY"
