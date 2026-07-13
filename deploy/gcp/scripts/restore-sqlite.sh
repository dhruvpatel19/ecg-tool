#!/usr/bin/env bash
# Restore one explicitly selected backup, with integrity validation and rollback.

set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"
require_root
RESTORE_MODE=healthy
if [[ "${1:-}" == "--corrupt-source-break-glass" ]]; then
  RESTORE_MODE=corrupt
  shift
elif [[ "${1:-}" == "--release-rollback" ]]; then
  RESTORE_MODE=release
  shift
fi
[[ $# -eq 2 ]] \
  || die "usage: $0 [--corrupt-source-break-glass|--release-rollback] gs://BACKUP.sqlite3.gz SHA256"
BACKUP_URI="$1"
EXPECTED_SHA="${2,,}"
require_sha256 "${EXPECTED_SHA}"
[[ "${BACKUP_URI}" == gs://*.sqlite3.gz ]] || die "restore source must be a gs:// SQLite gzip backup"
for command in gcloud sha256sum gzip python3 systemctl flock setpriv; do require_command "${command}"; done

CONFIG_FILE="${ECG_DEPLOYMENT_ENV:-/etc/ecg/deployment.env}"
[[ -r "${CONFIG_FILE}" ]] || die "deployment environment is missing: ${CONFIG_FILE}"
# shellcheck disable=SC1090
source "${CONFIG_FILE}"
: "${ECG_STATE_DB:?ECG_STATE_DB is required}"
: "${ECG_OPS_ROOT:?ECG_OPS_ROOT is required}"
validate_ops_root "${ECG_OPS_ROOT}"

if [[ "${ECG_MAINTENANCE_LOCK_HELD:-0}" != "1" ]]; then
  exec 8>"${ECG_OPS_ROOT}/maintenance.lock"
  flock -n 8 || die "learner database is already in backup/maintenance"
fi

WORK="$(mktemp -d "${ECG_OPS_ROOT}/.restore.XXXXXX")"
trap 'remove_ops_worktree "${ECG_OPS_ROOT}" "${WORK}"' EXIT
ARCHIVE="${WORK}/restore.sqlite3.gz"
CANDIDATE="${WORK}/restore.sqlite3"
QUARANTINE=""

log "downloading selected restore point"
retry 8 2 gcloud storage cp "${BACKUP_URI}" "${ARCHIVE}"
ACTUAL_SHA="$(sha256_file "${ARCHIVE}")"
[[ "${ACTUAL_SHA}" == "${EXPECTED_SHA}" ]] \
  || die "backup checksum mismatch (${ACTUAL_SHA} != ${EXPECTED_SHA})"
gzip -dc "${ARCHIVE}" >"${CANDIDATE}"

chown 10001:10001 "${WORK}" "${CANDIDATE}"
chmod 0700 "${WORK}"
chmod 0600 "${CANDIDATE}"
setpriv --reuid=10001 --regid=10001 --clear-groups -- \
  python3 - "${CANDIDATE}" <<'PY'
import sqlite3
import sys

connection = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
try:
    result = connection.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        raise RuntimeError(f"restore candidate integrity check failed: {result}")
finally:
    connection.close()
PY
chown root:root "${WORK}" "${CANDIDATE}"
chmod 0700 "${WORK}"
chmod 0600 "${CANDIDATE}"

# Healthy-source mode refuses to touch the live database unless a fresh remote
# recovery point succeeds. Break-glass mode is for
# an unreadable/corrupt source: stop the writer and quarantine the raw DB/WAL/SHM
# without trying to open them.
if [[ "${RESTORE_MODE}" == "healthy" ]]; then
  ECG_MAINTENANCE_LOCK_HELD=1 /bin/bash "${SCRIPT_DIR}/backup-sqlite.sh"
  systemctl stop ecg-backend.service
  ORIGINAL="${WORK}/original"
  mkdir -m 0700 "${ORIGINAL}"
elif [[ "${RESTORE_MODE}" == "corrupt" ]]; then
  log "BREAK GLASS: stopping the writer and quarantining the unreadable source"
  systemctl stop ecg-backend.service
  QUARANTINE_ROOT="${ECG_OPS_ROOT}/quarantine"
  mkdir -p "${QUARANTINE_ROOT}"
  chmod 0700 "${QUARANTINE_ROOT}"
  QUARANTINE="$(mktemp -d "${QUARANTINE_ROOT}/corrupt-source-$(date -u +'%Y%m%dT%H%M%SZ').XXXXXX")"
  chmod 0700 "${QUARANTINE}"
  ORIGINAL="${QUARANTINE}"
else
  # install-release.sh already proved and recorded the exact append-only remote
  # recovery point while the writer was stopped. Preserve the candidate state
  # locally until the previous image passes readiness against the restored DB.
  log "release rollback: stopping the candidate and restoring the pre-release snapshot"
  systemctl stop ecg-backend.service
  ORIGINAL="${WORK}/post-release-source"
  mkdir -m 0700 "${ORIGINAL}"
fi

# With the writer stopped, move the exact DB/WAL/SHM set into a root-owned
# same-filesystem directory. `mv` renames a hostile symlink itself rather than
# following it. The final candidate rename is likewise atomic and cannot follow
# a pre-created destination symlink.
for suffix in '' '-wal' '-shm'; do
  source_file="${ECG_STATE_DB}${suffix}"
  if [[ -e "${source_file}" || -L "${source_file}" ]]; then
    mv -- "${source_file}" "${ORIGINAL}/$(basename "${source_file}")"
  fi
done
READY_CANDIDATE="${WORK}/ready.sqlite3"
install -o 10001 -g 10001 -m 0640 "${CANDIDATE}" "${READY_CANDIDATE}"
mv -f -- "${READY_CANDIDATE}" "${ECG_STATE_DB}"
RESTORE_READY=0
if systemctl start ecg-backend.service; then
  if [[ "${RESTORE_MODE}" == "corrupt" ]]; then
    # The restored database itself must produce a new application-consistent
    # recovery point before public readiness can reopen.
    if wait_live 180 \
      && ECG_MAINTENANCE_LOCK_HELD=1 /bin/bash "${SCRIPT_DIR}/backup-sqlite.sh" \
      && wait_ready 180; then
      RESTORE_READY=1
    fi
  elif wait_ready 180; then
    RESTORE_READY=1
  fi
fi
if [[ "${RESTORE_READY}" == "1" ]]; then
  if [[ "${RESTORE_MODE}" == "corrupt" ]]; then
    log "restore succeeded; corrupt source evidence remains quarantined at ${QUARANTINE}"
  fi
  log "restore succeeded and readiness passed"
  exit 0
fi

systemctl stop ecg-backend.service || true
if [[ "${RESTORE_MODE}" == "corrupt" ]]; then
  log "break-glass candidate failed; preserving both evidence sets"
  for suffix in '' '-wal' '-shm'; do
    failed_file="${ECG_STATE_DB}${suffix}"
    if [[ -e "${failed_file}" || -L "${failed_file}" ]]; then
      mv -- "${failed_file}" "${QUARANTINE}/failed-restore$(printf '%s' "${suffix}")"
    fi
  done
  die "break-glass restore failed; service is isolated and source/candidate evidence is in ${QUARANTINE}"
fi
log "restored database failed readiness; atomically restoring the stopped source set"
FAILED="${WORK}/failed-candidate"
mkdir -m 0700 "${FAILED}"
for suffix in '' '-wal' '-shm'; do
  failed_file="${ECG_STATE_DB}${suffix}"
  if [[ -e "${failed_file}" || -L "${failed_file}" ]]; then
    mv -- "${failed_file}" "${FAILED}/$(basename "${failed_file}")"
  fi
  original_file="${ORIGINAL}/$(basename "${ECG_STATE_DB}${suffix}")"
  if [[ -e "${original_file}" || -L "${original_file}" ]]; then
    mv -- "${original_file}" "${ECG_STATE_DB}${suffix}"
  fi
done
if ! systemctl start ecg-backend.service || ! wait_ready 180; then
  die "rollback also failed readiness; keep service isolated and investigate"
fi
die "restore failed readiness and was rolled back"
