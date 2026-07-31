from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from src.lingua_viva.spec_status import (
    _topic_key,
    check_spec_status,
    discover_specs,
    parse_index,
    report_to_json,
    report_to_markdown,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _mini_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    _write(
        root / "dev" / "INDEX.md",
        """# dev/ Index

| Spec | Date | Status | Evidence |
|---|---|---|---|
| [SPEC_INDEXED](SPEC_INDEXED_2026-07-30.md) | 2026-07-30 | DRAFT | tests/test_indexed.py |
""",
    )
    _write(root / "src" / "web.py", 'from fastapi import FastAPI\napp = FastAPI()\n@app.post("/api/live")\nasync def live():\n    return {}\n')
    _write(root / "contracts" / "ROUTE_REACHABILITY.yaml", "reachable_from_ui: []\nintentionally_backend_only: []\n")
    _write(root / "contracts" / "UI_CONTRACT.yaml", "version: 3\nfiles:\n  - src/web.py\n")
    _write(root / "tests" / "test_ui_contract.py", "EXPECTED_VERSION = 3\n")
    return root


def test_discovers_specs_from_top_level_and_specs_dir(tmp_path):
    root = _mini_repo(tmp_path)
    _write(root / "dev" / "SPEC_TOP_2026-07-30.md", "# SPEC TOP\n\n**Status**: DRAFT\n")
    _write(root / "dev" / "specs" / "SPEC_NESTED_2026-07-30.md", "# SPEC NESTED\n\n**Status**: DRAFT\n")

    paths = {record.path for record in discover_specs(root)}

    assert "dev/SPEC_TOP_2026-07-30.md" in paths
    assert "dev/specs/SPEC_NESTED_2026-07-30.md" in paths


def test_parse_index_rows_into_status_and_evidence(tmp_path):
    root = _mini_repo(tmp_path)

    rows = parse_index(root / "dev" / "INDEX.md")

    row = rows["dev/SPEC_INDEXED_2026-07-30.md"]
    assert row["status"] == "DRAFT"
    assert "tests/test_indexed.py" in row["evidence"]


def test_missing_index_row_emits_warn(tmp_path):
    root = _mini_repo(tmp_path)
    _write(root / "dev" / "SPEC_MISSING_2026-07-30.md", "# SPEC MISSING\n\n**Status**: DRAFT\n")

    report = check_spec_status(root)

    assert any(f.code == "missing_index_entry" and f.severity == "warn" for f in report.findings)


def test_header_index_status_contradiction_emits_warn(tmp_path):
    root = _mini_repo(tmp_path)
    _write(
        root / "dev" / "INDEX.md",
        """| Spec | Date | Status | Evidence |
|---|---|---|---|
| [SPEC_INDEXED](SPEC_INDEXED_2026-07-30.md) | 2026-07-30 | SHIPPED | ok |
""",
    )
    _write(root / "dev" / "SPEC_INDEXED_2026-07-30.md", "# SPEC INDEXED\n\n**Status**: DRAFT\n")

    report = check_spec_status(root)

    assert any(f.code == "status_drift" and f.severity == "warn" for f in report.findings)


def test_built_spec_with_missing_concrete_source_file_emits_fail(tmp_path):
    root = _mini_repo(tmp_path)
    _write(
        root / "dev" / "SPEC_INDEXED_2026-07-30.md",
        "# SPEC INDEXED\n\n**Status**: BUILT\n\nUses `src/missing_module.py`.\n",
    )

    report = check_spec_status(root)

    assert any(f.code == "missing_claimed_file" and f.severity == "fail" for f in report.findings)


def test_draft_planned_create_file_does_not_fail(tmp_path):
    root = _mini_repo(tmp_path)
    _write(
        root / "dev" / "SPEC_INDEXED_2026-07-30.md",
        "# SPEC INDEXED\n\n**Status**: DRAFT\n\nCreate `src/future_module.py`.\n",
    )

    report = check_spec_status(root)

    assert not any(f.code == "missing_claimed_file" for f in report.findings)


def test_missing_concrete_test_claim_uses_status_severity(tmp_path):
    root = _mini_repo(tmp_path)
    _write(root / "dev" / "SPEC_INDEXED_2026-07-30.md", "# SPEC INDEXED\n\n**Status**: BUILT\n\nVerified by tests/test_missing.py.\n")

    report = check_spec_status(root)

    assert any(f.code == "missing_claimed_test" and f.severity == "fail" for f in report.findings)


def test_missing_prompt_pair_and_orphan_prompt_emit_warn(tmp_path):
    root = _mini_repo(tmp_path)
    _write(root / "dev" / "SPEC_LV_PAIRLESS_2026-07-30.md", "# Pairless\n\n**Status**: DRAFT\n")
    _write(root / "dev" / "PROMPT_LV_ORPHAN_BUILD_2026-07-30.md", "# Orphan prompt\n")

    report = check_spec_status(root)

    assert any(f.code == "missing_spec_prompt_pair" and f.severity == "warn" for f in report.findings)
    assert any(f.code == "orphan_prompt" and f.severity == "warn" for f in report.findings)


def test_existing_route_missing_from_reachability_manifest_emits_warn(tmp_path):
    root = _mini_repo(tmp_path)
    _write(root / "dev" / "SPEC_INDEXED_2026-07-30.md", "# SPEC INDEXED\n\n**Status**: BUILT\n\nRoute: POST /api/live\n")

    report = check_spec_status(root)

    assert any(f.code == "route_contract_gap" and f.severity == "warn" for f in report.findings)


def test_report_json_and_markdown_include_summary_and_codes(tmp_path):
    root = _mini_repo(tmp_path)
    _write(root / "dev" / "SPEC_MISSING_2026-07-30.md", "# Missing\n\n**Status**: DRAFT\n")
    report = check_spec_status(root)

    payload = report_to_json(report)
    markdown = report_to_markdown(report)

    assert "summary" in payload
    assert "missing_index_entry" in payload["summary"]["codes"]
    assert "## Summary" in markdown
    assert "missing_index_entry" in markdown


def test_cli_exit_behavior_default_vs_strict(tmp_path):
    root = _mini_repo(tmp_path)
    _write(root / "dev" / "SPEC_WARN_2026-07-30.md", "# Warn\n\n**Status**: DRAFT\n")

    default = subprocess.run(
        [sys.executable, "-m", "src.lingua_viva.spec_status", "--root", str(root), "--json"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
    )
    strict = subprocess.run(
        [sys.executable, "-m", "src.lingua_viva.spec_status", "--root", str(root), "--strict"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
    )

    assert default.returncode == 0
    assert strict.returncode == 1


def test_topic_key_pairs_common_build_suffixes():
    spec = Path("dev/SPEC_LV_COHORT_LESSON_PLANNING_WORKFLOW_2026-07-30.md")
    prompt = Path("dev/PROMPT_LV_COHORT_LESSON_PLANNING_BUILD_2026-07-30.md")
    loop_spec = Path("dev/SPEC_LV_GIR_VOICE_HARDENING_LOOP_2026-07-30.md")
    loop_prompt = Path("dev/PROMPT_LV_GIR_VOICE_HARDENING_BUILD_2026-07-30.md")

    assert _topic_key(spec) == _topic_key(prompt)
    assert _topic_key(loop_spec) == _topic_key(loop_prompt)


def test_checker_does_not_mutate_inputs(tmp_path):
    root = _mini_repo(tmp_path)
    _write(root / "dev" / "SPEC_WARN_2026-07-30.md", "# Warn\n\n**Status**: DRAFT\n")
    watched = [
        root / "dev" / "INDEX.md",
        root / "dev" / "SPEC_WARN_2026-07-30.md",
        root / "contracts" / "ROUTE_REACHABILITY.yaml",
        root / "tests" / "test_ui_contract.py",
    ]
    before = {path: path.read_text(encoding="utf-8") for path in watched}

    check_spec_status(root)

    after = {path: path.read_text(encoding="utf-8") for path in watched}
    assert after == before
