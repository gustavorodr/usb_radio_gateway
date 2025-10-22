#!/usr/bin/env bash
set -euo pipefail
# Run tunnel on endpoint A
python3 -m nrf_tun --role a --tun tun0 --channel 0x76 --ce-pin D25 --csn-pin D8 --tx-addr E0E0F1F1E0 --rx-addr F1F1F0F0E0 --rate 1000000 --pa -6
