# Still I Rise + Lingua Viva SlackBot Workflow Proposal Checklist

Date: 2026-07-30
Purpose: proposal-ready checklist for a SlackBot creation plan grounded in what Lingua Viva can actually implement.

## Executive Recommendation

Start with a school-operations SlackBot, not a broad AI chatbot.

The first production workflow should be **staff absence and substitute coverage**. It is frequent, urgent, measurable, and already maps closely to Lingua Viva's existing Slack operations architecture:

- deterministic ops classifier
- ops record database
- coverage request status machine
- Slack interactive buttons
- daily staff briefing file
- configurable workflow packs
- app-side Bot Setup panel
- audit/privacy logging

The bot should turn Slack messages or structured forms into operational records, route them, ask humans to claim or approve, escalate unresolved work, update participants, and preserve an audit trail outside Slack.

## Product Principle

Structured input beats message surveillance.

For Still I Rise, the bot should not start by reading every Slack conversation. The safer and more useful model is:

1. Staff use a slash command, shortcut, button, DM, or designated ops channel.
2. The bot asks for missing fields.
3. The deterministic workflow engine creates a record.
4. Human coordinators approve or resolve high-impact actions.
5. Daily and cross-school summaries are generated from records, not Slack history.

AI can assist with wording, summarization, translation, and approved-document retrieval later. It should not be the authority for staffing, safeguarding, leave legitimacy, or student supervision.

## What Lingua Viva Already Supports

These are implementable now or very close to implementable because the repo already has the underlying primitives.

| Capability | Current Lingua Viva support | Proposal status |
|---|---|---|
| Slack Socket Mode transport | Built: `src/lingua_viva/slack_socket.py` handles Socket Mode, reconnect, ack-before-processing, posting, updating, and DMs. | Use as base transport. |
| Slack credential setup | Built: `src/lingua_viva/slack_credentials.py` and Settings UI store/configure Slack tokens and teacher map. | Use, but improve credential/security posture before production. |
| Ops record database | Built: `src/education/ops_records.py` stores absences, coverage, schedule, announcements, logistics, facilities. | Use as system of record for MVP or bridge to external SoR. |
| Absence intake by natural message | Built: deterministic classifier detects absence and coverage requests. | Use for DM/ops-channel MVP; add slash-command/modal structured path next. |
| Coverage request cards | Built: bot posts coverage card with Claim button. | Use; add coordinator approval if Still I Rise requires it. |
| Coverage status machine | Built: `open -> claimed -> confirmed` for coverage requests. | Use; adjust to `open -> claimed -> approved/confirmed` for larger schools. |
| Lesson notes / emergency plan | Built: absence flow supports Add lesson notes, Use emergency plan, Cancel. | Use as immediate substitute handover. |
| Daily briefing / daily file | Built: `DailyFileEngine` renders teacher daily files and app Daily view. | Use for campus daily command briefing. |
| Workflow packs | Built: config packs for absence/coverage, announcements, schedule, student logistics, facilities, bus/transport, dismissal. | Use as proposal catalog. |
| Bot setup + corpus gate | Built: Bot Setup panel, pack selection, corpus testing, go-live gate. | Use for school-specific configuration. |
| Privacy boundary | Built: ops bot reads only configured ops channel and DMs; Slack ops never writes student lenses. | Preserve as non-negotiable. |

## Important Current Limits

These should be stated clearly in the proposal so expectations stay realistic.

| Limit | Meaning | Recommendation |
|---|---|---|
| Coverage auto-confirms today | The first successful claim becomes confirmed. | Add coordinator approval for Still I Rise if class supervision requires explicit approval. |
| No structured Slack modal intake yet | Current flow is natural-language DM/ops-channel classification, not `/absence` modal form. | Build `/absence` as the first Still I Rise extension. |
| Staff directory is minimal | Current `LV_SLACK_TEACHER_MAP` has Slack ID, teacher_id, display name. | Add campus, role, grade, subject, eligibility, availability, manager, timezone. |
| No intelligent eligibility routing yet | Coverage cards go to configured ops channel, not only qualified substitutes. | Add routing rules before multi-campus rollout. |
| Escalation is limited | Current bot has scheduled briefings/reminders, not full escalation ladders. | Add campus-configurable escalation timers. |
| Facilities is capture-only | Facilities messages can be recorded, but not assigned/resolved with owners. | Phase 2 workflow extension. |
| No Slack App Home workflow UI yet | Lingua Viva has app UI and Slack buttons, but not a Slack App Home command center. | Optional Phase 2/3. |
| Slack is not emergency infrastructure | Socket Mode requires internet and the LV service running. | Critical workflows need SMS/phone/manual fallback. |

## Recommended Phase 1: Absence and Coverage MVP

### Goal

Convert staff absences into confirmed, auditable coverage assignments with minimal manual coordination.

### User Entry Points

Checklist:

- [ ] `/absence` slash command
- [ ] Slack global shortcut: Report an absence
- [ ] Mission Canvas / Lingua Viva app button: Report absence
- [ ] DM fallback: teacher can still type "I'm out tomorrow and need coverage for period 2"
- [ ] Ops-channel fallback: coordinator can post a coverage request manually

### Absence Form Fields

Checklist:

- [ ] Campus
- [ ] Date
- [ ] Full day or specific periods
- [ ] Grade / class
- [ ] Subject / responsibility
- [ ] Type: planned leave, illness, emergency, late arrival
- [ ] Coverage needed: yes/no
- [ ] Handover / lesson-plan link
- [ ] Emergency plan available: yes/no
- [ ] Should coordinator contact teacher: yes/no
- [ ] Optional private note for HR/leadership

Privacy rule:

- [ ] Public Slack notifications must not display medical details or private explanations.

### Coverage Record

Each absence that needs coverage should create a record similar to:

```text
Coverage request SIR-0241
Campus: Nairobi
Class: Grade 7 Mathematics
Date: Thursday
Periods: 1-3
Coverage: required
Handover: available
Status: searching
```

Checklist:

- [ ] Record exists outside Slack
- [ ] Record has stable ID
- [ ] Record stores source Slack event reference
- [ ] Record stores status
- [ ] Record stores assigned substitute, if any
- [ ] Record stores approval history
- [ ] Record stores final outcome

### Routing

The bot should notify only appropriate people.

Checklist:

- [ ] Campus coverage channel, e.g. `#coverage-nairobi`
- [ ] Campus operations channel, e.g. `#campus-operations`
- [ ] Relevant coordinator DM
- [ ] Optional central staffing channel
- [ ] Substitute pool filtered by campus
- [ ] Teacher pool filtered by subject/grade permission
- [ ] Availability filtered by period
- [ ] Weekly coverage-limit check

### Claim and Approval

Current Lingua Viva can post a Claim button and confirm coverage. For Still I Rise, use a stronger approval model:

Checklist:

- [ ] `I can cover all`
- [ ] `I can cover part`
- [ ] `Unavailable`
- [ ] `Assign substitute`
- [ ] `Escalate`
- [ ] Partial-coverage form asks which periods
- [ ] Claim creates tentative assignment
- [ ] Coordinator receives Confirm / Choose another person
- [ ] Final confirmation updates all parties

Recommended status machine:

```text
open -> claimed -> coordinator_approved -> confirmed
open -> escalated -> claimed -> coordinator_approved -> confirmed
open/claimed -> cancelled
open/claimed -> unresolved
```

### Notifications

Checklist:

- [ ] Absent teacher receives receipt
- [ ] Substitute receives assignment confirmation
- [ ] Coordinator receives approval request
- [ ] Coverage channel receives status update
- [ ] Original Slack card updates in place
- [ ] Daily staffing summary updates
- [ ] Calendar/staffing sheet updates, if connected

### Escalation

Campus-configurable example:

- [ ] T+0: notify qualified substitute pool
- [ ] T+10 minutes: notify grade/department colleagues
- [ ] T+20 minutes: notify academic coordinator
- [ ] T+30 minutes or class-start threshold: notify Head of Teaching and Learning / operations lead
- [ ] Stop all escalation once confirmed
- [ ] Mark critical if class start is approaching and no coverage is confirmed

### Daily Staffing Summary

Checklist:

- [ ] Posted each morning per campus
- [ ] Central summary for authorized leadership
- [ ] Counts reported absences
- [ ] Counts fully covered absences
- [ ] Counts awaiting coverage
- [ ] Counts substitute periods assigned
- [ ] Flags teachers approaching coverage limits
- [ ] Lists critical unresolved classes

Example:

```text
Nairobi staffing - Thursday
4 reported absences
3 fully covered
1 awaiting coverage
6 substitute periods assigned
2 teachers approaching weekly coverage limit
```

## Recommended Phase 2: Operational Request Center

These workflows reuse the same model:

```text
Request -> Triage -> Assign -> Act -> Escalate -> Resolve
```

### Facilities

Already partially implementable as capture-only. Extend to full workflow.

Checklist:

- [ ] Report a problem shortcut
- [ ] Campus
- [ ] Room/location
- [ ] Category
- [ ] Severity
- [ ] Description
- [ ] Photo upload, if useful
- [ ] Teaching blocked: yes/no
- [ ] Assign owner
- [ ] Remind owner
- [ ] Requester confirms resolution
- [ ] Close record

### IT Help

Checklist:

- [ ] Device/account/network/software category
- [ ] Urgency
- [ ] Affected class or staff member
- [ ] Owner assignment
- [ ] Status updates in thread
- [ ] Resolution confirmation

### Supplies

Checklist:

- [ ] Item needed
- [ ] Quantity
- [ ] Campus/room
- [ ] Needed by date
- [ ] Approval threshold
- [ ] Procurement owner

### Schedule and Timetable Changes

Partially implementable now through schedule-change pack and daily files.

Checklist:

- [ ] Leadership posts schedule change
- [ ] Bot identifies affected campus/grade/staff
- [ ] Sends targeted notifications
- [ ] Staff acknowledge Seen / Conflict / Need clarification
- [ ] Coordinator sees missing acknowledgements
- [ ] Daily file and campus briefing update

### Transport

Backlog pack already exists as vocabulary/section data.

Checklist:

- [ ] Bus delay notices
- [ ] Route changes
- [ ] Bus duty changes
- [ ] Student pickup/dismissal interaction with student logistics
- [ ] Broadcast to affected staff only when directory data supports it

## Recommended Phase 3: Knowledge, Onboarding, and Communication

### Policy and Procedure Assistant

This should use approved documents only. It should always cite source document, version, and effective date.

Checklist:

- [ ] Absence procedure
- [ ] Field-trip risk assessment
- [ ] Purchase approval process
- [ ] Safeguarding escalation path
- [ ] Assessment reporting deadlines
- [ ] HR / leave policy
- [ ] Campus-specific operations handbook
- [ ] Escalate to human when answer is not in approved sources

AI rule:

- [ ] Retrieval can help find approved policy text.
- [ ] The bot must not invent policy.
- [ ] The bot must cite sources.

### Teacher Check-ins

Checklist:

- [ ] Morning readiness pulse
- [ ] Staffing blockers
- [ ] Materials blockers
- [ ] Student-support blockers
- [ ] Facilities blockers
- [ ] Only exceptions enter command channel

### Teacher Onboarding

Checklist:

- [ ] Assign mentor
- [ ] Safeguarding policy acknowledgement
- [ ] Emergency procedures acknowledgement
- [ ] Timetable review
- [ ] Curriculum resources access
- [ ] Required training completion
- [ ] Leadership meeting
- [ ] First-week check-in

## Recommended Phase 4: Carefully Governed AI

AI can help with:

- [ ] classify incoming requests when deterministic rules are insufficient
- [ ] extract date, campus, class, and urgency from free text
- [ ] summarize long operational threads
- [ ] find approved policy information
- [ ] translate notices
- [ ] draft handover summaries
- [ ] detect missing information

AI must not:

- [ ] decide whether leave is legitimate
- [ ] assign an unqualified person to supervise students
- [ ] make safeguarding decisions
- [ ] diagnose a student or employee
- [ ] reveal sensitive student information
- [ ] override campus leadership
- [ ] close high-risk incidents without human confirmation

The live operational engine should remain deterministic. AI assists language and retrieval; humans approve decisions.

## Staff Directory Requirements

The absence/coverage workflow needs a controlled directory.

Checklist:

- [ ] Slack user ID
- [ ] Full name
- [ ] Campus
- [ ] Role
- [ ] Grade levels
- [ ] Subjects
- [ ] Coverage eligibility
- [ ] Normal working days
- [ ] Available periods
- [ ] Manager/coordinator
- [ ] Preferred language
- [ ] Time zone
- [ ] Current leave status
- [ ] Maximum additional coverage
- [ ] Safeguarding / supervision eligibility, if applicable

Without this layer, the bot can broadcast requests but cannot make reliable assignments.

## Recommended Channel Structure

Per campus:

- [ ] `#campus-announcements`
- [ ] `#campus-operations`
- [ ] `#staff-absence`
- [ ] `#coverage-[campus]`
- [ ] `#facilities-[campus]`
- [ ] `#it-help`
- [ ] `#teacher-resources`

Central / authorized staff:

- [ ] `#ops-command`
- [ ] `#staffing-central`
- [ ] `#cross-school-education`
- [ ] `#urgent-operations`
- [ ] `#mission-canvas-audit`

Sensitive safeguarding or HR details should not be posted in broad staff channels. Public alerts should say that a restricted case requires attention; details should remain in an authorized system or controlled private channel.

## Slack Permissions Recommendation

For the absence MVP, request the minimum scopes required.

Recommended starting scopes:

- [ ] `commands`
- [ ] `chat:write`
- [ ] `users:read`
- [ ] `channels:read`
- [ ] `app_mentions:read`, only if app mentions are supported
- [ ] `im:history`, only for direct-message intake

Avoid at MVP:

- [ ] `channels:history`, unless the bot must interpret normal messages in a designated public channel
- [ ] `groups:history`, unless the bot must monitor a designated private channel
- [ ] `mpim:history`, likely unnecessary for the initial product

Principle:

- [ ] The bot should read only configured intake surfaces.
- [ ] Slack should not be the permanent database.
- [ ] Every sensitive workflow needs an external record and audit trail.

## Technical Architecture

Recommended architecture:

```text
Slack
  - Slash commands
  - Shortcuts
  - Modal forms
  - Interactive notification cards
  - Optional App Home

Lingua Viva / Mission Canvas service
  - Deterministic workflow engine
  - Staff and role directory
  - Availability and coverage rules
  - Escalation scheduler
  - Notification service
  - Audit logging
  - Optional approved-document retrieval

Systems of record
  - Staff directory / HR source
  - Timetable / calendar
  - Absence and coverage records
  - Policy/document repository
  - Reporting dashboard
```

Implementation note:

Lingua Viva already has a local-first Socket Mode implementation. For a Still I Rise multi-campus production deployment, decide whether this runs:

- centrally hosted by Still I Rise, or
- per-campus local Lingua Viva instance, or
- hybrid local capture with central reporting.

This decision affects reliability, Slack event delivery, data residency, and escalation fallback.

## Metrics

Absence and coverage:

- [ ] Median time from report to confirmed coverage
- [ ] Percentage covered before school day begins
- [ ] Number of manual messages per absence
- [ ] Percentage requiring escalation
- [ ] Uncovered teaching periods
- [ ] Additional coverage distribution across staff
- [ ] Percentage submitted with complete information
- [ ] Incorrect assignments
- [ ] Notification acknowledgement rate
- [ ] Teacher satisfaction
- [ ] Coordinator satisfaction

Facilities / IT:

- [ ] Time to first owner
- [ ] Time to resolution
- [ ] Reopened requests
- [ ] Blocked-teaching incidents
- [ ] Requests by campus/room/category

Knowledge assistant:

- [ ] Answered from approved source
- [ ] Escalated to human
- [ ] Missing source gaps
- [ ] Source/version citation present

## Proposed Build Sequence

### Phase 1: Absence and Coverage MVP

- [ ] Extend staff directory model
- [ ] Add `/absence` slash command
- [ ] Add Slack modal form
- [ ] Create absence/coverage record from modal
- [ ] Route to campus coverage channel
- [ ] Add partial-coverage claim form
- [ ] Add coordinator approval before final confirmation
- [ ] Add configurable escalation ladder
- [ ] Add daily staffing summary
- [ ] Add metrics dashboard/report
- [ ] Run campus pilot with synthetic data first

### Phase 2: Operational Request Center

- [ ] Facilities full assignment/resolution workflow
- [ ] IT help workflow
- [ ] Supplies workflow
- [ ] Timetable-change acknowledgement workflow
- [ ] Transport and dismissal packs enabled after corpus testing

### Phase 3: Knowledge and Communications

- [ ] Approved policy search
- [ ] Calendar integration
- [ ] Teacher digests
- [ ] Onboarding checklist
- [ ] Surveys / check-ins
- [ ] Cross-campus education updates

### Phase 4: Governed AI

- [ ] AI extraction for incomplete requests
- [ ] AI summarization for long threads
- [ ] AI translation for notices
- [ ] AI policy retrieval with citations
- [ ] Human approval gates for all operational decisions

## Proposal Decision Checklist

Before build starts, Still I Rise should decide:

- [ ] Which campus pilots first?
- [ ] Who owns coverage approval?
- [ ] Who may cover which classes?
- [ ] What is the escalation ladder by campus?
- [ ] What is the source of truth for staff availability?
- [ ] What is the source of truth for timetables?
- [ ] What Slack channels are official intake surfaces?
- [ ] What details are never allowed in public Slack messages?
- [ ] What fallback channel is used if Slack/internet is unavailable?
- [ ] Is the bot centrally hosted, campus-local, or hybrid?
- [ ] Which workflows are in Monday MVP vs later phases?

## Bottom Line

The strongest Still I Rise SlackBot is a reliable staffing and operations router that happens to live in Slack. Lingua Viva already has enough Slack ops infrastructure to support a credible absence-and-coverage MVP. The next step is not a general AI assistant; it is structured absence intake, eligibility-aware routing, human approval, escalation, and daily staffing reporting.
