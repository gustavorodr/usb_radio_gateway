# USB Radio Gateway

**Man-in-the-Middle gateway for USB devices over radio links**

Authorized penetration testing project for Brazilian electronic voting system (TSE): https://www.tse.jus.br/eleicoes/tpu

---

## Overview

Two Raspberry Pis communicate via low-latency radio (nRF24L01+) and Wi-Fi backup to create a **transparent wireless bridge** between USB devices and host systems. Designed for security research, protocol analysis, and penetration testing.

### Key Features

- 🔗 **Dual wireless links** with automatic failover (nRF24L01 primary, Wi-Fi backup)
- 🔌 **USB forwarding** over radio (USB/IP protocol)
- 📱 **Touchscreen forwarding** with ~1.5ms latency (evdev → radio → uinput)
- 🎭 **USB gadget emulation** for device presence when disconnected
- 🔍 **USB traffic sniffing** and protocol analysis
- 🎚️ **Hardware USB switching** via GPIO (slave toggles between real device and gadget)
- 🌐 **Remote control protocol** (master commands slave mode changes)

### Use Cases

- Transparent USB device relay over wireless
- USB protocol analysis and traffic capture
- Security testing of USB authentication systems
- Remote biometric sensor operation
- Touchscreen forwarding for remote displays

---

## Quick Start

---

## Quick Start

### 1. Installation

```bash
git clone https://github.com/gustavorodr/usb_radio_gateway
cd usb_radio_gateway
sudo ./scripts/install.sh
sudo reboot
```

### 2. Hardware Setup

**Both Pis**: Connect nRF24L01+ module to SPI pins (see [Hardware Wiring](#hardware-wiring))

**Slave Pi only**: Connect GPIO relay for USB switching (default: GPIO17)

### 3. Start System

**Master Pi:**
```bash
# USB forwarding mode
MODE=forward PEER_IP=10.24.0.2 ./scripts/start_master.sh

# Or sniffing mode
MODE=sniff PEER_IP=10.24.0.2 ./scripts/start_master.sh
```

**Slave Pi:**
```bash
# Passive mode (real device, monitor traffic)
MODE=passive PEER_IP=10.24.0.1 SWITCH_GPIO=17 ./scripts/start_slave.sh

# Or active mode (gadget emulation)
MODE=active PEER_IP=10.24.0.1 SWITCH_GPIO=17 ./scripts/start_slave.sh
```

### 4. Remote Control (Optional)

```bash
# Switch slave to active mode
python3 -m orchestrator.control_protocol client \
  --peer-ip 10.24.0.2 \
  --cmd '{"cmd":"set_mode","mode":"active"}'
```

---

## Architecture

```
┌─────────────┐                    ┌──────────────┐
│  Master Pi  │   nRF24L01 Radio   │   Slave Pi   │
│             │ ◄────────────────► │              │
│ USB Gadget  │   Wi-Fi Backup     │  Real Device │
│   (Host)    │ ◄- - - - - - - - → │   + Switch   │
└─────────────┘                    └──────────────┘
```

**Master modes:**
- `forward`: Receives USB/IP from slave, presents gadget to local host
- `sniff`: Receives USB traffic captures from slave for analysis

**Slave modes:**
- `passive`: Real device connected, Pi monitors traffic
- `active`: Pi gadget connected (via USB switch), USB/IP server

**Wireless:**
- Primary: nRF24L01+ (kernel or Python tunnel, <2ms latency)
- Backup: Wi-Fi Ad-Hoc 5GHz (automatic failover when primary fails)

**Touchscreen:** Optional evdev capture → radio → uinput injection (~1.5ms latency)

📖 **Full details:** [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

---

## Hardware Wiring

### nRF24L01+ Module (Both Pis)

Connect to SPI pins (BCM numbering):

| nRF24 Pin | Pi Pin | BCM |
|-----------|--------|-----|
| VCC | 3.3V | - |
| GND | GND | - |
| CE | Pin 22 | GPIO25 |
| CSN | Pin 24 | GPIO8 (CE0) |
| SCK | Pin 23 | GPIO11 |
| MOSI | Pin 19 | GPIO10 |
| MISO | Pin 21 | GPIO9 |

**⚠️ Important:** Use 3.3V, NOT 5V!

Enable SPI: Add `dtparam=spi=on` to `/boot/config.txt` (or `/boot/firmware/config.txt`), then reboot.

### USB Hardware Switch (Slave Pi Only)

Use GPIO-controlled relay to route USB D+/D- between:
- **Passive**: Real device ↔ Target board
- **Active**: Pi gadget ↔ Target board

Default control pin: GPIO17 (configurable via `SWITCH_GPIO`)

📖 **Wiring diagrams:** [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

---

## Documentation

| Document | Description |
|----------|-------------|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Complete system design, modes, diagrams |
| [TOUCHSCREEN.md](docs/TOUCHSCREEN.md) | Touchscreen forwarding setup and API |
| [LATENCY.md](docs/LATENCY.md) | Latency optimization guide |
| [USB_GADGET.md](docs/USB_GADGET.md) | USB gadget configuration details |
| [CLEANUP.md](docs/CLEANUP.md) | File inventory and usage |

---

## Project Structure

```
usb_radio_gateway/
├── src/
│   ├── nrf_tun/          # Python radio tunnel (userspace)
│   ├── orchestrator/      # Master/slave control daemons
│   ├── touch/            # Touchscreen capture/injection
│   └── gadget/           # USB gadget utilities
├── scripts/
│   ├── start_master.sh   # Master startup
│   ├── start_slave.sh    # Slave startup
│   ├── install.sh        # Dependencies installer
│   ├── touch/            # Touchscreen setup scripts
│   ├── wifi/             # Wi-Fi Ad-Hoc configuration
│   └── gadget/           # USB gadget/OTG setup
├── kernel/
│   └── nrf24_net/        # Kernel driver (optional, low latency)
└── docs/                 # Documentation
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| **Radio link not working** | Check nRF24 wiring, verify SPI enabled (`ls /dev/spidev*`), test with `ping` |
| **USB switch not responding** | Verify GPIO pin number, check relay wiring/polarity |
| **USB/IP connection fails** | Ensure `usbipd` running on slave, `modprobe vhci-hcd` on master |
| **Gadget not enumerating** | Check OTG configuration, use Pi Zero/CM4 with OTG port |
| **Touchscreen not detected** | Run `sudo ./scripts/touch/setup_touch.sh`, check `/dev/input/event*` |

📖 **Detailed troubleshooting:** See individual documentation files

---

## Security & Legal

⚠️ **This tool is for authorized testing only**

- Requires explicit permission for penetration testing
- Cloning commercial device VID/PID may violate regulations
- Radio traffic is unencrypted (use WireGuard VPN if needed)
- Intended for TSE authorized tests: https://www.tse.jus.br/eleicoes/tpu

---

## License

See [LICENSE](LICENSE) file.

---

## References

- Linux USB Gadget: https://kernel.org/doc/html/latest/usb/gadget.html
- USB/IP Protocol: http://usbip.sourceforge.net
- nRF24L01 Datasheet: Nordic Semiconductor
- TSE Public Tests: https://www.tse.jus.br/eleicoes/tpu

---

## Architecture Overview

**See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for complete details.**

**Wireless Links** (automatic failover):
1. nRF24L01 (primary): kernel driver or Python tunnel (~1–2 ms RTT)
2. Wi-Fi Ad-Hoc (backup): 5 GHz optimized (~2–3 ms RTT)

**Slave Modes:**
- **Passive**: Real sensor → target board; Pi monitors USB traffic
- **Active**: Pi USB gadget → target board; USB/IP server shares to master

**Master Modes:**
- **Forward**: USB/IP client to slave + gadget to master's board
- **Sniff**: Listen to slave's USB captures for analysis

---

## Hardware Wiring

### nRF24L01 (Both Pis)

Default pins (BCM):
- CE → GPIO25
- CSN → CE0 (GPIO8)
- SCK → GPIO11
- MOSI → GPIO10
- MISO → GPIO9
- VCC → 3.3V (never 5V!)
- GND → GND

Enable SPI: Edit `/boot/config.txt` or `/boot/firmware/config.txt`, add `dtparam=spi=on`, then reboot.

### USB Hardware Switch (Slave Pi Only)

Use GPIO-controlled relay/optocoupler to route USB D+/D- between:
- **Passive**: Real sensor ↔ target board
- **Active**: Pi USB gadget ↔ target board

Example: GPIO17 HIGH = active mode, LOW = passive mode

---

## Advanced Options

### Kernel nRF24 (Ultra-Low Latency)

For sub-millisecond latency, use the kernel driver instead of Python:

```bash
sudo ./scripts/build_nrf24_kernel.sh
```

See `kernel/nrf24_net/` for skeleton code. Wire SPI functions and create Device Tree overlay.

### Wi-Fi Backup Link

Automatically configured by startup scripts. Scripts in `scripts/wifi/` set up Ad-Hoc mode with power save disabled.

### USB Gadget Configuration

Scripts in `scripts/gadget/` handle OTG setup and HID gadget creation. For device-specific emulation, modify VID/PID in `create_hid_gadget.sh`.

---

## Troubleshooting

- **Link not up**: Check nRF24 wiring, verify SPI enabled (`ls /dev/spidev*`), ping peer IP
- **USB switch not working**: Verify GPIO pin number, check relay polarity
- **USB/IP fails**: Ensure `usbipd` running on server, `modprobe vhci-hcd` on client
- **Gadget not enumerating**: Check OTG config, use Pi Zero/CM with OTG-capable port

---

## Security & Legal

- **Authorization required**: This tool is for authorized penetration testing only
- Traffic over radio is **unencrypted**; add VPN (WireGuard) if needed
- Cloning commercial device VID/PID may be restricted by law

---

## Project Structure

```
usb_radio_gateway/
├── src/
│   ├── nrf_tun/          # Python tunnel (userspace radio link)
│   ├── orchestrator/      # Master/slave orchestrator
│   └── gadget/           # USB gadget utilities
├── scripts/
│   ├── start_master.sh   # Master startup (all-in-one)
│   ├── start_slave.sh    # Slave startup (all-in-one)
│   ├── install.sh        # Install dependencies
│   ├── wifi/             # Wi-Fi Ad-Hoc setup
│   └── gadget/           # USB gadget/OTG setup
├── kernel/
│   └── nrf24_net/        # Kernel module (optional, advanced)
└── docs/
    ├── ARCHITECTURE.md   # Complete system design
    ├── LATENCY.md        # Latency optimization guide
    └── USB_GADGET.md     # USB gadget details
```

---

## References

- TSE public pentest: https://www.tse.jus.br/eleicoes/tpu
- Linux USB Gadget: https://kernel.org/doc/html/latest/usb/gadget.html
- USB/IP: http://usbip.sourceforge.net

If you need the Raspberry Pi to appear as a USB device to a host when the real peripheral is unplugged (maintenance window), use the Linux USB Gadget subsystem:

- Enable OTG and create a simple HID gadget using scripts under `scripts/gadget/`.
- Run the minimal keepalive feeder `python3 -m gadget.hid_keepalive` to periodically send input reports and keep the host link alive.
- See `docs/USB_GADGET.md` for details, limitations, and a systemd service example.

Legal and protocol note:

- Emulating a commercial device’s exact VID/PID and encrypted protocol may be restricted and technically complex. For true 1:1 emulation, you’ll need the device’s descriptors and protocol specifics; otherwise, use a generic HID presence during short maintenance windows.
