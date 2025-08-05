## @file main.py
#  @brief Programa principal para medir frecuencia cardíaca, SpO2 y temperatura con un MAX30102.
#
#  Librería para medir la frecuencia cardíaca, saturación de oxígeno y temperatura, enviarlos a Firebase, 
#  mostrar en una pantalla OLED y permitir parada limpia del programa.
#  Se utiliza un modelo de IA para calcular la precisión de los resultados y un nivel de riesgo.
#
#  @author Alejandro Fernández Rodríguez
#  @contact github.com/afernandezLuc
#  @version 1.0.0
#  @date 2025-08-02
#  @copyright Copyright (c) 2025 Alejandro Fernández Rodríguez
#  @license MIT — Consulte el archivo LICENSE para más información.
#
#  ---------------------------------------------------------------------------

"""
Lectura de frecuencia cardiaca, SpO2 y temperatura usando un MAX30102
con salida en una pantalla OLED. Añadido un "kill‑switch" dual:
  1) Ctrl‑C desde el REPL (KeyboardInterrupt)
  2) Botón físico en el pin IO0 (o el que definas en BUTTON_PIN)

Ambos mecanismos provocan la salida limpia al prompt >>>
"""
import time
import sys
from machine import I2C, Pin
from lib.max30102 import MAX30105
from lib.max30102.heartrate import HeartRate
from lib.max30102.oxygen import OxygenSaturation
from lib.ssd1306.ssd1306 import SSD1306
from lib.firebase_data_send.FirebaseRawSender import FirebaseRawSender
from lib.predictionModel.modeloIA.pesos_modelo import predict

# -----------------------------------------------------------------------------
# --------------------------------- MAIN DATA ---------------------------------
# -----------------------------------------------------------------------------

# Exponer datos por puerto serie
printSerial = True  # Cambia a False si no quieres salida por puerto serie

# -----------------------------------------------------------------------------
# Configuración del "key interrupt" físico
# -----------------------------------------------------------------------------
BUTTON_PIN = 0            # IO0 (BOOT).
LED_POWER   = 0x7F        # Corriente normal de los LED de medición
LED_OFF     = 0x00        # LEDs apagados
PROX_LED    = 0x10        # Corriente del LED de proximidad (~0,8 mA)
PROX_THRESH = 0x20        # Umbral de proximidad (≈25 µA)
stop_flag = False         # Se pondrá a True cuando se pulse el botón

SAMPLE_RATE = 400   # Tasa de muestreo del sensor (400 Hz)

# Inicializa I2C
i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=400000)

#sensor MAX30102
sensor = MAX30105(i2c)

# Inicializa la pantalla OLED
display = SSD1306(i2c=i2c)

# Inicializa los algoritmos de ritmo cardiaco y saturación O2
hr = HeartRate()
ox = OxygenSaturation(sample_rate_hz=SAMPLE_RATE)

# Inicializa el sender de Firebase
# ----------------------- AÑADE AQUÍ TUS CREDENCIALES WIFI-----------------------   
config = {
    "ssid": "YOUR_WIFI_SSID",
    "password": "YOUR_WIFI_PASSWORD"
}

# ----------------------- AÑADE AQUÍ TUS CREDENCIALES DE FIREBASE-----------------------   
sender = FirebaseRawSender(
    email="rawdata@sauderemota.com",
    password="rawdata2025",
    api_key="AIzaSyCZPe0DeM15cQiU7tzpQ5qsI6XtUqXvJ7E",
    database_url="https://saude-remota-default-rtdb.europe-west1.firebasedatabase.app",
    wifi_config=config
)

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
spo2_valid = False
bpm_valid = False  

# Buffer para SpO2
spo2_ir_buf = []
spo2_red_buf = []
SPO2_BUF_SIZE = ox.BUFFER_SIZE  # ventana de SpO2


# -----------------------------------------------------------------------------
# ------------------------------ MAIN FUNCTIONS -------------------------------
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# Configuración del "key interrupt" físico
# -----------------------------------------------------------------------------
def _button_handler(pin):
    """Interrupción del botón: marca la bandera y vuelve rápidamente."""
    global stop_flag
    stop_flag = True

# -----------------------------------------------------------------------------
# Funciones de control de LED y proximidad
# -----------------------------------------------------------------------------

def leds_on():
    """Activa los LED de medición con la potencia definida en LED_POWER."""
    sensor.setPulseAmplitudeIR(LED_POWER)
    sensor.setPulseAmplitudeRed(LED_POWER)  # ledMode = 2 → IR + Rojo


def leds_off():
    """Apaga los LED de medición (corriente = 0)."""
    sensor.setPulseAmplitudeIR(LED_OFF)
    sensor.setPulseAmplitudeRed(LED_OFF)


def enable_proximity():
    """Habilita el detector de proximidad con LED Prox de baja corriente."""
    sensor.setPulseAmplitudeProximity(PROX_LED)
    sensor.setProximityThreshold(PROX_THRESH)
    sensor.enablePROXINT()


def disable_proximity():
    """Deshabilita el modo de proximidad para evitar falsas interrupciones."""
    sensor.disablePROXINT()
    sensor.setPulseAmplitudeProximity(0)

#not in use for future implementations
def optimized_bpm_calculation():
    if hr.check_for_beat(ir):
        now = time.ticks_ms()

        # Filtrar latidos demasiado cercanos
        if last_beat_time > 0 and (now - last_beat_time) < 300:
            return

        last_beat_time = now
        beat_times.append(now)

        # Mantener solo los últimos 5 latidos
        if len(beat_times) > 5:
            beat_times.pop(0)

        # Calcular BPM solo con suficientes latidos
        if len(beat_times) >= 2:
            elapsed = time.ticks_diff(beat_times[-1], beat_times[-2])
            new_bpm = 60000 / elapsed

            # Filtrar valores fuera de rango fisiológico
            if 40 <= new_bpm <= 200:
                bpm_valid = True
                # Suavizar transición (EMA)
                if stable_count == 0:
                    bpm = new_bpm
                else:
                    bpm = (bpm * 0.7) + (new_bpm * 0.3)

                stable_count += 1
# -----------------------------------------------------------------------------
# ---------------------------------- MAIN  ------------------------------------
# -----------------------------------------------------------------------------


# Pin en modo entrada con pull‑up interno y disparo por flanco de bajada
button = Pin(BUTTON_PIN, Pin.IN, Pin.PULL_UP)
button.irq(trigger=Pin.IRQ_FALLING, handler=_button_handler)
# -----------------------------------------------------------------------------
# Inicializa el sensor MAX30102
if not sensor.begin():
    if printSerial:
        print("ERROR: MAX30105 no detectado.")
    while True:
        if stop_flag:
            if printSerial:
                print("Parada solicitada por botón.")
            sys.exit()
        time.sleep(1)

# Configuración optimizada para mayor velocidad y precisión
sensor.setup(
    powerLevel    = LED_POWER,   # Potencia media (balance entre consumo y señal)
    sampleAverage = 1,      # Sin promedios (mejor para latencia)
    ledMode       = 2,      # Solo IR (mejor para detección cardíaca)
    sampleRate    = SAMPLE_RATE,     # Tasa de muestreo
    pulseWidth    = 411,    # Mayor ancho de pulso para más luz
    adcRange      = 16384
)

# Mostrar mensaje inicial
if display.is_connected():
    display.display_finger_message()
if printSerial:
    print("Sensor inicializado. Coloque su dedo en el sensor…")

# -----------------------------------------------------------------------------
# Bucle principal con salida limpia por Ctrl‑C o botón
# -----------------------------------------------------------------------------
try:
    while True:
        current_time = time.ticks_ms()
        ir = sensor.getIR()
        red = sensor.getRed()

        # ------------------------ Detección dedo ------------------------------
        if ir > reset_threshold:
            if not finger_present:
                if printSerial:
                    print("\nDedo detectado. Midiendo…")
                if display.is_connected():
                    display.clear()
                finger_present = True
                min_ir = 100000
                hr = HeartRate()  # Reiniciar detector
                beat_times = []
                last_beat_time = 0
                stable_count = 0

            # Calibración dinámica del mínimo IR
            if ir < min_ir:
                min_ir = ir

            # Procesar solo si la señal es suficientemente buena
            signal_strength = ir - min_ir
            if signal_strength > 15000:  # Umbral de amplitud
                # Acumula muestras para SpO2
                spo2_ir_buf.append(ir)
                spo2_red_buf.append(red)
                if len(spo2_ir_buf) > SPO2_BUF_SIZE:
                    spo2_ir_buf.pop(0)
                    spo2_red_buf.pop(0)
                # Calcular SpO2 y bpm si hay suficientes muestras
                if len(spo2_ir_buf) == SPO2_BUF_SIZE:
                    spo2, spo2_valid, bpm, bpm_valid = ox.calculate_spo2_and_heart_rate(
                        spo2_ir_buf, spo2_red_buf
                    )
                                    
            # Actualizar pantalla cada 500 ms
            if time.ticks_diff(current_time, last_update_time) > 500:
                last_update_time = current_time
                temperature = sensor.readTemperature()
                # Mostrar datos en pantalla        
                if display.is_connected():
                    if spo2_valid:
                        display.display_parameter("Oxigeno", spo2, "%", icon="oxygen")
                    else:
                        display.display_parameter("Ritmo Cardiaco", bpm, "bpm", icon="heart")

                # Mostrar en consola
                if printSerial and (bpm_valid or spo2_valid):
                    if bpm_valid:
                        print(f"LPM: {bpm:.1f}  Señal: {signal_strength}")
                    print(f"Temperatura: {temperature:.2f}°C")
                    if spo2_valid:
                        print(f"SpO2: {spo2}%")
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
                    if printSerial:
                        print("Enviando datos a Firebase...")
                    sender.send_measurement(temperature=temperature, bmp=bpm, spo2=spo2, modelPrecision = 0, riskScore = 0)
        # ---------------------- Dedo retirado -------------------------------
        else:
            if finger_present:
                if printSerial:
                    print("\nDedo retirado. Coloque su dedo en el sensor…")
                if display.is_connected():
                    display.display_finger_message()
                finger_present = False
                bpm_valid = False
                spo2_valid = False
                stable_count = 0

            time.sleep_ms(100)
            
        # Señal débil
        if finger_present and (ir - min_ir) < 10000 and stable_count > 0:
            stable_count = max(0, stable_count - 1)
            if stable_count == 0:
                if printSerial:
                    print("Señal débil. Ajuste el dedo")
                if display.is_connected():
                    display.display_weak_signal()

        # ------------------- Comprobación de parada -------------------------
        if stop_flag:
            if printSerial:
                print("\nParada solicitada por botón.")
            break

        time.sleep_ms(5)

except KeyboardInterrupt:
    # Captura Ctrl‑C enviado desde el REPL
    if printSerial:
        print("\nParada solicitada por Ctrl‑C.")

finally:
    # Limpieza de recursos y salida limpia al prompt >>>
    if display.is_connected():
        display.clear()
    try:
        if display.is_connected():
            display.display_text("Programa detenido")
    except AttributeError:
        pass  # Si la función no existe en tu SSD1306
    sys.exit()
