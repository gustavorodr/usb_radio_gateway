#!/usr/bin/env bash
set -euo pipefail
# Enable USB gadget (OTG) mode on Raspberry Pi (Zero/Zero2/CM/CM4 with OTG-capable port)
# Requires reboot to take effect.

if [[ $EUID -ne 0 ]]; then
  echo "Run as root (sudo)." >&2
  exit 1
fi

# Enable dwc2 and libcomposite
if ! grep -q '^dtoverlay=dwc2' /boot/config.txt 2>/dev/null; then
  echo 'dtoverlay=dwc2' >> /boot/config.txt || true
fi
if ! grep -q '^dwc2' /etc/modules 2>/dev/null; then
  echo 'dwc2' >> /etc/modules
fi
if ! grep -q '^libcomposite' /etc/modules 2>/dev/null; then
  echo 'libcomposite' >> /etc/modules
fi

echo "OTG enabled. Reboot required."
