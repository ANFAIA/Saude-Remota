#!/bin/bash

# -----------------------------------------------------------------------------
#  @file upload.sh
#  @brief Script Bash para cargar automáticamente archivos .py a un dispositivo
#         MicroPython/ESP32 mediante **adafruit‑ampy**.
#
#  El script realiza estas tareas:
#    1. Verifica que `ampy` esté instalado en el sistema.
#    2. Comprueba que se haya proporcionado el puerto serie.
#    3. Elimina recursivamente todo el contenido existente en el sistema de
#       archivos del dispositivo (excepto *boot.py*).
#    4. Sube todos los archivos *.py* presentes en el directorio actual y sus
#       sub‑carpetas, creando la jerarquía remota necesaria.
#    5. Muestra al final un árbol de archivos resultante.
#
#  @usage
#    ./upload.sh <PUERTO_SERIAL>
#  @example
#    ./upload.sh /dev/ttyUSB0
#
#  @dependencies adafruit‑ampy ≥ 1.1.0 (pip install adafruit‑ampy)
#  @author Alejandro Fernández Rodríguez
#  @contact github.com/afernandez13Uclm
#  @version 1.0.0
#  @date 2025‑08‑02
#  @license MIT
# -----------------------------------------------------------------------------

set -euo pipefail

if ! command -v ampy &> /dev/null; then
  echo "El comando 'ampy' no está instalado."
  echo "Instálalo con: pip install adafruit-ampy"
  exit 1
fi

if [ -z "${1-}" ]; then
  echo "Uso: $0 <PUERTO_SERIAL>"
  echo "Ejemplo: $0 /dev/ttyUSB0"
  exit 1
fi

PORT="$1"

borrar_remoto_recursivo() {
  local path="$1"
  local entradas
  entradas=$(ampy --port "$PORT" ls "$path" 2>/dev/null || true)
  [ -z "$entradas" ] && return

  while IFS= read -r entrada; do
    entrada=${entrada//$'\r'/}
    [ -z "$entrada" ] && continue
    local full_path
    if [ "$path" = "/" ]; then
      full_path="/$entrada"
    else
      full_path="$path/$entrada"
    fi
    # No borrar boot.py
    if [[ "$full_path" == "/boot.py" ]]; then
      continue
    fi
    if ampy --port "$PORT" ls "$full_path" &>/dev/null; then
      borrar_remoto_recursivo "$full_path"
      ampy --port "$PORT" rmdir "$full_path" 2>/dev/null || true
    else
      ampy --port "$PORT" rm "$full_path" 2>/dev/null || true
    fi
  done <<< "$entradas"
}

listar_remoto_recursivo() {
  local path="$1"
  local prefix="$2"
  local entradas
  entradas=$(ampy --port "$PORT" ls "$path" 2>/dev/null || true)
  [ -z "$entradas" ] && return

  while IFS= read -r item; do
    item=${item//$'\r'/}
    [ -z "$item" ] && continue

    local full_path
    if [ "$path" = "/" ]; then
      full_path="/$item"
    else
      full_path="$path/$item"
    fi

    if ampy --port "$PORT" ls "$full_path" &>/dev/null; then
      echo "${prefix}${item}/"
      listar_remoto_recursivo "$full_path" "  $prefix"
    else
      echo "${prefix}${item}"
    fi
  done <<< "$entradas"
}

echo "Borrando archivos remotos existentes (excepto /boot.py)..."
borrar_remoto_recursivo "/"

echo "Iniciando carga a $PORT"
echo "============================"

# Busca *.py y *.json, ignorando directorios comunes que no debemos subir
# -print0 + read -d '' permite manejar nombres con espacios
find . \
  -path "./.git" -prune -o \
  -path "./.venv" -prune -o \
  -path "./venv" -prune -o \
  -path "./__pycache__" -prune -o \
  -path "./.mypy_cache" -prune -o \
  -type f \( -name "*.py" -o -name "*.json" \) -print0 \
| while IFS= read -r -d '' LOCAL_FILE; do
    # Quita el prefijo "./"
    REL="${LOCAL_FILE#./}"
    REMOTE_PATH="/$REL"
    REMOTE_DIR="$(dirname "$REMOTE_PATH")"

    echo "Verificando carpeta remota: $REMOTE_DIR"
    IFS='/' read -r -a PARTS <<< "$REMOTE_DIR"
    CURRENT=""
    for part in "${PARTS[@]}"; do
      [ -z "$part" ] && continue
      CURRENT="$CURRENT/$part"
      ampy --port "$PORT" mkdir "$CURRENT" 2>/dev/null || true
    done

    echo -n "Subiendo $REL ... "
    if ampy --port "$PORT" put "$LOCAL_FILE" "$REMOTE_PATH" 2>/dev/null; then
      echo "Ok"
    else
      echo "Error"
    fi
  done

echo -e "\nListando archivos en el ESP32:"
echo "============================"
listar_remoto_recursivo "/" ""
echo "============================"

echo -e "\nCarga finalizada."
echo "Puedes ejecutar el programa con:"
echo "ampy --port $PORT run main.py"
