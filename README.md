# usb_radio_gateway
This repository is a exploit project for the brazilian eletronic voting sistem, This pentes is authorized for the public tests in 2025. https://www.tse.jus.br/eleicoes/tpu


## USB-over-IP via nRF24L01 between two Raspberry Pis

This project provides a working, minimal tunnel that carries IP packets over an nRF24L01 2.4GHz radio link between two Raspberry Pis. Once the IP link is up, you can run USB/IP on top to share a USB device from one Pi to the other without Wi‑Fi/Ethernet.

What you get:

- A Python tunnel daemon that bridges a TUN interface to the nRF24L01 (32-byte frames with fragmentation/reassembly)
- Shell scripts to set up TUN addresses and run the tunnel on each endpoint
- Optional systemd service to auto-start the tunnel
- USB/IP helper scripts for server/client

Limitations and notes:

- nRF24L01 has small frames (32 bytes) and modest data rates (250 kbps – 2 Mbps). Expect low throughput and higher latency vs Wi‑Fi.
- The link is point-to-point and unencrypted. Use at your own risk; add a VPN if you need confidentiality.
- Requires SPI enabled on both Pis and proper wiring of the nRF24L01 modules.

---

## Hardware wiring (Raspberry Pi + nRF24L01)

Default pins used by the tunnel (BCM):

- CE -> GPIO25
- CSN (chip select) -> CE0 (GPIO8)
- SCK -> GPIO11
- MOSI -> GPIO10
- MISO -> GPIO9
- Vcc -> 3.3V (never 5V)
- GND -> GND

You can change CE/CSN via CLI flags `--ce-pin` and `--csn-pin` (e.g., `D25`, `D8`).

Enable SPI on each Pi:

1) Edit `/boot/config.txt` (or `/boot/firmware/config.txt` on newer RPi OS) and ensure this line exists:

```
dtparam=spi=on
```

2) Reboot the Pi.

---

## Software install

On each Pi, run (as root):

```
sudo ./scripts/install.sh
```

This installs Python deps and enables SPI. Reboot if SPI was newly enabled.

---

## Bring up the IP-over-radio link

We create a TUN interface `tun0` on each Pi with a /30 point-to-point network (10.24.0.1 <-> 10.24.0.2).

Pi A:

```
./scripts/setup_tun_a.sh
./scripts/run_tunnel_a.sh
```

Pi B:

```
./scripts/setup_tun_b.sh
./scripts/run_tunnel_b.sh
```

Test connectivity once both tunnels are running:

```
ping -c 3 10.24.0.1   # from Pi B
ping -c 3 10.24.0.2   # from Pi A
```

If pings work, the IP tunnel over radio is up.

---

## Optional: Auto-start with systemd

Copy the unit and enable it. On each Pi:

```
sudo cp systemd/nrf-tun@.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now nrf-tun@a.service   # on Pi A
sudo systemctl enable --now nrf-tun@b.service   # on Pi B
```

Edit the unit if you need different pins, addresses, or channel.

---

## Run USB/IP over the radio link

On Pi A (server, with the USB device plugged in):

```
sudo ./scripts/usbip_server.sh <BUSID>
```

- Find `<BUSID>` via `usbip list -l` (e.g., `1-1`).
- This starts `usbipd` and binds the device.

On Pi B (client):

```
sudo ./scripts/usbip_client.sh 10.24.0.1 <BUSID>
```

Then verify on Pi B with `lsusb` and/or by accessing the device as if locally attached.

---

## Configuration knobs

The tunnel CLI supports:

- `--role` a|b (or server|client) to select which address is used for TX/RX
- `--channel` (default 0x76)
- `--ce-pin`, `--csn-pin` (default D25 and D8)
- `--tx-addr`, `--rx-addr` (5-byte pipe addresses in hex, default E0E0F1F1E0 / F1F1F0F0E0)
- `--rate` (250000, 1000000, 2000000)
- `--pa` power level in dBm (-18, -12, -6, 0)

You can edit `scripts/run_tunnel_*.sh` or the systemd unit to change these.

---

## How it works (design brief)

- The Python daemon opens `/dev/net/tun` (no PI) and an nRF24L01 radio.
- IP packets from `tun0` are fragmented into 32-byte radio frames with a tiny header (msg_id, frag_idx, frag_count), sent over the air.
- The peer collects fragments, reassembles the packet, and writes it into its `tun0` device.
- With the /30 configuration, you get an IP link suitable for TCP/UDP and thus USB/IP.

Edge cases handled:

- Fragment reassembly with timeout and GC (drops stale partial messages)
- Bounded TX queue with drop-tail under overload
- Simple retries at radio level using auto-ack

---

## Troubleshooting

- SPI not found: ensure `dtparam=spi=on`, reboot, and `ls /dev/spidev*` shows devices.
- No radio packets: check 3.3V supply and wiring (CE=GPIO25, CSN=GPIO8/CE0).
- Ping drops/slow: lower data rate (`--rate 250000`), increase PA (`--pa 0`), reduce interference (change `--channel`).
- USB/IP attach fails: verify `ping 10.24.0.1` works from Pi B, confirm port 3240 is reachable, and BUSID is correct.

---

## Security

Traffic over the nRF24L01 link is unencrypted and trivially sniffable/spoofable within range. For sensitive use, run a VPN (e.g., WireGuard) across `tun0` before running USB/IP, or adapt the code to add authenticated encryption.

---

## Kernel path for ultra‑baixa latência (nRF24 em kernel)

Se a latência mínima é crítica para cargas pequenas (até ~128 bytes), mova o caminho de dados para dentro do kernel (evita overhead de userspace e cópias extras):

Conteúdo inicial incluído em `kernel/nrf24_net/`:

- `nrf24_net.c`: módulo de kernel que registra uma interface `nrf0` (net_device) e fornece esqueleto de TX/RX via SPI.
- `Makefile`: Kbuild para compilar fora da árvore.

Como compilar no Raspberry Pi (requer headers do kernel):

```
sudo apt-get update && sudo apt-get install -y raspberrypi-kernel-headers build-essential
cd kernel/nrf24_net
make
sudo insmod nrf24_net.ko
ip link show nrf0
```

Notas importantes:

- O arquivo é um esqueleto: as funções `nrf24_hw_*` precisam ser conectadas ao SPI real (via `spi_sync`) e a re‑montagem dos frames deve emitir `skb`s em RX (`netif_rx`).
- Sugere-se definir um node DT `nordic,nrf24l01` no SPI0/CE0 e mapear CE/CSN/IRQ no overlay.
- Essa abordagem remove Python/userspace do caminho quente, reduzindo jitter; combine com um kernel RT para latência mais estável.

---

## Alternativa: Wi‑Fi P2P/Ad‑Hoc de baixa latência

Para payloads maiores (>= 1 KiB) ou quando se deseja simplicidade com IP, o Wi‑Fi otimizado pode atingir RTT estável de ~1–3 ms no RPi quando ajustado:

Scripts incluídos em `scripts/wifi/`:

- `adhoc_low_latency_a.sh` e `_b.sh`: configuram IBSS (Ad‑Hoc) em 5 GHz, desativam power save e offloads (GRO/GSO/TSO) que aumentam jitter.

Uso (em cada Pi):

```
./scripts/wifi/adhoc_low_latency_a.sh   # Pi A -> 10.25.0.1/30
./scripts/wifi/adhoc_low_latency_b.sh   # Pi B -> 10.25.0.2/30
ping -c 5 10.25.0.1   # a partir do Pi B
```

Afinando ainda mais:

- Desativar WMM/power management via opções do módulo do driver (dependente do chipset).
- Considerar Wi‑Fi 6/6E adaptadores USB/PCIe compatíveis com monitor/injeção para caminhos de Camada 2 (ex.: Wifibroadcast) quando latência/jitter mínimos forem mandatórios.
