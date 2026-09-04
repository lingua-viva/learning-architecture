# NIGHT SUMMARY — 2026-09-03 → 04, PC-23, for the morning

**Operator:** Mical Neill · **Branch:** `fix/cefr-write-and-unknown-field-refusal-2026-09-03` (pushed; `main` untouched at `7037037`; no merge, no tag, no release)
**Your two instructions tonight:** (1) *"A — run Rung 2 … continue through all 4 rungs"*; (2) *"full diagnostic … each and every line of code … run Doctor … push as far as you can … then admin functions, querying against lenses, creating materials, assess changes needed and logged."*

Everything below is read from the tree or from a command run tonight. Denominators are attached. Anything not measured says CANNOT-TELL.

---

## 1. The commits, in order

| sha | what |
|---|---|
| `aeb33bb` | Rung 1 honest baseline B1–B9, nothing fixed; K8 fired |
| `f0ba78d` | K8-stop report (superseded) |
| `fcc4afe` | **Rung 2** — `lens_field_contract.py` (one registry, `resolve()` the only way in), writer rewritten with the accounting invariant, refusals returned over HTTP |
| `90d2888` | **Rung 3** — five sabotages all red and restored; Observe through the contract (`observe_to_lens.py`); Prepare reads through `requires("prepare")` |
| `fd98e8c` | **Rung 4** — producer drift alarm, bridge parity, support-entry endpoint resolves before the store |
| `dfc1c24` | final four-rung report `dev/REPORT_LENS_FIELD_CONTRACT_2026-09-03.md` |
| `3eaa943` | **Doctor fix** — four hardcoded `python3` subprocesses → `sys.executable` (Doctor crashed on every Windows box; `/api/health` read degraded) |
| `6841c99` | **Diagnostic** — `scripts/trash-collector.py` ported from MC, `config/reachability_roots.yaml` (13 roots), **Observe wired into `/api/query`** (`lens_update` in the response) |
| `12d75de` | `dev/DIAGNOSTIC_UX_CENSUS_2026-09-03.md` — every module → UX, per-line reachability, 60 findings triaged |
| `4eabf6b` | **U18** — `lens_query.py` (12 admin questions over the STORE through the contract), `/api/admin/lens-query/*`, `lv lens-query`, 11 tests |
| this commit | `dev/ASSESS_CHANGES_NEEDED_2026-09-03.md` + this summary |

## 2. The numbers, before → after

| measurement | Rung 1 (a08f1c6) | close |
|---|---|---|
| emittable paths B2 | 72 | 72 |
| written when well-formed B3 | 55 / 72 | **60 / 72** |
| emitted-but-unwritten B4 | 17: **1 silently dropped, 1 uncaught exception** | 12: 9 ethos declared-not-implemented (on purpose), 1 read-only, 1 marker, 1 review-by-design. **Dropped 0, exceptions 0.** |
| report card over HTTP (Abigail, sandbox) | 51 → 8/5/38 by count; refusals **not** in the response; re-import **double-writes** | 51 → 8/5/38 with a 51-row ledger in the response; re-apply writes **0** new rows |
| bounded suite | 790 passed / 13 failed | **843 passed / 10 failed** — 0 new, **3 fixed** (the Doctor `python3` class); the remaining 10 are `sqlite_vec` missing (3), CRLF sha256 (5), CRLF ui-contract (2) — all PC-23 artifacts |
| Doctor | crashed (`WinError 2`) | runs: 15 files, 7 gates, gauntlet PASS; BLOCKED only by branch≠main + dirty worktree (its policy) |
| route reachability | 196 OK | 198 OK (+2 admin routes, classified) |
| trash-collector (src/, 13 roots) | — | 2103 symbols: **1958 reached from product (93.1%)**, 60 tested-but-unreached, 78 unreferenced, 7 script-only, 1 unwired module (`docpipe/grounding.py`, 13 lines) |
| lines in src/ | — | 57,183: 75.9% inside reached defs, 3.1% inside unreached defs, 22.1% module-level (runs on import) |

## 3. What is now wired that was not

- **Report card → lens (U3):** every field accounted for, refusals named, on the wire, idempotent.
- **Observe → lens (U4):** a comment's content reaches lens fields through the same logic as a document, `lens_update` returned; RED/duplicate paths untouched. **Correction 2026-09-04:** the night wiring was on `/api/voice/act` (voice), not on `/api/observe/capture`, which is what the typed Observe view posts to. Both are wired now (chain commit). Running the chain also found that plus levels (A2+) were being stored as A2 by both CEFR extractors, and that applied imports lost their source filename — both fixed in the same commit.
- **Prepare (U9):** tiering reads through the OUT filter; a lens with no tier refuses instead of guessing; missing CEFR is *named*. `/api/lesson-materials/roster-split` and `/api/prepare/activity` run without a model; `generate` returns three tier cards without a model **but the response does not say it ran without one** — CANNOT-TELL from the payload whether content is template or model. That is the OUT-filter honesty rule not yet applied to materials. Next window.
- **Admin query (U18):** `lv lens-query L1..L12` and `/api/admin/lens-query/{id}` over the store. **Finding:** the existing `fleet` engine reads the docpipe vault, which the product's write paths never touch.
- **Doctor** runs on Windows.

## 4. What I got wrong tonight (the useful section)

1. Spec said four lists; five. 2. "Silent drop closed"; one branch wider. 3. Assumed HTTP carried refusals; it dropped them. 4. Put idempotency on the contract; it is the writer's. 5. Assumed `scratch/` was gitignored. 6. Hand-count 61 ≠ measured 55. 7. Diff fence excluded the router that had the teacher-visible bug. 8. Declared `cefr_snapshot` essential for Prepare, over a ruled default; corrected to enriching. 9. Observe's confirm path never exercised on a comment (test skipped, named). 10. Rung 4 "convert every site" became convert-one, check-eight, leave-four; said so. **11. Wrote "Whisper is not in the tree" before grepping; it is (`voice_stt.py`). Fixed before commit.** 12. The first trash-collector run flagged every FastAPI route and every closure as unreached — two analyser blind spots, both fixed and documented before any number was reported.

## 5. Open — yours

- **`support_profile` origin** (K7 flag): authored today; if you want every claim behind an observation, say so.
- **`strategies_trialed` re-home** applied per A; option C is one line.
- **Ethos writes**: refused on purpose until you rule review semantics (9 refusals per report card).
- **Assess storage shape** (`dev/ASSESS_CHANGES_NEEDED` §2): new `assessment_profile` blob (recommended) vs support entries.
- **Who drains safeguarding notifications?** `pending_notifications` / the sync drains are started by nothing in `src/` (census §4.2). If nothing outside does either, RED items queue and never deliver.
- ~~`detect_injection` is an unarmed guard~~ — corrected 2026-09-04: the redaction guard is armed at three seams; the detect-only twin was DELETED on the operator's ruling and its tests retargeted at `redact_injection`'s list.
- The 34 (now 36) `deferred_undecided` routes are still a to-do list.
- The two fixture rows in your real store. Untouched. Gone on your word.

## 6. Open — next window

- Wire U8: endpoints for `set_avoid_pairing_with` / `replace_support_profile`; confirm affordance for `review_required` (the payload now carries `candidate_fields`).
- U10: `parent_report.approve` / `to_print_html` / `render_parent_report_pdf` are on no route.
- OUT filter for the other 12 consumers (`drive_sync` first) and for materials (`generate` must say "no model").
- Retire `observation_capture.py`'s four direct store writes once a teacher has used the new Observe path.
- Admin UI panel for U18 (adminNav exists; two routes are `deferred_undecided`).
- `check_app_reality.py`: 24 pre-existing unescaped template values in `static/index.html`.

## 7. CANNOT-TELL

No local model on PC-23 (classifier-routed paths proven in-process only; Prepare `generate`'s content provenance); whether the desktop wrapper starts the drains; whether the UI renders `lens_update` / `accounting`; `provider_config.py` vs `config.py` as the live provider door; the 78 unreferenced symbols listed individually; the 5 CRLF sha256 failures classed by error line only.

## 8. Fences

Never `main`, never a tag, never `--bump`, never `git add -A`, never a heredoc for file content, exit codes read bare, both sandbox variables set and verified before trusting any result, the real store read once read-only and byte-identical after.
