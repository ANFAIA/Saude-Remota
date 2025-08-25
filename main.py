# main.py — MAX3010x + OLED (opcional) + IA + Firebase + BLE (NUS)
# Envío BLE continuo (keep‑alive 1 Hz) y, cuando hay medidas válidas, BLE + Firebase + IA.

import sys
import utime as time
from machine import I2C, Pin

# --- Sensores / UI ---
from lib.max30102 import MAX30105
from lib.max30102.heartrate import HeartRate
from lib.max30102.oxygen import OxygenSaturation
# (opcional) comenta si no tienes pantalla:
from lib.ssd1306.ssd1306 import SSD1306

# --- BLE (NUS) ---
from BLERawSender import BLERawSender  # ponlo en /lib/BLERawSender.py

# --- Firebase + IA ---
from lib.firebase_data_send.FirebaseRawSender import FirebaseRawSender
from lib.predictionModel.modeloIA.pesos_modelo import predict
from configuracion import WIFI_CONFIG, FIREBASE_CONFIG

# =========================== CONFIGURACIÓN ===========================
DEVICE_NAME    = "ESP32-SaudeRemota"  # nombre BLE (corto = más visible)
I2C_SCL_PIN    = 22
I2C_SDA_PIN    = 21
BUTTON_PIN     = 0          # IO0 (BOOT) para parada limpia

SAMPLE_RATE    = 400        # Hz
LED_POWER      = 0x7F
RESET_THRESH   = 50000      # umbral IR para “hay dedo”
AMP_MIN        = 15000      # amplitud mínima (ir - min_ir)
UI_REFRESH_MS  = 500
BLE_KEEPALIVE_MS = 1000     # envío 0,0,0 cuando no hay válidos
FIREBASE_MIN_PERIOD_MS = 2000  # no mandar a Firebase más a menudo que esto

PRINT_SERIAL   = True

# =========================== ESTADO GLOBAL ===========================
stop_flag = False

spo2_ir_buf = []
spo2_red_buf = []
finger_present = False
min_ir = 100000

spo2 = 0
bpm  = 0
temp = 0.0
spo2_valid = False
bpm_valid  = False

last_ui_ms = time.ticks_ms()
last_ble_keepalive_ms = time.ticks_ms()
last_fb_send_ms = 0

# =========================== UTILIDADES ==============================
def clamp(v, lo, hi):
    if v < lo: return lo
    if v > hi: return hi
    return v

def log(*a):
    if PRINT_SERIAL:
        try: print(*a)
        except: pass

# =========================== INICIALIZACIÓN ==========================
# Botón parada
def _button_handler(pin):
    global stop_flag
    stop_flag = True
button = Pin(BUTTON_PIN, Pin.IN, Pin.PULL_UP)
button.irq(trigger=Pin.IRQ_FALLING, handler=_button_handler)

# I2C, sensor y pantalla
i2c = I2C(0, scl=Pin(I2C_SCL_PIN), sda=Pin(I2C_SDA_PIN), freq=400000)
sensor = MAX30105(i2c)

if not sensor.begin():
    log("ERROR: MAX30105 no detectado.")
    sys.exit()

sensor.setup(
    powerLevel    = LED_POWER,
    sampleAverage = 1,
    ledMode       = 2,          # IR + Rojo (necesario para SpO2)
    sampleRate    = SAMPLE_RATE,
    pulseWidth    = 411,
    adcRange      = 16384
)

# (opcional) Pantalla
try:
    display = SSD1306(i2c=i2c)
except Exception:
    display = None
if display and display.is_connected():
    display.display_finger_message()

# Algoritmos
hr = HeartRate()
ox = OxygenSaturation(sample_rate_hz=SAMPLE_RATE)
SPO2_BUF_SIZE = ox.BUFFER_SIZE

# BLE
ble = BLERawSender(device_name=DEVICE_NAME, auto_wait_ms=0)
log("BLE anunciando como", DEVICE_NAME)

# Firebase
#sender = FirebaseRawSender(
    #email=FIREBASE_CONFIG["email"],
    #password=FIREBASE_CONFIG["password"],
    #api_key=FIREBASE_CONFIG["api_key"],
    #database_url=FIREBASE_CONFIG["database_url"],
    #wifi_config=WIFI_CONFIG
#)

log("Sensor inicializado. Coloque su dedo en el sensor…")

# =========================== LECTURA / CÁLCULO =======================
def read_and_update():
    """Lee una muestra IR/Red, actualiza buffers y calcula spo2/bpm si hay ventana completa."""
    global finger_present, min_ir, spo2, bpm, temp, spo2_valid, bpm_valid

    ir  = sensor.getIR()
    red = sensor.getRed()

    if ir > RESET_THRESH:
        if not finger_present:
            log("Dedo detectado. Midiendo…")
            finger_present = True
            min_ir = 100000
            spo2_ir_buf.clear()
            spo2_red_buf.clear()
            spo2_valid = False
            bpm_valid  = False

        if ir < min_ir:
            min_ir = ir

        strength = ir - min_ir
        if strength > AMP_MIN:
            spo2_ir_buf.append(ir)
            spo2_red_buf.append(red)
            if len(spo2_ir_buf) > SPO2_BUF_SIZE:
                spo2_ir_buf.pop(0)
                spo2_red_buf.pop(0)
            if len(spo2_ir_buf) == SPO2_BUF_SIZE:
                spo2, spo2_valid, bpm, bpm_valid = ox.calculate_spo2_and_heart_rate(
                    spo2_ir_buf, spo2_red_buf
                )
        else:
            spo2_valid = False
            bpm_valid  = False
    else:
        if finger_present:
            log("Dedo retirado. Coloque su dedo…")
        finger_present = False
        spo2_valid = False
        bpm_valid  = False

    return spo2_valid, bpm_valid

def refresh_temperature():
    global temp
    try:
        temp = float(sensor.readTemperature())
    except Exception:
        temp = 0.0

def send_ble(spo2_i, bpm_i, temp_f, label, prob):
    """Envío por BLE con protección."""
    if ble.is_connected():
        try:
            BLERawSender espera 'modelPreccision' (con doble c) por compatibilidad
            ble.send_measurement(
                temperature=temp_f,
                bmp=bpm_i,
                spo2=spo2_i,
                modelPreccision=prob,
                riskScore=label
            )
            log("[BLE] TX ->", f"{spo2_i},{bpm_i},{temp_f:.2f}")
        except Exception as e:
            log("[BLE] ERROR notify:", e)
    else:
        log("[BLE] sin conexión; omitido:", f"{spo2_i},{bpm_i},{temp_f:.2f}")

#def send_firebase(spo2_i, bpm_i, temp_f, label, prob):
    #"""Envío a Firebase con control de frecuencia."""
    #global last_fb_send_ms
    #now = time.ticks_ms()
    #if time.ticks_diff(now, last_fb_send_ms) < FIREBASE_MIN_PERIOD_MS:
        #return
    #last_fb_send_ms = now
    #try:
        #sender.send_measurement(
            #temperature=temp_f,
            #bmp=bpm_i,
            #spo2=spo2_i,
            #modelPrecision=round(float(prob), 4),  # Firebase usa 'modelPrecision' (una c)
            #riskScore=int(label)
        #)
        #log("[FB] Enviado: spo2=", spo2_i, " bpm=", bpm_i, " temp=", temp_f, " prob=", round(float(prob),4), " label=", label)
    #except Exception as e:
        #log("[FB] ERROR:", e)

# =========================== BUCLE PRINCIPAL =========================
try:
    while True:
        sv, bv = read_and_update()

        now = time.ticks_ms()
        if time.ticks_diff(now, last_ui_ms) > UI_REFRESH_MS:
            last_ui_ms = now
            refresh_temperature()

            # UI por serie
            if sv or bv:
                log("SpO2:", (int(spo2) if sv else "-"),
                    " BPM:", (("%.1f" % bpm) if bv else "-"),
                    " Temp:", ("%.2f°C" % temp))

            # UI en pantalla
            if display and display.is_connected():
                try:
                    if sv:
                        display.display_parameter("Oxigeno", int(spo2), "%", icon="oxygen")
                    else:
                        display.display_parameter("Ritmo Cardiaco", int(bpm), "bpm", icon="heart")
                except Exception:
                    pass

        # Envíos
        if sv and bv:
            s_spo2 = int(clamp(spo2, 0, 100))
            s_bpm  = int(clamp(bpm, 30, 220))
            s_temp = float(clamp(temp, 25.0, 45.0))

            #IA
            #try:
                #label, prob = predict([s_spo2, s_bpm, s_temp])
                #log(f"IA: prob={float(prob):.4f} →", ("Riesgo" if int(label)==1 else "No riesgo"))
            #except Exception as e:
                #label, prob = 0, 0.0
                #log("IA ERROR:", e)

             BLE (en cada lectura válida)
            send_ble(s_spo2, s_bpm, s_temp, label, prob)

            # Firebase (rate‑limited)
            #send_firebase(s_spo2, s_bpm, s_temp, label, prob)

            last_ble_keepalive_ms = now  # resetea el temporizador
        else:
             keep‑alive BLE 0,0,0 cada 1 s
            if time.ticks_diff(now, last_ble_keepalive_ms) > BLE_KEEPALIVE_MS:
                last_ble_keepalive_ms = now
                send_ble(0, 0, 0.0)

        # Parada por botón
        if stop_flag:
            log("Parada solicitada por botón.")
            break

        time.sleep_ms(5)

except KeyboardInterrupt:
    log("Parada solicitada por Ctrl‑C.")

finally:
    try:
        if display and display.is_connected():
            display.clear()
            try: display.display_text("Programa detenido")
            except: pass
    except Exception:
        pass
    sys.exit()
