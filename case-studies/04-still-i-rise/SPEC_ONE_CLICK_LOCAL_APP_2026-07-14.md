# Spec: One-Command Local-First App Experience for Still I Rise

**Date**: 2026-07-14 · **Deadline**: 2026-07-15 (not rushed — Claudia is in Italy — but firm)
**Status**: SPEC ONLY. No build has started. Operator directive: *"DO NOT BUILD YET. Just get a solid spec together and then we will discuss if we should do the build in another window."*

## Revision history

1. **v1** proposed a hosted VPS + public URL. **Wrong** — operator: *"the biggest seller is it runs local. it has to run local. a public URL will not work."*
2. **v2** overcorrected to "local only." **Also wrong** — operator: *"Local first, not local only. We still want the onboarding experience where they can choose to connect to external models if they like... with the wall protecting PII and the firewall against malware... is that not integrated?"* Verified the governance is real and already wired (§2). The actual gap was onboarding UX, not missing governance.
3. **v3** incorporated four independent reviews of v2 (a structural/code-accuracy review, a UX/positioning review, a ground-truth verification pass, and a testability/buildability review). All four agreed the direction is right; all four found the spec under-specified or, in two places, factually wrong about what the code actually does. Every finding is dispositioned in §9. The two load-bearing corrections:
   - **Gap 1's fix as originally written would not work.** `install.sh`/`install.ps1` download from `raw.githubusercontent.com/.../main/dist/...`, but `release.yml` publishes to GitHub **Release assets** — a different URL entirely, and `dist/` is never committed to `main`. Cutting a tag alone would not make the binary path engage. Fixed in Gap 1 below.
   - **Gap 5a's fix as originally written would not work either.** `providers.json` is not read anywhere in `src/*.py` (confirmed by grep) — the model-calling code (`src/pipeline.py`'s `_resolve_endpoint()`) reads `OPENAI_API_KEY`/`GROQ_API_KEY`/`MISTRAL_API_KEY` env vars directly, and only implements OpenAI, Groq, Mistral, and Ollama — **not** Anthropic or Gemini, despite both being in the exit-gate allowlist and `litellm.yaml`. Writing a JSON file nothing reads would have done nothing. Fixed in Gap 5a below, which now specifies actual new code.
4. **v4 (this version)** incorporates a second round of review against v3 from the same four reviewers, all now "approve" or "approve-with-edits." No architectural blockers were found this round — all five findings (C-3 through C-7) are implementation-contract refinements, verified directly against the code before being folded in. Disposition added to §9. The load-bearing one:
   - **Gap 5a's resolution-order fix in v3 was still incomplete.** Confirmed at `src/pipeline.py:651`: `Pipeline.run()` always calls `self.reasoning.reason(..., model=classification.default_model, ...)` — i.e., the ontology's `default_model` is passed as the `model` param on *every* call, not just true task/@mention overrides. Since `reason()`'s docstring resolution order treats the `model` param as highest priority (#1, above the `MC_REASON_MODEL` env tier), a provider-config check slotted into that env tier would **never fire** — `classification.default_model` would always win first. Fixed in Gap 5a below: provider config must be checked *ahead of* `classification.default_model`, with a distinct, narrower channel reserved for genuine explicit overrides (a real @mention or task envelope), so user provider preference isn't silently shadowed by the ontology default.

## 1. What the operator actually wants

- **Local-first, not local-only.** Default experience runs fully on-device (already what `install.sh` sets up via Ollama). Users can *opt in* to an external model for better/faster reasoning — governed by the PII sanitizer and connection firewall, which are already built and already apply regardless of which model is used.
- **One interface, not two.** No CLI exposed to end users at all — the browser/app surface is the only thing a teacher ever touches, including the provider choice and restarting the app after a reboot. (The CLI stays for technical/dev use — Claudia's own future contributors, CI.)
- **The ideal**: a genuine one-click install, on any device, opening straight into something that feels like an app, with direct local-file access (e.g., drop in a curriculum PDF, no CLI command).
- **The acceptable fallback, operator's own words**: *"a local host would be good enough."* Honest naming (per review feedback): what's achievable by tomorrow is **one command, run once, in a terminal** — after that, zero further CLI contact, including across reboots (see Gap 2b). This is "one-command install," not "one-click install" — true one-click native packaging (no terminal step at all, ever) is explicitly backlog (§4).
- **Audience framing that matters**: *"they do not need to test and play around... they are already interested, and I am building this specifically for them."* Known, committed staff — a short personal walkthrough is an acceptable onboarding cost. Bar is "simple with light guidance," not "flawless with zero support."

## 2. What's already true and doesn't need to change

Verified directly against the repo:
- `install.sh` / `install.ps1`: one command → installs locally → auto-starts the local server → auto-opens the browser to `localhost:7896`.
- `static/index.html`: a full browser chat UI already exists — this is the one interface.
- PWA-capable: `/manifest.json` (dynamically built by `src/pwa.py` from `static/manifest.json` as its base, with env-var overrides layered on top), `/sw.js`, `/offline.html`, full icon set. Chrome allows installing a PWA from `http://localhost` as an app-drawer/desktop icon without real TLS.
- **Governance is real, already wired, nothing to build**:
  - `sanitizer/app.py` — 3-layer PII sanitizer (regex + NER-style patterns + ontology `blocks_external` signals), fail-closed, every call logged to `sanitizer/data/firewall_log.ndjson`. Wired into `src/pipeline.py`'s `GatewayInterface.sanitize_query()`.
  - `src/gates/exit.py` — socket-level firewall: monkey-patches `socket.create_connection` so only an explicit `ALLOWLIST` can be reached (`api.anthropic.com`, `api.mistral.ai`, `api.groq.com`, `generativelanguage.googleapis.com`, `api.perplexity.ai`, local/Ollama hosts), plus inbound response scanning for malicious patterns.
  - `src/pipeline.py`'s REASON step (`reason()`/`_resolve_best_model()`/`_detect_model()`) already resolves "prefer local, then cloud" via live Ollama auto-detection.
- **Correction from v2**: `_resolve_endpoint()` (`src/pipeline.py`, the function that actually builds the HTTP call) only implements `openai/`, `groq/`, `mistral/`, and a default Ollama branch. **No Anthropic or Gemini branch exists.** They're in the exit-gate allowlist and in `config/litellm.yaml`'s model list, but not in the thing that actually places the call. This matters directly for Gap 5a's scope.
- **Correction from v2**: `providers.json` is written by `install.sh` (for Ollama detection) but read by **nothing** in `src/*.py` (confirmed by grep). It is currently decorative. Any provider-choice UX must add real code that reads config at call time — this doesn't exist yet.

## 3. Concrete gaps to close (in priority order)

### Gap 1 — No binary has ever been published; installer's binary path is pointed at a URL that will never resolve
Confirmed: no `v*` tag exists. A `dist/sir` binary (168MB) already exists **locally on this dev machine** from an earlier local PyInstaller build — it is not published anywhere and does not help an end user. `install.sh:74` / `install.ps1:41` download from `https://raw.githubusercontent.com/lingua-viva/learning-architecture/main/dist/${BINARY}`. `release.yml`'s `release` job publishes build artifacts as **GitHub Release assets** via `softprops/action-gh-release@v2` — these live at a release-asset URL, never at `raw.githubusercontent.com/.../main/dist/...`, and `dist/` is gitignored so it never lands on `main` regardless. **As written, cutting a tag would not fix the binary path** — the installers would still 404 and fall through to source-fallback, silently.

**Fix**:
1. Change `install.sh`/`install.ps1`'s download URL to a GitHub Releases asset URL — e.g. `https://github.com/lingua-viva/learning-architecture/releases/latest/download/${BINARY}` (GitHub's `/releases/latest/download/<asset-name>` redirect resolves to the current latest release automatically, no API call or version-number hardcoding needed).
2. Do **not** commit `dist/*` to `main` — release assets are the correct mechanism; committing binaries to the tracked tree is the worse alternative and is explicitly rejected.
3. Tag name for this first release: **`v1.0.0`**.
4. After tagging, confirm end-to-end (not just "workflow ran green"): download via the corrected URL in a clean environment and confirm the binary — not the source-fallback path — actually executed (see Gap 1's test-script addition, §6 step 1).

**Approval needed**: cutting `v1.0.0` triggers real GitHub Actions build minutes and a public release artifact on `lingua-viva/learning-architecture` — confirm before tagging.

### Gap 2 — The one real CLI dependency a teacher would otherwise hit: document ingestion
Today, ingestion is `sir ingest <path> --type=curriculum|organizational`, CLI-only (`src/mc_cli.py:79-102`, calling `document_parser.DocumentParser.parse()`). **Confirmed**: `document_parser.py` only supports PDF today — `parse()` raises `ValueError` on any other suffix. Scope the upload feature to match reality, not aspiration.

**Fix**: add a file-upload affordance to `static/index.html` (drag-and-drop or file picker) hitting a new `POST /api/ingest` route in `src/web.py`, thin-wrapping the same `document_parser`/`document_store` pipeline `run_ingest()` already uses (same PII redaction, same `student-records` hard refusal). Concrete contract for the route, not left to the builder to invent:
- **Accepted type**: `.pdf` only for tomorrow (matches actual parser support). Reject anything else at the route, before parsing, with a plain-language message ("Only PDF files are supported right now").
- **Max size**: 50MB, rejected with a clear message before the file is even fully read into memory (check `Content-Length` first).
- **Temp-file lifecycle**: write the upload to a scoped temp path (e.g. `tempfile.mkstemp` under a dedicated ingest-temp dir), parse, then delete the temp file in a `finally` block regardless of success/failure — never leave uploaded content sitting on disk outside the governed document store.
- **No arbitrary server paths**: the route must never accept or trust a client-supplied filesystem path (unlike the CLI's `run_ingest(path_arg, ...)`, which trusts a local operator) — only an uploaded file stream.
- **Concurrency**: a single local user is the real-world case; serialize ingestion behind a simple lock rather than building a queue.
- **Error reporting**: parsing failures (corrupt PDF, scanned-image-only PDF with no extractable text) return a friendly message ("This file couldn't be read — try a different PDF"), never a raw 500.
- **Progress feedback**: minimum viable — an immediate "Uploading…" state, then "Processing…" (parsing can take real time on a large guide), then "Done — ingested, N sections found."

### Gap 2b — Restarting after a reboot must not require a terminal either (new — flagged by UX review)
`install.sh` handles first launch, but nothing today handles *next* launch. If the process dies (reboot, crash, laptop closed) and the only way to bring it back is re-running the curl command or opening a terminal, the "no CLI" promise silently breaks on day 2 — a real gap the v2 spec missed entirely.

**Fix**: `install.sh`/`install.ps1` create a native launcher during setup that repeats the "start server, wait for it to bind, open browser" sequence with zero terminal interaction:
- **Linux**: a `.desktop` file (e.g. `~/.local/share/applications/still-i-rise.desktop`) with an `Exec=` line running a small wrapper script.
- **macOS**: a minimal `.app` (an Automator-style shell wrapper is sufficient; not a real Xcode build) placed in `~/Applications` or opened via `open`.
- **Windows**: a `.lnk` shortcut on the Desktop/Start Menu pointing at a wrapper `.bat`/`.ps1` that starts `sir.exe`/`python -m src.web` and opens the browser.
This is genuinely new, scoped work — small, but real; call it out explicitly rather than letting it hide inside Gap 1.

**Idempotency requirement (new, round-2 review)**: the launcher wrapper must check whether port 7896 is already serving *this* app before starting a second server instance — if it is, just open the browser to the existing instance. If the port is occupied by something else entirely, show a friendly failure ("Port 7896 is in use by another program — close it and try again") rather than silently opening a browser tab to the wrong thing.

### Gap 3 — PWA branding is currently wrong for this product, at the source, not just via env var
**Correction from v2**: `src/pwa.py`'s `build_manifest()` loads `static/manifest.json` as its **base object** and only *overrides* specific keys from env vars — it does not replace the base. `static/manifest.json:2-3` hardcodes `"name": "Mission Canvas"`, `"short_name": "MC"`. Independently, `static/index.html:197-203` hardcodes the literal strings `"MC"` (header mark), `"Mission Canvas"` (H1), `"Governed agent workbench"` (subtitle), and `"Install Mission Canvas for fast access and offline queueing."` (install-prompt button copy) directly in the HTML — none of this is touched by any env var at all. Setting `MC_PWA_NAME` alone, as v2 proposed, would leave the on-screen UI still reading "Mission Canvas" everywhere a user actually looks.

**Fix**: edit the source files directly for this fork — `static/manifest.json`'s `name`/`short_name` fields, and `static/index.html`'s hardcoded header/title/subtitle/install-button strings — to "Still I Rise." Keep the `MC_PWA_*` env-var mechanism as-is for any *future* white-labeling need; it's not the mechanism for this fork's own default branding.
**Also**: after first launch, tell the user explicitly *"click the install icon in your browser's address bar to add this as an app"* — Chrome doesn't always auto-prompt.

### Gap 4 — Built-but-unreachable education modules (highest-risk gap; needs a concrete contract, not a one-line instruction)
`content_differentiator.py`, `teacher_guide.py`, `assessment_generator.py`, `student_lens.py` are real and tested (262/262 per Turn 22/23), but nothing in `pipeline.py`/`mc_cli.py` calls them (confirmed by grep). Without this wired, §6's core demo queries (steps 6-8) cannot pass — this is the module that makes the product actually deliver structured education outputs instead of generic RAG chat.

**Execution point**: after CLASSIFY, before REASON. When classification lands on a wired education node, the matching module's structured output is computed and passed into REASON's `context` dict — the same injection pattern already used for KL/RAG retrieval feeding REASON (`context_builder.py`). **Output contract**: the module's own existing `to_markdown()` output (already built, already tested) is the **primary answer body**, rendered verbatim to the user. The model (REASON step) is only asked to write a short (1-3 sentence) framing/intro wrapper around it — it must not regenerate, paraphrase, or replace the structured content.

**Node-to-module map** (real function names, verified against the code, not placeholders):
| Ontology node | Module entry point | Real data dependency |
|---|---|---|
| `LV-CUR-002` (differentiation) | `ContentDifferentiator.generate_from_documents(lesson, retriever, domain)` | needs ingested curriculum chunks (Gap 2) in the document store for the relevant lesson/topic — **see guard below, this method has its own silent fallback that must be intercepted** |
| `LV-TCH-002` (grouping) | `TeacherGuideGenerator.generate(...)` → `build_cross_level_groups(roster, assignments)` | needs a roster with tier assignments already recorded (`StudentLensStore`); `avoid_pairing_with` is teacher-set, not inferred |
| `LV-STU-003` (RTI tier) | `StudentLensStore.evaluate_rti_rules(student_id)` — **the public wrapper (`student_lens.py:454`), not the private `_evaluate_rti_rules`** — evaluating "Rules A-E" | **needs an existing student record with observation history already logged** — this is not a fresh inference from a single chat message; there is no function that computes an RTI tier from a plain-language description alone |
| assessment node | `AssessmentGenerator.generate(pack)` | needs a `ContentPack` — i.e., depends on `LV-CUR-002` having already run for that lesson; the EXECUTE wrapper should check for this rather than assuming it |

**Missing-data fallback (the part v2 omitted entirely)**: if the required input isn't present — no ingested curriculum for a differentiation request, no known student record for an RTI request, no roster/tier assignments for a grouping request — the EXECUTE step must return a structured, honest prompt telling the teacher what's missing ("I don't have this student's observation history yet — log an observation first, then ask me again" / "Upload the curriculum document for this lesson first"), rather than silently falling through to a generic, ungrounded RAG answer that looks plausible but isn't real. This is a correctness requirement, not a nicety — a wrong-looking-right answer is worse than an honest "I need more information" for this audience.

**Confirmed contradiction to guard against explicitly (round-2 review, verified)**: `ContentDifferentiator.generate_from_documents()` (`content_differentiator.py:502-518`) does **not** itself produce the honest fallback above — its own docstring states it "falls back to template generation (`self.generate(lesson)`) if nothing was retrieved" and that "an empty or not-yet-populated document store must never block a teacher from getting a pack." That's the right behavior for other callers, but it's the opposite of what this UI path needs: a teacher who hasn't uploaded curriculum yet must see "upload curriculum first," not a generic templated pack that looks grounded but isn't. **Fix**: the EXECUTE wrapper for `LV-CUR-002` must check document availability (or inspect the returned `ContentPack.source_mode`, which is `"generated"` when the fallback fired) *before* surfacing the result to this UI path, and route to the honest missing-data prompt instead of returning a `source_mode == "generated"` pack silently. Do not modify `generate_from_documents()` itself — the guard belongs in the wrapper, since other callers may legitimately want the template fallback.

Keep narrow: wire these 4 modules via this one map; do not build a general action-dispatch framework.

### Gap 5a — Onboarding UX for the local-vs-external model choice (mechanism corrected from v2; scope corrected per review)
**What v2 got wrong**: proposed writing `providers.json` and expecting the pipeline to respect it. Confirmed nothing reads that file. **This gap requires new pipeline code**, not just a new UI screen.

**Fix, fully specified**:
1. **New pipeline read path — resolution order corrected (round-2 review, verified against the code)**: `src/pipeline.py:651` shows `Pipeline.run()` always passes `model=classification.default_model` into `reason()` — the ontology's default model, not a true explicit override — on every call. Since `reason()` treats its `model` param as top priority, slotting provider config in below that (at the `MC_REASON_MODEL` tier, as originally planned) would mean `classification.default_model` always wins and the user's provider choice never takes effect. **Corrected order**: `reason()` must distinguish two different things currently conflated into one `model` param:
   - a **true explicit override** (an actual @mention or task-envelope-specified model — rare, caller must opt in deliberately) — stays highest priority, unchanged.
   - the **ontology's `default_model`** (what `Pipeline.run()` passes today as a matter of course) — must now be checked *after* user provider config, not before.
   Concretely: check the local config file (e.g. `~/.still-i-rise/config/providers.json`, read fresh at call time, not cached) first; if it specifies a provider+key, use it (via `_resolve_endpoint()` for `openai/`/`groq/`/`mistral/`) regardless of `classification.default_model`; only fall through to `classification.default_model` → `MC_REASON_MODEL` → auto-detected local as today when no provider config is set. This requires a small signature/call-site change distinguishing "caller explicitly demanded this exact model" from "this is just the ontology's suggestion" — not just a new config file.
2. **Scope the provider dropdown to what's actually implemented**: **OpenAI, Groq, Mistral, or Local (default)** — not Claude/Gemini, since `_resolve_endpoint()` doesn't support them yet. Adding Anthropic/Gemini branches later is a small, mirror-pattern addition (a few lines each, matching the existing OpenAI/Groq/Mistral branches) but needs its own tests before being offered to a user — explicit backlog item, not promised in tomorrow's UI copy.
3. **Key verification before saving**: on submit, make one lightweight test call (e.g., a 1-token completion) to the chosen provider before writing the config.
   - Bad/invalid key → inline error ("This key didn't work — check it and try again"), nothing saved.
   - Network unreachable (not an auth failure) → save anyway, with an honest message ("Saved — will use local mode until we can reach [provider]"), distinct from a rejected key.
4. **Reversible**: a visible "Disconnect / go back to local-only" action (in the same screen, reachable again later, not just a one-time first-run choice) that deletes/resets the config file.
5. **First-run local-mode health check (new — this is the most likely real-world failure mode a non-technical user will hit)**: before defaulting to "Keep it fully local," ping `http://localhost:11434/api/tags` (Ollama's own API). If unreachable, do not silently let the user pick a broken default — show a warning with two clear options: "Start Ollama" (brief instructions) or "Connect an external provider instead." A teacher whose laptop rebooted and whose Ollama service didn't auto-start must not be met with silent empty responses after picking "local."
6. **Copy, in plain language, no jargon** (per UX review — avoid "regex/NER sanitizer," "socket monkey-patch," etc.): *"This runs on your own device by default — nothing you type leaves this computer. If you'd like faster or smarter answers, you can connect your own account with a provider like OpenAI or Groq. Even then, your personal privacy guard automatically removes names and other identifying details before anything is sent, and a digital firewall only ever allows connections to that provider's own official servers — nothing else."*
7. **Key storage/security (new, round-2 review)**: the config file holding the API key must be created with `0600` permissions on Unix (owner read/write only) and an equivalent restricted-ACL intent on Windows. The key must never be echoed back to the UI once saved (show a masked placeholder, not the value) and must never appear in application logs. "Disconnect" (point 4) must actually delete the key material from disk, not just mark it inactive.

### Gap 5b — Routing-misfire risk (named explicitly per review; was previously vague)
The documented `_rank_score()` coverage-bias bug (misrouted 2 of 3 Turn 21 demo queries) risks silently wrong answers for a user who can't tell right-domain from wrong-domain. Do **not** attempt the full cross-domain fix by tomorrow (known wide-blast-radius change, previously deferred).

**Fix, fully specified**:
- Env flag: `SIR_EDUCATION_BIAS=0.20` (matches the magnitude of the canvas runtime's existing active-canvas-domain bias pattern), applied at the same insertion point as that existing bias, in this fork's classify() call path only.
- Code comment required at the insertion point: `# TEMPORARY: workaround for _rank_score() coverage-bias (see SPEC_ONE_CLICK_LOCAL_APP_2026-07-14.md Gap 5b). Remove when the cross-domain fix ships.` — so this doesn't quietly become permanent, undocumented behavior.
- **Required test, not optional**: a golden-query check proving cross-domain decoy queries (plainly non-education questions) still do *not* get misrouted into an `LV-*` node because of the added bias — the fix must not trade "misses education queries" for "wrongly claims everything is an education query."

## 4. Explicit non-goals for tomorrow (backlog, not silently dropped)
- True native one-click packaging (Windows `.exe`/Mac `.app`/Android `.apk` via Play Store for Chromebook) with zero terminal step ever, including for Chromebooks *without* Crostini — the "most awesome" version; real, valuable, out of scope for tomorrow.
- Anthropic/Gemini endpoint support in `_resolve_endpoint()` — small addition, needs its own tests, not promised in tomorrow's provider dropdown (Gap 5a).
- Full `_rank_score()` engine-wide fix.
- Individual accounts/auth — single-user local install regardless of model choice.
- Any *new* governance/protection code (sanitizer, exit-gate firewall) — already built; scope here is wiring/config, not touching that layer.
- Mid-session provider switching without a restart, multi-file batch upload, non-PDF ingestion (.docx/.txt) — parser doesn't support them today; naming them as backlog rather than silently dropping.
- Automated regression harness for Gap 4's demo queries — backlog note: post-ship, convert §6 steps 6-8 into golden queries for this fork's own eval suite (same pattern as `golden_mc_v1.yaml`). Steps 1-5 test install/onboarding UX, not pipeline behavior, and stay manual.
- Slack bot wiring, Tier-2 admin tools (unchanged scope cut from Turn 22).
- A real safeguarding/home-visit ontology node + document ingestion (Turn 21 content gap).

## 5. Chromebook reality check
For a Chromebook **without** Crostini, there is currently no way to run anything local at all — the native-app path (§4) is the only real fix, and it's backlog. For a Chromebook **with** Crostini (common on newer education-model Chromebooks), `install.sh` already works today via the built-in Linux terminal app.

**New deliverable (per UX review)**: don't just note this limitation — ship a short `GETTING_STARTED.md` (or a section in the existing README) with the actual current ChromeOS steps (Settings → Advanced → Developers → "Turn on" Linux development environment), written for someone who's never done it, so a Chromebook-using teacher isn't handed a caveat with no path forward.

## 6. Test script

No terminal beyond the one install step, once Gaps 1-5b are closed:
1. **Gap 1 verification, not just "workflow ran green"**: in an environment with no local `dist/` present, run the actual public install command against the real cut release and confirm — via installer output, not assumption — that the **binary** path engaged (skipped git/pip entirely), not source-fallback. A local dev machine with a stray `dist/sir` already sitting around can make this look fixed when it isn't.
2. Run the install command once — confirm it ends with the app already open in a browser tab, nothing further typed.
3. Quit the app/reboot, then use the native launcher (Gap 2b) to bring it back — confirm zero terminal contact on second launch.
4. On first launch, confirm the local-vs-external choice screen (Gap 5a) appears. With Ollama intentionally stopped, confirm the "local isn't running" warning appears instead of a silent broken default (Gap 5a point 5).
5. Restart Ollama, confirm "Keep it fully local" now works normally.
6. Separately, pick "Connect a provider," enter a deliberately wrong API key — confirm a clear rejection message and that nothing is saved. Then enter a real key — confirm the test call succeeds, the choice is saved, and a real query routes externally (check `sanitizer/data/firewall_log.ndjson` for the logged, redacted outbound call; confirm a deliberately-planted PII string in the test query was redacted before send).
7. Click "Install app" in the browser address bar — confirm an app icon appears named "Still I Rise," not "Mission Canvas," in both the icon and the on-screen header/title.
8. Drag a real curriculum PDF onto the upload area — confirm it ingests with visible progress feedback and no terminal step. Separately, drag an oversized file and a non-PDF file — confirm both are rejected with a friendly message, not a crash.
9. Ask, with **no curriculum uploaded yet**: *"Can you help me differentiate this lesson for three levels?"* — expect the honest missing-data prompt (Gap 4), not a fabricated-looking generic answer. Then upload the relevant PDF and ask again — expect an actual 3-tier breakdown grounded in it.
10. Ask about a student **with no existing record**: *"This student isn't progressing, what tier of support should they be on?"* — expect the honest "I need an observation history first" response, not a guessed tier.
11. Ask: *"Group my class for a mixed-ability activity, but don't pair Amara with Kofi."* — expect conflict-aware groups honoring the exclusion (assumes a roster with tier assignments already exists).

If any of these return a generic, fabricated-looking, or off-topic answer instead of the specified honest fallback, that's the signal Gap 4's wiring or Gap 5b's routing bias needs another pass before this goes to real staff.

## 7. Approval needed before building
- Cutting the `v1.0.0` release tag (Gap 1) — the one action with an external, visible effect (public GitHub release artifact + CI minutes).
- Everything else in this spec (upload endpoint, native launcher, PWA branding, module wiring, provider-choice pipeline code, domain bias) is local code change only, no external effect.

## 8. Explicit scope of this document
Per operator instruction, **this is a spec-only deliverable**. No code has been written or changed as part of producing this document. The next step is an explicit operator decision on whether/when to execute this spec (possibly in a separate window), not automatic build start.

## 9. Reviewer disposition

### Round 2 (against v3 — all four reviewers: approve / approve-with-edits, no architectural blockers)

| ID | Finding | Disposition |
|---|---|---|
| C-1 | Gap 1's release-asset URL fix is structurally correct; keep the source-fallback-didn't-run test | Confirmed, no change — already in §6 step 1 |
| C-2 | "One-command" title correction is right | Confirmed, no change needed |
| C-3 | `Pipeline.run()` (`pipeline.py:651`) always passes `classification.default_model` as the explicit `model` param, which `reason()` treats as top priority — a provider-config check at the `MC_REASON_MODEL` tier would never fire | **Fixed** — Gap 5a point 1 rewritten: provider config now checked ahead of `classification.default_model`; true explicit overrides (@mention/task envelope) kept distinct and still highest priority |
| C-4 | RTI table should name the public `evaluate_rti_rules()` wrapper, not the private `_evaluate_rti_rules()` | **Fixed** — Gap 4's node-to-module table corrected |
| C-5 | `generate_from_documents()` silently falls back to template generation when retrieval is empty — contradicts the "upload curriculum first" honest-fallback requirement | **Fixed** — Gap 4 adds an explicit guard requirement: EXECUTE wrapper must check `ContentPack.source_mode` and route to the honest prompt instead of surfacing a `"generated"` pack, without modifying the module itself |
| C-6 | Provider key storage needs a security sentence (file perms, no echo, no logging, delete on disconnect) | **Fixed** — Gap 5a point 7 added |
| C-7 | Native launcher must be idempotent (don't double-start if port 7896 already serving; friendly failure if occupied by something else) | **Fixed** — added to Gap 2b |
| C-8 | Gap 5b is properly bounded (named flag, comment, decoy test) | Confirmed, no change needed |
| C-9 | PWA branding fix correctly edits source files, not just env vars | Confirmed, no change needed |
| C-10 | Test script now catches the major false-passes | Confirmed, no change needed |
| Gemini (round 2) | Full approval, all 32 round-1 items addressed; no new findings | Confirmed, no change needed |
| Mistral (round 2) | All 6 v3 changes independently re-verified against live code (installer URL, provider fix, native launcher, upload contract, module signatures, routing bias) | Confirmed, no change needed |
| Kiro (round 2) | Score 9/10, verdict approve. Non-blocking notes: macOS `.app` will trigger Gatekeeper warnings without code-signing (acceptable for known-audience personal walkthrough); assessment module's implicit ordering dependency on `LV-CUR-002` should be enforced by the EXECUTE wrapper (same fix as C-5 covers this); Gap 5b's decoy tests should be sourced from the existing gauntlet decoy pattern, 3-5 queries minimum | **Partially fixed** — C-5's guard also resolves the assessment-ordering note; Gatekeeper and decoy-test-sourcing notes are implementation-time guidance, not spec changes, recorded here for the builder |

### Round 1 (against v2)

Four independent reviews were run against v2 of this spec. Disposition of every finding:

| ID | Finding | Disposition |
|---|---|---|
| C-1 | Release binary URL points at `main`'s `dist/`, which release.yml never populates | **Fixed** — Gap 1 now specifies the correct GitHub Releases asset URL |
| C-2 | "One-click" overstates a terminal-required command | **Fixed** — retitled "one-command," native one-click named as explicit backlog |
| C-3 | `/api/provider` writing `providers.json` has no consumer in the pipeline | **Fixed** — Gap 5a now specifies the actual new read-path code needed |
| C-4 | Claude/Gemini are allowlisted/configured but not implemented in `_resolve_endpoint()` | **Fixed** — Gap 5a scoped to OpenAI/Groq/Mistral/Local only; Anthropic/Gemini moved to §4 backlog |
| C-5 | `/api/ingest` needs a real security spec, not "thin wrapper" | **Fixed** — Gap 2 now specifies size limit, type allowlist (PDF-only, matching actual parser support), temp-file lifecycle, error handling |
| C-6 | PWA branding fix needs to touch source files, not just env vars | **Fixed** — Gap 3 now specifies editing `static/manifest.json` and `static/index.html` directly |
| C-7 | EXECUTE step needs an explicit output-combination contract | **Fixed** — Gap 4 specifies execution point (post-CLASSIFY, pre-REASON) and that module output is primary, model text is wrapper-only |
| C-8 | Routing-bias fix should be named deployment config with a revert plan | **Fixed** — Gap 5b names the exact env var, value, code-comment convention, and requires a cross-domain-safety golden test |
| C-9 | Test script needs to verify the binary path against a real release, not a local `dist/` | **Fixed** — §6 step 1 |
| C-10 | Local-first framing / existing governance wiring is correctly described | Confirmed, no change needed |
| G-1 | Onboarding copy must avoid technical jargon | **Fixed** — Gap 5a includes exact plain-language copy |
| G-2 | No plan for restarting the app without a terminal after reboot/crash | **Fixed** — new Gap 2b (native launcher) |
| G-3 | Chromebook guidance should be a real walkthrough, not just a caveat | **Fixed** — §5 now requires a `GETTING_STARTED.md` deliverable |
| G-4 | Approve cutting the release tag to enable real binary-path testing | Accepted — reflected in §7's approval ask |
| M-1 – M-17 | Ground-truth verification of every "already true"/gap claim in v2 | All 20 items confirmed against the code; no corrections needed beyond what C-1/C-3/C-4/C-6 already surfaced |
| K-1 | Gap 4 under-specified: execution point, node-to-module map, missing-data handling | **Fixed** — full table + fallback contract added |
| K-2 | Upload route needs size/type/error/progress spec | **Fixed** — folded into Gap 2 (same underlying issue as C-5) |
| K-3 | Provider-choice screen needs bad-key/network/reversibility handling | **Fixed** — Gap 5a points 3-4 |
| K-4 | Routing-bias fix needs a named flag, value, and revert plan | **Fixed** — same fix as C-8 |
| K-5 | Test script is manual-only; note automation as backlog | **Fixed** — added to §4 non-goals |
| K-6 | Release tag format unspecified | **Fixed** — named `v1.0.0` |
| K-7 | No check for Ollama being down at first launch | **Fixed** — Gap 5a point 5, and §6 steps 4-5 |
