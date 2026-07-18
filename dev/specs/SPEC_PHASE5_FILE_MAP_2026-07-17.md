# SPEC: Phase 5 — Curriculum File Map

**Date**: 2026-07-17
**Status**: READY TO BUILD
**Repo**: `/home/mical/learning-architecture`
**Branch**: `LINGUA-VIVA-UPDATE`
**Depends on**: Phase 4 complete (home view + brief endpoint must exist)
**Author**: kiro.design

---

## 0. What This Phase Delivers

Teachers work with physical files: lesson plans, downloaded PDFs, student portfolios, assessment samples, CEFR checklists. These live scattered across their machine. Lingua Viva should know WHERE curriculum-relevant materials live without ever reading their contents — especially sensitive student files.

The file map answers:
1. "Where are my curriculum materials?" → Domain inference from folder names
2. "Which folders have student data?" → Sensitivity inference (these folders get extra protection)
3. "What does the system know about my files?" → Transparent in Settings
4. "Can the AI read my student files?" → No. Never. Only folder names and sizes.

**Design principle:** The file map is a structural awareness layer for the teacher's file system. It learns WHERE things live and WHAT KIND of things they are. It never opens a file. Student data zones are detected and excluded from all processing.

---

## 1. What Already Exists (Verified Jul 17)

| Component | Status | How Phase 5 Uses It |
|---|---|---|
| Doctor privacy.py patterns | Working | Student data detection patterns (names, grades, IEPs) |
| doctor/support_loop/rules/privacy_patterns.yaml | Working | Exclusion patterns for sensitive content |
| src/lingua_viva/privacy.py | Working | Student data privacy enforcement |
| CurriculumService | Working | Knows about curriculum/ — file map extends awareness |
| Brief endpoint | Working (Phase 4) | Will include file map summary |
| Settings view | Working | Will get File Map section |
| Home view | Working (Phase 4) | No direct integration needed |

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Settings View (HTML)                         │
│                                                                 │
│  ┌─── Curriculum File Map ────────────────────────────────────┐ │
│  │                                                             │ │
│  │  Scanned folders:                                           │ │
│  │  ~/Documents/Teaching  ·  34 folders  ·  curriculum, cefr   │ │
│  │  ~/Desktop/Italian     ·  12 folders  ·  curriculum         │ │
│  │                                                             │ │
│  │  Detected:                                                  │ │
│  │  ■ curriculum (18)  ■ assessment (8)  ■ cefr (6)            │ │
│  │                                                             │ │
│  │  ⚠️ Student data zones (excluded from all processing):      │ │
│  │  ~/Documents/Students/ (never scanned, never read)          │ │
│  │                                                             │ │
│  │  [Scan a folder]  [Clear map]                               │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
         │
         │ POST /api/filemap/scan { root_path, max_depth }
         │ GET  /api/filemap
         ▼
┌─────────────────────────────────────────────────────────────────┐
│              src/lingua_viva/filemap.py                          │
│                                                                 │
│  scan_directory(root, max_depth=3)                              │
│  ├── os.walk() — names and sizes only, NEVER file contents      │
│  ├── student_data_zone() check per directory                    │
│  ├── infer_education_domain() from path components              │
│  ├── infer_sensitivity() — student/private → high               │
│  └── skip: symlinks, hidden dirs, .git, node_modules            │
│                                                                 │
│  Storage: ~/.lingua-viva/file_map.yaml (mode 0o600)             │
│                                                                 │
│  Pipeline context:                                              │
│  build_filemap_context(query_domain) → curriculum locations      │
│  (ONLY for local reasoning — NEVER for any external call)       │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Build Steps

### 3.1 Core Scanner (`src/lingua_viva/filemap.py`)

**New file.** Scan a teacher's directory tree. Collect folder structure. Infer education-relevant domains. Detect student data zones.

```python
"""
Curriculum File Map — structural awareness for teacher files.

Scans directory trees to learn WHERE curriculum materials, assessment files,
and reference documents live. NEVER opens files. NEVER reads contents.
Student data zones are detected and EXCLUDED from all processing.

Storage: ~/.lingua-viva/file_map.yaml (mode 0o600)
"""

# ── Education Domain Inference ──────────────────────────────────────

EDUCATION_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "curriculum": ["curriculum", "lesson", "unit", "syllabus", "programme",
                   "indicazioni", "manuale", "piano", "programmazione",
                   "scope", "sequence", "scheme"],
    "assessment": ["assessment", "rubric", "portfolio", "grade", "valutazione",
                   "test", "exam", "evaluation", "checklist", "criteria"],
    "cefr": ["cefr", "a1", "a2", "b1", "b2", "proficiency", "level",
             "can-do", "competenza", "livello"],
    "resources": ["resource", "material", "worksheet", "activity",
                  "risorsa", "scheda", "attività", "template"],
    "reference": ["reference", "research", "article", "framework",
                  "ib", "pyp", "reggio", "montessori"],
    "planning": ["plan", "planning", "weekly", "daily", "schedule",
                 "timetable", "calendar", "orario"],
}

# ── Sensitivity: Student Data Zones ─────────────────────────────────

STUDENT_DATA_KEYWORDS: list[str] = [
    "student", "studente", "alunno", "pupil",
    "iep", "bes", "pdp",  # Italian special needs docs
    "observation", "osservazione",
    "report", "pagella", "scheda-valutazione",
    "parent", "genitore", "famiglia",
    "confidential", "riservato", "private",
    "grade-book", "registro",
]

SENSITIVITY_KEYWORDS: dict[str, list[str]] = {
    "high": STUDENT_DATA_KEYWORDS + [
        "medical", "health", "salute",
        "credential", "password", "secret", "token",
    ],
    "medium": ["draft", "bozza", "internal", "interno", "review"],
}

SKIP_DIRS: set[str] = {
    ".git", ".svn", "node_modules", "__pycache__",
    ".venv", "venv", ".cache", ".tmp", ".Trash",
}
```

**Data structures:**

```python
@dataclass
class FileMapEntry:
    path: str
    file_count: int
    total_size_bytes: int
    last_modified: str  # ISO 8601
    inferred_domain: Optional[str] = None
    sensitivity: str = "low"  # low, medium, high
    depth: int = 0

@dataclass
class ScanRoot:
    path: str
    scanned_at: str
    entry_count: int = 0
    domain_summary: dict[str, int] = field(default_factory=dict)
    student_zones_detected: int = 0

@dataclass
class FileMap:
    roots: list[ScanRoot] = field(default_factory=list)
    entries: list[FileMapEntry] = field(default_factory=list)
    exclusions: list[str] = field(default_factory=list)
    student_zones: list[str] = field(default_factory=list)  # detected, never scanned
    version: int = 1
```

**Key function:**

```python
def is_student_data_zone(dir_path: str) -> bool:
    """Detect folders likely containing student data. These are EXCLUDED entirely."""
    path_lower = dir_path.lower()
    return any(kw in path_lower for kw in STUDENT_DATA_KEYWORDS)
```

**Scanner behavior:**
- When `is_student_data_zone()` returns True: skip the directory, log it in `student_zones`, do NOT create an entry. This is a hard exclusion.
- The .docx file (`Manuale_*.docx`) is never opened by the scanner (it uses stat only).
- `followlinks=False` — no symlink traversal.
- Only calls `os.stat()`, never `open()`, `read()`, `read_text()`.

**Storage:**
- Path: `~/.lingua-viva/file_map.yaml`
- Mode: `0o600` (owner-only)
- Format: YAML with roots, entries, exclusions, student_zones

**Functions to implement:**
- `scan_directory(root, max_depth=3, exclusions=[])` → `list[FileMapEntry]`
- `infer_education_domain(dir_path)` → `Optional[str]`
- `infer_sensitivity(dir_path)` → `"low" | "medium" | "high"`
- `is_student_data_zone(dir_path)` → `bool`
- `run_scan(root_path, max_depth=3)` → `FileMap` (merge + save)
- `load_map()` → `FileMap`
- `save_map(file_map)` → None
- `clear_map()` → None
- `add_exclusion(path)` → `FileMap`
- `build_filemap_context(query_domain)` → `str` (curriculum locations for local reasoning)

---

### 3.2 API Endpoints

Add to `src/web.py`:

```
POST /api/filemap/scan   { root_path, max_depth }  → scan and return summary
GET  /api/filemap        → current map (paths use ~ not absolute home)
POST /api/filemap/exclude { path, action: "add"|"remove" }
POST /api/filemap/clear  → delete entire map
```

**Privacy rules for API responses:**
- Paths always use `~` replacing home directory
- Student zones listed by count only, never by full path
- No file names ever returned (only directories)

---

### 3.3 CLI Integration

Add `filemap` subcommand to `src/lingua_viva/cli.py`:

```
lv filemap show           → display current map
lv filemap scan <path>    → scan a directory
lv filemap exclude <path> → add exclusion
lv filemap clear          → delete map
```

---

### 3.4 Settings UI

Add "Curriculum File Map" section to the Settings view in `static/index.html`:

- Shows scanned roots with domain chip badges
- Shows student data zones detected (with explanation: "these folders are never read")
- "Scan a folder" button → text input → POST /api/filemap/scan
- "Clear map" button → POST /api/filemap/clear
- Exclusion list with remove buttons

---

### 3.5 Brief Integration

Add to the `/api/brief` response (from Phase 4):

```json
{
  "filemap": {
    "configured": true,
    "root_count": 2,
    "total_directories": 46,
    "domains_detected": {"curriculum": 18, "assessment": 8, "cefr": 6},
    "student_zones_excluded": 3
  }
}
```

If no map exists: `"filemap": null`

---

### 3.6 Reasoning Context (Local Only)

When the pipeline reasons about curriculum questions, inject file map awareness:

```python
def build_filemap_context(query_domain: Optional[str]) -> str:
    """
    Build context string from file map for local reasoning.
    
    ONLY for local Ollama calls. NEVER for external models.
    Returns directory locations matching the query domain.
    """
    file_map = load_map()
    if not file_map.entries or not query_domain:
        return ""
    
    matching = [e for e in file_map.entries if e.inferred_domain == query_domain]
    if not matching:
        return ""
    
    lines = [f"Teacher has {len(matching)} {query_domain} folders:"]
    for entry in matching[:5]:
        display = entry.path.replace(str(Path.home()), "~")
        lines.append(f"  - {display} ({entry.file_count} files)")
    return "\n".join(lines)
```

Wire into `src/lingua_viva/reasoning.py` — when reasoning locally, append filemap context if domain matches. This helps the model say "Your curriculum materials are at ~/Documents/Teaching/G3" instead of guessing.

---

## 4. Privacy Gates (Non-Negotiable)

| Rule | Implementation |
|---|---|
| Never read file contents | Scanner uses `os.stat()` only. Test verifies no `open()`/`read()` calls. |
| Student data zones excluded | `is_student_data_zone()` → directory and all children skipped entirely |
| Storage restricted | `file_map.yaml` written mode `0o600` |
| API redacts home path | All responses use `~` not absolute path |
| No external model gets paths | `build_filemap_context()` returns "" for non-local routes |
| No symlink following | `os.walk(followlinks=False)` |
| .docx never opened | Scanner stat-only; .docx is a file not a directory so scanner doesn't touch it |
| Student zone paths not in responses | API shows count of zones, not their paths |

---

## 5. Test Plan

| # | Test | Pass Criteria |
|---|---|---|
| 1 | `scan_directory()` returns entries | Non-empty list for real dir |
| 2 | Depth limit respected | `max_depth=0` → root only |
| 3 | Hidden dirs skipped | `.git` not in results |
| 4 | SKIP_DIRS skipped | `node_modules`, `__pycache__` not in results |
| 5 | Symlinks not followed | Symlink not traversed |
| 6 | Student data zones excluded | `~/Students/` detected and skipped |
| 7 | Student zones logged | Detected zones appear in `file_map.student_zones` |
| 8 | No file content access | Scanner never calls `open()`/`read()` — verify via mock |
| 9 | `infer_education_domain("~/curriculum/G3")` | Returns `"curriculum"` |
| 10 | `infer_education_domain("~/Photos")` | Returns `None` |
| 11 | `infer_sensitivity("~/Students/reports")` | Returns `"high"` |
| 12 | `infer_sensitivity("~/Teaching/resources")` | Returns `"low"` |
| 13 | Italian keywords work | `"programmazione"` → curriculum, `"valutazione"` → assessment |
| 14 | `save_map()` + `load_map()` round-trip | Data survives |
| 15 | File permissions | Mode `0o600` after save |
| 16 | Multi-root scan | Root B preserves root A entries |
| 17 | `add_exclusion()` removes entries | Entries under excluded path gone |
| 18 | `clear_map()` | File deleted, load returns empty |
| 19 | `POST /api/filemap/scan` | Returns 200 with domain summary |
| 20 | `POST /api/filemap/scan` invalid path | Returns 400 |
| 21 | `GET /api/filemap` | Returns map with `~` paths, no absolute home |
| 22 | `GET /api/filemap` returns no student zone paths | Only count, not paths |
| 23 | `POST /api/filemap/exclude` | Adds exclusion |
| 24 | `POST /api/filemap/clear` | Returns 200, map empty |
| 25 | `GET /api/brief` includes filemap | filemap section present when map exists |
| 26 | `GET /api/brief` filemap null when no map | No crash |
| 27 | `build_filemap_context()` curriculum match | Returns context with dirs |
| 28 | `build_filemap_context()` no external paths | Returns "" for non-local |
| 29 | CLI `lv filemap scan` works | Produces output |
| 30 | CLI `lv filemap show` displays map | Shows roots and domains |

**Test file:** `tests/test_filemap.py`

---

## 6. Hardening Gate

After all steps pass individually, run 15 consecutive iterations:

```bash
for i in $(seq 1 15); do
  echo "=== Phase 5 hardening iteration $i ==="
  
  # Create temp tree:
  #   /tmp/lv-test/
  #   ├── curriculum/G3/         (3 files)
  #   ├── assessment/rubrics/    (2 files)
  #   ├── cefr/checklists/       (2 files)
  #   ├── Students/reports/      (should be EXCLUDED — student zone)
  #   ├── .git/                  (should be skipped)
  #   └── node_modules/          (should be skipped)
  
  # Scan
  curl -s -X POST http://127.0.0.1:8787/api/filemap/scan \
    -H 'Content-Type: application/json' \
    -d '{"root_path": "/tmp/lv-test", "max_depth": 3}' | \
    python3 -c "import json,sys; d=json.load(sys.stdin); assert d['total_entries'] > 0; assert 'student_zones_detected' in str(d)"
  
  # Student zone excluded
  curl -s http://127.0.0.1:8787/api/filemap | \
    python3 -c "import json,sys; d=json.load(sys.stdin); assert not any('Students' in e.get('path','') for e in d.get('entries',[]))"
  
  # Paths redacted (no absolute home)
  curl -s http://127.0.0.1:8787/api/filemap | \
    python3 -c "import json,sys,os; d=json.load(sys.stdin); home=os.path.expanduser('~'); assert home not in json.dumps(d)"
  
  # Brief includes filemap
  curl -s http://127.0.0.1:8787/api/brief | \
    python3 -c "import json,sys; d=json.load(sys.stdin); assert d.get('filemap') is not None"
  
  # Clear
  curl -s -X POST http://127.0.0.1:8787/api/filemap/clear | \
    python3 -c "import json,sys; d=json.load(sys.stdin); assert d['status']=='ok'"
  
  # App doesn't crash with empty map
  curl -s http://127.0.0.1:8787/api/brief | \
    python3 -c "import json,sys; d=json.load(sys.stdin); assert d.get('filemap') is None"
  
  echo "Iteration $i passed"
done

# Then:
python3 -m pytest tests/ -q                          # 332+ pass
python3 -m pytest doctor/support_loop/tests/ -q      # 15 pass
python3 -m doctor.support_loop doctor                # WARN or OK
rg "Mission Canvas|Still I Rise|MC_|mc\." static/ src/lingua_viva/ tests/  # 0
git status --short -- Manuale_Italiano_Laboratorio_Linguistico_G1-G5.docx  # empty
```

---

## 7. What NOT To Build

| Feature | Why not |
|---|---|
| File content indexing | Architectural invariant: LV reads names, never contents |
| File browser panel | Teachers use Finder/Explorer. LV just needs to know where things are. |
| Auto re-scan on file change | fs.watch is fragile. Teacher triggers manually. |
| Per-file entries | Map tracks DIRECTORIES not individual files |
| Document ingestion from file map | Separate feature (already exists via /api/upload). Not Phase 5. |
| Student file reading | NEVER. Student data zones are detected and excluded. Period. |
| Automatic curriculum import | The .docx stays authoritative. File map is awareness, not action. |

---

## 8. Success Criteria

- [ ] `lv filemap scan ~/Documents/Teaching` produces a map with education domain tags
- [ ] Student data zones (`~/Students/`, `~/Reports/`) detected and excluded
- [ ] `GET /api/filemap` returns map with `~` paths, student zone count
- [ ] Settings UI shows file map with scan/clear/exclusions
- [ ] `file_map.yaml` has mode 600
- [ ] No file contents ever read
- [ ] Brief includes filemap summary
- [ ] Local reasoning gets curriculum folder awareness
- [ ] Italian keywords work (programmazione → curriculum, valutazione → assessment)
- [ ] All existing tests still pass
- [ ] .docx untouched
