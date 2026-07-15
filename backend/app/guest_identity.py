"""Legacy guest-cookie recognition for one-time account migration.

Deployed applications no longer manufacture anonymous learner identities or
persist new unauthenticated work. A syntactically valid cookie that already
arrived with the request is exposed only so historical progress can be previewed,
claimed once, or erased. Test mode deliberately retains the old deterministic
``demo`` principal as an internal fixture; it is never issued to a browser.
"""

from __future__ import annotations

import contextvars
import re
from http.cookies import SimpleCookie
from typing import Any, Awaitable, Callable


GUEST_COOKIE_NAME = "ecg_guest"
_GUEST_ID = re.compile(r"^g_[A-Za-z0-9_-]{24,64}$")
_PUBLIC_PROBE_PATHS = frozenset({"/health", "/livez", "/readyz"})
_guest_learner: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "ecg_guest_learner", default=None
)
_claimable_guest_learner: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "ecg_claimable_guest_learner", default=None
)


def current_guest_learner() -> str | None:
    return _guest_learner.get()


def current_claimable_guest_learner() -> str | None:
    """Return only a guest namespace that arrived with the request.

    A newly generated first-request namespace cannot own durable work yet and
    must not be consumed by a claim. Test mode retains its deterministic demo
    fixture so endpoint tests can exercise the same explicit flow.
    """
    return _claimable_guest_learner.get()


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


def clear_guest_cookie(response: Any, *, app_env: str) -> None:
    """Retire the legacy migration credential after claim or explicit erasure."""

    response.delete_cookie(
        key=GUEST_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=app_env.lower() in {"production", "prod"},
        samesite="lax",
    )


class GuestIdentityMiddleware:
    """Expose only a pre-existing migration cookie; never mint guest state."""

    def __init__(self, app: Callable[..., Awaitable[None]], *, app_env: str):
        self.app = app
        self.test_mode = app_env.lower() == "test"

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
        guest_id = "demo" if self.test_mode else existing
        context_token = _guest_learner.set(guest_id)
        claimable_token = _claimable_guest_learner.set(
            "demo" if self.test_mode else existing
        )

        try:
            await self.app(scope, receive, send)
        finally:
            _claimable_guest_learner.reset(claimable_token)
            _guest_learner.reset(context_token)
