# FirebaseRawSender

Pequeña librería de ayuda para enviar lecturas de dispositivos (IoT, wearables, sensores médicos, etc.) a **Firebase Realtime Database** de forma sencilla y segura.

## Características

- 🔑 **Autenticación automática** con Firebase Auth (método correo/contraseña).  
- 📤 **Envío inmediato** de mediciones mediante `send_measurement(temperature, bmp, spo2)`.  
- 🧩 **`send_raw(payload)`** para mandar cualquier diccionario personalizado.  
- ♻️ Reutiliza `requests.Session` para conexiones HTTP persistentes.  
- ⚠️ Manejo de errores HTTP con `raise_for_status()` y mensajes claros.  
- 🪶 Código independiente, sin dependencias externas (solo `requests`).

---

## Instalación

Requiere **Python ≥ 3.10**.

```bash
pip install requests
```

Clona este repositorio o copia `FirebaseSender.py` a tu proyecto.

---

## Configuración de Firebase Realtime Database

1. Accede a [Firebase Console](https://console.firebase.google.com/) y crea un **nuevo proyecto** (o usa uno existente).
2. En el menú de la izquierda selecciona **Build ▸ Realtime Database** y pulsa **Create Database**.  
   - Elige la ubicación más cercana a tus usuarios.  
   - Selecciona el modo **Locked** (*Start in locked mode*) para que se apliquen reglas de seguridad.
3. Anota la **Database URL** que aparece en la parte superior (formato `https://<TU-PROYECTO>.firebaseio.com`); la necesitarás como `database_url`.
4. Abre la pestaña **Rules** y sustituye el contenido por:

```json
{
  "rules": {
    ".read": "auth != null",
    ".write": "auth.uid === '<YOUR_AUTH_ID>'"
  }
}
```

   - Reemplaza `<YOUR_AUTH_ID>` por el `uid` del usuario autorizado a escribir.  
     Puedes obtener tu `uid` desde **Build ▸ Authentication ▸ Users** después de crear el usuario.
5. En **Build ▸ Authentication ▸ Sign‑in method** habilita **Email/Password** y crea el usuario que utilizarás desde tu dispositivo o aplicación.
6. Dirígete a **Project settings ▸ General** y copia el valor **Web API key** para usarlo como `api_key` en el código.

---

## Uso rápido

```python
from FirebaseSender import FirebaseRawSender
sender = FirebaseRawSender(
    email="usuario@ejemplo.com",
    password="TU_PASSWORD",
    api_key="TU_API_KEY_DE_FIREBASE",
    database_url="https://<TU-PROYECTO>.firebaseio.com"
)

# Envía una medición concreta
sender.send_measurement(temperature=36.6, bmp=72, spo2=98, modelPreccision=90.5, riskScore=0.3)

# O un payload arbitrario
sender.send_raw({"pressure": 1011, "nota": "prueba"})
```

### Nota: Si no se proporciona la configuracion wifi se asume que la conexión ya se ha realizado
---

## Ejemplos avanzados

| Escenario                            | Código / Idea principal                                                                               |
|--------------------------------------|--------------------------------------------------------------------------------------------------------|
| **Enviar varias variables adicionales** | `payload = {"temp": 25.4, "hum": 40, "uv": 3.1}; sender.send_raw(payload)`                           |
| **Timestamp personalizado**          | `sender.send_measurement(36.5, 80, 97, timestamp_ms=1722600000000)`                                   |
| **Reautenticación manual**           | Simplemente llama `sender._authenticate()` si necesitas forzar el refresh del idToken.                |
| **Uso en multihilo / asyncio**       | Instancia la clase en el hilo principal y pasa la misma instancia a los hilos / corrutinas hijas.     |

---

## Variables de entorno (opcional)

Para evitar hardcodear credenciales puedes usar variables de entorno:

| Variable              | Descripción                               |
|-----------------------|-------------------------------------------|
| `FIREBASE_EMAIL`      | Correo de la cuenta de servicio / usuario |
| `FIREBASE_PASSWORD`   | Contraseña de la cuenta                   |
| `FIREBASE_API_KEY`    | API key pública del proyecto de Firebase  |
| `FIREBASE_DB_URL`     | URL de la Realtime Database               |

---

## Contribuciones

¡Las *pull requests* son bienvenidas!  
Abre un *issue* para reportar bugs o proponer mejoras.

---

## Licencia

Distribuido bajo la licencia **MIT**.  
Consulta el archivo [LICENSE](LICENSE) para más detalles.
