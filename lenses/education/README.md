# Lingua Viva Education Lenses

**Status**: `designed` — generated through MC CREATE intent with Claude Sonnet 4.6
**Generated**: June 19, 2026

## 9 Education-Specific Lenses

Each lens changes HOW the model reasons without changing WHICH node executes.

| Lens | Activates On | Core Constraint |
|------|-------------|-----------------|
| **curriculum-designer** | LV-CUR-* | Every unit anchored to testable central idea + CEFR alignment |
| **differentiation-coach** | LV-CUR-004, LV-TCH-004 | All 3 levels address same central idea — differentiation ≠ less content |
| **rti-monitor** | LV-STU-004/005/006 | Tier movement is a human decision gate, never automatic |
| **assessment-specialist** | LV-ASS-* | Gaps framed as forward steps, never deficits. No grade-level comparison for SIFE students |
| **trauma-informed** | wellbeing flags, refugee context | Emotional safety, low-stakes framing, progressive disclosure |
| **multilingual-learner** | LV-CUR-003, CEFR queries | L1 transfer as competence, code-switching as strength, oral-first |
| **observation-coach** | LV-TCH-001/002 | Structured observation, pattern interpretation, not vague notes |
| **parent-voice** | LV-PAR-* | Teacher voice only, zero AI attribution, no jargon |
| **school-leader** | LV-INF-*, cross-campus | Systemic patterns, resource allocation, never micro-managing students |

Each lens defines:
- `activates_on` — trigger conditions (node IDs or semantic signals)
- `reasoning_frame` — ordered steps the model must execute
- `forbidden_patterns` — what the lens actively suppresses
- `quality_checks` — verifiable signals that the lens worked
- `output_contract` — required sections in every response
