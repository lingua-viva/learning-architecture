# PROMPT — Build: Pending Evidence Review Loop — 2026-08-08

You are the implementing builder for `~/learning-architecture` (Lingua Viva).

Setup: `cd ~/learning-architecture`, `unset ANTHROPIC_API_KEY` (subscription auth
only), `export MC_AGENT=1`. Start from current `main` — run `git log --oneline -10`
and confirm you see BOTH `c18dd30` (roster-split surface) and `2831ce3`
(unattributed queue). Commits may exist on top of them — fine. If either is
missing, STOP: you are on a stale tree. Then run `git status --short`: if
`src/web.py` or `static/index.html` show modifications you did not make, another
window is still landing its build — wait for a clean status on those files before
touching them.

Read, in order, before writing any code:

1. `dev/SPEC_LV_PENDING_EVIDENCE_REVIEW_2026-08-08.md` — your spec. It wins on scope.
2. `dev/SPEC_LV_STUDENT_LENS_FULL_CIRCLE_2026-08-08.md` §G5 (evidence grades) —
   the honesty rules you are completing, not changing.
3. `AGENTS.md` — "pushed" has a 7-step definition; you will NOT push.

## What this is

**One UX piece to perfect** (operator ruling 2026-08-08: no whole-system passes).
Report bodies only include `REPORT_GRADE_CONFIDENCE` evidence
(`src/education/student_lens.py:161`) — correct and fail-closed. But
model-suggested ethos-trait and strengths evidence is a permanent dead letter:
`export_ethos_report(..., include_unconfirmed=True)` builds a `pending_review`
payload that NO web route requests (`grep include_unconfirmed src/web.py` → 0),
the UI never renders it (`grep -c pending_review static/index.html` → 0), and
the only suggestion→evidence-grade path in the product
(`confirm_support_entry`, student_lens.py:1123, route src/web.py:~4735) covers
support-profile entries ONLY. You are closing one loop: pending items become
visible → teacher confirms or dismisses → report body updates. If you find
yourself changing what counts as report-grade, adding bulk confirm, or touching
parent-report generation, stop — you are off the map.

## Map (verified against disk 2026-08-08)

- `src/education/student_lens.py`:
  - `:161` `REPORT_GRADE_CONFIDENCE = ("teacher_confirmed", "imported_verified")`.
  - `:1123` `confirm_support_entry` — THE pattern to mirror (locate by id, flip
    confidence in place, bump profile_version, ValueError on unknown).
  - `:2166` `add_profile_strength` — entries carry `"id"` (uuid4) + `"active"`.
  - `:2271` `_append_ethos_evidence_item` — items carry `"id"`; dual-writes to the
    evidence_records ledger "under the same id" (keep them in sync on confirm);
    latent upgrade branch at ~2337-2353 (model_suggested→teacher_confirmed flips
    in place).
  - `:2719` `export_ethos_report(student_id, include_unconfirmed=False)`;
    `_pending` at 2771-2781 currently STRIPS ids — make pending items actionable
    (add id, evidence_type, source_observation_id, created_by).
  - `pending_review` shape at ~2817-2821.
- `src/web.py:~4735` — `POST /api/students/{student_id}/support-entry/confirm`
  (teacher-id handling to mirror); `:2915` house language "Kept out of parent
  reports until you confirm them." — reuse it.
- `static/index.html` ~2948-2955 — student lens strengths render (where the
  "Waiting for your confirmation (N)" section mounts).
- `contracts/UI_CONTRACT.yaml`/`.lock`, `contracts/ROUTE_REACHABILITY.yaml`,
  `tests/test_ui_contract.py` (`EXPECTED_VERSION`) — read the LIVE version at
  build time (v129 when this prompt was written; it may have moved — never assume).
- Test styles: `tests/test_ethos.py` (report-grade semantics — must stay green
  untouched), `tests/test_ask_grounding_surface.py` (surface-lock grep style).

## Build order (each phase its own commit)

1. **Store chokepoints**: `_pending` returns ids; `confirm_profile_strength`,
   `confirm_ethos_evidence` (profile + ledger stay in sync), dismiss variants
   (`active = False`, never delete). Locking tests in
   `tests/test_pending_evidence_review.py`: suggested→invisible→confirm→in
   report body; dismiss→leaves pending AND can never reach a report; unknown
   id/kind/trait → ValueError + profile_version unchanged (zero writes).
2. **Routes**: `GET /api/students/{student_id}/evidence/pending` (404 unknown
   student); `POST /api/students/{student_id}/evidence/confirm`
   (`target: strength|trait`, `entry_id`, `action: confirm|dismiss`). Off-map
   ids → 422 and ZERO writes — locking test. One item per call, no bulk.
3. **UI**: "Waiting for your confirmation (N)" section in the Students detail
   view — pending strengths (academic/personal) + trait evidence grouped by
   trait label; per-row Confirm/Dismiss; "Kept out of parent reports until you
   confirm them." hint; toast + refresh on action (item visibly moves to the
   confirmed display); "Nothing waiting for review." empty state; no
   "confirm all" anywhere.
4. **Ceremony + surface lock**: classify both routes in
   `ROUTE_REACHABILITY.yaml`; UI contract bump (live+1 on the merged tree,
   bump-log line, `EXPECTED_VERSION`, yaml+lock+test one commit); surface-lock
   test — `/evidence/pending` consumed, "Waiting for your confirmation" present,
   Confirm/Dismiss present, kept-out language present, "confirm all" ABSENT.

## Rules that ride with this build

- **Shared repo, concurrent windows.** Another window may be editing
  `static/index.html` / `src/web.py` (packet-print build). Hunk-isolate your
  commits — only your own hunks, never `git add .`, never stash without popping.
  If the other window bumped the contract first, recompute yours on top of the
  merged tree — never race it.
- **Everything local.** No egress. No student PII in this PUBLIC repo — fixtures
  use obviously fake names.
- **No push, no release, no tag.** Committed ≠ shipped; the operator pushes.
- Class fixes at one chokepoint + a locking test; no instance patches — the
  confirm logic lives in `student_lens.py`, never in a route body.
- Commit style: `type(scope): description` heredoc + `Co-Authored-By:` trailer.

## Verify before claiming done

`pytest -q tests/test_ethos.py tests/test_pending_evidence_review.py
tests/test_ui_contract.py tests/test_route_reachability.py` green (test_ethos.py
UNTOUCHED); `python3 scripts/check_ui_contract.py` and
`check_route_reachability.py` OK; then full `pytest -q tests/`. Write
`dev/REPORT_LV_PENDING_EVIDENCE_REVIEW_2026-08-08.md` (commits, acceptance vs
spec, what's still manual) and close with the 5-line format:
WINDOW / SHIPPED / MID-FLIGHT / BLOCKED / REPORT, with SHAs and paths.
