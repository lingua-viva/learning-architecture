# UX Walkthrough Harness — Claudia's Daily Workflow (2026-08-29)

## To Claude Code: read this entire file before starting

You are walking **Claudia Canu Fautre** through every screen of Lingua Viva,
one at a time, as she would use it on a real teaching day. She teaches K-5
Italian immersion at Still I Rise and La Scuola. She is not a developer.
**If something confuses her, slows her down, or looks wrong — that is a
finding.** She is the final judge of whether something works for a teacher.

**Do not fix anything.** Do not call APIs on her behalf unless a feature has
no button yet. Record what she sees and says. One step at a time — wait for
her reply before moving on.

### App state

The app is running at http://127.0.0.1:8787, version desktop-v0.2.72.
Students are already loaded (Still I Rise class — ~40 students including
Boyce Aiken, Corazza Miro, Fujinaga Midori, Kleuser Noemi, Scala Luca, etc.).
Use these real test students throughout — no need to create new ones.

For any safeguarding scenario, use invented phrases about these students.
They are synthetic test data.

### Reporting

Create `qa/2026-08-29_claudia-full-audit/UX_REPORT.md` at session start.
File every finding the moment she reports it:
- **FRICTION** — UX slows her down, confuses her, or requires extra clicks
- **BUG** — something broken, wrong output, error shown
- **GOOD** — something she likes (capture these too)
- **FR** — feature request

ID format: `FRICTION-1`, `BUG-1`, `GOOD-1`, `FR-1`, sequential.
Quote her words — do not soften them.

After each view, give her a running count.

---

## The Walkthrough — View by View

Go through every sidebar view in order. For each one:
1. Tell her to click that sidebar item
2. Ask her: "What do you see? Is it clear what to do here?"
3. Walk her through the main action for that view
4. Ask her: "Would this help you at 8am on a Monday, or would it waste your time?"
5. Record her verdict, move to the next view

---

### View 1 — HOME

Tell her to look at the Home screen.

- Does the greeting make sense for the time of day?
- Does the "next action" strip suggest something useful, or is it generic?
- Are the counts correct (observations to renew, decisions to review)?
- Is it obvious what to do first?
- Click "Go to Observe" — does it take her there?
- Come back to Home.

---

### View 2 — DAILY

Click the Daily tab.

- What shows up? Is there a daily briefing?
- If Slack isn't connected, is that clear without being alarming?
- Is this view useful to her, or does it feel empty?

---

### View 3 — PLAN

Click Plan.

- Can she find her grade? Click a grade band (e.g. G3).
- Do units appear? Are they recognizable curriculum units?
- Click "Plan from this unit" — does it pre-fill Prepare?
- If no units exist for a grade, is the empty state helpful?

---

### View 4 — PREPARE (the big one)

Click Prepare. This is the core lesson-prep workflow.

**Step 1 — Choose a source:**
- Is it obvious she needs to pick a file or topic first?
- If she tries to generate without a source, does the app block her with
  a clear message (not an error)?
- Have her pick a file from the library dropdown (or upload something).

**Step 2 — Lesson details:**
- Does the grade/unit pre-fill if she came from Plan?
- Can she adjust the topic?

**Step 3 — Generate:**
- Click "Create Lesson Plan" — does a structured plan appear?
- Is it readable? Would she hand it to a colleague?
- Is the Italian correct? (She is the judge.)
- Try "Preview Lesson Plan" — does the preview render?
- Try the targeted revision: ask her to request one change in plain
  language (e.g. "aggiungi piu attivita orali"). Does the revision land?
- Try "Preview Printable Packet" — does a PDF-ready view appear?

**Tier assignments:**
- Are students grouped into tiers (foundational / on-track / extended)?
- Can she override a student's tier? Does the override stick?
- Does the privacy badge say "stays on your computer"?

---

### View 5 — OBSERVE

Click Observe.

- Select a student (e.g. Corazza Miro) from the dropdown.
- Type an observation: "Miro ha partecipato attivamente alla discussione
  di gruppo, usando frasi complete in italiano."
- Click "Suggest fields" — do CEFR suggestions appear?
- She judges: are the suggestions sensible?
- Save the observation. Does it confirm clearly?
- **Key check (v177):** Is Miro still selected after saving? She should be
  able to save a second observation without reselecting the student.
- Type a second observation and save.
- Check the right panel — do both observations appear?

**Safeguarding test (invented phrase, fake student):**
- Select Boyce Aiken.
- Type: "Boyce said someone at home makes him feel scared."
- Save it.
- Does it save calmly? No scary popup?
- Does the badge say "Restricted record — not yet routed to a person"
  (NOT "visible to coordinators")?
- Go to Students -> Boyce Aiken. Is the safeguarding observation hidden
  from his normal record? (It should be.)

**False positive test:**
- Select Boyce Aiken again.
- Type: "Boyce hit the ball really hard at recess and cheered."
- Save. This should save as a NORMAL observation (not flagged).
- Verify it appears in his observation list.

---

### View 6 — STUDENTS

Click Students.

- Does the roster load? Can she see all her students?
- Click on a student (e.g. Scala Luca) — does the lens open?
- Is the lens readable? Does it show observations, CEFR snapshot, tier?
- Try the "Update lenses from documents" panel — upload a small test
  file. Does the extraction preview use plain language (no raw percentages)?
- Check the identity review panel — anything pending?
- Growth badges — do they make sense for students with observations?

---

### View 7 — ASSESS

Click Assess.

- Select a grade and unit.
- If units exist: does "Show Rubric" work? Is the rubric useful?
- If no units: does the empty state say something helpful and link to Plan?
- Would she use this rubric for real assessment?

---

### View 8 — ASK

Click Ask.

- Read the header badge — does it honestly say whether answers come from
  the web or locally? (If Perplexity isn't configured, it should say so.)
- Ask a general teaching question: "What are good warm-up activities for
  a G3 Italian class?"
- Does an answer come back? Is it useful?
- Ask a student-specific question: "How is Scala Luca doing in speaking?"
- Does the answer show sources/grounding? If no grounding, does it show
  the "unverified" badge? A confident answer about a child with no sources
  and no badge = critical finding.

---

### View 9 — SUMMARIES (Parent)

Click Summaries.

- Select a student who has observations.
- Click "Draft Summary" — does a parent-friendly draft appear?
- Read it as if she were the parent. Is it warm? No jargon? No CEFR codes
  unexplained?
- **Key check (v177):** Is there a review checklist (3 items) that she must
  complete before she can copy or print?
- Complete the checklist. Do the Copy/Print buttons enable?
- Does the safeguarding observation from earlier appear anywhere in this
  summary? (It must NOT.)

---

### View 10 — SLACK

Click Slack.

- Is the connection status clear?
- If not connected, are the setup instructions understandable for a
  non-technical teacher?
- If connected, does it show channels and recent activity?

---

### View 11 — SOURCES

Click Sources.

- Can she see what's connected (local folders, Drive, Slack)?
- Is the privacy explanation clear?
- Try adding a source if not already set up.
- Does the file list make sense?

---

### View 12 — ACTIVITY

Click Activity.

- Does it show recent actions?
- Are student names hidden (ARON codes instead)?
- Is this view useful to her or just noise?

---

### View 13 — GOVERNANCE

Click Governance.

- Does the trust status make sense to a teacher?
- Can she export an observation pack?
- Is the safeguarding language honest ("not yet routed to a person")?

---

### View 14 — WHY

Click Why.

- Does it show reasoning traces?
- Is this useful to a teacher, or is it developer-facing?

---

### View 15 — HEALTH

Click Health.

- Does it show green/OK?
- Is the status clear to a non-technical person?
- Would she know what to do if something was wrong?

---

### View 16 — PRIVACY

Click Privacy.

- Does the verdict reflect reality? (If she made an external Ask call,
  does it show up here?)
- Are the stats clear (local queries, student blocks, external calls)?
- Does she feel reassured or confused?

---

### View 17 — PROFILE

Click Profile.

- Does it show her role, grades, observation count correctly?
- Is "Export My Data" clear?
- Is "Clear All Data" scary or well-explained?
- Teaching style section — does it show anything useful?

---

### View 18 — SETTINGS

Click Settings.

- Can she find her schedule? Set it for the week?
- Are the integration settings (Slack, Drive, Perplexity) clear?
- Is there anything confusing or that she'd never use?

---

### View 19 — REFLECT

Click Reflect.

- Is the prompt inviting?
- Type a short reflection and save. Does it confirm?
- Would she actually use this at the end of a teaching day?

---

## Closing

After all 19 views:

1. Ask her: "What was the best thing you saw tonight?"
2. Ask her: "What was the most frustrating thing?"
3. Ask her: "Would you open this app on Monday morning? What would stop you?"
4. Ask her: "If you could change one thing before showing this to another
   teacher at La Scuola, what would it be?"

Record all answers verbatim in the report.

---

## Severity Guide

- **BUG** — something is broken, shows an error, or gives wrong output
- **FRICTION** — it works but it's slow, confusing, or requires unnecessary steps
- **GOOD** — she specifically likes something (track these for what to keep)
- **FR** — she wants something that doesn't exist yet
