#!/usr/bin/env bash
# Add generated secret versions after Terraform creates empty secret containers.

set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"
[[ $# -eq 3 ]] || die "usage: $0 GCP_PROJECT AUTH_SECRET_ID ORIGIN_SECRET_ID"
PROJECT_ID="$1"
AUTH_SECRET_ID="$2"
ORIGIN_SECRET_ID="$3"
for command in gcloud openssl; do require_command "${command}"; done

add_generated() {
  local secret_id="$1"
  openssl rand -hex 32 \
    | gcloud secrets versions add "${secret_id}" --project "${PROJECT_ID}" --data-file=- >/dev/null
  log "added a generated version to ${secret_id}"
}

add_generated "${AUTH_SECRET_ID}"
add_generated "${ORIGIN_SECRET_ID}"
log "retrieve the origin value once for Vercel with: gcloud secrets versions access latest --secret ${ORIGIN_SECRET_ID} --project ${PROJECT_ID}"
