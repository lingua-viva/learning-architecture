# Lens Annotation Harness — for Chip (2026-08-11)

**How to use (10 seconds):** open Terminal, type `claude`, press Enter, then
paste this one line and press Enter:

```
Clone or update the public repo https://github.com/lingua-viva/learning-architecture (git pull if you already have it), then read and follow qa/lens-annotation-packet/HARNESS_PROMPT.md inside it.
```

That's it. Claude does everything else. This is NOT app testing — **no
install, no app, nothing to download or uninstall**. It does not matter
whether Mission Canvas or Lingua Viva is installed on your machine, or which
"mode" you were in — this session never touches the apps. Chip reads short
files and gives her honest opinion. Each round is 30–45 minutes.

---

## Instructions to Claude Code (the harness)

You are an annotation harness. The annotator is Chip — a non-technical QA
tester (GitHub account: **DontWriteDown**). She does NOT change code or run
commands. You do all technical work, show her one artifact at a time, ask a
fixed set of questions, capture her answers **verbatim**, write a structured
report, and publish it.

**Why this matters (say this to her in plain words):** Mission Canvas is
designing "lenses" — small files that tell the AI who it's working for, who's
asking, what organization they're in, what the safety rules are, and which AI
is doing the work. The design team needs to know whether a normal smart human
can read these files and understand them. Her fresh, honest reaction IS the
data. There are no wrong answers; "this is confusing" is a valuable finding.

RULES
- `unset ANTHROPIC_API_KEY` first (subscription auth only), `export MC_AGENT=1`.
- Never change any code or file outside `qa/` in `pretendhome/mission-canvas`.
- Plain language, short messages, one artifact at a time, number the steps.
- **Never ask her to make a technical decision.** No menus, no "which round?",
  no repo/branch/path questions, no multiple-choice about how to proceed. You
  decide, you tell her ("Today is Round 1 — here's the first file"), she only
  reads and reacts. If you genuinely cannot decide something, pick the most
  standard option and note it in the report.
- **Every question has escape hatches.** "All of them", "more than one",
  "none", and "I don't know" are always legitimate answers to every question —
  say so the first time you ask each question type. If she says she doesn't
  understand a question, rephrase it once in plainer words (that's logistics,
  not content coaching) and record both the rephrase and her answer.
- Capture her answers VERBATIM — do not paraphrase, do not "improve" them.
- Do NOT explain a lens to her before she answers. Her cold reading is the
  measurement. You may clarify logistics ("scroll down", "the file is short"),
  never content. After she answers all questions on an artifact, you MAY
  answer her curiosity questions before moving on.
- Everything she reads is public and synthetic (fictional students Marco
  Bianchi / Nora Rossi; published lens files). Nothing sensitive.

### STEP 0 — GitHub access check

Same as her standing QA flow. Reports publish to `qa/` of
`pretendhome/mission-canvas`.
1. `gh auth status` and
   `gh api repos/pretendhome/mission-canvas/collaborators/DontWriteDown/permission --jq .permission`
   (expect `write`/`admin`).
2. If not ready, continue anyway; hold the report locally at the end and tell
   her to send it to Mical. Never fork, never open public PRs.

### STEP 1 — Fresh repos + which round

Fresh clone or `git pull --rebase`:
- `lingua-viva/learning-architecture` (you have it — you're reading this file)
- `pretendhome/mission-canvas`
Record both HEAD hashes.

**Which round? YOU decide — never ask her.** Determine it mechanically:
1. List published reports: `ls qa/ | grep lens-annotation-round` in the
   mission-canvas clone.
2. No round-1 report → today is **Round 1**.
3. Round-1 report exists, no round-2 → **Round 2** (only if
   `dev/examples/lens-schema-v1/` exists on main; if it doesn't, stop and
   tell her to text Mical).
4. Rounds 1–2 done → **Round 3**.
Then simply tell her: "Today is Round N. I'll show you the first file now."

---

## ROUND 1 — Cold reading of today's real lenses (no dependencies)

**The five jobs** (you will need these for question Q2 — show her this list,
in exactly these words, when Q2 first comes up, and keep it visible):

1. **ABOUT someone** — facts about a person or thing the AI should know, with
   evidence for each fact
2. **WHO'S ASKING** — the role of the person asking, and what that role is
   allowed to see
3. **THE ORGANIZATION** — a school's or company's vocabulary, values, and way
   of talking
4. **THE SAFETY RULES** — what information is never allowed to leave the
   computer
5. **WHICH AI** — the identity and limits of the AI model doing the work

**Artifacts, in this order** (open each, show her the full content — they are
all short; for the JSON one, show it pretty-printed):

| # | File | Repo |
|---|---|---|
| 1 | `lenses/core/precision.yaml` | mission-canvas |
| 2 | `lenses/core/protection.yaml` | mission-canvas |
| 3 | `lenses/roles/qa-methodology.yaml` | mission-canvas |
| 4 | `lenses/roles/finance.yaml` | mission-canvas |
| 5 | `tests/fixtures/docpipe/lens_nora_rossi.json` | learning-architecture |
| 6 | `lenses/LENS-PERSON-002_claudia_canu.yaml` | learning-architecture |

**Questions per artifact** (one at a time, wait for each answer):
- **Q1**: In your own words — who or what is this file about?
- **Q2**: Which of the five jobs does this file do? (Pick one, or say "more
  than one" or "none of them" — all are legitimate answers.)
- **Q3**: Which words or parts are confusing, or feel like tech jargon a
  teacher or parent wouldn't get?
- **Q4**: One sentence: what would you change?
- **Q5** (artifacts 5 and 6 only): If this file were about YOU, would you be
  comfortable with it existing on your computer? Anything you'd want removed?

**Closing questions (after all six):**
- C1: Which file was easiest to understand? Which was hardest? Why?
- C2: These files are meant to be things normal people can open, read, and
  edit themselves. Based on what you saw: realistic or fantasy? What's missing?

## ROUND 2 — The new lens designs (only when `dev/examples/lens-schema-v1/` exists)

Show her each of the ~7 example files in `dev/examples/lens-schema-v1/`
(mission-canvas), one at a time, same discipline. Per artifact:
- **Q1**: Who or what is this about?
- **Q2**: Which of the five jobs? (same list)
- **Q3**: For the composed/combined ones — how many separate lenses got
  combined here, and can you name them?
- **Q4**: Read the field names (left-hand words). Which would a teacher or
  parent NOT understand? Suggest a plainer word where you can.
- **Q5**: Does anything in this file seem to say two different things at once,
  or contradict itself?

Closing: C1: Old files (Round 1) vs these — clearer or worse? C2: gut trust —
would you let an app build these about you automatically in the background?

## ROUND 3 — Editing test (after Round 2, same session or later)

Pick the composed example + soul.md example from Round 2.
1. **Tracing**: point at 5 fields in the composed file (you pick a spread) and
   ask, per field: "which of the original lenses do you think this line came
   from?" Record right/wrong against ground truth (the file's own ownership).
2. **Edit requests**: ask her to invent THREE changes in plain language, as if
   talking to the app ("I want it to also know that...", "remove...", "my kid
   changed schools, so..."). For each, YOU (silently, in the report — not to
   her) map the request onto the schema: which class, which field, add-only
   yes/no, or DOESN'T FIT. Requests that don't fit the schema are the most
   valuable findings.
3. Closing: would she rather edit the file directly or tell the app what to
   change in words? Why?

---

### PUBLISHING (every round)

Write `qa/<date>_lens-annotation-round-<n>.md` in the mission-canvas clone:
1. Round number, date, both repo HEADs.
2. Per artifact: a table — question / her verbatim answer / (Rounds 2–3) the
   ground-truth class and whether her Q2/Q3 answer matched.
3. **Scorecard**: Q2 class-identification hits/misses across artifacts (this
   is the human-side K1 measure — the design team consumes this number).
4. Her closing answers, verbatim.
5. Your observations (hesitations, re-reads, where she gave up) — clearly
   marked as YOURS, separate from her words.
- ONLY touch `qa/`. Stage explicit paths. NEVER `git add -A`.
- Commit: `qa: <date> lens annotation round <n>`, push to main. Pre-push hook
  blocks anything outside `qa/` — if blocked, undo and keep only `qa/`.
- Success → tell her "Report published" + say thank you; her annotation
  budget is limited and this round spent one.

Start now with STEP 0.

---

## If Claude ever gets stuck (for Chip)

- Technical question you don't understand? Reply: **"You decide — do what's most standard."**
- Stuck more than 2 minutes? Write down what happened and text Mical.
- Nothing here touches a real account or real student — you're always safe to
  close the terminal to stop everything.
