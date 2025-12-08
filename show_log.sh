#!/bin/bash

# Tail wan-monitor systemd logs in realtime.
journalctl -u wan-monitor.service -f
