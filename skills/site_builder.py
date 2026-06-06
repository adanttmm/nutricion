import json
import re
from pathlib import Path
from datetime import date, timedelta
import yaml

from .base_skill import BaseSkill

_DAY_RE = re.compile(
    r'^#{1,2} [^a-zA-Z\n]{0,10}(LUNES|MARTES|MI[ÉE]RCOLES|JUEVES|VIERNES|S[ÁA]BADO|DOMINGO)',
    re.MULTILINE | re.IGNORECASE,
)
_DAY_SHORT = {
    'LUNES': 'Lun', 'MARTES': 'Mar', 'MIÉRCOLES': 'Mié', 'MIERCOLES': 'Mié',
    'JUEVES': 'Jue', 'VIERNES': 'Vie', 'SÁBADO': 'Sáb', 'SABADO': 'Sáb', 'DOMINGO': 'Dom',
}


class SiteBuilderSkill(BaseSkill):

    def build(self, week_date: date = None) -> Path:
        if week_date is None:
            week_date = date.today()

        docs_dir = Path("docs")
        docs_dir.mkdir(exist_ok=True)
        (docs_dir / ".nojekyll").touch()

        diet_plan   = self._load_latest_diet_plan()
        menu_md     = self._load_latest("outputs/menus",     "menu_*.md")
        shopping_md = self._load_latest("outputs/shopping",  "compras_*.md")
        recipes_md  = self._load_latest("outputs/recipes",   "recetas_*.md")
        prep_md     = self._load_latest("outputs/meal_prep", "meal_prep_*.md")
        tracking    = self._export_tracking()
        costco_md, city_md = self._split_shopping(shopping_md)
        days_data   = self._split_by_days(menu_md, recipes_md)

        plan_name    = diet_plan.get("plan_name") or f"Plan Nutricional — {week_date.strftime('%d/%m/%Y')}"
        nutritionist = diet_plan.get("nutritionist") or ""
        nut_line     = f'<p class="text-xs text-gray-400">{nutritionist}</p>' if nutritionist else ""

        html = (
            self._HTML
            .replace("__PLAN_NAME__",  plan_name)
            .replace("__NUT_LINE__",   nut_line)
            .replace("__WEEK_LABEL__", week_date.strftime("%d de %B de %Y"))
            .replace("__PERSONS__",    json.dumps(self._persons(diet_plan), ensure_ascii=False))
            .replace("__TRACKING__",   json.dumps(tracking, ensure_ascii=False, default=str))
            .replace("__DAYS__",       json.dumps(days_data, ensure_ascii=False))
            .replace("__COSTCO__",     self._js(costco_md))
            .replace("__CITY__",       self._js(city_md))
            .replace("__PREP__",       self._js(prep_md))
            .replace("__WEEK_KEY__",   week_date.strftime("%Y%m%d"))
        )

        output = docs_dir / "index.html"
        output.write_text(html, encoding="utf-8")
        return output

    @staticmethod
    def _load_latest_diet_plan() -> dict:
        pd = Path("config/parsed_diets")
        cands = sorted(pd.glob("combined_*.yaml"), reverse=True) if pd.exists() else []
        if not cands:
            cands = sorted(pd.glob("*.yaml"), reverse=True) if pd.exists() else []
        if cands:
            with open(cands[0], encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        try:
            from skills.base_skill import BaseSkill as _B
            return _B()._load_yaml("diet_plan_example.yaml")
        except Exception:
            return {}

    @staticmethod
    def _load_latest(directory: str, pattern: str) -> str:
        p = Path(directory)
        if not p.exists():
            return ""
        files = sorted(p.glob(pattern), reverse=True)
        return files[0].read_text(encoding="utf-8") if files else ""

    @staticmethod
    def _split_shopping(md: str):
        costco, city, cur = [], [], None
        for line in md.split("\n"):
            up = line.upper()
            if line.startswith("#") and "COSTCO" in up:
                cur = costco
            elif line.startswith("#") and "CITY MARKET" in up:
                cur = city
            if cur is not None:
                cur.append(line)
        return "\n".join(costco), "\n".join(city)

    @staticmethod
    def _split_by_days(menu_md: str, recipes_md: str) -> list:
        def sections(text):
            matches = list(_DAY_RE.finditer(text))
            result = []
            for i, m in enumerate(matches):
                end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
                header = m.group(0).strip()
                day_key = next(
                    (k for k in _DAY_SHORT if k in header.upper()),
                    None,
                )
                result.append((day_key, header, text[m.start():end].strip()))
            return result

        menu_secs = sections(menu_md)
        rec_secs  = sections(recipes_md)

        # Append any trailing content after last recipe day section (e.g. "Preparaciones Base")
        if rec_secs and recipes_md:
            last_m = list(_DAY_RE.finditer(recipes_md))
            if last_m:
                trailing = recipes_md[last_m[-1].start():].strip()
                key, hdr, _ = rec_secs[-1]
                rec_secs[-1] = (key, hdr, trailing)

        rec_map = {key: content for key, _, content in rec_secs if key}

        days = []
        for day_key, header, menu_content in menu_secs:
            if not day_key:
                continue
            days.append({
                "key":     day_key.lower().replace("é", "e").replace("á", "a"),
                "short":   _DAY_SHORT.get(day_key, day_key[:3]),
                "name":    header,
                "menu":    menu_content,
                "recipes": rec_map.get(day_key, ""),
            })
        return days

    @staticmethod
    def _persons(diet_plan: dict) -> list:
        if not diet_plan:
            return []
        out = []
        if diet_plan.get("document_type") == "combined_diet_plan":
            for name, data in diet_plan.get("persons", {}).items():
                t = data.get("daily_targets", {})
                out.append({
                    "name": name, "goal": data.get("goal", ""),
                    "calories": t.get("calories", 0),
                    "protein_g": t.get("protein_g", 0),
                    "carbs_g": t.get("carbs_g", 0),
                    "fat_g": t.get("fat_g", 0),
                    "derived": data.get("derived_from_body_composition", False),
                })
        else:
            t = diet_plan.get("daily_targets", {})
            out.append({
                "name": diet_plan.get("person", ""),
                "goal": diet_plan.get("goal", ""),
                "calories": t.get("calories", 0),
                "protein_g": t.get("protein_g", 0),
                "carbs_g": t.get("carbs_g", 0),
                "fat_g": t.get("fat_g", 0),
                "derived": diet_plan.get("derived_from_body_composition", False),
            })
        return out

    def _export_tracking(self) -> dict:
        try:
            from tracker.daily_log import DailyLog
            log = DailyLog()
            today = date.today()
            week_start = today - timedelta(days=today.weekday())
            result = {
                "weekly": log.get_weekly_data(week_start),
                "weight_history": log.get_weight_history(60),
                "today": log.get_daily_summary(today),
            }
            log.close()
            return result
        except Exception:
            return {}

    @staticmethod
    def _js(text: str) -> str:
        return text.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")

    _HTML = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>__PLAN_NAME__</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdn.jsdelivr.net/npm/marked@9/marked.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    .prose table{width:100%;border-collapse:collapse}
    .prose th{background:#f3f4f6;padding:6px 10px;text-align:left;font-weight:600;font-size:.8rem}
    .prose td{padding:6px 10px;border-top:1px solid #f3f4f6;font-size:.82rem}
    .prose h1{font-size:1.25rem;font-weight:700;margin:1.25rem 0 .5rem}
    .prose h2{font-size:1.1rem;font-weight:700;margin:1rem 0 .4rem}
    .prose h3{font-size:.95rem;font-weight:600;margin:.85rem 0 .3rem}
    .prose h4{font-size:.88rem;font-weight:600;margin:.65rem 0 .2rem}
    .prose ul,.prose ol{padding-left:1.4rem;margin:.4rem 0}
    .prose li{margin:.2rem 0;font-size:.87rem;line-height:1.5}
    .prose p{margin:.4rem 0;font-size:.87rem;line-height:1.6}
    .prose strong{font-weight:600}
    .prose em{font-style:italic;color:#6b7280}
    .prose hr{margin:1.25rem 0;border-color:#e5e7eb}
    .prose blockquote{border-left:3px solid #bbf7d0;background:#f0fdf4;padding:.6rem 1rem;margin:.6rem 0;border-radius:.375rem;color:#4b5563;font-size:.85rem}
    .prose code{background:#f3f4f6;padding:.1rem .3rem;border-radius:.2rem;font-size:.78rem}
    .prose input[type=checkbox]{margin-right:6px;cursor:pointer;width:16px;height:16px;vertical-align:middle;accent-color:#059669}
    .tab-btn.active{border-bottom:2px solid #059669;color:#059669;font-weight:600}
    .tab-pane{display:none}.tab-pane.active{display:block}
    .day-btn{transition:all .15s}
    .day-btn.active{background:#059669!important;color:white!important;border-color:#059669!important}
    details>summary{list-style:none}
    details>summary::-webkit-details-marker{display:none}
    details[open]>summary .arrow{transform:rotate(90deg)}
    .arrow{display:inline-block;transition:transform .2s}
    .star-btn{font-size:1.1rem;cursor:pointer;opacity:.3;transition:opacity .1s;line-height:1}
    .star-btn.lit{opacity:1;color:#f59e0b}
    .tag-btn{font-size:.78rem;padding:2px 8px;border-radius:9999px;border:1px solid #e5e7eb;cursor:pointer;background:white;transition:all .15s}
    .tag-btn.active-fav{background:#fee2e2;border-color:#fca5a5}
    .tag-btn.active-rep{background:#d1fae5;border-color:#6ee7b7}
    .tag-btn.active-no{background:#f3f4f6;border-color:#d1d5db;opacity:.7}
    @media(max-width:640px){.prose th,.prose td{padding:4px 6px;font-size:.75rem}}
  </style>
</head>
<body class="bg-gray-50 text-gray-800 min-h-screen">

<header class="bg-white shadow-sm sticky top-0 z-20">
  <div class="max-w-5xl mx-auto px-4 py-3 flex items-center justify-between">
    <div>
      <div class="font-bold text-green-700 text-base">🥗 __PLAN_NAME__</div>
      __NUT_LINE__
    </div>
    <span class="text-xs text-gray-400 shrink-0 ml-3">__WEEK_LABEL__</span>
  </div>
  <div class="max-w-5xl mx-auto px-3 flex overflow-x-auto border-t border-gray-100">
    <button onclick="tab('resumen',this)" class="tab-btn active px-3 py-2.5 text-sm whitespace-nowrap text-gray-600">📊 Resumen</button>
    <button onclick="tab('semana',this)"  class="tab-btn px-3 py-2.5 text-sm whitespace-nowrap text-gray-500">📅 Semana</button>
    <button onclick="tab('compras',this)" class="tab-btn px-3 py-2.5 text-sm whitespace-nowrap text-gray-500">🛒 Compras</button>
    <button onclick="tab('prep',this)"    class="tab-btn px-3 py-2.5 text-sm whitespace-nowrap text-gray-500">🏪 Meal Prep</button>
    <button onclick="tab('tracking',this)"class="tab-btn px-3 py-2.5 text-sm whitespace-nowrap text-gray-500">📈 Seguimiento</button>
  </div>
</header>

<main class="max-w-5xl mx-auto px-4 py-5 space-y-4">

  <!-- Resumen -->
  <div id="tab-resumen" class="tab-pane active space-y-4">
    <div id="person-cards" class="grid grid-cols-1 sm:grid-cols-2 gap-4"></div>
    <div class="bg-white rounded-xl shadow-sm p-5">
      <p class="text-xs font-semibold uppercase tracking-wide text-gray-400 mb-3">Esta semana</p>
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
        <div class="bg-green-50 rounded-xl p-4"><div class="text-3xl font-bold text-green-600">7</div><div class="text-xs text-gray-400 mt-1">días de menú</div></div>
        <div class="bg-blue-50 rounded-xl p-4"><div class="text-3xl font-bold text-blue-600">5</div><div class="text-xs text-gray-400 mt-1">tiempos / día</div></div>
        <div class="bg-orange-50 rounded-xl p-4"><div class="text-3xl font-bold text-orange-600">1</div><div class="text-xs text-gray-400 mt-1">comida trampa</div></div>
        <div class="bg-purple-50 rounded-xl p-4"><div class="text-2xl font-bold text-purple-600">🏪</div><div class="text-xs text-gray-400 mt-1">meal prep dominical</div></div>
      </div>
    </div>
    <div id="fav-section" class="hidden bg-white rounded-xl shadow-sm p-5">
      <p class="text-xs font-semibold uppercase tracking-wide text-gray-400 mb-3">⭐ Favoritos &amp; Para repetir</p>
      <div id="fav-list" class="space-y-1"></div>
    </div>
  </div>

  <!-- Semana (per-day view) -->
  <div id="tab-semana" class="tab-pane space-y-3">
    <div id="day-tabs" class="flex gap-2 flex-wrap"></div>
    <div id="day-content"></div>
  </div>

  <!-- Compras -->
  <div id="tab-compras" class="tab-pane space-y-3">
    <div class="flex items-center gap-2 flex-wrap">
      <button id="btn-costco" onclick="shop('costco')" class="px-4 py-2 rounded-xl text-sm font-semibold bg-blue-600 text-white">🏪 Costco</button>
      <button id="btn-city"   onclick="shop('city')"   class="px-4 py-2 rounded-xl text-sm font-semibold bg-gray-100 text-gray-600">🏬 City Market</button>
      <div class="ml-auto flex items-center gap-3">
        <span id="check-prog" class="text-xs text-gray-400 font-medium"></span>
        <button onclick="clearChecks()" class="px-3 py-1.5 text-xs border border-gray-200 text-gray-400 rounded-lg hover:border-red-200 hover:text-red-400 transition-colors">Limpiar ✕</button>
      </div>
    </div>
    <div id="shop-content" class="bg-white rounded-xl shadow-sm p-5 prose max-w-none"></div>
  </div>

  <!-- Meal Prep -->
  <div id="tab-prep" class="tab-pane">
    <div id="prep-content" class="bg-white rounded-xl shadow-sm p-5 prose max-w-none">
      <p class="text-gray-400 italic">Sin plan de meal prep generado.</p>
    </div>
  </div>

  <!-- Seguimiento -->
  <div id="tab-tracking" class="tab-pane">
    <div id="no-data" class="hidden text-center py-16 text-gray-400">
      <div class="text-5xl mb-3">📊</div>
      <p class="font-medium text-gray-500">Sin datos de seguimiento todavía</p>
      <p class="text-sm mt-2">Registra comidas con <code class="bg-gray-100 px-1.5 py-0.5 rounded text-gray-600">python main.py registrar</code></p>
    </div>
    <div id="charts-grid" class="grid grid-cols-1 sm:grid-cols-2 gap-4">
      <div class="bg-white rounded-xl shadow-sm p-4 sm:col-span-2"><canvas id="chart-cal" height="70"></canvas></div>
      <div class="bg-white rounded-xl shadow-sm p-4"><canvas id="chart-macro" height="220"></canvas></div>
      <div class="bg-white rounded-xl shadow-sm p-4"><canvas id="chart-weight" height="220"></canvas></div>
    </div>
  </div>

</main>

<script>
const PERSONS  = __PERSONS__;
const TRACKING = __TRACKING__;
const DAYS     = __DAYS__;
const C = { costco: `__COSTCO__`, city: `__CITY__`, prep: `__PREP__` };
const SHOP_KEY   = 'ns___WEEK_KEY__';
const RATING_KEY = 'nr___WEEK_KEY__';

// ── Tabs ──────────────────────────────────────────────────────────────────────
function tab(name, btn) {
  document.querySelectorAll('.tab-pane').forEach(e => e.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(e => e.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  btn.classList.add('active');
  if (name === 'compras') { shopRendered = true; shop(curShop); }
}

// ── Person cards ──────────────────────────────────────────────────────────────
function mbar(v, max, col) {
  const pct = Math.min(100, Math.round(v / max * 100));
  return `<div class="w-full bg-${col}-100 rounded-full h-1.5 mb-2.5"><div class="bg-${col}-400 h-1.5 rounded-full" style="width:${pct}%"></div></div>`;
}
PERSONS.forEach(p => {
  const badge = p.derived
    ? `<span class="text-xs bg-amber-50 text-amber-600 px-2 py-0.5 rounded-full border border-amber-100">Derivado</span>`
    : `<span class="text-xs bg-green-50 text-green-700 px-2 py-0.5 rounded-full border border-green-100">Prescrito</span>`;
  document.getElementById('person-cards').innerHTML += `
  <div class="bg-white rounded-xl shadow-sm p-5">
    <div class="flex items-center justify-between mb-4">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-full bg-green-100 text-green-700 font-bold text-sm flex items-center justify-center shrink-0">${p.name}</div>
        <div><div class="font-semibold">${p.name}</div>${p.goal?`<div class="text-xs text-gray-400 mt-0.5">${p.goal}</div>`:''}</div>
      </div>${badge}
    </div>
    <div class="text-center mb-4">
      <div class="text-4xl font-bold text-green-600">${p.calories}</div>
      <div class="text-xs text-gray-400 mt-0.5">kcal / día</div>
    </div>
    <div class="text-xs space-y-0.5">
      <div class="flex justify-between text-gray-500 mb-0.5"><span>🥩 Proteína</span><span class="font-semibold text-gray-700">${p.protein_g}g</span></div>
      ${mbar(p.protein_g,300,'blue')}
      <div class="flex justify-between text-gray-500 mb-0.5"><span>🌾 Carbohidratos</span><span class="font-semibold text-gray-700">${p.carbs_g}g</span></div>
      ${mbar(p.carbs_g,400,'orange')}
      <div class="flex justify-between text-gray-500 mb-0.5"><span>🥑 Grasas</span><span class="font-semibold text-gray-700">${p.fat_g}g</span></div>
      ${mbar(p.fat_g,120,'yellow')}
    </div>
  </div>`;
});

marked.use({ gfm: true, breaks: true });
if (C.prep) document.getElementById('prep-content').innerHTML = marked.parse(C.prep);

// ── Per-day view ──────────────────────────────────────────────────────────────
let curDay = 0;
const dayTabsEl   = document.getElementById('day-tabs');
const dayContentEl = document.getElementById('day-content');

DAYS.forEach((d, i) => {
  const btn = document.createElement('button');
  btn.className = 'day-btn px-3 py-1.5 rounded-lg text-sm font-medium border border-gray-200 text-gray-600 hover:border-green-400 hover:text-green-700';
  btn.textContent = d.short;
  btn.onclick = () => showDay(i);
  dayTabsEl.appendChild(btn);
});

function showDay(i) {
  curDay = i;
  document.querySelectorAll('.day-btn').forEach((b, j) => b.classList.toggle('active', i === j));
  const d = DAYS[i];
  dayContentEl.innerHTML =
    `<details open class="bg-white rounded-xl shadow-sm mb-3 overflow-hidden">
      <summary class="flex items-center justify-between px-5 py-3 font-semibold text-green-700 text-sm hover:bg-green-50 cursor-pointer">
        <span>🍽️ Menú del día</span><span class="arrow text-gray-300 text-xs ml-2">▶</span>
      </summary>
      <div class="px-5 pb-4 prose max-w-none">${marked.parse(d.menu || '_Sin menú_')}</div>
    </details>
    <div class="bg-white rounded-xl shadow-sm overflow-hidden">
      <div class="px-5 py-3 font-semibold text-green-700 text-sm border-b border-gray-100">📖 Recetas</div>
      <div id="recipes-day" class="px-5 pb-4 prose max-w-none">${marked.parse(d.recipes || '_Sin recetas para este día_')}</div>
    </div>`;
  addRatingWidgets();
}

if (DAYS.length > 0) showDay(0);

// ── Rating system ─────────────────────────────────────────────────────────────
let ratings = JSON.parse(localStorage.getItem(RATING_KEY) || '{}');

function rkey(title) {
  return title.toLowerCase()
    .replace(/[áàäâ]/g,'a').replace(/[éèëê]/g,'e').replace(/[íìïî]/g,'i')
    .replace(/[óòöô]/g,'o').replace(/[úùüû]/g,'u').replace(/ñ/g,'n')
    .replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'');
}

function saveRatings() {
  localStorage.setItem(RATING_KEY, JSON.stringify(ratings));
  renderFavoritos();
}

function addRatingWidgets() {
  const dayShort = DAYS[curDay]?.short || '';
  document.getElementById('recipes-day').querySelectorAll('h3').forEach(h3 => {
    if (h3.nextElementSibling?.classList.contains('recipe-rating')) return;
    const title = h3.textContent.trim();
    const key   = rkey(title);
    const r     = ratings[key] || { stars: 0, tag: '', title, day: dayShort };

    const w = document.createElement('div');
    w.className = 'recipe-rating not-prose flex items-center flex-wrap gap-2 my-2 px-3 py-2 bg-gray-50 rounded-lg';
    w.dataset.recipe = key;

    // Stars
    const sd = document.createElement('div');
    sd.className = 'flex gap-0.5 items-center';
    for (let s = 1; s <= 5; s++) {
      const sb = document.createElement('span');
      sb.className = 'star-btn' + (s <= r.stars ? ' lit' : '');
      sb.textContent = '★';
      sb.onclick = () => {
        const ns = ratings[key]?.stars === s ? 0 : s;
        ratings[key] = { ...(ratings[key] || {}), stars: ns, title, day: dayShort };
        saveRatings();
        w.querySelectorAll('.star-btn').forEach((b, j) => b.classList.toggle('lit', j < ns));
      };
      sd.appendChild(sb);
    }
    w.appendChild(sd);

    // Tag buttons
    [['favorito','❤️ fav','active-fav'],['repetir','🔄 repetir','active-rep'],['no','🚫 no','active-no']].forEach(([t, l, ac]) => {
      const tb = document.createElement('button');
      tb.className = 'tag-btn' + (r.tag === t ? ' ' + ac : '');
      tb.dataset.tag = t;
      tb.textContent = l;
      tb.onclick = () => {
        const cur = ratings[key]?.tag;
        ratings[key] = { ...(ratings[key] || {}), tag: cur === t ? '' : t, title, day: dayShort };
        saveRatings();
        const newTag = ratings[key].tag;
        w.querySelectorAll('.tag-btn').forEach(b => {
          b.classList.remove('active-fav','active-rep','active-no');
          if (b.dataset.tag === newTag) {
            if (newTag === 'favorito') b.classList.add('active-fav');
            else if (newTag === 'repetir') b.classList.add('active-rep');
            else if (newTag === 'no') b.classList.add('active-no');
          }
        });
      };
      w.appendChild(tb);
    });

    h3.after(w);
  });
}

// ── Favoritos section ─────────────────────────────────────────────────────────
function renderFavoritos() {
  const favs = Object.values(ratings).filter(r => r.tag === 'favorito' || r.tag === 'repetir' || r.stars >= 4);
  const sec  = document.getElementById('fav-section');
  const list = document.getElementById('fav-list');
  if (!favs.length) { sec.classList.add('hidden'); return; }
  sec.classList.remove('hidden');
  list.innerHTML = favs.map(r => {
    const tagEl = r.tag === 'favorito' ? '<span class="text-xs bg-red-50 text-red-400 border border-red-100 px-2 py-0.5 rounded-full">❤️ fav</span>'
                : r.tag === 'repetir'  ? '<span class="text-xs bg-green-50 text-green-600 border border-green-100 px-2 py-0.5 rounded-full">🔄 repetir</span>'
                : '';
    const starsEl = r.stars > 0 ? `<span class="text-yellow-400 text-sm tracking-tighter">${'★'.repeat(r.stars)}</span>` : '';
    return `<div class="flex items-center justify-between py-2 border-b border-gray-100 last:border-0 gap-2">
      <div class="flex items-center gap-2 min-w-0">
        ${tagEl}
        <span class="text-sm text-gray-700 truncate">${r.title}</span>
        ${r.day ? `<span class="text-xs text-gray-400 shrink-0">${r.day}</span>` : ''}
      </div>
      ${starsEl}
    </div>`;
  }).join('');
}

renderFavoritos();

// ── Shopping ──────────────────────────────────────────────────────────────────
let checks  = JSON.parse(localStorage.getItem(SHOP_KEY) || '{}');
let curShop = 'costco';
let shopRendered = false;

function shop(which) {
  curShop = which;
  const on  = 'px-4 py-2 rounded-xl text-sm font-semibold bg-blue-600 text-white';
  const off = 'px-4 py-2 rounded-xl text-sm font-semibold bg-gray-100 text-gray-600';
  document.getElementById('btn-costco').className = which === 'costco' ? on : off;
  document.getElementById('btn-city').className   = which === 'city'   ? on : off;
  const el = document.getElementById('shop-content');
  el.innerHTML = marked.parse(C[which] || '_Sin contenido_');
  let tot = 0, chk = 0;
  el.querySelectorAll('input[type=checkbox]').forEach((cb, i) => {
    const k = which + '_' + i;
    cb.checked = !!checks[k];
    if (cb.checked) chk++;
    tot++;
    cb.addEventListener('change', () => {
      checks[k] = cb.checked;
      localStorage.setItem(SHOP_KEY, JSON.stringify(checks));
      setProgress(which);
    });
  });
  setProgress(which, tot, chk);
}

function setProgress(which, tot, chk) {
  if (tot === undefined) {
    const boxes = document.getElementById('shop-content').querySelectorAll('input[type=checkbox]');
    tot = boxes.length; chk = 0;
    boxes.forEach((cb, i) => { if (checks[which + '_' + i]) chk++; });
  }
  const p = document.getElementById('check-prog');
  p.textContent = tot ? `${chk} / ${tot} ítems` : '';
  p.className = chk === tot && tot > 0 ? 'text-xs text-green-600 font-medium' : 'text-xs text-gray-400 font-medium';
}

function clearChecks() {
  Object.keys(checks).filter(k => k.startsWith(curShop + '_')).forEach(k => delete checks[k]);
  localStorage.setItem(SHOP_KEY, JSON.stringify(checks));
  shop(curShop);
}

try { shop('costco'); shopRendered = true; } catch(e) { console.error('shop init:', e); }

// ── Tracking charts ───────────────────────────────────────────────────────────
const tr = TRACKING;
if (!(tr.weekly && tr.weekly.length > 0)) {
  document.getElementById('charts-grid').style.display = 'none';
  document.getElementById('no-data').classList.remove('hidden');
} else {
  const dLabels = ['Lun','Mar','Mié','Jue','Vie','Sáb','Dom'];
  const calTarget = PERSONS[0]?.calories || 2000;
  const calData = dLabels.map((_, i) => { const d = tr.weekly[i]; return d ? (d.calories || 0) : 0; });
  new Chart(document.getElementById('chart-cal'), {
    type: 'bar',
    data: { labels: dLabels, datasets: [
      { label: 'kcal consumidas', data: calData, backgroundColor: 'rgba(5,150,105,.7)', borderRadius: 6, borderSkipped: false },
      { label: 'Meta', data: Array(7).fill(calTarget), type: 'line', borderColor: '#f59e0b', borderWidth: 2, borderDash: [6,4], pointRadius: 0, fill: false }
    ]},
    options: { responsive: true, plugins: { title: { display: true, text: 'Calorías · Esta semana' }, legend: { position: 'bottom' } } }
  });
  const t = tr.today?.totals || {};
  new Chart(document.getElementById('chart-macro'), {
    type: 'doughnut',
    data: { labels: ['Proteína','Carbs','Grasas'],
      datasets: [{ data: [t.protein_g||0, t.carbs_g||0, t.fat_g||0], backgroundColor: ['#60a5fa','#fb923c','#fbbf24'], borderWidth: 0 }] },
    options: { responsive: true, cutout: '62%', plugins: { title: { display: true, text: 'Macros · Hoy' }, legend: { position: 'bottom' } } }
  });
  const wh = (tr.weight_history || []).slice().reverse();
  if (wh.length > 0) {
    new Chart(document.getElementById('chart-weight'), {
      type: 'line',
      data: { labels: wh.map(w => w.date.slice(5)),
        datasets: [{ label: 'kg', data: wh.map(w => w.weight_kg), borderColor: '#8b5cf6', backgroundColor: 'rgba(139,92,246,.08)', fill: true, tension: 0.3, pointRadius: 3 }] },
      options: { responsive: true, plugins: { title: { display: true, text: 'Tendencia de peso' }, legend: { display: false } }, scales: { y: { beginAtZero: false } } }
    });
  }
}
</script>
</body>
</html>"""
