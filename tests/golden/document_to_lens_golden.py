"""
Golden test set for the document-to-lens pipeline.

Hand-crafted expected results for:
1. Name matching (50 cases with edge cases)
2. Sentence classification (80 labeled sentences)
3. Section splitting (multi-student documents)

Each case has: input, expected output, difficulty tag.
Run with: python3 -m pytest tests/golden/document_to_lens_golden.py -v
"""

# ---------------------------------------------------------------------------
# GOLDEN SET 1: Name Matching
# ---------------------------------------------------------------------------
# Format: (document_name, roster_name, should_match: bool, difficulty)
#
# The roster stores names surname-first. Documents use various orderings.
# A match means the system correctly identifies them as the same person.

NAME_MATCH_CASES = [
    # --- Exact and reversed order ---
    ("Abigail Chang", "Chang Abigail", True, "reversed"),
    ("Miro Corazza", "Corazza Miro", True, "reversed"),
    ("Luca Scala", "Scala Luca", True, "reversed"),
    ("Aiken Boyce", "Boyce Aiken", True, "reversed"),
    ("Noemi Kleuser", "Kleuser Noemi", True, "reversed"),
    ("Midori Fujinaga", "Fujinaga Midori", True, "reversed"),
    ("Grey Muller", "Muller Grey", True, "reversed"),
    ("Elena Montemurro", "Montemurro Elena", True, "reversed"),
    ("Caleb Gerstein", "Gerstein Caleb", True, "reversed"),
    ("Rowan Linsley", "Linsley Rowan", True, "reversed"),

    # --- Exact match (same order) ---
    ("Chang Abigail", "Chang Abigail", True, "exact"),
    ("Boyce Aiken", "Boyce Aiken", True, "exact"),

    # --- First name only ---
    ("Abigail", "Chang Abigail", True, "first_name_only"),
    ("Miro", "Corazza Miro", True, "first_name_only"),

    # --- Nickname / diminutive ---
    ("Abby Chang", "Chang Abigail", True, "nickname"),
    ("Abi Chang", "Chang Abigail", True, "nickname"),
    ("Luca S.", "Scala Luca", True, "abbreviated"),
    ("M. Corazza", "Corazza Miro", True, "abbreviated"),

    # --- Typos (Levenshtein distance 1-2) ---
    ("Abigail Chnag", "Chang Abigail", True, "typo"),
    ("Abigal Chang", "Chang Abigail", True, "typo"),
    ("Coraza Miro", "Corazza Miro", True, "typo"),
    ("Scala Lucca", "Scala Luca", True, "typo"),

    # --- Accents ---
    ("Lucà Scala", "Scala Luca", True, "accent"),
    ("Noëmi Kleuser", "Kleuser Noemi", True, "accent"),

    # --- Should NOT match (negative cases — critical for safety) ---
    ("Abigail Johnson", "Chang Abigail", False, "wrong_person"),
    ("Chang Michael", "Chang Abigail", False, "same_surname_diff_person"),
    ("Progress Report", "Corazza Miro", False, "false_positive_header"),
    ("Learning Goals", "Scala Luca", False, "false_positive_header"),
    ("Student Profile", "Boyce Aiken", False, "false_positive_header"),
    ("International School", "Montemurro Elena", False, "false_positive_header"),
    ("Grade Three", "Gerstein Caleb", False, "false_positive_header"),
    ("", "Chang Abigail", False, "empty_input"),
    ("A B", "Chang Abigail", False, "too_short"),

    # --- Multi-word surnames ---
    ("Maria De Luca", "De Luca Maria", True, "multi_word_surname"),
    ("Giovanni Di Marco", "Di Marco Giovanni", True, "multi_word_surname"),

    # --- Case insensitive ---
    ("ABIGAIL CHANG", "Chang Abigail", True, "case"),
    ("abigail chang", "Chang Abigail", True, "case"),
    ("CORAZZA MIRO", "Corazza Miro", True, "case"),
]


# ---------------------------------------------------------------------------
# GOLDEN SET 2: Sentence Classification
# ---------------------------------------------------------------------------
# Format: (sentence, expected_field_id, difficulty)
#
# expected_field_id is one of the 10 lens profile fields, or "none".

SENTENCE_CLASSIFICATION_CASES = [
    # --- communication_and_language ---
    ("Demonstrates strong reading comprehension and can identify main ideas.",
     "communication_and_language", "clear"),
    ("Written expression is developing. Needs support with complex sentence structures.",
     "communication_and_language", "clear"),
    ("Reads aloud with appropriate intonation and expression.",
     "communication_and_language", "clear"),
    ("Can write short paragraphs using familiar vocabulary.",
     "communication_and_language", "clear"),
    ("Speaks in complete sentences during group discussions.",
     "communication_and_language", "clear"),
    ("Listening comprehension is strong in one-on-one settings.",
     "communication_and_language", "clear"),
    ("Spelling of irregular words needs attention.",
     "communication_and_language", "clear"),
    ("Uses context clues to decode unfamiliar words.",
     "communication_and_language", "clear"),
    ("Vocabulary acquisition is progressing steadily.",
     "communication_and_language", "clear"),
    ("Struggles to express ideas in writing independently.",
     "communication_and_language", "clear"),

    # --- learning_and_cognition ---
    ("Strong number sense and problem-solving skills.",
     "learning_and_cognition", "clear"),
    ("Understands basic addition and subtraction concepts.",
     "learning_and_cognition", "clear"),
    ("Can apply multiplication strategies independently.",
     "learning_and_cognition", "clear"),
    ("Mathematical reasoning is well above grade level expectations.",
     "learning_and_cognition", "clear"),
    ("Needs concrete manipulatives for multi-digit problems.",
     "learning_and_cognition", "clear"),
    ("Shows strong analytical thinking across subject areas.",
     "learning_and_cognition", "clear"),
    ("Learning new concepts quickly when presented visually.",
     "learning_and_cognition", "moderate"),
    ("Benefits from repeated practice to consolidate new skills.",
     "learning_and_cognition", "moderate"),

    # --- executive_functioning ---
    ("Needs support with task organization and time management.",
     "executive_functioning", "clear"),
    ("Benefits from visual schedules and step-by-step instructions.",
     "strategies_trialed", "clear"),  # This IS a strategy/accommodation, not EF itself
    ("Struggles to complete multi-step assignments independently.",
     "executive_functioning", "clear"),
    ("Can plan and organize short projects with minimal guidance.",
     "executive_functioning", "clear"),
    ("Often loses track of materials and homework.",
     "executive_functioning", "clear"),
    ("Self-regulation during transitions has improved significantly.",
     "executive_functioning", "moderate"),
    ("Needs reminders to start tasks and stay on track.",
     "executive_functioning", "clear"),

    # --- social_skills ---
    ("Collaborates well with peers during group work.",
     "social_skills", "clear"),
    ("Contributes actively to group discussions.",
     "social_skills", "clear"),
    ("Sometimes needs reminders to listen to others before speaking.",
     "social_skills", "clear"),
    ("Shows empathy toward classmates who are struggling.",
     "social_skills", "clear"),
    ("Builds positive relationships with both peers and adults.",
     "social_skills", "clear"),
    ("Prefers to work alone and resists group activities.",
     "social_skills", "clear"),
    ("Is a natural mediator in peer conflicts.",
     "social_skills", "clear"),

    # --- emotional_regulation ---
    ("Manages frustration well during challenging tasks.",
     "emotional_regulation", "clear"),
    ("Sometimes becomes overwhelmed during transitions.",
     "emotional_regulation", "clear"),
    ("Has developed strong coping strategies this semester.",
     "emotional_regulation", "clear"),
    ("Reacts strongly to unexpected changes in routine.",
     "emotional_regulation", "clear"),
    ("Shows growing emotional awareness and self-control.",
     "emotional_regulation", "clear"),
    ("Uses breathing exercises effectively when upset.",
     "emotional_regulation", "clear"),

    # --- physical_sensory_needs ---
    ("Fine motor skills are developing. Letter formation needs practice.",
     "physical_sensory_needs", "clear"),
    ("Handwriting is legible but slow.",
     "physical_sensory_needs", "clear"),
    ("Benefits from a sensory break every 30 minutes.",
     "physical_sensory_needs", "clear"),
    ("Gross motor coordination is strong for age.",
     "physical_sensory_needs", "clear"),

    # --- attendance_and_engagement ---
    ("95% attendance this semester.",
     "attendance_and_engagement", "clear"),
    ("Participates actively in all classroom activities.",
     "attendance_and_engagement", "clear"),
    ("Engagement drops during afternoon sessions.",
     "attendance_and_engagement", "clear"),
    ("Has been absent 12 days this term.",
     "attendance_and_engagement", "clear"),
    ("Shows strong motivation and enthusiasm for learning.",
     "attendance_and_engagement", "moderate"),

    # --- strategies_trialed ---
    ("Benefits from a visual schedule posted on the desk.",
     "strategies_trialed", "clear"),
    ("We have implemented a behavior chart with positive reinforcement.",
     "strategies_trialed", "clear"),
    ("Receives additional small-group reading support three times per week.",
     "strategies_trialed", "clear"),
    ("Occupational therapy referral has been initiated.",
     "strategies_trialed", "clear"),
    ("Uses a noise-canceling headset during independent work time.",
     "strategies_trialed", "clear"),

    # --- academic_strengths ---
    ("Excels in science and shows particular interest in ecosystems.",
     "academic_strengths", "clear"),
    ("Mathematics is a clear area of strength.",
     "academic_strengths", "clear"),
    ("Exceptional creative writing ability.",
     "academic_strengths", "clear"),
    ("Shows advanced understanding of historical concepts.",
     "academic_strengths", "clear"),
    ("Consistently performs above grade level in reading.",
     "academic_strengths", "clear"),

    # --- personal_strengths ---
    ("Natural leader who inspires classmates.",
     "personal_strengths", "clear"),
    ("Shows curiosity about science topics.",
     "personal_strengths", "clear"),
    ("Kind and empathetic classmate.",
     "personal_strengths", "clear"),
    ("Brings energy and enthusiasm to all activities.",
     "personal_strengths", "clear"),
    ("Shows persistence and does not give up easily.",
     "personal_strengths", "clear"),
    ("Has a wonderful sense of humor that brightens the classroom.",
     "personal_strengths", "clear"),

    # --- none (should NOT be classified) ---
    ("La Scuola International School.",
     "none", "boilerplate"),
    ("Grade 3 — Semester 2, 2025-2026.",
     "none", "boilerplate"),
    ("Teacher: Ms. Canu Fautré.",
     "none", "boilerplate"),
    ("This report reflects the student's progress this semester.",
     "none", "boilerplate"),
    ("Please contact the school office with any questions.",
     "none", "boilerplate"),
    ("Page 1 of 3.",
     "none", "boilerplate"),
    ("IB PYP Progress Report.",
     "none", "boilerplate"),

    # --- Ambiguous / hard cases ---
    ("Reads well but struggles with comprehension of abstract concepts.",
     "communication_and_language", "ambiguous"),
    ("Often helps other students understand difficult problems.",
     "social_skills", "ambiguous"),
    ("Needs more time to complete written assignments.",
     "executive_functioning", "ambiguous"),
    ("Strong oral presenter but avoids written work.",
     "communication_and_language", "ambiguous"),
]


# ---------------------------------------------------------------------------
# GOLDEN SET 3: Section Splitting (cross-contamination)
# ---------------------------------------------------------------------------

MULTI_STUDENT_REPORT = """
La Scuola International School — Grade 3 Progress Report

Chang Abigail

Reading: A2. Strong reading comprehension. Can identify main ideas.
Writing: A1+. Developing writer. Needs support with sentence structures.
Math: Accomplished. Strong number sense.
Social: Collaborates well with peers.
Attendance: 95% present.

Corazza Miro

Reading: A1. Building foundational reading skills.
Writing: A1. Emerging writer. Can write individual words and short phrases.
Math: Developing. Needs concrete manipulatives.
Social: Kind and empathetic classmate.
Executive: Needs support with organization.

Scala Luca

Reading: A2+. Advanced reader who enjoys chapter books.
Writing: A2. Creative writer with strong voice.
Math: Exemplary. Exceptional mathematical reasoning.
Personal: Natural leader. Shows curiosity about science.
"""

# Expected: each student's section contains ONLY their data
SECTION_SPLIT_EXPECTATIONS = {
    "s-chang": {
        "must_contain": ["Strong reading comprehension", "A1+", "95% present"],
        "must_not_contain": ["Building foundational", "Advanced reader", "Exemplary"],
    },
    "s-miro": {
        "must_contain": ["Building foundational", "empathetic classmate", "organization"],
        "must_not_contain": ["Strong reading comprehension", "Advanced reader", "95% present"],
    },
    "s-luca": {
        "must_contain": ["Advanced reader", "Exemplary", "Natural leader"],
        "must_not_contain": ["Strong reading comprehension", "Building foundational", "95% present"],
    },
}
