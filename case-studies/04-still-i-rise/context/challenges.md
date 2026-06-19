# Refugee Education Challenges — Design Constraints

**Status**: `observed` — from research and analogous contexts

---

## Six challenges that shape every design decision

### 1. Interrupted Education
Students arrive with no standardized starting point. A 12-year-old may have the reading level of a 7-year-old and the life experience of an adult. Grade-level assumptions are meaningless.

**Design implication**: Assessment must find what students CAN do, not what they can't. Mastery-based progression — students advance when they demonstrate competence, not by calendar. Gap detection identifies what's needed next, never what's "missing."

### 2. Multilingual Classrooms with No Common L1
A single classroom might include speakers of Somali, Swahili, Arabic, French, Tigrinya, Oromo — with instruction in English (Nairobi) or Spanish (Bogotá). Students are acquiring L2 while also learning academic content.

**Design implication**: CEFR framework is language-pair agnostic — it works for ANY L1 acquiring ANY L2. The Lingua Viva structure (communicative functions, thematic vocabulary, oral routines, chunking) transfers to any target language. Language progression must be tracked independently from content knowledge.

### 3. Teacher Burden in Extreme Contexts
Teachers are doing extraordinary work with limited resources. They cannot absorb additional complexity. Any system that adds work — even "useful" work — will be abandoned.

**Design implication**: Zero-sum complexity. Every tool must reduce burden, not add it. If we add curriculum tracking, we must eliminate an equivalent amount of manual documentation. The system serves teachers, never the reverse.

### 4. Trauma-Informed Education
Students have experienced war, displacement, family separation, loss. Assessment cannot feel like testing. The learning environment must be emotionally safe.

**Design implication**: Portfolio-based assessment, not standardized testing. Progressive disclosure — the system adapts to the student's emotional readiness. Self-assessment and narrative observation, not grades. The assessment philosophy from our prior work (honoring the whole child) applies directly.

### 5. Low and Variable Connectivity
Nairobi, Bogotá, Mumbai — internet reliability varies by campus, by day, by time of day. A system that requires constant cloud connectivity will fail.

**Design implication**: Local-first architecture. The system runs on-site hardware. Sync when connected, work offline when not. No cloud dependency for core functions.

### 6. Institutional Independence
Still I Rise refuses government and supranational funding. They will not adopt a vendor tool that creates dependency. Any technology must be owned by them.

**Design implication**: Open source. We deploy, they own. The knowledge compounds in their instance. When we step back, the system keeps working. No subscription, no vendor lock-in, no data leaving their control.
