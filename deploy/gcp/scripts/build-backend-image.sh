#!/usr/bin/env bash
# Build and push the production backend, then print its immutable digest URI.

set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"
[[ $# -eq 3 ]] \
  || die "usage: $0 GCP_PROJECT REGION ARTIFACT_REPOSITORY"
PROJECT_ID="$1"
REGION="$2"
REPOSITORY="$3"
TAG="$(git rev-parse --short=12 HEAD)-$(date -u +'%Y%m%dT%H%M%S%N')"
[[ "${PROJECT_ID}" =~ ^[a-z][a-z0-9-]{4,28}[a-z0-9]$ ]] || die "invalid GCP project id"
[[ "${REGION}" =~ ^[a-z]+-[a-z]+[0-9]$ ]] || die "invalid GCP region"
[[ "${REPOSITORY}" =~ ^[a-z][a-z0-9._-]{2,62}$ ]] || die "invalid Artifact Registry repository"
[[ "${TAG}" =~ ^[A-Za-z0-9._-]{1,128}$ ]] || die "generated image tag is invalid"
for command in docker gcloud git; do require_command "${command}"; done

REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
if [[ -n "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=all -- backend)" ]]; then
  die "backend build inputs are dirty or untracked; commit the reviewed image inputs first"
fi
HOST="${REGION}-docker.pkg.dev"
IMAGE="${HOST}/${PROJECT_ID}/${REPOSITORY}/ecg-backend:${TAG}"
VCS_REF="$(git -C "${REPO_ROOT}" rev-parse HEAD)"
BUILD_DATE="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"

gcloud auth configure-docker "${HOST}" --quiet
docker build --platform linux/amd64 \
  --file "${REPO_ROOT}/backend/Dockerfile" \
  --build-arg "VCS_REF=${VCS_REF}" \
  --build-arg "BUILD_DATE=${BUILD_DATE}" \
  --tag "${IMAGE}" \
  "${REPO_ROOT}/backend"
docker push "${IMAGE}"
DIGEST="$(gcloud artifacts docker images describe "${IMAGE}" \
  --project "${PROJECT_ID}" --format='value(image_summary.digest)')"
[[ "${DIGEST}" =~ ^sha256:[a-f0-9]{64}$ ]] || die "registry did not return an immutable digest"
printf '%s@%s\n' "${IMAGE%:*}" "${DIGEST}"
