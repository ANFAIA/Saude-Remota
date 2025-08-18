## @file main.py
#  @brief Medición de FC, SpO2 y temperatura (MAX3010x) con OLED/Firebase
#         y envío por BLE (UART-like) para Web Bluetooth en Chrome.
#  @version 1.1.3  (BLE: ADV flags+name, UUID en scan resp, intervalo en µs)
#  ---------------------------------------------------------------------------

import time
import sys
from machine import I2C, Pin
from lib.max30102 import MAX30105
from lib.max30102.heartrate import HeartRate
from lib.max30102.oxygen import OxygenSaturation
from lib.ssd1306.ssd1306 import SSD1306
from lib.firebase_data_send.FirebaseRawSender import FirebaseRawSender
from lib.predictionModel.modeloIA.pesos_modelo import predict
from configuracion import WIFI_CONFIG, FIREBASE_CONFIG

# =============================== BLE (NUS-like) ==============================
import ubluetooth as bt

UART_SERVICE_UUID = bt.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
UART_TX_UUID      = bt.UUID("6E400003-B5A3-F393-E0A9-E50E24DCCA9E")  # notify (ESP32 -> Chrome)
UART_RX_UUID      = bt.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E")  # write  (Chrome -> ESP32)

class BLEPeripheral:
    def __init__(self, name="ESP32-SENSOR"):
        self.name = name
        self.ble = bt.BLE()
        self.ble.active(True)
        self.ble.irq(self._irq)

        self.tx_char = (UART_TX_UUID, bt.FLAG_NOTIFY)
        self.rx_char = (UART_RX_UUID, bt.FLAG_WRITE)
        ((self.tx_handle, self.rx_handle),) = self.ble.gatts_register_services(
            ((UART_SERVICE_UUID, (self.tx_char, self.rx_char)),)
        )
        self.conn_handle = None
        self._advertise()
        print("BLE listo. Anunciando como:", self.name)

    # --- ADV payload seguro: FLAGS + NOMBRE (<=31 B) ---
    def _adv_payload(self) -> bytes:
        # 0x01 = Flags → 0x06 (LE General Discoverable + BR/EDR not supported)
        flags = b"\x02\x01\x06"
        # 0x09 = Complete Local Name
        nb = self.name.encode()
        name = bytes([len(nb) + 1, 0x09]) + nb
        return flags + name

    # --- Scan Response con UUID 128-bit del servicio (<=31 B) ---
    def _scanresp_payload(self) -> bytes:
        # 0x07 = Complete List of 128-bit Service Class UUIDs
        u = bytes(UART_SERVICE_UUID)  # 16 bytes
        return bytes([len(u) + 1, 0x07]) + u

    def _advertise(self):
        adv  = self._adv_payload()
        resp = self._scanresp_payload()
        # Intervalo en MICROsegundos (p. ej. 300 ms)
        self.ble.gap_advertise(300_000, adv_data=adv, resp_data=resp)

    def _irq(self, event, data):
        if event == bt.IRQ_CENTRAL_CONNECT:
            self.conn_handle, _, _ = data
            print("BLE conectado:", self.conn_handle)
        elif event == bt.IRQ_CENTRAL_DISCONNECT:
            ch, _, _ = data
            if self.conn_handle == ch:
                print("BLE desconectado:", self.conn_handle)
                self.conn_handle = None
            self._advertise()  # reanunciar
        elif event == bt.IRQ_GATTS_WRITE:
            # Aquí podrías leer comandos desde Chrome (RX)
            pass

    def notify_str(self, s: str):
        if self.conn_handle is not None:
            try:
                self.ble.gatts_notify(self.conn_handle, self.tx_handle, s.encode("utf-8"))
            except Exception as e:
                print("BLE notify error:", e)

# ------------------------------- MAIN DATA -----------------------------------
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

# ----------------------------- AUX FUNCTIONS ---------------------------------
def _button_handler(pin):
    global stop_flag
    stop_flag = True

def leds_on():
    sensor.setPulseAmplitudeIR(LED_POWER)
    sensor.setPulseAmplitudeRed(LED_POWER)

def leds_off():
    sensor.setPulseAmplitudeIR(LED_OFF)
    sensor.setPulseAmplitudeRed(LED_OFF)

def read_vitals():
    """Devuelve (spo2:int, bpm:int, temp:float) ya validados o ceros."""
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

# === Inicia BLE ===
blep = BLEPeripheral("ESP32-SENSOR")

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

                if display.is_connected():
                    if spo2_valid:
                        display.display_parameter("Oxigeno", spo2, "%", icon="oxygen")
                    else:
                        display.display_parameter("Ritmo Cardiaco", bpm, "bpm", icon="heart")

                if printSerial and (bpm_valid or spo2_valid):
                    if bpm_valid: print(f"LPM: {bpm:.1f}  Señal: {signal_strength}")
                    print(f"Temperatura: {temperature:.2f}°C")
                    if spo2_valid: print(f"SpO2: {spo2}%")

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

                    # ---------- Envío BLE a Chrome ----------
                    s_spo2, s_bpm, s_temp = read_vitals()
                    blep.notify_str(f"{s_spo2},{s_bpm},{s_temp:.2f}")

        else:
            if finger_present:
                if printSerial: print("\nDedo retirado. Coloque su dedo en el sensor…")
                if display.is_connected(): display.display_finger_message()
                finger_present = False
                bpm_valid = False
                spo2_valid = False
                stable_count = 0
            time.sleep_ms(100)

        if finger_present and (ir - min_ir) < 10000 and stable_count > 0:
            stable_count = max(0, stable_count - 1)
            if stable_count == 0:
                if printSerial: print("Señal débil. Ajuste el dedo")
                if display.is_connected(): display.display_weak_signal()

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
