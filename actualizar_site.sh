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
    if [[ "$base" =~ ^(.*)\ \(([0-9]+)\)\.json$ ]]; then
      clean="${BASH_REMATCH[1]}.json"
      rank="${BASH_REMATCH[2]}"
    elif [[ "$base" =~ ^(.*)\(([0-9]+)\)\.json$ ]]; then
      clean="${BASH_REMATCH[1]}.json"
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
echo "  🌐  Asistente Nutricional — Publicar Sitio"
echo "  $(date '+%A %d/%m/%Y %H:%M')"
echo "════════════════════════════════════════════════"
echo ""

# ── 1. Traer valoraciones sincronizadas por el Worker de Cloudflare ────────────
T_STEP=$(_now_s)
echo "▶ [1/5] Trayendo cambios de GitHub (ratings sincronizados desde el sitio)..."
if git pull --ff-only origin master 2>/tmp/_git_pull_err; then
  _record_step "1. Git pull" "$(_elapsed $T_STEP)" "✅"
else
  echo "  ⚠  git pull falló (revisa cambios locales sin commitear) — continuando de todas formas:"
  sed 's/^/    /' /tmp/_git_pull_err
  _record_step "1. Git pull" "—" "⚠️"
fi
rm -f /tmp/_git_pull_err
echo ""

# ── 2. Recoger valoraciones descargadas del navegador ──────────────────────────
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

# ── 3. Importar valoraciones auto-guardadas ────────────────────────────────────
T_STEP=$(_now_s)
echo "▶ [3/5] Importando valoraciones desde data/ratings/..."
python main.py importar-ratings
_record_step "3. Importar ratings" "$(_elapsed $T_STEP)" "✅"
echo ""

# ── 4. Generar sitio estático ──────────────────────────────────────────────────
T_STEP=$(_now_s)
echo "▶ [4/5] Generando sitio estático en docs/..."
python main.py generar-sitio
_record_step "4. Generar sitio" "$(_elapsed $T_STEP)" "✅"
echo ""

# ── 5. Publicar en GitHub Pages ────────────────────────────────────────────────
T_STEP=$(_now_s)
if [ "$SIN_PUSH" = false ]; then
  echo "▶ [5/5] Publicando en GitHub Pages..."
  git add docs/
  git add outputs/recipes/ outputs/menus/
  if git diff --cached --quiet; then
    echo "  Sin cambios — nada que publicar."
    _record_step "5. Publicar (git push)" "—" "⏭"
  else
    git commit -m "actualizar semana $(date +%Y-%m-%d)"
    git push origin master
    echo ""
    echo "✅ Publicado — https://adanttmm.github.io/nutricion/"
    _record_step "5. Publicar (git push)" "$(_elapsed $T_STEP)" "✅"
  fi
else
  echo "⏭  [5/5] Push omitido (--sin-push)."
  _record_step "5. Publicar (git push)" "—" "⏭"
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
