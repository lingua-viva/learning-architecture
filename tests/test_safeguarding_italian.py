"""Safeguarding detection in Italian, and the EN causative gap Claudia found.

Two findings, both measured against v0.2.83 before these tests existed.

BUG-3 (Claudia's QA, 2026-08-29). She typed
"Aiken said someone at home makes him feel scared." into Observe and it
saved as a normal observation — GREEN, "normal teaching observation". The
emotional_abuse patterns required "scared TO GO home", the literal phrase
"unsafe at home", or a NAMED relative. A causative with an unnamed adult
missed all three, and that is closer to how a young child actually
discloses than any of them.

THE LANGUAGE GAP. Every indicator in this module was English. Lingua Viva
is an Italian classroom product — the teacher manual ships in Italian and
`language_of_instruction` was corrected to "it" on 2026-08-29. Measured
before the Italian block was added:

    "Ha detto che suo padre lo picchia"   -> GREEN
    "He said his dad hits him"            -> RED

The most explicit disclosure a teacher can record was invisible in the
language they write in, and it failed OPEN, which inverts this module's
stated fail-closed policy.

The false-positive cases below matter as much as the positives. A
safeguarding flag on an innocent observation is not free: it puts a child
under a restricted record and it teaches a teacher to distrust the flag.
Both directions are locked here.

All names are synthetic per publication-policy.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.lingua_viva import safeguarding as sg


def tier(text: str) -> str:
    return sg.classify_severity(text).tier


# ---------------------------------------------------------------------------
# BUG-3 — the English causative gap
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "Aiken said someone at home makes him feel scared.",   # Claudia, verbatim
    "Someone at home scares him",
    "He is scared of someone at home",
    "There is a man at home who makes her frightened",
])
def test_unnamed_person_at_home_causing_fear_is_red(text):
    assert tier(text) == "RED"


@pytest.mark.parametrize("text", [
    "Boyce hit the ball really hard at recess and cheered",  # Claudia's GOOD-12
    "He was scared of the dark during story time",
    "She is afraid to read aloud in front of the class",
    "The class was frightened by the thunder",
    "He forgot his homework at home and was upset",
    "Someone at home helps him with reading every night",
])
def test_ordinary_classroom_fear_stays_green(text):
    """Fear is ordinary classroom vocabulary. Only fear anchored to the home
    and to a person may escalate, or the flag becomes noise."""
    assert tier(text) == "GREEN"


# ---------------------------------------------------------------------------
# Italian — the disclosures a teacher here would actually write
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,why", [
    ("Ha detto che suo padre lo picchia",        "named household adult, physical"),
    ("Il papa lo mena quando torna",             "accent-less 'papa', teachers type fast"),
    ("Qualcuno a casa gli fa paura.",            "Claudia's BUG-3 sentence, in Italian"),
    ("Ha paura di tornare a casa",               "fear of going home"),
    ("Non si sente al sicuro a casa",            "explicit unsafe-at-home"),
    ("Mi ha chiesto di non dirlo a nessuno",     "secrecy request"),
    ("Mi ha detto che e' un segreto",            "secrecy framing, apostrophe form"),
    ("Mi ha detto che è un segreto",             "secrecy framing, accented form"),
    ("Non c'è da mangiare a casa",               "neglect, food"),
    ("Resta solo a casa tutta la notte",         "neglect, unsupervised"),
    ("Ha delle bruciature sul braccio",          "burn marks"),
])
def test_italian_disclosures_are_red(text, why):
    assert tier(text) == "RED", why


@pytest.mark.parametrize("text,why", [
    ("Ha paura di parlare davanti alla classe",  "ordinary stage fright"),
    ("Ha paura del buio durante la lettura",     "ordinary fear of the dark"),
    ("Il lupo picchia alla porta nella storia",  "'picchiare alla porta' = to KNOCK, in a story"),
    ("Ha dimenticato i compiti a casa",          "home mentioned, nothing else"),
    ("Ha giocato a palla e ha colpito il muro",  "hit, but no household adult"),
    ("A casa lo aiutano con i compiti",          "home mentioned, positively"),
])
def test_ordinary_italian_observations_stay_green(text, why):
    assert tier(text) == "GREEN", why


# ---------------------------------------------------------------------------
# The two languages must agree. A disclosure is a disclosure.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("italian,english", [
    ("Ha detto che suo padre lo picchia",  "He said his dad hits him"),
    ("Ha paura di tornare a casa",         "He is afraid to go home"),
    ("Non si sente al sicuro a casa",      "He feels unsafe at home"),
    ("Qualcuno a casa gli fa paura",       "Someone at home scares him"),
])
def test_italian_and_english_reach_the_same_tier(italian, english):
    """The regression that started this: the same disclosure scored RED in
    English and GREEN in Italian. Whichever way the patterns later change,
    the two languages must not drift apart again."""
    assert tier(italian) == tier(english) == "RED"


# ---------------------------------------------------------------------------
# Explicit vocabulary — the pattern that had to be narrowed twice
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,why", [
    ("Ho fatto una segnalazione per il proiettore rotto", "a report about a broken projector"),
    ("Segnalazione di assenza per malattia", "a sick-absence report"),
    ("Abbiamo parlato di abuso di sostanze nella lezione di scienze",
     "substance abuse as curriculum content, not a disclosure"),
])
def test_ordinary_school_admin_language_is_not_a_safeguarding_flag(text, why):
    """The first draft of the IT explicit pattern accepted bare
    "segnalazione" and bare "abuso" and scored all three of these RED. A
    flag on a broken projector would put a child under a restricted record
    and would teach the teacher to ignore the flag — the false-positive
    direction is how a safeguarding system dies quietly."""
    assert tier(text) == "GREEN", why


@pytest.mark.parametrize("text", [
    "Ho fatto una segnalazione ai servizi sociali",
    "La famiglia e seguita dai servizi sociali",
    "Sospetto maltrattamento in famiglia",
    "Si tratta di abuso su minore",
    "Segnalazione al tribunale dei minori",
])
def test_real_italian_safeguarding_vocabulary_still_flags(text):
    """Narrowing must not have cost the real referrals."""
    assert tier(text) == "RED"


def test_the_italian_block_is_actually_present():
    """Anti-vacuity. If the Italian indicators were dropped, every test above
    that asserts RED would still be satisfiable by an accidental English
    match — this pins that Italian patterns exist as their own set."""
    italian_notes = [
        note for _cat, _pat, note in sg.RED_INDICATORS if note.startswith("IT:")
    ]
    assert len(italian_notes) >= 10, italian_notes
