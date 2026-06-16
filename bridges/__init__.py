"""
Mission Canvas — Communication Bridges

Platform adapters for email, Slack, WhatsApp, Discord, Signal, Teams, and more.
Each bridge connects MC's governance pipeline to external messaging platforms.

All inbound messages pass through MC governance (sanitizer + classification + store)
before any agent sees the content.

License: Core extracted from Hermes (MIT, Nous Research). Additional bridges written for MC.
"""

from .base import (
    BaseBridge,
    MessageEvent,
    MessageSource,
    MessageType,
    SendResult,
    MessageHandler,
)
from .email_bridge import EmailBridge
from .slack_bridge import SlackBridge
from .whatsapp_bridge import WhatsAppBridge
from .discord_bridge import DiscordBridge
from .signal_bridge import SignalBridge
from .teams_bridge import TeamsBridge

__all__ = [
    "BaseBridge",
    "MessageEvent",
    "MessageSource",
    "MessageType",
    "SendResult",
    "MessageHandler",
    "EmailBridge",
    "SlackBridge",
    "WhatsAppBridge",
    "DiscordBridge",
    "SignalBridge",
    "TeamsBridge",
]
