from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dependency installed for app runtime
    load_dotenv = None


if load_dotenv is not None:
    load_dotenv()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes"}:
        return True
    if normalized in {"0", "false", "no"}:
        return False
    raise ValueError(f"{name} must be a boolean (true/false or 1/0)")


def _env_int(name: str, default: int, minimum: int, maximum: int | None = None) -> int:
    value = int(os.getenv(name, str(default)))
    if value < minimum or (maximum is not None and value > maximum):
        upper = f" and at most {maximum}" if maximum is not None else ""
        raise ValueError(f"{name} must be at least {minimum}{upper}")
    return value


@dataclass(frozen=True)
class Settings:
    corpus_root: str | None = os.getenv("ECG_CORPUS_ROOT") or None
    case_limit: int = int(os.getenv("ECG_CASE_LIMIT", "0"))
    # Learner-facing deployments fail closed when the curated PTB corpus is
    # unavailable. Tests that exercise fixture mechanics must opt out explicitly.
    require_real_data: bool = os.getenv("ECG_REQUIRE_REAL_DATA", "1").lower() in {"1", "true", "yes"}
    # Production sets these to the complete audited corpus contract. Local
    # tests retain small defaults so purpose-built fixture stores remain useful.
    min_corpus_cases: int = _env_int("ECG_MIN_CORPUS_CASES", 1, 1)
    min_ptbxl_cases: int = _env_int("ECG_MIN_PTBXL_CASES", 1, 1)
    min_practice_cases: int = _env_int("ECG_MIN_PRACTICE_CASES", 1, 1)
    min_clinical_cases: int = _env_int("ECG_MIN_CLINICAL_CASES", 1, 1)
    require_release_audit: bool = _env_bool("ECG_REQUIRE_RELEASE_AUDIT", False)
    ptbxl_data_root: str | None = os.getenv("PTBXL_DATA_ROOT") or None
    ptbxl_plus_data_root: str | None = os.getenv("PTBXL_PLUS_DATA_ROOT") or None
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./ecg_learning.db")
    llm_provider: str = os.getenv("LLM_PROVIDER", "mock")
    llm_api_key: str | None = os.getenv("LLM_API_KEY") or None
    llm_model: str | None = os.getenv("LLM_MODEL") or None
    llm_base_url: str | None = os.getenv("LLM_BASE_URL") or None
    llm_required: bool = _env_bool("LLM_REQUIRED", False)
    llm_max_completion_tokens: int = _env_int("LLM_MAX_COMPLETION_TOKENS", 1200, 128, 4096)
    llm_request_timeout_seconds: int = _env_int("LLM_REQUEST_TIMEOUT_SECONDS", 30, 5, 60)
    llm_max_request_bytes: int = _env_int("LLM_MAX_REQUEST_BYTES", 131072, 32768, 524288)
    llm_max_response_bytes: int = _env_int("LLM_MAX_RESPONSE_BYTES", 131072, 16384, 1048576)
    llm_authenticated_daily_limit: int = _env_int("LLM_AUTHENTICATED_DAILY_LIMIT", 60, 1)
    llm_guest_daily_limit: int = _env_int("LLM_GUEST_DAILY_LIMIT", 15, 1)
    llm_ip_hourly_limit: int = _env_int("LLM_IP_HOURLY_LIMIT", 240, 1)
    llm_global_daily_limit: int = _env_int("LLM_GLOBAL_DAILY_LIMIT", 500, 1)
    require_recent_backup: bool = _env_bool("ECG_REQUIRE_RECENT_BACKUP", False)
    backup_max_age_seconds: int = _env_int("ECG_BACKUP_MAX_AGE_SECONDS", 50400, 3600, 604800)
    backup_marker_path: str | None = os.getenv("ECG_BACKUP_MARKER_PATH") or None
    min_state_free_bytes: int = _env_int(
        "ECG_MIN_STATE_FREE_BYTES",
        2147483648,
        268435456,
        53687091200,
    )
    app_env: str = os.getenv("APP_ENV", "development")
    auth_rate_limit_secret: str | None = os.getenv("AUTH_RATE_LIMIT_SECRET") or None
    # Set by the production Vercel proxy and checked by the backend. It stays
    # optional for local development and tests.
    origin_shared_secret: str | None = os.getenv("ECG_ORIGIN_SHARED_SECRET") or None

    @property
    def using_mock_llm(self) -> bool:
        return self.llm_provider.lower() in {"", "mock"}

    @property
    def registration_rate_limit_secret(self) -> str:
        if self.auth_rate_limit_secret:
            return self.auth_rate_limit_secret
        if self.app_env.lower() in {"production", "prod"}:
            raise ValueError("AUTH_RATE_LIMIT_SECRET is required in production")
        # Stable only for local/test databases. Deployments must supply a
        # private secret so low-entropy IP addresses cannot be enumerated.
        return "ecg-tool-local-registration-rate-limit-v1"

    @property
    def origin_guard_secret(self) -> str | None:
        secret = self.origin_shared_secret
        if secret and (len(secret) < 32 or any(ord(char) < 32 or ord(char) == 127 for char in secret)):
            raise ValueError("ECG_ORIGIN_SHARED_SECRET must be a single-line value of at least 32 characters")
        if not secret and self.app_env.lower() in {"production", "prod"}:
            raise ValueError("ECG_ORIGIN_SHARED_SECRET is required in production")
        return secret

    @property
    def sqlite_path(self) -> Path:
        if self.database_url.startswith("sqlite:///"):
            raw = self.database_url.removeprefix("sqlite:///")
            if raw == ":memory:":
                return Path(":memory:")
            path = Path(raw)
            # Anchor relative paths to the project root so learner state does not
            # split across files depending on the launch directory (V1 audit fix).
            if not path.is_absolute():
                project_root = Path(__file__).resolve().parents[2]
                path = project_root / path
            return path
        raise ValueError("Only sqlite:/// DATABASE_URL values are supported in V1")

    @property
    def learner_backup_marker_path(self) -> Path:
        if self.backup_marker_path:
            return Path(self.backup_marker_path)
        return Path(f"{self.sqlite_path}.last-backup-success")


def get_settings() -> Settings:
    return Settings()
