[MC-WORK-001] | 86608ms

# MC REFLECT — Education System Architecture Review

**Node:** MC-WORK-001 | **Classification:** Scope Definition → Integration Risk Analysis
**Confidence:** 80% → I'm applying structural pressure to this; treat flagged risks as load-bearing

---

## STRUCTURAL CHECK BEFORE I RESPOND

The question is correctly framed as integration risk, not feature review. But the ontology points somewhere important: this query sits at the **boundary between MC-WORK-001 (Scope Definition) and MC-WORK-002/005 (likely Execution Planning and Risk)**. The assumptions_list artifact from scope definition hasn't been formally closed — which means some of what I'm about to surface as "untested assumptions" may actually be **untracked scope decisions** that were made implicitly. That's the first finding.

**Dependency chain concern:** If MC-WORK-001 hasn't produced a published convergence_brief, then MC-WORK-002 (whatever follows) is building on an informal baseline. Pilot failure is often a scope artifact, not a technical one.

---

## PART 1 — INTEGRATION RISKS (What could break at the seams)

These are risks at the **joints between components**, not within them.

---

### 1.1 Offline-First Sync ↔ RTI 3-Tier Gates

**The seam:** RTI gating decisions depend on current learner data. Offline-first means that data may be stale at the moment a gate decision is made.

**Specific failure mode:** A child is assessed offline at Tier 1. The device syncs three days later. During those three days, a teacher makes a Tier 2 intervention decision based on the last-synced state — which is now wrong. The gate fires on ghost data.

**What makes this loud vs. silent:** This is a **silent failure**. The teacher doesn't know the gate fired on stale data. The intervention log looks clean. Only a data audit would catch it.

**Risk rating:** High. RTI integrity depends on temporal accuracy. Offline-first and time-sensitive clinical gates are architecturally in tension.

**Mitigation question (unanswered):** Is there a timestamp-aware gate logic that refuses to fire a tier transition until sync is confirmed within a defined window? If not, this needs to be designed, not assumed.

---

### 1.2 Differentiated Content Packs ↔ Offline-First Sync

**The seam:** Content packs are presumably versioned and pushed. Offline devices may be running pack version N while the curriculum has moved to N+1.

**Specific failure mode:** A teacher assigns a task from a lesson they saw in a training. The device runs an older pack. The task doesn't exist or has different scaffolding. The teacher's mental model and the device's state are misaligned. Trust in the system erodes.

**Secondary failure:** If packs are large and sync windows are narrow (refugee school bandwidth reality), pack updates may fail silently or partially. A partial pack is potentially worse than an old complete pack — some content is missing, some is present, no indication to the teacher which is which.

**Risk rating:** High. Content version drift is a known EdTech failure pattern in low-connectivity deployments.

**Mitigation question (unanswered):** What is the pack integrity check at sync time? Is partial sync detectable and rolled back? Is the teacher shown pack version explicitly?

---

### 1.3 Speech-to-Text Observation ↔ Refugee School Environment

**The seam:** Speech-to-text performance degrades with background noise, accent variation, and low-resource languages. Refugee schools are frequently multilingual, crowded, and physically loud.

**Specific failure mode (triple):**
- **Acoustic:** Open classrooms, corrugated roofing, adjacent classes — SNR (signal-to-noise ratio) makes transcription unreliable.
- **Linguistic:** If the STT model was trained primarily on majority-language data, it will perform worse on the specific languages spoken in this context. This is not a minor performance dip — it can be a failure condition.
- **Trust collapse:** Teachers who use STT observations three times and get garbled output stop using it. The observation artifact drops out of the workflow entirely. You've lost the feedback loop the whole RTI system depends on.

**Risk rating:** Critical. This is the highest single-component risk in the architecture. STT is the observation capture mechanism. If it fails, the data pipeline feeding RTI gates is broken at the source.

**Mitigation question (unanswered):** Has the STT model been tested on the specific language profile of the target school? Is there a fallback observation capture method (structured form, voice memo with manual review)?

---

### 1.4 Parent Artifacts ↔ Parent Literacy and Device Access

**The seam:** Parent artifacts (presumably take-home materials, reports, engagement prompts) assume a minimum parent literacy level and some form of access — physical pickup, digital delivery, or both.

**Specific failure mode:** In many refugee contexts, parents are working multiple jobs, may be in resettlement processing, or may themselves have interrupted schooling. An artifact system designed for engaged middle-class parents becomes an unused subsystem in this environment. Worse: if RTI tier decisions are supposed to be communicated to parents as part of the intervention loop, and parents don't engage, the loop is broken.

**Secondary failure:** If parent artifacts are digitally delivered and require a parent device/app, you've added a dependency on parent technology access that may not have been scoped. This is a classic scope creep via untracked ask — the failure mode your node's own ontology flags.

**Risk rating:** Medium-High. Not an immediate pilot-killer, but a systemic gap that will appear in month 2-3 of a pilot when engagement data is reviewed.

---

### 1.5 RTI 3-Tier Gates ↔ Teacher Training and Cognitive Load

**The seam:** RTI as a framework requires teachers to understand what the tiers mean, when to act, and what the intervention looks like at each tier. The system can surface a gate; it cannot ensure the teacher knows what to do when it fires.

**Specific failure mode:** The system correctly identifies a Tier 2 learner. The teacher has had one training session on RTI. The recommended intervention requires differentiated small-group instruction with specific scaffolding materials. The teacher has 45 students, no teaching assistant, and five minutes between lessons. The gate fires. Nothing happens. The system logs a Tier 2 classification. The child receives no different treatment.

**This is the most dangerous kind of failure:** The data looks like the system is working. The RTI rates look reasonable. The intervention rates show action. But the interventions are not being executed faithfully. A pilot review at month 6 will show no learning gain differential between Tier 2 and Tier 1 students, and the conclusion drawn may be "RTI doesn't work here" rather than "RTI was never implemented as designed."

**Risk rating:** High. Fidelity monitoring is required, not optional.

---

## PART 2 — UNTESTED ASSUMPTIONS

These are the load-bearing beliefs that have not been validated by evidence from this context.

| # | Assumption | Why It's Load-Bearing | How to Test It |
|---|---|---|---|
| A1 | Devices will sync often enough to keep RTI data current | The entire clinical decision loop depends on this | Measure actual sync frequency in a comparable site for 2 weeks before pilot |
| A2 | STT accuracy is sufficient in target language(s) and acoustic environment | STT is the primary observation input | Run STT accuracy test in the physical classroom before pilot launch |
| A3 | Teachers have sufficient RTI conceptual fluency to act on gate signals | Gate signals are useless without fidelity of response | Administer a structured fidelity observation in training week |
| A4 | Parents can and will engage with artifacts | Parent loop closes the RTI circuit | Interview 10 parents before designing artifact format and delivery mechanism |
| A5 | Content packs cover the language of instruction at the school | Mismatch here is an immediate usability failure | Confirm language of instruction, script, and literacy baseline before pack selection |
| A6 | The RTI tier thresholds are calibrated for this population | Thresholds from normative data on other populations may over- or under-identify | Plan a calibration phase in pilot month 1 before using gate data for decisions |
| A7 | Devices are charged, maintained, and present in classrooms | Offline-first is only useful if devices are consistently in use | Conduct a device utilization audit in week 1 of pilot |
| A8 | School leadership will protect pilot time and space | Refugee schools operate under extreme resource pressure; pilot activities will be displaced unless protected | Get written commitment from school leadership before pilot launch, not during |

---

## PART 3 — WHAT WOULD CAUSE PILOT FAILURE

Ranked by probability × impact. These are the scenarios I'd bet on.

---

### FAILURE MODE 1 — The Observation Pipeline Breaks (Probability: High)

STT performs poorly → teachers stop using it → observation data drops to zero → RTI gates have no input → the entire system operates on no new data after week 3. The system appears to be running. Nothing is actually happening.

**Trigger condition:** STT accuracy below ~75% on first real classroom use.

**Leading indicator:** Check STT usage rates weekly. If usage drops more than 30% from week 1 to week 3, the observation pipeline is failing.

---

### FAILURE MODE 2 — Sync Debt Accumulates to the Point of Data Corruption (Probability: Medium-High)

Devices don't sync for 5+ days. Sync queue grows. On reconnection, conflict resolution logic (if it exists) makes bad merges. Assessment records are duplicated or overwritten. A child who was correctly Tier 2 is now Tier 1 in the system. The teacher is confused. Trust in data drops.

**Trigger condition:** Connectivity at the school is worse than assumed, or sync protocol doesn't handle large queue sizes gracefully.

**Leading indicator:** Monitor sync latency and queue depth from day 1. Set an alert threshold at 72 hours without sync.

---

### FAILURE MODE 3 — RTI Without Fidelity Produces Null Results and Gets Blamed on the Model (Probability: High)

Teachers know the RTI language but not the practice. Interventions are labeled but not executed. Month 4 learning data shows no effect. The narrative becomes "the system doesn't work for refugee learners," which is both wrong and damaging for future deployments.

**Trigger condition:** No fidelity monitoring built into the pilot design.

**Prevention:** Fidelity observations must be a designed pilot activity, not an afterthought. Observe 20% of Tier 2 intervention sessions in months 1-2.

---

### FAILURE MODE 4 — Teacher Turnover Voids Training Investment (Probability: Medium, Context-Dependent)

Refugee school teacher turnover is often high. If two of five trained teachers leave in month 2, the remaining teachers carry excess load and the new teachers have no training. The pilot limps forward on institutional memory.

**Trigger condition:** No built-in teacher onboarding mechanism for mid-pilot replacement.

**Prevention:** Document training in a format new teachers can self-administer. Don't rely on cohort training as the only knowledge transfer mechanism.

---

### FAILURE MODE 5 — Scope Creep via Stakeholder Requests Dilutes Focus (Probability: High — this is a named failure mode for MC-WORK-001)

Once the pilot is live, NGO partners, ministry observers, and school leadership will request additions: "Can we add attendance tracking?" "Can we generate a report for our donor?" Each request is reasonable in isolation. Collectively they overload the teaching staff and the development team. The pilot's ability to measure what it was designed to measure degrades.

**Prevention:** The convergence_brief must exist and be signed before pilot launch. Scope additions during pilot must go through a named change control process. This is not bureaucracy — it's survival.

---

## PART 4 — REFLECTION FINDINGS (System Meta-Layer)

*Per REFLECT mode: what this session surfaces about the architecture's knowledge state.*

**Gap signal:** No knowledge entries exist for MC-WORK-001 in this domain. Two prior paths completed at 95% and 80% confidence but left no reusable knowledge artifacts. This means the next similar query starts from scratch. **Recommendation (Tier 3, auto-apply):** The assumptions_list and integration risk patterns from this session should be stored as a KL entry tagged to refugee-context EdTech deployments.

**Confidence calibration concern:** The 80% classification confidence on this query is appropriate but should note that "scope definition" is underselling what this query actually is — it's a pre-pilot risk audit. If the ontology classified this as scope definition, it may have routed away from a more specific risk-analysis node. **Recommendation (Tier 2, review needed):** Consider whether integration risk review deserves its own node signal distinct from general scope definition, particularly for deployments in constrained environments.

**Untested assumption about the architecture itself:** The five components (offline-first, RTI gates, content packs, STT, parent artifacts) were designed as a coherent system, but this reflection reveals that their **integration points were not explicitly specified in scope**. The non_goals artifact from MC-WORK-001 should have named what the integration layer was NOT responsible for. If it doesn't exist or doesn't address sync conflict resolution, gate data freshness, and STT fallback — those gaps are live risks right now.

---

## WHAT TO DO NEXT

| Action | Owner | When | Governance |
|---|---|---|---|
| Run STT accuracy test in physical classroom before pilot | Technical lead | Pre-pilot | Tier 3 |
| Publish convergence_brief with signed scope baseline | Project lead | Immediately | Tier 2 |
| Design fidelity observation protocol for RTI interventions | Curriculum lead | Pre-pilot | Tier 2 |
| Confirm language of instruction and run pack audit | Content lead | Pre-pilot | Tier 3 |
| Set sync monitoring alerts at 72-hour threshold | Technical lead | Pilot day 1 | Tier 3 |
| Interview 10 parents on artifact access before designing delivery mechanism | Field team | Pre-pilot | Tier 3 |
| Get written leadership commitment on pilot time protection | Project lead | Before pilot launch | Tier 2 |
| Store this risk analysis as KL entry for future deployments | MC system | Post-session | Tier 3 |

---

**Bottom line:** The architecture is coherent in design but has at least three critical integration seams that are untested against the actual deployment context. The highest-risk single point is the STT observation pipeline — if that fails, the entire data loop fails silently. The highest-risk systemic failure is RTI without fidelity monitoring producing null results that get attributed to the wrong cause. Neither failure is inevitable. Both require deliberate pre-pilot action to prevent.
