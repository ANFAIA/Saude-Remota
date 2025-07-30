# Módulo para guardar datos del sensor MAX30102 en un archivo simulado (CSV)

import time

ARCHIVO = "datos_max30102.csv"

class FileStore: 
    def __init__(self, archivo=ARCHIVO):
        self.archivo = archivo

    # Inicializa el archivo si no existe, escribiendo la cabecera
    def inicializar_archivo(self):
        try:
            with open(self.archivo, "x") as f: # Crea el archivo sólo si no existe ("x" = modo exclusivo)
                f.write("timestamp,heart_rate,spo2,temperature\n")
        except OSError:
            pass  # El archivo ya existe

    # Guarda una lectura de los datos del sensor en el archivo
    def guardar_datos(self, hr, spo2, temp):
        timestamp = time.time()  # Tiempo desde que se encendió el ESP32 (en segundos)
        try:
            with open(self.archivo, "a") as f: # El archivo se abre en modo append ("a") para agregar sin borrar nada
                f.write(f"{timestamp:.2f},{hr},{spo2},{temp}\n")
        except Exception as e:
            print("Error guardando datos:", e)

    # Lee todas las filas del archivo (por si se quieren enviar o visualizar)
    def leer_datos(self):
        datos = []
        try:
            with open(self.archivo, "r") as f: # Abre el archivo en modo lectura "r"
                next(f)  # saltar cabecera
                for linea in f:
                    valores = linea.strip().split(",") # Para cada línea, la divide en columnas por ,
                    datos.append({
                        "timestamp": float(valores[0]),
                        "heart_rate": int(valores[1]),
                        "spo2": int(valores[2]),
                        "temperature": float(valores[3])
                    })
        except Exception as e:
            print("Error leyendo archivo:", e)
        return datos

    # Borra el archivo si se necesita liberar espacio o reiniciar almacenamiento
    def borrar_datos(self):
        try:
            import os
            os.remove(self.archivo)  # Elimina el archivo
            print("Archivo eliminado con éxito")
        except OSError:
            print("No se pudo eliminar el archivo (quizá no existe)")
