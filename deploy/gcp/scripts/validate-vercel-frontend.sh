#!/usr/bin/env bash
# Read-only security-header check for the deployed Vercel student frontend.

set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"
[[ $# -eq 1 ]] || die "usage: $0 https://student.example.org"
BASE_URL="${1%/}"
[[ "${BASE_URL}" == https://* ]] || die "frontend validation requires HTTPS"
require_command curl

LOGIN_HEADERS="$(curl --disable --silent --show-error --fail --proto '=https' --tlsv1.2 \
  --max-time 20 --dump-header - --output /dev/null "${BASE_URL}/login" | tr -d '\r')"
printf '%s\n' "${LOGIN_HEADERS}" | grep -Eqi '^content-security-policy:.*script-src.*nonce-' \
  || die "login response lacks a nonce-based Content-Security-Policy"
printf '%s\n' "${LOGIN_HEADERS}" \
  | grep -Eqi "^content-security-policy:.*frame-ancestors[[:space:]]+'none'([[:space:]]*;|[[:space:]]*$)" \
  || die "login response does not deny framing"
printf '%s\n' "${LOGIN_HEADERS}" | grep -Eqi '^x-frame-options:[[:space:]]*DENY' \
  || die "login response lacks X-Frame-Options DENY"
printf '%s\n' "${LOGIN_HEADERS}" | grep -Eqi '^x-content-type-options:[[:space:]]*nosniff' \
  || die "login response lacks nosniff"
printf '%s\n' "${LOGIN_HEADERS}" | grep -Eqi '^strict-transport-security:' \
  || die "login response lacks HSTS"
if printf '%s\n' "${LOGIN_HEADERS}" | grep -Eqi '^content-security-policy:.*unsafe-eval'; then
  die "production Content-Security-Policy permits unsafe-eval"
fi

FOUNDATION_RESPONSE="$(curl --disable --silent --show-error --proto '=https' --tlsv1.2 \
  --max-time 20 --dump-header - --output /dev/null --write-out '%{http_code}' \
  "${BASE_URL}/foundations/config.js" | tr -d '\r')"
FOUNDATION_STATUS="${FOUNDATION_RESPONSE##*$'\n'}"
FOUNDATION_HEADERS="${FOUNDATION_RESPONSE%$'\n'*}"
[[ "${FOUNDATION_STATUS}" == "401" ]] \
  || die "unauthenticated foundation asset did not require a learner session"
printf '%s\n' "${FOUNDATION_HEADERS}" \
  | grep -Eqi "^content-security-policy:.*frame-ancestors[[:space:]]+'self'([[:space:]]*;|[[:space:]]*$)" \
  || die "foundation asset is not limited to same-origin framing"
printf '%s\n' "${FOUNDATION_HEADERS}" | grep -Eqi '^x-frame-options:[[:space:]]*SAMEORIGIN' \
  || die "foundation asset lacks SAMEORIGIN framing policy"
printf '%s\n' "${FOUNDATION_HEADERS}" | grep -Eqi '^cache-control:.*no-store' \
  || die "foundation authentication response is not no-store"
printf '%s\n' "${FOUNDATION_HEADERS}" | grep -Eqi '^cache-control:.*private' \
  || die "foundation authentication response is not private"
printf '%s\n' "${FOUNDATION_HEADERS}" | grep -Eqi '^vary:.*cookie' \
  || die "foundation authentication response does not vary on Cookie"
log "Vercel nonce CSP and security-header checks passed"
