#!/usr/bin/env bash
set -euo pipefail
# Unified startup for slave Pi
# 1. Bring up primary link (nRF24 kernel or tun0)
# 2. Bring up backup link (Wi-Fi Ad-Hoc)
# 3. Start link monitor with failover
# 4. Start orchestrator in slave mode

ROLE=slave
MODE=${MODE:-passive}  # passive | active
PEER_IP=${PEER_IP:-10.24.0.1}
SWITCH_GPIO=${SWITCH_GPIO:-17}  # example GPIO for USB switch

# Primary link: nRF24 kernel module or Python tunnel
if lsmod | grep -q nrf24_net; then
  echo "[slave] Using kernel nrf24_net (nrf0)"
  PRIMARY_IFACE=nrf0
  sudo ip addr add 10.24.0.2/30 dev nrf0 || true
  sudo ip link set nrf0 up || true
else
  echo "[slave] Using Python tunnel (tun0)"
  PRIMARY_IFACE=tun0
  ./scripts/setup_tun_b.sh
  ./scripts/run_tunnel_b.sh &
  sleep 2
fi

# Backup link: Wi-Fi Ad-Hoc
echo "[slave] Setting up Wi-Fi backup (wlan0)"
./scripts/wifi/adhoc_low_latency_b.sh wlan0 p2p-lowlat 5180 10.25.0.2/30

# Start link monitor
echo "[slave] Starting link health monitor"
python3 -m orchestrator.link_monitor --peer-ip "$PEER_IP" --primary-iface "$PRIMARY_IFACE" --backup-iface wlan0 &
MONITOR_PID=$!

# Start orchestrator
echo "[slave] Starting orchestrator: role=$ROLE, mode=$MODE"
ARGS="--role $ROLE --mode $MODE --peer-ip $PEER_IP"
if [[ -n "$SWITCH_GPIO" ]]; then
  ARGS="$ARGS --switch-gpio $SWITCH_GPIO"
fi
python3 -m orchestrator.main $ARGS

kill $MONITOR_PID 2>/dev/null || true
