# main.py

import time
from machine import I2C, Pin
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
            
        # Solo procesar si la señal es suficientemente buena
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
                
                # Mantener solo los últimos 5 latidos
                if len(beat_times) > 5:
                    beat_times.pop(0)
                
                # Calcular BPM solo con suficientes latidos
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
                        
                        # Actualizar pantalla solo cada 500ms
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