# boot.py
# ---------------------------------------------------
# Arranque automático del ESP32 con MicroPython
# Llama a main.py al iniciar.
# ---------------------------------------------------

import sys
import time

print("\n[BOOT] ESP32 arrancando...")
time.sleep(1)

try:
    import main
    print("[BOOT] main.py ejecutándose correctamente ✅")
except Exception as e:
    print("[BOOT] ERROR al ejecutar main.py ❌")
    sys.print_exception(e)
