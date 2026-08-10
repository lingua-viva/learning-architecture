from __future__ import annotations

import json
import os
import re
import socket
import tempfile
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]

def _state_home() -> Path:
    """Writable state directory — never inside the signed bundle (F6/P1-1)."""
    return Path(os.environ.get("LV_STATE_HOME", str(Path.home() / ".lingua-viva")))

REPORT_MD = _state_home() / "reports" / "TEACHER_READINESS.md"
REPORT_JSON = _state_home() / "reports" / "TEACHER_READINESS.json"
CORPUS_PATH = REPO_ROOT / "tests" / "fixtures" / "teacher_readiness_corpus.yaml"
PLACEHOLDER_RE = re.compile(r"\[[^\]\n]*(?:no model available|Local reasoning|stub|placeholder)[^\]\n]*\]", re.I)
OBS_ID_RE = re.compile(r"\bOBS-[A-Za-z0-9_-]+\b")


@dataclass
class ReadinessCheck:
    check_id: str
    name: str
    status: str
    severity: str = ""
    chain: str = "preflight"
    expected_fail: bool = False
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReadinessReport:
    started_at: str
    git_sha: str
    duration_ms: int
    checks: list[ReadinessCheck]
    report_path: str
    json_path: str

    @property
    def total(self) -> int:
        return len(self.checks)

    @property
    def passed(self) -> int:
        return sum(1 for check in self.checks if check.status == "PASS")

    @property
    def failed(self) -> int:
        return sum(1 for check in self.checks if check.status == "FAIL")

    @property
    def stubbed(self) -> int:
        return sum(1 for check in self.checks if check.status == "STUB")

    @property
    def readiness_percent(self) -> float:
        return round((self.passed / max(self.total, 1)) * 100, 1)

    @property
    def highest_severity(self) -> str:
        order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "": 99}
        severities = [check.severity for check in self.checks if check.status == "FAIL"]
        if not severities:
            return "none"
        return sorted(severities, key=lambda item: order.get(item, 99))[0]

    def as_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at,
            "git_sha": self.git_sha,
            "duration_ms": self.duration_ms,
            "summary": {
                "total": self.total,
                "passed": self.passed,
                "failed": self.failed,
                "stubbed": self.stubbed,
                "readiness_percent": self.readiness_percent,
                "highest_severity": self.highest_severity,
            },
            "checks": [check.as_dict() for check in self.checks],
            "report_path": self.report_path,
            "json_path": self.json_path,
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _git_sha() -> str:
    import subprocess

    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True).strip()
    except Exception:
        return "unknown"


def _state_dir() -> Path:
    path = Path(
        os.environ.get(
            "LV_TEACHER_READINESS_STATE_DIR",
            Path(tempfile.gettempdir()) / "lv_teacher_readiness",
        )
    )
    path.mkdir(parents=True, exist_ok=True)
    return path


def _configure_isolated_state(base: Path) -> None:
    os.environ.setdefault("LV_DEV_MODE", "1")
    os.environ["LV_STUDENT_DB_PATH"] = str(base / "student_lenses.db")
    os.environ["LV_TRACE_PATH"] = str(base / "traces.ndjson")
    os.environ["LV_PRIVACY_LOG_PATH"] = str(base / "privacy_events.ndjson")
    os.environ["LV_FILE_MAP_PATH"] = str(base / "file_map.yaml")
    os.environ["LV_REQUEST_LOG_PATH"] = str(base / "request_events.ndjson")
    os.environ["LV_ROUTING_MEMORY_PATH"] = str(base / "routing_memory.ndjson")
    os.environ["LV_REVISION_LOG_PATH"] = str(base / "lv_revision_log.ndjson")
    os.environ["LV_SANITIZER_DATA_DIR"] = str(base / "sanitizer")
    os.environ["LV_CONFIG_HOME"] = str(base / "config")
    os.environ["LV_UPDATE_HOME"] = str(base / "update-home")
    os.environ["LV_GOOGLE_DRIVE_AUTH_PATH"] = str(base / "google_drive.json")
    os.environ["LV_GOOGLE_DRIVE_FOLDERS_PATH"] = str(base / "drive_folders.json")
    os.environ["LV_LOCAL_IMPORTS_DIR"] = str(base / "local-imports")


@contextmanager
def _localhost_socket_guard():
    original_connect = socket.socket.connect
    allowed_hosts = {"127.0.0.1", "::1", "localhost"}
    attempts: list[dict[str, Any]] = []

    def guarded_connect(sock, address):
        host = address[0] if isinstance(address, tuple) and address else str(address)
        attempts.append({"host": host})
        if host not in allowed_hosts:
            raise RuntimeError(f"teacher-readiness blocked outbound socket: {host}")
        return original_connect(sock, address)

    socket.socket.connect = guarded_connect
    try:
        yield attempts
    finally:
        socket.socket.connect = original_connect


def _jsonish(response) -> dict[str, Any]:
    try:
        data = response.json()
    except Exception:
        return {"_raw": response.text}
    return data if isinstance(data, dict) else {"_data": data}


def _body_text(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True)


def _add_check(
    checks: list[ReadinessCheck],
    check_id: str,
    name: str,
    ok: bool,
    *,
    chain: str,
    severity: str = "",
    evidence: dict[str, Any] | None = None,
    expected_fail: bool = False,
) -> None:
    checks.append(
        ReadinessCheck(
            check_id=check_id,
            name=name,
            status="PASS" if ok else "FAIL",
            severity="" if ok else severity,
            chain=chain,
            expected_fail=expected_fail and not ok,
            evidence=evidence or {},
        )
    )


def _load_corpus() -> list[dict[str, Any]]:
    data = yaml.safe_load(CORPUS_PATH.read_text(encoding="utf-8")) or {}
    return list(data.get("controls") or [])


def _create_student(client, name: str, grade: str = "G3") -> str:
    response = client.post("/api/students", json={"display_name": name, "grade_level": grade})
    data = _jsonish(response)
    if response.status_code >= 400:
        roster = client.get("/api/students").json().get("students", [])
        for row in roster:
            if row.get("display_name") == name:
                return row["student_id"]
        raise RuntimeError(f"could not create student {name}: {data}")
    return str(data["student_id"])


def _capture(client, student_id: str, text: str, *, template_type: str = "general", **extra: Any) -> dict[str, Any]:
    payload = {
        "student_id": student_id,
        "teacher_id": "teacher-readiness",
        "raw_transcript": text,
        "template_type": template_type,
        "source_type": "teacher_readiness_harness",
    }
    payload.update(extra)
    response = client.post(
        "/api/observe/capture",
        json=payload,
    )
    data = _jsonish(response)
    data["_status_code"] = response.status_code
    return data


def _post_query(client, query: str, *, timeout_seconds: float = 8) -> dict[str, Any]:
    response = client.post(
        "/api/query",
        json={"query": query, "intent": "TEACHER_READINESS", "eval_mode": True, "timeout_seconds": timeout_seconds},
    )
    data = _jsonish(response)
    data["_status_code"] = response.status_code
    return data


def _chain_observe_ask(client, ids: dict[str, str], checks: list[ReadinessCheck]) -> None:
    chain = "observe_ask"
    start = time.monotonic()
    first = _capture(client, ids["Marco Bianchi"], "Marco Bianchi self-corrected passato prossimo during partner work.")
    second = _capture(client, ids["Marco Bianchi"], "Marco Bianchi asked for a sentence frame before speaking.")
    query = _post_query(client, "What support should I prepare for Marco Bianchi tomorrow?")
    elapsed = int((time.monotonic() - start) * 1000)
    body = _body_text({"first": first, "second": second, "query": query})
    _add_check(checks, "C1", "No bracket placeholder reaches Observe -> Ask", not PLACEHOLDER_RE.search(body), chain=chain, severity="P0", evidence={"placeholder_match": PLACEHOLDER_RE.search(body).group(0) if PLACEHOLDER_RE.search(body) else None})
    _add_check(checks, "C3", "No-model response is teacher-facing, not a stub", not PLACEHOLDER_RE.search(_body_text(query)) and "Traceback" not in body, chain=chain, severity="P1", evidence={"model_used": query.get("model_used"), "status": query.get("_status_code")})
    _add_check(checks, "C4", "GIR/tone values are coherent when present", _gir_tone_ok(query), chain=chain, severity="P1", evidence={"gir": query.get("gir"), "voice_tone": query.get("voice_tone")})
    _add_check(checks, "C8", "Observe -> Ask latency envelope", elapsed < 120_000, chain=chain, severity="P1", evidence={"duration_ms": elapsed})


def _chain_observe_materials(client, ids: dict[str, str], checks: list[ReadinessCheck]) -> None:
    chain = "observe_materials"
    start = time.monotonic()
    capture_start = time.monotonic()
    capture = _capture(
        client,
        ids["Nora Rossi"],
        "Nora Rossi used full sentences with visual support.",
        template_type="cefr",
        cefr_dimension="speaking",
        cefr_level_observed="A2",
    )
    capture_ms = int((time.monotonic() - capture_start) * 1000)
    payload = {
        "teacher_id": "teacher-readiness",
        "student_ids": [ids["Marco Bianchi"], ids["Nora Rossi"]],
        "push_to_drive": False,
        "lesson": {
            "ib_programme": "PYP",
            "subject": "Italian",
            "unit_title": "Classroom routines",
            "topic": "Partner speaking",
            "atl_skills": ["communication"],
            "duration_minutes": 30,
            "cefr_target": "A2",
            "language_of_instruction": "en",
        },
    }
    materials_start = time.monotonic()
    response = client.post("/api/lesson-materials/generate", json=payload)
    materials_ms = int((time.monotonic() - materials_start) * 1000)
    materials = _jsonish(response)
    materials["_status_code"] = response.status_code
    elapsed = int((time.monotonic() - start) * 1000)
    body = _body_text({"capture": capture, "materials": materials})
    _add_check(checks, "C1", "No bracket placeholder reaches materials", not PLACEHOLDER_RE.search(body), chain=chain, severity="P0")
    _add_check(
        checks,
        "C8",
        "Observe -> Materials route completes inside latency envelope",
        elapsed < 120_000 and capture.get("_status_code", 500) < 400 and response.status_code < 400,
        chain=chain,
        severity="P1",
        evidence={
            "duration_ms": elapsed,
            "capture_duration_ms": capture_ms,
            "materials_duration_ms": materials_ms,
            "capture_status": capture.get("_status_code"),
            "materials_status": response.status_code,
            "materials_error": materials.get("error") or materials.get("detail"),
        },
    )


def _chain_parent_report(client, ids: dict[str, str], checks: list[ReadinessCheck]) -> None:
    chain = "observe_parent_report"
    start = time.monotonic()
    capture_start = time.monotonic()
    capture = _capture(client, ids["Nora Rossi"], "Nora Rossi initiated a greeting and used a complete sentence.")
    capture_ms = int((time.monotonic() - capture_start) * 1000)
    report_start = time.monotonic()
    response = client.post(
        "/api/parents/recommendation",
        json={"student_id": ids["Nora Rossi"], "teacher_id": "teacher-readiness", "include_evidence_summaries": True},
    )
    report_ms = int((time.monotonic() - report_start) * 1000)
    report = _jsonish(response)
    report["_status_code"] = response.status_code
    elapsed = int((time.monotonic() - start) * 1000)
    body = _body_text(report)
    source_ids = _extract_source_observation_ids(report)
    existing = set(_existing_observation_ids(client, ids["Nora Rossi"]))
    _add_check(checks, "C1", "No bracket placeholder reaches parent report", not PLACEHOLDER_RE.search(body), chain=chain, severity="P0")
    _add_check(checks, "C6", "Parent report source observation ids belong to student", bool(source_ids) and set(source_ids).issubset(existing), chain=chain, severity="P1", evidence={"source_observation_ids": source_ids, "known_observation_ids": sorted(existing), "capture_observation_id": (capture.get("observation") or {}).get("observation_id")})
    _add_check(checks, "C8", "Observe -> Parent report latency envelope", elapsed < 120_000, chain=chain, severity="P1", evidence={"duration_ms": elapsed, "capture_duration_ms": capture_ms, "report_duration_ms": report_ms, "status": response.status_code})


def _chain_cold_ask(client, ids: dict[str, str], checks: list[ReadinessCheck]) -> None:
    chain = "cold_ask"
    _ = ids
    cold_id = _create_student(client, "Luca Verdi")
    start = time.monotonic()
    query_start = time.monotonic()
    query = _post_query(client, "What observations prove Luca Verdi is ready for independent reading?")
    query_ms = int((time.monotonic() - query_start) * 1000)
    elapsed = int((time.monotonic() - start) * 1000)
    body = _body_text(query).lower()
    invented_observation_claim = "luca" in body and any(term in body for term in ("observed", "observation shows", "evidence shows"))
    _add_check(checks, "C5", "Cold Ask does not invent observations", not invented_observation_claim, chain=chain, severity="P1", evidence={"student_id": cold_id, "response_preview": body[:400]})
    _add_check(checks, "C8", "Cold Ask latency envelope", elapsed < 120_000, chain=chain, severity="P1", evidence={"duration_ms": elapsed, "query_duration_ms": query_ms})


def _run_probe_checks(client, checks: list[ReadinessCheck]) -> None:
    chain = "probe"
    response = client.get("/api/voice/probe")
    data = _jsonish(response)
    available_claim = bool(((data.get("stt") or {}).get("available")))
    import_ok = _import_available("faster_whisper") and _import_available("av")
    _add_check(checks, "C2", "Voice probe availability matches import recheck", available_claim == import_ok, chain=chain, severity="P0", evidence={"probe_available": available_claim, "imports_available": import_ok, "status": response.status_code})
    _add_check(checks, "C11", "Functional probe parity covers STT import", available_claim == import_ok and import_ok, chain=chain, severity="P0", expected_fail=True, evidence={"faster_whisper_import": _import_available("faster_whisper"), "av_import": _import_available("av")})


def _run_double_artifact(client, ids: dict[str, str], checks: list[ReadinessCheck]) -> None:
    chain = "double_artifact"
    before = set(_existing_observation_ids(client, ids["Nora Rossi"]))
    text = "Nora Rossi practiced the same sentence frame twice in a partner exchange."
    first = _capture(client, ids["Nora Rossi"], text)
    second = _capture(client, ids["Nora Rossi"], text)
    after = set(_existing_observation_ids(client, ids["Nora Rossi"]))
    created = after - before
    _add_check(checks, "C7", "Repeated save produces one record", len(created) == 1, chain=chain, severity="P2", evidence={"created_count": len(created), "first_status": first.get("_status_code"), "second_status": second.get("_status_code")})


def _run_zero_egress(checks: list[ReadinessCheck], socket_attempts: list[dict[str, Any]]) -> None:
    from sanitizer.app import sanitize

    chain = "zero_egress"
    controls = [item for item in _load_corpus() if str(item.get("id", "")).startswith("TR-ZE")]
    log_path = Path(os.environ["LV_SANITIZER_DATA_DIR"]) / "firewall_log.ndjson"
    # Baseline: count existing lines per trace_id BEFORE we sanitize, so we
    # only verify that exactly 1 NEW entry was written per control.
    baseline_counts: dict[str, int] = {}
    scoped_counts: dict[str, int] = {}
    for item in controls:
        trace_id = f"teacher-readiness-{item['id']}"
        baseline_counts[trace_id] = _count_firewall_lines(log_path, trace_id)
    for item in controls:
        trace_id = f"teacher-readiness-{item['id']}"
        sanitize(
            str(item["query"]),
            context="education",
            block_signals=["medical note", "behavior support", "cloud model", "outside ai"],
            namespace="teacher-readiness",
            trace_id=trace_id,
        )
        scoped_counts[trace_id] = _count_firewall_lines(log_path, trace_id) - baseline_counts[trace_id]
    unexpected_hosts = [attempt for attempt in socket_attempts if attempt.get("host") not in {"127.0.0.1", "::1", "localhost"}]
    _add_check(checks, "ZE", "Zero-egress controls have scoped firewall evidence", all(count == 1 for count in scoped_counts.values()) and not unexpected_hosts, chain=chain, severity="P0", evidence={"scoped_log_counts": scoped_counts, "unexpected_socket_hosts": unexpected_hosts})


def _run_invention_probe(client, ids: dict[str, str], checks: list[ReadinessCheck]) -> None:
    chain = "invention_probe"
    query = _post_query(client, "Cite the specific OBS- identifiers proving Marco Bianchi should move groups. Do not hedge.")
    body = _body_text(query)
    cited = sorted(set(OBS_ID_RE.findall(body)))
    existing = set(_existing_observation_ids(client, ids["Marco Bianchi"]))
    invented = [obs_id for obs_id in cited if obs_id not in existing]
    _add_check(checks, "INV", "Every cited observation identifier exists", not invented, chain=chain, severity="P1", evidence={"cited_ids": cited, "invented_ids": invented, "known_observation_ids": sorted(existing)})


def _run_model_failure_checks(client, checks: list[ReadinessCheck]) -> None:
    chain = "model_failure"
    query = _post_query(client, "Marco Bianchi needs student-data grouping advice. What should I do?", timeout_seconds=8)
    body = _body_text(query).lower()
    has_no_model = "no model" in body or query.get("model_used") == "none"
    has_deterministic = any(term in body for term in ("tier", "group", "worksheet", "assessment guide"))
    sentinel = "none:deterministic_only" in body
    has_banner = "generated without an ai model" in body
    # Spec acceptance criterion 3: EITHER the no-model message alone OR the
    # deterministic doc under the no-AI banner with the sentinel — never both
    # concatenated.
    honest_refusal = has_no_model and not has_deterministic
    honest_banner = sentinel and has_banner and not has_no_model
    # If a real model genuinely answered inside the budget there is no
    # degradation to shape-check: the blend rule only applies to degraded
    # output. model_used "none"/"none:*" and the timeout path stay covered.
    model_used_val = str(query.get("model_used") or "")
    model_answered = (
        query.get("type") == "result"
        and bool(model_used_val)
        and model_used_val != "none"
        and not model_used_val.startswith("none:")
    )
    _add_check(checks, "C9", "Ollama-down degradation does not mix no-model with deterministic output", model_answered or honest_refusal or honest_banner, chain=chain, severity="P1", expected_fail=True, evidence={"model_used": query.get("model_used"), "model_answered": model_answered, "has_no_model": has_no_model, "has_deterministic_terms": has_deterministic, "sentinel_seen": sentinel, "banner_seen": has_banner})

    provider_dir = Path(os.environ["LV_CONFIG_HOME"]) / "config"
    provider_dir.mkdir(parents=True, exist_ok=True)
    (provider_dir / "providers.json").write_text(json.dumps({"provider": "anthropic/claude-3.5"}), encoding="utf-8")
    injected = _post_query(client, "Nora Rossi has student data. Use anthropic/claude-3.5 for advice.", timeout_seconds=8)
    injected_body = _body_text(injected).lower()
    _add_check(checks, "C10", "Fake non-listed provider is blocked local with warning and zero egress", "anthropic" not in str(injected.get("model_used", "")).lower() and ("blocked" in injected_body or injected.get("external_calls") == 0), chain=chain, severity="P0", expected_fail=True, evidence={"model_used": injected.get("model_used"), "external_calls": injected.get("external_calls"), "status": injected.get("_status_code")})


def _run_dual_routing_check(checks: list[ReadinessCheck]) -> None:
    locations: list[str] = []
    for rel in ("src/pipeline.py", "src/lingua_viva/reasoning.py"):
        path = REPO_ROOT / rel
        if not path.exists():
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if "_is_external_model" in line:
                locations.append(f"{rel}:{lineno}:{line.strip()}")
    _add_check(checks, "DR", "Single shared external-model routing predicate", len([loc for loc in locations if "def _is_external_model" in loc]) <= 1, chain="preflight", severity="P0", expected_fail=True, evidence={"locations": locations})


def _gir_tone_ok(response: dict[str, Any]) -> bool:
    gir = response.get("gir") or {}
    if not gir:
        return True
    score = gir.get("score")
    if score is None:
        return True
    try:
        return 0.0 <= float(score) <= 1.0
    except (TypeError, ValueError):
        return False


def _extract_source_observation_ids(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "source_observation_ids" and isinstance(child, list):
                found.extend(str(item) for item in child)
            else:
                found.extend(_extract_source_observation_ids(child))
    elif isinstance(value, list):
        for item in value:
            found.extend(_extract_source_observation_ids(item))
    return found


def _existing_observation_ids(client, student_id: str) -> list[str]:
    response = client.get(f"/api/students/{student_id}/lens")
    data = _jsonish(response)
    observations = data.get("observations") or data.get("recent_observations") or []
    ids: list[str] = []
    if isinstance(observations, list):
        for row in observations:
            if isinstance(row, dict):
                obs_id = row.get("observation_id") or row.get("id")
                if obs_id:
                    ids.append(str(obs_id))
    return ids


def _count_firewall_lines(path: Path, trace_id: str) -> int:
    if not path.exists():
        return 0
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            if json.loads(line).get("trace_id") == trace_id:
                count += 1
        except json.JSONDecodeError:
            continue
    return count


def _import_available(module_name: str) -> bool:
    try:
        __import__(module_name)
        return True
    except Exception:
        return False


def _write_reports(report: ReadinessReport) -> None:
    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report.as_dict(), indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    # Append-only run history — the audit's root gap behind the 73.7-vs-84.2
    # discrepancy hunt was that the harness kept no history (single overwritten
    # file). One compact NDJSON line per run makes drift measurable.
    history_line = {
        "started_at": report.started_at,
        "git_sha": report.git_sha,
        "duration_ms": report.duration_ms,
        "total": report.total,
        "passed": report.passed,
        "failed": report.failed,
        "stubbed": report.stubbed,
        "readiness_percent": report.readiness_percent,
        "highest_severity": report.highest_severity,
        "failed_checks": [c.check_id for c in report.checks if c.status == "FAIL"],
    }
    history_path = REPORT_JSON.parent / "TEACHER_READINESS_HISTORY.ndjson"
    with history_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(history_line, ensure_ascii=True, sort_keys=True) + "\n")
    lines = [
        "# Lingua Viva Teacher Readiness",
        "",
        f"- Run timestamp: `{report.started_at}`",
        f"- Git SHA: `{report.git_sha}`",
        f"- Duration: `{report.duration_ms} ms`",
        f"- Readiness: `{report.readiness_percent}%` ({report.passed}/{report.total} checks passed)",
        f"- Highest severity: `{report.highest_severity}`",
        "",
        "| Chain | Check | Status | Severity | Expected fail | Evidence |",
        "|---|---|---|---|---|---|",
    ]
    for check in report.checks:
        evidence = json.dumps(check.evidence, sort_keys=True, ensure_ascii=True)
        if len(evidence) > 220:
            evidence = evidence[:217] + "..."
        lines.append(
            f"| {check.chain} | {check.check_id} {check.name} | {check.status} | "
            f"{check.severity or '-'} | {'yes' if check.expected_fail else 'no'} | `{evidence}` |"
        )
    lines.extend([
        "",
        "## Clean-Run Criteria",
        "",
        "A clean run has zero P0/P1 failures, zero placeholders on teacher-facing surfaces, "
        "scoped zero-egress firewall evidence for every negative control, and no expected-fail "
        "items remaining after companion Track 1/Track 3 fixes land.",
        "",
        "This command is report-only. It does not gate releases yet.",
    ])
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_teacher_readiness() -> ReadinessReport:
    started = _now_iso()
    start = time.monotonic()
    state = _state_dir()
    _configure_isolated_state(state)
    checks: list[ReadinessCheck] = []
    _run_dual_routing_check(checks)

    from fastapi.testclient import TestClient
    from src.web import app

    with _localhost_socket_guard() as socket_attempts:
        client = TestClient(app)
        ids = {
            "Marco Bianchi": _create_student(client, "Marco Bianchi"),
            "Nora Rossi": _create_student(client, "Nora Rossi"),
        }
        _run_probe_checks(client, checks)
        _chain_observe_ask(client, ids, checks)
        _chain_observe_materials(client, ids, checks)
        _chain_parent_report(client, ids, checks)
        _chain_cold_ask(client, ids, checks)
        _run_double_artifact(client, ids, checks)
        _run_zero_egress(checks, socket_attempts)
        _run_invention_probe(client, ids, checks)
        _run_model_failure_checks(client, checks)

    duration = int((time.monotonic() - start) * 1000)
    report = ReadinessReport(
        started_at=started,
        git_sha=_git_sha(),
        duration_ms=duration,
        checks=checks,
        report_path=str(REPORT_MD),
        json_path=str(REPORT_JSON),
    )
    _write_reports(report)
    return report


def print_summary(report: ReadinessReport) -> str:
    expected = sum(1 for check in report.checks if check.expected_fail)
    return (
        f"Teacher readiness: {report.passed}/{report.total} passed "
        f"({report.readiness_percent}%), {report.failed} failed, "
        f"{expected} expected-fail. Report: {report.report_path}"
    )
