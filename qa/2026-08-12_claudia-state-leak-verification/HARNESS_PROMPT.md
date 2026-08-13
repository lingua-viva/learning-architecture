# Harness Prompt — State Leak Verification + Core Teaching Workflow
# Claudia Canu, 2026-08-12, Lingua Viva v0.2.56

## To Claude Code: read this entire file before starting

You are running a QA verification session with **Claudia Canu** — the
curriculum architect and Italian K-5 educator who IS the product's real user.
She is not a QA engineer; she is a teacher. Frame everything in terms she
uses daily (students, observations, lesson prep), not in terms of APIs or
state variables.

**Version gate:** The app MUST be desktop-v0.2.56 or newer. Check
Settings or the title bar. If older, stop — ask her to re-download from
linguaviva.art.

**What we're testing:** A fix for two bugs Chip found tonight:
1. Selecting a student in Observe, then switching to Students, caused errors
   or showed the wrong student's data (stale state leak).
2. "Programme of Inquiry Progression: Request failed: 404" appearing on every
   student detail view (missing router in packaged app).

Plus: a quick pass through the core teaching workflows to confirm nothing
regressed.

**Synthetic data only.** Students: **Marco Bianchi** (G3, A2 speaking) and
**Nora Rossi** (G3, B1 speaking). Never use real children's names.

**Pacing:** One step at a time. Wait for her reply before moving on. If she
says something is confusing, explain it simply — she speaks fluent English but
thinks in Italian pedagogical terms. Use her framework language when possible
(PoI = Programme of Inquiry, UdA = learning unit, CEFR levels, Indicazioni
Ministeriali).

**Honest degradation rule:** If the app says a model isn't available and shows
a plain message or deterministic answer, that is a PASS. A raw error, a
traceback, or silence is a FAIL.

---

## Phase 1 — Setup (~5 min)

### Step 1: Fresh install gate
Ask Claudia:
> Is the app open? What does the title bar or Settings page say for the
> version number?

**PASS:** v0.2.56 or newer, app loads, no error banner.
**FAIL:** App won't open, error on launch, version older than v0.2.56.

### Step 2: Seed two students
Walk her through:
1. Go to **Students** tab.
2. Use the "Add Student" form at the bottom: **Marco Bianchi**, Grade **G3**.
   Click Add.
3. Same for **Nora Rossi**, Grade **G3**. Click Add.
4. Both should appear in the roster.

**PASS:** Both students visible in the roster list.

### Step 3: Seed observations
Walk her through:
1. Go to **Observe** tab.
2. Select **Marco Bianchi** from the Student dropdown.
3. Type in the observation box: `A learner self-corrected piazza/prossima,
   used essare correctly in context.`
4. Set Observation type to **General**, leave other fields as they are.
5. Click **Save**.
6. Now select **Nora Rossi**.
7. Type: `Nora used full sentences to describe her weekend in Italian,
   including past tense correctly.`
8. Save.

**PASS:** Both observations save with a confirmation. No error messages.

---

## Phase 2 — The Bug Chip Found (~10 min)

This is the PRIMARY verification. Go slowly. Record exactly what happens.

### Step 4: Observe → Students (the core bug)
Walk her through:
1. Go to **Observe** tab.
2. Select **Marco Bianchi** from the dropdown. His data should load on the
   right side (recent observations, support profile).
3. Now click **Students** in the sidebar.

**PASS:** Students tab loads normally. Roster is visible. No error message.
The lens panel either shows "Choose a student" placeholder OR is empty.
Marco is NOT pre-selected.
**FAIL:** Error message takes over the page, or Marco's data is already
showing without clicking on him.

### Step 5: Students → Observe → Students (round-trip)
1. In **Students**, click on **Nora Rossi** to load her lens.
2. Click **Observe** in the sidebar.
3. Check the Student dropdown — it should say "Choose a student..." (the
   placeholder), NOT "Nora Rossi".
4. Click **Students** in the sidebar again.

**PASS:** Students tab loads cleanly. Nora is NOT pre-selected. No error.
**FAIL:** Nora is still selected, or an error appears.

### Step 6: Rapid tab switching (stress test)
Ask her:
> Click back and forth between Observe and Students about 10 times, quickly.
> Tell me if anything breaks, flashes red, or shows an error.

**PASS:** No errors across 10 switches.
**FAIL:** Any error, crash, or "Request failed" message.

### Step 7: Archive → tab switch (the hard case)
1. Go to **Students**. Click on **Marco Bianchi**.
2. Scroll down to the **Archive student** button. Click it, confirm the
   dialog.
3. Marco disappears from the roster.
4. Click **Observe**, then click **Students** again.

**PASS:** Students tab loads. Roster shows only Nora. No error, no
"Request failed: 404", no stale Marco data.
**FAIL:** Error page, Marco's stale data visible, or "Request failed" message.

5. **Un-archive Marco** (or re-add him as "Marco Bianchi", G3) so later
   checks have two students. Note: if un-archive isn't available, just
   re-add him.

### Step 8: PoI Progression panel (Bug 2)
1. Go to **Students**. Click on **Marco Bianchi** (or whichever student).
2. Scroll down to **Programme of Inquiry Progression**.

**PASS:** Panel shows "No PoI activity recorded yet" or actual data.
**FAIL:** Panel shows "Request failed: 404" or any other error text.

3. Click on **Nora Rossi** and check the same panel.

**PASS:** Same — clean empty state or data, no error.

---

## Phase 3 — Core Teaching Workflows (~20 min)

Quick pass through the workflows a teacher uses daily. We're checking nothing
regressed from the state-leak fix.

### Step 9: Observe a student — full workflow
1. Go to **Observe**.
2. Select **Marco Bianchi**.
3. Type: `Marco raised his hand three times during the vocabulary review today.`
4. Set Observation type → **General**.
5. Click **Save**.

**PASS:** Saves with confirmation. Observation appears in "Recent
observations" on the right panel. No error.

### Step 10: Check the student lens updated
1. Go to **Students**. Click **Marco Bianchi**.
2. Look at his **Recent observations** section.

**PASS:** The new observation from Step 9 is visible.
**FAIL:** Missing, or shows data from a different student.

### Step 11: Ask about a student
1. Go to **Ask** tab.
2. Type: `What do I know about Marco's speaking ability?`
3. Wait for the response (~30 seconds).

**PASS:** Response references his observations. If no model is available,
an honest "no model" message is fine. No fabricated data.
**FAIL:** Fabricated observation IDs, data from Nora appearing in Marco's
answer, or a raw error/traceback.

### Step 12: Lesson materials (Prepare tab)
1. Go to **Prepare** tab (if it exists).
2. If there's a way to generate lesson materials, try it for Marco's class.
3. If no Prepare tab, go to **Ask** and type:
   `Help me plan a 30-minute Italian lesson on daily routines for Grade 3.`

**PASS:** Produces something useful (tiers, activities, or a lesson
outline). No student names in the generated content.
**FAIL:** Student names in generated materials (P0), raw error, or hang.

### Step 13: Student Summaries (formerly Parent Reports)
1. Go to **Summaries** tab (or wherever parent/student summaries are).
2. Generate a summary for **Marco Bianchi**.
3. Read it as if you were Marco's parent.

**PASS:** Warm, plain language. Based on real observations. No jargon, no
internal codes, no other student's data.
**FAIL:** Nora's data in Marco's report, fabricated observations,
restricted/safeguarding content visible, or raw error.

### Step 14: Tab-switch stress after all workflows
Now that data exists in multiple places:
1. Click **Observe** → **Students** → **Ask** → **Students** → **Observe** →
   **Summaries** → **Students**.
2. At each Students landing, check: no pre-selected student, no error.

**PASS:** Clean navigation throughout. "Choose a student" placeholder every
time on Students (until she clicks one).

---

## Phase 4 — Safeguarding Quick Check (~5 min)

### Step 15: Concerning observation routing
1. Go to **Observe**. Select **Marco Bianchi**.
2. Type: `Marco said his dad hits him at home.`
3. Save.

**PASS:** Saves calmly (no scary popup). But the harness should verify via
the API that it was routed to the restricted ledger.

**Harness (Claude Code):** Call `GET /api/safeguarding/restricted` — this
should be denied (teacher role). Then check Marco's normal observation list
(`GET /api/students/{marco_id}/lens`) — the concerning observation should
NOT appear there.

### Step 16: Benign contact phrase (over-flagging check)
1. Still in Observe, Marco selected.
2. Type: `Marco hit the ball hard at recess and laughed.`
3. Save.

**PASS:** Saves as a NORMAL observation. Visible in Marco's record in
Students tab.
**FAIL:** Flagged as concerning (over-flagging = alert fatigue, P1).

### Step 17: Cross-contamination check after safeguarding
1. Go to **Students** → **Marco** → scroll through his observations and
   profile.

**PASS:** The recess observation (Step 16) is visible. The concerning
observation (Step 15) is NOT visible.

---

## Phase 5 — Claudia's Eye (~5 min)

This is the most important part. Ask her, in her own words:

1. **Does this feel like a tool you would use in your classroom tomorrow?**
   If not, what's the one thing blocking you?

2. **When you looked at a student's profile, did it make sense to you as a
   teacher?** Was anything confusing, or did anything look wrong?

3. **What's missing?** What would you expect to see that isn't there?

4. **Did anything surprise you — good or bad?**

5. **If you were training Olga's teachers to use this, what would you warn
   them about?**

Record her answers verbatim.

---

## Reporting

When Claudia says "I'm done" or you finish all steps, write a report to:

```
qa/2026-08-12_claudia-state-leak-verification/REPORT.md
```

**Report format:**

```markdown
# QA Report — State Leak Verification (Claudia Canu, 2026-08-12)

**App version:** desktop-v0.2.XX
**Platform:** [macOS / Linux / Windows]
**Duration:** ~XX min
**Tester:** Claudia Canu (real teacher, product user)

## Verdict

[ONE LINE — e.g., "Bug 1 FIXED, Bug 2 FIXED, no regressions found" or
"Bug 1 fixed but new issue in Step X"]

## Bug Verification

| Step | Check | Result | Notes |
|------|-------|--------|-------|
| 4    | Observe→Students state leak | PASS/FAIL | ... |
| 5    | Round-trip tab switch | PASS/FAIL | ... |
| 6    | Rapid tab switching ×10 | PASS/FAIL | ... |
| 7    | Archive→tab switch | PASS/FAIL | ... |
| 8    | PoI panel (no 404) | PASS/FAIL | ... |

## Teaching Workflow Regression

| Step | Check | Result | Notes |
|------|-------|--------|-------|
| 9    | Observe save | PASS/FAIL | ... |
| 10   | Lens update | PASS/FAIL | ... |
| 11   | Ask grounding | PASS/FAIL | ... |
| 12   | Lesson materials | PASS/FAIL | ... |
| 13   | Student summaries | PASS/FAIL | ... |
| 14   | Multi-tab stress | PASS/FAIL | ... |

## Safeguarding

| Step | Check | Result | Notes |
|------|-------|--------|-------|
| 15   | Restricted routing | PASS/FAIL | ... |
| 16   | Benign not over-flagged | PASS/FAIL | ... |
| 17   | No cross-contamination | PASS/FAIL | ... |

## Claudia's Feedback (verbatim)

1. Ready for classroom? ...
2. Student profile clarity? ...
3. What's missing? ...
4. Surprises? ...
5. Warnings for other teachers? ...

## New Findings (if any)

[Anything not in the checklist that she noticed — new bugs, UX friction,
feature requests. Each with severity P0/P1/P2/FR.]
```

**After writing the report**, tell Claudia:
> Thank you! Your report is saved. Mical will review it.
