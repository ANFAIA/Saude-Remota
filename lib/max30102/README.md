# MAX30105 MicroPython Driver

**Version 1.0.0 – 2 August 2025**

Pequeña librería (MicroPython) para controlar el sensor óptico **MAX30105 / MAX30102** y calcular **frecuencia cardiaca (HR)** y **saturación de oxígeno en sangre (SpO₂)** en placas basadas en micro-controladores.

> Implementa algoritmos basados en la _application note_ Maxim AN-6595 y en filtros FIR de paso bajo optimizados para entornos con recursos limitados.

---

## Tabla de contenidos
1. [Características](#características)
2. [Instalación](#instalación)
3. [Ejemplo rápido](#ejemplo-rápido)
4. [Referencia de la API](#referencia-de-la-api)
5. [Contribuir](#contribuir)
6. [Historial de versiones](#historial-de-versiones)
7. [Licencia](#licencia)

---

## Características

- **Driver I²C completo** para el MAX30105 / MAX30102.
- Lectura de FIFO y gestión de **interrupciones** internas.
- **Lectura de temperatura** integrada del chip.
- Algoritmo `HeartRate` para detección de latidos (BPM).
- Algoritmo `OxygenSaturation` para estimar SpO₂.
- Código **100 % MicroPython** — no requiere dependencias externas.
- Licencia MIT.

---

## Instalación

Copie los archivos `max30102.py`, `heartrate.py`, `oxygen.py` y `__init__.py` en su proyecto o instale el paquete (cuando esté publicado) con:

```bash
pip install max30102-micropython   # pendiente de publicación
```

> Asegúrese de habilitar el bus **I²C** en su placa (por ejemplo `machine.I2C(0)` en ESP32).

---

## Ejemplo rápido

```python
from machine import I2C, Pin
from max30102 import MAX30105, HeartRate, OxygenSaturation

# 1) Configuración del bus I²C
i2c = I2C(1, scl=Pin(22), sda=Pin(21), freq=400_000)

# 2) Inicializar el sensor
sensor = MAX30105(i2c)
sensor.setup()          # Configuración por defecto (modo SpO2 a 100 Hz)

# 3) Procesadores de señal
hr_proc = HeartRate()
oxi     = OxygenSaturation()

ir_buf  = []
red_buf = []

while True:
    red, ir, _ = sensor.read_fifo()

    bpm = hr_proc.process(ir)
    if bpm is not None:
        print(f"BPM: {bpm:0.1f}")

    ir_buf.append(ir)
    red_buf.append(red)

    if len(ir_buf) == 100:                       # 1 s a 100 Hz
        spo2, spo2_ok, hr, hr_ok = oxi.calculate_spo2_and_heart_rate(ir_buf, red_buf)
        if spo2_ok:
            print(f"SpO₂: {spo2:.1f} %")
        ir_buf.clear()
        red_buf.clear()
```

---

## Referencia de la API

| Clase | Descripción | Métodos clave |
|-------|-------------|---------------|
| `MAX30105` | Driver de bajo nivel para el sensor (configuración, lectura FIFO, temperatura, modos LED, etc.). | `setup`, `soft_reset`, `read_fifo`, `read_temperature`, `set_led_mode`, `set_sample_rate`, `enable_slot` |
| `HeartRate` | Estimación de frecuencia cardiaca en tiempo real usando filtrado FIR y umbral adaptativo. | `process`, `get_bpm` |
| `OxygenSaturation` | Estima SpO₂ a partir de la relación _AC/DC_ de las señales IR y RED, implementando Maxim AN-6595. | `calculate_spo2_and_heart_rate` |

---

## Contribuir

1. **Fork** el repositorio y cree una rama.
2. Envíe un **Pull Request** con una descripción clara de sus cambios.
3. Asegúrese de que su código pase _flake8_ y añada pruebas si procede.

---

## Historial de versiones

- **1.0.0** — 2 ago 2025 — Versión inicial con soporte HR y SpO₂.

---

## Licencia

Distribuido bajo la [licencia MIT](LICENSE). © 2025 Alejandro Fernández Rodríguez
