#!/usr/bin/env bash
# Thin wrapper to keep legacy path working; real script lives in scripts/show_log.sh
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scripts/show_log.sh" "$@"
