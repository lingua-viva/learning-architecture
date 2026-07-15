"""
Scheduled Tasks / Cron System

Governed scheduled execution. Every cron task goes through the same pipeline
with the same gates. No ungoverned background work.

Usage:
    mc cron list                    — show all schedules
    mc cron run <id>                — manual trigger
    mc cron daemon                  — run forever (60s check interval)

Schedule YAML format (config/schedules/*.yaml):
    id: weekly-legal-research
    intent: RESEARCH
    query: "Recent Delaware fiduciary duty case law updates"
    interval_minutes: 10080
    boundary: governed_external
    delivery: stdout
    approved_by: operator
    enabled: true
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class Schedule:
    """A governed scheduled task."""
    id: str
    intent: str
    query: str
    interval_minutes: int
    boundary: str = "governed_external"  # governed_external, local_only
    delivery: str = "stdout"             # stdout, file, telegram
    approved_by: str = ""
    enabled: bool = True
    last_run: Optional[float] = None
    run_count: int = 0


class CronSystem:
    """Manages and executes governed scheduled tasks."""

    def __init__(self, schedules_dir: Optional[Path] = None, artifacts_dir: Optional[Path] = None):
        self._schedules_dir = schedules_dir or Path(__file__).parent.parent / "config" / "schedules"
        self._artifacts_dir = artifacts_dir or Path(__file__).parent.parent / "memory" / "data" / "cron_artifacts"
        self._schedules_dir.mkdir(parents=True, exist_ok=True)
        self._artifacts_dir.mkdir(parents=True, exist_ok=True)
        self._state_file = self._artifacts_dir / "cron_state.json"

    def list_schedules(self) -> list[Schedule]:
        """Load all schedule YAML files."""
        schedules = []
        state = self._load_state()
        for yaml_file in sorted(self._schedules_dir.glob("*.yaml")):
            with open(yaml_file, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if not data or "id" not in data:
                continue
            sched = Schedule(
                id=data["id"],
                intent=data.get("intent", "RESEARCH"),
                query=data.get("query", ""),
                interval_minutes=data.get("interval_minutes", 60),
                boundary=data.get("boundary", "governed_external"),
                delivery=data.get("delivery", "stdout"),
                approved_by=data.get("approved_by", ""),
                enabled=data.get("enabled", True),
                last_run=state.get(data["id"], {}).get("last_run"),
                run_count=state.get(data["id"], {}).get("run_count", 0),
            )
            schedules.append(sched)
        return schedules

    def is_due(self, sched: Schedule) -> bool:
        """Check if a schedule is due to run."""
        if not sched.enabled:
            return False
        if sched.last_run is None:
            return True
        elapsed = (time.time() - sched.last_run) / 60
        return elapsed >= sched.interval_minutes

    async def run_schedule(self, sched: Schedule) -> dict:
        """Execute a single scheduled task through the pipeline."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from src.pipeline import Pipeline

        pipeline = Pipeline()

        # Override intent for local_only boundary
        intent = sched.intent
        if sched.boundary == "local_only":
            intent = "PROTECT"

        result = await pipeline.run(sched.query, intent=intent)

        # Store artifact
        artifact = {
            "schedule_id": sched.id,
            "timestamp": time.time(),
            "intent": intent,
            "query": sched.query,
            "classification": result.classification.riu_id,
            "confidence": result.path_record.confidence_at_exit,
            "external_called": result.external_called,
            "content": result.synthesis.content[:2000],
            "gap_signals": result.gap_signals,
            "steps": result.steps_executed,
        }

        artifact_path = self._artifacts_dir / f"{sched.id}_{int(time.time())}.json"
        with open(artifact_path, "w", encoding="utf-8") as f:
            json.dump(artifact, f, indent=2)

        # Update state
        self._update_state(sched.id)

        return artifact

    async def daemon(self, check_interval: int = 60):
        """Run forever, checking schedules every interval."""
        print(f"Mission Canvas cron daemon started (checking every {check_interval}s)")
        while True:
            schedules = self.list_schedules()
            for sched in schedules:
                if self.is_due(sched):
                    print(f"[cron] Running: {sched.id} ({sched.intent}: {sched.query[:50]}...)")
                    try:
                        artifact = await self.run_schedule(sched)
                        print(f"[cron] Done: {sched.id} → {artifact['classification']} "
                              f"(conf: {artifact['confidence']:.2f})")
                    except Exception as e:
                        print(f"[cron] Error: {sched.id} — {e}")
            await asyncio.sleep(check_interval)

    def _load_state(self) -> dict:
        if self._state_file.exists():
            with open(self._state_file, encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _update_state(self, schedule_id: str) -> None:
        state = self._load_state()
        if schedule_id not in state:
            state[schedule_id] = {"run_count": 0}
        state[schedule_id]["last_run"] = time.time()
        state[schedule_id]["run_count"] = state[schedule_id].get("run_count", 0) + 1
        with open(self._state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
