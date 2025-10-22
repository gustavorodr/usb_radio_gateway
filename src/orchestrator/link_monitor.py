#!/usr/bin/env python3
"""
Link health monitor with automatic failover from nRF24 (primary) to Wi-Fi (backup).
Pings peer IP, measures loss/RTT, and triggers failover if primary link degrades.
"""
import argparse
import subprocess
import sys
import time
from typing import Optional


class LinkMonitor:
    def __init__(
        self,
        peer_ip: str,
        primary_iface: str = "nrf0",
        backup_iface: str = "wlan0",
        check_interval: float = 2.0,
        loss_threshold: float = 0.5,
    ):
        self.peer_ip = peer_ip
        self.primary_iface = primary_iface
        self.backup_iface = backup_iface
        self.check_interval = check_interval
        self.loss_threshold = loss_threshold
        self.current_link = "primary"

    def start(self):
        print(f"[link_monitor] Monitoring {self.peer_ip}, primary={self.primary_iface}, backup={self.backup_iface}")
        while True:
            loss = self._check_link()
            if loss > self.loss_threshold and self.current_link == "primary":
                print(f"[link_monitor] Primary link loss={loss:.1%}, failing over to {self.backup_iface}")
                self._failover_to_backup()
            elif loss <= self.loss_threshold and self.current_link == "backup":
                print(f"[link_monitor] Primary link recovered, switching back to {self.primary_iface}")
                self._failback_to_primary()
            time.sleep(self.check_interval)

    def _check_link(self) -> float:
        """
        Ping peer, return packet loss ratio.
        """
        cmd = ["ping", "-c", "3", "-W", "1", self.peer_ip]
        try:
            out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=5, text=True)
            # Parse "3 packets transmitted, 2 received, 33% packet loss"
            for line in out.splitlines():
                if "packet loss" in line:
                    pct = line.split("%")[0].split()[-1]
                    return float(pct) / 100.0
        except Exception:
            return 1.0  # 100% loss
        return 0.0

    def _failover_to_backup(self):
        """
        Route traffic over backup interface.
        """
        # Add route to peer via backup iface
        subprocess.run(["ip", "route", "del", self.peer_ip], check=False, stderr=subprocess.DEVNULL)
        subprocess.run(["ip", "route", "add", self.peer_ip, "dev", self.backup_iface], check=False)
        self.current_link = "backup"

    def _failback_to_primary(self):
        """
        Restore primary link.
        """
        subprocess.run(["ip", "route", "del", self.peer_ip], check=False, stderr=subprocess.DEVNULL)
        subprocess.run(["ip", "route", "add", self.peer_ip, "dev", self.primary_iface], check=False)
        self.current_link = "primary"


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Link health monitor with failover")
    p.add_argument("--peer-ip", default="10.24.0.1", help="Peer IP to ping")
    p.add_argument("--primary-iface", default="nrf0", help="Primary interface (kernel nRF24 or tun0)")
    p.add_argument("--backup-iface", default="wlan0", help="Backup interface (Wi-Fi)")
    p.add_argument("--check-interval", type=float, default=2.0, help="Seconds between checks")
    p.add_argument("--loss-threshold", type=float, default=0.5, help="Loss ratio to trigger failover")
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    mon = LinkMonitor(
        args.peer_ip,
        args.primary_iface,
        args.backup_iface,
        args.check_interval,
        args.loss_threshold,
    )
    try:
        mon.start()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
