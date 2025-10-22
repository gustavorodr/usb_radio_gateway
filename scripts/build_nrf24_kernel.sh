#!/usr/bin/env bash
set -euo pipefail
# Build and load the nrf24_net kernel module on Raspberry Pi

if [[ $EUID -ne 0 ]]; then
  echo "Run as root (sudo)" >&2
  exit 1
fi

apt-get update
apt-get install -y raspberrypi-kernel-headers build-essential
cd kernel/nrf24_net
make
rmmod nrf24_net 2>/dev/null || true
insmod nrf24_net.ko
ip link show | grep -E "nrf[0-9]" || true
