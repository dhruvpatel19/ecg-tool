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

LOGIN_HEADERS="$(curl --silent --show-error --fail --proto '=https' --tlsv1.2 \
  --max-time 20 --dump-header - --output /dev/null "${BASE_URL}/login" | tr -d '\r')"
printf '%s\n' "${LOGIN_HEADERS}" | grep -Eqi '^content-security-policy:.*script-src.*nonce-' \
  || die "login response lacks a nonce-based Content-Security-Policy"
printf '%s\n' "${LOGIN_HEADERS}" | grep -Eqi '^content-security-policy:.*frame-ancestors .none.' \
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

FOUNDATION_HEADERS="$(curl --silent --show-error --fail --proto '=https' --tlsv1.2 \
  --max-time 20 --dump-header - --output /dev/null "${BASE_URL}/foundations/config.js" | tr -d '\r')"
printf '%s\n' "${FOUNDATION_HEADERS}" | grep -Eqi '^content-security-policy:.*frame-ancestors .self.' \
  || die "foundation asset is not limited to same-origin framing"
printf '%s\n' "${FOUNDATION_HEADERS}" | grep -Eqi '^x-frame-options:[[:space:]]*SAMEORIGIN' \
  || die "foundation asset lacks SAMEORIGIN framing policy"
log "Vercel nonce CSP and security-header checks passed"
