from __future__ import annotations

import argparse
import fcntl
import os
import queue
import select
import signal
import struct
import sys
import threading
import time
from typing import Optional

from .framing import fragment, Reassembler
from .radio import NRF24Radio

TUNSETIFF = 0x400454ca
IFF_TUN = 0x0001
IFF_NO_PI = 0x1000


def create_tun(name: str = "tun0") -> int:
    tun = os.open("/dev/net/tun", os.O_RDWR)
    ifr = struct.pack("16sH", name.encode(), IFF_TUN | IFF_NO_PI)
    fcntl.ioctl(tun, TUNSETIFF, ifr)
    return tun


def tun_readable(tun_fd: int) -> bool:
    r, _, _ = select.select([tun_fd], [], [], 0)
    return bool(r)


class TunnelDaemon:
    def __init__(
        self,
        role: str,
        tun_name: str = "tun0",
        channel: int = 0x76,
        ce_pin: str = "D25",
        csn_pin: str = "D8",
        tx_addr: bytes = b"\xE0\xE0\xF1\xF1\xE0",
        rx_addr: bytes = b"\xF1\xF1\xF0\xF0\xE0",
        data_rate: int = 1_000_000,
        pa_level: int = -6,
    ) -> None:
        self.role = role
        self.tun_fd = create_tun(tun_name)
        # For point-to-point, swap addresses by role
        if role.lower() in ("a", "server"):
            _tx, _rx = tx_addr, rx_addr
        else:
            _tx, _rx = rx_addr, tx_addr
        self.radio = NRF24Radio(
            ce_pin=ce_pin,
            csn_pin=csn_pin,
            channel=channel,
            payload_size=32,
            tx_addr=_tx,
            rx_addr=_rx,
            pa_level=pa_level,
            data_rate=data_rate,
        )
        self.radio.listen(True)
        self.tx_queue: "queue.Queue[bytes]" = queue.Queue(maxsize=200)
        self.msg_id = 0
        self.reasm = Reassembler(ttl_sec=5.0)
        self._stop = threading.Event()

    def start(self) -> None:
        self._threads = [
            threading.Thread(target=self._tun_to_radio, daemon=True),
            threading.Thread(target=self._radio_to_tun, daemon=True),
            threading.Thread(target=self._tx_worker, daemon=True),
        ]
        for t in self._threads:
            t.start()

    def stop(self) -> None:
        self._stop.set()
        try:
            self.radio.close()
        except Exception:
            pass
        os.close(self.tun_fd)

    def _tun_to_radio(self) -> None:
        while not self._stop.is_set():
            try:
                if not tun_readable(self.tun_fd):
                    time.sleep(0.001)
                    continue
                pkt = os.read(self.tun_fd, 2000)
                if not pkt:
                    continue
                # Fragment and enqueue
                self.msg_id = (self.msg_id + 1) & 0xFFFF
                for frame in fragment(self.msg_id, pkt):
                    try:
                        self.tx_queue.put(frame, timeout=0.5)
                    except queue.Full:
                        # Drop oldest to make room
                        try:
                            _ = self.tx_queue.get_nowait()
                            self.tx_queue.put_nowait(frame)
                        except Exception:
                            pass
            except Exception:
                time.sleep(0.005)

    def _tx_worker(self) -> None:
        while not self._stop.is_set():
            try:
                frame = self.tx_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            ok = self.radio.send(frame)
            if not ok:
                # Simple retry is already inside radio.send; drop if still failing
                pass

    def _radio_to_tun(self) -> None:
        while not self._stop.is_set():
            try:
                if not self.radio.any():
                    time.sleep(0.001)
                    continue
                data = self.radio.recv()
                if not data:
                    continue
                complete, payload = self.reasm.push(data)
                if complete and payload is not None:
                    try:
                        os.write(self.tun_fd, payload)
                    except Exception:
                        pass
            except Exception:
                time.sleep(0.002)


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="NRF24L01-backed TUN link for IP over radio")
    p.add_argument("--role", choices=["a", "b", "server", "client"], required=True,
                   help="Endpoint role; determines TX/RX addresses")
    p.add_argument("--tun", default="tun0", help="TUN interface name")
    p.add_argument("--channel", type=lambda x: int(x, 0), default="0x76", help="NRF channel (0-125)")
    p.add_argument("--ce-pin", default="D25", help="BCM pin name for CE (e.g., D25)")
    p.add_argument("--csn-pin", default="D8", help="BCM pin name for CSN/CE0 (e.g., D8)")
    p.add_argument("--tx-addr", default="E0E0F1F1E0", help="TX pipe address hex (10 hex chars)")
    p.add_argument("--rx-addr", default="F1F1F0F0E0", help="RX pipe address hex (10 hex chars)")
    p.add_argument("--rate", type=int, default=1_000_000, help="Data rate: 250000, 1000000, 2000000")
    p.add_argument("--pa", type=int, default=-6, help="PA level in dBm: -18,-12,-6,0")
    return p.parse_args(argv)


def parse_addr_hex(s: str) -> bytes:
    s = s.strip().lower()
    if s.startswith("0x"):
        s = s[2:]
    if len(s) != 10:
        raise ValueError("address must be 5 bytes (10 hex chars)")
    return bytes.fromhex(s)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    tx_addr = parse_addr_hex(args.tx_addr)
    rx_addr = parse_addr_hex(args.rx_addr)

    daemon = TunnelDaemon(
        role=args.role,
        tun_name=args.tun,
        channel=args.channel,
        ce_pin=args.ce_pin,
        csn_pin=args.csn_pin,
        tx_addr=tx_addr,
        rx_addr=rx_addr,
        data_rate=args.rate,
        pa_level=args.pa,
    )

    stop_evt = threading.Event()

    def handle_sig(signum, frame):
        stop_evt.set()

    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)

    daemon.start()
    try:
        while not stop_evt.is_set():
            time.sleep(0.2)
    finally:
        daemon.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
