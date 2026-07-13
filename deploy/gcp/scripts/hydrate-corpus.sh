#!/usr/bin/env bash
""":"
Hydrate and atomically activate one checksum-pinned corpus release.

Usage:
  hydrate-corpus.sh GCS_OBJECT_URI RELEASE SHA256 [DATA_ROOT]
":"""

set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"
require_root
[[ $# -ge 3 && $# -le 4 ]] || die "usage: $0 GCS_OBJECT_URI RELEASE SHA256 [DATA_ROOT]"

GCS_URI="$1"
RELEASE="$2"
EXPECTED_SHA="${3,,}"
DATA_ROOT="${4:-/srv/ecg-data}"
CORPUS_ROOT="${DATA_ROOT%/}/corpus"
RELEASES_ROOT="${CORPUS_ROOT}/releases"
TARGET="${RELEASES_ROOT}/${RELEASE}"
require_safe_release "${RELEASE}"
require_sha256 "${EXPECTED_SHA}"
[[ "${GCS_URI}" == gs://* ]] || die "corpus object must use gs://"
for command in gcloud sha256sum tar zstd jq sqlite3 find; do require_command "${command}"; done

mkdir -p "${RELEASES_ROOT}" "${DATA_ROOT%/}/artifacts"
exec 9>"${CORPUS_ROOT}/.hydrate.lock"
flock 9

if [[ -f "${TARGET}/.verified.sha256" ]] \
  && [[ "$(tr -d '[:space:]' <"${TARGET}/.verified.sha256")" == "${EXPECTED_SHA}" ]]; then
  validate_corpus_tree "${TARGET}"
  log "release ${RELEASE} is already verified"
else
  [[ ! -e "${TARGET}" ]] || die "release directory exists without the expected verification marker"
  STAGE="$(mktemp -d "${RELEASES_ROOT}/.staging-${RELEASE}.XXXXXX")"
  trap 'rm -rf "${STAGE:-}"' EXIT
  ARCHIVE="${DATA_ROOT%/}/artifacts/ecg-corpus-${RELEASE}.tar.zst"
  log "downloading ${GCS_URI}"
  retry 8 2 gcloud storage cp "${GCS_URI}" "${ARCHIVE}.part"
  ACTUAL_SHA="$(sha256_file "${ARCHIVE}.part")"
  [[ "${ACTUAL_SHA}" == "${EXPECTED_SHA}" ]] \
    || die "corpus checksum mismatch (${ACTUAL_SHA} != ${EXPECTED_SHA})"
  mv -f "${ARCHIVE}.part" "${ARCHIVE}"

  # Refuse absolute paths or parent traversal before extraction. The checksum is
  # the primary trust anchor; this is defense in depth for archive handling.
  while IFS= read -r entry; do
    normalized="${entry#./}"
    [[ "${normalized}" != /* && "${normalized}" != ".." \
      && "${normalized}" != ../* && "${normalized}" != */../* \
      && "${normalized}" != */.. ]] || die "unsafe archive path"
  done < <(tar --zstd -tf "${ARCHIVE}")
  if tar --zstd -tvf "${ARCHIVE}" | awk 'substr($1,1,1) !~ /[-d]/ {exit 1}'; then
    :
  else
    die "archive contains a non-file/non-directory entry"
  fi

  tar --directory "${STAGE}" --zstd --no-same-owner --no-same-permissions -xf "${ARCHIVE}"
  validate_corpus_tree "${STAGE}"
  printf '%s\n' "${EXPECTED_SHA}" >"${STAGE}/.verified.sha256"
  chmod -R a=rX,u+w "${STAGE}"
  mv "${STAGE}" "${TARGET}"
  trap - EXIT
fi

ln -sfn "releases/${RELEASE}" "${CORPUS_ROOT}/current.next"
mv -Tf "${CORPUS_ROOT}/current.next" "${CORPUS_ROOT}/current"

# The private GCS artifact remains the durable rollback source. Keep recent
# local releases for fast rollback but remove inactive directories/artifacts
# older than 30 days after verifying every resolved deletion target is confined
# to the intended persistent-disk subtree.
RELEASES_REAL="$(realpath -e "${RELEASES_ROOT}")"
TARGET_REAL="$(realpath -e "${TARGET}")"
while IFS= read -r -d '' candidate; do
  CANDIDATE_REAL="$(realpath -e "${candidate}")"
  [[ "${CANDIDATE_REAL}" == "${RELEASES_REAL}/"* && "${CANDIDATE_REAL}" != "${TARGET_REAL}" ]] \
    || die "refusing out-of-scope corpus release cleanup"
  rm -rf -- "${CANDIDATE_REAL}"
done < <(find "${RELEASES_ROOT}" -mindepth 1 -maxdepth 1 -type d -mtime +30 -print0)

ARTIFACTS_REAL="$(realpath -e "${DATA_ROOT%/}/artifacts")"
while IFS= read -r -d '' candidate; do
  CANDIDATE_REAL="$(realpath -e "${candidate}")"
  [[ "${CANDIDATE_REAL}" == "${ARTIFACTS_REAL}/"* ]] \
    || die "refusing out-of-scope corpus artifact cleanup"
  rm -f -- "${CANDIDATE_REAL}"
done < <(find "${ARTIFACTS_REAL}" -mindepth 1 -maxdepth 1 -type f -mtime +30 -print0)
log "activated corpus release ${RELEASE}"
