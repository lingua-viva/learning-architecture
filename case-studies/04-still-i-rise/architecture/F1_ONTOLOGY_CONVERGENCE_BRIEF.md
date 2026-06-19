[MC-DATA-002] Taxonomy / Ontology Design | 0.85 | 73491ms

# IB Education Ontology — Refugee & Vulnerable Children School System
## Node Definitions YAML

```yaml
# =============================================================================
# IB EDUCATION ONTOLOGY — REFUGEE & VULNERABLE CHILDREN SCHOOL SYSTEM
# Version: 1.0.0
# Replaces: 137 enterprise nodes
# Preserves: 31 MC-native core nodes (MC-GOV, MC-WORK, MC-DATA, MC-DEPLOY, MC-LEGAL)
# Preserves: 6 intents (unchanged)
# New domains: LV-CUR, LV-STU, LV-TCH, LV-PAR, LV-ASS, LV-INF
# Serves: 7 schools (6 refugee campuses + 1 Italian immersion)
# Users: Teachers, Administrators, Students
# =============================================================================

meta:
  ontology_name: "LearnVerse IB Education Ontology"
  version: "1.0.0"
  created: "2025-01"
  replaces_node_count: 137
  total_new_nodes: 106
  preserved_mc_nodes: 31
  total_system_nodes: 137
  school_contexts:
    - id: "CAMPUS-REF-01"
      type: refugee_campus
      language_primary: "English"
    - id: "CAMPUS-REF-02"
      type: refugee_campus
      language_primary: "Arabic"
    - id: "CAMPUS-REF-03"
      type: refugee_campus
      language_primary: "Somali"
    - id: "CAMPUS-REF-04"
      type: refugee_campus
      language_primary: "Amharic"
    - id: "CAMPUS-REF-05"
      type: refugee_campus
      language_primary: "Swahili"
    - id: "CAMPUS-REF-06"
      type: refugee_campus
      language_primary: "Dari"
    - id: "CAMPUS-ITA-01"
      type: italian_immersion
      language_primary: "Italian"
      language_secondary: "English"
  user_types:
    - teacher
    - administrator
    - student

# =============================================================================
# DOMAIN REGISTRY
# =============================================================================

domains:
  LV-CUR:
    name: "Curriculum"
    description: "IB curriculum planning, unit design, differentiation, and cross-campus normalization"
    owner: "Curriculum Coordinator"
    applicable_campuses: all

  LV-STU:
    name: "Student"
    description: "Student learning journeys, AI awareness, guided projects, capstone builds"
    owner: "Student Support Lead"
    applicable_campuses: all

  LV-TCH:
    name: "Teacher"
    description: "Lesson planning, observation capture, RTI intervention, progress tracking"
    owner: "Instructional Coach"
    applicable_campuses: all

  LV-PAR:
    name: "Parent"
    description: "Family engagement, communication, progress sharing for refugee contexts"
    owner: "Community Liaison"
    applicable_campuses: all

  LV-ASS:
    name: "Assessment"
    description: "Rubric templates, grading scales, IB criterion alignment, portfolio review"
    owner: "Assessment Coordinator"
    applicable_campuses: all

  LV-INF:
    name: "Infrastructure"
    description: "Cross-campus dashboards, onboarding, data normalization, system configuration"
    owner: "Systems Administrator"
    applicable_campuses: all

# =============================================================================
# SIGNAL INDEX
# =============================================================================

signal_index:

  # --- TEACHER SIGNALS ---
  teacher_signals:
    lesson_planning:
      - "lesson plan"
      - "unit plan"
      - "IB unit"
      - "central idea"
      - "lines of inquiry"
      - "transdisciplinary"
      - "differentiate lesson"
      - "scaffold"
      - "modify for ELL"
      - "language of instruction"
    observation:
      - "observation"
      - "anecdotal note"
      - "running record"
      - "student observation"
      - "capture observation"
      - "document behavior"
      - "learning evidence"
    differentiation:
      - "differentiate"
      - "accommodation"
      - "modification"
      - "tiered activity"
      - "gifted"
      - "struggling learner"
      - "ELL support"
      - "trauma-informed"
      - "language barrier"
    rti:
      - "RTI"
      - "response to intervention"
      - "intervention plan"
      - "tier 1"
      - "tier 2"
      - "tier 3"
      - "learning gap"
      - "reading intervention"
      - "math intervention"
      - "support plan"
    progress_tracking:
      - "progress"
      - "track learning"
      - "student growth"
      - "learning goals"
      - "benchmark"
      - "proficiency"
      - "learning continuum"
      - "IB learner profile"

  # --- ADMINISTRATOR SIGNALS ---
  admin_signals:
    rubric_templates:
      - "rubric"
      - "rubric template"
      - "scoring guide"
      - "criterion"
      - "IB rubric"
      - "assessment rubric"
      - "create rubric"
    grading_scales:
      - "grading scale"
      - "grade"
      - "IB grades"
      - "1-7 scale"
      - "achievement level"
      - "grade boundary"
      - "stanine"
    curriculum_normalization:
      - "normalize"
      - "align curriculum"
      - "cross-campus"
      - "scope and sequence"
      - "curriculum map"
      - "vertical alignment"
      - "horizontal alignment"
    onboarding:
      - "onboard"
      - "new teacher"
      - "new student"
      - "enrollment"
      - "intake"
      - "refugee intake"
      - "setup account"
      - "new campus"
    dashboard:
      - "dashboard"
      - "report"
      - "analytics"
      - "cross-school data"
      - "campus comparison"
      - "attendance"
      - "enrollment data"

  # --- STUDENT SIGNALS ---
  student_signals:
    ai_awareness:
      - "AI"
      - "artificial intelligence"
      - "what is AI"
      - "machine learning"
      - "AI ethics"
      - "AI activity"
      - "responsible AI"
      - "digital citizenship"
    guided_projects:
      - "project"
      - "guided project"
      - "inquiry project"
      - "exhibition"
      - "PYP exhibition"
      - "community project"
      - "MYP project"
    capstone:
      - "capstone"
      - "extended essay"
      - "personal project"
      - "final project"
      - "showcase"
      - "portfolio"
      - "DP project"

# =============================================================================
# NODE DEFINITIONS
# =============================================================================

nodes:

  # ===========================================================================
  # DOMAIN: LV-CUR — CURRICULUM
  # ===========================================================================

  - id: "LV-CUR-001"
    name: "IB Unit Planner"
    domain: "LV-CUR"
    user_types: [teacher, administrator]
    description: >
      Generates and stores IB Programme of Inquiry unit plans including central idea,
      lines of inquiry, transdisciplinary themes, learner profile attributes, and
      key concepts. Adapted for multilingual and refugee contexts.
    produces:
      - ib_unit_plan_document
      - central_idea_statement
      - lines_of_inquiry_list
      - transdisciplinary_theme_alignment
      - learner_profile_connections
      - key_concept_map
    requires:
      - grade_level
      - subject_area
      - campus_context
      - language_of_instruction
    suggests_next:
      - "LV-CUR-002"  # Differentiation Layer
      - "LV-CUR-003"  # Scope and Sequence Mapper
      - "LV-TCH-001"  # Lesson Plan Builder
      - "LV-ASS-001"  # Assessment Design Node
    failure_modes:
      silent:
        - description: "Unit plan generated without trauma-informed language considerations"
          detection: "Trauma-informed flag not triggered for refugee campus"
          mitigation: "Inject campus_context check before generation"
        - description: "Central idea misaligned with IB transdisciplinary framework"
          detection: "IB framework validator returns null match"
          mitigation: "Require IB theme selection before proceeding"
      loud:
        - description: "Conflicting programme level — PYP unit routed to MYP node"
          detection: "Programme level mismatch error at routing"
          mitigation: "Enforce programme_level as required field"
    success_conditions:
      - "Unit plan contains all 6 IB planner sections"
      - "Language of instruction matches campus configuration"
      - "Trauma-informed language flag evaluated"
      - "Learner profile attributes mapped to at least 2 attributes"
    blocks_external: false
    tags: [ib, unit_plan, curriculum, pyp, myp, dp]

  - id: "LV-CUR-002"
    name: "Differentiation Layer"
    domain: "LV-CUR"
    user_types: [teacher]
    description: >
      Applies differentiation strategies to any curriculum artifact. Produces tiered
      activities, scaffolds for ELL students, accommodations for trauma-affected
      learners, and modifications for learners with identified needs. Aware of
      refugee context and limited prior schooling backgrounds.
    produces:
      - tiered_activity_set
      - ell_scaffold_document
      - trauma_informed_modification
      - visual_language_support
      - simplified_instruction_set
      - enrichment_extension_tasks
    requires:
      - base_curriculum_artifact
      - learner_profile_data
      - language_proficiency_level
      - identified_needs_flags
    suggests_next:
      - "LV-TCH-003"  # RTI Intervention Planner
      - "LV-ASS-003"  # Accessible Assessment Builder
      - "LV-STU-001"  # Student Learning Profile
    failure_modes:
      silent:
        - description: "Differentiation applied without checking prior schooling gaps"
          detection: "Prior_schooling_flag missing from learner profile"
          mitigation: "Default to 'interrupted schooling' for refugee campus profiles"
        - description: "ELL scaffold generated in wrong language"
          detection: "Output language mismatch with campus language config"
          mitigation: "Pull language_of_instruction from campus context"
      loud:
        - description: "Tiered activities conflict — same content at all tiers"
          detection: "Tier similarity score above 0.9"
          mitigation: "Enforce cognitive demand differentiation check"
    success_conditions:
      - "Minimum 3 tiers produced for each activity"
      - "ELL scaffold present when ELL flag is true"
      - "Trauma-informed language review passed"
      - "Visual support included for pre-literate learners when flagged"
    blocks_external: false
    tags: [differentiation, ell, scaffold, trauma_informed, tiered]

  - id: "LV-CUR-003"
    name: "Scope and Sequence Mapper"
    domain: "LV-CUR"
    user_types: [administrator, teacher]
    description: >
      Maps curriculum scope and sequence across grade levels and across campuses.
      Normalizes IB programme requirements with the reality of interrupted schooling
      and multi-age classrooms common in refugee school contexts.
    produces:
      - vertical_alignment_map
      - horizontal_alignment_map
      - curriculum_gap_report
      - cross_campus_scope_document
      - multi_age_grouping_suggestion
    requires:
      - grade_levels_served
      - subject_areas
      - campus_list
      - programme_level
    suggests_next:
      - "LV-CUR-001"  # IB Unit Planner
      - "LV-INF-004"  # Cross-Campus Dashboard
      - "LV-ASS-002"  # Grading Scale Manager
    failure_modes:
      silent:
        - description: "Scope map generated without accounting for multi-age classrooms"
          detection: "Multi-age flag absent in refugee campus config"
          mitigation: "Auto-inject multi_age_classroom=true for refugee campuses"
      loud:
        - description: "Horizontal and vertical maps contradict each other"
          detection: "Alignment conflict flag raised by validation engine"
          mitigation: "Require conflict resolution step before publishing"
    success_conditions:
      - "All 7 campuses represented in cross-campus map"
      - "Gap report identifies at least programme-level mismatches"
      - "Italian immersion campus has dual-language scope column"
    blocks_external: false
    tags: [scope_sequence, alignment, curriculum_map, cross_campus]

  - id: "LV-CUR-004"
    name: "Curriculum Normalization Engine"
    domain: "LV-CUR"
    user_types: [administrator]
    description: >
      Standardizes curriculum documents across all 7 campuses to a common IB-aligned
      format. Handles translation normalization, grading scale reconciliation, and
      programme terminology alignment. Critical for cross-campus reporting integrity.
    produces:
      - normalized_curriculum_document
      - translation_alignment_log
      - terminology_glossary
      - cross_campus_alignment_certificate
    requires:
      - raw_curriculum_documents
      - target_language_standards
      - ib_programme_framework
      - campus_language_configs
    suggests_next:
      - "LV-INF-004"  # Cross-Campus Dashboard
      - "LV-ASS-002"  # Grading Scale Manager
      - "LV-CUR-003"  # Scope and Sequence Mapper
    failure_modes:
      silent:
        - description: "Italian immersion terminology not flagged for dual normalization"
          detection: "Single-language normalization applied to bilingual campus"
          mitigation: "Detect campus_type=italian_immersion and fork normalization path"
      loud:
        - description: "Conflicting grade descriptors across campuses after normalization"
          detection: "Grade descriptor conflict report non-empty"
          mitigation: "Escalate to administrator for manual reconciliation"
    success_conditions:
      - "All documents share common IB terminology set"
      - "Zero untranslated terms in output"
      - "Italian immersion campus receives bilingual normalized output"
    blocks_external: false
    tags: [normalization, curriculum, cross_campus, translation, ib]

  - id: "LV-CUR-005"
    name: "Transdisciplinary Theme Classifier"
    domain: "LV-CUR"
    user_types: [teacher, administrator]
    description: >
      Classifies learning activities, units, and student projects against IB
      transdisciplinary themes. Particularly tuned for refugee and displacement
      contexts where themes like 'Sharing the Planet' and 'Who We Are' carry
      specific pedagogical weight.
    produces:
      - theme_classification_result
      - theme_connection_rationale
      - cross_theme_link_map
    requires:
      - content_artifact
      - programme_level
    suggests_next:
      - "LV-CUR-001"  # IB Unit Planner
      - "LV-STU-003"  # Guided Project Launcher
    failure_modes:
      silent:
        - description: "Theme misclassified due to cultural context gap"
          detection: "Low confidence score on refugee-context content"
          mitigation: "Flag for teacher review when confidence below 0.75"
      loud:
        - description: "Content classified under two conflicting themes"
          detection: "Dual-theme conflict raised"
          mitigation: "Present both options to teacher for selection"
    success_conditions:
      - "Classification confidence above 0.75"
      - "Rationale statement generated for each classification"
    blocks_external: false
    tags: [transdisciplinary, ib_themes, classification, pyp]

  - id: "LV-CUR-006"
    name: "
