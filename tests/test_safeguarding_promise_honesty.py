"""The app must not tell a teacher her safeguarding concern reached a person.

Context (2026-08-27): four surfaces — the Observe result panel, /api/observe
voice confirmation, the safeguarding module's note, and the Slack ack — all
said the item was "routed for coordinator review only" or "visible to
coordinators and above only".

Both halves were wrong in the way that matters:

  * There is no coordinator view. GET /api/safeguarding/restricted,
    POST /api/safeguarding/drain and POST /api/safeguarding/restricted/
    {entry_id}/status are all classified intentionally_backend_only with
    status deferred_undecided — no UI reaches any of them.
  * safeguarding_config() defaults safeguarding_channel to "", so by default
    the notification sits at pending_config and is delivered to nobody.

A teacher who believes a coordinator has seen a disclosure may not escalate it
herself. That is the one place in this product where a reassuring default is a
safety problem rather than a UX one, so it gets a test rather than a comment.

These guards fail if the old wording returns anywhere.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _reader_text(path: Path) -> str:
    """The copy as a teacher would read it.

    Two normalisations, both needed or this test lies:
      * Drop whole-line comments. The fix's own rationale quotes the wording it
        removed; a scan that cannot tell an explanation from a claim would
        forbid documenting the bug.
      * Join adjacent string literals. Every one of these messages is written
        as implicit concatenation across lines, so "safeguarding process" never
        appears contiguously in the source even when the teacher reads it.
    """
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines()
             if not ln.lstrip().startswith(("#", "//"))]
    joined = "\n".join(lines)
    # "...so nobody has been " \n "notified" -> "...so nobody has been notified"
    return re.sub(r'"\s*\n\s*"', "", joined)

# Surfaces a teacher can actually read.
SURFACES = [
    REPO / "static" / "index.html",
    REPO / "src" / "web.py",
    REPO / "src" / "lingua_viva" / "safeguarding.py",
    REPO / "src" / "education" / "slack_bot.py",
]

# Phrasings that assert a human has seen, or will see, the item in-product.
BANNED = [
    r"visible to coordinators",
    r"coordinator review only",
    r"routed for coordinator review",
]


def test_no_surface_claims_a_coordinator_can_see_the_item():
    offenders = []
    for path in SURFACES:
        text = _reader_text(path)
        for pattern in BANNED:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                line = text[: match.start()].count("\n") + 1
                offenders.append(f"{path.relative_to(REPO)}:{line} — {match.group(0)!r}")
    assert not offenders, (
        "A surface claims a coordinator sees safeguarding items, but no "
        "coordinator UI exists:\n  " + "\n  ".join(offenders)
    )


def test_unconfigured_note_says_nobody_was_notified():
    """The default install has no channel. The note must say so, not imply reach."""
    from src.lingua_viva.safeguarding import safeguarding_config

    text = _reader_text(REPO / "src" / "lingua_viva" / "safeguarding.py")
    assert "nobody has been notified" in text, (
        "The unconfigured branch must state plainly that no one was notified."
    )
    # The honest branch has to be reachable: the default config is unconfigured.
    assert not safeguarding_config().get("safeguarding_channel"), (
        "Default config now ships a safeguarding_channel — re-check that the "
        "configured branch's wording is the one a default install sees."
    )


def test_every_surface_points_at_the_human_process():
    """Removing a false assurance is only safe if the real route is named."""
    missing = [
        str(path.relative_to(REPO))
        for path in SURFACES
        if "safeguarding process" not in _reader_text(path)
    ]
    assert not missing, (
        "These surfaces stopped naming the school's safeguarding process: "
        + ", ".join(missing)
    )
