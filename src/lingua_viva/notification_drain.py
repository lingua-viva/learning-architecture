"""Drain for the safeguarding notification outbox (integration, 2026-08-09).

Closes W2's gap #1: safeguarding.py deliberately contains no network code —
its outbox entries sit at ``queued`` (channel configured) or
``pending_config`` (not configured). This module is the delivery side:
explicitly invoked (route/CLI — never a background loop), it posts each
``queued`` entry's content-free summary to the designated Slack channel via
the existing ``slack_integration.post_slack_message`` chokepoint.

Discipline:
- ``pending_config`` entries are never delivered — config first.
- Entries carry no student names or narrative (enforced upstream); this
  module still refuses to send anything but the stored summary line.
- Delivery failure keeps the entry ``queued`` with ``last_error`` recorded —
  fail-soft, never fail-silent.
"""

from __future__ import annotations

import json
import os
from typing import Callable, Optional

from src.lingua_viva.safeguarding import (
    notifications_path,
    safeguarding_config,
)


def _read_all(path) -> list[dict]:
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def _write_all(path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries)
    path.write_text(text, encoding="utf-8")


def drain_notifications(
    *,
    transport: Optional[Callable[[str, str, str], None]] = None,
) -> dict:
    """Deliver queued safeguarding notifications; return an honest tally.

    ``transport(bot_token, channel, text)`` is injectable for tests; the
    default is the existing Slack Web API chokepoint.
    """
    from src.lingua_viva.safeguarding import _now  # shared timestamp format

    config = safeguarding_config()
    channel = config.get("safeguarding_channel") or ""
    bot_token = os.environ.get("SLACK_BOT_TOKEN", "")

    path = notifications_path()
    entries = _read_all(path)
    tally = {"delivered": 0, "failed": 0, "pending_config": 0, "skipped": 0}

    if transport is None:
        from src.lingua_viva.slack_integration import post_slack_message as transport  # type: ignore[assignment]

    for entry in entries:
        status = entry.get("status")
        if status == "pending_config":
            tally["pending_config"] += 1
            continue
        if status != "queued":
            tally["skipped"] += 1
            continue
        if not channel or not bot_token:
            # Configured state regressed (channel/token removed) — be honest.
            entry["last_error"] = "missing safeguarding_channel or SLACK_BOT_TOKEN"
            tally["failed"] += 1
            continue
        # Content discipline: only the stored generic summary ever leaves.
        text = f"[Lingua Viva] {entry.get('summary', 'A restricted item requires review.')}"
        try:
            transport(bot_token, channel, text)
        except Exception as exc:  # noqa: BLE001 — record, keep queued
            entry["last_error"] = str(exc)
            tally["failed"] += 1
            continue
        entry["status"] = "delivered"
        entry["delivered_at"] = _now()
        entry.pop("last_error", None)
        tally["delivered"] += 1

    _write_all(path, entries)
    return {"channel_configured": bool(channel), **tally}
