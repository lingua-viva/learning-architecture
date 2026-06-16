"""
Mission Canvas — Email Bridge

IMAP/SMTP email adapter. Works with any provider:
  Gmail, Outlook/Office365, Yahoo, ProtonMail (bridge), Exchange, etc.

Extracted from Hermes (MIT, Nous Research), adapted for MC governance pipeline.

Environment variables:
    MC_EMAIL_ADDRESS       — Agent's email address
    MC_EMAIL_PASSWORD      — App password (Gmail: myaccount.google.com/apppasswords)
    MC_EMAIL_IMAP_HOST     — IMAP host (e.g., imap.gmail.com)
    MC_EMAIL_IMAP_PORT     — IMAP port (default: 993)
    MC_EMAIL_SMTP_HOST     — SMTP host (e.g., smtp.gmail.com)
    MC_EMAIL_SMTP_PORT     — SMTP port (default: 587)
    MC_EMAIL_POLL_INTERVAL — Seconds between checks (default: 30)
    MC_EMAIL_ALLOWED_SENDERS — Comma-separated allowed sender addresses (empty = all)

Provider quick reference:
    Gmail:      imap.gmail.com:993 / smtp.gmail.com:587
    Outlook:    outlook.office365.com:993 / smtp.office365.com:587
    Yahoo:      imap.mail.yahoo.com:993 / smtp.mail.yahoo.com:587
    ProtonMail: 127.0.0.1:1143 / 127.0.0.1:1025 (requires ProtonMail Bridge)
    FastMail:   imap.fastmail.com:993 / smtp.fastmail.com:587
"""

import asyncio
import email as email_lib
import imaplib
import logging
import os
import re
import smtplib
import ssl
import uuid
from email.header import decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.utils import formatdate
from email import encoders
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .base import BaseBridge, MessageEvent, MessageType, SendResult

logger = logging.getLogger(__name__)

# Automated sender patterns — silently ignored
_NOREPLY_PATTERNS = (
    "noreply", "no-reply", "no_reply", "donotreply", "do-not-reply",
    "mailer-daemon", "postmaster", "bounce", "notifications@",
    "automated@", "auto-confirm", "auto-reply", "automailer",
)

# RFC headers indicating bulk/automated mail
_AUTOMATED_HEADERS = {
    "Auto-Submitted": lambda v: v.lower() != "no",
    "Precedence": lambda v: v.lower() in {"bulk", "list", "junk"},
    "X-Auto-Response-Suppress": lambda v: bool(v),
    "List-Unsubscribe": lambda v: bool(v),
}


def _is_automated_sender(address: str, headers: dict) -> bool:
    addr = address.lower()
    if any(pattern in addr for pattern in _NOREPLY_PATTERNS):
        return True
    for header, check in _AUTOMATED_HEADERS.items():
        value = headers.get(header, "")
        if value and check(value):
            return True
    return False


def _decode_header_value(raw: str) -> str:
    parts = decode_header(raw)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return " ".join(decoded)


def _extract_email_address(raw: str) -> str:
    match = re.search(r"<([^>]+)>", raw)
    if match:
        return match.group(1).strip().lower()
    return raw.strip().lower()


def _extract_text_body(msg: email_lib.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", ""))
            if "attachment" in disposition:
                continue
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
        # Fallback: strip HTML
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", ""))
            if "attachment" in disposition:
                continue
            if content_type == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return _strip_html(payload.decode(charset, errors="replace"))
        return ""
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")
            if msg.get_content_type() == "text/html":
                return _strip_html(text)
            return text
        return ""


def _strip_html(html: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"<p[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class EmailBridge(BaseBridge):
    """IMAP/SMTP email bridge for Mission Canvas."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("email", config or {})
        self._address = os.getenv("MC_EMAIL_ADDRESS", "")
        self._password = os.getenv("MC_EMAIL_PASSWORD", "")
        self._imap_host = os.getenv("MC_EMAIL_IMAP_HOST", "")
        self._imap_port = int(os.getenv("MC_EMAIL_IMAP_PORT", "993"))
        self._smtp_host = os.getenv("MC_EMAIL_SMTP_HOST", "")
        self._smtp_port = int(os.getenv("MC_EMAIL_SMTP_PORT", "587"))
        self._poll_interval = int(os.getenv("MC_EMAIL_POLL_INTERVAL", "30"))
        self._allowed_senders = set()
        allowed_raw = os.getenv("MC_EMAIL_ALLOWED_SENDERS", "").strip()
        if allowed_raw:
            self._allowed_senders = {a.strip().lower() for a in allowed_raw.split(",") if a.strip()}

        self._seen_uids: set = set()
        self._seen_uids_max = 2000
        self._poll_task: Optional[asyncio.Task] = None
        self._thread_context: Dict[str, Dict[str, str]] = {}

    @classmethod
    def is_configured(cls) -> bool:
        """Check if required env vars are set."""
        return all([
            os.getenv("MC_EMAIL_ADDRESS"),
            os.getenv("MC_EMAIL_PASSWORD"),
            os.getenv("MC_EMAIL_IMAP_HOST"),
            os.getenv("MC_EMAIL_SMTP_HOST"),
        ])

    async def connect(self) -> bool:
        try:
            imap = imaplib.IMAP4_SSL(self._imap_host, self._imap_port, timeout=30)
            imap.login(self._address, self._password)
            imap.select("INBOX")
            status, data = imap.uid("search", None, "ALL")
            if status == "OK" and data and data[0]:
                for uid in data[0].split():
                    self._seen_uids.add(uid)
            imap.logout()
            logger.info("[Email] Connected. %d existing messages skipped.", len(self._seen_uids))
        except Exception as e:
            logger.error("[Email] IMAP connection failed: %s", e)
            return False

        try:
            smtp = smtplib.SMTP(self._smtp_host, self._smtp_port, timeout=30)
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(self._address, self._password)
            smtp.quit()
            logger.info("[Email] SMTP verified.")
        except Exception as e:
            logger.error("[Email] SMTP connection failed: %s", e)
            return False

        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        return True

    async def disconnect(self) -> None:
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                await self._check_inbox()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("[Email] Poll error: %s", e)
            await asyncio.sleep(self._poll_interval)

    async def _check_inbox(self) -> None:
        loop = asyncio.get_running_loop()
        messages = await loop.run_in_executor(None, self._fetch_new_messages)
        for msg_data in messages:
            await self._dispatch_message(msg_data)

    def _fetch_new_messages(self) -> List[Dict[str, Any]]:
        results = []
        try:
            imap = imaplib.IMAP4_SSL(self._imap_host, self._imap_port, timeout=30)
            try:
                imap.login(self._address, self._password)
                imap.select("INBOX")
                status, data = imap.uid("search", None, "UNSEEN")
                if status != "OK" or not data or not data[0]:
                    return results
                for uid in data[0].split():
                    if uid in self._seen_uids:
                        continue
                    self._seen_uids.add(uid)
                    if len(self._seen_uids) > self._seen_uids_max:
                        sorted_uids = sorted(self._seen_uids, key=lambda u: int(u))
                        self._seen_uids = set(sorted_uids[-(self._seen_uids_max // 2):])

                    status, msg_data = imap.uid("fetch", uid, "(RFC822)")
                    if status != "OK":
                        continue
                    raw_email = msg_data[0][1]
                    msg = email_lib.message_from_bytes(raw_email)
                    sender_raw = msg.get("From", "")
                    sender_addr = _extract_email_address(sender_raw)
                    sender_name = _decode_header_value(sender_raw)
                    if "<" in sender_name:
                        sender_name = sender_name.split("<")[0].strip().strip('"')
                    subject = _decode_header_value(msg.get("Subject", "(no subject)"))
                    message_id = msg.get("Message-ID", "")
                    in_reply_to = msg.get("In-Reply-To", "")
                    msg_headers = dict(msg.items())
                    if _is_automated_sender(sender_addr, msg_headers):
                        continue
                    body = _extract_text_body(msg)
                    results.append({
                        "uid": uid,
                        "sender_addr": sender_addr,
                        "sender_name": sender_name,
                        "subject": subject,
                        "message_id": message_id,
                        "in_reply_to": in_reply_to,
                        "body": body,
                    })
            finally:
                try:
                    imap.logout()
                except Exception:
                    pass
        except Exception as e:
            logger.error("[Email] IMAP fetch error: %s", e)
        return results

    async def _dispatch_message(self, msg_data: Dict[str, Any]) -> None:
        sender_addr = msg_data["sender_addr"]
        if sender_addr == self._address.lower():
            return
        if self._allowed_senders and sender_addr not in self._allowed_senders:
            return

        subject = msg_data["subject"]
        body = msg_data["body"].strip()
        text = body
        if subject and not subject.startswith("Re:"):
            text = f"[Subject: {subject}]\n\n{body}"

        self._thread_context[sender_addr] = {
            "subject": subject,
            "message_id": msg_data["message_id"],
        }

        source = self.build_source(
            chat_id=sender_addr,
            chat_name=msg_data["sender_name"] or sender_addr,
            chat_type="dm",
            user_id=sender_addr,
            user_name=msg_data["sender_name"] or sender_addr,
        )

        event = MessageEvent(
            text=text or "(empty email)",
            message_type=MessageType.TEXT,
            source=source,
            message_id=msg_data["message_id"],
            reply_to_message_id=msg_data["in_reply_to"] or None,
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
            loop = asyncio.get_running_loop()
            message_id = await loop.run_in_executor(
                None, self._send_email, chat_id, content, reply_to
            )
            return SendResult(success=True, message_id=message_id)
        except Exception as e:
            logger.error("[Email] Send failed to %s: %s", chat_id, e)
            return SendResult(success=False, error=str(e))

    def _send_email(self, to_addr: str, body: str, reply_to_msg_id: Optional[str] = None) -> str:
        msg = MIMEMultipart()
        msg["From"] = self._address
        msg["To"] = to_addr

        ctx = self._thread_context.get(to_addr, {})
        subject = ctx.get("subject", "Mission Canvas")
        if not subject.startswith("Re:"):
            subject = f"Re: {subject}"
        msg["Subject"] = subject

        original_msg_id = reply_to_msg_id or ctx.get("message_id")
        if original_msg_id:
            msg["In-Reply-To"] = original_msg_id
            msg["References"] = original_msg_id

        msg["Date"] = formatdate(localtime=True)
        msg_id = f"<mc-{uuid.uuid4().hex[:12]}@{self._address.split('@')[1]}>"
        msg["Message-ID"] = msg_id

        msg.attach(MIMEText(body, "plain", "utf-8"))

        smtp = smtplib.SMTP(self._smtp_host, self._smtp_port, timeout=30)
        try:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(self._address, self._password)
            smtp.send_message(msg)
        finally:
            try:
                smtp.quit()
            except Exception:
                smtp.close()

        logger.info("[Email] Sent reply to %s (subject: %s)", to_addr, subject)
        return msg_id

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        ctx = self._thread_context.get(chat_id, {})
        return {"name": chat_id, "type": "dm", "subject": ctx.get("subject", "")}
