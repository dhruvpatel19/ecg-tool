from __future__ import annotations

from types import SimpleNamespace

from app.auth_mailer_cli import safe_auth_email_diagnostic


def _production_settings(**overrides):
    values = {
        "app_env": "production",
        "auth_email_delivery_mode": "smtp",
        "auth_email_from_address": "TRACE <no-reply@example.edu>",
        "auth_email_reply_to": "TRACE support <support@example.edu>",
        "auth_public_app_url": "https://trace.example.edu",
        "auth_smtp_host": "smtp.example.edu",
        "auth_smtp_port": 587,
        "auth_smtp_username": "trace-mailer",
        "auth_smtp_password": "never-print-this-secret",
        "auth_smtp_starttls": True,
        "auth_smtp_timeout_seconds": 10,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_operator_diagnostic_reports_only_safe_configuration_identifiers() -> None:
    secret = "never-print-this-secret"
    settings = _production_settings(
        auth_smtp_password=secret,
        auth_email_reply_to=None,
        auth_public_app_url="https://localhost/private?token=unsafe",
    )

    report = safe_auth_email_diagnostic(settings)

    assert report == {
        "configurationErrors": [
            "AUTH_EMAIL_REPLY_TO_REQUIRED",
            "AUTH_PUBLIC_APP_URL",
        ],
        "mode": "smtp",
        "ready": False,
    }
    rendered = repr(report)
    assert secret not in rendered
    assert "localhost" not in rendered
    assert "support@" not in rendered


def test_operator_diagnostic_accepts_complete_production_transport() -> None:
    assert safe_auth_email_diagnostic(_production_settings()) == {
        "configurationErrors": [],
        "mode": "smtp",
        "ready": True,
    }
