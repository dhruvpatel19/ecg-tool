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

# GCE exposes its recursive DNS resolver on the metadata address. The backend
# still needs that resolver for the configured SMTP and AI-provider hostnames,
# while metadata credentials themselves must remain unreachable. Permit only
# DNS before the destination-wide reject below; TCP/UDP port 53 cannot access
# the HTTP metadata/token service.
ensure_dns_accept() {
  local command="$1" destination="$2" protocol="$3"
  if ! "${command}" --wait 5 --check OUTPUT \
    --destination "${destination}" --protocol "${protocol}" --dport 53 \
    --match owner --uid-owner 10001 --jump ACCEPT 2>/dev/null; then
    "${command}" --wait 5 --insert OUTPUT 1 \
      --destination "${destination}" --protocol "${protocol}" --dport 53 \
      --match owner --uid-owner 10001 --jump ACCEPT
  fi
  "${command}" --wait 5 --check OUTPUT \
    --destination "${destination}" --protocol "${protocol}" --dport 53 \
    --match owner --uid-owner 10001 --jump ACCEPT \
    || die "metadata-address DNS allowance did not persist"
}

ensure_reject iptables 169.254.169.254/32
ensure_reject ip6tables fd20:ce::254/128
ensure_dns_accept iptables 169.254.169.254/32 udp
ensure_dns_accept iptables 169.254.169.254/32 tcp
ensure_dns_accept ip6tables fd20:ce::254/128 udp
ensure_dns_accept ip6tables fd20:ce::254/128 tcp
log "backend UID metadata isolation is active with DNS-only resolver access"
