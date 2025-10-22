#!/usr/bin/env bash
set -euo pipefail
# Unified startup for master Pi
# 1. Bring up primary link (nRF24 kernel or tun0)
# 2. Bring up backup link (Wi-Fi Ad-Hoc)
# 3. Start link monitor with failover
# 4. Start orchestrator in master mode

ROLE=master
MODE=${MODE:-forward}  # forward | sniff
PEER_IP=${PEER_IP:-10.24.0.2}
SWITCH_GPIO=${SWITCH_GPIO:-}

# Primary link: nRF24 kernel module or Python tunnel
if lsmod | grep -q nrf24_net; then
  echo "[master] Using kernel nrf24_net (nrf0)"
  PRIMARY_IFACE=nrf0
  sudo ip addr add 10.24.0.1/30 dev nrf0 || true
  sudo ip link set nrf0 up || true
else
  echo "[master] Using Python tunnel (tun0)"
  PRIMARY_IFACE=tun0
  ./scripts/setup_tun_a.sh
  ./scripts/run_tunnel_a.sh &
  sleep 2
fi

# Backup link: Wi-Fi Ad-Hoc
echo "[master] Setting up Wi-Fi backup (wlan0)"
./scripts/wifi/adhoc_low_latency_a.sh wlan0 p2p-lowlat 5180 10.25.0.1/30

# Start link monitor
echo "[master] Starting link health monitor"
python3 -m orchestrator.link_monitor --peer-ip "$PEER_IP" --primary-iface "$PRIMARY_IFACE" --backup-iface wlan0 &
MONITOR_PID=$!

# Start orchestrator
echo "[master] Starting orchestrator: role=$ROLE, mode=$MODE"
ARGS="--role $ROLE --mode $MODE --peer-ip $PEER_IP"
if [[ -n "$SWITCH_GPIO" ]]; then
  ARGS="$ARGS --switch-gpio $SWITCH_GPIO"
fi
python3 -m orchestrator.main $ARGS

kill $MONITOR_PID 2>/dev/null || true
