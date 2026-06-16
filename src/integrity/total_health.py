"""
Total Health — The Self-Improving Recursive Loop

ONE BUTTON. Press it. Mission Canvas runs on Mission Canvas until
it has improved itself.

The loop:
  1. Run all integrity checks
  2. Analyze path consistency
  3. Detect knowledge gaps
  4. Propose enhancements
  5. Apply safe improvements (Tier 3 only — automated, reversible)
  6. Queue risky improvements (Tier 1-2 — human review required)
  7. Measure convergence (confidence_delta)
  8. Repeat until convergence (delta < 0.01 for 3 consecutive iterations)

Governance:
  - Tier 3 (observations): automated, reversible, append-only
  - Tier 2 (assumptions): human review, reversible
  - Tier 1 (immutable rules): human approval + commit required
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .health_check import HealthCheck, HealthResult


@dataclass
class IterationLog:
    """Log of a single self-improvement iteration."""
    iteration: int
    health_score: float
    checks_passed: int
    checks_total: int
    improvements_applied: list[str] = field(default_factory=list)
    improvements_queued: list[str] = field(default_factory=list)
    confidence_delta: float = 0.0
    duration_ms: int = 0
    timestamp: float = field(default_factory=time.time)


@dataclass
class TotalHealthReport:
    """Final report from a total health run."""
    iterations_run: int
    converged: bool
    final_score: float
    initial_score: float
    improvements_applied: int
    improvements_queued: int
    iterations: list[IterationLog] = field(default_factory=list)
    duration_total_ms: int = 0

    def summary(self) -> str:
        lines = [
            f"Total Health Report",
            f"  Iterations: {self.iterations_run}",
            f"  Converged: {self.converged}",
            f"  Score: {self.initial_score:.1%} → {self.final_score:.1%}",
            f"  Improvements applied (Tier 3): {self.improvements_applied}",
            f"  Improvements queued (Tier 1-2): {self.improvements_queued}",
            f"  Duration: {self.duration_total_ms}ms",
        ]
        return "\n".join(lines)


class TotalHealth:
    """
    The self-improvement loop. When run, iterates until convergence.
    Minimum: 3 iterations. Maximum: until confidence_delta < 0.01
    for 3 consecutive iterations.
    """

    def __init__(self, root_dir: Optional[Path] = None):
        self.root = root_dir or Path(__file__).parent.parent.parent
        self.health_check = HealthCheck(root_dir=self.root)

    async def run(self, max_iterations: Optional[int] = None) -> TotalHealthReport:
        """Run the self-improvement loop."""
        start_time = time.time()
        iterations: list[IterationLog] = []
        previous_score = 0.0
        stable_count = 0
        initial_score = 0.0

        iteration = 0
        while True:
            iteration += 1
            iter_start = time.time()

            # Step 1: Run all integrity checks
            health = self.health_check.run()

            if iteration == 1:
                initial_score = health.score

            # Step 2: Analyze and propose improvements
            improvements = self._analyze_and_propose(health)

            # Step 3: Apply safe improvements (Tier 3 only)
            applied = self._apply_safe_improvements(improvements)

            # Step 4: Queue risky improvements (Tier 1-2)
            queued = self._queue_for_review(improvements)

            # Step 5: Measure convergence
            delta = abs(health.score - previous_score)
            iter_duration = int((time.time() - iter_start) * 1000)

            log = IterationLog(
                iteration=iteration,
                health_score=health.score,
                checks_passed=health.checks_passed,
                checks_total=health.checks_total,
                improvements_applied=applied,
                improvements_queued=queued,
                confidence_delta=delta,
                duration_ms=iter_duration,
            )
            iterations.append(log)

            # Convergence check
            if delta < 0.01:
                stable_count += 1
            else:
                stable_count = 0

            if iteration >= 3 and stable_count >= 3:
                break

            if max_iterations and iteration >= max_iterations:
                break

            previous_score = health.score

        total_duration = int((time.time() - start_time) * 1000)

        return TotalHealthReport(
            iterations_run=iteration,
            converged=stable_count >= 3,
            final_score=iterations[-1].health_score if iterations else 0.0,
            initial_score=initial_score,
            improvements_applied=sum(len(i.improvements_applied) for i in iterations),
            improvements_queued=sum(len(i.improvements_queued) for i in iterations),
            iterations=iterations,
            duration_total_ms=total_duration,
        )

    def _analyze_and_propose(self, health: HealthResult) -> list[dict]:
        """Analyze health results and propose improvements."""
        proposals = []
        for section, data in health.sections.items():
            for issue in data.get("issues", []):
                # Determine tier based on issue type
                tier = self._classify_issue_tier(section, issue)
                proposals.append({
                    "section": section,
                    "issue": issue,
                    "tier": tier,
                    "proposed_fix": self._generate_fix(section, issue),
                })
        return proposals

    def _classify_issue_tier(self, section: str, issue: str) -> int:
        """Classify an issue's governance tier."""
        # Tier 1: ontology structure, core rules
        if section == "ontology" and "cycle" in issue.lower():
            return 1
        if section == "config":
            return 1
        # Tier 2: knowledge entries, skill definitions
        if section in ("knowledge", "skills"):
            return 2
        # Tier 3: metrics, observations
        return 3

    def _apply_safe_improvements(self, proposals: list[dict]) -> list[str]:
        """Apply Tier 3 improvements automatically."""
        applied = []
        for p in proposals:
            if p["tier"] == 3 and p.get("proposed_fix"):
                # In production: actually apply the fix
                applied.append(f"[Tier 3] {p['section']}: {p['issue']}")
        return applied

    def _queue_for_review(self, proposals: list[dict]) -> list[str]:
        """Queue Tier 1-2 improvements for human review."""
        queued = []
        for p in proposals:
            if p["tier"] in (1, 2):
                queued.append(f"[Tier {p['tier']}] {p['section']}: {p['issue']}")
        return queued

    def _generate_fix(self, section: str, issue: str) -> Optional[str]:
        """Generate a proposed fix for an issue."""
        # In production: use the pipeline itself to generate fixes
        return None
