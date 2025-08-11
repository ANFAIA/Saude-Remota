#!/bin/bash

# ===============================
#  upload.sh para ESP32 (ampy)
# ===============================
# Uso:
#   ./upload.sh /dev/ttyUSB0
# ===============================

if ! command -v ampy &> /dev/null; then
  echo "El comando 'ampy' no está instalado."
  echo "Instálalo con:"
  echo "pip install adafruit-ampy"
  exit 1
fi

if [ -z "$1" ]; then
  echo "Uso: $0 <PUERTO_SERIAL>"
  echo "Ejemplo: $0 /dev/ttyUSB0"
  exit 1
fi

PORT="$1"

# ====== Función para borrar recursivamente (excepto boot.py) ======
function borrar_remoto_recursivo() {
  local path="$1"
  local archivos
  archivos=$(ampy --port "$PORT" ls "$path" 2>/dev/null)

  if [ -z "$archivos" ]; then
    return
  fi

  while read -r archivo; do
    archivo=${archivo//$'\r'/}
    [ -z "$archivo" ] && continue
    full_path="$path/$archivo"
    if [[ "$archivo" == "boot.py" ]]; then
      continue
    fi
    if [[ "$archivo" == *.* ]]; then
      ampy --port "$PORT" rm "$full_path" || true
    else
      borrar_remoto_recursivo "$full_path"
      ampy --port "$PORT" rmdir "$full_path" || true
    fi
  done <<< "$archivos"
}

echo "[1/4] Borrando archivos del ESP32 (excepto boot.py)..."
borrar_remoto_recursivo ""

# ====== Función para subir un archivo y crear carpeta si no existe ======
function subir_archivo() {
  local archivo="$1"
  local destino="$2"
  local carpeta
  carpeta=$(dirname "$destino")

  if [ "$carpeta" != "." ]; then
    ampy --port "$PORT" mkdir "$carpeta" 2>/dev/null || true
  fi

  ampy --port "$PORT" put "$archivo" "$destino"
}

echo "[2/4] Subiendo archivos .py..."
while IFS= read -r -d '' archivo; do
  destino="${archivo#./}"
  subir_archivo "$archivo" "$destino"
done < <(find . -type f -name "*.py" -print0)

echo "[3/4] Subiendo archivos del modelo..."
for modelo_file in "./lib/predictionModel/modeloIA/pesos.json" "./lib/predictionModel/modeloIA/escala.json"; do
  if [ -f "$modelo_file" ]; then
    destino="${modelo_file#./}"
    subir_archivo "$modelo_file" "$destino"
  else
    echo "⚠️  Aviso: No se encontró $modelo_file"
  fi
done

echo "[4/4] Mostrando estructura de archivos en el ESP32:"
ampy --port "$PORT" ls -r

echo "✅ Subida completa."
