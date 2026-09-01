# Claudia QA Harness — v0.2.78 (Document Pipeline, Full Range)

**For:** Claudia · **Time needed:** ~45–60 minutes · **Date:** ____________

You are testing the newest release exactly the way any teacher would — download,
install, use. No special setup, no developer tools. If at any point you have to
guess what to do next, **that guess is a finding** — write it down.

## How to record answers

Fill in the `→` lines directly in this file (or on paper / in an email — whatever
is fastest for you). For every test, three things matter:

1. **Did it work?** (yes / no / partly)
2. **Did you trust it?** (did the app claim anything about a child you didn't tell it?)
3. **Monday-8am test:** would this step survive a real classroom morning?

**Privacy rule for reporting:** when you write results, never use a real student's
name — say "student A" or use the fictional roster below. Your real data stays on
your machine; only your notes travel.

---

## Part 0 — Fresh install (this is itself a test)

1. Go to **https://linguaviva.art** and download the app for your computer
   (Mac: `LinguaViva.dmg`).
2. Install and open it. Check the version shows **0.2.78**.

- T0.1 Did the download + install work with zero help?  → Yes, install worked fine.
- T0.2 Anything scary or confusing in the install (warnings, prompts)?  → No warnings, version shows 0.2.78.

---

## Part 1 — The fictional test class (copy-paste, 2 minutes)

So you can be rough with the app without touching real children, create a file
called `classe-test.csv` with exactly this content:

```csv
Nome,Classe,Note
Lucà Rossi,3B,
Noëmi Villa,3B,
Chang Abigail,3B,
Chang Marco,3B,
Bianchi Sofia,3B,
Giuseppe Esposito,3B,
```

Note what's hiding in there: **accented names** (Lucà, Noëmi), **two siblings
with the same surname** (Chang), and **mixed name order** (Bianchi Sofia is
surname-first). These are exactly the cases that used to silently lose students.

3. Go to **Students** tab → **"Update lenses from documents"** → **"Upload and extract"** → choose `classe-test.csv`.

**PRE-TEST FINDING — BUG-P1**: Claudia uploaded Abigail Chang's PYP Progress Report PDF (real file, already on device) via "Update lenses from documents". The app showed "Extracting..." for several minutes, then displayed **"Failed to fetch"**. No useful error message — just "Failed to fetch." Attempted a second time after creating the fictional roster — same result, "taking too long." The extraction consistently fails on real PDF report cards. This is a **blocking bug** for the document-to-lens workflow. Likely cause: the LLM sentence classification calls are sequential (one per sentence) and a multi-page PDF has dozens of sentences — each LLM call takes 5-10 seconds, so the total exceeds the HTTP timeout.

- T1.1 Were **all 6 students** detected? (count them)  → **NO — only 5 detected.** "Lucà Rossi" is missing from the list. The app found: Noëmi Villa, Chang Abigail, Chang Marco, Bianchi Sofia, Giuseppe Esposito. **BUG-T1.1**: Lucà Rossi was dropped entirely — the accented "Lucà" may have caused the detection to fail.
- T1.2 Did Lucà and Noëmi appear with their accents intact?  → Noëmi: YES, accent preserved (ë visible). Lucà: NOT DETECTED AT ALL — cannot verify accent.
- T1.3 Did "Bianchi Sofia" come in as one student (not "Bianchi" + "Sofia", not lost)?  → YES — appears correctly as one student "Bianchi Sofia".
- T1.4 UX: after upload, was it obvious what would happen next and what "Update all lenses" would do — before you pressed it?  → YES — clear message: "5 student names found... Nothing has been created yet — review the list, then choose." Button says "Create these 5 students" with Cancel option. "Nothing has been saved yet — click a name to leave it out; cancelling leaves no trace." is reassuring.

**FRICTION-T1.1**: Every name shows "check this name — it was hard to read" badge. This is misleading — the names were perfectly readable in the CSV. The badge suggests a problem where there is none. A teacher might worry she needs to fix something.

**Part 2 DEFERRED** — Document extraction times out in v0.2.78 (BUG-P1). Fix committed (`0a6c2ad` — batch LLM classification, 15s instead of 3-5min). Needs v0.2.79 release to test.

## Part 2 — Document formats, full range

Feed it one of each (real anonymized docs or quick fakes — content can be short):

| Test | File | What to check |
|---|---|---|
| T2.1 | **PDF** report card mentioning "Lucà" by first name only | he gets the extraction, not a stranger |
| T2.2 | **DOCX** notes mentioning "Rossi Luca" (reversed, no accent) | still matches Lucà Rossi |
| T2.3 | **XLSX** spreadsheet | parses at all |
| T2.4 | **TXT or MD** note mentioning two students in one file | each gets only THEIR part (no cross-contamination) |
| T2.5 | A PDF that is just a photo/scan (no real text) | app says it can't read it — honestly — instead of inventing content |
| T2.6 | An empty or totally unrelated file (a recipe, a flyer) | app says "nothing found" rather than forcing matches |

For each: after "Upload and extract", read the **preview** before confirming.

- T2.a For every extracted field — could you tell **where it came from**? Did the confidence badges ("verified" vs yellow "needs_confirmation") match your intuition?  → _____
- T2.b Did the app ever attribute a sentence about one child to a different child?  → _____
- T2.c **The trust question:** did anything appear in a preview that was NOT actually in the document?  → _____
- T2.d UX: is "Update all lenses" the right size of commitment — or did you want to accept/reject per student or per field?  → _____

## Part 3 — Identity review (the "is this the same child?" queue)

4. Upload a small note mentioning **"Luca Rosi"** (missing accent AND one 's').
5. Look at **Students** tab → **"Identity review"** section.

- T3.1 Did it appear in the queue asking, rather than silently creating a duplicate student or silently merging?  → _____
- T3.2 Try each button on different items: **"Same child"**, **"New student"**, **"Dismiss"**. Did each do what you expected?  → _____
- T3.3 UX: the question the card asks — is the wording clear enough that a tired colleague would choose correctly?  → _____

## Part 4 — The lens (what the app believes about a child)

6. Click **Lucà Rossi** in the roster. Look at his profile.

- T4.1 Do imported entries show the yellow **"imported — tap to confirm"** badge — and does tapping turn them green ("teacher confirmed")?  → _____
- T4.2 Is it always visible **which claims you confirmed** vs which the app imported?  → _____
- T4.3 Is anything in the Category Profile you never told the app and never imported?  → _____
- T4.4 UX: reading this lens cold — would it help you prep for a parent meeting in 3 minutes, or is the layout in the way? What would you move/remove?  → _____

## Part 5 — Voice observations (the fresh fixes)

Go to **Observe** tab → mic button 🎙️.

**T5.0 (typed observation)**: Typed "Abigail ha lavorato con impegno al suo tema oggi." for Chang Abigail. Saved successfully, no UUID in confirmation, student stayed selected after save. Three v179 fixes confirmed working (UUID hidden, student persists, clean save).

- T5.1 Say: *"Abigail worked hard on her essay today."* — Does it attach to **Chang Abigail** (surname-first roster)?  → _____
- T5.2 Say: *"Chang was very helpful today."* — Two Changs exist. The app must **ask which one** — never silently pick. Did it?  → **NO — BUG-T5.2**: The app silently saved it under Chang Abigail without asking. Chang Abigail was already selected in the dropdown, so the observation went to whoever was selected — it didn't detect "Chang" in the text and flag the ambiguity. With two Changs in the roster, a surname-only observation should prompt the teacher to choose.
- T5.3 Say an observation using *"Noemi"* (no accent). Does it reach **Noëmi**?  → YES — saved correctly under Noëmi Villa. Accent normalization working.
- T5.4 Tap the mic twice to add two sentences — did the second **add** to the first rather than erase it?  → YES — both observations appear in "Recent observations" panel. The "Saved" confirmation section only shows the latest save, which was initially confusing, but the observation list has both.
- T5.5 Say something with no level or skill in it. Does the app leave those fields empty — or does it **invent** a CEFR level? (Inventing = serious bug.)  → CEFR skill: "Not tagged", Observed level: "Not tagged" — correctly left empty, no invention. SEL tone correctly detected as "positive". Support Profile auto-suggested "Emotional Regulation" category with Evidence: "Student expressed contentment." This is a reasonable routing for "era contenta" — not invented, just interpreted. The fields Need/Strength/Strategy are left as placeholder text for teacher to fill.
- T5.6 UX: whole flow one-handed while "supervising a class" — realistic? What breaks first?  → "No I will not use it while supervising a class. I would need to take a couple of minutes after my class to record the most meaningful observation on a couple of students at a time."

## Part 6 — Parent summary (end of the pipeline)

Go to **Student Summary** tab, pick Lucà, press **"Draft Summary"**.

- T6.1 Is every claim in the draft traceable to something you observed or confirmed?  → The draft says "We noticed your child trying new ways to make meaning in class" and recommends "offer a creative quiet workspace" — neither of these came from the observations entered ("ha lavorato con impegno al suo tema" and "Chang was very helpful today"). Claudia: "It is not sharing a concrete example or writing anything specific. It is not a meaningful note yet because there's not enough data collected." **The app generates a parent note even with insufficient data, and the content is generic rather than grounded in actual observations.**
- T6.2 Did safety warnings appear when they should (e.g. another child's name in the text)?  → Not tested (no cross-student content in this draft).
- T6.3 The 3-checkbox review list before Copy/Print — helpful ritual or annoying friction?  → Checklist present and working. "Complete the checklist to copy or print" shown. Copy/Print disabled until checked. (Same result as v179 audit — confirmed still working.)
- T6.4 **Voice test:** does the draft sound like *you* — or like an AI pretending to be a teacher? Quote one sentence you'd rewrite.  → Generic AI voice. "We noticed your child trying new ways to make meaning in class" — Claudia never observed this. "offer a creative quiet workspace" — not grounded in anything. The summary focus field auto-filled "creative quiet workspace" which then drove the recommendation, but this has no connection to the actual observations.

---

### Views 13-19 (quick pass)

**D1 — Governance**: Claudia: "yes, it makes sense, especially if we want to check privacy concerns." Trust Status is clear: 5 questions in plain language — "What student data did Lingua Viva use?" (46 records), "What stayed on this computer?" (1419 questions answered here), "Was any student information sent outside?" (No), "What was removed before anything was written?" (0 redactions), "What needs your review before a parent sees it?" (2 items awaiting confirmation). **GOOD**: honest, transparent, teacher-readable. The questions are framed the way a principal or parent would ask them.

**D2 — Why**: Claudia: "it looks like a developer screen, not useful for me." Shows trace IDs (UUIDs), token counts, model names (ollama/qwen3:8b), timing. **FRICTION**: This is developer debugging — "Trace: 3c86c296-2504-488d..." means nothing to a teacher. Could be hidden behind a "Developer" toggle or removed from the teacher view entirely.

**D3 — Health**: Claudia: "it looks really weird, I'm not sure whose health we are talking about. The app health?" Shows "Doctor — Everything looks healthy" followed by a long list of internal checks: "pass · branch", "pass · required_file:README.md", "pass · required_file:Manuale_Italiano..." — all developer diagnostics. **FRICTION**: A teacher doesn't know what "required_file:artifacts/inventory.yaml" means. The "Everything looks healthy" line is the only useful part. The rest should be hidden or simplified to a single green checkmark with "Your app is working correctly."

**D4 — Privacy**: Claudia: "privacy looks fine, it shows everything stays local, but again I'm not sure if an educator needs to check that. It seems more useful for the developer." **FRICTION**: The information is accurate and reassuring, but a teacher wouldn't think to come here. The privacy assurance would be more useful embedded in the views where data moves (Observe, Summaries, Students) — which is already partially done with the "Saved locally" badges.

**D5 — Profile**: Shows "Your Teaching Profile" with Role: teacher, Grades: not set, Observations: 13, Students: 46, File map: 1 roots/4284 directories, Reasoning traces: 1545. "Export My Data" and "Clear All Data" buttons. "My Teaching Style" section with "Confidence: no data yet" and an "Ingest Artifact" option. Profile is clear and accurate. **FRICTION**: "Grades: not set" — should auto-detect from roster (she teaches G3). "File map: 1 roots, 4284 directories" and "Reasoning traces: 1545" are developer metrics, not teacher-useful. "Clear All Data" in red is well-placed but could use a confirmation explaining what exactly gets cleared.

**D6 — Settings**: Claudia: "Settings looks fine, nothing special to report. Again there are a lot of information in this page that are not all useful from a teacher perspective. Local model and local app, I don't need to know. And maybe if the schedule is something that I would use everyday it should be on top of the options and not at the bottom." **FRICTION**: Schedule ("My week") is buried below technical settings (local model, local app). A teacher's weekly schedule is the most actionable thing on this page — it should be first. Developer settings (model selection, app config) should be collapsed or at the bottom.

**D7 — Reflect**: Claudia: "yes, I like it." **GOOD**: The reflection prompt is inviting and would be used at the end of a teaching day.

---

## The Five Pointed Questions

**1. Where did you hesitate longest?**
"All pages and views that are more for developers." — The Why, Health, Privacy, and parts of Settings/Profile felt like developer tools, not teacher tools. The hesitation was "is this for me or not?"

**2. What did the app get wrong about a child?**
"Children's lenses have not enough data to be meaningful yet." — The lenses are empty shells waiting for data. The parent summary invented claims ("trying new ways to make meaning in class") that weren't grounded in observations. The document extraction (the main way to populate lenses at scale) timed out and couldn't run.

**3. What would you show a colleague first — and what would you quietly hope she doesn't click?**
Show first: "The observation page and the way we can communicate meaningful data/observation." Would hope she doesn't click: (implied) the developer-facing views (Why, Health) and the document extraction which doesn't work yet.

**4. After this session, do you trust the lenses more or less than before?**
"The most meaningful thing is having those lenses accurate enough to really customize activities, comments to families, etc." — Trust is conditional: the lenses need to be populated with real data before trust can be evaluated. The observation flow works and builds trust. The document import (which would populate lenses at scale) is blocked by the timeout bug.

**5. If you could delete one step and add one step?**
(Not explicitly answered — implied from context: DELETE the developer-facing views from the teacher interface. ADD a working, fast way to import report cards and populate lenses automatically.)

## Part 7 — Break it on purpose (5 minutes)

- T7.1 Upload the same document **twice**. Duplicated entries, or handled gracefully?  → _____
- T7.2 Close the app mid-extraction, reopen. Anything lost or corrupted?  → _____
- T7.3 Upload a big PDF (20+ pages). Does the app stay honest about progress, or freeze silently?  → _____

---

## The five pointed questions (please answer all five)

1. **Where did you hesitate longest?** The single moment you most had to stop and think — what were you looking at?
2. **What did the app get wrong about a child** — even slightly, even once? (This outranks every other finding.)
3. **What would you show a colleague first** — and what would you quietly hope she doesn't click?
4. **After this session, do you trust the lenses more or less than before?** Why?
5. **If you could delete one step and add one step** in the document→lens→report journey, which and which?

## Sending results back

Whatever is easiest: fill this file in and push it on your `claudia` branch, or
just email/message Mical your notes. Rough notes beat polished silence.
Afterwards you can delete the fictional students from your roster.
