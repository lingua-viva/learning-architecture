"""
Regression coverage for desktop/package.json's extraResources.filter —
specifically the fix that lets the packaged desktop app's `ontology.engine`
import actually succeed (previously ModuleNotFoundError on every real
install, since only `ontology/education/**` was ever shipped).

Live-verified this session by mirroring the filter's additions into the
actually-installed desktop app and confirming `/api/query` runs the full
SCAN->CLASSIFY->RETRIEVE->REASON->SYNTHESIZE->STORE pipeline end to end with
a real local model response (see dev/reports/
REPORT_LV_DESKTOP_ONTOLOGY_PACKAGING_2026-07-22.md). This file protects that
fix from silently regressing, and — just as importantly — protects the
privacy exclusions that made it safe to ship.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_JSON = REPO_ROOT / "desktop" / "package.json"


def _filter_list() -> list[str]:
    data = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    resources = data["build"]["extraResources"]
    assert len(resources) == 1
    return resources[0]["filter"]


def test_ontology_engine_dependency_closure_is_shipped():
    """Every file ontology.engine's import chain actually needs at runtime —
    traced by hand this session — must be present in the filter."""
    filt = _filter_list()
    required = [
        "ontology/__init__.py",
        "ontology/engine.py",
        "ontology/schema.yaml",
        "ontology/core/**",
        "ontology/domains/**",
        "ontology/proposals/**",
        "ontology/learned_weights.py",
        "memory/**",
        "lenses/__init__.py",
        "lenses/engine.py",
        "lenses/core/**",
        "lenses/professional/**",
        "lenses/education/**",
        "knowledge/__init__.py",
        "knowledge/*.yaml",
        "knowledge/education/**",
    ]
    for entry in required:
        assert entry in filt, f"{entry} missing — ontology.engine's import chain will break in the packaged app"


def test_personal_lens_file_is_never_shipped():
    """LENS-PERSON-002_claudia_canu.yaml is a real person's private profile
    (career history, family finance analysis sources) — LensEngine never
    reads it (it only auto-loads core/professional/education subdirs), so
    there is no functional reason to ship it, and every reason not to."""
    filt = _filter_list()
    assert "lenses/**" not in filt, (
        "A blanket 'lenses/**' would ship LENS-PERSON-002_claudia_canu.yaml "
        "(and any future top-level personal lens file) to every install — "
        "list lenses/core, lenses/professional, lenses/education explicitly instead"
    )
    for entry in filt:
        assert "LENS-PERSON" not in entry, f"Personal lens file pattern found in filter: {entry}"


def test_accumulated_runtime_state_is_excluded():
    """learned_weights.yaml and memory/data/ are auto-accumulated from this
    dev machine's actual query history — shipping them would leak dev-session
    data to every teacher's install and pre-seed their app with someone
    else's usage patterns instead of a clean slate. Both classes tolerate a
    missing file gracefully (confirmed: LearnedWeights._load() and
    StudentLensStore's own local-only storage), so excluding them is safe."""
    filt = _filter_list()
    assert "!ontology/learned_weights.yaml" in filt
    assert "!memory/data/**" in filt
