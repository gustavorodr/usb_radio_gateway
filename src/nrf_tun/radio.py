from __future__ import annotations

import time
from typing import Optional

import board  # type: ignore
from digitalio import DigitalInOut  # type: ignore
import busio  # type: ignore

try:
    from adafruit_nrf24l01 import NRF24L01  # type: ignore
except Exception as e:  # pragma: no cover
    raise RuntimeError(
        "adafruit-circuitpython-nrf24l01 is required. Install with: pip install Adafruit-Blinka adafruit-circuitpython-nrf24l01"
    ) from e


class NRF24Radio:
    """
    Minimal wrapper around Adafruit CircuitPython NRF24L01 for 32-byte frames.
    """

    def __init__(
        self,
        ce_pin: str = "D25",
        csn_pin: str = "D8",
        channel: int = 0x76,
        payload_size: int = 32,
        tx_addr: bytes = b"\xE0\xE0\xF1\xF1\xE0",
        rx_addr: bytes = b"\xF1\xF1\xF0\xF0\xE0",
        pa_level: int = -6,  # dBm: -18, -12, -6, 0
        data_rate: int = 1_000_000,
    ) -> None:
        spi = busio.SPI(clock=board.SCK, MOSI=board.MOSI, MISO=board.MISO)
        # Map str to actual board pin attributes
        ce = DigitalInOut(getattr(board, ce_pin))
        csn = DigitalInOut(getattr(board, csn_pin))
        self._nrf = NRF24L01(spi, csn, ce, channel=channel, payload_size=payload_size)
        # Configure addresses
        self._nrf.open_tx_pipe(tx_addr)
        self._nrf.open_rx_pipe(1, rx_addr)
        # Power and data rate
        # pa_level in Adafruit lib uses -18, -12, -6, 0
        self._nrf.pa_level = pa_level
        # data rate mapping
        if data_rate <= 250_000:
            self._nrf.data_rate = NRF24L01.RATE_250_KBPS
        elif data_rate <= 1_000_000:
            self._nrf.data_rate = NRF24L01.RATE_1_MBPS
        else:
            self._nrf.data_rate = NRF24L01.RATE_2_MBPS
        # Auto ack helps with reliability
        self._nrf.auto_ack = True
        # Fixed payload size (32) for simplicity

    def send(self, frame: bytes, retries: int = 3, ack_wait: float = 0.03) -> bool:
        for _ in range(retries):
            try:
                self._nrf.send(frame)
                # Wait a bit for ack
                time.sleep(ack_wait)
                return True
            except Exception:
                # Backoff and retry
                time.sleep(0.01)
        return False

    def any(self) -> bool:
        try:
            return self._nrf.any()
        except Exception:
            return False

    def recv(self) -> Optional[bytes]:
        try:
            buf = self._nrf.recv()  # returns a bytes-like object
            return bytes(buf)
        except Exception:
            return None

    def listen(self, enable: bool = True) -> None:
        self._nrf.listen = enable

    def close(self) -> None:
        try:
            self._nrf.power = False
        except Exception:
            pass
