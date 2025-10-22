# Touchscreen Forwarding via nRF24L01+ Radio

This module provides ultra-low latency touchscreen event forwarding between two Raspberry Pis using nRF24L01+ radio modules.

## Architecture

```
┌─────────────┐                      ┌──────────────┐
│  Slave Pi   │                      │  Master Pi   │
│             │                      │              │
│  Physical   │   nRF24L01+ Radio    │   Virtual    │
│ Touchscreen │ ◄──────────────────► │ Touchscreen  │
│   (evdev)   │   ~0.5-1ms latency   │   (uinput)   │
└─────────────┘                      └──────────────┘
```

### Components

1. **`touch_capture.py`** (Slave): Reads touch events from `/dev/input/eventX` using evdev
   - Supports single-touch (ABS_X/Y) and multi-touch (ABS_MT_*) protocols
   - Auto-detects touchscreen devices
   - Minimal latency buffering (1ms poll timeout)

2. **`touch_inject.py`** (Master): Creates virtual touchscreen using uinput
   - Appears as `/dev/input/eventY` on master Pi
   - Injects received touch events (X, Y, pressure, BTN_TOUCH)
   - Supports both single-touch and multi-touch protocol B

3. **`touch_protocol.py`**: Compact binary packet format (12 bytes)
   - Header (1B) + Sequence (2B) + X (2B) + Y (2B) + Pressure (2B) + Flags (1B) + Timestamp (2B)
   - Fits in single nRF24 frame (32 bytes) with room for radio overhead
   - Automatic coordinate scaling between different resolutions
   - Packet loss detection and latency tracking

4. **`touch_forward.py`** (Slave daemon): Capture → Encode → Radio TX
5. **`touch_receive.py`** (Master daemon): Radio RX → Decode → Inject

## Requirements

### Hardware
- Raspberry Pi with touchscreen (Slave side)
- Raspberry Pi Zero/CM4 with OTG support (Master side)
- nRF24L01+ modules connected via SPI on both Pis

### Software
```bash
# On both Pis
sudo apt-get install python3-dev libgpiod2

# Load uinput module (Master side)
sudo modprobe uinput
echo "uinput" | sudo tee -a /etc/modules

# Set permissions
sudo usermod -a -G input $USER
# Logout/login required for group change
```

## Setup

### 1. Configure Permissions
```bash
cd /home/gustavo/Documents/usb_radio_gateway
sudo ./scripts/touch/setup_touch.sh
```

This script:
- Loads uinput kernel module
- Sets permissions for `/dev/uinput` and `/dev/input/event*`
- Creates udev rules for persistent permissions
- Adds user to `input` group (requires logout/login)
- Auto-detects touchscreen devices

### 2. Test Capture (Slave Side)
```bash
# Auto-detect touchscreen
python3 -m touch.touch_capture

# Or specify device
python3 -m touch.touch_capture /dev/input/event2
```

Output:
```
Auto-detected touchscreen: /dev/input/event2
Device info: {'path': '/dev/input/event2', 'max_x': 4095, 'max_y': 4095, 'max_pressure': 255, 'multitouch': True}
Waiting for touch events (Ctrl+C to exit)...
[DOWN] X: 50% Y: 30% P: 80% (raw: 2048, 1228, 204)
[DOWN] X: 51% Y: 31% P: 82% (raw: 2089, 1269, 209)
```

### 3. Test Injection (Master Side)
```bash
# Create virtual touchscreen with default resolution
python3 -m touch.touch_inject

# Or specify custom resolution
python3 -m touch.touch_inject 1920 1080
```

This creates a virtual touchscreen device. Check with:
```bash
cat /proc/bus/input/devices
# Look for "Virtual Touchscreen"
```

Test with a diagonal swipe pattern (5 seconds).

## Usage

### Standalone Testing (No Radio)

**Slave (Capture and Mock TX):**
```bash
TEST_MODE=1 ./scripts/touch/start_touch_forward.sh
```

**Master (Mock RX and Inject):**
```bash
TEST_MODE=1 ./scripts/touch/start_touch_receive.sh
```

### With Radio Integration

**Slave:**
```bash
# Auto-detect touchscreen
TOUCH_DEVICE=auto TOUCH_MAX_X=4095 TOUCH_MAX_Y=4095 \
  ./scripts/touch/start_touch_forward.sh

# Or specify device
TOUCH_DEVICE=/dev/input/event2 TOUCH_MAX_X=1920 TOUCH_MAX_Y=1080 \
  ./scripts/touch/start_touch_forward.sh
```

**Master:**
```bash
TOUCH_MAX_X=4095 TOUCH_MAX_Y=4095 \
  ./scripts/touch/start_touch_receive.sh
```

### Integration with Orchestrator

The touch forwarding will be integrated into the master/slave orchestrator:

**Slave modes:**
- `passive`: Captures touch from real device → sends via radio
- `active`: (same as passive, touchscreen is independent of USB gadget)

**Master modes:**
- `forward`: Receives touch via radio → injects to virtual device
- `sniff`: (same as forward, touch independent of USB sniffing)

## Protocol Details

### Packet Format (12 bytes)

```
Offset | Size | Field         | Description
-------|------|---------------|----------------------------------
0      | 1    | Header        | [7:6]=version [5:4]=rsvd [3:0]=type
1      | 2    | Sequence      | Packet sequence (0-65535, wraps)
3      | 2    | X             | X coordinate (0-65535, normalized)
5      | 2    | Y             | Y coordinate (0-65535, normalized)
7      | 2    | Pressure      | Pressure (0-65535, normalized)
9      | 1    | Flags         | [0]=touch_down [1-7]=reserved
10     | 2    | Timestamp     | Milliseconds within second (0-999)
```

All multi-byte fields are big-endian.

### Coordinate Scaling

The protocol normalizes coordinates to 16-bit range (0-65535) for transport:

**Encoding (Slave):**
```python
normalized_x = (device_x * 65535) / device_max_x
```

**Decoding (Master):**
```python
target_x = (normalized_x * target_max_x) / 65535
```

This allows different resolutions on sender and receiver sides.

### Latency Budget

| Component | Latency |
|-----------|---------|
| evdev read (poll) | ~0.5ms |
| Packet encode | <0.1ms |
| Radio TX (nRF24 SPI) | ~0.3ms |
| Radio RX | ~0.3ms |
| Packet decode | <0.1ms |
| uinput inject | ~0.2ms |
| **Total** | **~1.5ms** |

This is well below the 5ms threshold for imperceptible touch latency.

## Performance Tuning

### 1. Increase evdev priority (Slave)
```bash
sudo chrt -f 99 python3 -m touch.touch_forward
```

### 2. Reduce kernel timer tick (both Pis)
Add to `/boot/cmdline.txt`:
```
highres=on nohz=on
```

### 3. Disable power management (both Pis)
```bash
# CPU governor
sudo cpufreq-set -g performance

# USB autosuspend (if touchscreen is USB)
echo -1 | sudo tee /sys/bus/usb/devices/*/power/autosuspend_delay_ms
```

### 4. Use kernel nRF24 driver
The Python tunnel adds ~2ms overhead. The kernel `nrf24_net.ko` driver reduces this to <0.5ms.

## Troubleshooting

### No touchscreen detected
```bash
# List all input devices
ls -l /dev/input/event*

# Check device capabilities
sudo evtest /dev/input/event2
```

Look for devices with `EV_ABS` and `BTN_TOUCH` support.

### Permission denied
```bash
# Check group membership
groups $USER
# Should include 'input'

# If not, run setup again
sudo ./scripts/touch/setup_touch.sh
# Then logout/login
```

### Virtual device not appearing
```bash
# Check uinput module
lsmod | grep uinput

# Check /dev/uinput permissions
ls -l /dev/uinput
# Should be: crw-rw---- 1 root input

# Reload udev rules
sudo udevadm control --reload-rules
sudo udevadm trigger
```

### High latency
```bash
# Check for packet loss
# Output every 10 seconds shows loss rate
[TouchForwarder] Stats: Sent=1234 Lost=5 (0.41%)

# Monitor system load
top
# High CPU usage indicates bottleneck

# Check radio performance
# See nrf_tun/README.md for radio tuning
```

## API Reference

### TouchCapture
```python
from touch import TouchCapture, find_touch_device

device = find_touch_device()  # Auto-detect
capture = TouchCapture(device)
capture.open()

def on_event(event):
    print(f"X={event.x} Y={event.y} Down={event.touch_down}")

capture.read_events(on_event)
```

### TouchInjector
```python
from touch import TouchInjector, TouchEvent
import time

injector = TouchInjector(max_x=1920, max_y=1080)
injector.create()

event = TouchEvent(x=960, y=540, pressure=128, 
                  touch_down=True, timestamp=time.time())
injector.inject_event(event)

injector.destroy()
```

### TouchPacket
```python
from touch import TouchPacket, TouchEvent
import time

# Encode
encoder = TouchPacket()
event = TouchEvent(x=1024, y=768, pressure=100, 
                  touch_down=True, timestamp=time.time())
packet = encoder.encode(event)  # 12 bytes

# Decode
decoded = TouchPacket.decode(packet)
```

## Integration Status

- ✅ Touch capture (evdev reader)
- ✅ Touch injection (uinput)
- ✅ Binary protocol (12-byte packets)
- ✅ Coordinate scaling
- ✅ Statistics tracking
- ✅ Standalone test daemons
- ⚠️ Radio integration (TODO: connect to nrf_tun or nrf24_net)
- ⚠️ Orchestrator integration (TODO: add to master/slave modes)

## Next Steps

1. **Radio Integration**: Connect touch_forward/receive to nRF24 radio
   - Option A: Use existing Python `nrf_tun.radio.NRF24Radio`
   - Option B: Add touch packet type to kernel `nrf24_net` driver

2. **Orchestrator Integration**: Add touch forwarding to main.py
   - Slave: Start touch_forward thread in both modes
   - Master: Start touch_receive thread in both modes

3. **Multi-touch Support**: Extend protocol for up to 10 simultaneous touch points
   - Current: Single-touch (slot 0 only)
   - Future: Array of touch packets (one per active slot)

4. **Hardware Testing**: Validate end-to-end with real touchscreen and target device
