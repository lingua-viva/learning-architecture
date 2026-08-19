from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MATRIX = ROOT / "curriculum" / "lingua_viva_matrix.yaml"


def _resolve_live_matrix() -> tuple[Path, dict[str, Any] | None]:
    """Resolve the default matrix source (SPEC_LIVE_LAYER_READ_PATH §2b).

    The live teacher copy at ``live_root()/curriculum/lingua_viva_matrix.yaml``
    wins iff it exists and passes the guarded parse (alias-bomb refusal +
    size cap — the file is teacher-writable) at resolve time. Any failure —
    missing file, bad parse, guard trip, broken update subsystem import —
    falls back to the shipped bundle matrix. Returns ``(path, parsed)``;
    ``parsed`` is pre-validated data for the live path (avoids re-parsing
    the teacher file with unguarded YAML), or ``None`` for the bundle path
    (lazy-loaded as today).
    """
    try:
        from src.lingua_viva.reconcile import _parse_yaml_guarded, live_root

        live = live_root() / "curriculum" / "lingua_viva_matrix.yaml"
        if live.is_file():
            data = _parse_yaml_guarded(live.read_bytes())
            if isinstance(data, dict) and data:
                return live, data
    except Exception:
        pass
    return DEFAULT_MATRIX, None


class CurriculumService:
    """Read-only access to curriculum data from curriculum/lingua_viva_matrix.yaml.

    Default construction resolves the teacher's live matrix copy when one
    exists and is readable (see ``_resolve_live_matrix``). Routes construct
    this service per request, so live curriculum edits apply on the next
    request — no restart needed. Explicit ``matrix_path`` arguments (tests,
    tooling) bypass live resolution entirely and keep exact prior behavior.
    """

    def __init__(self, matrix_path: Path | str | None = None):
        self._data: dict[str, Any] | None = None
        if matrix_path is None:
            self.matrix_path, self._data = _resolve_live_matrix()
        else:
            self.matrix_path = Path(matrix_path)

    def _load(self) -> dict[str, Any]:
        if self._data is None:
            with self.matrix_path.open(encoding="utf-8") as handle:
                data = yaml.safe_load(handle) or {}
            self._data = data if isinstance(data, dict) else {}
        return self._data

    def get_overview(self) -> dict:
        data = self._load()
        units = self._all_units()
        grade_bands = []
        for band in data.get("grade_bands", []):
            grade = str(band.get("grade", ""))
            grade_units = [unit for unit in units if unit["grade"] == grade]
            grade_bands.append({
                "grade": grade,
                "cefr_target_wording": band.get("cefr_target_wording", ""),
                "curriculum_focus": band.get("curriculum_focus", ""),
                "publication_status": band.get("publication_status", "review_needed"),
                "unit_count": len(grade_units),
            })
        return {
            "version": data.get("version"),
            "status": data.get("status"),
            "authority": data.get("authority"),
            "frameworks": deepcopy(data.get("frameworks", [])),
            "grade_bands": grade_bands,
            "source_status": self.source_status(),
        }

    def get_grade(self, grade: str) -> list[dict]:
        normalized = self._normalize_grade(grade)
        return [deepcopy(unit) for unit in self._all_units() if unit["grade"] == normalized]

    def get_unit(self, unit_id: str) -> dict:
        for unit in self._all_units():
            if unit["unit_id"] == unit_id:
                return deepcopy(unit)
        raise KeyError(unit_id)

    def source_status(self) -> dict:
        data = self._load()
        return {
            "authoritative_source": "Manuale v1",
            "authoritative_path": data.get("source_of_truth"),
            "matrix_authority": data.get("authority", "non_authoritative"),
            "promotion_status": deepcopy(data.get("promotion_status", {})),
            "badge": "Authoritative source: Manuale v1",
            "derivative_notice": "Curriculum matrix is a draft derivative until promoted by review.",
        }

    def _normalize_grade(self, grade: str) -> str:
        value = str(grade or "").strip().upper()
        if value.startswith("GRADE "):
            value = "G" + value.split(" ", 1)[1]
        if value.isdigit():
            value = f"G{value}"
        return value

    def _all_units(self) -> list[dict]:
        data = self._load()
        explicit = data.get("units")
        if isinstance(explicit, list):
            return [deepcopy(unit) for unit in explicit if isinstance(unit, dict)]

        # No explicit units means NO units. A fresh install starts empty —
        # fabricated "starter theme" units presented as real curriculum were
        # the Issue-5 defect; teachers create units via the unit CRUD below.
        return []

    @staticmethod
    def _designed_to_sentence(cefr_wording: str) -> str:
        wording = cefr_wording.strip()
        if wording.lower().startswith("designed"):
            return wording[0].upper() + wording[1:]
        return f"Designed to target {wording}"


# --- Teacher unit CRUD (Issue 5) ---------------------------------------------
#
# Writes always target the LIVE matrix copy (teacher-writable); the shipped
# bundle matrix stays read-only. The first write materializes the currently
# resolved matrix (bundle or live) with an explicit ``units`` list so later
# edits are stable.


def _live_matrix_path() -> Path:
    from src.lingua_viva.reconcile import live_root

    return live_root() / "curriculum" / "lingua_viva_matrix.yaml"


def _matrix_for_write() -> dict[str, Any]:
    service = CurriculumService()
    data = deepcopy(service._load())
    data["units"] = service._all_units()
    return data


def _write_live_matrix(data: dict[str, Any]) -> None:
    path = _live_matrix_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _unit_slug(grade: str, title: str, existing_ids: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "unit"
    candidate = f"{grade.lower()}-{base}"
    counter = 2
    while candidate in existing_ids:
        candidate = f"{grade.lower()}-{base}-{counter}"
        counter += 1
    return candidate


def add_unit(grade: str, title: str, *, focus: str = "", cefr_target: str = "") -> dict:
    title = str(title or "").strip()
    if not title:
        raise ValueError("unit title is required")
    data = _matrix_for_write()
    service = CurriculumService()
    normalized = service._normalize_grade(grade)
    known_grades = {str(band.get("grade", "")) for band in data.get("grade_bands", [])}
    if normalized not in known_grades:
        raise ValueError(f"unknown grade: {grade}")
    units: list[dict] = data["units"]
    unit = {
        "unit_id": _unit_slug(normalized, title, {str(u.get("unit_id")) for u in units}),
        "grade": normalized,
        "title": title,
        "focus": str(focus or "").strip(),
        "cefr_target": str(cefr_target or "").strip(),
        "cefr_language": (
            CurriculumService._designed_to_sentence(str(cefr_target)) if str(cefr_target or "").strip() else ""
        ),
        "manuale_section": "",
        "source_citation": "Teacher-created unit",
        "source_status": "teacher_created",
        "framework_alignment": deepcopy(data.get("frameworks", [])),
        "materials": [],
    }
    units.append(unit)
    _write_live_matrix(data)
    return deepcopy(unit)


def update_unit(unit_id: str, updates: dict) -> dict:
    data = _matrix_for_write()
    units: list[dict] = data["units"]
    unit = next((item for item in units if str(item.get("unit_id")) == unit_id), None)
    if unit is None:
        raise KeyError(unit_id)
    if "title" in updates:
        title = str(updates.get("title") or "").strip()
        if not title:
            raise ValueError("unit title is required")
        unit["title"] = title
    if "focus" in updates:
        unit["focus"] = str(updates.get("focus") or "").strip()
    if "cefr_target" in updates:
        cefr_target = str(updates.get("cefr_target") or "").strip()
        unit["cefr_target"] = cefr_target
        unit["cefr_language"] = (
            CurriculumService._designed_to_sentence(cefr_target) if cefr_target else ""
        )
    if updates.get("position") is not None:
        # Position is an index WITHIN the unit's grade — the reorder the
        # teacher sees in the per-grade dropdown. Units of other grades keep
        # their slots in the flat list.
        position = max(0, int(updates["position"]))
        grade = unit.get("grade")
        same_grade = [item for item in units if item.get("grade") == grade]
        same_grade.remove(unit)
        same_grade.insert(min(position, len(same_grade)), unit)
        replacement = iter(same_grade)
        data["units"] = [
            next(replacement) if item.get("grade") == grade else item for item in units
        ]
    _write_live_matrix(data)
    return deepcopy(unit)


def delete_unit(unit_id: str) -> None:
    data = _matrix_for_write()
    units: list[dict] = data["units"]
    remaining = [item for item in units if str(item.get("unit_id")) != unit_id]
    if len(remaining) == len(units):
        raise KeyError(unit_id)
    data["units"] = remaining
    _write_live_matrix(data)
