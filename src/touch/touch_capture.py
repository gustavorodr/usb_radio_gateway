"""
Touch screen capture module (Slave side)
Reads touchscreen events from /dev/input/eventX using evdev
and forwards them via radio with minimal latency (<1ms buffer).
"""
import struct
import select
import fcntl
import os
import time
from typing import Callable, Optional, Tuple
from dataclasses import dataclass


# Event input constants (from linux/input-event-codes.h)
EV_SYN = 0x00
EV_KEY = 0x01
EV_ABS = 0x03

SYN_REPORT = 0x00
BTN_TOUCH = 0x14a  # 330

ABS_X = 0x00
ABS_Y = 0x01
ABS_PRESSURE = 0x18  # 24
ABS_MT_SLOT = 0x2f  # 47
ABS_MT_POSITION_X = 0x35  # 53
ABS_MT_POSITION_Y = 0x36  # 54
ABS_MT_TRACKING_ID = 0x39  # 57
ABS_MT_PRESSURE = 0x3a  # 58

# Event structure: timeval (8 bytes) + type (2) + code (2) + value (4) = 16 bytes
EVENT_SIZE = 16
EVENT_FORMAT = 'llHHi'  # sec, usec, type, code, value


@dataclass
class TouchEvent:
    """Unified touch event representation"""
    x: int
    y: int
    pressure: int
    touch_down: bool  # True if finger down, False if lifted
    timestamp: float


class TouchCapture:
    """
    Captures touchscreen events from evdev device with ultra-low latency.
    Supports both single-touch (ABS_X/Y) and multi-touch (ABS_MT_*) protocols.
    """
    
    def __init__(self, device_path: str = "/dev/input/event0"):
        """
        Args:
            device_path: Path to evdev device (e.g., /dev/input/event2)
        """
        self.device_path = device_path
        self.fd = None
        self.running = False
        
        # Current touch state (accumulated from events until SYN_REPORT)
        self.current_x = 0
        self.current_y = 0
        self.current_pressure = 0
        self.current_touch = False
        self.has_changes = False
        
        # Multi-touch state
        self.current_slot = 0
        self.mt_slots = {}  # slot_id -> (x, y, pressure, tracking_id)
        
        # Device capabilities
        self.max_x = 4095
        self.max_y = 4095
        self.max_pressure = 255
        self.is_multitouch = False
        
    def open(self):
        """Open the evdev device and query capabilities"""
        try:
            self.fd = os.open(self.device_path, os.O_RDONLY | os.O_NONBLOCK)
            self._query_capabilities()
            self.running = True
            print(f"[TouchCapture] Opened {self.device_path}")
            print(f"[TouchCapture] Resolution: {self.max_x}x{self.max_y}, "
                  f"Pressure: 0-{self.max_pressure}, MT: {self.is_multitouch}")
        except (OSError, IOError) as e:
            raise RuntimeError(f"Failed to open touch device {self.device_path}: {e}")
    
    def _query_capabilities(self):
        """Query device capabilities using ioctl (EVIOCGABS)"""
        # EVIOCGABS(axis) = _IOR('E', 0x40 + axis, struct input_absinfo)
        # struct input_absinfo: value, min, max, fuzz, flat, resolution (6 ints = 24 bytes)
        EVIOCGABS = lambda axis: 0x80000000 | (24 << 16) | (ord('E') << 8) | (0x40 + axis)
        
        try:
            # Query ABS_X
            buf = bytearray(24)
            fcntl.ioctl(self.fd, EVIOCGABS(ABS_X), buf)
            _, _, self.max_x, _, _, _ = struct.unpack('iiiiii', buf)
            
            # Query ABS_Y
            buf = bytearray(24)
            fcntl.ioctl(self.fd, EVIOCGABS(ABS_Y), buf)
            _, _, self.max_y, _, _, _ = struct.unpack('iiiiii', buf)
            
            # Query ABS_PRESSURE (optional)
            try:
                buf = bytearray(24)
                fcntl.ioctl(self.fd, EVIOCGABS(ABS_PRESSURE), buf)
                _, _, self.max_pressure, _, _, _ = struct.unpack('iiiiii', buf)
            except OSError:
                self.max_pressure = 255  # Default if not supported
            
            # Check for multi-touch support (ABS_MT_POSITION_X)
            try:
                buf = bytearray(24)
                fcntl.ioctl(self.fd, EVIOCGABS(ABS_MT_POSITION_X), buf)
                self.is_multitouch = True
            except OSError:
                self.is_multitouch = False
                
        except OSError as e:
            print(f"[TouchCapture] Warning: Could not query all capabilities: {e}")
            # Use defaults
            pass
    
    def close(self):
        """Close the device"""
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        self.running = False
        print("[TouchCapture] Closed device")
    
    def read_events(self, callback: Callable[[TouchEvent], None], timeout: float = 0.001):
        """
        Read touch events with minimal latency and call callback on each complete event.
        
        Args:
            callback: Function to call with TouchEvent when SYN_REPORT received
            timeout: select() timeout in seconds (default 1ms for ultra-low latency)
        """
        if not self.running or self.fd is None:
            raise RuntimeError("Device not opened")
        
        poll = select.poll()
        poll.register(self.fd, select.POLLIN)
        
        while self.running:
            # Wait for events with minimal timeout
            events = poll.poll(int(timeout * 1000))  # Convert to milliseconds
            
            if not events:
                continue
            
            # Read all available events in one shot (reduces syscalls)
            try:
                data = os.read(self.fd, EVENT_SIZE * 64)  # Read up to 64 events
            except (OSError, IOError) as e:
                if e.errno == 11:  # EAGAIN - no data available
                    continue
                raise
            
            # Parse events
            num_events = len(data) // EVENT_SIZE
            for i in range(num_events):
                offset = i * EVENT_SIZE
                event_data = data[offset:offset + EVENT_SIZE]
                
                sec, usec, ev_type, ev_code, ev_value = struct.unpack(
                    EVENT_FORMAT, event_data
                )
                
                self._process_event(ev_type, ev_code, ev_value, callback, 
                                   timestamp=sec + usec / 1000000.0)
    
    def _process_event(self, ev_type: int, ev_code: int, ev_value: int,
                      callback: Callable[[TouchEvent], None], timestamp: float):
        """Process a single input event"""
        
        # EV_SYN: End of event frame - emit accumulated state
        if ev_type == EV_SYN and ev_code == SYN_REPORT:
            if self.has_changes:
                # For multi-touch, use primary slot (slot 0) or first active slot
                if self.is_multitouch and self.mt_slots:
                    if 0 in self.mt_slots:
                        slot = self.mt_slots[0]
                    else:
                        slot = list(self.mt_slots.values())[0]
                    
                    x, y, pressure, tracking_id = slot
                    touch_down = tracking_id >= 0
                else:
                    x = self.current_x
                    y = self.current_y
                    pressure = self.current_pressure
                    touch_down = self.current_touch
                
                event = TouchEvent(
                    x=x,
                    y=y,
                    pressure=pressure,
                    touch_down=touch_down,
                    timestamp=timestamp
                )
                callback(event)
                self.has_changes = False
        
        # EV_KEY: Button events (BTN_TOUCH)
        elif ev_type == EV_KEY:
            if ev_code == BTN_TOUCH:
                self.current_touch = (ev_value == 1)
                self.has_changes = True
        
        # EV_ABS: Absolute position events
        elif ev_type == EV_ABS:
            if ev_code == ABS_X:
                self.current_x = ev_value
                self.has_changes = True
            elif ev_code == ABS_Y:
                self.current_y = ev_value
                self.has_changes = True
            elif ev_code == ABS_PRESSURE:
                self.current_pressure = ev_value
                self.has_changes = True
            
            # Multi-touch protocol
            elif ev_code == ABS_MT_SLOT:
                self.current_slot = ev_value
                if self.current_slot not in self.mt_slots:
                    self.mt_slots[self.current_slot] = [0, 0, 0, -1]
            elif ev_code == ABS_MT_POSITION_X:
                if self.current_slot in self.mt_slots:
                    self.mt_slots[self.current_slot][0] = ev_value
                self.has_changes = True
            elif ev_code == ABS_MT_POSITION_Y:
                if self.current_slot in self.mt_slots:
                    self.mt_slots[self.current_slot][1] = ev_value
                self.has_changes = True
            elif ev_code == ABS_MT_PRESSURE:
                if self.current_slot in self.mt_slots:
                    self.mt_slots[self.current_slot][2] = ev_value
                self.has_changes = True
            elif ev_code == ABS_MT_TRACKING_ID:
                if self.current_slot in self.mt_slots:
                    self.mt_slots[self.current_slot][3] = ev_value
                    # Remove slot when finger lifted (tracking_id = -1)
                    if ev_value == -1 and self.current_slot in self.mt_slots:
                        del self.mt_slots[self.current_slot]
                self.has_changes = True
    
    def get_device_info(self) -> dict:
        """Return device capabilities"""
        return {
            "path": self.device_path,
            "max_x": self.max_x,
            "max_y": self.max_y,
            "max_pressure": self.max_pressure,
            "multitouch": self.is_multitouch
        }


def find_touch_device() -> Optional[str]:
    """
    Auto-detect touchscreen device by searching /dev/input/event* for devices
    that support ABS_X, ABS_Y, and BTN_TOUCH.
    
    Returns:
        Device path (e.g., "/dev/input/event2") or None if not found
    """
    import glob
    
    # EVIOCGBIT(ev, len) = _IOC(_IOC_READ, 'E', 0x20 + ev, len)
    EVIOCGBIT = lambda ev, length: (0x80000000 | ((length & 0x1fff) << 16) | 
                                    (ord('E') << 8) | (0x20 + ev))
    
    for device_path in sorted(glob.glob("/dev/input/event*")):
        try:
            fd = os.open(device_path, os.O_RDONLY)
            
            # Check for EV_ABS support (bit 3)
            ev_bits = bytearray(4)
            fcntl.ioctl(fd, EVIOCGBIT(0, 4), ev_bits)
            has_abs = (ev_bits[0] & (1 << EV_ABS)) != 0
            
            # Check for EV_KEY support (bit 1)
            has_key = (ev_bits[0] & (1 << EV_KEY)) != 0
            
            if has_abs and has_key:
                # Check for BTN_TOUCH (bit 330 in KEY bits)
                key_bits = bytearray(64)
                fcntl.ioctl(fd, EVIOCGBIT(EV_KEY, 64), key_bits)
                byte_idx = BTN_TOUCH // 8
                bit_idx = BTN_TOUCH % 8
                has_btn_touch = (key_bits[byte_idx] & (1 << bit_idx)) != 0
                
                # Check for ABS_X and ABS_Y
                abs_bits = bytearray(8)
                fcntl.ioctl(fd, EVIOCGBIT(EV_ABS, 8), abs_bits)
                has_abs_x = (abs_bits[ABS_X // 8] & (1 << (ABS_X % 8))) != 0
                has_abs_y = (abs_bits[ABS_Y // 8] & (1 << (ABS_Y % 8))) != 0
                
                os.close(fd)
                
                if has_btn_touch and has_abs_x and has_abs_y:
                    return device_path
            else:
                os.close(fd)
                
        except (OSError, IOError):
            continue
    
    return None


if __name__ == "__main__":
    """Test touchscreen capture"""
    import sys
    
    # Auto-detect or use provided path
    if len(sys.argv) > 1:
        device = sys.argv[1]
    else:
        device = find_touch_device()
        if device is None:
            print("ERROR: No touchscreen device found!")
            print("Usage: python3 -m touch.touch_capture [/dev/input/eventX]")
            sys.exit(1)
        print(f"Auto-detected touchscreen: {device}")
    
    capture = TouchCapture(device)
    
    try:
        capture.open()
        info = capture.get_device_info()
        print(f"Device info: {info}")
        print("Waiting for touch events (Ctrl+C to exit)...")
        
        def print_event(event: TouchEvent):
            status = "DOWN" if event.touch_down else "UP  "
            # Normalize to 0-100% for display
            x_pct = (event.x * 100) // capture.max_x
            y_pct = (event.y * 100) // capture.max_y
            p_pct = (event.pressure * 100) // max(capture.max_pressure, 1)
            print(f"[{status}] X:{x_pct:3d}% Y:{y_pct:3d}% P:{p_pct:3d}% "
                  f"(raw: {event.x}, {event.y}, {event.pressure})")
        
        capture.read_events(print_event)
        
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        capture.close()
