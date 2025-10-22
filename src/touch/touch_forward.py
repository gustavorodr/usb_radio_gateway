"""
Touch forwarding daemon (Slave side)
Captures touchscreen events and forwards them via radio.
"""
import sys
import time
import signal
import argparse
from threading import Thread, Event
from queue import Queue, Empty

from touch import TouchCapture, find_touch_device, TouchEvent, ScaledTouchPacket, TouchStatistics


class TouchForwarder:
    """
    Captures touch events and forwards them via radio with minimal latency.
    Runs capture in dedicated thread to minimize latency.
    """
    
    def __init__(self, device_path: str, radio_send_callback, 
                 source_max_x: int = 4095, source_max_y: int = 4095):
        """
        Args:
            device_path: Path to evdev touchscreen device
            radio_send_callback: Function to call with encoded packet bytes
            source_max_x/y: Source touchscreen resolution
        """
        self.capture = TouchCapture(device_path)
        self.radio_send = radio_send_callback
        self.encoder = ScaledTouchPacket(
            source_max_x=source_max_x,
            source_max_y=source_max_y,
            source_max_pressure=255
        )
        self.stats = TouchStatistics()
        
        self.running = Event()
        self.capture_thread = None
        self.stats_thread = None
        
    def start(self):
        """Start touch capture and forwarding"""
        self.capture.open()
        self.running.set()
        
        # Start capture thread
        self.capture_thread = Thread(target=self._capture_loop, daemon=True)
        self.capture_thread.start()
        
        # Start stats reporting thread
        self.stats_thread = Thread(target=self._stats_loop, daemon=True)
        self.stats_thread.start()
        
        print("[TouchForwarder] Started")
    
    def stop(self):
        """Stop forwarding"""
        self.running.clear()
        if self.capture_thread:
            self.capture_thread.join(timeout=1.0)
        if self.stats_thread:
            self.stats_thread.join(timeout=1.0)
        self.capture.close()
        print("[TouchForwarder] Stopped")
    
    def _capture_loop(self):
        """Touch capture loop (runs in dedicated thread)"""
        def on_touch_event(event: TouchEvent):
            # Encode and send immediately (minimal latency path)
            packet = self.encoder.encode(event)
            self.radio_send(packet)
            self.stats.on_send()
        
        try:
            self.capture.read_events(on_touch_event, timeout=0.001)
        except Exception as e:
            print(f"[TouchForwarder] Capture error: {e}")
    
    def _stats_loop(self):
        """Periodic statistics reporting"""
        while self.running.is_set():
            time.sleep(10.0)
            stats = self.stats.get_stats()
            print(f"[TouchForwarder] Stats: Sent={stats['packets_sent']} "
                  f"Lost={stats['packets_lost']} ({stats['loss_rate_percent']:.2f}%)")


# Mock radio interface for testing
class MockRadio:
    """Simulates radio transmission for testing"""
    def __init__(self):
        self.packets_sent = 0
    
    def send(self, packet: bytes):
        self.packets_sent += 1
        # Simulate transmission time (< 1ms for nRF24)
        time.sleep(0.0005)


def main():
    parser = argparse.ArgumentParser(description="Touch forwarder (Slave)")
    parser.add_argument("--device", help="Touch device path (auto-detect if not provided)")
    parser.add_argument("--max-x", type=int, default=4095, help="Source max X coordinate")
    parser.add_argument("--max-y", type=int, default=4095, help="Source max Y coordinate")
    parser.add_argument("--test", action="store_true", help="Test mode (no radio)")
    args = parser.parse_args()
    
    # Find touch device
    device = args.device
    if not device:
        device = find_touch_device()
        if not device:
            print("ERROR: No touchscreen device found!")
            print("Try: sudo python3 -m touch.touch_forward --device /dev/input/eventX")
            return 1
        print(f"Auto-detected: {device}")
    
    # Setup radio (or mock for testing)
    if args.test:
        print("TEST MODE: Using mock radio")
        radio = MockRadio()
        radio_send = radio.send
    else:
        # TODO: Import real nRF24 radio interface
        print("ERROR: Real radio not implemented yet. Use --test for testing.")
        print("TODO: Import from nrf_tun.radio import NRF24Radio")
        return 1
    
    # Create and start forwarder
    forwarder = TouchForwarder(device, radio_send, args.max_x, args.max_y)
    
    # Signal handler for clean shutdown
    def signal_handler(sig, frame):
        print("\nShutting down...")
        forwarder.stop()
        if args.test:
            print(f"Mock radio: {radio.packets_sent} packets sent")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        forwarder.start()
        # Keep main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        forwarder.stop()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
