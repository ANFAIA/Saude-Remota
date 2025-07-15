# Saúde Remota

## 🩺 Descripción general

Este proyecto implementa un sistema de **monitorización remota de salud** utilizando un microcontrolador **ESP32-WROOM-32** y un sensor óptico **Max30102**. Está desarrollado en **Python con MicroPython**, lo que permite una ejecución eficiente sobre el hardware embebido.

El sistema permite leer datos de:
- Frecuencia cardíaca (BPM)
- Saturación de oxígeno (SpO₂)
- Temperatura del sensor (opcional)

Y los muestra a través de una pantalla OLED I2C (SSD1306), si está conectada.

---

## 📁 Estructura del proyecto

```
.
├── lib/
│   ├── max30102/
│   │   ├── __init__.py         # Inicialización del paquete del sensor
│   │   ├── heartrate.py        # Cálculo de BPM a partir de las muestras del sensor
│   │   ├── max30102.py         # Controlador del sensor MAX30102
│   │   └── oxygen.py           # Estimación de SpO₂ (saturación de oxígeno)
│   └── ssd1306/
│       ├── __init__.py         # Inicialización del paquete OLED
│       └── ssd1306.py          # Controlador de la pantalla OLED (basado en MicroPython)
├── main.py                     # Script principal de ejecución en el ESP32
├── upload.sh                   # Script Bash para subir automáticamente los archivos al ESP32
├── README.md                   # Este archivo
```

---

## 🧾 Requisitos

### Hardware
- Microcontrolador **ESP32-WROOM-32**
- Sensor **Max30102** (conexión I2C)
- Pantalla **OLED SSD1306** (opcional)

### Software en PC
- Python ≥ 3.9
- Herramientas de comunicación:
  - [`adafruit-ampy`](https://github.com/adafruit/ampy)

---

## ⚙️ Preparación del entorno de desarrollo

1. Crea un entorno virtual:
   ```bash
   python3.9 -m venv venv
   source venv/bin/activate
   ```

2. Instala las dependencias:
   ```bash
   pip install adafruit-ampy
   ```

---

## 🚀 Instalación en el ESP32

1. Asegúrate de tener MicroPython flasheado en el ESP32.

2. Conecta el ESP32 por USB y localiza el puerto serial:
   ```bash
   ls /dev/tty.usb*
   ```

3. Ejecuta el script de carga:
   ```bash
   ./upload.sh /dev/tty.usbserial-0001
   ```

Este script:
- Verifica si `ampy` está instalado.
- Elimina los archivos del ESP32 (excepto `boot.py` si existe).
- Sube todos los ficheros `.py` y crea la estructura de carpetas.
- Lista el contenido final cargado.

---

## 🩺 Uso

1. Conecta el sensor Max30102 a los pines I2C del ESP32 (por defecto SDA: GPIO21, SCL: GPIO22).
2. (Opcional) Conecta la pantalla OLED SSD1306 por I2C.
3. Abre un monitor serial:
   ```bash
   screen /dev/tty.usbserial-0001 115200
   ```
4. Ejecuta el programa principal:
   ```bash
   ampy --port /dev/tty.usbserial-0001 run main.py
   ```

5. Verás la lectura en tiempo real de:
   ```
   🌡️ Temperatura: 36.25 °C
   ❤️ BPM: 75
   🩸 SpO₂: 98%
   ```

---

## 📌 Notas

- Asegúrate de tener bien conectados los cables I2C y alimentación.
- El sensor puede tardar unos segundos en estabilizarse.
- Si no aparecen datos, revisa la orientación del dedo o el nivel de señal IR.
