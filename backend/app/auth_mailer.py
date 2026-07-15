"""Provider-neutral delivery boundary for authentication email.

The application creates and stores only hashes of verification/reset secrets.
Adapters receive the one plaintext value long enough to deliver it. The memory
adapter is intentionally limited to development/test and never writes messages
to disk or application logs. Production stays fail-closed until an operator
injects a reviewed external adapter.
"""

from __future__ import annotations

import html
import logging
import queue
import re
import smtplib
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid, parseaddr
from threading import Lock, Thread
from typing import Callable, Protocol
from urllib.parse import urlencode, urlsplit


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthEmail:
    purpose: str
    recipient: str
    challenge_id: str
    secret: str
    expires_at: str


@dataclass(frozen=True)
class SecurityEmail:
    """A secret-free notice sent after a sensitive account change commits."""

    purpose: str
    recipient: str
    occurred_at: str


class AuthMailer(Protocol):
    @property
    def ready(self) -> bool: ...

    @property
    def mode(self) -> str: ...

    def send(self, message: AuthEmail | SecurityEmail) -> None: ...


class AuthTaskDispatcher(Protocol):
    def submit(self, task: Callable[[], None]) -> bool: ...


class InlineAuthTaskDispatcher:
    """Deterministic service-test dispatcher; production injects a bounded queue."""

    def submit(self, task: Callable[[], None]) -> bool:
        task()
        return True


class BoundedAuthTaskDispatcher:
    """Small daemon worker pool so public recovery responses never wait on SMTP."""

    def __init__(self, *, workers: int = 2, capacity: int = 100) -> None:
        if workers < 1 or capacity < workers:
            raise ValueError("Authentication dispatcher capacity is invalid")
        self._queue: queue.Queue[Callable[[], None]] = queue.Queue(maxsize=capacity)
        self._stats_lock = Lock()
        self._submitted = 0
        self._completed = 0
        self._failed = 0
        self._dropped = 0
        for index in range(workers):
            worker = Thread(
                target=self._run,
                name=f"auth-email-{index + 1}",
                daemon=True,
            )
            worker.start()

    def _run(self) -> None:
        while True:
            task = self._queue.get()
            try:
                task()
            except Exception:
                # Public recovery is intentionally generic. The learner can
                # retry; never log SMTP bodies, tokens, codes, or destinations.
                with self._stats_lock:
                    self._failed += 1
                logger.warning("auth_email_background_task_failed")
            finally:
                with self._stats_lock:
                    self._completed += 1
                self._queue.task_done()

    def submit(self, task: Callable[[], None]) -> bool:
        try:
            self._queue.put_nowait(task)
        except queue.Full:
            with self._stats_lock:
                self._dropped += 1
            logger.warning("auth_email_background_queue_full")
            return False
        with self._stats_lock:
            self._submitted += 1
        return True

    def telemetry(self) -> dict[str, int]:
        """Return aggregate-only counters suitable for operator monitoring."""

        with self._stats_lock:
            return {
                "submitted": self._submitted,
                "completed": self._completed,
                "failed": self._failed,
                "dropped": self._dropped,
                "queued": self._queue.qsize(),
            }


class AuthMailerUnavailable(RuntimeError):
    """Authentication email cannot be delivered in this environment."""


class DisabledAuthMailer:
    mode = "disabled"
    ready = False

    def send(self, message: AuthEmail | SecurityEmail) -> None:
        del message
        raise AuthMailerUnavailable(
            "Authentication email delivery is not configured for this deployment."
        )


class MemoryAuthMailer:
    """Ephemeral development/test outbox; plaintext is never persisted or logged."""

    mode = "memory"
    ready = True

    def __init__(self) -> None:
        self._messages: list[AuthEmail | SecurityEmail] = []
        self._lock = Lock()

    def send(self, message: AuthEmail | SecurityEmail) -> None:
        with self._lock:
            self._messages.append(message)

    def messages(
        self, *, purpose: str | None = None
    ) -> tuple[AuthEmail | SecurityEmail, ...]:
        """Test-only inspection surface; no HTTP route exposes this collection."""

        with self._lock:
            values = tuple(self._messages)
        return tuple(item for item in values if purpose is None or item.purpose == purpose)

    def clear(self) -> None:
        with self._lock:
            self._messages.clear()


class SmtpAuthMailer:
    """Standard SMTP transport with deterministic, injection-safe templates."""

    mode = "smtp"
    _SUBJECTS = {
        "email_verification": "Verify your TRACE account",
        "registration_resolution": "Continue with your existing TRACE account",
        "password_reset": "Reset your TRACE password",
        "two_factor_login": "Your TRACE sign-in code",
        "two_factor_enable": "Confirm TRACE two-factor authentication",
        "two_factor_disable": "Confirm disabling TRACE two-factor authentication",
        "email_change_current_factor": "Confirm your current TRACE email",
        "email_change": "Confirm your new TRACE email",
        "password_changed": "Your TRACE password was changed",
        "password_reset_complete": "Your TRACE password was reset",
        "two_factor_enabled": "TRACE email two-step protection was enabled",
        "two_factor_disabled": "TRACE email two-step protection was disabled",
        "email_changed": "Your TRACE account email was changed",
        "account_deleted": "Your TRACE account was deleted",
    }
    _LINK_PATHS = {
        "email_verification": "/verify-email",
        "password_reset": "/reset-password",
        "email_change": "/account/email-change",
    }

    def __init__(
        self,
        *,
        host: str | None,
        port: int,
        username: str | None,
        password: str | None,
        from_address: str | None,
        reply_to: str | None,
        public_app_url: str | None,
        starttls: bool,
        timeout_seconds: int,
        require_starttls: bool = False,
        require_https_links: bool = False,
        require_authentication: bool = False,
        require_public_hosts: bool = False,
        require_reply_to: bool = False,
    ) -> None:
        self.host = (host or "").strip()
        self.port = int(port)
        self.username = (username or "").strip() or None
        self.password = password or None
        self.from_address = (from_address or "").strip()
        self.reply_to = (reply_to or "").strip() or None
        self.public_app_url = (public_app_url or "").strip().rstrip("/")
        self.starttls = bool(starttls)
        self.require_starttls = bool(require_starttls)
        self.require_https_links = bool(require_https_links)
        self.require_authentication = bool(require_authentication)
        self.require_public_hosts = bool(require_public_hosts)
        self.require_reply_to = bool(require_reply_to)
        self.timeout_seconds = int(timeout_seconds)
        self.readiness_errors = self._readiness_errors()

    @staticmethod
    def _safe_address(value: str) -> bool:
        if not value or "\r" in value or "\n" in value:
            return False
        _display, address = parseaddr(value)
        if not address or address.count("@") != 1:
            return False
        local_part, domain = address.rsplit("@", 1)
        return bool(
            local_part
            and domain
            and not any(character.isspace() for character in address)
        )

    @staticmethod
    def _safe_smtp_host(value: str, *, require_public: bool) -> bool:
        """Accept one DNS hostname, never a URL, path, literal, or port."""

        if (
            not value
            or len(value) > 253
            or value != value.strip()
            or value.startswith(".")
            or value.endswith(".")
            or ".." in value
            or not re.fullmatch(r"[A-Za-z0-9.-]+", value)
        ):
            return False
        labels = value.split(".")
        if any(
            not label
            or len(label) > 63
            or label.startswith("-")
            or label.endswith("-")
            for label in labels
        ):
            return False
        if not require_public:
            return True
        lowered = value.lower()
        return bool(
            len(labels) >= 2
            and lowered != "localhost"
            and not lowered.endswith(
                (".localhost", ".local", ".internal", ".invalid", ".test", ".example")
            )
        )

    @staticmethod
    def _safe_public_origin(value: str, *, require_public: bool) -> tuple[bool, bool]:
        """Return structural validity and HTTPS validity for a frontend origin."""

        parsed = urlsplit(value)
        try:
            port = parsed.port
        except ValueError:
            return False, False
        hostname = (parsed.hostname or "").lower()
        structure_ok = bool(
            parsed.scheme in {"http", "https"}
            and parsed.netloc
            and hostname
            and not parsed.username
            and not parsed.password
            and parsed.path in {"", "/"}
            and not parsed.query
            and not parsed.fragment
        )
        if not structure_ok:
            return False, False
        if not require_public:
            return True, parsed.scheme == "https"
        public_host = bool(
            "." in hostname
            and hostname != "localhost"
            and not hostname.endswith(
                (".localhost", ".local", ".internal", ".invalid", ".test", ".example")
            )
            and re.fullmatch(r"[a-z0-9.-]+", hostname)
            and (port is None or port == 443)
        )
        return public_host, parsed.scheme == "https" and public_host

    @staticmethod
    def _display_expiry(value: str) -> str:
        """Render an unambiguous UTC expiry for text and HTML mail clients."""

        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise AuthMailerUnavailable(
                "Authentication email expiry is invalid."
            ) from exc
        if parsed.tzinfo is None:
            raise AuthMailerUnavailable("Authentication email expiry is invalid.")
        utc_value = parsed.astimezone(UTC)
        hour = utc_value.strftime("%I").lstrip("0") or "0"
        return (
            f"{utc_value.strftime('%B')} {utc_value.day}, {utc_value.year} at "
            f"{hour}:{utc_value.strftime('%M %p')} UTC"
        )

    def _readiness_errors(self) -> tuple[str, ...]:
        errors: list[str] = []
        if not self._safe_smtp_host(
            self.host, require_public=self.require_public_hosts
        ):
            errors.append("AUTH_SMTP_HOST")
        if self.port in {465, 2465}:
            # This adapter implements explicit STARTTLS, not implicit TLS.
            errors.append("AUTH_SMTP_PORT_STARTTLS")
        if not (1 <= self.port <= 65535):
            errors.append("AUTH_SMTP_PORT")
        if not self._safe_address(self.from_address):
            errors.append("AUTH_EMAIL_FROM_ADDRESS")
        if self.require_reply_to and not self.reply_to:
            errors.append("AUTH_EMAIL_REPLY_TO_REQUIRED")
        elif self.reply_to and not self._safe_address(self.reply_to):
            errors.append("AUTH_EMAIL_REPLY_TO")
        origin_ok, origin_https = self._safe_public_origin(
            self.public_app_url, require_public=self.require_public_hosts
        )
        if not origin_ok:
            errors.append("AUTH_PUBLIC_APP_URL")
        elif self.require_https_links and not origin_https:
            errors.append("AUTH_PUBLIC_APP_URL_HTTPS")
        if bool(self.username) != bool(self.password):
            errors.append("AUTH_SMTP_USERNAME/AUTH_SMTP_PASSWORD")
        elif self.require_authentication and not self.username:
            errors.append("AUTH_SMTP_USERNAME/AUTH_SMTP_PASSWORD_REQUIRED")
        if (
            (self.username and ("\r" in self.username or "\n" in self.username))
            or (self.password and ("\r" in self.password or "\n" in self.password))
        ):
            errors.append("AUTH_SMTP_CREDENTIALS_SINGLE_LINE")
        if self.require_starttls and not self.starttls:
            errors.append("AUTH_SMTP_STARTTLS")
        if not (2 <= self.timeout_seconds <= 60):
            errors.append("AUTH_SMTP_TIMEOUT_SECONDS")
        return tuple(errors)

    @property
    def ready(self) -> bool:
        return not self.readiness_errors

    def _content(
        self, message: AuthEmail | SecurityEmail
    ) -> tuple[str, str, str]:
        subject = self._SUBJECTS.get(message.purpose)
        if subject is None:
            raise AuthMailerUnavailable("Unsupported authentication email purpose.")
        if isinstance(message, SecurityEmail):
            action = {
                "password_changed": "password was changed",
                "password_reset_complete": "password was reset using email recovery",
                "two_factor_enabled": "email two-step protection was enabled",
                "two_factor_disabled": "email two-step protection was disabled",
                "email_changed": "account email was changed",
                "account_deleted": "account was deleted",
            }.get(message.purpose)
            if action is None:
                raise AuthMailerUnavailable(
                    "Unsupported authentication email purpose."
                )
            display_time = self._display_expiry(message.occurred_at)
            safe_time = html.escape(display_time)
            plain = (
                f"Your TRACE {action} on {display_time}.\n\n"
                "If you made this change, no action is needed. If you did not, "
                "secure your email account, then reply to this message or contact TRACE support immediately."
            )
            rich = (
                f"<p>Your TRACE {html.escape(action)} on {safe_time}.</p>"
                "<p>If you made this change, no action is needed. If you did not, "
                "secure your email account, then reply to this message or contact TRACE support immediately.</p>"
            )
            return subject, plain, rich
        display_expiry = self._display_expiry(message.expires_at)
        safe_expiry = html.escape(display_expiry)
        if message.purpose in {
            "two_factor_login",
            "two_factor_enable",
            "two_factor_disable",
            "email_change_current_factor",
        }:
            plain = (
                f"Your one-time TRACE code is {message.secret}. "
                f"It expires on {display_expiry}. If you did not request this, ignore this email."
            )
            rich = (
                "<p>Your one-time TRACE code is:</p>"
                f"<p style=\"font-size:24px;font-weight:700;letter-spacing:4px\">"
                f"{html.escape(message.secret)}</p><p>It expires on {safe_expiry}.</p>"
                "<p>If you did not request this, ignore this email.</p>"
            )
            return subject, plain, rich
        if message.purpose == "registration_resolution":
            plain = (
                f"This email is already connected to TRACE. Your one-time code is {message.secret}. "
                f"It expires on {display_expiry}. Enter the code in the registration screen to continue "
                "to sign-in or password recovery. If you did not try to register, ignore this email."
            )
            rich = (
                "<p>This email is already connected to TRACE. Your one-time code is:</p>"
                f"<p style=\"font-size:24px;font-weight:700;letter-spacing:4px\">"
                f"{html.escape(message.secret)}</p><p>It expires on {safe_expiry}.</p>"
                "<p>Enter the code in the registration screen to continue to sign-in or password "
                "recovery. If you did not try to register, ignore this email.</p>"
            )
            return subject, plain, rich
        path = self._LINK_PATHS[message.purpose]
        # Keep the one-time secret out of the HTTP request target. Browsers do
        # not send URL fragments to the origin, reverse proxy, or access logs;
        # the client reads the fragment and scrubs it before submitting proof.
        # ``challengeId`` is an opaque public handle and remains in the query so
        # the landing page can select the correct challenge without the secret.
        link = (
            f"{self.public_app_url}{path}?"
            + urlencode({"challengeId": message.challenge_id})
            + "#"
            + urlencode({"token": message.secret})
        )
        action = {
            "email_verification": "verify your email",
            "password_reset": "reset your password",
            "email_change": "confirm your new email",
        }[message.purpose]
        plain = (
            f"Use this link to {action}: {link}\n\n"
            f"It expires on {display_expiry}. If you did not request this, ignore this email."
        )
        rich = (
            f"<p>Use the secure link below to {html.escape(action)}.</p>"
            f"<p><a href=\"{html.escape(link, quote=True)}\">Continue securely</a></p>"
            f"<p>It expires on {safe_expiry}.</p>"
            "<p>If you did not request this, ignore this email.</p>"
        )
        if message.purpose == "email_verification":
            plain = (
                f"Your TRACE verification code is {message.secret}.\n\n"
                + plain
            )
            rich = (
                "<p>Your TRACE verification code is:</p>"
                f"<p style=\"font-size:24px;font-weight:700;letter-spacing:4px\">"
                f"{html.escape(message.secret)}</p>"
                + rich
            )
        return subject, plain, rich

    def send(self, message: AuthEmail | SecurityEmail) -> None:
        if not self.ready:
            raise AuthMailerUnavailable(
                "SMTP authentication email delivery is not ready."
            )
        if not self._safe_address(message.recipient):
            raise AuthMailerUnavailable("Authentication email destination is invalid.")
        subject, plain, rich = self._content(message)
        email = EmailMessage()
        email["Subject"] = subject
        email["From"] = self.from_address
        email["To"] = message.recipient
        if self.reply_to:
            email["Reply-To"] = self.reply_to
        email["Date"] = format_datetime(datetime.now(UTC))
        sender_address = parseaddr(self.from_address)[1]
        email["Message-ID"] = make_msgid(domain=sender_address.rsplit("@", 1)[1])
        email["Auto-Submitted"] = "auto-generated"
        email["X-Auto-Response-Suppress"] = "All"
        email.set_content(plain)
        email.add_alternative(rich, subtype="html")
        try:
            with smtplib.SMTP(
                self.host, self.port, timeout=self.timeout_seconds
            ) as smtp:
                smtp.ehlo()
                if self.starttls:
                    tls_context = ssl.create_default_context()
                    tls_context.minimum_version = ssl.TLSVersion.TLSv1_2
                    smtp.starttls(context=tls_context)
                    smtp.ehlo()
                if self.username:
                    assert self.password is not None
                    smtp.login(self.username, self.password)
                smtp.send_message(email)
        except (OSError, TimeoutError, smtplib.SMTPException) as exc:
            # Preserve no SMTP response/body in user-visible errors or logs.
            raise AuthMailerUnavailable(
                "Authentication email could not be delivered."
            ) from exc


def build_auth_mailer(
    *,
    app_env: str,
    mode: str,
    smtp_host: str | None = None,
    smtp_port: int = 587,
    smtp_username: str | None = None,
    smtp_password: str | None = None,
    from_address: str | None = None,
    reply_to: str | None = None,
    public_app_url: str | None = None,
    smtp_starttls: bool = True,
    smtp_timeout_seconds: int = 10,
) -> AuthMailer:
    """Build only adapters that are safe for the selected environment.

    A real provider adapter can satisfy ``AuthMailer`` and be injected into
    ``AuthService`` without changing account or challenge semantics. Until that
    adapter is configured, production registration/recovery fails explicitly.
    """

    normalized_env = app_env.strip().lower()
    normalized_mode = mode.strip().lower()
    if normalized_mode == "memory" and normalized_env in {"development", "test"}:
        return MemoryAuthMailer()
    if normalized_mode == "smtp":
        return SmtpAuthMailer(
            host=smtp_host,
            port=smtp_port,
            username=smtp_username,
            password=smtp_password,
            from_address=from_address,
            reply_to=reply_to,
            public_app_url=public_app_url,
            starttls=smtp_starttls,
            timeout_seconds=smtp_timeout_seconds,
            require_starttls=normalized_env in {"production", "prod"},
            require_https_links=normalized_env in {"production", "prod"},
            require_authentication=normalized_env in {"production", "prod"},
            require_public_hosts=normalized_env in {"production", "prod"},
            require_reply_to=normalized_env in {"production", "prod"},
        )
    return DisabledAuthMailer()
