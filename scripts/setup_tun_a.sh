#!/usr/bin/env bash
set -euo pipefail
# Configure tun0 on endpoint A
sudo ip tuntap add dev tun0 mode tun || true
sudo ip addr add 10.24.0.1/30 dev tun0 || true
sudo ip link set dev tun0 up
