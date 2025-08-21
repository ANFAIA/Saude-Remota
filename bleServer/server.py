
## @file server.py
#  @brief Servidor BLE → Web para Saúde Remota.
#  @details
#  Este módulo implementa un servidor que:
#   - Descubre y se conecta por **Bluetooth Low Energy (BLE)** a un ESP32 que expone
#     el servicio **Nordic UART Service (NUS)**.
#   - Recibe mediciones como líneas JSON por notificación BLE, las guarda en **CSV** y **JSONL**.
#   - Publica en tiempo real cada lectura hacia los navegadores conectados mediante **WebSocket**.
#   - Sirve la interfaz web (HTML/CSS/JS) desde el directorio `web/`.
#
#  Arquitectura (alto nivel):
#   - **Tarea BLE** (`ble_task`): scan → connect → subscribe → parse → log → broadcast.
#   - **Servidor HTTP/WS** (`aiohttp`): rutas estáticas y endpoint `/ws` para streaming en vivo.
#   - **Difusión** (`broadcast`): envío concurrente a todos los clientes WebSocket conectados.
#
#  Requisitos de ejecución:
#   - Python 3.11+
#   - Paquetes: `bleak`, `aiohttp` (ver `requirements.txt`)
#
#  @author Alejandro Fernández Rodríguez
#  @contact github.com/afernandezLuc
#  @version 1.0.0
#  @date 2025-08-21
#  @copyright Copyright (c) 2025
#  @license MIT — Consulte el archivo LICENSE para más información.
#  ---------------------------------------------------------------------------

import asyncio
import json
import csv
import argparse
from datetime import datetime
from pathlib import Path
from typing import Set

from aiohttp import web, WSMsgType
from bleak import BleakScanner, BleakClient

## @defgroup BLE_UUIDs UUIDs BLE (NUS)
## @{

## @var UART_SERVICE_UUID
## @brief UUID del servicio **Nordic UART Service (NUS)** anunciado por el ESP32.
UART_SERVICE_UUID = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"

## @var UART_TX_UUID
## @brief UUID de la característica TX (notificaciones del periférico hacia el host).
UART_TX_UUID      = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"
## @}

## @defgroup PATHS Rutas del servidor
## @{

## @var HERE
## @brief Directorio donde reside este archivo `server.py`.
HERE = Path(__file__).resolve().parent

## @var WEB_DIR
## @brief Directorio raíz con los archivos estáticos de la interfaz web.
WEB_DIR = HERE / "web"

## @var LOG_DIR
## @brief Directorio de logs (CSV/JSONL).
LOG_DIR = HERE / "logs"
LOG_DIR.mkdir(exist_ok=True)

## @var CSV_PATH
## @brief Ruta del fichero CSV con las mediciones acumuladas.
CSV_PATH = LOG_DIR / "raw_log.csv"

## @var JSONL_PATH
## @brief Ruta del fichero JSONL (una lectura JSON por línea).
JSONL_PATH = LOG_DIR / "raw_log.jsonl"
## @}

## @defgroup STATE Estado del servidor
## @{

## @var clients
## @brief Conjunto en memoria con las conexiones WebSocket activas.
clients: Set[web.WebSocketResponse] = set()
## @}

## @brief Asegura que el fichero CSV existe y contiene cabecera.
## @details Crea `CSV_PATH` si no existe y escribe la fila de cabecera con las columnas estándar.
## @ingroup PATHS
## @return None
async def ensure_csv_header():
    if not CSV_PATH.exists():
        with open(CSV_PATH, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["timestamp_ms","iso_time","temperature","bmp","spo2","modelPreccision","riskScore","json_raw"])

## @brief Difunde un payload JSON a todos los clientes WebSocket conectados.
## @details Serializa el `payload` y lo envía a cada cliente activo. Conexiones rotas se purgan.
## @param payload Diccionario serializable a JSON con la lectura a emitir.
## @ingroup STATE
## @return None
async def broadcast(payload: dict):
    # Send one JSON message to all connected WS clients
    data = json.dumps(payload)
    stale = []
    for ws in clients:
        try:
            await ws.send_str(data)
        except Exception:
            stale.append(ws)
    for ws in stale:
        clients.discard(ws)

## @brief Tarea principal BLE: escanea, conecta, suscribe notificaciones, parsea y reintenta ante desconexiones.
## @details
##   - Escanea por nombre del dispositivo y, si no lo encuentra, por UUID de servicio NUS.
##   - Al conectar, se suscribe a notificaciones de `UART_TX_UUID`.
##   - Cada notificación se trata como **línea JSON** terminada en `\\n` → se parsea, se guarda en CSV/JSONL y se difunde por WebSocket.
##   - Si la conexión se cae, reintenta escaneo y reconexión de forma indefinida.
## @param device_name Nombre BLE anunciado por el ESP32 (ej.: `"ESP32-SaudeRemota"`).
## @param scan_timeout Tiempo (s) para cada barrido de escaneo BLE.
## @ingroup BLE_UUIDs
## @return None
## @exception Exception Cualquier error de BLE o parseo se imprime por consola y se reintenta tras breve espera.
async def ble_task(device_name: str, scan_timeout: float):
    """Scan, connect and stream notifications to CSV + WS. Reconnect if needed."""
    await ensure_csv_header()
    while True:
        try:
            print(f"[BLE] Scanning for '{device_name}' (or service {UART_SERVICE_UUID})...")
            dev = None
            devices = await BleakScanner.discover(timeout=scan_timeout)
            # 1) by name
            for d in devices:
                if d.name == device_name:
                    dev = d
                    break
            # 2) by uuid
            if not dev:
                for d in devices:
                    uuids = (d.metadata or {}).get("uuids") or []
                    if any((u or "").lower() == UART_SERVICE_UUID.lower() for u in uuids):
                        dev = d
                        break
            if not dev:
                print("[BLE] Device not found, retrying scan...")
                await asyncio.sleep(2)
                continue

            print(f"[BLE] Connecting to {dev.address} (name={dev.name})")
            async with BleakClient(dev) as client:
                print("[BLE] Connected, subscribing...")
                buffer = bytearray()

                def on_notify(_h, data: bytearray):
                    """!
                    @brief Callback de notificación BLE (hilo del backend BLE).
                    @details
                      - Acumula bytes en un buffer y procesa por líneas delimitadas por `\\n`.
                      - Por cada línea JSON válida:
                          1) Parseo a objeto (dict)
                          2) Persistencia en JSONL y CSV
                          3) Difusión a clientes WebSocket (planificada en el loop principal)
                    @param _h Handle/descriptor de la característica (no utilizado).
                    @param data Bloque de bytes recibido en la notificación.
                    """
                    nonlocal buffer
                    buffer.extend(data)
                    while b"\n" in buffer:
                        line, _, rest = buffer.partition(b"\n")
                        buffer[:] = rest
                        try:
                            obj = json.loads(line.decode("utf-8"))
                            ts = obj.get("ts")
                            payload = obj.get("data", {})
                            iso = datetime.utcfromtimestamp(ts/1000).isoformat()+"Z" if ts else ""
                            # write CSV + JSONL
                            with open(JSONL_PATH, "a", encoding="utf-8") as jf:
                                jf.write(json.dumps(obj, ensure_ascii=False)+"\n")
                            with open(CSV_PATH, "a", newline="") as cf:
                                csv.writer(cf).writerow([
                                    ts, iso,
                                    payload.get("temperature"),
                                    payload.get("bmp"),
                                    payload.get("spo2"),
                                    payload.get("modelPreccision"),
                                    payload.get("riskScore"),
                                    json.dumps(payload, ensure_ascii=False)
                                ])
                            # schedule broadcast (thread-safe -> call_soon_threadsafe)
                            asyncio.get_event_loop().call_soon_threadsafe(asyncio.create_task, broadcast(obj))
                        except Exception as e:
                            print("[BLE] Parse error:", e)

                await client.start_notify(UART_TX_UUID, on_notify)
                print("[BLE] Receiving... (will reconnect on disconnect)")
                while client.is_connected:
                    await asyncio.sleep(1.0)
                print("[BLE] Disconnected, will rescan.")
        except Exception as e:
            print("[BLE] Error:", e)
            await asyncio.sleep(3.0)

# ---------------- HTTP / WS HANDLERS ----------------

## @brief Sirve el documento principal `index.html`.
## @param request Petición HTTP.
## @ingroup PATHS
## @return web.FileResponse con el HTML.
async def index(request: web.Request):
    return web.FileResponse(WEB_DIR / "index.html")

## @brief Sirve archivos CSS desde `web/css/`.
## @param request Petición HTTP; requiere `request.match_info["name"]`.
## @ingroup PATHS
## @return web.FileResponse con el recurso solicitado.
async def static_css(request: web.Request):
    fname = request.match_info["name"]
    path = WEB_DIR / "css" / fname
    return web.FileResponse(path)

## @brief Sirve archivos JS desde `web/js/`.
## @param request Petición HTTP; requiere `request.match_info["name"]`.
## @ingroup PATHS
## @return web.FileResponse con el recurso solicitado.
async def static_js(request: web.Request):
    fname = request.match_info["name"]
    path = WEB_DIR / "js" / fname
    return web.FileResponse(path)

## @brief Endpoint de control de estado del servidor.
## @param request Petición HTTP.
## @ingroup STATE
## @return JSON con `ok` y número de clientes WS conectados.
async def health(request: web.Request):
    return web.json_response({"ok": True, "clients": len(clients)})

## @brief Endpoint WebSocket para streaming en tiempo real hacia la UI.
## @details
##   - Acepta la conexión, añade el socket a `clients` y envía un mensaje de estado inicial.
##   - Responde a pings (`"ping" → "pong"`).
##   - Limpia el socket del conjunto al desconectar o error.
## @param request Petición HTTP que se actualizará a WebSocket.
## @ingroup STATE
## @return web.WebSocketResponse
async def ws_handler(request: web.Request):
    ws = web.WebSocketResponse(heartbeat=20)
    await ws.prepare(request)
    clients.add(ws)
    try:
        # notify status
        await ws.send_str(json.dumps({"type":"status","clients":len(clients)}))
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                # (optional) accept pings or commands
                if msg.data == "ping":
                    await ws.send_str("pong")
            elif msg.type == WSMsgType.ERROR:
                break
    finally:
        clients.discard(ws)
    return ws

## @brief Arranca el servidor HTTP/WS y la tarea BLE, y mantiene el bucle principal.
## @details
##   - Define rutas HTTP/WS (estáticos, `/ws`, `/health`).
##   - Lanza la tarea `ble_task()` concurrentemente.
##   - Gestiona apagado ordenado al cancelar/interrumpir.
## @param args Argumentos CLI parseados (host, port, device_name, scan_timeout).
## @ingroup PATHS
## @return None
async def main_async(args):
    app = web.Application()
    app.add_routes([
        web.get("/", index),
        web.get("/health", health),
        web.get("/ws", ws_handler),
        web.get("/css/{name}", static_css),
        web.get("/js/{name}", static_js),
    ])

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=args.host, port=args.port)
    await site.start()
    print(f"[WEB] Serving on http://{args.host}:{args.port}")

    # Start BLE task
    ble = asyncio.create_task(ble_task(args.device_name, args.scan_timeout))

    try:
        while True:
            await asyncio.sleep(3600)
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        ble.cancel()
        await runner.cleanup()

## @brief Define y parsea los argumentos de línea de comandos.
## @details
##   - `--device-name`: nombre BLE anunciado por el ESP32.
##   - `--host`: interfaz de red a escuchar (por defecto `127.0.0.1`).
##   - `--port`: puerto HTTP (por defecto `8000`).
##   - `--scan-timeout`: segundos por barrido de escaneo BLE.
## @ingroup PATHS
## @return argparse.Namespace con los campos `device_name`, `host`, `port`, `scan_timeout`.
def parse_args():
    p = argparse.ArgumentParser(description="BLE receiver + Web UI server")
    p.add_argument("--device-name", default="ESP32-SaudeRemota", help="BLE advertised device name")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--scan-timeout", type=float, default=8.0)
    return p.parse_args()

if __name__ == "__main__":
    args = parse_args()
    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        pass
