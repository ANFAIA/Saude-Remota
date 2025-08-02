import time
import json
import requests


class FirebaseRawSender:
    """
    Envía lecturas a la ruta `raw/` de una Realtime Database de Firebase.
    Uso típico:
        sender = FirebaseRawSender(...credenciales...)
        sender.send_measurement(36.5, 78, 98)          # ← datos en Firebase
    """
    def __init__(self,
                 email: str,
                 password: str,
                 api_key: str,
                 database_url: str,
                 session: requests.Session | None = None) -> None:
        self.email = email
        self.password = password
        self.api_key = api_key
        self.database_url = database_url.rstrip("/")
        self.session = session or requests.Session()
        self.id_token: str | None = None
        self._authenticate()

    # ---------- API pública ----------

    def send_measurement(self,
                         temperature: float,
                         bmp: float,
                         spo2: float,
                         timestamp_ms: int | None = None) -> None:
        """
        Construye el payload con tus valores *y lo envía de inmediato*.

        :param temperature: Temperatura en °C
        :param bmp: Pulsaciones por minuto
        :param spo2: Saturación de O₂ %
        :param timestamp_ms: Época en milisegundos; si se omite se usa "ahora"
        """
        payload = {
            "temperature": round(float(temperature), 2),
            "bmp": round(float(bmp), 2),
            "spo2": round(float(spo2), 2),
        }
        self.send_raw(payload, timestamp_ms)

    def send_raw(self, data: dict, timestamp_ms: int | None = None) -> None:
        """
        Envía un diccionario ya preparado a Firebase.
        :param data: Dict con los campos que quieras almacenar
        :param timestamp_ms: Marca de tiempo en ms; si se omite se usa "ahora"
        """
        if timestamp_ms is None:
            timestamp_ms = int(time.time() * 1000)

        if not self.id_token:
            self._authenticate()

        url = f"{self.database_url}/raw/{timestamp_ms}.json"
        params = {"auth": self.id_token}

        try:
            res = self.session.put(url, params=params, data=json.dumps(data), timeout=10)
            res.raise_for_status()
        except requests.HTTPError as e:
            print("Error HTTP al escribir en Firebase:", e.response.text)
        except Exception as e:
            print("Excepción al escribir en Firebase:", e)

    # ---------- Métodos internos ----------

    def _authenticate(self) -> None:
        url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={self.api_key}"
        payload = {
            "email": self.email,
            "password": self.password,
            "returnSecureToken": True
        }
        try:
            res = self.session.post(url, json=payload, timeout=10)
            res.raise_for_status()
            self.id_token = res.json().get("idToken")
        except requests.HTTPError as e:
            raise RuntimeError(f"Error de autenticación: {e.response.text}") from e

