"""Live-layer read path tests (SPEC_LIVE_LAYER_READ_PATH_2026-07-27).

The one-button update system preserves teacher edits under
``~/.lingua-viva/templates/`` — these tests pin the readers that make those
files actually change behavior: the LensEngine education overlay, the
CurriculumService live-matrix resolution, and the Doctor visibility check.

Hermeticity: the autouse ``_hermetic_lv_state`` fixture (conftest) points
LV_UPDATE_HOME at a per-test tmp dir, so every test here builds its live
layer from scratch and never touches the operator's real home.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lenses.engine import LensEngine, scan_live_lens_issues


def _live_education_dir() -> Path:
    root = Path(os.environ["LV_UPDATE_HOME"]) / "templates" / "lenses" / "education"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _write(dirpath: Path, filename: str, text: str) -> Path:
    path = dirpath / filename
    path.write_text(text, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Shadowing + new lenses (acceptance #1 unit-level, #2)
# ---------------------------------------------------------------------------

def test_live_edit_shadows_bundle_education_lens():
    _write(
        _live_education_dir(),
        "observation-coach.yaml",
        "name: observation-coach\n"
        "description: teacher-customized\n"
        "system_prompt_modifier: 'TEACHER CUSTOM MARKER'\n",
    )
    engine = LensEngine()
    lens = engine.get_lens("observation-coach")
    assert lens is not None
    assert lens.system_prompt_modifier == "TEACHER CUSTOM MARKER"
    assert lens.description == "teacher-customized"


def test_teacher_created_lens_loads_and_activates():
    _write(
        _live_education_dir(),
        "my-class-voice.yaml",
        "name: my-class-voice\n"
        "description: a brand-new teacher lens\n"
        "activation:\n  on_signal_keywords: [xylophone]\n"
        "system_prompt_modifier: 'CLASS VOICE'\n",
    )
    engine = LensEngine()
    assert "my-class-voice" in engine.lenses
    active = engine.get_active_lenses(query="the xylophone lesson")
    assert "my-class-voice" in [l.name for l in active]


def test_shadowing_is_case_folded_no_duplicate_lens():
    _write(
        _live_education_dir(),
        "obs.yaml",
        "name: Observation-Coach\n"
        "system_prompt_modifier: 'CASE FOLDED WINNER'\n",
    )
    engine = LensEngine()
    matches = [k for k in engine.lenses if k.casefold() == "observation-coach"]
    assert matches == ["Observation-Coach"], matches
    assert engine.lenses["Observation-Coach"].system_prompt_modifier == "CASE FOLDED WINNER"


# ---------------------------------------------------------------------------
# Namespace guard (acceptance #3)
# ---------------------------------------------------------------------------

def test_core_lens_name_cannot_be_hijacked():
    _write(
        _live_education_dir(),
        "evil.yaml",
        "name: protection\nsystem_prompt_modifier: 'HIJACKED'\n",
    )
    engine = LensEngine()
    assert engine.lenses["protection"].system_prompt_modifier != "HIJACKED"
    assert any("protection" in rec["reason"] for rec in engine.skipped_live)


def test_professional_lens_name_guard_is_case_folded():
    _write(
        _live_education_dir(),
        "evil.yaml",
        "name: Legal\nsystem_prompt_modifier: 'HIJACKED'\n",
    )
    engine = LensEngine()
    assert "Legal" not in engine.lenses
    assert engine.lenses["legal"].system_prompt_modifier != "HIJACKED"
    assert len(engine.skipped_live) == 1


# ---------------------------------------------------------------------------
# Guarded parse failures (acceptance #4) + deletion/fresh home (#5, #6)
# ---------------------------------------------------------------------------

def test_corrupt_live_file_bundle_copy_serves():
    _write(_live_education_dir(), "observation-coach.yaml", "name: [unclosed\n")
    engine = LensEngine()
    lens = engine.get_lens("observation-coach")
    assert lens is not None
    assert "structured" in lens.description  # bundle copy's wording
    assert len(engine.skipped_live) == 1


def test_alias_bomb_live_file_is_refused():
    _write(
        _live_education_dir(),
        "bomb.yaml",
        "a: &a [1, 2]\nname: bomb\nb: *a\n",
    )
    engine = LensEngine()
    assert "bomb" not in engine.lenses
    assert any("bomb.yaml" in rec["path"] for rec in engine.skipped_live)


def test_oversize_live_file_is_refused():
    big = "name: big\ndescription: " + "x" * 1_100_000 + "\n"
    _write(_live_education_dir(), "big.yaml", big)
    engine = LensEngine()
    assert "big" not in engine.lenses
    assert len(engine.skipped_live) == 1


def test_non_mapping_live_file_is_skipped():
    _write(_live_education_dir(), "list.yaml", "- just\n- a\n- list\n")
    engine = LensEngine()
    assert len(engine.skipped_live) == 1
    assert "mapping" in engine.skipped_live[0]["reason"]


def test_fresh_home_is_byte_identical_to_bundle_load():
    # LV_UPDATE_HOME exists but has no templates dir (the conftest default).
    default_engine = LensEngine()
    bundle_engine = LensEngine(Path(__file__).parent.parent / "lenses")
    assert set(default_engine.lenses) == set(bundle_engine.lenses)
    assert default_engine.skipped_live == []


def test_explicit_lenses_dir_disables_overlay():
    _write(
        _live_education_dir(),
        "my-class-voice.yaml",
        "name: my-class-voice\n",
    )
    engine = LensEngine(Path(__file__).parent.parent / "lenses")
    assert "my-class-voice" not in engine.lenses


# ---------------------------------------------------------------------------
# Import tolerance (acceptance #9)
# ---------------------------------------------------------------------------

def test_reconcile_import_failure_falls_back_to_bundle(monkeypatch):
    _write(
        _live_education_dir(),
        "my-class-voice.yaml",
        "name: my-class-voice\n",
    )
    # sys.modules[name] = None makes ``from name import ...`` raise ImportError.
    monkeypatch.setitem(sys.modules, "src.lingua_viva.reconcile", None)
    engine = LensEngine()
    assert "my-class-voice" not in engine.lenses
    assert "observation-coach" in engine.lenses  # bundle load intact
    assert engine.skipped_live == []


# ---------------------------------------------------------------------------
# Overlay scan budget (acceptance #4 timing clause)
# ---------------------------------------------------------------------------

def test_overlay_scan_overhead_under_100ms():
    live = _live_education_dir()
    for i in range(5):
        _write(live, f"lens-{i}.yaml", f"name: teacher-lens-{i}\n")
    LensEngine()  # warm imports/caches
    start = time.perf_counter()
    engine = LensEngine()
    elapsed = time.perf_counter() - start
    assert all(f"teacher-lens-{i}" in engine.lenses for i in range(5))
    # Full construction (bundle + overlay) — comfortably inside the spec's
    # <100ms overlay budget even with margin for slow CI.
    assert elapsed < 0.100, f"engine construction took {elapsed * 1000:.1f}ms"


# ---------------------------------------------------------------------------
# Doctor helper (acceptance #3/#4 visibility)
# ---------------------------------------------------------------------------

def test_scan_live_lens_issues_reports_both_skip_kinds():
    live = _live_education_dir()
    _write(live, "broken.yaml", "name: [unclosed\n")
    _write(live, "evil.yaml", "name: protection\n")
    issues = scan_live_lens_issues()
    reasons = " | ".join(rec["reason"] for rec in issues)
    assert len(issues) == 2
    assert "could not be read" in reasons
    assert "core/professional" in reasons


def test_scan_live_lens_issues_clean_when_no_live_layer():
    assert scan_live_lens_issues() == []


# ---------------------------------------------------------------------------
# Doctor live_templates check (spec §2d)
# ---------------------------------------------------------------------------

def test_doctor_live_templates_warns_never_fails_on_issues():
    from doctor.support_loop.doctor import check_live_templates

    live = _live_education_dir()
    _write(live, "broken.yaml", "name: [unclosed\n")
    _write(live, "evil.yaml", "name: protection\n")
    result = check_live_templates()
    assert result.status == "warn"
    assert "shipped version is serving" in result.message
    assert "broken.yaml" in (result.detail or "")
    assert "evil.yaml" in (result.detail or "")


def test_doctor_live_templates_passes_clean():
    from doctor.support_loop.doctor import check_live_templates

    result = check_live_templates()
    assert result.status == "pass"


def test_doctor_live_templates_registered_in_run_doctor():
    """A check that exists but never runs is the pacdiff failure mode."""
    import inspect

    from doctor.support_loop import doctor as doc

    assert "check_live_templates" in inspect.getsource(doc.run_doctor)


def test_doctor_live_templates_import_failure_is_pass(monkeypatch):
    from doctor.support_loop.doctor import check_live_templates

    monkeypatch.setitem(sys.modules, "lenses.engine", None)
    result = check_live_templates()
    assert result.status == "pass"
    assert "skipped" in result.message


# ---------------------------------------------------------------------------
# CurriculumService live matrix (acceptance #8)
# ---------------------------------------------------------------------------

def _live_matrix_path() -> Path:
    path = Path(os.environ["LV_UPDATE_HOME"]) / "templates" / "curriculum" / "lingua_viva_matrix.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def test_curriculum_default_uses_live_matrix_when_valid():
    from src.lingua_viva.curriculum import CurriculumService

    live = _live_matrix_path()
    live.write_text(
        "version: teacher-edited\nstatus: live\ngrade_bands: []\n",
        encoding="utf-8",
    )
    service = CurriculumService()
    assert service.matrix_path == live
    assert service.get_overview()["version"] == "teacher-edited"


def test_curriculum_corrupt_live_matrix_falls_back_to_bundle():
    from src.lingua_viva.curriculum import DEFAULT_MATRIX, CurriculumService

    _live_matrix_path().write_text("version: [unclosed\n", encoding="utf-8")
    service = CurriculumService()
    assert service.matrix_path == DEFAULT_MATRIX
    assert service.get_overview()["version"] is not None


def test_curriculum_no_live_matrix_uses_bundle():
    from src.lingua_viva.curriculum import DEFAULT_MATRIX, CurriculumService

    service = CurriculumService()
    assert service.matrix_path == DEFAULT_MATRIX


def test_curriculum_explicit_path_bypasses_live_resolution(tmp_path):
    from src.lingua_viva.curriculum import CurriculumService

    _live_matrix_path().write_text("version: live\n", encoding="utf-8")
    explicit = tmp_path / "matrix.yaml"
    explicit.write_text("version: explicit\ngrade_bands: []\n", encoding="utf-8")
    service = CurriculumService(explicit)
    assert service.matrix_path == explicit
    assert service.get_overview()["version"] == "explicit"


def test_curriculum_live_edit_serves_on_next_request_via_route():
    """Acceptance #8 end-to-end: routes construct CurriculumService per
    request, so a live matrix edit applies on the next request — no restart."""
    from fastapi.testclient import TestClient

    from src.web import app

    live = _live_matrix_path()
    with TestClient(app) as client:
        before = client.get("/api/admin/programme")
        assert before.status_code == 200
        live.write_text(
            "version: live-edited-mid-session\nstatus: live\ngrade_bands: []\n",
            encoding="utf-8",
        )
        after = client.get("/api/admin/programme")
    assert after.status_code == 200
    assert before.json()["version"] != "live-edited-mid-session"
    assert after.json()["version"] == "live-edited-mid-session"


def test_take_new_resolution_serves_through_engine_next_construction(monkeypatch, tmp_path):
    """Acceptance #7 (backend half): after take_new through the resolve
    machinery, the next LensEngine() construction serves the new content —
    the Settings panel's promise becomes true. (The restart-hint UI half is
    sealed by the v45 contract lock.)"""
    from src.lingua_viva import reconcile as rec

    seed = tmp_path / "seed"
    (seed / "lenses" / "education").mkdir(parents=True)
    (seed / "curriculum").mkdir(parents=True)
    base = "name: observation-coach\ndescription: 'shipped v1'\nschema_version: 1\n"
    (seed / "lenses" / "education" / "observation-coach.yaml").write_text(base, encoding="utf-8")
    (seed / "curriculum" / "lingua_viva_matrix.yaml").write_text("authority: x\n", encoding="utf-8")
    monkeypatch.setenv("LV_SEED_ROOT", str(seed))
    monkeypatch.setenv("LV_ENGINE_VERSION", "1.0.0")

    rel = "lenses/education/observation-coach.yaml"
    rec.reconcile()
    live_path = rec.live_root() / rel
    live_path.write_text(base + "teacher_note: mine\n", encoding="utf-8")
    (seed / rel).write_text(base.replace("shipped v1", "shipped v2"), encoding="utf-8")
    monkeypatch.setenv("LV_ENGINE_VERSION", "1.1.0")
    rec.reconcile()  # parks the update (teacher copy modified)

    assert LensEngine().get_lens("observation-coach").description == "shipped v1"
    rec.resolve_pending(rel, "take_new")
    assert LensEngine().get_lens("observation-coach").description == "shipped v2"


def test_curriculum_reconcile_import_failure_uses_bundle(monkeypatch):
    from src.lingua_viva.curriculum import DEFAULT_MATRIX, CurriculumService

    _live_matrix_path().write_text("version: live\ngrade_bands: []\n", encoding="utf-8")
    monkeypatch.setitem(sys.modules, "src.lingua_viva.reconcile", None)
    service = CurriculumService()
    assert service.matrix_path == DEFAULT_MATRIX
