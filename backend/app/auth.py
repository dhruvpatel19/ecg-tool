"""Phase 4 auth: users, password hashing, and session tokens.

Stdlib only (PBKDF2-HMAC-SHA256 passwords + hashed, revocable opaque sessions).
Learner data is keyed by verified user id. Pre-existing beta guest namespaces
are migration-only and never authorize new anonymous learning.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import re
import secrets
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from .auth_mailer import (
    AuthEmail,
    AuthMailer,
    AuthMailerUnavailable,
    AuthTaskDispatcher,
    DisabledAuthMailer,
    InlineAuthTaskDispatcher,
    SecurityEmail,
)
from .guest_progress import GuestProgressService
from .storage import LearningStore

SESSION_DAYS = 30
SESSION_COOKIE_NAME = "ecg_session"
PRODUCTION_SESSION_COOKIE_NAME = "__Host-ecg_session"
EXPORT_AUTH_COOKIE_NAME = "ecg_export_auth"
EXPORT_AUTHORIZATION_SECONDS = 5 * 60
PASSWORD_ITERATIONS = 600_000
# Login limits are a second line of defense behind Vercel's edge rule.  The
# pair bucket is deliberately IP-scoped so an attacker cannot lock a known
# learner out from every network.  The larger IP/global circuit breakers bound
# expensive PBKDF2 work while tolerating a classroom sharing one NAT address.
LOGIN_PAIR_MAX_ATTEMPTS = 8
LOGIN_IP_MAX_ATTEMPTS = 120
LOGIN_GLOBAL_MAX_ATTEMPTS = 600
LOGIN_WINDOW_MINUTES = 15
LOGIN_BLOCK_MINUTES = 15
REGISTRATION_PAIR_MAX_ATTEMPTS = 8
REGISTRATION_IP_MAX_ATTEMPTS = 200
REGISTRATION_GLOBAL_MAX_ATTEMPTS = 600
REGISTRATION_WINDOW_MINUTES = 15
REGISTRATION_BLOCK_MINUTES = 15
ACCOUNT_REAUTH_PAIR_MAX_ATTEMPTS = 8
ACCOUNT_REAUTH_IP_MAX_ATTEMPTS = 120
ACCOUNT_REAUTH_GLOBAL_MAX_ATTEMPTS = 600
ACCOUNT_REAUTH_WINDOW_MINUTES = 15
ACCOUNT_REAUTH_BLOCK_MINUTES = 15
EMAIL_VERIFICATION_MINUTES = 15
PASSWORD_RESET_MINUTES = 30
EMAIL_OTP_MINUTES = 10
EMAIL_CHANGE_FACTOR_WINDOW_MINUTES = 15
EMAIL_CHALLENGE_MAX_ATTEMPTS = 8
EMAIL_OTP_MAX_ATTEMPTS = 5
EMAIL_RESEND_COOLDOWN_SECONDS = 60
EMAIL_CHALLENGE_MAX_SENDS = 5
VERIFICATION_FAILURE_BUDGET_MAX = 5
VERIFICATION_FAILURE_BUDGET_WINDOW_SECONDS = 30 * 60
RECOVERY_PAIR_MAX_ATTEMPTS = 5
RECOVERY_IP_MAX_ATTEMPTS = 100
RECOVERY_GLOBAL_MAX_ATTEMPTS = 500
RECOVERY_WINDOW_MINUTES = 15
RECOVERY_BLOCK_MINUTES = 15
RECOVERY_CONFIRM_PAIR_MAX_ATTEMPTS = 8
RECOVERY_CONFIRM_IP_MAX_ATTEMPTS = 60
RECOVERY_CONFIRM_GLOBAL_MAX_ATTEMPTS = 300
RECOVERY_CONFIRM_WINDOW_MINUTES = 15
RECOVERY_CONFIRM_BLOCK_MINUTES = 15
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
_EMAIL_LOCAL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}$")
RESERVED_USERNAMES = {"demo", "guest", "admin"}
_COMMON_PASSWORDS = frozenset(
    {
        "1234567890",
        "abcdefghij",
        "changeme123",
        "iloveyou123",
        "letmein1234",
        "password10",
        "password123",
        "qwerty1234",
        "student123",
        "welcome123",
    }
)
_DUMMY_PASSWORD_HASH = (
    "pbkdf2_sha256$600000$00000000000000000000000000000000$"
    "1d426911dbe3390a224210a21a7d938eb44360e0f1ebd4f84a3658566112283b"
)


def session_cookie_name(app_env: str) -> str:
    """Use the host-only cookie prefix only where HTTPS is mandatory."""

    return (
        PRODUCTION_SESSION_COOKIE_NAME
        if str(app_env or "").strip().casefold() in {"production", "prod"}
        else SESSION_COOKIE_NAME
    )


def hash_password(password: str, salt: str | None = None, iterations: int = PASSWORD_ITERATIONS) -> str:
    if iterations < 100_000 or iterations > 2_000_000:
        raise ValueError("Password-hash iterations are outside the supported range")
    salt = salt or secrets.token_hex(16)
    if len(salt) != 32:
        raise ValueError("Password-hash salt must contain 16 bytes")
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations)
    return f"pbkdf2_sha256${iterations}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations_text, salt, hexhash = stored.split("$")
        iterations = int(iterations_text)
        if (
            algorithm != "pbkdf2_sha256"
            or iterations < 100_000
            or iterations > 2_000_000
            or len(salt) != 32
            or len(bytes.fromhex(salt)) != 16
            or len(hexhash) != 64
            or len(bytes.fromhex(hexhash)) != 32
        ):
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations
        )
    except (ValueError, AttributeError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), hexhash)


def password_hash_iterations(stored: str) -> int | None:
    """Return the reviewed PBKDF2 work factor, or ``None`` for bad input."""

    try:
        algorithm, iterations_text, salt, digest = stored.split("$")
        iterations = int(iterations_text)
        if (
            algorithm != "pbkdf2_sha256"
            or iterations < 100_000
            or iterations > 2_000_000
            or len(salt) != 32
            or len(bytes.fromhex(salt)) != 16
            or len(digest) != 64
            or len(bytes.fromhex(digest)) != 32
        ):
            return None
    except (ValueError, AttributeError, TypeError):
        return None
    return iterations


def verify_password_with_current_work(password: str, stored: str) -> bool:
    """Verify while padding legacy/invalid rows to today's minimum work.

    A database migrated from the 200k-iteration beta otherwise makes a wrong
    password measurably cheaper than the 600k dummy path for an unknown user.
    The domain-separated padding digest is discarded; successful legacy login
    still upgrades the persisted hash through the existing compare-and-write.
    """

    iterations = password_hash_iterations(stored)
    valid = verify_password(password, stored)
    completed_iterations = iterations or 0
    if completed_iterations < PASSWORD_ITERATIONS:
        hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            b"ecg-hash-pad-v1!",
            PASSWORD_ITERATIONS - completed_iterations,
        )
    return valid


def normalize_email(email: str | None) -> str:
    """Validate and canonicalize an account email for unique lookup."""

    candidate = (email or "").strip()
    if len(candidate) > 254 or candidate.count("@") != 1:
        raise AuthError(
            "Enter a valid email address.", field="email", code="invalid_email"
        )
    local, domain = candidate.rsplit("@", 1)
    if not _EMAIL_LOCAL_RE.fullmatch(local) or not domain or any(
        character.isspace() for character in domain
    ):
        raise AuthError(
            "Enter a valid email address.", field="email", code="invalid_email"
        )
    try:
        ascii_domain = domain.rstrip(".").encode("idna").decode("ascii").casefold()
    except UnicodeError as exc:
        raise AuthError(
            "Enter a valid email address.", field="email", code="invalid_email"
        ) from exc
    labels = ascii_domain.split(".")
    if (
        len(labels) < 2
        or any(not label or len(label) > 63 for label in labels)
        or any(label.startswith("-") or label.endswith("-") for label in labels)
        or any(not re.fullmatch(r"[a-z0-9-]+", label) for label in labels)
    ):
        raise AuthError(
            "Enter a valid email address.", field="email", code="invalid_email"
        )
    normalized = f"{local.casefold()}@{ascii_domain}"
    if len(normalized) > 254:
        raise AuthError(
            "Enter a valid email address.", field="email", code="invalid_email"
        )
    return normalized


def mask_email(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    local, domain = email.rsplit("@", 1)
    domain_parts = domain.split(".")
    host = domain_parts[0]
    suffix = "." + ".".join(domain_parts[1:]) if len(domain_parts) > 1 else ""
    return f"{local[:1]}***@{host[:1]}***{suffix}"


def validate_new_password(
    password: str | None,
    *,
    username: str,
    field: str,
    label: str = "Password",
) -> str:
    """Apply one permissive-but-safe policy to registration and rotation.

    Long passphrases remain valid without arbitrary symbol/case rules. The
    small local denylist and repeated-character check catch only demonstrably
    weak choices; a production institution can add a reviewed breached-password
    service later without changing the account contract.
    """

    candidate = password or ""
    if len(candidate) < 10:
        raise AuthError(
            f"{label} must be at least 10 characters.",
            field=field,
            code="password_too_short",
        )
    if len(candidate) > 256:
        raise AuthError(
            f"{label} must be 256 characters or fewer.",
            field=field,
            code="password_too_long",
        )
    normalized = candidate.casefold()
    if (
        normalized == username.casefold()
        or normalized in _COMMON_PASSWORDS
        or len(set(normalized)) == 1
        or not any(not character.isspace() for character in candidate)
    ):
        raise AuthError(
            f"{label} is too easy to guess. Choose a less common passphrase that is not your username.",
            field=field,
            code="password_too_common",
        )
    return candidate


class AuthError(ValueError):
    """A safe, field-addressable authentication validation error."""

    def __init__(self, message: str, field: str | None = None, code: str = "invalid"):
        super().__init__(message)
        self.field = field
        self.code = code


class AuthService:
    def __init__(
        self,
        store: LearningStore,
        guest_progress: GuestProgressService | None = None,
        registration_rate_limit_secret: str = "ecg-tool-local-registration-rate-limit-v1",
        mailer: AuthMailer | None = None,
        recovery_dispatcher: AuthTaskDispatcher | None = None,
        email_two_factor_enabled: bool = True,
    ):
        self.store = store
        self.guest_progress = guest_progress
        self._auth_rate_limit_secret = registration_rate_limit_secret.encode("utf-8")
        self.mailer = mailer or DisabledAuthMailer()
        self.recovery_dispatcher = recovery_dispatcher or InlineAuthTaskDispatcher()
        self.email_two_factor_enabled = email_two_factor_enabled

    @staticmethod
    def _normalized_client_ip(client_ip: str | None) -> str:
        try:
            return ipaddress.ip_address((client_ip or "").strip()).compressed
        except ValueError:
            # Missing/non-address peers share one fail-closed bucket.
            return "unknown"

    def _rate_limit_digest(self, namespace: str, *parts: str) -> str:
        material = "\0".join((namespace, *parts)).encode("utf-8")
        return hmac.new(
            self._auth_rate_limit_secret,
            material,
            hashlib.sha256,
        ).hexdigest()

    def email_delivery_status(self) -> dict[str, Any]:
        return {"ready": bool(self.mailer.ready), "mode": self.mailer.mode}

    def _require_mailer(self) -> None:
        if not self.mailer.ready:
            raise AuthError(
                "Account email delivery is not configured for this deployment.",
                code="email_delivery_unavailable",
            )

    def _challenge_hash(self, purpose: str, challenge_id: str, secret: str) -> str:
        return hmac.new(
            self._auth_rate_limit_secret,
            f"ecg-auth-challenge-v1\0{purpose}\0{challenge_id}\0{secret}".encode(
                "utf-8"
            ),
            hashlib.sha256,
        ).hexdigest()

    def _verification_budget_context(
        self,
        *,
        purpose: str,
        user_id: str,
        email: str,
    ) -> dict[str, Any]:
        if purpose in {"email_verification", "registration_resolution"}:
            group = "registration_email"
            scope = normalize_email(email)
        elif purpose in {
            "two_factor_login",
            "two_factor_enable",
            "two_factor_disable",
            "email_change_current_factor",
        }:
            group = purpose
            scope = user_id
        else:
            return {}
        return {
            "verificationBudgetKey": self._rate_limit_digest(
                "ecg-verification-failure-budget-v1", group, scope
            ),
            "verificationBudgetGroup": group,
            "verificationBudgetMaxFailures": VERIFICATION_FAILURE_BUDGET_MAX,
            "verificationBudgetWindowSeconds": VERIFICATION_FAILURE_BUDGET_WINDOW_SECONDS,
        }

    def _new_challenge(
        self,
        purpose: str,
        *,
        ttl: timedelta,
        otp: bool = False,
    ) -> dict[str, str]:
        challenge_id = f"ach_{secrets.token_urlsafe(24)}"
        secret = f"{secrets.randbelow(1_000_000):06d}" if otp else secrets.token_urlsafe(32)
        expires_at = (datetime.now(UTC) + ttl).isoformat()
        return {
            "challengeId": challenge_id,
            "secret": secret,
            "secretHash": self._challenge_hash(purpose, challenge_id, secret),
            "expiresAt": expires_at,
        }

    def _deliver_challenge(
        self,
        *,
        purpose: str,
        email: str,
        challenge: dict[str, str],
    ) -> None:
        self.mailer.send(
            AuthEmail(
                purpose=purpose,
                recipient=email,
                challenge_id=challenge["challengeId"],
                secret=challenge["secret"],
                expires_at=challenge["expiresAt"],
            )
        )

    def _queue_security_notification(
        self,
        *,
        purpose: str,
        email: str | None,
        occurred_at: str | None = None,
    ) -> bool:
        """Best-effort, secret-free notice after a security mutation commits.

        Notification transport can never turn a completed credential change
        into an apparent failure. The production dispatcher records aggregate
        queue/delivery failures without logging the destination or account.
        """

        recipient = str(email or "").strip()
        if not recipient or not self.mailer.ready:
            return False
        message = SecurityEmail(
            purpose=purpose,
            recipient=recipient,
            occurred_at=occurred_at or datetime.now(UTC).isoformat(),
        )

        def deliver() -> None:
            # Let the bounded production dispatcher observe and count delivery
            # failure. Inline/custom dispatcher exceptions are contained by
            # the outer submit guard below, after the mutation has committed.
            self.mailer.send(message)

        try:
            return bool(self.recovery_dispatcher.submit(deliver))
        except Exception:
            # Inline/custom dispatchers are not allowed to retroactively fail
            # the committed security change either.
            return False

    def _reserve_registration_attempt(
        self, *, username: str, client_ip: str | None
    ) -> None:
        normalized_ip = self._normalized_client_ip(client_ip)
        pair_key_hash = self._rate_limit_digest(
            "ecg-registration-v1", "pair", normalized_ip, username
        )
        ip_key_hash = self._rate_limit_digest(
            "ecg-registration-v1", "ip", normalized_ip
        )
        global_key_hash = self._rate_limit_digest("ecg-registration-v1", "global")
        if self.store.consume_registration_attempt(
            pair_key_hash=pair_key_hash,
            ip_key_hash=ip_key_hash,
            global_key_hash=global_key_hash,
            max_pair_attempts=REGISTRATION_PAIR_MAX_ATTEMPTS,
            max_ip_attempts=REGISTRATION_IP_MAX_ATTEMPTS,
            max_global_attempts=REGISTRATION_GLOBAL_MAX_ATTEMPTS,
            window_minutes=REGISTRATION_WINDOW_MINUTES,
            block_minutes=REGISTRATION_BLOCK_MINUTES,
        ):
            raise AuthError(
                "Too many registration attempts. Please wait and try again.",
                code="registration_throttled",
            )

    def register(
        self,
        username: str,
        password: str,
        display_name: str | None = None,
        *,
        claim_guest_progress: bool = False,
        guest_id: str | None = None,
        client_ip: str | None = None,
    ) -> dict[str, Any]:
        # Usernames are canonical identifiers, not display strings. Persisting a
        # single lowercase form keeps registration and login case-insensitive on
        # every SQLite build (including databases created before this rule).
        username = (username or "").strip().casefold()
        self._reserve_registration_attempt(username=username, client_ip=client_ip)
        if not _USERNAME_RE.fullmatch(username) or username in RESERVED_USERNAMES:
            raise AuthError(
                "Username must be 3-32 characters using only letters, digits, _, . or -, and cannot be reserved.",
                field="username",
                code="invalid_username",
            )
        password = validate_new_password(
            password,
            username=username,
            field="password",
        )
        safe_display_name = (display_name or "").strip() or username
        if len(safe_display_name) > 80:
            raise AuthError(
                "Display name must be 80 characters or fewer.",
                field="displayName",
                code="display_name_too_long",
            )
        if self._user_by_username(username):
            raise AuthError("That username is already taken.", field="username", code="username_taken")
        user_id = f"u_{uuid.uuid4().hex[:16]}"
        guest_claim: dict[str, Any] | None = None
        token = secrets.token_urlsafe(32)
        expires_at = (datetime.now(UTC) + timedelta(days=SESSION_DAYS)).isoformat()
        try:
            password_hash = hash_password(password)
            if claim_guest_progress:
                if not self.guest_progress or not guest_id:
                    raise AuthError(
                        "Guest progress is unavailable for this request.",
                        code="guest_claim_unavailable",
                    )
                guest_claim = self.guest_progress.create_user_and_claim(
                    user_id=user_id,
                    username=username,
                    display_name=safe_display_name,
                    password_hash=password_hash,
                    email_normalized=None,
                    guest_id=guest_id,
                    session_token=token,
                    session_expires_at=expires_at,
                )
            else:
                self.store.create_registered_user(
                    user_id=user_id,
                    username=username,
                    display_name=safe_display_name,
                    password_hash=password_hash,
                    email_normalized=None,
                    session_token=token,
                    session_expires_at=expires_at,
                )
        except sqlite3.IntegrityError as exc:
            # Close the check/insert race without exposing database details.
            raise AuthError(
                "That username is already taken.", field="username", code="username_taken"
            ) from exc
        session = {
            "token": token,
            "user": self.public_user(user_id),
        }
        if guest_claim:
            session["guestClaim"] = guest_claim
        return session

    def register_with_email(
        self,
        username: str | None,
        password: str,
        email: str,
        display_name: str | None = None,
        *,
        claim_guest_progress: bool = False,
        guest_id: str | None = None,
        client_ip: str | None = None,
    ) -> dict[str, Any]:
        """Create an unverified account and deliver its one-time email proof.

        No learning session is issued here. The full account graph, optional
        legacy claim, and hashed verification challenge commit together; email
        confirmation later creates the first authenticated session.
        """

        self._require_mailer()
        normalized_email = normalize_email(email)
        requested_username = (username or "").strip().casefold()
        self._reserve_registration_attempt(
            username=requested_username or normalized_email,
            client_ip=client_ip,
        )
        if requested_username:
            if (
                not _USERNAME_RE.fullmatch(requested_username)
                or requested_username in RESERVED_USERNAMES
            ):
                raise AuthError(
                    "Username must be 3-32 characters using only letters, digits, _, . or -, and cannot be reserved.",
                    field="username",
                    code="invalid_username",
                )
            username = requested_username
        else:
            # The student-facing account flow is email-first. Keep the legacy
            # username column as a private stable identifier until the schema
            # can be migrated without making learners invent another handle.
            username = f"student_{uuid.uuid4().hex[:20]}"
        password = validate_new_password(password, username=username, field="password")
        safe_display_name = (display_name or "").strip() or "Student"
        if len(safe_display_name) > 80:
            raise AuthError(
                "Display name must be 80 characters or fewer.",
                field="displayName",
                code="display_name_too_long",
            )
        if claim_guest_progress and (not self.guest_progress or not guest_id):
            raise AuthError(
                "Legacy guest progress is unavailable for this request.",
                code="guest_claim_unavailable",
            )

        user_id = f"u_{uuid.uuid4().hex[:16]}"
        challenge = self._new_challenge(
            "email_verification",
            ttl=timedelta(minutes=EMAIL_VERIFICATION_MINUTES),
            otp=True,
        )
        password_hash = hash_password(password)

        def insert_challenge(
            conn: sqlite3.Connection,
            now: str,
        ) -> None:
            context = {"guestId": guest_id} if claim_guest_progress and guest_id else {}
            context.update(
                self._verification_budget_context(
                    purpose="email_verification",
                    user_id=user_id,
                    email=normalized_email,
                )
            )
            self.store._insert_auth_challenge(
                conn,
                challenge_id=challenge["challengeId"],
                user_id=user_id,
                purpose="email_verification",
                secret_hash=challenge["secretHash"],
                expires_at=challenge["expiresAt"],
                max_attempts=EMAIL_OTP_MAX_ATTEMPTS,
                now=now,
                credential_fingerprint=self.store._password_fingerprint(
                    password_hash
                ),
                context=context,
            )

        try:
            self.store.create_registered_user(
                user_id=user_id,
                username=username,
                display_name=safe_display_name,
                password_hash=password_hash,
                email_normalized=normalized_email,
                session_token=None,
                session_expires_at=None,
                account_origin="pending_registration",
                _transaction_hook=insert_challenge,
            )
        except sqlite3.IntegrityError as exc:
            # The insert is the only pre-delivery membership authority, closing
            # the check/insert race. Existing *email* membership remains
            # private: the same public 200/check-email flow is completed with
            # an owner-only resolution code. Username availability is
            # intentionally public because it is a user-chosen public identity.
            # A public username collision always wins, including when both
            # identifiers collide. Otherwise a known-taken username could be
            # combined with candidate emails to probe email membership.
            if self._user_by_username(username):
                raise AuthError(
                    "That username is unavailable. Choose another.",
                    field="username",
                    code="username_taken",
                ) from exc
            existing_email_owner = self.store.get_user_by_email(normalized_email)
            if existing_email_owner:
                resolution = self._issue_email_challenge(
                    user=existing_email_owner,
                    purpose="registration_resolution",
                    ttl=timedelta(minutes=EMAIL_VERIFICATION_MINUTES),
                    otp=True,
                    max_attempts=EMAIL_OTP_MAX_ATTEMPTS,
                    reuse_active=True,
                    restart_exhausted=False,
                    registration_reservation_username=username,
                )
                return {
                    "verificationRequired": True,
                    "challengeId": resolution["challengeId"],
                    "maskedEmail": resolution["maskedEmail"],
                    "expiresAt": resolution["expiresAt"],
                    # Match the submitted migration intent exactly so this
                    # field cannot distinguish existing from new email. No
                    # transfer occurs on this resolution-only challenge.
                    "guestClaimPendingVerification": bool(
                        claim_guest_progress and guest_id
                    ),
                    "deliveryFailed": resolution.get("deliveryFailed", False),
                    "retryAfterSeconds": resolution.get("retryAfterSeconds"),
                }
            raise AuthError(
                "That username is unavailable. Choose another.",
                field="username",
                code="username_taken",
            ) from exc

        delivery_failed = False
        try:
            self._deliver_challenge(
                purpose="email_verification",
                email=normalized_email,
                challenge=challenge,
            )
        except AuthMailerUnavailable:
            delivery_failed = True
            self.store.allow_auth_challenge_resend_now(challenge["challengeId"])
        return {
            "verificationRequired": True,
            "challengeId": challenge["challengeId"],
            "maskedEmail": mask_email(normalized_email),
            "expiresAt": challenge["expiresAt"],
            "guestClaimPendingVerification": bool(
                claim_guest_progress and guest_id
            ),
            "deliveryFailed": delivery_failed,
            "retryAfterSeconds": 0 if delivery_failed else None,
        }

    @staticmethod
    def _challenge_context(row: dict[str, Any]) -> dict[str, Any]:
        try:
            value = json.loads(str(row.get("context_json") or "{}"))
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}

    def _issue_email_challenge(
        self,
        *,
        user: dict[str, Any],
        purpose: str,
        ttl: timedelta,
        otp: bool,
        max_attempts: int,
        context: dict[str, Any] | None = None,
        reuse_active: bool = True,
        restart_exhausted: bool = True,
        credential_bound: bool = False,
        destination_email: str | None = None,
        registration_reservation_username: str | None = None,
    ) -> dict[str, Any]:
        self._require_mailer()
        account_email = str(user.get("email_normalized") or "")
        delivery_email = destination_email or account_email
        if not delivery_email:
            raise AuthError(
                "Add an email address before using this account feature.",
                code="email_upgrade_required",
            )
        challenge_context = dict(context or {})
        challenge_context.update(
            self._verification_budget_context(
                purpose=purpose,
                user_id=str(user["user_id"]),
                email=delivery_email,
            )
        )
        # ``reuse_active`` remains part of the call contract for compatibility,
        # but identical concurrent requests always reuse the storage-selected
        # winner. Explicit context changes (for example a new email-change
        # destination) are the replacement boundary.
        _ = reuse_active
        challenge = self._new_challenge(purpose, ttl=ttl, otp=otp)
        reservation_user_id = None
        reservation_password_hash = None
        if registration_reservation_username is not None:
            reservation_user_id = f"u_registration_reservation_{uuid.uuid4().hex[:16]}"
            # A syntactically valid PBKDF2 record with an unknowable random
            # digest makes the placeholder non-loginable without another slow
            # hash during the already expensive registration path.
            reservation_password_hash = (
                f"pbkdf2_sha256${PASSWORD_ITERATIONS}${secrets.token_hex(16)}$"
                f"{secrets.token_hex(32)}"
            )
        status, selected = self.store.reserve_auth_challenge_issue(
            challenge_id=challenge["challengeId"],
            user_id=str(user["user_id"]),
            purpose=purpose,
            secret_hash=challenge["secretHash"],
            expires_at=challenge["expiresAt"],
            max_attempts=max_attempts,
            max_sends=EMAIL_CHALLENGE_MAX_SENDS,
            restart_exhausted=restart_exhausted,
            credential_fingerprint=(
                self.store._password_fingerprint(str(user["password_hash"]))
                if credential_bound
                else None
            ),
            context=challenge_context,
            reservation_user_id=reservation_user_id,
            reservation_username=registration_reservation_username,
            reservation_password_hash=reservation_password_hash,
        )
        if status == "reservation_conflict":
            raise AuthError(
                "That username is unavailable. Choose another.",
                field="username",
                code="username_taken",
            )
        if selected is None:
            raise RuntimeError("Authentication challenge issue returned no selection")
        if status in {"existing", "send_limit"}:
            if status == "existing" and str(
                selected.get("last_sent_at") or ""
            ).startswith("1970-"):
                resend = self.resend_email_challenge(
                    str(selected["challenge_id"]), purpose=purpose
                )
                refreshed = self.store.get_auth_challenge(
                    str(selected["challenge_id"])
                ) or selected
                return {
                    "challengeId": str(selected["challenge_id"]),
                    "expiresAt": str(refreshed["expires_at"]),
                    "maskedEmail": mask_email(delivery_email),
                    "reused": True,
                    "deliveryFailed": bool(resend.get("deliveryFailed")),
                    "retryAfterSeconds": resend.get("retryAfterSeconds"),
                }
            return {
                "challengeId": str(selected["challenge_id"]),
                "expiresAt": str(selected["expires_at"]),
                "maskedEmail": mask_email(delivery_email),
                "reused": True,
                "deliveryFailed": False,
                "retryAfterSeconds": None,
            }
        if status != "created":
            raise RuntimeError(f"Unsupported challenge issue status: {status}")
        if not self.store.auth_challenge_is_active(challenge["challengeId"]):
            winner = self.store.get_active_auth_challenge(
                str(user["user_id"]), purpose
            )
            if winner:
                return {
                    "challengeId": str(winner["challenge_id"]),
                    "expiresAt": str(winner["expires_at"]),
                    "maskedEmail": mask_email(delivery_email),
                    "reused": True,
                    "deliveryFailed": False,
                    "retryAfterSeconds": None,
                }
            raise AuthError(
                "This authentication request changed. Start again.",
                code="challenge_stale",
            )
        delivery_failed = False
        try:
            self._deliver_challenge(
                purpose=purpose, email=delivery_email, challenge=challenge
            )
        except AuthMailerUnavailable:
            delivery_failed = True
            self.store.allow_auth_challenge_resend_now(challenge["challengeId"])
        return {
            "challengeId": challenge["challengeId"],
            "expiresAt": challenge["expiresAt"],
            "maskedEmail": mask_email(delivery_email),
            "reused": False,
            "deliveryFailed": delivery_failed,
            "retryAfterSeconds": 0 if delivery_failed else None,
        }

    def login(
        self,
        username: str,
        password: str,
        *,
        claim_guest_progress: bool = False,
        guest_id: str | None = None,
        client_ip: str | None = None,
    ) -> dict[str, Any]:
        raw_identifier = (username or "").strip()
        normalized = raw_identifier.casefold()
        if "@" in raw_identifier:
            try:
                normalized = normalize_email(raw_identifier)
            except AuthError:
                # Invalid email-shaped identifiers follow the same dummy-hash
                # path and generic response as an unknown username.
                normalized = raw_identifier.casefold()
        normalized_ip = self._normalized_client_ip(client_ip)
        pair_key_hash = self._rate_limit_digest(
            "ecg-login-v1", "pair", normalized_ip, normalized
        )
        ip_key_hash = self._rate_limit_digest(
            "ecg-login-v1", "ip", normalized_ip
        )
        global_key_hash = self._rate_limit_digest("ecg-login-v1", "global")
        # Reserve the slow hash *before* any user lookup or PBKDF2 work.  Every
        # attempt consumes capacity, so random usernames cannot bypass the CPU
        # circuit breaker.  The response remains account-enumeration safe.
        if self.store.consume_login_attempt(
            pair_key_hash=pair_key_hash,
            ip_key_hash=ip_key_hash,
            global_key_hash=global_key_hash,
            max_pair_attempts=LOGIN_PAIR_MAX_ATTEMPTS,
            max_ip_attempts=LOGIN_IP_MAX_ATTEMPTS,
            max_global_attempts=LOGIN_GLOBAL_MAX_ATTEMPTS,
            window_minutes=LOGIN_WINDOW_MINUTES,
            block_minutes=LOGIN_BLOCK_MINUTES,
        ):
            raise AuthError("Invalid username or password.", code="login_throttled")
        user = (
            self.store.get_user_by_email(normalized)
            if "@" in normalized
            else self._user_by_username(normalized)
        )
        if user and bool(user.get("registration_reservation")):
            user = None
        # Keep the slow-hash work comparable for missing and existing users so
        # the generic response does not become an account-enumeration oracle.
        password_valid = verify_password_with_current_work(
            password or "", user["password_hash"] if user else _DUMMY_PASSWORD_HASH
        )
        if not user or not password_valid:
            # Deliberately do not reveal whether the identifier exists.
            raise AuthError("Invalid username or password.", code="invalid")
        # A verified learner's pair bucket is cleared after the slow work, but
        # aggregate IP/global reservations remain so login churn stays bounded.
        self.store.clear_login_pair_attempts(pair_key_hash)
        deferred_context = {"guestId": guest_id} if claim_guest_progress and guest_id else {}
        if user.get("email_normalized") and not user.get("email_verified_at"):
            challenge = self._issue_email_challenge(
                user=user,
                purpose="email_verification",
                ttl=timedelta(minutes=EMAIL_VERIFICATION_MINUTES),
                otp=True,
                max_attempts=EMAIL_OTP_MAX_ATTEMPTS,
                context=deferred_context,
                reuse_active=not bool(deferred_context),
                credential_bound=True,
            )
            return {
                "verificationRequired": True,
                "challengeId": challenge["challengeId"],
                "maskedEmail": challenge["maskedEmail"],
                "expiresAt": challenge["expiresAt"],
                "deliveryFailed": challenge.get("deliveryFailed", False),
                "retryAfterSeconds": challenge.get("retryAfterSeconds"),
            }
        if self.email_two_factor_enabled and bool(user.get("email_two_factor_enabled")):
            challenge = self._issue_email_challenge(
                user=user,
                purpose="two_factor_login",
                ttl=timedelta(minutes=EMAIL_OTP_MINUTES),
                otp=True,
                max_attempts=EMAIL_OTP_MAX_ATTEMPTS,
                context=deferred_context,
                reuse_active=not bool(deferred_context),
                credential_bound=True,
            )
            return {
                "twoFactorRequired": True,
                "challengeId": challenge["challengeId"],
                "maskedEmail": challenge["maskedEmail"],
                "expiresAt": challenge["expiresAt"],
                "deliveryFailed": challenge.get("deliveryFailed", False),
                "retryAfterSeconds": challenge.get("retryAfterSeconds"),
            }
        if bool(user.get("email_two_factor_enabled")):
            # Email two-step verification was retired in favor of a simple
            # verified-email/password flow. Migrate any early pilot account on
            # its next successful password login so it cannot become stranded.
            if not self.store.disable_email_two_factor(
                user_id=str(user["user_id"]),
                expected_password_hash=str(user["password_hash"]),
            ):
                raise AuthError("Invalid username or password.", code="invalid")
            user["email_two_factor_enabled"] = 0
        token = secrets.token_urlsafe(32)
        expires_at = (datetime.now(UTC) + timedelta(days=SESSION_DAYS)).isoformat()
        replacement_hash = (
            hash_password(password)
            if (password_hash_iterations(str(user["password_hash"])) or 0)
            < PASSWORD_ITERATIONS
            else None
        )
        guest_claim: dict[str, Any] | None = None
        if claim_guest_progress:
            if not self.guest_progress or not guest_id:
                raise AuthError(
                    "Guest progress is unavailable for this request.",
                    code="guest_claim_unavailable",
                )
            guest_claim = self.guest_progress.claim_and_create_session(
                guest_id=guest_id,
                user_id=user["user_id"],
                expected_password_hash=str(user["password_hash"]),
                session_token=token,
                session_expires_at=expires_at,
                replacement_password_hash=replacement_hash,
            )
            session_created = guest_claim is not None
        else:
            session_created = self.store.create_session_if_password_current(
                user_id=user["user_id"],
                expected_password_hash=str(user["password_hash"]),
                token=token,
                expires_at=expires_at,
                replacement_password_hash=replacement_hash,
            )
        if not session_created:
            # A concurrent credential rotation invalidates the password proof.
            raise AuthError("Invalid username or password.", code="invalid")
        session = {
            "token": token,
            "user": self.public_user(str(user["user_id"])),
        }
        if guest_claim:
            session["guestClaim"] = guest_claim
        return session

    @staticmethod
    def _raise_challenge_failure(status: str) -> None:
        if status == "verified":
            return
        codes = {
            "expired": "challenge_expired",
            "consumed": "challenge_used",
            "attempts_exhausted": "challenge_attempts_exhausted",
            "incorrect": "challenge_incorrect",
        }
        raise AuthError(
            "That authentication code or link is invalid or expired.",
            code=codes.get(status, "challenge_invalid"),
        )

    def confirm_email_verification(
        self,
        challenge_id: str,
        token: str,
        password: str,
        *,
        client_ip: str | None = None,
    ) -> dict[str, Any]:
        """Activate an email only after proving both factors again.

        The email proof alone must never activate an attacker-chosen password
        from a pre-registration attempt. Password work is rate-limited before
        entering the SQLite writer transaction; the exact hash/fingerprint is
        rechecked under the challenge-consumption transaction to close races.
        """

        challenge = self.store.get_auth_challenge(challenge_id)
        challenge_purpose = (
            str(challenge.get("purpose")) if challenge else ""
        )
        resolution = challenge_purpose == "registration_resolution"
        candidate_user_id = (
            str(challenge["user_id"])
            if challenge and challenge_purpose == "email_verification"
            else (
                "u_registration_resolution_"
                + self._rate_limit_digest(
                    "ecg-registration-resolution-password-work-v1",
                    challenge_id,
                )[:16]
                if resolution
                else "u_missing_email_verification"
            )
        )
        password_user: dict[str, Any] | None = None
        try:
            password_user = self._verify_current_password(
                candidate_user_id, password, client_ip
            )
        except AuthError as exc:
            if exc.code == "reauth_throttled":
                raise
            # Defer the credential error until a valid owner-only code reaches
            # the transaction. Wrong-code work and responses are therefore the
            # same for a new-account verification and existing-email resolution.
            password_user = None
        expected_password_hash = (
            str(password_user["password_hash"]) if password_user else ""
        )
        session_token = secrets.token_urlsafe(32)
        session_expires_at = (
            datetime.now(UTC) + timedelta(days=SESSION_DAYS)
        ).isoformat()

        def verified(
            conn: sqlite3.Connection, row: dict[str, Any], now: str
        ) -> dict[str, Any]:
            if password_user is None:
                raise AuthError(
                    "That verification code or password is invalid or expired.",
                    field="password",
                    code="invalid_verification_credentials",
                )
            current_password_hash = str(row["password_hash"])
            current_fingerprint = self.store._password_fingerprint(
                current_password_hash
            )
            if (
                str(row["user_id"]) != str(password_user["user_id"])
                or not hmac.compare_digest(
                    current_password_hash, expected_password_hash
                )
                or not row.get("credential_fingerprint")
                or not hmac.compare_digest(
                    current_fingerprint, str(row["credential_fingerprint"])
                )
            ):
                raise AuthError(
                    "This email-verification proof is no longer valid.",
                    code="challenge_stale",
                )
            if not row.get("email_normalized"):
                raise AuthError(
                    "This account no longer has an email to verify.",
                    code="challenge_stale",
                )
            conn.execute(
                "UPDATE users SET email_verified_at = ?, "
                "account_origin = CASE WHEN account_origin = 'pending_registration' "
                "THEN 'registered' ELSE account_origin END WHERE user_id = ?",
                (now, row["user_id"]),
            )
            context = self._challenge_context(row)
            guest_claim = context.get("guestClaim")
            guest_id = context.get("guestId")
            if guest_id:
                if not self.guest_progress:
                    raise AuthError(
                        "Legacy guest progress is unavailable.",
                        code="guest_claim_unavailable",
                    )
                guest_claim = self.guest_progress._claim(
                    conn, str(guest_id), str(row["user_id"])
                )
            self.store._insert_session(
                conn,
                token=session_token,
                user_id=str(row["user_id"]),
                expires_at=session_expires_at,
                now=now,
            )
            return {
                "token": session_token,
                "user": {
                    "userId": row["user_id"],
                    "username": row["username"],
                    "displayName": row["display_name"],
                },
                "accountStatus": "verified",
                "guestClaim": guest_claim,
            }

        def resolve_existing_registration(
            _conn: sqlite3.Connection, row: dict[str, Any], _now: str
        ) -> dict[str, Any]:
            # Only possession of the owner-only code reaches this branch. The
            # dummy password work above is ignored and never reads the existing
            # account's credential. No session or account mutation is granted.
            return {
                "accountResolutionRequired": True,
                "suggestedAction": (
                    "sign_in_or_reset_password"
                    if row.get("email_verified_at")
                    else "reset_password"
                ),
                "message": (
                    "This email is already connected to TRACE. Sign in or reset your password."
                    if row.get("email_verified_at")
                    else "Finish recovering this pending account by resetting its password."
                ),
            }

        status, result = self.store.verify_auth_challenge(
            challenge_id=challenge_id,
            purpose=(
                "registration_resolution" if resolution else "email_verification"
            ),
            presented_secret_hash=self._challenge_hash(
                "registration_resolution" if resolution else "email_verification",
                challenge_id,
                token or "",
            ),
            on_success=resolve_existing_registration if resolution else verified,
        )
        self._raise_challenge_failure(status)
        assert isinstance(result, dict)
        return result

    def resend_email_challenge(
        self,
        challenge_id: str,
        *,
        purpose: str,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        if purpose not in {
            "email_verification",
            "registration_resolution",
            "password_reset",
            "two_factor_login",
            "two_factor_enable",
            "two_factor_disable",
            "email_change_current_factor",
            "email_change",
        }:
            raise AuthError("Unsupported authentication email.", code="invalid_purpose")
        self._require_mailer()
        if user_id is not None:
            existing = self.store.get_auth_challenge(challenge_id)
            if not existing or str(existing["user_id"]) != user_id:
                return {
                    "ok": True,
                    "message": "If the request is eligible, an email will be sent.",
                }
        otp = purpose.startswith("two_factor_") or purpose in {
            "email_verification",
            "registration_resolution",
            "email_change_current_factor",
        }
        secret = f"{secrets.randbelow(1_000_000):06d}" if otp else secrets.token_urlsafe(32)
        ttl = (
            timedelta(minutes=EMAIL_OTP_MINUTES)
            if otp
            else timedelta(minutes=PASSWORD_RESET_MINUTES)
            if purpose == "password_reset"
            else timedelta(minutes=EMAIL_VERIFICATION_MINUTES)
            if purpose in {"email_verification", "registration_resolution"}
            else timedelta(hours=24)
        )
        expires_at = (datetime.now(UTC) + ttl).isoformat()
        status, row = self.store.resend_auth_challenge(
            challenge_id=challenge_id,
            purpose=purpose,
            replacement_secret_hash=self._challenge_hash(
                purpose, challenge_id, secret
            ),
            replacement_expires_at=expires_at,
            cooldown_seconds=EMAIL_RESEND_COOLDOWN_SECONDS,
            max_sends=EMAIL_CHALLENGE_MAX_SENDS,
        )
        # Invalid identifiers intentionally look like accepted no-op requests.
        if status == "invalid" or row is None:
            return {"ok": True, "message": "If the request is eligible, an email will be sent."}
        if status == "cooldown":
            raise AuthError(
                "Please wait before requesting another email.",
                code="resend_cooldown",
            )
        if status == "send_limit":
            raise AuthError(
                "This challenge cannot send more emails. Start the account flow again.",
                code="resend_limit",
            )
        context = self._challenge_context(row)
        recipient = str(
            context.get("destinationEmail") or row["email_normalized"]
        )
        try:
            self.mailer.send(
                AuthEmail(
                    purpose=purpose,
                    recipient=recipient,
                    challenge_id=challenge_id,
                    secret=secret,
                    expires_at=expires_at,
                )
            )
        except AuthMailerUnavailable:
            self.store.allow_auth_challenge_resend_now(challenge_id)
            return {
                "ok": True,
                "message": "Email delivery failed. Retry is available now.",
                "deliveryFailed": True,
                "retryAfterSeconds": 0,
            }
        return {
            "ok": True,
            "message": "If the request is eligible, an email will be sent.",
            "deliveryFailed": False,
            "retryAfterSeconds": EMAIL_RESEND_COOLDOWN_SECONDS,
        }

    def resend_registration_email(self, challenge_id: str) -> dict[str, Any]:
        """Resend either side of the privacy-preserving registration flow.

        The public endpoint does not expose whether the handle belongs to a new
        verification or an existing-account resolution challenge.
        """

        challenge = self.store.get_auth_challenge(challenge_id)
        purpose = (
            str(challenge.get("purpose"))
            if challenge
            and str(challenge.get("purpose"))
            in {"email_verification", "registration_resolution"}
            else "email_verification"
        )
        return self.resend_email_challenge(
            challenge_id,
            purpose=purpose,
        )

    def _reserve_recovery_request(
        self, *, email_key: str, client_ip: str | None
    ) -> None:
        normalized_ip = self._normalized_client_ip(client_ip)
        if self.store.consume_registration_attempt(
            pair_key_hash=self._rate_limit_digest(
                "ecg-password-reset-v1", "pair", normalized_ip, email_key
            ),
            ip_key_hash=self._rate_limit_digest(
                "ecg-password-reset-v1", "ip", normalized_ip
            ),
            global_key_hash=self._rate_limit_digest(
                "ecg-password-reset-v1", "global"
            ),
            max_pair_attempts=RECOVERY_PAIR_MAX_ATTEMPTS,
            max_ip_attempts=RECOVERY_IP_MAX_ATTEMPTS,
            max_global_attempts=RECOVERY_GLOBAL_MAX_ATTEMPTS,
            window_minutes=RECOVERY_WINDOW_MINUTES,
            block_minutes=RECOVERY_BLOCK_MINUTES,
        ):
            raise AuthError(
                "If the request is eligible, an email will be sent.",
                code="recovery_throttled",
            )

    def _reserve_recovery_confirm_attempt(
        self, *, challenge_id: str, client_ip: str | None
    ) -> None:
        """Bound PBKDF2 work before looking up an attacker-chosen reset id."""

        normalized_ip = self._normalized_client_ip(client_ip)
        if self.store.consume_registration_attempt(
            pair_key_hash=self._rate_limit_digest(
                "ecg-password-reset-confirm-v1",
                "pair",
                normalized_ip,
                challenge_id,
            ),
            ip_key_hash=self._rate_limit_digest(
                "ecg-password-reset-confirm-v1", "ip", normalized_ip
            ),
            global_key_hash=self._rate_limit_digest(
                "ecg-password-reset-confirm-v1", "global"
            ),
            max_pair_attempts=RECOVERY_CONFIRM_PAIR_MAX_ATTEMPTS,
            max_ip_attempts=RECOVERY_CONFIRM_IP_MAX_ATTEMPTS,
            max_global_attempts=RECOVERY_CONFIRM_GLOBAL_MAX_ATTEMPTS,
            window_minutes=RECOVERY_CONFIRM_WINDOW_MINUTES,
            block_minutes=RECOVERY_CONFIRM_BLOCK_MINUTES,
        ):
            raise AuthError(
                "Too many recovery confirmations. Wait before trying again.",
                code="recovery_confirm_throttled",
            )

    def request_password_reset(
        self, email: str | None, *, client_ip: str | None = None
    ) -> dict[str, Any]:
        """Create recovery mail without revealing whether an account exists."""

        self._require_mailer()
        try:
            normalized = normalize_email(email)
        except AuthError:
            normalized = "invalid@example.invalid"
        self._reserve_recovery_request(email_key=normalized, client_ip=client_ip)
        self.recovery_dispatcher.submit(
            lambda: self._dispatch_password_reset(normalized)
        )
        return {"ok": True, "message": "If the request is eligible, an email will be sent."}

    def _dispatch_password_reset(self, normalized: str) -> None:
        """Run account lookup and delivery outside the public response path."""

        user = self.store.get_user_by_email(normalized)
        recovery_eligible = bool(
            user
            and user.get("email_normalized")
            and (
                user.get("email_verified_at")
                or user.get("account_origin") == "pending_registration"
            )
        )
        if recovery_eligible and user:
            active = self.store.get_active_auth_challenge(
                str(user["user_id"]), "password_reset"
            )
            if active and int(active.get("send_count") or 0) >= EMAIL_CHALLENGE_MAX_SENDS:
                # Generic public recovery must not reset an account's delivery
                # ceiling. Wait for this challenge window to expire.
                return
            if active:
                try:
                    delivery = self.resend_email_challenge(
                        str(active["challenge_id"]), purpose="password_reset"
                    )
                    if delivery.get("deliveryFailed"):
                        raise AuthMailerUnavailable(
                            "Background password-reset delivery failed."
                        )
                except AuthError:
                    # Cooldown/send-limit state is deliberately indistinguishable
                    # from a missing account at this public endpoint.
                    pass
            else:
                delivery = self._issue_email_challenge(
                    user=user,
                    purpose="password_reset",
                    ttl=timedelta(minutes=PASSWORD_RESET_MINUTES),
                    otp=False,
                    max_attempts=EMAIL_CHALLENGE_MAX_ATTEMPTS,
                    reuse_active=True,
                    restart_exhausted=False,
                    credential_bound=True,
                )
                if delivery.get("deliveryFailed"):
                    raise AuthMailerUnavailable(
                        "Background password-reset delivery failed."
                    )
        else:
            # Match the purpose-bound secret work without storing an identifier.
            self._challenge_hash("password_reset", "dummy", normalized)

    def confirm_password_reset(
        self,
        challenge_id: str,
        token: str,
        new_password: str,
        *,
        recovery_username: str | None = None,
        recovery_display_name: str | None = None,
        client_ip: str | None = None,
    ) -> dict[str, Any]:
        self._reserve_recovery_confirm_attempt(
            challenge_id=challenge_id or "missing", client_ip=client_ip
        )
        challenge = self.store.get_auth_challenge(challenge_id)
        # Validate optional identity input uniformly before checking the proof.
        # Whether the challenge belongs to a pending or verified account must
        # not be observable from pre-proof validation behavior.
        requested_username = (recovery_username or "").strip().casefold()
        recovered_username = requested_username or (
            "student_" + str(challenge["user_id"]).removeprefix("u_")
            if challenge
            else "student_recovered"
        )
        if (
            not _USERNAME_RE.fullmatch(recovered_username)
            or recovered_username in RESERVED_USERNAMES
        ):
            raise AuthError(
                "Username must be 3-32 characters using only letters, digits, _, . or -, and cannot be reserved.",
                field="recoveryUsername",
                code="invalid_username",
            )
        recovered_display_name = (
            (recovery_display_name or "").strip() or "Student"
        )
        if len(recovered_display_name) > 80:
            raise AuthError(
                "Display name must be 80 characters or fewer.",
                field="recoveryDisplayName",
                code="display_name_too_long",
            )
        username = str(challenge["username"]) if challenge else "student"
        new_password = validate_new_password(
            new_password,
            username=username,
            field="newPassword",
            label="New password",
        )
        if recovered_username.casefold() != username.casefold():
            # Apply the same prospective-identity password check regardless of
            # whether the verified transaction ultimately needs a rename.
            validate_new_password(
                new_password,
                username=recovered_username,
                field="newPassword",
                label="New password",
            )
        new_hash = hash_password(new_password)

        def reset(
            conn: sqlite3.Connection, row: dict[str, Any], now: str
        ) -> dict[str, Any]:
            current_fingerprint = self.store._password_fingerprint(
                str(row["password_hash"])
            )
            if not row.get("credential_fingerprint") or not hmac.compare_digest(
                current_fingerprint, str(row["credential_fingerprint"])
            ):
                raise AuthError(
                    "This password-reset link is no longer valid.",
                    code="challenge_stale",
                )
            identity_recovered = bool(
                not row.get("email_verified_at")
                and row.get("account_origin") == "pending_registration"
            )
            if not row.get("email_verified_at") and not identity_recovered:
                # An established legacy account may have attached a typo that
                # was never proven. Email possession must not transfer its
                # username, password, or longitudinal learning record.
                raise AuthError(
                    "This password-reset link is no longer valid.",
                    code="challenge_stale",
                )
            if identity_recovered:
                updated = conn.execute(
                    "UPDATE users SET username = ?, display_name = ?, password_hash = ?, "
                    "email_verified_at = ?, account_origin = 'registered' "
                    "WHERE user_id = ? AND email_verified_at IS NULL "
                    "AND account_origin = 'pending_registration'",
                    (
                        recovered_username,
                        recovered_display_name,
                        new_hash,
                        now,
                        row["user_id"],
                    ),
                )
                profile_updated = conn.execute(
                    "UPDATE learner_profiles SET display_name = ?, updated_at = ? "
                    "WHERE learner_id = ?",
                    (recovered_display_name, now, row["user_id"]),
                )
                if int(profile_updated.rowcount) != 1:
                    raise AuthError(
                        "Pending account identity recovery is incomplete. Start again.",
                        code="recovery_identity_unavailable",
                    )
            else:
                updated = conn.execute(
                    "UPDATE users SET password_hash = ? WHERE user_id = ?",
                    (new_hash, row["user_id"]),
                )
            if int(updated.rowcount) != 1:
                raise AuthError(
                    "The account changed while recovery was being confirmed. Start again.",
                    code="challenge_stale",
                )
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (row["user_id"],))
            if self.store._table_exists(conn, "export_authorizations"):
                conn.execute(
                    "DELETE FROM export_authorizations WHERE user_id = ?",
                    (row["user_id"],),
                )
            conn.execute(
                "UPDATE auth_challenges SET consumed_at = ? "
                "WHERE user_id = ? AND challenge_id <> ? AND consumed_at IS NULL",
                (now, row["user_id"], challenge_id),
            )
            result: dict[str, Any] = {
                "ok": True,
                "_securityNotificationEmail": row.get("email_normalized"),
                "_securityNotificationAt": now,
            }
            if identity_recovered:
                result.update(
                    {
                        "identityRecovered": True,
                        "username": recovered_username,
                        "displayName": recovered_display_name,
                    }
                )
            return result

        try:
            status, result = self.store.verify_auth_challenge(
                challenge_id=challenge_id,
                purpose="password_reset",
                presented_secret_hash=self._challenge_hash(
                    "password_reset", challenge_id, token or ""
                ),
                on_success=reset,
            )
        except sqlite3.IntegrityError as exc:
            # The only mutable unique identity in this transaction is the
            # optional replacement username. A collision leaves the password,
            # verification state, sessions, and one-time proof untouched.
            raise AuthError(
                "That recovery username is unavailable. Choose another.",
                field="recoveryUsername",
                code="recovery_identity_unavailable",
            ) from exc
        self._raise_challenge_failure(status)
        assert isinstance(result, dict)
        notification_email = result.pop("_securityNotificationEmail", None)
        notification_at = result.pop("_securityNotificationAt", None)
        self._queue_security_notification(
            purpose="password_reset_complete",
            email=str(notification_email or ""),
            occurred_at=str(notification_at or "") or None,
        )
        return result

    def verify_email_two_factor(
        self, challenge_id: str, code: str
    ) -> dict[str, Any]:
        session_token = secrets.token_urlsafe(32)
        session_expires_at = (
            datetime.now(UTC) + timedelta(days=SESSION_DAYS)
        ).isoformat()

        def complete(
            conn: sqlite3.Connection, row: dict[str, Any], now: str
        ) -> dict[str, Any]:
            current_fingerprint = self.store._password_fingerprint(
                str(row["password_hash"])
            )
            if (
                not row.get("email_verified_at")
                or not bool(row.get("email_two_factor_enabled"))
                or not row.get("credential_fingerprint")
                or not hmac.compare_digest(
                    current_fingerprint, str(row["credential_fingerprint"])
                )
            ):
                raise AuthError(
                    "This sign-in challenge is no longer valid.",
                    code="challenge_stale",
                )
            context = self._challenge_context(row)
            guest_claim = None
            guest_id = context.get("guestId")
            if guest_id:
                if not self.guest_progress:
                    raise AuthError(
                        "Legacy guest progress is unavailable.",
                        code="guest_claim_unavailable",
                    )
                guest_claim = self.guest_progress._claim(
                    conn, str(guest_id), str(row["user_id"])
                )
            self.store._insert_session(
                conn,
                token=session_token,
                user_id=str(row["user_id"]),
                expires_at=session_expires_at,
                now=now,
            )
            return {
                "token": session_token,
                "user": {
                    "userId": row["user_id"],
                    "username": row["username"],
                    "displayName": row["display_name"],
                },
                "twoFactorRequired": False,
                "guestClaim": guest_claim,
            }

        status, result = self.store.verify_auth_challenge(
            challenge_id=challenge_id,
            purpose="two_factor_login",
            presented_secret_hash=self._challenge_hash(
                "two_factor_login", challenge_id, code or ""
            ),
            on_success=complete,
        )
        self._raise_challenge_failure(status)
        assert isinstance(result, dict)
        return result

    def request_email_two_factor_enable(
        self,
        user_id: str,
        current_password: str,
        *,
        client_ip: str | None = None,
    ) -> dict[str, Any]:
        user = self._verify_current_password(
            user_id, current_password, client_ip
        )
        if not user or not user.get("email_verified_at"):
            raise AuthError(
                "Verify your email before enabling email two-factor authentication.",
                code="email_verification_required",
            )
        if bool(user.get("email_two_factor_enabled")):
            raise AuthError(
                "Email two-factor authentication is already enabled.",
                code="two_factor_already_enabled",
            )
        return self._issue_email_challenge(
            user=user,
            purpose="two_factor_enable",
            ttl=timedelta(minutes=EMAIL_OTP_MINUTES),
            otp=True,
            max_attempts=EMAIL_OTP_MAX_ATTEMPTS,
            reuse_active=True,
            credential_bound=True,
        )

    def _rotate_sensitive_session(
        self,
        conn: sqlite3.Connection,
        *,
        user_id: str,
        current_session_token: str,
        replacement_session_token: str,
        replacement_session_expires_at: str,
        now: str,
    ) -> None:
        """Replace the proving credential inside a sensitive-change transaction."""

        current_session_key = self.store._session_key(current_session_token)
        if not conn.execute(
            "SELECT 1 FROM sessions WHERE token = ? AND user_id = ?",
            (current_session_key, user_id),
        ).fetchone():
            raise AuthError(
                "The session proving this account change is no longer active.",
                code="challenge_stale",
            )
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        if self.store._table_exists(conn, "export_authorizations"):
            conn.execute(
                "DELETE FROM export_authorizations WHERE user_id = ?", (user_id,)
            )
        self.store._insert_session(
            conn,
            token=replacement_session_token,
            user_id=user_id,
            expires_at=replacement_session_expires_at,
            now=now,
        )

    def confirm_email_two_factor_enable(
        self,
        user_id: str,
        challenge_id: str,
        code: str,
        current_session_token: str,
    ) -> dict[str, Any]:
        replacement_session_token = secrets.token_urlsafe(32)
        replacement_session_expires_at = (
            datetime.now(UTC) + timedelta(days=SESSION_DAYS)
        ).isoformat()

        def enable(
            conn: sqlite3.Connection, row: dict[str, Any], now: str
        ) -> dict[str, Any]:
            if not row.get("email_verified_at"):
                raise AuthError(
                    "Verify your email before enabling two-factor authentication.",
                    code="email_verification_required",
                )
            current_fingerprint = self.store._password_fingerprint(
                str(row["password_hash"])
            )
            if not row.get("credential_fingerprint") or not hmac.compare_digest(
                current_fingerprint, str(row["credential_fingerprint"])
            ):
                raise AuthError(
                    "This two-factor challenge is no longer valid.",
                    code="challenge_stale",
                )
            if bool(row.get("email_two_factor_enabled")):
                raise AuthError(
                    "This two-factor challenge is no longer valid.",
                    code="challenge_stale",
                )
            self._rotate_sensitive_session(
                conn,
                user_id=user_id,
                current_session_token=current_session_token,
                replacement_session_token=replacement_session_token,
                replacement_session_expires_at=replacement_session_expires_at,
                now=now,
            )
            updated = conn.execute(
                "UPDATE users SET email_two_factor_enabled = 1 "
                "WHERE user_id = ? AND email_two_factor_enabled = 0",
                (user_id,),
            )
            if int(updated.rowcount) != 1:
                raise AuthError(
                    "This two-factor challenge is no longer valid.",
                    code="challenge_stale",
                )
            # Enabling a new factor invalidates every proof minted under the
            # prior account-security state. The current proof is consumed by
            # ``verify_auth_challenge`` immediately after this callback.
            conn.execute(
                "UPDATE auth_challenges SET consumed_at = ? WHERE user_id = ? "
                "AND challenge_id <> ? AND consumed_at IS NULL",
                (now, user_id, challenge_id),
            )
            return {
                "ok": True,
                "emailTwoFactorEnabled": True,
                "_sessionToken": replacement_session_token,
                "_securityNotificationEmail": row.get("email_normalized"),
                "_securityNotificationAt": now,
            }

        status, result = self.store.verify_auth_challenge(
            challenge_id=challenge_id,
            purpose="two_factor_enable",
            user_id=user_id,
            presented_secret_hash=self._challenge_hash(
                "two_factor_enable", challenge_id, code or ""
            ),
            on_success=enable,
        )
        self._raise_challenge_failure(status)
        assert isinstance(result, dict)
        notification_email = result.pop("_securityNotificationEmail", None)
        notification_at = result.pop("_securityNotificationAt", None)
        self._queue_security_notification(
            purpose="two_factor_enabled",
            email=str(notification_email or ""),
            occurred_at=str(notification_at or "") or None,
        )
        return result

    def request_email_two_factor_disable(
        self,
        user_id: str,
        current_password: str,
        *,
        client_ip: str | None = None,
    ) -> dict[str, Any]:
        user = self._verify_current_password(user_id, current_password, client_ip)
        if not user.get("email_verified_at") or not user.get("email_normalized"):
            raise AuthError(
                "A verified email is required to change two-factor authentication.",
                code="email_verification_required",
            )
        if not bool(user.get("email_two_factor_enabled")):
            raise AuthError(
                "Email two-factor authentication is already disabled.",
                code="two_factor_already_disabled",
            )
        return self._issue_email_challenge(
            user=user,
            purpose="two_factor_disable",
            ttl=timedelta(minutes=EMAIL_OTP_MINUTES),
            otp=True,
            max_attempts=EMAIL_OTP_MAX_ATTEMPTS,
            reuse_active=True,
            credential_bound=True,
        )

    def confirm_email_two_factor_disable(
        self,
        user_id: str,
        challenge_id: str,
        code: str,
        current_session_token: str,
    ) -> dict[str, Any]:
        replacement_session_token = secrets.token_urlsafe(32)
        replacement_session_expires_at = (
            datetime.now(UTC) + timedelta(days=SESSION_DAYS)
        ).isoformat()

        def disable(
            conn: sqlite3.Connection, row: dict[str, Any], now: str
        ) -> dict[str, Any]:
            current_fingerprint = self.store._password_fingerprint(
                str(row["password_hash"])
            )
            if (
                not row.get("email_verified_at")
                or not bool(row.get("email_two_factor_enabled"))
                or not row.get("credential_fingerprint")
                or not hmac.compare_digest(
                    current_fingerprint, str(row["credential_fingerprint"])
                )
            ):
                raise AuthError(
                    "This two-factor challenge is no longer valid.",
                    code="challenge_stale",
                )
            self._rotate_sensitive_session(
                conn,
                user_id=user_id,
                current_session_token=current_session_token,
                replacement_session_token=replacement_session_token,
                replacement_session_expires_at=replacement_session_expires_at,
                now=now,
            )
            updated = conn.execute(
                "UPDATE users SET email_two_factor_enabled = 0 "
                "WHERE user_id = ? AND email_two_factor_enabled = 1",
                (user_id,),
            )
            if int(updated.rowcount) != 1:
                raise AuthError(
                    "This two-factor challenge is no longer valid.",
                    code="challenge_stale",
                )
            conn.execute(
                "UPDATE auth_challenges SET consumed_at = ? WHERE user_id = ? "
                "AND challenge_id <> ? AND purpose IN "
                "('two_factor_login', 'two_factor_enable', "
                "'email_change_current_factor') AND consumed_at IS NULL",
                (now, user_id, challenge_id),
            )
            return {
                "ok": True,
                "emailTwoFactorEnabled": False,
                "_sessionToken": replacement_session_token,
                "_securityNotificationEmail": row.get("email_normalized"),
                "_securityNotificationAt": now,
            }

        status, result = self.store.verify_auth_challenge(
            challenge_id=challenge_id,
            purpose="two_factor_disable",
            user_id=user_id,
            presented_secret_hash=self._challenge_hash(
                "two_factor_disable", challenge_id, code or ""
            ),
            on_success=disable,
        )
        self._raise_challenge_failure(status)
        assert isinstance(result, dict)
        notification_email = result.pop("_securityNotificationEmail", None)
        notification_at = result.pop("_securityNotificationAt", None)
        self._queue_security_notification(
            purpose="two_factor_disabled",
            email=str(notification_email or ""),
            occurred_at=str(notification_at or "") or None,
        )
        return result

    def request_legacy_email_upgrade(
        self,
        user_id: str,
        email: str,
        current_password: str,
        *,
        client_ip: str | None = None,
    ) -> dict[str, Any]:
        self._require_mailer()
        user = self._verify_current_password(user_id, current_password, client_ip)
        if user.get("email_normalized"):
            raise AuthError(
                "This account already has an email address.",
                code="email_already_set",
            )
        normalized = normalize_email(email)
        challenge = self._new_challenge(
            "email_verification",
            ttl=timedelta(minutes=EMAIL_VERIFICATION_MINUTES),
            otp=True,
        )
        try:
            updated = self.store.set_unverified_email(
                user_id=user_id,
                expected_password_hash=str(user["password_hash"]),
                email_normalized=normalized,
                challenge_id=challenge["challengeId"],
                secret_hash=challenge["secretHash"],
                expires_at=challenge["expiresAt"],
                max_attempts=EMAIL_OTP_MAX_ATTEMPTS,
                context=self._verification_budget_context(
                    purpose="email_verification",
                    user_id=user_id,
                    email=normalized,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise AuthError(
                "That email cannot be added to this account.",
                field="email",
                code="email_unavailable",
            ) from exc
        if not updated:
            raise AuthError(
                "Your account changed while email setup was being confirmed. Please try again.",
                code="account_changed",
            )
        delivery_failed = False
        try:
            self._deliver_challenge(
                purpose="email_verification", email=normalized, challenge=challenge
            )
        except AuthMailerUnavailable:
            delivery_failed = True
            self.store.allow_auth_challenge_resend_now(challenge["challengeId"])
        return {
            "verificationRequired": True,
            "challengeId": challenge["challengeId"],
            "maskedEmail": mask_email(normalized),
            "expiresAt": challenge["expiresAt"],
            "deliveryFailed": delivery_failed,
            "retryAfterSeconds": 0 if delivery_failed else None,
        }

    def request_email_change(
        self,
        user_id: str,
        email: str,
        current_password: str,
        *,
        client_ip: str | None = None,
    ) -> dict[str, Any]:
        self._require_mailer()
        user = self._verify_current_password(user_id, current_password, client_ip)
        if not user.get("email_verified_at"):
            raise AuthError(
                "Verify your current account email before changing it.",
                code="email_verification_required",
            )
        normalized = normalize_email(email)
        if normalized == user.get("email_normalized"):
            raise AuthError(
                "New email must differ from the current email.",
                field="email",
                code="email_unchanged",
            )
        existing = self.store.get_user_by_email(normalized)
        if existing and str(existing["user_id"]) != user_id:
            raise AuthError(
                "That email cannot be added to this account.",
                field="email",
                code="email_unavailable",
            )
        if bool(user.get("email_two_factor_enabled")):
            challenge = self._issue_email_challenge(
                user=user,
                purpose="email_change_current_factor",
                ttl=timedelta(minutes=EMAIL_OTP_MINUTES),
                otp=True,
                max_attempts=EMAIL_OTP_MAX_ATTEMPTS,
                context={"pendingDestinationEmail": normalized},
                reuse_active=False,
                credential_bound=True,
            )
            return {
                "currentEmailFactorRequired": True,
                "challengeId": challenge["challengeId"],
                "maskedEmail": challenge["maskedEmail"],
                "expiresAt": challenge["expiresAt"],
                "deliveryFailed": challenge.get("deliveryFailed", False),
                "retryAfterSeconds": challenge.get("retryAfterSeconds"),
            }
        challenge = self._issue_email_challenge(
            user=user,
            purpose="email_change",
            ttl=timedelta(hours=24),
            otp=False,
            max_attempts=EMAIL_CHALLENGE_MAX_ATTEMPTS,
            context={"destinationEmail": normalized},
            reuse_active=False,
            credential_bound=True,
            destination_email=normalized,
        )
        return {
            "emailChangeVerificationRequired": True,
            "challengeId": challenge["challengeId"],
            "maskedEmail": challenge["maskedEmail"],
            "expiresAt": challenge["expiresAt"],
            "deliveryFailed": challenge.get("deliveryFailed", False),
            "retryAfterSeconds": challenge.get("retryAfterSeconds"),
        }

    def confirm_email_change_current_factor(
        self,
        user_id: str,
        challenge_id: str,
        code: str,
        current_session_token: str,
    ) -> dict[str, Any]:
        """Exchange a current-address OTP for one new-address proof."""

        link_challenge = self._new_challenge(
            "email_change",
            ttl=timedelta(minutes=EMAIL_CHANGE_FACTOR_WINDOW_MINUTES),
            otp=False,
        )

        def prove_current_factor(
            conn: sqlite3.Connection, row: dict[str, Any], now: str
        ) -> dict[str, Any]:
            current_fingerprint = self.store._password_fingerprint(
                str(row["password_hash"])
            )
            if (
                not row.get("email_verified_at")
                or not bool(row.get("email_two_factor_enabled"))
                or not row.get("credential_fingerprint")
                or not hmac.compare_digest(
                    current_fingerprint, str(row["credential_fingerprint"])
                )
            ):
                raise AuthError(
                    "This email-change security code is no longer valid.",
                    code="challenge_stale",
                )
            current_session_key = self.store._session_key(current_session_token)
            if not conn.execute(
                "SELECT 1 FROM sessions WHERE token = ? AND user_id = ?",
                (current_session_key, user_id),
            ).fetchone():
                raise AuthError(
                    "The session proving this email change is no longer active.",
                    code="challenge_stale",
                )
            destination = self._challenge_context(row).get(
                "pendingDestinationEmail"
            )
            normalized = normalize_email(str(destination or ""))
            if normalized == str(row.get("email_normalized") or ""):
                raise AuthError(
                    "New email must differ from the current email.",
                    field="email",
                    code="email_unchanged",
                )
            existing = conn.execute(
                "SELECT user_id FROM users WHERE email_normalized = ?",
                (normalized,),
            ).fetchone()
            if existing and str(existing["user_id"]) != user_id:
                raise AuthError(
                    "That email cannot be added to this account.",
                    field="email",
                    code="email_unavailable",
                )
            self.store._insert_auth_challenge(
                conn,
                challenge_id=link_challenge["challengeId"],
                user_id=user_id,
                purpose="email_change",
                secret_hash=link_challenge["secretHash"],
                expires_at=link_challenge["expiresAt"],
                max_attempts=EMAIL_CHALLENGE_MAX_ATTEMPTS,
                now=now,
                credential_fingerprint=current_fingerprint,
                context={
                    "destinationEmail": normalized,
                    "currentFactorVerifiedAt": now,
                },
            )
            return {"destinationEmail": normalized}

        status, result = self.store.verify_auth_challenge(
            challenge_id=challenge_id,
            purpose="email_change_current_factor",
            user_id=user_id,
            presented_secret_hash=self._challenge_hash(
                "email_change_current_factor", challenge_id, code or ""
            ),
            on_success=prove_current_factor,
        )
        self._raise_challenge_failure(status)
        assert isinstance(result, dict)
        delivery_failed = False
        try:
            self._deliver_challenge(
                purpose="email_change",
                email=str(result["destinationEmail"]),
                challenge=link_challenge,
            )
        except AuthMailerUnavailable:
            delivery_failed = True
            self.store.allow_auth_challenge_resend_now(
                link_challenge["challengeId"]
            )
        return {
            "emailChangeVerificationRequired": True,
            "challengeId": link_challenge["challengeId"],
            "maskedEmail": mask_email(str(result["destinationEmail"])),
            "expiresAt": link_challenge["expiresAt"],
            "deliveryFailed": delivery_failed,
            "retryAfterSeconds": 0 if delivery_failed else None,
        }

    @staticmethod
    def _raise_unverified_email_change_unavailable() -> None:
        raise AuthError(
            "That unverified email update is no longer available. Start the account flow again.",
            code="unverified_email_change_unavailable",
        )

    def _unverified_email_change_actor(
        self,
        *,
        user_id: str | None,
        challenge_id: str | None,
        current_password: str,
        client_ip: str | None,
    ) -> tuple[dict[str, Any], str, str | None]:
        """Authenticate either side of the typo-correction lifecycle."""

        expected_origin = "established" if user_id else "pending_registration"
        supplied_challenge = None
        candidate_user_id = user_id
        if candidate_user_id is None and challenge_id:
            supplied_challenge = self.store.get_auth_challenge(challenge_id)
            if (
                supplied_challenge
                and supplied_challenge.get("purpose") == "email_verification"
                and not supplied_challenge.get("consumed_at")
                and supplied_challenge.get("account_origin")
                == "pending_registration"
                and not supplied_challenge.get("email_verified_at")
            ):
                candidate_user_id = str(supplied_challenge["user_id"])
        if candidate_user_id is None:
            candidate_user_id = (
                "u_unverified_email_"
                + self._rate_limit_digest(
                    "ecg-unverified-email-change-v1", challenge_id or "missing"
                )[:16]
            )
        try:
            user = self._verify_current_password(
                candidate_user_id, current_password, client_ip
            )
        except AuthError as exc:
            if exc.code == "reauth_throttled":
                raise
            self._raise_unverified_email_change_unavailable()
        if (
            user.get("account_origin") != expected_origin
            or user.get("email_verified_at")
            or not user.get("email_normalized")
        ):
            self._raise_unverified_email_change_unavailable()
        pending = self.store.get_pending_auth_challenge(
            str(user["user_id"]), "email_verification"
        )
        pending_id = str(pending["challenge_id"]) if pending else None
        if user_id is None and pending_id != challenge_id:
            self._raise_unverified_email_change_unavailable()
        return user, expected_origin, pending_id

    def replace_unverified_email(
        self,
        *,
        user_id: str | None,
        challenge_id: str | None,
        current_password: str,
        new_email: str,
        client_ip: str | None = None,
    ) -> dict[str, Any]:
        """Correct an unreachable setup address without weakening activation."""

        self._require_mailer()
        normalized = normalize_email(new_email)
        user, origin, expected_challenge_id = self._unverified_email_change_actor(
            user_id=user_id,
            challenge_id=challenge_id,
            current_password=current_password,
            client_ip=client_ip,
        )
        challenge = self._new_challenge(
            "email_verification",
            ttl=timedelta(minutes=EMAIL_VERIFICATION_MINUTES),
            otp=True,
        )
        try:
            replaced = self.store.replace_unverified_email(
                user_id=str(user["user_id"]),
                expected_password_hash=str(user["password_hash"]),
                expected_account_origin=origin,
                expected_email_normalized=str(user["email_normalized"]),
                expected_challenge_id=expected_challenge_id,
                email_normalized=normalized,
                challenge_id=challenge["challengeId"],
                secret_hash=challenge["secretHash"],
                expires_at=challenge["expiresAt"],
                max_attempts=EMAIL_OTP_MAX_ATTEMPTS,
                context=self._verification_budget_context(
                    purpose="email_verification",
                    user_id=str(user["user_id"]),
                    email=normalized,
                ),
            )
        except sqlite3.IntegrityError:
            self._raise_unverified_email_change_unavailable()
        if not replaced:
            self._raise_unverified_email_change_unavailable()
        delivery_failed = False
        try:
            self._deliver_challenge(
                purpose="email_verification",
                email=normalized,
                challenge=challenge,
            )
        except AuthMailerUnavailable:
            delivery_failed = True
            self.store.allow_auth_challenge_resend_now(challenge["challengeId"])
        return {
            "verificationRequired": True,
            "challengeId": challenge["challengeId"],
            "maskedEmail": mask_email(normalized),
            "expiresAt": challenge["expiresAt"],
            "deliveryFailed": delivery_failed,
            "retryAfterSeconds": 0 if delivery_failed else None,
        }

    def cancel_unverified_email(
        self,
        *,
        user_id: str | None,
        challenge_id: str | None,
        current_password: str,
        client_ip: str | None = None,
    ) -> dict[str, Any]:
        """Cancel pending registration or detach a legacy setup typo."""

        user, origin, expected_challenge_id = self._unverified_email_change_actor(
            user_id=user_id,
            challenge_id=challenge_id,
            current_password=current_password,
            client_ip=client_ip,
        )
        result = self.store.cancel_unverified_email(
            user_id=str(user["user_id"]),
            expected_password_hash=str(user["password_hash"]),
            expected_account_origin=origin,
            expected_email_normalized=str(user["email_normalized"]),
            expected_challenge_id=expected_challenge_id,
        )
        if result == "account_cancelled":
            return {"ok": True, "accountCancelled": True}
        if result == "email_removed":
            return {
                "ok": True,
                "emailRemoved": True,
                "accountStatus": "email_upgrade_required",
            }
        self._raise_unverified_email_change_unavailable()

    def cancel_email_change(self, user_id: str, challenge_id: str) -> dict[str, bool]:
        """Dismiss a pending email change by consuming its owner-bound proof."""

        self.store.consume_owner_auth_challenge(
            user_id=user_id,
            challenge_id=challenge_id,
            purpose="email_change",
        )
        return {"ok": True}

    def confirm_email_change(
        self,
        user_id: str,
        challenge_id: str,
        token: str,
        current_session_token: str,
    ) -> dict[str, Any]:
        replacement_session_token = secrets.token_urlsafe(32)
        replacement_session_expires_at = (
            datetime.now(UTC) + timedelta(days=SESSION_DAYS)
        ).isoformat()

        def change(
            conn: sqlite3.Connection, row: dict[str, Any], now: str
        ) -> dict[str, Any]:
            current_fingerprint = self.store._password_fingerprint(
                str(row["password_hash"])
            )
            if not row.get("credential_fingerprint") or not hmac.compare_digest(
                current_fingerprint, str(row["credential_fingerprint"])
            ):
                raise AuthError(
                    "This email-change link is no longer valid.",
                    code="challenge_stale",
                )
            destination = self._challenge_context(row).get("destinationEmail")
            context = self._challenge_context(row)
            if bool(row.get("email_two_factor_enabled")):
                try:
                    factor_verified_at = datetime.fromisoformat(
                        str(context.get("currentFactorVerifiedAt") or "")
                    )
                    if factor_verified_at.tzinfo is None:
                        factor_verified_at = factor_verified_at.replace(tzinfo=UTC)
                    factor_is_fresh = factor_verified_at + timedelta(
                        minutes=EMAIL_CHANGE_FACTOR_WINDOW_MINUTES
                    ) >= datetime.fromisoformat(now)
                except (TypeError, ValueError):
                    factor_is_fresh = False
                if not factor_is_fresh:
                    raise AuthError(
                        "Confirm a fresh code sent to your current email before changing it.",
                        code="current_email_factor_required",
                    )
            normalized = normalize_email(str(destination or ""))
            updated = conn.execute(
                "UPDATE users SET email_normalized = ?, email_verified_at = ? "
                "WHERE user_id = ?",
                (normalized, now, user_id),
            )
            if int(updated.rowcount) != 1:
                raise AuthError("Account not found.", code="account_changed")
            self._rotate_sensitive_session(
                conn,
                user_id=user_id,
                current_session_token=current_session_token,
                replacement_session_token=replacement_session_token,
                replacement_session_expires_at=replacement_session_expires_at,
                now=now,
            )
            conn.execute(
                "UPDATE auth_challenges SET consumed_at = ? "
                "WHERE user_id = ? AND challenge_id <> ? AND consumed_at IS NULL",
                (now, user_id, challenge_id),
            )
            return {
                "ok": True,
                "_sessionToken": replacement_session_token,
                "_securityNotificationEmail": row.get("email_normalized"),
                "_securityNotificationAt": now,
            }

        try:
            status, result = self.store.verify_auth_challenge(
                challenge_id=challenge_id,
                purpose="email_change",
                user_id=user_id,
                presented_secret_hash=self._challenge_hash(
                    "email_change", challenge_id, token or ""
                ),
                on_success=change,
            )
        except sqlite3.IntegrityError as exc:
            raise AuthError(
                "That email cannot be added to this account.",
                field="email",
                code="email_unavailable",
            ) from exc
        self._raise_challenge_failure(status)
        assert isinstance(result, dict)
        previous_email = result.pop("_securityNotificationEmail", None)
        notification_at = result.pop("_securityNotificationAt", None)
        self._queue_security_notification(
            purpose="email_changed",
            email=str(previous_email or ""),
            occurred_at=str(notification_at or "") or None,
        )
        result["user"] = self.public_user(user_id)
        return result

    def logout(self, token: str | None) -> None:
        if token:
            self.store.delete_session(token)

    def logout_all(self, user_id: str) -> int:
        return self.store.delete_user_sessions(user_id)

    def logout_others(self, user_id: str, current_token: str) -> int:
        return self.store.delete_other_user_sessions(user_id, current_token)

    def sessions(self, user_id: str, current_token: str) -> list[dict[str, Any]]:
        return self.store.list_user_sessions(user_id, current_token)

    def revoke_session(
        self, user_id: str, current_token: str, session_id: str
    ) -> None:
        status = self.store.delete_owned_session_by_public_id(
            user_id, current_token, session_id
        )
        if status == "current":
            raise AuthError(
                "The current session must be signed out normally.",
                code="current_session",
            )
        if status != "revoked":
            # Foreign and absent identifiers intentionally share one response.
            raise AuthError("Session not found.", code="session_not_found")

    def _verify_current_password(
        self,
        user_id: str,
        current_password: str,
        client_ip: str | None,
    ) -> dict[str, Any]:
        """Rate-limit password reauthentication before doing PBKDF2 work."""

        user = self.store.get_user_auth(user_id)
        username = str(user["username"]) if user else user_id
        normalized_ip = self._normalized_client_ip(client_ip)
        pair_key_hash = self._rate_limit_digest(
            "ecg-account-reauth-v1", "pair", normalized_ip, username
        )
        ip_key_hash = self._rate_limit_digest(
            "ecg-account-reauth-v1", "ip", normalized_ip
        )
        global_key_hash = self._rate_limit_digest("ecg-account-reauth-v1", "global")
        if self.store.consume_login_attempt(
            pair_key_hash=pair_key_hash,
            ip_key_hash=ip_key_hash,
            global_key_hash=global_key_hash,
            max_pair_attempts=ACCOUNT_REAUTH_PAIR_MAX_ATTEMPTS,
            max_ip_attempts=ACCOUNT_REAUTH_IP_MAX_ATTEMPTS,
            max_global_attempts=ACCOUNT_REAUTH_GLOBAL_MAX_ATTEMPTS,
            window_minutes=ACCOUNT_REAUTH_WINDOW_MINUTES,
            block_minutes=ACCOUNT_REAUTH_BLOCK_MINUTES,
        ):
            raise AuthError(
                "Too many password confirmation attempts. Please wait and try again.",
                code="reauth_throttled",
            )
        valid = verify_password(
            current_password or "", user["password_hash"] if user else _DUMMY_PASSWORD_HASH
        )
        if not user or not valid:
            raise AuthError(
                "Current password is incorrect.",
                field="currentPassword",
                code="invalid_current_password",
            )
        self.store.clear_login_pair_attempts(pair_key_hash)
        return user

    def change_password(
        self,
        user_id: str,
        current_password: str,
        new_password: str,
        *,
        client_ip: str | None = None,
    ) -> dict[str, Any]:
        user = self._verify_current_password(user_id, current_password, client_ip)
        new_password = validate_new_password(
            new_password,
            username=str(user["username"]),
            field="newPassword",
            label="New password",
        )
        if verify_password(new_password, user["password_hash"]):
            raise AuthError(
                "New password must be different from the current password.",
                field="newPassword",
                code="password_unchanged",
            )
        replacement_token = secrets.token_urlsafe(32)
        replacement_expiry = (
            datetime.now(UTC) + timedelta(days=SESSION_DAYS)
        ).isoformat()
        rotated = self.store.rotate_password_and_sessions(
            user_id=user_id,
            expected_password_hash=str(user["password_hash"]),
            new_password_hash=hash_password(new_password),
            new_session_token=replacement_token,
            new_session_expires_at=replacement_expiry,
        )
        if not rotated:
            raise AuthError(
                "Your password changed while the update was being confirmed. Please try again.",
                field="currentPassword",
                code="password_changed",
            )
        self._queue_security_notification(
            purpose="password_changed",
            email=str(user.get("email_normalized") or ""),
        )
        return {
            "token": replacement_token,
            "user": {
                "userId": user_id,
                "username": user["username"],
                "displayName": user["display_name"],
            },
        }

    def authorize_export(
        self,
        user_id: str,
        current_session_token: str,
        current_password: str,
        *,
        client_ip: str | None = None,
    ) -> dict[str, str]:
        """Issue one short-lived export grant after fresh password verification."""

        # Starting a new confirmation attempt rotates away any prior unused
        # grant for this session, even if the newly supplied password is wrong.
        self.store.delete_export_authorization_for_session(
            user_id, current_session_token
        )
        user = self._verify_current_password(user_id, current_password, client_ip)
        token = secrets.token_urlsafe(32)
        expires_at = (
            datetime.now(UTC) + timedelta(seconds=EXPORT_AUTHORIZATION_SECONDS)
        ).isoformat()
        if not self.store.create_export_authorization(
            token=token,
            user_id=user_id,
            current_session_token=current_session_token,
            expected_password_hash=str(user["password_hash"]),
            expires_at=expires_at,
        ):
            raise AuthError(
                "Your account credentials changed while export access was being confirmed. Confirm your password again.",
                field="currentPassword",
                code="export_authorization_stale",
            )
        return {"token": token, "expiresAt": expires_at}

    def export_progress(
        self,
        user_id: str,
        current_session_token: str,
        export_authorization: str | None,
    ) -> dict[str, Any]:
        status = self.store.consume_export_authorization(
            token=export_authorization,
            user_id=user_id,
            current_session_token=current_session_token,
        )
        if status != "authorized":
            codes = {
                "expired": "export_authorization_expired",
                "invalid": "export_authorization_invalid",
                "credentials_changed": "export_authorization_stale",
            }
            raise AuthError(
                "Confirm your current password again before downloading progress.",
                field="currentPassword",
                code=codes.get(status, "export_authorization_required"),
            )
        exported = self.store.export_user_progress(user_id)
        if not exported:
            raise AuthError("Account is no longer available.", code="account_unavailable")
        return exported

    def delete_account(
        self,
        user_id: str,
        current_password: str,
        confirmation: str,
        *,
        client_ip: str | None = None,
    ) -> None:
        user = self._verify_current_password(user_id, current_password, client_ip)
        if (confirmation or "").strip() != str(user["username"]):
            raise AuthError(
                "Type your username exactly to confirm account deletion.",
                field="confirmation",
                code="confirmation_mismatch",
            )
        if not self.store.delete_user_account(user_id, str(user["password_hash"])):
            # A concurrent password change invalidates the recent-password
            # confirmation rather than deleting under stale credentials.
            raise AuthError(
                "Your password changed while deletion was being confirmed. Please try again.",
                field="currentPassword",
                code="password_changed",
            )
        self._queue_security_notification(
            purpose="account_deleted",
            email=str(user.get("email_normalized") or ""),
        )

    def resolve(self, token: str | None) -> str | None:
        """Return the user id for a valid bearer token, otherwise ``None``."""
        return self.store.get_session_user(token) if token else None

    def me(self, token: str | None) -> dict[str, Any] | None:
        user_id = self.resolve(token)
        return self.public_user(user_id) if user_id else None

    def public_user(self, user_id: str) -> dict[str, Any] | None:
        user = self.store.get_user(user_id)
        if not user:
            return None
        status = self.account_status(user)
        return {
            "userId": user["user_id"],
            "username": user["username"],
            "displayName": user["display_name"],
            "accountStatus": status,
            "emailMasked": mask_email(user.get("email_normalized")),
            "emailVerified": status == "verified",
            "emailTwoFactorEnabled": bool(user.get("email_two_factor_enabled")),
        }

    @staticmethod
    def account_status(user: dict[str, Any] | None) -> str:
        if not user or not user.get("email_normalized"):
            return "email_upgrade_required"
        if not user.get("email_verified_at"):
            return "email_verification_required"
        return "verified"

    def _user_by_username(self, username: str) -> dict[str, Any] | None:
        """Case-insensitive lookup also covering legacy mixed-case rows."""
        with self.store.connect() as conn:
            row = conn.execute(
                "SELECT user_id, username, display_name, password_hash, email_normalized, "
                "email_verified_at, email_two_factor_enabled, registration_reservation, "
                "account_origin, created_at "
                "FROM users WHERE username = ? COLLATE NOCASE",
                (username,),
            ).fetchone()
        return dict(row) if row else None


def bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, separator, credentials = authorization.partition(" ")
    if not separator or scheme.casefold() != "bearer":
        return None
    # A whitespace-only credential used to reach ``split(...)[1]`` and raise
    # IndexError.  Authentication input is untrusted: malformed headers must
    # follow the ordinary invalid-session path, never turn an auth check (or a
    # successful login that tries to retire an old bearer) into a 500.
    token = credentials.strip()
    return token or None
