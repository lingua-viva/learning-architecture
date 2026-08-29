# Lingua Viva — Claudia's App

You are helping **Claudia Canu Fautré**, an Italian-immersion K-5 IB PYP teacher, improve
and customize her teaching app. She is not a developer. She is the user AND the designer.
When she tells you something is wrong or asks for a change, she is speaking from daily
classroom experience — trust her judgment about what teachers need.

## What This App Does

Lingua Viva helps Claudia:
- **Create lesson plans** — differentiated by tier, aligned to IB PYP curriculum
- **Import student data** — from class list spreadsheets, keeps everything local
- **Track observations** — notes about students that build up over time
- **Generate parent reports** — from observation history
- **Prepare materials** — upload a PDF, get differentiated learning packets

Everything stays on her computer. Student data never leaves her machine.
Routing uses the current 111-node classification system before model reasoning.

## What Claudia Can Change (and how)

### Easy changes — do these confidently:

**Fix Italian language errors:**
The generated content sometimes has wrong Italian. Claudia will say things like "it says
'istituzioni' but it should say 'istinti'" or "the plural is wrong here." These fixes go in
the generation prompts or the template text:
- Lesson plan template: `templates/lesson_plan.html`
- Generation prompts: look in `src/lingua_viva/lesson_materials.py`
- If it's a recurring mistake, add a correction rule or example to the prompt

**Change the lesson plan format:**
The lesson plan template is HTML. Claudia might want to:
- Add a section ("I need a space for homework notes")
- Remove a section ("I never use the extension tier")
- Change the order of sections
- Make the print layout wider/narrower
- Change fonts or spacing for readability

Template file: `templates/lesson_plan.html`

**Add curriculum knowledge:**
When Claudia says "the app doesn't know about [topic/standard]," add a knowledge entry:

File: `knowledge/education/curriculum_ib.yaml`

Copy this format exactly:
```yaml
- id: LV-KL-NNN
  title: "[What this knowledge is about]"
  content: >
    [The actual content — what the app should know. Write it as a fact,
    not as a prompt. Include enough detail that a lesson plan generator
    can cite it.]
  ontology_nodes:
  - LV-CUR-001
  evidence_tier: 2
  citations:
  - "[Where this comes from — a book, a standard, Claudia's experience]"
  tags:
  - [relevant tags]
  verified: true
```

Claudia knows her curriculum. If she says "IB PYP requires X," that's evidence tier 1
(official standard). If she says "in my experience, students learn better when Y," that's
evidence tier 2 (professional expertise).

**Change UI text and labels:**
The web interface is in `static/index.html`. Button labels, headings, instructions,
placeholder text — Claudia can change these to match how she thinks about her work.

**Change activity types in lesson plans:**
If Claudia wants new activity types (songs, games, TPR activities, read-alouds), these
are in the generation prompts in `src/lingua_viva/lesson_materials.py`. Add them to the
prompt's list of available activity types.

### Changes that need care:

**Student detection rules:**
If a new spreadsheet format isn't being parsed correctly, the detection logic is in
`src/lingua_viva/docpipe/extract.py`. This is complex code — make small, targeted changes
and run the tests after:
```bash
python3 -m pytest tests/test_docpipe_extract.py tests/test_students_ingest.py -q
```

**Adding new pages or features to the web UI:**
The web server is `src/web.py` (large file). New routes and API endpoints go here.
Always run:
```bash
python3 -m pytest tests/ -q
```

**Anything touching student data:**
Student data is sacred. The student store is at `src/student_store.py` (in the Mission
Canvas repo). Changes here must preserve:
- Local-only storage (no network calls)
- No student names in any log, report, or error message that could be seen by others
- Observation data only created by teacher, never fabricated

### Changes to avoid:

- Don't modify the pipeline architecture (`src/lingua_viva/pipeline.py` or similar)
- Don't change how models are called (the model routing is handled by Mission Canvas)
- Don't touch the governance or classification system
- If something feels architectural, tell Mical instead — he handles the engine

## How to Test Your Changes

After any change, run:

```bash
# Quick check — tests related to what you changed
python3 -m pytest tests/test_lesson_materials.py -q      # lesson plan changes
python3 -m pytest tests/test_docpipe_extract.py -q       # student detection changes
python3 -m pytest tests/test_students_ingest.py -q       # student import changes

# Full check — everything
python3 -m pytest tests/ -q
```

To see your changes live:
```bash
# Start the app
python3 -m src.web

# Open in browser
# http://localhost:8787
```

## How to Save Your Changes

After you've tested and you're happy:

```bash
# See what changed
git status
git diff

# Save it
git add -A
git commit -m "fix: [what you changed, in plain language]"

# Send to Mical for review (he'll merge it)
git push origin claudia
```

Work on the `claudia` branch. Mical reviews and merges to `main`. This keeps
the production app safe while giving you full freedom to experiment.

To create your branch the first time:
```bash
git checkout -b claudia
git push -u origin claudia
```

## Important Files — Quick Reference

| What | Where |
|---|---|
| **Lesson plan template** | `templates/lesson_plan.html` |
| **Lesson plan generation** | `src/lingua_viva/lesson_materials.py` |
| **Web UI** | `static/index.html` |
| **Web server + API** | `src/web.py` |
| **Curriculum knowledge** | `knowledge/education/curriculum_ib.yaml` |
| **Differentiation knowledge** | `knowledge/education/differentiation.yaml` |
| **Your lens (who you are)** | `lenses/LENS-PERSON-002_claudia_canu.yaml` |
| **Your teaching voice guide** | `lenses/VOICE-EDU-001_malaguzzi_inspired.md` |
| **Student detection** | `src/lingua_viva/docpipe/extract.py` |
| **Student store** | Mission Canvas repo — don't modify directly |
| **Tests** | `tests/` |

## Privacy Rules (non-negotiable)

- **Never** commit student names, student data, or parent information to the repo
- **Never** include the school name — use "an IB international school" if needed
- **Never** add student spreadsheets to the repo (they stay in your local data folder)
- The app keeps student data in local files on YOUR computer only
- If you need to describe a student scenario in a test, use fictional names

## Your Voice

You are Claudia — a trilingual educator (Italian/French/English) with deep IB PYP
expertise, a Malaguzzi-inspired pedagogy, and three children including one with
phonological dyslexia. You know what works in a real classroom. You know what
differentiation actually looks like at 8am on a Monday. The app should reflect YOUR
professional judgment, not generic AI-generated lesson structures.

When you change something, you're making the app more like how YOU teach. That's
the whole point.

## Getting Help

If something breaks and you're not sure how to fix it:
1. Run `git diff` to see what changed
2. Run `python3 -m pytest tests/ -q` to see what failed
3. If you're stuck, undo your changes: `git checkout -- .`
4. Tell Mical what you were trying to do — he'll figure out the code part

If Claude Code suggests something that doesn't feel right for your classroom,
say no. You are the authority on teaching. The AI is the authority on code.
Both are needed. Neither overrides the other.
