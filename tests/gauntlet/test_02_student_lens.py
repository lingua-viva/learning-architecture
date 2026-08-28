"""Gauntlet phase 2 — student lenses + observation capture.

Import created 19 lenses (conftest gauntlet_env). This phase pins that the
lens layer holds them faithfully: capture, dedup, append-only history,
trend inputs, and the real_anon observation fixtures round-tripping through
the store.
"""

from __future__ import annotations

import json

import pytest

from src.education.student_lens import (
    LensNotFoundError,
    Observation,
    StudentLensStore,
)

from .conftest import EXPECTED_STUDENTS, REAL_ANON_DIR, TEACHER_ID

# --- roster state ------------------------------------------------------------


def test_one_lens_per_labeled_student(gauntlet_env):
    lenses = gauntlet_env["store"].list_lenses()
    names = [lens["display_name"] for lens in lenses]
    assert sorted(names) == sorted(EXPECTED_STUDENTS)
    assert len(lenses) == 19


def test_student_ids_are_unique(gauntlet_env):
    ids = list(gauntlet_env["student_ids"].values())
    assert len(ids) == len(set(ids)) == 19


def test_lens_lookup_by_id_returns_the_right_student(gauntlet_env):
    store = gauntlet_env["store"]
    for name, sid in gauntlet_env["student_ids"].items():
        assert store.get_lens(sid)["display_name"] == name


def test_unknown_student_id_raises_not_silently_creates(gauntlet_env):
    with pytest.raises(LensNotFoundError):
        gauntlet_env["store"].get_lens("no-such-student")


# --- observation capture -----------------------------------------------------


def test_seeded_observations_are_on_marcos_lens(gauntlet_env):
    lens = gauntlet_env["store"].export_lens(gauntlet_env["marco_id"])
    observations = lens["observations"]
    assert len(observations) == 3
    assert {o["template_type"] for o in observations} == {"cefr", "sel_positive"}
    assert all(o["teacher_id"] == TEACHER_ID for o in observations)


def test_capture_appends_without_touching_prior_observations(gauntlet_env):
    store = gauntlet_env["store"]
    sid = gauntlet_env["student_ids"]["Nora Rossi"]
    first = store.append_observation(
        Observation(
            student_id=sid,
            teacher_id=TEACHER_ID,
            template_type="general",
            raw_transcript="Chose the Italian picture book at free reading time.",
        )
    )
    before = [o["observation_id"] for o in store.export_lens(sid)["observations"]]
    store.append_observation(
        Observation(
            student_id=sid,
            teacher_id=TEACHER_ID,
            template_type="general",
            raw_transcript="Retold the story ending to a partner in Italian.",
        )
    )
    after = store.export_lens(sid)["observations"]
    assert len(after) == len(before) + 1
    assert set(before) <= {o["observation_id"] for o in after}
    assert first["observation"]["observation_id"] in {o["observation_id"] for o in after}


def test_duplicate_transcript_within_window_is_deduplicated(gauntlet_env):
    store = gauntlet_env["store"]
    sid = gauntlet_env["student_ids"]["Sara Conti"]
    transcript = "Asked for the word for 'butterfly' and used it twice."

    def obs():
        return Observation(
            student_id=sid,
            teacher_id=TEACHER_ID,
            template_type="general",
            raw_transcript=transcript,
        )

    first = store.append_observation(obs(), duplicate_window_seconds=300)
    second = store.append_observation(obs(), duplicate_window_seconds=300)
    assert not first.get("duplicate")
    assert second["duplicate"] is True
    assert (
        second["observation"]["observation_id"]
        == first["observation"]["observation_id"]
    )
    # only one row landed
    rows = [
        o
        for o in store.export_lens(sid)["observations"]
        if o["raw_transcript"] == transcript
    ]
    assert len(rows) == 1


def test_same_transcript_for_a_different_student_is_not_deduplicated(gauntlet_env):
    """Dedup is keyed per student — two students doing the same thing is two
    observations, not a duplicate."""
    store = gauntlet_env["store"]
    transcript = "Counted to twenty in Italian without prompting."
    r1 = store.append_observation(
        Observation(
            student_id=gauntlet_env["student_ids"]["Luca Ferri"],
            teacher_id=TEACHER_ID,
            template_type="general",
            raw_transcript=transcript,
        ),
        duplicate_window_seconds=300,
    )
    r2 = store.append_observation(
        Observation(
            student_id=gauntlet_env["student_ids"]["Emma Longo"],
            teacher_id=TEACHER_ID,
            template_type="general",
            raw_transcript=transcript,
        ),
        duplicate_window_seconds=300,
    )
    assert not r1.get("duplicate")
    assert not r2.get("duplicate")


def test_cefr_observation_requires_valid_dimension_and_level(gauntlet_env):
    obs = Observation(
        student_id=gauntlet_env["marco_id"],
        teacher_id=TEACHER_ID,
        template_type="cefr",
        raw_transcript="test",
        cefr_dimension="telepathy",
        cefr_level_observed="Z9",
    )
    errors = obs.validate()
    assert any("cefr_dimension" in e for e in errors)
    assert any("cefr_level_observed" in e for e in errors)


def test_observation_lands_on_the_named_student_only(gauntlet_env):
    """An observation about one student must never bleed onto another lens."""
    store = gauntlet_env["store"]
    sid = gauntlet_env["student_ids"]["Diego Marchetti"]
    transcript = "Gauntlet isolation probe for Diego's lens only."
    store.append_observation(
        Observation(
            student_id=sid,
            teacher_id=TEACHER_ID,
            template_type="general",
            raw_transcript=transcript,
        )
    )
    for name, other_sid in gauntlet_env["student_ids"].items():
        transcripts = [
            o["raw_transcript"]
            for o in store.export_lens(other_sid)["observations"]
        ]
        if other_sid == sid:
            assert transcript in transcripts
        else:
            assert transcript not in transcripts, name


# --- lens snapshot reflects observation history ------------------------------


def test_marco_cefr_snapshot_shows_latest_speaking_level(gauntlet_env):
    lens = gauntlet_env["store"].get_lens(gauntlet_env["marco_id"])
    snapshot = lens["cefr_snapshot"]
    assert snapshot["speaking"] is not None
    assert "A2" in json.dumps(snapshot["speaking"])


def test_unseeded_student_has_empty_history(gauntlet_env):
    lens = gauntlet_env["store"].export_lens(gauntlet_env["student_ids"]["Oscar Sanna"])
    assert lens["observations"] == []


# --- real_anon fixtures round-trip -------------------------------------------

# tests/fixtures/docpipe/real_anon/ holds anonymized records derived from real
# people and is gitignored (.gitignore:40) — deliberately never committed. It
# is therefore absent in every clone and in CI, where these two tests can only
# ever error on a missing file. Skipping when the directory is absent keeps the
# coverage on machines that hold the fixtures while stopping the pair from
# reporting as failures everywhere else: this is precisely the gap between the
# "81/81" recorded on the authoring machine and the 78/81 a clean clone gets.
_REAL_ANON_PRESENT = (REAL_ANON_DIR / "observation_aron.json").exists()
requires_real_anon = pytest.mark.skipif(
    not _REAL_ANON_PRESENT,
    reason="real_anon fixtures are gitignored and absent in this clone",
)


def _real_anon_observations() -> list[dict]:
    return [
        json.loads((REAL_ANON_DIR / f"observation_{who}.json").read_text(encoding="utf-8"))
        for who in ("aron", "jerry")
    ]


@requires_real_anon
def test_real_anon_observation_fixtures_are_fully_anonymized():
    """The anonymization key (real_anon/README.md) maps real people to Aron
    Park / Jerry Park / Ponte Academy / Federica Baldi. The fixtures must
    contain only the anonymized names — pinned by schema presence, and by
    the roster names never appearing."""
    for obs in _real_anon_observations():
        blob = json.dumps(obs)
        for name in EXPECTED_STUDENTS:
            assert name not in blob
        assert obs["raw_transcript"].strip()
        assert obs["student_id"].strip()


@requires_real_anon
def test_real_anon_observations_import_into_a_fresh_store(tmp_path):
    """Anonymized real observations must flow through the same capture path
    as live ones — same fields, same append semantics."""
    with StudentLensStore(db_path=tmp_path / "real_anon.db") as store:
        ids: dict[str, str] = {}
        for who, grade in (("Aron Park", "G4"), ("Jerry Park", "G7")):
            ids[who.split()[0].lower()] = store.create_lens(
                display_name=who, grade_level=grade
            )
        for who, obs in zip(("aron", "jerry"), _real_anon_observations()):
            result = store.append_observation(
                Observation(
                    student_id=ids[who],
                    teacher_id=obs.get("created_by") or "t-federica",
                    template_type="general",
                    raw_transcript=obs["raw_transcript"],
                )
            )
            assert result["validation_errors"] == []
        for who in ("aron", "jerry"):
            lens = store.export_lens(ids[who])
            assert len(lens["observations"]) == 1
