"""Voice input must recognise Italian, not English.

Lingua Viva's teachers speak Italian. Both Web Speech handlers in
static/index.html previously set ``recognition.lang = "en-US"``, so the
browser transcribed Italian speech against an English acoustic/language
model — Ask returned garbled queries and Observe dictation produced
unusable observation text. Fixed per SPEC_WORKSTATION_BUILD_ORDER_2026-07-28
("fix immediately", not a slice).

There are exactly two handlers and both must be Italian:
  - ``toggleAsk``     — the "Talk to Lingua Viva" mic (#ask-mic)
  - ``toggleObserve`` — the Observe mic (#mic)

No browser/JS test runner exists in this repo, so this asserts on the
served HTML text directly, following the pattern of other markup/contract
tests in this suite (e.g. test_quick_capture.py, test_sw_surface_parity.py).
Asserting on the *served* body — not the file on disk — proves the fix
reaches the real route a teacher's browser hits.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from src.web import app

client = TestClient(app)

LANG_ASSIGNMENT = re.compile(r'recognition\.lang\s*=\s*"([^"]+)"')


def _served_index() -> str:
    response = client.get("/")
    assert response.status_code == 200, response.status_code
    return response.text


def test_both_voice_handlers_recognise_italian():
    langs = LANG_ASSIGNMENT.findall(_served_index())
    assert langs == ["it-IT", "it-IT"], (
        f"expected exactly two Italian recognition handlers, got {langs!r}"
    )


def test_no_english_recogniser_survives_anywhere_in_the_bundle():
    """Guards against a third handler being added in English later."""
    assert 'recognition.lang = "en-US"' not in _served_index()


def test_language_is_set_inside_both_named_handlers():
    """Proves the Italian lines sit in the two real mic handlers.

    A regex count alone would still pass if someone moved both assignments
    into dead code, so anchor each one to the handler that owns it.
    """
    body = _served_index()
    for handler, next_handler_marker in (
        ("toggleAsk()", "toggleObserve()"),
        ("toggleObserve()", None),
    ):
        start = body.index(handler)
        end = body.index(next_handler_marker) if next_handler_marker else len(body)
        assert 'recognition.lang = "it-IT"' in body[start:end], (
            f"{handler} does not set Italian recognition language"
        )
