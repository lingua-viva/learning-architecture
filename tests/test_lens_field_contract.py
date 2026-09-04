"""The lens field contract — parity, resolution, the accounting invariant, and
every guard the contract introduces (each of these was watched FAILING under
sabotage in Rung 3 of dev/REPORT_LENS_FIELD_CONTRACT_2026-09-03.md).

The single most important assertion here is the accounting invariant: every
field that enters write_student_lens ends up in exactly one of
written_fields / review_required / unresolved_questions. That is what makes
"silently dropped" structurally impossible instead of currently absent.
"""

from __future__ import annotations

import pytest

from src.education.student_lens import (
    SUPPORT_CATEGORY_IDS,
    VALID_CEFR_DIMENSIONS,
    VALID_SUPPORT_BUCKETS,
    StudentLensStore,
)
from src.lingua_viva import lens_field_contract as contract
from src.lingua_viva.data_in_contracts import (
    STUDENT_LENS_FIELDS,
    ExtractedField,
    ExtractionResult,
)
from src.lingua_viva.docpipe.lens import PROFILE_FIELDS
from src.lingua_viva.docpipe.lens_extract import _LENS_FIELD_IDS
from src.lingua_viva.lens_field_contract import (
    LensContractError,
    MissingEssentialFieldError,
    read_for,
    requires,
    resolve,
)
from src.lingua_viva.student_lens_writer import write_student_lens


def _field(path, value, status="verified", chunks=("chunk-1",), confidence=0.9):
    return ExtractedField(
        field_path=path, value=value, confidence=confidence,
        supporting_chunk_ids=list(chunks), status=status,
    )


def _result(fields, source="report_card.txt"):
    return ExtractionResult(
        target_schema_id="student_lens", fields=fields,
        unresolved_questions=[], source_files=[source],
    )


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path))
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "lenses.db"))
    s = StudentLensStore(db_path=tmp_path / "lenses.db")
    s.create_lens(student_id="student-test", display_name="Test Student")
    yield s
    s.close()


def _write(store, fields, **kw):
    return write_student_lens(result=_result(fields), store=store,
                              hint={"student_id": "student-test"}, **kw)


# ---------------------------------------------------------------------------
# 1. The registry is the authority; the five lists agree with it (spec §2.3)
# ---------------------------------------------------------------------------

def test_every_students_column_is_declared_and_matches_the_schema(tmp_path):
    s = StudentLensStore(db_path=tmp_path / "cols.db")
    try:
        live = tuple(r[1] for r in s._conn.execute("PRAGMA table_info(students)"))
    finally:
        s.close()
    assert live == contract.STUDENT_COLUMNS, "students schema drifted from the contract's column pin"
    registry_paths = {spec.path for spec in contract.REGISTRY}
    undeclared = [c for c in live if c not in registry_paths
                  and c not in ("created_at", "updated_at", "deleted", "deleted_at")]
    assert undeclared == [], f"students columns with no registry entry: {undeclared}"


def test_student_lens_fields_all_resolve_in_the_registry():
    unresolved = [p for p in STUDENT_LENS_FIELDS if resolve(p) is None]
    assert unresolved == [], f"STUDENT_LENS_FIELDS names paths the registry does not declare: {unresolved}"


def test_support_category_ids_equal_the_registry_segment():
    spec = next(s for s in contract.REGISTRY if s.path == "support_profile.categories.{category}.{bucket}")
    assert tuple(spec.segments["category"]) == tuple(SUPPORT_CATEGORY_IDS)
    assert tuple(spec.segments["bucket"]) == tuple(VALID_SUPPORT_BUCKETS) + ("evidence",)


def test_lens_field_ids_and_profile_fields_each_have_a_declared_home():
    """The docpipe world (10 fields) and the store world (9 categories)
    disagree; every docpipe field must still resolve to a declared path,
    with the disagreement recorded in the note, not unified silently."""
    assert tuple(_LENS_FIELD_IDS) == tuple(PROFILE_FIELDS)
    for fid in _LENS_FIELD_IDS:
        path = fid if fid in ("academic_strengths", "personal_strengths") \
            else f"support_profile.categories.{fid}.evidence"
        r = resolve(path)
        assert r is not None, f"docpipe field {fid} has no declared path"
        if fid == "strategies_trialed":
            assert r.spec.rehome == {"category": "learning_and_cognition", "bucket": "open_questions"}
            assert "ruling A" in r.spec.note.lower() or "Ruling A" in r.spec.note
    only_in_store = sorted(set(SUPPORT_CATEGORY_IDS) - set(_LENS_FIELD_IDS))
    assert only_in_store == ["advanced_enrichment", "personal_context"]
    for cat in only_in_store:
        assert resolve(f"support_profile.categories.{cat}.evidence") is not None


def test_updatable_profile_fields_are_writable_scalars():
    for name in StudentLensStore.UPDATABLE_PROFILE_FIELDS:
        r = resolve(name)
        assert r is not None and r.spec.kind == "scalar" and r.writable, name
        assert r.spec.writer == "store:update_profile"


def test_every_writer_names_a_real_store_operation():
    for spec in contract.REGISTRY:
        if not spec.writer:
            continue
        kind, _, target = spec.writer.partition(":")
        if kind == "store":
            assert callable(getattr(StudentLensStore, target, None)), spec.path
        else:
            assert kind == "column" and target in contract.STUDENT_COLUMNS, spec.path


def test_registry_rejects_a_writer_that_does_not_exist(monkeypatch):
    """Sabotage row 2 (spec §6.1): pointing an entry at a missing store op must
    fail at validation time, not as an AttributeError during a write."""
    bad = contract.FieldSpec("campus", "scalar", "authored", "writable", writer="store:no_such_op")
    monkeypatch.setattr(contract, "REGISTRY", tuple(s for s in contract.REGISTRY if s.path != "campus") + (bad,))
    with pytest.raises(LensContractError, match="no_such_op"):
        contract._validate_registry()


def test_derived_fields_are_never_writable_except_through_the_observation_log():
    for spec in contract.REGISTRY:
        if spec.origin == "derived" and spec.status == "writable":
            assert spec.writer == "store:append_observation", spec.path


def test_ethos_is_declared_not_implemented_and_refuses_by_name(store):
    r = resolve("ethos_profile.traits.grit.evidence")
    assert r is not None and r.spec.status == "declared_not_implemented"
    out = _write(store, [_field("ethos_profile.traits.grit.evidence", "kept going")])
    assert out["written_fields"] == []
    assert any("ethos_profile.traits.grit.evidence" in q for q in out["unresolved_questions"])


# ---------------------------------------------------------------------------
# 2. Resolution is the only way in
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", [
    "cefr_snapshot.telepathy",
    "support_profile.categories.not_a_category.evidence",
    "support_profile.categories.learning_and_cognition.not_a_bucket",
    "support_profile.categories.learning_and_cognition",
    "favourite_colour",
])
def test_undeclared_paths_do_not_resolve(path):
    assert resolve(path) is None


def test_unknown_category_is_refused_by_name_not_dropped(store):
    """Baseline B4a: these three shapes fell out of the support_profile branch
    with a bare `continue` — absent from all three lists."""
    for path in (
        "support_profile.categories.not_a_category.evidence",
        "support_profile.categories.learning_and_cognition",
    ):
        out = _write(store, [_field(path, "x")])
        assert path not in out["written_fields"] and path not in out["review_required"]
        assert any(path in q for q in out["unresolved_questions"]), f"{path} vanished"


def test_unknown_bucket_is_a_refusal_not_an_exception(store):
    """Baseline B4a: this raised ValueError through the whole import."""
    path = "support_profile.categories.learning_and_cognition.not_a_bucket"
    out = _write(store, [_field("cefr_snapshot.reading", "A2"), _field(path, "x")])
    assert "cefr_snapshot.reading" in out["written_fields"], "one bad field voided the good one"
    assert any(path in q for q in out["unresolved_questions"])


def test_strategies_trialed_lands_and_says_where(store):
    """Baseline B4a: emitted at lens_extract.py:734, silently dropped. Ruling A:
    the bridge's mapping is declared and applied, and the result SAYS SO."""
    path = "support_profile.categories.strategies_trialed.evidence"
    out = _write(store, [_field(path, "checklist helped")])
    assert path in out["written_fields"]
    row = next(a for a in out["accounting"] if a["field_path"] == path)
    assert "learning_and_cognition.open_questions" in row["reason"]
    sp = store.get_support_profile("student-test")
    texts = [e["text"] for e in sp["categories"]["learning_and_cognition"]["open_questions"]]
    assert "checklist helped" in texts


def test_store_supported_paths_are_now_wired(store):
    """Baseline B4: four paths refused by name although the store had an
    operation for each. Wiring, not authoring."""
    out = _write(store, [
        _field("academic_strengths", "reading comprehension"),
        _field("personal_strengths", "curiosity"),
        _field("home_languages", ["it", "en"]),
        _field("learning_differences", ["dyslexia"]),
    ])
    assert set(out["written_fields"]) == {
        "academic_strengths", "personal_strengths", "home_languages", "learning_differences"
    }, out["unresolved_questions"]
    lens = store.get_lens("student-test")
    assert lens["home_languages"] == ["it", "en"]
    assert [e["text"] for e in lens["strengths_profile"]["academic_strengths"]] == ["reading comprehension"]


def test_display_name_refusal_says_it_was_used(store):
    out = _write(store, [_field("display_name", "Someone Else")])
    assert any("display_name" in q and "used to create" in q for q in out["unresolved_questions"])


# ---------------------------------------------------------------------------
# 3. THE ACCOUNTING INVARIANT (spec §2.4) — the deliverable
# ---------------------------------------------------------------------------

def _entered_and_accounted(out, fields):
    entered = [f.field_path for f in fields]
    assert len(out["accounting"]) == len(entered)
    for f in fields:
        p = f.field_path
        in_written = p in out["written_fields"]
        in_review = p in out["review_required"]
        in_refused = any(f"'{p}'" in q for q in out["unresolved_questions"])
        assert in_written or in_review or in_refused, f"{p} is absent from all three lists"


def test_every_field_that_enters_is_accounted_for_exactly_once(store):
    fields = [
        _field("cefr_snapshot.reading", "A2"),
        _field("cefr_snapshot.writing", "Z9"),                              # bad value
        _field("cefr_snapshot.telepathy", "A2"),                            # bad dimension
        _field("support_profile.categories.learning_and_cognition.evidence", "reads well"),
        _field("support_profile.categories.learning_and_cognition.evidence", "no refs", chunks=()),
        _field("support_profile.categories.strategies_trialed.evidence", "checklist"),
        _field("support_profile.categories.not_a_category.evidence", "x"),
        _field("support_profile.categories.learning_and_cognition.not_a_bucket", "x"),
        _field("support_profile.categories.communication_and_language.evidence", "maybe", status="needs_confirmation"),
        _field("ethos_profile.traits.grit.evidence", "kept going"),
        _field("academic_strengths", "reading"),
        _field("trauma_flag", True, status="needs_confirmation"),
        _field("display_name", "X"),
        _field("unclassified", "This raw sentence never got classified.", status="classify_failed"),
        _field("favourite_colour", "blue"),
        _field("home_languages", "not-a-list"),                             # validator refusal
    ]
    out = _write(store, fields)
    _entered_and_accounted(out, fields)
    n = len(fields)
    assert (len(out["written_fields"]) + len(out["review_required"])
            + sum(1 for a in out["accounting"] if a["outcome"] == "refused")) == n
    # the content-free note names the path, never the sentence
    assert all("raw sentence" not in q for q in out["unresolved_questions"])
    assert any("'unclassified'" in q for q in out["unresolved_questions"])


def test_every_declared_writable_path_is_accounted_for(store):
    """Feed the writer every concrete path the registry declares writable."""
    fields = []
    for p in contract.writable_paths():
        if p.startswith("cefr_snapshot."):
            fields.append(_field(p, "A2"))
        elif p in ("home_languages", "learning_differences"):
            fields.append(_field(p, ["x"]))
        elif p == "trauma_flag":
            fields.append(_field(p, True, status="needs_confirmation"))
        else:
            fields.append(_field(p, f"probe {p}"))
    out = _write(store, fields)
    _entered_and_accounted(out, fields)
    refused = [a for a in out["accounting"] if a["outcome"] == "refused"]
    assert refused == [], f"declared-writable paths refused: {[a['field_path'] for a in refused]}"


def test_a_bad_field_never_voids_the_document(store):
    out = _write(store, [
        _field("cefr_snapshot.reading", "A2"),
        _field("support_profile.categories.learning_and_cognition.not_a_bucket", "x"),
        _field("totally.unknown", "x"),
    ])
    assert "cefr_snapshot.reading" in out["written_fields"]
    assert store.get_lens("student-test")["cefr_snapshot"]["reading"] == "A2"


# ---------------------------------------------------------------------------
# 4. Idempotency — the same import applied twice writes once (baseline B5)
# ---------------------------------------------------------------------------

def test_reapplying_the_same_import_does_not_double_write(store):
    fields = [
        _field("cefr_snapshot.reading", "A2"),
        _field("support_profile.categories.learning_and_cognition.evidence", "reads well"),
        _field("support_profile.categories.learning_and_cognition.strengths", "inquirer"),
        _field("academic_strengths", "reading"),
        _field("grade_level", "G3"),
    ]
    first = _write(store, fields)
    second = _write(store, fields)
    assert set(first["written_fields"]) == set(second["written_fields"])
    lens = store.get_lens("student-test")
    cats = lens["support_profile"]["categories"]["learning_and_cognition"]
    assert len(cats["evidence"]) == 1 and len(cats["strengths"]) == 1
    assert len(lens["strengths_profile"]["academic_strengths"]) == 1
    obs = store.export_lens("student-test")["observations"]
    assert len([o for o in obs if o.get("cefr_dimension") == "reading"]) == 1
    assert any("already present" in a["reason"] for a in second["accounting"])


# ---------------------------------------------------------------------------
# 5. The OUT filter (spec §2.8) — an output can say what it did not have
# ---------------------------------------------------------------------------

def test_every_output_requirement_resolves():
    for output_id in contract.OUTPUT_REQUIREMENTS:
        for req in requires(output_id):
            assert resolve(req.path) is not None, (output_id, req.path)


def test_prepare_refuses_to_render_without_its_essential_field(store):
    lens = dict(store.get_lens("student-test"))
    lens.pop("rti_current_tier")
    with pytest.raises(MissingEssentialFieldError) as exc:
        read_for("prepare", lens)
    assert exc.value.missing == ["rti_current_tier"]


def test_prepare_says_what_it_did_not_have(store):
    """An output must be able to say what it did not have (spec §2.8.2)."""
    from src.education.content_differentiator import ContentDifferentiator

    lens = store.get_lens("student-test")   # cefr_snapshot all null
    report = read_for("prepare", lens)
    assert report["fields_missing"] == []
    assert report["fields_enriching_missing"] == ["cefr_snapshot"]
    assert list(report["fields_used"]) == ["rti_current_tier"]

    tiered = ContentDifferentiator().assign_tier_with_provenance(lens)
    assert tiered["tier"] == "foundational"           # the ruled default, and it is named
    assert tiered["fields_enriching_missing"] == ["cefr_snapshot"]
    assert ContentDifferentiator().assign_tier_for_student(lens) == "foundational"


def test_prepare_reports_fields_used_once_the_lens_has_them(store):
    from src.education.content_differentiator import ContentDifferentiator

    _write(store, [_field(f"cefr_snapshot.{d}", "A2") for d in VALID_CEFR_DIMENSIONS])
    lens = store.get_lens("student-test")
    report = read_for("prepare", lens)
    assert report["fields_enriching_missing"] == []
    assert set(report["fields_used"]) == {"rti_current_tier", "cefr_snapshot"}
    tiered = ContentDifferentiator().assign_tier_with_provenance(lens)
    assert tiered["tier"] == "on_track"
    assert set(tiered["fields_used"]) == {"rti_current_tier", "cefr_snapshot"}


def test_prepare_refuses_a_lens_shaped_dict_without_a_tier():
    from src.education.content_differentiator import ContentDifferentiator

    with pytest.raises(MissingEssentialFieldError):
        ContentDifferentiator().assign_tier_for_student({"cefr_snapshot": {"reading": "B2"}})


def test_unknown_output_is_an_error_not_silence():
    with pytest.raises(LensContractError):
        requires("no_such_output")


# ---------------------------------------------------------------------------
# 6. Producers and the bridge — drift fails a test (Rung 4 sweep)
# ---------------------------------------------------------------------------

def _producer_paths() -> dict[str, set[str]]:
    """Every path each producer in src/ can build, from the constants the
    producers read (baseline B2, scratch/b2_b3_count.py)."""
    from src.education.ethos import load_ethos
    from src.education.observation_capture import CATEGORY_SIGNALS

    out: dict[str, set[str]] = {}
    out["lens_extract:_extract_cefr"] = {f"cefr_snapshot.{d}" for d in VALID_CEFR_DIMENSIONS}
    out["lens_extract:heuristics"] = {
        "support_profile.categories.learning_and_cognition.evidence",
        "support_profile.categories.learning_and_cognition.strengths",
        "support_profile.categories.attendance_and_engagement.evidence",
    }
    out["lens_extract:_route_to_support_category"] = {
        f"support_profile.categories.{c}.evidence" for c in CATEGORY_SIGNALS
    }
    out["lens_extract:_route_to_ethos"] = {
        f"ethos_profile.traits.{t['id']}.evidence" for t in load_ethos()["traits"]
    }
    out["lens_extract:classify_failed"] = {"unclassified"}
    out["lens_extract:sentence_classify"] = {
        fid if fid in ("academic_strengths", "personal_strengths")
        else f"support_profile.categories.{fid}.evidence"
        for fid in _LENS_FIELD_IDS
    }
    out["extraction_engine+whole_doc_llm"] = set(STUDENT_LENS_FIELDS)
    return out


def test_every_producer_path_is_declared_in_the_registry():
    """A producer that can build a path the registry does not declare is the
    CEFR defect waiting to happen again. This is the drift alarm."""
    undeclared = {
        producer: sorted(p for p in paths if resolve(p) is None)
        for producer, paths in _producer_paths().items()
    }
    undeclared = {k: v for k, v in undeclared.items() if v}
    assert undeclared == {}, f"producers emit undeclared paths: {undeclared}"


def test_every_producer_path_has_a_named_home_or_a_named_refusal(store):
    """Feed every producer path through the writer once; none may be absent
    from all three lists (the accounting invariant over the producer set)."""
    all_paths = sorted(set().union(*_producer_paths().values()))
    fields = []
    for p in all_paths:
        if p.startswith("cefr_snapshot."):
            fields.append(_field(p, "A2"))
        elif p in ("home_languages", "learning_differences"):
            fields.append(_field(p, ["x"]))
        elif p == "trauma_flag":
            fields.append(_field(p, True, status="needs_confirmation"))
        elif p == "unclassified":
            fields.append(_field(p, "sentence", status="classify_failed"))
        else:
            fields.append(_field(p, f"probe {p}"))
    out = _write(store, fields)
    _entered_and_accounted(out, fields)


def test_bridge_targets_resolve_in_the_registry():
    """Ruling A: the docpipe->store bridge's mapping is declared as-is. Every
    store path the bridge writes must resolve, and strategies_trialed must
    resolve to the same re-home the bridge applies (docpipe/lens.py:434-446)."""
    from src.lingua_viva.docpipe.lens import SUPPORT_CATEGORY_FIELDS

    for fid in SUPPORT_CATEGORY_FIELDS:
        assert resolve(f"support_profile.categories.{fid}.evidence") is not None, fid
    for fid in ("academic_strengths", "personal_strengths"):
        r = resolve(fid)
        assert r is not None and r.spec.docpipe_field_id == fid
    r = resolve("support_profile.categories.strategies_trialed.open_questions")
    assert r is not None and r.spec.rehome["category"] == "learning_and_cognition"
    for bucket in ("strategies_worked", "strategies_not_worked", "open_questions"):
        assert resolve(f"support_profile.categories.learning_and_cognition.{bucket}") is not None
