#!/usr/bin/env bash
# Explicit post-release smoke test. This performs one authenticated remote
# tutor call; it is intentionally not part of /readyz.

set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"
[[ $# -eq 1 ]] || die "usage: [origin-secret-on-stdin] $0 https://api.example.org"
BASE_URL="${1%/}"
[[ "${BASE_URL}" == https://* ]] || die "live tutor validation requires HTTPS"
ORIGIN_SECRET="${ECG_ORIGIN_SHARED_SECRET:-}"
if [[ -z "${ORIGIN_SECRET}" && ! -t 0 ]]; then
  IFS= read -r ORIGIN_SECRET || [[ -n "${ORIGIN_SECRET}" ]]
fi
[[ ${#ORIGIN_SECRET} -ge 32 && "${ORIGIN_SECRET}" != *$'\n'* ]] \
  || die "origin secret must be a single-line value of at least 32 characters"
SESSION_COOKIE=""
if [[ -r /dev/fd/3 ]]; then
  IFS= read -r SESSION_COOKIE <&3 || [[ -n "${SESSION_COOKIE}" ]]
elif [[ -r /dev/tty ]]; then
  printf 'Verified disposable account Cookie header: ' >/dev/tty
  IFS= read -r -s SESSION_COOKIE </dev/tty || [[ -n "${SESSION_COOKIE}" ]]
  printf '\n' >/dev/tty
else
  die "an authenticated production session is required on file descriptor 3 or a TTY"
fi
[[ "${SESSION_COOKIE}" == __Host-ecg_session=* \
  && "${SESSION_COOKIE}" != *$'\n'* \
  && "${SESSION_COOKIE}" != *$'\r'* ]] \
  || die "the supplied Cookie header is not an authenticated production session"
trap 'unset ORIGIN_SECRET SESSION_COOKIE' EXIT
for command in curl jq; do require_command "${command}"; done

RESPONSE="$(printf 'X-ECG-Origin-Key: %s\nCookie: %s\n' \
  "${ORIGIN_SECRET}" "${SESSION_COOKIE}" \
  | curl --disable --silent --show-error --fail --proto '=https' --tlsv1.2 --max-time 75 \
  --header @- \
  -H 'Content-Type: application/json' \
  --data '{"mode":"freeform","learnerMessage":"Give me one short Socratic question that helps a learner reflect on diagnostic uncertainty."}' \
  "${BASE_URL}/tutor/chat")"
unset ORIGIN_SECRET SESSION_COOKIE
trap - EXIT
printf '%s' "${RESPONSE}" | jq -e \
  '.remoteProviderConfigured == true
    and .provider == "openai-compatible"
    and .remoteCall.status == "success"
    and .schemaError == null
    and ((.tutorMessage | type) == "string")
    and (.tutorMessage | test("\\S"))' >/dev/null \
  || die "tutor did not prove a live openai-compatible provider call"
log "live tutor provider smoke test passed"
