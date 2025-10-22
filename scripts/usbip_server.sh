#!/usr/bin/env bash
set -euo pipefail
# USB/IP server setup on endpoint A (10.24.0.1)
# Usage: sudo ./scripts/usbip_server.sh <BUSID>
# Find BUSID with: usbip list -l

if [[ $EUID -ne 0 ]]; then
  echo "Run as root (sudo)" >&2
  exit 1
fi

BUSID=${1:-}
if [[ -z "$BUSID" ]]; then
  echo "Provide BUSID, e.g., '1-1'" >&2
  exit 1
fi

apt-get update
apt-get install -y usbip

# Start daemon
usbipd -D || true
# Bind device
usbip bind --busid="$BUSID"

echo "USB/IP server ready. Listening on 0.0.0.0:3240"
