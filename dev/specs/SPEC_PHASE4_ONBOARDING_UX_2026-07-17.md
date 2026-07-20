# SPEC: Lingua Viva Phase 4 — Teacher Home View + Onboarding UX

**Date**: 2026-07-17
**Status**: SHIPPED
**Repo**: `/home/mical/learning-architecture`
**Branch**: `LINGUA-VIVA-UPDATE`
**Depends on**: Phase 1 (Electron shell), Phase 2 (teacher interface), Phase 3 (support bundle)
**Author**: kiro.design

---

## 0. What's Missing

Phases 1-3 built the full teacher sidebar, curriculum service, observation capture, student lens, support bundle, and Electron shell. All pass hardening. But:

1. **No home view** — the app opens directly to Plan. A teacher opening the app at 7:30am should see a summary of what matters today, not a curriculum browser.
2. **No teacher brief** — MC has a morning brief built on action cache. LV equivalent: "what's on today's plan, which students need attention, what observations are due."
3. **Bootstrap is invisible** — `desktop/electron/main.ts` waits for the backend silently. The teacher sees a blank window for 3-5 seconds. Needs a rich progress UI showing Python check, Ollama check, model status, server start.
4. **Role selection is abrupt** — the first-launch role picker (teacher/coordinator) has no context. Needs a 2-sentence welcome before the choice.
5. **No observation reminders** — teachers forget to observe certain students. The system knows who hasn't been observed recently (from student lens data). That signal should surface on the home view.

---

## 1. Architecture

```
No new external dependencies. No new infrastructure patterns.
Everything reads from existing data:

Home view reads:
  - curriculum/lingua_viva_matrix.yaml (today's scheduled units)
  - Student lens database (recent observations, unobserved students)
  - dev/lv_revision_log.ndjson (recent reflections)
  - doctor/support_loop status (system health)

No LLM call needed. No network call. Pure local data aggregation.
```

---

## 2. What Exists (Verified Jul 17)

| Component | Status | How Home Uses It |
|---|---|---|
| CurriculumService | Working | Get today's grade/unit if teacher configures their schedule |
| StudentLensStore | Working | Query unobserved students, recent observations |
| Doctor | Working (WARN) | Health indicator on home |
| Revision log | Working | Last reflection date |
| Electron bootstrap.ts | Working | checkPython, checkOllama, probeHealth, waitForBackend all exist |
| Role selection | Working | localStorage("lvRole") |
| 332 tests | Passing | Safety net |

---

## 3. Build Steps (In Order)

### 3.1 Teacher Schedule Config (Settings + localStorage)

Before a home brief can say "today you teach Grade 3, Unit: La Famiglia", the teacher needs to have told the system their schedule.

Add to Settings view in `static/index.html`:

```
My Schedule:
  Monday:    [Grade 3 ▼] [Unit: La Famiglia ▼]
  Tuesday:   [Grade 1 ▼] [Unit: I Colori ▼]
  Wednesday: [Grade 3 ▼] [Unit: La Famiglia ▼]
  Thursday:  [Grade 5 ▼] [Unit: Il Viaggio ▼]
  Friday:    [Grade 2 ▼] [Unit: Gli Animali ▼]
```

Store in localStorage as `lvSchedule`. Grade/unit options populated from `/api/curriculum/overview`.

Add endpoint:
```
GET /api/teacher/today → returns { grade, unit, unit_id, cefr_targets } based on day-of-week + localStorage schedule
```

If no schedule configured, return `{ configured: false }` — home view shows "Set up your schedule in Settings to see today's plan."

**Tests**: `tests/test_teacher_schedule.py`
- test_today_endpoint_returns_unit_for_configured_day
- test_today_endpoint_returns_unconfigured_when_no_schedule

---

### 3.2 Unobserved Students Endpoint

The student lens tracks observations. Teachers need to know: "which students haven't I observed recently?"

Add endpoint:
```
GET /api/students/unobserved?days=14 → returns list of students with no observation in N days
```

Implementation: query StudentLensStore for students whose last observation is older than N days (default 14).

**Tests**: `tests/test_unobserved_students.py`
- test_unobserved_returns_students_without_recent_observations
- test_unobserved_respects_days_parameter
- test_unobserved_excludes_recently_observed

---

### 3.3 Brief Endpoint

```
GET /api/brief → aggregates teacher's day into a single JSON response
```

Response shape:
```json
{
  "today": {
    "day": "Thursday",
    "configured": true,
    "grade": "Grade 3",
    "unit": "La Famiglia",
    "cefr_targets": ["A1 listening", "A1 speaking (guided)"],
    "source": "Manuale §4.2"
  },
  "attention": {
    "unobserved_count": 3,
    "unobserved_students": ["Student A", "Student B", "Student C"],
    "rti_pending": 1,
    "rti_pending_names": ["Student D"]
  },
  "recent": {
    "last_observation": "2026-07-16T14:30:00",
    "observations_this_week": 7,
    "last_reflection": "2026-07-15T21:00:00"
  },
  "health": {
    "status": "WARN",
    "summary": "Something may need attention"
  }
}
```

No LLM. No network. Reads only from: schedule (localStorage via query param or header), student lens DB, revision log, Doctor.

**Tests**: `tests/test_brief_endpoint.py`
- test_brief_returns_today_when_schedule_configured
- test_brief_returns_unobserved_students
- test_brief_returns_recent_observation_count
- test_brief_returns_health_status
- test_brief_returns_unconfigured_today_when_no_schedule

---

### 3.4 Home View (Default Landing)

Add a "Home" view to `static/index.html`. It becomes the DEFAULT view when the app opens (not Plan).

**Layout:**
```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  Good morning.                                              │
│                                                             │
│  Today: Grade 3 — La Famiglia                               │
│  CEFR targets: A1 listening, A1 speaking (guided)           │
│  Source: Manuale §4.2                                       │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  ⚠️ 3 students unobserved for 14+ days              │   │
│  │  [Go to Observe]                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  👤 1 RTI decision pending                           │   │
│  │  [Go to Students]                                    │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  This week: 7 observations captured                         │
│  Last reflection: yesterday                                 │
│                                                             │
│  ❤️ System: WARN                                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Behavior:**
- Fetches `/api/brief` on mount
- If schedule not configured: shows "Set up your schedule in Settings → My Schedule"
- If no students loaded: shows "Add students in the Students view to see observation reminders"
- Clicking [Go to Observe] switches to Observe view
- Clicking [Go to Students] switches to Students view
- Logo in sidebar always returns to Home

**Add to sidebar:**
```
  🏠 Home              ← NEW, first item (above Plan)
  📋 Plan
  ✏️ Prepare
  ...
```

---

### 3.5 Rich Bootstrap Progress (Electron)

Update `desktop/electron/main.ts` to show a progress HTML page while the backend starts.

The loading screen (rendered directly in BrowserWindow via `loadURL('data:text/html,...')` or a local HTML string):

```
┌─────────────────────────────────────────┐
│                                         │
│        🌱 Lingua Viva                   │
│                                         │
│   ✓ Python 3.12 found                  │
│   ✓ Ollama available                   │
│   ⏳ Starting server...                │
│   ○ Ready                              │
│                                         │
│   Everything stays on your machine.     │
│                                         │
└─────────────────────────────────────────┘
```

Steps:
1. Check Python → ✓ or ✗ with detail
2. Check Ollama → ✓ or "Install Ollama at ollama.com" with link
3. Start server → ⏳ spinning until health probe succeeds → ✓
4. Ready → redirect to `http://127.0.0.1:8787`

The existing `bootstrap.ts` already has `checkPython()`, `checkOllama()`, `startBackend()`, `waitForBackend()`. Wire them to progress updates sent to the renderer via `win.webContents.send()` or just update the loading HTML between steps.

---

### 3.6 Welcome Screen (First Launch Only)

On FIRST launch (no `lvRole` in the response from `/`), before the role picker shows:

```
┌─────────────────────────────────────────┐
│                                         │
│        🌱 Lingua Viva                   │
│                                         │
│   A teacher workbench for Italian       │
│   language instruction.                 │
│                                         │
│   Everything stays on your machine.     │
│   No student data leaves. Ever.         │
│                                         │
│   I am a:                               │
│   [Teacher]  [Coordinator]              │
│                                         │
└─────────────────────────────────────────┘
```

After selection → redirect to Home view (not Plan, not Ask).

---

## 4. File Changes Summary

| File | Change |
|------|--------|
| `src/web.py` | Add: GET /api/teacher/today, GET /api/students/unobserved, GET /api/brief |
| `static/index.html` | Add: Home view (default), schedule config in Settings, sidebar Home item |
| `desktop/electron/main.ts` | Add: rich loading HTML with 4-step progress |
| `src/lingua_viva/brief.py` | NEW: BriefService aggregating schedule + lens + log + health |

## 5. Tests

| File | Tests |
|------|-------|
| `tests/test_teacher_schedule.py` | today endpoint, configured/unconfigured |
| `tests/test_unobserved_students.py` | unobserved query, days param, exclusion |
| `tests/test_brief_endpoint.py` | full brief aggregation, health, observations |
| `tests/test_home_view.py` | home renders, links to Observe/Students, schedule prompt |

---

## 6. Hardening Gate

After all 6 steps pass individually, run 15 consecutive iterations:

```bash
for i in $(seq 1 15); do
  echo "=== Iteration $i ==="
  
  # Server starts, health probe succeeds
  python3 src/web.py &
  sleep 3
  
  # Brief endpoint returns valid JSON
  curl -s http://127.0.0.1:8787/api/brief | python3 -c "import json,sys; d=json.load(sys.stdin); assert 'today' in d and 'attention' in d"
  
  # Home view renders (check static/index.html serves with home content)
  curl -s http://127.0.0.1:8787/ | grep -q "Good morning\|Set up your schedule"
  
  # Unobserved endpoint works
  curl -s http://127.0.0.1:8787/api/students/unobserved | python3 -c "import json,sys; json.load(sys.stdin)"
  
  # Kill server, port freed
  kill %1 2>/dev/null; wait 2>/dev/null
  sleep 1
  ! lsof -i :8787 -t >/dev/null 2>&1
  
  echo "Iteration $i passed"
done

# Then:
python3 -m pytest tests/ -q                          # 332+ (more with new tests)
python3 -m pytest doctor/support_loop/tests/ -q      # 15
python3 -m doctor.support_loop doctor                # WARN or OK
rg "Mission Canvas|Still I Rise|MC_|mc\." static/ src/lingua_viva/ tests/  # 0
git status --short -- Manuale_Italiano_Laboratorio_Linguistico_G1-G5.docx  # empty
```

---

## 7. What NOT To Build

- No LLM-generated brief (pure data aggregation only)
- No calendar integration (teachers use their school calendar, not this app)
- No email/inbox (this is a curriculum tool, not a communication tool)
- No action cache (LV doesn't have MC's action registry — observations ARE the cache)
- No notification system (teachers check the app when they choose to)
- No wizard (role selection IS the onboarding — teachers don't need a 5-step wizard)

---

## 8. Success Criteria

After Phase 4, a teacher opens the app and sees:
1. Rich progress screen during startup (Python ✓, Ollama ✓, Server ✓)
2. Welcome + role selection on first launch
3. Home view with today's plan, unobserved students, RTI pending, observation count
4. One tap from Home → Observe or Students for immediate action
5. Schedule configuration in Settings that feeds the Home view

The app now has a LANDING, not just a tool grid.
