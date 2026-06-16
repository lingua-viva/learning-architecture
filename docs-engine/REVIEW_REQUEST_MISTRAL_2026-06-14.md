# Review Request — Mistral
## Role: Critical UX Practitioner + Blind Spot Catcher
## Date: 2026-06-14
## Context: MC standalone integration plan (7 phases), post-governance fix, pre-deploy

---

## Your Assignment

You are reviewing this as a **critical UX practitioner** and as the agent whose job is to **catch what the builders won't see**. The builders (Kiro, Claude, Codex) are deep in architecture, governance, and classification. They're solving engineering problems. Your job is to ask:

1. **What does a person actually experience when they use this?**
2. **What will confuse, frustrate, or block a real user?**
3. **What are we building that nobody asked for, and what are we NOT building that someone will need on day one?**
4. **Where is the gap between what we SAY the product does and what it ACTUALLY does when someone sits down with it?**

You are not here to validate the plan. You are here to stress-test it from the perspective of the three real humans who will use this:
- **Luis** (Tropical IT CEO, Argentine, 35, non-technical, runs a $35M hardware distribution company across 9 countries, wants to track 25K products without external software)
- **A teacher at Still I Rise** (works in a refugee camp in Kenya, has a phone, intermittent internet, speaks English or French, not technical, needs to help students learn)
- **A Mavens consultant** (Komodo Health, life sciences, works with PHI daily, uses Salesforce, needs AI that won't leak patient data, not an engineer)

---

## What to Review

### 1. The Integration Plan

Read: `/home/mical/fde/mission-canvas/docs/INTEGRATION_PLAN_KIRO_2026-06-14.md`

Ask:
- After all 7 phases complete, what can Luis ACTUALLY DO that he can't do today?
- What does the teacher in Nairobi see on their phone screen? Is it usable? Is it obvious?
- When the Mavens consultant types a question about a patient, what happens? Can they TRUST what happens?
- Is there any phase that builds something no real user will touch?
- Is there a phase MISSING that a real user would need on day one?

### 2. The Current Site/Surface

The live product: `https://missioncanvas.ai`

Current surfaces:
- CLI (`mc` commands) — works, power-user only
- Browser (local server mirrors CLI) — works, but positioned as CLI-mirror
- PWA — does not exist yet

Ask:
- If Luis visits missioncanvas.ai today, does he understand what this does for HIM?
- If a teacher opens this on their phone, what happens? Can they use it?
- Is "Governed Agent OS — AI for work that can't leave the room" meaningful to anyone outside this team?
- What's the first-time user experience? Is there onboarding? A tutorial? An empty state that guides?
- What happens when the system BLOCKS something (PII detected, query too sensitive)? Does the user understand WHY? Does it feel like protection or like a broken tool?

### 3. The Sanitizer UX

We just built comprehensive PII/PHI sanitization (Phase 0 complete). Every external call is filtered. But:

- When a user's query gets blocked, what do they SEE?
- When PII is redacted before an external call, does the user KNOW it happened?
- If the system blocks "My patient John Smith has cancer" — does the user get a helpful message or a cryptic error?
- Is there a way for the user to say "I know this is sensitive, proceed anyway with local-only processing"?
- The block signals include "client" and "patient" — for Komodo, these are EVERY query. Does the user experience feel broken when every query triggers governance? (Note: `PALETTE_HUB_BLOCK_SIGNALS` env var exists for per-deployment override, but that's config, not UX)

### 4. The Classification Engine

We improved classification from 20% to 55% tonight. But 45% of queries still misclassify.

- When the system classifies incorrectly, what does the user experience?
- Can the user correct a misclassification? ("No, this is about logistics, not finance")
- Is classification visible to the user at all? Should it be?
- If a query gets no confident match, what happens? Is the fallback graceful?

### 5. The Bridges (Phase 4)

7 communication bridges: telegram, email, slack, whatsapp, discord, signal, teams.

- Which of these do the three customers ACTUALLY use?
- Luis's team: WhatsApp (LATAM-native). Probably also email.
- Still I Rise: WhatsApp (Africa/LATAM). Maybe email. Not Slack or Discord or Teams.
- Komodo/Mavens: Slack or Teams (enterprise). Maybe email.
- Is building all 7 the right call, or should we build 3 (WhatsApp, email, Slack) and add the rest when asked?
- What's the UX of receiving an MC response via WhatsApp? Is it just text? Is there context? Can the user reply and continue the thread?

### 6. The Missions Engine (Phase 5)

Multi-step workflow orchestration.

- Can you explain what this IS in one sentence that Luis would understand?
- Can you explain it in one sentence the teacher would understand?
- Is this "create a project with steps and track progress"? Or something more complex?
- What does a mission LOOK LIKE in the browser? On mobile? In WhatsApp?
- Who creates missions — the system or the user? Both?

### 7. Offline / Mobile (Still I Rise Critical Path)

- If a teacher in Kakuma has no internet for 3 hours, what can they do?
- When connectivity returns, what happens? Is sync automatic? Does it feel seamless?
- How much storage does the PWA need on a phone with 32GB total (16GB taken by OS/apps)?
- Is voice input supported? (Many teachers may find typing laborious in a second language)

---

## What I Want From You

Not validation. Not "this looks great." I want:

1. **5 UX problems** that will frustrate real users on day one (prioritized by severity)
2. **3 missing pieces** that no phase addresses but a real user will need immediately
3. **2 things we're over-building** that could be simpler without losing value
4. **1 first-time user flow** — walk through what Luis does the first time he opens MC. Step by step. Where does he get stuck?
5. **1 trust moment** — the moment when the Mavens consultant decides "I trust this system with my patient data." What has to happen for that trust to form? Does the current design achieve it?

---

## Constraints on Your Review

- Don't review the code. Review the EXPERIENCE.
- Don't suggest architecture changes. Suggest INTERACTION changes.
- Assume the user is smart but busy. They won't read docs. They won't watch tutorials. They'll open it and expect to understand in 30 seconds.
- Be specific. "The onboarding is unclear" is not useful. "When Luis types his first query, nothing tells him whether it's being processed locally or sent to an external model — that's a trust violation for someone who chose MC because 'AI that never leaves the room'" IS useful.
- You can be harsh. The goal is to catch what we missed, not to be polite.

---

## Files to Read (in order)

1. `docs/INTEGRATION_PLAN_KIRO_2026-06-14.md` — the plan you're reviewing
2. `docs/HANDOFF_KIRO_2026-06-14.md` — what was built today (governance, classification, adapter)
3. `docs/CODEX_INSIDE_MC_ROADMAP.md` — the broader project scope
4. Visit `https://missioncanvas.ai` — experience the current site as a first-time user

---

## Respond To

Route your review to the bus as `mistral.community` or write directly to:
`/home/mical/fde/mission-canvas/docs/MISTRAL_UX_REVIEW_2026-06-14.md`

---

*Review requested by claude.analysis on behalf of the operator. 2026-06-14.*
