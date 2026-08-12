# Chip Teacher Verification Session — 2026-08-12

**How to use:** open Terminal, type `claude`, press Enter, then paste this:

```
Read and follow ~/learning-architecture/qa/chip-teacher-verification/HARNESS_PROMPT.md
```

---

## Instructions to Claude Code (the harness)

You are running a **live app verification session** with Chip — a non-technical
QA tester who acts as a real IB teacher using the Lingua Viva desktop app on her
Mac. This is NOT a file-reading annotation — she is actually using the app.

**Goal:** Verify every teacher-facing capability end-to-end, produce real
teaching materials, and capture every friction point or failure. The app is
`desktop-v0.2.55` (Still I Rise branding, orange theme). She should already
have it installed from linguaviva.art.

RULES:
- `unset ANTHROPIC_API_KEY` first, `export MC_AGENT=1`.
- **YOU monitor the backend; she uses the app.** You watch traces, she clicks buttons.
- Plain language, one task at a time, number the steps.
- Never ask her to make a technical decision.
- Capture her reactions VERBATIM in the report.
- After EACH task, ask: "What happened?" and "Anything surprising or confusing?"
- If something fails, record it exactly — the failure IS the finding.

---

## STEP 0 — Pre-flight

1. Confirm the app is running: `curl -s http://127.0.0.1:8787/api/health 2>/dev/null || echo "NOT RUNNING"`
2. Record the version: `curl -s http://127.0.0.1:8787/api/version 2>/dev/null`
3. Check Drive connected: `curl -s http://127.0.0.1:8787/api/google-drive/status 2>/dev/null`
4. Start a fresh trace log watcher:
   ```bash
   LV_HOME="${LV_STATE_HOME:-$HOME/.lingua-viva}"
   TRACE_LOG="$LV_HOME/runtime/traces.ndjson"
   echo "Watching: $TRACE_LOG"
   tail -f "$TRACE_LOG" 2>/dev/null | python3 -c "
   import sys, json
   for line in sys.stdin:
       try:
           t = json.loads(line.strip())
           ts = t.get('timestamp','')[-8:]
           print(f'{ts} | {t.get(\"event_type\",\"?\"):20s} | {t.get(\"student_id\",\"-\"):20s} | {t.get(\"status\",\"\")}')
       except: pass
   " &
   WATCHER_PID=$!
   ```
5. Tell Chip: "We're going to walk through everything a teacher does in the app,
   start to finish. I'll give you one thing to try at a time. Just tell me what
   happens — there are no wrong answers. If something breaks, that's useful data."

---

## ROUND 1 — File Import (local files)

**Tell Chip:** "Go to the Students view. We're going to import some students."

### Task 1.1 — Import a text file
1. Ask her to create a quick text file on her Desktop with 3-4 student names
   (first and last), one per line, with a heading. Example she can type into
   Notes.app or TextEdit and save as `.txt`:
   ```
   MYP3 English Roster
   Student: Amina Hassan
   Student: David Ouma
   Student: Grace Wanjiku
   Student: James Mwangi
   ```
2. "Click Import on the Students page and pick that file."
3. Record: did students appear? How many? Any error?
4. Backend check: `curl -s http://127.0.0.1:8787/api/students | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'{len(d)} students')" 2>/dev/null`

### Task 1.2 — Import a Word doc or PDF
1. Ask Chip: "Do you have a Word document or PDF with student names on your
   machine? A class roster, a lesson plan, anything with names in it."
2. If yes: "Import that one too."
3. If no: create a quick `.docx` for her:
   ```python
   import docx; d=docx.Document(); d.add_heading("Grade 5 Science",1)
   d.add_paragraph("Student: Fatima Ali"); d.add_paragraph("Student: Peter Njoroge")
   d.save("/tmp/test-roster.docx"); print("Saved to /tmp/test-roster.docx")
   ```
   Tell her the path.
4. Record: success/failure, student count, any error messages.

### Task 1.3 — Undo an import
1. "Now try the Undo button on that import."
2. Record: did it work? Are the students gone from the roster?

---

## ROUND 2 — Google Drive Import

**Skip this round if Drive is not connected (Step 0.3 returned disconnected).**

### Task 2.1 — Connect Drive
1. "Go to Settings, then the Sources/Drive section."
2. "Connect your Google Drive."
3. Record: did the OAuth flow work? Any errors?

### Task 2.2 — Import from Drive
1. "Go to Students, and look for the Drive import option."
2. "Pick a folder from Drive that has class-related documents."
3. Record: what happened? Files pulled? Students detected?

---

## ROUND 3 — Observe (recording observations)

### Task 3.1 — Type an observation
1. "Go to Observe. Pick one of the students you imported."
2. "Type a short observation about them — something like 'Amina used strong
   topic sentences today and helped David reorganize his paragraph.'"
3. "Hit Save."
4. Record: did it save? What confirmation did she see?
5. Backend: check the trace log for the observation event.

### Task 3.2 — Voice observation (if mic works)
1. "Now try the microphone button instead of typing."
2. "Say an observation out loud about a different student."
3. Record: did voice capture work? Did it transcribe correctly?

### Task 3.3 — Check the student lens
1. "Go back to Students and click on the student you just observed."
2. "What do you see in their profile?"
3. Record: is the observation visible? Any CEFR/RTI updates? Anything odd?

### Task 3.4 — Ethos trait observation
1. "Make another observation, but this time look for the ethos/trait selector."
2. "Pick a trait (or let the app suggest one) and save."
3. Record: did the trait appear? Was it intuitive?

---

## ROUND 4 — Prepare (differentiated materials)

### Task 4.1 — Generate a lesson pack
1. "Go to the Prepare view."
2. "Pick a unit or type in a topic — something like 'Persuasive Writing' for
   English, MYP3."
3. "Generate materials."
4. Record: did 3 tiers appear (foundational, on-track, extended)? Content quality?

### Task 4.2 — Review the tiers
1. "Look at each tier. Does the foundational tier look simpler than extended?"
2. "Is there anything you'd change as a teacher?"
3. Record her reactions verbatim.

### Task 4.3 — Generate PDFs (the big E2E test)
1. Run the PDF generation from the backend while she watches:
   ```bash
   curl -s -X POST http://127.0.0.1:8787/api/prepare/differentiated-pdf \
     -H "Content-Type: application/json" \
     -d '{"subject":"English","unit_title":"The Power of Persuasion","topic":"Writing persuasive arguments","ib_programme":"MYP","cefr_target":"B1","duration_minutes":50}' | python3 -m json.tool
   ```
2. Open the PDFs for her: `xdg-open` or `open` the paths from the response.
3. "Would you hand this to a student? What would you change?"
4. Record her reaction to each tier's PDF.

### Task 4.4 — Push PDFs to Drive (if connected)
1. If Drive is connected, re-run with a `drive_folder_id`:
   ```bash
   # Get a folder ID first
   curl -s http://127.0.0.1:8787/api/google-drive/folders | python3 -m json.tool
   ```
2. Record: did the PDFs appear in Drive?

---

## ROUND 5 — Parent Reports

### Task 5.1 — Generate a parent report
1. "Go to a student who has at least 2 observations. Look for the parent
   report or summary option."
2. "Generate a report."
3. Record: is it readable? Warm tone? Any internal jargon leaking?

---

## ROUND 6 — Edge Cases

### Task 6.1 — Empty state
1. "Archive all students. What does the empty state look like?"
2. Record: is it clear what to do next?

### Task 6.2 — Bad file
1. "Try importing a random non-document file — a photo, a zip, anything weird."
2. Record: what error message does she see?

---

## STEP FINAL — Report

Write the report to `qa/chip-teacher-verification/REPORT_2026-08-12.md` with:

```markdown
# Chip Teacher Verification — 2026-08-12

## Version
- App: desktop-v0.2.55
- Machine: [her machine tag]
- Drive connected: [yes/no]

## Summary
[1-3 sentences: does it work as a teacher tool?]

P0: ___ · P1: ___ · P2: ___ · Passed: ___

## Results by round
[For each task: PASS/FAIL/PARTIAL, what happened, her verbatim reaction]

## Chip's top 3
[Ask her: "What are the three things you'd fix first?"]

## Backend trace summary
[How many traces fired, any errors in the log, timing]
```

Commit to `pretendhome/mission-canvas` repo under `qa/` if she has write access,
otherwise save locally and tell her to send it.
