# @file firebase_raw_sender_pc.py
# @brief Librería Python (PC) para enviar lecturas a Firebase Realtime Database.
#
# Esta versión es equivalente funcionalmente a la versión MicroPython proporcionada,
# pero pensada para ejecutarse en un PC/servidor:
#   - Usa `json` en lugar de `ujson`
#   - Usa `requests` en lugar de `urequests`
#   - Elimina cualquier lógica de Wi‑Fi/ESP32
#
# @author Alejandro Fernández Rodríguez
# @contact github.com/afernandezLuc
# @version 1.0.0
# @date 2025-08-31
# @copyright Copyright (c) 2025
# @license MIT — Consulte el archivo LICENSE para más información.
# ---------------------------------------------------------------------------

from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional
import requests


class FirebaseRawSender:
    """
    @class FirebaseRawSender
    @brief Cliente para enviar datos a Firebase Realtime Database desde PC.

    Replica la interfaz pública del ejemplo MicroPython:
      - Autenticación por email/contraseña (Firebase Auth REST)
      - Envío de mediciones estándar con `send_measurement(...)`
      - Envío de datos arbitrarios con `send_raw({...})` a la ruta `raw/<timestamp>.json`
    """

    def __init__(
        self,
        email: str,
        password: str,
        api_key: str,
        database_url: str,
        *,  # solo argumentos con nombre a partir de aquí
        session: Optional[requests.Session] = None,
        request_timeout: float = 10.0,
        user_agent: str = "FirebaseRawSender-PC/1.0",
    ) -> None:
        """
        @brief Constructor de la clase.

        @param email Correo electrónico del usuario Firebase.
        @param password Contraseña del usuario Firebase.
        @param api_key Clave de API Web del proyecto Firebase (del panel de Firebase).
        @param database_url URL base de la RTDB (por ejemplo: https://tu-proyecto-default-rtdb.europe-west1.firebasedatabase.app)
                            No debe terminar en '/'. Se recorta automáticamente.
        @param session (Opcional) requests.Session reutilizable.
        @param request_timeout (Opcional) Timeout en segundos para las peticiones HTTP.
        @param user_agent (Opcional) Cabecera User-Agent personalizada.
        """
        self.email = email
        self.password = password
        self.api_key = api_key
        self.database_url = database_url.rstrip("/")
        self.id_token: Optional[str] = None

        self._session = session or requests.Session()
        self._timeout = float(request_timeout)
        self._ua = user_agent

        self._authenticate()

    def send_measurement(
        self,
        temperature: float,
        bmp: float,
        spo2: float,
        modelPreccision: float = 0.0,
        riskScore: float = 0.0,
        timestamp_ms: Optional[int] = None,
    ) -> None:
        """
        @brief Envía una medición estándar a Firebase.

        @param temperature Temperatura corporal (°C).
        @param bmp Pulsaciones por minuto.
        @param spo2 Saturación de oxígeno (%).
        @param modelPreccision Precisión del modelo (0.0 a 1.0).
        @param riskScore Riesgo calculado por el modelo (0.0 a 1.0).
        @param timestamp_ms Marca temporal en milisegundos desde época Unix.
        """
        payload = {
            "temperature": round(float(temperature), 2),
            "bmp": round(float(bmp), 2),
            "spo2": round(float(spo2), 2),
            "modelPreccision": round(float(modelPreccision), 2),
            "riskScore": round(float(riskScore), 2),
        }
        self.send_raw(payload, timestamp_ms=timestamp_ms)

    def send_raw(self, data: Dict[str, Any], timestamp_ms: Optional[int] = None) -> None:
        """
        @brief Envía un diccionario arbitrario a la base de datos Firebase.
        @param data Diccionario de datos a almacenar.
        @param timestamp_ms Marca temporal en ms. Si no se proporciona, se usa el tiempo actual.
        """
        if timestamp_ms is None:
            timestamp_ms = int(time.time() * 1000)

        if not self.id_token:
            self._authenticate()

        url = f"{self.database_url}/raw/{timestamp_ms}.json"
        params = {"auth": self.id_token}

        try:
            res = self._session.put(
                url,
                params=params,
                data=json.dumps(data),
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": self._ua,
                },
                timeout=self._timeout,
            )
            res.raise_for_status()
        finally:
            try:
                res.close()
            except Exception:
                pass

    def _authenticate(self) -> None:
        """
        @brief Realiza la autenticación con Firebase Auth y obtiene el ID token (idToken).
        """
        url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
        params = {"key": self.api_key}
        payload = {
            "email": self.email,
            "password": self.password,
            "returnSecureToken": True,
        }

        res = None
        try:
            res = self._session.post(
                url,
                params=params,
                data=json.dumps(payload),
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": self._ua,
                },
                timeout=self._timeout,
            )
            if res.status_code == 200:
                body = res.json()
                self.id_token = body.get("idToken")
                if not self.id_token:
                    raise RuntimeError("Respuesta de autenticación sin 'idToken'.")
                print("✔ Autenticado con Firebase.")
            else:
                # Incluir cuerpo textual para facilitar la depuración
                raise RuntimeError(f"Error de autenticación: {res.status_code} — {res.text}")
        except requests.RequestException as e:
            raise RuntimeError(f"Excepción de red al autenticar: {e}") from e
        finally:
            try:
                res.close()
            except Exception:
                pass

