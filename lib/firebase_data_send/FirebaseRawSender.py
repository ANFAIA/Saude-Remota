## @file FirebaseRawSender.py
#  @brief Librería MicroPython para enviar lecturas a Firebase Realtime Database.
#
#  Esta clase permite autenticarse con Firebase mediante correo y contraseña,
#  y enviar mediciones o datos arbitrarios a la ruta `raw/` de la base de datos.
#
#  @author Alejandro Fernández Rodríguez
#  @contact github.com/afernandezLuc
#  @version 1.0.0
#  @date 2025-08-02
#  @copyright Copyright (c) 2025 Alejandro Fernández Rodríguez
#  @license MIT — Consulte el archivo LICENSE para más información.
#  ---------------------------------------------------------------------------

import ujson as json
import urequests as requests
import time


class FirebaseRawSender:
    """
    @class FirebaseRawSender
    @brief Cliente para enviar datos a Firebase Realtime Database usando REST API.
    
    Este cliente permite autenticar con Firebase Auth (correo/contraseña),
    y enviar lecturas a una ruta de tiempo (`/raw/timestamp.json`).
    """

    def __init__(self, email, password, api_key, database_url):
        """
        @brief Constructor de la clase.

        @param email Correo electrónico del usuario de Firebase.
        @param password Contraseña del usuario.
        @param api_key Clave de API del proyecto de Firebase.
        @param database_url URL de la base de datos Realtime (sin `/` al final).
        """
        self.email = email
        self.password = password
        self.api_key = api_key
        self.database_url = database_url.rstrip("/")
        self.id_token = None
        self._authenticate()

    def send_measurement(self, temperature, bmp, spo2, modelPreccision=0.0, riskScore=0.0, timestamp_ms=None):
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
        self.send_raw(payload, timestamp_ms)

    def send_raw(self, data, timestamp_ms=None):
        """
        @brief Envía un diccionario arbitrario a la base de datos Firebase.

        @param data Diccionario de datos a almacenar.
        @param timestamp_ms Marca de tiempo personalizada en milisegundos.
                         Si no se proporciona, se usa el tiempo actual.
        """
        if timestamp_ms is None:
            timestamp_ms = int(time.time() * 1000)

        if not self.id_token:
            self._authenticate()

        url = f"{self.database_url}/raw/{timestamp_ms}.json?auth={self.id_token}"

        try:
            headers = {'Content-Type': 'application/json'}
            res = requests.put(url, data=json.dumps(data), headers=headers)
            res.close()
        except Exception as e:
            print("Error al escribir en Firebase:", e)

    def _authenticate(self):
        """
        @brief Realiza la autenticación con Firebase Auth y obtiene el ID token.
        """
        url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={self.api_key}"
        payload = {
            "email": self.email,
            "password": self.password,
            "returnSecureToken": True
        }

        try:
            headers = {'Content-Type': 'application/json'}
            res = requests.post(url, data=json.dumps(payload), headers=headers)
            if res.status_code == 200:
                self.id_token = res.json().get("idToken")
            else:
                print("Error de autenticación:", res.text)
            res.close()
        except Exception as e:
            print("Excepción al autenticar:", e)
