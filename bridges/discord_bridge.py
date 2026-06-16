"""
Mission Canvas — Discord Bridge

Discord adapter using discord.py library.

Environment variables:
    MC_DISCORD_BOT_TOKEN       — Bot token from discord.com/developers
    MC_DISCORD_ALLOWED_CHANNELS — Comma-separated channel IDs (empty = all)
    MC_DISCORD_REQUIRE_MENTION  — If "true", only respond when @mentioned (default: true)

Setup:
    1. Create app at discord.com/developers/applications
    2. Bot section → create bot, copy token
    3. OAuth2 → URL Generator → scopes: bot → permissions: Send Messages, Read Message History
    4. Invite bot to server with generated URL
    5. pip install discord.py
"""

import asyncio
import logging
import os
import re
from typing import Any, Dict, Optional

from .base import BaseBridge, MessageEvent, MessageType, SendResult

logger = logging.getLogger(__name__)

try:
    import discord
    DISCORD_AVAILABLE = True
except ImportError:
    DISCORD_AVAILABLE = False


class DiscordBridge(BaseBridge):
    """Discord bridge for Mission Canvas."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("discord", config or {})
        self._token = os.getenv("MC_DISCORD_BOT_TOKEN", "")
        self._require_mention = os.getenv("MC_DISCORD_REQUIRE_MENTION", "true").lower() == "true"
        self._allowed_channels = set()
        allowed_raw = os.getenv("MC_DISCORD_ALLOWED_CHANNELS", "").strip()
        if allowed_raw:
            self._allowed_channels = {c.strip() for c in allowed_raw.split(",") if c.strip()}
        self._client: Optional[Any] = None
        self._ready = asyncio.Event()

    @classmethod
    def is_configured(cls) -> bool:
        return bool(os.getenv("MC_DISCORD_BOT_TOKEN"))

    async def connect(self) -> bool:
        if not DISCORD_AVAILABLE:
            logger.error("[Discord] discord.py not installed. Run: pip install discord.py")
            return False
        if not self._token:
            logger.error("[Discord] MC_DISCORD_BOT_TOKEN required")
            return False

        intents = discord.Intents.default()
        intents.message_content = True
        self._client = discord.Client(intents=intents)

        @self._client.event
        async def on_ready():
            logger.info("[Discord] Connected as %s", self._client.user)
            self._ready.set()

        @self._client.event
        async def on_message(message):
            await self._on_message(message)

        self._running = True
        asyncio.create_task(self._client.start(self._token))
        await asyncio.wait_for(self._ready.wait(), timeout=30)
        return True

    async def disconnect(self) -> None:
        self._running = False
        if self._client:
            await self._client.close()

    async def _on_message(self, message) -> None:
        # Skip own messages
        if message.author == self._client.user:
            return
        # Skip bots
        if message.author.bot:
            return
        # Channel filter
        if self._allowed_channels and str(message.channel.id) not in self._allowed_channels:
            return
        # Mention filter (skip DMs from this check)
        is_dm = isinstance(message.channel, discord.DMChannel)
        if self._require_mention and not is_dm:
            if self._client.user not in message.mentions:
                return

        text = message.content
        # Strip bot mention
        if self._client.user:
            text = re.sub(rf"<@!?{self._client.user.id}>", "", text).strip()

        if not text:
            return

        source = self.build_source(
            chat_id=str(message.channel.id),
            chat_name=getattr(message.channel, "name", "DM"),
            chat_type="dm" if is_dm else "channel",
            user_id=str(message.author.id),
            user_name=message.author.display_name,
            thread_id=str(message.channel.id) if hasattr(message.channel, "parent") else None,
        )

        event = MessageEvent(
            text=text,
            message_type=MessageType.TEXT,
            source=source,
            message_id=str(message.id),
        )

        await self.handle_message(event)

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        try:
            channel = self._client.get_channel(int(chat_id))
            if not channel:
                channel = await self._client.fetch_channel(int(chat_id))
            # Discord 2000 char limit — chunk if needed
            for i in range(0, len(content), 2000):
                msg = await channel.send(content[i:i+2000])
            return SendResult(success=True, message_id=str(msg.id))
        except Exception as e:
            logger.error("[Discord] Send failed: %s", e)
            return SendResult(success=False, error=str(e))

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        try:
            channel = self._client.get_channel(int(chat_id))
            return {"name": getattr(channel, "name", chat_id), "type": "channel", "chat_id": chat_id}
        except Exception:
            return {"name": chat_id, "type": "unknown", "chat_id": chat_id}
