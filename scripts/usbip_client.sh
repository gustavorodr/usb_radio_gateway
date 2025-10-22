#!/usr/bin/env bash
set -euo pipefail
# USB/IP client setup on endpoint B (10.24.0.2)
# Usage: sudo ./scripts/usbip_client.sh <SERVER_IP> <BUSID>
# Example: sudo ./scripts/usbip_client.sh 10.24.0.1 1-1

if [[ $EUID -ne 0 ]]; then
  echo "Run as root (sudo)" >&2
  exit 1
fi

SERVER_IP=${1:-}
BUSID=${2:-}
if [[ -z "$SERVER_IP" || -z "$BUSID" ]]; then
  echo "Usage: sudo ./scripts/usbip_client.sh <SERVER_IP> <BUSID>" >&2
  exit 1
fi

apt-get update
apt-get install -y linux-tools-generic || true
modprobe vhci-hcd || true

usbip attach --remote="$SERVER_IP" --busid="$BUSID"

echo "Attached $BUSID from $SERVER_IP via USB/IP"
