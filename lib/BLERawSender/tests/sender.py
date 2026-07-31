from BLERawSender import BLERawSender
import utime as time

ble = BLERawSender(device_name="ESP32-SaudeRemota", auto_wait_ms=0)
print("Nombre del dispositivo ESP32-SaudeRemota. Conéctate desde el PC (BLE).")

# (opcional) bloquear hasta que se conecte el ordenador
ble.wait_for_central(timeout_ms=60000)  # 60 s

i = 0 # Contador para variar los datos simulados
while True:
    if ble.is_connected():
        # Simulación de datos
        ble.send_measurement(temperature=36.8, bmp=72 + (i % 5), spo2=98.2, modelPreccision=0.93, riskScore=0.12) # Calcula el resto de dividir i entre 5
        i += 1
    time.sleep_ms(1000) # Evita que el programa compruebe la conexión miles de veces por segundo y consuma innecesariamente recursos
