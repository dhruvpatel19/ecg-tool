from __future__ import annotations

import pytest

from app.main import _runtime_index_build_enabled, app


@pytest.mark.parametrize("app_env", ["production", "prod", " PRODUCTION "])
def test_runtime_index_build_is_never_mounted_for_hosted_environments(
    app_env: str,
) -> None:
    assert _runtime_index_build_enabled(app_env) is False


def test_runtime_index_build_remains_an_explicit_local_development_tool() -> None:
    assert _runtime_index_build_enabled("development") is True
    assert any(
        getattr(route, "path", None) == "/ingest/build-index"
        for route in app.routes
    )
