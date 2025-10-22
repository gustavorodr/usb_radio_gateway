#!/usr/bin/env python3
"""
USB sniffer/forwarder for passive mode.
Captures USB traffic from real sensor using usbmon and forwards to master over socket.
"""
import argparse
import socket
import subprocess
import sys
from typing import Optional


def sniff_and_forward(busnum: int, peer_ip: str, peer_port: int):
    """
    Use tcpdump on usbmon interface to capture USB traffic, send to peer.
    """
    iface = f"usbmon{busnum}"
    print(f"[usb_sniffer] Capturing {iface}, forwarding to {peer_ip}:{peer_port}")
    # tcpdump -i usbmon0 -w - | nc peer port
    # Or use python-pcapng / pyshark for more control
    cmd = ["tcpdump", "-i", iface, "-U", "-w", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((peer_ip, peer_port))
    try:
        while True:
            chunk = proc.stdout.read(4096)
            if not chunk:
                break
            sock.sendall(chunk)
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()
        proc.terminate()


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="USB sniffer/forwarder")
    p.add_argument("--busnum", type=int, default=0, help="USB bus number (0 = all)")
    p.add_argument("--peer-ip", default="10.24.0.1", help="Master IP")
    p.add_argument("--peer-port", type=int, default=10000, help="Master port")
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    sniff_and_forward(args.busnum, args.peer_ip, args.peer_port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
