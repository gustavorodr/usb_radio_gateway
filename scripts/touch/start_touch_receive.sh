#!/bin/bash
# Start touch receiver on master Pi (receives and injects touch events)

set -e

MAX_X="${TOUCH_MAX_X:-4095}"
MAX_Y="${TOUCH_MAX_Y:-4095}"

cd "$(dirname "$0")/../.."

echo "[Touch Receive] Starting touch receiver (Master)..."
echo "  Virtual device resolution: ${MAX_X}x${MAX_Y}"

# Build command
CMD="python3 -m touch.touch_receive"
CMD="$CMD --max-x $MAX_X --max-y $MAX_Y"

# For testing without radio
if [ "$TEST_MODE" = "1" ]; then
    CMD="$CMD --test"
    echo "  Mode: TEST (simulated swipe)"
fi

echo ""
echo "Command: $CMD"
echo ""

exec $CMD
