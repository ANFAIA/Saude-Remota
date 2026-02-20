# Servidor BLE → Web (Saúde Remota)

Este servidor **escucha por Bluetooth Low Energy (BLE)** a tu ESP32 (perfil **UART/NUS**), 
**difunde los datos en tiempo real al navegador** vía **WebSocket**, **registra** todas las lecturas en **CSV** (y JSONL) y envía las mediciones a una base de datos de tiempo real en **Firebase**.

- BLE mediante [`bleak`](https://github.com/hbldh/bleak)
- HTTP/WS mediante [`aiohttp`](https://docs.aiohttp.org/)
- UI estática servida desde `web/` (tu `index.html` y CSS)
- Logs en `logs/raw_log.csv` y `logs/raw_log.jsonl`
- Firebase mediante [`requests`](https://pypi.org/project/requests/)

---

## Requisitos

- **Python 3.11+** (funciona en 3.13)
- macOS 12+/Windows 10+/Linux con adaptador **BLE** compatible
- Paquetes Python: `aiohttp`, `bleak` y `requests`

> **macOS**: si `bleak` lo requiere, instala el extra:  
> `python -m pip install 'bleak[macos]'`

> **Linux**: puede requerir privilegios BLE (o `sudo`). Alternativa recomendada:  
> `sudo setcap 'cap_net_raw,cap_net_admin+eip' $(readlink -f $(which python))`

---

## Instalación (recomendada con entorno virtual)

```bash
cd ble_web_server

python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows (PowerShell)
# .venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
# macOS: python -m pip install 'bleak[macos]'
```

---

## Puesta en marcha

1. Conecta/enciende tu ESP32 y asegúrate de que **está anunciando BLE** con el nombre configurado (p. ej. `ESP32-SaudeRemota`).  
2. Ejecuta el servidor:
   ```bash
   python server.py --device-name "ESP32-SaudeRemota" --host 127.0.0.1 --port 8000
   ```
3. Abre el navegador en:  
   `http://127.0.0.1:8000`

El servidor escaneará por **nombre** y, si no lo encuentra, **por UUID de servicio** (NUS: `6E400001-B5A3-F393-E0A9-E50E24DCCA9E`).  
Si se corta la conexión BLE, se **reconectará** automáticamente.

---

## Estructura del proyecto

```
bleServer/
├─ server.py                  # servidor BLE + HTTP + WebSocket
├─ requirements.txt
├─ LICENSE
├─ README.md
├─ firebaseConfig.json
├─ lib/
│  ├─ Firebase/
│  │  ├─ __init__.py
│  │  ├─ FirebaseSender.py
│  │  ├─ LICENSE
├─ logs/
│  ├─ raw_log.csv             # log en CSV (append)
│  └─ raw_log.jsonl           # log en JSONL (append)
└─ web/
   ├─ index.html              # TU interfaz (ya copiada aquí)
   ├─ css/
   │  ├─ reset.css
   │  ├─ colors.css
   │  └─ styles.css
   └─ js/
      └─ utils.js             # cliente WS que actualiza el DOM
```

---

## Interfaz Web (frontend)

- El backend sirve **estático** desde `web/` (ya se han copiado tus archivos).  
- El archivo `web/js/utils.js` abre un **WebSocket** a `/ws` y actualiza los elementos del DOM que ya tienes en tu UI.
- Si prefieres usar **tu propio** `utils.js`, simplemente reemplázalo por el tuyo y mantén la conexión a `/ws`.

### Esquema de mensajes (WS → navegador)

Cada lectura se emite como un JSON con este formato:

```json
{
  "ts": 1724190000123,
  "data": {
    "temperature": 36.7,
    "bmp": 72,
    "spo2": 98.2,
    "modelPreccision": 0.93,
    "riskScore": 0.12
  }
}
```

> Los valores de `modelPreccision` y `riskScore` suelen venir en `[0,1]`. En la UI los puedes multiplicar por 100 si quieres porcentaje.

---

## Logs

- **CSV**: `logs/raw_log.csv` con cabecera  
  Columnas: `timestamp_ms, iso_time, temperature, bmp, spo2, modelPreccision, riskScore, json_raw`
- **JSONL**: `logs/raw_log.jsonl` una línea por lectura

Puedes cambiar las rutas editando las constantes `CSV_PATH` y `JSONL_PATH` en `server.py`.

---

## Opciones de línea de comandos

```bash
python server.py \
  --device-name "ESP32-SaudeRemota" \  # nombre BLE anunciado por el ESP32
  --host 0.0.0.0 \                     # interfaz de red a escuchar (0.0.0.0 = todas)
  --port 8000 \                        # puerto HTTP
  --scan-timeout 8.0                   # tiempo de cada barrido BLE (s)
  --fb-config firebaseConfig.json      # configuración de acceso a firebase

```

Es posible desactivar el uso de firebase por medio del argumento **--no-firebase** 

---

## Configuración de acceso a Firebase
En el archivo firebaseConfig.json se deben añadir las credenciales de acceso a Firebase

```json
{
  "email": "<TU_EMAIL_DE_ACCESO>",
  "password": "<TU_CLAVE_DE_ACCESO>",
  "api_key": "<TU_API_KEY>",
  "database_url": "<URL_DE_LA_BASE_DE_DATOS>/"
}
```

---

## Solución de problemas

**No encuentra el dispositivo**
- Verifica que el ESP32 está **anunciando** y no está ya conectado a otro host.
- Comprueba el nombre en `--device-name`. Si a veces no aparece el nombre (payload excede 31 bytes), el servidor también buscará por **UUID**.
- Reinicia el ESP32 (Ctrl+D) para regenerar el ADV/SCAN_RSP.

**macOS no detecta nada**
- Concede permisos de **Bluetooth** a tu Terminal/IDE (Ajustes → Privacidad y seguridad → Bluetooth).
- Instala el extra de bleak: `python -m pip install 'bleak[macos]'`.

**Linux: permisos BLE**
- Usa `sudo` al ejecutar o aplica `setcap` al intérprete de Python (ver sección Requisitos).

**El navegador no actualiza**
- Revisa la consola (F12) por errores de WebSocket.
- Asegúrate de abrir la URL y puerto correctos.
- Si sirves detrás de HTTPS, necesitarás **WSS** (ver nota de despliegue).

**Puerto en uso**
- Cambia `--port` o para el proceso que lo esté usando.

---

## Despliegue / Producción

- Por defecto sirve **HTTP** sin TLS. Para exponerlo públicamente, ponlo detrás de un **reverse proxy** (Nginx/Caddy) con TLS y reenvía el WS (`/ws`) como **WSS**.
- Para iniciar al arranque en Linux, puedes usar **systemd**. Ejemplo (ajusta rutas/intérprete):

```
[Unit]
Description=Saude Remota BLE Web Server
After=network-online.target

[Service]
WorkingDirectory=/opt/saude-remota/ble_web_server
ExecStart=/opt/saude-remota/ble_web_server/.venv/bin/python server.py --device-name "ESP32-SaudeRemota" --host 0.0.0.0 --port 8000
Restart=always
User=www-data
Group=www-data
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

---

## Notas

- Este servidor **no implementa autenticación**. Si lo expones fuera de tu red local, añade control de acceso.
- Múltiples navegadores pueden conectarse simultáneamente al WS; todos reciben las mismas lecturas.
- Si deseas **simular datos** sin el ESP32, se puede añadir un modo “simulador” que emita lecturas sintéticas.

---


¡Listo! Abre el servidor, conecta el ESP32, y mira los datos en tu navegador 
