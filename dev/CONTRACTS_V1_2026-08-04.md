# Lingua Viva Document Pipeline Contracts v1
**Status:** FROZEN 2026-08-04 for T1-T7 parallel implementation.

## 0. Hard Rules

1. **All model calls are LOCAL.** No external LLM is allowed in the document pipeline. The only model seam is `ModelClient`, so a governed external client can be swapped in later without changing pipeline call sites.
2. **No field is written without evidence.** Ungrounded output is a bug. Any non-empty lens field MUST carry at least one evidence item.
3. **The vault module is the ONLY writer of disk state.** Drive, extraction, lens, grounding, UI, and jobs code return data structures and call vault to persist.
4. **Vault root comes from `LV_STATE_HOME`/`~/.lingua-viva`.** The canonical vault path is never bundle-relative or repo-relative.

## 1. Vault Layout

Canonical root:

```text
${LV_STATE_HOME:-~/.lingua-viva}/vault/
  manifest.json
  sources/<source_id>/
    original.<ext>
    source.json
  extracted/<source_id>.json
  lenses/<student_id>/
    lens.json
    observations/OBS-<ulid>.json
  sync/queue.json
```

No defect was found in the starting layout, so v1 keeps it unchanged.

### `manifest.json`

Index of every vault object and sync state.

Required top-level fields:

- `schema_version`: `"docpipe.v1"`
- `vault_id`: stable local vault identifier.
- `created_at`, `updated_at`: ISO-8601 UTC timestamps.
- `sources`: object keyed by `source_id`.
- `extractions`: object keyed by `source_id`.
- `lenses`: object keyed by `student_id`.
- `sync`: object with `queue_path` and `pending_count`.

### `sources/<source_id>/source.json`

Provenance for the byte-identical original file.

Required fields:

- `schema_version`: `"docpipe.source.v1"`
- `source_id`: stable ID, recommended `SRC-<ulid>`.
- `origin`: one of `drive`, `local`.
- `drive_file_id`: string or null.
- `path`: original local path or Drive display path.
- `sha256`: SHA-256 of `original.<ext>`.
- `imported_at`: ISO-8601 UTC timestamp.
- `mime`: MIME type.
- `owner`: teacher/user/machine label available at import time.
- `original_filename`: original basename.
- `original_ext`: extension including dot, lower-case when known.
- `byte_size`: original byte length.

## 2. Extraction Schema

Path: `extracted/<source_id>.json`

Required top-level fields:

- `schema_version`: `"docpipe.extraction.v1"`
- `source_id`
- `source_sha256`
- `extracted_at`
- `extractor`: `{name, version, model}`
- `mime`
- `language`
- `normalized_text`
- `spans`
- `structure`
- `warnings`

The `normalized_text` field is the full addressable text. Every grounding offset in downstream work refers to this string.

Each item in `spans` MUST be:

```json
{
  "span_id": "SPN-0001",
  "char_start": 0,
  "char_end": 148,
  "text": "..."
}
```

Rules:

- `char_start` is inclusive; `char_end` is exclusive.
- `0 <= char_start < char_end <= len(normalized_text)`.
- `text == normalized_text[char_start:char_end]`.
- `span_id` is unique within the extraction.
- Spans may be sentence, paragraph, table-cell, rubric-row, or section sized. They must be small enough for teacher-readable evidence.

`structure` is normalized document structure:

- `title`: string or null.
- `document_type`: one of `lesson_plan`, `student_work_sample`, `rubric`, `report`, `roster`, `unknown`.
- `sections`: array of `{section_id, heading, span_ids}`.
- `students_detected`: array of `{student_id, display_name, confidence, span_ids}`.
- `curriculum`: optional object for grade/unit/lesson metadata when present.

## 3. Lens Schema

Path: `lenses/<student_id>/lens.json`

The lens is the one student lens format for the document pipeline. It must bridge to the existing `StudentLensStore`; no competing student profile format is allowed.

Required top-level fields:

- `schema_version`: `"docpipe.lens.v1"`
- `student_id`
- `display_name`
- `created_at`
- `updated_at`
- `profile`
- `metadata`

### Christi's 10 Profile Categories

The `profile` object contains exactly these first-class fields. IDs reuse the existing `support_category` enum where it overlaps.

| Field ID | Label | ID rule |
|---|---|---|
| `learning_and_cognition` | Learning and Cognition | existing `support_category` |
| `communication_and_language` | Communication and Language | existing `support_category` |
| `executive_functioning` | Executive Functioning | existing `support_category` |
| `social_skills` | Social Skills | existing `support_category` |
| `emotional_regulation` | Emotional Regulation | existing `support_category` |
| `physical_sensory_needs` | Physical/Sensory Needs | existing `support_category` |
| `attendance_and_engagement` | Attendance and Engagement | existing `support_category` |
| `strategies_trialed` | Strategies trialed - successful or not | v1 field because existing enum models strategy outcome separately |
| `academic_strengths` | Academic Strengths | v1 top-level strength kind |
| `personal_strengths` | Personal Strengths | v1 top-level strength kind |

The existing `advanced_enrichment` support category is intentionally not a first-class v1 field because Christi's frozen list has 10 fields and does not include it. Implementations may preserve imported `advanced_enrichment` evidence in metadata or future extensions, but must not add an eleventh profile field.

Each profile field is an object:

```json
{
  "value": "Teacher-readable statement or structured value",
  "evidence": [
    {
      "source_ref": {
        "type": "DOCUMENT",
        "source_id": "SRC-...",
        "path": "sources/SRC-.../source.json"
      },
      "span_id": "SPN-0003",
      "confidence": 0.84,
      "added_at": "2026-08-04T08:00:00Z",
      "added_by": "teacher:federica"
    }
  ]
}
```

Rules:

- Empty field: `value` is `null`, `""`, `[]`, or `{}`, and `evidence` MUST be `[]`.
- Populated field: `value` is non-empty and `evidence` MUST contain at least one item.
- `source_ref.type` is either `DOCUMENT` or `OBSERVATION`.
- DOCUMENT evidence MUST include `source_id`; it MUST include either `span_id` on the evidence item or a document-level reason in future extensions.
- OBSERVATION evidence MUST include `obs_id`; observations are separate files and are never inlined into `lens.json`.
- `confidence` is a number from 0.0 to 1.0.

### Observation Files

Path: `lenses/<student_id>/observations/OBS-<ulid>.json`

Observation files are append-only records created from teacher dictation or typed feedback. They are referenced by lens evidence and never inlined into the lens.

Required fields:

- `schema_version`: `"docpipe.observation.v1"`
- `obs_id`
- `student_id`
- `created_at`
- `created_by`
- `raw_transcript`
- `teacher_edited_text`
- `claims`

Each `claims[]` item has `{field_id, value, confidence}` and is promoted into `lens.json` only through `lens.merge_observation`.

## 4. Module Interfaces

All modules live in `src/lingua_viva/docpipe/`.

### `model.py`

```python
class ModelClient(Protocol):
    async def complete(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        context: dict | None = None,
        max_tokens: int = 2000,
    ) -> ModelResult: ...

class LocalModelClient:
    async def complete(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        context: dict | None = None,
        max_tokens: int = 2000,
    ) -> ModelResult: ...
```

`LocalModelClient` wraps the existing `src.lingua_viva.reasoning.ReasoningEngine` and `config.detect_model`; it must not spawn a second Ollama client.

### `drive.py`

```python
def list_folder(folder_ref: str, *, recursive: bool = False) -> list[DriveItem]: ...
def fetch_file(file_ref: str) -> SourceBytes: ...
def push_file(local_path: Path, destination_ref: str, *, mime: str | None = None) -> DriveWriteResult: ...
```

### `vault.py`

```python
def vault_root() -> Path: ...
def put_source(source: SourceRecord, content: bytes, *, root: Path | None = None) -> SourceRecord: ...
def get_source(source_id: str, *, root: Path | None = None) -> SourceRecord: ...
def put_extraction(extraction: ExtractionRecord, *, root: Path | None = None) -> ExtractionRecord: ...
def get_extraction(source_id: str, *, root: Path | None = None) -> ExtractionRecord: ...
def get_lens(student_id: str, *, root: Path | None = None) -> LensRecord: ...
def put_lens(lens: LensRecord, *, root: Path | None = None) -> LensRecord: ...
def manifest(*, root: Path | None = None) -> ManifestRecord: ...
```

### `extract.py`

```python
async def extract_document(
    source: SourceRecord,
    content: bytes,
    *,
    model_client: ModelClient | None = None,
) -> ExtractionRecord: ...
```

### `lens.py`

```python
def create_from_extraction(
    extraction: ExtractionRecord,
    *,
    student_id: str,
    student_name: str,
    added_by: str,
) -> LensRecord: ...

def merge_observation(
    lens: LensRecord,
    observation: ObservationRecord,
    *,
    added_by: str,
) -> LensRecord: ...
```

### `grounding.py`

```python
def verify(
    lens: LensRecord,
    *,
    manifest: ManifestRecord | None = None,
) -> GroundingReport: ...
```

## 5. Compatibility Notes

- Day-one Drive write-back may degrade to a local `sync/queue.json` entry if offline.
- Ask/Perplexity is outside this contract and must not use these student-data interfaces for external calls.
- The validator CLI is authoritative for fixture/schema compatibility: `python -m src.lingua_viva.docpipe.validate <path>`.
