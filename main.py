# ========================= AÑADIDOS (BLE + IA) =========================
# Ejecuta tareas BLE/IA en segundo plano usando Timer + micropython.schedule

import sys
import utime as time
from machine import Pin, Timer
import micropython

# --- BLE (NUS) ---
from lib.BLERawSender import BLERawSender  

# --- Modelo IA ---
from lib.predictionModel.modeloIA.pesos_modelo import predict  # -> (label, y)

# -------- Config añadida --------
DEVICE_NAME      = "ESP32-SaudeRemota"
BLE_KEEPALIVE_MS = 1000
PRINT_SERIAL     = True

# -------- Estado añadido --------
stop_flag = False
_last_ble_send_ms = time.ticks_ms()
_last_values = None  # (spo2,bpm,temp,label,y)

def _log(*a):
    if PRINT_SERIAL:
        try: print(*a)
        except: pass

def _clamp(v, lo, hi):
    try:
        if v < lo: return lo
        if v > hi: return hi
    except Exception:
        return lo
    return v

# Botón de parada (IO0/BOOT)
def _button_handler(pin):
    global stop_flag
    stop_flag = True
try:
    _button = Pin(0, Pin.IN, Pin.PULL_UP)
    _button.irq(trigger=Pin.IRQ_FALLING, handler=_button_handler)
except Exception:
    pass

# BLE init
try:
    ble = BLERawSender(device_name=DEVICE_NAME, auto_wait_ms=0)
    _log("BLE anunciando como", DEVICE_NAME)
except Exception as _e:
    ble = None
    _log("BLE ERROR al iniciar:", _e)

def _send_ble(spo2_i, bpm_i, temp_f, label_i, y_i):
    if not ble:
        return
    if ble.is_connected():
        try:
            ble.send_measurement(
                temperature=float(temp_f),
                bmp=int(bpm_i),
                spo2=int(spo2_i),
                riskScore=float(y_i),
                modelPreccision=float(y_i)  # compat
            )
            _log("[BLE] TX ->",
                 f"spo2={int(spo2_i)} bpm={int(bpm_i)} temp={float(temp_f):.2f} "
                 f"label={'Riesgo' if int(label_i)==1 else 'No riesgo'} y={float(y_i):.3f}")
        except Exception as e:
            _log("[BLE] ERROR notify:", e)

def _background_tasks():
    """Se ejecuta en contexto normal (no IRQ) gracias a micropython.schedule."""
    global _last_ble_send_ms, _last_values, stop_flag

    # Parada por botón sin tocar tu bucle
    if stop_flag:
        _log("Parada solicitada por botón.")
        try:
            display.clear()
            try: display.display_text("Programa detenido")
            except: pass
        except: pass
        sys.exit()

    now = time.ticks_ms()

    # Validez de medidas usando variables de TU main
    try:
        sv = (finger_present and (len(spo2_ir_buf) == SPO2_BUF_SIZE) and (spo2 > 0))
    except Exception:
        sv = False
    try:
        bv = (finger_present and (stable_count > 0) and (40 <= bpm <= 220))
    except Exception:
        bv = False

    if sv and bv:
        try: s_spo2 = int(_clamp(spo2, 0, 100))
        except: s_spo2 = 0
        try: s_bpm  = int(_clamp(bpm, 30, 220))
        except: s_bpm  = 0
        try: s_temp = float(_clamp(temperature, 25.0, 45.0))
        except: s_temp = 0.0

        try:
            label_i, y_i = predict([s_spo2, s_bpm, s_temp])  # -> (0/1, y)
        except Exception as e:
            _log("IA ERROR:", e)
            label_i, y_i = 0, 0.0

        cur = (s_spo2, s_bpm, s_temp, int(label_i), float(y_i))
        if (_last_values != cur) or (time.ticks_diff(now, _last_ble_send_ms) > 300):
            _send_ble(s_spo2, s_bpm, s_temp, label_i, y_i)
            _last_values = cur
            _last_ble_send_ms = now
    else:
        # keep-alive cada 1 s
        if time.ticks_diff(now, _last_ble_send_ms) > BLE_KEEPALIVE_MS:
            _send_ble(0, 0, 0.0, 0, 0.0)
            _last_ble_send_ms = now

# ---------- Temporizador periódico para disparar _background_tasks ----------
_bg_pending = False
def _timer_cb(_t):
    # Lanza _background_tasks en el hilo principal (no IRQ)
    global _bg_pending
    if _bg_pending:
        return
    _bg_pending = True
    try:
        micropython.schedule(_run_bg, 0)
    except:
        _bg_pending = False

def _run_bg(_):
    global _bg_pending
    _bg_pending = False
    try:
        _background_tasks()
    except Exception as e:
        _log("BG ERROR:", e)

# Algunos firmwares no soportan Timer(-1). Probamos con 1 y, si falla, con 0.
try:
    _timer = Timer(1)
except:
    _timer = Timer(0)

# mode puede no tener la constante; hacemos fallback a 2 (PERIODIC)
try:
    _timer.init(period=100, mode=Timer.PERIODIC, callback=_timer_cb)
except:
    _timer.init(period=100, mode=2, callback=_timer_cb)

# ======================= FIN AÑADIDOS (BLE + IA) =====================

from lib.max30102 import MAX30105
from lib.max30102.heartrate import HeartRate
from lib.max30102.oxygen import OxygenSaturation
from lib.ssd1306.ssd1306 import SSD1306

# Inicializa I2C
i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=400000)

# Inicializa el sensor MAX30102
sensor = MAX30105(i2c)
if not sensor.begin():
    print("ERROR: MAX30105 no detectado.")
    while True:
        time.sleep(1)

# Inicializa la pantalla OLED
display = SSD1306(i2c=i2c)

# Configuración optimizada para mayor velocidad y precisión
sensor.setup(
    powerLevel    = 0x7F,   # Potencia media (balance entre consumo y señal)
    sampleAverage = 1,      # Sin promediado para respuesta más rápida
    ledMode       = 2,      # Solo IR (mejor para detección cardíaca)
    sampleRate    = 400,    # Mayor tasa de muestreo
    pulseWidth    = 411,    # Mayor ancho de pulso para más luz
    adcRange      = 16384
)

# Inicializa el detector de latidos
hr = HeartRate()
ox = OxygenSaturation()

# Variables de estado
beat_times = []
last_beat_time = 0
bpm = 0
spo2 = 0
temperature = 0
stable_count = 0
finger_present = False
min_ir = 100000
last_update_time = 0
reset_threshold = 50000  # Umbral para detectar dedo

# Buffer para SpO2
spo2_ir_buf = []
spo2_red_buf = []
SPO2_BUF_SIZE = 50  #ventana de SpO2

# Mostrar mensaje inicial
display.display_finger_message()
print("Coloque su dedo en el sensor...")

while True:
    current_time = time.ticks_ms()
    ir = sensor.getIR()
    red = sensor.getRed()

    # Detección de presencia del dedo
    if ir > reset_threshold:
        if not finger_present:
            print("\nDedo detectado. Midiendo...")
            display.clear()
            finger_present = True
            min_ir = 100000
            hr = HeartRate()  # Reiniciar detector
            beat_times = []
            last_beat_time = 0
            stable_count = 0

        # Actualizar mínimo IR para calibración dinámica
        if ir < min_ir:
            min_ir = ir

        # Sólo procesar si la señal es suficientemente buena
        signal_strength = ir - min_ir
        if signal_strength > 15000:  # Umbral de amplitud
            # Acumula muestras para SpO2
            spo2_ir_buf.append(ir)
            spo2_red_buf.append(red)
            if len(spo2_ir_buf) > SPO2_BUF_SIZE:
                spo2_ir_buf.pop(0)
                spo2_red_buf.pop(0)

            if hr.check_for_beat(ir):
                now = time.ticks_ms()

                # Filtrar latidos demasiado cercanos
                if last_beat_time > 0 and (now - last_beat_time) < 300:
                    continue

                last_beat_time = now
                beat_times.append(now)

                # Mantener sólo los últimos 5 latidos
                if len(beat_times) > 5:
                    beat_times.pop(0)

                # Calcular BPM sólo con suficientes latidos
                if len(beat_times) >= 2:
                    elapsed = time.ticks_diff(beat_times[-1], beat_times[-2])
                    new_bpm = 60000 / elapsed

                    # Filtrar valores fuera de rango fisiológico
                    if 40 <= new_bpm <= 200:
                        # Suavizar la transición
                        if stable_count == 0:
                            bpm = new_bpm
                        else:
                            bpm = (bpm * 0.7) + (new_bpm * 0.3)  # Filtro EMA

                        stable_count += 1

                        # Actualizar pantalla sólo cada 500ms
                        if time.ticks_diff(current_time, last_update_time) > 500:
                            last_update_time = current_time
                            temperature = sensor.readTemperature()

                            # Mostrar datos en pantalla
                            display.display_parameter("Ritmo Cardiaco", bpm, "bpm", icon="heart")

                            # Mostrar en consola
                            print(f"LPM: {bpm:.1f}  Señal: {signal_strength}")
                            print(f"Temperatura: {temperature:.2f}°C")

                    # Calcular SpO2 si hay suficientes muestras
                    if len(spo2_ir_buf) == SPO2_BUF_SIZE:
                        spo2, spo2_valid, _, _ = ox.calculate_spo2_and_heart_rate(
                            spo2_ir_buf, spo2_red_buf
                        )
                        if spo2_valid:
                            # Mostrar SpO2 en pantalla alternadamente
                            if time.ticks_diff(current_time, last_update_time) > 1000:
                                display.display_parameter("Oxigeno", spo2, "%", icon="oxygen")
                                print(f"SpO2: {spo2}%")

    else:
        if finger_present:
            print("\nDedo retirado. Coloque su dedo en el sensor...")
            display.display_finger_message()
            finger_present = False
            stable_count = 0

        time.sleep_ms(100)
        continue
    if finger_present and (ir - min_ir) < 10000 and stable_count > 0:
        stable_count = max(0, stable_count - 1)
        if stable_count == 0:
            print("Señal débil. Ajuste el dedo")
            display.display_weak_signal()

    time.sleep_ms(5)
# ======================= FIN =======================
