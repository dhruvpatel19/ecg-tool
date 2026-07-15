from __future__ import annotations

import smtplib
import time
from urllib.parse import parse_qs, urlsplit

import pytest

from app import auth_mailer as mailer_module
from app.auth_mailer import (
    AuthEmail,
    AuthMailerUnavailable,
    BoundedAuthTaskDispatcher,
    DisabledAuthMailer,
    MemoryAuthMailer,
    SecurityEmail,
    SmtpAuthMailer,
    build_auth_mailer,
)


def _smtp(
    *,
    app_env: str = "production",
    starttls: bool = True,
    url: str = "https://trace.example.edu",
    host: str = "smtp.example.edu",
    port: int = 587,
    username: str | None = "trace-mailer",
    password: str | None = "test-secret",
    reply_to: str | None = "TRACE support <support@example.edu>",
):
    return build_auth_mailer(
        app_env=app_env,
        mode="smtp",
        smtp_host=host,
        smtp_port=port,
        smtp_username=username,
        smtp_password=password,
        from_address="TRACE <no-reply@example.edu>",
        reply_to=reply_to,
        public_app_url=url,
        smtp_starttls=starttls,
        smtp_timeout_seconds=8,
    )


def test_mailer_modes_and_production_transport_readiness_fail_closed() -> None:
    assert isinstance(
        build_auth_mailer(app_env="test", mode="memory"), MemoryAuthMailer
    )
    assert isinstance(
        build_auth_mailer(app_env="production", mode="memory"), DisabledAuthMailer
    )

    ready = _smtp()
    assert isinstance(ready, SmtpAuthMailer)
    assert ready.ready is True

    no_tls = _smtp(starttls=False)
    assert no_tls.ready is False
    assert "AUTH_SMTP_STARTTLS" in no_tls.readiness_errors

    http_links = _smtp(url="http://trace.example.edu")
    assert http_links.ready is False
    assert "AUTH_PUBLIC_APP_URL_HTTPS" in http_links.readiness_errors

    for invalid_origin in (
        "https://trace.example.edu/unexpected-path",
        "https://trace.example.edu?token=unsafe",
        "https://localhost",
        "https://trace.example.edu:8443",
    ):
        origin = _smtp(url=invalid_origin)
        assert origin.ready is False
        assert "AUTH_PUBLIC_APP_URL" in origin.readiness_errors

    unauthenticated = _smtp(username=None, password=None)
    assert unauthenticated.ready is False
    assert (
        "AUTH_SMTP_USERNAME/AUTH_SMTP_PASSWORD_REQUIRED"
        in unauthenticated.readiness_errors
    )

    implicit_tls = _smtp(port=465)
    assert implicit_tls.ready is False
    assert "AUTH_SMTP_PORT_STARTTLS" in implicit_tls.readiness_errors

    malformed_host = _smtp(host="https://smtp.example.edu")
    assert malformed_host.ready is False
    assert "AUTH_SMTP_HOST" in malformed_host.readiness_errors

    unsafe_reply_to = _smtp(reply_to="support@example.edu\r\nBcc: attacker@example.edu")
    assert unsafe_reply_to.ready is False
    assert "AUTH_EMAIL_REPLY_TO" in unsafe_reply_to.readiness_errors

    missing_reply_to = _smtp(reply_to=None)
    assert missing_reply_to.ready is False
    assert "AUTH_EMAIL_REPLY_TO_REQUIRED" in missing_reply_to.readiness_errors

    missing = build_auth_mailer(app_env="production", mode="smtp")
    assert missing.ready is False


def test_smtp_builds_trace_text_and_html_without_logging_or_header_injection(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeSmtp:
        def __init__(self, host, port, timeout):
            captured.update(host=host, port=port, timeout=timeout)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def ehlo(self):
            captured["ehlo"] = int(captured.get("ehlo", 0)) + 1

        def starttls(self, *, context):
            captured["tls"] = context is not None

        def login(self, username, password):
            captured["login"] = (username, password)

        def send_message(self, message):
            captured["message"] = message

    monkeypatch.setattr(mailer_module.smtplib, "SMTP", FakeSmtp)
    mailer = _smtp(reply_to="TRACE support <support@example.edu>")
    secret = "plain-secret-never-persisted"
    mailer.send(
        AuthEmail(
            purpose="email_verification",
            recipient="student@example.edu",
            challenge_id="ach_public",
            secret=secret,
            expires_at="2026-07-15T00:00:00+00:00",
        )
    )

    message = captured["message"]
    assert message["Subject"] == "Verify your TRACE account"
    assert message["To"] == "student@example.edu"
    assert message["Reply-To"] == "TRACE support <support@example.edu>"
    assert message["Date"]
    assert message["Message-ID"].endswith("@example.edu>")
    assert message["Auto-Submitted"] == "auto-generated"
    assert message["X-Auto-Response-Suppress"] == "All"
    assert captured["tls"] is True
    assert captured["login"] == ("trace-mailer", "test-secret")
    rendered = message.get_body(preferencelist=("plain",)).get_content()
    assert "https://trace.example.edu/verify-email?" in rendered
    assert "challengeId=ach_public" in rendered
    assert secret in rendered
    assert "July 15, 2026 at 12:00 AM UTC" in rendered

    with pytest.raises(AuthMailerUnavailable, match="destination"):
        mailer.send(
            AuthEmail(
                purpose="email_verification",
                recipient="student@example.edu\r\nBcc: attacker@example.edu",
                challenge_id="ach_public",
                secret=secret,
                expires_at="2026-07-15T00:00:00+00:00",
            )
        )


@pytest.mark.parametrize(
    ("purpose", "path", "secret"),
    [
        ("email_verification", "/verify-email", "482913"),
        ("password_reset", "/reset-password", "reset-secret"),
        ("email_change", "/account/email-change", "change-secret"),
    ],
)
def test_link_secrets_live_only_in_url_fragment(
    purpose: str,
    path: str,
    secret: str,
) -> None:
    mailer = _smtp()
    _subject, plain, _rich = mailer._content(
        AuthEmail(
            purpose=purpose,
            recipient="student@example.edu",
            challenge_id="ach_public",
            secret=secret,
            expires_at="2026-07-15T00:00:00+00:00",
        )
    )
    link = next(
        word for word in plain.split() if word.startswith("https://trace.example.edu/")
    )
    parsed = urlsplit(link)

    assert parsed.path == path
    assert parse_qs(parsed.query) == {"challengeId": ["ach_public"]}
    assert "token" not in parse_qs(parsed.query)
    assert secret not in parsed.query
    assert parse_qs(parsed.fragment) == {"token": [secret]}
    # The request target sent to the origin excludes the fragment and secret.
    request_url = parsed._replace(fragment="").geturl()
    assert secret not in request_url
    if purpose == "email_verification":
        # The accessible copy/paste code remains available independently of
        # the secure link for clients that do not support fragment handoff.
        assert f"verification code is {secret}" in plain


@pytest.mark.parametrize(
    "purpose",
    [
        "password_changed",
        "password_reset_complete",
        "two_factor_enabled",
        "two_factor_disabled",
        "email_changed",
        "account_deleted",
    ],
)
def test_security_notification_templates_are_secret_free_and_actionable(
    purpose: str,
) -> None:
    mailer = _smtp()
    subject, plain, rich = mailer._content(
        SecurityEmail(
            purpose=purpose,
            recipient="student@example.edu",
            occurred_at="2026-07-15T00:00:00+00:00",
        )
    )
    rendered = f"{subject}\n{plain}\n{rich}".casefold()
    assert "july 15, 2026 at 12:00 am utc" in rendered
    assert "if you did not" in rendered
    assert "secure your email account" in rendered
    assert "token=" not in rendered
    assert "challengeid" not in rendered
    assert "one-time" not in rendered


def test_existing_account_registration_resolution_is_owner_only_code_not_link() -> None:
    mailer = _smtp()
    _subject, plain, rich = mailer._content(
        AuthEmail(
            purpose="registration_resolution",
            recipient="student@example.edu",
            challenge_id="ach_resolution",
            secret="482913",
            expires_at="2026-07-15T00:00:00+00:00",
        )
    )
    rendered = f"{plain}\n{rich}".casefold()
    assert "already connected to trace" in rendered
    assert "482913" in rendered
    assert "sign-in or password recovery" in rendered
    assert "http://" not in rendered
    assert "https://" not in rendered
    assert "challengeid" not in rendered


def test_smtp_timeout_is_wrapped_without_provider_response(monkeypatch) -> None:
    class TimeoutSmtp:
        def __init__(self, *_args, **_kwargs):
            raise TimeoutError("provider detail must not escape")

    monkeypatch.setattr(mailer_module.smtplib, "SMTP", TimeoutSmtp)
    with pytest.raises(AuthMailerUnavailable) as raised:
        _smtp().send(
            AuthEmail(
                purpose="password_reset",
                recipient="student@example.edu",
                challenge_id="ach_timeout",
                secret="secret",
                expires_at="2026-07-15T00:00:00+00:00",
            )
        )
    assert "provider detail" not in str(raised.value)


def test_background_delivery_failure_emits_only_aggregate_safe_telemetry(caplog) -> None:
    dispatcher = BoundedAuthTaskDispatcher(workers=1, capacity=2)
    secret = "never-log-this-reset-token"

    def fail() -> None:
        raise RuntimeError(secret)

    assert dispatcher.submit(fail) is True
    deadline = time.monotonic() + 2
    while dispatcher.telemetry()["completed"] < 1 and time.monotonic() < deadline:
        time.sleep(0.01)

    telemetry = dispatcher.telemetry()
    assert telemetry["submitted"] == 1
    assert telemetry["completed"] == 1
    assert telemetry["failed"] == 1
    assert "auth_email_background_task_failed" in caplog.text
    assert secret not in caplog.text
