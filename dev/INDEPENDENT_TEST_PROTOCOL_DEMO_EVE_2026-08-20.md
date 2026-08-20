# Independent Test Protocol — Demo-Eve Build (2026-08-20)

**Build under test:** desktop-v0.2.67 (or whichever tag is live at
https://linguaviva.art when you begin — check the download button URL).

**What changed since v0.2.65:** six fixes (F1–F5 + a partial-fill roster fix),
all targeting the three demo-blocking capability defects found in the v0.2.65
independent test. The five lying patterns found in the v0.2.64 test remain dead
(verified in v0.2.65). This protocol tests the NEW fixes without re-running the
full lying-patterns audit — that protocol is at
`dev/INDEPENDENT_TEST_PROTOCOL_REAL_DATA_2026-08-19.md` if you want to double-check.

**Privacy (non-negotiable):** test files contain real student names. Screenshots
and raw backend captures stay on the test machine — never committed, never pasted
into shared docs. Your written results use COUNTS and redacted placeholders only.

---

## 0. Setup

1. **Download from the live site** (https://linguaviva.art) — the Mac, Windows,
   or Linux button. Do NOT side-load a dev build.
2. **Record the version** the app displays in the topbar (new: F4 added a version
   badge next to the route badge). It must match the release tag from the download
   URL. If it doesn't, STOP — you're testing a stale or broken build.
3. **Record the environment:** OS, RAM, GPU/VRAM, `ollama list` output.
4. **Fresh home:** if `~/.lingua-viva/` exists, rename it aside. This protocol
   assumes zero prior state.
5. **Get the test files** onto the machine (private channel):
   - `2026-2027 Class List Drafts.xlsx` (the grade sheet)
   - `3V ES Student Support.xlsx`
   - `ES Student Support (K-5) 2025-2026.xlsx`
   - A curriculum mapping xlsx (any)
   - A 6-day calendar xlsx (any)
   - The 2-page IB PDF (chameleon/lizard-brain unit)

---

## 1. Expected Numbers (human-confirmed 2026-08-20)

| File | Expected | FAIL if |
|---|---|---|
| Curriculum mapping xlsx | **0 students** | any detection |
| 6-day calendar xlsx | **0 students** | any detection |
| Class list, her class (Grade 3 Verdi, col A/B) | **18 students** | ~35 (group-table fusions), 11 (block cut short at partial-fill row), 41 (both class columns merged), teachers as students |
| 3V support xlsx | **6 students** (abbreviated names) | 0, garbage |
| K-5 support xlsx | ~76, no roles as students | headers/roles as students |

**End-to-end after all imports:** 18 lenses for the one class, enriched from
support files, 0 lenses from curriculum/calendar. That single count is the gate.

---

## 2. The Fixes — What Specifically to Verify

### F1 — Roster-block segmentation (P0)

**What it fixed:** importing the class list fabricated children (18 → 35) because
group tables (Music/STEAM) below the roster were processed with the surname+firstname
join rule, fusing two real names into one fake student.

**How to test:**
1. Import the class list xlsx.
2. In the preview, verify **18 names** for her class — not 35, not 11.
3. Look for the **source_rows** provenance on each entry (e.g., "Grade 3 rows 3–20
   cols A+B"). If visible, it confirms the block segmentation.
4. Confirm that NO group-table names appear (these would be full names like
   "Aiken Aleahmed-Boyce" in a single cell, not split across surname/firstname).
5. **Preview must write nothing** — check store count before and after preview.
   Only the explicit Confirm button creates lenses.

### F1b — Per-entry exclude in preview

**What it fixed:** previously it was all-or-nothing — create all 35 or Cancel.

**How to test:**
1. In the preview (before confirming), click/tap a name pill to toggle it OUT.
2. The confirm button count must update (e.g., "Confirm 17" instead of "Confirm 18").
3. Confirm. The excluded name must NOT appear in the student store.
4. Re-import the same file — the excluded student should appear in the preview again
   (the exclusion was one-time, not permanent).

### F2 — Zero-data refusal gate (P0)

**What it fixed:** Ask said a child was "making good progress… working on basic
sentences" when that child had zero observations, zero evidence, and no CEFR data.
The model fabricated a confident-sounding progress narrative from nothing.

**How to test:**
1. After importing the class list and confirming, open Ask.
2. Select a student who has **no observations** (any freshly created lens).
3. Ask a progress question: "How is [student] doing?"
4. The response must be a **refusal** — something like "There are no observations
   recorded for this student yet." It must NOT contain progress claims, ability
   descriptions, or sentences-in-progress claims.
5. The refusal must still play through TTS (voice reads it aloud).
6. Verify `route=local` on the response (the route badge in the topbar).

### F3 — Packet prints stored reviewed artifact (P0)

**What it fixed:** "Preview Printable Packet" fired three FRESH model calls; the
printed packet differed from the reviewed tier cards. Teacher review was defeated.

**How to test:**
1. Go to Prepare, generate materials for a lesson (using the IB PDF).
2. **Note the exact text** of the three tier cards on screen.
3. Click "Preview Printable Packet."
4. The packet text must be **byte-identical** to the reviewed cards. Compare the
   Italian (or language-of-instruction) phrases specifically — if they differ,
   the old bug is back.
5. **Check the trace count** (backend model calls): generation should have produced
   a trace; the preview should produce **zero additional model calls**. If you
   can access backend logs, look for model invocations between the generate and
   preview steps — there must be none.
6. Click "Regenerate" — new content appears. Preview again — the new content prints,
   not the old content.

### F4 — App version in UI

**What it fixed:** no way to verify which build the teacher was running.

**How to test:**
1. Look at the topbar, next to the route badge.
2. A version badge must be visible (e.g., "v0.2.67").
3. It must match the `desktop/package.json` version and the release tag.

### F5 — Honest import copy

**What it fixed:** the import box said "Every student gets a profile automatically;
one click undoes the whole import" — describing a model that v0.2.65 deliberately
replaced with preview-first.

**How to test:**
1. Open the Students view.
2. Read the import box description text.
3. It must say something about "Nothing is created until you review and confirm" —
   NOT "Every student gets a profile automatically."
4. Import a non-student xlsx (e.g., the curriculum) — the "no students found" message
   should NOT say "try a Word or text version" for an xlsx. It should give
   spreadsheet-relevant guidance.

---

## 3. Arc A — Full Import Sequence

| # | Action | Expected | Verify |
|---|---|---|---|
| A1 | Open Students, fresh app | 0 students | Screenshot |
| A2 | Import curriculum xlsx | Preview: 0 students | Store count unchanged |
| A3 | Import calendar xlsx | Preview: 0 students | Store count unchanged |
| A4 | Import class list xlsx | Preview: **18 names** for her class, per-entry toggles visible | Store count STILL 0 (preview-never-writes) |
| A5 | Toggle one name OUT, then Confirm | 17 lenses created (the toggled name absent) | Store count = 17 |
| A6 | Re-import class list | Preview shows 18 again (including the previously excluded one) | Store count still 17 (preview-never-writes) |
| A7 | Confirm (all 18 this time) | The previously missing student created; duplicates NOT created | Store count = 18 |
| A8 | Import 3V support xlsx | 6 recognized; her 3 matched to existing lenses (enrich, not duplicate) | Store count must NOT grow by 6 |
| A9 | Import K-5 support xlsx | ~76 recognized; enrichment only, no duplicates | Store count stays 18 |
| A10 | Open one enriched lens | Support info visible, traceable to source file | Screenshot (redact names) |

---

## 4. Arc B — Lesson Content + Packet Integrity

| # | Action | Expected | Verify |
|---|---|---|---|
| B1 | Prepare → upload IB PDF | Metadata pre-fills with real document title | Screenshot |
| B2 | Generate materials | 3 tiers grounded in document content; foundational NOT blank | Model used + timing |
| B3 | Note the exact text of all 3 tiers | Save locally (redacted) for comparison | Text file |
| B4 | Preview Printable Packet | Packet text **identical** to B3 text; zero new model calls | Compare text; check logs |
| B5 | Print student handout | No teacher-only / individual-support content in student variant | Screenshot |
| B6 | Regenerate | New content appears (may differ from B3) | Note new text |
| B7 | Preview packet again | Prints the NEW (B6) content, not the old (B3) content | Compare |
| B8 | If generation fails at any step | Honest on-screen signal, never silent filler | Screenshot + log |

---

## 5. Arc C — Zero-Data Refusal

| # | Action | Expected | Verify |
|---|---|---|---|
| C1 | Select any student with 0 observations | Lens exists but empty | Screenshot |
| C2 | Ask: "How is [student] doing?" | **Refusal with reason** — no progress claims, no ability descriptions | Full response text |
| C3 | Verify TTS reads the refusal | Voice plays the refusal aloud | Listen |
| C4 | Add ONE observation for that student | Normal observation flow | Observation saved |
| C5 | Ask same question again | Normal response, grounded in the observation | Compare to C2 |

---

## 6. Arc D — Hostile Pokes (15 min)

- Import a random non-school xlsx — graceful zero-detection.
- Import the class list twice with no changes — no duplicates.
- Kill network mid-session — local-first must not break.
- Cancel a preview at every stage — zero writes.
- Import the class list without selecting a class (if the UI allows it) — must
  not mass-create all 212 students across all grades.

---

## 7. Reporting Format

```
# Demo-Eve Test Run — <date> — <machine nickname>
Build: <release tag> / app-reported version <from topbar badge>  [MUST match]
Environment: <GPU/VRAM/RAM/OS>; ollama list: <models>
Fresh home: yes/no

## Verdict: PASS / FAIL / MIXED  (one line why)

## Scorecard
| File | Expected | Actual | PASS/FAIL |
|---|---|---|---|
| Curriculum | 0 | | |
| Calendar | 0 | | |
| Class list (her class) | 18 | | |
| 3V support | 6 | | |
| K-5 support | ~76 | | |
| End-to-end lens count | 18 | | |

## Per-arc results
### Arc A (imports)
A1: PASS/FAIL — ...
...
### Arc B (lesson content + packet)
B1: PASS/FAIL — ...
...
### Arc C (zero-data refusal)
C1: PASS/FAIL — ...
...
### Arc D (hostile pokes)
...

## Fix-specific checklist
- [ ] F1: 18 students, not 35 or 11 — group tables excluded
- [ ] F1b: per-entry toggle works, count updates, exclusion is one-time
- [ ] F2: zero-data student gets honest refusal, not fabricated progress
- [ ] F3: packet text identical to reviewed cards, zero model calls on preview
- [ ] F4: version badge visible in topbar, matches release tag
- [ ] F5: import copy says "review and confirm", not "automatic"

## Contradictions found (screen vs backend)

## Findings not covered by this protocol

## Raw artifacts (kept local)
```

Report FAILs immediately — don't wait for the full run. A precise FAIL with
evidence is worth more than ten vague PASSes.
