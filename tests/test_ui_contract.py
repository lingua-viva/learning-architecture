"""UI bundle contract regression test (MC-lessons §3).

Pins the current contract version. When a deliberate UI change requires a
version bump (`python3 scripts/check_ui_contract.py --bump`), update
EXPECTED_VERSION here in the same commit and add a bump-log line to
contracts/UI_CONTRACT.yaml explaining why — MC's own ceremony discipline:
the comments are the changelog.
"""

import subprocess
import sys
import tempfile
from pathlib import Path
import shutil

import yaml

REPO = Path(__file__).resolve().parent.parent

# Bump log:
#   v1 (2026-07-19): initial lock, MC-lessons pass baseline.
#   v2 (2026-07-19): src/web.py request-outcome logging middleware (§5).
#   v3 (2026-07-19): static/index.html Ctrl/Cmd+K quick-capture overlay (§7).
#   v4 (2026-07-19): GET /api/profile/export + Export My Data button (§8).
#   v5 (2026-07-20): default ingest scratch storage moved to LV runtime home.
#   v6 (2026-07-20): admin deferred views explain reasons/prerequisites.
#   v7 (2026-07-20): EXP09 fix — healthBadgeClass() + .badge.risk CSS class.
#   v8 (2026-07-20): Claudia-lens hardening — copy/register updates for
#     teacher UI, parent draft route, and quick-capture deterministic feedback.
#   v9 (2026-07-20): sidebar accessibility + token pass.
#   v10 (2026-07-22): file-map confirmation, opt-in zone peek, and assignment UI.
#   v11 (2026-07-22): Slack utility view and Events API integration.
#   v12 (2026-07-22): Slack setup-scope and network-boundary hardening.
#   v13 (2026-07-22): convergence re-lock for combined protected UI work.
#   v14-v18 (2026-07-22): convergence plus local-only Observe/Ask voice workflow.
#   v19 (2026-07-22): 15-pass Observe/Ask Oka voice hardening.
#   v20 (2026-07-23): teacher-lens/RTI endpoints + Phase 5B surface cards.
#   v21 (2026-07-23): Linux download button.
#   v22 (2026-07-23): Observe support-profile classification write path.
#   v23 (2026-07-23): Google Drive explicit-import Settings mount.
#   v26 (2026-07-23): Restored unobserved_students return statement in web.py.
#   v27 (2026-07-23): support-profile summary JavaScript parse fix.
#   v28 (2026-07-23): Ingestion and extraction mapping v2 UI implementation.
#   v29 (2026-07-23): LV-BLT-001 provider connect form + LV-BLT-003 teaching
#     artifact ingest UI in Settings.
#   v30 (2026-07-23): LV-BLT-007 System stats mounted in Health; direct RTI
#     tier control mounted in Students; removed duplicate, never-mounted
#     GET /api/students/unobserved (brief.py's own _unobserved() is what
#     Home's reminder actually calls); removed duplicate GET
#     /api/teacher/today (Home retains /api/brief); session_info() docstring.
#   v31–33 (2026-07-23): re-seal lock after pull merged remote v30 with local
#     v29; BLT-009 Knowledge browser; BLT-006 route reclassification; fix
#     OntologyNode.name field.
#   v34 (2026-07-27): Drive round-trip: extraction-sources dual-scan
#     (path-mismatch fix) + explicit POST /api/google-drive/upload with
#     Share-back-to-Drive panel in Settings.
#   v35 (2026-07-27): One-button update: reflection-log relocation + updates
#     pending/diff/resolve routes + Settings Template Updates panel.
#   v36 (2026-07-27): Drive workspace Phase 1: Drive utility-nav view with
#     URL-paste folder connect (GET/POST/DELETE /api/google-drive/folders),
#     teacher-language import + Review-now next action, share-back panel.
#   v37 (2026-07-27): Slack Daily Operations Assistant Lane E: Socket Mode
#     wiring + ops status/daily/records routes, "Daily" teacher-nav view.
#   v38 (2026-07-27): re-seal after both concurrent lanes (Drive workspace +
#     Slack ops) finished editing the shared tree; no new features.
#   v39 (2026-07-27): Sources view + File Map UX redesign
#     (SPEC_LV_SOURCES_VIEW_FILE_MAP_UX_2026-07-27): Sources utility-nav
#     view (Slack card + Drive relocation + Local folders invitation/scan
#     UX), filemap error `code` field, Home nudge.
#   v40 (2026-07-27): Drive-surface hardening loop re-seal
#     (dev/HARDENING_LOOP_DRIVE_2026-07-27.md): web.py-only hardening —
#     Drive route validation, privacy events, hermeticity seam. No UI changes.
#   v41 (2026-07-27): one-button-update hardening iteration 7
#     (REPORT_ONE_BUTTON_UPDATE §8): web.py legacy-migration intra-file
#     dedupe + UnicodeDecodeError guard. No UI changes.
#   v42 (2026-07-27): Slack Ops Assistant 15-pass hardening loop
#     (dev/reports/REPORT_SLACK_OPS_HARDENING_2026-07-27.md): web.py
#     shutdown now awaits the cancelled briefing scheduler. No UI changes.
#   v43 (2026-07-27): review finding 2 — uuid4 reflection revision_ids +
#     content-aware migration dedupe. No UI changes.
#   v44 (2026-07-27): in-app Google sign-in for Drive (spec §A): auth
#     start/disconnect routes + Sources/Drive sign-in panel with trust
#     copy, status polling, sign-in-again, and env-credential shadowing.
#   v45 (2026-07-27): live-layer read path §3 — restart hint appended to the
#     Template Updates take-new success message. No web.py changes.
#   v46 (2026-07-27): Drive final hardening H1-H5: interstitial walkthrough
#     copy in the sign-in panel; web.py 0600 lens snapshots + prune exports
#     to 3/student after upload. Zero new routes.
#   v47 (2026-07-27): Slack ops v2 packs Phase 2+3 — bot-spec startup
#     compile + go-live gate + schedule times; Bot Setup routes
#     (catalog/bot-spec get+put/roster) and Daily sub-view panel.
#   v48 (2026-07-27): Slack ops v2 packs Phase 4+5 — teach-loop
#     reclassify route, corpus run/sentences/rules-decide routes with
#     the go-live + candidate-approve gates, PUT staleness guard, and
#     the Bot Setup panel's teach/corpus/go-live controls.
#   v49 (2026-07-27): Slack ops v2 packs Phase 6 stretch — shadow
#     suggester route + panel line; backlog packs bus_transport and
#     dismissal_changes ship as data, out of the parity compile.
#   v50 (2026-07-27): LV-5 startup blocker — web.py event handlers moved
#     to app.router.add_event_handler (app-level method removed in
#     Starlette 1.0; unpinned installs crashed at import). No UI change.
#   v51 (2026-07-28): Italian STT — recognition.lang "en-US" -> "it-IT" in
#     both voice handlers (toggleAsk, toggleObserve). Teachers speak
#     Italian; the recogniser was using an English model.
#   v52 (2026-07-28): Italian TTS — voiceRuntime.speak() sets
#     utterance.lang = "it-IT" before reading the voice list and prefers an
#     Italian voice, replacing the English name/lang preference. Completes
#     the v51 fix (was: listens Italian, answers English).
#   v53 (2026-07-28): Slice 5 Credentials — in-app Slack setup. src/web.py:
#     GET/PUT/DELETE /api/slack/credentials + POST
#     /api/slack/credentials/test. static/index.html: Settings ->
#     Integrations panel (Slack form + Drive status).
#   v54 (2026-07-28): Slice 4 Governance — unified Governance view with
#     Trust Status (5 questions), sealed observation export, and evidence
#     tabs over the privacy log / traces / Doctor. src/web.py: GET
#     /api/governance/trust, POST /api/governance/observation-export, POST
#     /api/governance/verify-pack. Also removed three UI claims that were
#     rendered regardless of the facts (hardcoded "external calls: 0" badge,
#     a count labelled "No external calls", and "No data has left this
#     machine.").
#   v55 (2026-07-28): Slice 1 Sources — GET /api/sources/status registry,
#     student-zone badges, and measured route/external_calls provenance
#     (previously hardcoded in the response, new_trace() and read_traces()).
#   v56 (2026-07-28): Slice 3 Action Queue — Activity view + GET
#     /api/actions/history, built from the trace and privacy logs. No student
#     names (projection constraint); unreadable records report unknown.
#   v57 (2026-07-28): Slice 2 Dispatcher — action registry + governance
#     preview. GET /api/actions/registry; Activity "What you can do" panel;
#     inline preview in Prepare.
#   v58 (2026-07-28): Slice 6 Daily augmentation — GET /api/daily/briefing +
#     "Your day" widgets, anonymous student references.
#   v59 (2026-07-29): Gap 1 — parent report safety gate wired on
#     /api/parents/recommendation; warnings rendered above the draft.
#   v60 (2026-07-29): Gap 2 — filemap auto-scan on startup (daemon thread,
#     LV_AGENT + pytest guarded). src/web.py startup handler only.
#   v61 (2026-07-29): Gap 3 — ARON named (aron_ref), explained in Privacy,
#     tooltips wherever S-XXXX codes appear.
#   v62 (2026-07-29): Gap 4 — Evidence/Capacity/Trends return real counts;
#     deferred stubs and _admin_deferred() removed.
#   v63 (2026-07-29): Gap 5 — POST /api/voice/tts with the publication-safety
#     gate ahead of the key check; UI falls back to the local Italian voice.
#   v64 (2026-07-29): Gap 6 — assessment deltas, growth badges, tier
#     recommendations (never applied automatically).
#   v65 (2026-07-29): 15-pass hardening — contradicted labels removed,
#     /api/voice/tts non-object body fixed, ARON reference on the roster.
#   v66 (2026-07-29): Integration loop + voice-first contracts — source
#     ledger, grounding, action plans, deliverables, audit receipts, golden
#     workflows, and MediaRecorder -> /api/voice/stt local capture.
#   v67 (2026-07-29): source registry keeps unavailable connector counts null
#     even when the durable ledger has stale records.
#   v68 (2026-07-29): fixed right-side voice companion panel, avatar asset
#     route, and Electron blob-media CSP.
#   v69 (2026-07-29): pre-push audit fix — Drive share-back now writes a
#     DeliverableRecord + AuditReceipt (src/web.py only, no markup change).
#   v70 (2026-07-29): GIR → voice delivery tone — speak() accepts tonePrefix,
#     /api/query returns voice_tone + tone_prefix, speakLocally fallback
#     preserves hedge prefix.
#   v71 (2026-07-30): re-lock after concurrent commit of GIR voice tone build.
#   v72 (2026-07-30): voice-originated Ask uses /api/query/stream SSE and
#     queued answer_sentence playback while /api/query stays JSON-compatible.
#   v73 (2026-07-30): re-lock after v72 stream parser cleanup.
#   v74 (2026-07-30): GIR hardening review — /api/query stops inventing
#     Manuale v1 citations for uncited answers.
#   v75 (2026-07-30): Still I Rise absence+coverage MVP staffing-summary endpoint.
#   v76 (2026-07-30): SIR Phase 2A ops request center request-summary endpoint.
#   v77 (2026-07-30): SIR Phase 2B schedule-change ack summary endpoint.
#   v78 (2026-07-30): server-side auth role gate middleware.
#   v79 (2026-07-30): auth role gate hardening for teacher-owned writes.
#   v80 (2026-07-30): native exit integrity gates for TTS, Drive upload,
#     and governance export web paths.
#   v81 (2026-07-30): exit gate hardening for blocked Drive path disclosure.
#   v82 (2026-07-30): teacher decision flywheel backend preview/approval routes.
#   v83 (2026-07-30): teacher decision flywheel preview non-mutation hardening.
#   v84 (2026-07-30): teacher decision flywheel complete local audit receipts.
#   v85 (2026-07-30): cohort lesson-planning backend preview/approval/list routes.
#   v86 (2026-07-30): cohort lesson-planning complete local audit receipts.
#   v89 (2026-08-01): lesson-materials generate endpoint (MVP sprint Spec 3).
#   v90 (2026-08-01): voice intent router endpoint (MVP sprint Spec 4).
#   v91 (2026-08-01): frontend voice wire — mic routes through /api/voice/act.
#   v92 (2026-08-01): school category profile wiring (MVP sprint Spec 1).
#   v93 (2026-08-01): voice student detection v2 — fuzzy names + context.
#   v94 (2026-08-01): multi-teacher triangulation — colleague ledgers + UI.
#   v95 (2026-08-01): evidence + ethos traits — unified evidence ledger
#     endpoints, ethos taxonomy + suggestions, evidence-in-parent-draft
#     behind the safety gates, Evidence panel + Sources add-as-evidence.
#   v96 (2026-08-01): voice latency — qwen2.5:3b + 256 max tokens on voice/act.
#   v97 (2026-08-02): teacher identity provisioning — POST /api/school-profile,
#     Settings identity panel, un-provisioned nudge, sentinel ledger guards.
#   v98 (2026-08-02): routing-memory hardening — raw values into
#     record_decision at category_suggest emission sites (no route/UI change).
#   v100 (2026-08-03): Claudia QA fixes — voice/probe wired into every mic
#     surface (P0-1), success save toast before form clear (P2-1).
#   v101 (2026-08-04): HF1 frontend hotfixes (Chip QA 0.2.32) — F2
#     renderAnswerSafety gate for text + voice, F1b guaranteed mic release,
#     F5 student placeholder + refusals, §8.2 voice companion hidden.
#   v102 (2026-08-04): relock only — v101 hashes were CRLF-contaminated
#     (Windows autocrlf checkout); recomputed from LF-canonical bytes.
#   v103-v104 (2026-08-04): T8 Ask = voice-first Perplexity — /api/ask with
#     PII egress refusal gate, ASK button + examples + stop/more intercepts,
#     no-redirect rule (switchView("ask") removed); v104 = 401-vs-offline
#     honesty fix in the same session.
#   v105 (2026-08-04): 15-pass hardening of HF1+T8 — mic release on setup
#     crash, null-GIR no false warning, stale-student placeholder fallback,
#     Ask hint copy, question length cap, egress event before the call.
#   v106 (2026-08-04): T9 Students-from-file ingest + T6 sync enqueue;
#     demo-roster seeding removed (empty on install, acceptance A6).
#   v107 (2026-08-04): relock — T9 follow-up wired real T3 extraction into
#     the ingest job (web.py) without a bump; sealed here.
#   v109 (2026-08-04): T5 observe mic, B1-B5 gate closures, A3 JSON errors, A4 CEFR optional.
#   v111 (2026-08-04): P0-A/B + P1-1/2/3/4/5/9 fixes from v0.2.36 QA (three reports).
#   v112 (2026-08-04): P1-3 follow-up — sel_domain/sel_valence null-out on general type.
#   v119 (2026-08-05): F3 local-route metadata gap — model_used/duration_ms
#     threaded through the ask_endpoint success-path return dict.
#   v120 (2026-08-06): Still I Rise Phase 1 Items 1-5 — roster import review/
#     undo, G1-G12 Add Student, Settings Perplexity/Rime keys.
#   v123 (2026-08-07): real deliverable hardening — Prepare printable packet
#     preview/approval surface and Drive lens Markdown preview-before-share.
#   v126 (2026-08-08): Voice §1 Ask grounding surface — shared safety gate
#     mirrors resolve_voice_tone; /api/ask routed through it; TTS locale fix.
#   v134 (2026-08-09): Router plug-in point in src/web.py (ROUTER_MODULES
#     include loop) — enables sources/safeguarding/artifacts feature routers.
#   v135 (2026-08-09): Daily brief extensions — absence escalations, knowledge
#     library, coursework artifacts widgets via brief_extensions (fail-soft).
#   v136 (2026-08-09): Safeguarding severity gate live-wired into all three
#     capture sites (voice observe, observe/capture, Slack bot).
#   v138 (2026-08-09): PoI progression panel mounted in the selected student
#     lens; consumes /api/poi/progression/{student_id} and renders objective
#     phases, trend, and consolidate-next guidance.
#   v139 (2026-08-09): Query timeout honesty marker — timeout errors state
#     no model answered, carry model_used="none", and report external_calls=0
#     only when configuration is provably local-only.
#   v140 (2026-08-09): Parent recommendation route now passes the final
#     parent-safe draft through sharing_matrix.filter_payload(role=parent)
#     before returning the legacy flat response shape.
#   v154 (2026-08-18): Drive out-of-the-box roster→lenses (SPEC_LV_DRIVE_OOTB):
#     real drive_ref import, roster auto-create-all with undo review, Drive
#     sync-back auto-provision + startup drain, Students Drive import UI.
#   v155 (2026-08-18): per-student Remove button on each roster row (soft
#     archive via DELETE /api/students/{id}; observations kept).
#   v156 (2026-08-18): Drive folder links accepted by the Students import
#     (class-folder ingest, match-by-name, review queue); inline teacher
#     entry per Category Profile section via POST .../support-entry
#     (teacher_confirmed — typing it IS the evidence).
#   v157 (2026-08-18): Prepare/class-materials fix build — 3-step Prepare with
#     drop zone, unit CRUD (starter themes removed), file-content generation,
#     starting CEFR levels at import, teacher_roster, native print, Claudia-
#     lens copy pass.
#   v158 (2026-08-19): Drive per-file access — OAuth scope → drive.file,
#     sign-in panel copy rewritten (obsolete unverified-app walkthrough and
#     broad-permission line removed), honest DriveAuthError passthrough.
#   v159 (2026-08-19): Phase 0A always-preview ingest — imports stop at a
#     preview that writes nothing; explicit approve/cancel routes + panel.
#   v160 (2026-08-19): STEP 3 — dead numeric confidence gate deleted; trust
#     rides on the corpus-measured evidence class (server-side only).
#   v161 (2026-08-19): STEP 4 — class membership on preview rows + "only my
#     class" approve scope (web.py + index.html scope picker).
EXPECTED_VERSION = 161


def _html() -> str:
    return (REPO / "static" / "index.html").read_text(encoding="utf-8")


def test_roster_split_review_surface_stays_mounted():
    import re

    html = _html()
    assert "/api/lesson-materials/roster-split" in html
    assert "Class groups for this lesson" in html
    assert "Foundational / On Track / Extended" in html
    assert 'id="individual-support-review"' in html
    assert "not a fourth tier" in html
    assert 'data-tier-override="' in html
    assert 'data-reset-tier="' in html
    assert "teacher override" in html
    assert "No roster observations yet. Generation can still continue with empty groups." in html

    split_markup = re.search(
        r'<div class="grid three">.*?id="individual-support-review"',
        html,
        flags=re.S,
    )
    assert split_markup, "Individual Support must render after the three tier columns, not as a fourth column"


def test_lesson_materials_post_bodies_keep_tier_overrides():
    import re

    html = _html()
    assert "tier_overrides: activeTierOverrides()" in html

    calls = {
        "/api/lesson-materials/generate": r'api\("/api/lesson-materials/generate".*?body:\s*JSON\.stringify\(lessonPayload\(\)\)',
        "/api/lesson-materials/packet/preview": r'api\("/api/lesson-materials/packet/preview".*?body:\s*JSON\.stringify\(lessonPayload\(\)\)',
        "/api/lesson-materials/packet/approve": r'api\("/api/lesson-materials/packet/approve".*?body:\s*JSON\.stringify\(\{\.\.\.lessonPayload\(\),',
    }
    for route, pattern in calls.items():
        assert re.search(pattern, html, flags=re.S), f"{route} no longer posts lessonPayload() with tier_overrides"


def test_poi_progression_surface_stays_mounted_in_student_lens():
    html = _html()
    assert 'id="poi-progression-panel"' in html
    assert "renderPoiProgression(targetId, state.selectedStudent)" in html
    assert "/api/poi/progression/" in html
    assert "Consolidate next" in html
    assert "data-poi-objective" in html


def test_version_bumped_exactly_one_from_live():
    contract = yaml.safe_load((REPO / "contracts" / "UI_CONTRACT.yaml").read_text(encoding="utf-8"))
    assert contract["version"] == EXPECTED_VERSION, (
        "contracts/UI_CONTRACT.yaml version drifted from the pinned test value — "
        "if this was a deliberate UI change, update EXPECTED_VERSION here and add "
        "a bump-log line to the contract file."
    )


def test_ui_contract_check_passes():
    result = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "check_ui_contract.py")],
        capture_output=True, text=True, cwd=REPO,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_ui_contract_lock_matches_live_files():
    import hashlib
    import json

    contract = yaml.safe_load((REPO / "contracts" / "UI_CONTRACT.yaml").read_text(encoding="utf-8"))
    lock = json.loads((REPO / "contracts" / "UI_CONTRACT.lock").read_text(encoding="utf-8"))
    assert lock["version"] == contract["version"]
    for rel in contract["files"]:
        actual = hashlib.sha256((REPO / rel).read_bytes()).hexdigest()
        assert lock["hashes"][rel] == actual, f"{rel} hash drifted from lock without a version bump"


def test_static_inline_javascript_syntax_is_valid():
    import pytest

    node = shutil.which("node")
    if not node:
        pytest.skip("node is not available for static JS syntax check")
    html = _html()
    start = html.index("<script>") + len("<script>")
    end = html.index("</script>", start)
    script = html[start:end]
    with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8") as handle:
        handle.write(script)
        handle.flush()
        result = subprocess.run([node, "--check", handle.name], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_sidebar_nav_contract_counts_and_handlers():
    import re

    html = _html()
    arrays = {}
    for name in ("teacherNav", "adminNav", "utilityNav"):
        match = re.search(rf"const {name} = \[(.*?)\];", html, flags=re.S)
        assert match, f"{name} array missing"
        arrays[name] = re.findall(r'\["([^"]+)",\s*"([^"]+)",\s*"([^"]+)"\]', match.group(1))

    assert len(arrays["teacherNav"]) == 9
    assert len(arrays["adminNav"]) == 5
    assert len(arrays["utilityNav"]) == 10

    view_map = re.search(r"const views = \{(.*?)\n      \};", html, flags=re.S)
    assert view_map, "renderView() view handler map missing"
    handler_entries = re.findall(r"^\s*([a-z]+):\s*render[A-Za-z]+,?", view_map.group(1), flags=re.M)
    nav_entries = [item[0] for items in arrays.values() for item in items]
    handler_ids = set(handler_entries)
    nav_ids = set(nav_entries)

    assert len(handler_entries) == len(handler_ids), "renderView() contains duplicate handler ids"
    assert len(nav_entries) == len(nav_ids), "sidebar contains duplicate nav ids"
    assert nav_ids == handler_ids, (
        "every live view handler must have exactly one sidebar mount, and every "
        "sidebar item must have a handler; do not ship dead renderers or dead nav"
    )


def test_sidebar_accessibility_markup_and_tokens_present():
    html = _html()
    assert 'id="primary-nav" class="nav" aria-label="Primary"' in html
    assert 'id="utility-nav" class="nav utility" aria-label="Utility"' in html
    assert 'aria-current="page"' in html
    assert ".nav button:focus-visible" in html
    assert "--lv-sidebar-width: 200px;" in html
    assert "grid-template-columns: var(--lv-sidebar-width) minmax(0, 1fr);" in html
    assert "--lv-nav-gap: 4px;" in html
    assert "gap: var(--lv-nav-gap);" in html
    assert "--lv-nav-row-min-height: 38px;" in html
