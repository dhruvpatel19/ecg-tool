from __future__ import annotations

import json
import re
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.config import Settings
from app.llm import OpenAICompatibleProvider, ProviderOutput, TutorService
from app.main import app
from app.storage import LearningStore


def _reserve(store: LearningStore, *, now: datetime, learner: str = "g_private", ip: str = "203.0.113.8"):
    return store.consume_remote_tutor_quota(
        learner_id=learner,
        client_ip=ip,
        hash_secret="x" * 32,
        authenticated=learner.startswith("u_"),
        authenticated_daily_limit=3,
        guest_daily_limit=2,
        ip_hourly_limit=10,
        global_daily_limit=20,
        now=now,
    )


def test_remote_tutor_quota_is_atomic_durable_and_privacy_preserving(tmp_path) -> None:
    store = LearningStore(tmp_path / "learner.db")
    instant = datetime(2026, 7, 13, 15, 20, tzinfo=UTC)

    with ThreadPoolExecutor(max_workers=8) as pool:
        decisions = list(pool.map(lambda _index: _reserve(store, now=instant), range(8)))

    assert sum(bool(item["allowed"]) for item in decisions) == 2
    assert {item["reason"] for item in decisions if not item["allowed"]} == {"learner_daily"}
    assert _reserve(store, now=instant + timedelta(days=1))["allowed"] is True

    raw = (tmp_path / "learner.db").read_bytes()
    assert b"g_private" not in raw
    assert b"203.0.113.8" not in raw


def test_quota_exhaustion_keeps_the_grounded_tutor_available() -> None:
    class ExplodingProvider:
        def generate(self, *_args, **_kwargs) -> str:
            raise AssertionError("quota fallback must not call the remote provider")

    service = TutorService(Settings(llm_provider="openai-compatible", llm_api_key="unused"))
    service.provider = ExplodingProvider()
    result = service.converse(
        "Help me inspect this tracing systematically.",
        None,
        {"learnerId": "g_private"},
        [],
        remote_reservation=lambda: {
            "allowed": False,
            "reason": "learner_daily",
            "resetAt": "2026-07-14T00:00:00+00:00",
            "remaining": {"learnerDaily": 0, "ipHourly": 9, "globalDaily": 19},
            "limits": {"learnerDaily": 2, "ipHourly": 10, "globalDaily": 20},
        },
    )

    assert result["provider"] == "grounded-fallback"
    assert result["remoteUsage"]["status"] == "quota_fallback"
    assert result["tutorMessage"]


def test_curated_answer_does_not_consume_remote_quota() -> None:
    service = TutorService(Settings(llm_provider="openai-compatible", llm_api_key="unused"))

    def should_not_reserve() -> dict:
        raise AssertionError("curated questions must not consume remote quota")

    result = service.converse(
        "How do I distinguish wide-complex tachycardia from VT?",
        None,
        {"learnerId": "g_private"},
        [],
        remote_reservation=should_not_reserve,
    )

    assert result["provider"] == "grounded-fallback"
    assert "remoteUsage" not in result


def test_openai_payload_caps_output_and_uses_hashed_safety_identifier(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size: int) -> bytes:
            return json.dumps(
                {"choices": [{"message": {"content": '{"tutorMessage":"Grounded."}'}}]}
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("app.llm.urllib.request.urlopen", fake_urlopen)
    settings = Settings(
        llm_provider="openai-compatible",
        llm_api_key="not-a-real-key",
        llm_base_url="https://api.openai.com/v1",
    )
    provider = OpenAICompatibleProvider(settings)

    provider.generate(
        [{"role": "user", "content": "Explain the P-QRS relationship."}],
        {"_safetyIdentifier": "ecg_0123456789abcdef", "casePacket": None},
    )

    body = captured["body"]
    assert body["max_completion_tokens"] == settings.llm_max_completion_tokens
    assert body["safety_identifier"] == "ecg_0123456789abcdef"
    assert "_safetyIdentifier" not in json.dumps(body["messages"])
    assert captured["timeout"] == settings.llm_request_timeout_seconds


def test_remote_tutor_payload_never_contains_raw_learner_identifier(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size: int) -> bytes:
            return json.dumps(
                {"choices": [{"message": {"content": '{"tutorMessage":"Grounded."}'}}]}
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        del timeout
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr("app.llm.urllib.request.urlopen", fake_urlopen)
    service = TutorService(
        Settings(
            llm_provider="openai-compatible",
            llm_api_key="not-a-real-key",
            llm_base_url="https://api.openai.com/v1",
            auth_rate_limit_secret="s" * 32,
        )
    )
    raw_learner_id = "u_private-learner-identifier"

    service.converse(
        "Help me inspect this tracing systematically.",
        None,
        {"learnerId": raw_learner_id, "weakObjectives": ["atrial_fibrillation"]},
        [],
        remote_reservation=lambda: {"allowed": True},
    )

    body = captured["body"]
    serialized = json.dumps(body)
    assert raw_learner_id not in serialized
    assert "learnerId" not in serialized
    assert re.fullmatch(r"ecg_[0-9a-f]{40}", body["safety_identifier"])


def test_oversized_remote_prompt_is_rejected_before_network_use(monkeypatch) -> None:
    def unexpected_urlopen(*_args, **_kwargs):
        raise AssertionError("oversized provider payload must not reach the network")

    monkeypatch.setattr("app.llm.urllib.request.urlopen", unexpected_urlopen)
    settings = Settings(
        llm_provider="openai-compatible",
        llm_api_key="not-a-real-key",
        llm_max_request_bytes=32 * 1024,
    )

    raw = OpenAICompatibleProvider(settings).generate(
        [{"role": "user", "content": "x" * (40 * 1024)}], {}
    )

    assert isinstance(raw, ProviderOutput)
    assert raw.provider_status == "request_rejected"
    assert "was not sent" in raw


def test_provider_http_error_body_is_bounded_and_not_returned_to_learner(monkeypatch) -> None:
    captured: dict[str, int] = {}

    class ErrorBody:
        def read(self, size: int = -1) -> bytes:
            captured["readSize"] = size
            return b"INTERNAL_PROVIDER_SECRET=" + (b"z" * max(1, size))

        def close(self) -> None:
            return None

    error = urllib.error.HTTPError(
        "https://api.openai.com/v1/chat/completions",
        500,
        "provider failed",
        {"x-request-id": "req_safe-123"},
        ErrorBody(),
    )

    def raise_http_error(*_args, **_kwargs):
        raise error

    monkeypatch.setattr("app.llm.urllib.request.urlopen", raise_http_error)
    settings = Settings(llm_provider="openai-compatible", llm_api_key="not-a-real-key")
    raw = OpenAICompatibleProvider(settings).generate(
        [{"role": "user", "content": "Teach rate."}], {}
    )

    assert raw.provider_status == "failed"
    assert captured["readSize"] == settings.llm_max_response_bytes + 1
    assert "INTERNAL_PROVIDER_SECRET" not in raw
    assert "temporarily unavailable" in raw


def test_failed_remote_call_is_reported_as_grounded_fallback() -> None:
    class FailedProvider:
        def generate(self, *_args, **_kwargs) -> str:
            return ProviderOutput(
                json.dumps(
                    {
                        "tutorMessage": "Grounded fallback.",
                        "feedback": "Use packet evidence.",
                        "viewerActions": [],
                        "uncertaintyWarnings": [],
                        "suggestedNextStep": "Continue.",
                    }
                ),
                "failed",
            )

    service = TutorService(Settings(llm_provider="openai-compatible", llm_api_key="unused"))
    service.provider = FailedProvider()
    result = service.converse(
        "Help me inspect this tracing systematically.",
        None,
        {"learnerId": "g_private"},
        [],
        remote_reservation=lambda: {"allowed": True},
    )

    assert result["provider"] == "grounded-fallback"
    assert result["remoteCall"] == {"attempted": True, "status": "failed"}


def test_tutor_http_inputs_are_bounded_before_persistence_or_remote_use() -> None:
    client = TestClient(app)

    assert client.post("/tutor/message", json={"message": "x" * 4_001}).status_code == 422
    assert client.post(
        "/tutor/message",
        json={"message": "Question", "viewerState": {"blob": "x" * (32 * 1024)}},
    ).status_code == 422
    assert client.post(
        "/tutor/foundations", json={"learnerMessage": "x" * 4_001}
    ).status_code == 422
