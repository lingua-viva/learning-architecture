# Report — Tiered Materials Full Circle — 2026-08-08

## Status

Built locally, not committed, not pushed, not released. No live Drive account was used.

## What Landed

- G2 roster split: `assign_roster_split()` separates RTI tier 3 or explicitly flagged support-profile students into `individual_support`, outside Foundational / On Track / Extended. Rule chosen: `rti_current_tier == 3` or `support_profile.needs_individual_support|individual_support|requires_individual_support == true`, because `ContentDifferentiator` already uses `rti_current_tier` and broad support notes should not automatically remove a student from classwide work.
- G4 readable packet: canonical Markdown remains, with `render_printable_packet_html()` and print-ready HTML returned by preview/approval. Prepare now renders HTML instead of raw Markdown.
- G1 local library: Drive folder pull into `lv_home()/runtime/lesson_materials/library/<grade>/<subject>/`, manifest-backed listing, unchanged-file skip, and local file browser route/UI.
- G3 today's lesson: `select_todays_lesson()` persists class/grade/subject local lesson selection under runtime state.
- G5 share-back: approval can upload stripped Markdown + print HTML to a class/grade/subject folder. Teacher-only individual-support section is local only and absent from uploaded content. `assert_safe_for_external_output()` runs on both uploaded payloads.

## Folder-Map Shape

Minimal shared shape for the lens lane to reuse:

```json
{
  "lesson_materials": {
    "class_id": {
      "G3": {
        "language": {"folder_id": "drive-folder-id"}
      }
    },
    "default_folder_id": "optional-fallback"
  }
}
```

## Verification

- `pytest -q tests/test_lesson_materials.py tests/test_lesson_packet_routes.py` → 17 passed
- `python3 scripts/check_route_reachability.py` → OK, 150 routes classified
- `python3 scripts/check_ui_contract.py` → OK, contract v124
- `pytest -q tests/test_route_reachability.py tests/test_ui_contract.py` → 15 passed
- `pytest -q tests/test_lesson_materials.py tests/test_lesson_packet_routes.py tests/test_route_reachability.py tests/test_ui_contract.py` → 32 passed

## Acceptance Status

1. Local library pull/list implemented and hermetic-tested with mocked Drive; live Drive manual test still required.
2. Roster split into three tiers plus kept-apart individual support implemented and tested.
3. Today's lesson selection implemented and tested.
4. Rendered packet contains no raw Markdown syntax in the UI/HTML test path.
5. Share-back uploads Markdown + HTML to routed folder with support section stripped; mocked Drive test covers it.
6. Existing privacy prompt/name leak tests still cover no names/RTI/trauma flags in the generation prompt.
7. Full regression suite and release/push verification not run in this local build.

## Manual Live-Drive Checklist

1. Connect Google Drive in Settings.
2. In Prepare, enter a coursework folder id, pull library, confirm files appear.
3. Select today's lesson, preview packet, approve locally.
4. Approve with `push_to_drive` and a configured folder map.
5. Confirm both `.md` and `.html` files appear in the expected Drive folder and no teacher-only individual-support section is present.
