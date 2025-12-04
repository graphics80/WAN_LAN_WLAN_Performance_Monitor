#!/usr/bin/env bash
# Restart a wireless interface to recover from flaky Wi-Fi sessions. Default: wlan0.

set -euo pipefail

IFACE="${1:-wlan0}"
LOG_TAG="wan-wlan-restart"

log() {
  # Log to both syslog and stdout so cron captures output.
  logger -t "$LOG_TAG" "$*"
  printf "%s\n" "$*"
}

log "Restarting interface $IFACE"
if ! ip link set "$IFACE" down; then
  log "Failed to bring $IFACE down"
fi

sleep 5
if ! ip link set "$IFACE" up; then
  log "Failed to bring $IFACE up"
fi

# Renew DHCP lease if dhclient is present.
if command -v dhclient >/dev/null 2>&1; then
  dhclient -r "$IFACE" || true
  dhclient "$IFACE" || true
fi

log "Interface $IFACE restart complete"
