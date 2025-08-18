## @file main.py
#  MAX3010x + OLED + Firebase + IA + BLE (SOLO NUS TX notify)
#  Envío continuo (keep-alive 1 Hz) y cuando hay medidas válidas.
#  ----------------------------------------------------------------

import time, sys
from machine import I2C, Pin
from lib.max30102 import MAX30105
from lib.max30102.heartrate import HeartRate
from lib.max30102.oxygen import OxygenSaturation
from lib.ssd1306.ssd1306 import SSD1306
from lib.firebase_data_send.FirebaseRawSender import FirebaseRawSender
from lib.predictionModel.modeloIA.pesos_modelo import predict
from configuracion import WIFI_CONFIG, FIREBASE_CONFIG

# =============================== BLE (NUS) ================================
import ubluetooth as bt

NUS_SERVICE_UUID = bt.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
NUS_TX_UUID      = bt.UUID("6E400003-B5A3-F393-E0A9-E50E24DCCA9E")  # notify
NUS_RX_UUID      = bt.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E")  # write

class BLEPeripheral:
    def __init__(self, name="ESP32-SENSOR"):
        self.name = name
        self.ble = bt.BLE()
        self.ble.active(True)
        self.ble.irq(self._irq)

        tx_char = (NUS_TX_UUID, bt.FLAG_NOTIFY)
        rx_char = (NUS_RX_UUID, bt.FLAG_WRITE)
        ((self.tx_handle, self.rx_handle),) = self.ble.gatts_register_services(
            ((NUS_SERVICE_UUID, (tx_char, rx_char)),)
        )

        self.conn_handle = None
        self._advertise()
        print("BLE listo. Anunciando como:", self.name)

    # ADV: flags + nombre
    def _adv_payload(self) -> bytes:
        flags = b"\x02\x01\x06"
        nb = self.name.encode()
        name = bytes([len(nb) + 1, 0x09]) + nb
        return flags + name

    # Scan response: UUID 128-bit del servicio NUS
    def _scanresp_payload(self) -> bytes:
        u = bytes(NUS_SERVICE_UUID)
        return bytes([len(u) + 1, 0x07]) + u

    def _advertise(self):
        self.ble.gap_advertise(300_000,  # 300 ms en µs
                               adv_data=self._adv_payload(),
                               resp_data=self._scanresp_payload())

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
            pass  # aquí podrías leer comandos de RX si algún día los usas

    def notify_uart(self, s: str):
        if self.conn_handle is not None:
            self.ble.gatts_notify(self.conn_handle, self.tx_handle, s.encode("utf-8"))
        else:
            # útil para depurar si la web no está realmente conectada
            print("[BLE] OMITIDO (sin conexión):", s)

# --- Helper de envío con trazas
def send_ble_values(blep: BLEPeripheral, spo2, bpm, temp):
    try:
        msg = f"{int(spo2)},{int(bpm)},{float(temp):.2f}"
    except Exception:
        msg = "0,0,0.00"
    if blep.conn_handle is None:
        print("[BLE] OMITIDO (sin conexión):", msg)
        return
    try:
        blep.notify_uart(msg)
        print("[BLE] TX ->", msg, " (conn=", blep.conn_handle, ")")
    except Exception as e:
        print("[BLE] ERROR al notificar:", e)

# ============================== APLICACIÓN ================================
printSerial = True

BUTTON_PIN  = 0
LED_POWER   = 0x7F
LED_OFF     = 0x00
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
bpm = 0
spo2 = 0
temperature = 0
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

# ------------------------------- MAIN -----------------------------------
button = Pin(BUTTON_PIN, Pin.IN, Pin.PULL_UP)
button.irq(trigger=Pin.IRQ_FALLING, handler=_button_handler)

if not sensor.begin():
    if printSerial: print("ERROR: MAX30105 no detectado.")
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

# === Inicia BLE (solo NUS) y temporizador keep-alive ===
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
                spo2_ir_buf.clear(); spo2_red_buf.clear()

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

            # refresco UI/serie
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

                # cuando hay válidos: IA, Firebase y envío
                if bpm_valid and spo2_valid:
                    entrada_modelo = [spo2, bpm, temperature]
                    label, prob = predict(entrada_modelo)
                    if printSerial:
                        print(f"Probabilidad de riesgo: {prob:.4f}")
                        print("Clasificación:", "Riesgo" if label == 1 else "No riesgo")
                    sender.send_measurement(
                        temperature=temperature, bmp=bpm, spo2=spo2,
                        modelPrecision=round(prob, 4), riskScore=label
                    )
                    # notifica a la web por NUS
                    s_spo2, s_bpm, s_temp = read_vitals()
                    send_ble_values(blep, s_spo2, s_bpm, s_temp)

        else:
            if finger_present:
                if printSerial: print("\nDedo retirado. Coloque su dedo en el sensor…")
                if display.is_connected(): display.display_finger_message()
                finger_present = False
                bpm_valid = False; spo2_valid = False
            time.sleep_ms(100)

        # ---------- Keep-alive cada 1 s ----------
        if time.ticks_diff(current_time, last_ble_ping) > 1000:
            s_spo2, s_bpm, s_temp = read_vitals()  # 0,0,0.00 si no válidos
            send_ble_values(blep, s_spo2, s_bpm, s_temp)
            last_ble_ping = current_time

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
