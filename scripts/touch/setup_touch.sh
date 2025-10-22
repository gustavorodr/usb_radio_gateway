#!/bin/bash
# Setup uinput and evdev permissions for touchscreen forwarding

set -e

echo "[Touch Setup] Configuring uinput and evdev..."

# 1. Load uinput kernel module
echo "Loading uinput module..."
if ! lsmod | grep -q uinput; then
    sudo modprobe uinput
    echo "uinput" | sudo tee -a /etc/modules > /dev/null
    echo "✓ uinput module loaded and configured for auto-load"
else
    echo "✓ uinput module already loaded"
fi

# 2. Set permissions for /dev/uinput
echo "Setting /dev/uinput permissions..."
sudo chmod 0660 /dev/uinput
sudo chown root:input /dev/uinput

# Create udev rule for persistent permissions
UDEV_RULE="/etc/udev/rules.d/99-uinput.rules"
if [ ! -f "$UDEV_RULE" ]; then
    echo 'KERNEL=="uinput", MODE="0660", GROUP="input"' | sudo tee "$UDEV_RULE" > /dev/null
    sudo udevadm control --reload-rules
    echo "✓ Created udev rule: $UDEV_RULE"
else
    echo "✓ udev rule already exists"
fi

# 3. Add current user to input group
echo "Adding $USER to 'input' group..."
if ! groups $USER | grep -q input; then
    sudo usermod -a -G input $USER
    echo "✓ User added to 'input' group (logout/login required)"
else
    echo "✓ User already in 'input' group"
fi

# 4. Set permissions for evdev devices
echo "Setting /dev/input/event* permissions..."
sudo chmod 0660 /dev/input/event*
sudo chown root:input /dev/input/event*

# Create udev rule for evdev
EVDEV_RULE="/etc/udev/rules.d/99-input.rules"
if [ ! -f "$EVDEV_RULE" ]; then
    echo 'KERNEL=="event*", SUBSYSTEM=="input", MODE="0660", GROUP="input"' | sudo tee "$EVDEV_RULE" > /dev/null
    sudo udevadm control --reload-rules
    echo "✓ Created udev rule: $EVDEV_RULE"
else
    echo "✓ evdev rule already exists"
fi

# 5. Detect touchscreen devices
echo ""
echo "Detecting touchscreen devices..."
python3 << 'EOF'
import sys
sys.path.insert(0, '/home/gustavo/Documents/usb_radio_gateway/src')
from touch import find_touch_device
device = find_touch_device()
if device:
    print(f"✓ Found touchscreen: {device}")
else:
    print("⚠ No touchscreen device detected")
    print("  If you have a touchscreen, ensure drivers are loaded")
EOF

echo ""
echo "Setup complete!"
echo ""
echo "IMPORTANT: If you were added to 'input' group, you MUST logout and login"
echo "           for group changes to take effect!"
echo ""
echo "Test touch capture with:"
echo "  python3 -m touch.touch_capture"
echo ""
echo "Test touch injection with:"
echo "  python3 -m touch.touch_inject"
