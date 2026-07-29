"""Teacher action registry + governance preview — Slice 2.

Spec: dev/SPEC_ACTION_DISPATCHER_FORMS_2026-07-28.md §Lingua Viva.

Prepare and Assess already had parameter forms (item 2), so the gap this
closes is items 1 and 3: a declared, small registry of what a teacher can do,
and a preview shown BEFORE an action of what it will read and whether anything
leaves the machine.

The registry is only worth anything if it stays true, so the tests below check
it against reality rather than against itself: every declared route must
actually exist in src/web.py, and the one action marked as sending data out
must be the one that really does.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.lingua_viva import actions
from src.web import app

client = TestClient(app)
REPO = Path(__file__).resolve().parent.parent


def _declared_routes() -> set[str]:
    web = (REPO / "src" / "web.py").read_text(encoding="utf-8")
    found = set()
    for method, path in re.findall(r'@app\.(get|post|put|delete)\(\s*"([^"]+)"', web):
        found.add(f"{method.upper()} {path}")
    return found


# --- the registry describes something real ---------------------------------


def test_every_action_names_a_route_that_exists():
    """A registry that describes routes which no longer exist is worse than
    no registry: it reads as documentation while being fiction."""
    live = _declared_routes()
    for action in actions.ACTIONS:
        assert action["route"] in live, (
            f"{action['id']} declares {action['route']}, which is not in src/web.py"
        )


def test_every_action_has_a_preview_in_teacher_language():
    for action in actions.ACTIONS:
        assert action["preview"], f"{action['id']} has no preview"
        assert action["label"]
        assert action["view"]


def test_action_ids_are_unique():
    ids = [action["id"] for action in actions.ACTIONS]
    assert len(ids) == len(set(ids))


# --- the honesty of leaves_machine ------------------------------------------


def test_exactly_the_drive_upload_leaves_the_machine():
    """This is the field a teacher relies on. If a future action starts
    sending data out without setting it, this test is the thing that catches
    it — hence pinning the exact set, not just the count."""
    outbound = {a["id"] for a in actions.ACTIONS if a["leaves_machine"]}
    assert outbound == {"export_lens_to_drive"}


def test_the_outbound_action_says_so_plainly_in_its_preview():
    upload = next(a for a in actions.ACTIONS if a["id"] == "export_lens_to_drive")
    assert "off this computer" in upload["preview"]


def test_local_actions_do_not_claim_to_send_anything():
    for action in actions.ACTIONS:
        if not action["leaves_machine"]:
            assert "upload" not in action["preview"].lower() or "Drive" not in action["preview"]


def test_writing_actions_also_read():
    """Nothing should claim to change a student record without reading one."""
    for action in actions.ACTIONS:
        if action["writes_student_data"]:
            assert action["reads_student_data"], f"{action['id']} writes without reading"


# --- preview lookup --------------------------------------------------------


def test_preview_for_known_action():
    preview = actions.preview_for("capture_observation")
    assert preview is not None
    assert preview["reads_student_data"] is True
    assert preview["leaves_machine"] is False


def test_preview_for_unknown_action_is_none_not_a_reassurance():
    """The build order's law: no affordance may imply something it cannot
    back. A generic 'this is safe' for an unknown id would do exactly that."""
    assert actions.preview_for("no_such_action") is None
    assert actions.preview_for("") is None


# --- route + UI ------------------------------------------------------------


def test_registry_route_returns_the_actions_and_counts():
    payload = client.get("/api/actions/registry").json()
    assert payload["total"] == len(actions.ACTIONS)
    assert payload["leave_this_computer"] == 1
    assert payload["outbound_ids"] == ["export_lens_to_drive"]
    assert payload["touch_student_data"] == sum(
        1 for a in actions.ACTIONS if a["reads_student_data"]
    )


def test_activity_view_renders_the_registry():
    body = client.get("/").text
    assert "renderActionRegistry()" in body
    assert 'id="actions-registry"' in body
    assert 'api("/api/actions/registry")' in body


def test_prepare_view_shows_a_governance_preview_before_generating():
    body = client.get("/").text
    assert 'renderPrivacyPreview("generate_activity_pack", "prepare-privacy-preview")' in body
    assert 'id="prepare-privacy-preview"' in body


def test_prepare_and_assess_still_have_their_parameter_forms():
    """Item 2 was already satisfied before this slice; guard it so the
    registry work did not quietly remove it."""
    body = client.get("/").text
    for element in ('id="prep-grade"', 'id="prep-unit"', 'id="assess-grade"', 'id="assess-unit"'):
        assert element in body, f"{element} missing from the forms"
