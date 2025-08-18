# main.py - Test BLE simple
import ubluetooth as bt
import time

ble = bt.BLE()
ble.active(True)

# UUID propio ficticio
SVC_UUID = bt.UUID("12345678-1234-5678-1234-56789abcdef0")
CHAR_UUID = bt.UUID("12345678-1234-5678-1234-56789abcdef1")

CHAR = (CHAR_UUID, bt.FLAG_NOTIFY,)
SERVICES = ((SVC_UUID, (CHAR,)),)

handles = ble.gatts_register_services(SERVICES)
tx_handle = handles[0][0]

def adv_payload(name="ESP32-TEST"):
    return b"\x02\x01\x06" + bytes([len(name) + 1, 0x09]) + name.encode()

ble.gap_advertise(100, adv_data=adv_payload("ESP32-TEST"))

print("Anunciando como ESP32-TEST")

while True:
    ble.gatts_notify(0, tx_handle, b"hello")
    print("Enviado hello")
    time.sleep(2)
