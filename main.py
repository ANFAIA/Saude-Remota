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
from lib.ssd1306.ssd1306 import SSD1306

#BLE
from lib.BLERawSender import BLERawSender 

#modelo IA
from lib.predictionModel.modeloIA.pesos_modelo import predict

#configuración
DEVICE_NAME       = "ESP32-SaudeRemota"
I2C_SCL_PIN       = 22
I2C_SDA_PIN       = 21
BUTTON_PIN        = 0

SAMPLE_RATE       = 100 
LED_POWER         = 0x9F
FINGER_ON         = 52000      #histeresis entrada para evitar parpadeos al colocar el dedo
FINGER_OFF        = 48000      #histeresis salida
AMP_MIN           = 500
UI_REFRESH_MS     = 500
BLE_KEEPALIVE_MS  = 1000
BLE_SEND_MS       = 2000
SCREEN_UPDATE_MS  = 2000

#mejora de estabilidad
HISTORY_LEN       = 5          #media móvil (BPM/SpO2)
MED_WIN           = 8          #mediana para BPM
MAX_BPM_JUMP      = 20         #anti-spike por ciclo (lpm)
MAX_SPO2_JUMP     = 3          #anti-spike por ciclo (%)
SPO2_BOOTSTRAP_SAMPLES = 3
WARMUP_MS         = 3000       #no usar medidas los 3s iniciales tras detectar dedo

#temperatura (offset y suavizado)
TEMP_OFFSET       = 3         #para corregir las lecturas iniciales más bajas
ALPHA_TEMP        = 0.1       #filtro exponencial 0.1 más suave
TEMP_TARGET       = 35.9      #temperatura fisiológica de referencia
TEMP_GAIN         = 0.1       #ganancia proporcional para acercar la lectura a la referencia
#rangos fisiológicos para validación de medidas
BPM_MIN,  BPM_MAX  = 40, 110
SPO2_MIN, SPO2_MAX = 70, 100

#umbrales clínicos (OR lógico) para la decisión por REGLAS
TEMP_LO, TEMP_HI = 36.0, 37.5
BPM_LO,  BPM_HI  = 60, 100
SPO2_LO          = 95

PRINT_SERIAL      = True #activa mensajes por consola

#estado global
stop_flag = False
last_beat_ms = 0
last_good_bpm = 0
spo2_ir_buf = []
spo2_red_buf = []
finger_present = False
finger_since_ms = 0
min_ir = 100000
last_ble_send_ms = 0
last_valid_bpm_ms = 0
last_calc_ms = 0
sample_counter = 0
last_beat_sample = None
temp_baseline = None
temp_filtered = None
bpm_display = 0
spo2_display = 0
SPO2_DISPLAY_STEP = 1.0
CALC_INTERVAL_MS = 500
BPM_BOOTSTRAP_SAMPLES = 3
BPM_BOOTSTRAP_RANGE = 25
SENSOR_SAMPLE_RATE = 400
SAMPLE_AVERAGE = 4
EFFECTIVE_SAMPLE_RATE = SENSOR_SAMPLE_RATE // SAMPLE_AVERAGE

spo2 = 0
bpm  = 0
temp = 0.0
spo2_valid = False
bpm_valid  = False
label, y = predict([spo2, bpm, temp])

last_ui_ms = time.ticks_ms()
last_ble_keepalive_ms = time.ticks_ms()
last_ble_send_ms = time.ticks_ms()
last_screen_update_ms = time.ticks_ms()
screen_mode = 0
last_risk_label = 0

#historiales para suavizado
SPO2_HISTORY = []
BPM_HISTORY  = []
TEMP_HISTORY = []
BPM_RAW_HISTORY = []  #para mediana
BPM_STABLE_HISTORY = []
SPO2_PENDING_HISTORY = []
BPM_PENDING_HISTORY = []
BPM_DISPLAY_STEP = 4
bpm_smooth_display = 0
BPM_STABLE_WIN = 5
BPM_MAX_DEVIATION = 15
BPM_REBASE_SAMPLES = 3
BPM_LOW_REBASE_SAMPLES = 5
BPM_DISPLAY_MIN = 60
BPM_DISPLAY_MAX = 100

def push_and_mean(value, history, maxlen):
    history.append(value)
    if len(history) > maxlen:
        history.pop(0)
    return sum(history) / len(history) #devuelve la media 

def median(xs):
    s = sorted(xs)
    n = len(s)
    return s[n//2] if n % 2 == 1 else 0.5*(s[n//2-1] + s[n//2]) #devuelve la mediana (promedio de los 2 centrales si es un número par)

def stabilize_bpm_output(value):

    if value <= 0:
        return value

    # Primer valor
    if len(BPM_STABLE_HISTORY) == 0:
        BPM_STABLE_HISTORY.append(value)
        return value

    reference = median(BPM_STABLE_HISTORY)

    # Aceptar únicamente valores próximos a la referencia estable
    if abs(value - reference) <= BPM_MAX_DEVIATION:

        BPM_STABLE_HISTORY.append(value)

        if len(BPM_STABLE_HISTORY) > BPM_STABLE_WIN:
            BPM_STABLE_HISTORY.pop(0)

    # Si aparece un valor anómalo, se conserva la mediana estable
    return median(BPM_STABLE_HISTORY)

def smooth_bpm_display(value):

    global bpm_smooth_display

    if value <= 0:
        return bpm_smooth_display

    # Primera medida
    if bpm_smooth_display == 0:
        bpm_smooth_display = value
        return bpm_smooth_display

    diff = value - bpm_smooth_display

    if diff > BPM_DISPLAY_STEP:
        bpm_smooth_display += BPM_DISPLAY_STEP

    elif diff < -BPM_DISPLAY_STEP:
        bpm_smooth_display -= BPM_DISPLAY_STEP

    else:
        bpm_smooth_display = value

    return bpm_smooth_display

def stabilize_spo2_display(value):

    global spo2_display

    if value <= 0:
        return spo2_display

    # Primera medida
    if spo2_display == 0:
        spo2_display = value
        return spo2_display

    diff = value - spo2_display

    # Limitar cuánto puede cambiar cada actualización
    if diff > SPO2_DISPLAY_STEP:
        spo2_display += SPO2_DISPLAY_STEP

    elif diff < -SPO2_DISPLAY_STEP:
        spo2_display -= SPO2_DISPLAY_STEP

    else:
        spo2_display = value

    return spo2_display

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
    sampleAverage = SAMPLE_AVERAGE,     
    ledMode       = 2,
    sampleRate    = SENSOR_SAMPLE_RATE,
    pulseWidth    = 411,
    adcRange      = 16384
)

try:
    display = SSD1306(width=128, height=32, i2c=i2c)
except Exception:
    display = None
if display and display.is_connected():
    display.display_finger_message()

hr = HeartRate()
ox = OxygenSaturation(sample_rate_hz=EFFECTIVE_SAMPLE_RATE)
SPO2_BUF_SIZE = ox.BUFFER_SIZE

ble = BLERawSender(device_name=DEVICE_NAME, auto_wait_ms=0)
log("BLE anunciando como", DEVICE_NAME)
log("Sensor inicializado. Coloque su dedo…")

#lectura/cálculo
def read_and_update():
    """Lee IR/Red, actualiza buffers y calcula spo2/bpm si hay ventana completa."""
    global finger_present, finger_since_ms, min_ir, spo2, bpm, spo2_valid, bpm_valid, last_good_bpm
    global last_beat_ms
    global last_valid_bpm_ms
    global last_calc_ms
    global sample_counter, last_beat_sample
    global temp_baseline, temp_filtered
    global bpm_display, bpm_smooth_display, spo2_display

    #Si el búfer local está vacío, descargar nuevas muestras del FIFO
    if sensor.available() == 0:

        if not sensor.safeCheck(250):
            return False, False

    #Procesar la muestra pendiente más antigua, no únicamente la última
    ir = sensor.getFIFOIR()
    red = sensor.getFIFORed()

    #Marcar la muestra como consumida
    sensor.nextSample()

    sample_counter += 1

    has_finger = (ir > FINGER_OFF) if finger_present else (ir > FINGER_ON)

    if has_finger:
        if not finger_present:
            log("Dedo detectado. Midiendo…")
            finger_present = True
            finger_since_ms = time.ticks_ms()
            min_ir = 100000

            bpm = 0
            spo2 = 0

            spo2_ir_buf.clear()
            spo2_red_buf.clear()
            SPO2_HISTORY.clear()
            BPM_HISTORY.clear()
            BPM_RAW_HISTORY.clear()
            BPM_STABLE_HISTORY.clear()
            SPO2_PENDING_HISTORY.clear()
            BPM_PENDING_HISTORY.clear()
            bpm_display = 0
            bpm_smooth_display = 0
            spo2_display = 0
            

            last_beat_ms = 0
            last_good_bpm = 0
            last_valid_bpm_ms = 0
            last_calc_ms = time.ticks_ms()

            sample_counter = 0
            last_beat_sample = None
            hr.__init__()
            
            bpm_valid = False
            spo2_valid = False

        #Cálculo de BPM mediante detección de latidos de HeartRate
        if hr.check_for_beat(ir):

            #El primer latido únicamente establece la referencia
            if last_beat_sample is None:
                last_beat_sample = sample_counter
                print("Primer latido detectado por HeartRate")
        
            else: 
                samples_between_beats = sample_counter - last_beat_sample
                last_beat_sample = sample_counter

                if samples_between_beats > 0:
                    bpm_calc_hr = (
                        60 * EFFECTIVE_SAMPLE_RATE
                        / samples_between_beats
                    )

                    print(
                        "HeartRate: muestras entre latidos =",
                        samples_between_beats,
                        "| BPM candidato =",
                        bpm_calc_hr
                    )

                    if BPM_MIN <= bpm_calc_hr <= BPM_MAX:

                        #Fase inicial: reunir varios latidos antes de fijar el BPM
                        if len(BPM_RAW_HISTORY) < BPM_BOOTSTRAP_SAMPLES:
                            BPM_RAW_HISTORY.append(bpm_calc_hr)

                            print(
                                "BPM inicial candidato =",
                                bpm_calc_hr,
                                "| muestras =",
                                len(BPM_RAW_HISTORY)
                            )

                            #Mostrar ya el primer BPM fisiológicamente válido para evitar que aparezca --- continuamente
                            if len(BPM_RAW_HISTORY) >= BPM_BOOTSTRAP_SAMPLES:
                                bpm = median(BPM_RAW_HISTORY)
                                bpm_valid = True
                                last_good_bpm = bpm
                                last_valid_bpm_ms = time.ticks_ms()
                            else:
                                bpm_valid = False

                            #Comprobar coherencia al completar el inicio
                            if len(BPM_RAW_HISTORY) == BPM_BOOTSTRAP_SAMPLES:
                                bpm_central = median(BPM_RAW_HISTORY)

                                if (max(BPM_RAW_HISTORY) - min(BPM_RAW_HISTORY) > BPM_BOOTSTRAP_RANGE):
                                    valor_peor = max(
                                        BPM_RAW_HISTORY,
                                        key=lambda valor: abs(valor - bpm_central)
                                    )

                                    BPM_RAW_HISTORY.remove(valor_peor)
                                    bpm = median(BPM_RAW_HISTORY)
                                    last_good_bpm = bpm

                                    print(
                                        "BPM inicial anómalo eliminado =",
                                        valor_peor,
                                        "| BPM mantenido =",
                                        bpm
                                    )
                            
                                else:
                                    
                                    print(
                                        "BPM inicial estabilizado =",
                                        bpm
                                    )
                        #Fase estable: ya se reunieron las muestras iniciales
                        else:
                            bpm_referencia = median(BPM_RAW_HISTORY)

                            if abs(bpm_calc_hr - bpm_referencia) <= MAX_BPM_JUMP:
                                BPM_RAW_HISTORY.append(bpm_calc_hr)
                                BPM_PENDING_HISTORY.clear()

                                if len(BPM_RAW_HISTORY) > MED_WIN:
                                    BPM_RAW_HISTORY.pop(0)

                                bpm = median(BPM_RAW_HISTORY)
                                bpm_valid = True
                                last_good_bpm = bpm
                                last_valid_bpm_ms = time.ticks_ms()

                                print(
                                    "BPM por HeartRate filtrado =",
                                    bpm
                                )

                            else:
                                # El candidato está lejos de la referencia actual.
                                # Comprobar si varios candidatos consecutivos confirman que el BPM real ha cambiado de nivel
                                BPM_PENDING_HISTORY.append(bpm_calc_hr)

                                if len(BPM_PENDING_HISTORY) > BPM_LOW_REBASE_SAMPLES:
                                    BPM_PENDING_HISTORY.pop(0)

                                # Si la nueva referencia es claramente más baja que la actual, exigir 5 candidatos coherentes

                                if bpm_calc_hr < bpm_referencia - 15:
                                    required_samples = BPM_LOW_REBASE_SAMPLES
                                else:
                                    required_samples = BPM_REBASE_SAMPLES

                                if len(BPM_PENDING_HISTORY) >= required_samples:

                                    recent = BPM_PENDING_HISTORY[-required_samples:]

                                    # Los candidatos tienen que ser coherentes entre sí

                                    if max(recent) - min(recent) <= 8:

                                        bpm = median(recent)

                                        BPM_RAW_HISTORY.clear()
                                        BPM_RAW_HISTORY.extend(recent)

                                        BPM_STABLE_HISTORY.clear()
                                        BPM_STABLE_HISTORY.append(bpm)

                                        bpm_display = bpm

                                        BPM_PENDING_HISTORY.clear()

                                        bpm_valid = True
                                        last_good_bpm = bpm
                                        last_valid_bpm_ms = time.ticks_ms()

                                        print("BPM reajustado por nueva referencia =", bpm)

                                    else:
                                        bpm_valid = bpm != 0

                                        print("BPM salto no confirmado =", bpm_calc_hr, "| se mantiene =", bpm)

                                else:
                                    bpm_valid = bpm != 0
    
                    else:
                        #Una detección fuera de rango no elimina el BPM anterior
                        bpm_valid = bpm != 0

                        print(
                            "BPM HeartRate fuera de rango =",
                            bpm_calc_hr,
                            "| se mantiene =",
                            bpm
                        )

        if ir < min_ir:
            min_ir = ir

        strength = ir - min_ir
        if strength > AMP_MIN:
            spo2_ir_buf.append(ir)
            spo2_red_buf.append(red)
            if len(spo2_ir_buf) > SPO2_BUF_SIZE:
                spo2_ir_buf.pop(0)
                spo2_red_buf.pop(0) #mantiene el tamaño fijo eliminando el valor más antiguo
            if (
                len(spo2_ir_buf) == SPO2_BUF_SIZE
                and time.ticks_diff(time.ticks_ms(), last_calc_ms) >= CALC_INTERVAL_MS
            ):
                last_calc_ms = time.ticks_ms()
                spo2_calc, sv, bpm_calc, bv = ox.calculate_spo2_and_heart_rate(
                    spo2_ir_buf, spo2_red_buf
                )
                print("oxygen BPM =", bpm_calc, "valid =", bv)
                #validación fisiológica previa
                #if bv and (BPM_MIN <= bpm_calc <= BPM_MAX):

                    #Fase inicial: reunir varias lecturas antes de fijar el BPM
                    #if bpm == 0:
                        #BPM_RAW_HISTORY.append(bpm_calc)

                        #if len(BPM_RAW_HISTORY) > BPM_BOOTSTRAP_SAMPLES:
                            #BPM_RAW_HISTORY.pop(0)

                        #print("BPM inicial candidato =", bpm_calc,
                            #"| muestras =", BPM_RAW_HISTORY)

                        #if len(BPM_RAW_HISTORY) >= BPM_BOOTSTRAP_SAMPLES:
                            #bpm_minimo = min(BPM_RAW_HISTORY)
                            #bpm_maximo = max(BPM_RAW_HISTORY)

                            #Solo se acepta si las lecturas iniciales son suficientemente coherentes
                            #if bpm_maximo - bpm_minimo <= BPM_BOOTSTRAP_RANGE:
                                #bpm = median(BPM_RAW_HISTORY)
                                #bpm_valid = True
                                #last_valid_bpm_ms = time.ticks_ms()

                                #print("BPM inicial estabilizado =", bpm)
                            #else:
                                #Las lecturas son inestables: descartar la más alejada
                                #bpm_central = median(BPM_RAW_HISTORY)

                                #valor_peor = max(
                                    #BPM_RAW_HISTORY,
                                    #key=lambda valor: abs(valor - bpm_central)
                                #)

                                #BPM_RAW_HISTORY.remove(valor_peor)
                                #bpm_valid = False

                                #print("BPM inicial inestable. Eliminado =", valor_peor)

                    #Fase estable: ya existe un BPM aceptado
                    #else:
                        #bpm_actual = median(BPM_RAW_HISTORY)

                        #if abs(bpm_calc - bpm_actual) <= MAX_BPM_JUMP:
                            #BPM_RAW_HISTORY.append(bpm_calc)

                            #if len(BPM_RAW_HISTORY) > MED_WIN:
                                #BPM_RAW_HISTORY.pop(0)

                            #bpm = median(BPM_RAW_HISTORY)
                            #bpm_valid = True
                            #last_valid_bpm_ms = time.ticks_ms()

                            #print("BPM filtrado =", bpm)

                        #else:
                            #No se sustituye el BPM estable por una lectura anómala
                            #bpm_valid = True

                            #print(
                                #"BPM descartado por salto =", bpm_calc,
                                #"| se mantiene =", bpm
                            #)   

                #else:
                    #Mientras el dedo continúe colocado, conservar el último BPM estable
                    #if bpm != 0:
                        #bpm_valid = True
                        #print("BPM no válido =", bpm_calc, "| se mantiene =", bpm)
                    #else:
                        #bpm_valid = False
                        #print("Todavía no existe un BPM estable")

                pass
                if sv and (SPO2_MIN <= spo2_calc <= SPO2_MAX):
                    # Fase inicial: reunir varias lecturas antes de fijar la SpO2
                    if spo2 == 0:

                        SPO2_HISTORY.append(spo2_calc)

                        # Mantener solo las muestras iniciales necesarias
                        if len(SPO2_HISTORY) > SPO2_BOOTSTRAP_SAMPLES:
                            SPO2_HISTORY.pop(0)

                        print("SpO2 inicial candidata =", spo2_calc, "| muestras =", SPO2_HISTORY)

                        # No mostrar todavía hasta tener varias lecturas
                        if len(SPO2_HISTORY) >= SPO2_BOOTSTRAP_SAMPLES:
                            spo2 = median(SPO2_HISTORY)
                            spo2_valid = True

                            print("SpO2 inicial estabilizada =", spo2)
                        else:
                            spo2_valid = False
                    # Fase estable: ya existe una SpO2 aceptada
                    else:
                        # Aceptar solo cambios pequeños respecto al valor estable
                        if abs(spo2_calc - spo2) <= MAX_SPO2_JUMP:

                            spo2 = push_and_mean(spo2_calc, SPO2_HISTORY, 10)

                            spo2_valid = True

                            SPO2_PENDING_HISTORY.clear()

                            print("SpO2 filtrada =", spo2)

                        else:
                            # El valor está lejos del actual: comprobar si se trata de un nuevo nivel estable y no de un artefacto aislado
                            SPO2_PENDING_HISTORY.append(spo2_calc)

                            if len(SPO2_PENDING_HISTORY) > 3:
                                SPO2_PENDING_HISTORY.pop(0)

                            if len(SPO2_PENDING_HISTORY) == 3:
                                if max(SPO2_PENDING_HISTORY) - min(SPO2_PENDING_HISTORY) <= 2:
                                    spo2 = median(SPO2_PENDING_HISTORY)

                                    SPO2_HISTORY.clear()
                                    SPO2_HISTORY.append(spo2)
                                    SPO2_PENDING_HISTORY.clear()

                                    print("SpO2 reajustada =", spo2)
                                else:
                                    print("SpO2 salto no confirmado =", spo2_calc, "| se mantiene =", spo2)

                            spo2_valid = True
                else:
                    # Si hay dedo y ya existe una SpO2 estable, conservar el último valor ante un fallo puntual
                    if finger_present and spo2 != 0:
                        spo2_valid = True

                        print("SpO2 no válida =", spo2_calc, "| se mantiene =", spo2)
                    else:
                        spo2_valid = False

                        print("SpO2 descartada =", spo2_calc)

                #warm-up inicial
                if time.ticks_diff(time.ticks_ms(), finger_since_ms) < WARMUP_MS:
                    spo2_valid = False
                    #Durante el calentamiento solo se oculta el BPM si todavía no se ha obtenido uno estable
                    if bpm == 0:
                        bpm_valid = False
        else:
            #Una muestra aislada con poca amplitud no elimina inmediatamente el último BPM válido
            bpm_valid = bpm != 0
            spo2_valid = spo2 != 0
    else:
        if finger_present:
            log("Dedo retirado. Coloque su dedo…")
            if display and display.is_connected():
                display.display_finger_message()
            #Avisar a la interfaz web de que se ha retirado el dedo
            if ble.is_connected():
                try:
                    ble.send_raw({
                        "fingerDetected": False
                    })
                except Exception as e:
                    log("[BLE] Error enviando estado de dedo retirado:", e)
        finger_present = False
        spo2_valid = bpm_valid = False
        temp_baseline = None
        temp_filtered = None

    return spo2_valid, bpm_valid

def refresh_temperature():
    global temp, temp_baseline, temp_filtered
    try:
        raw = float(sensor.readTemperature())
        # Primera lectura de la sesión:
        # se usa como referencia ambiental/térmica del sensor
        if temp_baseline is None:
            temp_baseline = raw
            temp_filtered = TEMP_TARGET
            temp = TEMP_TARGET
            return
        # Cambio respecto a la temperatura inicial del sensor
        delta = raw - temp_baseline
        # Estimación de temperatura corporal
        estimated = TEMP_TARGET + (delta * TEMP_GAIN)
        # Suavizado
        temp_filtered = ((1 - ALPHA_TEMP) * temp_filtered + ALPHA_TEMP * estimated)
        temp = temp_filtered
    except Exception as e:
        log("[TEMP] Error:", e)

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
        if bpm_valid and bpm > 0:
            bpm_stable = stabilize_bpm_output(bpm)
            # Solo aceptar para visualización valores dentro del rango normal establecido para la demo
            if BPM_DISPLAY_MIN <= bpm_stable <= BPM_DISPLAY_MAX:

                bpm_display = smooth_bpm_display(bpm_stable)

            else:
                # Si ya existe un BPM válido previo, conservarlo
                # No mostrar un valor anómalo aislado
                if bpm_display > 0:
                    bpm_display = bpm_display
        if spo2_valid and spo2 > 0:
            spo2_display = stabilize_spo2_display(spo2)
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
                    if time.ticks_diff(now, last_screen_update_ms) > SCREEN_UPDATE_MS:
                        #Mostrar valores cuando ya exista al menos una medición
                        if finger_present and spo2 != 0 and bpm_display != 0:
                            if screen_mode == 0:
                                display.display_values(
                                    int(round(spo2_display)), int(bpm_display), temp
                                )
                                screen_mode = 1
                            #Antes de obtener la primera medición
                            else:
                                display.display_risk(last_risk_label == 1)
                                screen_mode = 0
                        else:
                            display.display_finger_message()

                        last_screen_update_ms = now
                except Exception as e:
                    print("OLED error:", e)

        #usar promedios al enviar
        if sv and bv and bpm_display > 0 and time.ticks_diff(now, last_ble_send_ms) > BLE_SEND_MS:
            spo2_use = spo2_display
            bpm_use  = bpm_display

            s_spo2 = int(round(clamp(spo2_use, SPO2_MIN, SPO2_MAX)))
            s_bpm = int(round(clamp(bpm_use, BPM_MIN, BPM_MAX)))
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
            
            last_risk_label = final_label
            send_ble(s_spo2, s_bpm, s_temp, final_label, final_y)
            last_ble_keepalive_ms = now
            last_ble_send_ms = now

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