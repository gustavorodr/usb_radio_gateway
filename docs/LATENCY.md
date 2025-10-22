# Guia de Latência e Modos de Operação

Este documento resume recomendações práticas para minimizar latência P2P entre dois Raspberry Pis.

## 1) nRF24L01+ com caminho em kernel (mínima latência para payloads pequenos)

- Meta: RTT sub‑milissegundo para mensagens pequenas (12–128 bytes) em condições ideais.
- Estratégia: mover TX/RX para o kernel (módulo `nrf24_net`) para evitar overhead de userspace e cópias.
- A fazer no driver: acesso SPI via `spi_sync`, configuração do rádio (canal, data rate, auto‑ack), reassemblagem de frames (32B) e emissão de `skb`s via `netif_rx`.
- Dicas: kernel RT opcional; polling curto em RX para reduzir jitter; aumentar PA/antena quando necessário.

## 2) IP sobre nRF24 (simples, mas maior latência)

- Disponível no pacote Python `nrf_tun` (userspace). Mais fácil de operar, porém latência maior devido a fragmentação 32B + cópia userspace.
- Recomendado apenas para testes e para dispositivos USB/IP de baixa taxa.

## 3) Wi‑Fi P2P/Ad‑Hoc (1–3 ms RTT estável com tuning)

- Scripts `scripts/wifi/adhoc_low_latency_*.sh` montam IBSS em 5 GHz, desativam power save e offloads de NIC.
- Ajuste conforme o chipset (desabilitar WMM e power management no driver).
- Ideal para payloads maiores (>= 1 KiB) e quando simplicidade IP importa.

## 4) Wi‑Fi Layer‑2 Raw (Wifibroadcast) – avançado

- Para latência/jitter mínimos com robustez (FEC), usar injeção 802.11 em modo monitor.
- Requer adaptadores compatíveis e configuração avançada. Não incluído aqui, mas suportado conceitualmente.

## 5) Considerações gerais

- Pequenos pacotes: nRF24 em kernel vence em latência.
- Grandes pacotes/throughput: Wi‑Fi otimizado vence.
- Segurança: adicione VPN (WireGuard) sobre o link quando necessário.
