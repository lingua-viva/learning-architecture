# HARNESS — Mical's live test of the 2026-09-04 releases

**Interactive version (records verdicts, exports witness-log rows):** https://claude.ai/code/artifact/4acfefa3-151d-4f15-822c-639b2dedfeef
**Record of verdicts:** `dev/WITNESS_LOG_UX_2026-09.md` (append-only; one section per cycle, same steps as below).
**Download:** https://linguaviva.art/ — the main button or the **Still I Rise schools** section (same build; the section adds the one-click profile instruction). The tag is in the file URL.

Rules: PASS / FAIL / CANNOT-TELL per step, exact wording seen. Only `demo-data/` fixtures, never a real child. Install over your existing install — that is C8 (durability) tested for real. A Mical PASS = "ready for teacher witness"; green needs Claudia or Olga.

## 1. Install and first run — U1 (v0.2.85+)
1. Click the download button on linguaviva.art → the latest pinned tag is served; the file downloads.
2. Open the installer → no unexpected dialog (SmartScreen "More info → Run anyway" is expected and named on the site).
3. First launch, minute one → usable, no traceback, no blank window.
4. Governance → Doctor → green in plain words (if WARN / BLOCKED: copy the check names verbatim).
5. Students → import `demo-data/classe-3B.csv` → approve → 6 lenses; Lucà and Noëmi keep their accents.
6. Quit, relaunch → the 6 students are still there.
7. Network off, relaunch → works, or names exactly what is unavailable.

## 2. Report card → Observe → lens → summary — U3 · U4 · U10 (v0.2.85+)
1. Sources → upload `demo-data/pagella_abigail_chang.txt` → Update lenses → CEFR reading A2 / writing A1 / speaking A1+ / listening A2; the result lists written / needs confirmation / **every refused field by name**.
2. Apply the same report card again → nothing doubles.
3. Observe (typed): `Abigail finished early again and could benefit from extension activities. Listening: A2+.` → saved; "What this note did to the lens: 1 lens field updated" with a *not this — remove* button; the lens gains an Advanced/Enrichment entry marked as a teacher note; listening moves to A2+.
4. Students → Abigail → lens → report entries and the note both visible, each with where it came from.
5. Summaries → Abigail → Draft → the note mentions the listening progress AND a strength from the report card; nothing invented; no red "Not enough evidence" box.

## 3. Roster honesty — U2 (v0.2.86+)
1. Students → import `classe-3B.csv` → 6 names, accents intact, **no** "low confidence" mark, class picker shows `3B`.
2. Approve → "6 students added from classe-3B.csv."; no "Check these names".
3. Roster rows show `3B` after the support tier.
4. Import the same file again → still 6; nothing doubled; a grade you edited by hand is untouched.

## 4. Safeguarding, two roles — U13 (v0.2.86+)
1. Coordinator: Governance → Safeguarding panel "No safeguarding items are waiting." badge 0.
2. Teacher: Observe, pick a student, type `Qualcuno a casa gli fa paura.` save → **Restricted record — not yet routed to a person.** (not "Saved locally").
3. Students → that student → the sentence is nowhere; no observation added.
4. Summaries → Draft for that student → no word of it.
5. Teacher: Observe `Ha paura del buio durante la lettura` → an ordinary note.
6. Coordinator: Governance → "1 safeguarding item is waiting. No notification channel is configured — set one in Settings, or review them here." badge 1; no name, no words of the sentence.
7. Teacher: Governance → no Safeguarding panel.

## 5. Edit a lens by hand — U8 (v0.2.87+; sticky remove v0.2.89+)
1. Observe → `Finished early again and could benefit from extension activities.` save → "What this note did to the lens: 1 lens field updated." + one row `advanced enrichment · evidence` with *not this — remove*.
2. Click *not this — remove* → "removed".
3. Students → lens → the entry is not shown.
4. Students → any student with support entries → *remove* on one → toast "Removed from the lens. The note it came from is kept."; entry gone; observation still in history.
5. Summaries → Draft → the removed text is absent.
6. Sticky: Observe → the same note again → "0 lens fields updated" (or "already present"); no new remove row; lens unchanged.

## 6. Still I Rise profile (v0.2.88+; Settings control v0.2.90+)
1. Fresh launch → teacher nav Home · Daily · Plan · Prepare · Observe · Students · Assess · Ask · Summaries; utility nav has Slack.
2. Settings → School profile → Still I Rise → Apply profile → "Applied. Still I Rise profile: Home, Daily, Plan and Slack are hidden; the app opens on Students." The nav repaints at once.
3. Teacher nav → Prepare · Observe · Students · Assess · Ask · Summaries only; no Slack; on Students.
4. Brand/home click → Students, not Home.
5. Coordinator → Programme as before; Governance still there.
6. Quit, relaunch → still the Still I Rise nav, opening on Students.
7. Settings → La Scuola → Apply → Home returns.

## 7. Approve and print a summary — U10 (v0.2.89+)
1. Summaries → a student with nothing recorded → Draft → red **Not enough evidence to send** + reason; Approve stays disabled after the checklist; status "Not enough evidence to send — nothing here can be approved."
2. Abigail → Draft → no red box; a report-card strength; tick the three boxes → Approve enabled.
3. Add one warm sentence → Approve → toast "summary approved"; status "Approved — N piece(s) of evidence behind this note, signed <you> (Class Teacher)."; Copy final text and Print appear.
4. Print → subject, your text, "A few things you could try at home", "— <you> (Class Teacher)"; no student name, no ids, no AI wording.
5. Put the child's first name in the text → Approve → refused: "The child's name or a private detail is still in the note. Replace it with 'your child' and approve again."
6. Put "refugee student" in the text → Approve → refused with the label named.

_(FAIL → verbatim wording back to PC-23. Every row lands in the witness log.)_
