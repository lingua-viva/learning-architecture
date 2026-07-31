from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SEVERITIES = ("info", "warn", "fail")
BUILT_STATUSES = ("built", "shipped", "built + hardened")
DRAFT_STATUSES = ("draft", "approved", "approved for build", "triage")
FINDING_CODES = (
    "missing_index_entry",
    "status_drift",
    "missing_claimed_file",
    "missing_claimed_test",
    "missing_spec_prompt_pair",
    "orphan_prompt",
    "route_contract_gap",
    "ui_contract_evidence_gap",
    "malformed_index",
)

FILE_REF_RE = re.compile(
    r"\b(?:src|tests|contracts|scripts|static|dev/reports)/[A-Za-z0-9_./{}-]+"
)
ROUTE_RE = re.compile(r"\b(GET|POST|PUT|DELETE)\s+(/api/[A-Za-z0-9_./{}-]+)")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
FENCE_RE = re.compile(r"```.*?```", re.DOTALL)


@dataclass
class SpecRecord:
    path: str
    title: str
    date: str
    header_status: str
    indexed: bool
    index_status: str
    claimed_files: list[str] = field(default_factory=list)
    claimed_tests: list[str] = field(default_factory=list)
    claimed_routes: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class SpecStatusFinding:
    severity: str
    code: str
    spec_path: str
    message: str
    evidence: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.severity not in SEVERITIES:
            self.severity = "warn"
        if self.code not in FINDING_CODES:
            self.code = "malformed_index"

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class SpecStatusReport:
    generated_at: str
    spec_count: int
    indexed_count: int
    findings: list[SpecStatusFinding] = field(default_factory=list)
    summary: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        data = asdict(self)
        data["findings"] = [finding.as_dict() for finding in self.findings]
        return data


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _strip_fenced_code(text: str) -> str:
    return FENCE_RE.sub("", text)


def _metadata_value(text: str, key: str) -> str:
    match = re.search(rf"^\s*\*\*{re.escape(key)}\*\*\s*:\s*(.+)$", text, flags=re.M)
    if match:
        return match.group(1).strip()
    match = re.search(rf"^\s*{re.escape(key)}\s*:\s*(.+)$", text, flags=re.M | re.I)
    return match.group(1).strip() if match else ""


def _title(text: str, fallback: str) -> str:
    match = re.search(r"^\s*#\s+(.+)$", text, flags=re.M)
    return match.group(1).strip() if match else fallback


def _date_from(path: Path, text: str) -> str:
    explicit = _metadata_value(text, "Date")
    if explicit:
        return explicit
    match = DATE_RE.search(path.name)
    return match.group(0) if match else ""


def _clean_ref(ref: str) -> str:
    return ref.rstrip("`'\"),.;:]}")


def _file_refs(text: str) -> list[str]:
    cleaned = _strip_fenced_code(text)
    refs = {_clean_ref(match.group(0)) for match in FILE_REF_RE.finditer(cleaned)}
    return sorted(
        ref for ref in refs
        if ref and (ref.endswith("/") or Path(ref).suffix)
    )


def _routes(text: str) -> list[str]:
    return sorted({f"{method} {_clean_ref(route)}" for method, route in ROUTE_RE.findall(text)})


def _is_status_built(status: str) -> bool:
    status_l = status.lower()
    if "unbuilt" in status_l or "not built" in status_l:
        return False
    return any(marker in status_l for marker in BUILT_STATUSES)


def _is_status_draft(status: str) -> bool:
    status_l = status.lower()
    return any(marker in status_l for marker in DRAFT_STATUSES)


def _planned_target_context(text: str, ref: str) -> bool:
    idx = text.find(ref)
    if idx < 0:
        return False
    context = text[max(0, idx - 100): idx + len(ref) + 80].lower()
    return any(word in context for word in ("create", "add", "build", "recommended", "planned", "future", "should generate"))


def _normalize_index_path(path: str) -> str:
    path = path.strip().strip("`")
    if not path:
        return ""
    if path.startswith("../dev/"):
        path = path.removeprefix("../")
    elif path.startswith("../"):
        path = path.removeprefix("../")
    elif path.startswith("specs/"):
        path = f"dev/{path}"
    elif not path.startswith("dev/"):
        path = f"dev/{path}"
    return path


def _topic_key(path: Path) -> tuple[str, str]:
    stem = path.stem.lower()
    stem = re.sub(r"^(spec|prompt)_", "", stem)
    stem = re.sub(r"^lv_", "", stem)
    stem = re.sub(r"_build_", "_", stem)
    stem = stem.replace("_build", "")
    date = DATE_RE.search(stem)
    date_text = date.group(0) if date else ""
    stem = DATE_RE.sub("", stem)
    stem = re.sub(r"_+", "_", stem).strip("_-")
    return stem, date_text


def parse_index(index_path: Path | None = None) -> dict:
    root = (index_path.parent.parent if index_path else REPO_ROOT).resolve()
    path = index_path or root / "dev" / "INDEX.md"
    if not path.exists():
        return {"__errors__": [f"missing index: {_rel(path, root)}"]}
    rows: dict[str, dict] = {}
    errors: list[str] = []
    for line_no, line in enumerate(_read(path).splitlines(), start=1):
        line = line.strip()
        if not (line.startswith("|") and line.endswith("|")):
            continue
        if re.match(r"^\|\s*-+\s*\|", line):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if not cells or cells[0].lower() in {"spec", "doc", "report", "handoff"}:
            continue
        link = re.search(r"\[([^\]]+)\]\(([^)]+)\)", cells[0])
        if not link:
            continue
        normalized = _normalize_index_path(link.group(2))
        status = cells[2] if len(cells) >= 4 else ""
        evidence = cells[3] if len(cells) >= 4 else cells[-1] if cells else ""
        rows[normalized] = {
            "title": link.group(1),
            "path": normalized,
            "date": cells[1] if len(cells) > 1 else "",
            "status": status,
            "evidence": evidence,
            "line": line_no,
            "raw": line,
        }
    if errors:
        rows["__errors__"] = errors
    return rows


def _index_match(record_path: str, index: dict) -> dict:
    candidates = [
        record_path,
        record_path.removeprefix("dev/"),
        f"dev/{Path(record_path).name}",
        Path(record_path).name,
    ]
    for candidate in candidates:
        normalized = _normalize_index_path(candidate)
        if normalized in index:
            return index[normalized]
    filename = Path(record_path).name
    for row in index.values():
        if isinstance(row, dict) and Path(str(row.get("path") or "")).name == filename:
            return row
    return {}


def discover_specs(root: Path | None = None) -> list[SpecRecord]:
    root = (root or REPO_ROOT).resolve()
    index = parse_index(root / "dev" / "INDEX.md")
    spec_paths = sorted(
        path for path in (
            set((root / "dev").glob("*SPEC*.md")) | set((root / "dev" / "specs").glob("*SPEC*.md"))
        )
        if "PROMPT" not in path.name
    )
    records: list[SpecRecord] = []
    for path in spec_paths:
        text = _read(path)
        rel_path = _rel(path, root)
        index_row = _index_match(rel_path, index)
        files = _file_refs(text)
        records.append(
            SpecRecord(
                path=rel_path,
                title=_title(text, path.stem),
                date=_date_from(path, text),
                header_status=_metadata_value(text, "Status"),
                indexed=bool(index_row),
                index_status=str(index_row.get("status") or "") if index_row else "",
                claimed_files=files,
                claimed_tests=[ref for ref in files if ref.startswith("tests/")],
                claimed_routes=_routes(text),
                evidence_refs=[ref for ref in files if ref.startswith("dev/reports/")],
            )
        )
    return records


def _all_prompt_paths(root: Path) -> list[Path]:
    return sorted((root / "dev").glob("*PROMPT*.md"))


def _route_manifest_routes(root: Path) -> set[str]:
    path = root / "contracts" / "ROUTE_REACHABILITY.yaml"
    if not path.exists():
        return set()
    text = _read(path)
    return set(re.findall(r'route:\s*"([^"]+)"', text))


def _web_routes(root: Path) -> set[str]:
    path = root / "src" / "web.py"
    if not path.exists():
        return set()
    text = _read(path)
    routes = set()
    for method, route in re.findall(r'@app\.(get|post|put|delete)\(\s*"([^"]+)"', text):
        routes.add(f"{method.upper()} {route}")
    return routes


def _ui_contract_versions(root: Path) -> tuple[int | None, int | None]:
    contract_path = root / "contracts" / "UI_CONTRACT.yaml"
    test_path = root / "tests" / "test_ui_contract.py"
    contract_version = None
    expected_version = None
    if contract_path.exists():
        match = re.search(r"^version:\s*(\d+)", _read(contract_path), flags=re.M)
        contract_version = int(match.group(1)) if match else None
    if test_path.exists():
        match = re.search(r"EXPECTED_VERSION\s*=\s*(\d+)", _read(test_path))
        expected_version = int(match.group(1)) if match else None
    return contract_version, expected_version


def _finding(severity: str, code: str, spec_path: str, message: str, evidence: dict | None = None) -> SpecStatusFinding:
    return SpecStatusFinding(severity, code, spec_path, message, evidence or {})


def _status_findings(record: SpecRecord) -> list[SpecStatusFinding]:
    findings: list[SpecStatusFinding] = []
    header = record.header_status
    index_status = record.index_status
    if not header:
        findings.append(_finding("warn", "status_drift", record.path, "Spec has no Status metadata header."))
        return findings
    if "see index" in header.lower():
        findings.append(_finding("info", "status_drift", record.path, "Spec delegates status to dev/INDEX.md."))
        return findings
    if header and index_status:
        if _is_status_draft(header) and _is_status_built(index_status):
            findings.append(_finding("warn", "status_drift", record.path, "Spec header is draft-like but index is built/shipped.", {"header_status": header, "index_status": index_status}))
        elif _is_status_built(header) and _is_status_draft(index_status):
            findings.append(_finding("warn", "status_drift", record.path, "Spec header is built/shipped but index is draft-like.", {"header_status": header, "index_status": index_status}))
    return findings


def check_spec_status(root: Path | None = None) -> SpecStatusReport:
    root = (root or REPO_ROOT).resolve()
    index = parse_index(root / "dev" / "INDEX.md")
    records = discover_specs(root)
    findings: list[SpecStatusFinding] = []
    for error in index.get("__errors__", []):
        findings.append(_finding("fail", "malformed_index", "dev/INDEX.md", error))

    web_routes = _web_routes(root)
    manifest_routes = _route_manifest_routes(root)
    prompt_paths = _all_prompt_paths(root)
    prompt_keys = {_topic_key(path): path for path in prompt_paths}
    spec_keys = {_topic_key(root / record.path): record for record in records}
    contract_version, expected_version = _ui_contract_versions(root)

    for record in records:
        spec_file = root / record.path
        text = _read(spec_file)
        if not record.indexed:
            findings.append(_finding("warn", "missing_index_entry", record.path, "Spec is not listed in dev/INDEX.md."))
        findings.extend(_status_findings(record))
        built = _is_status_built(record.header_status) or _is_status_built(record.index_status)
        for ref in record.claimed_files:
            if _planned_target_context(text, ref) and _is_status_draft(record.header_status or record.index_status):
                continue
            if not (root / ref).exists():
                code = "missing_claimed_test" if ref.startswith("tests/") else "missing_claimed_file"
                severity = "fail" if built else "warn"
                findings.append(_finding(severity, code, record.path, f"Claimed file does not exist: {ref}", {"ref": ref}))
        key = _topic_key(spec_file)
        if spec_file.parent == root / "dev" and key not in prompt_keys:
            findings.append(_finding("warn", "missing_spec_prompt_pair", record.path, "Top-level spec has no matching build prompt.", {"topic_key": key[0], "date": key[1]}))
        for route in record.claimed_routes:
            if route in web_routes and route not in manifest_routes:
                findings.append(_finding("warn", "route_contract_gap", record.path, f"Route exists but is absent from ROUTE_REACHABILITY.yaml: {route}", {"route": route}))
        protected_mentions = any(ref in text for ref in ("src/web.py", "static/index.html", "static/sw.js"))
        if built and protected_mentions and contract_version != expected_version:
            findings.append(_finding("warn", "ui_contract_evidence_gap", record.path, "UI contract version and test expected version disagree.", {"contract_version": contract_version, "expected_version": expected_version}))

    for path in prompt_paths:
        key = _topic_key(path)
        if key not in spec_keys:
            findings.append(_finding("warn", "orphan_prompt", _rel(path, root), "Prompt has no matching spec.", {"topic_key": key[0], "date": key[1]}))

    summary = {
        "info": sum(1 for finding in findings if finding.severity == "info"),
        "warn": sum(1 for finding in findings if finding.severity == "warn"),
        "fail": sum(1 for finding in findings if finding.severity == "fail"),
        "codes": {},
    }
    for finding in findings:
        summary["codes"][finding.code] = summary["codes"].get(finding.code, 0) + 1
    return SpecStatusReport(
        generated_at=_now_iso(),
        spec_count=len(records),
        indexed_count=sum(1 for record in records if record.indexed),
        findings=findings,
        summary=summary,
    )


def report_to_json(report: SpecStatusReport) -> dict:
    return report.as_dict()


def report_to_markdown(report: SpecStatusReport) -> str:
    lines = [
        "# Spec Status Drift Report",
        "",
        f"Generated: {report.generated_at}",
        f"Specs: {report.spec_count} ({report.indexed_count} indexed)",
        f"Findings: {len(report.findings)}",
        "",
        "## Summary",
    ]
    for severity in SEVERITIES:
        lines.append(f"- {severity}: {report.summary.get(severity, 0)}")
    if report.findings:
        lines.append("")
        lines.append("## Findings")
        for finding in report.findings:
            lines.append(f"- **{finding.severity}** `{finding.code}` {finding.spec_path}: {finding.message}")
    return "\n".join(lines)


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report Lingua Viva spec/status drift.")
    parser.add_argument("--json", action="store_true", help="Print JSON report.")
    parser.add_argument("--markdown", action="store_true", help="Print Markdown report.")
    parser.add_argument("--strict", action="store_true", help="Exit 1 when warn or fail findings exist.")
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="Repository root to scan.")
    args = parser.parse_args(argv)
    report = check_spec_status(args.root)
    if args.json:
        print(json.dumps(report_to_json(report), sort_keys=True))
    else:
        print(report_to_markdown(report))
    if report.summary.get("fail", 0):
        return 1
    if args.strict and report.summary.get("warn", 0):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
