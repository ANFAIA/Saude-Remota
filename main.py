# main.py — MÍNIMO: BLE NUS keep‑alive (0,0,0.00 cada 1 s)
import time
from machine import Pin
import ubluetooth as bt

# -------- Compatibilidad de versiones (elige el primer nombre que exista) --
def _pick(*names):
    for n in names:
        if hasattr(bt, n):
            return getattr(bt, n)
    return None

IRQ_CENTRAL_CONNECT    = _pick('IRQ_CENTRAL_CONNECT',    '_IRQ_CENTRAL_CONNECT')
IRQ_CENTRAL_DISCONNECT = _pick('IRQ_CENTRAL_DISCONNECT', '_IRQ_CENTRAL_DISCONNECT')
IRQ_GATTS_WRITE        = _pick('IRQ_GATTS_WRITE', '_IRQ_GATTS_WRITE', 'GATTS_WRITE')

# UUIDs NUS (Nordic UART Service)
SVC_UUID = bt.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
TX_UUID  = bt.UUID("6E400003-B5A3-F393-E0A9-E50E24DCCA9E")  # notify
RX_UUID  = bt.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E")  # write

LED = Pin(2, Pin.OUT)  # LED integrado (parpadea al enviar)

class NUSPeripheral:
    def __init__(self, name="ESP32-SENSOR"):
        self.name = name
        self.ble  = bt.BLE()
        self.ble.active(True)
        self.ble.irq(self._irq)

        tx = (TX_UUID, bt.FLAG_NOTIFY)
        rx = (RX_UUID, bt.FLAG_WRITE)
        ((self.tx_handle, self.rx_handle),) = self.ble.gatts_register_services(((SVC_UUID, (tx, rx)),))
        self.conn = None
        self._advertise()

    def _adv_payload(self):
        # Flags + nombre
        flags = b"\x02\x01\x06"
        nb = self.name.encode()
        name = bytes([len(nb) + 1, 0x09]) + nb
        return flags + name

    def _scanresp_payload(self):
        u = bytes(SVC_UUID)  # UUID 128‑bit para que el navegador lo vea
        return bytes([len(u) + 1, 0x07]) + u

    def _advertise(self):
        self.ble.gap_advertise(300_000, adv_data=self._adv_payload(), resp_data=self._scanresp_payload())

    def _irq(self, event, data):
        if IRQ_CENTRAL_CONNECT is not None and event == IRQ_CENTRAL_CONNECT:
            self.conn, _, _ = data
        elif IRQ_CENTRAL_DISCONNECT is not None and event == IRQ_CENTRAL_DISCONNECT:
            self.conn = None
            self._advertise()
        elif IRQ_GATTS_WRITE is not None and event == IRQ_GATTS_WRITE:
            # Podrías leer comandos RX aquí (no usado)
            pass

    def notify(self, s: str):
        if self.conn is not None:
            try:
                LED.on()
                self.ble.gatts_notify(self.conn, self.tx_handle, s.encode())
            finally:
                LED.off()

def main():
    nus = NUSPeripheral("ESP32-SENSOR")
    # Bucle de keep‑alive estable (no bloqueante)
    while True:
        nus.notify("0,0,0.00")
        time.sleep(1)

try:
    main()
except Exception as e:
    # Evita resets silenciosos si algo raro pasa
    try:
        import sys
        sys.print_exception(e)
    except:
        pass
