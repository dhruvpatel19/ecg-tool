#!/usr/bin/env bash
# Execute the real backup/restore scripts against SQLite and a filesystem-backed
# fake GCS boundary. Intended for clean Linux CI runners under sudo.

set -Eeuo pipefail
[[ "${EUID}" -eq 0 ]] || { echo "run this regression as root" >&2; exit 1; }

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
TEST_ROOT="$(mktemp -d /srv/ecg-deploy-regression.XXXXXX)"
chmod 0711 "${TEST_ROOT}"
cleanup() {
  [[ "${TEST_ROOT}" == /srv/ecg-deploy-regression.* && -d "${TEST_ROOT}" ]] \
    || { echo "refusing unsafe regression cleanup" >&2; return 1; }
  rm -rf -- "${TEST_ROOT}"
}
trap cleanup EXIT

OPS_ROOT="${TEST_ROOT}/ops"
STATE_ROOT="${TEST_ROOT}/state"
FAKE_GCS_ROOT="${TEST_ROOT}/gcs"
FAKE_BIN="${TEST_ROOT}/bin"
mkdir -m 0700 "${STATE_ROOT}" "${FAKE_GCS_ROOT}" "${FAKE_BIN}"
mkdir -m 0750 "${OPS_ROOT}"
chown root:10001 "${OPS_ROOT}"
chown 10001:10001 "${STATE_ROOT}"

cat >"${FAKE_BIN}/gcloud" <<'SH'
#!/usr/bin/env bash
set -Eeuo pipefail
[[ "${1:-}" == "storage" && "${2:-}" == "cp" ]] || exit 64
shift 2
exclusive=0
if [[ "${1:-}" == "--if-generation-match=0" ]]; then
  exclusive=1
  shift
fi
[[ $# -eq 2 ]] || exit 64
source_path="$1"
destination_path="$2"
map_uri() {
  [[ "$1" == gs://* ]] || exit 64
  printf '%s/%s' "${FAKE_GCS_ROOT:?}" "${1#gs://}"
}
if [[ "${source_path}" == gs://* ]]; then
  cp -- "$(map_uri "${source_path}")" "${destination_path}"
else
  target="$(map_uri "${destination_path}")"
  mkdir -p -- "$(dirname -- "${target}")"
  if [[ "${exclusive}" == "1" && -e "${target}" ]]; then
    exit 1
  fi
  cp -- "${source_path}" "${target}"
fi
SH
cat >"${FAKE_BIN}/systemctl" <<'SH'
#!/usr/bin/env bash
set -Eeuo pipefail
case "${1:-}" in
  start|stop|restart|is-active|daemon-reload) exit 0 ;;
  *) exit 64 ;;
esac
SH
cat >"${FAKE_BIN}/curl" <<'SH'
#!/usr/bin/env bash
printf '{"ok":true}\n'
SH
chmod 0755 "${FAKE_BIN}/gcloud" "${FAKE_BIN}/systemctl" "${FAKE_BIN}/curl"
export FAKE_GCS_ROOT
export PATH="${FAKE_BIN}:${PATH}"

DATABASE="${STATE_ROOT}/ecg_learning.db"
setpriv --reuid=10001 --regid=10001 --clear-groups -- python3 - "${DATABASE}" <<'PY'
import sqlite3
import sys

with sqlite3.connect(sys.argv[1]) as connection:
    connection.execute("CREATE TABLE durable_state (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
    connection.execute("INSERT INTO durable_state VALUES (1, 'pre-release')")
PY

CONFIG="${TEST_ROOT}/deployment.env"
cat >"${CONFIG}" <<EOF
ECG_STATE_DB=${DATABASE}
ECG_OPS_ROOT=${OPS_ROOT}
ECG_BACKUP_GCS_PREFIX=gs://test-bucket/backups
EOF
chmod 0600 "${CONFIG}"

ECG_DEPLOYMENT_ENV="${CONFIG}" \
  bash "${DEPLOY_ROOT}/scripts/backup-sqlite.sh"
IFS=$'\t' read -r _ BACKUP_URI BACKUP_SHA <"${OPS_ROOT}/last-backup-success"
[[ "${BACKUP_URI}" == gs://*.sqlite3.gz && "${BACKUP_SHA}" =~ ^[a-f0-9]{64}$ ]]

python3 - "${DATABASE}" <<'PY'
import sqlite3
import sys

with sqlite3.connect(sys.argv[1]) as connection:
    connection.execute("UPDATE durable_state SET value = 'after-backup' WHERE id = 1")
PY

# Healthy-source restore creates its own safety backup before swapping the
# selected recovery point into place.
ECG_DEPLOYMENT_ENV="${CONFIG}" \
  bash "${DEPLOY_ROOT}/scripts/restore-sqlite.sh" "${BACKUP_URI}" "${BACKUP_SHA}"
[[ "$(sqlite3 -readonly "${DATABASE}" 'SELECT value FROM durable_state WHERE id = 1;')" == "pre-release" ]]
[[ "$(sqlite3 -readonly "${DATABASE}" 'PRAGMA integrity_check;')" == "ok" ]]

python3 - "${DATABASE}" <<'PY'
import sqlite3
import sys

with sqlite3.connect(sys.argv[1]) as connection:
    connection.execute("UPDATE durable_state SET value = 'candidate-migration' WHERE id = 1")
PY

# The release mode consumes the already-proven pre-release recovery point and
# restores it without taking a newer, semantically incompatible snapshot first.
ECG_DEPLOYMENT_ENV="${CONFIG}" ECG_MAINTENANCE_LOCK_HELD=0 \
  bash "${DEPLOY_ROOT}/scripts/restore-sqlite.sh" \
    --release-rollback "${BACKUP_URI}" "${BACKUP_SHA}"
[[ "$(sqlite3 -readonly "${DATABASE}" 'SELECT value FROM durable_state WHERE id = 1;')" == "pre-release" ]]

BAD_SHA="$(printf '0%.0s' {1..64})"
if ECG_DEPLOYMENT_ENV="${CONFIG}" \
  bash "${DEPLOY_ROOT}/scripts/restore-sqlite.sh" "${BACKUP_URI}" "${BAD_SHA}"; then
  echo "restore unexpectedly accepted an incorrect checksum" >&2
  exit 1
fi
[[ "$(sqlite3 -readonly "${DATABASE}" 'SELECT value FROM durable_state WHERE id = 1;')" == "pre-release" ]]

echo "backup/restore regression passed"
