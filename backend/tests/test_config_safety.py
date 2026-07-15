from __future__ import annotations

import pytest

from app.config import Settings


def test_unknown_app_environment_fails_closed() -> None:
    with pytest.raises(ValueError, match="APP_ENV must be one of"):
        Settings(app_env="prodution")


@pytest.mark.parametrize("app_env", ["development", "test", "production", "prod"])
def test_reviewed_app_environments_remain_available(app_env: str) -> None:
    assert Settings(app_env=app_env).app_env == app_env


def test_app_environment_is_normalized_before_security_checks() -> None:
    settings = Settings(
        app_env="  PRODUCTION  ",
        auth_rate_limit_secret="a" * 32,
        origin_shared_secret="b" * 32,
    )

    assert settings.app_env == "production"
    assert settings.registration_rate_limit_secret == "a" * 32
    assert settings.origin_guard_secret == "b" * 32
