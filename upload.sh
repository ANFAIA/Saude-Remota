#!/bin/bash
set -euo pipefail

# ========= Config =========
BAUD=115200
DELAY=${AMPY_DELAY:-2}    # más estable con 2s
PORT_ARG="${1:-}"

# Usar ampy como módulo (evita pipx)
AMPY() { python3 -m ampy.cli --baud "$BAUD" --delay "$DELAY" --port "$PORT" "$@"; }

# ---- Detectar puerto si no se pasa ----
detectar_puerto() {
  for p in /dev/ttyUSB* /dev/ttyACM*; do
    [ -e "$p" ] && echo "$p" && return 0
  done
  return 1
}

if [ -n "$PORT_ARG" ]; then
  PORT="$PORT_ARG"
else
  PORT="$(detectar_puerto || true)"
  [ -z "${PORT:-}" ] && { echo "❌ No encuentro puerto. Conecta el ESP32 o pasa /dev/ttyUSB0"; exit 1; }
fi

# ---- Comprobar que el puerto no está ocupado ----
if lsof "$PORT" >/dev/null 2>&1; then
  echo "❌ $PORT está en uso. Cierra Thonny/screen/etc."
  lsof "$PORT" || true
  exit 1
fi

echo "🔌 Puerto: $PORT  | baud=$BAUD  | delay=${DELAY}s"

# ---- Probar conexión (sin tracebacks feos) ----
if ! AMPY ls >/dev/null 2>&1; then
  echo "❌ No puedo hablar con el ESP32 en $PORT. Pulsa RST y reintenta."
  exit 1
fi
echo "✅ Conexión OK"

# ========= Borrar (excepto boot.py) =========
echo "[1/4] Limpiando dispositivo (excepto boot.py)…"
borrar_rec() {
  local path="$1"
  local entries
  entries="$(AMPY ls "$path" 2>/dev/null || true)"
  [ -z "$entries" ] && return 0
  while read -r e; do
    [ -z "$e" ] && continue
    e="${e//$'\r'/}"
    local full="${path:+$path/}$e"
    if [[ "$e" == "boot.py" ]]; then continue; fi
    # intentar como dir, si falla, como archivo
    AMPY rmdir "$full" >/dev/null 2>&1 || AMPY rm "$full" >/dev/null 2>&1 || {
      borrar_rec "$full"
      AMPY rmdir "$full" >/dev/null 2>&1 || true
    }
  done <<<"$entries"
}
borrar_rec ""

# ========= Subir archivos =========
mkpath_remote() {
  local dir="$1"
  IFS='/' read -r -a parts <<<"$dir"
  local acc=""
  for part in "${parts[@]}"; do
    [ -z "$part" ] && continue
    acc="$acc/$part"
    AMPY mkdir "$acc" >/dev/null 2>&1 || true
  done
}

put_file() {
  local src="$1"
  local dst="${src#./}"
  local dir="$(dirname "$dst")"
  [ "$dir" != "." ] && mkpath_remote "/$dir"
  echo "⬆️  $dst"
  AMPY put "$src" "/$dst"
  sleep 0.3
}

echo "[2/4] Subiendo .py…"
while IFS= read -r -d '' f; do put_file "$f"; done < <(find . -type f -name "*.py" -print0)

echo "[3/4] Subiendo modelo (JSON)…"
for f in ./lib/predictionModel/modeloIA/pesos.json ./lib/predictionModel/modeloIA/escala.json; do
  if [ -f "$f" ]; then put_file "$f"; else echo "⚠️  Falta $f"; fi
done

echo "[4/4] Listado final:"
AMPY ls -r || true

echo "🔁 Reset suave…"
AMPY reset || true
echo "✅ Hecho."
