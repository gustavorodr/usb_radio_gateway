#!/usr/bin/env bash
set -euo pipefail
# Configure wlan0 for ad-hoc (IBSS) P2P low-latency link on Pi B
IF=${1:-wlan0}
SSID=${2:-p2p-lowlat}
FREQ=${3:-5180} # 5 GHz ch 36
IP=${4:-10.25.0.2/30}

sudo ip link set "$IF" down || true
sudo iw dev "$IF" set type ibss || true
sudo iw dev "$IF" set power_save off || true
sudo ip link set "$IF" up
sudo iw dev "$IF" ibss join "$SSID" "$FREQ" fixed-freq beacon-interval 100 basic-rates 12 24 48 mcast-rate 24
sudo ip addr flush dev "$IF" || true
sudo ip addr add "$IP" dev "$IF"
sudo ethtool -K "$IF" tso off gso off gro off rx off tx off || true
