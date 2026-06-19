[RIU-324] | 72187ms

# Classroom Content Differentiation Engine
## System Architecture for IB Schools Serving Refugee Students

---

## 1. Executive Summary

This system pre-generates differentiated 3-tier content packs from teacher lesson inputs and student roster data, caches them locally for offline use, and syncs opportunistically when connectivity is available. The architecture prioritises **offline-first reliability**, **multilingual support**, and **trauma-informed design** over real-time AI API calls.

**Design principle:** Generate at night when connectivity exists. Serve from cache always.

---

## 2. Component Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        TEACHER-FACING CLIENT LAYER                          │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        Teacher App (PWA)                            │   │
│  │                                                                     │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │   │
│  │  │  Lesson      │  │  Roster      │  │  Pack        │             │   │
│  │  │  Input Form  │  │  Manager     │  │  Viewer      │             │   │
│  │  │              │  │              │  │              │             │   │
│  │  │ • IB Subject │  │ • CEFR level │  │ • 3-tier     │             │   │
│  │  │ • Unit/Topic │  │ • RTI tier   │  │   tabs       │             │   │
│  │  │ • ATL skills │  │ • Learning   │  │ • Print view │             │   │
│  │  │ • Duration   │  │   diffs      │  │ • Student    │             │   │
│  │  │ • CEFR band  │  │ • Home lang  │  │   selector   │             │   │
│  │  │              │  │ • Trauma     │  │ • Offline    │             │   │
│  │  │              │  │   flags      │  │   indicator  │             │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘             │   │
│  │                                                                     │   │
│  │  ┌──────────────────────────────────────────────────────────────┐  │   │
│  │  │                    Service Worker (SW)                       │  │   │
│  │  │  • Intercepts all API calls                                  │  │   │
│  │  │  • Cache-first routing: SW checks LocalPackStore first       │  │   │
│  │  │  • Queues generation requests when offline                   │  │   │
│  │  │  • Plays queued requests on reconnect                        │  │   │
│  │  └──────────────────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│         ┌────────────────────────┼───────────────────┐                     │
│         ▼                        ▼                   ▼                     │
│  ┌──────────────┐  ┌─────────────────────┐  ┌──────────────────┐          │
│  │ LocalPack    │  │  IndexedDB Schema   │  │  Sync Queue      │          │
│  │ Store        │  │                     │  │                  │          │
│  │              │  │  packs {}           │  │  Pending genera- │          │
│  │  Cache-first │  │  roster {}          │  │  tion requests   │          │
│  │  read layer  │  │  templates {}       │  │  waiting for     │          │
│  │              │  │  sync_queue {}      │  │  connectivity    │          │
│  └──────────────┘  └─────────────────────┘  └──────────────────┘          │
└─────────────────────────────────────────────────────────────────────────────┘
                                   │
                          [HTTPS / offline gap]
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     LOCAL SCHOOL SERVER (LAN, no internet needed)           │
│                  (Raspberry Pi 4 / repurposed laptop / NUC)                 │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    Pack Generation Orchestrator                     │   │
│  │                                                                     │   │
│  │  ┌──────────────────────────────────────────────────────────────┐  │   │
│  │  │               Lesson Input Normaliser                        │  │   │
│  │  │  • Validates IB subject + unit against MYP/DP framework      │  │   │
│  │  │  • Generates canonical cache key:                            │  │   │
│  │  │    SHA256(subject + unit + topic + CEFR_target + ATL_codes)  │  │   │
│  │  │  • Checks PackCache before triggering generation             │  │   │
│  │  └──────────────────────────────────────────────────────────────┘  │   │
│  │                            │                                        │   │
│  │              ┌─────────────┴─────────────┐                         │   │
│  │              ▼                           ▼                          │   │
│  │  ┌───────────────────────┐  ┌────────────────────────────────┐     │   │
│  │  │   Template & Rules    │  │   Local Model Runtime          │     │   │
│  │  │   Engine              │  │   (Ollama + Llama 3.2:3b)      │     │   │
│  │  │                       │  │                                │     │   │
│  │  │  Rule-based scaffold: │  │  Used only when:               │     │   │
│  │  │  • CEFR A1→C2 rules   │  │  • Cache miss on topic        │     │   │
│  │  │  • RTI Tier 1/2/3     │  │  • No template match          │     │   │
│  │  │  • Dyslexia flags     │  │  • Internet unavailable        │     │   │
│  │  │  • ADHD/trauma flags  │  │                                │     │   │
│  │  │  • Home lang map      │  │  Fallback to Cloud API         │     │   │
│  │  │                       │  │  when internet available       │     │   │
│  │  │  Produces structured  │  │  (Claude / GPT-4o)             │     │   │
│  │  │  JSON pack skeleton   │  │                                │     │   │
│  │  └───────────┬───────────┘  └───────────────┬────────────────┘     │   │
│  │              │                              │                        │   │
│  │              └──────────────┬───────────────┘                       │   │
│  │                             ▼                                        │   │
│  │  ┌──────────────────────────────────────────────────────────────┐  │   │
│  │  │              Adaptation Pipeline                             │  │   │
│  │  │                                                              │  │   │
│  │  │  Stage 1 — Content Scaffold                                  │  │   │
│  │  │    Input: pack skeleton + tier (foundational/on-track/ext)   │  │   │
│  │  │    Output: exercises, explanations, discussion prompts       │  │   │
│  │  │                                                              │  │   │
│  │  │  Stage 2 — Language Adaptation                               │  │   │
│  │  │    Simplified syntax for A1/A2 (< 10-word sentences)        │  │   │
│  │  │    Glossary injection for content-specific vocabulary        │  │   │
│  │  │    Home language key-term overlay (Arabic, Somali, Dari…)    │  │   │
│  │  │                                                              │  │   │
│  │  │  Stage 3 — Learning Difference Adaptations                   │  │   │
│  │  │    Dyslexia: font tags, line-spacing flags, reading-load     │  │   │
│  │  │    ADHD:     chunked tasks ≤ 10 min, checklist format        │  │   │
│  │  │    Trauma:   low-stakes framing, opt-out prompts             │  │   │
│  │  │                                                              │  │   │
│  │  │  Stage 4 — Visual Support Generator                          │  │   │
│  │  │    Selects from pre-rendered SVG symbol library              │  │   │
│  │  │    Generates sentence frames as image overlays               │  │   │
│  │  │    Attaches Widgit/PECS-compatible icon sequences            │  │   │
│  │  │                                                              │  │   │
│  │  │  Stage 5 — Timing & Movement Injector                        │  │   │
│  │  │    Injects timer blocks per task chunk                       │  │   │
│  │  │    Adds movement break cards at configurable intervals       │  │   │
│  │  │    Respects lesson duration constraint                       │  │   │
│  │  └──────────────────────────────────────────────────────────────┘  │   │
│  │                             │                                        │   │
│  │                             ▼                                        │   │
│  │  ┌──────────────────────────────────────────────────────────────┐  │   │
│  │  │                      Pack Cache                              │  │   │
│  │  │                                                              │  │   │
│  │  │  Key:   SHA256(subject|unit|topic|cefr_target|atl_codes)     │  │   │
│  │  │  Value: Serialised PackBundle (JSON + asset references)      │  │   │
│  │  │                                                              │  │   │
│  │  │  TTL policy:                                                 │  │   │
│  │  │  • Curriculum content: 90 days (stable)                      │  │   │
│  │  │  • Student-personalised overlays: 7 days (rosters change)    │  │   │
│  │  │  • Visual assets: indefinite (versioned by hash)             │  │   │
│  │  │                                                              │  │   │
│  │  │  Eviction: LRU, max 2 GB local storage                       │  │   │
│  │  │  Staleness check: compare against content_version header     │  │   │
│  │  └──────────────────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                   │
                    [Opportunistic sync — HTTPS]
                    [Fires when internet detected]
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CLOUD SYNC LAYER (optional)                         │
│                                                                             │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────────┐ │
│  │  Template CDN    │  │  Cloud LLM API   │  │  Analytics Aggregator   │ │
│  │                  │  │  (Claude /       │  │                          │ │
│  │  Pushes updated  │  │   GPT-4o)        │  │  Anonymised usage data   │ │
│  │  template packs  │  │                  │  │  to improve templates    │ │
│  │  to all schools  │  │  Higher-quality  │  │  No PII ever leaves      │ │
│  │  on reconnect    │  │  generation for  │  │  local server            │ │
│  │                  │  │  cache-miss      │  │                          │ │
│  └──────────────────┘  └──────────────────┘  └──────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Data Models

### 3.1 Lesson Input

```typescript
interface LessonInput {
  id: string;                        // UUID, teacher-generated
  ib_programme: "MYP" | "DP" | "PYP";
  subject: string;                   // e.g. "Individuals & Societies"
  unit_title: string;                // e.g. "Migration and Identity"
  topic: string;                     // e.g. "Push and pull factors of forced migration"
  atl_skills: ATLSkillCode[];        // e.g. ["COMM-01", "CRIT-03"]
  cefr_target: CEFRBand;             // Class-level target, e.g. "B1"
  duration_minutes: number;          // Total lesson time, e.g. 60
  language_of_instruction: string;   // ISO 639-1
  created_by: string;                // Teacher ID (local, no PII sync)
  created_at: ISO8601;
}

type ATLSkillCode = string;          // IB ATL taxonomy codes
type CEFRBand = "A1"|"A2"|"B1"|"B2"|"C1"|"C2";
```

### 3.2 Student Lens

```typescript
interface StudentLens {
  student_id: string;                // Local pseudonym, never real name in transit
  cefr_level: CEFRBand;
  rti_tier: 1 | 2 | 3;             // 1 = universal, 2 = targeted, 3 = intensive
  learning_differences: LearningDiff[];
  home_languages: string[];          // ISO 639-1, ordered by proficiency
  trauma_flag: boolean;              // Triggers low-stakes framing only
  mobility_interruption_years: number; // Years of interrupted schooling
  last_updated: ISO8601;
}

type LearningDiff =
  | "dyslexia"
  | "adhd"
  | "dyscalculia"
  | "processing_speed"
  | "working_memory"
  | "anxiety"
  | "sensory";
```

### 3.3 Content Pack (Cache Unit)

```typescript
interface ContentPack {
  pack_id: string;                   // SHA256 of cache key components
  lesson_id: string;
  generated_at: ISO8601;
  content_version: string;           // Semver, bumped on template update
  tiers: {
    foundational: TierContent;
    on_track: TierContent;
    extended: TierContent;
  };
  student_overlays: Record<string, StudentOverlay>; // keyed by student_id
  assets: AssetManifest;
}

interface TierContent {
  tier: "foundational" | "on_track" | "extended";
  learning_objective: string;        // Simplified for tier
  vocabulary_list: VocabItem[];

A differentiation engine for IB refugee classrooms should be built as an **offline‑first, pre‑generation pipeline** that converts lesson topics and student profiles into a cached library of 3‑tier content packs (foundational / on‑track / extended), so classrooms can operate without reliable connectivity while periodically syncing to improve models and content templates.[1][2] The core gap in the literature is how to adapt standard LLM caching concepts (prompt/prefix, semantic, multi‑layer caches) to *pre‑planned, humanitarian, multilingual, low‑connectivity* IB settings, rather than just web apps with always‑on APIs.[1][2][3][8]

Below is an architecture tailored to that gap.

---

### 1. High‑level system architecture (offline‑first, pre‑generation)

**Core components**

- **Teacher App (Client)**
  - Runs on low‑spec laptop or tablet.
  - UI to enter:
    - Lesson metadata: IB subject, unit, topic, ATL skills, target CEFR band.
    - Class roster: name or ID, CEFR level, RTI tier, learning differences (e.g., dyslexia, ADHD), home language, trauma flags.
  - Displays generated 3‑tier packs:
    - Foundational / On‑track / Extended variants.
    - Adapted exercises, visual supports, checklists with timers, movement breaks.
  - Works entirely offline using a local content cache; sync is opportunistic.

- **Local Content Engine (on device or local school server)**
  - **Template & Rules Engine**
    - Rule‑based scaffolding by CEFR and RTI:
      - Foundational: simplified language, more visuals, sentence frames, more guided practice.
      - On‑track: standard IB expectations, mixed item types.
      - Extended: open inquiry tasks, higher‑order questions, extended writing.
    - Learning‑difference adaptations:
      - Dyslexia: font choice tags, line spacing, more visuals, reduced reading load.
      - ADHD / trauma: short timed chunks, clear checklists, frequent movement or quiet breaks.
  - **Local Model Runtime (optional, depending on hardware)**
    - Small multilingual model for text rewriting / simplification.
    - All prompts and outputs are deterministic or tightly constrained to maximize cache reuse.[1][2][8]
  - **Local Cache Store**
    - Multi‑layer
