# SPEC: Phase 6 — Trust UI + Final Gate

**Date**: 2026-07-18
**Status**: READY TO BUILD
**Repo**: `/home/mical/learning-architecture`
**Branch**: `LINGUA-VIVA-UPDATE`
**Depends on**: Phases 1-5 complete
**Author**: kiro.design

---

## 0. What This Phase Delivers

The final phase. Everything the teacher needs to TRUST the system — visible, inspectable, one click away.

Lingua Viva already does the right thing silently: reasoning stays local, student data never leaves, the .docx is never modified, privacy patterns block sensitive content. But the teacher can't SEE that it's working. Phase 6 makes the trust machinery visible:

1. **Why viewer** — "Why did you answer that way?" Full reasoning trace for every response.
2. **Privacy log viewer** — "What stayed local?" Every query that was processed, confirming nothing left.
3. **Data transparency viewer** — "What do you know about me?" Full lens/profile display with edit/delete.

These already work in the backend (Doctor runs diagnostics, privacy.py blocks student data, reasoning.py logs traces). Phase 6 surfaces them in the UI.

---

## 1. What Already Exists (Verified Jul 18)

| Component | Backend | UI |
|---|---|---|
| Reasoning traces | `src/lingua_viva/reasoning.py` logs model, duration, tokens | ❌ No viewer |
| Privacy enforcement | `src/lingua_viva/privacy.py` blocks student names/data | ❌ No log visible to teacher |
| Doctor health | `doctor/support_loop/doctor.py` full diagnostics | ✅ Health view shows summary |
| Student lens store | `src/education/student_lens.py` full CRUD | ✅ Students view shows lens |
| File map | `src/lingua_viva/filemap.py` (Phase 5) | ✅ Settings section |
| Curriculum service | `src/lingua_viva/curriculum.py` read-only | ✅ Plan view |
| Observation history | `src/education/observation_capture.py` | ✅ Observe view |

**What's missing:**
- No API to fetch reasoning trace history
- No API to fetch privacy/routing log
- No API to manage teacher profile/preferences (beyond lens)
- No UI for "Why did you answer that way?"
- No UI for "prove nothing left the machine"
- No UI for "what does the system know about my teaching?"

---

## 2. Architecture

```
┌────────────────────────────────────────────────────────────┐
│                    Teacher Interface                        │
│                                                            │
│  ┌── Why ──────────────────────────────────────────────┐  │
│  │  Last 5 queries with full trace:                    │  │
│  │  - Classification: curriculum/G3                    │  │
│  │  - Route: local (Ollama qwen2.5:7b)                │  │
│  │  - Source: Manuale §4.2 + KL entries               │  │
│  │  - Duration: 2.3s                                   │  │
│  │  - Privacy: 0 blocked, 0 student data detected     │  │
│  │  - External calls: NONE                             │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                            │
│  ┌── Privacy Log ──────────────────────────────────────┐  │
│  │  All queries processed locally: 47                  │  │
│  │  Student data blocked: 3 instances                  │  │
│  │  External calls: 0 (ever)                           │  │
│  │  .docx modifications: 0 (ever)                      │  │
│  │                                                     │  │
│  │  Recent privacy events:                             │  │
│  │  • 10:32 — blocked student name "Marco" from output │  │
│  │  • 09:15 — observation saved locally only           │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                            │
│  ┌── Profile ──────────────────────────────────────────┐  │
│  │  Teaching profile:                                  │  │
│  │  - Role: Teacher                                    │  │
│  │  - Grades: G3, G5                                   │  │
│  │  - Schedule: configured (5 days)                    │  │
│  │  - Observations this month: 23                      │  │
│  │  - File map: 2 roots, 46 dirs                       │  │
│  │                                                     │  │
│  │  [Clear all data]  [Export profile]                 │  │
│  └─────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────┘
```

---

## 3. Build Steps

### 3.1 Reasoning Trace Store

Before we can show "why", we need to store traces. Create a lightweight append-only trace log.

**New file:** `src/lingua_viva/traces.py`

```python
"""
Reasoning trace store — append-only NDJSON log of every reasoning call.

Stores: timestamp, query_hash (never raw query), classification_domain,
model_used, duration_ms, token_count, source_citations, privacy_events,
external_calls (always 0 for LV).

Location: ~/.lingua-viva/traces.ndjson
"""

@dataclass
class ReasoningTrace:
    trace_id: str                  # UUID
    timestamp: str                 # ISO 8601
    query_hash: str                # SHA256 of query (never raw text)
    classification_domain: str     # e.g. "curriculum", "assessment"
    model_used: str                # e.g. "ollama/qwen2.5:7b"
    duration_ms: int
    token_count: int
    source_citations: list[str]    # e.g. ["Manuale §4.2", "KL-CUR-003"]
    privacy_events: list[str]      # e.g. ["blocked_student_name"]
    external_calls: int            # Always 0 for LV (local-only)
    route: str                     # Always "local" for LV

def append_trace(trace: ReasoningTrace) -> None: ...
def read_traces(limit: int = 20) -> list[ReasoningTrace]: ...
def get_trace(trace_id: str) -> Optional[ReasoningTrace]: ...
```

Wire into `src/lingua_viva/reasoning.py`: after every reasoning call, append a trace.

**Tests:** `tests/test_reasoning_traces.py`
- test_trace_appended_after_reasoning
- test_trace_never_contains_raw_query
- test_read_traces_returns_most_recent_first
- test_get_trace_by_id

---

### 3.2 Privacy Event Log

Track privacy enforcement events so teachers can see "the system blocked student data 3 times today."

**New file:** `src/lingua_viva/privacy_log.py`

```python
"""
Privacy event log — records when privacy enforcement fires.

Events: student_name_blocked, student_data_blocked, observation_saved_locally,
query_processed_locally, ai_attribution_stripped.

Location: ~/.lingua-viva/privacy_events.ndjson
"""

@dataclass
class PrivacyEvent:
    timestamp: str
    event_type: str          # student_name_blocked, query_processed_locally, etc.
    detail: str              # "Blocked 'Marco' from parent recommendation output"
    query_hash: str          # Reference to trace (never raw query)

def log_privacy_event(event: PrivacyEvent) -> None: ...
def read_privacy_events(limit: int = 50) -> list[PrivacyEvent]: ...
def privacy_summary() -> dict: ...
    # Returns: { total_queries_local: N, student_blocks: N, external_calls: 0, docx_modifications: 0 }
```

Wire into `src/lingua_viva/privacy.py`: when student data is blocked, log an event.
Wire into `src/web.py`: when parent recommendation strips AI attribution, log an event.

**Tests:** `tests/test_privacy_log.py`
- test_privacy_event_logged_on_student_block
- test_privacy_summary_counts
- test_privacy_log_never_contains_student_names
- test_external_calls_always_zero

---

### 3.3 Trust API Endpoints

Add to `src/web.py`:

```
GET /api/why                    → last N traces (default 5)
GET /api/why?trace_id=<id>      → single trace detail
GET /api/privacy                → privacy summary + recent events
GET /api/profile                → teacher profile aggregation
POST /api/profile/clear         → clear all local data (with confirmation)
```

**Privacy rules:**
- `/api/why` NEVER returns raw query text. Only query_hash, domain, model, duration.
- `/api/privacy` NEVER returns student names in event details. Only event type + generic detail.
- `/api/profile/clear` requires `{"confirm": "clear-all-data"}` in body.

**Tests:** `tests/test_trust_api.py`
- test_why_returns_traces_without_raw_query
- test_why_single_trace_by_id
- test_privacy_returns_summary
- test_privacy_events_no_student_names
- test_profile_returns_aggregation
- test_profile_clear_requires_confirmation
- test_profile_clear_without_confirmation_rejected

---

### 3.4 Why Viewer

Update the utility bar's existing Why/trace view in `static/index.html`.

Replace any placeholder with a real trace viewer:

```
┌─────────────────────────────────────────────────────────────┐
│  Why — Last 5 Reasoning Traces                              │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  10:32 AM · curriculum · qwen2.5:7b · 2.3s         │   │
│  │  Sources: Manuale §4.2, KL-CUR-003                  │   │
│  │  Privacy: 0 events · External: none                  │   │
│  │  ▼ expand                                           │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  10:28 AM · assessment · qwen2.5:7b · 1.8s         │   │
│  │  Sources: CEFR A1 checklist                          │   │
│  │  Privacy: 1 student name blocked · External: none    │   │
│  │  ▼ expand                                           │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ℹ️ Every query is processed locally on your machine.       │
│  No query text is stored — only classification and timing.  │
└─────────────────────────────────────────────────────────────┘
```

**Expand detail shows:**
- Domain classification
- Model used + tokens
- Duration
- Source citations
- Privacy events (if any)
- Route confirmation: "Processed locally. No external calls."

---

### 3.5 Privacy Log Viewer

Add to the existing Privacy view in `static/index.html`. Currently it's static text confirming "all local." Replace with live data:

```
┌─────────────────────────────────────────────────────────────┐
│  Privacy — Data Protection Log                              │
│                                                             │
│  ┌─── Summary ─────────────────────────────────────────┐   │
│  │  Total queries processed locally: 47                 │   │
│  │  Student data blocked: 3 instances                   │   │
│  │  AI attribution stripped: 5 parent messages          │   │
│  │  External API calls: 0 (always)                      │   │
│  │  .docx modifications: 0 (always)                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Recent privacy events:                                     │
│  • Jul 17 10:32 — student data blocked in output            │
│  • Jul 17 09:15 — observation saved locally                 │
│  • Jul 16 15:40 — AI attribution stripped from parent msg   │
│                                                             │
│  ✓ No student names appear in any log or output.            │
│  ✓ No data has ever left this machine.                      │
│  ✓ The .docx has never been modified by this app.           │
└─────────────────────────────────────────────────────────────┘
```

---

### 3.6 Teacher Profile Viewer

Add to Settings view (or make it its own utility item). Shows what the system knows about this teacher:

```
┌─────────────────────────────────────────────────────────────┐
│  Your Teaching Profile                                       │
│                                                             │
│  Role: Teacher                                              │
│  Schedule: 5 days configured                                │
│  Grades taught: G3, G5                                      │
│  Observations this month: 23                                │
│  Students tracked: 18                                       │
│  Reflections: 7                                             │
│  File map: 2 roots, 46 directories                          │
│  Reasoning traces: 47 queries                               │
│                                                             │
│  All data is stored at: ~/.lingua-viva/                      │
│  Nothing is uploaded. Nothing is shared.                     │
│                                                             │
│  [Clear All Data]                                           │
│  ⚠️ This permanently deletes all local data including        │
│  observations, traces, privacy log, and file map.           │
│  The .docx and curriculum/ files are not affected.           │
└─────────────────────────────────────────────────────────────┘
```

"Clear All Data" calls `POST /api/profile/clear` with confirmation.

---

### 3.7 Enhanced Response Metadata

When the Ask view receives a response from `/api/query`, show trust metadata inline:

```
┌─────────────────────────────────────────────────────────────┐
│  [Response text here...]                                    │
│                                                             │
│  ───────────────────────────────────────────────────────── │
│  🔒 local · qwen2.5:7b · 2.3s · Manuale §4.2              │
│  [Why?]                                                     │
└─────────────────────────────────────────────────────────────┘
```

The metadata line shows: route (always "local"), model, duration, primary source.
Clicking [Why?] switches to the Why view filtered to that trace.

Wire: the `/api/query` SSE response should include `trace_id`, `model_used`, `duration_ms`, `source_citation`, `route` in its final event.

---

### 3.8 Observe View Trust Indicator

When an observation is captured, show a brief confirmation:

```
✓ Saved locally. Not uploaded. Not shared.
  Tagged to: [student] · Domain: observation
```

This reinforces trust every time the teacher uses the most sensitive feature (observations contain student identifiers).

---

## 4. File Changes Summary

| File | Change |
|------|--------|
| `src/lingua_viva/traces.py` | NEW — reasoning trace store |
| `src/lingua_viva/privacy_log.py` | NEW — privacy event log |
| `src/lingua_viva/reasoning.py` | MODIFY — append trace after every call |
| `src/lingua_viva/privacy.py` | MODIFY — log events on student data blocks |
| `src/web.py` | MODIFY — add /api/why, /api/privacy, /api/profile, /api/profile/clear; add trace metadata to /api/query response |
| `static/index.html` | MODIFY — Why viewer, Privacy log viewer, Profile viewer, response metadata, observe confirmation |
| `tests/test_reasoning_traces.py` | NEW |
| `tests/test_privacy_log.py` | NEW |
| `tests/test_trust_api.py` | NEW |

---

## 5. Privacy Invariants (Non-Negotiable)

| Rule | Verification |
|---|---|
| No raw query text in traces | `ReasoningTrace.query_hash` is SHA256, test asserts no plain text |
| No student names in privacy log | Events use generic descriptions, test asserts no names |
| No student names in API responses | `/api/why` and `/api/privacy` tested for absence |
| Profile clear requires confirmation | `POST /api/profile/clear` without `{"confirm": "clear-all-data"}` returns 400 |
| External calls always 0 | Every trace has `external_calls: 0`, test asserts |
| .docx never modified | `git status` check in every hardening iteration |
| Traces stored mode 600 | `~/.lingua-viva/traces.ndjson` permissions verified |

---

## 6. Test Plan

| # | Test | Pass Criteria |
|---|---|---|
| 1 | Trace appended after reasoning | traces.ndjson grows by 1 entry |
| 2 | Trace never has raw query | No entry contains the original query text |
| 3 | Trace has required fields | trace_id, timestamp, domain, model, duration all present |
| 4 | Read traces returns recent first | Most recent timestamp first |
| 5 | Get trace by ID | Returns correct trace |
| 6 | Privacy event logged on block | Event appears after student name blocked |
| 7 | Privacy summary counts correctly | total, student_blocks, external_calls=0 |
| 8 | Privacy log has no student names | No name strings in event details |
| 9 | GET /api/why returns traces | JSON array with trace objects |
| 10 | GET /api/why no raw query | Response body grep for test query returns empty |
| 11 | GET /api/why?trace_id=X | Single trace returned |
| 12 | GET /api/privacy returns summary | Contains total_queries_local, student_blocks |
| 13 | GET /api/privacy events list | Recent events present |
| 14 | GET /api/profile aggregates | Shows role, schedule, observations, file map |
| 15 | POST /api/profile/clear with confirm | Returns 200, data cleared |
| 16 | POST /api/profile/clear without confirm | Returns 400 |
| 17 | /api/query response includes trace_id | SSE done event has trace metadata |
| 18 | /api/query response includes route | Always "local" |
| 19 | Why viewer renders traces | HTML contains trace elements |
| 20 | Privacy viewer renders summary | HTML contains privacy stats |
| 21 | Profile viewer renders aggregation | HTML contains role, observations |
| 22 | Observe confirmation shown | After capture, trust message appears |
| 23 | All existing tests still pass | 332+ green |
| 24 | Doctor still WARN not worse | Doctor status unchanged |
| 25 | .docx untouched | git status empty |

---

## 7. Hardening Gate — FINAL (Gate 3)

**This is the last gate before the app can be considered shippable.**

After all 8 steps pass individually, run 15 consecutive iterations of the complete teacher demo:

```bash
for i in $(seq 1 15); do
  echo "=== FINAL GATE iteration $i ==="
  
  # Start server
  python3 src/web.py &
  SERVER_PID=$!
  sleep 3
  
  # === THE TEACHER TRUST DEMO ===
  
  # 1. Ask a curriculum question
  RESPONSE=$(curl -s -X POST http://127.0.0.1:8787/api/query \
    -H 'Content-Type: application/json' \
    -d '{"query": "What CEFR targets for Grade 3 La Famiglia?"}')
  echo "$RESPONSE" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d.get('route')=='local'; assert 'trace_id' in d"
  
  # 2. Verify trace was stored
  TRACE_ID=$(echo "$RESPONSE" | python3 -c "import json,sys; print(json.load(sys.stdin)['trace_id'])")
  curl -s "http://127.0.0.1:8787/api/why?trace_id=$TRACE_ID" | \
    python3 -c "import json,sys; d=json.load(sys.stdin); assert d['route']=='local'; assert d['external_calls']==0"
  
  # 3. Verify no raw query in trace
  curl -s "http://127.0.0.1:8787/api/why" | \
    python3 -c "import json,sys; d=json.load(sys.stdin); assert 'CEFR targets' not in json.dumps(d)"
  
  # 4. Test privacy enforcement (try to get student name in output)
  curl -s -X POST http://127.0.0.1:8787/api/parents/recommendation \
    -H 'Content-Type: application/json' \
    -d '{"student_id": "student-1", "context": "needs quiet workspace"}' | \
    python3 -c "import json,sys; d=json.load(sys.stdin); assert 'AI' not in d.get('body','')"
  
  # 5. Check privacy log shows enforcement
  curl -s http://127.0.0.1:8787/api/privacy | \
    python3 -c "import json,sys; d=json.load(sys.stdin); assert d['external_calls']==0; assert d['docx_modifications']==0"
  
  # 6. Verify profile aggregation
  curl -s http://127.0.0.1:8787/api/profile | \
    python3 -c "import json,sys; d=json.load(sys.stdin); assert 'role' in d; assert 'reasoning_traces' in d"
  
  # 7. Verify .docx untouched
  git status --short -- Manuale_Italiano_Laboratorio_Linguistico_G1-G5.docx | \
    python3 -c "import sys; assert sys.stdin.read().strip() == ''"
  
  # 8. Verify no MC/SIR branding
  curl -s http://127.0.0.1:8787/ | python3 -c "
import sys
page = sys.stdin.read()
assert 'Mission Canvas' not in page
assert 'Still I Rise' not in page
assert 'MC_' not in page
"
  
  # 9. Home view renders
  curl -s http://127.0.0.1:8787/ | grep -q "Good morning\|Set up your schedule\|Home"
  
  # 10. Health endpoint works
  curl -s http://127.0.0.1:8787/api/health | \
    python3 -c "import json,sys; d=json.load(sys.stdin); assert d['status'] in ('OK','WARN')"
  
  # Kill server, verify cleanup
  kill $SERVER_PID 2>/dev/null; wait $SERVER_PID 2>/dev/null
  sleep 1
  ! lsof -i :8787 -t >/dev/null 2>&1
  
  echo "Iteration $i PASSED"
done

# Final validation
python3 -m pytest tests/ -q                          # All pass
python3 -m pytest doctor/support_loop/tests/ -q      # 15 pass
python3 -m doctor.support_loop doctor                # WARN or OK
python3 doctor/lv_artifact_gauntlet.py               # PASS
rg "Mission Canvas|Still I Rise|MC_|mc\." static/ src/lingua_viva/ tests/  # 0 hits
git status --short -- Manuale_Italiano_Laboratorio_Linguistico_G1-G5.docx  # empty
```

**What this catches:**
- Trust metadata missing from responses (trace_id, route, model)
- Raw query text leaking into traces or API responses
- Student names leaking into privacy log
- External calls counter being non-zero (should be impossible for LV)
- .docx being modified by any operation
- MC/SIR branding remaining anywhere
- Privacy viewer showing incorrect data
- Profile clear not working or not requiring confirmation
- Server leaving orphaned processes

**Pass criteria:** 15 consecutive iterations. Zero privacy leaks. Zero external calls. Zero .docx modifications. Zero branding violations. The teacher can see WHY the system answered, WHAT stayed local, and WHAT the system knows about them — and can delete everything with one button.

---

## 8. What NOT To Build

| Feature | Why not |
|---|---|
| Query history (showing actual queries) | Privacy. We store hashes, never text. |
| Exportable trace logs | Future. For now, traces are internal transparency only. |
| Per-student privacy reports | Too complex. Summary counts are sufficient for trust. |
| External call toggle | LV is ALWAYS local. There's no toggle because there's no option. |
| Admin audit trail | Admin tier is separate. Teacher sees their own data only. |
| Undo for profile clear | One-way door. Confirmation dialog is the safety gate. |

---

## 9. Success Criteria

After Phase 6, a teacher can:
1. Ask a question and see **route: local, model: qwen2.5:7b, 2.3s** on every response
2. Click **Why** and see the full reasoning trace (domain, sources, timing, privacy)
3. Open **Privacy** and see: 47 queries local, 0 external, 0 .docx modifications, 3 student blocks
4. Open **Profile** and see everything the system knows — role, schedule, observations, file map
5. Click **Clear All Data** and confirm it's gone
6. See **"✓ Saved locally"** every time they capture an observation
7. See **zero AI attribution** on every parent recommendation
8. Know, with evidence, that nothing left their machine

**The trust promise:** Lingua Viva doesn't ask teachers to believe it's private. It SHOWS them. Every query, every trace, every privacy event is visible. The app is a glass box.
