"""Operator-only authentication-email configuration diagnostic.

Run inside the backend container with::

    python -m app.auth_mailer_cli

The command performs no network request and prints no addresses, hostnames,
credentials, URLs, message bodies, or provider responses. It reports only the
transport mode, a readiness boolean, and safe environment-variable identifiers.
"""

from __future__ import annotations

import json
from typing import Any

from .auth_mailer import build_auth_mailer
from .config import Settings


def safe_auth_email_diagnostic(settings: Any) -> dict[str, object]:
    mailer = build_auth_mailer(
        app_env=str(getattr(settings, "app_env", "production")),
        mode=str(getattr(settings, "auth_email_delivery_mode", "disabled")),
        smtp_host=getattr(settings, "auth_smtp_host", None),
        smtp_port=int(getattr(settings, "auth_smtp_port", 587)),
        smtp_username=getattr(settings, "auth_smtp_username", None),
        smtp_password=getattr(settings, "auth_smtp_password", None),
        from_address=getattr(settings, "auth_email_from_address", None),
        reply_to=getattr(settings, "auth_email_reply_to", None),
        public_app_url=getattr(settings, "auth_public_app_url", None),
        smtp_starttls=bool(getattr(settings, "auth_smtp_starttls", True)),
        smtp_timeout_seconds=int(
            getattr(settings, "auth_smtp_timeout_seconds", 10)
        ),
    )
    errors = list(getattr(mailer, "readiness_errors", ()))
    if not mailer.ready and not errors:
        errors = ["AUTH_EMAIL_DELIVERY_MODE"]
    return {
        "configurationErrors": errors,
        "mode": str(mailer.mode),
        "ready": bool(mailer.ready),
    }


def main() -> int:
    report = safe_auth_email_diagnostic(Settings())
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["ready"] else 1


if __name__ == "__main__":  # pragma: no cover - exercised as an operator command
    raise SystemExit(main())
