#!/usr/bin/env bash
""":"
Package a complete corpus into an immutable, checksum-pinned artifact.

Usage:
  package-corpus.sh CORPUS_ROOT RELEASE OUTPUT_DIR [gs://BUCKET/releases] [--upload]

Uploading is opt-in. The generation-match precondition prevents accidentally
replacing an existing release object.
":"""

set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"

[[ $# -ge 3 && $# -le 5 ]] || die "usage: $0 CORPUS_ROOT RELEASE OUTPUT_DIR [GCS_PREFIX] [--upload]"
CORPUS_ROOT="$(realpath "$1")"
RELEASE="$2"
OUTPUT_DIR="$3"
GCS_PREFIX="${4:-}"
UPLOAD="${5:-}"
require_safe_release "${RELEASE}"
require_command jq
require_command python3
require_command sqlite3
require_command sha256sum
require_command tar
require_command zstd
sqlite3 "${CORPUS_ROOT}/corpus.db" 'PRAGMA wal_checkpoint(TRUNCATE);' >/dev/null
[[ ! -s "${CORPUS_ROOT}/corpus.db-wal" ]] \
  || die "corpus WAL is not empty; stop corpus writers before packaging"
REPO_ROOT="$(realpath "${SCRIPT_DIR}/../../..")"
log "running exhaustive release corpus audit"
PYTHONPATH="${REPO_ROOT}/backend" python3 "${REPO_ROOT}/scripts/audit_release_corpus.py" \
  --corpus-root "${CORPUS_ROOT}" --output "${CORPUS_ROOT}/release-audit.json"
validate_corpus_tree "${CORPUS_ROOT}"

mkdir -p "${OUTPUT_DIR}"
ARTIFACT="${OUTPUT_DIR%/}/ecg-corpus-${RELEASE}.tar.zst"
CHECKSUM="${ARTIFACT}.sha256"
[[ ! -e "${ARTIFACT}" ]] || die "artifact already exists: ${ARTIFACT}"

log "creating deterministic corpus artifact"
tar --directory "${CORPUS_ROOT}" \
  --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner \
  --exclude='corpus.db-wal' --exclude='corpus.db-shm' \
  --zstd -cf "${ARTIFACT}" manifest.json release-audit.json corpus.db waveforms
SHA256="$(sha256_file "${ARTIFACT}")"
printf '%s  %s\n' "${SHA256}" "$(basename "${ARTIFACT}")" >"${CHECKSUM}"
log "artifact: ${ARTIFACT}"
log "sha256: ${SHA256}"

if [[ "${UPLOAD}" == "--upload" ]]; then
  [[ "${GCS_PREFIX}" == gs://* ]] || die "a gs:// prefix is required for upload"
  require_command gcloud
  DESTINATION="${GCS_PREFIX%/}/$(basename "${ARTIFACT}")"
  log "uploading immutable object ${DESTINATION}"
  gcloud storage cp --if-generation-match=0 "${ARTIFACT}" "${DESTINATION}"
  gcloud storage cp --if-generation-match=0 "${CHECKSUM}" "${DESTINATION}.sha256"
elif [[ -n "${UPLOAD}" ]]; then
  die "unknown option: ${UPLOAD}"
fi

printf 'ECG_CORPUS_RELEASE=%s\nECG_CORPUS_SHA256=%s\n' "${RELEASE}" "${SHA256}"
