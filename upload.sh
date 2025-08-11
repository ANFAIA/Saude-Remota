#!/bin/bash
set -euo pipefail

# =========================
# upload.sh — seguro y auto-instalador de ampy
# =========================

BAUD=115200
DELAY=${AMPY_DELAY:-2}
PORT_ARG="${1:-}"

# Función para ejecutar ampy con Python3 directamente
AMPY() { python3 -m ampy.cli --baud "$BAUD" --delay "$DELAY" --port "$PORT" "$@"; }

# ==== 0. Comprobar que ampy esté instalado ====
if ! python3 -c "import ampy" >/dev/null 2>&1; then
    echo "📦 Instalando adafruit-ampy..."
    python3 -m pip install --user adafruit-ampy
    echo "✅ ampy instalado."
fi

# ==== 1. Detectar puerto ====
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
    [ -z "${PORT:-}" ] && { echo "❌ No se encontró puerto. Conecta el ESP32 o pasa /dev/ttyUSB0"; exit 1; }
fi

# ==== 2. Comprobar que el puerto no esté ocupado ====
if lsof "$PORT" >/dev/null 2>&1; then
    echo "❌ El puerto $PORT está en uso. Cierra Thonny/screen/etc."
    lsof "$PORT" || true
    exit 1
fi

echo "🔌 Puerto: $PORT  | baud=$BAUD  | delay=${DELAY}s"

# ==== 3. Probar conexión ====
if ! AMPY ls >/dev/null 2>&1; then
    echo "❌ No puedo hablar con el ESP32 en $PORT. Pulsa RST y reintenta."
    exit 1
fi
echo "✅ Conexión OK"

# ==== 4. Borrar archivos excepto boot.py ====
echo "[1/4] Borrando archivos del ESP32..."
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
        AMPY rmdir "$full" >/dev/null 2>&1 || AMPY rm "$full" >/dev/null 2>&1 || {
            borrar_rec "$full"
            AMPY rmdir "$full" >/dev/null 2>&1 || true
        }
    done <<<"$entries"
}
borrar_rec ""

# ==== 5. Crear carpetas remotas si no existen ====
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

# ==== 6. Subir un archivo ====
put_file() {
    local src="$1"
    local dst="${src#./}"
    local dir="$(dirname "$dst")"
    [ "$dir" != "." ] && mkpath_remote "/$dir"
    echo "⬆️  $dst"
    AMPY put "$src" "/$dst"
    sleep 0.3
}

# ==== 7. Subir .py ====
echo "[2/4] Subiendo .py..."
while IFS= read -r -d '' f; do put_file "$f"; done < <(find . -type f -name "*.py" -print0)

# ==== 8. Subir JSON del modelo ====
echo "[3/4] Subiendo modelo (.json)..."
for f in ./lib/predictionModel/modeloIA/pesos.json ./lib/predictionModel/modeloIA/escala.json; do
    if [ -f "$f" ]; then put_file "$f"; else echo "⚠️  Falta $f"; fi
done

# ==== 9. Listar archivos en el ESP32 ====
echo "[4/4] Archivos en el ESP32:"
AMPY ls -r || true

# ==== 10. Reset suave ====
echo "🔁 Reset suave..."
AMPY reset || true
echo "✅ Subida completa."
