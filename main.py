## @file main.py
#  MAX3010x + OLED + Firebase + IA + BLE (NUS → JSONL con BLERawSender)
#  - Envío keep‑alive (1 Hz) con ceros si no hay medidas válidas
#  - Cuando hay medidas válidas: envía a Firebase + IA + BLE JSONL (lo que espera server.py)

import time, sys
from machine import I2C, Pin
from lib.max30102 import MAX30105
from lib.max30102.heartrate import HeartRate
from lib.max30102.oxygen import OxygenSaturation
from lib.ssd1306.ssd1306 import SSD1306
from lib.firebase_data_send.FirebaseRawSender import FirebaseRawSender
from lib.predictionModel.modeloIA.pesos_modelo import predict
from configuracion import WIFI_CONFIG, FIREBASE_CONFIG

# === NUEVO: BLE mediante tu librería ===
# Asegúrate de que BLERawSender.py esté en la raíz del dispositivo o en /lib y ajusta el import si hace falta
from BLERawSender import BLERawSender

# ------------------------------------------------------------------
# Configuración general
# ------------------------------------------------------------------
printSerial = True

BUTTON_PIN  = 0
LED_POWER   = 0x7F
LED_OFF     = 0x00
stop_flag   = False

SAMPLE_RATE = 400

# I2C y periféricos
i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=400000)
sensor = MAX30105(i2c)
display = SSD1306(i2c=i2c)

# Algoritmos señal
hr = HeartRate()
ox = OxygenSaturation(sample_rate_hz=SAMPLE_RATE)

# Firebase
sender = FirebaseRawSender(
    email=FIREBASE_CONFIG["email"],
    password=FIREBASE_CONFIG["password"],
    api_key=FIREBASE_CONFIG["api_key"],
    database_url=FIREBASE_CONFIG["database_url"],
    wifi_config=WIFI_CONFIG
)

# ------------------------------------------------------------------
# Estado de medición
# ------------------------------------------------------------------
bpm = 0
spo2 = 0
temperature = 0.0
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

# ------------------------------------------------------------------
# Inicialización
# ------------------------------------------------------------------
button = Pin(BUTTON_PIN, Pin.IN, Pin.PULL_UP)
button.irq(trigger=Pin.IRQ_FALLING, handler=_button_handler)

# Sensor
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

# ------------------------------------------------------------------
# BLE: crea el emisor NUS
#   Muy importante: usa un nombre que coincida con el que escanea tu server.py
#   - server.py por defecto usa --device-name ESP32-SaudeRemota
#   - Si quieres usar "ESP32-SENSOR", lánzalo con: --device-name ESP32-SENSOR
# ------------------------------------------------------------------
ble_name = "ESP32-SaudeRemota"   # ← pon aquí el que vayas a usar con el server
ble = BLERawSender(device_name=ble_name, auto_wait_ms=0)  # no bloquea el arranque

last_ble_ping = time.ticks_ms()

# ------------------------------------------------------------------
# Bucle principal
# ------------------------------------------------------------------
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

            # refresco UI/serie cada 500 ms
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

                # cuando hay válidos → IA + Firebase + BLE JSON
                if bpm_valid and spo2_valid:
                    entrada_modelo = [spo2, bpm, temperature]
                    label, prob = predict(entrada_modelo)
                    if printSerial:
                        print(f"Probabilidad de riesgo: {prob:.4f}")
                        print("Clasificación:", "Riesgo" if label == 1 else "No riesgo")

                    # Firebase
                    sender.send_measurement(
                        temperature=temperature, bmp=bpm, spo2=spo2,
                        modelPrecision=round(prob, 4), riskScore=label
                    )

                    # BLE JSONL (línea JSON + '\n')
                    if ble.is_connected():
                        try:
                            ble.send_measurement(
                                temperature=temperature,
                                bmp=bpm,
                                spo2=spo2,
                                modelPreccision=round(prob, 4),
                                riskScore=label
                            )
                        except Exception as e:
                            if printSerial: print("[BLE] Error envío:", e)

        else:
            if finger_present:
                if printSerial: print("\nDedo retirado. Coloque su dedo en el sensor…")
                if display.is_connected(): display.display_finger_message()
                finger_present = False
                bpm_valid = False; spo2_valid = False
            time.sleep_ms(100)

        # ---------- Keep‑alive BLE cada 1 s ----------
        if time.ticks_diff(current_time, last_ble_ping) > 1000:
            s_spo2, s_bpm, s_temp = read_vitals()  # (0,0,0.0) si no hay válidos
            if ble.is_connected():
                try:
                    # manda una línea JSON con ceros si aún no hay medidas válidas
                    ble.send_measurement(
                        temperature=s_temp,
                        bmp=s_bpm,
                        spo2=s_spo2,
                        modelPreccision=0.0,
                        riskScore=0.0
                    )
                except Exception as e:
                    if printSerial: print("[BLE] keep‑alive error:", e)
            last_ble_ping = current_time

        # salida por botón
        if stop_flag:
            if printSerial: print("\nParada solicitada por botón.")
            break

        time.sleep_ms(5)

except KeyboardInterrupt:
    if printSerial: print("\nParada solicitada por Ctrl‑C.")

finally:
    if display.is_connected():
        display.clear()
    try:
        if display.is_connected(): display.display_text("Programa detenido")
    except AttributeError:
        pass
    sys.exit()