#!/usr/bin/env bash
# Deny the unprivileged backend UID access to the GCE metadata/token service.
# Root deployment/backup processes retain access to metadata and VM credentials.

set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"
require_root
for command in iptables ip6tables; do require_command "${command}"; done

ensure_reject() {
  local command="$1" destination="$2"
  if ! "${command}" --wait 5 --check OUTPUT \
    --destination "${destination}" --match owner --uid-owner 10001 --jump REJECT \
    2>/dev/null; then
    "${command}" --wait 5 --insert OUTPUT 1 \
      --destination "${destination}" --match owner --uid-owner 10001 --jump REJECT
  fi
  "${command}" --wait 5 --check OUTPUT \
    --destination "${destination}" --match owner --uid-owner 10001 --jump REJECT \
    || die "metadata firewall rule did not persist"
}

ensure_reject iptables 169.254.169.254/32
ensure_reject ip6tables fd20:ce::254/128
log "backend UID metadata isolation is active"
