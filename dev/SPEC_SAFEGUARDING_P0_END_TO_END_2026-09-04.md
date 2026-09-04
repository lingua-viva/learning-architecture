# SPEC — Safeguarding P0, closed end to end: Claudia's sentence, through the typed Observe view, in both languages

**Date:** 2026-09-04 · **Author:** PC-23 seat · **Operator:** Mical Neill
**Origin:** Claudia's audit 2026-08-29 (`qa/2026-08-29_claudia-full-audit/UX_REPORT.md` BUG-3, BUG-4 — the two P0s), the 2026-09-03 Italian parity repair, and the readiness path's launch gate item 2 (`dev/PATH_TO_UX_READINESS_2026-09-04.md` §4: "safeguarding P0s closed by a test that was red first").
**Status:** spec. Kill criteria frozen before any build. Companion prompt: `dev/PROMPT_SAFEGUARDING_P0_AND_PARENT_TONE_2026-09-04.md`.

---

## 0. WILL IMPROVE WHAT · HOW MUCH · HOW VERIFIED

| | |
|---|---|
| **WHAT** | On 29 August a teacher typed *"Aiken said someone at home makes him feel scared."* into the Observe view and it saved as a normal observation, untagged, visible in the student's record (BUG-3, BUG-4). The safeguarding gate had existed since 9 August (`capture_with_safeguarding`, `src/lingua_viva/safeguarding.py:469`), so this was a **detection miss on that phrasing**, not missing wiring — and the 3 September repair fixed the *Italian* gap in a *different* detector (`lens_extract._is_red_safeguarding`). **Nothing on the tree proves Claudia's exact sentence is RED today, in English or Italian, through the route she used.** This spec makes that one proof exist, and makes the three things that must be true of a RED disclosure true by test: restricted, absent from every normal surface, and *seen* by a coordinator. |
| **HOW MUCH** | A corpus of the audit's sentence plus its Italian twin plus the existing RED/AMBER/GREEN fixtures, run through the typed route (`POST /api/observe/capture`), the voice route (`/api/voice/act`), and the document route (report card with a disclosure inside). Target: **0 RED sentences in any normal surface** (observation store, `get_lens`, `export_lens`, `/lens/markdown`, parent note, lens query), **1 restricted-ledger entry per RED capture**, **1 queued notification per RED capture**, and a coordinator-visible count of what is waiting. Denominators reported per route and per language. |
| **VERIFIED** | Every assertion is watched failing first: the corpus test runs against the tree before any change and its result is recorded whether red or green. A green on the first run is a finding, not a pass — it means the 29 August failure is not reproduced and the spec's §1.1 CANNOT-TELL becomes the deliverable. |

## 1. What the tree says today (read 2026-09-04)

### 1.1 The gate exists; the sentence is unproven

- `capture_with_safeguarding()` wraps both capture routes: typed (`src/web.py:/api/observe/capture` → `capture(store)`), voice (`/api/voice/act`). RED → `record_red_observation()` → `safeguarding/restricted.ndjson`; `pipeline.capture` is never called (`safeguarding.py:479-499`).
- `classify_severity()` (`:128`) has RED, AMBER-rounds-up-to-RED for ambiguous indicators (`:147-154`), AMBER, GREEN. The fixtures that prove RED use *"someone hurts her at home and begged me not to tell"* (`tests/test_safeguarding.py:124-147`). **Claudia's sentence — "someone at home makes him feel scared" — is not in any test.** CANNOT-TELL whether it is RED, AMBER, or GREEN today.
- The 09-03 Italian repair unioned the shared taxonomy into `lens_extract._is_red_safeguarding` (the *document* path). Whether `classify_severity` (the *Observe* path) has Italian parity for *this* phrasing is `tests/test_safeguarding_italian.py`'s job; the audit sentence's Italian twin is not in it either.

### 1.2 Absence from normal surfaces is proven at one layer only

`test_red_capture_never_lands_in_normal_observation_store` proves the SQLite store gets no row. Nothing proves the *surfaces* a teacher looks at: the Students view's "Recent observations" (BUG-4 was seen there), `export_lens`, `/lens/markdown`, the parent note, the Observe view's own confirmation badge (BUG-3 was the badge saying "Saved locally" with no "Restricted record"). Since RED never reaches the store, these should follow — but "should follow" is exactly what BUG-4 was.

### 1.3 The notification is queued and, by design, nobody is pushed

`enqueue_notification()` (`safeguarding.py:429`) writes `queued` (Slack channel configured) or `pending_config` (not configured). `notification_drain.drain_notifications()` delivers `queued` entries **only when a coordinator presses** `POST /api/safeguarding/drain` (`routers/safeguarding.py:70`: *"Never runs in the background; a human presses this"*). That is a deliberate ruling and this spec keeps it. The gap is one step earlier: **nothing tells the coordinator there is something to press.** `pending_notifications()` (`:457`) exists and no UI reads it. On a school with no Slack channel every entry is `pending_config` forever and no human knows.

## 2. The contract

1. **The audit sentence is RED, in both languages, on every route.** `"Aiken said someone at home makes him feel scared."` and `"Aiken ha detto che qualcuno a casa lo fa sentire spaventato."` classify RED (or AMBER-rounded-to-RED — either lands in the restricted ledger). If the tree says GREEN or AMBER-not-rounded today, the indicator taxonomy gains the class *a child says someone at home makes them feel <fear-word>* with the Italian pair, under the parity discipline (`tests/test_safeguarding_parity.py`: every English row has an Italian row).
2. **Absent from every normal surface, proven at the surface.** After a RED capture through the typed route: `export_lens(...)["observations"]` is empty of it; `/api/students/{id}/lens/markdown` does not contain any word of it; the parent note does not; `lv lens-query L11 --term <a word from it>` does not; the Observe capture response has `restricted: true`, no `observation` key, and a content-free message.
3. **Seen.** `GET /api/safeguarding/pending` (new; coordinator-gated like `/drain`) returns `{count, queued, pending_config, oldest_at}`. The desktop shows a badge with that count on the Governance / Safeguarding entry for coordinator and admin roles, and the `pending_config` state says in plain words: *"N safeguarding items are waiting. No notification channel is configured — set one in Settings, or review them here."* The drain stays a button. Teachers see nothing (role gate as today).
4. **Content-free everywhere except the ledger.** Every new surface (badge, pending route, log lines) carries counts and ids only. The existing `test_safeguarding_promise_honesty.py` discipline extends to the new route.

## 3. Rungs

**R0** sandbox both home variables; verify `$SB/runtime/student_lenses.db` and `$SB/safeguarding/` are the ones written. Never the operator's real home.

**R1 — the honest baseline, fix nothing.** Run the corpus (audit sentence EN/IT + existing RED/AMBER/GREEN rows) through `classify_severity` and through all three routes on a sandboxed server. Record per row: tier, ledger entry (y/n), store row (y/n), presence in each normal surface (y/n), notification state. Record `pending_notifications()` on a fresh home. Commit `dev/BASELINE_SAFEGUARDING_P0_2026-09-04.md`.

**R2 — build.** (a) Taxonomy rows if R1 shows the sentence is not RED, with the Italian pair and the parity test; (b) the surface tests from §2.2 (they may already be green — record it); (c) `GET /api/safeguarding/pending`; (d) the badge + the `pending_config` sentence in `static/index.html` (this touches the UI contract — **`check_ui_contract.py --bump` is the operator's, never the builder's; leave the lock red on PC-23 and say so**); (e) reachability manifest rows.

**R3 — sabotage.** Remove the new taxonomy row → the corpus test goes red. Make `capture_with_safeguarding` fall through to `pipeline.capture` on RED → every surface test goes red. Return `count: 0` from the pending route regardless → the badge test goes red. Restore by inverse edit.

**R4 — witness.** Claudia (or Olga) types the sentence in her own app: she must see *Restricted record*, not the normal badge; the student's record must not show it; a coordinator must see the count. Level 4 or it is not closed.

## 4. Kill criteria

- **K1** the corpus test is green on the untouched tree AND the 29 August failure cannot be reproduced by any phrasing in the audit → stop; the deliverable becomes the proof plus the CANNOT-TELL ("we could not make it fail"), not a taxonomy change made to look busy.
- **K2** any new surface carries a student name or a word of the transcript.
- **K3** a RED capture ever calls `pipeline.capture` or `append_observation`.
- **K4** an Italian row is added without its English pair, or vice versa (parity test red).
- **K5** the drain starts running in the background — the "a human presses this" ruling stands.
- **K6** `--bump` run on `check_ui_contract.py` from PC-23.

## 5. Fences

Never `main`. Path-scoped adds. Both sandbox variables. No real student data; the fixture names are the audit's fictional ones. The Italian sentence is authored by the builder and marked as such — a native check is R4's, not the tree's.

## 6. CANNOT-TELL, today

Whether the audit sentence is RED on this tree (R1 settles it). Whether v0.2.72 — the build Claudia used — predates a detector change that would already explain BUG-3. What Olga's school will use as a notification channel (Slack is the only transport; `pending_config` is the likely steady state).
