#!/bin/bash

# =========================
#  upload.sh — versión segura
# =========================

if ! command -v ampy &> /dev/null; then
  echo "❌ Error: 'ampy' no está instalado."
  echo "Instálalo con: pip install adafruit-ampy"
  exit 1
fi

if [ -z "$1" ]; then
  echo "Uso: $0 <PUERTO_SERIAL>"
  echo "Ejemplo: $0 /dev/ttyUSB0"
  exit 1
fi

PORT="$1"
BAUD=115200
DELAY=2

# ==== 1. Probar conexión ====
echo "🔍 Probando conexión con el ESP32..."
if ! ampy --port "$PORT" --baud $BAUD --delay $DELAY ls &> /dev/null; then
  echo "❌ No se pudo conectar al ESP32 en $PORT"
  echo "Verifica que no esté abierto en otro programa (Thonny, screen, etc.)"
  exit 1
fi
echo "✅ Conexión correcta."

# ==== 2. Borrar archivos (excepto boot.py) ====
echo "[1/4] Borrando archivos del ESP32..."
for file in $(ampy --port "$PORT" --baud $BAUD --delay $DELAY ls); do
  if [[ "$file" != "boot.py" ]]; then
    echo "   🗑  Eliminando $file"
    ampy --port "$PORT" --baud $BAUD --delay $DELAY rmdir "$file" 2>/dev/null || \
    ampy --port "$PORT" --baud $BAUD --delay $DELAY rm "$file" 2>/dev/null
  fi
done
echo "✅ Archivos borrados."

# ==== 3. Subir todos los .py ====
echo "[2/4] Subiendo archivos .py..."
find . -type f -name "*.py" | while read file; do
  remote_path="${file#./}"
  echo "   ⬆️  $remote_path"
  ampy --port "$PORT" --baud $BAUD --delay $DELAY put "$file" "$remote_path"
done
echo "✅ Archivos subidos."

# ==== 4. Mostrar contenido final ====
echo "[3/4] Archivos en el ESP32:"
ampy --port "$PORT" --baud $BAUD --delay $DELAY ls

echo "🎯 Proceso completado."
