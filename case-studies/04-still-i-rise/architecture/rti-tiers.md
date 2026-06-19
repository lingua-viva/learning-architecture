# RTI 3-Tier System: Refugee & SLIFE Education Context

## Structural Check Before Proceeding

**Classification mismatch flagged:** This query was routed to MC-DEPLOY-005 (System Monitoring), but the artifact needed is an **educational intervention framework**, not a technical monitoring dashboard. The ontology's expected artifacts (dashboard, alert_rules, incident_log) map imperfectly here — I am reinterpreting them as: **tier decision framework** (≈ dashboard), **escalation/de-escalation rules** (≈ alert_rules), and **student progress log schema** (≈ incident_log). This reinterpretation is flagged explicitly.

**Dependency gap:** No prior paths exist at this node. No knowledge entries exist. External research was returned but contains a domain mismatch in its sources (NIST AI monitoring, LogicMonitor — not RTI literature). The Perplexity excerpt on refugee RTI is the primary usable input, and it explicitly notes its own thinness. I am marking all extrapolated claims below.

**One-way door check:** Tier 3 placement decisions are **partially irreversible** in practice — stigma, resource allocation, and parent/guardian trust are affected. Flag: escalation to Tier 3 requires human educator confirmation, not automated trigger alone.

**Suggests next:** MC-DEPLOY-004 and MC-DATA-001 — meaning this framework should feed into a data collection schema and a deployment/rollout plan. This artifact is designed to make those next nodes easier to execute.

---

# THE FRAMEWORK

---

## 0. Foundational Constraints (Apply Across All Tiers)

Before any tier logic runs, three conditions must be acknowledged:

**C1 — The Baseline Problem**
Students with interrupted formal education (SLIFE) frequently have no valid normed scores, no school records, and no language assessment history. All tier decisions during the first 6–8 weeks are therefore **provisional**. No permanent Tier 2 or Tier 3 placement should be made during this window. *(Source: Perplexity research excerpt, explicitly stated as a gap in primary literature.)*

**C2 — The Confound Stack**
Poor performance may reflect trauma response, language acquisition stage, cultural unfamiliarity with schooling conventions, or undetected learning difference — or any combination. The system must require **multi-source evidence** before escalation. Single-signal escalation is a known failure mode (maps to MC-DEPLOY-005's "missed incident" / "silent failure" modes — here meaning: misattributing language acquisition as learning disability, or vice versa).

**C3 — CEFR as the Common Language**
CEFR (Common European Framework of Reference) provides the shared vocabulary for tracking language development independent of grade-level norms. All tiers track CEFR can-do descriptors as a parallel strand to academic performance. CEFR progress informs — but does not solely determine — tier movement.

---

## TIER 1 — Universal Instruction

**Who:** All students, from day one.

**Design Principles:**
- Trauma-informed, low-threat learning environment by default
- Multimodal delivery: visual supports, manipulatives, body language, peer modeling
- Scaffolded task design: chunked instructions, visual sequences, reduced linguistic load
- No cold-calling; structured participation routines that allow non-verbal responses

**Progress Monitoring Frequency — Tier 1:**

| Strand | Method | Frequency |
|---|---|---|
| Academic performance | Curriculum-embedded tasks with rubric | Weekly, weeks 1–8; then biweekly |
| CEFR language development | Teacher-rated can-do descriptors (simplified set: 5–8 descriptors per band) | Every 3 weeks |
| Functional classroom indicators | Structured teacher observation log | Daily → weekly summary |
| Social-emotional indicators | Brief wellbeing check-in (visual scale, non-verbal options) | Daily |

**Teacher Observation Role at Tier 1:**
Teacher observation is the **primary signal**. Automated signals (attendance, task completion rates if digitally tracked) are **secondary** and can only flag for teacher review — never trigger tier movement alone.

---

## TIER 1 → TIER 2 ESCALATION

### Trigger Conditions

**Gate 0 — Timing Lock:**
No escalation before 6–8 week acclimatization period is complete, except in cases of acute safety concern. *(Rationale: language shock, trauma response, and school culture adjustment create false positives in weeks 1–5. Source: Perplexity excerpt.)*

**Gate 1 — Multi-Signal Threshold (at least 2 of 4 must be met, sustained over 4+ weeks after acclimatization):**

| Signal | Threshold | Evidence Type |
|---|---|---|
| Academic task performance | Persistent bottom 20–25% *relative to peers with similar time-in-country* on curriculum-embedded tasks | Graded rubrics, weekly samples |
| CEFR language progress | No observable can-do descriptor gain across 2 consecutive 3-week monitoring windows, while most similar peers show ≥1 gain | Teacher-rated can-do log |
| Task initiation | Consistent non-initiation on simplified tasks even with visual prompts and peer modeling, ≥3 days/week for 4 weeks | Daily observation log |
| Multistep direction following | Cannot follow 2-step directions even when chunked and illustrated, across multiple contexts | Structured observation |

**Gate 2 — Confound Elimination Check (required before escalation is confirmed):**
Educator team must document ruling out or accounting for:
- [ ] Recent trauma event or acute stressor (consult with social worker/counselor)
- [ ] Attendance below 80% (absences explain gaps before learning difference is assumed)
- [ ] Language acquisition stage (is CEFR progress simply slower, or absent?)
- [ ] Vision or hearing concern not yet screened
- [ ] Cultural unfamiliarity with task format (try format variation before escalating)

**Gate 3 — Human Confirmation:**
Escalation to Tier 2 requires sign-off from at least: classroom teacher + one additional (specialist, coordinator, or team lead). It is not automated.

**One-Way Door Rating: LOW** — Tier 2 escalation is reversible; de-escalation criteria defined below.

---

## TIER 2 — Targeted Small-Group Intervention

**Who:** Students meeting escalation criteria above. Groups of 3–5, matched by functional need (not age or grade level).

**Design Principles:**
- Heavy visual scaffolding: picture-supported task cards, visual schedules, graphic organizers
- Task decomposition by default: no multi-step task presented whole
- Work initiation support: teacher or aide physically cues initiation (point, gesture, paired start)
- Language-integrated: intervention targets both academic skill and CEFR language progression simultaneously
- Sessions run parallel to Tier 1 — student is not fully pulled from universal instruction

**Session Structure (recommended):**
- 3–4 sessions/week, 30–45 minutes each
- Session opening: visual schedule review + check-in (2 min)
- Core task: one focused skill, broken into ≤3 steps, with modeled example (20–25 min)
- Language moment: explicit CEFR can-do practice embedded in task (5–8 min)
- Closing: student self-assessment using visual scale (2 min)

**Progress Monitoring Frequency — Tier 2:**

| Strand | Method | Frequency |
|---|---|---|
| Targeted skill | Brief probe or work sample against specific objective | Every session (weekly summary) |
| CEFR can-do progress | Teacher-rated can-do descriptors, same simplified set | Every 2 weeks (increased from Tier 1) |
| Task initiation rate | Tally: initiated / did not initiate, per session | Every session |
| Tier 2 response | Rate of progress compared to entry-level baseline | Every 4 weeks, formal review |

**Teacher Observation Role at Tier 2:**
Observation becomes **structured and quantified** — not impressionistic. Initiation tallies, task completion rates, and language use observations are logged in a consistent format (see Incident Log Schema below). This creates the data trail needed for Tier 3 escalation decisions or de-escalation.

---

## TIER 2 → TIER 3 ESCALATION

### Trigger Conditions

**Gate 0 — Timing Lock:**
No Tier 3 escalation before 8–10 weeks of consistent Tier 2 intervention. Insufficient Tier 2 exposure is not the same as Tier 2 failure.

**Gate 1 — Non-Response Criteria (all of the following must be present):**

| Criterion | Threshold |
|---|---|
| Skill progress | No measurable progress on targeted skill after 8 weeks of consistent Tier 2 intervention (probe data flat or declining) |
| CEFR progress | No can-do descriptor gain across 3 consecutive 2-week windows despite language-integrated intervention |
| Initiation support | Continues to require physical/gestural cuing to initiate every session; no drift toward independent initiation |
| Peer comparison | Gap relative to lowest-performing Tier 2 peers is widening, not narrowing |

**Gate 2 — Confound Elimination (extended):**
Before Tier 3, team must additionally document:
- [ ] Formal vision and hearing screening completed
- [ ] Trauma/mental health consultation completed
- [ ] Home language literacy assessment attempted (even informally — can student read/write in L1?)
- [ ] Task format variation attempted and documented
- [ ] Attendance ≥80% during Tier 2 period (if not, Tier 2 must be re-attempted with attendance addressed first)

**Gate 3 — Human Confirmation (elevated):**
⚠️ **ONE-WAY DOOR WARNING — PARTIAL:** Tier 3 placement carries stigma risk, resource implications, and family relationship implications. Requires: classroom teacher + intervention specialist + school leadership + family/guardian notification and input. This is not automated under any circumstance.

---

## TIER 3 — Intensive Individualized Support

**Who:** Students who demonstrate non-response to Tier 2 after adequate exposure. Individualized 1:1 or 1:2.

**Design Principles:**
- Fully individualized learning plan (ILP) based on functional assessment, not normed scores
- Assessment is **dynamic**: what can the student do with support? (zone of proximal development focus)
- Home language integration where possible: bilingual support, L1-L2 bridging
- Trauma specialist involved in planning
- Family/guardian as active partners in plan — not just notified

**Progress Monitoring Frequency — Tier 3:**

| Strand | Method | Frequency |
|---|---|---|
| Individualized objectives | Criterion-referenced probes against ILP goals | Every session (daily/near-daily summary) |
| CEFR language | Can-do descriptors, extended set if student has reached A1+ | Weekly |
| Functional skill generalization | Does skill transfer to Tier 1 classroom context? | Bi-weekly observation in Tier 1 setting |
| Family input | Brief check-in (translated if needed) | Monthly minimum |
| Full plan review | Multi-party team review | Every 6–8 weeks |

**Teacher Observation Role at Tier 3:**
Observation is **diagnostic and relational**. The question shifts from "is the student responding?" to "what conditions support this specific student's access?" Qualitative observation is as important as quantitative probe data.

---

## DE-ESCALATION CRITERIA

*De-escalation is always the goal. The tier system should not be a one-way ratchet.*

### Tier 2 → Tier 1 (De-escalation from Tier 2)

Criteria for return to Tier 1 with monitoring:
- Targeted skill probes show consistent progress for 4+ consecutive weeks
- CEFR can-do descriptors: ≥2 gains within a monitoring window, approaching peer trajectory
- Task initiation: student independently initiates ≥70% of sessions without physical prompting
- No new confounds emerging

**Process:** 4-week gradual fade (reduce Tier 2 sessions from 4x → 2x → 1x/week while maintaining Tier 1 monitoring at elevated frequency). If regression occurs during fade, pause and re-evaluate — do not immediately re-escalate.

### Tier 3 → Tier 2 (De-escalation from Tier 3)

Criteria for step-down to small-group:
- ILP objectives showing consistent criterion-level performance (define criterion per objective)
- Evidence of skill generalization into Tier 1 setting observed ≥2 bi-weekly checks
- CEFR progress resumed (≥1 can-do gain per 2-week window for 4 consecutive windows)
- Family/guardian agreement

**Process:** 6-week transition — Tier 3 intensity reduces while Tier 2 group exposure increases. Maintain Tier 3 consultant check-in for 8 weeks post step-down.

---

## CEFR INTEGRATION SCHEMA

CEFR runs as a **parallel spine** through all three tiers — it is not a tier-specific tool.

**Simplified Can-Do Tracker (pre-A1 through A2, suitable for SLIFE/refugee contexts):**

| Band | Sample Descriptors Tracked |
|---|---|
| Pre-A1 | Can respond non-verbally to simple instructions; can match spoken words to pictures |
| A1 | Can use isolated words or formulaic phrases to communicate basic needs; can follow 1-step illustrated instructions |
| A1+ | Can produce short sentences with support; can understand simple questions in familiar contexts |
| A2 | Can participate in simple structured exchanges; can read short illustrated texts for gist |

**CEFR-to-Tier Decision Rules:**

- CEFR progress **alone** does not de-escalate or escalate — it is one strand in a multi-signal system
- CEFR stagnation in the context of other progress (academic skill moving, initiation improving) is **not** a Tier 2 trigger — language acquisition is not linear
- CEFR stagnation **combined** with academic non-response and initiation failure is a valid component of the escalation signal

**Teacher-Rated vs. Automated CEFR Signals:**
In fully digital contexts (tablet-based literacy tools, etc.), automated task-completion data can flag for teacher review. It cannot assign a CEFR rating. Teacher judgment on can-do descriptors remains the primary source.

---

## STUDENT PROGRESS LOG SCHEMA
*(Maps to MC-DEPLOY-005's "incident_log" artifact)*

```
STUDENT RECORD [de-identified ID]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Enrollment date:
Time-in-country at enrollment:
Home language(s):
L1 literacy status: [none / partial / functional]
Acclimatization period end date:
Current tier: [1 / 2 / 3]
Tier entry date:
Last tier review date:

CEFR STRAND
  Current estimated band:
  Last can-do assessment date:
  Descriptors achieved: [list]
  Descriptors in progress: [list]
  Progress rate: [gaining / stagnant / declining]

ACADEMIC STRAND
  Current targeted skill:
  Probe data (last 4 weeks): [scores/observations]
  Progress rate: [gaining / stagnant / declining]

INITIATION STRAND (Tier 2/3 only)
  Initiation rate this week: [X/Y sessions]
  Trend (4-week): [improving / stable / declining]

CONFOUND LOG
  Dates and outcomes of:
    Vision screen: 
    Hearing screen:
    Trauma/counselor consultation:
    Attendance rate (rolling 8 weeks):
    L1 literacy check:
    Format variation attempts:

ESCALATION/DE-ESCALATION HISTORY
  [Date | Direction | Signals | Decision-makers | Notes]

FAMILY CONTACT LOG
  [Date | Method | Summary | Language used]

NEXT REVIEW DATE:
```

---

## ALERT RULES (Failure Mode Prevention)
*(Maps to MC-DEPLOY-005's "alert_rules" artifact)*

| Alert Type | Trigger | Response |
|---|---|---|
| **Alert Fatigue Risk** (silent failure) | >30% of class in Tier 2 simultaneously | Review Tier 1 design — systemic issue, not individual. Do not escalate individuals; improve universal instruction first. |
| **Missed Incident Risk** (loud failure) | Student at Tier 1 with 3+ weeks of flat academic AND language probes AND attendance >80% | Flag for Gate 1 review — may have been missed |
| **False Positive Risk** | Escalation triggered in weeks 1–5 | Block: acclimatization lock not met. Return to Tier 1 

Most RTI work in refugee/SLIFE (Students with Limited or Interrupted Formal Education) contexts is adapted from general RTI/MTSS and language‑learner RTI, rather than being defined in a single authoritative framework, so some aspects below are extrapolated from broader RTI and CEFR practice rather than directly specified in primary sources.[1][2] What follows highlights where the research is thin or missing as well as a concrete design.

**1. Trigger conditions between tiers (with incomplete baselines)**  
In standard RTI, movement from Tier 1→2 is typically triggered by *multi‑step screening*: universal screening + classroom performance + progress‑monitoring data over several weeks.[2] However, refugee learners with interrupted schooling often lack valid normed baseline scores or recent schooling records; the literature stresses the need for “extended diagnostic periods” and qualitative data, but gives few operational thresholds.[2]  

A workable refugee‑context design, making these gaps explicit:  
- **Tier 1 → Tier 2 triggers**  
  - After an *initial 6–8 week acclimatization period* with trauma‑informed, scaffolded universal instruction, move a student to Tier 2 if at least two of the following hold, *relative to peers with similar time‑in‑country*:  
    - Persistent performance in the bottom ~20–25% of the class on **curriculum‑embedded tasks** in literacy and numeracy for 4+ weeks (e.g., cannot complete simplified tasks even with visuals and modeling).  
    - **CEFR‑aligned language tasks**: little or no observable progress on teacher‑rated can‑do descriptors from initial estimated pre‑A1/A1 band after 6–8 weeks of exposure, while most similar peers show at least one descriptor gain (e.g., from “can say isolated words” to “can use simple formulaic phrases”).  
    - **Functional indicators**: frequent task non‑initiation, inability to follow multistep directions even when chunked and supported with visuals, or severe work avoidance not explained by immediate psychosocial crisis (the latter requiring separate mental‑health response).  
  - Because norm‑referenced cut‑scores are unreliable for SLIFE, these are *local, cohort‑relative thresholds*; the gap in the literature is the lack of validated, refugee‑specific cutoffs or decision rules.  

- **
