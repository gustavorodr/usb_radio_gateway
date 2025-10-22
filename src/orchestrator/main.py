#!/usr/bin/env python3
"""
Master/Slave orchestrator for USB radio gateway.

Master modes:
  - forward: USB/IP client to slave, present slave's sensor to master's board via gadget
  - sniff: Listen to slave's USB capture stream, log/analyze

Slave modes:
  - active: USB gadget on, USB/IP server shares gadget to master
  - passive: Real sensor connected to target board, Pi sniffs USB traffic and sends to master

Hardware USB switch (GPIO-controlled optocouplers/relays) toggles between:
  - Passive: sensor <-> target board (Pi monitors via USB host sniffer)
  - Active: sensor disconnected, Pi gadget <-> target board
"""
import argparse
import logging
import signal
import sys
import threading
from enum import Enum
from typing import Optional

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


class Role(Enum):
    MASTER = "master"
    SLAVE = "slave"


class MasterMode(Enum):
    FORWARD = "forward"   # USB/IP client + gadget emulation
    SNIFF = "sniff"       # Listen to slave's capture stream


class SlaveMode(Enum):
    ACTIVE = "active"     # Gadget mode + USB/IP server
    PASSIVE = "passive"   # Real sensor to board, sniff USB


class Orchestrator:
    def __init__(
        self,
        role: Role,
        mode: str,
        peer_ip: str = "10.24.0.1",
        control_port: int = 9999,
        switch_gpio: Optional[int] = None,
    ):
        self.role = role
        self.mode = mode
        self.peer_ip = peer_ip
        self.control_port = control_port
        self.switch_gpio = switch_gpio
        self._stop = threading.Event()

    def start(self):
        log.info(f"Starting orchestrator: role={self.role.value}, mode={self.mode}")
        if self.role == Role.MASTER:
            self._run_master()
        else:
            self._run_slave()

    def stop(self):
        self._stop.set()

    def _run_master(self):
        if self.mode == MasterMode.FORWARD.value:
            self._master_forward()
        elif self.mode == MasterMode.SNIFF.value:
            self._master_sniff()
        else:
            log.error(f"Unknown master mode: {self.mode}")

    def _run_slave(self):
        if self.mode == SlaveMode.ACTIVE.value:
            self._slave_active()
        elif self.mode == SlaveMode.PASSIVE.value:
            self._slave_passive()
        else:
            log.error(f"Unknown slave mode: {self.mode}")

    def _master_forward(self):
        """
        Master forward mode:
        1. Connect USB/IP client to slave
        2. Start gadget to present slave's device to master's target board
        """
        log.info("Master forward: connecting USB/IP to slave and starting gadget")
        # TODO: call usbip attach, create gadget, proxy traffic
        while not self._stop.wait(1):
            pass

    def _master_sniff(self):
        """
        Master sniff mode:
        Listen to slave's USB capture stream (socket or file transfer)
        """
        log.info("Master sniff: listening for slave USB captures")
        # TODO: open socket, receive pcap/usbmon data
        while not self._stop.wait(1):
            pass

    def _slave_active(self):
        """
        Slave active mode:
        1. Set GPIO to disconnect real sensor, connect Pi gadget to target board
        2. Start USB gadget (HID/custom)
        3. Start USB/IP server to share gadget with master
        """
        log.info("Slave active: switching to gadget mode, starting USB/IP server")
        self._set_usb_switch("active")
        # TODO: create gadget, start usbipd
        while not self._stop.wait(1):
            pass

    def _slave_passive(self):
        """
        Slave passive mode:
        1. Set GPIO to connect real sensor to target board
        2. Pi monitors USB traffic (usbmon/pcap) and sends to master
        """
        log.info("Slave passive: switching to passthrough, starting USB sniffer")
        self._set_usb_switch("passive")
        # TODO: start usbmon capture, stream to master
        while not self._stop.wait(1):
            pass

    def _set_usb_switch(self, position: str):
        """
        Control GPIO to toggle optocouplers/relays:
        - passive: real sensor <-> board
        - active: Pi gadget <-> board
        """
        if self.switch_gpio is None:
            log.warning("No switch GPIO configured, skipping hardware toggle")
            return
        # TODO: use RPi.GPIO or gpiod to set pin high/low
        log.info(f"USB switch set to: {position} (GPIO {self.switch_gpio})")


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="USB radio gateway orchestrator")
    p.add_argument("--role", choices=["master", "slave"], required=True)
    p.add_argument("--mode", required=True, help="master: forward|sniff, slave: active|passive")
    p.add_argument("--peer-ip", default="10.24.0.1", help="IP of peer Pi over radio/wifi link")
    p.add_argument("--control-port", type=int, default=9999, help="TCP port for control msgs")
    p.add_argument("--switch-gpio", type=int, help="GPIO pin for USB hardware switch")
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    role = Role(args.role)
    orch = Orchestrator(
        role=role,
        mode=args.mode,
        peer_ip=args.peer_ip,
        control_port=args.control_port,
        switch_gpio=args.switch_gpio,
    )

    def handle_sig(signum, frame):
        orch.stop()

    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)

    try:
        orch.start()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
