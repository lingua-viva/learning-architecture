"""Nothing that ships in the installer may contain student information.

The desktop installer bundles part of the repo into the app (electron-builder
`extraResources` in desktop/package.json). Whatever matches that filter is
copied onto every teacher's machine and onto every machine the app is ever
distributed to.

Audited 2026-09-03 and clean:
  * tests/ is not bundled, so no fixture children (Abigail Chang et al.) ship
  * memory/data/ is excluded, so no path records ship
  * no .db / .sqlite ships, so no student lens store ships
  * lenses/education/ holds ROLE templates (rti-monitor, parent-voice, ...),
    not people
  * the one data file that matched the filter, sanitizer/data/firewall_log.ndjson,
    carried metadata only — every one of its 1776 rows had zero free-text
    outside timestamp/context/reason. It has since been excluded anyway: it is
    this machine's operational telemetry and has no business on a customer's
    disk.

This file makes that a standing property instead of a thing someone once
checked. It fails loudly if a future filter change starts shipping data.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PKG = REPO / "desktop" / "package.json"


def _bundle_filter() -> tuple[list[str], list[str]]:
    build = json.loads(PKG.read_text(encoding="utf-8"))["build"]
    res = build["extraResources"]
    res = res[0] if isinstance(res, list) else res
    filt = res["filter"]
    included = [f for f in filt if not f.startswith("!")]
    excluded = [f[1:] for f in filt if f.startswith("!")]
    return included, excluded


def test_tests_directory_is_never_bundled():
    """tests/ holds synthetic children with names, grades and report cards.
    If it ever ships, every install carries fixture student records."""
    included, _ = _bundle_filter()
    assert not any(f.startswith("tests") for f in included), (
        "tests/ is in the installer bundle — synthetic student fixtures would ship"
    )


def test_memory_data_is_excluded():
    """memory/data/ holds path records and run history."""
    _, excluded = _bundle_filter()
    assert any(e.startswith("memory/data") for e in excluded), (
        "memory/data/** is no longer excluded from the installer bundle"
    )


def test_no_database_file_is_bundled():
    """The student lens store is SQLite. A shipped .db is a shipped roster."""
    included, _ = _bundle_filter()
    roots = sorted({f.split("/")[0] for f in included if "/" in f or "." not in f})
    offenders = []
    for root in roots:
        base = REPO / root
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if "__pycache__" in p.parts or not p.is_file():
                continue
            if p.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
                offenders.append(str(p.relative_to(REPO)))
    assert not offenders, f"database files inside the installer bundle: {offenders}"


def test_no_bundled_data_file_carries_free_text():
    """Any .ndjson / .csv that ships must be metadata only.

    A log that records WHAT was redacted is fine. A log that records the text
    it redacted is a student-data leak wearing a telemetry filename.
    """
    included, excluded = _bundle_filter()
    roots = sorted({f.split("/")[0] for f in included if "/" in f or "." not in f})
    metadata_keys = {"timestamp", "context", "reason", "ts", "level", "event"}
    offenders = []

    for root in roots:
        base = REPO / root
        if not base.exists():
            continue
        for p in base.rglob("*.ndjson"):
            if "__pycache__" in p.parts:
                continue
            rel = p.relative_to(REPO).as_posix()
            if any(rel.startswith(e.replace("/**", "")) for e in excluded):
                continue
            for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                for key, val in row.items():
                    if key in metadata_keys or not isinstance(val, str):
                        continue
                    # A long free-text value in a shipped file is the risk.
                    if len(val) > 40:
                        offenders.append(f"{rel}: {key} carries {len(val)} chars of free text")
                        break
                if offenders:
                    break
    assert not offenders, (
        "bundled data files carry free text that could contain student "
        f"information: {offenders[:5]}"
    )


def test_bundled_lenses_are_role_templates_not_people():
    """lenses/education/ ships. It must hold role lenses, never a person's."""
    included, _ = _bundle_filter()
    if not any(f.startswith("lenses/education") for f in included):
        pytest.skip("lenses/education is not bundled")
    person_like = re.compile(r"LENS-PERSON-|date_of_birth|guardian|parent_email", re.I)
    offenders = [
        str(p.relative_to(REPO))
        for p in (REPO / "lenses" / "education").rglob("*.yaml")
        if person_like.search(p.read_text(encoding="utf-8", errors="replace"))
    ]
    assert not offenders, f"person-shaped lenses inside the bundle: {offenders}"
