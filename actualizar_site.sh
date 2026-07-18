#!/usr/bin/env bash
# actualizar_site.sh — genera el sitio web y lo publica en GitHub Pages
# Uso: bash actualizar_site.sh [--sin-push]
set -euo pipefail

cd "$(dirname "$0")"
source venv/bin/activate

SIN_PUSH=false
for arg in "$@"; do
  case "$arg" in
    --sin-push) SIN_PUSH=true ;;
  esac
done

# ── Utilidades de tiempo ───────────────────────────────────────────────────────
_now_s() { date +%s; }
_elapsed() {
  local secs=$(( $(_now_s) - $1 ))
  if   [ "$secs" -ge 3600 ]; then printf "%dh %02dm %02ds" $((secs/3600)) $(((secs%3600)/60)) $((secs%60))
  elif [ "$secs" -ge   60 ]; then printf "%dm %02ds" $((secs/60)) $((secs%60))
  else printf "%ds" "$secs"
  fi
}

declare -a STEP_NAMES
declare -a STEP_TIMES
declare -a STEP_ICONS

_record_step() {
  STEP_NAMES+=("$1")
  STEP_TIMES+=("$2")
  STEP_ICONS+=("$3")
}

# ── Cabecera ───────────────────────────────────────────────────────────────────
T_GLOBAL=$(_now_s)
echo ""
echo "════════════════════════════════════════════════"
echo "  🌐  Asistente Nutricional — Publicar Sitio"
echo "  $(date '+%A %d/%m/%Y %H:%M')"
echo "════════════════════════════════════════════════"
echo ""

# ── 1. Importar valoraciones auto-guardadas ────────────────────────────────────
T_STEP=$(_now_s)
echo "▶ [1/3] Importando valoraciones desde data/ratings/..."
python main.py importar-ratings
_record_step "1. Importar ratings" "$(_elapsed $T_STEP)" "✅"
echo ""

# ── 2. Generar sitio estático ──────────────────────────────────────────────────
T_STEP=$(_now_s)
echo "▶ [2/3] Generando sitio estático en docs/..."
python main.py generar-sitio
_record_step "2. Generar sitio" "$(_elapsed $T_STEP)" "✅"
echo ""

# ── 3. Publicar en GitHub Pages ────────────────────────────────────────────────
T_STEP=$(_now_s)
if [ "$SIN_PUSH" = false ]; then
  echo "▶ [3/3] Publicando en GitHub Pages..."
  git add docs/
  git add outputs/recipes/ outputs/menus/
  if git diff --cached --quiet; then
    echo "  Sin cambios — nada que publicar."
    _record_step "2. Publicar (git push)" "—" "⏭"
  else
    git commit -m "actualizar semana $(date +%Y-%m-%d)"
    git push origin master
    echo ""
    echo "✅ Publicado — https://adanttmm.github.io/nutricion/"
    _record_step "3. Publicar (git push)" "$(_elapsed $T_STEP)" "✅"
  fi
else
  echo "⏭  [3/3] Push omitido (--sin-push)."
  _record_step "3. Publicar (git push)" "—" "⏭"
fi
echo ""

# ── Resumen final ─────────────────────────────────────────────────────────────
T_TOTAL_ELAPSED=$(_elapsed $T_GLOBAL)

echo "════════════════════════════════════════════════"
echo "  ✅  Sitio listo — resumen de ejecución"
echo "════════════════════════════════════════════════"
echo ""
echo "  ⏱  Tiempos por paso:"
echo "  ┌────────────────────────────────────┬──────────────┐"
printf "  │ %-34s │ %-12s │\n" "Paso" "Duración"
echo "  ├────────────────────────────────────┼──────────────┤"
for i in "${!STEP_NAMES[@]}"; do
  printf "  │ %s %-32s │ %-12s │\n" "${STEP_ICONS[$i]}" "${STEP_NAMES[$i]}" "${STEP_TIMES[$i]}"
done
echo "  ├────────────────────────────────────┼──────────────┤"
printf "  │ %-34s │ %-12s │\n" "TOTAL" "$T_TOTAL_ELAPSED"
echo "  └────────────────────────────────────┴──────────────┘"
echo ""
echo "════════════════════════════════════════════════"
echo ""
