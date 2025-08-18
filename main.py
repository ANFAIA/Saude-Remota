## @file main.py
#  @brief MAX3010x + OLED + Firebase + IA + BLE (UART + Servicio Datos)
#         con envío continuo (keep-alive) cada 1 s a Web Bluetooth.
#  @version 1.3.0
#  ---------------------------------------------------------------------------

import time, sys
from machine import I2C, Pin
from lib.max30102 import MAX30105
from lib.max30102.heartrate import HeartRate
from lib.max30102.oxygen import OxygenSaturation
from lib.ssd1306.ssd1306 import SSD1306
from lib.firebase_data_send.FirebaseRawSender import FirebaseRawSender
from lib.predictionModel.modeloIA.pesos_modelo import predict
from configuracion import WIFI_CONFIG, FIREBASE_CONFIG

# =============================== BLE =========================================
import ubluetooth as bt

# --- Servicio UART (NUS) ---
UART_SERVICE_UUID = bt.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
UART_TX_UUID      = bt.UUID("6E400003-B5A3-F393-E0A9-E50E24DCCA9E")  # notify
UART_RX_UUID      = bt.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E")  # write

# --- Servicio propio de datos (solo-notify, pensado para Web Bluetooth) ---
DATA_SERVICE_UUID = bt.UUID("12345678-1234-5678-1234-56789ABCDEF0")
DATA_TX_UUID      = bt.UUID("12345678-1234-5678-1234-56789ABCDEF1")  # notify + read

class BLEPeripheral:
    def __init__(self, name="ESP32-SENSOR"):
        self.name = name
        self.ble = bt.BLE()
        self.ble.active(True)
        self.ble.irq(self._irq)

        tx_char = (UART_TX_UUID, bt.FLAG_NOTIFY)
        rx_char = (UART_RX_UUID, bt.FLAG_WRITE)
        data_tx = (DATA_TX_UUID, bt.FLAG_NOTIFY | bt.FLAG_READ)

        services = (
            (UART_SERVICE_UUID, (tx_char, rx_char)),
            (DATA_SERVICE_UUID, (data_tx,)),
        )
        ((self.tx_uart, self.rx_uart), (self.tx_data,)) = self.ble.gatts_register_services(services)

        self.conn_handle = None
        self._advertise()
        print("BLE listo. Anunciando como:", self.name)

    # ADV: flags + nombre (≤31 B)
    def _adv_payload(self) -> bytes:
        flags = b"\x02\x01\x06"  # LE General Discoverable + BR/EDR not supported
        nb = self.name.encode()
        name = bytes([len(nb) + 1, 0x09]) + nb  # 0x09 = Complete Local Name
        return flags + name

    # Scan Response: UUID 128-bit (NUS) para no superar 31 B
    def _scanresp_payload(self) -> bytes:
        u = bytes(UART_SERVICE_UUID)  # 16 B
        return bytes([len(u) + 1, 0x07]) + u  # 0x07 = Complete List of 128-bit UUIDs

    def _advertise(self):
        adv  = self._adv_payload()
        resp = self._scanresp_payload()
        self.ble.gap_advertise(300_000, adv_data=adv, resp_data=resp)  # intervalo en µs (300 ms)

    def _irq(self, event, data):
        if event == bt.IRQ_CENTRAL_CONNECT:
            self.conn_handle, _, _ = data
            print("BLE conectado:", self.conn_handle)
        elif event == bt.IRQ_CENTRAL_DISCONNECT:
            ch, _, _ = data
            if self.conn_handle == ch:
                print("BLE desconectado:", self.conn_handle)
                self.conn_handle = None
            self._advertise()
        elif event == bt.IRQ_GATTS_WRITE:
            pass  # Aquí podrías leer comandos desde RX si algún día los usas

    def notify_uart(self, s: str):
        if self.conn_handle is not None:
            self.ble.gatts_notify(self.conn_handle, self.tx_uart, s.encode("utf-8"))

    def notify_data(self, s: str):
        if self.conn_handle is not None:
            self.ble.gatts_notify(self.conn_handle, self.tx_data, s.encode("utf-8"))

# --- Envío BLE con trazas (ambos servicios) ----------------------------------
def send_ble_values(blep: BLEPeripheral, spo2, bpm, temp):
    try:
        msg = f"{int(spo2)},{int(bpm)},{float(temp):.2f}"
    except Exception:
        msg = "0,0,0.00"
    try:
        blep.notify_data(msg)
        blep.notify_uart(msg)
        print("[BLE] TX ->", msg)
    except Exception as e:
        print("[BLE] ERROR al notificar:", e)

# ============================== APP PRINCIPAL ================================
printSerial = True

BUTTON_PIN  = 0
LED_POWER   = 0x7F
LED_OFF     = 0x00
PROX_LED    = 0x10
PROX_THRESH = 0x20
stop_flag   = False

SAMPLE_RATE = 400

i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=400000)
sensor = MAX30105(i2c)
display = SSD1306(i2c=i2c)

hr = HeartRate()
ox = OxygenSaturation(sample_rate_hz=SAMPLE_RATE)

sender = FirebaseRawSender(
    email=FIREBASE_CONFIG["email"],
    password=FIREBASE_CONFIG["password"],
    api_key=FIREBASE_CONFIG["api_key"],
    database_url=FIREBASE_CONFIG["database_url"],
    wifi_config=WIFI_CONFIG
)

# Estado
beat_times = []
last_beat_time = 0
bpm = 0
spo2 = 0
temperature = 0
stable_count = 0
finger_present = False
min_ir = 100000
last_update_time = 0
reset_threshold = 50000
spo2_valid = False
bpm_valid  = False

spo2_ir_buf = []
spo2_red_buf = []
SPO2_BUF_SIZE = ox.BUFFER_SIZE

def _button_handler(pin):
    global stop_flag
    stop_flag = True

def read_vitals():
    """Devuelve (spo2:int, bpm:int, temp:float) validados o ceros."""
    global spo2, bpm, temperature, spo2_valid, bpm_valid
    if spo2_valid and bpm_valid:
        try:
            t = float(temperature)
        except:
            t = 0.0
        if 70 <= int(spo2) <= 100 and 30 <= int(bpm) <= 220 and 30.0 <= t <= 45.0:
            return int(spo2), int(bpm), t
    return 0, 0, 0.0

# ---------------------------------- MAIN -------------------------------------
button = Pin(BUTTON_PIN, Pin.IN, Pin.PULL_UP)
button.irq(trigger=Pin.IRQ_FALLING, handler=_button_handler)

if not sensor.begin():
    if printSerial:
        print("ERROR: MAX30105 no detectado.")
    while True:
        if stop_flag:
            if printSerial: print("Parada solicitada por botón.")
            sys.exit()
        time.sleep(1)

sensor.setup(
    powerLevel    = LED_POWER,
    sampleAverage = 1,
    ledMode       = 2,        # IR + Rojo
    sampleRate    = SAMPLE_RATE,
    pulseWidth    = 411,
    adcRange      = 16384
)

if display.is_connected():
    display.display_finger_message()
if printSerial:
    print("Sensor inicializado. Coloque su dedo en el sensor…")

# === Inicia BLE (UART + DATOS) y latido de 1 s ===
blep = BLEPeripheral("ESP32-SENSOR")
last_ble_ping = time.ticks_ms()

try:
    while True:
        current_time = time.ticks_ms()
        ir = sensor.getIR()
        red = sensor.getRed()

        if ir > reset_threshold:
            if not finger_present:
                if printSerial: print("\nDedo detectado. Midiendo…")
                if display.is_connected(): display.clear()
                finger_present = True
                min_ir = 100000
                hr = HeartRate()
                beat_times = []
                last_beat_time = 0
                stable_count = 0

            if ir < min_ir:
                min_ir = ir

            signal_strength = ir - min_ir
            if signal_strength > 15000:
                spo2_ir_buf.append(ir); spo2_red_buf.append(red)
                if len(spo2_ir_buf) > SPO2_BUF_SIZE:
                    spo2_ir_buf.pop(0); spo2_red_buf.pop(0)
                if len(spo2_ir_buf) == SPO2_BUF_SIZE:
                    spo2, spo2_valid, bpm, bpm_valid = ox.calculate_spo2_and_heart_rate(
                        spo2_ir_buf, spo2_red_buf
                    )

            if time.ticks_diff(current_time, last_update_time) > 500:
                last_update_time = current_time
                temperature = sensor.readTemperature()

                # OLED
                if display.is_connected():
                    if spo2_valid:
                        display.display_parameter("Oxigeno", spo2, "%", icon="oxygen")
                    else:
                        display.display_parameter("Ritmo Cardiaco", bpm, "bpm", icon="heart")

                # Serie
                if printSerial and (bpm_valid or spo2_valid):
                    if bpm_valid: print(f"LPM: {bpm:.1f}  Señal: {signal_strength}")
                    print(f"Temperatura: {temperature:.2f}°C")
                    if spo2_valid: print(f"SpO2: {spo2}%")

                # Cuando hay datos válidos: IA, Firebase y BLE
                if bpm_valid and spo2_valid:
                    temperature = sensor.readTemperature()
                    entrada_modelo = [spo2, bpm, temperature]
                    label, prob = predict(entrada_modelo)

                    if printSerial:
                        print(f"Probabilidad de riesgo: {prob:.4f}")
                        print("Clasificación:", "Riesgo" if label == 1 else "No riesgo")

                    sender.send_measurement(
                        temperature=temperature,
                        bmp=bpm,
                        spo2=spo2,
                        modelPrecision=round(prob, 4),
                        riskScore=label
                    )
                    if printSerial: print("Enviando datos a Firebase...")
                    sender.send_measurement(
                        temperature=temperature, bmp=bpm, spo2=spo2, modelPrecision=0, riskScore=0
                    )

                    # ---------- Envío BLE cuando hay válidos ----------
                    s_spo2, s_bpm, s_temp = read_vitals()
                    send_ble_values(blep, s_spo2, s_bpm, s_temp)

        else:
            if finger_present:
                if printSerial: print("\nDedo retirado. Coloque su dedo en el sensor…")
                if display.is_connected(): display.display_finger_message()
                finger_present = False
                bpm_valid = False
                spo2_valid = False
                stable_count = 0
            time.sleep_ms(100)

        # Señal débil
        if finger_present and (ir - min_ir) < 10000 and stable_count > 0:
            stable_count = max(0, stable_count - 1)
            if stable_count == 0:
                if printSerial: print("Señal débil. Ajuste el dedo")
                if display.is_connected(): display.display_weak_signal()

        # ---------- Keep-alive BLE cada 1 s (aunque no haya válidos) ----------
        if time.ticks_diff(current_time, last_ble_ping) > 1000:
            s_spo2, s_bpm, s_temp = read_vitals()  # 0,0,0 si aún no válidos
            send_ble_values(blep, s_spo2, s_bpm, s_temp)
            last_ble_ping = current_time

        # Parada limpia
        if stop_flag:
            if printSerial: print("\nParada solicitada por botón.")
            break

        time.sleep_ms(5)

except KeyboardInterrupt:
    if printSerial: print("\nParada solicitada por Ctrl-C.")

finally:
    if display.is_connected():
        display.clear()
    try:
        if display.is_connected(): display.display_text("Programa detenido")
    except AttributeError:
        pass
    sys.exit()
