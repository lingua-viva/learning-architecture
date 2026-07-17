from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MATRIX = ROOT / "curriculum" / "lingua_viva_matrix.yaml"


class CurriculumService:
    """Read-only access to curriculum data from curriculum/lingua_viva_matrix.yaml."""

    def __init__(self, matrix_path: Path | str = DEFAULT_MATRIX):
        self.matrix_path = Path(matrix_path)
        self._data: dict[str, Any] | None = None

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

        units: list[dict] = []
        for band in data.get("grade_bands", []):
            grade = str(band.get("grade", ""))
            focus = str(band.get("curriculum_focus", "Italian language development"))
            cefr = str(band.get("cefr_target_wording", "designed to target CEFR growth"))
            themes = self._starter_themes(grade)
            for index, theme in enumerate(themes, start=1):
                section = f"{index + 1}.{index}"
                units.append({
                    "unit_id": f"{grade.lower()}-unit-{index}",
                    "grade": grade,
                    "title": theme,
                    "focus": focus,
                    "cefr_target": cefr,
                    "cefr_language": self._designed_to_sentence(cefr),
                    "manuale_section": section,
                    "source_citation": f"Manuale §{section}, Grade {grade.removeprefix('G')}",
                    "source_status": "authoritative_source_derivative_matrix",
                    "framework_alignment": deepcopy(data.get("frameworks", [])),
                    "materials": ["Manuale v1", "teacher notes", "student notebook"],
                })
        return units

    @staticmethod
    def _designed_to_sentence(cefr_wording: str) -> str:
        wording = cefr_wording.strip()
        if wording.lower().startswith("designed"):
            return wording[0].upper() + wording[1:]
        return f"Designed to target {wording}"

    @staticmethod
    def _starter_themes(grade: str) -> list[str]:
        return {
            "G1": ["Suoni e parole", "La mia classe", "Storie con immagini"],
            "G2": ["Lettura fluente", "Frasi intenzionali", "Prime strutture grammaticali"],
            "G3": ["La famiglia e le relazioni", "Testi brevi e autonomi", "Tempi verbali in contesto"],
            "G4": ["Comprensione avanzata", "Produzione scritta ricca", "Lingua per l'indagine"],
            "G5": ["Portfolio linguistico", "Testi multiparagrafo", "Prontezza B1"],
        }.get(grade, ["Unit 1", "Unit 2", "Unit 3"])
