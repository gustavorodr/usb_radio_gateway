"""
Touch receiver daemon (Master side)
Receives touch packets via radio and injects them into virtual touchscreen.
"""
import sys
import time
import signal
import argparse
from threading import Thread, Event
from queue import Queue, Full

from touch import TouchInjector, TouchEvent, ScaledTouchPacket, TouchStatistics


class TouchReceiver:
    """
    Receives touch packets from radio and injects into virtual touchscreen.
    Uses queue to decouple radio reception from uinput injection.
    """
    
    def __init__(self, radio_receive_callback,
                 target_max_x: int = 4095, target_max_y: int = 4095,
                 queue_size: int = 32):
        """
        Args:
            radio_receive_callback: Function to call repeatedly to get packets
            target_max_x/y: Target virtual device resolution
            queue_size: Max packets to buffer (keep small for low latency)
        """
        self.radio_receive = radio_receive_callback
        self.injector = TouchInjector(
            name="Virtual Touchscreen (Radio)",
            max_x=target_max_x,
            max_y=target_max_y
        )
        self.decoder = ScaledTouchPacket(
            target_max_x=target_max_x,
            target_max_y=target_max_y,
            target_max_pressure=255
        )
        self.stats = TouchStatistics()
        
        self.packet_queue = Queue(maxsize=queue_size)
        self.running = Event()
        self.receive_thread = None
        self.inject_thread = None
        self.stats_thread = None
        
    def start(self):
        """Start receiver and injector"""
        self.injector.create()
        self.running.set()
        
        # Start receive thread (radio -> queue)
        self.receive_thread = Thread(target=self._receive_loop, daemon=True)
        self.receive_thread.start()
        
        # Start inject thread (queue -> uinput)
        self.inject_thread = Thread(target=self._inject_loop, daemon=True)
        self.inject_thread.start()
        
        # Start stats thread
        self.stats_thread = Thread(target=self._stats_loop, daemon=True)
        self.stats_thread.start()
        
        print("[TouchReceiver] Started")
    
    def stop(self):
        """Stop receiver"""
        self.running.clear()
        if self.receive_thread:
            self.receive_thread.join(timeout=1.0)
        if self.inject_thread:
            self.inject_thread.join(timeout=1.0)
        if self.stats_thread:
            self.stats_thread.join(timeout=1.0)
        self.injector.destroy()
        print("[TouchReceiver] Stopped")
    
    def _receive_loop(self):
        """Radio reception loop"""
        while self.running.is_set():
            try:
                # Get packet from radio (blocking or timeout)
                packet = self.radio_receive(timeout=0.01)
                if packet:
                    # Decode packet
                    event = self.decoder.decode(packet)
                    if event:
                        # Add to queue (drop if full to maintain low latency)
                        try:
                            self.packet_queue.put_nowait((event, time.time()))
                        except Full:
                            print("[TouchReceiver] Warning: Queue full, dropping packet")
            except Exception as e:
                if self.running.is_set():
                    print(f"[TouchReceiver] Receive error: {e}")
                time.sleep(0.001)
    
    def _inject_loop(self):
        """Touch injection loop"""
        while self.running.is_set():
            try:
                # Get event from queue (with timeout)
                event, recv_time = self.packet_queue.get(timeout=0.01)
                
                # Inject into virtual device
                self.injector.inject_event(event)
                
                # Update statistics
                # Note: We don't have sequence number here, would need to extract from packet
                # For now, just count received
                self.stats.packets_received += 1
                
            except Exception as e:
                if self.running.is_set() and "Empty" not in str(e):
                    print(f"[TouchReceiver] Inject error: {e}")
    
    def _stats_loop(self):
        """Periodic statistics reporting"""
        while self.running.is_set():
            time.sleep(10.0)
            print(f"[TouchReceiver] Stats: Received={self.stats.packets_received} "
                  f"Injected={self.stats.packets_received} "
                  f"QueueSize={self.packet_queue.qsize()}")


# Mock radio interface for testing
class MockRadio:
    """Simulates radio reception for testing"""
    def __init__(self):
        self.test_packets = []
        self.current_idx = 0
    
    def add_test_packet(self, packet: bytes):
        self.test_packets.append(packet)
    
    def receive(self, timeout: float = 0.01) -> bytes:
        if self.current_idx < len(self.test_packets):
            packet = self.test_packets[self.current_idx]
            self.current_idx += 1
            time.sleep(0.01)  # Simulate reception delay
            return packet
        time.sleep(timeout)
        return None


def main():
    parser = argparse.ArgumentParser(description="Touch receiver (Master)")
    parser.add_argument("--max-x", type=int, default=4095, help="Target max X coordinate")
    parser.add_argument("--max-y", type=int, default=4095, help="Target max Y coordinate")
    parser.add_argument("--test", action="store_true", help="Test mode (no radio)")
    args = parser.parse_args()
    
    # Setup radio (or mock for testing)
    if args.test:
        print("TEST MODE: Using mock radio with simulated diagonal swipe")
        radio = MockRadio()
        
        # Generate test packets (diagonal swipe)
        from touch.touch_protocol import TouchPacket
        encoder = TouchPacket()
        for i in range(50):
            x = int((i * 4095) / 50)
            y = int((i * 4095) / 50)
            event = TouchEvent(x=x, y=y, pressure=128, touch_down=True, 
                              timestamp=time.time())
            packet = encoder.encode(event)
            radio.add_test_packet(packet)
        
        # Add finger up
        event = TouchEvent(x=4095, y=4095, pressure=0, touch_down=False,
                          timestamp=time.time())
        packet = encoder.encode(event)
        radio.add_test_packet(packet)
        
        radio_receive = radio.receive
    else:
        # TODO: Import real nRF24 radio interface
        print("ERROR: Real radio not implemented yet. Use --test for testing.")
        print("TODO: Import from nrf_tun.radio import NRF24Radio")
        return 1
    
    # Create and start receiver
    receiver = TouchReceiver(radio_receive, args.max_x, args.max_y)
    
    # Signal handler for clean shutdown
    def signal_handler(sig, frame):
        print("\nShutting down...")
        receiver.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        receiver.start()
        print("Virtual touchscreen active. Check with: cat /proc/bus/input/devices")
        if args.test:
            print("Test will inject 51 touch events over 5 seconds...")
        # Keep main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        receiver.stop()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
