#!/bin/bash

# Verificar si se pasó el puerto
if [ -z "$1" ]; then
    echo "Uso: $0 <PUERTO_SERIAL>"
    exit 1
fi

PORT="$1"

# Verificar si ampy está instalado
if ! command -v ampy &> /dev/null; then
    echo "El comando 'ampy' no está instalado."
    exit 1
fi

# Subir todos los archivos .py del proyecto
echo "📤 Subiendo archivos .py al ESP32..."
find . -type f -name "*.py" | while read file; do
    remote_path="${file#./}"
    echo "➡ Subiendo $remote_path"
    ampy --port "$PORT" put "$file" "$remote_path"
done

# Confirmar subida
echo "✅ Archivos subidos. Contenido actual del microcontrolador:"
ampy --port "$PORT" ls
