# Independent Test Protocol — Real-Data Build (2026-08-19)

**Who this is for:** a tester on a SEPARATE machine, independent of the dev machine,
verifying the unified real-data fix build the way a real teacher would use it.

**The standard:** what is on the screen is the only truth. A green test suite, a 200
response, or "the backend says it worked" counts for NOTHING here. Five days of false
"everything works" came from trusting the system's own reporting — this protocol exists
to break that pattern. The system has lied in five specific ways (listed in §4); your
job is to catch them, not to confirm success.

**Privacy (non-negotiable):** the test files contain real student names. Screenshots and
raw backend files stay on the test machine / private channel — never committed, never
pasted into shared docs. Your written results use COUNTS and redacted placeholders
("student #12", "teacher row") only.

---

## 1. Setup — do this before anything else, record everything

1. **Install from the live site** (linguaviva.art), exactly as a stranger would.
   No dev builds, no side-loaded artifacts. If the site's download is not the new build,
   STOP and report that first — testing a stale build is how false audits happen.
2. **Record the version** immediately: the release tag you downloaded, and the version
   the running app reports (Settings/About). They must match. Screenshot it.
3. **Record the environment:**
   - `ollama list` output (full)
   - GPU + VRAM (`nvidia-smi` or equivalent), RAM, OS
   - whether `~/.lingua-viva` existed before install (it should NOT — if this machine
     has old state, back it up and move it aside; we are testing "any teacher, zero
     special access," which means a fresh home)
4. **Get the test files** onto the machine (private channel): the 5 xlsx school files +
   the 2-page IB PDF. Verify file names/sizes match the manifest you were given.
5. **Baseline the backend** (see §3 for how): student store count = 0, no pending Drive
   queue, empty ingest-review queue. Screenshot/save.

---

## 2. What "success" is — the only numbers that count

| Import | Expected result | FAIL if |
|---|---|---|
| Curriculum mapping xlsx | **0 students detected** | any detection at all |
| 6-day calendar xlsx | **0 students detected** | any detection at all |
| 3V support xlsx | **6 students** (abbreviated names) | 0, or garbage names |
| Class list xlsx, scoped to the teacher's class | **~39, attributed to her class** | 400+, teachers-as-students, class names as students |
| K-5 support xlsx | ~76, no roles (e.g. "Include Specialist") as students | roles/headers as students |

**End-to-end:** after importing all five files the app holds **~39 lenses for the one
class, enriched from the support files, ZERO lenses originating from the curriculum or
calendar files.** Count them. That single number is the product requirement.

**Content side:** the real IB PDF generates 3 tiers that visibly reference the actual
document content (chameleon/lizard-brain material — you will recognize it), within a
tolerable wait, OR the app says honestly on screen that generation did not run. Generic
text like "Read the example about <topic>. Write three complete practice sentences." is
the known template-filler signature = FAIL if presented as generated.

---

## 3. Backend recording — capture these around EVERY test step

All app state lives under `~/.lingua-viva/` (the runtime home). Before/after each import
or generation, capture:

1. **Student store count + IDs** — before/after snapshot. The critical check:
   **preview must write NOTHING.** Same count before preview and after preview, every
   time. Only the explicit confirm may change it.
2. **Drive sync queue** — nothing may be enqueued by a preview, and nothing may sync
   anywhere without an explicit confirmed import. If the app offers a sync
   status/ledger view, screenshot it after each step.
3. **Import/extraction warnings** — record every warning string verbatim (redact
   names). Two known dishonest signatures to specifically hunt:
   - `model_enrichment_discarded: invalid JSON after retry` — historically this
     MISREPORTED a privacy refusal. If you see it, flag it; the new build must report
     the true reason.
   - any error/empty result presented with no on-screen consequence.
4. **Which model actually ran, per generation call** — the new build logs the model
   used on every call. Record model name + wall-clock time for every generation. If you
   cannot find where the model-used is surfaced/logged, that is itself a FINDING —
   record it.
5. **Timing** — stopwatch every import and every generation. Note anything ≥30s and
   anything that hits exactly ~60s (the timeout signature).
6. **App logs** — locate the app/backend log location, note it in your report, and save
   a copy of the log after each major step (label them: `after-import-1.log` etc.).
   Keep them local; quote only redacted excerpts.
7. **Screenshots at every numbered step of §5** — named `A3-preview.png` style. Local
   only.

If any backend observation contradicts what the screen says, that contradiction is the
single most valuable finding you can file. Record both sides precisely.

---

## 4. The five known lying patterns — what to look out for

1. **Failure presented as success.** Plausible-looking output that was actually a
   deterministic template (see the filler signature in §2). Cross-check: does the
   output reference the ACTUAL uploaded document's content, or could it have been
   produced without reading it?
2. **Wrong failure reasons.** An error message whose stated cause doesn't match backend
   logs. Always compare the on-screen message against the log line.
3. **Gates that cannot fail.** If every detection shows the same confidence value
   (historically flat 0.99), confidence is decorative — record the confidence values
   you see across different files.
4. **Environment-dependent breakage.** The dev machine's model lineup masked bugs. Your
   different `ollama list` is the point of independent testing — if behavior differs
   from the dev machine's report, capture your model list alongside the finding.
5. **No denominator.** Never report "N students detected" alone — always report it
   against the expected number from §2's table.

Also watch for (previous-generation bugs that must stay dead):
- blank foundational tier (empty instructions/exercise for the weakest students)
- document title pre-filled with school letterhead instead of the real title
- the same import run twice creating duplicates
- teachers ingested as students; Italian story/song titles as students

---

## 5. The test script — two arcs, in order

### Arc A — Student lenses (the ~39)

| # | Action | Expected on screen | Record |
|---|---|---|---|
| A1 | Open Students view, fresh app | zero students, coherent empty state | screenshot |
| A2 | Import the CURRICULUM xlsx | **preview shows 0 students**; no create offered/needed | store count unchanged (§3.1) |
| A3 | Import the CALENDAR xlsx | **preview shows 0 students** | store count unchanged |
| A4 | Import the CLASS LIST xlsx | preview appears BEFORE anything is created; class/teacher scoping offered; her class ⇒ ~39 names, no teachers in the list | screenshot preview; store count STILL unchanged |
| A5 | Confirm creation | ~39 lenses exist, attributed to her class | store count = ~39; Drive queue state |
| A6 | Import the 3V SUPPORT xlsx | 6 students recognized; her 3 matched to existing lenses (enrich, not duplicate); the other 3 handled visibly (ignored or queued — but VISIBLY) | store count must NOT grow by 6; unresolved queue contents |
| A7 | Open one enriched lens | support info in the correct categories, traceable to the source file | screenshot (redact before sharing) |
| A8 | Import the K-5 xlsx (last year) | no duplicate lenses; whatever the build's ruling on history, behavior is explained on screen | store count delta; any duplicates = FAIL |
| A9 | Re-run one import identically | no duplicates, honest "already imported"-type behavior | store count unchanged |
| A10 | Undo/preview-cancel path | cancelling a preview leaves zero trace | store count |

### Arc B — Lesson content (the 3 tiers)

| # | Action | Expected on screen | Record |
|---|---|---|---|
| B1 | Prepare view → import the IB PDF (local upload) | metadata pre-fill uses the real document title (NOT school letterhead); unit detected | screenshot |
| B2 | Generate materials | 3 tiers, each grounded in the actual document; foundational tier NOT blank; wait time tolerable | model used + timing per call (§3.4/5) |
| B3 | Inspect all 3 tiers | no template-filler signature; tiers differ meaningfully | full text saved locally |
| B4 | If generation fails | an HONEST on-screen signal ("AI generation did not run"), never silent filler | screenshot + log line |
| B5 | Packet preview/print | student-facing packet contains no teacher-only/individual-support content | screenshot |

### Arc C — Hostile pokes (15 minutes, after A+B pass)

- Import a random non-school xlsx/PDF you have lying around — expect graceful, honest
  handling, zero student detections from non-student docs.
- Kill the network (airplane mode) mid-session — the app is local-first; generation and
  lenses must not break or silently change behavior.
- Import the class list with NO class selected (if possible) — must not mass-create.

---

## 6. Reporting format

One MD file per run:

```
# Independent Test Run — <date> — <machine nickname>
Build: <release tag> / app-reported version <...>  [MUST match]
Environment: <GPU/VRAM/RAM/OS>; ollama list: <models>
Fresh home: yes/no

## Verdict: PASS / FAIL / MIXED  (one line why)

## Scorecard (fill §2 table with actuals)

## Per-step results (A1..A10, B1..B5, C)
<step>: PASS/FAIL — what happened — evidence file names

## Contradictions found (screen vs backend)  ← most valuable section

## Findings not covered by this protocol

## Raw artifacts (kept local): <list of screenshots/logs/store snapshots>
```

Report FAILs as you find them — don't wait for the full run if something demo-blocking
appears. A FAIL with precise evidence is worth more than ten vague PASSes.
