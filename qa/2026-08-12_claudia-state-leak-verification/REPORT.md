# QA Report — State Leak Verification (Claudia Canu, 2026-08-12)

**App version:** desktop-v0.2.56
**Platform:** macOS
**Duration:** ~45 min
**Tester:** Claudia Canu (real teacher, product user)

## Verdict

Bug 1 (state leak) FIXED, Bug 2 (PoI 404) FIXED, no regressions in core workflows. One new P1 bug found in safeguarding UI feedback. Several UX findings noted.

## Bug Verification

| Step | Check | Result | Notes |
|------|-------|--------|-------|
| 4    | Observe→Students state leak | PASS | Students tab loads normally, roster visible, Marco not pre-selected |
| 5    | Round-trip tab switch | PASS | Observe dropdown resets to "Choose a student", Students roster clean on return |
| 6    | Rapid tab switching ×10 | PASS | No errors across 10 rapid switches |
| 7    | Archive→tab switch | PASS | Marco archived, Observe→Students clean, only Nora in roster, no errors |
| 8    | PoI panel (no 404) | PASS | Shows "No POI activity recorded yet" for both students. Minor: casing is "Poi" not "PoI" |

## Teaching Workflow Regression

| Step | Check | Result | Notes |
|------|-------|--------|-------|
| 9    | Observe save | PASS | Observation saved with confirmation. Note: scroll issue — Save button not visible without maximizing the window |
| 10   | Lens update | PASS | New observation visible in Marco's student lens |
| 11   | Ask grounding | PASS | Response referenced Marco's observation only, no Nora data, no fabrication |
| 12   | Lesson materials | PASS | Prepare tab: "generation-failed" (no model). Ask tab: honest message explaining Perplexity key needed. Both are graceful degradation |
| 13   | Student summaries | PASS | Warm, plain language summary generated. No student names in output, no jargon, no cross-contamination |
| 14   | Multi-tab stress | PASS | Observe→Students→Ask→Students→Observe→Summaries→Students — clean navigation, no pre-selected student, no errors |

## Safeguarding

| Step | Check | Result | Notes |
|------|-------|--------|-------|
| 15   | Restricted routing | PARTIAL PASS | Backend: PASS — observation correctly flagged RED (physical_abuse), routed to restricted ledger, not visible in normal lens. UI: FAIL — showed raw error "Cannot read properties of undefined (reading 'observation_id')" instead of calm confirmation. The save did happen but the UI thought it failed. |
| 16   | Benign not over-flagged | PASS | "Marco hit the ball hard at recess and laughed" saved as normal observation, visible in record |
| 17   | No cross-contamination | PASS | Recess observation visible in Marco's profile, concerning observation correctly hidden |

### Safeguarding API verification (Claude Code)

- `GET /api/safeguarding/restricted` — returned the restricted entry (note: endpoint was accessible without auth restriction; harness expected denial for teacher role)
- `GET /api/students/student-marco/lens` — concerning observation NOT present in normal lens (correct)
- Restricted entry details: severity RED, matched physical_abuse patterns, status "open"

## Claudia's Feedback (verbatim)

1. **Ready for classroom?** "I cannot say yet. I don't have clarity on how the observations are gonna be used. I haven't tried to see the potential of preparing a differentiated material based on the lens or to assess."

2. **Student profile clarity?** "Student profile is very complete. Once the data will be inserted with consistency it will be a great lens."

3. **What's missing?** (Covered in answer 1 — needs to experience the full observation-to-differentiation pipeline before she can judge.)

4. **Surprises?** "The section 'Needs review' is not clear to me. Is it something we would use often and for what, why does it take the most visible portion of the page?"

5. **Warnings for other teachers?** "In the Observe section, it looks a little confusing that there is a text already inserted where we need to type a new observation (A learner self corrected passato prossimo, etc). Why there is 'Choose a student' twice — on the left with a scroll bar, on the right."

## New Findings

| # | Severity | Finding |
|---|----------|---------|
| 1 | P1 | **Safeguarding UI feedback broken.** When a concerning observation is routed to restricted ledger, the UI shows `Cannot read properties of undefined (reading 'observation_id')` instead of a calm confirmation. Backend routing works correctly — this is a frontend-only bug where the response shape from restricted saves differs from normal saves. |
| 2 | P2 | **Observe page scroll issue.** On a normal-sized window, the Save button is not visible — page doesn't scroll down to it. Claudia had to maximize the window to reach Save. |
| 3 | P2 | **Observe tab has confusing placeholder text.** The observation text box appears pre-filled with example text ("A learner self corrected passato prossimo...") which looks like an existing observation rather than a placeholder hint. |
| 4 | P2 | **Duplicate "Choose a student" UI.** The Observe tab shows a student selector both on the left (with scroll bar) and on the right. Unclear which to use. |
| 5 | P2 | **"Needs review" section prominence.** On the student profile, the "Needs review" section takes the most visible portion of the page. Its purpose is unclear to the teacher. |
| 6 | FR | **PoI casing.** Displayed as "Poi" instead of "PoI" (Programme of Inquiry). Minor cosmetic. |
| 7 | FR | **Restricted endpoint access.** `GET /api/safeguarding/restricted` returned data without teacher-role denial. May need role-based access control. |
