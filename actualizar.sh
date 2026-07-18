#!/usr/bin/env bash
# actualizar.sh — flujo completo semanal (menú → sitio)
# Uso: bash actualizar.sh [--sin-parsear] [--sin-push]
#
# NOTA DE SEMANA: crea nota_semana.txt antes de ejecutar para personalizar el menú:
#   echo "Esta semana tengo poco tiempo. Tengo sobras de pollo y arroz del lunes pasado.
#   Prefiero más platillos sous vide entre semana." > nota_semana.txt
#
# Para ejecutar por pasos:
#   bash actualizar_menu.sh  [--sin-parsear]  ← genera menú, compras y meal prep
#   bash actualizar_site.sh  [--sin-push]     ← construye sitio y publica en GitHub
set -euo pipefail

cd "$(dirname "$0")"

MENU_ARGS=()
SITE_ARGS=()

for arg in "$@"; do
  case "$arg" in
    --sin-parsear) MENU_ARGS+=("--sin-parsear") ;;
    --sin-push)    SITE_ARGS+=("--sin-push") ;;
  esac
done

bash actualizar_menu.sh "${MENU_ARGS[@]+"${MENU_ARGS[@]}"}"
bash actualizar_site.sh "${SITE_ARGS[@]+"${SITE_ARGS[@]}"}"
