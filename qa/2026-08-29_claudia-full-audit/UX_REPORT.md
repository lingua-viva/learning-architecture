# UX Walkthrough Report — 2026-08-29

**Tester:** Claudia Canu Fautre
**App version:** desktop-v0.2.72
**URL:** http://127.0.0.1:8787
**Started:** 2026-08-29

## Running Totals

| Type | Count |
|------|-------|
| BUG | 6 |
| FRICTION | 20 |
| GOOD | 31 |
| FR | 0 |

---

## Findings

### View 1 — HOME

**GOOD-1** — Greeting is correct for time of day, next-action strip is useful, counts are accurate, clear what to do first, "Go to Observe" navigation works and returns cleanly. No issues found.

### View 2 — DAILY

**FRICTION-1** — Knowledge library empty state says "add IB guides and support materials with `lv library add`". That is a terminal command. Claudia: "I would not know what to do with it." Needs a button or plain-language instruction instead.

**FRICTION-2** — "Suggestions awaiting your confirmation" shows 2 ARON codes but clicking them does nothing. Claudia: "not clear, I'm clicking on it and they don't open up." No way to act on confirmations from this view.

**FRICTION-3** — Overall Daily view usefulness uncertain. Claudia: "I'm not sure" whether this would help at 8am on a Monday. View may feel more like a status dashboard than an actionable morning tool.

**GOOD-2** — ARON codes for "Not observed in 7 days" are fine — Claudia teaches only G3 so she knows who they are. Privacy-safe display works for her.

### View 3 — PLAN

**GOOD-3** — Grade bands are visible and recognizable (G1-G5 with CEFR descriptors). G3 selected correctly. Empty state is clear: "No units yet for this grade" with an orange "Add your first unit" button. Claudia found her grade immediately.

**GOOD-4** — Badges show "authoritative" / "non_authoritative" and "Authoritative source: Manuale v1" — useful metadata for a teacher who cares about curriculum provenance.

**FRICTION-4** — No units loaded for any grade. Claudia asked "shall I start uploading my units?" — she's willing, but it means the Plan → Prepare flow can't be tested yet. The empty state is clear but the app has no pre-loaded curriculum content to start from.

### View 4 — PREPARE

**GOOD-5** — Clear that you need to pick a source first. "Create Lesson Plan" button is correctly disabled until a source is selected — no confusing error.

**FRICTION-5** — File upload gives no feedback. Claudia: "I tried to upload one but it is not clear if it is still uploading or didn't work." No spinner, no progress bar, no success/failure message. She can't tell if it's processing or broken.

**FRICTION-6** — Source text excerpt capped at 1,500 characters (`_SOURCE_EXCERPT_CHARS = 1500` in `lesson_materials.py:688`). Claudia's Blocco 1 lesson plan is a 4-block cycle (~3,500 chars). The generator only sees Blocco 1 + part of Blocco 2; the atelier (Blocco 3) and assessment/verifica (Blocco 4) are truncated. The app gives no indication that content was cut off — the teacher assumes the full file was used.

**BUG-1** — Generated activity does not reflect the uploaded lesson content. Claudia's file is a sensory museum provocation (6 stations: olfatto, udito, tatto, vista, movimento) but the generated tiers are generic brain/emotion worksheets ("My Brain and Me", "Exploring How We Express Emotions", "Exploring How We Think and Feel"). None reference the museum stations, the taccuino del ricercatore, the ⨯/~/✓/★ scale, or any specific element from her file. The tiers also have different *topics* rather than the same topic at different complexity levels — Foundational is about labeling a brain, On Track is about writing emotion sentences, Extended is about brain-body connections. These should be the same activity differentiated by scaffolding, not three unrelated worksheets.

**BUG-2** — All generated content is in English. Claudia teaches Italian immersion — the file is entirely in Italian. The generated activities should be in Italian (or at minimum bilingual), not monolingual English. The `language_of_instruction` is hardcoded to "en" in `lessonPayload()` (`static/index.html:2546`).

**GOOD-6** — Three tiers do appear, "stays on this computer" and "using selected coursework" badges are clear and reassuring.

**FRICTION-7** — All students default to Foundational tier. Only Corazza Miro and Muller Grey visible, both "default placement" → Foundational. On Track and Extended show "No students in this group." With no observations or CEFR data yet, the system has no basis to differentiate — but defaulting everyone to Foundational feels wrong. A teacher would expect most students in On Track with a few in Foundational/Extended. Override dropdown exists per student ("Use suggested (Foundational)") so manual override is possible.

**FRICTION-8** — Only 2 of ~40 students appear in Class groups. Claudia's roster has ~40 students but only Corazza Miro and Muller Grey show. The rest are missing from tier assignments — unclear why.

### View 5 — OBSERVE

**GOOD-7** — CEFR skill suggestion is correct: "speaking" for an observation about participating in group discussion using complete Italian sentences. Suggest fields works.

**GOOD-8** — Student stays selected after saving (v177 fix confirmed). Claudia saved a second observation for Miro without reselecting. Both observations appear in the right panel.

**GOOD-9** — Support Profile Review auto-populates sensible fields: "Communication and Language" category, Need ("Student needs to continue practicing structured speaking tasks in Italian"), Strength ("Student demonstrates ability to use complete sentences in Italian during group discussions"). SEL area "collaboration" and tone "positive" also correct.

**GOOD-10** — Privacy badge on saved observation: "Saved locally. Not uploaded. Not shared." with Domain: observation. Clear and honest.

**GOOD-11** — Right panel shows all observations for Miro including the new ones. Support profile section updated with "Communication and Language — 3 items".

**FRICTION-9** — Observation ID shown to teacher is a raw UUID: "Observation a2beac80-7e22-4b7d-abcb-3a7ed8100e42 is attached to the local lens." Claudia: "the number assigned to the observation is ridiculously long and I'm not sure it interests a teacher." Should be hidden or replaced with a human-readable label (e.g. "Observation #3 saved").

**FRICTION-10** — Existing observation on Miro's record reads: "Divorced parents. The mother appreciates being involved in school activities..." — this looks like a parent communication note, not a classroom observation. It's tagged "not tagged" and appears alongside academic observations. Mixing parent/family notes with classroom observations without clear visual separation could be confusing.

**BUG-3** — Safeguarding observation not flagged as restricted. Claudia typed "Aiken said someone at home makes him feel scared." for Boyce Aiken (note: student display name is "Boyce Aiken" = surname "Boyce", first name "Aiken" — all students are stored surname-first). It saved as a normal observation — tagged "not tagged", shown in Recent observations alongside regular notes, with standard "Saved locally. Not uploaded. Not shared." badge. No "Restricted record" badge, no safeguarding flag, no separation from normal observations. This is a critical safeguarding gap — this type of disclosure should be automatically flagged and restricted.

**GOOD-12** — False-positive test passed. "Boyce hit the ball really hard at recess and cheered" saved as a normal observation (not flagged), which is correct. Both observations now visible in Boyce Aiken's Recent observations panel.

**FRICTION-11** — Student names stored surname-first throughout the app (e.g. "Boyce Aiken" where Boyce is the surname and Aiken is the first name). This is how the roster was imported, but it's unintuitive — a teacher thinks of students as "Aiken" (first name) not "Boyce" (surname). The display order matters for quick scanning.

### View 6 — STUDENTS

**GOOD-13** — Roster loads and shows all students in a scrollable list. Each student card shows name, growth badge ("not enough yet"), data status ("insufficient_data"), and support tier. "Remove" button per student.

**GOOD-14** — Clicking Scala Luca opens a detailed lens panel with: CEFR trajectory, support tier, recent observations, colleague observations, and a full Category Profile (Learning and Cognition, Communication and Language, Executive Functioning, Social Skills — each with Need/Add fields). The layout is clear and structured.

**GOOD-15** — "System suggests; teacher reviews before any support-tier decision" badge with Confirm/Defer buttons and manual "Set support tier directly" dropdown. Teacher authority is respected — the system suggests, the teacher decides.

**FRICTION-12** — Every student shows "not enough yet" / "insufficient_data" / "support tier 1" — the roster is uniform with no differentiation. This is because observations haven't been entered yet for most students, but it makes the entire Students view feel empty/useless at this stage. No guidance on "start by observing these 5 students" or similar onboarding.

**GOOD-16** — "Remove" button does ask for confirmation before deleting a student. Safe against accidental clicks.

**BUG-4** — Safeguarding observation visible in Students view. Boyce Aiken's Recent observations in the Students view shows both observations including "someone at home makes him feel scared." This observation should be hidden from the normal student record and only visible in the restricted safeguarding ledger. Combined with BUG-3 (observation not flagged as restricted in Observe), the safeguarding pipeline is not functioning — sensitive disclosures are stored and displayed as normal observations.

### View 7 — ASSESS

**GOOD-17** — Empty state is clear and helpful: "No units for G3 yet — a rubric is built from a unit." with "Add a unit in Plan" button linking to Plan view. Teacher knows exactly what to do. Description is good: "Build CEFR-informed assessment structures that keep evidence visible without reducing a learner to a score."

**FRICTION-15** — Claudia uploaded her G3 Units of Inquiry file in Prepare and clicked "Add Unit" there, but it doesn't appear in the Assess unit dropdown. The unit was either not saved successfully during the Prepare flow, or the Add Unit form in Prepare requires different steps than expected. Claudia: "It doesn't see my unit, but I have uploaded the one on diversity, correct?" — the app didn't make it clear whether the unit was actually created.

### View 8 — ASK

**GOOD-18** — Header badge clearly states "answers come from the web" and the description honestly says "Nothing about your students is ever sent — questions that name a student are answered from their lens instead." Clear privacy boundary.

**GOOD-19** — Suggested starter questions are relevant and useful for a teacher: "What are strategies for a student with ADD in a language immersion classroom?", "What are some suggestions for helping kids with dyslexia learn to read?", "What are some good lesson plan ideas around Italian food vocabulary?"

**GOOD-20** — When Perplexity is not configured, the app is honest: "Ask searches the web for general teaching questions, and the web search service is not set up on this computer yet. Ask needs a Perplexity key before it can answer. Everything else in Lingua Viva works without it." Badges: "answered on this computer", "none", "0.0s", "no sources recorded". Not alarming — clearly explains the limitation.

**GOOD-21** — Student-specific question ("How is Corazza Miro doing in speaking?") shows "unverified" badge with disclaimer: "I don't have a solid source for this one, so take it as a starting point, not a final answer." This is honest and exactly right — the system doesn't claim certainty when it lacks grounding.

**BUG-5** — Despite the "unverified" badge, the answer about Miro fabricates specific claims: "Corazza Miro is making great progress in speaking! They are now able to use simple sentences to talk about their day and share what they like. This shows they are building confidence and understanding how to use words in real conversations. We've noticed they are especially excited..." These are invented details not grounded in any observation data. The only observations for Miro are "partecipato attivamente alla discussione di gruppo" and "segue le routines di classe con rispetto" — neither mentions sentences about daily life, sharing likes, or excitement. The "unverified" badge is necessary but insufficient — a fabricated narrative with an "unverified" label is still misleading.

### View 9 — SUMMARIES (Parent)

**GOOD-22** — Teacher review checklist present with 3 items: "Any student name or private detail that should not be shared has been removed", "Every claim is supported by observations I trust", "The tone sounds like me and is ready for this family." Copy/Print buttons disabled until checklist is completed. This is the right safeguard.

**GOOD-23** — "Review before sharing. No AI attribution in final message." badge visible at top right. Good — parents shouldn't see "generated by AI".

**GOOD-24** — Source attribution: "authoritative — Source: Manuale v1 and local teacher observations." Honest provenance.

**GOOD-25** — Safeguarding observation for Boyce Aiken does NOT appear in the Summaries view. Claudia confirmed: "I don't see Aiken here." This is correct — safeguarding data should never reach parent summaries.

**BUG-6** — Parent summary fabricates recommendations not grounded in observations. Summary says "We noticed your child trying new ways to make meaning in class" and recommends "offer a creative quiet workspace and notice what your child chooses to try first" and "Ask them one specific thing about their day and give them your full attention while they answer." Claudia: "I don't see why it is recommending that based on the two observations we collected so far. Why does he need to try new things?" The actual observations (group discussion participation, following class routines) don't support these specific recommendations. The summary invents a narrative from insufficient data.

**FRICTION-16** — Summary tone is functional but not warm. Claudia: "The tone is ok, not particularly warm." For a parent communication, warmth matters — especially in a Malaguzzi-inspired programme where the relationship with families is central.

### View 10 — SLACK

**GOOD-26** — Connection status is clear: three items (Signing secret, Bot token, Teacher channels) each with orange "needed" badge. Privacy boundary panel explains clearly: "Slack receives the original message under your school's workspace policy. Lingua Viva writes the observation to this machine and sends only a fixed saved/review acknowledgement back." Badges: "local student record", "no external model", "voice transcript supported".

**FRICTION-17** — Setup instructions are developer-level: "Set the HTTPS request URL to your approved public app address plus `/api/slack/events`", "subscribe to `message.channels` and grant `channels:history`", "Set `LV_SLACK_SIGNING_SECRET`, `LV_SLACK_BOT_TOKEN`, and `LV_SLACK_TEACHER_CHANNEL_MAP` in the local app environment." Claudia would not be able to follow these steps without IT support. Needs a simpler guide or a "Ask your school's IT administrator" message.

### View 11 — SOURCES

**GOOD-27** — Clear overview of what's connected: "1 of 3 set up". Folders on this computer: "connected, 4192 folders indexed, 53 student data zones excluded." Google Drive and Slack both show "not set up" with clear next steps. Good at-a-glance status.

**GOOD-28** — "Student data zone — excluded from AI processing" badge with explanation: "Folders that look like student records are found during a scan and left out of everything Lingua Viva reads." Privacy protection is visible and explained.

**GOOD-29** — Google Drive section is clear and honest: "Lingua Viva never sees the rest of your Drive. To bring in existing school documents, upload them directly in the app. Nothing leaves this machine until you choose to share it."

**FRICTION-18** — Claudia: "privacy explanation says clearly where materials come from but not where it lands." The page explains sources well but doesn't clarify where imported data ends up on her machine or how it's stored locally.

**FRICTION-19** — Claudia: "I don't understand what is Source ledger." The "Source ledger — 0 records" section uses technical terminology. A teacher doesn't think in terms of "ledgers" — needs a plain-language label like "Import history" or "Files Lingua Viva has read".

### View 12 — ACTIVITY

**GOOD-30** — "What you can do" section is excellent: lists each action (Save an observation, Generate a three-level activity pack, Show an assessment rubric, Draft a message for a parent) with clear privacy badges ("stays on this computer", "reads a student record", "changes a student record") and links to the relevant view. "1 of 8 send anything" visible — transparent about what stays local vs. what could go external.

**GOOD-31** — "Waiting for you" section with "Nothing here reaches a parent until you confirm it" is reassuring. Teacher stays in control.

**FRICTION-20** — "Suggestions awaiting your confirmation" items show ARON codes (S-055F0C2E3419, S-B9E52AC18B0C) with no way to identify which students they refer to or act on them. Claudia: "the suggestions are not clear. Those codes don't make any sense to me." Same issue as FRICTION-2 in Daily — the ARON codes are privacy-safe but useless without context. Clicking them doesn't open anything. Should either show initials, link to the student, or provide a way to confirm/dismiss inline.

---

## View Progress

- [x] View 1 — HOME
- [x] View 2 — DAILY
- [x] View 3 — PLAN
- [x] View 4 — PREPARE
- [x] View 5 — OBSERVE
- [x] View 6 — STUDENTS
- [x] View 7 — ASSESS
- [x] View 8 — ASK
- [x] View 9 — SUMMARIES
- [x] View 10 — SLACK
- [x] View 11 — SOURCES
- [x] View 12 — ACTIVITY
- [ ] View 13 — GOVERNANCE
- [ ] View 14 — WHY
- [ ] View 15 — HEALTH
- [ ] View 16 — PRIVACY
- [ ] View 17 — PROFILE
- [ ] View 18 — SETTINGS
- [ ] View 19 — REFLECT

---

## Session Notes

**Audit paused after View 12 (Activity).** Views 13-19 (Governance, Why, Health, Privacy, Profile, Settings, Reflect) remain untested. Claudia ended the session to focus on fixing the issues found so far.

**Coverage:** 12 of 19 views tested (63%). The 12 tested views cover all core teacher workflows (Home, Daily, Plan, Prepare, Observe, Students, Assess, Ask, Summaries) plus integrations (Slack, Sources) and Activity.

---

## Issue Summary — Prioritized by Impact

### P0 — Critical (safeguarding / data integrity)

| ID | View | Issue |
|----|------|-------|
| BUG-3 | Observe | Safeguarding observation not flagged as restricted |
| BUG-4 | Students | Safeguarding observation visible in normal student record |

### P1 — High (generation quality / teacher trust)

| ID | View | Issue |
|----|------|-------|
| BUG-1 | Prepare | Generated activity ignores uploaded lesson content |
| BUG-2 | Prepare | Language hardcoded to English instead of Italian |
| BUG-5 | Ask | Fabricated student claims despite "unverified" badge |
| BUG-6 | Summaries | Parent summary fabricates ungrounded recommendations |
| FRICTION-6 | Prepare | Source text truncated at 1500 chars with no warning |

### P2 — Medium (UX friction that blocks or confuses)

| ID | View | Issue |
|----|------|-------|
| FRICTION-2 | Daily | ARON confirmation items not clickable |
| FRICTION-5 | Prepare | File upload gives no feedback |
| FRICTION-7 | Prepare | All students default to Foundational tier |
| FRICTION-8 | Prepare | Only 2 of ~40 students appear in tier groups |
| FRICTION-9 | Observe | Raw UUID shown as observation ID |
| FRICTION-15 | Assess | Unit created in Prepare doesn't appear in Assess |
| FRICTION-20 | Activity | ARON codes not actionable or identifiable |

### P3 — Low (copy/terminology / polish)

| ID | View | Issue |
|----|------|-------|
| FRICTION-1 | Daily | CLI command in knowledge library empty state |
| FRICTION-3 | Daily | Daily view usefulness uncertain |
| FRICTION-4 | Plan | No pre-loaded curriculum content |
| FRICTION-10 | Observe | Parent notes mixed with classroom observations |
| FRICTION-11 | Observe | Student names stored surname-first |
| FRICTION-12 | Students | Uniform "insufficient data" for all students |
| FRICTION-16 | Summaries | Parent summary tone not warm enough |
| FRICTION-17 | Slack | Developer-level setup instructions |
| FRICTION-18 | Sources | Privacy page doesn't explain where data lands |
| FRICTION-19 | Sources | "Source ledger" is technical jargon |

---

## Fixes Applied (2026-08-29 session)

### Completed

| Finding | Fix | Files Changed |
|---------|-----|---------------|
| BUG-2 | `language_of_instruction` changed from `"en"` to `"it"` (frontend + backend defaults) | `static/index.html`, `src/education/content_differentiator.py`, `src/web.py` |
| FRICTION-9 | Removed raw UUID from observation confirmation — now shows human-friendly "Observation saved" | `static/index.html` |
| FRICTION-1 | Replaced CLI command `lv library add` with "upload in Sources or Prepare" | `src/lingua_viva/brief_extensions.py` |
| FRICTION-19 | Replaced "Source ledger" with "Import history" throughout Sources view | `static/index.html` |
| FRICTION-5 | Added visible upload/import badges during file upload in Prepare | `static/index.html` |
| FRICTION-6 | Added truncation warning when source file exceeds 1500 chars | `src/web.py`, `static/index.html` |
| FRICTION-2/20 | Made confirmation items clickable — Activity items navigate to Students, Daily items show "Review in Students →" link | `src/lingua_viva/activity.py`, `static/index.html` |
| FRICTION-18 | Added "Imported files stay in a private folder on this computer" to Sources description | `static/index.html` |

### Remaining (not yet fixed)

| Finding | Why Not Fixed | Recommended Approach |
|---------|--------------|---------------------|
| BUG-1 | Generation quality requires prompt engineering + possible excerpt cap increase | Increase `_SOURCE_EXCERPT_CHARS`, improve tier prompt to differentiate by scaffolding not topic |
| BUG-3/4 | Safeguarding pipeline not triggering — requires investigation of detection logic | Investigate `safeguarding.py` detection patterns, ensure Observe route calls safeguarding check |
| BUG-5/6 | Model fabrication with insufficient data — architectural issue | Add minimum-evidence gate: refuse to generate narrative with <3 observations, show honest "not enough data" |
| FRICTION-7/8 | Tier defaults + missing students in groups — needs data investigation | Check why only 2 students appear in tier assignments |
| FRICTION-11 | Surname-first display — depends on roster import format | Add display_name field or first/last name parsing |
| FRICTION-16 | Parent summary tone — prompt tuning needed | Adjust summary prompt to use Malaguzzi voice lens |
| FRICTION-17 | Slack setup instructions too technical | Rewrite as "Ask your school's IT team" + simplified guide |

---

## Closing Questions

*(to be completed when remaining views 13-19 are tested)*
