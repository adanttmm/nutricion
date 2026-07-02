#!/bin/bash
set -e
echo "🥗 Configurando Asistente Nutricional..."
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
if [ ! -f .env ]; then
    cp .env.example .env
    echo ""
    echo "⚠️  Edita el archivo .env y agrega tu ANTHROPIC_API_KEY:"
    echo "    https://console.anthropic.com/settings/keys"
fi
echo ""
echo "✅ Listo. Activa el entorno con:"
echo "    source venv/bin/activate"
echo ""
echo "Luego ejecuta tu primera semana con:"
echo "    python main.py semana-completa"
