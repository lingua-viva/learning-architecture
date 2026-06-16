"""
Mission Canvas — Communication Bridges Base

Minimal abstract interface for platform adapters.
Extracted from Hermes (MIT, Nous Research) and stripped to MC essentials.

Each bridge:
1. Connects to a platform (IMAP, Slack WebSocket, WhatsApp, etc.)
2. Polls or listens for inbound messages
3. Emits MessageEvent objects to a handler callback
4. Sends replies back through the platform

The handler callback is where MC governance fires:
  inbound message → sanitizer → classification → agent → response → send()
"""

import asyncio
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Awaitable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class MessageType(Enum):
    TEXT = "text"
    PHOTO = "image"
    DOCUMENT = "document"
    VOICE = "voice"
    VIDEO = "video"


@dataclass
class MessageSource:
    """Where a message came from."""
    platform: str           # "email", "slack", "whatsapp", "telegram"
    chat_id: str            # unique conversation identifier
    chat_name: str          # display name of chat/channel
    chat_type: str          # "dm", "channel", "group"
    user_id: str            # sender identifier
    user_name: str          # sender display name
    thread_id: Optional[str] = None


@dataclass
class MessageEvent:
    """An inbound message from any platform."""
    text: str
    message_type: MessageType = MessageType.TEXT
    source: MessageSource = None
    message_id: str = ""
    media_urls: List[str] = field(default_factory=list)
    media_types: List[str] = field(default_factory=list)
    reply_to_message_id: Optional[str] = None
    timestamp: str = ""


@dataclass
class SendResult:
    """Result of sending a message."""
    success: bool
    message_id: str = ""
    error: str = ""


# Type for the message handler callback
MessageHandler = Callable[[MessageEvent], Awaitable[Optional[str]]]


class BaseBridge(ABC):
    """Abstract base for all MC communication bridges."""

    def __init__(self, platform: str, config: Dict[str, Any]):
        self.platform = platform
        self.config = config
        self._running = False
        self._handler: Optional[MessageHandler] = None

    def on_message(self, handler: MessageHandler):
        """Register the callback that handles inbound messages."""
        self._handler = handler

    async def handle_message(self, event: MessageEvent):
        """Dispatch an inbound message to the registered handler.

        Governance is enforced HERE, at the base class level, so all bridges
        are governed by default. A developer cannot implement a bridge that
        accidentally skips sanitization.
        """
        if not self._handler:
            logger.warning("[%s] No message handler registered, dropping message", self.platform)
            return

        # Governance gate: sanitize inbound text before any handler sees it.
        # Uses the unified sanitizer (direct import for same-process use).
        try:
            from sanitizer.app import sanitize
            result = sanitize(event.text, context="general")
            if result["blocked"]:
                logger.warning("[%s] Inbound message blocked by sanitizer: %s", self.platform, result["reason"])
                await self.send(event.source.chat_id, "This message was blocked by governance policy.", reply_to=event.message_id)
                return
            if result["redactions"]:
                logger.info("[%s] Inbound message sanitized: %d redactions", self.platform, len(result["redactions"]))
                event.text = result["text"]  # Handler sees sanitized version
        except ImportError:
            logger.warning("[%s] Sanitizer not available — proceeding without governance", self.platform)

        try:
            response = await self._handler(event)
            if response:
                await self.send(event.source.chat_id, response, reply_to=event.message_id)
        except Exception as e:
            logger.error("[%s] Handler error: %s", self.platform, e)

    @abstractmethod
    async def connect(self) -> bool:
        """Connect to the platform. Return True on success."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the platform."""
        ...

    @abstractmethod
    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Send a message to the given chat."""
        ...

    async def send_document(
        self,
        chat_id: str,
        file_path: str,
        caption: Optional[str] = None,
        **kwargs,
    ) -> SendResult:
        """Send a file. Default: send caption as text."""
        return await self.send(chat_id, caption or f"[File: {file_path}]")

    def build_source(
        self,
        chat_id: str,
        chat_name: str = "",
        chat_type: str = "dm",
        user_id: str = "",
        user_name: str = "",
        thread_id: Optional[str] = None,
    ) -> MessageSource:
        return MessageSource(
            platform=self.platform,
            chat_id=chat_id,
            chat_name=chat_name or chat_id,
            chat_type=chat_type,
            user_id=user_id or chat_id,
            user_name=user_name or chat_id,
            thread_id=thread_id,
        )
