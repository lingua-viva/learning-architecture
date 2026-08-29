from __future__ import annotations

import contextlib
import io
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
MEASUREMENT_MANIFEST = REPO_ROOT / "config" / "measurement_manifest.yaml"
DOCS_INDEX = REPO_ROOT / "docs" / "index.html"
LIVE_SITE = "https://linguaviva.art/"
DESKTOP_ASSETS = ("LinguaViva.dmg", "LinguaViva-Setup.exe", "LinguaViva.AppImage")

VALID_VALUE_CATEGORIES = {
    "teacher_daily",
    "teacher_weekly",
    "admin_visibility",
    "privacy/safety",
    "release_only",
    "internal_only",
}
VALID_LIFECYCLES = {
    "active",
    "teacher-facing",
    "admin-only",
    "release-only",
    "retired",
}


@dataclass
class ImproveFinding:
    finding_id: str
    severity: str
    audience: str
    title: str
    action: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_report(*, run_readiness: bool = True, live: bool = False) -> dict[str, Any]:
    findings: list[ImproveFinding] = []
    sections = {
        "teacher_readiness": _teacher_readiness(run_readiness, findings),
        "route_reachability": _route_reachability(findings),
        "governance_honesty": _governance_honesty(findings),
        "admin_metrics": _admin_metrics(findings),
        "measurement_value": _measurement_value(findings),
        "production_surface": _production_surface(findings, live=live),
    }
    ordered = sorted(findings, key=lambda f: (_severity_rank(f.severity), f.finding_id))
    verdict = _verdict(ordered)
    return {
        "verdict": verdict,
        "summary": {
            "findings": len(ordered),
            "p0": sum(1 for f in ordered if f.severity == "P0"),
            "p1": sum(1 for f in ordered if f.severity == "P1"),
            "p2": sum(1 for f in ordered if f.severity == "P2"),
            "p3": sum(1 for f in ordered if f.severity == "P3"),
        },
        "sections": sections,
        "findings": [f.as_dict() for f in ordered],
    }


def format_report(report: dict[str, Any]) -> str:
    lines = [f"LV improve: {report['verdict']}"]
    summary = report["summary"]
    lines.append(
        f"Findings: {summary['findings']} "
        f"(P0 {summary['p0']}, P1 {summary['p1']}, P2 {summary['p2']}, P3 {summary['p3']})"
    )
    production = report["sections"]["production_surface"]
    if production.get("pinned_desktop_tag"):
        lines.append(f"Desktop site pin: {production['pinned_desktop_tag']}")
    if report["findings"]:
        lines.append("")
        for finding in report["findings"]:
            lines.append(f"- {finding['severity']} [{finding['audience']}] {finding['title']}")
            lines.append(f"  Action: {finding['action']}")
    return "\n".join(lines)


def _teacher_readiness(run_readiness: bool, findings: list[ImproveFinding]) -> dict[str, Any]:
    if not run_readiness:
        return {"status": "SKIPPED", "reason": "disabled by --no-readiness"}
    from src.lingua_viva.teacher_readiness import run_teacher_readiness

    report = run_teacher_readiness()
    gating = [
        check for check in report.checks
        if check.status == "FAIL" and check.severity in ("P0", "P1") and not check.expected_fail
    ]
    for check in gating:
        findings.append(
            ImproveFinding(
                finding_id=f"teacher_readiness:{check.check_id}",
                severity=check.severity,
                audience="teacher",
                title=check.name,
                action="Fix the teacher workflow before treating LV as ready for classroom use.",
                evidence={"check_id": check.check_id, "chain": check.chain, **check.evidence},
            )
        )
    return {
        "status": "PASS" if not gating else "FAIL",
        "readiness_percent": report.readiness_percent,
        "passed": report.passed,
        "total": report.total,
        "failed": report.failed,
        "report_path": report.report_path,
    }


def _route_reachability(findings: list[ImproveFinding]) -> dict[str, Any]:
    from scripts import check_route_reachability as routes

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = routes.check()
    manifest = routes.load_manifest()
    reachable = manifest.get("reachable_from_ui") or []
    backend = manifest.get("intentionally_backend_only") or []
    deferred = [entry for entry in backend if entry.get("status") == "deferred_undecided"]
    if code != 0:
        findings.append(
            ImproveFinding(
                finding_id="route_reachability:check",
                severity="P1",
                audience="release",
                title="Route reachability gate is failing",
                action="Classify, mount, or remove the failing routes before release.",
                evidence={"output": buffer.getvalue().splitlines()[:20]},
            )
        )
    if deferred:
        findings.append(
            ImproveFinding(
                finding_id="route_reachability:deferred",
                severity="P3",
                audience="product",
                title="Backend-only routes still need product disposition",
                action="Mark each deferred route as teacher/admin-facing, permanent backend-only, or dead.",
                evidence={"count": len(deferred), "routes": [e.get("route") for e in deferred[:20]]},
            )
        )
    return {
        "status": "PASS" if code == 0 else "FAIL",
        "reachable_from_ui": len(reachable),
        "backend_only": len(backend),
        "deferred_undecided": len(deferred),
        "teacher_reachable": sum(1 for e in reachable if _route_audience(e.get("route", "")) == "teacher"),
        "admin_reachable": sum(1 for e in reachable if _route_audience(e.get("route", "")) == "admin"),
    }


def _admin_metrics(findings: list[ImproveFinding]) -> dict[str, Any]:
    from src.lingua_viva import admin_metrics

    evidence = admin_metrics.evidence_metrics()
    capacity = admin_metrics.capacity_metrics()
    trends = admin_metrics.trends_metrics()
    unavailable = [
        name for name, payload in (
            ("evidence", evidence), ("capacity", capacity), ("trends", trends)
        )
        if payload.get("available") is False
    ]
    if unavailable:
        findings.append(
            ImproveFinding(
                finding_id="admin_metrics:unavailable",
                severity="P2",
                audience="admin",
                title="Coordinator metrics cannot read local state",
                action="Keep the empty-state honesty, but fix the local store read error.",
                evidence={"unavailable": unavailable},
            )
        )
    return {
        "status": "PASS" if not unavailable else "WARN",
        "evidence_empty_reason": evidence.get("empty_reason"),
        "capacity_empty_reason": capacity.get("empty_reason"),
        "trends_empty_reason": trends.get("empty_reason"),
        "students_without_recent_observations": evidence.get("not_covered", 0),
    }


def _governance_honesty(findings: list[ImproveFinding]) -> dict[str, Any]:
    from src.lingua_viva.governance import check_governance_honesty

    result = check_governance_honesty()
    blocking = [item for item in result.get("findings") or [] if item.get("severity") in {"P0", "P1"}]
    if blocking:
        findings.append(
            ImproveFinding(
                finding_id="governance_honesty:ledger_mismatch",
                severity="P1",
                audience="admin",
                title="Governance dashboard counters do not match local evidence",
                action="Fix the Trust Status counters before using the governance pack with administrators.",
                evidence={"findings": blocking},
            )
        )
    return result


def _measurement_value(findings: list[ImproveFinding]) -> dict[str, Any]:
    data = yaml.safe_load(MEASUREMENT_MANIFEST.read_text(encoding="utf-8")) or {}
    instruments = data.get("instruments") or []
    invalid: list[str] = []
    review: list[str] = []
    for instrument in instruments:
        ident = str(instrument.get("id") or "")
        category = instrument.get("value_category")
        lifecycle = instrument.get("lifecycle")
        if category not in VALID_VALUE_CATEGORIES or lifecycle not in VALID_LIFECYCLES:
            invalid.append(ident)
        if category == "internal_only" and lifecycle != "retired":
            review.append(ident)
    if invalid:
        findings.append(
            ImproveFinding(
                finding_id="measurement_value:invalid_manifest",
                severity="P2",
                audience="release",
                title="Measurement manifest has invalid categories",
                action="Use only the declared value categories and lifecycle states.",
                evidence={"instrument_ids": invalid},
            )
        )
    if review:
        findings.append(
            ImproveFinding(
                finding_id="measurement_value:internal_only_active",
                severity="P3",
                audience="operator",
                title="Active instruments lack direct teacher/admin value",
                action="Review whether these checks still produce concrete fixes; retire them if not.",
                evidence={"instrument_ids": review},
            )
        )
    return {
        "status": "PASS" if not invalid else "WARN",
        "manifest": str(MEASUREMENT_MANIFEST.relative_to(REPO_ROOT)),
        "instruments": len(instruments),
        "needs_value_review": review,
    }


def _production_surface(findings: list[ImproveFinding], *, live: bool) -> dict[str, Any]:
    html = DOCS_INDEX.read_text(encoding="utf-8") if DOCS_INDEX.exists() else ""
    tags = sorted(set(re.findall(r"desktop-v[0-9.]+", html)))
    release_urls = re.findall(r'https://github\.com/lingua-viva/learning-architecture/releases/download/([^"]+)', html)
    assets = {Path(url).name for url in release_urls}
    missing_assets = [asset for asset in DESKTOP_ASSETS if asset not in assets]
    if len(tags) != 1 or missing_assets:
        findings.append(
            ImproveFinding(
                finding_id="production_surface:local_site_pin",
                severity="P1",
                audience="release",
                title="Public site download surface is not a single complete desktop release",
                action="Pin docs/index.html to exactly one desktop tag with Mac, Windows, and Linux artifacts.",
                evidence={"desktop_tags": tags, "missing_assets": missing_assets},
            )
        )
    result = {
        "status": "PASS" if len(tags) == 1 and not missing_assets else "FAIL",
        "pinned_desktop_tag": tags[0] if len(tags) == 1 else None,
        "desktop_tags": tags,
        "desktop_assets": sorted(assets),
        "live_checked": live,
    }
    if live:
        checks = [_head_status(LIVE_SITE)]
        tag = result["pinned_desktop_tag"]
        if tag:
            for asset in DESKTOP_ASSETS:
                checks.append(
                    _head_status(
                        f"https://github.com/lingua-viva/learning-architecture/releases/download/{tag}/{asset}"
                    )
                )
        failed = [check for check in checks if check["ok"] is False]
        if failed:
            findings.append(
                ImproveFinding(
                    finding_id="production_surface:live_downloads",
                    severity="P1",
                    audience="release",
                    title="Live site or release artifacts are not reachable",
                    action="Fix the live Pages deploy or release assets before calling the app pushed.",
                    evidence={"failed": failed},
                )
            )
        result["live"] = checks
    return result


def _head_status(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "lv-improve/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return {"url": url, "status": response.status, "ok": 200 <= response.status < 400}
    except urllib.error.HTTPError as exc:
        return {"url": url, "status": exc.code, "ok": 200 <= exc.code < 400}
    except Exception as exc:  # noqa: BLE001 - reported as live-surface evidence
        return {"url": url, "status": None, "ok": False, "error": type(exc).__name__}


def _route_audience(route: str) -> str:
    if route.startswith(("GET /api/admin/", "POST /api/admin/")):
        return "admin"
    if "/safeguarding/" in route or "/ops/staffing" in route or "/audit-receipts/" in route:
        return "admin"
    return "teacher"


def _severity_rank(severity: str) -> int:
    return {"P0": 0, "P1": 1, "P2": 2, "P3": 3}.get(severity, 99)


def _verdict(findings: list[ImproveFinding]) -> str:
    if any(f.severity == "P0" for f in findings):
        return "BLOCKED"
    if any(f.severity == "P1" for f in findings):
        return "NOT READY"
    if any(f.severity in {"P2", "P3"} for f in findings):
        return "READY WITH REVIEW"
    return "READY"
