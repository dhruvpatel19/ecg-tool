"""Phase 4 auth: users, password hashing, and session tokens.

Stdlib only (PBKDF2-HMAC-SHA256 passwords + hashed, revocable opaque sessions).
Learner data is keyed by user id; unauthenticated previews use a separate
per-browser guest identity.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import re
import secrets
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from .guest_progress import GuestProgressService
from .storage import LearningStore

SESSION_DAYS = 30
SESSION_COOKIE_NAME = "ecg_session"
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
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
RESERVED_USERNAMES = {"demo", "guest", "admin"}
_DUMMY_PASSWORD_HASH = (
    "pbkdf2_sha256$600000$00000000000000000000000000000000$"
    "1d426911dbe3390a224210a21a7d938eb44360e0f1ebd4f84a3658566112283b"
)


def hash_password(password: str, salt: str | None = None, iterations: int = PASSWORD_ITERATIONS) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations)
    return f"pbkdf2_sha256${iterations}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt, hexhash = stored.split("$")
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iterations))
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(digest.hex(), hexhash)


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
    ):
        self.store = store
        self.guest_progress = guest_progress
        self._auth_rate_limit_secret = registration_rate_limit_secret.encode("utf-8")

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
        if client_ip:
            normalized_ip = self._normalized_client_ip(client_ip)
            pair_key_hash = self._rate_limit_digest(
                "ecg-registration-v1", "pair", normalized_ip, username
            )
            ip_key_hash = self._rate_limit_digest(
                "ecg-registration-v1", "ip", normalized_ip
            )
            global_key_hash = self._rate_limit_digest(
                "ecg-registration-v1", "global"
            )
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
        if not _USERNAME_RE.fullmatch(username) or username in RESERVED_USERNAMES:
            raise AuthError(
                "Username must be 3-32 characters using only letters, digits, _, . or -, and cannot be reserved.",
                field="username",
                code="invalid_username",
            )
        if len(password or "") < 10:
            raise AuthError(
                "Password must be at least 10 characters.",
                field="password",
                code="password_too_short",
            )
        if len(password) > 256:
            raise AuthError(
                "Password must be 256 characters or fewer.",
                field="password",
                code="password_too_long",
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
                    guest_id=guest_id,
                )
            else:
                self.store.create_user(user_id, username, safe_display_name, password_hash)
        except sqlite3.IntegrityError as exc:
            # Close the check/insert race without exposing database details.
            raise AuthError(
                "That username is already taken.", field="username", code="username_taken"
            ) from exc
        if not claim_guest_progress:
            self.store.ensure_profile(user_id, safe_display_name)
        session = self._issue(user_id, username, safe_display_name)
        if guest_claim:
            session["guestClaim"] = guest_claim
        return session

    def login(
        self,
        username: str,
        password: str,
        *,
        claim_guest_progress: bool = False,
        guest_id: str | None = None,
        client_ip: str | None = None,
    ) -> dict[str, Any]:
        normalized = (username or "").strip().casefold()
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
        user = self._user_by_username(normalized)
        # Keep the slow-hash work comparable for missing and existing users so
        # the generic response does not become an account-enumeration oracle.
        password_valid = verify_password(
            password or "", user["password_hash"] if user else _DUMMY_PASSWORD_HASH
        )
        if not user or not password_valid:
            # Deliberately do not reveal whether the identifier exists.
            raise AuthError("Invalid username or password.", code="invalid")
        # A verified learner's pair bucket is cleared after the slow work, but
        # aggregate IP/global reservations remain so login churn stays bounded.
        self.store.clear_login_pair_attempts(pair_key_hash)
        guest_claim: dict[str, Any] | None = None
        if claim_guest_progress:
            if not self.guest_progress or not guest_id:
                raise AuthError(
                    "Guest progress is unavailable for this request.",
                    code="guest_claim_unavailable",
                )
            guest_claim = self.guest_progress.claim(guest_id, user["user_id"])
        session = self._issue(user["user_id"], user["username"], user["display_name"])
        if guest_claim:
            session["guestClaim"] = guest_claim
        return session

    def logout(self, token: str | None) -> None:
        if token:
            self.store.delete_session(token)

    def logout_all(self, user_id: str) -> int:
        return self.store.delete_user_sessions(user_id)

    def change_password(
        self, user_id: str, current_password: str, new_password: str
    ) -> dict[str, Any]:
        user = self.store.get_user_auth(user_id)
        if not user or not verify_password(current_password or "", user["password_hash"]):
            raise AuthError("Current password is incorrect.", field="currentPassword", code="invalid_current_password")
        if len(new_password or "") < 10:
            raise AuthError(
                "New password must be at least 10 characters.",
                field="newPassword",
                code="password_too_short",
            )
        if len(new_password) > 256:
            raise AuthError(
                "New password must be 256 characters or fewer.",
                field="newPassword",
                code="password_too_long",
            )
        if verify_password(new_password, user["password_hash"]):
            raise AuthError(
                "New password must be different from the current password.",
                field="newPassword",
                code="password_unchanged",
            )
        self.store.update_user_password(user_id, hash_password(new_password))
        self.store.delete_user_sessions(user_id)
        return self._issue(user_id, user["username"], user["display_name"])

    def resolve(self, token: str | None) -> str | None:
        """Return the user id for a valid bearer token, else None (guest)."""
        return self.store.get_session_user(token) if token else None

    def me(self, token: str | None) -> dict[str, Any] | None:
        user_id = self.resolve(token)
        return self.public_user(user_id) if user_id else None

    def public_user(self, user_id: str) -> dict[str, Any] | None:
        user = self.store.get_user(user_id)
        if not user:
            return None
        return {
            "userId": user["user_id"],
            "username": user["username"],
            "displayName": user["display_name"],
        }

    def _issue(self, user_id: str, username: str, display_name: str) -> dict[str, Any]:
        token = secrets.token_urlsafe(32)
        expires = (datetime.now(UTC) + timedelta(days=SESSION_DAYS)).isoformat()
        self.store.create_session(token, user_id, expires)
        return {
            "token": token,
            "user": {"userId": user_id, "username": username, "displayName": display_name},
        }

    def _user_by_username(self, username: str) -> dict[str, Any] | None:
        """Case-insensitive lookup also covering legacy mixed-case rows."""
        with self.store.connect() as conn:
            row = conn.execute(
                "SELECT user_id, username, display_name, password_hash, created_at "
                "FROM users WHERE username = ? COLLATE NOCASE",
                (username,),
            ).fetchone()
        return dict(row) if row else None


def bearer_token(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(None, 1)[1].strip()
    return None
