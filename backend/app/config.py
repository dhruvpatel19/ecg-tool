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
    require_real_data: bool = _env_bool("ECG_REQUIRE_REAL_DATA", True)
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
    # Guest cookies live for 30 days; matching that explicit browser lifecycle
    # is the conservative default for anonymous records that cannot be recovered
    # after the cookie expires. Each pass is intentionally owner-bounded.
    retention_cleanup_enabled: bool = _env_bool("ECG_RETENTION_CLEANUP_ENABLED", True)
    guest_inactivity_days: int = _env_int("ECG_GUEST_INACTIVITY_DAYS", 30, 1, 3650)
    unverified_account_expiry_days: int = _env_int(
        "ECG_UNVERIFIED_ACCOUNT_EXPIRY_DAYS", 7, 1, 90
    )
    retention_cleanup_batch_size: int = _env_int(
        "ECG_RETENTION_CLEANUP_BATCH_SIZE", 100, 1, 1000
    )
    retention_cleanup_interval_seconds: int = _env_int(
        "ECG_RETENTION_CLEANUP_INTERVAL_SECONDS", 21600, 60, 604800
    )
    retention_cleanup_lease_seconds: int = _env_int(
        "ECG_RETENTION_CLEANUP_LEASE_SECONDS", 300, 30, 3600
    )
    # This acknowledges an external product/legal decision; it does not select
    # a retention duration and never enables automatic account deletion.
    authenticated_retention_policy_acknowledged: bool = _env_bool(
        "ECG_AUTHENTICATED_RETENTION_POLICY_ACKNOWLEDGED", False
    )
    authenticated_retention_policy_reference: str | None = (
        os.getenv("ECG_AUTHENTICATED_RETENTION_POLICY_REFERENCE") or None
    )
    app_env: str = os.getenv("APP_ENV", "development")
    # Authentication email is provider-neutral. ``memory`` is an ephemeral
    # development/test outbox only; production treats it as unavailable. A
    # reviewed external adapter may be injected when these operator-facing
    # delivery values are configured.
    auth_email_delivery_mode: str = os.getenv("AUTH_EMAIL_DELIVERY_MODE", "memory")
    auth_email_from_address: str | None = os.getenv("AUTH_EMAIL_FROM_ADDRESS") or None
    auth_email_reply_to: str | None = os.getenv("AUTH_EMAIL_REPLY_TO") or None
    auth_public_app_url: str | None = os.getenv("AUTH_PUBLIC_APP_URL") or None
    auth_smtp_host: str | None = os.getenv("AUTH_SMTP_HOST") or None
    auth_smtp_port: int = _env_int("AUTH_SMTP_PORT", 587, 1, 65535)
    auth_smtp_username: str | None = os.getenv("AUTH_SMTP_USERNAME") or None
    auth_smtp_password: str | None = os.getenv("AUTH_SMTP_PASSWORD") or None
    auth_smtp_starttls: bool = _env_bool("AUTH_SMTP_STARTTLS", True)
    auth_smtp_timeout_seconds: int = _env_int("AUTH_SMTP_TIMEOUT_SECONDS", 10, 2, 60)
    auth_rate_limit_secret: str | None = os.getenv("AUTH_RATE_LIMIT_SECRET") or None
    # Set by the production Vercel proxy and checked by the backend. It stays
    # optional for local development and tests.
    origin_shared_secret: str | None = os.getenv("ECG_ORIGIN_SHARED_SECRET") or None

    def __post_init__(self) -> None:
        # A misspelled deployment environment must not silently disable secure
        # cookies, origin enforcement, and production secret requirements.
        normalized_env = self.app_env.strip().lower()
        if normalized_env not in {
            "development",
            "test",
            "production",
            "prod",
        }:
            raise ValueError(
                "APP_ENV must be one of development, test, production, or prod"
            )
        object.__setattr__(self, "app_env", normalized_env)
        normalized_mailer = self.auth_email_delivery_mode.strip().lower()
        if normalized_mailer not in {"disabled", "memory", "smtp"}:
            raise ValueError(
                "AUTH_EMAIL_DELIVERY_MODE must be disabled, memory, or smtp"
            )
        object.__setattr__(self, "auth_email_delivery_mode", normalized_mailer)

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
    def adaptive_plan_context_secret(self) -> str:
        """Private root key for signed, owner-bound mastery-plan references."""

        secret = self.registration_rate_limit_secret
        if self.app_env.lower() in {"production", "prod"} and (
            len(secret) < 32
            or any(ord(char) < 32 or ord(char) == 127 for char in secret)
        ):
            raise ValueError(
                "AUTH_RATE_LIMIT_SECRET must be a single-line value of at least 32 "
                "characters because it also roots adaptive-plan context signatures"
            )
        return secret

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
