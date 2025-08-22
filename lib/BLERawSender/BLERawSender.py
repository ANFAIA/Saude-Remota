# BLERawSender.py (compat MicroPython 1.19.x)
import ujson as json
import ubluetooth as bt
import utime as time

# Eventos (con compat)
_IRQ_CENTRAL_CONNECT    = getattr(bt, "_IRQ_CENTRAL_CONNECT", 1)
_IRQ_CENTRAL_DISCONNECT = getattr(bt, "_IRQ_CENTRAL_DISCONNECT", 2)
_IRQ_GATTS_WRITE        = getattr(bt, "_IRQ_GATTS_WRITE", 3)
_IRQ_MTU_EXCHANGED      = getattr(bt, "_IRQ_MTU_EXCHANGED", 21)

# UUIDs NUS
_UART_SERVICE_UUID = bt.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
_UART_RX_UUID      = bt.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E")  # WRITE
_UART_TX_UUID      = bt.UUID("6E400003-B5A3-F393-E0A9-E50E24DCCA9E")  # NOTIFY

_FLAG_WRITE = bt.FLAG_WRITE
_FLAG_WRITE_NO_RESPONSE = bt.FLAG_WRITE_NO_RESPONSE
_FLAG_NOTIFY = bt.FLAG_NOTIFY

def _adv_payload_flags_only():
    # ADV con sólo FLAGS (LE General Discoverable + BR/EDR not supported)
    p = bytearray()
    p.extend((2, 0x01, 0x02 | 0x04))
    return bytes(p)

def _scan_resp_payload_name(name: str):
    p = bytearray()
    if name:
        n = name.encode()
        if len(n) > 29:  # 31-(len+type)
            n = n[:29]
        p.extend((len(n) + 1, 0x09))
        p.extend(n)
    return bytes(p)

class _BLEUART:
    def __init__(self, name="ESP32-BLERaw", adv_interval_ms=100, preferred_mtu=247):
        self._ble = bt.BLE()
        self._ble.active(True)
        try:
            self._ble.config(gap_name=name)
        except Exception:
            pass
        try:
            self._ble.config(mtu=preferred_mtu)
        except Exception:
            pass

        self._ble.irq(self._irq)

        tx = (_UART_TX_UUID, _FLAG_NOTIFY)
        rx = (_UART_RX_UUID, _FLAG_WRITE | _FLAG_WRITE_NO_RESPONSE)
        ((self._tx_handle, self._rx_handle),) = self._ble.gatts_register_services(
            ((_UART_SERVICE_UUID, (tx, rx)),)
        )

        self._name = name
        self._conn = None
        self._mtu = 23
        self._adv_interval_us = adv_interval_ms * 1000

        # *** COMPAT ***
        # ADV = SOLO FLAGS (sin UUIDs) → evitamos bytes(UUID) en firmwares antiguos
        self._adv = _adv_payload_flags_only()
        # SCAN RESPONSE = NOMBRE
        self._scan = _scan_resp_payload_name(self._name)

        self._safe_stop_adv()
        self._start_adv()

    def _irq(self, event, data):
        if event == _IRQ_CENTRAL_CONNECT:
            self._conn, _, _ = data
        elif event == _IRQ_CENTRAL_DISCONNECT:
            self._conn = None
            self._start_adv()
        elif event == _IRQ_MTU_EXCHANGED:
            try:
                ch, mtu = data
                if self._conn == ch:
                    self._mtu = mtu
            except Exception:
                pass
        elif event == _IRQ_GATTS_WRITE:
            pass

    def is_connected(self):
        return self._conn is not None

    def max_payload(self):
        return max(1, self._mtu - 3)  # ATT notify header = 3 bytes

    def wait_for_connection(self, timeout_ms=None):
        t0 = time.ticks_ms()
        while not self.is_connected():
            time.sleep_ms(50)
            if timeout_ms is not None and time.ticks_diff(time.ticks_ms(), t0) > timeout_ms:
                return False
        return True

    def send(self, data: bytes):
        if not self.is_connected():
            raise RuntimeError("No hay central BLE conectado.")
        chunk = self.max_payload()
        for i in range(0, len(data), chunk):
            self._ble.gatts_notify(self._conn, self._tx_handle, data[i:i+chunk])
            time.sleep_ms(5)

    def _safe_stop_adv(self):
        for arg in (None, 0):
            try:
                self._ble.gap_advertise(arg)
            except Exception:
                pass
        time.sleep_ms(10)

    def _start_adv(self):
        self._safe_stop_adv()
        try:
            # ports nuevos
            self._ble.gap_advertise(self._adv_interval_us, self._adv, connectable=True, resp_data=self._scan)
        except TypeError:
            # ports antiguos (sin resp_data)
            try:
                self._ble.gap_advertise(self._adv_interval_us, self._adv)
            except Exception:
                # último intento por si la firma exige kwargs distintos
                self._ble.gap_advertise(self._adv_interval_us)

class BLERawSender:
    def __init__(self, device_name="ESP32-BLERaw", auto_wait_ms=0):
        self._uart = _BLEUART(name=device_name)
        if auto_wait_ms:
            self._uart.wait_for_connection(timeout_ms=auto_wait_ms)

    def is_connected(self):
        return self._uart.is_connected()

    def wait_for_central(self, timeout_ms=None):
        return self._uart.wait_for_connection(timeout_ms=timeout_ms)

    def send_measurement(self, temperature, bmp, spo2, modelPreccision=0.0, riskScore=0.0, timestamp_ms=None):
        payload = {
            "temperature": round(float(temperature), 2),
            "bmp": round(float(bmp), 2),
            "spo2": round(float(spo2), 2),
            "modelPreccision": round(float(modelPreccision), 2),
            "riskScore": round(float(riskScore), 2),
        }
        self.send_raw(payload, timestamp_ms)

    def send_raw(self, data, timestamp_ms=None):
        if timestamp_ms is None:
            try:
                timestamp_ms = int(time.time() * 1000)
            except Exception:
                timestamp_ms = time.ticks_ms()
        if not self._uart.is_connected():
            raise RuntimeError("No hay central BLE conectado. Conéctate desde el ordenador antes de enviar.")
        line = json.dumps({"ts": timestamp_ms, "data": data}) + "\n"
        self._uart.send(line.encode("utf-8"))
