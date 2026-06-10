#main.py — MAX30102 + OLED (opcional) + IA + BLE
#envío BLE continuo (keep-alive 1 Hz) y, cuando hay medidas válidas, BLE + IA + REGLAS

import sys #sys: utilidades del sistema
import utime as time #módulo de tiempo de MicroPython, renombrado a time
from machine import I2C, Pin

#sensores
from lib.max30102 import MAX30105
from lib.max30102.heartrate import HeartRate
from lib.max30102.oxygen import OxygenSaturation
#(opcional) comenta si no tienes pantalla:
#from lib.ssd1306.ssd1306 import SSD1306

#BLE
from lib.BLERawSender import BLERawSender 

#modelo IA
from lib.predictionModel.modeloIA.pesos_modelo import predict

#configuración
DEVICE_NAME       = "ESP32-SaudeRemota"
I2C_SCL_PIN       = 22
I2C_SDA_PIN       = 21
BUTTON_PIN        = 0

SAMPLE_RATE       = 50 
LED_POWER         = 0x9F
FINGER_ON         = 52000      #histeresis entrada para evitar parpadeos al colocar el dedo
FINGER_OFF        = 48000      #histeresis salida
AMP_MIN           = 500
UI_REFRESH_MS     = 500
BLE_KEEPALIVE_MS  = 1000

#mejora de estabilidad
HISTORY_LEN       = 5          #media móvil (BPM/SpO2)
MED_WIN           = 5          #mediana para BPM
MAX_BPM_JUMP      = 6          #anti-spike por ciclo (lpm)
MAX_SPO2_JUMP     = 5          #anti-spike por ciclo (%)
WARMUP_MS         = 2000       #no usar medidas los 2s iniciales tras detectar dedo

#temperatura (offset y suavizado)
TEMP_OFFSET       = 0          #para corregir las lecturas iniciales más bajas
ALPHA_TEMP        = 0.25       #filtro exponencial 0.1 más suave

#rangos fisiológicos para validación de medidas
BPM_MIN,  BPM_MAX  = 45, 130
SPO2_MIN, SPO2_MAX = 70, 100

#umbrales clínicos (OR lógico) para la decisión por REGLAS
TEMP_LO, TEMP_HI = 36.0, 37.5
BPM_LO,  BPM_HI  = 60, 100
SPO2_LO          = 95

PRINT_SERIAL      = True #activa mensajes por consola

#estado global
stop_flag = False
last_beat_ms = 0
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

#historiales para suavizado
SPO2_HISTORY = []
BPM_HISTORY  = []
TEMP_HISTORY = []
BPM_RAW_HISTORY = []  #para mediana

def push_and_mean(value, history, maxlen):
    history.append(value)
    if len(history) > maxlen:
        history.pop(0)
    return sum(history) / len(history) #devuelve la media 

def median(xs):
    s = sorted(xs)
    n = len(s)
    return s[n//2] if n % 2 == 1 else 0.5*(s[n//2-1] + s[n//2]) #devuelve la mediana (promedio de los 2 centrales si es un número par)

def clamp(v, lo, hi):
    if v < lo: return lo
    if v > hi: return hi
    return v

def log(*a):
    if PRINT_SERIAL:
        try: print(*a)
        except: pass #evita que un fallo al imprimir rompa el programa

#regla clínica: riesgo si cualquier umbral se incumple (OR)
def rule_risk(spo2_v, bpm_v, temp_v):
    """(label, score, viols): label=1 si se incumple cualquiera; score=violaciones/3."""
    viols = []
    if (temp_v < TEMP_LO) or (temp_v > TEMP_HI): viols.append("temp")
    if (bpm_v  < BPM_LO)  or (bpm_v  > BPM_HI):  viols.append("bpm")
    if (spo2_v < SPO2_LO):                        viols.append("spo2")
    label = 1 if viols else 0
    score = len(viols) / 3.0 #score en 0...1
    return label, score, viols

#inicialización
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
    sampleAverage = 8,     
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

#lectura/cálculo
def read_and_update():
    """Lee IR/Red, actualiza buffers y calcula spo2/bpm si hay ventana completa."""
    global finger_present, finger_since_ms, min_ir, spo2, bpm, spo2_valid, bpm_valid

    ir  = sensor.getIR()
    red = sensor.getRed()

    global last_beat_ms

    if hr.check_for_beat(ir):
        now_beat = time.ticks_ms()
        if last_beat_ms != 0:
            dt = time.ticks_diff(now_beat, last_beat_ms)
            bpm_calc = 60000 / dt
            print("Latido detectado. BPM calculado =", bpm_calc)

            if BPM_MIN <= bpm_calc <= BPM_MAX:
                bpm_valid = True
                BPM_RAW_HISTORY.append(bpm_calc)
                if len(BPM_RAW_HISTORY) > MED_WIN:
                    BPM_RAW_HISTORY.pop(0)
                bpm = median(BPM_RAW_HISTORY)
                print("BPM por HeartRate =", bpm)
            else:
                print("BPM detectado fuera de rango:", bpm_calc)

        last_beat_ms = now_beat

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
            BPM_RAW_HISTORY.clear()
            last_beat_ms = 0
            spo2_valid = bpm_valid = False

        if ir < min_ir:
            min_ir = ir

        strength = ir - min_ir
        if strength > AMP_MIN:
            spo2_ir_buf.append(ir)
            spo2_red_buf.append(red)
            if len(spo2_ir_buf) > SPO2_BUF_SIZE:
                spo2_ir_buf.pop(0)
                spo2_red_buf.pop(0) #mantiene el tamaño fijo eliminando el valor más antiguo
            if len(spo2_ir_buf) == SPO2_BUF_SIZE:
                spo2_calc, sv, bpm_calc, bv = ox.calculate_spo2_and_heart_rate(
                    spo2_ir_buf, spo2_red_buf
                )

                #validación fisiológica previa
                #if bv and (BPM_MIN <= bpm_calc <= BPM_MAX):
                    #bpm_valid = True
                    #anti-spike por salto
                    #if BPM_HISTORY and abs(bpm_calc - BPM_HISTORY[-1]) > MAX_BPM_JUMP:
                        #bpm_calc = BPM_HISTORY[-1] #si salta demasiado respecto al último valor histórico, se recorta al valor anterior
                    #mediana de ventana corta para estabilizar picos
                    #BPM_RAW_HISTORY.append(bpm_calc)
                    #if len(BPM_RAW_HISTORY) > MED_WIN:
                        #BPM_RAW_HISTORY.pop(0)
                    #bpm = median(BPM_RAW_HISTORY)
                #else:
                    #bpm_valid = False
                #no se usa el BPM calculado por oxygen.py porque es menos estable, se calcula arriba con HeartRate()
                pass
                if sv and (SPO2_MIN <= spo2_calc <= SPO2_MAX):
                    if SPO2_HISTORY and abs(spo2_calc - SPO2_HISTORY[-1]) > MAX_SPO2_JUMP:
                        spo2_valid = False
                    else:
                        spo2_valid = True
                        spo2 = spo2_calc
                else:
                    spo2_valid = False

                #warm-up inicial
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
        raw = float(sensor.readTemperature())
        corr = raw + TEMP_OFFSET   #offset fijo
        #EMA + media móvil para estabilizar
        if not TEMP_HISTORY:
            temp_ema = corr
        else:
            temp_ema = (1-ALPHA_TEMP) * TEMP_HISTORY[-1] + ALPHA_TEMP * corr
        temp = push_and_mean(temp_ema, TEMP_HISTORY, HISTORY_LEN)
    except Exception:
        temp = 0.0

def send_ble(spo2_i, bpm_i, temp_f, label, y):
    """Envío por BLE con la API existente (formato que espera el server). No tocar BLE."""
    if ble.is_connected():
        try:
            ble.send_measurement(
                temperature=temp_f,
                bmp=bpm_i,                 #la web/servidor esperan 'bmp'
                spo2=spo2_i,
                riskScore=label,           #0/1
                modelPreccision=y          #score 0...1
            )
            log("[BLE] TX ->", f"{spo2_i},{bpm_i},{temp_f:.2f} label={label} y={y:.3f}")
        except Exception as e:
            log("[BLE] ERROR notify:", e)
    else:
        log("[BLE] sin conexión; omitido:", f"{spo2_i},{bpm_i},{temp_f:.2f}")

#bucle principal
try:
    while True:
        sv, bv = read_and_update()

        now = time.ticks_ms()
        if time.ticks_diff(now, last_ui_ms) > UI_REFRESH_MS:
            last_ui_ms = now
            refresh_temperature()

            #mostrar por consola
            if sv or bv:
                log("SpO2:", (int(spo2) if sv else "-"),
                    " BPM:", (("%.1f" % bpm) if bv else "-"),
                    " Temp:", ("%.2f°C" % temp))

            #OLED
            if display and display.is_connected():
                try:
                    if sv:
                        display.display_parameter("Oxigeno", int(spo2), "%", icon="oxygen")
                    elif bv:
                        display.display_parameter("Ritmo Cardiaco", int(bpm), "bpm", icon="heart")
                except Exception:
                    pass

        #usar promedios al enviar
        if sv and bv:
            spo2_use = push_and_mean(spo2, SPO2_HISTORY, HISTORY_LEN)
            bpm_use  = push_and_mean(bpm,  BPM_HISTORY,  HISTORY_LEN)

            s_spo2 = int(clamp(spo2_use, SPO2_MIN, SPO2_MAX))
            s_bpm  = int(clamp(bpm_use,  BPM_MIN,  BPM_MAX))
            s_temp = float(clamp(temp, 25.0, 45.0))

            #IA 
            try:
                model_label, model_y = predict([s_spo2, s_bpm, s_temp])  # (0/1, 0..1)
            except Exception as e:
                log("IA ERROR:", e)
                model_label, model_y = 0, 0.0 #si falla, pone no riesgo por defecto

            #reglas clínicas (prioritarias sobre la IA, OR lógico)
            rule_label, rule_score, viols = rule_risk(s_spo2, s_bpm, s_temp)

            if rule_label == 1:
                final_label = 1
                final_y = max(model_y, rule_score)  
                log(f"[RULE] Riesgo por: {','.join(viols)} "
                    f"(T={s_temp:.2f}°C, BPM={s_bpm}, SpO2={s_spo2}%)")
            else:
                final_label = int(model_label)
                final_y = float(model_y)

            send_ble(s_spo2, s_bpm, s_temp, final_label, final_y)
            last_ble_keepalive_ms = now
        else:
            if time.ticks_diff(now, last_ble_keepalive_ms) > BLE_KEEPALIVE_MS: #mantiene un latido temporal
                last_ble_keepalive_ms = now

        if stop_flag:
            log("Parada solicitada por botón.")
            break

        time.sleep_ms(5) #pequeña espera para no saturar CPU/I2C

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