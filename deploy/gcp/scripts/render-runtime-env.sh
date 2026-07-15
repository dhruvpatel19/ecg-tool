#!/usr/bin/env bash
# Fetch only the VM's scoped secrets and render root-only Docker environment.

set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"
require_root
require_command gcloud

CONFIG_FILE="${ECG_DEPLOYMENT_ENV:-/etc/ecg/deployment.env}"
[[ -r "${CONFIG_FILE}" ]] || die "deployment environment is missing: ${CONFIG_FILE}"
# shellcheck disable=SC1090
source "${CONFIG_FILE}"
: "${GCP_PROJECT_ID:?GCP_PROJECT_ID is required}"
: "${ECG_AUTH_SECRET_ID:?ECG_AUTH_SECRET_ID is required}"
: "${ECG_ORIGIN_SECRET_ID:?ECG_ORIGIN_SECRET_ID is required}"
: "${ECG_AUTH_EMAIL_DELIVERY_MODE:?ECG_AUTH_EMAIL_DELIVERY_MODE is required}"
: "${ECG_AUTH_EMAIL_FROM_ADDRESS:?ECG_AUTH_EMAIL_FROM_ADDRESS is required}"
: "${ECG_AUTH_EMAIL_REPLY_TO:?ECG_AUTH_EMAIL_REPLY_TO is required}"
: "${ECG_AUTH_PUBLIC_APP_URL:?ECG_AUTH_PUBLIC_APP_URL is required}"
: "${ECG_AUTH_SMTP_HOST:?ECG_AUTH_SMTP_HOST is required}"
: "${ECG_AUTH_SMTP_PORT:?ECG_AUTH_SMTP_PORT is required}"
: "${ECG_AUTH_SMTP_USERNAME:?ECG_AUTH_SMTP_USERNAME is required}"
: "${ECG_AUTH_SMTP_PASSWORD_SECRET_ID:?ECG_AUTH_SMTP_PASSWORD_SECRET_ID is required}"
: "${ECG_AUTH_SMTP_STARTTLS:?ECG_AUTH_SMTP_STARTTLS is required}"
: "${ECG_AUTH_SMTP_TIMEOUT_SECONDS:?ECG_AUTH_SMTP_TIMEOUT_SECONDS is required}"

fetch_secret() {
  local secret_id="$1" value="" attempt=1 delay=2
  while (( attempt <= 8 )); do
    if value="$(gcloud secrets versions access latest \
      --project "${GCP_PROJECT_ID}" --secret "${secret_id}")"; then
      printf '%s' "${value}"
      return 0
    fi
    if (( attempt == 8 )); then
      return 1
    fi
    log "secret ${secret_id} is not readable yet; retrying in ${delay}s"
    sleep "${delay}"
    attempt=$((attempt + 1))
    delay=$((delay < 15 ? delay * 2 : 30))
  done
}

AUTH_SECRET="$(fetch_secret "${ECG_AUTH_SECRET_ID}")"
ORIGIN_SECRET="$(fetch_secret "${ECG_ORIGIN_SECRET_ID}")"
[[ ${#AUTH_SECRET} -ge 32 ]] || die "auth rate-limit secret must contain at least 32 characters"
[[ ${#ORIGIN_SECRET} -ge 32 ]] || die "origin secret must contain at least 32 characters"
[[ "${AUTH_SECRET}" != *$'\n'* && "${ORIGIN_SECRET}" != *$'\n'* ]] \
  || die "deployment secrets must be single-line values"

[[ "${ECG_AUTH_EMAIL_DELIVERY_MODE}" == "smtp" ]] \
  || die "production authentication email delivery must use smtp"
[[ "${ECG_AUTH_PUBLIC_APP_URL}" =~ ^https://[A-Za-z0-9-]+([.][A-Za-z0-9-]+)+(:443)?$ ]] \
  || die "authentication public app URL must be an HTTPS origin"
[[ "${ECG_AUTH_SMTP_HOST}" =~ ^[A-Za-z0-9.-]+$ && "${ECG_AUTH_SMTP_HOST}" == *.* ]] \
  || die "authentication SMTP hostname is invalid"
[[ "${ECG_AUTH_SMTP_PORT}" == "587" ]] \
  || die "authentication SMTP port must be 587 for explicit STARTTLS"
[[ "${ECG_AUTH_SMTP_STARTTLS}" == "true" ]] \
  || die "authentication SMTP STARTTLS must remain enabled"
[[ "${ECG_AUTH_SMTP_TIMEOUT_SECONDS}" =~ ^[0-9]+$ ]] && (( ECG_AUTH_SMTP_TIMEOUT_SECONDS >= 2 && ECG_AUTH_SMTP_TIMEOUT_SECONDS <= 60 )) \
  || die "authentication SMTP timeout must be an integer from 2 through 60 seconds"
[[ "${ECG_AUTH_EMAIL_FROM_ADDRESS}" == *@* && "${ECG_AUTH_EMAIL_FROM_ADDRESS}" != *$'\n'* && "${ECG_AUTH_EMAIL_FROM_ADDRESS}" != *$'\r'* ]] \
  || die "authentication email From address must be non-empty and single-line"
[[ "${ECG_AUTH_EMAIL_REPLY_TO}" == *@* && "${ECG_AUTH_EMAIL_REPLY_TO}" != *$'\n'* && "${ECG_AUTH_EMAIL_REPLY_TO}" != *$'\r'* ]] \
  || die "authentication email Reply-To address must be non-empty, monitored, and single-line"
[[ -n "${ECG_AUTH_SMTP_USERNAME}" && "${ECG_AUTH_SMTP_USERNAME}" != *$'\n'* && "${ECG_AUTH_SMTP_USERNAME}" != *$'\r'* ]] \
  || die "authentication SMTP username must be non-empty and single-line"

if ! AUTH_SMTP_PASSWORD_VALUE="$(fetch_secret "${ECG_AUTH_SMTP_PASSWORD_SECRET_ID}")"; then
  die "authentication SMTP password secret is unavailable"
fi
[[ -n "${AUTH_SMTP_PASSWORD_VALUE}" && "${AUTH_SMTP_PASSWORD_VALUE}" != *$'\n'* && "${AUTH_SMTP_PASSWORD_VALUE}" != *$'\r'* ]] \
  || die "authentication SMTP password must be a non-empty single-line secret"

LLM_PROVIDER_VALUE="${ECG_LLM_PROVIDER:-mock}"
LLM_API_KEY_VALUE=""
if [[ "${LLM_PROVIDER_VALUE}" != "mock" ]]; then
  : "${ECG_LLM_SECRET_ID:?ECG_LLM_SECRET_ID is required for a non-mock provider}"
  LLM_API_KEY_VALUE="$(fetch_secret "${ECG_LLM_SECRET_ID}")"
  [[ -n "${LLM_API_KEY_VALUE}" && "${LLM_API_KEY_VALUE}" != *$'\n'* ]] \
    || die "LLM secret must be a non-empty single-line value"
fi

AUTH_RETENTION_ACKNOWLEDGED="${ECG_AUTHENTICATED_RETENTION_POLICY_ACKNOWLEDGED:-false}"
AUTH_RETENTION_REFERENCE="${ECG_AUTHENTICATED_RETENTION_POLICY_REFERENCE:-}"
[[ "${AUTH_RETENTION_ACKNOWLEDGED}" == "true" || "${AUTH_RETENTION_ACKNOWLEDGED}" == "false" ]] \
  || die "authenticated retention policy acknowledgement must be true or false"
if [[ "${AUTH_RETENTION_ACKNOWLEDGED}" == "true" ]]; then
  [[ "${AUTH_RETENTION_REFERENCE}" =~ ^[A-Za-z0-9][A-Za-z0-9._:/#@+-]{7,511}$ ]] \
    || die "approved authenticated retention policy reference is missing or invalid"
else
  [[ -z "${AUTH_RETENTION_REFERENCE}" ]] \
    || die "authenticated retention policy reference cannot be set before acknowledgement"
fi

umask 077
mkdir -p /etc/ecg
ENV_NEW="$(mktemp /etc/ecg/backend.env.XXXXXX)"
{
  printf '%s\n' \
    'APP_ENV=production' \
    'ECG_REQUIRE_REAL_DATA=1' \
    'ECG_CASE_LIMIT=0' \
    'ECG_MIN_CORPUS_CASES=22497' \
    'ECG_MIN_PTBXL_CASES=21799' \
    'ECG_MIN_PRACTICE_CASES=5000' \
    'ECG_MIN_CLINICAL_CASES=100' \
    'ECG_REQUIRE_RELEASE_AUDIT=1' \
    'ECG_CORPUS_ROOT=/srv/ecg/corpus' \
    'DATABASE_URL=sqlite:////srv/ecg/state/ecg_learning.db' \
    'ECG_REQUIRE_RECENT_BACKUP=1'
  printf '%s\n' 'ECG_BACKUP_MARKER_PATH=/srv/ecg/ops/last-backup-success'
  printf 'ECG_BACKUP_MAX_AGE_SECONDS=%s\n' "${ECG_BACKUP_MAX_AGE_SECONDS:-50400}"
  printf 'ECG_MIN_STATE_FREE_BYTES=%s\n' "${ECG_MIN_STATE_FREE_BYTES:-2147483648}"
  printf 'ECG_AUTHENTICATED_RETENTION_POLICY_ACKNOWLEDGED=%s\n' "${AUTH_RETENTION_ACKNOWLEDGED}"
  printf 'ECG_AUTHENTICATED_RETENTION_POLICY_REFERENCE=%s\n' "${AUTH_RETENTION_REFERENCE}"
  printf 'AUTH_RATE_LIMIT_SECRET=%s\n' "${AUTH_SECRET}"
  printf 'ECG_ORIGIN_SHARED_SECRET=%s\n' "${ORIGIN_SECRET}"
  printf 'AUTH_EMAIL_DELIVERY_MODE=%s\n' "${ECG_AUTH_EMAIL_DELIVERY_MODE}"
  printf 'AUTH_EMAIL_FROM_ADDRESS=%s\n' "${ECG_AUTH_EMAIL_FROM_ADDRESS}"
  printf 'AUTH_EMAIL_REPLY_TO=%s\n' "${ECG_AUTH_EMAIL_REPLY_TO}"
  printf 'AUTH_PUBLIC_APP_URL=%s\n' "${ECG_AUTH_PUBLIC_APP_URL}"
  printf 'AUTH_SMTP_HOST=%s\n' "${ECG_AUTH_SMTP_HOST}"
  printf 'AUTH_SMTP_PORT=%s\n' "${ECG_AUTH_SMTP_PORT}"
  printf 'AUTH_SMTP_USERNAME=%s\n' "${ECG_AUTH_SMTP_USERNAME}"
  printf 'AUTH_SMTP_PASSWORD=%s\n' "${AUTH_SMTP_PASSWORD_VALUE}"
  printf 'AUTH_SMTP_STARTTLS=%s\n' "${ECG_AUTH_SMTP_STARTTLS}"
  printf 'AUTH_SMTP_TIMEOUT_SECONDS=%s\n' "${ECG_AUTH_SMTP_TIMEOUT_SECONDS}"
  printf 'LLM_PROVIDER=%s\n' "${LLM_PROVIDER_VALUE}"
  printf 'LLM_REQUIRED=%s\n' "${ECG_LLM_REQUIRED:-0}"
  printf 'LLM_API_KEY=%s\n' "${LLM_API_KEY_VALUE}"
  printf 'LLM_MODEL=%s\n' "${ECG_LLM_MODEL:-}"
  printf 'LLM_BASE_URL=%s\n' "${ECG_LLM_BASE_URL:-}"
  printf 'LLM_MAX_COMPLETION_TOKENS=%s\n' "${ECG_LLM_MAX_COMPLETION_TOKENS:-1200}"
  printf 'LLM_REQUEST_TIMEOUT_SECONDS=%s\n' "${ECG_LLM_REQUEST_TIMEOUT_SECONDS:-30}"
  printf 'LLM_MAX_REQUEST_BYTES=%s\n' "${ECG_LLM_MAX_REQUEST_BYTES:-131072}"
  printf 'LLM_MAX_RESPONSE_BYTES=%s\n' "${ECG_LLM_MAX_RESPONSE_BYTES:-131072}"
  printf 'LLM_AUTHENTICATED_DAILY_LIMIT=%s\n' "${ECG_LLM_AUTHENTICATED_DAILY_LIMIT:-60}"
  printf 'LLM_GUEST_DAILY_LIMIT=%s\n' "${ECG_LLM_GUEST_DAILY_LIMIT:-15}"
  printf 'LLM_IP_HOURLY_LIMIT=%s\n' "${ECG_LLM_IP_HOURLY_LIMIT:-240}"
  printf 'LLM_GLOBAL_DAILY_LIMIT=%s\n' "${ECG_LLM_GLOBAL_DAILY_LIMIT:-500}"
} >"${ENV_NEW}"
chmod 0600 "${ENV_NEW}"
mv -f "${ENV_NEW}" /etc/ecg/backend.env
unset AUTH_SECRET ORIGIN_SECRET AUTH_SMTP_PASSWORD_VALUE LLM_API_KEY_VALUE AUTH_RETENTION_REFERENCE
log "rendered root-only backend environment"
