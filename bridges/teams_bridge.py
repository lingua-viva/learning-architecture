"""
Mission Canvas — Microsoft Teams Bridge

Teams adapter using Microsoft Graph API (webhook-based).
For enterprise/corporate clients (Tropical IT, etc.)

Environment variables:
    MC_TEAMS_CLIENT_ID      — Azure App Registration client ID
    MC_TEAMS_CLIENT_SECRET  — Azure App Registration client secret
    MC_TEAMS_TENANT_ID      — Azure AD tenant ID
    MC_TEAMS_ALLOWED_USERS  — Comma-separated user IDs (empty = all)
    MC_TEAMS_WEBHOOK_PORT   — Local webhook port (default: 8646)

Setup:
    1. Azure Portal → App registrations → New registration
    2. Add Bot Framework channel
    3. API permissions: Chat.Read, Chat.ReadWrite, User.Read
    4. Install bot to Teams via App Studio
    5. Set env vars

Note: Also works for reading Outlook email via Graph API if configured
with Mail.Read permission.
"""

import asyncio
import json
import logging
import os
from typing import Any, Dict, Optional

from .base import BaseBridge, MessageEvent, MessageType, SendResult

logger = logging.getLogger(__name__)

try:
    from aiohttp import web
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False


class TeamsBridge(BaseBridge):
    """Microsoft Teams bridge for Mission Canvas via Bot Framework webhook."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("teams", config or {})
        self._client_id = os.getenv("MC_TEAMS_CLIENT_ID", "")
        self._client_secret = os.getenv("MC_TEAMS_CLIENT_SECRET", "")
        self._tenant_id = os.getenv("MC_TEAMS_TENANT_ID", "")
        self._webhook_port = int(os.getenv("MC_TEAMS_WEBHOOK_PORT", "8646"))
        self._allowed_users = set()
        allowed_raw = os.getenv("MC_TEAMS_ALLOWED_USERS", "").strip()
        if allowed_raw:
            self._allowed_users = {u.strip() for u in allowed_raw.split(",") if u.strip()}
        self._app: Optional[Any] = None
        self._runner: Optional[Any] = None
        self._access_token: str = ""

    @classmethod
    def is_configured(cls) -> bool:
        return all([
            os.getenv("MC_TEAMS_CLIENT_ID"),
            os.getenv("MC_TEAMS_CLIENT_SECRET"),
            os.getenv("MC_TEAMS_TENANT_ID"),
        ])

    async def _get_token(self) -> str:
        """Get OAuth2 token from Azure AD."""
        import aiohttp
        url = f"https://login.microsoftonline.com/{self._tenant_id}/oauth2/v2.0/token"
        data = {
            "grant_type": "client_credentials",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "scope": "https://api.botframework.com/.default",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data) as resp:
                result = await resp.json()
                return result.get("access_token", "")

    async def connect(self) -> bool:
        if not AIOHTTP_AVAILABLE:
            logger.error("[Teams] aiohttp not installed. Run: pip install aiohttp")
            return False
        if not self._client_id:
            logger.error("[Teams] MC_TEAMS_CLIENT_ID required")
            return False

        try:
            self._access_token = await self._get_token()
            if not self._access_token:
                logger.error("[Teams] Failed to get access token")
                return False
        except Exception as e:
            logger.error("[Teams] Auth failed: %s", e)
            return False

        # Start webhook server
        self._app = web.Application()
        self._app.router.add_post("/api/messages", self._webhook_handler)
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", self._webhook_port)
        await site.start()
        self._running = True
        logger.info("[Teams] Webhook listening on port %d", self._webhook_port)
        return True

    async def disconnect(self) -> None:
        self._running = False
        if self._runner:
            await self._runner.cleanup()

    async def _webhook_handler(self, request) -> web.Response:
        try:
            data = await request.json()
            if data.get("type") == "message":
                await self._on_message(data)
            return web.Response(status=200)
        except Exception as e:
            logger.error("[Teams] Webhook error: %s", e)
            return web.Response(status=500)

    async def _on_message(self, activity: dict) -> None:
        text = activity.get("text", "").strip()
        sender = activity.get("from", {})
        user_id = sender.get("id", "")
        user_name = sender.get("name", "")
        conversation = activity.get("conversation", {})
        chat_id = conversation.get("id", "")

        if not text:
            return
        if self._allowed_users and user_id not in self._allowed_users:
            return

        # Strip bot mention (Teams includes <at>BotName</at> in text)
        import re
        text = re.sub(r"<at>.*?</at>", "", text).strip()

        source = self.build_source(
            chat_id=chat_id,
            chat_name=conversation.get("name", chat_id),
            chat_type="channel" if conversation.get("isGroup") else "dm",
            user_id=user_id,
            user_name=user_name,
        )

        event = MessageEvent(
            text=text,
            message_type=MessageType.TEXT,
            source=source,
            message_id=activity.get("id", ""),
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
            import aiohttp
            service_url = (metadata or {}).get("serviceUrl", "https://smba.trafficmanager.net/teams/")
            url = f"{service_url}v3/conversations/{chat_id}/activities"
            headers = {
                "Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json",
            }
            payload = {"type": "message", "text": content}
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status == 200 or resp.status == 201:
                        result = await resp.json()
                        return SendResult(success=True, message_id=result.get("id", ""))
                    else:
                        return SendResult(success=False, error=f"HTTP {resp.status}")
        except Exception as e:
            logger.error("[Teams] Send failed: %s", e)
            return SendResult(success=False, error=str(e))

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        return {"name": chat_id, "type": "channel", "chat_id": chat_id}
