#!/usr/bin/env bash
set -euo pipefail

# Tail wan-monitor systemd logs in realtime.
journalctl -u wan-monitor.service -f
