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

- T0.1 Did the download + install work with zero help?  → _____
- T0.2 Anything scary or confusing in the install (warnings, prompts)?  → _____

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

- T1.1 Were **all 6 students** detected? (count them)  → _____
- T1.2 Did Lucà and Noëmi appear with their accents intact?  → _____
- T1.3 Did "Bianchi Sofia" come in as one student (not "Bianchi" + "Sofia", not lost)?  → _____
- T1.4 UX: after upload, was it obvious what would happen next and what "Update all lenses" would do — before you pressed it?  → _____

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

- T5.1 Say: *"Abigail worked hard on her essay today."* — Does it attach to **Chang Abigail** (surname-first roster)?  → _____
- T5.2 Say: *"Chang was very helpful today."* — Two Changs exist. The app must **ask which one** — never silently pick. Did it?  → _____
- T5.3 Say an observation using *"Noemi"* (no accent). Does it reach **Noëmi**?  → _____
- T5.4 Tap the mic twice to add two sentences — did the second **add** to the first rather than erase it?  → _____
- T5.5 Say something with no level or skill in it. Does the app leave those fields empty — or does it **invent** a CEFR level? (Inventing = serious bug.)  → _____
- T5.6 UX: whole flow one-handed while "supervising a class" — realistic? What breaks first?  → _____

## Part 6 — Parent summary (end of the pipeline)

Go to **Student Summary** tab, pick Lucà, press **"Draft Summary"**.

- T6.1 Is every claim in the draft traceable to something you observed or confirmed?  → _____
- T6.2 Did safety warnings appear when they should (e.g. another child's name in the text)?  → _____
- T6.3 The 3-checkbox review list before Copy/Print — helpful ritual or annoying friction?  → _____
- T6.4 **Voice test:** does the draft sound like *you* — or like an AI pretending to be a teacher? Quote one sentence you'd rewrite.  → _____

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
