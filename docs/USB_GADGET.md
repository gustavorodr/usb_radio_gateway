# USB Device Emulation (Failover) on Raspberry Pi

Goal: keep a USB device "present" to a host even when the real sensor is unplugged, by making a Raspberry Pi act as a USB device (gadget) and providing minimal keep-alive behavior.

Important:
- Only certain Raspberry Pis can act as a USB device (OTG/peripheral). Pi Zero/Zero 2 W and CM/CM4 (with proper carrier) work. Pi 4B's USB-A ports are host-only; the USB-C is power and not generally a USB device data port.
- Cloning a commercial device's VID/PID and security features may violate license or law. Use your own VID/PID or get permission.
- Some biometric sensors use encrypted, vendor-specific protocols; a perfect emulation may require keys/chips you do not possess. For maintenance-only presence, a generic HID keepalive may suffice if the host software tolerates inactivity.

## 1) Enable OTG (once)

```
sudo ./scripts/gadget/enable_otg.sh
sudo reboot
```

## 2) Create a basic HID gadget

This creates a simple HID device with an 8-byte input report using ConfigFS. Adjust VID/PID/report descriptor for your use.

```
sudo ./scripts/gadget/create_hid_gadget.sh
```

Now the Pi should enumerate as a USB HID on the host. Verify with `lsusb` on the host.

## 3) Send periodic keep-alive reports

```
HID_DEV=/dev/hidg0 REPORT_SIZE=8 PERIOD=0.5 python3 -m gadget.hid_keepalive
```

If you install as a service, keep this daemon running whenever the real sensor is unavailable.

## 4) Bridging to a real sensor (optional, advanced)

If the real sensor is connected to another path (e.g., remote over USB/IP or a local USB host on the Pi via a second controller), you can replace the keepalive with a proxy that forwards reports. For vendor-specific protocols, consider:
- **FunctionFS (usb_f_fs)**: Implement endpoints and handle control requests from userspace.
- **USB Raw Gadget**: Userspace can see every control transfer and craft responses.
- **Replay tooling** (e.g., usbrply): Capture and reproduce known-good traffic, if allowed.

This repository includes only the minimal HID keepalive demo. A full DP5360 emulation would require the device's exact descriptors and protocol, which are out of scope here.

## 5) Systemd service example

Create `/etc/systemd/system/hid-keepalive.service`:

```
[Unit]
Description=HID gadget keepalive
After=multi-user.target

[Service]
Type=simple
Environment=HID_DEV=/dev/hidg0
Environment=REPORT_SIZE=8
Environment=PERIOD=0.5
ExecStart=/usr/bin/python3 -m gadget.hid_keepalive
Restart=always
RestartSec=1

[Install]
WantedBy=multi-user.target
```

Then:

```
sudo systemctl daemon-reload
sudo systemctl enable --now hid-keepalive.service
```

## 6) Troubleshooting
- Ensure `dwc2` and `libcomposite` are loaded and a UDC is present (`ls /sys/class/udc`).
- Use a short, known-good USB cable and the correct OTG-capable port.
- If the host polls vendor endpoints that the simple HID function doesn't provide, switch to FunctionFS/Raw Gadget and implement those endpoints.
