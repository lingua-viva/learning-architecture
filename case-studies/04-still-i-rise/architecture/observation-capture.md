# Teacher Observation Capture System
## Data Pipeline Design — Refugee Education Classrooms

---

## ARTIFACT 1: Pipeline Specification

---

### 1. System Overview

This pipeline converts a teacher's spoken observation (≤30 seconds interaction time) into a structured record that flows through student profiles, RTI escalation logic, and teacher-approved parent recommendations. It operates offline-first with eventual sync, and never exposes AI attribution to parents.

---

### 2. Core Data Models

#### 2.1 Observation Record (canonical schema)

```json
{
  "observation_id": "uuid-v4",
  "schema_version": "1.2",
  
  // Pre-set context (teacher taps before recording)
  "session_id": "uuid-v4",
  "student_id": "uuid-v4",
  "teacher_id": "uuid-v4",
  "template_type": "literacy | cefr | sel_incident | sel_positive | rtl_flag",
  
  // Capture metadata
  "recorded_at_local": "ISO8601 with timezone offset",
  "device_id": "uuid-v4",
  "connectivity_at_capture": "offline | online",
  "audio_duration_seconds": 12,
  
  // Speech-to-text
  "raw_transcript": "She read the passage but lost the thread at paragraph 3...",
  "transcript_confidence": 0.87,
  "transcript_language": "en | ar | fr | so | other",
  "teacher_edited_transcript": "She read the passage but lost comprehension at paragraph 3",
  
  // Structured tags (template-specific defaults, teacher-confirmed)
  "tags": {
    "rti_tier": 1 | 2 | 3,
    "rti_tier_changed_this_obs": false,
    "cefr_dimension": "reading | writing | speaking | listening | null",
    "cefr_level_observed": "A1 | A1+ | A2 | B1 | null",
    "cefr_direction": "progressing | plateaued | regressing | null",
    "sel_domain": "self_regulation | peer_relations | engagement | null | not_applicable",
    "sel_valence": "positive | concern | neutral | null",
    "urgency_flag": false,
    "language_of_instruction_note": "student switched to L1 mid-task"
  },
  
  // Sync state
  "sync_status": "pending | synced | conflict",
  "synced_at": null,
  "server_observation_id": null,
  
  // Provenance
  "pipeline_stage": "captured | validated | enriched | archived",
  "validation_errors": [],
  "schema_validated": true
}
```

#### 2.2 Session Record (pre-populated before observation)

```json
{
  "session_id": "uuid-v4",
  "class_group_id": "uuid-v4",
  "subject": "literacy | numeracy | language | sel | integrated",
  "language_of_instruction": "ar | fr | en | so | multilingual",
  "session_date": "YYYY-MM-DD",
  "period": "morning | afternoon | period_3",
  "teacher_id": "uuid-v4",
  "student_roster": ["student_id_1", "student_id_2"]
}
```

#### 2.3 Student Longitudinal Profile (built from observations)

```json
{
  "student_id": "uuid-v4",
  "profile_version": "integer, increments on each update",
  "last_updated": "ISO8601",
  
  "rti_current_tier": 2,
  "rti_tier_history": [
    {"tier": 1, "from": "2025-01-10", "to": "2025-03-01", "trigger": "observation_id"},
    {"tier": 2, "from": "2025-03-01", "to": null, "trigger": "observation_id"}
  ],
  
  "cefr_snapshot": {
    "reading": "A2", "writing": "A1+", "speaking": "A2", "listening": "B1"
  },
  "cefr_trajectory_30d": "progressing | plateaued | mixed | insufficient_data",
  
  "sel_summary": {
    "recent_concerns": 2,
    "recent_positives": 5,
    "dominant_domain": "self_regulation",
    "last_urgency_flag": null
  },
  
  "observation_count_total": 47,
  "last_observation_date": "2025-07-14",
  
  "recommendation_history": [
    {
      "recommendation_id": "uuid-v4",
      "sent_date": "2025-06-30",
      "teacher_approved": true,
      "parent_delivered": true
    }
  ]
}
```

#### 2.4 Parent Recommendation Record

```json
{
  "recommendation_id": "uuid-v4",
  "student_id": "uuid-v4",
  "teacher_id": "uuid-v4",
  
  // Generation
  "generated_at": "ISO8601",
  "generating_observation_ids": ["obs-id-1", "obs-id-2"],
  "ai_draft": {
    "subject_line": "A note about Amina's reading progress",
    "body": "Over the past two weeks, Amina has been working hard on...",
    "suggested_home_activities": ["Read together for 10 minutes...", "Ask her to retell..."],
    "tone": "encouraging | informational | action_required"
  },
  
  // Teacher review
  "teacher_review_status": "pending | approved | edited_and_approved | rejected",
  "teacher_edited_body": null,
  "teacher_approved_at": null,
  "teacher_approval_notes": "Changed activity 2, tone was right",
  
  // Parent-facing artifact (what parents actually see — no AI fields)
  "parent_artifact": {
    "subject_line": "A note about Amina's reading progress",
    "body": "Over the past two weeks, Amina has been working hard on...",
    "home_activities": ["Read together for 10 minutes...", "Ask her to retell..."],
    "from": "Ms. Fatima (Class Teacher)",
    "sent_via": "sms | print | app_message",
    "language": "ar | fr | so | en"
  },
  
  // Delivery
  "delivered_at": null,
  "delivery_confirmed": false,
  "attribution_visible_to_parent": false   // hard-coded false, never changes
}
```

---

### 3. Pipeline Stages

#### Stage 0: Pre-Session Setup (teacher, 60 seconds, once per session)
```
Teacher opens app → taps "New Session"
→ Selects class group (pre-loaded roster)
→ Confirms subject and language of instruction
→ Session record written to local SQLite
→ Student avatars loaded from local cache
→ All subsequent observations inherit session_id automatically
```

#### Stage 1: Observation Capture (teacher, ≤30 seconds per observation)
```
Step 1 (2s):  Teacher taps student avatar
              → student_id pre-set
              → current RTI tier loaded as default tag

Step 2 (2s):  Teacher taps observation template icon
              → template_type set
              → tag defaults populated from student profile

Step 3 (10-15s): Teacher holds RECORD button
              → audio captured to local buffer
              → on-device STT begins (Whisper or equivalent)
              → audio discarded after transcription (privacy)

Step 4 (5-8s): Transcript displayed for quick review
              → Teacher edits if needed (keyboard or re-record)
              → Tag defaults shown; teacher adjusts if wrong
              → RTI tier shown prominently — tap to change

Step 5 (1s):  Teacher taps SAVE
              → Observation record written to local SQLite
              → Validation runs immediately (see Stage 2)
              → UI resets for next student
```

**30-second budget breakdown:**

| Action | Max Time |
|---|---|
| Tap student + template | 4s |
| Record speech | 12s |
| Review transcript | 8s |
| Confirm/adjust tags | 4s |
| Save | 2s |
| **Total** | **30s** |

#### Stage 2: Local Validation (device, immediate, background)
```
On SAVE:
  □ required fields present (student_id, session_id, template_type)
  □ transcript length > 0
  □ rti_tier within {1, 2, 3}
  □ cefr fields present if template_type = 'cefr'
  □ sel_domain present if template_type = 'sel_incident'
  □ timestamp is not in the future
  □ schema_version matches current app version

If validation_errors > 0:
  → Flag observation with warning (does not block save)
  → Teacher sees amber indicator on saved card
  → Errors logged to validation_errors[]

Schema version mismatch:
  → Observation quarantined locally
  → Not synced until app update resolves schema
  → Teacher notified: "1 observation held — update app to sync"
```

#### Stage 3: Local Enrichment (device, background, post-save)
```
After save, background process:
  → Load student's observation history from local cache
  → Update local running aggregates:
      - cefr_trajectory_30d (recalculate from last 30 days)
      - sel_recent_concerns (count urgency_flag = true, last 14 days)
      - rti_tier_unchanged_days (days since last tier change)
  → Write updated snapshot to local student profile cache
  → If urgency_flag = true:
      → Trigger local notification: "Review [student] before end of day"
```

#### Stage 4: Sync (device ↔ server, background, opportunistic)
```
Sync triggers:
  → Device connects to WiFi
  → Teacher manually taps "Sync now"
  → App opened after 24h offline gap

Sync protocol:
  → All pending observations ordered by recorded_at_local ASC
  → POST each to /api/v1/observations in batches of 20
  → Server returns server_observation_id + server_timestamp
  → Local record updated: sync_status = "synced"

Conflict detection (schema drift guard):
  → Server validates schema_version on each record
  → If server schema_version > record schema_version:
      → Server attempts backward-compatible migration
      → If migration fails: record flagged sync_status = "conflict"
      → Teacher dashboard shows conflict count
      → Admin resolves via migration tool (not teacher's problem)

Sync failure handling:
  → Retry with exponential backoff (1m, 5m, 30m, 2h)
  → Records never deleted from local until sync_status = "synced"
  → Local data is always the source of truth until confirmed synced
```

#### Stage 5: Server-Side Aggregation (server, post-sync)
```
On receiving new observation batch:
  → Append to observations table (append-only, immutable)
  → Recalculate student longitudinal profile:
      - RTI tier history
      - CEFR snapshots and trajectories
      - SEL trend summaries
  → Write new profile_version (previous version archived, not deleted)
  → Evaluate RTI escalation rules (see Section 4)
  → If recommendation_trigger conditions met → queue recommendation generation
```

#### Stage 6: RTI Escalation Logic (server, event-driven)
```
Escalation triggers (any one condition):
  Rule A: ≥3 observations with rti_tier = 2 in 10 school days
           AND cefr_direction = "regressing" in ≥2 of those
           → Escalate to Tier 2 review queue

  Rule B: Any single observation with urgency_flag = true
           → Immediate notification to teacher + support coordinator

  Rule C: rti_tier = 1 AND no observations in 15 school days
           → "Monitoring gap" alert to teacher

  Rule D: sel_recent_concerns ≥ 3 in 7 days
           → SEL support flag added to student lens

  Rule E: Teacher manually changes rti_tier in any observation
           → Always triggers review queue regardless of other rules

On escalation:
  → Escalation event written to rti_events table
  → Student lens updated: rti_alert_status = "review_needed"
  → Teacher dashboard badge increments
  → Support coordinator notified (if role exists in school config)
```

#### Stage 7: Recommendation Generation (server, AI-assisted)
```
Trigger: recommendation_trigger = true (from Stage 5)
  OR teacher manually requests recommendation from student lens

Input to AI model:
  → Last 14 days of observations for this student
  → Current CEFR snapshot
  → Current RTI tier and recent trajectory
  → Student language background (not name, not ID — pseudonymized)
  → Template: which type of note (progress | concern | activity_ideas)
  → School config: max reading level for parent communications,
                   preferred language, cultural tone flags

AI generates:
  → subject_line
  → body (teacher voice, first-person plural "we")
  → 2-3 home_activities (concrete, no materials required)
  → tone classification

All of this written to ai_draft field.
recommendation_status = "pending_teacher_review"
Teacher notified: "You have 1 recommendation to review"

IMPORTANT: ai_draft is a backend field only.
           It is never transmitted to any parent-facing endpoint.
           parent_artifact is constructed only after teacher approval.
```

#### Stage 8: Teacher Approval (teacher, ≤5 minutes)
```
Teacher opens recommendation review:
  → Sees AI draft presented as "suggested message"
  → No "generated by AI" label visible in UI
    (Internal admin logs retain full provenance)
  → Can: Approve as-is | Edit then approve | Reject

On Approve:
  → parent_artifact constructed from approved body
  → from field set to teacher's display name
  → attribution_visible_to_parent hard-locked to false
  → teacher_approved_at timestamped
  → Recommendation queued for delivery

On Edit then Approve:
  → teacher_edited_body stored (for audit, not sent to parent)
  → parent_artifact constructed from edited body
  → Same lock: attribution_visible_to_parent = false

On Reject:
  → Draft discarded
  → teacher_approval_notes optionally captured
  → No parent artifact created
  → Model feedback loop: rejection + notes fed back to improve
    future generation (aggregated, not individual student data)
```

#### Stage 9: Parent Delivery
```
Delivery channels (school configures priority order):
  1. In-app message (if parent has app)
  2. SMS (body text only, no attachments)
  3. Print queue (PDF generated, printed by school admin)
  4. WhatsApp via approved gateway (where infrastructure exists)

Parent artifact transmitted:
  → subject_line
  → body (teacher-approved text only)
  → home_activities list
  → from: "Ms. [Teacher Name] (Class Teacher)"
  → school_logo (if app/print channel)

Fields NEVER transmitted to parent:
  → ai_draft
  → generating_observation_ids
  → Any student performance metrics
  → Any field with "ai_" prefix
  → Any internal IDs

Delivery confirmation:
  → App: read receipt
  → SMS: delivery receipt from gateway
  → Print: admin marks as "handed to family"
  → delivered_at timestamped on confirmation
```

---

## ARTIFACT 2: Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  DEVICE (offline-capable)                                                   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  STAGE 0: Session Setup                                             │   │
│  │  Teacher selects class → session_id created → roster loaded        │   │
│  └─────────────────────────────┬───────────────────────────────────────┘   │
│                                │ session_id inherited by all observations   │
│  ┌─────────────────────────────

A practical design is a **mobile-first, offline-capable note‑taking app** where the teacher taps a student and session, speaks for a few seconds, the app transcribes locally (or via on‑device model), and the teacher quickly confirms tags (RTI tier, CEFR aspect, SEL note) before saving; these events sync to a central store that powers student profiles, RTI escalation logic, and parent‑facing recommendations that are AI‑drafted but always teacher‑approved and never labeled as AI.

Below focuses on the **data pipeline gaps** and design details you will not get from general data‑pipeline best‑practice articles, which mostly address generic batch/stream pipelines and not ultra‑short, human‑in‑the‑loop, offline classroom workflows.[1][3][5][6]

---

### 1. Observation capture: what standard data‑pipeline patterns don’t cover

General pipeline guides describe ingestion → transformation → storage but do **not** address: ultra‑low interaction time (<30s), intermittent connectivity, and high‑stakes human annotation under stress.[1][5][6] Missing details you must design explicitly:

1. **UX + data model coupling**

   What is usually missing:
   - Pipelines docs rarely specify how the UI constrains the schema, but here the schema must mirror a 30‑second flow.

   Concrete design:
   - Teacher taps a **session** (class/time) first; this pre‑sets `session_id`, `subject`, `language_of_instruction`, `group_id`.
   - Teacher taps a **student avatar** (photo or pseudonym icon) which pre‑sets `student_id`.
   - Teacher taps one of 3–4 **observation templates** (e.g., “literacy skill,” “language CEFR,” “SEL incident,” “positive SEL”) – each template maps to different required/optional tags.
   - Teacher presses and holds **Record** (max 10–15 seconds). On release:
     - Local STT engine produces draft text.
     - Template‑specific tag prompts appear as **defaults**, not blank fields:
       - `RTI_tier` defaulted from current student status but editable.
       - `CEFR_dimension` pre‑selected (e.g., “speaking: interaction”) based on template.
       - `SEL_code` surfaced as top 3 predictions from a local lightweight classifier
