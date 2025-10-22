#!/usr/bin/env python3
"""
Minimal HID keepalive feeder for USB gadget hidg0.
- Opens /dev/hidg0 and writes periodic 8-byte input reports.
- Intended to maintain presence on host when the real device is unavailable.

WARNING: This is a generic demo. Emulating a commercial device's VID/PID,
strings, or security features may be restricted by law/license. Use responsibly.
"""
import os
import time
import signal
from typing import Optional

REPORT_SIZE = int(os.environ.get("REPORT_SIZE", "8"))
PERIOD = float(os.environ.get("PERIOD", "0.5"))  # seconds
HID_DEV = os.environ.get("HID_DEV", "/dev/hidg0")
FILL_HEX = os.environ.get("FILL_HEX", "00 00 00 00 00 00 00 00")


def parse_hex_bytes(s: str, size: int) -> bytes:
    parts = [p for p in s.replace(",", " ").split() if p]
    data = bytes(int(p, 16) for p in parts)
    if len(data) < size:
        data = data + bytes(size - len(data))
    return data[:size]


def main(argv: Optional[list[str]] = None) -> int:
    keep = parse_hex_bytes(FILL_HEX, REPORT_SIZE)

    # Open hidg0 non-blocking for write
    fd = os.open(HID_DEV, os.O_WRONLY | os.O_NONBLOCK)

    stop = False

    def handler(signum, frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)

    print(f"[hid_keepalive] Writing {REPORT_SIZE}-byte reports to {HID_DEV} every {PERIOD}s")
    while not stop:
        try:
            os.write(fd, keep)
        except BlockingIOError:
            pass
        except Exception as e:
            print(f"write error: {e}")
            time.sleep(PERIOD)
            continue
        time.sleep(PERIOD)
    os.close(fd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
