# Brief: GIR for Lingua Viva — Research & Write AGENTS.md Section

**Date:** 2026-08-03
**Author:** kiro.design
**Purpose:** Hand to a dev window to research LV's grounding surface and write a GIR section for its AGENTS.md
**Repo:** `~/learning-architecture` (remote: lingua-viva/learning-architecture)

---

## Context

Mission Canvas has a mature GIR (Grounding Integrity Rate) definition in its AGENTS.md:

```
GIR = 1 − (certainty claims about external state with an empty source list)
          / (total certainty claims about external state)
```

Computed inline at SYNTHESIZE, using trace fields: `kl_entries_loaded`, `patient_record_sources`, `case_file_sources`, `observation_sources`. The "caught lie" is mechanical: you stated something with certainty, your source list is empty.

LV needs its own version. But LV's grounding surface is different — it's an education app whose primary outputs are:
- CEFR level assessments
- Observation records
- Lesson materials (Italian language content)
- Cohort grouping decisions
- Teacher guides

The "caught lie" equivalents in LV would be things like:
- Assigned a CEFR level with no observation backing it
- Generated a grouping decision based on stale/wrong data
- Produced lesson content at a tier that doesn't match the student's actual level
- Made a certainty claim about a student with insufficient observation history

---

## Research Required

Before writing the GIR section, the dev window needs to read:

### 1. Current GIR implementation in LV
- `src/lingua_viva/grounding/build.py` — how is GIR computed today?
- `src/lingua_viva/grounding/__init__.py` — what's exported?
- What trace fields does LV's GIR check? (equivalent of MC's source lists)

### 2. What "grounded" means in the education domain
- When the system says "Marco is at A2 in speaking" — what constitutes grounding? (specific observation IDs? observation count threshold? recency?)
- When the system generates a cohort plan — what grounds the tier assignments? (student lens data? CEFR snapshots?)
- When lesson materials are generated — what grounds the content quality? (curriculum alignment? CEFR target match?)

### 3. Existing traces with GIR data
- Look at traces from Chip's QA session: `qa/traces/lingua-viva-2026-08-02_1334/`
- Look at Claudia's session traces (if they exist)
- Check: what does a GIR of 0.0 vs >0 look like in real LV output?

### 4. LV's current AGENTS.md
- Read the full file — understand its tone, structure, level of detail
- The current focus is the 7-step push definition + onboarding rules
- Where would a GIR section fit? After push def? As a separate "Quality" section?

---

## What to Write

A GIR section for LV's AGENTS.md that:

1. **Defines the LV-specific formula** — adapted for education domain, not copy-pasted from MC
2. **Lists the source fields** that constitute "grounding" for each output type (observations for CEFR claims, curriculum for lesson content, student lens for grouping decisions)
3. **Defines "caught lie" mechanically** — no interpretation needed, same as MC's principle
4. **Specifies where it's computed** — inline at the response moment, verdict-not-reconstruction
5. **Identifies the LV-specific lagging indicators** — what drifts look like in an education app (e.g., level inflation without new observations, curriculum coverage gaps in generated materials, grouping staleness)

---

## Key Principle to Preserve

From MC's AGENTS.md: **"Verdict, not reconstruction: compute the real thing once, at the real moment, in the real code path that has the ground truth. Store only the verdict. Never reconstruct it later from a proxy."**

This must carry over to LV. The question is: what IS the "real moment" for each LV output type?

- For CEFR claims → the moment student_lens is queried and observation_sources are in memory
- For lesson materials → the moment curriculum + student tiers are loaded and content is generated
- For cohort plans → the moment all student lenses are loaded and tier assignments computed

---

## Tone Guidance

LV's AGENTS.md is more concise and operationally focused than MC's. The GIR section should be:
- Short (1 page max)
- Concrete (exact field names, exact formula)
- Actionable (a dev should be able to implement a GIR check from reading this alone)
- Domain-specific (use "observation" / "curriculum" / "student lens" language, not MC's "file" / "record" / "calendar" language)

---

*End of brief. Research first, then write. Don't copy MC's GIR — adapt it.*
