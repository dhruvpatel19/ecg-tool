from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ops import (
    ReadinessProbeCoordinator,
    build_ops_router,
)


class FakeRetentionCleanup:
    def __init__(self) -> None:
        self.healthy = True
        self.calls = 0

    def maybe_run(self) -> None:
        self.calls += 1


def test_readiness_caches_success_and_failure_then_recovers_after_ttl() -> None:
    now = [100.0]
    states = [True, False, True]
    reports = 0
    cleanup = FakeRetentionCleanup()

    def reporter(*_args):
        nonlocal reports
        value = states[reports]
        reports += 1
        return {"ok": value, "checks": {"private": "never returned"}}

    probe = ReadinessProbeCoordinator(
        object(),
        object(),
        object(),
        object(),
        cleanup,
        cache_ttl_seconds=15,
        clock=lambda: now[0],
        reporter=reporter,
    )

    assert probe.ready() is True
    now[0] = 114.999
    assert probe.ready() is True
    assert reports == cleanup.calls == 1

    now[0] = 115.0
    assert probe.ready() is False
    now[0] = 129.999
    assert probe.ready() is False
    assert reports == cleanup.calls == 2

    now[0] = 130.0
    assert probe.ready() is True
    assert reports == cleanup.calls == 3


def test_readiness_evaluation_is_single_flight_under_concurrency() -> None:
    cleanup = FakeRetentionCleanup()
    reporter_started = threading.Event()
    release_reporter = threading.Event()
    reports = 0

    def reporter(*_args):
        nonlocal reports
        reports += 1
        reporter_started.set()
        assert release_reporter.wait(timeout=2)
        return {"ok": True}

    probe = ReadinessProbeCoordinator(
        object(),
        object(),
        object(),
        object(),
        cleanup,
        cache_ttl_seconds=15,
        reporter=reporter,
    )
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(probe.ready) for _ in range(8)]
        assert reporter_started.wait(timeout=2)
        release_reporter.set()
        assert [future.result(timeout=2) for future in futures] == [True] * 8

    assert reports == cleanup.calls == 1


def test_readyz_returns_only_boolean_and_recovers_after_cached_failure(
    monkeypatch,
) -> None:
    reports = 0
    now = [100.0]

    def reporter(*_args):
        nonlocal reports
        reports += 1
        if reports == 1:
            raise RuntimeError("private /srv/ecg/state path")
        return {"ok": True, "checks": {"path": "private /srv/ecg/state path"}}

    # Use a short test TTL while exercising the real route response contract.
    original_init = ReadinessProbeCoordinator.__init__

    def short_init(self, *args, **kwargs):
        kwargs["cache_ttl_seconds"] = 15
        kwargs["clock"] = lambda: now[0]
        kwargs["reporter"] = reporter
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(ReadinessProbeCoordinator, "__init__", short_init)
    settings = SimpleNamespace(retention_cleanup_enabled=False)
    app = FastAPI()
    app.include_router(build_ops_router(settings, object(), object(), object()))

    with TestClient(app) as client:
        failed = client.get("/readyz")
        assert failed.status_code == 503
        assert failed.json() == {"ok": False}
        assert "/srv/ecg/state" not in failed.text

        cached = client.get("/readyz")
        assert cached.status_code == 503
        assert reports == 1

        now[0] = 115.0
        recovered = client.get("/readyz")
        assert recovered.status_code == 200
        assert recovered.json() == {"ok": True}
        assert "/srv/ecg/state" not in recovered.text
