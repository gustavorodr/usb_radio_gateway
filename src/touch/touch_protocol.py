"""
Touch packet protocol for ultra-low latency radio transmission.
Compact binary format optimized for nRF24L01+ 32-byte frames.
"""
import struct
from enum import IntEnum
from dataclasses import dataclass
from typing import Optional


class PacketType(IntEnum):
    """Packet type identifiers"""
    TOUCH = 0x01      # Touch event (high priority)
    USB = 0x02        # USB data (medium priority)
    CONTROL = 0x03    # Control command (high priority)
    ACK = 0x04        # Acknowledgment
    HEARTBEAT = 0x05  # Keep-alive ping


@dataclass
class TouchEvent:
    """Touch event data"""
    x: int
    y: int
    pressure: int
    touch_down: bool
    timestamp: float


class TouchPacket:
    """
    Ultra-compact touch packet for minimal latency.
    
    Format (12 bytes total):
    - Header (1 byte): [7:6]=version(0) [5:4]=reserved [3:0]=packet_type(TOUCH)
    - Sequence (2 bytes): Packet sequence number for loss detection
    - X coordinate (2 bytes): 0-65535 (scaled from device resolution)
    - Y coordinate (2 bytes): 0-65535 (scaled from device resolution)
    - Pressure (2 bytes): 0-65535 (scaled from device resolution)
    - Flags (1 byte): [0]=touch_down, [1-7]=reserved
    - Timestamp (2 bytes): Milliseconds since last second (0-999)
    
    This format fits comfortably in a single nRF24L01 frame (32 bytes),
    leaving 20 bytes for radio overhead/future expansion.
    """
    
    VERSION = 0
    HEADER_SIZE = 12
    
    def __init__(self):
        self.sequence = 0
    
    def encode(self, event: TouchEvent) -> bytes:
        """
        Encode a TouchEvent into binary packet.
        
        Args:
            event: TouchEvent to encode
            
        Returns:
            12-byte binary packet
        """
        # Header byte: version(2) + reserved(2) + packet_type(4)
        header = (self.VERSION << 6) | PacketType.TOUCH
        
        # Sequence number (wraps at 65536)
        seq = self.sequence
        self.sequence = (self.sequence + 1) & 0xFFFF
        
        # Coordinates and pressure (unsigned 16-bit)
        x = event.x & 0xFFFF
        y = event.y & 0xFFFF
        pressure = event.pressure & 0xFFFF
        
        # Flags byte
        flags = 0x01 if event.touch_down else 0x00
        
        # Timestamp: milliseconds within current second (0-999)
        timestamp_ms = int((event.timestamp % 1.0) * 1000) & 0xFFFF
        
        # Pack into struct
        packet = struct.pack(
            '>BHHHHBH',  # Big-endian: B=byte, H=ushort
            header,
            seq,
            x,
            y,
            pressure,
            flags,
            timestamp_ms
        )
        
        return packet
    
    @staticmethod
    def decode(packet: bytes) -> Optional[TouchEvent]:
        """
        Decode binary packet into TouchEvent.
        
        Args:
            packet: 12-byte binary packet
            
        Returns:
            TouchEvent or None if invalid
        """
        if len(packet) < TouchPacket.HEADER_SIZE:
            return None
        
        try:
            header, seq, x, y, pressure, flags, timestamp_ms = struct.unpack(
                '>BHHHHBH',
                packet[:TouchPacket.HEADER_SIZE]
            )
            
            # Validate header
            version = (header >> 6) & 0x03
            packet_type = header & 0x0F
            
            if version != TouchPacket.VERSION or packet_type != PacketType.TOUCH:
                return None
            
            # Extract touch_down flag
            touch_down = (flags & 0x01) != 0
            
            # Reconstruct approximate timestamp (we don't have full seconds)
            # Use current time's second + received milliseconds
            import time
            current_time = time.time()
            base_seconds = int(current_time)
            timestamp = base_seconds + (timestamp_ms / 1000.0)
            
            return TouchEvent(
                x=x,
                y=y,
                pressure=pressure,
                touch_down=touch_down,
                timestamp=timestamp
            )
            
        except struct.error:
            return None


class ScaledTouchPacket(TouchPacket):
    """
    Touch packet with automatic coordinate scaling.
    Allows different resolutions on sender and receiver sides.
    """
    
    def __init__(self, source_max_x: int = 4095, source_max_y: int = 4095,
                 source_max_pressure: int = 255,
                 target_max_x: int = 4095, target_max_y: int = 4095,
                 target_max_pressure: int = 255):
        """
        Args:
            source_max_x/y/pressure: Source device resolution
            target_max_x/y/pressure: Target device resolution
        """
        super().__init__()
        self.source_max_x = source_max_x
        self.source_max_y = source_max_y
        self.source_max_pressure = source_max_pressure
        self.target_max_x = target_max_x
        self.target_max_y = target_max_y
        self.target_max_pressure = target_max_pressure
    
    def encode(self, event: TouchEvent) -> bytes:
        """Encode with normalization to 16-bit range"""
        # Normalize source coordinates to 0-65535
        normalized_event = TouchEvent(
            x=int((event.x * 65535) / self.source_max_x) if self.source_max_x > 0 else 0,
            y=int((event.y * 65535) / self.source_max_y) if self.source_max_y > 0 else 0,
            pressure=int((event.pressure * 65535) / self.source_max_pressure) if self.source_max_pressure > 0 else 0,
            touch_down=event.touch_down,
            timestamp=event.timestamp
        )
        return super().encode(normalized_event)
    
    def decode(self, packet: bytes) -> Optional[TouchEvent]:
        """Decode and scale to target resolution"""
        event = super().decode(packet)
        if event is None:
            return None
        
        # Scale from 0-65535 to target resolution
        event.x = int((event.x * self.target_max_x) / 65535)
        event.y = int((event.y * self.target_max_y) / 65535)
        event.pressure = int((event.pressure * self.target_max_pressure) / 65535)
        
        return event


class TouchStatistics:
    """Track touch forwarding statistics"""
    
    def __init__(self):
        self.packets_sent = 0
        self.packets_received = 0
        self.last_sequence = None
        self.packets_lost = 0
        self.total_latency_ms = 0.0
        self.latency_samples = 0
    
    def on_send(self):
        """Called when a packet is sent"""
        self.packets_sent += 1
    
    def on_receive(self, sequence: int, send_timestamp: float, recv_timestamp: float):
        """
        Called when a packet is received.
        
        Args:
            sequence: Packet sequence number
            send_timestamp: Original event timestamp
            recv_timestamp: Reception timestamp
        """
        self.packets_received += 1
        
        # Detect packet loss
        if self.last_sequence is not None:
            expected_seq = (self.last_sequence + 1) & 0xFFFF
            if sequence != expected_seq:
                # Calculate lost packets (handle wraparound)
                if sequence > expected_seq:
                    lost = sequence - expected_seq
                else:
                    lost = (0xFFFF - expected_seq) + sequence + 1
                self.packets_lost += lost
        
        self.last_sequence = sequence
        
        # Calculate latency
        latency_ms = (recv_timestamp - send_timestamp) * 1000.0
        if 0 < latency_ms < 1000:  # Sanity check (discard negative or >1s)
            self.total_latency_ms += latency_ms
            self.latency_samples += 1
    
    def get_stats(self) -> dict:
        """Return current statistics"""
        avg_latency = (self.total_latency_ms / self.latency_samples 
                      if self.latency_samples > 0 else 0)
        
        loss_rate = (self.packets_lost / max(self.packets_sent, 1)) * 100.0
        
        return {
            "packets_sent": self.packets_sent,
            "packets_received": self.packets_received,
            "packets_lost": self.packets_lost,
            "loss_rate_percent": loss_rate,
            "average_latency_ms": avg_latency,
            "latency_samples": self.latency_samples
        }
    
    def reset(self):
        """Reset all counters"""
        self.__init__()


if __name__ == "__main__":
    """Test packet encoding/decoding"""
    import time
    
    # Create test event
    event = TouchEvent(
        x=2048,
        y=3072,
        pressure=128,
        touch_down=True,
        timestamp=time.time()
    )
    
    # Test basic encoding
    print("=== Basic TouchPacket ===")
    encoder = TouchPacket()
    packet = encoder.encode(event)
    print(f"Encoded packet ({len(packet)} bytes): {packet.hex()}")
    
    decoded = TouchPacket.decode(packet)
    if decoded:
        print(f"Decoded: X={decoded.x} Y={decoded.y} P={decoded.pressure} "
              f"Down={decoded.touch_down}")
    
    # Test scaled encoding
    print("\n=== Scaled TouchPacket (4095x4095 -> 1920x1080) ===")
    scaled_encoder = ScaledTouchPacket(
        source_max_x=4095, source_max_y=4095, source_max_pressure=255,
        target_max_x=1920, target_max_y=1080, target_max_pressure=255
    )
    
    packet = scaled_encoder.encode(event)
    decoded = scaled_encoder.decode(packet)
    if decoded:
        print(f"Original: X={event.x} Y={event.y}")
        print(f"Scaled:   X={decoded.x} Y={decoded.y}")
    
    # Test statistics
    print("\n=== Statistics ===")
    stats = TouchStatistics()
    
    for i in range(10):
        stats.on_send()
        # Simulate 1ms latency
        recv_time = time.time() + 0.001
        stats.on_receive(i, time.time(), recv_time)
    
    print(f"Stats: {stats.get_stats()}")
