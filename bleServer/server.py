## @file server.py
#  @brief Servidor BLE → Web con envío a Firebase usando cola asíncrona y configuración por JSON.
#
#  @details
#  Este módulo implementa un servidor que:
#   - Descubre y se conecta por **Bluetooth Low Energy (BLE)** a un ESP32 con
#     el servicio **Nordic UART Service (NUS)**.
#   - Recibe mediciones como **líneas JSON** vía notificaciones BLE.
#   - Persiste en **CSV** y **JSONL**.
#   - Publica cada lectura en tiempo real a navegadores via **WebSocket (aiohttp)**.
#   - Encola las lecturas y las envía a **Firebase Realtime Database** mediante
#     un *worker* asíncrono que usa `requests` (bloqueante) sin frenar BLE.
#   - Permite cargar las credenciales de Firebase desde un **archivo JSON** de configuración.
#
#  Arquitectura:
#   - **ble_task**: scan → connect → subscribe → parse → persist → broadcast → enqueue(Firebase)
#   - **firebase_worker**: consume cola → (re)intentos con backoff → sender.send_*
#   - **Servidor HTTP/WS**: rutas estáticas y `/ws` para streaming (aiohttp)
#
#  Configuración de Firebase (prioridad descendente):
#   1. Argumentos CLI: --fb-email, --fb-password, --fb-api-key, --fb-db-url
#   2. JSON con --fb-config
#   3. Variables de entorno: FIREBASE_EMAIL, FIREBASE_PASSWORD, FIREBASE_API_KEY, FIREBASE_DB_URL
#
#  @author
#    Alejandro Fernández Rodríguez — github.com/afernandezLuc
#  @version 1.2.0
#  @date 2025-08-31
#  ---------------------------------------------------------------------------

from __future__ import annotations

import asyncio
import json
import csv
import argparse
import os
from datetime import datetime
from pathlib import Path
from typing import Set, Optional, Dict, Any

from aiohttp import web, WSMsgType
from bleak import BleakScanner, BleakClient

from lib.Firebase.FirebaseSender import FirebaseRawSender

# =============================================================================
#                                CONSTANTES / UUIDs
# =============================================================================

UART_SERVICE_UUID: str = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
UART_TX_UUID: str      = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

# =============================================================================
#                                 RUTAS / ARCHIVOS
# =============================================================================

HERE: Path = Path(__file__).resolve().parent
WEB_DIR: Path = HERE / "web"
LOG_DIR: Path = HERE / "logs"
LOG_DIR.mkdir(exist_ok=True)

CSV_PATH: Path   = LOG_DIR / "raw_log.csv"
JSONL_PATH: Path = LOG_DIR / "raw_log.jsonl"

# =============================================================================
#                                  ESTADO GLOBAL
# =============================================================================

clients: Set[web.WebSocketResponse] = set()
FIREBASE_QUEUE: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(maxsize=1000)
firebase_sender: Optional[FirebaseRawSender] = None
ENABLE_FIREBASE: bool = True

# =============================================================================
#                               UTILIDADES / HELPERS
# =============================================================================

async def ensure_csv_header() -> None:
    if not CSV_PATH.exists():
        with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["timestamp_ms","iso_time","temperature","bmp","spo2","modelPreccision","riskScore","json_raw"])

async def broadcast(payload: Dict[str, Any]) -> None:
    data = json.dumps(payload, ensure_ascii=False)
    stale = []
    for ws in clients:
        try:
            await ws.send_str(data)
        except Exception:
            stale.append(ws)
    for ws in stale:
        clients.discard(ws)

async def firebase_worker() -> None:
    if not ENABLE_FIREBASE:
        while True:
            _ = await FIREBASE_QUEUE.get()
            FIREBASE_QUEUE.task_done()

    if firebase_sender is None:
        print("[FB] Advertencia: firebase_sender es None. El worker descartará lecturas.")
        while True:
            _ = await FIREBASE_QUEUE.get()
            FIREBASE_QUEUE.task_done()

    backoff = 1.0
    while True:
        obj = await FIREBASE_QUEUE.get()
        try:
            ts = obj.get("ts")
            data = obj.get("data", {})
            if all(k in data for k in ("temperature","bmp","spo2")):
                firebase_sender.send_measurement(
                    temperature=data.get("temperature",0.0),
                    bmp=data.get("bmp",0.0),
                    spo2=data.get("spo2",0.0),
                    modelPreccision=data.get("modelPreccision",0.0),
                    riskScore=data.get("riskScore",0.0),
                    timestamp_ms=ts,
                )
            else:
                firebase_sender.send_raw(obj, timestamp_ms=ts)
            backoff = 1.0
        except Exception as e:
            print(f"[FB] Error enviando a Firebase: {e}. Reintentando en {backoff:.1f}s")
            await asyncio.sleep(backoff)
            backoff = min(backoff*2.0, 30.0)
            await FIREBASE_QUEUE.put(obj)
        finally:
            FIREBASE_QUEUE.task_done()

# =============================================================================
#                                   TAREA BLE
# =============================================================================

async def ble_task(device_name: str, scan_timeout: float) -> None:
    await ensure_csv_header()
    loop = asyncio.get_event_loop()
    while True:
        try:
            devices = await BleakScanner.discover(timeout=scan_timeout)
            print(f"[BLE] {len(devices)} dispositivos encontrados.")
            dev = next((d for d in devices if d.name==device_name), None)
            if not dev:
                for d in devices:
                    uuids = (d.metadata or {}).get("uuids") or []
                    if any((u or "").lower() == UART_SERVICE_UUID.lower() for u in uuids):
                        dev = d; break
            if not dev:
                print(f"[BLE] ❌ No se encontró {device_name}. Reintentando...")
                await asyncio.sleep(2.0)
                continue
            print(f"[BLE] ✔ Encontrado {device_name} ({dev.address}), intentando conectar...")
            async with BleakClient(dev) as client:
                print(f"[BLE] 🔗 Conectado a {dev.address}. Suscribiéndose a notificaciones...")
                buffer = bytearray()
                def on_notify(_h, data: bytearray):
                    nonlocal buffer
                    buffer.extend(data)
                    while b"\n" in buffer:
                        line,_,rest = buffer.partition(b"\n")
                        buffer[:] = rest
                        try:
                            obj = json.loads(line.decode("utf-8"))
                            ts = obj.get("ts")
                            payload = obj.get("data", {})
                            iso = datetime.utcfromtimestamp(ts/1000).isoformat()+"Z" if ts else ""
                            with open(JSONL_PATH,"a",encoding="utf-8") as jf:
                                jf.write(json.dumps(obj,ensure_ascii=False)+"\n")
                            with open(CSV_PATH,"a",newline="",encoding="utf-8") as cf:
                                csv.writer(cf).writerow([
                                    ts, iso,
                                    payload.get("temperature"),
                                    payload.get("bmp"),
                                    payload.get("spo2"),
                                    payload.get("modelPreccision"),
                                    payload.get("riskScore"),
                                    json.dumps(payload,ensure_ascii=False)
                                ])
                            loop.call_soon_threadsafe(asyncio.create_task,broadcast(obj))
                            if ENABLE_FIREBASE:
                                try:
                                    loop.call_soon_threadsafe(FIREBASE_QUEUE.put_nowait,obj)
                                except asyncio.QueueFull:
                                    print("[FB] Cola llena: lectura descartada.")
                        except Exception as e:
                            print("[BLE] Parse error:",e)
                await client.start_notify(UART_TX_UUID,on_notify)
                print("[BLE] ✅ Suscripción activa.")
                while client.is_connected: await asyncio.sleep(1.0)
        except Exception as e:
            print("[BLE] Error:",e)
            await asyncio.sleep(3.0)

# =============================================================================
#                           HTTP / WS HANDLERS
# =============================================================================

async def index(request): return web.FileResponse(WEB_DIR/"index.html")
async def static_css(request): return web.FileResponse(WEB_DIR/"css"/request.match_info["name"])
async def static_js(request):  return web.FileResponse(WEB_DIR/"js"/request.match_info["name"])

async def health(request):
    return web.json_response({"ok":True,"clients":len(clients),"firebase_enabled":ENABLE_FIREBASE,"queue_size":FIREBASE_QUEUE.qsize()})

async def ws_handler(request):
    ws=web.WebSocketResponse(heartbeat=20); await ws.prepare(request); clients.add(ws)
    try:
        await ws.send_str(json.dumps({"type":"status","clients":len(clients)}))
        async for msg in ws:
            if msg.type==WSMsgType.TEXT and msg.data=="ping":
                await ws.send_str("pong")
    finally:
        clients.discard(ws)
    return ws

# =============================================================================
#                              MAIN APP
# =============================================================================

async def main_async(args):
    global ENABLE_FIREBASE,firebase_sender
    ENABLE_FIREBASE=not args.no_firebase
    config_data={}
    if args.fb_config:
        with open(args.fb_config,"r",encoding="utf-8") as f:
            config_data=json.load(f)
    if ENABLE_FIREBASE:
        email=args.fb_email or config_data.get("email") or os.getenv("FIREBASE_EMAIL")
        password=args.fb_password or config_data.get("password") or os.getenv("FIREBASE_PASSWORD")
        api_key=args.fb_api_key or config_data.get("api_key") or os.getenv("FIREBASE_API_KEY")
        db_url=args.fb_db_url or config_data.get("database_url") or os.getenv("FIREBASE_DB_URL")
        if not all([email,password,api_key,db_url]):
            raise RuntimeError("Credenciales Firebase incompletas.")
        firebase_sender=FirebaseRawSender(email=email,password=password,api_key=api_key,database_url=db_url)
        print("[FB] Envío a Firebase habilitado.")
    app=web.Application()
    app.add_routes([web.get("/",index),web.get("/health",health),web.get("/ws",ws_handler),
                    web.get("/css/{name}",static_css),web.get("/js/{name}",static_js)])
    runner=web.AppRunner(app); await runner.setup()
    site=web.TCPSite(runner,host=args.host,port=args.port); await site.start()
    url = f"http://{args.host}:{args.port}"
    print(f"[WEB] 🌍 Servidor disponible en {url}")
    print(f"[WEB] Endpoints: {url}/  {url}/ws  {url}/health")
    ble=asyncio.create_task(ble_task(args.device_name,args.scan_timeout))
    fbw=asyncio.create_task(firebase_worker())
    try:
        while True: await asyncio.sleep(3600)
    except (asyncio.CancelledError,KeyboardInterrupt): pass
    finally:
        ble.cancel(); fbw.cancel(); await runner.cleanup()

def parse_args():
    p=argparse.ArgumentParser()
    p.add_argument("--device-name",default="ESP32-SaudeRemota")
    p.add_argument("--host",default="127.0.0.1")
    p.add_argument("--port",type=int,default=8000)
    p.add_argument("--scan-timeout",type=float,default=8.0)
    p.add_argument("--no-firebase",action="store_true")
    p.add_argument("--fb-config",default=None)
    p.add_argument("--fb-email",default=None)
    p.add_argument("--fb-password",default=None)
    p.add_argument("--fb-api-key",default=None)
    p.add_argument("--fb-db-url",default=None)
    return p.parse_args()

if __name__=="__main__":
    args=parse_args()
    try: asyncio.run(main_async(args))
    except KeyboardInterrupt: pass
