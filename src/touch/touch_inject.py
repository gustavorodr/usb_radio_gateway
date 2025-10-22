"""
Touch screen injection module (Master side)
Creates a virtual touchscreen device using uinput and injects touch events
received from radio with minimal latency.
"""
import struct
import fcntl
import os
import time
from typing import Optional
from dataclasses import dataclass


# Input event constants
EV_SYN = 0x00
EV_KEY = 0x01
EV_ABS = 0x03

SYN_REPORT = 0x00
SYN_CONFIG = 0x01
SYN_MT_REPORT = 0x02

BTN_TOUCH = 0x14a  # 330

ABS_X = 0x00
ABS_Y = 0x01
ABS_PRESSURE = 0x18

# Multi-touch protocol B
ABS_MT_SLOT = 0x2f
ABS_MT_POSITION_X = 0x35
ABS_MT_POSITION_Y = 0x36
ABS_MT_TRACKING_ID = 0x39
ABS_MT_PRESSURE = 0x3a

# ioctl constants
UI_SET_EVBIT = 0x40045564
UI_SET_KEYBIT = 0x40045565
UI_SET_ABSBIT = 0x40045567
UI_DEV_CREATE = 0x5501
UI_DEV_DESTROY = 0x5502

# struct input_absinfo
INPUT_ABSINFO_SIZE = 24


@dataclass
class TouchEvent:
    """Touch event (matches touch_capture.TouchEvent)"""
    x: int
    y: int
    pressure: int
    touch_down: bool
    timestamp: float


class TouchInjector:
    """
    Creates a virtual touchscreen device using uinput and injects touch events.
    The virtual device appears as /dev/input/eventX on the host system.
    """
    
    def __init__(self, name: str = "Virtual Touchscreen", 
                 max_x: int = 4095, max_y: int = 4095, max_pressure: int = 255):
        """
        Args:
            name: Device name as shown in /proc/bus/input/devices
            max_x: Maximum X coordinate (resolution)
            max_y: Maximum Y coordinate (resolution)
            max_pressure: Maximum pressure value
        """
        self.name = name
        self.max_x = max_x
        self.max_y = max_y
        self.max_pressure = max_pressure
        self.fd = None
        self.active = False
        self.last_tracking_id = 0
        
    def create(self):
        """Create the virtual uinput device"""
        try:
            # Open uinput device
            self.fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
            
            # Enable event types
            fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_KEY)
            fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_ABS)
            fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_SYN)
            
            # Enable BTN_TOUCH
            fcntl.ioctl(self.fd, UI_SET_KEYBIT, BTN_TOUCH)
            
            # Enable absolute axes
            fcntl.ioctl(self.fd, UI_SET_ABSBIT, ABS_X)
            fcntl.ioctl(self.fd, UI_SET_ABSBIT, ABS_Y)
            fcntl.ioctl(self.fd, UI_SET_ABSBIT, ABS_PRESSURE)
            
            # Enable multi-touch protocol B axes
            fcntl.ioctl(self.fd, UI_SET_ABSBIT, ABS_MT_SLOT)
            fcntl.ioctl(self.fd, UI_SET_ABSBIT, ABS_MT_POSITION_X)
            fcntl.ioctl(self.fd, UI_SET_ABSBIT, ABS_MT_POSITION_Y)
            fcntl.ioctl(self.fd, UI_SET_ABSBIT, ABS_MT_TRACKING_ID)
            fcntl.ioctl(self.fd, UI_SET_ABSBIT, ABS_MT_PRESSURE)
            
            # Create uinput_user_dev structure (276 bytes in older kernels, 1116 in newer)
            # For compatibility, use the newer UI_DEV_SETUP ioctl if available,
            # otherwise fall back to write()
            
            # Try modern UI_DEV_SETUP (kernel 4.5+)
            UI_DEV_SETUP = 0x405c5503  # _IOW(UINPUT_IOCTL_BASE, 3, struct uinput_setup)
            
            # struct uinput_setup: id (8), name (80), ff_effects_max (4) = 92 bytes
            setup_struct = struct.pack(
                'HHIIIIIIIHHxxx' + '80s' + 'I',  # bustype, vendor, product, version + name + ff_effects_max
                0x03,  # BUS_USB
                0x1234,  # Vendor ID
                0x5678,  # Product ID
                1,  # Version
                0, 0, 0, 0, 0, 0, 0,  # id.padding
                self.name.encode('utf-8')[:80],
                0  # ff_effects_max
            )
            
            try:
                fcntl.ioctl(self.fd, UI_DEV_SETUP, setup_struct)
                use_modern = True
            except OSError:
                use_modern = False
            
            if use_modern:
                # Set up abs info using UI_ABS_SETUP
                UI_ABS_SETUP = 0x401c5504  # _IOW(UINPUT_IOCTL_BASE, 4, struct uinput_abs_setup)
                
                def setup_abs(code: int, minimum: int, maximum: int):
                    # struct uinput_abs_setup: code (2) + padding (2) + absinfo (24) = 28 bytes
                    abs_setup = struct.pack(
                        'HHiiiiii',
                        code, 0,  # code, padding
                        0, minimum, maximum,  # value, min, max
                        0, 0, 0  # fuzz, flat, resolution
                    )
                    fcntl.ioctl(self.fd, UI_ABS_SETUP, abs_setup)
                
                setup_abs(ABS_X, 0, self.max_x)
                setup_abs(ABS_Y, 0, self.max_y)
                setup_abs(ABS_PRESSURE, 0, self.max_pressure)
                setup_abs(ABS_MT_SLOT, 0, 9)  # Support 10 touch points
                setup_abs(ABS_MT_POSITION_X, 0, self.max_x)
                setup_abs(ABS_MT_POSITION_Y, 0, self.max_y)
                setup_abs(ABS_MT_TRACKING_ID, 0, 65535)
                setup_abs(ABS_MT_PRESSURE, 0, self.max_pressure)
                
                # Create device
                fcntl.ioctl(self.fd, UI_DEV_CREATE)
                
            else:
                # Fallback: legacy write() method (kernel < 4.5)
                # struct uinput_user_dev (276 bytes)
                dev_struct = struct.pack('80sHHHH', 
                                        self.name.encode('utf-8')[:80],
                                        0x03,  # BUS_USB
                                        0x1234,  # vendor
                                        0x5678,  # product
                                        1)  # version
                
                # Add padding to reach 276 bytes (80 + 8 + 64*4 = 344, but actual is 276)
                # absmax[64], absmin[64], absfuzz[64], absflat[64] = 256 bytes
                absmax = [0] * 64
                absmin = [0] * 64
                absfuzz = [0] * 64
                absflat = [0] * 64
                
                absmax[ABS_X] = self.max_x
                absmax[ABS_Y] = self.max_y
                absmax[ABS_PRESSURE] = self.max_pressure
                absmax[ABS_MT_SLOT] = 9
                absmax[ABS_MT_POSITION_X] = self.max_x
                absmax[ABS_MT_POSITION_Y] = self.max_y
                absmax[ABS_MT_TRACKING_ID] = 65535
                absmax[ABS_MT_PRESSURE] = self.max_pressure
                
                for val in absmax + absmin + absfuzz + absflat:
                    dev_struct += struct.pack('i', val)
                
                os.write(self.fd, dev_struct)
                fcntl.ioctl(self.fd, UI_DEV_CREATE)
            
            # Wait for device creation
            time.sleep(0.1)
            
            self.active = True
            print(f"[TouchInjector] Created virtual touchscreen '{self.name}'")
            print(f"[TouchInjector] Resolution: {self.max_x}x{self.max_y}, "
                  f"Pressure: 0-{self.max_pressure}")
            
        except (OSError, IOError) as e:
            if self.fd is not None:
                os.close(self.fd)
                self.fd = None
            raise RuntimeError(f"Failed to create uinput device: {e}")
    
    def destroy(self):
        """Destroy the virtual device"""
        if self.fd is not None:
            try:
                fcntl.ioctl(self.fd, UI_DEV_DESTROY)
            except OSError:
                pass
            os.close(self.fd)
            self.fd = None
        self.active = False
        print("[TouchInjector] Destroyed virtual device")
    
    def inject_event(self, event: TouchEvent):
        """
        Inject a touch event into the virtual device.
        
        Args:
            event: TouchEvent to inject
        """
        if not self.active or self.fd is None:
            raise RuntimeError("Device not created")
        
        # Clamp coordinates to device range
        x = max(0, min(event.x, self.max_x))
        y = max(0, min(event.y, self.max_y))
        pressure = max(0, min(event.pressure, self.max_pressure))
        
        # Send events in order:
        # 1. Multi-touch slot and tracking ID
        # 2. Multi-touch position and pressure
        # 3. Legacy single-touch position and pressure
        # 4. BTN_TOUCH
        # 5. SYN_REPORT
        
        if event.touch_down:
            # Finger down
            tracking_id = self.last_tracking_id
            self.last_tracking_id = (self.last_tracking_id + 1) % 65536
            
            # Multi-touch protocol B (slot 0)
            self._write_event(EV_ABS, ABS_MT_SLOT, 0)
            self._write_event(EV_ABS, ABS_MT_TRACKING_ID, tracking_id)
            self._write_event(EV_ABS, ABS_MT_POSITION_X, x)
            self._write_event(EV_ABS, ABS_MT_POSITION_Y, y)
            if pressure > 0:
                self._write_event(EV_ABS, ABS_MT_PRESSURE, pressure)
            
            # Legacy single-touch
            self._write_event(EV_ABS, ABS_X, x)
            self._write_event(EV_ABS, ABS_Y, y)
            if pressure > 0:
                self._write_event(EV_ABS, ABS_PRESSURE, pressure)
            
            self._write_event(EV_KEY, BTN_TOUCH, 1)
            
        else:
            # Finger up
            self._write_event(EV_ABS, ABS_MT_SLOT, 0)
            self._write_event(EV_ABS, ABS_MT_TRACKING_ID, -1)
            self._write_event(EV_KEY, BTN_TOUCH, 0)
        
        # Synchronize
        self._write_event(EV_SYN, SYN_REPORT, 0)
    
    def _write_event(self, ev_type: int, ev_code: int, ev_value: int):
        """Write a single input event to uinput device"""
        # struct input_event: timeval (16 bytes) + type (2) + code (2) + value (4) = 24 bytes
        # On 64-bit systems, timeval is 16 bytes (long long sec + long long usec)
        event = struct.pack('QQHHi', 0, 0, ev_type, ev_code, ev_value)
        os.write(self.fd, event)


if __name__ == "__main__":
    """Test virtual touchscreen creation and event injection"""
    import sys
    
    # Parse resolution from command line
    max_x = int(sys.argv[1]) if len(sys.argv) > 1 else 4095
    max_y = int(sys.argv[2]) if len(sys.argv) > 2 else 4095
    
    injector = TouchInjector(max_x=max_x, max_y=max_y)
    
    try:
        injector.create()
        print("Virtual touchscreen created. Check /proc/bus/input/devices")
        print("Injecting test pattern (5 seconds)...")
        
        # Inject a diagonal swipe
        steps = 50
        for i in range(steps):
            x = int((i * max_x) / steps)
            y = int((i * max_y) / steps)
            pressure = 128
            
            event = TouchEvent(
                x=x,
                y=y,
                pressure=pressure,
                touch_down=True,
                timestamp=time.time()
            )
            injector.inject_event(event)
            time.sleep(0.1)
        
        # Lift finger
        event = TouchEvent(x=max_x, y=max_y, pressure=0, touch_down=False, 
                          timestamp=time.time())
        injector.inject_event(event)
        
        print("Test complete. Device will remain active for 5 seconds...")
        time.sleep(5)
        
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        injector.destroy()
