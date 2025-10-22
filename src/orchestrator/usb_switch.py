#!/usr/bin/env python3
"""
USB hardware switch GPIO controller.
Toggles relay/optocoupler to route USB D+/D- between:
  - Passive: real sensor <-> target board (Pi monitors via separate USB host port)
  - Active: Pi USB gadget <-> target board

Example wiring (conceptual):
  - GPIO_PIN high: relay connects Pi gadget port to board USB
  - GPIO_PIN low: relay connects sensor USB to board USB (passthrough)
"""
import argparse
import sys
import time
from typing import Optional

try:
    import RPi.GPIO as GPIO
except ImportError:
    print("RPi.GPIO not available; using mock", file=sys.stderr)
    GPIO = None


class USBSwitch:
    def __init__(self, gpio_pin: int, active_high: bool = True):
        self.gpio_pin = gpio_pin
        self.active_high = active_high
        if GPIO:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.gpio_pin, GPIO.OUT)
        self.set_mode("passive")

    def set_mode(self, mode: str):
        """
        mode: 'active' or 'passive'
        """
        if mode == "active":
            state = GPIO.HIGH if self.active_high else GPIO.LOW
        else:
            state = GPIO.LOW if self.active_high else GPIO.HIGH
        if GPIO:
            GPIO.output(self.gpio_pin, state)
        print(f"[usb_switch] Set to {mode} (GPIO {self.gpio_pin} = {state})")

    def cleanup(self):
        if GPIO:
            GPIO.cleanup()


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="USB hardware switch control")
    p.add_argument("--gpio", type=int, required=True, help="GPIO pin (BCM)")
    p.add_argument("--mode", choices=["active", "passive"], required=True)
    p.add_argument("--active-high", action="store_true", help="Active mode = GPIO HIGH")
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    sw = USBSwitch(args.gpio, args.active_high)
    sw.set_mode(args.mode)
    time.sleep(0.1)
    sw.cleanup()
    return 0


if __name__ == "__main__":
    sys.exit(main())
