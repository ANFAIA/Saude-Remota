#!/bin/bash

if ! command -v ampy &> /dev/null; then
  echo "El comando 'ampy' no está instalado."
  echo "Puedes instalarlo con pip ejecutando:"
  echo "pip install adafruit-ampy"
  exit 1
fi

if [ -z "$1" ]; then
  echo "Uso: $0 <PUERTO_SERIAL>"
  echo "Ejemplo: $0 /dev/tty.usbserial-0001"
  exit 1
fi

PORT="$1"

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
    # No borrar boot.py
    if [[ "$full_path" == "/boot.py" ]]; then
      continue
    fi
    if ampy --port "$PORT" ls "$full_path" &>/dev/null; then
      borrar_remoto_recursivo "$full_path"
      ampy --port "$PORT" rmdir "$full_path" 2>/dev/null
    else
      ampy --port "$PORT" rm "$full_path" 2>/dev/null
    fi
  done <<< "$archivos"
}

function listar_remoto_recursivo() {
  local path="$1"
  local prefix="$2"
  local archivos
  archivos=$(ampy --port "$PORT" ls "$path" 2>/dev/null)

  if [ -z "$archivos" ]; then
    return
  fi

  while read -r item; do
    item=$(echo "$item" | tr -d '\r')
    [ -z "$item" ] && continue
    full_path="${path}/${item}"
    if ampy --port "$PORT" ls "$full_path" &>/dev/null; then
      echo "${prefix}${item}/"
      listar_remoto_recursivo "$full_path" "  $prefix"
    else
      echo "${prefix}${item}"
    fi
  done <<< "$archivos"
}

echo "Borrando archivos remotos existentes..."
borrar_remoto_recursivo "/"

echo "Iniciando carga a $PORT"
echo "============================"
find . -type f -name "*.py" | while read -r LOCAL_FILE; do
  REMOTE_PATH="/$LOCAL_FILE"
  REMOTE_DIR=$(dirname "$REMOTE_PATH")

  echo "Verificando carpeta remota: $REMOTE_DIR"
  IFS='/' read -ra PARTS <<< "$REMOTE_DIR"
  CURRENT=""
  for part in "${PARTS[@]}"; do
    [ -z "$part" ] && continue
    CURRENT="$CURRENT/$part"
    ampy --port "$PORT" mkdir "$CURRENT" 2>/dev/null
  done

  echo -n "Subiendo $LOCAL_FILE ... "
  ampy --port "$PORT" put "$LOCAL_FILE" "$REMOTE_PATH" && echo "Ok" || echo "Error"
done

echo -e "\nListando archivos en el ESP32:"
echo "============================"
listar_remoto_recursivo "" ""
echo "============================"

echo -e "\nCarga finalizada. Puedes ejecutar el programa con:\nampy --port $PORT run main.py"
