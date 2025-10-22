# USB Radio Gateway – Master/Slave Architecture

## Overview

This system enables two Raspberry Pis to act as **man-in-the-middle intermediaries** between a biometric sensor (e.g., HID DigitalPersona) and the target boards they authenticate to. Designed for security research and penetration testing of electronic voting systems.

### Architecture

- **Master Pi**: Controls operation, can forward USB/IP from slave or sniff/log traffic
- **Slave Pi**: Physically connected to sensor and target board; has hardware USB switch to toggle between:
  - **Passive mode**: Real sensor ↔ target board (Pi monitors traffic)
  - **Active mode**: Pi USB gadget ↔ target board (sensor disconnected, Pi emulates)

- **Wireless Links** (automatic failover):
  1. **Primary**: nRF24L01 at kernel level (ultra-low latency, ~1–2 ms RTT)
  2. **Backup**: Wi-Fi Ad-Hoc 5 GHz (optimized, ~2–3 ms RTT)

- **USB Modes**:
  - USB/IP: Forward real sensor from slave to master over IP link
  - USB gadget: Pi pretends to be sensor when real one is unavailable
  - USB sniffer: Capture and forward USB traffic to master for analysis

---

## Components

### Hardware

- 2× Raspberry Pi (Pi Zero 2 W, CM4, or Pi 4)
- 2× nRF24L01+ modules (or nRF24L01+PA for extended range)
- 2x WiFi 6E for Raspberry Pi
- Optocouplers/relays (breadboard) for USB data line switching on slave Pi
- Biometric sensor (e.g., HID DigitalPersona DP5360)
- Generic LCD touchscreen
- Target boards to authenticate to eletronic votin system* Only on authorized tests.

### Software

- Kernel module `nrf24_net` (optional, for lowest latency)
- Python tunnel `nrf_tun` (userspace fallback)
- Wi-Fi Ad-Hoc with tuning scripts
- USB gadget (ConfigFS HID/custom)
- USB/IP server/client
- Link health monitor with auto-failover
- Master/slave orchestrator with mode control

---

## Modes of Operation

### Master Modes

1. **Forward**: 
   - USB/IP client connects to slave's sensor
   - Master creates USB gadget to present sensor to its own target board
   - Bidirectional authentication flow: master board ↔ master Pi gadget ↔ (radio) ↔ slave Pi ↔ real sensor

2. **Sniff**:
   - Master listens to USB traffic captured by slave
   - Logs/analyzes sensor protocol
   - Master discards its own target board's requests

### Slave Modes

1. **Active**:
   - GPIO switch disconnects real sensor from target board
   - Slave Pi USB gadget connects to target board
   - USB/IP server shares gadget to master
   - Master can remotely control the "fake sensor"

2. **Passive**:
   - GPIO switch connects real sensor directly to target board
   - Slave Pi monitors USB traffic via usbmon (passive tap or separate USB host port)
   - Forwards captured traffic to master over IP link
   - Used for reconnaissance and protocol analysis

---

## Quick Start

### 1. Install on both Pis

```bash
sudo ./scripts/install.sh
sudo reboot
```

### 2. Hardware setup

- Wire nRF24L01 modules (see README section on wiring)
- On slave Pi: wire GPIO-controlled relay/optocoupler to USB D+/D- lines
  - Example: GPIO17 controls relay; HIGH = gadget mode, LOW = passthrough mode

### 3. Start master

```bash
MODE=forward PEER_IP=10.24.0.2 SWITCH_GPIO=  ./scripts/start_master.sh
```

(Master doesn't need switch GPIO; leave empty)

### 4. Start slave

```bash
MODE=passive PEER_IP=10.24.0.1 SWITCH_GPIO=17 ./scripts/start_slave.sh
```

### 5. Control slave from master

```bash
# Tell slave to switch to active mode
python3 -m orchestrator.control_protocol client --peer-ip 10.24.0.2 --cmd '{"cmd":"set_mode","mode":"active"}'

# Query slave status
python3 -m orchestrator.control_protocol client --peer-ip 10.24.0.2 --cmd '{"cmd":"status"}'
```

---

## Link Failover

The link monitor automatically pings the peer:
- If nRF24 (primary) packet loss > 50%, routes traffic over Wi-Fi (backup)
- If nRF24 recovers, switches back

Configure thresholds in `link_monitor.py` or via CLI args.

---

## USB Hardware Switch (Slave)

Use a dual SPDT relay or optocouplers on a breadboard:

```
Sensor USB D+/D- ───┐
                    ├─ Relay (GPIO17) ─┬─ Target Board USB
Pi Gadget USB D+/D- ┘                  │
                                       └─ (common)
```

When `GPIO17=LOW`: sensor directly to board (passive)
When `GPIO17=HIGH`: Pi gadget to board (active)

---

## Security & Legal

- This tool is for **authorized penetration testing only** (e.g., TSE public tests 2025).
- Cloning commercial device VID/PID/crypto may be restricted.
- Traffic over radio is unencrypted; add VPN (WireGuard) if needed.

---

## Advanced

- **Kernel nRF24**: See `kernel/nrf24_net/` for ultra-low latency; wire SPI and DT overlay
- **Wi-Fi Layer-2 (Wifibroadcast)**: See `docs/LATENCY.md` for advanced monitor/injection setup
- **USB Gadget Customization**: Edit `scripts/gadget/create_hid_gadget.sh` to match your sensor's descriptors

---

## Troubleshooting

- **Link not up**: Check nRF24 wiring, SPI enabled, peer IP reachable via `ping`
- **USB switch not working**: Verify GPIO pin, relay polarity, and `usb_switch.py` logs
- **USB/IP fails**: Ensure `usbipd` running on slave, `modprobe vhci-hcd` on master
- **Gadget not enumerating**: Check OTG config (`dtoverlay=dwc2`), use Pi Zero/CM with OTG-capable port

---

## References

- TSE public pentest: https://www.tse.jus.br/eleicoes/tpu
- nRF24L01 datasheet: Nordic Semi
- Linux USB Gadget: kernel.org/doc/html/latest/usb/gadget.html
- USB/IP: usbip.sourceforge.net
