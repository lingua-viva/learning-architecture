"""Safeguarding indicator taxonomy — the single source for every detector.

Before 2026-09-03 this repository carried THREE independent safeguarding
vocabularies that did not agree with each other:

  1. safeguarding.py::classify_severity        RED/AMBER/GREEN tiers, EN + IT
  2. docpipe/lens_extract.py::_is_red_safeguarding   a separate 10-word English
     regex, and the gate that decides whether content is routed to the
     restricted log or into the student's ORDINARY lens
  3. education/observation_capture.py          a weighted advisory suggester

Measured consequence: an Italian disclosure ("il bambino ha subito abusi in
casa") passed (2) and was written into the child's normal record, while its
English twin was correctly routed to restricted. Each detector also knew things
the others did not -- (2) carried self-harm and suicide terms that (1) had never
had in either language.

This module holds the tiers once. (1) and (2) both consume it, so the two
surfaces cannot drift apart again without a test going red. (3) keeps its own
weighted contract -- it scores support categories rather than gating -- but its
personal_context signals are language-matched here so the secondary AMBER
round-up fires in Italian too.

Entry format is unchanged: (category, pattern, note).

Fail-closed order of tiers: RED wins; AMBIGUOUS rounds UP to RED for coordinator
review; AMBER is a wellbeing signal only. A coordinator dismissing a false
positive is cheap. A missed indicator is not.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Indicator taxonomy — reviewable data, not scattered strings.
# Each entry: (category, pattern, note). Categories cite the recognized
# safeguarding-practice grouping the pattern belongs to.
# ---------------------------------------------------------------------------

# RED: explicit safeguarding indicators. Any match -> RED.
RED_INDICATORS: list[tuple[str, str, str]] = [
    # -- Disclosure language (KCSIE-style: a child telling, or being told
    #    to keep secrets, is treated as a disclosure signal).
    ("disclosure", r"\btold me (that )?(someone|he|she|they|[a-z]+) (hurts?|hit|touched|scares?)\b",
     "child disclosed harm by a person"),
    ("disclosure", r"\b(asked|told|begged) me not to tell\b",
     "secrecy request around a concern"),
    ("disclosure", r"\b(don'?t|do not) tell (anyone|my (mum|mom|dad|parents|family))\b",
     "secrecy request around a concern"),
    ("disclosure", r"\b(keep|it'?s) (this |a )?secret\b",
     "secrecy framing by the child"),
    ("disclosure", r"\b(has|needs) to stay (a )?secret\b",
     "secrecy framing by the child"),
    ("disclosure", r"\bsaid (that )?(someone|he|she|they) (hurt|hurts|touched) (him|her|them|me)\b",
     "reported harm to self"),
    # -- Physical abuse indicators.
    ("physical_abuse", r"\b(hit(s|ting)?|beat(s|en|ing)?|punch(es|ed|ing)?|slapp?(s|ed|ing)?|kick(s|ed|ing)?|smack(s|ed|ing)?)\b[^.!?\n]{0,40}\b(at home|by (his|her|their|my))\b",
     "reported physical harm at home / by a named adult"),
    ("physical_abuse", r"\b(dad|daddy|father|mum|mom|mommy|mother|stepdad|stepfather|stepmum|stepmother|uncle|aunt|grandpa|grandma|carer|caregiver|an? adult)\b[^.!?\n]{0,30}\b(hit(s|ting)?|beat(s|ing)?|punch(es|ed|ing)?|slapp?(s|ed|ing)?|kick(s|ed|ing)?|smack(s|ed|ing)?|hurts?)\b",
     "named household adult physically harming the child"),
    ("physical_abuse", r"\b(cigarette )?burn(s| marks?)\b",
     "burn marks"),
    ("physical_abuse", r"\bflinch(es|ed|ing)? (when|at)\b",
     "flinching at contact/approach"),
    # -- Sexual abuse indicators.
    ("sexual_abuse", r"\b(inappropriate|sexuali[sz]ed) (touch(ing)?|behaviou?r|language|knowledge)\b",
     "sexualized behavior/knowledge beyond age expectation"),
    ("sexual_abuse", r"\btouched (him|her|them|me) (somewhere|in a way|where)\b",
     "disclosure of inappropriate touch"),
    # -- Emotional abuse indicators.
    ("emotional_abuse", r"\b(afraid|scared|terrified) (to go|of going) home\b",
     "fear of going home"),
    ("emotional_abuse", r"\bunsafe at home\b",
     "explicit statement of feeling unsafe at home"),
    # -- Neglect indicators.
    ("neglect", r"\b(left|home) alone (at night|for days|overnight|all (day|night))\b",
     "unsupervised for extended periods"),
    ("neglect", r"\bno (food|dinner|breakfast) at home\b",
     "reported lack of food at home"),
    # -- Explicit safeguarding vocabulary (already-escalated language).
    ("explicit", r"\b(safeguarding|child protection) (concern|referral|issue|disclosure)\b",
     "teacher used explicit safeguarding vocabulary"),
    # Narrowed 2026-09-03, and the parity test is why. The Italian side of this
    # pattern was deliberately narrowed on 09-02 so that "abuso di sostanze"
    # discussed in a science lesson would not put a child under a restricted
    # record. The English side was never given the same treatment, so
    # "We discussed substance abuse in the science lesson" scored RED — the
    # exact false positive we had already guarded against in the other
    # language. Substance/drug/alcohol are excluded by name; every other use of
    # "abuse" in a teacher observation is treated as a disclosure.
    ("explicit",
     r"\b(?<!substance )(?<!drug )(?<!alcohol )abuse[ds]?\b|"
     r"\bneglect(ed)?\b|\bdomestic violence\b",
     "explicit abuse/neglect vocabulary"),
    # English had NO red-tier pattern for naming a safeguarding referral, while
    # Italian did ("segnalazione ai servizi sociali"). Found by the parity test:
    # the Italian taxonomy was stronger than the English one here.
    ("explicit",
     r"\b(report(ed|ing)?|referral|referred|disclosure)\b[^.!?\n]{0,30}"
     r"\b(social services|children'?s services|safeguarding lead|"
     r"child protection|social worker|cps)\b",
     "safeguarding referral named"),
    ("explicit",
     r"\b(made|filed|submitted)\s+a\s+(mandated\s+)?report\b[^.!?\n]{0,30}"
     r"\b(social services|children'?s services|safeguarding|child protection)\b|"
     r"\bmandated report(ing)?\b",
     "mandated reporting named"),

    # ------------------------------------------------------------------
    # EN gap found by Claudia's QA, 2026-08-29 (BUG-3). She typed
    # "Aiken said someone at home makes him feel scared." and it scored
    # GREEN — "normal teaching observation".
    #
    # The emotional_abuse patterns above all missed it: they require
    # "scared TO GO home", the literal "unsafe at home", or a NAMED
    # relative. Hers is a causative with an UNNAMED adult — "someone at
    # home MAKES him feel scared" — which is closer to how a young child
    # actually discloses than any of the three. A six-year-old does not
    # say "I feel unsafe at home".
    #
    # Every pattern requires a home/household anchor, so ordinary
    # classroom fear ("scared of the dark", "afraid to read aloud")
    # cannot reach RED.
    ("emotional_abuse",
     r"\b(someone|somebody|a (?:man|woman|adult|person)|people)\b[^.!?\n]{0,40}"
     r"\b(?:at|back) home\b[^.!?\n]{0,40}"
     r"\b(scares?|scared|scary|afraid|frightened|terrified|feel unsafe)\b",
     "unnamed person at home causing fear"),
    ("emotional_abuse",
     r"\b(scared|afraid|frightened|terrified)\b[^.!?\n]{0,30}"
     r"\bof (?:someone|somebody|a (?:man|woman|adult|person))\b[^.!?\n]{0,20}"
     r"\bat home\b",
     "child fears an unnamed person at home"),
    ("emotional_abuse",
     r"\b(?:at|back) home\b[^.!?\n]{0,30}\bmakes? (?:him|her|them|me)\b"
     r"[^.!?\n]{0,20}\b(scared|afraid|frightened|feel unsafe)\b",
     "home context named as the cause of fear"),

    # ==================================================================
    # ITALIAN — added 2026-09-02.
    #
    # WHY THIS BLOCK EXISTS. Every pattern above this line is English.
    # Lingua Viva is an Italian classroom product: the teacher manual
    # ships as Manuale_Italiano_Laboratorio_Linguistico_G1-G5.docx and
    # `language_of_instruction` was corrected to "it" on 2026-08-29.
    # Teachers write observations in Italian. Measured before this block
    # was added, on v0.2.83:
    #
    #     "Ha detto che suo padre lo picchia"      -> GREEN
    #     "He said his dad hits him"               -> RED
    #
    # The most explicit disclosure a teacher can record was invisible in
    # the language they actually write in, and it failed OPEN — returning
    # GREEN, "normal teaching observation" — which is the opposite of this
    # module's stated fail-closed policy.
    #
    # AUDIT NOTE FOR CLAUDIA. These are written by a non-native speaker
    # and need a native Italian educator's review, which is exactly why
    # they live here as a reviewable constant. Two questions worth your
    # eye: (1) does any pattern here catch something innocent a teacher
    # would plausibly write, and (2) what phrasing would a child in YOUR
    # classroom actually use that is missing? The second is the dangerous
    # direction.
    #
    # Accent-less spellings are included deliberately ("papa" as well as
    # "papà"): teachers type quickly and this module does not fold
    # diacritics before matching.
    # ==================================================================

    # -- Disclosure / secrecy (IT).
    ("disclosure",
     r"\bmi ha (?:detto|chiesto|pregato) di non (?:dir|racconta)\w*\b",
     "IT: secrecy request around a concern"),
    ("disclosure",
     r"\bnon (?:dir|dirlo|dirglielo|raccontarlo) a nessuno\b",
     "IT: secrecy request around a concern"),
    ("disclosure",
     r"\b(?:è|e'|resta|deve restare|rimane) un segreto\b",
     "IT: secrecy framing by the child"),
    ("disclosure",
     r"\bmi ha detto che\b[^.!?\n]{0,40}\b(?:gli|le|mi)\s+fa(?:nno)? male\b",
     "IT: child disclosed being hurt"),

    # -- Physical abuse (IT). A household adult, or an object pronoun, is
    #    required: "picchiare alla porta" (to knock at the door) must not
    #    reach RED.
    ("physical_abuse",
     r"\b(?:pap[àa]|padre|mamm[àa]|madre|zio|zia|nonno|nonna|patrigno|matrigna|"
     r"compagno della madre|convivente)\b[^.!?\n]{0,30}"
     r"\b(?:picchi\w*|men\w*|colpisc\w*|colpit\w*|schiaffegg\w*|maltratt\w*)\b",
     "IT: named household adult physically harming the child"),
    ("physical_abuse",
     r"\b(?:lo|la|mi|ti|gli|le)\s+(?:picchia\w*|mena\w*|maltratta\w*)\b",
     "IT: reported physical harm with an explicit object"),
    ("physical_abuse",
     r"\b(?:le\s+)?botte\b|\bbruciatur\w*\b|\bustion\w*\b",
     "IT: beatings / burn marks"),

    # -- Sexual abuse (IT).
    ("sexual_abuse",
     r"\b(?:toccat\w*|toccare)\b[^.!?\n]{0,30}"
     r"\b(?:dove non|parti intime|in modo strano|nelle parti)\b",
     "IT: disclosure of inappropriate touch"),
    ("sexual_abuse",
     r"\bcomportament\w*\s+sessualizzat\w*\b|\blinguaggio sessualizzato\b",
     "IT: sexualized behaviour/knowledge beyond age expectation"),

    # -- Emotional abuse (IT). "paura" alone is ordinary classroom
    #    vocabulary, so every pattern requires a home/household anchor.
    ("emotional_abuse",
     r"\bpaura di (?:tornare|andare|rientrare) a casa\b",
     "IT: fear of going home"),
    ("emotional_abuse",
     r"\bnon si sente (?:al )?sicur\w*\s+a casa\b",
     "IT: explicit statement of feeling unsafe at home"),
    ("emotional_abuse",
     r"\b(?:qualcuno|una persona|un adulto)\b[^.!?\n]{0,30}\ba casa\b"
     r"[^.!?\n]{0,30}\b(?:gli|le|mi)\s+fa paura\b",
     "IT: unnamed person at home causing fear"),
    ("emotional_abuse",
     r"\ba casa\b[^.!?\n]{0,30}\b(?:gli|le|mi)\s+fa(?:nno)? paura\b",
     "IT: home context named as the cause of fear"),

    # -- Neglect (IT).
    ("neglect",
     r"\bnon c'?[eè]\s+(?:da mangiare|cibo|niente da mangiare)\s+a casa\b",
     "IT: reported lack of food at home"),
    ("neglect",
     r"\b(?:lasciat\w*|rimane|resta|sta)\s+(?:da )?sol\w*\b[^.!?\n]{0,30}"
     r"\b(?:la notte|tutta la notte|per giorni|di notte)\b",
     "IT: unsupervised for extended periods"),

    # -- Explicit safeguarding vocabulary (IT).
    #
    # Deliberately narrower than it first looks. The first draft of this
    # pattern accepted bare "segnalazione" and bare "abuso", and scored
    # RED on "Ho fatto una segnalazione per il proiettore rotto" (I filed
    # a report about the broken projector) and on "abuso di sostanze"
    # discussed in a science lesson. A safeguarding flag is not free: it
    # puts a child under a restricted record and it teaches the teacher to
    # distrust the flag. Both terms now require a safeguarding object.
    ("explicit",
     r"\bmaltrattament\w*\b|\bviolenza domestica\b|\btutela dei minori\b|"
     r"\bservizi sociali\b",
     "IT: explicit abuse/neglect vocabulary"),
    ("explicit",
     r"\babus\w*\s+(?:su|sul|sui|sulla|di)\s+(?:un\s+|una\s+)?"
     r"(?:minor\w*|bambin\w*|minorenne)\b",
     "IT: explicit child-abuse vocabulary"),
    ("explicit",
     r"\bsegnalazione\b[^.!?\n]{0,30}"
     r"\b(?:servizi sociali|tribunale|minor\w*|maltrattament\w*|abus\w*)\b",
     "IT: safeguarding referral named"),
]

# AMBIGUOUS: could be innocent, could be an indicator. Fail closed: any
# match ROUNDS UP to RED for coordinator review (a coordinator dismissing
# a false positive is cheap; a missed indicator is not).
AMBIGUOUS_INDICATORS: list[tuple[str, str, str]] = [
    ("physical_abuse", r"\b(unexplained|recurring|frequent) (bruis(e|es|ing)|marks?|injur(y|ies))\b",
     "unexplained/recurring physical marks"),
    ("physical_abuse", r"\bbruis(e|es|ing)\b",
     "bruising mentioned in a school observation — cause unknown here"),
    ("neglect", r"\b(always|often|constantly|persistently) (hungry|tired|exhausted|unwashed|dirty)\b",
     "persistent hunger/fatigue/poor care pattern"),
    ("neglect", r"\b(comes to school )?hungry every day\b",
     "persistent hunger pattern"),
    ("neglect", r"\bsame (clothes|uniform) (all week|for days|every day)\b",
     "persistent unchanged clothing"),
    ("emotional_abuse", r"\b(scared|afraid|frightened) of (his|her|their) (dad|father|mum|mom|mother|uncle|aunt|stepdad|stepmum|carer|caregiver)\b",
     "fear of a specific household adult"),
    ("disclosure", r"\bstarted to (tell|say) (me )?something (about home )?(but|and) stopped\b",
     "interrupted possible disclosure"),
]

# AMBER: wellbeing concerns — patterns worth monitoring, not (alone)
# safeguarding indicators.
AMBER_INDICATORS: list[tuple[str, str, str]] = [
    ("wellbeing", r"\b(withdrawn|isolat(ed|ing)|stopped (talking|playing|participating))\b",
     "social withdrawal"),
    ("wellbeing", r"\b(tearful|crying|cried|in tears)\b",
     "tearfulness"),
    ("wellbeing", r"\b(anxious|anxiety|worried|overwhelmed)\b",
     "anxiety signals"),
    ("wellbeing", r"\b(sudden|marked|noticeable) change in (behaviou?r|mood|engagement)\b",
     "sudden behavior change"),
    ("wellbeing", r"\b(hungry|no (lunch|snack)) (today|this morning)\b",
     "one-off hunger/no lunch — monitor for a pattern"),
    ("wellbeing", r"\b(tired|exhausted|falling asleep) (today|in class|this morning)\b",
     "one-off fatigue — monitor for a pattern"),
    ("wellbeing", r"\b(bereavement|grief|family emergency|parents? (are )?(separating|divorcing))\b",
     "difficult personal context affecting wellbeing"),
    ("wellbeing", r"\blow self[- ]esteem|puts? (himself|herself|themselves) down\b",
     "self-esteem concern"),
    ("wellbeing", r"\bgets in trouble at home\b",
     "home-context euphemism worth monitoring"),
    ("wellbeing", r"\b(dad|daddy|father|mum|mom|mommy|mother|stepdad|stepfather|stepmum|stepmother|carer|caregiver) gets angry with (him|her|them|me)\b",
     "household-adult anger reported by child"),
]


# ---------------------------------------------------------------------------
# Gap closures, 2026-09-03. Each entry states the measured miss it fixes.
# ---------------------------------------------------------------------------

# Self-harm and suicide had NO entry in the tier taxonomy at all, in either
# language -- verified by grep over the whole module before this change. Only
# detector (2) carried the words, and its own pattern was \bself[- ]harm\b,
# which does not match the inflection "self-harmed" that a teacher actually
# writes. Both languages, both inflections, closed here.
_SELF_HARM: list[tuple[str, str, str]] = [
    ("self_harm",
     r"\bself[- ]?harm(s|ed|ing)?\b|\bharm(s|ed|ing)? (?:him|her|them)sel(?:f|ves)\b",
     "self-harm disclosed or observed"),
    ("self_harm",
     r"\bcut(s|ting)? (?:him|her|them)sel(?:f|ves)\b|\bcutting\b[^.!?\n]{0,20}\b(?:arms?|wrists?|legs?)\b",
     "cutting disclosed or observed"),
    ("self_harm",
     r"\bsuicid(?:e|al)\b|\bkill (?:him|her|them)sel(?:f|ves)\b|\bwants? to die\b|\bend (?:his|her|their) life\b",
     "suicidal ideation disclosed"),
    ("self_harm",
     r"\bautolesionism\w*\b|\bsi (?:e|\u00e8) (?:fatt[oa]|tagliat[oa]) del male\b|"
     r"\bsi fa del male\b|\bfarsi del male\b|\bsi (?:e|\u00e8) tagliat[oa]\b",
     "IT: self-harm disclosed or observed"),
    ("self_harm",
     r"\bsuicid\w*\b|\bvuole morire\b|\bfarla finita\b|\btogliersi la vita\b",
     "IT: suicidal ideation disclosed"),
]

# "Il bambino ha subito abusi in casa" scored GREEN while the English twin
# scored RED. The existing IT abuse pattern deliberately requires a
# safeguarding OBJECT ("abusi su minore") because an earlier draft accepted
# bare "abuso" and fired on "abuso di sostanze" in a science lesson. That
# narrowing was right and is preserved. These add the other honest shapes --
# a victim or a home context -- without reopening the bare-noun false positive.
_IT_ABUSE_CONTEXT: list[tuple[str, str, str]] = [
    ("explicit",
     r"\b(?:ha|hanno|avrebbe) subit[oa]\s+(?:degli\s+|dei\s+|un\s+)?abus\w*\b|"
     r"\bvittima di abus\w*\b",
     "IT: child named as having suffered abuse"),
    ("explicit",
     r"\babus\w*\b[^.!?\n]{0,20}\b(?:in casa|a casa|in famiglia|domestic\w*)\b",
     "IT: abuse located in the home"),
]

# Claudia's BUG-3 was a causative with an UNNAMED adult. Three English patterns
# were added for it on 2026-09-02; the Italian twin was never added, so the
# exact phrasing she reported still read GREEN in the language she writes in.
_IT_CAUSATIVE: list[tuple[str, str, str]] = [
    ("emotional_abuse",
     r"\b(?:qualcuno|una persona|un adulto|qualcun altro)\b[^.!?\n]{0,40}"
     r"\b(?:a|in) casa\b[^.!?\n]{0,40}"
     r"\b(?:spavent\w*|paura|terrorizz\w*|sentire? (?:non )?al sicuro)\b",
     "IT: unnamed person at home causing fear"),
    ("emotional_abuse",
     r"\b(?:a|in) casa\b[^.!?\n]{0,40}\b(?:lo|la|li|le|gli|mi|ti)\s+"
     r"fa\s+(?:sentire\s+)?(?:spaventat\w*|paura|insicur\w*|a disagio)\b",
     "IT: home context named as the cause of fear"),
    ("emotional_abuse",
     r"\bnon (?:si sente|e|\u00e8) al sicuro (?:a|in) casa\b|"
     r"\bha paura di (?:tornare|andare) a casa\b",
     "IT: explicit statement of feeling unsafe at home"),
]

RED_INDICATORS = RED_INDICATORS + _SELF_HARM + _IT_ABUSE_CONTEXT + _IT_CAUSATIVE


# ---------------------------------------------------------------------------
# Compiled RED gate, for callers that need a boolean rather than a tier.
# docpipe/lens_extract.py consumes this: it is the gate deciding restricted
# log vs the student's ordinary lens, and before 2026-09-03 it ran its own
# English-only regex.
# ---------------------------------------------------------------------------

_RED_COMPILED = tuple(
    re.compile(pattern, re.IGNORECASE) for _cat, pattern, _note in RED_INDICATORS
)
_AMBIGUOUS_COMPILED = tuple(
    re.compile(pattern, re.IGNORECASE) for _cat, pattern, _note in AMBIGUOUS_INDICATORS
)


def is_red(text: str, *, include_ambiguous: bool = True) -> bool:
    """True if text carries a RED safeguarding indicator in EN or IT.

    include_ambiguous mirrors classify_severity's fail-closed rule: an
    AMBIGUOUS match rounds UP, because routing a borderline observation to a
    restricted log is recoverable and leaving a disclosure in the ordinary
    student record is not.
    """
    if not text:
        return False
    for rx in _RED_COMPILED:
        if rx.search(text):
            return True
    if include_ambiguous:
        for rx in _AMBIGUOUS_COMPILED:
            if rx.search(text):
                return True
    return False


def all_red_patterns() -> tuple[tuple[str, str, str], ...]:
    """The RED table, for tests and audits that must enumerate it."""
    return tuple(RED_INDICATORS)
