# PROMPT — two lanes, one window: safeguarding P0 end to end, then the parent note's tone

**Specs (read both in full before touching anything):**
1. `dev/SPEC_SAFEGUARDING_P0_END_TO_END_2026-09-04.md` — lane A, first, it gates the launch
2. `dev/SPEC_PARENT_NOTE_TONE_2026-09-04.md` — lane B, after A's Rung 2 is committed

**Repo:** `C:\Users\spide\lv-work` (`lingua-viva/learning-architecture`). **Base:** the branch `fix/cefr-write-and-unknown-field-refusal-2026-09-03` at its remote head, or `main` if it has merged — check, do not assume. **Operator:** Mical Neill. Nothing that needs a human decision gets decided: record it and move on. Where this prompt and a spec disagree, the spec wins and you report the disagreement.

**Then read only these:**
```
src/lingua_viva/safeguarding.py            classify_severity, record_red_observation, enqueue_notification, capture_with_safeguarding
src/lingua_viva/notification_drain.py      the delivery side and its "a human presses this" rule
src/lingua_viva/routers/safeguarding.py    the coordinator gate and the drain route
tests/test_safeguarding.py                 the RED fixtures that exist; test_safeguarding_parity.py for the EN/IT discipline
src/education/parent_report.py            generate_draft, the 2026-09-04 lens read, source_entry_ids
src/lingua_viva/docpipe/lens_extract.py   lines 59-74 only: IB_LEARNER_PROFILE, ATL_SKILLS, GRADE_SCALE
```
Stop reading there. Eleven files where six would do is this seat's known failure.

---

## Before your first edit

```bash
cd /c/Users/spide/lv-work
git status --porcelain            # 0 lines before you build; scratch/ is NOT gitignored — leave it untracked
git rev-parse HEAD                # record; re-check before every commit (K5: HEAD moved = stop)
git fetch origin && git log --oneline -3 origin/fix/cefr-write-and-unknown-field-refusal-2026-09-03
```

Sandbox every run with BOTH home variables and verify the sandbox held before trusting a result:
```bash
SB=/c/Users/spide/AppData/Local/Temp/claude/lv_sg; rm -rf "$SB"; mkdir -p "$SB"
LV_CONFIG_HOME="$SB" LV_STATE_HOME="$SB" PYTHONPATH=. python src/web.py 8831 > "$SB/server.log" 2>&1 &
ls "$SB/runtime/student_lenses.db" "$SB/safeguarding" 2>/dev/null    # both must appear after the first capture; if not, STOP
```
`python`, not `python3`. Exit codes read bare. No heredoc for file content. No `git add -A`.

---

## LANE A — safeguarding P0 (spec 1)

### A-R1 baseline, fix nothing
**Know before you start:** `71b069d` (in this branch) already pins the audit sentence at the classifier in both languages (`tests/test_safeguarding_italian.py:54,:84`, `tests/test_safeguarding_parity.py:59-60`). Expect the classifier half of R1 to be green; the route half is what nobody has measured. Build the corpus from `~/Downloads/CLAUDIA_SAFEGUARDING_RETEST_2026-09-02.md` if present (it is not in the repo — copy its rows into the test, credit it) or from spec §2.1: RED rows 1.1–1.3, GREEN rows 2.1–2.5, plus every row already in `tests/test_safeguarding_italian.py`. For each row record:
- `classify_severity(text).tier` and `rounded_up`
- through the sandboxed server, one student `student-aiken-test` created via the roster chain: `POST /api/observe/capture` with `student_confirmed: true` → response keys, `restricted`, `observation` present?, ledger line count, `pending_notifications()` count and state
- then the four normal surfaces: `GET /api/students/{id}/lens` observations count, `GET /api/students/{id}/lens/markdown` contains any 4-letter-or-longer word of the sentence?, `POST /api/parents/recommendation` body contains any?, `lv lens-query L11 --term scared --names` hits
- the voice route with the same sentence (`POST /api/voice/act {transcript}`), same checks

Write `dev/BASELINE_SAFEGUARDING_P0_2026-09-04.md` with the table, commit it. **If every row is already RED and absent everywhere, that is K1: stop lane A's build, write the finding (the 29 August failure does not reproduce on this tree; name the commits between v0.2.72 and HEAD that touch `safeguarding.py`), still build A-R2(c)(d) — the pending route and the badge are independent of detection — and move to lane B.**

### A-R2 build, in this order, one commit each
1. If R1 shows the sentence is not RED: the indicator class (spec §2.1) with its Italian pair; parity test; the corpus test red-then-green.
2. `tests/test_safeguarding_surfaces.py`: the §2.2 assertions through the typed route on a sandboxed app (`fastapi.testclient`), EN and IT rows parametrised. Record which were green before you changed anything.
3. `GET /api/safeguarding/pending` in `routers/safeguarding.py`, coordinator-gated exactly like `/drain`; content-free; `tests/test_safeguarding_promise_honesty.py` extended to it.
4. The badge + the `pending_config` sentence in `static/index.html` for coordinator/admin. **Do not run `check_ui_contract.py --bump`.** Leave the lock red on this box and say so in the report; the operator bumps it on PC-0.
5. `contracts/ROUTE_REACHABILITY.yaml`: the pending route as `reachable_from_ui` with the badge's literal call site, or `deferred_undecided` if you did not land the badge.

### A-R3 sabotage (each restored by inverse edit, never `git checkout`)
| plant | must produce |
|---|---|
| remove the new indicator row (if added) | corpus test red |
| make `capture_with_safeguarding` fall through to `pipeline.capture` on RED | every surface test red |
| make the pending route return `count: 0` always | badge/honesty test red |
| put a transcript word in the pending route's payload | honesty test red |

### A exit gate
Corpus green, surfaces green in both languages, pending route + honesty green, sabotage all observed red, `python scripts/check_route_reachability.py` exit 0, the bounded suite (`-k "safeguard or observ or lens or parent"`) diffed test-id for test-id against your baseline: **new failures are reported as new failures.**

---

## LANE B — the parent note's tone (spec 2)

### B-R1 baseline, fix nothing
On the sandbox: roster → Abigail report card → `POST /api/parents/recommendation`. Save the body bytes. List every code-like token (`ATL:`, `grade descriptor:`, any of `IB_LEARNER_PROFILE`, any `VALID_CEFR_LEVELS` code). Record `source_entry_ids` and `source_observation_ids` counts. Commit `dev/BASELINE_PARENT_NOTE_TONE_2026-09-04.md`.

### B-R2 build, one commit each
1. The phrase map in `parent_report.py`, keyed to the extractor's constants (import them; never retype the vocabulary). `unmapped_terms` on the draft and in the endpoint response.
2. `lenses/VOICE-EDU-001_malaguzzi_inspired.yaml` sidecar + the reader in `generate_draft`; **no sidecar → bytes identical to B-R1** (test it by removing the file in the test).
3. Frames with deterministic variety (`hash(student_id + reporting_period)`), each frame with an `it` slot declared.
4. `tests/test_parent_note_tone.py`: zero codes on the Abigail note (red first); byte-identity without the sidecar; every sentence traced; `it` slots declared for every entry; forbidden registers refused.

### B-R3 sabotage
| plant | must produce |
|---|---|
| delete the sidecar | frames revert, bytes identical to B-R1 — test green, and *say* it is the byte-identity test that proves the sidecar is optional |
| delete one map entry | `unmapped_terms` counts it; the zero-codes test red |
| add a frame with no backing source | traceability test red |
| put "struggles with" in a frame | register test red |

### B exit gate
Zero codes on both fixtures, traceability unchanged, no-sidecar byte-identical, `it` slots declared, the parent-report suites green (`tests/test_parent_report*.py`, `tests/test_launch_privacy_safety.py`, `tests/test_launch_teacher_day.py`).

---

## Kill gates, both lanes — stop and report, do not work around
A-K1 corpus green on the untouched tree (the deliverable becomes the finding) · A-K2 a name or transcript word in any new surface · A-K3 RED reaches `pipeline.capture` / `append_observation` · A-K4 an EN or IT row without its pair · A-K5 the drain runs in the background · B-K1 a sentence without a source id · B-K2 a model call in the note path · B-K3 a code in a rendered note after the map · B-K4 no-sidecar bytes differ from baseline · B-K5 a frame or map entry without an `it` slot · B-K6 `personal_context` or a `needs` entry in a note · **both** K-UI `check_ui_contract.py --bump` from PC-23 · **both** K-HEAD HEAD moved between writes · **both** K-HOME any measurement needed the operator's real `~/.lingua-viva`.

A kill gate that fires is a success. Say so plainly.

## The report
`dev/REPORT_SAFEGUARDING_P0_AND_PARENT_TONE_2026-09-04.md`: state at close (branch, HEAD, pushed, the UI lock's state); the delta per lane with denominators; every kill gate and whether it fired; every sabotage and what it turned red; **what you got wrong**; open-and-whose (the R4 witnesses are Claudia's and a coordinator's — they are not yours to mark done); every CANNOT-TELL. Push the branch. Never `main`.
