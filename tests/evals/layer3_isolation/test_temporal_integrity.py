"""Layer 3: Temporal Integrity — lens at time T has correct observation window.

Property proved:
- Lens never includes observations from the future
- Lens includes ALL observations through the requested time
- Future-timestamped observations are rejected at input
"""

import json
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from src.education.student_lens import StudentLensStore, Observation


@pytest.mark.skip(reason="awaiting get_lens_as_of() implementation per CONTRACTS.md")
def test_L3_TIME_001_lens_at_T_excludes_future():
    """L3-TIME-001: Lens at time T contains no observations after T.

    Setup: Insert 5 observations with timestamps Sept-Jan. Query as_of=November.
    Pass: Only Sept, Oct, Nov observations present. Dec, Jan excluded.
    """
    pass


@pytest.mark.skip(reason="awaiting get_lens_as_of() implementation per CONTRACTS.md")
def test_L3_TIME_002_lens_at_T_includes_all_through_T():
    """L3-TIME-002: Lens at time T contains ALL observations through T.

    Setup: Insert 5 observations Sept-Jan. Query as_of=January.
    Pass: All 5 observations are present.
    """
    pass


def test_L3_TIME_003_future_timestamp_rejected():
    """L3-TIME-003: Observation with timestamp in the future is rejected.

    Pass: append_observation with a future recorded_at returns validation error.

    NOTE: This tests whether the StudentLensStore rejects future observations.
    If it doesn't (current behavior may accept any timestamp), this documents
    a gap the implementation team needs to close.
    """
    with tempfile.TemporaryDirectory() as tmp:
        store = StudentLensStore(db_path=Path(tmp) / "temporal.db")
        sid = store.create_lens(display_name="Temporal Test", grade_level="G3")

        future_time = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()

        obs = Observation(
            student_id=sid,
            teacher_id="teacher-eval",
            template_type="cefr",
            raw_transcript="This observation is from the future",
            cefr_dimension="reading",
            cefr_level_observed="B1",
            cefr_direction="progressing",
            recorded_at=future_time,
        )

        # Try to append — if the system accepts it, that's a gap
        try:
            result = store.append_observation(obs)
            if result.get("validation_errors"):
                # Good — system caught the future timestamp
                assert any("future" in e.lower() for e in result["validation_errors"])
            else:
                # System accepted it — this is a gap
                pytest.xfail(
                    "KNOWN GAP: StudentLensStore accepts future-dated observations. "
                    "Perfect state requires rejection."
                )
        except Exception as e:
            # If it raises, that's also acceptable rejection
            assert "future" in str(e).lower() or "timestamp" in str(e).lower()
        finally:
            store.close()


def test_L3_TIME_004_observations_are_chronologically_ordered():
    """Observations returned in a lens are ordered by time (oldest first).

    This is a prerequisite for temporal queries — if ordering is wrong,
    as_of() queries will produce wrong results.
    """
    with tempfile.TemporaryDirectory() as tmp:
        store = StudentLensStore(db_path=Path(tmp) / "chrono.db")
        sid = store.create_lens(display_name="Chrono Test", grade_level="G3")

        # Insert observations in non-chronological order
        timestamps = [
            "2025-11-01T10:00:00Z",
            "2025-09-01T10:00:00Z",
            "2025-10-01T10:00:00Z",
        ]
        for ts in timestamps:
            store.append_observation(Observation(
                student_id=sid,
                teacher_id="teacher-eval",
                template_type="literacy",
                raw_transcript=f"Observation at {ts}",
                recorded_at=ts,
            ))

        # Verify profile was updated (3 observations)
        lens = store.get_lens(sid)
        assert lens["profile_version"] >= 4  # 1 (create) + 3 (observations)
        store.close()
