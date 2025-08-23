# main.py — MAX3010x + Temperatura + IA + BLE (NUS) + Firebase (sin cambios)
# Envía por BLE: spo2, bpm, temp, modelPreccision (0..1), riskScore (0/1)
# Mantiene envío a Firebase como ya lo tenías.

import sys
import utime as time
from machine import I2C, Pin

# --- Sensores / UI ---
from lib.max30102 import MAX30105
from lib.max30102.heartrate import HeartRate
from lib.max30102.oxygen import OxygenSaturation
from lib.ssd1306.ssd1306 import SSD1306   # opcional

# --- BLE (NUS) ---
from BLERawSender import BLERawSender

# --- Firebase + IA (SIN CAMBIOS) ---
from lib.firebase_data_send.FirebaseRawSender import FirebaseRawSender
from lib.predictionModel.modeloIA.pesos_modelo import predict
from configuracion import WIFI_CONFIG, FIREBASE_CONFIG

# =========================== CONFIG ===========================
DEVICE_NAME       = "ESP32-SaudeRemota"
I2C_SCL_PIN       = 22
I2C_SDA_PIN       = 21
BUTTON_PIN        = 0

SAMPLE_RATE       = 400
LED_POWER         = 0x7F
RESET_THRESH      = 50000
AMP_MIN           = 15000
UI_REFRESH_MS     = 500
BLE_KEEPALIVE_MS  = 1000
FIREBASE_MIN_PERIOD_MS = 2000  # (igual que antes)

PRINT_SERIAL      = True

# =========================== ESTADO ===========================
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

# =========================== UTILS ===========================
def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def log(*a):
    if PRINT_SERIAL:
        try: print(*a)
        except: pass

# ======================== INICIALIZACIÓN ======================
# Botón parada
def _button_handler(pin):
    global stop_flag
    stop_flag = True
button = Pin(BUTTON_PIN, Pin.IN, Pin.PULL_UP)
button.irq(trigger=Pin.IRQ_FALLING, handler=_button_handler)

# I2C, sensor, OLED
i2c = I2C(0, scl=Pin(I2C_SCL_PIN), sda=Pin(I2C_SDA_PIN), freq=400000)
sensor = MAX30105(i2c)

if not sensor.begin():
    log("ERROR: MAX30105 no detectado.")
    sys.exit()

sensor.setup(
    powerLevel    = LED_POWER,
    sampleAverage = 1,
    ledMode       = 2,        # IR + Rojo (SpO2)
    sampleRate    = SAMPLE_RATE,
    pulseWidth    = 411,
    adcRange      = 16384
)

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

# Firebase (SIN CAMBIOS)
sender = FirebaseRawSender(
    email=FIREBASE_CONFIG["email"],
    password=FIREBASE_CONFIG["password"],
    api_key=FIREBASE_CONFIG["api_key"],
    database_url=FIREBASE_CONFIG["database_url"],
    wifi_config=WIFI_CONFIG
)

log("Sensor inicializado. Coloque su dedo en el sensor…")

# ======================= LECTURA / CÁLCULO ====================
def read_and_update():
    global finger_present, min_ir, spo2, bpm, spo2_valid, bpm_valid

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

# ===== BLE: enviar también riesgo (0/1) y precisión (0..1) =====
def send_ble(spo2_i, bpm_i, temp_f, risk_score, model_precision):
    """Envía por BLE: spo2,bpm,temp + modelPreccision (0..1) + riskScore (0/1)."""
    try: r = int(risk_score)
    except: r = 0
    try: p = float(model_precision)
    except: p = 0.0

    if ble.is_connected():
        try:
            # ¡OJO! BLERawSender espera 'modelPreccision' (doble 'c') para la web.
            ble.send_measurement(
                temperature=float(temp_f),
                bmp=float(bpm_i),
                spo2=float(spo2_i),
                modelPreccision=round(p, 4),
                riskScore=int(r)
            )
            log("[BLE] TX ->",
                f"SPO2={spo2_i}, BPM={bpm_i}, T={float(temp_f):.2f}, Risk={int(r)}, Prec={p:.4f}")
        except Exception as e:
            log("[BLE] ERROR notify:", e)
    else:
        log("[BLE] sin conexión; omitido:",
            f"SPO2={spo2_i}, BPM={bpm_i}, T={float(temp_f):.2f}, Risk={int(r)}, Prec={p:.4f}")

# ===== Firebase: lo dejamos como ya estaba =====
def send_firebase_unchanged(spo2_i, bpm_i, temp_f, label, prob):
    """Mantiene tu envío original a Firebase (sin tocar nombres/campos)."""
    global last_fb_send_ms
    now = time.ticks_ms()
    if time.ticks_diff(now, last_fb_send_ms) < FIREBASE_MIN_PERIOD_MS:
        return
    last_fb_send_ms = now
    try:
        sender.send_measurement(
            temperature=float(temp_f),
            bmp=int(bpm_i),
            spo2=int(spo2_i),
            modelPrecision=round(float(prob), 4),  # tu backend ya lo usaba así
            riskScore=int(label)
        )
        log("[FB] Enviado:", spo2_i, bpm_i, temp_f,
            " risk=", int(label), " prec=", round(float(prob), 4))
    except Exception as e:
        log("[FB] ERROR:", e)

# ======================== BUCLE PRINCIPAL =====================
try:
    while True:
        sv, bv = read_and_update()

        now = time.ticks_ms()
        if time.ticks_diff(now, last_ui_ms) > UI_REFRESH_MS:
            last_ui_ms = now
            refresh_temperature()

            if sv or bv:
                log("SpO2:", (int(spo2) if sv else "-"),
                    " BPM:", (("%.1f" % bpm) if bv else "-"),
                    " Temp:", ("%.2f°C" % temp))
            if display and display.is_connected():
                try:
                    if sv:
                        display.display_parameter("Oxigeno", int(spo2), "%", icon="oxygen")
                    else:
                        display.display_parameter("Ritmo Cardiaco", int(bpm), "bpm", icon="heart")
                except Exception:
                    pass

        if sv and bv:
            s_spo2 = int(clamp(spo2, 0, 100))
            s_bpm  = int(clamp(bpm, 30, 220))
            s_temp = float(temp)

            # === IA: riesgo (0/1) + precisión (0..1) ===
            try:
                label, prob = predict([s_spo2, s_bpm, s_temp])
                label = 1 if int(label) == 1 else 0
                prob  = float(prob)
                log(f"IA: prob={prob:.4f} →", ("Riesgo" if label==1 else "No riesgo"))
            except Exception as e:
                label, prob = 0, 0.0
                log("IA ERROR:", e)

            # BLE (con riesgo y precisión para la web)
            send_ble(s_spo2, s_bpm, s_temp, label, prob)

            # Firebase (SIN CAMBIOS)
            send_firebase_unchanged(s_spo2, s_bpm, s_temp, label, prob)

            last_ble_keepalive_ms = now
        else:
            if time.ticks_diff(now, last_ble_keepalive_ms) > BLE_KEEPALIVE_MS:
                last_ble_keepalive_ms = now
                # keep-alive para que la web “latido”:
                send_ble(0, 0, 0.0, 0, 0.0)

        if stop_flag:
            log("Parada solicitada por botón.")
            break

        time.sleep_ms(5)

except KeyboardInterrupt:
    log("Parada solicitada por Ctrl-C.")

finally:
    try:
        if display and display.is_connected():
            display.clear()
            try: display.display_text("Programa detenido")
            except: pass
    except Exception:
        pass
    sys.exit()
