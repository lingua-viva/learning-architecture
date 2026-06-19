# 04 — AI-Powered Education for Refugee and Vulnerable Children

**`observed` · `designed`**

Adapting the frameworks from cases 01-03 (structural coherence, AI in the classroom, Lingua Viva) for an organization providing free IB World School education to refugee and vulnerable children across four countries.

---

## The Challenge

How do you build a governed AI education system for classrooms where:
- Students have experienced displacement, trauma, and interrupted formal education
- No two students share the same starting point or first language
- Teachers work in extreme conditions with limited resources and infrastructure
- The organization is fiercely independent and will not adopt tools that create dependency
- Internet connectivity is variable across campuses in different countries

## What Transfers from Prior Work

| Prior Case Study | What Transfers | What Must Be Adapted |
|-----------------|---------------|---------------------|
| **01 — Structural Coherence** | 50/50 principle (structure + autonomy), vertical alignment methodology, zero-sum complexity | Context shifts from a single well-resourced school to multiple campuses in low-resource settings |
| **02 — AI in the Classroom** | Teacher observation lenses, tiered adaptive learning, knowledge accumulation across grades | Must be redesigned for offline-first, low-tech environments |
| **03 — Lingua Viva** | CEFR progression framework (A1→B1), four-section grade structure, portfolio assessment, assessment systematization | Language pair changes (not Italian L2 — multiple L1s acquiring English/Spanish L2) |

## Design Principles for This Context

1. **Meet students where they are** — mastery-based progression, not grade-level assumptions
2. **Zero-sum complexity** — every tool must reduce teacher burden, never add to it
3. **Offline-first** — the system must work without reliable internet
4. **Teacher-owned** — knowledge compounds in their system, not ours
5. **Trauma-informed** — assessment must be safe, portfolio-based, never punitive
6. **Language-agnostic framework** — CEFR structure works for any L1→L2 pair
7. **Open source, no dependency** — they own the deployment, we train and step back

## Status

- **Meeting**: June 19, 2026
- **Phase**: Initial discovery — understanding their context, presenting our frameworks
- **Next**: If aligned, Phase 1 assessment (map their curriculum, identify AI opportunities)

---

## Directory Structure

```
04-still-i-rise/
├── README.md                          ← this file
├── context/
│   ├── organization.md                ← who they are, schools, philosophy
│   ├── challenges.md                  ← refugee education challenges we must solve
│   ├── prior-art.md                   ← what transfers from cases 01-03
│   └── teacher-use-cases.md           ← real teacher workflows from IB classrooms
├── proposal/
│   ├── approach.md                    ← how we'd approach this engagement
│   └── differentiators.md             ← why MC, not another EdTech
├── frameworks/
│   ├── multilingual-acquisition.md    ← CEFR applied to diverse L1 populations
│   ├── interrupted-education.md       ← assessment for students with gaps
│   └── teacher-empowerment.md         ← zero-sum complexity, institutional memory
├── architecture/
│   ├── README.md                      ← build sequence, decisions, risks overview
│   ├── data-model.md                  ← entity schema, pipeline spec, sync architecture
│   ├── rti-tiers.md                   ← 3-tier intervention system with escalation logic
│   ├── content-differentiation.md     ← 3-level content pack engine
│   ├── observation-capture.md         ← speech-to-text + parent artifacts
│   └── integration-risks.md          ← 5 seam risks, untested assumptions
└── meeting/
    ├── cheatsheet.md                  ← dense paragraphs for the conversation
    └── questions.md                   ← what to ask and why
```
