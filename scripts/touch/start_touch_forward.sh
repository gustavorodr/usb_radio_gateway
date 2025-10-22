#!/bin/bash
# Start touch forwarder on slave Pi (sends touch events via radio)

set -e

DEVICE="${TOUCH_DEVICE:-auto}"
MAX_X="${TOUCH_MAX_X:-4095}"
MAX_Y="${TOUCH_MAX_Y:-4095}"

cd "$(dirname "$0")/../.."

echo "[Touch Forward] Starting touchscreen forwarder (Slave)..."
echo "  Device: $DEVICE"
echo "  Resolution: ${MAX_X}x${MAX_Y}"

# Build command
CMD="python3 -m touch.touch_forward"
CMD="$CMD --max-x $MAX_X --max-y $MAX_Y"

if [ "$DEVICE" != "auto" ]; then
    CMD="$CMD --device $DEVICE"
fi

# For testing without radio
if [ "$TEST_MODE" = "1" ]; then
    CMD="$CMD --test"
    echo "  Mode: TEST (no radio)"
fi

echo ""
echo "Command: $CMD"
echo ""

exec $CMD
