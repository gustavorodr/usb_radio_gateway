#!/usr/bin/env python3
"""
Simple master control protocol over TCP.
Master sends JSON commands to slave:
  - {"cmd": "set_mode", "mode": "active"|"passive"}
  - {"cmd": "status"}
Slave responds with JSON status.
"""
import argparse
import json
import socket
import sys
import threading
from typing import Callable, Optional


class ControlServer:
    """Slave side: listen for commands from master"""

    def __init__(self, port: int, on_command: Callable[[dict], dict]):
        self.port = port
        self.on_command = on_command
        self._stop = threading.Event()

    def start(self):
        print(f"[control_server] Listening on port {self.port}")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", self.port))
        sock.listen(1)
        sock.settimeout(1.0)
        while not self._stop.is_set():
            try:
                conn, addr = sock.accept()
                threading.Thread(target=self._handle_conn, args=(conn,), daemon=True).start()
            except socket.timeout:
                continue
        sock.close()

    def stop(self):
        self._stop.set()

    def _handle_conn(self, conn: socket.socket):
        with conn:
            data = conn.recv(4096).decode()
            try:
                cmd = json.loads(data)
                resp = self.on_command(cmd)
                conn.sendall(json.dumps(resp).encode() + b"\n")
            except Exception as e:
                conn.sendall(json.dumps({"error": str(e)}).encode() + b"\n")


class ControlClient:
    """Master side: send commands to slave"""

    def __init__(self, peer_ip: str, port: int):
        self.peer_ip = peer_ip
        self.port = port

    def send_command(self, cmd: dict) -> dict:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        try:
            sock.connect((self.peer_ip, self.port))
            sock.sendall(json.dumps(cmd).encode())
            resp = sock.recv(4096).decode()
            return json.loads(resp)
        finally:
            sock.close()


def demo_server(argv: Optional[list[str]] = None):
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=9999)
    args = p.parse_args(argv)

    def handle(cmd):
        print(f"[control_server] Received: {cmd}")
        if cmd.get("cmd") == "set_mode":
            return {"status": "ok", "mode": cmd.get("mode")}
        elif cmd.get("cmd") == "status":
            return {"status": "ok", "mode": "passive", "link": "nrf24"}
        return {"error": "unknown command"}

    srv = ControlServer(args.port, handle)
    try:
        srv.start()
    except KeyboardInterrupt:
        srv.stop()


def demo_client(argv: Optional[list[str]] = None):
    p = argparse.ArgumentParser()
    p.add_argument("--peer-ip", default="10.24.0.2")
    p.add_argument("--port", type=int, default=9999)
    p.add_argument("--cmd", required=True, help='JSON command, e.g., \'{"cmd":"status"}\'')
    args = p.parse_args(argv)
    client = ControlClient(args.peer_ip, args.port)
    cmd = json.loads(args.cmd)
    resp = client.send_command(cmd)
    print(json.dumps(resp, indent=2))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "server":
        demo_server(sys.argv[2:])
    elif len(sys.argv) > 1 and sys.argv[1] == "client":
        demo_client(sys.argv[2:])
    else:
        print("Usage: control_protocol.py [server|client] ...")
        sys.exit(1)
