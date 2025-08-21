# BLERawSender

**MicroPython library to send sensor measurements via Bluetooth Low Energy (BLE) UART/NUS to a central device (PC, smartphone, etc.).**

This library provides a simple interface to advertise an ESP32 (or any MicroPython BLE-enabled device) as a **Nordic UART Service (NUS)** peripheral and send data as **JSON lines (`\n` terminated)**.

---

## ✨ Features

- BLE UART/NUS service (TX: notify, RX: write).
- Advertising split into **ADV (flags + UUID)** and **SCAN RESPONSE (name)** to avoid 31-byte limit issues.
- Automatic handling of MTU exchange and data fragmentation.
- High-level API:
  - `send_measurement()` for temperature, heart rate, SpO₂, etc.
  - `send_raw()` for arbitrary JSON objects.
- Auto-retry advertising after disconnection.

---

## 📂 Installation

1. Copy `BLERawSender.py` into your MicroPython device (`/lib/` is recommended).

```bash
ampy put BLERawSender.py /lib/BLERawSender.py
```

2. Import it in your MicroPython script:

```python
from BLERawSender import BLERawSender
```

---

## 🚀 Usage Example

### Basic sender (ESP32 MicroPython)

```python
from BLERawSender import BLERawSender
import time

# Create BLE UART peripheral
ble = BLERawSender(device_name="ESP32-BLERaw", auto_wait_ms=10000)

if ble.is_connected():
    print("Central connected!")

# Send a structured measurement
ble.send_measurement(
    temperature=36.55,
    bmp=72.0,
    spo2=98.0,
    modelPreccision=0.93,
    riskScore=0.12
)

# Send arbitrary data
for i in range(3):
    ble.send_raw({"counter": i, "status": "ok"})
    time.sleep(1)
```

Output sent over BLE (JSON line):
```json
{"ts": 1690972761000, "data": {"temperature": 36.55, "bmp": 72.0, "spo2": 98.0, "modelPreccision": 0.93, "riskScore": 0.12}}
```

---

## 💻 Example Central (Python with [bleak](https://github.com/hbldh/bleak))

```python
import asyncio
from bleak import BleakClient, BleakScanner

UART_SERVICE_UUID = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
UART_TX_UUID      = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

async def run():
    print("🔎 Scanning...")
    device = await BleakScanner.find_device_by_name("ESP32-BLERaw")
    if not device:
        print("Device not found")
        return

    async with BleakClient(device) as client:
        def handle_notify(_, data: bytearray):
            print("📩 Received:", data.decode().strip())

        await client.start_notify(UART_TX_UUID, handle_notify)
        print("Connected! Listening for notifications...")
        await asyncio.sleep(60)  # keep connection open

asyncio.run(run())
```

Console output:
```
📩 Received: {"ts": 1690972761000, "data": {"temperature": 36.55, "bmp": 72.0, "spo2": 98.0}}
📩 Received: {"ts": 1690972762000, "data": {"counter": 0, "status": "ok"}}
```

---

## ⚠️ Notes

- Tested with **ESP32 + MicroPython 1.20+**.
- Real MTU depends on central device; max payload is `MTU-3`.
- If `resp_data` is not supported by your port, device name may not appear in scanner.

---

## 📜 License

MIT License — see [LICENSE](LICENSE) file.

---

## 👤 Author

**Alejandro Fernández Rodríguez**  
🔗 [GitHub](https://github.com/afernandezLuc)
