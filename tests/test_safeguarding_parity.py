"""Parity: every safeguarding surface must reach the same verdict, IT and EN.

Why this file exists (measured 2026-09-03, not hypothesised):

Lingua Viva carried THREE independent safeguarding vocabularies that did not
agree. The Slack/capture path used the reviewed bilingual taxonomy; the
document-ingestion path used its own ten-word English regex; the support
suggester used a third list. The consequence was measurable and specific:

    "Il bambino ha subito abusi in casa"   -> written to the ORDINARY lens
    "The child suffered abuse at home"     -> routed to restricted

Same disclosure. Different language. Different destination. The gate that
decides restricted-vs-ordinary had never seen a word of Italian, and the
product is used in Italian classrooms.

Three gaps found in the same pass that were NOT about Italian at all:
  * self-harm and suicide had no entry in the tier taxonomy in either language
  * `\\bself[- ]harm\\b` does not match "self-harmed", the inflection a teacher
    actually writes
  * Claudia's BUG-3 causative phrasing was fixed in English only

The point of this file is not to re-test the patterns. It is to make the
surfaces unable to disagree again without something going red.
"""

from __future__ import annotations

import pytest

from src.education.observation_capture import suggest_support_categories
from src.lingua_viva.docpipe.lens_extract import _is_red_safeguarding
from src.lingua_viva.safeguarding import RED, classify_severity
from src.lingua_viva.safeguarding_indicators import RED_INDICATORS, is_red

# (english, italian, must_be_red, label)
# Each pair is the SAME disclosure in both languages. If a language changes the
# verdict, that is the defect this file exists to catch.
PARITY_CORPUS: list[tuple[str, str, bool, str]] = [
    (
        "He said his dad hits him",
        "Ha detto che suo padre lo picchia",
        True,
        "named household adult, physical harm",
    ),
    (
        "The child suffered abuse at home",
        "Il bambino ha subito abusi in casa",
        True,
        "abuse located in the home",
    ),
    (
        "She is a victim of abuse",
        "E' vittima di abusi",
        True,
        "child named as a victim of abuse",
    ),
    (
        "Someone at home makes him feel scared",
        "Qualcuno a casa lo fa sentire spaventato",
        True,
        "BUG-3: causative with an unnamed adult",
    ),
    (
        "He is scared to go home",
        "Ha paura di tornare a casa",
        True,
        "fear of going home",
    ),
    (
        "He self-harmed",
        "Si e fatto del male da solo",
        True,
        "self-harm, and the -ed inflection",
    ),
    (
        "She has been cutting herself",
        "Si e tagliata da sola",
        True,
        "cutting",
    ),
    (
        "He said he wants to die",
        "Ha detto che vuole morire",
        True,
        "suicidal ideation",
    ),
    (
        "I made a report to social services",
        "Ho fatto una segnalazione ai servizi sociali",
        True,
        "safeguarding referral named",
    ),
    # -- Controls. These must NOT flag. A safeguarding flag is not free: it
    #    puts a child under a restricted record and it teaches the teacher to
    #    distrust the flag.
    (
        "I reported the broken projector",
        "Ho fatto una segnalazione per il proiettore rotto",
        False,
        "CONTROL: a maintenance report is not a disclosure",
    ),
    (
        "We discussed substance abuse in the science lesson",
        "Abbiamo parlato di abuso di sostanze nella lezione di scienze",
        False,
        "CONTROL: curriculum vocabulary is not a disclosure",
    ),
    (
        "The wolf knocks at the door",
        "Il lupo picchia alla porta",
        False,
        "CONTROL: a fairy tale is not a disclosure",
    ),
]

IDS = [f"{label} [{'RED' if red else 'control'}]" for _en, _it, red, label in PARITY_CORPUS]


# ---------------------------------------------------------------------------
# 1. Cross-language parity, per surface.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("en, it, must_be_red, label", PARITY_CORPUS, ids=IDS)
def test_tier_surface_agrees_across_languages(en, it, must_be_red, label):
    """safeguarding.classify_severity — the Slack/capture surface."""
    en_red = classify_severity(en).tier == RED
    it_red = classify_severity(it).tier == RED
    assert en_red == it_red, (
        f"{label}: language changed the verdict — "
        f"EN={'RED' if en_red else 'not RED'}, IT={'RED' if it_red else 'not RED'}"
    )
    assert en_red == must_be_red, f"{label}: EN verdict wrong"


@pytest.mark.parametrize("en, it, must_be_red, label", PARITY_CORPUS, ids=IDS)
def test_document_surface_agrees_across_languages(en, it, must_be_red, label):
    """docpipe/lens_extract._is_red_safeguarding — the gate that decides
    whether a disclosure reaches the student's ordinary lens.

    This is the surface that was blind in Italian. It is the reason this file
    exists.
    """
    en_red = _is_red_safeguarding(en)
    it_red = _is_red_safeguarding(it)
    assert en_red == it_red, (
        f"{label}: the document gate changed its verdict with the language — "
        f"EN={'RED' if en_red else 'pass'}, IT={'RED' if it_red else 'pass'}. "
        f"An Italian disclosure would reach the ordinary student record."
    )


# ---------------------------------------------------------------------------
# 2. Cross-SURFACE parity. The two gates must not disagree with each other.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("en, it, must_be_red, label", PARITY_CORPUS, ids=IDS)
def test_both_surfaces_agree_with_each_other(en, it, must_be_red, label):
    """A disclosure the capture path calls RED must not be written to the
    ordinary lens by the document path, and vice versa."""
    for text, lang in ((en, "EN"), (it, "IT")):
        tier_red = classify_severity(text).tier == RED
        doc_red = _is_red_safeguarding(text)
        if tier_red:
            assert doc_red, (
                f"{label} [{lang}]: classify_severity says RED but the document "
                f"gate would write it to the ordinary lens. The surfaces disagree."
            )


# ---------------------------------------------------------------------------
# 3. Controls must hold on every surface. Over-flagging has a real cost.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "en, it, label",
    [(en, it, label) for en, it, red, label in PARITY_CORPUS if not red],
    ids=[label for _e, _i, red, label in PARITY_CORPUS if not red],
)
def test_controls_do_not_flag_on_any_surface(en, it, label):
    for text, lang in ((en, "EN"), (it, "IT")):
        assert classify_severity(text).tier != RED, f"{label} [{lang}]: false RED on tier surface"
        assert not _is_red_safeguarding(text), f"{label} [{lang}]: false RED on document surface"


# ---------------------------------------------------------------------------
# 4. The single source is actually single.
# ---------------------------------------------------------------------------

def test_document_gate_consumes_the_shared_taxonomy():
    """Non-vacuity: prove the document gate really reads the shared table
    rather than merely importing it.

    Uses a phrase that exists ONLY in the shared bilingual taxonomy and not in
    the legacy English regex. If someone unwires the union, this goes red.
    """
    only_in_shared = "Ha detto che suo padre lo picchia"
    assert is_red(only_in_shared), "shared taxonomy no longer recognises the phrase"
    assert _is_red_safeguarding(only_in_shared), (
        "the document gate is no longer consuming the shared taxonomy — "
        "the two surfaces have been allowed to drift apart again"
    )


def test_italian_and_english_both_represented_in_the_taxonomy():
    """Guards the regression where a table is 'bilingual' by having one token."""
    notes = [note for _cat, _pat, note in RED_INDICATORS]
    italian = [n for n in notes if n.startswith("IT:")]
    english = [n for n in notes if not n.startswith("IT:")]
    assert len(italian) >= 15, f"Italian coverage collapsed to {len(italian)} indicators"
    assert len(english) >= 15, f"English coverage collapsed to {len(english)} indicators"


def test_self_harm_is_covered_in_both_languages():
    """Regression guard: self-harm and suicide had NO entry in this taxonomy in
    either language before 2026-09-03, and the one English pattern that existed
    elsewhere could not match the inflection 'self-harmed'."""
    for phrase in ("He self-harmed", "he harmed himself", "Si e fatto del male da solo"):
        assert is_red(phrase), f"self-harm not detected: {phrase!r}"
    for phrase in ("He said he wants to die", "Ha detto che vuole morire"):
        assert is_red(phrase), f"suicidal ideation not detected: {phrase!r}"


def test_personal_context_suggester_speaks_italian():
    """The secondary GREEN->AMBER round-up must be reachable in Italian."""
    def has_personal_context(text: str) -> bool:
        return any(
            s["category_id"] == "personal_context"
            for s in suggest_support_categories(text)
        )

    assert has_personal_context("I made a mandated report")
    assert has_personal_context("Ho fatto una segnalazione ai servizi sociali"), (
        "personal_context never fires in Italian, so the secondary round-up "
        "that raises GREEN to AMBER is unreachable in an Italian classroom"
    )
