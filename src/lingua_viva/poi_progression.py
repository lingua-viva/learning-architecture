"""IB PYP Programme of Inquiry progression tracking (W3, 2026-08-09).

Models the PYP Programme of Inquiry structure — the six transdisciplinary
themes, units of inquiry per year level, and a four-phase progression
scale per learning objective — and records per-student activity
iterations against them, so a teacher can see the current level per
objective, its trend, and what to consolidate next.

Storage: NEW tables in the SAME SQLite database student_lens.py already
uses (default ~/.lingua-viva/runtime/student_lenses.db, override via
LV_STUDENT_DB_PATH — resolved through student_lens.default_db_path so the
two modules can never diverge). The iteration log is append-only, mirroring
the observations table philosophy: a progression summary is a
*recalculated snapshot* over the log, never stored state.

Privacy: pure local storage + arithmetic; no model call, no egress.
Student data never enters git history — tests use synthetic names only.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.education.student_lens import default_db_path

# The six PYP transdisciplinary themes (IBO, PYP: From Principles into
# Practice, 2018).
TRANSDISCIPLINARY_THEMES = (
    "Who we are",
    "Where we are in place and time",
    "How we express ourselves",
    "How the world works",
    "How we organize ourselves",
    "Sharing the planet",
)

# Progression phases per learning objective, ordered lowest → highest.
PROGRESSION_PHASES = ("beginning", "developing", "consolidating", "secure")

VALID_TRENDS = ("progressing", "plateauing", "needs_consolidation", "insufficient_data")

# Default units of inquiry per year level for the Italian language
# programme: one unit per transdisciplinary theme, themed to the grade
# band's language focus. Honest scaffolds — a coordinator can replace them
# by registering real units; these exist so the tracker is useful on day
# one without setup.
_DEFAULT_UNIT_TITLES: dict[str, tuple[str, ...]] = {
    "G1": ("Io e i miei suoni", "La mia giornata", "Storie che raccontiamo",
           "Il mondo intorno a me", "La nostra classe", "Prendersi cura"),
    "G2": ("Chi sono io", "Ieri e oggi", "Esprimersi con le parole",
           "Come funzionano le cose", "Regole e routine", "Il nostro ambiente"),
    "G3": ("La famiglia e le relazioni", "Luoghi e memorie", "Testi che creiamo",
           "Indagare con la lingua", "Organizzare le idee", "Condividere risorse"),
    "G4": ("Identità in crescita", "Viaggi nel tempo", "Scrittura ricca",
           "La lingua dell'indagine", "Sistemi e strutture", "Responsabilità condivise"),
    "G5": ("Il mio portfolio", "Storia e appartenenza", "Testi multiparagrafo",
           "Ricerca e evidenza", "Progetti insieme", "Il pianeta che condividiamo"),
}

_DEFAULT_OBJECTIVES = (
    "oral_communication",
    "reading_comprehension",
    "written_production",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def phase_index(phase: str) -> int:
    try:
        return PROGRESSION_PHASES.index(phase)
    except ValueError:
        raise ValueError(
            f"tier_demonstrated must be one of {PROGRESSION_PHASES}, got {phase!r}"
        )


def default_units_for_year(year_level: str) -> list[dict]:
    """Six default units of inquiry (one per transdisciplinary theme) for a
    year level, each carrying the default language objectives."""
    year = str(year_level or "").strip().upper()
    if year.isdigit():
        year = f"G{year}"
    titles = _DEFAULT_UNIT_TITLES.get(
        year, tuple(f"Unit of inquiry {i + 1}" for i in range(6))
    )
    return [
        {
            "unit_id": f"poi-{year.lower()}-{index + 1}",
            "year_level": year,
            "theme": theme,
            "title": titles[index],
            "central_idea": (
                f"Language lets us explore \"{theme.lower()}\" and share what we discover."
            ),
            "objectives": list(_DEFAULT_OBJECTIVES),
        }
        for index, theme in enumerate(TRANSDISCIPLINARY_THEMES)
    ]


class PoIProgressionStore:
    """SQLite-backed store for PoI units + append-only activity iterations."""

    def __init__(self, db_path: Optional[Path | str] = None):
        self.db_path = Path(db_path) if db_path else default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "PoIProgressionStore":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS poi_units (
                unit_id TEXT PRIMARY KEY,
                year_level TEXT NOT NULL,
                theme TEXT NOT NULL,
                title TEXT NOT NULL,
                central_idea TEXT NOT NULL DEFAULT '',
                objectives TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS poi_iterations (
                iteration_id TEXT PRIMARY KEY,
                student_id TEXT NOT NULL,
                unit_id TEXT NOT NULL,
                objective TEXT NOT NULL,
                activity_id TEXT NOT NULL,
                tier_demonstrated TEXT NOT NULL,
                evidence_note TEXT NOT NULL DEFAULT '',
                recorded_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_poi_iter_student
                ON poi_iterations(student_id, unit_id, objective, recorded_at);
            """
        )
        self._conn.commit()

    # ── Units ─────────────────────────────────────────────────────────

    def register_unit(
        self,
        *,
        unit_id: str,
        year_level: str,
        theme: str,
        title: str,
        central_idea: str = "",
        objectives: Optional[list[str]] = None,
    ) -> dict:
        if theme not in TRANSDISCIPLINARY_THEMES:
            raise ValueError(
                f"theme must be one of the six PYP transdisciplinary themes, got {theme!r}"
            )
        if not str(unit_id).strip():
            raise ValueError("unit_id is required")
        record = {
            "unit_id": unit_id,
            "year_level": year_level,
            "theme": theme,
            "title": title,
            "central_idea": central_idea,
            "objectives": list(objectives or _DEFAULT_OBJECTIVES),
        }
        self._conn.execute(
            """INSERT OR REPLACE INTO poi_units
               (unit_id, year_level, theme, title, central_idea, objectives, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (unit_id, year_level, theme, title, central_idea,
             json.dumps(record["objectives"]), _now_iso()),
        )
        self._conn.commit()
        return record

    def seed_default_units(self, year_level: str) -> list[dict]:
        """Register the default six-theme unit set for a year level.
        Idempotent (INSERT OR REPLACE on stable unit_ids)."""
        units = default_units_for_year(year_level)
        for unit in units:
            self.register_unit(**unit)
        return units

    def get_unit(self, unit_id: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT * FROM poi_units WHERE unit_id = ?", (unit_id,)
        ).fetchone()
        if row is None:
            return None
        record = dict(row)
        record["objectives"] = json.loads(record.get("objectives") or "[]")
        return record

    def list_units(self, year_level: Optional[str] = None) -> list[dict]:
        if year_level:
            rows = self._conn.execute(
                "SELECT * FROM poi_units WHERE year_level = ? ORDER BY unit_id",
                (year_level,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM poi_units ORDER BY unit_id"
            ).fetchall()
        out = []
        for row in rows:
            record = dict(row)
            record["objectives"] = json.loads(record.get("objectives") or "[]")
            out.append(record)
        return out

    # ── Iterations (append-only) ──────────────────────────────────────

    def record_iteration(
        self,
        *,
        student_id: str,
        unit_id: str,
        objective: str,
        activity_id: str,
        tier_demonstrated: str,
        evidence_note: str = "",
        recorded_at: Optional[str] = None,
    ) -> dict:
        """Append one activity iteration. Validates the tier against the
        progression scale and, when the unit is registered, the objective
        against the unit's objective list."""
        phase_index(tier_demonstrated)  # raises on invalid tier
        if not str(student_id).strip():
            raise ValueError("student_id is required")
        if not str(unit_id).strip():
            raise ValueError("unit_id is required")
        if not str(objective).strip():
            raise ValueError("objective is required")
        if not str(activity_id).strip():
            raise ValueError("activity_id is required")

        unit = self.get_unit(unit_id)
        if unit is not None and unit["objectives"] and objective not in unit["objectives"]:
            raise ValueError(
                f"objective {objective!r} is not part of unit {unit_id!r} "
                f"(known: {unit['objectives']})"
            )

        record = {
            "iteration_id": f"poi-it-{uuid.uuid4().hex[:12]}",
            "student_id": student_id,
            "unit_id": unit_id,
            "objective": objective,
            "activity_id": activity_id,
            "tier_demonstrated": tier_demonstrated,
            "evidence_note": evidence_note,
            "recorded_at": recorded_at or _now_iso(),
        }
        self._conn.execute(
            """INSERT INTO poi_iterations
               (iteration_id, student_id, unit_id, objective, activity_id,
                tier_demonstrated, evidence_note, recorded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            tuple(record.values()),
        )
        self._conn.commit()
        return record

    def list_iterations(
        self,
        student_id: str,
        unit_id: Optional[str] = None,
        objective: Optional[str] = None,
    ) -> list[dict]:
        query = "SELECT * FROM poi_iterations WHERE student_id = ?"
        params: list = [student_id]
        if unit_id:
            query += " AND unit_id = ?"
            params.append(unit_id)
        if objective:
            query += " AND objective = ?"
            params.append(objective)
        query += " ORDER BY recorded_at, iteration_id"
        return [dict(row) for row in self._conn.execute(query, params).fetchall()]

    # ── Derived views (recalculated, never stored) ────────────────────

    @staticmethod
    def _trend(indices: list[int]) -> str:
        """Trend over the ordered phase indices for one objective.

        - < 2 iterations → insufficient_data
        - recent window rising → progressing
        - recent window falling → needs_consolidation
        - flat: plateauing, EXCEPT ≥3 flat iterations below "consolidating"
          → needs_consolidation (a student stuck low is not merely flat)
        """
        if len(indices) < 2:
            return "insufficient_data"
        recent = indices[-3:]
        if recent[-1] > recent[0]:
            return "progressing"
        if recent[-1] < recent[0]:
            return "needs_consolidation"
        flat_run = 1
        for prev, cur in zip(reversed(indices[:-1]), reversed(indices[1:])):
            if prev == cur:
                flat_run += 1
            else:
                break
        if flat_run >= 3 and recent[-1] < PROGRESSION_PHASES.index("consolidating"):
            return "needs_consolidation"
        return "plateauing"

    def objective_summary(
        self, student_id: str, unit_id: str, objective: str
    ) -> dict:
        iterations = self.list_iterations(student_id, unit_id, objective)
        if not iterations:
            return {
                "student_id": student_id,
                "unit_id": unit_id,
                "objective": objective,
                "current_level": None,
                "trend": "insufficient_data",
                "iteration_count": 0,
                "last_recorded_at": None,
                "history": [],
            }
        indices = [phase_index(it["tier_demonstrated"]) for it in iterations]
        return {
            "student_id": student_id,
            "unit_id": unit_id,
            "objective": objective,
            "current_level": iterations[-1]["tier_demonstrated"],
            "trend": self._trend(indices),
            "iteration_count": len(iterations),
            "last_recorded_at": iterations[-1]["recorded_at"],
            "history": [
                {
                    "activity_id": it["activity_id"],
                    "tier_demonstrated": it["tier_demonstrated"],
                    "evidence_note": it["evidence_note"],
                    "recorded_at": it["recorded_at"],
                }
                for it in iterations
            ],
        }

    def student_summary(self, student_id: str) -> dict:
        """Full progression picture for one student: every (unit, objective)
        they have iterations for, plus a ranked "what to consolidate next"
        list (needs_consolidation first, then lowest plateaued levels)."""
        pairs = self._conn.execute(
            """SELECT DISTINCT unit_id, objective FROM poi_iterations
               WHERE student_id = ? ORDER BY unit_id, objective""",
            (student_id,),
        ).fetchall()
        summaries = [
            self.objective_summary(student_id, row["unit_id"], row["objective"])
            for row in pairs
        ]

        def _priority(summary: dict) -> tuple:
            trend_rank = {"needs_consolidation": 0, "plateauing": 1,
                          "insufficient_data": 2, "progressing": 3}
            level = summary["current_level"]
            level_idx = phase_index(level) if level else len(PROGRESSION_PHASES)
            return (trend_rank.get(summary["trend"], 3), level_idx)

        consolidate = [
            {
                "unit_id": s["unit_id"],
                "objective": s["objective"],
                "current_level": s["current_level"],
                "trend": s["trend"],
                "suggestion": (
                    f"Revisit {s['objective'].replace('_', ' ')} in unit "
                    f"{s['unit_id']} with a {s['current_level']}-level activity "
                    "before introducing new material."
                ),
            }
            for s in sorted(summaries, key=_priority)
            if s["trend"] in ("needs_consolidation", "plateauing")
            and s["current_level"] is not None
            and phase_index(s["current_level"]) < PROGRESSION_PHASES.index("secure")
        ]

        themes = sorted({
            unit["theme"]
            for s in summaries
            if (unit := self.get_unit(s["unit_id"])) is not None
        })
        return {
            "student_id": student_id,
            "objectives": [
                {k: v for k, v in s.items() if k != "history"} for s in summaries
            ],
            "consolidate_next": consolidate,
            "themes_touched": themes,
            "progression_scale": list(PROGRESSION_PHASES),
        }
