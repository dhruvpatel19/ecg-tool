#!/usr/bin/env bash
# Explicit post-release smoke test. This performs one remote tutor call and
# consumes a guest quota reservation; it is intentionally not part of /readyz.

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
for command in curl jq; do require_command "${command}"; done

RESPONSE="$(printf 'X-ECG-Origin-Key: %s\n' "${ORIGIN_SECRET}" \
  | curl --silent --show-error --fail --proto '=https' --tlsv1.2 --max-time 75 \
  --header @- \
  -H 'Content-Type: application/json' \
  --data '{"mode":"freeform","learnerMessage":"Give me one short Socratic question that helps a learner reflect on diagnostic uncertainty."}' \
  "${BASE_URL}/tutor/chat")"
unset ORIGIN_SECRET
printf '%s' "${RESPONSE}" | jq -e \
  '.remoteProviderConfigured == true and .provider == "openai-compatible" and .remoteCall.status == "success" and .schemaError == null' >/dev/null \
  || die "tutor did not prove a live openai-compatible provider call"
log "live tutor provider smoke test passed"
