# @file BLERawSender.py
# @brief Librería MicroPython para enviar lecturas vía BLE (UART/NUS) a un receptor.
#
# Cambios v1.0.4: divide advertising en ADV (flags+UUID) y SCAN RESPONSE (nombre),
#                 arreglando descubrimiento cuando el payload supera 31 bytes.
#
# @author   Alejandro Fernández Rodríguez
# @contact  github.com/afernandezLuc
# @version  1.0.4
# @date     2025-08-02
# @copyright Copyright (c) 2025
# @license  MIT — Consulte el archivo LICENSE para más información.
#
# @details
#   Implementa un periférico BLE con el servicio Nordic UART Service (NUS)
#   para transmitir mediciones (o diccionarios arbitrarios) como líneas JSON
#   terminadas en '\n'. Optimiza la publicidad separando ADV (flags+UUID)
#   y SCAN RESPONSE (nombre), mejorando la visibilidad cuando el nombre es largo.
#
# @par Requisitos
#   - MicroPython con módulo `ubluetooth` habilitado (ESP32 u otros con BLE).
#   - Stack BLE que soporte `gap_advertise(...)` con `resp_data` (si no, cae en modo compat).
#
# @par Limitaciones
#   - El tamaño efectivo de cada notificación ATT es MTU-3 bytes.
#   - El parámetro `preferred_mtu` es una preferencia: la MTU real depende del intercambio.
#
# @par Ejemplo rápido
# @code{.py}
# from BLERawSender import BLERawSender
#
# ble = BLERawSender(device_name="ESP32-BLERaw", auto_wait_ms=10000)
# if ble.is_connected():
#     ble.send_measurement(temperature=36.55, bmp=72.0, spo2=98.0,
#                          modelPreccision=0.93, riskScore=0.12)
# # o datos arbitrarios:
# ble.send_raw({"sensor":"tmp","value":25.1})
# @endcode
#
# ---------------------------------------------------------------------------

import ujson as json
import ubluetooth as bt
import utime as time

# --- Compat eventos BLE ---
_IRQ_CENTRAL_CONNECT    = getattr(bt, "_IRQ_CENTRAL_CONNECT", 1)
_IRQ_CENTRAL_DISCONNECT = getattr(bt, "_IRQ_CENTRAL_DISCONNECT", 2)
_IRQ_GATTS_WRITE        = getattr(bt, "_IRQ_GATTS_WRITE", 3)
_IRQ_MTU_EXCHANGED      = getattr(bt, "_IRQ_MTU_EXCHANGED", 21)

# --- UUIDs NUS ---
_UART_SERVICE_UUID = bt.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
_UART_RX_UUID      = bt.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E")  # central -> periférico (WRITE)
_UART_TX_UUID      = bt.UUID("6E400003-B5A3-F393-E0A9-E50E24DCCA9E")  # periférico -> central (NOTIFY)

# --- GATT flags ---
_FLAG_WRITE = bt.FLAG_WRITE
_FLAG_WRITE_NO_RESPONSE = bt.FLAG_WRITE_NO_RESPONSE
_FLAG_NOTIFY = bt.FLAG_NOTIFY


def _adv_payload(flags=True, services=None):
    r"""
    @brief Construye el payload de publicidad (ADV) con flags y lista de servicios.
    @param flags     Si `True`, incluye el campo de flags LE General Discoverable y BR/EDR not supported.
    @param services  Lista iterable de UUIDs (bt.UUID) a anunciar (16 o 128 bits).
    @return `bytearray` con el ADV listo para `gap_advertise`.
    @note Longitud máxima 31 bytes. No incluye el nombre.
    """
    payload = bytearray()

    def _append(adv_type, value):
        payload.extend((len(value) + 1, adv_type))
        payload.extend(value)

    if flags:
        _append(0x01, b"\x02\x04")  # LE General Discoverable + BR/EDR not supported
    if services:
        for uuid in services:
            b = bytes(uuid)
            if len(b) == 16:
                _append(0x07, b)  # Complete list of 128-bit UUIDs
            elif len(b) == 2:
                _append(0x03, b)  # Complete list of 16-bit UUIDs
    return payload


def _scan_resp_payload(name):
    r"""
    @brief Construye el payload de SCAN RESPONSE con el nombre completo.
    @param name  Nombre del dispositivo (str).
    @return `bytearray` con el SCAN RESPONSE para `gap_advertise(..., resp_data=...)`.
    @note Longitud máxima 31 bytes; el nombre se recorta a 29 bytes si fuese necesario.
    """
    payload = bytearray()
    if name:
        n = name.encode()
        if len(n) > 29:  # 31 - (len + type) = 29
            n = n[:29]   # recorta para caber en un solo paquete
        payload.extend((len(n) + 1, 0x09))  # Complete Local Name
        payload.extend(n)
    return payload


class _BLEUART:
    r"""
    @brief Encapsula un periférico BLE con servicio NUS (UART sobre GATT).
    @details
        Registra un servicio con dos características:
          - TX (notify): periférico → central
          - RX (write / write-no-response): central → periférico
        Gestiona publicidad, conexión, MTU y envío fragmentado por notificaciones.
    """

    def __init__(self, name="ESP32-BLERaw", adv_interval_ms=100, preferred_mtu=247):
        r"""
        @brief Constructor del periférico NUS.
        @param name            Nombre GAP del dispositivo.
        @param adv_interval_ms Intervalo de advertising en milisegundos.
        @param preferred_mtu   MTU preferida (se intentará configurar).
        @post Inicia publicidad (ADV + SCAN RESPONSE si el port lo soporta).
        """
        self._ble = bt.BLE()
        self._ble.active(True)

        # Opcionales (algunos ports pueden no soportar estas opciones)
        try:
            self._ble.config(gap_name=name)
        except Exception:
            pass
        try:
            self._ble.config(mtu=preferred_mtu)
        except Exception:
            pass

        self._ble.irq(self._irq)

        # Servicio GATTS
        self._tx = (_UART_TX_UUID, _FLAG_NOTIFY)
        self._rx = (_UART_RX_UUID, _FLAG_WRITE | _FLAG_WRITE_NO_RESPONSE)
        self._service = (_UART_SERVICE_UUID, (self._tx, self._rx))
        ((self._tx_handle, self._rx_handle),) = self._ble.gatts_register_services((self._service,))

        self._conn_handle = None
        self._mtu = 23
        self._name = name
        self._adv_interval_us = adv_interval_ms * 1000

        # Prepara ADV + SCAN_RSP
        self._adv = bytes(_adv_payload(flags=True, services=[_UART_SERVICE_UUID])) 
        self._scan = bytes(_scan_resp_payload(self._name))
        self._safe_stop_advertising()
        self._start_advertising()

    def _irq(self, event, data):
        r"""
        @brief Manejador de interrupciones BLE (conexión, desconexión, MTU, escrituras).
        @param event Código de evento BLE.
        @param data  Tupla de datos asociada al evento.
        @note En esta implementación, las escrituras (RX) se ignoran.
        """
        if event == _IRQ_CENTRAL_CONNECT:
            conn_handle, addr_type, addr = data
            self._conn_handle = conn_handle
        elif event == _IRQ_CENTRAL_DISCONNECT:
            self._conn_handle = None
            self._start_advertising()
        elif event == _IRQ_MTU_EXCHANGED:
            try:
                conn_handle, mtu = data
                if self._conn_handle == conn_handle:
                    self._mtu = mtu
            except Exception:
                pass
        elif event == _IRQ_GATTS_WRITE:
            # RX no utilizado en esta librería.
            pass

    # ---- API pública ----

    def is_connected(self):
        r"""
        @brief Indica si hay una central conectada.
        @return `True` si hay conexión, `False` en caso contrario.
        """
        return self._conn_handle is not None

    def max_payload(self):
        r"""
        @brief Devuelve el tamaño máximo de datos por notificación ATT.
        @return Entero con el máximo de bytes (MTU - 3).
        @note El encabezado ATT para Notify consume 3 bytes.
        """
        return max(1, self._mtu - 3)  # ATT notify: MTU-3

    def wait_for_connection(self, timeout_ms=None):
        r"""
        @brief Bloquea hasta que se establece una conexión con una central BLE.
        @param timeout_ms Tiempo máximo de espera en milisegundos (o `None` para infinito).
        @return `True` si se conecta dentro del tiempo; `False` si vence el timeout.
        """
        start = time.ticks_ms()
        while not self.is_connected():
            time.sleep_ms(50)
            if timeout_ms is not None and time.ticks_diff(time.ticks_ms(), start) > timeout_ms:
                return False
        return True

    def send(self, data_bytes):
        r"""
        @brief Envía bytes por la característica TX (NOTIFY), fragmentando por MTU.
        @param data_bytes Búfer `bytes`/`bytearray` con los datos a enviar.
        @exception RuntimeError Si no hay una central conectada.
        @note Inserta un retardo corto entre fragmentos para evitar congestión.
        """
        if not self.is_connected():
            raise RuntimeError("No hay central BLE conectado.")
        chunk = self.max_payload()
        for i in range(0, len(data_bytes), chunk):
            self._ble.gatts_notify(self._conn_handle, self._tx_handle, data_bytes[i:i+chunk])
            time.sleep_ms(5)

    # ---- Advertising ----

    def _safe_stop_advertising(self):
        r"""
        @brief Intenta detener la publicidad de forma tolerante a puertos/estados.
        @details
            Algunos ports aceptan `gap_advertise(None)` y otros `gap_advertise(0)`.
            Esta rutina prueba ambos silenciosamente.
        """
        for arg in (None, 0):
            try:
                self._ble.gap_advertise(arg)
            except Exception:
                pass
        time.sleep_ms(20)

    def _start_advertising(self):
        r"""
        @brief Inicia la publicidad, usando SCAN RESPONSE si el port lo soporta.
        @exception OSError Re-lanza errores distintos de "advertising ya activo".
        @note Si `resp_data` no es soportado, se anuncia solo ADV (el nombre puede no mostrarse).
        """
        self._safe_stop_advertising()
        time.sleep_ms(10)
        try:
            # En MP recientes: gap_advertise(interval_us, adv_data, *, connectable=True, resp_data=None)
            self._ble.gap_advertise(self._adv_interval_us, self._adv, connectable=True, resp_data=self._scan)
        except TypeError:
            # Fallback si tu port no soporta resp_data: anuncia solo ADV (nombre puede no verse)
            self._ble.gap_advertise(self._adv_interval_us, self._adv)
        except OSError as e:
            if getattr(e, "args", [None])[0] == -18:
                print("BLE: advertising ya activo; continúo.")
            else:
                raise


class BLERawSender:
    r"""
    @brief Envío de mediciones/diccionarios como líneas JSON vía UART BLE (NUS).
    @details
        Crea un periférico BLE NUS y ofrece utilidades de alto nivel para:
          - Esperar conexión con una central (ordenador/teléfono/puente BLE).
          - Enviar una medición típica (temp, bpm, SpO2, etc.) formateada.
          - Enviar cualquier estructura (dict/list/valor) con sello temporal.
        Cada envío se serializa como una línea JSON terminada en '\n':
        `{"ts": <timestamp_ms>, "data": <payload>}\n`
    """

    def __init__(self, device_name="ESP32-BLERaw", auto_wait_ms=0):
        r"""
        @brief Constructor de la interfaz de envío en bruto.
        @param device_name Nombre GAP del periférico.
        @param auto_wait_ms Tiempo de espera inicial (ms) a que se conecte una central; 0 para no esperar.
        @post Inicia publicidad inmediatamente. Si `auto_wait_ms>0`, espera conexión ese tiempo.
        @note Si no se conecta nadie en `auto_wait_ms`, continúa anunciando sin error.
        """
        self._uart = _BLEUART(name=device_name)
        if auto_wait_ms and not self._uart.wait_for_connection(timeout_ms=auto_wait_ms):
            print("⚠ No se conectó ningún central en el timeout; sigo anunciando.")

    def is_connected(self):
        r"""
        @brief Indica si hay una central conectada al periférico.
        @return `True` si hay conexión, `False` en caso contrario.
        """
        return self._uart.is_connected()

    def wait_for_central(self, timeout_ms=None):
        r"""
        @brief Espera (bloqueante) a que se conecte una central.
        @param timeout_ms Tiempo máximo de espera en milisegundos; `None` para infinito.
        @return `True` si se conectó; `False` si venció el timeout.
        """
        return self._uart.wait_for_connection(timeout_ms=timeout_ms)

    def send_measurement(self, temperature, bmp, spo2, modelPreccision=0.0, riskScore=0.0, timestamp_ms=None):
        r"""
        @brief Envía una medición típica como JSON con campos normalizados.
        @param temperature     Temperatura corporal en °C (float).
        @param bmp             Frecuencia cardíaca (BPM) (float).
        @param spo2            Saturación de oxígeno en sangre (%) (float).
        @param modelPreccision Precisión/fiabilidad del modelo (0..1) (float).
        @param riskScore       Puntuación de riesgo (0..1) (float).
        @param timestamp_ms    Marca temporal en milisegundos; si `None`, se genera automáticamente.
        @exception RuntimeError Si no hay una central BLE conectada.
        @post Envía una línea JSON terminada en '\n' vía característica TX (notify).
        """
        payload = {
            "temperature": round(float(temperature), 2),
            "bmp": round(float(bmp), 2),
            "spo2": round(float(spo2), 2),
            "modelPreccision": round(float(modelPreccision), 2),
            "riskScore": round(float(riskScore), 2),
        }
        self.send_raw(payload, timestamp_ms)

    def send_raw(self, data, timestamp_ms=None):
        r"""
        @brief Envía un payload arbitrario (por ejemplo, dict) con sello temporal.
        @param data          Datos serializables a JSON (dict/list/valor).
        @param timestamp_ms  Marca temporal en milisegundos; si `None`, se obtiene de `time`.
        @exception RuntimeError Si no hay una central BLE conectada.
        @exception ValueError  Si `data` no es serializable a JSON.
        @details
            Serializa el objeto como una línea:
            `{"ts": <timestamp_ms>, "data": <data>}\n`
            y lo envía fragmentado según MTU por notificaciones ATT.
        """
        if timestamp_ms is None:
            try:
                timestamp_ms = int(time.time() * 1000)
            except Exception:
                timestamp_ms = time.ticks_ms()
        if not self._uart.is_connected():
            raise RuntimeError("No hay central BLE conectado. Conéctate desde el ordenador antes de enviar.")
        line = json.dumps({"ts": timestamp_ms, "data": data}) + "\n"
        self._uart.send(line.encode("utf-8"))