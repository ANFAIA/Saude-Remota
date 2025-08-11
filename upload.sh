#!/bin/bash
set -euo pipefail

# ================================
#  Subida fiable de .py al ESP32
# ================================

# --- Config ---
DELAY="${AMPY_DELAY:-1}"      # segundos de delay para ampy (subidas más estables)
PAUSA="0.4"                   # pausa entre subidas
PORT_ARG="${1:-}"             # puerto opcional por argumento

# --- Dependencias ---
if ! command -v ampy >/dev/null 2>&1; then
  echo "❌ 'ampy' no está instalado. Instálalo con:  pipx install adafruit-ampy"
  exit 1
fi

# --- Detectar puerto si no se proporciona ---
detectar_puerto() {
  # Intentar USB primero, luego ACM
  for p in /dev/ttyUSB* /dev/ttyACM*; do
    [ -e "$p" ] && echo "$p" && return 0
  done
  return 1
}

if [ -n "$PORT_ARG" ]; then
  PORT="$PORT_ARG"
else
  PORT="$(detectar_puerto || true)"
  if [ -z "${PORT:-}" ]; then
    echo "❌ No se encontró puerto serie. Conecta el ESP32 y prueba: ls /dev/ttyUSB* /dev/ttyACM*"
    echo "   También puedes ejecutar: $0 /dev/ttyUSB0"
    exit 1
  fi
fi

echo "🔌 Usando puerto: $PORT  (delay=${DELAY}s)"

# --- Comprobar que nadie esté usando el puerto (p.ej. Thonny) ---
if lsof "$PORT" >/dev/null 2>&1; then
  echo "❌ El puerto $PORT está en uso por otro proceso. Cierra Thonny/Arduino/REPL y vuelve a intentar."
  lsof "$PORT" || true
  exit 1
fi

# --- Función para crear directorio remoto (anidado) ---
mkpath_remote() {
  local dir="$1"
  [ -z "$dir" ] && return 0
  IFS='/' read -r -a parts <<< "$dir"
  local path=""
  for part in "${parts[@]}"; do
    [ -z "$part" ] && continue
    path="$path/$part"
    # ignorar error si ya existe
    ampy --delay "$DELAY" --port "$PORT" mkdir "$path" >/dev/null 2>&1 || true
    sleep "$PAUSA"
  done
}

# --- Subir un archivo asegurando su directorio ---
put_file() {
  local src="$1"
  local dst="${src#./}"           # quitar ./ inicial
  local dir
  dir="$(dirname "$dst")"
  [ "$dir" = "." ] && dir=""      # raíz
  if [ -n "$dir" ]; then
    mkpath_remote "$dir"
  fi
  echo "➡  $dst"
  ampy --delay "$DELAY" --port "$PORT" put "$src" "$dst"
  sleep "$PAUSA"
}

# --- Lista de archivos a subir (orden sugerido) ---
# 1) configuracion.py si existe (con tus claves)
ARCHIVOS=()
[ -f "./configuracion.py" ] && ARCHIVOS+=("./configuracion.py")

# 2) librerías primero (para que main.py encuentre imports)
while IFS= read -r f; do ARCHIVOS+=("$f"); done < <(find ./lib -type f -name "*.py" 2>/dev/null | sort)

# 3) el resto de .py excepto main.py y configuracion.py
while IFS= read -r f; do
  [[ "$f" == "./main.py" ]] && continue
  [[ "$f" == "./configuracion.py" ]] && continue
  ARCHIVOS+=("$f")
done < <(find . -maxdepth 1 -type f -name "*.py" | sort)

# 4) main.py al final
[ -f "./main.py" ] && ARCHIVOS+=("./main.py")

# --- Resumen ---
echo "📤 Subiendo archivos al ESP32..."
for f in "${ARCHIVOS[@]}"; do
  put_file "$f"
done

echo "🔁 Reset suave del micro (opcional)…"
ampy --delay "$DELAY" --port "$PORT" reset || true

echo "✅ Hecho. Estructura en el dispositivo:"
ampy --delay "$DELAY" --port "$PORT" ls || true
