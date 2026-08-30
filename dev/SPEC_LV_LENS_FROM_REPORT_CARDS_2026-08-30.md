# SPEC: Document-to-Lens Pipeline — Report Card Ingestion

**Date**: 2026-08-30
**Author**: Claude (6th attempt — previous attempts logged in commit history)
**Status**: DRAFT — needs triple-lens review before implementation

## Problem Statement

Teachers have student report cards (PDFs, docx files) containing rich academic
performance data — grades, teacher comments, learning observations, areas of
concern. Currently, importing these files into Lingua Viva only finds student
names. The actual academic content is NOT parsed into student lenses.

Claudia said: "we can see the report cards but we only find the names... which
we already have. What we actually need is for the model to go through the
academic performance and parse out sentences or phrases and decide where to put
them in the student lens."

## Non-Negotiables (from Claudia)

1. **NEVER put information from Student A into Student B's lens.** Catastrophic.
2. **No hallucination.** Only insert text that actually appears in the document.
3. **OK to stop and ask.** Better to ask than to insert wrong data.
4. **Final repass.** After inserting all data, sweep each lens to deduplicate
   and summarize without inventing new information.

## Architecture Decision

**Local LLM first.** Use qwen3:8b via Ollama. If the model isn't strong enough,
the handoff infrastructure to Mission Canvas exists — but try local first.

## The 10 Lens Profile Fields

From `docpipe/schemas/lens.schema.json`:

1. `learning_and_cognition` — academic performance, learning style, cognitive needs
2. `communication_and_language` — reading, writing, speaking, listening, CEFR
3. `executive_functioning` — organization, focus, planning, self-regulation
4. `social_skills` — collaboration, peer interaction, group dynamics
5. `emotional_regulation` — emotional awareness, coping, self-management
6. `physical_sensory_needs` — motor skills, sensory processing, physical needs
7. `attendance_and_engagement` — participation, attendance, engagement patterns
8. `strategies_trialed` — interventions, accommodations, approaches tried
9. `academic_strengths` — subjects/areas where student excels
10. `personal_strengths` — character traits, interests, talents

## Current Infrastructure (what exists)

| Component | Status | What it does |
|-----------|--------|-------------|
| `routers/document_import.py` | EXISTS | Two-step flow: import-document → apply-extractions |
| `docpipe/lens_match.py` | WORKS | Matches names in document to roster |
| `docpipe/lens_extract.py` | PARTIAL | Has heuristic extractors (CEFR, IB, ATL, attendance) but NO sentence-level academic routing |
| `docpipe/identity.py` | WORKS | Name normalization and resolution |
| `student_lens_writer.py` | WORKS | Writes extracted fields to lens store |
| `data_in_contracts.py` | EXISTS | ExtractedField, ExtractionResult, field constants |
| `extraction_engine.py` | EXISTS | Chunking, LLM extraction, verification |

## What's Missing (the gap)

### Gap 1: No per-student section splitting for multi-student documents

A report card PDF contains sections for 40 students. The current code finds all
student names but doesn't split the document into per-student sections. When
it processes chunks for "Miro," it searches for chunks containing "Miro" — but
report cards often have the student's name only in a header, with the actual
grades/comments in a table or paragraph below that doesn't repeat the name.

**Fix**: After matching students, use a section-splitting strategy:
- Find each student's name position in the document
- Assign text between one student's name and the next to that student
- For single-student documents, all text is relevant

### Gap 2: No sentence-level academic content routing

The current heuristic extractors only catch keywords (CEFR levels, grade
descriptors, IB attributes). A sentence like "Demonstrates strong oral
participation but struggles to organize written responses independently"
contains rich data for:
- `communication_and_language` — "strong oral participation"
- `executive_functioning` — "struggles to organize written responses"
- `academic_strengths` — "oral participation"

**Fix**: Use the local LLM to classify each sentence into the appropriate
lens field(s). The LLM prompt must:
- Take ONE sentence at a time (not bulk text)
- Output the field_id + the relevant phrase (not the whole sentence)
- Output "none" if the sentence has no relevant content
- NEVER invent content — only extract what's there

### Gap 3: No deduplication/synthesis repass

After inserting data from a report card, a student's lens may have:
- "strong oral participation" (from sentence A)
- "participates actively in class discussions" (from sentence B)
These say the same thing. The lens needs a synthesis pass.

**Fix**: After all fields are populated for a student, run one final LLM pass
that reads the full lens and produces a condensed version. Rules:
- Remove duplicates
- Combine similar observations into one
- NEVER add new information not in the originals
- Preserve specific details (CEFR levels, grade descriptors)

## Implementation Plan

### Step 1: Section splitting (`_split_into_student_sections`)

```python
def _split_into_student_sections(
    text: str,
    matched_students: list[dict],
) -> dict[str, str]:
    """Split a multi-student document into per-student text sections.

    Strategy: find each student name's position, assign text from that
    position to the next student's name position. Students not found
    get empty string (no data to import).
    """
```

### Step 2: LLM sentence classifier (`_classify_sentence_to_field`)

```python
async def _classify_sentence_to_field(
    sentence: str,
    engine: ReasoningEngine,
) -> list[dict]:
    """Classify one sentence into lens field(s) using local LLM.

    Returns: [{"field_id": "...", "extracted_phrase": "...", "confidence": 0.x}]
    or [] if sentence has no relevant content.

    The prompt constrains output to ONLY the 10 valid field IDs.
    The extracted_phrase must be a substring of the input sentence.
    """
```

### Step 3: Integrate into `extract_for_lens_update`

Replace the current per-chunk loop with:
1. Split document into student sections (Step 1)
2. For each student's section:
   a. Split into sentences
   b. Run heuristics first (CEFR, grades — keep these, they work)
   c. For remaining sentences, use LLM classifier (Step 2)
   d. Collect all ExtractedField results
3. Safety checks (RED content, trauma_flag)

### Step 4: Synthesis repass (`_synthesize_lens`)

```python
async def _synthesize_lens(
    student_id: str,
    fields: list[ExtractedField],
    engine: ReasoningEngine,
) -> list[ExtractedField]:
    """Final repass: deduplicate and synthesize lens fields.

    Groups fields by field_id, asks LLM to produce one clean summary
    per field. Rules: no new information, preserve specifics.
    """
```

### Step 5: End-to-end test

- Upload a multi-student report card
- Verify: correct student-to-section mapping
- Verify: sentence content reaches correct lens fields
- Verify: NO cross-student contamination
- Verify: synthesis pass removes duplicates
- Verify: safeguarding content is blocked

## Prompt Design (Critical)

### Sentence classifier prompt

```
You are classifying a sentence from a student report card.
Student name: {student_name}

Classify this sentence into ONE of these categories:
- learning_and_cognition: academic performance, learning style, cognitive needs
- communication_and_language: reading, writing, speaking, listening skills
- executive_functioning: organization, focus, planning, task completion
- social_skills: collaboration, peer interaction, teamwork
- emotional_regulation: emotional awareness, coping, resilience
- physical_sensory_needs: motor skills, sensory processing
- attendance_and_engagement: participation, attendance, class engagement
- strategies_trialed: interventions, accommodations being used
- academic_strengths: specific subjects or areas of excellence
- personal_strengths: character traits, interests, talents
- none: sentence has no relevant student assessment content

Sentence: "{sentence}"

Respond with ONLY a JSON object:
{"field_id": "...", "phrase": "the exact words from the sentence that matter"}

If the sentence has no relevant content, respond: {"field_id": "none"}
```

### Synthesis prompt

```
You are condensing a student's profile field. Remove duplicates and combine
similar observations. NEVER add information that isn't in the originals.
Preserve specific data (CEFR levels, grade descriptors, test scores).

Field: {field_name}
Current entries:
{entries}

Write ONE condensed summary (2-3 sentences max). Use only information
from the entries above.
```

## Safety Rules

1. **Section isolation**: Each student's data comes ONLY from their section
2. **Substring check**: After LLM classification, verify the "phrase" is
   actually a substring of the source sentence
3. **Cross-contamination guard**: Before writing to a lens, verify the
   student_id matches the section that produced the data
4. **Confidence thresholds**: LLM-classified fields get `status: "needs_confirmation"`
   unless confidence >= 0.85
5. **RED content**: Safeguarding signals → restricted log, never lens

## Files to Modify

| File | Change |
|------|--------|
| `src/lingua_viva/docpipe/lens_extract.py` | Add section splitting, LLM classifier, synthesis |
| `src/lingua_viva/docpipe/lens_match.py` | Minor: also scan full text for names (not just header) |
| `src/lingua_viva/routers/document_import.py` | Pass ReasoningEngine to extraction |
| `static/index.html` | Ensure Students view "Update lenses from documents" works |

## Success Criteria

1. Upload one multi-student report card → all mentioned students' lenses updated
2. Each student's lens contains ONLY information from their section
3. No cross-student contamination (verified by test)
4. Synthesis pass produces clean, non-duplicated lens entries
5. Teacher can review and confirm before final write

---

## Triple Lens Review

### Claudia Canu Lens
- Does the extraction use teacher language, not developer language?
- Are the 10 profile fields the ones a teacher actually thinks about?
- Is the synthesis output warm and useful, not clinical?
- Will the teacher trust this enough to not have to re-read every report card?

### UX Lens
- Is the flow clear: upload → preview per student → confirm → done?
- Does the preview show what will change in each student's lens?
- Is there a way to reject/edit individual extractions before confirming?
- Does the app explain what it did in plain language?

### Principal Engineer Lens (Mission Canvas)
- Is section splitting robust for edge cases (single-student docs, PDFs with tables)?
- Is the LLM prompt constrained enough to prevent hallucination?
- Is the substring verification actually enforced?
- What happens when the local model is too weak? Is the fallback clean?
- Are there enough tests to catch cross-contamination regressions?
