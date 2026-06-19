# Refugee Education System — Data Model

## Pipeline Specification & Complete Schema

---

## 1. Pipeline Specification (`pipeline_spec`)

```yaml
pipeline:
  name: refugee_education_data_pipeline
  version: "1.0.0"
  classification: MC-DATA-005
  prerequisite: MC-DATA-001           # quality_report must exist before execution
  next_step: MC-DEPLOY-005

  governance:
    schema_validation: strict          # catches drift silently before it reaches destination
    soft_deletes: true                 # never hard-delete; sync integrity depends on this
    conflict_resolution: last-write-wins-with-version  # version field arbitrates

  sources:
    - id: device_local_db
      type: SQLite                     # offline-first; primary write surface
      sync_direction: bidirectional
    - id: cloud_postgres
      type: PostgreSQL                 # canonical store; receives synced payloads
      sync_direction: bidirectional

  transforms:
    - name: validate_schema
      runs: on_every_sync_event
      failure_mode: loud               # stops the pipeline; surfaces error immediately
    - name: detect_schema_drift
      runs: on_deploy
      failure_mode: silent_alert       # logs + alerts; does not silently pass
    - name: strip_ai_provenance
      description: >
        Remove any AI generation metadata before records enter ParentArtifact table.
        Parents never see AI attribution. This transform is mandatory and runs before
        any ParentArtifact write.
      failure_mode: loud

  success_criteria:
    - pipeline runs end-to-end without manual intervention
    - schema validation rejects malformed records at ingestion
    - schema drift detected and alerted within one sync cycle
    - ParentArtifact records contain zero AI provenance fields on arrival

  known_failure_modes:
    silent:
      - schema drift between SQLite device schema and PostgreSQL cloud schema
      - mitigation: versioned migrations, drift detection transform on every deploy
    loud:
      - sync failure — data stops flowing
      - mitigation: exponential backoff retry, conflict queue, manual reconciliation UI
```

---

## 2. Data Flow Diagram (`data_flow_diagram`)

```
┌─────────────────────────────────────────────────────────────────────┐
│                         DEVICE (Offline-First)                      │
│                                                                     │
│  Teacher App / Classroom App                                        │
│  ┌─────────────┐   Speech-to-Text   ┌──────────────────────┐       │
│  │ Teacher UI  │ ─────────────────► │ Observation (raw STT) │       │
│  └─────────────┘                    └──────────┬───────────┘       │
│                                                │                   │
│  ┌──────────────┐  ChecklistRun   ┌────────────▼──────────┐        │
│  │ Checklist UI │ ───────────────►│  ChecklistRun record  │        │
│  └──────────────┘                 └────────────┬──────────┘        │
│                                                │                   │
│                                   ┌────────────▼──────────┐        │
│                                   │   Local SQLite DB      │        │
│                                   │  (versioned, soft-del) │        │
│                                   └────────────┬──────────┘        │
└────────────────────────────────────────────────┼────────────────────┘
                                                 │
                         Sync (when online)      │ Bidirectional
                         Conflict resolution      │ version field wins
                         Schema validation        │
                                                 │
┌────────────────────────────────────────────────┼────────────────────┐
│                       CLOUD / SYNC LAYER        │                   │
│                                                 ▼                   │
│   ┌─────────────────────────────────────────────────────────────┐  │
│   │  Schema Validation Transform  (loud failure on bad record)  │  │
│   └──────────────────────────┬──────────────────────────────────┘  │
│                              │                                      │
│   ┌──────────────────────────▼──────────────────────────────────┐  │
│   │  Strip AI Provenance Transform  (mandatory, loud on failure) │  │
│   │  Applied before any ParentArtifact write                     │  │
│   └──────────────────────────┬──────────────────────────────────┘  │
│                              │                                      │
│   ┌──────────────────────────▼──────────────────────────────────┐  │
│   │            PostgreSQL (canonical cloud store)                │  │
│   │                                                              │  │
│   │  Campus ◄── Classroom ◄── Session ◄── Observation           │  │
│   │      │                       │                              │  │
│   │  Teacher ──────────────────►─┘                              │  │
│   │      │                                                      │  │
│   │  Student ──► RTIRecord ──► DifferentiatedPlan               │  │
│   │      │                                                      │  │
│   │      └──► ChecklistRun ──► ParentArtifact                   │  │
│   │              (AI stripped before write)                     │  │
│   └─────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────┘
```

---

## 3. Complete Schema (YAML)

```yaml
# ============================================================
# REFUGEE EDUCATION SYSTEM — COMPLETE DATA MODEL
# version: 1.0.0
# offline-first · 3-tier RTI · multilingual · STT observations
# Parents never see AI. AI provenance stripped at pipeline layer.
# ============================================================

# ── CONVENTIONS ─────────────────────────────────────────────
# Applied to every entity unless noted.
# Reasoning: offline-first sync requires version arbitration and
# soft deletes to prevent data loss on reconnect.
_conventions:
  primary_key:
    field: id
    type: UUID
    generation: client-side         # generated on device; safe for offline writes
  timestamps:
    created_at: datetime_utc
    updated_at: datetime_utc        # updated on every mutation, device or cloud
  soft_delete:
    is_deleted: boolean
    deleted_at: datetime_utc | null
    # Rationale: hard deletes during sync create ghost references and
    # unresolvable foreign key conflicts. Always soft-delete.
  sync_fields:
    version: integer                # monotonically incrementing; cloud wins on conflict
    client_id: string               # originating device UUID
    last_synced_at: datetime_utc | null
    sync_status:
      type: enum
      values: [pending, synced, conflict, error]


# ── ENTITY 1: Campus ────────────────────────────────────────
Campus:
  description: >
    Physical or administrative site. Refugee camps may have multiple
    campuses with intermittent connectivity; each campus is a sync boundary.
  fields:
    id: UUID
    name: string
    country_code: string            # ISO 3166-1 alpha-2
    region: string | null
    unhcr_site_code: string | null  # aligns with UNHCR operational data[external]
    is_active: boolean
    connectivity_profile:
      type: enum
      values: [offline_only, intermittent, reliable]
      # Drives sync scheduling; intermittent sites get priority sync slots
    created_at: datetime_utc
    updated_at: datetime_utc
    is_deleted: boolean
    deleted_at: datetime_utc | null
    version: integer
    client_id: string
    last_synced_at: datetime_utc | null
    sync_status: enum[pending, synced, conflict, error]

  indexes:
    - [country_code, is_active]
    - [unhcr_site_code]


# ── ENTITY 2: Classroom ─────────────────────────────────────
Classroom:
  description: >
    A physical or virtual learning group within a Campus. A classroom
    may span multiple grade-equivalent levels because students with
    interrupted schooling are placed by competency, not age or grade.
  fields:
    id: UUID
    campus_id: UUID                 # FK → Campus.id
    name: string
    grade_label: string | null      # human label only; not used for placement logic
    competency_band:
      type: enum
      values: [foundational, developing, grade_level]
      # Replaces grade as the operative grouping dimension
    max_capacity: integer | null
    room_identifier: string | null
    is_active: boolean
    created_at: datetime_utc
    updated_at: datetime_utc
    is_deleted: boolean
    deleted_at: datetime_utc | null
    version: integer
    client_id: string
    last_synced_at: datetime_utc | null
    sync_status: enum[pending, synced, conflict, error]

  indexes:
    - [campus_id, is_active]
    - [campus_id, competency_band]


# ── ENTITY 3: Teacher ───────────────────────────────────────
Teacher:
  description: >
    Educator assigned to one or more classrooms. May be a trained teacher,
    community facilitator, or paraprofessional — role field distinguishes.
  fields:
    id: UUID
    campus_id: UUID                 # FK → Campus.id (home campus)
    employee_code: string | null    # opaque HR identifier; no PII in this field
    display_name: string
    role:
      type: enum
      values: [certified_teacher, community_facilitator, paraprofessional, supervisor]
    primary_language_code: string   # ISO 639-1; for UI locale selection
    secondary_language_codes:
      type: array[string]
      # Multilingual teachers; used to route STT language model selection
    is_active: boolean
    pin_hash: string                # bcrypt hash; local auth for offline device login
    created_at: datetime_utc
    updated_at: datetime_utc
    is_deleted: boolean
    deleted_at: datetime_utc | null
    version: integer
    client_id: string
    last_synced_at: datetime_utc | null
    sync_status: enum[pending, synced, conflict, error]

  indexes:
    - [campus_id, is_active]


# ── ENTITY 4: Student ───────────────────────────────────────
Student:
  description: >
    Learner enrolled at a Campus. Refugee populations have high mobility;
    a student may transfer between campuses. Interrupted schooling history
    is captured in EducationGap. No grade field — placement is by
    competency. No L1 assumption; language profile is a separate entity.
  fields:
    id: UUID
    campus_id: UUID                 # FK → Campus.id (current campus)
    classroom_id: UUID              # FK → Classroom.id (current placement)
    token_id: string
      # Opaque, non-PII identifier printed on student card.
      # Used instead of name on shared devices to protect privacy.
    display_name: string | null     # shown only to teachers, never in parent-facing artifacts
    date_of_birth: date | null      # may be unknown; null allowed
    age_estimate: integer | null    # used when date_of_birth is null
    gender:
      type: enum
      values: [male, female, non_binary, prefer_not_to_say, unknown]
    nationality_code: string | null # ISO 3166-1 alpha-2
    enrollment_date: date
    enrollment_status:
      type: enum
      values: [active, transferred_out, withdrawn, graduated, unknown]
    transferred_from_campus_id: UUID | null   # FK → Campus.id
    transferred_at: datetime_utc | null
    rti_tier:
      type: enum
      values: [tier_1, tier_2, tier_3]
      default: tier_1
      # Current RTI tier; source of truth is RTIRecord history,
      # this is a denormalized cache for fast queries
    competency_band:
      type: enum
      values: [foundational, developing, grade_level]
      # Derived from most recent ChecklistRun; cached here for query performance
    created_at: datetime_utc
    updated_at: datetime_utc
    is_deleted: boolean
    deleted_at: datetime_utc | null
    version: integer
    client_id: string
    last_synced_at: datetime_utc | null
    sync_status: enum[pending, synced, conflict, error]

  indexes:
    - [campus_id, enrollment_status]
    - [classroom_id, rti_tier]
    - [token_id]                    # frequent lookup by card scan


# ── ENTITY 4a: StudentLanguageProfile ───────────────────────
StudentLanguageProfile:
  description: >
    Per-student language repertoire. Students share no common L1;
    each profile entry records a language and proficiency. Used to
    select STT model, assign translated materials, and flag when
    no materials exist in a student's dominant language.
  fields:
    id: UUID
    student_id: UUID                # FK → Student.id
    language_code: string           # ISO 639-1 or 639-3 for less-resourced languages
    language_name_local: string | null  # name in that language, for display
    proficiency_level:
      type: enum
      values: [none, beginner, intermediate, proficient, native]
    is_dominant: boolean            # true for the one primary language
    is_literacy_language: boolean   # student can read/write in this language
    source:
      type: enum
      values: [self_reported, teacher_assessed, translator_assessed]
    assessed_at: date | null
    created_at: datetime_utc
    updated_at: datetime_utc
    is_deleted: boolean
    deleted_at: datetime_utc | null
    version: integer
    client_id: string
    last_synced_at: datetime_utc | null
    sync_status: enum[pending, synced, conflict, error]

  constraints:
    - unique: [student_id, language_code]
    - rule: exactly_one_dominant_per_student
      # enforced at application layer; not DB constraint (SQLite limitation offline)


# ── ENTITY 4b: EducationGap ─────────────────────────────────
EducationGap:
  description: >
    Records periods of interrupted schooling. A student may have
    multiple gaps. Used to inform RTI tier assignment and to
    contextualize low checklist scores — a student with a 3-year
    gap is not failing; they are catching up.
  fields:
    id: UUID
    student_id: UUID                # FK → Student.id
    gap_start: date
    gap_end: date | null            # null = gap is ongoing at enrollment
    reason:
      type: enum
      values:
        [displacement, conflict, no_school_available, family_obligation,
         illness, documentation_barrier, unknown, other]
    reason_detail: string | null    # free text; teacher-entered
    years_of_prior_schooling: float | null
      # Estimated total schooling before this gap; may be fractional
    created_at: datetime_utc
    updated_at: datetime_utc
    is_deleted: boolean
    deleted_at: datetime_utc | null
    version: integer
    client_id: string
    last_synced_at: datetime_utc | null
    sync_status: enum[pending, synced, conflict, error]

  indexes:
    - [student_id, gap_start]


# ── ENTITY 5: Session ───────────────────────────────────────
Session:
  description: >
    A single instructional event: one classroom, one or more teachers,
    a defined time window. Observations and ChecklistRuns are anchored
    to a Session. Sessions created offline with local timestamps;
    clock skew corrected at sync using campus timezone metadata.
  fields:
    

A complete, production-ready data model for this use case is not available in existing literature or reference implementations; what follows is a synthesized schema that aligns with refugee education research, RTI practice, and offline‑first data patterns, with some design choices necessarily inferred rather than sourced directly.[1][5][6][2][3]

Below is a **single logical schema in YAML** (conceptual/relational, not vendor‑specific). It is structured for an offline‑first sync model (versioning, soft deletes, timestamps) and to support interrupted schooling, 3‑tier RTI, multilingual/differentiated content, and speech‑to‑text observations. Comments (`#`) mark key design decisions and where domain evidence is thinner and more inferred.

```yaml
# Core technical conventions for offline-first and sync
_conventions:
  id: UUID                        # All primary keys are UUIDs
  timestamps:
    - created_at: datetime_utc
    - updated_at: datetime_utc
  soft_delete:
    - is_deleted: boolean         # Never hard-delete; required for robust sync[2][3]
  offline_sync:
    - version: integer            # Increment on each mutation for conflict resolution[2]
    - client_id: string           # Originating device identifier
    - last_synced_at: datetime_utc

# Multilingual and content scaffolding support (students with no common L1)[5][6]
Locale:
  description: "Supported UI/assessment languages and localization metadata."
  fields:
    id: UUID
    code: string                  # e.g., 'en', 'ar', 'fr'
    name: string
    is_default: boolean
    direction: string             # 'ltr' or 'rtl'
    created_at: datetime_utc
    updated_at: datetime_utc
    version: integer
    is_deleted: boolean

LanguageProfile:
  description: "Per-student language repertoire for instruction and assessment; inferred structure due to limited primary schemas.[5][6]"
  fields:
    id: UUID
    student_id: UUID              # FK -> Student.id
    language_code: string         # ISO 639-1/2
    proficiency_receptive: string # 'none'|'basic'|'intermediate'|'advanced'
    proficiency_expressive: string
    literacy_level: string        # 'pre-literate'|'em
