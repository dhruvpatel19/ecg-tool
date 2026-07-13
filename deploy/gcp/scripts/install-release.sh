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
for command in docker systemctl curl; do require_command "${command}"; done
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

retry 8 2 docker pull "${IMAGE}"
printf 'ECG_BACKEND_IMAGE=%q\n' "${IMAGE}" >"${IMAGE_ENV}.new"
chmod 0600 "${IMAGE_ENV}.new"
mv -f "${IMAGE_ENV}.new" "${IMAGE_ENV}"
systemctl daemon-reload
if systemctl restart ecg-backend.service && wait_ready 240; then
  prune_docker_cache 720h
  log "backend release is ready: ${IMAGE}"
  exit 0
fi

if [[ -n "${PREVIOUS}" && "${PREVIOUS}" != "${IMAGE}" ]]; then
  log "new image failed readiness; rolling back to ${PREVIOUS}"
  printf 'ECG_BACKEND_IMAGE=%q\n' "${PREVIOUS}" >"${IMAGE_ENV}.rollback"
  chmod 0600 "${IMAGE_ENV}.rollback"
  mv -f "${IMAGE_ENV}.rollback" "${IMAGE_ENV}"
  if ! systemctl restart ecg-backend.service || ! wait_ready 240; then
    die "release and rollback both failed readiness"
  fi
  die "release failed readiness and was rolled back"
fi
die "release failed readiness and no previous image was available"
