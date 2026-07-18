#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../scripts/lib.sh
source "${SCRIPT_DIR}/../scripts/lib.sh"

require_command sqlite3
require_command find
require_command grep

STARTUP_TEMPLATE="${SCRIPT_DIR}/../terraform/startup.sh.tftpl"
bash -n "${STARTUP_TEMPLATE}"
if grep -F 'systemctl stop ecg-backend.service' "${STARTUP_TEMPLATE}" >/dev/null; then
  die "startup reconciliation stops the known-good backend before candidate validation"
fi

TEMP_ROOT="$(realpath -e "${TMPDIR:-/tmp}")"
WORK="$(mktemp -d "${TEMP_ROOT%/}/ecg-corpus-immutable-read.XXXXXX")"
cleanup() {
  local resolved
  resolved="$(realpath -e "${WORK}")"
  [[ "${resolved}" == "${TEMP_ROOT%/}/ecg-corpus-immutable-read."* ]] \
    || die "refusing out-of-scope immutable-read test cleanup"
  rm -rf -- "${resolved}"
}
trap cleanup EXIT

DATABASE="${WORK}/rhythm_streams.db"
JOURNAL_MODE="$(sqlite3 "${DATABASE}" '
  PRAGMA journal_mode=WAL;
  CREATE TABLE rhythm_windows (id INTEGER PRIMARY KEY);
  INSERT INTO rhythm_windows DEFAULT VALUES;
  PRAGMA wal_checkpoint(TRUNCATE);
')"
mapfile -t JOURNAL_LINES <<<"${JOURNAL_MODE}"
[[ "${#JOURNAL_LINES[@]}" -eq 2 \
  && "${JOURNAL_LINES[0]}" == "wal" \
  && "${JOURNAL_LINES[1]}" == "0|0|0" ]] \
  || die "test database did not enter and checkpoint WAL mode"

# Begin from the exact state of a packaged release: the database header retains
# WAL journal mode, while the checkpointed archive contains no mutable sidecars.
rm -f -- "${DATABASE}-wal" "${DATABASE}-shm"
[[ "$(sqlite_immutable_readonly "${DATABASE}" 'SELECT COUNT(*) FROM rhythm_windows;')" == "1" ]] \
  || die "immutable corpus query returned the wrong result"

ln -s "${WORK}" "${WORK}/database-parent"
[[ "$(sqlite_immutable_readonly \
  "${WORK}/database-parent/rhythm_streams.db" \
  'SELECT COUNT(*) FROM rhythm_windows;')" == "1" ]] \
  || die "immutable corpus query rejected a safe symlinked ancestor"

UNSAFE_DATABASE="${WORK}/unsafe?rhythm_streams.db"
cp "${DATABASE}" "${UNSAFE_DATABASE}"
if (sqlite_immutable_readonly "${UNSAFE_DATABASE}" 'SELECT 1;' >/dev/null 2>&1); then
  die "immutable corpus query accepted a URI-ambiguous database path"
fi
rm -f -- "${UNSAFE_DATABASE}"

CORPUS_ROOT="${WORK}/corpus"
mkdir -p "${CORPUS_ROOT}/releases/release-good" \
  "${CORPUS_ROOT}/releases/release-previous" \
  "${CORPUS_ROOT}/releases/nested/release-invalid"
touch -d '45 days ago' "${CORPUS_ROOT}/releases/release-previous"
activate_corpus_release_pointer \
  "${CORPUS_ROOT}" "${CORPUS_ROOT}/releases/release-previous"
activate_corpus_release_pointer \
  "${CORPUS_ROOT}" "${CORPUS_ROOT}/releases/release-good"
[[ "$(readlink -f "${CORPUS_ROOT}/current")" \
  == "$(realpath -e "${CORPUS_ROOT}/releases/release-good")" ]] \
  || die "corpus activation did not select the direct release target"
[[ -d "${CORPUS_ROOT}/releases/release-previous" ]] \
  || die "corpus activation deleted the aged previous release"
if (activate_corpus_release_pointer \
  "${CORPUS_ROOT}" "${CORPUS_ROOT}/releases/nested/release-invalid" \
  >/dev/null 2>&1); then
  die "corpus activation accepted a nested release target"
fi
ln -sfn "releases/release-missing" "${CORPUS_ROOT}/current"
activate_corpus_release_pointer \
  "${CORPUS_ROOT}" "${CORPUS_ROOT}/releases/release-good"
[[ "$(readlink -f "${CORPUS_ROOT}/current")" \
  == "$(realpath -e "${CORPUS_ROOT}/releases/release-good")" ]] \
  || die "corpus activation did not replace a broken pointer safely"

[[ -z "$(find "${WORK}" -mindepth 1 -maxdepth 1 -type f ! -name 'rhythm_streams.db' -print -quit)" ]] \
  || die "immutable corpus validation created a SQLite sidecar"

printf 'immutable corpus SQLite validation passed\n'
