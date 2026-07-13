#!/usr/bin/env bash
# Roll the single backend instance to an immutable image digest with rollback.

set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"
require_root
[[ $# -eq 1 ]] || die "usage: $0 REGION-docker.pkg.dev/PROJECT/REPO/IMAGE@sha256:DIGEST"
IMAGE="$1"
[[ "${IMAGE}" =~ ^[a-z0-9.-]+-docker\.pkg\.dev/[A-Za-z0-9._/-]+@sha256:[a-f0-9]{64}$ ]] \
  || die "backend image must be an Artifact Registry image pinned by sha256 digest"
for command in docker systemctl curl flock; do require_command "${command}"; done
[[ -L /srv/ecg-data/corpus/current ]] || die "no verified corpus release is active"

METADATA_IMAGE="$(curl --fail --silent --show-error --retry 8 --retry-all-errors \
  --retry-delay 2 --connect-timeout 5 --max-time 30 \
  --header 'Metadata-Flavor: Google' \
  'http://metadata.google.internal/computeMetadata/v1/instance/attributes/ecg-backend-image')"
[[ "${METADATA_IMAGE}" == "${IMAGE}" ]] \
  || die "Terraform metadata does not declare this image; update/apply backend_image first"

mkdir -p /etc/ecg
IMAGE_ENV=/etc/ecg/image.env
PREVIOUS=""
if [[ -r "${IMAGE_ENV}" ]]; then
  # shellcheck disable=SC1090
  source "${IMAGE_ENV}"
  PREVIOUS="${ECG_BACKEND_IMAGE:-}"
fi
[[ "${PREVIOUS}" =~ ^[a-z0-9.-]+-docker\.pkg\.dev/[A-Za-z0-9._/-]+@sha256:[a-f0-9]{64}$ ]] \
  || die "the currently installed backend image is not an immutable rollback candidate"

CONFIG_FILE="${ECG_DEPLOYMENT_ENV:-/etc/ecg/deployment.env}"
[[ -r "${CONFIG_FILE}" ]] || die "deployment environment is missing: ${CONFIG_FILE}"
# shellcheck disable=SC1090
source "${CONFIG_FILE}"
: "${ECG_STATE_DB:?ECG_STATE_DB is required}"
: "${ECG_OPS_ROOT:?ECG_OPS_ROOT is required}"
validate_ops_root "${ECG_OPS_ROOT}"
[[ -f "${ECG_STATE_DB}" && ! -L "${ECG_STATE_DB}" ]] \
  || die "learner database must be a regular non-symlink file"

write_image_env() {
  local selected_image="$1" suffix="$2"
  printf 'ECG_BACKEND_IMAGE=%q\n' "${selected_image}" >"${IMAGE_ENV}.${suffix}"
  chmod 0600 "${IMAGE_ENV}.${suffix}"
  mv -f "${IMAGE_ENV}.${suffix}" "${IMAGE_ENV}"
}

retry 8 2 docker pull "${IMAGE}"

# Exclude the scheduled backup/restore jobs for the complete cutover. Stopping
# the sole writer before the online-backup API runs closes the last-write race:
# no acknowledged learner change can land after the rollback point.
exec 8>"${ECG_OPS_ROOT}/maintenance.lock"
flock -n 8 || die "learner database is already in backup/maintenance"
systemctl is-active --quiet ecg-backend.service \
  || die "current backend is not active; recover it before attempting a release"
log "quiescing the single writer for the mandatory pre-release backup"
systemctl stop ecg-backend.service
if ! ECG_MAINTENANCE_LOCK_HELD=1 /bin/bash "${SCRIPT_DIR}/backup-sqlite.sh"; then
  log "pre-release backup failed; restarting the unchanged image"
  if systemctl start ecg-backend.service && wait_ready 240; then
    die "release aborted because the pre-release backup failed"
  fi
  die "pre-release backup failed and the unchanged backend did not recover"
fi

PRE_RELEASE_MARKER="${ECG_OPS_ROOT}/last-backup-success"
PRE_RELEASE_TIME=""
PRE_RELEASE_URI=""
PRE_RELEASE_SHA=""
IFS=$'\t' read -r PRE_RELEASE_TIME PRE_RELEASE_URI PRE_RELEASE_SHA <"${PRE_RELEASE_MARKER}"
[[ -n "${PRE_RELEASE_TIME}" && "${PRE_RELEASE_URI}" == gs://*.sqlite3.gz ]] \
  || die "pre-release backup marker is malformed"
require_sha256 "${PRE_RELEASE_SHA}"
log "pre-release recovery point is durable: ${PRE_RELEASE_URI}"

write_image_env "${IMAGE}" new
systemctl daemon-reload
if systemctl start ecg-backend.service && wait_ready 240; then
  prune_docker_cache 720h
  log "backend release is ready: ${IMAGE}"
  exit 0
fi

log "new image failed readiness; restoring pre-release data and image ${PREVIOUS}"
systemctl stop ecg-backend.service || true
write_image_env "${PREVIOUS}" rollback
if ECG_MAINTENANCE_LOCK_HELD=1 /bin/bash "${SCRIPT_DIR}/restore-sqlite.sh" \
  --release-rollback "${PRE_RELEASE_URI}" "${PRE_RELEASE_SHA}"; then
  die "release failed readiness; the exact pre-release database and image were restored"
fi

# restore-sqlite puts the post-candidate DB/WAL/SHM set back in place if the
# selected recovery point cannot pass readiness. Re-select the candidate so the
# preserved state is never opened by an older, schema-incompatible binary.
log "data rollback failed; preserving candidate state behind closed readiness"
write_image_env "${IMAGE}" failed-rollback
if systemctl restart ecg-backend.service && wait_live 120; then
  die "release and data rollback failed; candidate is live but isolated by readiness"
fi
die "release and data rollback failed; service remains stopped for recovery"
