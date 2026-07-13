"""Private per-browser identity for unauthenticated learning previews.

The guest cookie is an unguessable, limited-scope bearer identity. It is not a
student account, but it must be protected like a session token because it owns
guest drafts and attempts. Its only purpose is to keep two unrelated guest
browsers from sharing tutor threads, attempts, or active mode sessions. Test
mode deliberately retains the historical
``demo`` principal so deterministic unit fixtures remain isolated from this
browser lifecycle.
"""

from __future__ import annotations

import contextvars
import re
import secrets
from http.cookies import SimpleCookie
from typing import Any, Awaitable, Callable


GUEST_COOKIE_NAME = "ecg_guest"
GUEST_DAYS = 30
_GUEST_ID = re.compile(r"^g_[A-Za-z0-9_-]{24,64}$")
_PUBLIC_PROBE_PATHS = frozenset({"/health", "/livez", "/readyz"})
_guest_learner: contextvars.ContextVar[str] = contextvars.ContextVar(
    "ecg_guest_learner", default="demo"
)
_claimable_guest_learner: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "ecg_claimable_guest_learner", default=None
)


def current_guest_learner() -> str:
    return _guest_learner.get()


def current_claimable_guest_learner() -> str | None:
    """Return only a guest namespace that arrived with the request.

    A newly generated first-request namespace cannot own durable work yet and
    must not be consumed by a claim. Test mode retains its deterministic demo
    fixture so endpoint tests can exercise the same explicit flow.
    """
    return _claimable_guest_learner.get()


def _new_guest_id() -> str:
    return f"g_{secrets.token_urlsafe(24)}"


def _cookie_value(scope: dict[str, Any]) -> str | None:
    raw = next(
        (value for key, value in scope.get("headers", []) if key.lower() == b"cookie"),
        None,
    )
    if not raw:
        return None
    jar = SimpleCookie()
    try:
        jar.load(raw.decode("latin-1"))
    except Exception:
        return None
    morsel = jar.get(GUEST_COOKIE_NAME)
    value = morsel.value if morsel else None
    return value if value and _GUEST_ID.fullmatch(value) else None


def _set_cookie_header(guest_id: str, *, secure: bool) -> bytes:
    jar = SimpleCookie()
    jar[GUEST_COOKIE_NAME] = guest_id
    morsel = jar[GUEST_COOKIE_NAME]
    morsel["path"] = "/"
    morsel["max-age"] = str(GUEST_DAYS * 24 * 60 * 60)
    morsel["httponly"] = True
    morsel["samesite"] = "Lax"
    if secure:
        morsel["secure"] = True
    return morsel.OutputString().encode("latin-1")


def rotate_guest_cookie(response: Any, *, app_env: str) -> str:
    """Start a fresh, empty guest namespace after an explicit claim succeeds."""
    guest_id = _new_guest_id()
    response.set_cookie(
        key=GUEST_COOKIE_NAME,
        value=guest_id,
        max_age=GUEST_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=app_env.lower() in {"production", "prod"},
        samesite="lax",
        path="/",
    )
    return guest_id


class GuestIdentityMiddleware:
    """Assign one opaque guest namespace before any stateful route executes."""

    def __init__(self, app: Callable[..., Awaitable[None]], *, app_env: str):
        self.app = app
        self.test_mode = app_env.lower() == "test"
        self.secure = app_env.lower() in {"production", "prod"}

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        # Monitoring probes do not own learner state. Avoid manufacturing a
        # durable guest identity (and a Set-Cookie response) for every probe.
        if scope.get("path") in _PUBLIC_PROBE_PATHS:
            await self.app(scope, receive, send)
            return

        existing = _cookie_value(scope)
        guest_id = "demo" if self.test_mode else (existing or _new_guest_id())
        context_token = _guest_learner.set(guest_id)
        claimable_token = _claimable_guest_learner.set(
            "demo" if self.test_mode else existing
        )

        async def send_with_guest_cookie(message: dict[str, Any]) -> None:
            if message.get("type") == "http.response.start" and not self.test_mode and not existing:
                headers = list(message.get("headers", []))
                headers.append((b"set-cookie", _set_cookie_header(guest_id, secure=self.secure)))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_guest_cookie)
        finally:
            _claimable_guest_learner.reset(claimable_token)
            _guest_learner.reset(context_token)
