"""
Tests for the school-ethos layer (ethos-as-data, lens-as-mechanism):

  - src/education/ethos.py — configurable taxonomy loader + built-in seed
  - student_lens.py v2.1 — strengths_profile + ethos_profile columns,
    add_profile_strength / add_ethos_evidence / export_ethos_report
  - observation_capture.py — suggestion-only wiring + teacher confirm path
  - lenses/education/school-ethos.yaml — keyword activation

Teacher review authority is the invariant under test throughout: nothing
model-suggested is ever auto-written to a profile or exported into a
report body.
"""

import os
import sqlite3

import pytest

from src.education import ethos
from src.education.observation_capture import ObservationCapturePipeline
from src.education.student_lens import (
    REPORT_GRADE_CONFIDENCE,
    StudentLensStore,
    ethos_profile_default,
    strengths_profile_default,
    _normalize_ethos_profile_with_warnings,
    _normalize_strengths_profile_with_warnings,
)


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "lens.db"))
    monkeypatch.setenv("LV_ETHOS_PATH", str(tmp_path / "ethos.yaml"))
    s = StudentLensStore()
    yield s
    s.close()


@pytest.fixture
def student(store):
    return store.create_lens(display_name="Test Student", grade_level="MYP5")


# ----------------------------------------------------------------------
# ethos.py — taxonomy loader + seed
# ----------------------------------------------------------------------


class TestEthosTaxonomy:
    def test_seed_is_valid(self):
        seed = ethos.ethos_seed()
        ethos.validate_ethos(seed)  # must not raise
        assert len(seed["traits"]) == 9
        groups = {t["group"] for t in seed["traits"]}
        assert groups == {"value", "learner_attribute"}

    def test_seed_has_still_i_rise_traits(self):
        ids = ethos.trait_ids(ethos.ethos_seed())
        assert {
            "self_worth",
            "self_discipline",
            "critical_thinking",
            "emotional_intelligence",
            "self_organization",
            "grit",
            "social_intelligence",
            "entrepreneurship",
            "integrity",
        } <= set(ids)

    def test_missing_file_falls_back_to_seed(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LV_ETHOS_PATH", str(tmp_path / "nope.yaml"))
        assert ethos.load_ethos() == ethos.ethos_seed()

    def test_env_seam_controls_path(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LV_ETHOS_PATH", str(tmp_path / "custom.yaml"))
        assert ethos.default_ethos_path() == tmp_path / "custom.yaml"

    def test_save_load_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LV_ETHOS_PATH", str(tmp_path / "ethos.yaml"))
        school = {
            "schema_version": 1,
            "ethos_name": "test_school",
            "traits": [
                {
                    "id": "resilience",
                    "label": "Resilience",
                    "group": "value",
                    "descriptor": "Keeps going after setbacks.",
                    "signal_keywords": ["resilient", "bounced back"],
                }
            ],
        }
        ethos.save_ethos(school)
        loaded = ethos.load_ethos()
        assert loaded["ethos_name"] == "test_school"
        assert ethos.trait_ids(loaded) == ("resilience",)

    def test_invalid_file_raises_not_silently_replaced(self, tmp_path, monkeypatch):
        p = tmp_path / "ethos.yaml"
        p.write_text("traits: broken")
        monkeypatch.setenv("LV_ETHOS_PATH", str(p))
        with pytest.raises(ethos.EthosValidationError):
            ethos.load_ethos()

    @pytest.mark.parametrize(
        "mutation",
        [
            {"schema_version": 99},
            {"ethos_name": ""},
            {"traits": []},
            {"traits": [{"id": "Bad-Id", "label": "x", "group": "value", "descriptor": "y"}]},
            {"traits": [{"id": "ok", "label": "", "group": "value", "descriptor": "y"}]},
            {"traits": [{"id": "ok", "label": "x", "group": "nope", "descriptor": "y"}]},
            {"traits": [{"id": "ok", "label": "x", "group": "value", "descriptor": ""}]},
        ],
    )
    def test_validation_rejects_bad_shapes(self, mutation):
        data = ethos.ethos_seed()
        data.update(mutation)
        with pytest.raises(ethos.EthosValidationError):
            ethos.validate_ethos(data)

    def test_validation_rejects_duplicate_ids(self):
        data = ethos.ethos_seed()
        data["traits"].append(dict(data["traits"][0]))
        with pytest.raises(ethos.EthosValidationError, match="duplicate"):
            ethos.validate_ethos(data)

    def test_match_traits_is_case_insensitive_and_suggestion_only(self):
        seed = ethos.ethos_seed()
        matched = ethos.match_traits("She showed empathy and kept trying today", seed)
        assert "emotional_intelligence" in matched
        assert "grit" in matched

    def test_match_traits_no_signal_no_match(self):
        assert ethos.match_traits("Completed the worksheet.", ethos.ethos_seed()) == []

    def test_format_traits_for_prompt_groups_traits(self):
        text = ethos.format_traits_for_prompt(ethos.ethos_seed())
        assert "Core values:" in text
        assert "Learner attributes:" in text
        assert "Self-Worth (self_worth):" in text


# ----------------------------------------------------------------------
# student_lens.py v2.1 — profiles, normalization, store methods
# ----------------------------------------------------------------------


class TestStudentLensV21:
    def test_new_lens_has_empty_v21_profiles(self, store, student):
        lens = store.get_lens(student)
        assert lens["strengths_profile"] == strengths_profile_default()
        assert lens["ethos_profile"] == ethos_profile_default()
        assert lens["strengths_profile_warnings"] == []
        assert lens["ethos_profile_warnings"] == []

    def test_add_profile_strength_both_kinds(self, store, student):
        store.add_profile_strength(student, "academic", "Strong essay structure", "t1")
        p = store.add_profile_strength(student, "personal", "Welcomes new students", "t1")
        assert len(p["academic_strengths"]) == 1
        assert len(p["personal_strengths"]) == 1
        entry = p["academic_strengths"][0]
        assert entry["confidence"] == "teacher_confirmed"
        assert entry["active"] is True

    def test_add_profile_strength_rejects_unknown_kind(self, store, student):
        with pytest.raises(ValueError, match="strength kind"):
            store.add_profile_strength(student, "social", "x", "t1")

    def test_add_ethos_evidence_against_seed(self, store, student):
        ep = store.add_ethos_evidence(
            student, "grit", "Kept trying after a difficult first attempt", "t1"
        )
        assert ep["ethos_name"] == "still_i_rise_seed"
        assert len(ep["traits"]["grit"]["evidence"]) == 1

    def test_add_ethos_evidence_rejects_unknown_trait(self, store, student):
        with pytest.raises(ValueError, match="Unknown ethos trait"):
            store.add_ethos_evidence(student, "not_a_trait", "x", "t1")

    def test_add_ethos_evidence_accepts_injected_taxonomy(self, store, student):
        ep = store.add_ethos_evidence(
            student, "custom", "school-specific trait", "t1",
            allowed_trait_ids=["custom"],
        )
        assert "custom" in ep["traits"]

    def test_writes_bump_profile_version(self, store, student):
        v0 = store.get_lens(student)["profile_version"]
        store.add_profile_strength(student, "academic", "x", "t1")
        store.add_ethos_evidence(student, "social_intelligence", "helped a peer", "t1")
        assert store.get_lens(student)["profile_version"] == v0 + 2

    def test_corrupt_columns_normalize_with_warnings(self, store, student):
        store._conn.execute(
            "UPDATE students SET ethos_profile='not json', strengths_profile='[]' "
            "WHERE student_id=?",
            (student,),
        )
        store._conn.commit()
        lens = store.get_lens(student)
        assert lens["ethos_profile"]["traits"] == {}
        assert lens["ethos_profile_warnings"]
        assert lens["strengths_profile"] == strengths_profile_default()
        assert lens["strengths_profile_warnings"]

    def test_normalizer_drops_invalid_trait_keys(self):
        raw = {"traits": {"Good-No": {"evidence": []}, "fine_id": {"evidence": []}}}
        normalized, warnings = _normalize_ethos_profile_with_warnings(raw)
        assert "fine_id" in normalized["traits"]
        assert "Good-No" not in normalized["traits"]
        assert warnings

    def test_strengths_normalizer_handles_none(self):
        normalized, warnings = _normalize_strengths_profile_with_warnings(None)
        assert normalized == strengths_profile_default()
        assert warnings == []

    def test_legacy_db_migration_adds_columns(self, tmp_path, monkeypatch):
        db = tmp_path / "legacy.db"
        conn = sqlite3.connect(db)
        conn.execute(
            """CREATE TABLE students (
            student_id TEXT PRIMARY KEY, display_name TEXT, campus TEXT,
            grade_level TEXT, home_languages TEXT NOT NULL DEFAULT '[]',
            learning_differences TEXT NOT NULL DEFAULT '[]',
            trauma_flag INTEGER NOT NULL DEFAULT 0,
            avoid_pairing_with TEXT NOT NULL DEFAULT '[]',
            rti_current_tier INTEGER NOT NULL DEFAULT 1,
            rti_tier_history TEXT NOT NULL DEFAULT '[]',
            cefr_snapshot TEXT NOT NULL DEFAULT '{}',
            cefr_trajectory_30d TEXT NOT NULL DEFAULT 'insufficient_data',
            sel_summary TEXT NOT NULL DEFAULT '{}',
            support_profile TEXT NOT NULL DEFAULT '{}',
            profile_version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            deleted INTEGER NOT NULL DEFAULT 0, deleted_at TEXT)"""
        )
        conn.execute(
            "INSERT INTO students (student_id, created_at, updated_at) "
            "VALUES ('s1','t','t')"
        )
        conn.commit()
        conn.close()
        monkeypatch.setenv("LV_STUDENT_DB_PATH", str(db))
        monkeypatch.setenv("LV_ETHOS_PATH", str(tmp_path / "ethos.yaml"))
        s = StudentLensStore()
        try:
            lens = s.get_lens("s1")
            assert lens["ethos_profile"]["traits"] == {}
            s.add_profile_strength("s1", "academic", "migrated fine", "t1")
        finally:
            s.close()


# ----------------------------------------------------------------------
# observation_capture.py — suggestion-only wiring, teacher authority
# ----------------------------------------------------------------------


class TestCaptureWiring:
    @pytest.fixture
    def pipe(self, store):
        return ObservationCapturePipeline(store)

    def test_capture_returns_suggestions_never_auto_writes(self, store, student, pipe):
        r = pipe.capture(
            student_id=student,
            teacher_id="t1",
            raw_transcript=(
                "She kept trying today, volunteered first and showed real "
                "empathy in the group work."
            ),
            template_type="sel_positive",
            sel_domain="confidence",
            sel_valence="positive",
        )
        sugs = r["ethos_trait_suggestions"]
        assert {"grit", "emotional_intelligence", "social_intelligence"} <= {
            s["trait_id"] for s in sugs
        }
        for s in sugs:
            assert s["confidence"] == "model_suggested"
            assert s["status"] == "pending_teacher_confirmation"
        # THE invariant: nothing written to the profile without a teacher
        assert store.get_lens(student)["ethos_profile"]["traits"] == {}

    def test_confirm_writes_teacher_confirmed_with_source(self, store, student, pipe):
        r = pipe.capture(
            student_id=student,
            teacher_id="t1",
            raw_transcript="Kept trying while presenting to the class.",
            template_type="sel_positive",
        )
        obs_id = r["observation"]["observation_id"]
        ep = pipe.confirm_ethos_suggestion(
            student, "t1", "grit",
            "Presented to the whole class despite visible nerves.",
            observation_id=obs_id,
        )
        ev = ep["traits"]["grit"]["evidence"][0]
        assert ev["confidence"] == "teacher_confirmed"
        assert ev["source_observation_id"] == obs_id

    def test_broken_taxonomy_never_breaks_capture(self, store, student, pipe):
        with open(os.environ["LV_ETHOS_PATH"], "w") as f:
            f.write("traits: broken")
        r = pipe.capture(
            student_id=student,
            teacher_id="t1",
            raw_transcript="Read aloud with more fluency this week.",
            template_type="literacy",
        )
        assert r["observation"]["observation_id"]
        assert r["ethos_trait_suggestions"][0]["status"] == "taxonomy_error"


# ----------------------------------------------------------------------
# export_ethos_report — report-grade evidence only
# ----------------------------------------------------------------------


class TestEthosReport:
    def test_report_includes_only_report_grade_confidence(self, store, student):
        assert "model_suggested" not in REPORT_GRADE_CONFIDENCE
        store.add_ethos_evidence(
            student, "grit", "Confirmed persistence moment", "t1",
            confidence="teacher_confirmed",
        )
        store.add_ethos_evidence(
            student, "grit", "Unconfirmed model guess", "t1",
            confidence="model_suggested",
        )
        store.add_profile_strength(
            student, "academic", "Confirmed strength", "t1"
        )
        store.add_profile_strength(
            student, "personal", "Needs confirmation", "t1",
            confidence="imported_needs_confirmation",
        )
        report = store.export_ethos_report(student)
        assert report["display_name"] == "Test Student"
        [trait] = report["traits"]
        assert trait["trait_id"] == "grit"
        assert trait["label"] == "Grit"
        assert [e["summary"] for e in trait["evidence"]] == ["Confirmed persistence moment"]
        assert [e["text"] for e in report["academic_strengths"]] == ["Confirmed strength"]
        assert report["personal_strengths"] == []
        assert "pending_review" not in report

    def test_include_unconfirmed_surfaces_pending_separately(self, store, student):
        store.add_ethos_evidence(
            student, "social_intelligence", "Model-flagged peer support", "t1",
            confidence="model_suggested",
        )
        report = store.export_ethos_report(student, include_unconfirmed=True)
        assert report["traits"] == []  # never in the report body
        [pending] = report["pending_review"]["traits"]
        assert pending["trait_id"] == "social_intelligence"
        assert pending["items"][0]["confidence"] == "model_suggested"

    def test_report_degrades_to_trait_ids_on_broken_taxonomy(self, store, student):
        store.add_ethos_evidence(student, "grit", "Confirmed", "t1")
        with open(os.environ["LV_ETHOS_PATH"], "w") as f:
            f.write("traits: broken")
        report = store.export_ethos_report(student)
        [trait] = report["traits"]
        assert trait["label"] == "grit"  # id fallback, export never blocked

    def test_traits_with_no_confirmed_evidence_are_omitted(self, store, student):
        store.add_ethos_evidence(
            student, "integrity", "guess", "t1", confidence="model_suggested"
        )
        assert store.export_ethos_report(student)["traits"] == []


# ----------------------------------------------------------------------
# Hardening pass (2026-07-27): every case below reproduces a defect found
# by adversarial probing of the first build, then fixed.
# ----------------------------------------------------------------------


class TestHardening:
    def test_match_traits_word_boundaries_kill_substring_false_positives(self):
        seed = ethos.ethos_seed()
        # measured false positives under plain substring matching:
        assert ethos.match_traits("He was scared during the drill", seed) == []
        assert ethos.match_traits("She is careless with homework", seed) == []
        assert ethos.match_traits("He played goalkeeper today", seed) == []
        assert ethos.match_traits("Drew a portrait in art class", seed) == []
        # true positives still match:
        assert "social_intelligence" in ethos.match_traits("Showed peer support", seed)
        assert "self_discipline" in ethos.match_traits("Showed follow-through this term", seed)

    def test_match_traits_unicode_text_safe(self):
        seed = ethos.ethos_seed()
        assert ethos.match_traits("È stata molto resourceful oggi!", seed) == ["entrepreneurship"]
        assert ethos.match_traits("Ha mostrato coraggio", seed) == []

    def test_report_excludes_items_missing_confidence_field(self, store, student):
        import json

        store._conn.execute(
            "UPDATE students SET ethos_profile=? WHERE student_id=?",
            (
                json.dumps(
                    {
                        "traits": {
                            "bravery": {
                                "evidence": [
                                    {"summary": "no confidence field", "created_by": "x"}
                                ]
                            }
                        }
                    }
                ),
                student,
            ),
        )
        store._conn.commit()
        # fail-closed: ungoverned items never reach a report body
        assert store.export_ethos_report(student)["traits"] == []

    def test_non_dict_list_items_dropped_export_survives(self, store, student):
        import json

        store._conn.execute(
            "UPDATE students SET ethos_profile=?, strengths_profile=? "
            "WHERE student_id=?",
            (
                json.dumps({"traits": {"bravery": {"evidence": ["not a dict"]}}}),
                json.dumps({"academic_strengths": [42]}),
                student,
            ),
        )
        store._conn.commit()
        report = store.export_ethos_report(student)
        assert report["traits"] == []
        assert report["academic_strengths"] == []
        lens = store.get_lens(student)
        assert any("non-object" in w for w in lens["ethos_profile_warnings"])
        assert any("non-object" in w for w in lens["strengths_profile_warnings"])

    def test_confirm_rejects_forged_or_cross_student_observation(self, store, student):
        pipe = ObservationCapturePipeline(store)
        other = store.create_lens(display_name="Other")
        r = pipe.capture(
            student_id=other,
            teacher_id="t1",
            raw_transcript="Kept trying.",
            template_type="sel_positive",
        )
        other_obs = r["observation"]["observation_id"]
        with pytest.raises(ValueError, match="unverifiable source"):
            pipe.confirm_ethos_suggestion(
                student, "t1", "grit", "s", observation_id="forged-id"
            )
        with pytest.raises(ValueError, match="unverifiable source"):
            pipe.confirm_ethos_suggestion(
                student, "t1", "grit", "s", observation_id=other_obs
            )

    def test_oversized_ethos_file_refused(self, tmp_path, monkeypatch):
        p = tmp_path / "huge.yaml"
        p.write_text("x" * (ethos.MAX_ETHOS_FILE_BYTES + 1))
        monkeypatch.setenv("LV_ETHOS_PATH", str(p))
        with pytest.raises(ethos.EthosValidationError, match="refusing to parse"):
            ethos.load_ethos()

    def test_keyword_length_cap(self):
        bad = ethos.ethos_seed()
        bad["traits"][0]["signal_keywords"] = ["k" * (ethos.MAX_KEYWORD_LEN + 1)]
        with pytest.raises(ethos.EthosValidationError):
            ethos.validate_ethos(bad)

    def test_save_ethos_atomic_no_tmp_residue(self, tmp_path, monkeypatch):
        p = tmp_path / "ethos.yaml"
        monkeypatch.setenv("LV_ETHOS_PATH", str(p))
        ethos.save_ethos(ethos.ethos_seed())
        assert p.exists()
        assert list(tmp_path.glob("*.tmp")) == []

    def test_evidence_and_strengths_stripped_and_idempotent(self, store, student):
        p1 = store.add_ethos_evidence(student, "grit", "  Presented first.  ", "t1")
        assert p1["traits"]["grit"]["evidence"][0]["summary"] == "Presented first."
        v1 = store.get_lens(student)["profile_version"]
        p2 = store.add_ethos_evidence(student, "grit", "Presented first.", "t1")
        assert len(p2["traits"]["grit"]["evidence"]) == 1
        assert store.get_lens(student)["profile_version"] == v1
        store.add_profile_strength(student, "academic", " Strong writer ", "t1")
        s = store.add_profile_strength(student, "academic", "Strong writer", "t1")
        assert len(s["academic_strengths"]) == 1

    def test_unreadable_taxonomy_degrades_capture_not_crashes(
        self, store, student, tmp_path, monkeypatch
    ):
        # a directory at the taxonomy path raises OSError, not
        # EthosValidationError — capture must degrade identically
        bad = tmp_path / "ethos_dir.yaml"
        bad.mkdir()
        monkeypatch.setenv("LV_ETHOS_PATH", str(bad))
        pipe = ObservationCapturePipeline(store)
        r = pipe.capture(
            student_id=student,
            teacher_id="t1",
            raw_transcript="Read fluently.",
            template_type="literacy",
        )
        assert r["observation"]["observation_id"]
        assert r["ethos_trait_suggestions"][0]["status"] == "taxonomy_error"


# ----------------------------------------------------------------------
# school-ethos lens
# ----------------------------------------------------------------------


class TestSchoolEthosLens:
    def test_lens_loads_and_activates_on_keywords(self):
        from lenses import LensEngine

        engine = LensEngine()
        lens = engine.get_lens("school-ethos")
        assert lens is not None
        active = engine.get_active_lenses(
            query="Record this as report evidence for the student report"
        )
        assert any(l.name == "school-ethos" for l in active)

    def test_lens_does_not_activate_without_signal(self):
        from lenses import LensEngine

        engine = LensEngine()
        active = engine.get_active_lenses(query="What time is the staff meeting?")
        assert not any(l.name == "school-ethos" for l in active)

    def test_lens_modifier_preserves_teacher_authority(self):
        from lenses import LensEngine

        lens = LensEngine().get_lens("school-ethos")
        assert "model_suggested" in lens.system_prompt_modifier
        assert "teacher" in lens.system_prompt_modifier.lower()
