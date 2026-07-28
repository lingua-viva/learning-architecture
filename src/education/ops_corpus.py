"""
Ops test-corpus runner (spec SPEC_LV_SLACK_OPS_V2_WORKFLOW_PACKS §7).

Feeds every pack sample plus the admin-added sentences stored in the
bot-spec through the compiled rule set and compares actual vs expected
routing per sentence. The same runner is BOTH gates:

  - Go-live: the setup panel's corpus-run route records the result
    (timestamp + result hash) into the bot-spec; the PUT go-live toggle
    requires `corpus.last_run.passed` (a school never goes live on
    untested rules).
  - Candidate rules: the approve ceremony runs the corpus against a
    hypothetical compile WITH the candidate approved — zero
    previously-passing samples may change routing, so approval requires
    a fully passing run.

Determinism (spec §7): expectations use RELATIVE dates ("+1d", "+0d")
resolved against an injected reference `today`; the classifier already
takes `today` as a parameter, so corpus runs never rot. Weekday-name
offsets are deliberately NOT supported: `extract_date` has no
weekday-name resolution, so no classification can ever produce one — an
expectation form the classifier cannot satisfy would be a permanent
red row, not a test.

Fail-closed rules:
  - An empty corpus (no samples at all) never passes.
  - An unknown key in an `expect` block fails that row (a typo like
    `catgory:` must not silently pass).
  - The result hash covers the comparison-normalized rows (text,
    relative expectations, actual category, ok) — stable across days.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from src.education.ops_bot_spec import CompiledBotSpec
from src.education.ops_classifier import classify_ops_message

_RELATIVE_DATE_RE = re.compile(r"^\+(\d+)d$")

# The only keys an expect block may carry. `channel` is an input
# directive (run the sample as an ops-channel post), not an assertion.
_KNOWN_EXPECT_KEYS = frozenset(
    {
        "category",
        "confidence",
        "date_for",
        "periods",
        "wants_coverage",
        "time_window",
        "subject",
        "channel",
    }
)


class CorpusError(ValueError):
    """A sample/expectation is structurally unusable."""


def resolve_expected_date(token: str, today: date) -> Optional[str]:
    """Resolve a relative-date expectation ('+1d', '+0d') to ISO against
    the injected reference day. Returns None for unresolvable tokens —
    the row then fails with an explicit mismatch, never a crash."""
    match = _RELATIVE_DATE_RE.match(str(token or "").strip())
    if match:
        return (today + timedelta(days=int(match.group(1)))).isoformat()
    return None


@dataclass(frozen=True)
class CorpusRow:
    text: str
    source: str          # pack id, or "admin" for bot-spec sentences
    expect: dict         # as authored (relative dates preserved)
    actual: dict         # classifier projection for the panel table
    ok: bool
    mismatches: tuple    # field names (or "unknown expectation: X")

    def as_payload(self) -> dict:
        return {
            "text": self.text,
            "source": self.source,
            "expect": dict(self.expect),
            "actual": dict(self.actual),
            "ok": self.ok,
            "mismatches": list(self.mismatches),
        }


@dataclass(frozen=True)
class CorpusRunResult:
    rows: tuple
    total: int
    failed: int
    passed: bool
    result_hash: str
    at: str

    def last_run(self) -> dict:
        """The record the bot-spec stores (spec §7: timestamp + result
        hash; totals so the panel can summarize without re-running)."""
        return {
            "at": self.at,
            "passed": self.passed,
            "result_hash": self.result_hash,
            "total": self.total,
            "failed": self.failed,
        }

    def as_payload(self) -> dict:
        return {
            "rows": [row.as_payload() for row in self.rows],
            "run": self.last_run(),
        }


def collect_samples(spec: CompiledBotSpec) -> list:
    """Pack samples (from the compiled rule set — only ENABLED packs
    contribute) plus admin sentences stored in the bot-spec, in stable
    order: packs first, admin last."""
    combined = [
        {"text": s.text, "expect": dict(s.expect), "source": s.pack_id or "pack"}
        for s in spec.rule_set.samples
    ]
    for raw in spec.corpus_sentences:
        combined.append(
            {
                "text": str(raw.get("text") or ""),
                "expect": dict(raw.get("expect") or {}),
                "source": "admin",
            }
        )
    return combined


def _check_row(sample: dict, *, today: date, rule_set) -> CorpusRow:
    text = sample["text"]
    expect = sample["expect"]
    as_ops_channel = str(expect.get("channel") or "").strip().lower() == "ops"
    # ALWAYS classify against the spec under test, never the installed
    # process-wide compile — the candidate-approve gate runs against a
    # HYPOTHETICAL compile that must not be installed unless it passes.
    classified = classify_ops_message(
        text,
        today=today,
        is_dm=not as_ops_channel,
        is_ops_channel=as_ops_channel,
        rule_set=rule_set,
    )
    actual = {
        "category": classified.category,
        "confidence": classified.confidence,
        "date_for": classified.date_for,
        "time_window": classified.time_window,
        "periods": list(classified.periods or ()),
        "wants_coverage": bool(classified.wants_coverage),
        "subject": classified.subject,
    }

    mismatches = []
    for key in expect:
        if key not in _KNOWN_EXPECT_KEYS:
            mismatches.append(f"unknown expectation: {key}")
    if "category" not in expect:
        mismatches.append("expectation missing category")

    checks = {
        "category": lambda want: str(want) == actual["category"],
        "confidence": lambda want: str(want) == actual["confidence"],
        "date_for": lambda want: resolve_expected_date(want, today)
        == actual["date_for"],
        "periods": lambda want: [int(p) for p in (want or [])] == actual["periods"],
        "wants_coverage": lambda want: bool(want) == actual["wants_coverage"],
        "time_window": lambda want: str(want) == (actual["time_window"] or ""),
        "subject": lambda want: str(want) == (actual["subject"] or ""),
    }
    for key, check in checks.items():
        if key in expect and not check(expect[key]):
            mismatches.append(key)

    return CorpusRow(
        text=text,
        source=sample["source"],
        expect=dict(expect),
        actual=actual,
        ok=not mismatches,
        mismatches=tuple(mismatches),
    )


def run_corpus(spec: CompiledBotSpec, *, today: Optional[date] = None) -> CorpusRunResult:
    """Run every sample through the spec's compiled rule set. `today` is
    injectable for tests; live routes use the real date — results are
    date-independent because expectations are relative."""
    from src.education.ops_bot_spec import utc_now_iso

    reference = today or date.today()
    rows = tuple(
        _check_row(sample, today=reference, rule_set=spec.rule_set)
        for sample in collect_samples(spec)
    )
    failed = sum(1 for row in rows if not row.ok)
    total = len(rows)
    # Hash the comparison-normalized rows — stable across days because
    # expectations stay relative and `ok` is the resolved comparison.
    digest_input = json.dumps(
        [
            {
                "text": row.text,
                "source": row.source,
                "expect": row.expect,
                "actual_category": row.actual["category"],
                "ok": row.ok,
                "mismatches": list(row.mismatches),
            }
            for row in rows
        ],
        sort_keys=True,
        ensure_ascii=True,
    ).encode("utf-8")
    return CorpusRunResult(
        rows=rows,
        total=total,
        failed=failed,
        passed=(failed == 0 and total > 0),
        result_hash=hashlib.sha256(digest_input).hexdigest(),
        at=utc_now_iso(),
    )
