#!/usr/bin/env bash
# Read-only post-deployment checks. Set ECG_ORIGIN_SHARED_SECRET for protected APIs.

set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"
[[ $# -eq 1 ]] || die "usage: $0 https://api.example.org"
BASE_URL="${1%/}"
[[ "${BASE_URL}" == https://* ]] || die "validation requires an HTTPS URL"
require_command curl

CURL=(curl --disable --silent --show-error --fail --proto '=https' --tlsv1.2 --max-time 20)
"${CURL[@]}" "${BASE_URL}/livez" | grep -q '"ok":true' || die "liveness failed"
"${CURL[@]}" "${BASE_URL}/readyz" | grep -q '"ok":true' || die "readiness failed"

NO_KEY_STATUS="$(curl --disable --silent --show-error --output /dev/null --write-out '%{http_code}' \
  --proto '=https' --tlsv1.2 --max-time 20 "${BASE_URL}/dataset/status")"
[[ "${NO_KEY_STATUS}" == "403" ]] || die "protected API accepted a request without an origin key"
WRONG_KEY_STATUS="$(curl --disable --silent --show-error --output /dev/null --write-out '%{http_code}' \
  --proto '=https' --tlsv1.2 --max-time 20 \
  -H 'X-ECG-Origin-Key: deployment-validation-intentionally-wrong-key' \
  "${BASE_URL}/dataset/status")"
[[ "${WRONG_KEY_STATUS}" == "403" ]] || die "protected API accepted an incorrect origin key"

ORIGIN_SECRET="${ECG_ORIGIN_SHARED_SECRET:-}"
if [[ -z "${ORIGIN_SECRET}" && ! -t 0 ]]; then
  IFS= read -r ORIGIN_SECRET || [[ -n "${ORIGIN_SECRET}" ]]
fi
if [[ -n "${ORIGIN_SECRET}" ]]; then
  STATUS_BODY="$(mktemp)"
  STATUS_HEADERS="$(mktemp)"
  trap 'rm -f "${STATUS_BODY}" "${STATUS_HEADERS}"' EXIT
  STATUS_CODE="$(printf 'X-ECG-Origin-Key: %s\n' "${ORIGIN_SECRET}" \
    | curl --disable --silent --show-error --output "${STATUS_BODY}" --write-out '%{http_code}' \
      --dump-header "${STATUS_HEADERS}" --proto '=https' --tlsv1.2 --max-time 20 --header @- \
      "${BASE_URL}/dataset/status")"
  [[ "${STATUS_CODE}" == "401" ]] \
    || die "origin-only dataset request did not require a learner session (status ${STATUS_CODE})"
  grep -Eq '"code"[[:space:]]*:[[:space:]]*"authentication_required"' "${STATUS_BODY}" \
    || die "dataset authentication response did not identify the learner-session boundary"
  grep -Eqi '^cache-control:.*no-store' "${STATUS_HEADERS}" \
    || die "dataset authentication response is cacheable"
  log "origin key accepted; dataset metadata remains learner-authenticated"
  rm -f "${STATUS_BODY}" "${STATUS_HEADERS}"
  trap - EXIT
else
  log "origin key not supplied; protected dataset check skipped"
fi
unset ORIGIN_SECRET

log "HTTPS, liveness, readiness, and origin-guard rejection checks passed"
