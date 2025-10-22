from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List, Tuple

# NRF24L01 fixed payload size
MAX_RADIO_PAYLOAD = 32
# We reserve 4 bytes for header: 2 bytes msg_id, 1 byte frag_idx, 1 byte frag_count
HEADER_SIZE = 4
FRAG_DATA_SIZE = MAX_RADIO_PAYLOAD - HEADER_SIZE  # 28 bytes


@dataclass
class FrameHeader:
    msg_id: int  # 0-65535
    frag_idx: int  # 0..(frag_count-1)
    frag_count: int  # 1..N

    def pack(self) -> bytes:
        return bytes([
            (self.msg_id >> 8) & 0xFF,
            self.msg_id & 0xFF,
            self.frag_idx & 0xFF,
            self.frag_count & 0xFF,
        ])

    @staticmethod
    def unpack(buf: bytes) -> "FrameHeader":
        if len(buf) < HEADER_SIZE:
            raise ValueError("buffer too small for header")
        msg_id = (buf[0] << 8) | buf[1]
        frag_idx = buf[2]
        frag_count = buf[3]
        return FrameHeader(msg_id, frag_idx, frag_count)


def fragment(msg_id: int, payload: bytes) -> List[bytes]:
    """
    Split payload into NRF frames with a simple header.
    Returns a list of 32-byte frames ready to send.
    """
    if not payload:
        # Send a single empty fragment
        header = FrameHeader(msg_id, 0, 1).pack()
        return [header + bytes(FRAG_DATA_SIZE)]

    frags: List[bytes] = []
    total = (len(payload) + FRAG_DATA_SIZE - 1) // FRAG_DATA_SIZE
    for idx in range(total):
        start = idx * FRAG_DATA_SIZE
        end = min(start + FRAG_DATA_SIZE, len(payload))
        chunk = payload[start:end]
        # Pad to FRAG_DATA_SIZE
        if len(chunk) < FRAG_DATA_SIZE:
            chunk = chunk + bytes(FRAG_DATA_SIZE - len(chunk))
        hdr = FrameHeader(msg_id, idx, total).pack()
        frags.append(hdr + chunk)
    return frags


class Reassembler:
    """
    Collect fragments until full message is reassembled.
    Garbage collects old/incomplete messages on timeout.
    """

    def __init__(self, ttl_sec: float = 3.0):
        self._buffers: Dict[int, Tuple[float, int, Dict[int, bytes]]] = {}
        self._ttl = ttl_sec

    def push(self, frame: bytes) -> Tuple[bool, bytes | None]:
        """
        Add a frame. Returns (complete, payload) when a full message is ready.
        """
        if len(frame) != MAX_RADIO_PAYLOAD:
            # ignore invalid size
            return False, None
        hdr = FrameHeader.unpack(frame[:HEADER_SIZE])
        data = frame[HEADER_SIZE:]
        now = time.time()

        # Cleanup
        expired = [mid for mid, (ts, _, _) in self._buffers.items() if now - ts > self._ttl]
        for mid in expired:
            del self._buffers[mid]

        if hdr.frag_count == 0:
            # invalid
            return False, None

        if hdr.msg_id not in self._buffers:
            self._buffers[hdr.msg_id] = (now, hdr.frag_count, {})
        ts, total, parts = self._buffers[hdr.msg_id]
        parts[hdr.frag_idx] = data
        # refresh timestamp
        self._buffers[hdr.msg_id] = (now, total, parts)

        if len(parts) == total:
            # Reassemble
            payload = b"".join(parts[i] for i in range(total))
            # Strip padding
            # Determine actual size from total-1 last fragment padding
            # Trimming trailing nulls added during fragmentation
            payload = payload.rstrip(b"\x00")
            del self._buffers[hdr.msg_id]
            return True, payload
        return False, None
