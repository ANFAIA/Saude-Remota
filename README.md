# Saúde Remota

## 🩺 Descripción general

Este proyecto implementa un sistema de **monitorización remota de salud** utilizando un microcontrolador **ESP32-WROOM-32** y un sensor óptico **MAX30102**. Está desarrollado en **Python con MicroPython**, lo que permite una ejecución eficiente sobre el hardware embebido.

El sistema permite leer datos de:
- Frecuencia cardíaca (BPM)
- Saturación de oxígeno (SpO₂)
- Temperatura del sensor (opcional)

Y los muestra a través de una pantalla OLED I2C (SSD1306), si está conectada.

---

## 📁 Estructura del proyecto

```
.
├── docs/
├── bleServer/  
│   └── web/
│       ├── colors.css              # Definición de paletas de colores utilizadas en la web 
│       ├── reset.css               # Eliminar estilos por defecto de los navegadores
│       ├── styles.css              # Estilo principal de la web
│       ├── utils.js                # Cliente WS + DOM + envío a Firebase RTDB 
│       ├── index.html              # Estructura del contenido de la web 
│       ├── server.py               # Implementar un servidor BLE para una web
│       ├── README.md               # Archivo con documentacion sobre el uso y funcionalidad
│       └── LICENSE                 # Archivo de licencia de la librería                    
├── lib/
│   └── max30102/
│       ├── __init__.py             # Inicialización del paquete del sensor MAX30102 
│       ├── heartrate.py            # Cálculo de BPM a partir de las muestras del sensor
│       ├── max30102.py             # Controlador del sensor MAX30102
│       ├── oxygen.py               # Estimación de SpO₂ (saturación de oxígeno)
│       ├── README.md               # Archivo con documentacion sobre el uso y funcionalidad 
│       └── LICENSE                 # Archivo de licencia de la librería
│   └── ssd1306/
│       ├── __init__.py             # Inicialización del paquete OLED
│       │── ssd1306.py              # Controlador de la pantalla OLED (basado en MicroPython)
│       └── LICENSE                 # Archivo de licencia de la librería
│   └── firebase_data_send/
│       ├── __init__.py             # Inicialización del paquete de envío de datos a Firebase
│       ├── FirebaseRawSender.py    # Clase con funciones para enviar los datos a Firebase
│       ├── README.md               # Archivo con documentacion sobre el uso y funcionalidad
│       └── LICENSE                 # Archivo de licencia de la librería
│   └── BLERawSender/
│       ├── __init__.py             # Inicialización del paquete de envío de datos por Bluetooth
│       ├── BLERawSender.py         # Clase con funciones para enviar los datos por Bluetooth
│       ├── README.md               # Archivo con documentacion sobre el uso y funcionalidad
│       └── LICENSE                 # Archivo de licencia de la librería
│   └── file_store/
│       ├── __init__.py             # Inicialización del paquete de almacenamiento
│       └── store.py                # Módulo para guardar datos del sensor MAX30102 en un archivo simulado
│   └── predictionModel/
│       ├── compiledModel           # Modelo de IA en formato .tflite
│       ├── dataset                 # Datasets utilizados para entrenar el modelo
│       ├── arquitectura.py         # Arquitectura del modelo de IA
│       ├── combinar_datasets.py    # Combinar los tres datasets reales utilizados para entrenar el modelo
│       ├── convertir_json.py       # Convertir los pesos y escalas del modelo a formato .json
│       ├── entrenar_modelo.py      # Entrenamiento del modelo de IA
│       ├── dataset_sintetico.py    # Creación de un dataset sintético con datos de riesgo tipo 1
│       ├── pesos_modelo.py         # Utilizar los pesos del modelo para determinar el riesgo
│       ├── pesos_y_escalas.py      # Captar los pesos y escalas del modelo
│       ├── procesar_eicu_demo.py   # Procesar el dataset eicu
│       ├── procesar_human.py       # Procesar el dataset de Kaggle
│       ├── escala.json             # Escala del modelo en formato .json
│       ├── pesos.json              # Pesos del modelo en formato .json
│       ├── pesos.npz               # Pesos del modelo en formato .npz
│       └── escala.npz              # Escala del modelo en formato .npz
├── main.py                         # Script principal de ejecución en el ESP32
├── upload.sh                       # Script Bash para subir automáticamente los archivos al ESP32
├── LICENSE                         # Archivo de licencia del proyecto
├── README.md                       # Este archivo
├── boot.py                         # Arranque automático del ESP32 con MicroPython
├── Doxyfile                        # Genera documentación automática a partir de los comentarios del código
└── requirements.txt                # Dependencias necesarias para ejecutar el proyecto en un entorno

```

---

## 🧾 Requisitos

### Hardware
- Microcontrolador **ESP32-WROOM-32**
- Sensor **MAX30102** (conexión I2C)
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
## 🛜 Configuracion de tu red wifi
En el archivo main.py añade las credenciales de tu red para conectarte a la red wifi disponible

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

## 🔧 Conexion con el sensor

```
ESP32                     MAX30102
┌───────────┐             ┌─────────┐
│ 3V3  ───────────────► VCC         │
│ GND  ───────────────► GND         │
│ GPIO21 (SDA) ───────► SDA         │
│ GPIO22 (SCL) ───────► SCL         │
└───────────┘             └─────────┘

```

## 🩺 Uso

1. Conecta el sensor MAX30102 a los pines I2C del ESP32 (por defecto SDA: GPIO21, SCL: GPIO22).
2. (Opcional) Conecta la pantalla OLED SSD1306 al mismo bus I2C.
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
   🌡️ Temperatura: 36.25 °C (por ejemplo)
   ❤️ BPM: 75
   🩸 SpO₂: 98%
   ```

---

## 📌 Notas

- Asegúrate de tener bien conectados los cables I2C y alimentación.
- El sensor puede tardar unos segundos en estabilizarse.
- Si no aparecen datos, revisa la orientación del dedo o el nivel de señal IR.
