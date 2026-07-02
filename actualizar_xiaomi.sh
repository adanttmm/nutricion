#!/usr/bin/env bash
# actualizar_xiaomi.sh — descarga composición corporal desde Mi Fitness cloud
# sin Docker, usando el cliente Python nativo.
#
# Uso:
#   bash actualizar_xiaomi.sh              # ATM y IOB
#   bash actualizar_xiaomi.sh --atm        # solo ATM
#   bash actualizar_xiaomi.sh --iob        # solo IOB
#   bash actualizar_xiaomi.sh --dry-run    # muestra datos sin guardar
#   bash actualizar_xiaomi.sh --region cn  # forzar región
#
# Variables requeridas en .env:
#   XIAOMI_EMAIL      correo de la cuenta Xiaomi Home
#   XIAOMI_PASSWORD   contraseña
#   XIAOMI_REGION     cn | us | eu | sg  (default: cn)
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -f .env ]]; then
  echo "❌  Falta .env con credenciales Xiaomi." >&2; exit 1
fi
source .env
source venv/bin/activate

DRY_RUN=""
REGION_OVERRIDE=""
PERSONAS=()

for arg in "$@"; do
  case "$arg" in
    --atm)     PERSONAS=("ATM") ;;
    --iob)     PERSONAS=("IOB") ;;
    --dry-run) DRY_RUN="--dry-run" ;;
    --region)  shift; REGION_OVERRIDE="--region $1" ;;
    --region=*) REGION_OVERRIDE="--region ${arg#--region=}" ;;
  esac
done
[[ ${#PERSONAS[@]} -eq 0 ]] && PERSONAS=("ATM" "IOB")

echo ""
echo "════════════════════════════════════════════════"
echo "  ⚖️   Xiaomi Mi Fitness — Composición Corporal"
echo "  $(date '+%A %d/%m/%Y %H:%M')"
echo "════════════════════════════════════════════════"
echo ""

for persona in "${PERSONAS[@]}"; do
  echo "▶ Sincronizando $persona..."
  python main.py sincronizar-xiaomi \
    --persona "$persona" \
    ${REGION_OVERRIDE} \
    ${DRY_RUN}
  echo ""
done

echo "✅  Sincronización completada."
[[ -z "$DRY_RUN" ]] && echo "   Ejecuta 'bash actualizar_site.sh' para publicar los cambios."
echo ""
