"""
Ops Classifier — deterministic category + entity extraction for the Slack
Daily Operations Assistant.

Spec: dev/specs/SPEC_LV_SLACK_OPS_ASSISTANT_2026-07-27.md §3.2.

Design decisions (operator-locked 2026-07-27):
  - Deterministic-first. Keyword/pattern rules only — no LLM, no network,
    no I/O. Every input maps to exactly one category by a fixed priority
    order, so behavior is predictable, testable, and identical offline.
  - Confidence is binary (high | low). "high" means the category cue fired
    AND the entities that category needs resolved (possibly by a documented
    default, e.g. absence with no date defaults to today — a sick message
    normally means "today"). "low" routes to a one-question Block Kit
    clarification in the bot layer; the message is never dropped.
  - Self vs. student disambiguation: first-person markers ("I'm out",
    "I can't come in") always mean the *teacher* is the subject (absence);
    the same vocabulary about a named third party ("Sofia absent today")
    is student_logistics. This is the rule that keeps teacher absences out
    of student records and vice versa.
  - This module never touches student lenses. Its output feeds
    ops_records.OpsRecordStore only.

All date resolution is relative to an injectable `today` (local date) so
tests are hermetic and the bot layer passes the teacher's local day.

v2 (SPEC_LV_SLACK_OPS_V2_WORKFLOW_PACKS_2026-07-27 §3, Phase 1): category
vocabulary and routing moved from module-level regex constants into pack
data (config/ops_packs/*.yaml), compiled by src/education/ops_packs.py
into an injectable CompiledRuleSet. classify_ops_message() consults the
process-wide current compile by default (v1-parity when no bot-spec is
installed), so every v1 call site behaves unchanged. What stays CODE here
(spec §3(c) core): entity extraction (dates/times/periods/names), the
binary-confidence policy per category (incl. the student_logistics
subject rule), and the `other` fallback. Categories without a coded
confidence policy (future vocabulary-only packs) default to
high-confidence capture — a new pack needs no classifier change.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from src.education.ops_packs import CompiledRuleSet, current_rule_set

# Categories (spec §3.2) in dispatch-priority order. Earlier wins.
CATEGORY_ABSENCE = "absence"
CATEGORY_COVERAGE_REQUEST = "coverage_request"
CATEGORY_COVERAGE_CLAIM = "coverage_claim"
CATEGORY_SCHEDULE_CHANGE = "schedule_change"
CATEGORY_ANNOUNCEMENT = "announcement"
CATEGORY_STUDENT_LOGISTICS = "student_logistics"
CATEGORY_FACILITIES = "facilities"
CATEGORY_REMINDER = "reminder"
CATEGORY_OTHER = "other"

CONFIDENCE_HIGH = "high"
CONFIDENCE_LOW = "low"

MAX_TEXT_CHARS = 20_000

_MENTION_RE = re.compile(r"<@[A-Z0-9]+>")
_WHITESPACE_RE = re.compile(r"\s+")

# --- category cues ----------------------------------------------------------
# Moved to pack data (config/ops_packs/*.yaml) in v2 Phase 1, including the
# "out of <thing>" absence lookahead from hardening pass 11 (its regression
# tests below in tests/test_ops_classifier.py are unchanged). The compiled
# vocabulary arrives via the CompiledRuleSet.

# --- entity extraction ------------------------------------------------------

_TIME_RANGE_RE = re.compile(
    r"\b(\d{1,2}[:.]\d{2})\s*(?:-|–|to)\s*(\d{1,2}[:.]\d{2})\b"
)
_TIME_POINT_RE = re.compile(r"\b(?:at|to)\s+(\d{1,2}[:.]\d{2})\b", re.IGNORECASE)

_PERIOD_ORDINAL_RE = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)\b"
    r"(?=(?:(?:\s*,\s*|\s+(?:and|&)\s+|\s+)\d{1,2}(?:st|nd|rd|th))*\s+periods?\b)",
    re.IGNORECASE,
)
_PERIOD_PLAIN_RE = re.compile(r"\bperiods?\s+(\d{1,2})\b", re.IGNORECASE)

_WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}
_WEEKDAY_RE = re.compile(
    r"\b(?:on\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    re.IGNORECASE,
)

_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}
_MONTH_DAY_RE = re.compile(
    r"\b(" + "|".join(_MONTHS) + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b",
    re.IGNORECASE,
)
_SLASH_DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b")
_ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")

# Tokens that look like capitalized names but never are.
_NON_NAME_TOKENS = {
    "i", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
    "sunday", "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december", "grade", "room",
    "group", "period", "today", "tomorrow", "assembly", "lunch", "fire",
    "bus", "nurse", "the", "for", "need", "slack",
}
_NAME_RE = re.compile(r"\b([A-Z][a-z]{1,20})(?:'s)?\b")


@dataclass
class ClassifiedOpsMessage:
    category: str
    confidence: str
    text_clean: str
    date_for: Optional[str] = None       # ISO date the record applies to
    time_window: Optional[str] = None    # "9:00-11:30" or "10:30"
    periods: list = field(default_factory=list)
    subject: Optional[str] = None        # named third party, if any
    wants_coverage: bool = False         # absence explicitly asks for coverage
    clarification: Optional[str] = None  # one question to ask when low


def clean_text(text: str) -> str:
    text = _MENTION_RE.sub("", text or "")
    return _WHITESPACE_RE.sub(" ", text).strip()


def extract_date(text: str, today: date) -> Optional[str]:
    """Resolve the first date reference in *text* relative to *today*."""
    lowered = text.lower()
    match = _ISO_DATE_RE.search(text)
    if match:
        try:
            return date(int(match[1]), int(match[2]), int(match[3])).isoformat()
        except ValueError:
            pass
    if "tomorrow" in lowered:
        return (today + timedelta(days=1)).isoformat()
    if "today" in lowered or "tonight" in lowered:
        return today.isoformat()
    match = _MONTH_DAY_RE.search(text)
    if match:
        month = _MONTHS[match[1].lower().rstrip(".")]
        day = int(match[2])
        year = today.year
        try:
            candidate = date(year, month, day)
        except ValueError:
            return None
        if candidate < today:  # past this year → they mean next year
            candidate = date(year + 1, month, day)
        return candidate.isoformat()
    match = _SLASH_DATE_RE.search(text)
    if match:
        month, day = int(match[1]), int(match[2])
        year = int(match[3]) if match[3] else today.year
        if year < 100:
            year += 2000
        try:
            candidate = date(year, month, day)
        except ValueError:
            return None
        if not match[3] and candidate < today:
            candidate = date(year + 1, month, day)
        return candidate.isoformat()
    match = _WEEKDAY_RE.search(text)
    if match:
        target = _WEEKDAYS[match[1].lower()]
        ahead = (target - today.weekday()) % 7
        if ahead == 0:
            ahead = 7  # "on Monday" said on a Monday means next Monday
        return (today + timedelta(days=ahead)).isoformat()
    return None


def extract_time_window(text: str) -> Optional[str]:
    match = _TIME_RANGE_RE.search(text)
    if match:
        return f"{match[1].replace('.', ':')}-{match[2].replace('.', ':')}"
    match = _TIME_POINT_RE.search(text)
    if match:
        return match[1].replace(".", ":")
    return None


def extract_periods(text: str, alias_patterns: tuple = ()) -> list:
    """Extract period numbers. Core extraction (spec v2 §3(c)) plus
    settings-fed alias patterns from the bot-spec (spec v2 §2.2: "P2",
    "Block B") — each alias regex has ONE capture group; a digit group is
    the period number, a single-letter group maps A→1, B→2, …"""
    periods = [int(m) for m in _PERIOD_ORDINAL_RE.findall(text)]
    periods.extend(int(m) for m in _PERIOD_PLAIN_RE.findall(text))
    for pattern in alias_patterns:
        for match in pattern.findall(text):
            token = match if isinstance(match, str) else (match[0] if match else "")
            if token.isdigit():
                periods.append(int(token))
            elif len(token) == 1 and token.isalpha():
                periods.append(ord(token.lower()) - ord("a") + 1)
    seen: set = set()
    ordered = []
    for p in periods:
        if p not in seen and 1 <= p <= 12:
            seen.add(p)
            ordered.append(p)
    return ordered


def extract_subject_name(text: str) -> Optional[str]:
    """First capitalized token that plausibly names a person.

    Heuristic (v1, documented limitation): mid-sentence capitalized tokens
    count; a sentence-initial token counts only when followed by a
    person-verb ("Sofia has…", "Mateo absent today") so ordinary sentence
    starts ("Early pickup…") are not mistaken for names. Ambiguity is
    resolved by the bot layer's clarification buttons, never silently
    guessed into a record.
    """
    candidates = []
    for match in _NAME_RE.finditer(text):
        token = match[1]
        if token.lower() in _NON_NAME_TOKENS:
            continue
        candidates.append((match.start(), match.end(), token))
    if not candidates:
        return None
    for start, _end, token in candidates:
        if start > 0:
            return token
    start, end, token = candidates[0]
    follower = text[end:].lstrip().lower()
    if text[end:end + 2] == "'s" or re.match(
        r"(has|have|is|was|will|needs|absent|arriv|left|leaves|leaving|joined|picked|missed)\b",
        follower,
    ):
        return token
    return None


def classify_ops_message(
    text: str,
    *,
    today: date,
    is_dm: bool = False,
    is_ops_channel: bool = False,
    rule_set: Optional[CompiledRuleSet] = None,
) -> ClassifiedOpsMessage:
    """Classify one Slack message into an operational category + entities.

    Vocabulary comes from the injected CompiledRuleSet (default: the
    process-wide current compile — v1 parity until a bot-spec is
    installed). Confidence policy per category stays code here (core,
    spec v2 §3(c)).
    """
    rules = rule_set if rule_set is not None else current_rule_set()
    cleaned = clean_text(text)[:MAX_TEXT_CHARS]
    date_for = extract_date(cleaned, today)
    time_window = extract_time_window(cleaned)
    periods = extract_periods(cleaned, alias_patterns=rules.period_alias_patterns)
    subject = extract_subject_name(cleaned)

    def result(category, confidence, clarification=None, wants_coverage=False,
               resolved_date=None, keep_subject=True):
        return ClassifiedOpsMessage(
            category=category,
            confidence=confidence,
            text_clean=cleaned,
            date_for=resolved_date if resolved_date is not None else date_for,
            time_window=time_window,
            periods=periods,
            subject=subject if keep_subject else None,
            wants_coverage=wants_coverage,
            clarification=clarification,
        )

    if not cleaned:
        return result(CATEGORY_OTHER, CONFIDENCE_LOW,
                      clarification="I could not read that message. Could you resend it?")

    # First keyword-triggered category whose pack vocabulary matches, in
    # registry priority order (earlier wins — spec v2 §3.1). Confidence
    # policy per category is core code below.
    matched = rules.match_category(cleaned)

    if matched == CATEGORY_ABSENCE:
        # A sick message with no date normally means today.
        resolved = date_for or today.isoformat()
        wants_coverage = (
            rules.pattern_search(CATEGORY_COVERAGE_REQUEST, cleaned) or bool(periods)
        )
        return result(CATEGORY_ABSENCE, CONFIDENCE_HIGH,
                      wants_coverage=wants_coverage, resolved_date=resolved,
                      keep_subject=False)

    if matched == CATEGORY_COVERAGE_CLAIM:
        return result(CATEGORY_COVERAGE_CLAIM, CONFIDENCE_HIGH)

    if matched == CATEGORY_COVERAGE_REQUEST:
        if periods or time_window or date_for:
            return result(CATEGORY_COVERAGE_REQUEST, CONFIDENCE_HIGH)
        return result(CATEGORY_COVERAGE_REQUEST, CONFIDENCE_LOW,
                      clarification="Which class, period, or time needs coverage?")

    if matched == CATEGORY_STUDENT_LOGISTICS:
        # Subject-name confidence rule stays code (spec v2 §3.1).
        if subject:
            return result(CATEGORY_STUDENT_LOGISTICS, CONFIDENCE_HIGH)
        return result(CATEGORY_STUDENT_LOGISTICS, CONFIDENCE_LOW,
                      clarification="Who is this about?")

    if matched is not None:
        # schedule_change, facilities, reminder — and any future
        # vocabulary-only pack category: high-confidence capture, no
        # classifier change needed per pack (spec v2 §5 backlog proof).
        return result(matched, CONFIDENCE_HIGH)

    if is_ops_channel and not is_dm and rules.channel_default_category:
        # Positional default bucket (spec v2 §3.1: channel_default, not
        # keyword-triggered) — announcement in the launch compile.
        return result(rules.channel_default_category, CONFIDENCE_HIGH)

    return result(CATEGORY_OTHER, CONFIDENCE_LOW,
                  clarification="Should I log this as an announcement, or ignore it?")
