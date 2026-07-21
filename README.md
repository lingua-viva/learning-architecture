# Learning Architecture

**Frameworks for designing educational systems that actually work — powered by a governed AI engine.**

---

I'm Claudia Canu Fautré — a curriculum architect who has designed learning systems across three scales: global product launches at Google (40+ countries, 2 years as Localization PM), institutional curriculum design at a 4-campus IB international school in San Francisco (6 years), and multilingual academic research (PhD, Paris-Sorbonne; 31 publications across 5 languages).

My work sits at the intersection of three questions:
1. **How do you build a curriculum that integrates competing pedagogical frameworks** (IB, Reggio Emilia, language immersion) into a single coherent system?
2. **How can AI support teachers** without replacing the judgment, empathy, and relational complexity that only humans bring?
3. **How do you measure whether learning is actually happening** — not through compliance metrics, but through evidence that students are genuinely more capable?

This repository contains frameworks, case studies, and methods from my work designing educational systems, plus the Lingua Viva local-first teacher app. The runtime keeps teacher workflows inspectable: every response can show its route, sources, privacy events, and local trace metadata.

---

## Maturity Labels

Everything here is labeled with its honest maturity stage:

| Label | Meaning |
|-------|---------|
| `observed` | I noticed this pattern across multiple contexts |
| `designed` | I created a framework to address it |
| `proposed` | I presented this to institutional leadership |
| `piloted` | I tested this with a small group |
| `validated` | I measured outcomes and have evidence |

---

## Case Studies

### [01 — Structural Coherence](case-studies/01-structural-coherence/)
**`designed` · `proposed`**

A 6-layer diagnostic framework for institutions where multiple pedagogical traditions coexist but compete for limited time and resources. Developed from observing how IB, Reggio Emilia, and Italian language immersion interact — and fail to interact — across a K-8 school with four campuses.

### [02 — AI in the Classroom](case-studies/02-ai-classroom/)
**`designed` · `proposed`**

An institutional proposal for using AI to strengthen continuity — preserving and enriching the knowledge teachers build about students as they progress through grades. Two systems: teacher observation lenses (AI-summarized, accumulated K-8) and tiered adaptive learning (universal, targeted, intensive).

### [03 — Lingua Viva](case-studies/03-lingua-viva/)
**`designed`**

A K-5 Italian language programme guide designed to integrate four frameworks — Italy's Indicazioni Ministeriali, CEFR A1→B1 progression, IB PYP inquiry, and Reggio-inspired multimodality — into a single manual with learning goals, activities, assessment rubrics, and a student portfolio system. Part of a 3-year strategic initiative currently in the design and pilot phase.

---

## Methods

### [Teacher AI Workflow](methods/teacher-ai-workflow.md)
**`validated` — daily use since 2024**

How I actually use ChatGPT and Claude in my teaching practice — real prompts, real outputs, real iterations. What works, what doesn't, and what I'd build if I had engineering support. This is not theory. This is what a curriculum architect does with AI tools every day.

### [Assessment Philosophy](methods/assessment-philosophy.md)
**`validated` — 93% improvement measured against national norms**

Assessment coherence: how I design assessment systems that track real learning, not just completion. CEFR language progression (A1-B1), Prove MT national benchmarking, and the principle that every instructional decision should be traceable to evidence.

---

## Education Skills

Purpose-built frameworks in [`skills/education/`](skills/education/):

| Skill | What It Does |
|-------|-------------|
| [Adaptive Learning Framework](skills/education/adaptive-learning-framework.md) | AI-assisted personalized learning for children with learning differences (validated on ARON pilot) |
| [Curriculum Operating Workspace](skills/education/claudia-curriculum-operating-workspace.md) | Local-first framework treating curriculum as the primary data structure |
| [Convergence Workspace](skills/education/claudia-convergence.md) | Collaborative architecture for active education projects |

---

## Lenses

Interpretive filters that shape how the engine processes queries:

| Lens | Purpose |
|------|---------|
| [Person Lens — Claudia Canu Fautré](lenses/LENS-PERSON-002_claudia_canu.yaml) | Professional identity, capabilities, working style, and growth edges |
| [Malaguzzi Voice Guide](lenses/VOICE-EDU-001_malaguzzi_inspired.md) | Framework for writing educational documents in a Reggio-inspired voice |
| Core lenses (`lenses/core/`) | Protection, precision, critique, synthesis, reflection |
| Professional lenses (`lenses/professional/`) | Legal, clinical, fiduciary |

---

## The Runtime — Lingua Viva

This repository includes the Lingua Viva teacher runtime and the public site at [linguaviva.art](https://linguaviva.art). The app provides:

- **Teacher-first local app** — planning, preparation, observation capture, student lenses, assessment, parent drafts, health, privacy, profile, and Why views
- **Ontology-based routing** — 111 nodes across 25 domains classify teacher queries before model reasoning
- **Local-first reasoning** — Ollama-first model calls with trace metadata and no raw query text in trace storage
- **Privacy-visible workflow** — privacy events, support bundles, file maps, and profile clear controls are visible to the teacher
- **Evidence-tiered knowledge** — 178 entries and 559 citations

### Quick Start

**Download the app**: [linguaviva.art](https://linguaviva.art)

Or install from terminal:

```bash
curl -fsSL https://raw.githubusercontent.com/lingua-viva/learning-architecture/main/install.sh | sh
```

Or from source:

```bash
pip install -e .
python3 -m src.lv_cli serve 8787
```

### Engine Structure

| Directory | What's in it |
|---|---|
| `src/lingua_viva/` | Native local-first runtime, config, privacy, file map, trust traces, CLI |
| `src/education/` | Teacher-facing product modules |
| `src/` | Python runtime bridge and legacy pipeline retained for strangler migration |
| `ontology/` | 111-node classification system across 25 domains |
| `knowledge/` | Evidence-tiered library — 178 entries, 559 citations |
| `lenses/` | Interpretive filters + person lenses + voice guides |
| `memory/` | Path-structured persistence (Redis + NDJSON) |
| `agents/` | 6 intent agents + orchestrator |
| `skills/` | Education skills + morphable capability layer |
| `config/` | Three-tier governance (Tier 1 immutable, Tier 2 reviewed, Tier 3 auto) |
| `runtime/` | Node.js message broker + voice hub |
| `tests/` | Gateway, ontology, memory, knowledge, integration |
| `desktop/` | Electron shell with guided setup wizard (Python/Ollama detection, one-click install) |
| `doctor/` | Local diagnostics and support-bundle tooling |
| `docs/` | Public landing site (linguaviva.art — auto-deploys via GitHub Pages) |

---

## What This Repository Is

This is a **learning design portfolio and local teacher app**. The portfolio contains frameworks for thinking about educational systems, case studies from real institutional work, and methods I use daily as a practitioner. The app keeps teacher-facing AI support local, inspectable, and tied to accountable evidence.

If you are looking for someone who can design learning experiences that produce measurable outcomes, and who builds AI-governed systems to support that practice, this is what that looks like from the inside.

---

## Publication Policy

See [publication-policy.md](publication-policy.md) for what is shared here, what is anonymized, and why.

---

## About Me

**Current**: Italian Language Program Coordinator & K-8 Educator, 4-campus IB international school, San Francisco
**Recent**: Adjunct Lecturer, University of Paris Nanterre (2023–Dec 2025, concurrent — adult learning design)
**Previous**: Localization Program Manager, Google (2018-2020) · Research Associate & Lecturer, University of Cagliari (2012-2018) · PhD, Paris-Sorbonne University
**Professional Leadership**: AATI Conference Committee & California Chapter Organizer
**Languages**: Italian (native) · French (native) · English (C2) · Spanish (conversational)

---

### In My Own Words

*Translated from Italian — this is how I think about the throughline of my work:*

> In my doctoral training I was led to analyze complex intercultural systems and make sense of a research architecture by structuring concepts and content. I had the opportunity to complete an excellent academic path and at the same time organize international cultural events — inviting writers, curating programs, serving on scientific committees — and work with excellent results as a multilingual vendor at international fairs in Paris, seeing how my analytical and communication abilities found concrete application in real-life situations.
>
> Later I managed a group of 12 staff for the tourism office of Cagliari and began building experiences in human management — but also in solving problems in ways nobody had thought of before, contacting merchants on the main streets to request they stay open between 1pm and 5pm to guarantee cruise passengers a better experience in the city. The merchants improved their earnings, the cruise passengers found usable and authentic services.
>
> While maintaining a constant commitment to research and teaching — which allowed me to teach university courses and publish 10 books and more than 20 articles — I also managed the implementation of a localization project for a water treatment plant in North Africa, learning to manage larger projects with diverse stakeholders. This enabled me in my first phase of working life in San Francisco to work as a localization project manager for Google and successfully launch products in 40+ countries.
>
> In my phase at the school I confronted myself with teaching elementary school children and learned in a few years the complexity of managing classroom dynamics with particular attention to the child, their needs, and the best way to accompany them on their journey. The methodologies the school promotes — Italian language immersion, IB framework, and Reggio-inspired approach — make the educational environment stimulating but at the same time are perceived as a heavy load for the teachers who operate within it.
>
> In my journey at the school I have reached a professional maturity where the management of my individual classroom is now consolidated and produces excellent results. What I would like to engage my highest competencies in are the structural challenges that would allow bringing excellence not to one grade but to all grades. Moving in this direction, I proposed the creation of an Italian curriculum — Lingua Viva — conceived with the school's methodological pillars in mind. I asked myself whether AI could facilitate data collection and our system of communicating this data in the transition between academic years, realizing that teachers operate mostly in isolation and this lack of alignment ultimately affects the learning trajectory of individual students and how families perceive it.
>
> Although these proposals may seem disparate and heterogeneous, they all address the improvement of the school's structure, which at this historical moment must find greater coherence and stronger reference points to sustain the growth and trust earned from its community.

---

*This repository represents my professional portfolio of educational design work and the Lingua Viva local teacher app. For academic publications, see [LinkedIn](https://linkedin.com/in/claudia-canu-fautre-31b204162). For inquiries: claudiacanufautre@gmail.com*
