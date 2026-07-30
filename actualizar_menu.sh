#!/usr/bin/env bash
# actualizar_menu.sh — parsea dietas y genera menú, recetas, compras y meal prep
# Uso: bash actualizar_menu.sh [--sin-parsear]
#
# NOTA DE SEMANA: crea un archivo nota_semana.txt en esta carpeta con tus
# indicaciones especiales antes de ejecutar (sobras, tiempo libre, equipo, etc.).
# Se aplica automáticamente y se archiva en data/notas_semana/ al terminar.
set -euo pipefail

cd "$(dirname "$0")"
source venv/bin/activate

SIN_PARSEAR=false
for arg in "$@"; do
  case "$arg" in
    --sin-parsear) SIN_PARSEAR=true ;;
  esac
done

# ── Nota de semana ─────────────────────────────────────────────────────────────
NOTA_ARGS=()
if [[ -f "nota_semana.txt" ]]; then
  NOTA_CONTENT=$(cat nota_semana.txt)
  if [[ -n "$NOTA_CONTENT" ]]; then
    NOTA_ARGS=(--nota "$NOTA_CONTENT")
  fi
fi

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

# Recoge ratings_*.json / weights.json de la carpeta de Descargas del sistema
# hacia data/ratings/, y consolida duplicados (ahí o ya en data/ratings/).
# El navegador numera las descargas repetidas del mismo nombre como
# "archivo (1).json", "archivo (2).json", ... — el número más alto es
# siempre la descarga más reciente, así que ese es el criterio principal
# para decidir cuál copia gana (la fecha de modificación solo desempata
# cuando dos candidatos tienen el mismo número, p. ej. ninguno tiene sufijo).
# Devuelve cuántos archivos nuevos o actualizados quedaron en data/ratings/.
_recoger_de_descargas() {
  mkdir -p data/ratings

  local dl_dir=""
  for d in "$HOME/Descargas" "$HOME/Downloads"; do
    [ -d "$d" ] && dl_dir="$d" && break
  done

  local candidates=()
  shopt -s nullglob
  candidates+=(data/ratings/ratings_*.json)
  if [ -n "$dl_dir" ]; then
    candidates+=("$dl_dir"/ratings_*.json)
    [ -f "$dl_dir/weights.json" ] && candidates+=("$dl_dir/weights.json")
  fi
  shopt -u nullglob
  [ "${#candidates[@]}" -eq 0 ] && { echo "0"; return; }

  local -A best_path best_rank best_mtime clean_of
  local f base clean rank mtime key
  for f in "${candidates[@]}"; do
    base="$(basename "$f")"
    if [[ "$base" =~ ^(.*)\ ?\(([0-9]+)\)(\.json)$ ]]; then
      clean="${BASH_REMATCH[1]}${BASH_REMATCH[3]}"
      rank="${BASH_REMATCH[2]}"
    else
      clean="$base"
      rank=0
    fi
    clean_of["$f"]="$clean"
    mtime="$(stat -c '%Y' "$f" 2>/dev/null || echo 0)"
    key="$clean"
    if [ -z "${best_rank[$key]+x}" ] \
       || [ "$rank" -gt "${best_rank[$key]}" ] \
       || { [ "$rank" -eq "${best_rank[$key]}" ] && [ "$mtime" -gt "${best_mtime[$key]}" ]; }; then
      best_rank[$key]="$rank"
      best_mtime[$key]="$mtime"
      best_path[$key]="$f"
    fi
  done

  local count=0
  for key in "${!best_path[@]}"; do
    local dest="data/ratings/$key" winner="${best_path[$key]}"
    if [ "$winner" != "$dest" ]; then
      cp -f "$winner" "$dest"
      count=$((count+1))
      echo "  📥 $key" >&2
    fi
  done

  # Limpieza: borrar todo candidato que no sea ya el archivo canónico en
  # data/ratings/ (copias perdedoras y los originales recién copiados desde
  # Descargas — el contenido ganador ya quedó en data/ratings/$key).
  for f in "${candidates[@]}"; do
    [ "$f" = "data/ratings/${clean_of[$f]}" ] && continue
    rm -f "$f"
  done

  echo "$count"
}

# ── Cabecera ───────────────────────────────────────────────────────────────────
T_GLOBAL=$(_now_s)
echo ""
echo "════════════════════════════════════════════════"
echo "  🥗  Asistente Nutricional — Menú + Compras"
echo "  $(date '+%A %d/%m/%Y %H:%M')"
echo "════════════════════════════════════════════════"
echo ""
if [[ ${#NOTA_ARGS[@]} -gt 0 ]]; then
  echo "  📋 Nota de semana detectada (nota_semana.txt):"
  # Show first 120 chars of the note
  NOTA_PREVIEW="${NOTA_CONTENT:0:120}"
  [[ ${#NOTA_CONTENT} -gt 120 ]] && NOTA_PREVIEW="${NOTA_PREVIEW}…"
  echo "     ${NOTA_PREVIEW}"
  echo ""
else
  echo "  💡 Sin nota_semana.txt — menú estándar. Para personalizar:"
  echo "     echo 'Tengo poco tiempo, sobras de X, prefiero más sous vide' > nota_semana.txt"
  echo ""
fi

# ── 1. Parsear PDFs del nutriólogo ────────────────────────────────────────────
T_STEP=$(_now_s)
if [ "$SIN_PARSEAR" = false ]; then
  PDF_COUNT=$(find Dietas/ -maxdepth 1 -name "*.pdf" 2>/dev/null | wc -l)
  if [ "$PDF_COUNT" -gt 0 ]; then
    echo "▶ [1/5] Parseando dietas ($PDF_COUNT PDF encontrados)..."
    python main.py parsear-dietas
    _record_step "1. Parsear dietas" "$(_elapsed $T_STEP)" "✅"
  else
    echo "⚠  [1/5] Sin PDFs en Dietas/ — saltando parseo."
    _record_step "1. Parsear dietas" "—" "⏭"
  fi
else
  echo "⏭  [1/5] Parseo omitido (--sin-parsear)."
  _record_step "1. Parsear dietas" "—" "⏭"
fi
echo ""

# ── 2. Recoger valoraciones descargadas del navegador ─────────────────────────
T_STEP=$(_now_s)
echo "▶ [2/5] Buscando valoraciones en la carpeta de Descargas..."
COLLECTED=$(_recoger_de_descargas)
if [ "$COLLECTED" -gt 0 ]; then
  _record_step "2. Recoger de Descargas" "$(_elapsed $T_STEP)" "✅"
else
  echo "  ⏭  Nada nuevo en Descargas."
  _record_step "2. Recoger de Descargas" "—" "⏭"
fi
echo ""

# ── 3. Importar valoraciones de semanas anteriores ────────────────────────────
T_STEP=$(_now_s)
RATINGS_COUNT=$(find data/ratings/ -maxdepth 1 -name "ratings_*.json" 2>/dev/null | wc -l)
if [ "$RATINGS_COUNT" -gt 0 ]; then
  echo "▶ [3/5] Importando valoraciones ($RATINGS_COUNT archivo(s) en data/ratings/)..."
  python main.py importar-ratings
  _record_step "3. Importar ratings" "$(_elapsed $T_STEP)" "✅"
else
  echo "⏭  [3/5] Sin valoraciones en data/ratings/ — omitiendo."
  echo "         (Exporta desde el sitio web y coloca el JSON en data/ratings/)"
  _record_step "3. Importar ratings" "—" "⏭"
fi
echo ""

# ── 4. Menú, recetas, compras y meal prep (sin sitio) ─────────────────────────
T_STEP=$(_now_s)
echo "▶ [4/5] Generando semana completa (sin sitio)..."
echo "        menú (+ valoraciones + validación calórica) · recetas · meal prep · compras"
python main.py semana-completa --sin-sitio "${NOTA_ARGS[@]+"${NOTA_ARGS[@]}"}"
_record_step "4. Semana completa" "$(_elapsed $T_STEP)" "✅"
echo ""

# ── 5. Auditar plan de meal prep ──────────────────────────────────────────────
T_STEP=$(_now_s)
echo "▶ [5/5] Auditando plan de meal prep..."
python main.py verificar-prep || true
_record_step "5. Auditar meal prep" "$(_elapsed $T_STEP)" "✅"
echo ""

# ── Archivar nota de semana ────────────────────────────────────────────────────
if [[ ${#NOTA_ARGS[@]} -gt 0 ]]; then
  mkdir -p data/notas_semana
  NOTA_FECHA=$(date +%Y-%m-%d)
  cp nota_semana.txt "data/notas_semana/nota_${NOTA_FECHA}.txt"
  echo "  📁 Nota archivada en data/notas_semana/nota_${NOTA_FECHA}.txt"
  echo "  🗑  Puedes borrar nota_semana.txt cuando quieras (ya fue aplicada)."
  echo ""
fi

# ── Resumen final ─────────────────────────────────────────────────────────────
T_TOTAL_ELAPSED=$(_elapsed $T_GLOBAL)

echo "════════════════════════════════════════════════"
echo "  ✅  Menú + valoraciones listos — resumen de ejecución"
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
echo "  Cuando estés listo, ejecuta:"
echo "    bash actualizar_site.sh"
echo ""
echo "════════════════════════════════════════════════"
echo ""
