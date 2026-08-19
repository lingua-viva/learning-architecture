"""STEP 5 — identity resolution + unresolved queue (L8).

SPEC_LV_UNIFIED_REAL_DATA_FIX_2026-08-19 §STEP 5 and ruling §8-3 (default:
always queue, never auto-merge). `student_id = slug(display_name)` made
identity BE the spelling — "Marco B-R" in a support file next to "Marco
Bianchi" on the class list silently became two children. These tests lock
the fix: exact spellings (and human-ruled surface forms) resolve to the
canonical id, plausible matches queue for a human, only genuinely new names
are new.
"""
from __future__ import annotations

import json

import pytest

from src.lingua_viva.docpipe import identity


@pytest.fixture()
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path))
    return tmp_path


ROSTER = [
    {"student_id": "student-a1", "display_name": "Marco Bianchi"},
    {"student_id": "student-a2", "display_name": "Nora Rossi"},
    {"student_id": "student-a3", "display_name": "Giulia Bianchi-Rossi"},
    {"student_id": "student-a4", "display_name": "Anna (Annie) Villa"},
]


# ---------------------------------------------------------------------------
# Normalization: one normal form for COMPARISON, never for rewriting
# ---------------------------------------------------------------------------


def test_normalize_name_one_normal_form():
    assert identity.normalize_name("  Marco   Bianchi ") == "marco bianchi"
    assert identity.normalize_name("MARCO BIANCHI") == "marco bianchi"
    # nickname parentheses are dropped for comparison
    assert identity.normalize_name("Anna (Annie) Villa") == identity.normalize_name("Anna Villa")
    # NFKC: full-width and composed forms compare equal
    assert identity.normalize_name("Ｍarco Bianchi") == "marco bianchi"
    assert identity.normalize_name("") == ""
    assert identity.normalize_name(None) == ""


def test_initials_only_for_abbreviation_shaped_tokens():
    assert identity._initials("b-r") == ["b", "r"]
    assert identity._initials("b.") == ["b"]
    assert identity._initials("b") == ["b"]
    # a real surname is NOT an abbreviation
    assert identity._initials("bianchi") == []
    assert identity._initials("bianchi-rossi") == []


# ---------------------------------------------------------------------------
# Plausible-match compatibility (what earns a QUEUE, never a merge)
# ---------------------------------------------------------------------------


def test_compatible_abbreviated_surname():
    marco_br = identity._name_tokens("Marco B-R")
    assert identity._compatible(marco_br, identity._name_tokens("Marco Bianchi-Rossi"))
    # one initial resolvable is enough — the human decides
    assert identity._compatible(marco_br, identity._name_tokens("Marco Bianchi"))
    assert identity._compatible(
        identity._name_tokens("Marco B."), identity._name_tokens("Marco Bianchi")
    )


def test_compatible_requires_first_name_exact():
    assert not identity._compatible(
        identity._name_tokens("Mario B-R"), identity._name_tokens("Marco Bianchi-Rossi")
    )


def test_bare_first_name_is_plausible():
    assert identity._compatible(
        identity._name_tokens("Marco"), identity._name_tokens("Marco Bianchi")
    )


def test_different_full_surname_is_not_compatible():
    assert not identity._compatible(
        identity._name_tokens("Marco Verdi"), identity._name_tokens("Marco Bianchi")
    )
    # abbreviation whose initials start nothing on the roster name
    assert not identity._compatible(
        identity._name_tokens("Marco Z."), identity._name_tokens("Marco Bianchi")
    )


# ---------------------------------------------------------------------------
# resolve(): exact | queue | new
# ---------------------------------------------------------------------------


def test_resolve_exact_spelling_is_the_roster_student(isolated_state):
    result = identity.resolve("marco  BIANCHI", ROSTER)
    assert result == {"status": "exact", "student_id": "student-a1"}


def test_resolve_nickname_parentheses_compare_equal(isolated_state):
    result = identity.resolve("Anna Villa", ROSTER)
    assert result == {"status": "exact", "student_id": "student-a4"}


def test_resolve_abbreviation_queues_with_candidates_never_merges(isolated_state):
    result = identity.resolve("Marco B-R", ROSTER)
    assert result["status"] == "queue"
    ids = sorted(candidate["student_id"] for candidate in result["candidates"])
    # both Marco Bianchi and (via first name mismatch) NOT Giulia
    assert ids == ["student-a1"]


def test_resolve_new_name_is_new(isolated_state):
    assert identity.resolve("Tommaso Greco", ROSTER) == {"status": "new"}
    assert identity.resolve("", ROSTER) == {"status": "new"}


def test_resolve_scoped_to_the_roster_handed_in(isolated_state):
    # same spelling, different class roster → new, never a cross-class match
    assert identity.resolve("Marco B-R", [
        {"student_id": "student-x1", "display_name": "Sara Conti"},
    ]) == {"status": "new"}


# ---------------------------------------------------------------------------
# Event log: queue lifecycle + the surface-form registry
# ---------------------------------------------------------------------------


def test_enqueue_is_idempotent_while_open(isolated_state):
    first = identity.enqueue_unresolved(
        teacher_id="teacher:t1", display_name="Marco B-R", source_id="SRC-1",
        candidates=[{"student_id": "student-a1", "display_name": "Marco Bianchi"}],
    )
    second = identity.enqueue_unresolved(
        teacher_id="teacher:t1", display_name="marco b-r", source_id="SRC-2",
        candidates=[],
    )
    assert second["event_id"] == first["event_id"]
    assert len(identity.list_open_items()) == 1


def test_assigned_ruling_becomes_a_surface_form_and_replays(isolated_state):
    identity.enqueue_unresolved(
        teacher_id="teacher:t1", display_name="Marco B-R", source_id="SRC-1",
        candidates=[{"student_id": "student-a1", "display_name": "Marco Bianchi"}],
    )
    identity.mark_assigned(
        teacher_id="teacher:t1", display_name="Marco B-R", student_id="student-a1",
    )
    assert identity.list_open_items() == []
    # the ruling IS the registry: future resolution replays it deterministically
    assert identity.surface_forms() == {"marco b-r": "student-a1"}
    assert identity.resolve("Marco B-R", ROSTER) == {
        "status": "exact", "student_id": "student-a1",
    }
    # …even with an empty roster — the ruling outlives the snapshot
    assert identity.resolve("marco  b-r", []) == {
        "status": "exact", "student_id": "student-a1",
    }


def test_corrected_ruling_wins_last_event(isolated_state):
    identity.mark_assigned(teacher_id="t", display_name="Marco B-R", student_id="student-a1")
    identity.mark_assigned(teacher_id="t", display_name="Marco B-R", student_id="student-a3")
    assert identity.surface_forms()["marco b-r"] == "student-a3"


def test_created_and_dismissed_close_the_item(isolated_state):
    for name, closer in (
        ("Marco B-R", lambda: identity.mark_created(
            teacher_id="t", display_name="Marco B-R", student_id="student-new")),
        ("Nora R.", lambda: identity.mark_dismissed(teacher_id="t", display_name="Nora R.")),
    ):
        identity.enqueue_unresolved(
            teacher_id="t", display_name=name, source_id="SRC-1", candidates=[],
        )
        closer()
    assert identity.list_open_items() == []
    # neither created nor dismissed registers a surface form
    assert identity.surface_forms() == {}


def test_open_items_filter_by_teacher(isolated_state):
    identity.enqueue_unresolved(teacher_id="teacher:t1", display_name="A B.",
                                source_id="S", candidates=[])
    identity.enqueue_unresolved(teacher_id="teacher:t2", display_name="C D.",
                                source_id="S", candidates=[])
    assert len(identity.list_open_items()) == 2
    t1 = identity.list_open_items("teacher:t1")
    assert [item["display_name"] for item in t1] == ["A B."]


def test_event_log_survives_junk_lines(isolated_state):
    identity.enqueue_unresolved(teacher_id="t", display_name="A B.",
                                source_id="S", candidates=[])
    path = identity.identity_queue_path()
    with path.open("a", encoding="utf-8") as handle:
        handle.write("not json\n")
        handle.write(json.dumps(["not", "a", "dict"]) + "\n")
    assert len(identity.list_open_items()) == 1
