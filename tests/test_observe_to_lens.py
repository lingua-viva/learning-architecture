"""Observe (U4) writes through the lens field contract on a real comment.

Rung 3.2 of dev/REPORT_LENS_FIELD_CONTRACT_2026-09-03.md. The comment goes
through the SAME routing the report-card path uses (extract_for_lens_update)
and the SAME writer (write_student_lens), so every candidate field is
resolved through lens_field_contract.resolve(), gets the same refusal
semantics and the same accounting invariant, and carries provenance that
says it came from a teacher's note.

No local model is required: without one the sentence classifier reports
classify_failed and those sentences are refused BY NAME, never dropped —
which is itself the property under test.
"""

from __future__ import annotations

import pytest

from src.education.student_lens import StudentLensStore
from src.lingua_viva.lens_field_contract import resolve
from src.lingua_viva.observe_to_lens import observe_comment_to_lens_sync

COMMENT = (
    "Abigail finished early again today and could benefit from extension "
    "activities. Listening: A2. She needs sentence starters for extended "
    "writing tasks and was distracted during independent work."
)


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path))
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "lenses.db"))
    s = StudentLensStore(db_path=tmp_path / "lenses.db")
    s.create_lens(student_id="student-abigail", display_name="Abigail Chang")
    yield s
    s.close()


def _observe(store, text=COMMENT, **kw):
    return observe_comment_to_lens_sync(
        text, student_id="student-abigail", display_name="Abigail Chang",
        teacher_id="teacher:test", store=store, **kw,
    )


def test_every_candidate_field_is_accounted_for(store):
    out = _observe(store)
    candidates = out["candidate_fields"]
    assert candidates, "the routing proposed nothing for a comment with clear signals"
    assert len(out["accounting"]) == len(candidates)
    for c in candidates:
        p = c["field_path"]
        assert (
            p in out["written_fields"]
            or p in out["review_required"]
            or any(f"'{p}'" in q for q in out["unresolved_questions"])
        ), f"{p} is absent from all three lists"


def test_every_candidate_path_resolves_or_is_refused_by_name(store):
    out = _observe(store)
    for c in out["candidate_fields"]:
        if resolve(c["field_path"]) is None:
            assert any(f"'{c['field_path']}'" in q for q in out["unresolved_questions"])


def test_cefr_from_a_comment_reaches_the_lens_with_teacher_note_provenance(store):
    out = _observe(store)
    assert "cefr_snapshot.listening" in out["written_fields"], out["unresolved_questions"]
    lens = store.export_lens("student-abigail")
    assert lens["cefr_snapshot"]["listening"] == "A2"
    cefr_obs = [o for o in lens["observations"] if o.get("cefr_dimension") == "listening"]
    assert len(cefr_obs) == 1
    assert cefr_obs[0]["source_type"] == "teacher_note"
    assert out["source"].startswith("observe:teacher:test:")


def test_unsure_routing_waits_for_the_teacher(store):
    """Automatic routing must never silently become a confirmed fact
    (plan §2.3, R4). needs_confirmation candidates park in review_required."""
    out = _observe(store)
    unsure = [c["field_path"] for c in out["candidate_fields"] if c["status"] == "needs_confirmation"]
    for p in unsure:
        assert p in out["review_required"]
        assert p not in out["written_fields"]


def test_confirming_a_candidate_writes_it_with_provenance(store):
    first = _observe(store)
    unsure = [c for c in first["candidate_fields"]
              if c["status"] == "needs_confirmation" and c["field_path"].startswith("support_profile.")]
    if not unsure:
        pytest.skip("no support-profile candidate needed confirmation for this comment")
    target = unsure[0]
    second = _observe(store, confirmed_fields=[target["field_path"]])
    assert target["field_path"] in second["written_fields"], second["unresolved_questions"]
    sp = store.get_support_profile("student-abigail")
    _, _, cat, bucket = target["field_path"].split(".", 3)
    items = sp["categories"][cat][bucket]
    assert items, "confirmed field produced no entry"
    assert all(i.get("evidence_type", "teacher_note") == "teacher_note" for i in items)


def test_no_existing_field_changes_meaning(store):
    """Kill gate K2: Observe must not re-purpose a field a teacher already
    has data in. The only declared re-home is strategies_trialed, and it is
    the same mapping the docpipe bridge already applies."""
    out = _observe(store)
    for c in out["candidate_fields"]:
        r = resolve(c["field_path"])
        if r is not None and r.spec.rehome:
            assert r.spec.docpipe_field_id == "strategies_trialed"


def test_empty_comment_is_refused_not_written(store):
    out = _observe(store, text="   ")
    assert out["written_fields"] == [] and out["review_required"] == []
    assert out["unresolved_questions"]


def test_same_comment_twice_does_not_double_write(store):
    _observe(store)
    _observe(store)
    lens = store.export_lens("student-abigail")
    assert len([o for o in lens["observations"] if o.get("cefr_dimension") == "listening"]) == 1
