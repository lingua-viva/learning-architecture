"""
Mission Canvas Telegram Bot

Brings Mission Canvas to where professionals already live.
Every message goes through the same governed pipeline.

Usage:
    TELEGRAM_BOT_TOKEN=xxx python bridges/telegram/bot.py

Commands:
    /protect <query>  — force PROTECT intent (local only)
    /research <query> — force RESEARCH intent
    /decide <query>   — force DECIDE intent
    /health           — run health check
    /stats            — show compounding metrics
    Any text          — auto-classify and process

The bot is a surface, not a brain. The pipeline does the thinking.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Optional
from urllib import request, error, parse

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


class TelegramBot:
    """Minimal Telegram bot that routes messages through the MC pipeline."""

    def __init__(self, token: str):
        self._token = token
        self._offset = 0

    def run(self):
        """Poll for updates and process them."""
        print("Mission Canvas Telegram bot started")
        while True:
            updates = self._get_updates()
            for update in updates:
                self._handle_update(update)
                self._offset = update["update_id"] + 1

    def _get_updates(self) -> list:
        url = TELEGRAM_API.format(token=self._token, method="getUpdates")
        url += f"?offset={self._offset}&timeout=30"
        try:
            with request.urlopen(url, timeout=35) as resp:
                data = json.loads(resp.read())
                return data.get("result", [])
        except Exception:
            return []

    def _handle_update(self, update: dict):
        msg = update.get("message", {})
        text = msg.get("text", "")
        chat_id = msg.get("chat", {}).get("id")
        if not text or not chat_id:
            return

        # Parse command
        intent = None
        query = text
        if text.startswith("/protect "):
            intent, query = "PROTECT", text[9:]
        elif text.startswith("/research "):
            intent, query = "RESEARCH", text[10:]
        elif text.startswith("/decide "):
            intent, query = "DECIDE", text[8:]
        elif text.startswith("/create "):
            intent, query = "CREATE", text[8:]
        elif text.startswith("/health"):
            self._send_health(chat_id)
            return
        elif text.startswith("/stats"):
            self._send_stats(chat_id)
            return
        elif text.startswith("/"):
            self._send(chat_id, "Commands: /protect, /research, /decide, /create, /health, /stats")
            return

        # Run through pipeline
        self._send(chat_id, "Processing...")
        try:
            result = asyncio.run(self._run_pipeline(query, intent))
            response = self._format_response(result)
            self._send(chat_id, response)
        except Exception as e:
            self._send(chat_id, f"Error: {e}")

    async def _run_pipeline(self, query: str, intent: Optional[str] = None) -> dict:
        from src.pipeline import Pipeline
        pipeline = Pipeline()
        result = await pipeline.run(query, intent=intent)
        return {
            "node": result.classification.riu_id,
            "name": result.classification.name,
            "confidence": result.path_record.confidence_at_exit,
            "content": result.synthesis.content,
            "external": result.external_called,
            "steps": result.steps_executed,
            "citations": result.synthesis.citations,
            "gaps": result.gap_signals,
        }

    def _format_response(self, result: dict) -> str:
        lines = [
            f"*{result['name']}* ({result['node']})",
            f"Confidence: {result['confidence']:.0%}",
            f"Steps: {' → '.join(result['steps'])}",
            "",
            result["content"][:3500],  # Telegram 4096 char limit
        ]
        if result["citations"]:
            lines.append("\n*Sources:*")
            for c in result["citations"][:5]:
                lines.append(f"  {c}")
        if result["gaps"]:
            lines.append(f"\n⚠ {len(result['gaps'])} gap signal(s)")
        return "\n".join(lines)

    def _send_health(self, chat_id: int):
        from src.integrity.health_check import HealthCheck
        hc = HealthCheck()
        result = hc.run()
        text = f"Health: {result.score:.0%} ({result.checks_passed}/{result.checks_total})\n"
        for section, data in result.sections.items():
            status = "✓" if data["passed"] == data["total"] else "⚠"
            text += f"  {status} {section}: {data['passed']}/{data['total']}\n"
        self._send(chat_id, text)

    def _send_stats(self, chat_id: int):
        from ontology.engine import OntologyEngine
        from knowledge import KnowledgeStore
        from memory.store import MemoryStore
        engine = OntologyEngine()
        kl = KnowledgeStore()
        memory = MemoryStore()
        text = (
            f"*Mission Canvas*\n"
            f"Nodes: {engine.node_count}\n"
            f"Knowledge: {kl.entry_count} entries\n"
            f"Paths: {memory.total_path_count()}\n"
            f"Gaps: {memory.gap_signal_count()}\n"
            f"Redis: {'✓' if memory.redis_connected() else '✗'}"
        )
        self._send(chat_id, text)

    def _send(self, chat_id: int, text: str):
        url = TELEGRAM_API.format(token=self._token, method="sendMessage")
        payload = json.dumps({
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
        }).encode()
        req = request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        try:
            request.urlopen(req, timeout=10)
        except Exception:
            # Retry without markdown if parsing fails
            payload = json.dumps({"chat_id": chat_id, "text": text}).encode()
            req = request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            try:
                request.urlopen(req, timeout=10)
            except Exception:
                pass


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Set TELEGRAM_BOT_TOKEN environment variable")
        sys.exit(1)
    bot = TelegramBot(token)
    bot.run()


if __name__ == "__main__":
    main()
