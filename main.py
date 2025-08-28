# main.py — MAX3010x + OLED (opcional) + IA + BLE (NUS)
# Envío BLE continuo (keep-alive 1 Hz) y, cuando hay medidas válidas, BLE + IA.

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
from lib.BLERawSender import BLERawSender  # /lib/BLERawSender.py

# --- Modelo IA ---
from lib.predictionModel.modeloIA.pesos_modelo import predict

# =========================== CONFIGURACIÓN ===========================
DEVICE_NAME       = "ESP32-SaudeRemota"
I2C_SCL_PIN       = 22
I2C_SDA_PIN       = 21
BUTTON_PIN        = 0

SAMPLE_RATE       = 400
LED_POWER         = 0x7F
FINGER_ON         = 52000      # histeresis entrada
FINGER_OFF        = 48000      # histeresis salida
AMP_MIN           = 15000
UI_REFRESH_MS     = 500
BLE_KEEPALIVE_MS  = 1000

# --- NUEVO: parámetros de calidad/suavizado ---
HISTORY_LEN       = 5          # tamaño media móvil (5–10)
ALPHA_TEMP        = 0.25       # EMA temperatura (0.1 más suave)
TEMP_OFFSET       = 2.0        # corrección (ajústalo con tu termómetro)
WARMUP_MS         = 2000       # no usar medidas los 2 s iniciales tras detectar dedo

# Rangos fisiológicos (filtros)
BPM_MIN,  BPM_MAX  = 40, 200
SPO2_MIN, SPO2_MAX = 70, 100

PRINT_SERIAL      = True

# =========================== ESTADO GLOBAL ===========================
stop_flag = False

spo2_ir_buf = []
spo2_red_buf = []
finger_present = False
finger_since_ms = 0
min_ir = 100000

spo2 = 0
bpm  = 0
temp = 0.0
spo2_valid = False
bpm_valid  = False
label, y = predict([spo2, bpm, temp])

last_ui_ms = time.ticks_ms()
last_ble_keepalive_ms = time.ticks_ms()

# --- NUEVO: historiales para promediar ---
SPO2_HISTORY = []
BPM_HISTORY  = []
TEMP_HISTORY = []

# --- helpers suavizado ---
def push_and_mean(value, history, maxlen):
    history.append(value)
    if len(history) > maxlen:
        history.pop(0)
    return sum(history) / len(history)

def clamp(v, lo, hi):
    if v < lo: return lo
    if v > hi: return hi
    return v

def log(*a):
    if PRINT_SERIAL:
        try: print(*a)
        except: pass

# =========================== INICIALIZACIÓN ==========================
def _button_handler(pin):
    global stop_flag
    stop_flag = True

button = Pin(BUTTON_PIN, Pin.IN, Pin.PULL_UP)
button.irq(trigger=Pin.IRQ_FALLING, handler=_button_handler)

i2c = I2C(0, scl=Pin(I2C_SCL_PIN), sda=Pin(I2C_SDA_PIN), freq=400000)
sensor = MAX30105(i2c)

if not sensor.begin():
    log("ERROR: MAX30105 no detectado.")
    raise SystemExit

sensor.setup(
    powerLevel    = LED_POWER,
    sampleAverage = 1,     # si quieres aún más estabilidad: prueba 2–4
    ledMode       = 2,
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

hr = HeartRate()
ox = OxygenSaturation(sample_rate_hz=SAMPLE_RATE)
SPO2_BUF_SIZE = ox.BUFFER_SIZE

ble = BLERawSender(device_name=DEVICE_NAME, auto_wait_ms=0)
log("BLE anunciando como", DEVICE_NAME)
log("Sensor inicializado. Coloque su dedo…")

# =========================== LECTURA / CÁLCULO =======================
def read_and_update():
    """Lee IR/Red, actualiza buffers y calcula spo2/bpm si hay ventana completa."""
    global finger_present, finger_since_ms, min_ir, spo2, bpm, spo2_valid, bpm_valid

    ir  = sensor.getIR()
    red = sensor.getRed()

    has_finger = (ir > FINGER_OFF) if finger_present else (ir > FINGER_ON)

    if has_finger:
        if not finger_present:
            log("Dedo detectado. Midiendo…")
            finger_present = True
            finger_since_ms = time.ticks_ms()
            min_ir = 100000
            spo2_ir_buf.clear()
            spo2_red_buf.clear()
            SPO2_HISTORY.clear()
            BPM_HISTORY.clear()
            spo2_valid = bpm_valid = False

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
                spo2_calc, sv, bpm_calc, bv = ox.calculate_spo2_and_heart_rate(
                    spo2_ir_buf, spo2_red_buf
                )

                # --- NUEVO: filtros fisiológicos antes de aceptar ---
                if bv and (BPM_MIN <= bpm_calc <= BPM_MAX):
                    bpm_valid = True
                    bpm = bpm_calc
                else:
                    bpm_valid = False

                if sv and (SPO2_MIN <= spo2_calc <= SPO2_MAX):
                    spo2_valid = True
                    spo2 = spo2_calc
                else:
                    spo2_valid = False

                # --- NUEVO: warm-up; invalida si aún es pronto ---
                if time.ticks_diff(time.ticks_ms(), finger_since_ms) < WARMUP_MS:
                    spo2_valid = False
                    bpm_valid  = False
        else:
            spo2_valid = bpm_valid = False
    else:
        if finger_present:
            log("Dedo retirado. Coloque su dedo…")
            if display and display.is_connected():
                display.display_finger_message()
        finger_present = False
        spo2_valid = bpm_valid = False

    return spo2_valid, bpm_valid

def refresh_temperature():
    global temp
    try:
        t = float(sensor.readTemperature()) + TEMP_OFFSET
        # --- NUEVO: EMA + media móvil de temperatura ---
        # primero EMA corto (suaviza picos), luego media de ventana corta
        if not TEMP_HISTORY:
            temp_ema = t
        else:
            temp_ema = (1-ALPHA_TEMP) * TEMP_HISTORY[-1] + ALPHA_TEMP * t
        temp = push_and_mean(temp_ema, TEMP_HISTORY, HISTORY_LEN)
    except Exception:
        temp = 0.0

def send_ble(spo2_i, bpm_i, temp_f, label, y):
    """Envío por BLE con la API existente (formato que espera el server)."""
    if ble.is_connected():
        try:
            ble.send_measurement(
                temperature=temp_f,
                bmp=bpm_i,                 # la web espera 'bmp'
                spo2=spo2_i,
                riskScore=label,           # 0/1
                modelPreccision=y          # score 0..1
            )
            log("[BLE] TX ->", f"{spo2_i},{bpm_i},{temp_f:.2f} label={label} y={y:.3f}")
        except Exception as e:
            log("[BLE] ERROR notify:", e)
    else:
        log("[BLE] sin conexión; omitido:", f"{spo2_i},{bpm_i},{temp_f:.2f}")

# =========================== BUCLE PRINCIPAL =========================
try:
    while True:
        sv, bv = read_and_update()

        now = time.ticks_ms()
        if time.ticks_diff(now, last_ui_ms) > UI_REFRESH_MS:
            last_ui_ms = now
            refresh_temperature()

            # Mostrar por consola (raw para depurar)
            if sv or bv:
                log("SpO2:", (int(spo2) if sv else "-"),
                    " BPM:", (("%.1f" % bpm) if bv else "-"),
                    " Temp:", ("%.2f°C" % temp))

            # OLED
            if display and display.is_connected():
                try:
                    if sv:
                        display.display_parameter("Oxigeno", int(spo2), "%", icon="oxygen")
                    elif bv:
                        display.display_parameter("Ritmo Cardiaco", int(bpm), "bpm", icon="heart")
                except Exception:
                    pass

        # --- NUEVO: promediado móvil al usar/mandar ---
        if sv and bv:
            spo2_use = push_and_mean(spo2, SPO2_HISTORY, HISTORY_LEN)
            bpm_use  = push_and_mean(bpm,  BPM_HISTORY,  HISTORY_LEN)

            s_spo2 = int(clamp(spo2_use, SPO2_MIN, SPO2_MAX))
            s_bpm  = int(clamp(bpm_use,  BPM_MIN,  BPM_MAX))
            s_temp = float(clamp(temp, 25.0, 45.0))

            # IA
            try:
                label, y = predict([s_spo2, s_bpm, s_temp])  # (0/1, score 0..1)
            except Exception as e:
                log("IA ERROR:", e)
                label, y = 0, 0.0

            send_ble(s_spo2, s_bpm, s_temp, label, y)
            last_ble_keepalive_ms = now
        else:
            if time.ticks_diff(now, last_ble_keepalive_ms) > BLE_KEEPALIVE_MS:
                last_ble_keepalive_ms = now
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
    raise SystemExit
