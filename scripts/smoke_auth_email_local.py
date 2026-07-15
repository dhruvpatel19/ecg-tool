#!/usr/bin/env python3
"""Exercise every authentication-email purpose against an in-process SMTP sink.

This is deliberately local-only: it opens a loopback listener on an ephemeral
port, uses no provider credentials, persists nothing, and prints no recipient,
token, challenge, timestamp, header value, or message body.
"""

from __future__ import annotations

import json
import socketserver
import sys
from email import policy
from email.parser import BytesParser
from pathlib import Path
from threading import Lock, Thread


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.auth_mailer import (  # noqa: E402
    AuthEmail,
    SecurityEmail,
    SmtpAuthMailer,
    build_auth_mailer,
)


CHALLENGE_PURPOSES = (
    "email_verification",
    "registration_resolution",
    "password_reset",
    "two_factor_login",
    "two_factor_enable",
    "two_factor_disable",
    "email_change_current_factor",
    "email_change",
)
SECURITY_PURPOSES = (
    "password_changed",
    "password_reset_complete",
    "two_factor_enabled",
    "two_factor_disabled",
    "email_changed",
    "account_deleted",
)


class _CaptureServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, server_address):
        super().__init__(server_address, _SmtpHandler)
        self.messages: list[bytes] = []
        self.messages_lock = Lock()


class _SmtpHandler(socketserver.StreamRequestHandler):
    def _reply(self, value: bytes) -> None:
        self.wfile.write(value + b"\r\n")
        self.wfile.flush()

    def handle(self) -> None:
        self._reply(b"220 localhost ESMTP TRACE local smoke")
        while True:
            raw = self.rfile.readline(65537)
            if not raw or len(raw) > 65536:
                return
            command = raw.rstrip(b"\r\n").split(b" ", 1)[0].upper()
            if command == b"EHLO":
                self.wfile.write(b"250-localhost\r\n250 8BITMIME\r\n")
                self.wfile.flush()
            elif command in {b"HELO", b"MAIL", b"RCPT", b"RSET", b"NOOP"}:
                self._reply(b"250 OK")
            elif command == b"DATA":
                self._reply(b"354 End data with <CR><LF>.<CR><LF>")
                chunks: list[bytes] = []
                while True:
                    line = self.rfile.readline(65537)
                    if not line or len(line) > 65536:
                        return
                    if line == b".\r\n":
                        break
                    if line.startswith(b".."):
                        line = line[1:]
                    chunks.append(line)
                with self.server.messages_lock:  # type: ignore[attr-defined]
                    self.server.messages.append(b"".join(chunks))  # type: ignore[attr-defined]
                self._reply(b"250 Accepted")
            elif command == b"QUIT":
                self._reply(b"221 Bye")
                return
            else:
                self._reply(b"502 Command not implemented")


def run_smoke() -> dict[str, object]:
    expected_purposes = {*CHALLENGE_PURPOSES, *SECURITY_PURPOSES}
    if expected_purposes != set(SmtpAuthMailer._SUBJECTS):
        raise RuntimeError("local SMTP smoke purpose inventory is incomplete")
    with _CaptureServer(("127.0.0.1", 0)) as server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        port = int(server.server_address[1])
        mailer = build_auth_mailer(
            app_env="test",
            mode="smtp",
            smtp_host="localhost",
            smtp_port=port,
            from_address="TRACE <no-reply@example.test>",
            reply_to="TRACE support <support@example.test>",
            public_app_url="http://localhost:3000",
            smtp_starttls=False,
            smtp_timeout_seconds=5,
        )
        if not mailer.ready:
            raise RuntimeError("local SMTP transport did not pass test readiness")

        for index, purpose in enumerate(CHALLENGE_PURPOSES, start=1):
            mailer.send(
                AuthEmail(
                    purpose=purpose,
                    recipient="student@example.test",
                    challenge_id=f"local-smoke-{index}",
                    secret=f"local-secret-{index}",
                    expires_at="2030-01-01T00:00:00+00:00",
                )
            )
        for purpose in SECURITY_PURPOSES:
            mailer.send(
                SecurityEmail(
                    purpose=purpose,
                    recipient="student@example.test",
                    occurred_at="2030-01-01T00:00:00+00:00",
                )
            )

        server.shutdown()
        worker.join(timeout=5)
        with server.messages_lock:
            raw_messages = tuple(server.messages)

    expected_count = len(CHALLENGE_PURPOSES) + len(SECURITY_PURPOSES)
    if len(raw_messages) != expected_count:
        raise RuntimeError("local SMTP sink captured an unexpected message count")
    parsed_messages = tuple(
        BytesParser(policy=policy.default).parsebytes(value) for value in raw_messages
    )
    for message in parsed_messages:
        if not message.is_multipart():
            raise RuntimeError("authentication email is missing its HTML alternative")
        for header in (
            "Subject",
            "From",
            "To",
            "Reply-To",
            "Date",
            "Message-ID",
            "Auto-Submitted",
            "X-Auto-Response-Suppress",
        ):
            if not message.get(header):
                raise RuntimeError("authentication email is missing a required header")
        if message["Auto-Submitted"] != "auto-generated":
            raise RuntimeError("authentication email auto-response header is invalid")

    resolution_message = parsed_messages[
        CHALLENGE_PURPOSES.index("registration_resolution")
    ]
    resolution_plain = resolution_message.get_body(
        preferencelist=("plain",)
    ).get_content()
    if (
        "already connected to TRACE" not in resolution_plain
        or "sign-in or password recovery" not in resolution_plain
        or "http://" in resolution_plain
        or "https://" in resolution_plain
        or "challengeId" in resolution_plain
    ):
        raise RuntimeError("registration-resolution mail is not owner-only code copy")

    return {
        "messagesCaptured": expected_count,
        "purposes": [*CHALLENGE_PURPOSES, *SECURITY_PURPOSES],
        "ready": True,
    }


def main() -> int:
    print(json.dumps(run_smoke(), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
