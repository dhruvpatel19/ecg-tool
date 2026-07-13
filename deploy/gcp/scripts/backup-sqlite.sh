#!/usr/bin/env bash
# Create a transactionally consistent SQLite backup with the online backup API.

set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"
require_root
for command in python3 gzip gcloud sha256sum flock cmp setpriv; do require_command "${command}"; done

CONFIG_FILE="${ECG_DEPLOYMENT_ENV:-/etc/ecg/deployment.env}"
[[ -r "${CONFIG_FILE}" ]] || die "deployment environment is missing: ${CONFIG_FILE}"
# shellcheck disable=SC1090
source "${CONFIG_FILE}"
: "${ECG_STATE_DB:?ECG_STATE_DB is required}"
: "${ECG_OPS_ROOT:?ECG_OPS_ROOT is required}"
: "${ECG_BACKUP_GCS_PREFIX:?ECG_BACKUP_GCS_PREFIX is required}"
[[ "${ECG_BACKUP_GCS_PREFIX}" == gs://* ]] || die "backup prefix must use gs://"
validate_ops_root "${ECG_OPS_ROOT}"
[[ -f "${ECG_STATE_DB}" && ! -L "${ECG_STATE_DB}" ]] \
  || die "learner database must be a regular non-symlink file"

if [[ "${ECG_MAINTENANCE_LOCK_HELD:-0}" != "1" ]]; then
  exec 8>"${ECG_OPS_ROOT}/maintenance.lock"
  flock -s -n 8 || die "learner database is in maintenance"
fi

LOCK_FILE="${ECG_OPS_ROOT}/backup.lock"
exec 9>"${LOCK_FILE}"
flock -n 9 || die "another backup is already running"

WORK="$(mktemp -d "${ECG_OPS_ROOT}/.backup.XXXXXX")"
trap 'remove_ops_worktree "${ECG_OPS_ROOT}" "${WORK}"' EXIT
SNAPSHOT="${WORK}/ecg-learning.sqlite3"
TIMESTAMP="$(date -u +'%Y%m%dT%H%M%SZ')"
chown 10001:10001 "${WORK}"
chmod 0700 "${WORK}"

# Open the app-writable source with the same unprivileged UID as the container.
# A symlink race can therefore never turn this root service into a host-file
# reader; the root-owned ops mount is read-only inside the container.
setpriv --reuid=10001 --regid=10001 --clear-groups -- \
  python3 - "${ECG_STATE_DB}" "${SNAPSHOT}" <<'PY'
import sqlite3
import sys

source_path, destination_path = sys.argv[1:]
source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True, timeout=30)
destination = sqlite3.connect(destination_path)
try:
    source.execute("PRAGMA busy_timeout=30000")
    source.backup(destination, pages=1000, sleep=0.05)
    result = destination.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        raise RuntimeError(f"backup integrity check failed: {result}")
finally:
    destination.close()
    source.close()
PY
chown root:root "${WORK}" "${SNAPSHOT}"
chmod 0700 "${WORK}"
chmod 0600 "${SNAPSHOT}"

gzip -n -9 "${SNAPSHOT}"
ARCHIVE="${SNAPSHOT}.gz"
SHA256="$(sha256_file "${ARCHIVE}")"
printf '%s  %s\n' "${SHA256}" "$(basename "${ARCHIVE}")" >"${ARCHIVE}.sha256"
YEAR="${TIMESTAMP:0:4}"
MONTH="${TIMESTAMP:4:2}"
DAY="${TIMESTAMP:6:2}"
DESTINATION="${ECG_BACKUP_GCS_PREFIX%/}/${YEAR}/${MONTH}/${DAY}/ecg-learning-${TIMESTAMP}.sqlite3.gz"

upload_new_or_verify() {
  local source="$1" destination="$2" verify_copy
  if retry 6 2 gcloud storage cp --if-generation-match=0 "${source}" "${destination}"; then
    return 0
  fi
  # A connection can fail after GCS durably commits the unique object. Because
  # objectCreator denies overwrite, verify exact bytes before treating that
  # ambiguous outcome as success; never weaken the generation precondition.
  verify_copy="${WORK}/verify-$(basename "${source}")"
  rm -f "${verify_copy}"
  retry 6 2 gcloud storage cp "${destination}" "${verify_copy}"
  cmp --silent "${source}" "${verify_copy}" \
    || die "existing backup object does not match the attempted upload"
}

log "uploading consistent learner-state backup"
upload_new_or_verify "${ARCHIVE}" "${DESTINATION}"
upload_new_or_verify "${ARCHIVE}.sha256" "${DESTINATION}.sha256"
MARKER="${ECG_OPS_ROOT}/last-backup-success"
MARKER_NEW="$(mktemp "${ECG_OPS_ROOT}/.backup-marker.XXXXXX")"
printf '%s\t%s\t%s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "${DESTINATION}" "${SHA256}" >"${MARKER_NEW}"
chown root:10001 "${MARKER_NEW}"
chmod 0640 "${MARKER_NEW}"
mv -f -- "${MARKER_NEW}" "${MARKER}"
log "backup complete: ${DESTINATION} (sha256 ${SHA256})"
