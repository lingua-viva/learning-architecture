from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from doctor.support_loop.doctor import run_doctor
from src.education.student_lens import StudentLensStore
from src.lingua_viva.curriculum import CurriculumService
from src.lingua_viva.filemap import load_map, summarize


class BriefService:
    """Pure local aggregation for the teacher home brief."""

    def __init__(
        self,
        student_store_factory: Callable[[], StudentLensStore],
        revision_log_path: Path,
        doctor_runner: Callable[..., dict[str, Any]] = run_doctor,
    ):
        self.student_store_factory = student_store_factory
        self.revision_log_path = Path(revision_log_path)
        self.doctor_runner = doctor_runner
        self.curriculum = CurriculumService()

    def get_brief(self, schedule: dict | None = None, day: str | None = None, unobserved_days: int = 14) -> dict:
        schedule = schedule or {}
        with self.student_store_factory() as store:
            unobserved = self._unobserved(store, unobserved_days)
            recent = self._recent(store)
            rti_pending = self._rti_pending(store)
        health = self.doctor_runner(write_log=False)
        file_map_summary = summarize(load_map())
        return {
            "today": self._today(schedule, day),
            "attention": {
                "unobserved_count": len(unobserved),
                "unobserved_students": [student.get("display_name") or student["student_id"] for student in unobserved[:5]],
                "rti_pending": len(rti_pending),
                "rti_pending_names": [student.get("display_name") or student["student_id"] for student in rti_pending[:5]],
            },
            "recent": {
                **recent,
                "last_reflection": self._last_reflection(),
            },
            "health": {
                "status": health.get("status", "WARN"),
                "summary": health.get("summary", ""),
            },
            "filemap": file_map_summary if file_map_summary["configured"] else None,
        }

    def _today(self, schedule: dict, day: str | None) -> dict:
        day_key = (day or datetime.now().strftime("%A")).strip().lower()
        entry = schedule.get(day_key) or schedule.get(day_key.title()) or {}
        if not isinstance(entry, dict) or not entry.get("grade"):
            return {"day": day_key.title(), "configured": False}
        try:
            unit = self.curriculum.get_unit(str(entry.get("unit_id") or ""))
        except KeyError:
            units = self.curriculum.get_grade(str(entry.get("grade") or ""))
            unit = units[0] if units else self.curriculum.get_grade("G3")[0]
        return {
            "day": day_key.title(),
            "configured": True,
            "grade": unit["grade"],
            "unit": unit["title"],
            "unit_id": unit["unit_id"],
            "cefr_targets": [unit["cefr_language"]],
            "source": f"Manuale §{unit['manuale_section']}",
        }

    def _unobserved(self, store: StudentLensStore, days: int) -> list[dict]:
        cutoff = time.time() - max(days, 0) * 86400
        results = []
        for lens in store.list_lenses():
            last = self._last_observed(store, lens["student_id"])
            stale = True
            if last:
                try:
                    stale = datetime.fromisoformat(last).timestamp() < cutoff
                except ValueError:
                    stale = True
            if stale:
                results.append({**lens, "last_observed": last})
        return results

    def _rti_pending(self, store: StudentLensStore) -> list[dict]:
        pending = []
        for lens in store.list_lenses():
            try:
                if lens.get("rti_current_tier", 1) > 1 or store.evaluate_rti_rules(lens["student_id"]):
                    pending.append(lens)
            except Exception:
                continue
        return pending

    def _recent(self, store: StudentLensStore) -> dict:
        week_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        rows = store._conn.execute("SELECT recorded_at FROM observations ORDER BY recorded_at DESC").fetchall()
        observations_this_week = 0
        last_observation = rows[0]["recorded_at"] if rows else None
        for row in rows:
            try:
                if datetime.fromisoformat(row["recorded_at"]) >= week_cutoff:
                    observations_this_week += 1
            except ValueError:
                continue
        return {
            "last_observation": last_observation,
            "observations_this_week": observations_this_week,
        }

    def _last_observed(self, store: StudentLensStore, student_id: str) -> str | None:
        row = store._conn.execute(
            "SELECT recorded_at FROM observations WHERE student_id = ? ORDER BY recorded_at DESC LIMIT 1",
            (student_id,),
        ).fetchone()
        return row["recorded_at"] if row else None

    def _last_reflection(self) -> str | None:
        try:
            lines = [line for line in self.revision_log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        except OSError:
            return None
        for line in reversed(lines):
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("timestamp"):
                return entry["timestamp"]
        return None
