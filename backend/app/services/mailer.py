"""
Module 9 — sending email.

One rule governs everything here: **email is never allowed to break the thing
it reports on.** A candidate finishing an interview must not see that fail
because a mail server timed out, so every send is best-effort and returns a
result instead of raising. The caller records what happened; it does not have
to handle it.

Nothing is sent until SMTP_HOST is configured. Until then a send is logged in
full and reported as skipped, which keeps the whole notification path testable
and demoable without credentials.
"""

import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class SendResult:
    """
    What happened to one message.

    `skipped` and `failed` are kept apart on purpose. "No mail server is
    configured" is an expected state on a demo machine; "the server rejected
    us" is a fault someone needs to fix, and collapsing the two would hide the
    second behind the first.
    """

    sent: bool
    skipped: bool = False
    error: Optional[str] = None

    @property
    def status(self) -> str:
        if self.sent:
            return "sent"
        return "skipped" if self.skipped else "failed"


def build_message(to: str, subject: str, body: str, html: Optional[str] = None) -> EmailMessage:
    """
    The message itself, separated from delivery so it can be asserted on in a
    test without a socket anywhere near it.
    """
    message = EmailMessage()
    message["From"] = settings.email_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    if html:
        message.add_alternative(html, subtype="html")
    return message


def send_email(to: str, subject: str, body: str, html: Optional[str] = None) -> SendResult:
    """
    Send one message. Never raises.

    Blocking: smtplib is synchronous. Call it from a thread (asyncio.to_thread)
    or a background task rather than from an async request handler, or a slow
    mail server will stall the event loop.
    """
    if not settings.email_enabled:
        logger.info(
            "Email not configured — would have sent to %s: %r", to, subject
        )
        return SendResult(sent=False, skipped=True)

    if not to:
        return SendResult(sent=False, error="No recipient address.")

    message = build_message(to, subject, body, html)

    try:
        if settings.SMTP_USE_TLS:
            with smtplib.SMTP(
                settings.SMTP_HOST, settings.SMTP_PORT, timeout=settings.SMTP_TIMEOUT_SECONDS
            ) as server:
                server.starttls(context=ssl.create_default_context())
                if settings.SMTP_USER:
                    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.send_message(message)
        else:
            with smtplib.SMTP(
                settings.SMTP_HOST, settings.SMTP_PORT, timeout=settings.SMTP_TIMEOUT_SECONDS
            ) as server:
                if settings.SMTP_USER:
                    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.send_message(message)
    except Exception as exc:  # noqa: BLE001
        # Deliberately broad. smtplib raises a wide family (auth, connection,
        # DNS, TLS, timeout), and there is nothing this layer can do about any
        # of them beyond recording the reason and letting the caller continue.
        logger.warning("Email to %s failed: %s", to, exc)
        return SendResult(sent=False, error=str(exc))

    logger.info("Email sent to %s: %r", to, subject)
    return SendResult(sent=True)
