\#!/bin/bash

# -----------------------------------------------------------------------------

# @file upload.sh

# @brief Script Bash para cargar automáticamente archivos .py a un dispositivo

# MicroPython/ESP32 mediante **adafruit‑ampy**.

#

# El script realiza estas tareas:

# 1. Verifica que `ampy` esté instalado en el sistema.

# 2. Comprueba que se haya proporcionado el puerto serie.

# 3. Elimina recursivamente todo el contenido existente en el sistema de

# archivos del dispositivo (excepto *boot.py*).

# 4. Sube todos los archivos *.py* presentes en el directorio actual y sus

# sub‑carpetas, creando la jerarquía remota necesaria.

# 5. Muestra al final un árbol de archivos resultante.

#

# @usage

# ./upload.sh \<PUERTO\_SERIAL>

# @example

# ./upload.sh /dev/ttyUSB0

#

# @dependencies adafruit‑ampy ≥ 1.1.0 (pip install adafruit‑ampy)

# @author Alejandro Fernández Rodríguez

# @contact github.com/afernandezLuc

# @version 1.0.0

# @date 2025‑08‑02

# @license MIT

# -----------------------------------------------------------------------------

if ! command -v ampy &> /dev/null; then
echo "El comando 'ampy' no está instalado."
echo "Puedes instalarlo con pip ejecutando:"
echo "pip install adafruit-ampy"
exit 1
fi

if \[ -z "\$1" ]; then
echo "Uso: \$0 \<PUERTO\_SERIAL>"
echo "Ejemplo: \$0 /dev/tty.usbserial-0001"
exit 1
fi

PORT="\$1"

function borrar\_remoto\_recursivo() {
local path="\$1"
local archivos
archivos=\$(ampy --port "\$PORT" ls "\$path" 2>/dev/null)

if \[ -z "\$archivos" ]; then
return
fi

while read -r archivo; do
archivo=\${archivo//\$'\r'/}
\[ -z "\$archivo" ] && continue
full\_path="\$path/\$archivo"
\# No borrar boot.py
if \[\[ "\$full\_path" == "/boot.py" ]]; then
continue
fi
if ampy --port "\$PORT" ls "\$full\_path" &>/dev/null; then
borrar\_remoto\_recursivo "\$full\_path"
ampy --port "\$PORT" rmdir "\$full\_path" 2>/dev/null
else
ampy --port "\$PORT" rm "\$full\_path" 2>/dev/null
fi
done <<< "\$archivos"
}

function listar\_remoto\_recursivo() {
local path="\$1"
local prefix="\$2"
local archivos
archivos=\$(ampy --port "\$PORT" ls "\$path" 2>/dev/null)

if \[ -z "\$archivos" ]; then
return
fi

while read -r item; do
item=\$(echo "\$item" | tr -d '\r')
\[ -z "\$item" ] && continue
full\_path="\${path}/\${item}"
if ampy --port "\$PORT" ls "\$full\_path" &>/dev/null; then
echo "\${prefix}\${item}/"
listar\_remoto\_recursivo "\$full\_path" "  \$prefix"
else
echo "\${prefix}\${item}"
fi
done <<< "\$archivos"
}

echo "Borrando archivos remotos existentes..."
borrar\_remoto\_recursivo "/"

echo "Iniciando carga a \$PORT"
echo "============================"
find . -type f -name "\*.py" | while read -r LOCAL\_FILE; do
REMOTE\_PATH="/\$LOCAL\_FILE"
REMOTE\_DIR=\$(dirname "\$REMOTE\_PATH")

echo "Verificando carpeta remota: \$REMOTE\_DIR"
IFS='/' read -ra PARTS <<< "\$REMOTE\_DIR"
CURRENT=""
for part in "\${PARTS\[@]}"; do
\[ -z "\$part" ] && continue
CURRENT="\$CURRENT/\$part"
ampy --port "\$PORT" mkdir "\$CURRENT" 2>/dev/null
done

echo -n "Subiendo \$LOCAL\_FILE ... "
ampy --port "\$PORT" put "\$LOCAL\_FILE" "\$REMOTE\_PATH" && echo "Ok" || echo "Error"
done

echo -e "\nListando archivos en el ESP32:"
echo "============================"
listar\_remoto\_recursivo "" ""
echo "============================"

echo -e "\nCarga finalizada. Puedes ejecutar el programa con:\nampy --port \$PORT run main.py"
