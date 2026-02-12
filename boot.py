#boot.py
#arranque automático del ESP32 con MicroPython
#llama a main.py al iniciar

import sys #permite imprimir errores
import time #permite hacer pausas

print("\n[BOOT] ESP32 arrancando...")
time.sleep(1) #pausa el programa 1s para dar tiempo a que el puerto serie se estabilice y se puedan ver los mensajes

try:
    import main
    print("[BOOT] main.py ejecutándose correctamente ✅")
except Exception as e: #guarda el error en la variable "e"
    print("[BOOT] ERROR al ejecutar main.py ❌")
    sys.print_exception(e) #imprime el error indicando en qué línea del código se produjo 
