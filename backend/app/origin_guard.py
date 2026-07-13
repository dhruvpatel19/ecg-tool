"""Shared-secret guard for a backend published behind the Vercel proxy.

The secret is never sent to browser JavaScript. Vercel's route handler adds it
server-side, and this middleware rejects direct calls to learner endpoints when
the deployment configures ``ECG_ORIGIN_SHARED_SECRET``. Liveness/readiness stay
open so Caddy and Google Cloud can gate traffic without credentials.
"""

from __future__ import annotations

import hmac
import ipaddress
import json
from collections.abc import Awaitable, Callable
from typing import Any


_PUBLIC_PROBE_PATHS = frozenset({"/health", "/livez", "/readyz"})


class OriginKeyMiddleware:
    def __init__(self, app: Callable[..., Awaitable[Any]], shared_secret: str | None = None):
        self.app = app
        self.shared_secret = (shared_secret or "").encode("utf-8")

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if (
            scope.get("type") != "http"
            or not self.shared_secret
            or scope.get("path") in _PUBLIC_PROBE_PATHS
        ):
            await self.app(scope, receive, send)
            return

        supplied = b""
        for name, value in scope.get("headers", []):
            if name.lower() == b"x-ecg-origin-key":
                supplied = value
                break
        if hmac.compare_digest(supplied, self.shared_secret):
            scope.setdefault("state", {})["origin_key_verified"] = True
            await self.app(scope, receive, send)
            return

        body = json.dumps(
            {"detail": {"code": "origin_key_required", "message": "Request origin is not allowed."}}
        ).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                    (b"cache-control", b"no-store"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


def trusted_registration_ip(request: Any) -> str:
    """Use Vercel's canonical client IP only after origin-key verification."""

    socket_host = request.client.host if request.client else "unknown"
    if not getattr(request.state, "origin_key_verified", False):
        return socket_host
    supplied = request.headers.get("x-ecg-client-ip", "").strip()
    try:
        return ipaddress.ip_address(supplied).compressed
    except ValueError:
        return socket_host
