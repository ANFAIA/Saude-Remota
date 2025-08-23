## @file main.py
#  @brief Programa principal para medir frecuencia cardíaca, SpO2 y temperatura con un MAX30102.
#
#  Librería para medir la frecuencia cardíaca, saturación de oxígeno y temperatura, enviarlos a Firebase, 
#  mostrar en una pantalla OLED y permitir parada limpia del programa.
#  Se utiliza un modelo de IA para calcular la precisión de los resultados y un nivel de riesgo.
#
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

# -----------------------------------------------------------------
# Configuración
# -----------------------------------------------------------------
printSerial = True   # Cambia a False si no quieres salida por puerto serie
BUTTON_PIN = 0       # IO0 (BOOT)
SAMPLE_RATE = 400    # Hz

stop_flag = False
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

# Inicializa I2C, sensor y pantalla
i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=400000)
sensor = MAX30105(i2c)
display = SSD1306(i2c=i2c)
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

# Interrupción del botón
def _button_handler(pin):
    global stop_flag
    stop_flag = True

button = Pin(BUTTON_PIN, Pin.IN, Pin.PULL_UP)
button.irq(trigger=Pin.IRQ_FALLING, handler=_button_handler)

# -----------------------------------------------------------------
# Inicialización del sensor
# -----------------------------------------------------------------
if not sensor.begin():
    print("ERROR: MAX30105 no detectado.")
    sys.exit()

sensor.setup(
    powerLevel    = 0x7F,
    sampleAverage = 1,
    ledMode       = 2,
    sampleRate    = SAMPLE_RATE,
    pulseWidth    = 411,
    adcRange      = 16384
)

if display.is_connected():
    display.display_finger_message()
if printSerial:
    print("Sensor inicializado. Coloque su dedo en el sensor…")

# -----------------------------------------------------------------
# Bucle principal
# -----------------------------------------------------------------
try:
    while True:
        current_time = time.ticks_ms()
        ir = sensor.getIR()
        red = sensor.getRed()

        if ir > reset_threshold:
            if not finger_present:
                print("\nDedo detectado. Midiendo…")
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
                if len(spo2_ir_buf) > ox.BUFFER_SIZE:
                    spo2_ir_buf.pop(0); spo2_red_buf.pop(0)
                if len(spo2_ir_buf) == ox.BUFFER_SIZE:
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
                    entrada_modelo = [spo2, bpm, temperature]
                    label, prob = predict(entrada_modelo)

                    if printSerial:
                        print(f"Probabilidad de riesgo: {prob:.4f}")
                        print("Clasificación:", "Riesgo" if label == 1 else "No riesgo")

                    sender.send_measurement(
                        temperature=temperature, bmp=bpm, spo2=spo2,
                        modelPrecision=round(prob, 4), riskScore=label
                    )

        else:
            if finger_present:
                print("\nDedo retirado. Coloque su dedo en el sensor…")
                if display.is_connected(): display.display_finger_message()
                finger_present = False
                bpm_valid = False; spo2_valid = False
            time.sleep_ms(100)

        if stop_flag:
            print("\nParada solicitada por botón.")
            break

        time.sleep_ms(5)

except KeyboardInterrupt:
    print("\nParada solicitada por Ctrl-C.")

finally:
    if display.is_connected():
        display.clear()
        try: display.display_text("Programa detenido")
        except: pass
    sys.exit()
