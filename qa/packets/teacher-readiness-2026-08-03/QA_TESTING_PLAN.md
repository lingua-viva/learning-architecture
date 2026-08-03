# QA Testing Plan — Lingua Viva Teacher Readiness, Claudia (2026-08-03)

**Purpose**: Verify everything Claudia will touch in class, in priority order —
the core observation loop first, integrations later. 39 checks across 7 rounds.
Claudia tests by hand; Claude Code (the harness) walks her through each step,
watches the app, and publishes the combined report to this repo's `qa/` folder.

**Tester**: Claudia (repo owner)
**App**: Lingua Viva desktop app, downloaded fresh from **linguaviva.art**
(expected version: **desktop-v0.2.30 or later**)
**Local URL once running**: http://127.0.0.1:8787
**Test data**: SYNTHETIC ONLY. The two students used everywhere are
**Marco Bianchi** and **Nora Rossi** — fake children invented for this packet.
**Never type or speak a real child's name.** This repo is public.

---

## Note to the harness (Claude Code): read this first

- Lead the tester through the rounds below **in order, one step at a time**.
  She replies "done" (or describes what went wrong) after each step.
- **Round 1 must run before everything else** — later rounds depend on the two
  seeded students.
- Some features are **backend-only right now** (no button in the app yet):
  worksheet generation (Round 4, checks 15–19) and cohort planning (Round 6).
  For those, YOU call the local API yourself (examples below), show her the
  output, and she judges the content by eye. That is the intended test method,
  not a workaround.
- If a step's feature clearly does not exist in the installed build, record
  the outcome as **"NOT IN THIS BUILD (version X)"** — one line, not a bug
  hunt — and move on.
- Voice steps: if the mic mis-transcribes, let her retry twice, then have her
  paste the same sentence into the relevant text input instead and note
  "tested via text fallback".
- Voice note: the app transcribes locally (no ffmpeg install is needed as of
  0.2.30). The first voice action after launch may take noticeably longer
  while the speech model warms up — that's expected once, not a bug.

---

## Round 1 — FIRST: the core loop (checks 1–5, ~10 min)

Create the two test students and save typed observations. If this works,
everything else has a foundation.

| # | What Claudia does | Pass looks like |
|---|---|---|
| 1 | Create **Marco Bianchi**, grade G3, in the Students view | Marco appears in the roster |
| 2 | Create **Nora Rossi**, grade G3 | Nora appears in the roster |
| 3 | Start an observation for Marco, type the text, but leave the observation type on "Choose a type (required)" and try to save | App **refuses** with a clear message — it must not save without a type (new in 0.2.30) |
| 4 | Choose a type, then save: `During group reading, Marco helped a classmate find the right page.` | Saves with a **visible confirmation**; form clears afterwards |
| 5 | Save for Nora (with a type): `Nora used full sentences to describe her weekend.` | Same confirm; both students now show an observation on their records |

**Record if**: save fails silently, no confirmation shown, the form keeps old
text after saving, or check 3 saves anyway.

---

## Round 2 — SECOND: voice observations (checks 6–11, ~15 min)

| # | What Claudia says (tap mic first) | Pass looks like |
|---|---|---|
| 6 | `Marco helped a classmate find the right page during reading` | App recognizes it as an observation for Marco |
| 7 | (same as 6) | Spoken confirmation: "Got it. Observation saved for Marco." — **first name only** |
| 8 | Open Students → Marco | The new observation appears on his record |
| 9 | `Nora used full sentences to describe her weekend` | Same save-and-confirm flow for Nora |
| 10 | `The student struggled with greetings` | App **asks which student** — it must NOT guess |
| 11 | `Marco was kind to the new student today` | Saves as a **plain note**. The record must NOT show a language level (like "A2" or "speaking") — she never said one, and the app must not invent one (new in 0.2.30) |

**Record if**: observation saved to the wrong student, full name spoken aloud,
no confirmation, check 10 saves without asking, or check 11 shows any CEFR
level/dimension she didn't state.

---

## Round 3 — THIRD: voice questions (checks 12–13, ~5 min)

| # | What Claudia says | Pass looks like |
|---|---|---|
| 12 | `What level is Marco at in reading?` | Answer spoken back (and shown), based on his record |
| 13 | `How should I group my students for tomorrow?` | A grouping recommendation spoken/shown |

These go through the local reasoning model — allow up to ~60 seconds.
**Record if**: no answer, answer clearly ignores the students' data, error
text read aloud.

---

## Round 4 — FOURTH: worksheet generation (checks 14–19, ~15 min)

Check 14 by voice; 15–19 the harness triggers via API and shows her the output.

| # | Step | Pass looks like |
|---|---|---|
| 14 | Say: `Create a worksheet for daily routines in Italian` | App answers "Ready to create materials about daily routines..." and asks which students |
| 15 | Harness calls the generation API (below) | Three worksheets come back: foundational / on_track / extended |
| 16 | Read the foundational worksheet | Has word banks and sentence starters |
| 17 | Read the on-track worksheet | Has a model example + independent practice |
| 18 | Read the extended worksheet | Has an open-ended prompt |
| 19 | Scan all three | **No student names anywhere in worksheet content** |

Harness API call (adjust nothing except student IDs if needed):

```bash
curl -s -X POST http://127.0.0.1:8787/api/lesson-materials/generate \
  -H "Content-Type: application/json" \
  -d '{
    "teacher_id": "local-teacher",
    "lesson": {
      "ib_programme": "PYP",
      "subject": "Italian",
      "unit_title": "Daily Life",
      "topic": "daily routines",
      "atl_skills": ["communication"],
      "cefr_target": "A2",
      "duration_minutes": 45,
      "language_of_instruction": "it"
    }
  }'
```

Save the three worksheets as .md files in the session folder so Claudia can
read them comfortably. Check 19 is a **hard privacy gate**: if "Marco",
"Nora", "Bianchi", or "Rossi" appears in any worksheet body, that is a **P0**.

**Claudia extra (not scored)**: would you hand these out as-is? What would you
edit first? The harness records her answer verbatim.

---

## Round 5 — FIFTH: Google Drive (checks 20–32, ~25 min)

### Connect (20–24)

| # | What Claudia does | Pass looks like |
|---|---|---|
| 20 | Click "Connect Google Drive" | Browser opens the Google consent screen |
| 21 | Approve access | App shows "Connected" with her email |
| 22 | Connect a Drive folder (paste a folder URL) | Folder accepted, no error |
| 23 | Look at the folder's file list in the app | Files from that Drive folder are listed |
| 24 | Upload `documents/G3_family_relationships_unit.pdf` to that Drive folder, then Import it from the app | Import succeeds, file appears as imported |

### Document → student lens (25–28) — uses `documents/student_record_marco_bianchi.md`

| # | What Claudia does | Pass looks like |
|---|---|---|
| 25 | Upload the Marco record to the Drive folder, import it with purpose **student_lens_source** | Extraction runs automatically after import |
| 26 | Open the extraction result | Extracted fields visible: name, grade, language level, support needs |
| 27 | Confirm some fields, reject at least one | Lens updates with confirmed fields only |
| 28 | Go to Students → Marco Bianchi | Profile shows the newly confirmed data |

### Auto-sync (29–32)

| # | Step | Pass looks like |
|---|---|---|
| 29 | Set a Drive folder as the "sync folder" in the app | Setting saves |
| 30 | Save a new observation (voice or manual) for Marco, then check the Drive folder in the browser | An updated lens .md file for Marco appears/updates in Drive |
| 31 | After Round 4 generation, check the Drive folder | Worksheet .md files appear in Drive |
| 32 | Turn wifi OFF → save an observation → confirm **no error** → turn wifi back ON | The observation saved locally with no error; the file appears in Drive after reconnect (wait ~2 minutes before failing) |

**Record if**: consent screen never opens, wrong account shown, folder URL
rejected, extraction never runs, reject doesn't stick, sync errors surface to
the teacher, offline save fails.

---

## Round 6 — SIXTH: cohort lesson planning (checks 33–35, ~10 min)

Harness calls the API and shows Claudia the teacher guide:

```bash
curl -s -X POST http://127.0.0.1:8787/api/cohort-plans/preview \
  -H "Content-Type: application/json" \
  -d '{
    "teacher_id": "local-teacher",
    "lesson": {
      "ib_programme": "PYP",
      "subject": "Italian",
      "unit_title": "Daily Life",
      "topic": "describing daily routines",
      "atl_skills": ["communication"],
      "cefr_target": "A2",
      "duration_minutes": 45,
      "language_of_instruction": "it"
    },
    "teacher_notes": ["Use table groups."]
  }'
```

| # | Claudia checks | Pass looks like |
|---|---|---|
| 33 | The returned teacher guide | A readable lesson plan with tier groupings |
| 34 | Groupings section | Shows which students are foundational / on-track / extended |
| 35 | Distribution section | Instructions for handing out materials per tier |

**Claudia extra (not scored)**: does the grouping logic match how she would
actually group these two (fake) students? Record her answer verbatim.

---

## Round 7 — SEVENTH: general app health (checks 36–39, ~10 min)

| # | Step | Pass looks like |
|---|---|---|
| 36 | Click through every sidebar tab, top to bottom | No crash, no blank screen, back/away always possible |
| 37 | Open the Doctor / health page | Passes — specifically NO "PRIVATE_RISK" false positive |
| 38 | Open Settings | Expected controls present (Drive, voice, sync, privacy) |
| 39 | Archive one test student (new in 0.2.30) | Student disappears from the roster; the app says observations are retained (soft archive, not deletion) |

**Record if**: any tab crashes, Doctor flags a false privacy risk, archive
button missing, or archiving errors / the student stays in the roster.

---

## UX Feedback Template (Claudia fills in at the end)

1. What worked?
2. What didn't work, or looked wrong?
3. What was confusing?
4. Do the observation fields and language levels match how you actually think
   about your students? What's missing or mis-framed?
5. Would the generated materials be usable in your classroom as-is? What
   would you change before handing them out?
6. What would make you quit using this on a busy teaching day?
7. Feature requests (things that aren't bugs — keep the list going)

---

## Severity guide

- **P0** — teacher cannot use the app, data loss, or a privacy leak (student
  name in generated materials, spoken full names, invented language levels,
  real-looking data anywhere it shouldn't be)
- **P1** — a listed check fails but there's a workaround
- **P2** — cosmetic, confusing wording, papercuts
- **FR** — feature request (not a bug; goes in the feature list, and Claudia
  can ask the harness to draft a spec for it)
