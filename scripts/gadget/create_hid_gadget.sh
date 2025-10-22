#!/usr/bin/env bash
set -euo pipefail
# Create a generic USB HID gadget via ConfigFS
# NOTE: For a production clone of a specific device, you must use your own VID/PID and legal approvals.

if [[ $EUID -ne 0 ]]; then
  echo "Run as root (sudo)." >&2
  exit 1
fi

GADGET=/sys/kernel/config/usb_gadget/dp_hid
VID=${VID:-0x1d6b}   # default Linux Foundation (placeholder!)
PID=${PID:-0x0104}   # placeholder HID-like pid
SER=${SER:-"0001"}
MANUF=${MANUF:-"Demo"}
PROD=${PROD:-"HID Keepalive"}
UDC=$(ls /sys/class/udc | head -n1)

# HID report descriptor (simple 8-byte input report placeholder)
REPORT_DESC_HEX=${REPORT_DESC_HEX:-'05 01 09 00 A1 01 15 00 26 FF 00 75 08 95 08 09 00 81 82 C0'}
# Above: Generic vendor page, 8-byte input report; adjust to match your device.

modprobe libcomposite || true
mkdir -p /sys/kernel/config/usb_gadget || true

# Cleanup if exists
if [[ -d $GADGET ]]; then
  echo "Removing previous gadget ..."
  ( echo "" > "$GADGET/UDC" 2>/dev/null || true )
  rm -rf "$GADGET" || true
fi

mkdir -p "$GADGET"
cd "$GADGET"

echo $VID > idVendor
echo $PID > idProduct
echo 0x0200 > bcdUSB
mkdir -p strings/0x409

echo "$SER"   > strings/0x409/serialnumber
echo "$MANUF" > strings/0x409/manufacturer
echo "$PROD"  > strings/0x409/product

# Configuration
mkdir -p configs/c.1
mkdir -p configs/c.1/strings/0x409
echo "Config 1" > configs/c.1/strings/0x409/configuration
echo 120 > configs/c.1/MaxPower

# HID function
mkdir -p functions/hid.usb0
echo 1 > functions/hid.usb0/protocol
# 0 = None, 1 = Keyboard; use 0 for vendor HID; adjust as needed

echo 0 > functions/hid.usb0/subclass
# report_length must match your report size (8 here)
echo 8 > functions/hid.usb0/report_length

# Create report_desc from hex
python3 - "$REPORT_DESC_HEX" <<'PY'
import sys, binascii
hexs = sys.argv[1].split()
with open('functions/hid.usb0/report_desc', 'wb') as f:
    f.write(bytes(int(x,16) for x in hexs))
PY

ln -s functions/hid.usb0 configs/c.1/

echo "$UDC" > UDC

echo "HID gadget created and bound to $UDC. Device should enumerate on the host."
