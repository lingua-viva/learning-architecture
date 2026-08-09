# PROMPT — Build: Student Summary Finish Line — 2026-08-08

You are the implementing builder for `~/learning-architecture` (Lingua Viva).

Setup: `cd ~/learning-architecture`, `unset ANTHROPIC_API_KEY` (subscription auth
only), `export MC_AGENT=1`. Start from current `main` — run `git log --oneline -10`
and confirm you see `fd370a4` (packet-print contract v130) and `26836f5` (pending
evidence review, contract v131). Commits may exist on top — fine. If either is
missing, STOP: stale tree. If `git status --short` shows modifications to
`src/web.py`/`static/index.html` you did not make, another window is mid-landing —
wait for those files to be clean before touching them.

Read, in order, before writing any code:

1. `dev/SPEC_LV_PARENT_SUMMARY_FINISH_2026-08-08.md` — your spec. It wins on scope.
2. `AGENTS.md` — "pushed" has a 7-step definition; you will NOT push.

## What this is

**One UX piece to perfect** (operator ruling 2026-08-08: no whole-system passes).
The Student Summary drafts a family-safe note, then strands the teacher in a bare
textarea ("editing before sending" with no send/copy/print — grep verified 0
affordances), and the route is fail-open: missing OR unknown `student_id` silently
falls back to the demo student `student-nora` (`src/web.py:6141` and the
`except → retry with "student-nora"` at `:6152`) — a teacher can receive a
family-facing draft built from demo data labeled as their student. You are closing
the exit (copy + print via the existing chokepoint) and killing the demo-fallback
class. If you find yourself building email/send, draft history, or new draft
content, stop — off the map.

## Map (verified against disk 2026-08-08)

- `src/web.py:6136` — `POST /api/parents/recommendation`; the two `student-nora`
  fallbacks at `:6141`/`:6152`; `source_observation_ids` collection ~`:6170`
  (comment cites teacher-readiness C6 — the 08-03 harness recorded `[]`, FAIL P1;
  no test locks it).
- `static/index.html` ~3860-3898 — Student Summaries panel: `draftParent()`,
  F5 empty-student guard at ~3875, draft render at `:3898` (warnings + subject +
  `<textarea>` + review label, then nothing).
- `printPacketHtml(...)` — the packet-print build's single iframe print
  chokepoint; `tests/test_packet_print.py` locks EXACTLY ONE
  print-invocation site. Reuse it; never add a second.
- `contracts/UI_CONTRACT.yaml`/`.lock`, `tests/test_ui_contract.py`
  (`EXPECTED_VERSION`) — read the LIVE version (v131 at spec time; it may have
  moved — never assume).
- Harness C6 predicate: `src/lingua_viva/teacher_readiness.py`
  (`observe_parent_report` chain) — every `source_observation_ids` entry must
  belong to the student.

## Build order (each phase its own commit — do not collapse phases)

1. **Fail-closed identity (class fix)**: blank/missing `student_id` → 400;
   `export_lens` failure → 404 `unknown_student`; delete BOTH `student-nora`
   fallbacks (`grep -c student-nora src/web.py` → 0). Locking tests in
   `tests/test_parent_summary_finish.py`: 400/404 paths carry no draft body;
   string-level lock that `student-nora` never returns to `src/web.py`.
2. **C6 lock**: test — student with observations ⇒ `source_observation_ids`
   non-empty and every id belongs to that student. If current wiring passes,
   pure lock; if not, fix only the id-collection point in the route.
3. **Copy + Print exit**: "Copy final text" (copies the CURRENT edited textarea
   value + subject, toast) and "Print" (minimal escaped HTML doc from the edited
   text → `printPacketHtml`). Teacher's edits always win. Safety warnings and
   the review label stay exactly as they are — flag, never block.
4. **Ceremony + surface lock**: contract bump (live+1 on merged tree, bump-log
   line, `EXPECTED_VERSION`, yaml+lock+test one commit). Surface locks: "Copy
   final text" present, print wired through `printPacketHtml`, one
   print-invocation site still holds, F5 guard string still present.

## Rules that ride with this build

- **Shared repo, concurrent windows.** Another window is on the observation
  double-save piece (also touches `static/index.html`/`src/web.py`).
  Hunk-isolate; only your own hunks; never `git add .`; never stash without
  popping. Whoever lands the contract bump second recomputes on the merged
  tree — never race it.
- **Everything local.** Copy/print are browser-local. No student PII in this
  PUBLIC repo — fixtures use obviously fake names.
- **No push, no release, no tag.** Committed ≠ shipped; the operator pushes.
- Class fixes at one chokepoint + a locking test; no instance patches.
- Commit style: `type(scope): description` heredoc + `Co-Authored-By:` trailer.

## Verify before claiming done

`pytest -q tests/test_parent_summary_finish.py tests/test_packet_print.py
tests/test_ui_contract.py tests/test_route_reachability.py` green plus any
existing parent-report test modules; `python3 scripts/check_ui_contract.py` and
`check_route_reachability.py` OK; then full `pytest -q tests/`. Write
`dev/REPORT_LV_PARENT_SUMMARY_FINISH_2026-08-08.md` (commits, acceptance vs
spec, what's still manual — the actual family send stays human) and close with
the 5-line format: WINDOW / SHIPPED / MID-FLIGHT / BLOCKED / REPORT, with SHAs
and paths.
