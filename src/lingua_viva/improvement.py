"""
Lingua Viva Improvement Circuit — MEASURE → ANALYZE → VERIFY

SPEC: dev/SPEC_LV_IMPROVEMENT_CIRCUIT_2026-08-24.md
Adapted from Mission Canvas improvement_circuit.py (5-station model).

Stations:
  MEASURE — run all eval lanes, produce a snapshot
  ANALYZE — rank weaknesses by leverage, assign fix classes
  VERIFY  — re-run MEASURE, diff against baseline, detect regressions

No LLM calls. Pure subprocess + parsing. Local computation only.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _improvement_dir() -> Path:
    home = Path(os.environ.get("LV_STATE_HOME", Path.home() / ".lingua-viva"))
    d = home / "improvement"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _baseline_path() -> Path:
    return _improvement_dir() / "baseline.json"


def _journal_path() -> Path:
    return _improvement_dir() / "journal.ndjson"


_REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------

@dataclass
class ImprovementSnapshot:
    timestamp: str
    gauntlet_pass: int
    gauntlet_fail: int
    gauntlet_error: int
    gauntlet_total: int
    gauntlet_failures: list = field(default_factory=list)
    unit_pass: int = 0
    unit_fail: int = 0
    unit_total: int = 0
    unit_failures: list = field(default_factory=list)
    safety_pass: int = 0
    safety_fail: int = 0
    safety_checks: list = field(default_factory=list)
    schema_version_ok: bool = True
    snapshot_hash: str = ""

    def __post_init__(self):
        if not self.snapshot_hash:
            self.snapshot_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        data = {k: v for k, v in asdict(self).items() if k != "snapshot_hash"}
        blob = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ImprovementSnapshot":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# MEASURE — Station 1
# ---------------------------------------------------------------------------

def _parse_pytest_output(output: str) -> dict:
    """Parse pytest -q output into pass/fail/error counts and failure details."""
    lines = output.strip().splitlines()
    result = {"pass": 0, "fail": 0, "error": 0, "total": 0, "failures": []}

    # Find the summary line: "N passed", "N failed", "N error"
    for line in reversed(lines):
        if "passed" in line or "failed" in line or "error" in line:
            m_pass = re.search(r"(\d+) passed", line)
            m_fail = re.search(r"(\d+) failed", line)
            m_error = re.search(r"(\d+) error", line)
            if m_pass:
                result["pass"] = int(m_pass.group(1))
            if m_fail:
                result["fail"] = int(m_fail.group(1))
            if m_error:
                result["error"] = int(m_error.group(1))
            result["total"] = result["pass"] + result["fail"] + result["error"]
            break

    # Extract failure details from FAILED lines
    for line in lines:
        if line.startswith("FAILED "):
            # FAILED tests/path/test_file.py::test_name - ErrorType: message
            parts = line[7:].split(" - ", 1)
            test_id = parts[0].strip()
            error_summary = parts[1].strip() if len(parts) > 1 else "unknown error"
            result["failures"].append({
                "test_id": test_id,
                "error_summary": error_summary,
            })

    return result


def _run_pytest(args: list[str]) -> dict:
    """Run pytest with given args, return parsed results."""
    cmd = [sys.executable, "-m", "pytest", *args, "-q", "--tb=line", "--no-header"]  # not "python3": absent on Windows
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(_REPO_ROOT),
        )
        output = proc.stdout + "\n" + proc.stderr
    except subprocess.TimeoutExpired:
        return {"pass": 0, "fail": 0, "error": 1, "total": 1,
                "failures": [{"test_id": "timeout", "error_summary": "pytest timed out after 300s"}]}
    except Exception as e:
        return {"pass": 0, "fail": 0, "error": 1, "total": 1,
                "failures": [{"test_id": "subprocess", "error_summary": str(e)[:200]}]}
    return _parse_pytest_output(output)


def measure() -> ImprovementSnapshot:
    """Run all eval lanes and return a snapshot."""
    now = datetime.now(timezone.utc).isoformat()

    # Lane 1: Gauntlet
    gauntlet = _run_pytest(["tests/gauntlet/"])

    # Lane 2: Unit tests (non-gauntlet)
    unit = _run_pytest(["tests/", "--ignore=tests/gauntlet"])

    # Lane 3: Safety (document-to-lens safety tests)
    safety_args = ["tests/test_document_to_lens.py", "-q", "--tb=line", "--no-header"]
    safety = _run_pytest(["tests/test_document_to_lens.py"])

    return ImprovementSnapshot(
        timestamp=now,
        gauntlet_pass=gauntlet["pass"],
        gauntlet_fail=gauntlet["fail"],
        gauntlet_error=gauntlet["error"],
        gauntlet_total=gauntlet["total"],
        gauntlet_failures=gauntlet["failures"],
        unit_pass=unit["pass"],
        unit_fail=unit["fail"],
        unit_total=unit["total"],
        unit_failures=unit["failures"],
        safety_pass=safety["pass"],
        safety_fail=safety["fail"],
        safety_checks=["trauma_flag", "red_safeguarding", "cefr_extraction",
                        "student_matching", "extraction_persistence"],
    )


# ---------------------------------------------------------------------------
# VERIFY — Station 5
# ---------------------------------------------------------------------------

def persist_baseline(snapshot: ImprovementSnapshot) -> Path:
    """Save snapshot as the VERIFY baseline."""
    path = _baseline_path()
    path.write_text(json.dumps(snapshot.to_dict(), indent=2, default=str), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def load_baseline() -> Optional[ImprovementSnapshot]:
    """Load the persisted baseline, or None if no baseline exists."""
    path = _baseline_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return ImprovementSnapshot.from_dict(data)
    except (json.JSONDecodeError, TypeError, KeyError):
        return None


def snapshot_regressions(
    before: ImprovementSnapshot, after: ImprovementSnapshot
) -> list[str]:
    """Return list of regressions. Empty list = no regression."""
    regressions = []

    # Gauntlet regressions
    if after.gauntlet_fail > before.gauntlet_fail:
        before_fails = {f["test_id"] for f in before.gauntlet_failures}
        new_fails = [f for f in after.gauntlet_failures if f["test_id"] not in before_fails]
        for f in new_fails:
            regressions.append(f"GAUNTLET REGRESSION: {f['test_id']} — {f['error_summary']}")

    if after.gauntlet_error > before.gauntlet_error:
        regressions.append(
            f"GAUNTLET COLLECTION ERROR: {after.gauntlet_error} errors (was {before.gauntlet_error})"
        )

    # Unit test regressions
    if after.unit_fail > before.unit_fail:
        before_fails = {f["test_id"] for f in before.unit_failures}
        new_fails = [f for f in after.unit_failures if f["test_id"] not in before_fails]
        for f in new_fails:
            regressions.append(f"UNIT REGRESSION: {f['test_id']} — {f['error_summary']}")

    # Safety regressions
    if after.safety_fail > before.safety_fail:
        regressions.append(
            f"SAFETY REGRESSION: {after.safety_fail} failures (was {before.safety_fail})"
        )

    return regressions


def verify() -> list[str]:
    """Load baseline, run fresh MEASURE, compare. Returns regressions."""
    baseline = load_baseline()
    if baseline is None:
        return ["NO BASELINE: run persist_baseline(measure()) first"]

    fresh = measure()
    regressions = snapshot_regressions(baseline, fresh)

    if not regressions:
        # Update baseline to new clean state
        persist_baseline(fresh)

    # Always journal the verification
    append_journal("verify", baseline, fresh, regressions)

    return regressions


# ---------------------------------------------------------------------------
# Journal
# ---------------------------------------------------------------------------

def append_journal(
    action: str,
    before: ImprovementSnapshot,
    after: ImprovementSnapshot,
    regressions: Optional[list[str]] = None,
) -> Path:
    """Append one turn to the improvement journal (NDJSON, append-only)."""
    path = _journal_path()
    entry = {
        "turn_id": f"turn-{uuid.uuid4().hex[:12]}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "before": {
            "gauntlet": f"{before.gauntlet_pass}/{before.gauntlet_total}",
            "unit": f"{before.unit_pass}/{before.unit_total}",
            "safety": f"{before.safety_pass}/{before.safety_pass + before.safety_fail}",
        },
        "after": {
            "gauntlet": f"{after.gauntlet_pass}/{after.gauntlet_total}",
            "unit": f"{after.unit_pass}/{after.unit_total}",
            "safety": f"{after.safety_pass}/{after.safety_pass + after.safety_fail}",
        },
        "regressions": regressions or [],
        "verdict": "CLEAN" if not regressions else "REGRESSED",
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


# ---------------------------------------------------------------------------
# ANALYZE — Station 2
# ---------------------------------------------------------------------------

FIX_CLASSES = {
    "fix_missing_function": "Implement function that tests expect but doesn't exist",
    "fix_missing_fixture": "Create test fixture file that tests reference",
    "fix_broken_import": "Fix import referencing moved/renamed symbol",
    "fix_unwired_route": "Add UI fetch() for existing API route",
    "mark_internal_route": "Mark route as internal-only (not for UI)",
    "fix_safety_gap": "Add missing safety check in new code path",
    "fix_stale_test": "Update test to match refactored API",
    "add_test_coverage": "Add tests for untested code path",
}


def _classify_failure(failure: dict) -> str:
    """Determine fix_class from error type."""
    error = failure.get("error_summary", "")
    if "ImportError" in error or "cannot import" in error:
        return "fix_broken_import"
    if "FileNotFoundError" in error:
        return "fix_missing_fixture"
    if "AttributeError" in error and "has no attribute" in error:
        return "fix_missing_function"
    if "AssertionError" in error or "assert" in error.lower():
        return "fix_stale_test"
    return "add_test_coverage"


def analyze(snapshot: Optional[ImprovementSnapshot] = None) -> list[dict]:
    """Rank weaknesses by leverage. Returns ordered list of proposals."""
    if snapshot is None:
        snapshot = measure()

    weaknesses = []

    # Priority 1: Gauntlet failures (BLOCKER)
    for failure in snapshot.gauntlet_failures:
        weaknesses.append({
            "priority": 1,
            "signal": f"gauntlet_failure:{failure['test_id']}",
            "fix_class": _classify_failure(failure),
            "evidence": failure["error_summary"],
        })

    # Priority 2: Safety failures
    if snapshot.safety_fail > 0:
        weaknesses.append({
            "priority": 2,
            "signal": "safety_regression",
            "fix_class": "fix_safety_gap",
            "evidence": f"{snapshot.safety_fail} safety tests failing",
        })

    # Priority 3: Unit test failures
    for failure in snapshot.unit_failures:
        weaknesses.append({
            "priority": 3,
            "signal": f"unit_failure:{failure['test_id']}",
            "fix_class": _classify_failure(failure),
            "evidence": failure["error_summary"],
        })

    return sorted(weaknesses, key=lambda w: w["priority"])


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    import sys
    args = sys.argv[1:]

    if "--measure" in args:
        s = measure()
        path = persist_baseline(s)
        print(f"Gauntlet: {s.gauntlet_pass}/{s.gauntlet_total}")
        print(f"Unit: {s.unit_pass}/{s.unit_total}")
        print(f"Safety: {s.safety_pass}/{s.safety_pass + s.safety_fail}")
        print(f"Hash: {s.snapshot_hash[:16]}...")
        print(f"Baseline saved: {path}")

    elif "--verify" in args:
        regressions = verify()
        if regressions:
            print("REGRESSIONS DETECTED:")
            for r in regressions:
                print(f"  {r}")
            sys.exit(1)
        print("VERIFY: CLEAN — no regressions")

    elif "--analyze" in args:
        s = measure()
        proposals = analyze(s)
        print(f"{len(proposals)} weaknesses found:")
        for p in proposals[:10]:
            print(f"  P{p['priority']}: [{p['fix_class']}] {p['signal'][:70]}")
        if not proposals:
            print("  No weaknesses — all green.")

    elif "--journal" in args:
        path = _journal_path()
        if not path.exists():
            print("No journal entries yet.")
            return
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                entry = json.loads(line)
                print(f"  {entry['timestamp'][:19]} | {entry['verdict']:10} | "
                      f"gauntlet {entry['after']['gauntlet']} | "
                      f"unit {entry['after']['unit']} | "
                      f"action: {entry['action']}")

    else:
        # Default: MEASURE → ANALYZE → print top weakness
        s = measure()
        print(f"Gauntlet: {s.gauntlet_pass}/{s.gauntlet_total} | "
              f"Unit: {s.unit_pass}/{s.unit_total} | "
              f"Safety: {s.safety_pass}/{s.safety_pass + s.safety_fail}")
        proposals = analyze(s)
        if proposals:
            top = proposals[0]
            print(f"\nTop weakness (P{top['priority']}): {top['signal']}")
            print(f"Fix class: {top['fix_class']}")
            print(f"Hint: {FIX_CLASSES.get(top['fix_class'], 'No hint available')}")
        else:
            print("\nAll green. No weaknesses found.")


if __name__ == "__main__":
    main()
