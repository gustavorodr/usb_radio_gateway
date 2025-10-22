#!/usr/bin/env bash
set -euo pipefail

# This script installs Python deps and enables SPI on Raspberry Pi OS.
# Run with sudo.

if [[ $EUID -ne 0 ]]; then
  echo "Please run as root (sudo)." >&2
  exit 1
fi

apt-get update
apt-get install -y python3-pip python3-venv python3-dev git

# Enable SPI
if ! grep -q '^dtparam=spi=on' /boot/firmware/config.txt 2>/dev/null; then
  # Newer RPi OS uses /boot/firmware
  echo 'dtparam=spi=on' >> /boot/firmware/config.txt || true
fi
if ! grep -q '^dtparam=spi=on' /boot/config.txt 2>/dev/null; then
  echo 'dtparam=spi=on' >> /boot/config.txt || true
fi
modprobe spi_bcm2835 || true

# Python deps (system-wide for simplicity)
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

echo "Install complete. Reboot recommended if SPI was just enabled."
