#!/usr/bin/env bash

# -----------------------------------------------------------------------------
#  @file upload.sh
#  @brief Script Bash para cargar automáticamente archivos .py a un dispositivo
#         MicroPython/ESP32 mediante **adafruit‑ampy**.
#
#  El script realiza estas tareas:
#    1. Verifica que ampy esté instalado en el sistema.
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
#  @contact github.com/afernandezLuc
#  @version 1.0.0
#  @date 2025‑08‑02
#  @license MIT
# -----------------------------------------------------------------------------

set -euo pipefail

PORT="${1:-}"
[ -z "$PORT" ] && { echo "Uso: $0 /dev/ttyUSBx"; exit 1; }

# --- EXCLUSIONES (añade las que quieras) ---
EXCLUDE_DIRS=( ".venv" "venv" "env" ".git" "__pycache__" ".mypy_cache" ".idea" ".vscode" )
EXCLUDE_FILES=( "*.pyc" "*.pyo" )

# --- Comprobar ampy ---
AMPY_BIN="$(command -v ampy || true)"
[ -z "$AMPY_BIN" ] && { echo "No encuentro 'ampy'. Instala con: pipx install adafruit-ampy"; exit 1; }

# --- Funciones auxiliares ---
borrar_rec() {
  local base="$1"
  # Lista de nivel actual
  local items
  items="$("$AMPY_BIN" --port "$PORT" ls "$base" 2>/dev/null || true)"

  [ -z "$items" ] && return 0

  while IFS= read -r it; do
    it="${it%$'\r'}"
    [ -z "$it" ] && continue
    local full="${base%/}/$it"
    # No borrar boot.py de la raíz
    if [[ "$full" == "/boot.py" ]]; then
      continue
    fi
    # ¿Es directorio? truco: si 'ls' de dentro no falla, es dir
    if "$AMPY_BIN" --port "$PORT" ls "$full" >/dev/null 2>&1; then
      borrar_rec "$full"
      "$AMPY_BIN" --port "$PORT" rmdir "$full" >/dev/null 2>&1 || true
    else
      "$AMPY_BIN" --port "$PORT" rm "$full" >/dev/null 2>&1 || true
    fi
  done <<< "$items"
}

mkdirs_rec() {
  local remote="$1"
  IFS='/' read -ra parts <<< "$remote"
  local cur=""
  for p in "${parts[@]}"; do
    [ -z "$p" ] && continue
    cur="$cur/$p"
    "$AMPY_BIN" --port "$PORT" mkdir "$cur" >/dev/null 2>&1 || true
  done
}

should_skip() {
  local path="$1"
  # directorios
  for d in "${EXCLUDE_DIRS[@]}"; do
    [[ "$path" == ./$d/* ]] && return 0
    [[ "$path" == ./$d ]] && return 0
  done
  # patrones de archivo
  for f in "${EXCLUDE_FILES[@]}"; do
    [[ "$path" == $f ]] && return 0
    [[ "$path" == ./$f ]] && return 0
  done
  return 1
}

tree_remote() {
  local base="$1" indent="${2:-}"
  local items
  items="$("$AMPY_BIN" --port "$PORT" ls "$base" 2>/dev/null || true)"
  [ -z "$items" ] && return 0
  while IFS= read -r it; do
    it="${it%$'\r'}"
    [ -z "$it" ] && continue
    local full="${base%/}/$it"
    if "$AMPY_BIN" --port "$PORT" ls "$full" >/dev/null 2>&1; then
      echo "${indent}${it}/"
      tree_remote "$full" "  $indent"
    else
      echo "${indent}${it}"
    fi
  done <<< "$items"
}

echo "Borrando remoto (excepto /boot.py)…"
borrar_rec "/"

echo "Subiendo .py filtrados a $PORT"
# Sube .py del raíz
if [ -f "./main.py" ]; then
  echo "  + ./main.py"
  "$AMPY_BIN" --port "$PORT" put "./main.py" "/main.py"
fi
# Sube recursivo solo .py respetando exclusiones
while IFS= read -r f; do
  should_skip "$f" && continue
  remote="/${f#./}"
  remote_dir="$(dirname "$remote")"
  mkdirs_rec "$remote_dir"
  echo "  + $f"
  "$AMPY_BIN" --port "$PORT" put "$f" "$remote" || echo "    ! Error subiendo $f"
done < <(find . -type f -name '*.py' | sort)

echo -e "\nContenido en el ESP32:\n====================="
tree_remote "/"
echo "====================="
echo -e "Listo. Ejecuta con:\nampy --port $PORT run main.py"
