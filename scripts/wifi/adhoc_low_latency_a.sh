#!/usr/bin/env bash
set -euo pipefail
# Configure wlan0 for ad-hoc (IBSS) P2P low-latency link on Pi A
IF=${1:-wlan0}
SSID=${2:-p2p-lowlat}
FREQ=${3:-5180} # 5 GHz ch 36
IP=${4:-10.25.0.1/30}

sudo ip link set "$IF" down || true
sudo iw dev "$IF" set type ibss || true
sudo iw dev "$IF" set power_save off || true
# Some chipsets support iw dev set txpower fixed <mBm>
# sudo iw dev "$IF" set txpower fixed 1500 || true
sudo ip link set "$IF" up
sudo iw dev "$IF" ibss join "$SSID" "$FREQ" fixed-freq beacon-interval 100 basic-rates 12 24 48 mcast-rate 24
sudo ip addr flush dev "$IF" || true
sudo ip addr add "$IP" dev "$IF"
# Disable offloads that can add latency/jitter
sudo ethtool -K "$IF" tso off gso off gro off rx off tx off || true
# Disable Wi-Fi Multimedia (WMM) if supported via driver module options (vendor-specific)
# Example for rtl88XXau: sudo modprobe 88XXau rtw_power_mgnt=0 rtw_enusbss=0 rtw_switch_usb_mode=1 rtw_uapsd_enable=0
