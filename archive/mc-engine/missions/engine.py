"""
Mission Canvas — Missions Engine

Multi-step workflow orchestration with state machine enforcement.
Missions coordinate calls, messages, and actions across bridges with
full audit trail, memory persistence, and retry logic.

Inspired by ClawTalk's mission pattern (MIT, Telnyx).
Rewritten from scratch for MC governance pipeline.

Use cases:
    - Tropical IT: Order follow-up workflows (9 countries, SMS/WhatsApp/email)
    - Komodo Health: Multi-provider outreach with structured data collection
    - Any client: Scheduled multi-step workflows with tracking

Usage:
    from lib.missions import MissionEngine, Mission, StepState

    engine = MissionEngine(store_dir="~/.mc/missions/")

    mission = engine.create(
        name="Q3 order followup",
        steps=[
            {"title": "Confirm receipt", "description": "SMS all 12 suppliers"},
            {"title": "Collect ETAs", "description": "Call non-responders"},
            {"title": "Report", "description": "Compile results to Slack"},
        ],
        mission_class="parallel_sweep",
    )

    engine.update_step(mission.slug, "confirm-receipt", StepState.IN_PROGRESS)
    engine.log_event(mission.slug, "sms_sent", {"to": "+573001234567", "status": "delivered"})
    engine.save_memory(mission.slug, "responses", [{"supplier": "Acme", "eta": "June 20"}])
    engine.update_step(mission.slug, "confirm-receipt", StepState.COMPLETED)
"""

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class StepState(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class MissionState(Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


# Valid state transitions (state machine enforcement)
VALID_TRANSITIONS = {
    StepState.PENDING: {StepState.IN_PROGRESS, StepState.SKIPPED},
    StepState.IN_PROGRESS: {StepState.COMPLETED, StepState.FAILED, StepState.SKIPPED},
    StepState.COMPLETED: set(),   # terminal
    StepState.FAILED: set(),      # terminal
    StepState.SKIPPED: set(),     # terminal
}

TERMINAL_STATES = {StepState.COMPLETED, StepState.FAILED, StepState.SKIPPED}

# Mission classes (determines execution strategy)
MISSION_CLASSES = {
    "parallel_sweep": "Same action to many targets. All at once, analyze after.",
    "parallel_screening": "Fan-out with scoring rubric. Rank results.",
    "sequential": "Serial execution. Each step depends on prior results.",
    "multi_round": "Distinct phases with approval gates between rounds.",
    "info_then_act": "Gather info, then act on it. Cancel when goal met.",
}


def _slugify(name: str) -> str:
    slug = re.sub(r'[^\w\s-]', '', name.lower())
    slug = re.sub(r'[\s_]+', '-', slug).strip('-')
    return slug[:50]


@dataclass
class Step:
    id: str
    title: str
    description: str = ""
    state: StepState = StepState.PENDING
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[str] = None


@dataclass
class Mission:
    slug: str
    name: str
    mission_class: str
    state: MissionState = MissionState.ACTIVE
    steps: List[Step] = field(default_factory=list)
    memory: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = ""
    completed_at: Optional[str] = None
    summary: Optional[str] = None


class MissionEngine:
    """Manages mission lifecycle, persistence, and state transitions."""

    def __init__(self, store_dir: Optional[str] = None):
        self.store_dir = Path(store_dir or os.path.expanduser("~/.mc/missions"))
        self.store_dir.mkdir(parents=True, exist_ok=True)

    def create(self, name: str, steps: List[Dict[str, str]],
               mission_class: str = "parallel_sweep") -> Mission:
        slug = _slugify(name)
        # Resume if exists
        existing = self.get(slug)
        if existing:
            return existing

        mission_steps = []
        for s in steps:
            step_id = _slugify(s["title"])
            mission_steps.append(Step(
                id=step_id,
                title=s["title"],
                description=s.get("description", ""),
            ))

        mission = Mission(
            slug=slug,
            name=name,
            mission_class=mission_class,
            steps=mission_steps,
            created_at=datetime.now().isoformat(),
        )
        self._save(mission)
        logger.info("[Mission] Created: %s (%d steps, class=%s)", slug, len(steps), mission_class)
        return mission

    def get(self, slug: str) -> Optional[Mission]:
        path = self.store_dir / f"{slug}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        return self._deserialize(data)

    def list_active(self) -> List[Mission]:
        missions = []
        for f in self.store_dir.glob("*.json"):
            data = json.loads(f.read_text())
            m = self._deserialize(data)
            if m.state == MissionState.ACTIVE:
                missions.append(m)
        return missions

    def update_step(self, slug: str, step_id: str, new_state: StepState,
                    result: Optional[str] = None) -> Dict[str, Any]:
        mission = self.get(slug)
        if not mission:
            return {"error": f"Mission {slug} not found"}

        step = next((s for s in mission.steps if s.id == step_id), None)
        if not step:
            return {"error": f"Step {step_id} not found in mission {slug}"}

        # Enforce state machine
        if new_state not in VALID_TRANSITIONS[step.state]:
            return {
                "error": f"Invalid transition: {step.state.value} → {new_state.value}",
                "valid": [s.value for s in VALID_TRANSITIONS[step.state]],
            }

        step.state = new_state
        if new_state == StepState.IN_PROGRESS:
            step.started_at = datetime.now().isoformat()
        if new_state in TERMINAL_STATES:
            step.completed_at = datetime.now().isoformat()
            step.result = result

        self._save(mission)
        return {"ok": True, "step": step_id, "state": new_state.value}

    def log_event(self, slug: str, event_type: str, data: Dict[str, Any] = None) -> bool:
        mission = self.get(slug)
        if not mission:
            return False
        mission.events.append({
            "type": event_type,
            "data": data or {},
            "timestamp": datetime.now().isoformat(),
        })
        # Cap event log
        if len(mission.events) > 500:
            mission.events = mission.events[-500:]
        self._save(mission)
        return True

    def save_memory(self, slug: str, key: str, value: Any) -> bool:
        mission = self.get(slug)
        if not mission:
            return False
        mission.memory[key] = value
        self._save(mission)
        return True

    def append_memory(self, slug: str, key: str, value: Any) -> bool:
        mission = self.get(slug)
        if not mission:
            return False
        if key not in mission.memory:
            mission.memory[key] = []
        if isinstance(mission.memory[key], list):
            mission.memory[key].append(value)
        self._save(mission)
        return True

    def get_memory(self, slug: str, key: str) -> Any:
        mission = self.get(slug)
        if not mission:
            return None
        return mission.memory.get(key)

    def complete(self, slug: str, summary: str = "") -> Dict[str, Any]:
        mission = self.get(slug)
        if not mission:
            return {"error": f"Mission {slug} not found"}

        # Check all steps are terminal
        non_terminal = [s for s in mission.steps if s.state not in TERMINAL_STATES]
        if non_terminal:
            return {
                "error": "Cannot complete: non-terminal steps remain",
                "pending": [{"id": s.id, "state": s.state.value} for s in non_terminal],
            }

        mission.state = MissionState.COMPLETED
        mission.completed_at = datetime.now().isoformat()
        mission.summary = summary
        self._save(mission)
        logger.info("[Mission] Completed: %s", slug)
        return {"ok": True, "slug": slug, "summary": summary}

    def cancel(self, slug: str, reason: str = "") -> Dict[str, Any]:
        mission = self.get(slug)
        if not mission:
            return {"error": f"Mission {slug} not found"}
        mission.state = MissionState.CANCELLED
        mission.completed_at = datetime.now().isoformat()
        mission.summary = f"Cancelled: {reason}"
        self._save(mission)
        return {"ok": True, "slug": slug}

    def status(self, slug: str) -> Optional[Dict[str, Any]]:
        mission = self.get(slug)
        if not mission:
            return None
        steps_summary = {}
        for state in StepState:
            count = sum(1 for s in mission.steps if s.state == state)
            if count:
                steps_summary[state.value] = count
        return {
            "slug": mission.slug,
            "name": mission.name,
            "class": mission.mission_class,
            "state": mission.state.value,
            "steps": steps_summary,
            "total_steps": len(mission.steps),
            "events": len(mission.events),
            "created_at": mission.created_at,
            "completed_at": mission.completed_at,
        }

    def _save(self, mission: Mission) -> None:
        path = self.store_dir / f"{mission.slug}.json"
        path.write_text(json.dumps(self._serialize(mission), indent=2))

    def _serialize(self, m: Mission) -> dict:
        return {
            "slug": m.slug, "name": m.name, "mission_class": m.mission_class,
            "state": m.state.value, "created_at": m.created_at,
            "completed_at": m.completed_at, "summary": m.summary,
            "steps": [{"id": s.id, "title": s.title, "description": s.description,
                       "state": s.state.value, "started_at": s.started_at,
                       "completed_at": s.completed_at, "result": s.result}
                      for s in m.steps],
            "memory": m.memory,
            "events": m.events,
        }

    def _deserialize(self, d: dict) -> Mission:
        steps = [Step(id=s["id"], title=s["title"], description=s.get("description", ""),
                      state=StepState(s["state"]), started_at=s.get("started_at"),
                      completed_at=s.get("completed_at"), result=s.get("result"))
                 for s in d.get("steps", [])]
        return Mission(
            slug=d["slug"], name=d["name"], mission_class=d.get("mission_class", ""),
            state=MissionState(d["state"]), steps=steps,
            memory=d.get("memory", {}), events=d.get("events", []),
            created_at=d.get("created_at", ""), completed_at=d.get("completed_at"),
            summary=d.get("summary"),
        )
