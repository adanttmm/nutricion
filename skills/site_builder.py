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
_MEAL_EMOJIS = ['🌅', '🍎', '🍽', '🌿', '🌙', '🎉']


class SiteBuilderSkill(BaseSkill):

    def build(self, week_date: date = None) -> Path:
        if week_date is None:
            week_date = date.today()

        docs_dir = Path("docs")
        docs_dir.mkdir(exist_ok=True)
        (docs_dir / ".nojekyll").touch()

        self._copy_images(docs_dir)

        diet_plan        = self._load_latest_diet_plan()
        menu_md          = self._load_latest("outputs/menus",     "menu_*.md")
        shopping_md      = self._load_latest("outputs/shopping",  "compras_*.md")
        recipes_md       = self._load_latest("outputs/recipes",   "recetas_*.md")
        prep_md          = self._load_latest("outputs/meal_prep", "meal_prep_*.md")
        prev_recipes_md  = self._load_prev("outputs/recipes",     "recetas_*.md")
        prev_recipes_lbl = self._prev_label("outputs/recipes",    "recetas_*.md")
        tracking         = self._export_tracking()
        days_data        = self._split_by_days(menu_md, recipes_md)
        week_key         = week_date.strftime("%Y-%m-%d")
        ingr_hist        = self._update_ingredient_history(shopping_md, week_key)
        ratings_hist     = self._load_ratings_history()

        plan_name    = diet_plan.get("plan_name") or f"Plan Nutricional — {week_date.strftime('%d/%m/%Y')}"
        nutritionist = diet_plan.get("nutritionist") or ""
        nut_line     = f'<p class="logo-sub">{nutritionist}</p>' if nutritionist else ""

        html = (
            self._HTML
            .replace("__PLAN_NAME__",          plan_name)
            .replace("__NUT_LINE__",            nut_line)
            .replace("__WEEK_LABEL__",          week_date.strftime("%d de %B de %Y"))
            .replace("__PERSONS__",             json.dumps(self._persons(diet_plan), ensure_ascii=False))
            .replace("__TRACKING__",            json.dumps(tracking, ensure_ascii=False, default=str))
            .replace("__DAYS__",                json.dumps(days_data, ensure_ascii=False))
            .replace("__SHOPPING_HTML__",       self._md_to_html(shopping_md))
            .replace("__PREP_HTML__",           self._md_to_html(prep_md))
            .replace("__PREV_RECIPES_HTML__",   self._md_to_html(prev_recipes_md) if prev_recipes_md else "<p style='color:#a0aec0;padding:1.5rem 0;text-align:center'>Sin recetas de semana anterior.</p>")
            .replace("__PREV_RECIPES_LABEL__",  prev_recipes_lbl)
            .replace("__INGREDIENT_HISTORY__",  json.dumps(ingr_hist, ensure_ascii=False))
            .replace("__RATINGS_HISTORY__",     json.dumps(ratings_hist, ensure_ascii=False))
            .replace("__WEEK_KEY__",            week_date.strftime("%Y%m%d"))
        )

        output = docs_dir / "index.html"
        output.write_text(html, encoding="utf-8")
        return output

    @staticmethod
    def _copy_images(docs_dir: Path) -> None:
        import shutil
        src = Path("imagenes")
        if not src.exists():
            return
        dst = docs_dir / "imagenes"
        dst.mkdir(exist_ok=True)
        for img in src.iterdir():
            if img.is_file():
                shutil.copy2(img, dst / img.name)

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
    def _load_prev(directory: str, pattern: str) -> str:
        p = Path(directory)
        if not p.exists():
            return ""
        files = sorted(p.glob(pattern), reverse=True)
        return files[1].read_text(encoding="utf-8") if len(files) > 1 else ""

    @staticmethod
    def _prev_label(directory: str, pattern: str) -> str:
        p = Path(directory)
        if not p.exists():
            return ""
        files = sorted(p.glob(pattern), reverse=True)
        if len(files) < 2:
            return ""
        stem = files[1].stem
        date_str = stem.replace("recetas_", "")
        try:
            from datetime import date as _d
            d = _d.fromisoformat(date_str)
            months = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"]
            return f"{d.day} {months[d.month-1]}"
        except Exception:
            return date_str

    @staticmethod
    def _md_to_html(md: str) -> str:
        """Convert markdown to HTML without external libraries."""
        import html as h, re
        lines = md.split("\n")
        out = []
        in_list = False
        in_fence = False
        fence_lines: list = []

        def inline(text: str) -> str:
            text = h.escape(text)
            text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
            text = re.sub(r'\*(.+?)\*',     r'<em>\1</em>',         text)
            text = re.sub(r'`(.+?)`',       r'<code>\1</code>',     text)
            # Convert markdown links [text](url)
            text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" target="_blank">\1</a>', text)
            return text

        in_table = False
        table_rows: list = []

        def flush_table():
            nonlocal in_table, table_rows
            if not table_rows:
                return
            html_rows = []
            header_done = False
            for ri, row in enumerate(table_rows):
                cells = [c.strip() for c in row.strip('|').split('|')]
                if all(re.match(r'^:?-+:?$', c.strip()) for c in cells if c.strip()):
                    header_done = True
                    continue
                tag = 'th' if (ri == 0 and not header_done) else 'td'
                html_rows.append('<tr>' + ''.join(f'<{tag}>{inline(c)}</{tag}>' for c in cells) + '</tr>')
            if html_rows:
                out.append('<table class="prose-table"><thead>' + html_rows[0] + '</thead><tbody>' +
                           ''.join(html_rows[1:]) + '</tbody></table>')
            in_table = False
            table_rows = []

        for line in lines:
            if line.strip().startswith('|') and '|' in line.strip()[1:]:
                if in_list:
                    out.append('</ul>'); in_list = False
                in_table = True
                table_rows.append(line)
                continue
            elif in_table:
                flush_table()

            if line.startswith("```"):
                if not in_fence:
                    if in_list:
                        out.append('</ul>'); in_list = False
                    in_fence = True
                    fence_lines = []
                else:
                    in_fence = False
                    out.append(f'<pre><code>{h.escape(chr(10).join(fence_lines))}</code></pre>')
                continue
            if in_fence:
                fence_lines.append(line)
                continue
            if line.startswith("- [ ] ") or line.startswith("- [x] ") or line.startswith("- [X] "):
                if not in_list:
                    out.append('<ul class="shop-list">'); in_list = True
                checked = '' if line[3] == ' ' else ' checked'
                out.append(f'<li><label><input type="checkbox"{checked}> {inline(line[6:])}</label></li>')
                continue
            if line.startswith("- "):
                if not in_list:
                    out.append('<ul class="shop-list">'); in_list = True
                out.append(f'<li>{inline(line[2:])}</li>')
                continue
            if in_list:
                out.append('</ul>'); in_list = False
            s = line.strip()
            if   s.startswith("###### "): out.append(f'<h6>{inline(s[7:])}</h6>')
            elif s.startswith("##### "):  out.append(f'<h5>{inline(s[6:])}</h5>')
            elif s.startswith("#### "):   out.append(f'<h4>{inline(s[5:])}</h4>')
            elif s.startswith("### "):    out.append(f'<h3>{inline(s[4:])}</h3>')
            elif s.startswith("## "):     out.append(f'<h2>{inline(s[3:])}</h2>')
            elif s.startswith("# "):      out.append(f'<h1>{inline(s[2:])}</h1>')
            elif s in ("---", "***", "___"): out.append('<hr>')
            elif s == "":                 out.append('')
            else:                         out.append(f'<p>{inline(s)}</p>')

        if in_table: flush_table()
        if in_list:  out.append('</ul>')
        if in_fence: out.append(f'<pre><code>{h.escape(chr(10).join(fence_lines))}</code></pre>')
        return "\n".join(out)

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
            rec_content = rec_map.get(day_key, '')
            meals = SiteBuilderSkill._build_meals(
                SiteBuilderSkill._split_meal_sections(menu_content),
                SiteBuilderSkill._split_meal_sections(rec_content),
            )
            days.append({
                "key":    day_key.lower().replace("é", "e").replace("á", "a"),
                "short":  _DAY_SHORT.get(day_key, day_key[:3]),
                "name":   header,
                "dishes": SiteBuilderSkill._extract_dishes(menu_content),
                "meals":  meals,
            })
        return days

    @staticmethod
    def _split_meal_sections(text: str) -> list:
        """Split text by ### meal-time emoji headers. Returns list of (header, body)."""
        sections = []
        cur_header = None
        cur_body: list = []
        for line in text.split('\n'):
            if line.startswith('### ') and any(e in line for e in _MEAL_EMOJIS):
                if cur_header is not None:
                    sections.append((cur_header, '\n'.join(cur_body).strip()))
                cur_header = line
                cur_body = []
            elif cur_header is not None:
                cur_body.append(line)
        if cur_header is not None:
            sections.append((cur_header, '\n'.join(cur_body).strip()))
        return sections

    @staticmethod
    def _build_meals(menu_secs: list, rec_secs: list) -> list:
        """Match menu and recipe sections by emoji, pre-render both to HTML."""
        rec_by_emoji: dict = {}
        for hdr, body in rec_secs:
            for e in _MEAL_EMOJIS:
                if e in hdr:
                    rec_by_emoji[e] = (hdr, body)
                    break

        meals = []
        for hdr, body in menu_secs:
            emoji = next((e for e in _MEAL_EMOJIS if e in hdr), None)
            label = hdr.lstrip('#').strip()
            menu_html = SiteBuilderSkill._md_to_html(body)

            rec = rec_by_emoji.get(emoji) if emoji else None
            recipe_html = ''
            recipe_title = ''
            rkey_val = ''
            if rec:
                rec_hdr, rec_body = rec
                recipe_html = SiteBuilderSkill._md_to_html(rec_body)
                recipe_title = rec_hdr.lstrip('#').strip()
                r = recipe_title.lower()
                for src, dst in [('á','a'),('à','a'),('ä','a'),('â','a'),
                                  ('é','e'),('è','e'),('ë','e'),('ê','e'),
                                  ('í','i'),('ì','i'),('ï','i'),('î','i'),
                                  ('ó','o'),('ò','o'),('ö','o'),('ô','o'),
                                  ('ú','u'),('ù','u'),('ü','u'),('û','u'),('ñ','n')]:
                    r = r.replace(src, dst)
                rkey_val = re.sub(r'[^a-z0-9]+', '-', r).strip('-')

            meals.append({
                'emoji':        emoji or '',
                'label':        label,
                'menu_html':    menu_html,
                'recipe_title': recipe_title,
                'recipe_html':  recipe_html,
                'rkey':         rkey_val,
            })
        return meals

    @staticmethod
    def _extract_dishes(day_md: str) -> dict:
        """Extract first bold dish name per meal-time section."""
        import re
        SLOT_EMOJIS = [
            ('desayuno',   '🌅'),
            ('col_am',     '🍎'),
            ('comida',     '🍽'),
            ('col_pm',     '🌿'),
            ('cena',       '🌙'),
        ]
        dishes: dict = {}
        cur_slot: str | None = None
        for line in day_md.split('\n'):
            if line.startswith('### '):
                cur_slot = None
                for slot, emoji in SLOT_EMOJIS:
                    if emoji in line:
                        cur_slot = slot
                        break
            elif cur_slot and cur_slot not in dishes and '**' in line:
                m = re.search(r'\*\*([^*\n]+)\*\*', line)
                if m:
                    name = re.sub(r'[\U0001F300-\U0001FAFF\U00002600-\U000027BF🏪🎉\s]+$', '', m.group(1)).strip()
                    if name:
                        dishes[cur_slot] = name
        return dishes

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
                "weekly":            log.get_weekly_data(week_start),
                "weight_history_atm": log.get_weight_history(90, person='ATM'),
                "weight_history_iob": log.get_weight_history(90, person='IOB'),
                "body_comp_atm":     log.get_body_composition_history(90, person='ATM'),
                "body_comp_iob":     log.get_body_composition_history(90, person='IOB'),
                "today":             log.get_daily_summary(today),
            }
            log.close()
            return result
        except Exception:
            return {}

    @staticmethod
    def _extract_ingredients(shopping_md: str) -> dict:
        """Return {ingredient_name: count} from a shopping list markdown."""
        import re
        ingredients: dict[str, int] = {}
        skip_values = {'ingrediente', 'nombre', 'item', 'producto', '—', '-', 'leche de coco'}
        for m in re.finditer(r'^\|([^|]+)\|', shopping_md, re.MULTILINE):
            raw = m.group(1).strip()
            if not raw or re.match(r'^[-:\s]+$', raw) or raw.lower() in skip_values:
                continue
            name = re.sub(r'\s*\([^)]*\)', '', raw)       # remove parentheticals
            name = re.sub(r'\s*/.*$', '', name)            # remove "/ alternative"
            name = re.sub(r'\s*\d[\d.,]*\s*(g|ml|kg|L|pz|piezas|lata|latas)\b.*', '', name, flags=re.I)
            name = name.strip().rstrip('.,;:')
            if len(name) < 3 or name.lower() in skip_values:
                continue
            ingredients[name] = ingredients.get(name, 0) + 1
        return ingredients

    def _update_ingredient_history(self, shopping_md: str, week_key: str) -> dict:
        """Merge this week's ingredients into data/ingredient_history.json and return full history."""
        hist_path = Path("data/ingredient_history.json")
        try:
            history: dict = json.loads(hist_path.read_text(encoding="utf-8")) if hist_path.exists() else {}
        except Exception:
            history = {}
        if shopping_md:
            ingredients = self._extract_ingredients(shopping_md)
            if ingredients:
                history[week_key] = ingredients
        hist_path.parent.mkdir(parents=True, exist_ok=True)
        hist_path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
        return history

    @staticmethod
    def _load_ratings_history() -> dict:
        path = Path("data/ratings_history.json")
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"dishes": {}}

    @staticmethod
    def _js(text: str) -> str:
        return text.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")

    _HTML = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>__PLAN_NAME__</title>
  <style>
    /* ── Palette ─────────────────────────────────────────── */
    :root{
      --navy:#212e53;--teal:#4a919e;--terra:#ce6a6b;--blush:#ebaca2;--sage:#bed3c3;
      --teal-10:rgba(74,145,158,.1);--teal-20:rgba(74,145,158,.2);
      --terra-10:rgba(206,106,107,.1);--sage-20:rgba(190,211,195,.2);
      --navy-08:rgba(33,46,83,.08);
    }
    /* ── Reset ───────────────────────────────────────────── */
    *,::before,::after{box-sizing:border-box;margin:0;padding:0}
    body{font-family:ui-sans-serif,system-ui,-apple-system,sans-serif;font-size:.9rem;
      color:#2d3748;background:#f4f2ee;min-height:100vh}
    button{font-family:inherit;cursor:pointer;border:none;background:none}
    a{color:var(--teal);text-decoration:none}
    /* ── Header ──────────────────────────────────────────── */
    header{background:var(--navy);position:sticky;top:0;z-index:30;
      box-shadow:0 2px 16px rgba(33,46,83,.4)}
    .hd-inner{max-width:72rem;margin:0 auto;padding:.7rem 1.25rem;
      display:flex;align-items:center;justify-content:space-between}
    .logo{display:flex;align-items:center;gap:.65rem}
    .logo-icon{width:34px;height:34px;border-radius:50%;flex-shrink:0;
      background:linear-gradient(135deg,var(--teal),var(--blush));
      display:flex;align-items:center;justify-content:center;font-size:1.05rem}
    .logo-name{color:#fff;font-weight:700;font-size:.95rem;letter-spacing:-.01em;line-height:1.1}
    .logo-sub{color:var(--sage);font-size:.68rem;font-weight:400;margin-top:1px;opacity:.8}
    .hd-date{color:rgba(190,211,195,.6);font-size:.72rem;white-space:nowrap}
    .hd-tabs{max-width:72rem;margin:0 auto;padding:0 1rem;
      display:flex;overflow-x:auto;border-top:1px solid rgba(255,255,255,.07)}
    .hd-tabs::-webkit-scrollbar{height:2px}
    .hd-tabs::-webkit-scrollbar-thumb{background:var(--teal)}
    .tab-btn{background:none;border:none;padding:.6rem .95rem;font-size:.8rem;
      font-weight:500;color:rgba(255,255,255,.45);white-space:nowrap;cursor:pointer;
      border-bottom:2px solid transparent;transition:color .18s,border-color .18s}
    .tab-btn.active{color:#fff;border-bottom-color:var(--teal);font-weight:600}
    .tab-btn:hover:not(.active){color:rgba(255,255,255,.78)}
    .tab-pane{display:none}.tab-pane.active{display:block}
    /* ── Layout ──────────────────────────────────────────── */
    main{max-width:72rem;margin:0 auto;padding:1.5rem 1rem}
    main>*+*{margin-top:1.25rem}
    /* ── Card ────────────────────────────────────────────── */
    .card{background:#fff;border-radius:1rem;
      box-shadow:0 1px 3px rgba(33,46,83,.07),0 6px 24px rgba(33,46,83,.04);
      overflow:hidden}
    .card-pad{padding:1.25rem}
    .sec-label{font-size:.68rem;font-weight:700;text-transform:uppercase;
      letter-spacing:.08em;color:#a0aec0}
    /* ── Hero banner ─────────────────────────────────────── */
    .hero{height:180px;border-radius:1rem;position:relative;overflow:hidden;
      background:linear-gradient(125deg,rgba(33,46,83,.78) 0%,rgba(30,61,92,.55) 50%,rgba(74,145,158,.40) 100%),
        url('imagenes/hero.png');
      background-size:cover;background-position:center;
      display:flex;align-items:flex-end;padding:1.25rem 1.5rem}
    .hero-text{position:relative;z-index:1}
    .hero-title{color:#fff;font-size:1.3rem;font-weight:700;
      letter-spacing:-.02em;line-height:1.2;text-shadow:0 1px 6px rgba(0,0,0,.4)}
    .hero-sub{color:rgba(190,211,195,.85);font-size:.77rem;margin-top:.3rem;
      text-shadow:0 1px 4px rgba(0,0,0,.35)}
    /* ── Section image banners ───────────────────────────── */
    .sec-banner{position:relative;border-radius:1rem;overflow:hidden;height:120px;
      margin-bottom:1rem}
    .sec-banner img{position:absolute;inset:0;width:100%;height:100%;
      object-fit:cover;object-position:center}
    .sec-banner-ov{position:absolute;inset:0;
      background:linear-gradient(90deg,rgba(33,46,83,.80) 0%,rgba(33,46,83,.35) 60%,transparent 100%)}
    .sec-banner-text{position:absolute;inset:0;display:flex;flex-direction:column;
      justify-content:center;padding:1rem 1.5rem;z-index:1}
    .sec-banner-title{color:#fff;font-size:1.1rem;font-weight:700;
      text-shadow:0 1px 6px rgba(0,0,0,.4)}
    .sec-banner-sub{color:rgba(190,211,195,.85);font-size:.75rem;margin-top:.2rem;
      text-shadow:0 1px 4px rgba(0,0,0,.3)}
    @media(max-width:640px){
      .hero{height:140px}
      .sec-banner{height:90px}
      .sec-banner-title{font-size:.95rem}
    }
    /* ── Tile gallery ────────────────────────────────────── */
    .tile-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:.55rem}
    @media(max-width:860px){.tile-grid{grid-template-columns:repeat(4,1fr)}}
    @media(max-width:480px){.tile-grid{grid-template-columns:repeat(2,1fr)}}
    .day-tile{border-radius:.75rem;overflow:hidden;cursor:pointer;
      transition:transform .15s,box-shadow .15s;
      aspect-ratio:1;position:relative;display:flex;flex-direction:column;
      justify-content:flex-end}
    .day-tile:hover{transform:translateY(-3px);
      box-shadow:0 8px 24px rgba(33,46,83,.28)}
    .tile-bg{position:absolute;inset:0}
    .tile-body{position:relative;z-index:1;padding:.45rem .5rem}
    .tile-day{font-size:.57rem;font-weight:700;text-transform:uppercase;
      letter-spacing:.07em;color:rgba(255,255,255,.7);margin-bottom:.15rem}
    .tile-dish{font-size:.6rem;color:#fff;font-weight:500;line-height:1.25;
      white-space:nowrap;overflow:hidden;text-overflow:ellipsis;opacity:.9;
      display:flex;align-items:center;gap:2px}
    .tile-em{font-size:.57rem;opacity:.75;flex-shrink:0}
    /* ── Compact week table ──────────────────────────────── */
    .week-tbl{width:100%;border-collapse:collapse;font-size:.76rem}
    .week-tbl th{background:var(--navy);color:#fff;padding:6px 8px;
      font-weight:600;text-align:center;white-space:nowrap;font-size:.71rem}
    .week-tbl td{padding:6px 8px;border:1px solid #ede9e3;vertical-align:top;
      cursor:pointer;max-width:110px}
    .week-tbl td:hover{background:var(--teal-10)}
    .week-tbl td.dlabel{font-weight:600;color:var(--teal);
      background:#f8f6f2;cursor:default;white-space:nowrap}
    /* ── Day selector ────────────────────────────────────── */
    .day-nav{display:flex;gap:.4rem;flex-wrap:wrap}
    .day-btn{padding:.38rem .85rem;border-radius:.5rem;font-size:.8rem;font-weight:500;
      color:var(--navy);border:1.5px solid #e2ddd6;background:#fff;cursor:pointer;
      transition:all .15s}
    .day-btn:hover{border-color:var(--teal);color:var(--teal)}
    .day-btn.active{background:var(--navy);color:#fff;border-color:var(--navy)}
    /* ── Meal card ───────────────────────────────────────── */
    .meal-card{border-radius:.75rem;overflow:hidden;background:#fff;margin-bottom:.75rem;
      box-shadow:0 1px 4px rgba(33,46,83,.07);border-left:3px solid var(--terra)}
    .meal-card-header{padding:.55rem 1rem;
      background:linear-gradient(90deg,rgba(206,106,107,.08),transparent);
      font-weight:600;font-size:.8rem;color:var(--navy);
      display:flex;align-items:center;gap:.45rem}
    .meal-card-body{padding:.7rem 1rem}
    details.recipe-details>summary{list-style:none;padding:.42rem 1rem;font-size:.76rem;
      color:#9ca3af;cursor:pointer;display:flex;align-items:center;gap:.35rem;
      border-top:1px solid #f4f2ee}
    details.recipe-details>summary::-webkit-details-marker{display:none}
    details.recipe-details>summary:hover{background:var(--teal-10);color:var(--teal)}
    .recipe-inner{padding:.75rem 1rem 1rem;border-top:1px solid #f4f2ee}
    /* ── Shopping list ───────────────────────────────────── */
    .shop-list{list-style:none;padding:0;margin:.3rem 0}
    .shop-list li{padding:.38rem 0;border-bottom:1px solid #f4f2ee;
      font-size:.87rem;line-height:1.5}
    .shop-list li:last-child{border-bottom:none}
    .shop-list label{display:flex;align-items:flex-start;gap:8px;cursor:pointer}
    .shop-list input[type=checkbox]{margin-top:3px;width:14px;height:14px;
      accent-color:var(--teal);flex-shrink:0;cursor:pointer}
    /* ── Tables (shopping/recipe) ────────────────────────── */
    .prose-table{width:100%;border-collapse:collapse}
    .prose-table thead tr{background:var(--navy)}
    .prose-table th{padding:8px 10px;text-align:left;font-weight:600;
      font-size:.75rem;color:#fff;white-space:nowrap}
    .prose-table td{padding:7px 10px;border-bottom:1px solid #ede9e3;
      font-size:.82rem;vertical-align:top}
    .prose-table tr:hover td{background:rgba(74,145,158,.05)}
    .prose-table tr:last-child td{border-bottom:none}
    /* ── Prose (meal body / recipe body) ─────────────────── */
    .prose table{width:100%;border-collapse:collapse}
    .prose th{background:rgba(74,145,158,.1);padding:5px 8px;text-align:left;
      font-weight:600;font-size:.76rem;color:var(--teal)}
    .prose td{padding:5px 8px;border-top:1px solid #f4f2ee;font-size:.82rem}
    .prose h1{font-size:1.05rem;font-weight:700;color:var(--navy);margin:1rem 0 .4rem}
    .prose h2{font-size:.97rem;font-weight:700;color:var(--navy);margin:.9rem 0 .35rem}
    .prose h3{font-size:.88rem;font-weight:600;color:var(--teal);margin:.75rem 0 .28rem}
    .prose h4{font-size:.83rem;font-weight:600;color:var(--navy);margin:.6rem 0 .2rem}
    .prose ul,.prose ol{padding-left:1.3rem;margin:.3rem 0}
    .prose li{margin:.2rem 0;font-size:.87rem;line-height:1.5}
    .prose p{margin:.3rem 0;font-size:.87rem;line-height:1.6}
    .prose strong{font-weight:600;color:var(--navy)}
    .prose em{font-style:italic;color:#718096}
    .prose hr{margin:1rem 0;border:none;border-top:1px solid #ede9e3}
    .prose a{color:var(--teal)}
    .prose a:hover{color:var(--terra)}
    .prose code{background:#f4f2ee;padding:.1rem .3rem;border-radius:.2rem;font-size:.76rem}
    .prose input[type=checkbox]{margin-right:6px;cursor:pointer;accent-color:var(--teal)}
    .prose blockquote{border-left:3px solid var(--sage);background:rgba(190,211,195,.15);
      padding:.55rem .9rem;margin:.55rem 0;border-radius:0 .5rem .5rem 0;
      color:#4a5568;font-size:.85rem}
    @media(max-width:640px){.prose th,.prose td{padding:4px 6px;font-size:.76rem}}
    /* ── Person cards ────────────────────────────────────── */
    .person-card{border-radius:1rem;background:var(--navy);color:#fff;padding:1.25rem;
      box-shadow:0 4px 20px rgba(33,46,83,.25)}
    .person-avatar{width:40px;height:40px;border-radius:50%;flex-shrink:0;
      background:linear-gradient(135deg,var(--teal),var(--sage));
      display:flex;align-items:center;justify-content:center;
      font-weight:700;font-size:.85rem;color:var(--navy)}
    .mbar-bg{height:4px;border-radius:2px;background:rgba(255,255,255,.15);
      overflow:hidden;margin-bottom:10px}
    .mbar-fill{height:4px;border-radius:2px}
    /* ── Badges ──────────────────────────────────────────── */
    .badge{display:inline-flex;align-items:center;padding:2px 8px;
      border-radius:99px;font-size:.69rem;font-weight:600}
    .badge-teal{background:rgba(74,145,158,.15);color:var(--teal)}
    .badge-terra{background:rgba(206,106,107,.12);color:var(--terra)}
    .badge-sage{background:rgba(190,211,195,.35);color:#3a6652}
    .badge-blush{background:rgba(235,172,162,.25);color:#9b4a40}
    /* ── Rating ──────────────────────────────────────────── */
    .rating-row{display:flex;align-items:center;gap:.5rem;padding:.35rem .75rem;
      font-size:.75rem}
    .person-lbl{width:3rem;font-weight:600;flex-shrink:0;color:var(--navy)}
    .star-btn{font-size:1rem;cursor:pointer;opacity:.18;transition:opacity .1s;
      background:none;border:none;padding:0;line-height:1}
    .star-btn.lit{opacity:1;color:var(--terra)}
    .tag-btn{font-size:.7rem;padding:2px 7px;border-radius:99px;
      border:1px solid #e2ddd6;cursor:pointer;background:#fff;transition:all .15s}
    .tag-btn.active-fav{background:var(--terra-10);border-color:var(--terra);
      color:var(--terra)}
    .tag-btn.active-rep{background:var(--teal-10);border-color:var(--teal);
      color:var(--teal)}
    .tag-btn.active-no{background:#f3f4f6;border-color:#d1d5db;opacity:.6}
    /* ── Body composition ────────────────────────────────── */
    .bc-hero-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:.6rem;margin-bottom:1.1rem}
    .bc-hero{background:var(--navy-08);border-radius:.75rem;padding:.85rem 1rem}
    .bc-hero-label{font-size:.6rem;font-weight:700;text-transform:uppercase;
      letter-spacing:.07em;color:#a0aec0;margin-bottom:.2rem}
    .bc-hero-val{font-size:1.45rem;font-weight:700;color:var(--navy);line-height:1;margin-bottom:.3rem}
    .bc-hero-unit{font-size:.72rem;color:#718096;font-weight:400}
    .bc-delta{font-size:.68rem;font-weight:600;padding:2px 7px;border-radius:.3rem;display:inline-block}
    .bc-delta-good{background:rgba(190,211,195,.4);color:#2d6a4f}
    .bc-delta-bad{background:rgba(206,106,107,.12);color:var(--terra)}
    .bc-delta-neu{background:var(--navy-08);color:#a0aec0}
    .bc-sec-row{display:flex;align-items:center;justify-content:space-between;padding:.38rem 0;
      border-bottom:1px solid var(--navy-08);font-size:.78rem}
    .bc-sec-row:last-child{border-bottom:none}
    .bc-sec-name{color:#4a5568}
    .bc-sec-right{display:flex;align-items:center;gap:.45rem}
    .bc-sec-val{font-weight:700;color:var(--navy)}
    /* ── Tracking controls ───────────────────────────────── */
    .ctrl-select{font-family:inherit;font-size:.78rem;padding:.32rem .55rem;
      border:1.5px solid #e2ddd6;border-radius:.5rem;background:#fff;
      color:var(--navy);outline:none;cursor:pointer}
    .ctrl-select:focus{border-color:var(--teal)}
    .ctrl-input{font-family:inherit;font-size:.82rem;padding:.35rem .55rem;
      border:1.5px solid #e2ddd6;border-radius:.5rem;background:#fff;
      color:var(--navy);outline:none}
    .ctrl-input:focus{border-color:var(--teal)}
    .toggle-btn{padding:.3rem .65rem;border-radius:.4rem;font-size:.74rem;font-weight:600;
      color:#718096;border:1.5px solid #e2ddd6;background:#fff;cursor:pointer;
      transition:all .15s}
    .toggle-btn.active{background:var(--navy);color:#fff;border-color:var(--navy)}
    .rank-row{display:flex;align-items:center;gap:.55rem;padding:.42rem 0;
      border-bottom:1px solid #f4f2ee;font-size:.83rem}
    .rank-row:last-child{border-bottom:none}
    .rank-num{width:1.4rem;text-align:right;font-weight:700;color:var(--terra);
      flex-shrink:0;font-size:.75rem}
    .rank-stars{color:var(--terra);letter-spacing:-.05em;flex-shrink:0;font-size:.82rem}
    .rank-name{flex:1;min-width:0;color:var(--navy);font-weight:500;
      overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .rank-score{font-size:.7rem;color:#718096;flex-shrink:0}
    /* ── Misc utilities ──────────────────────────────────── */
    .hidden{display:none!important}
    .flex{display:flex}.grid{display:grid}
    .items-center{align-items:center}.justify-between{justify-content:space-between}
    .flex-wrap{flex-wrap:wrap}.gap-2{gap:.5rem}.gap-3{gap:.75rem}.gap-4{gap:1rem}
    .mt-1{margin-top:.25rem}.mt-2{margin-top:.5rem}.mt-3{margin-top:.75rem}
    .mb-2{margin-bottom:.5rem}.mb-3{margin-bottom:.75rem}.mb-4{margin-bottom:1rem}
    .shrink-0{flex-shrink:0}.min-w-0{min-width:0}.w-full{width:100%}
    .space-y-1>*+*{margin-top:.25rem}.space-y-3>*+*{margin-top:.75rem}
    .space-y-4>*+*{margin-top:1rem}
    .text-xs{font-size:.75rem}.text-sm{font-size:.875rem}
    .font-semibold{font-weight:600}.font-bold{font-weight:700}
    .text-center{text-align:center}
    .truncate{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .overflow-x-auto{overflow-x:auto}.overflow-hidden{overflow:hidden}
    .max-w-none{max-width:none}
    .text-gray-400{color:#a0aec0}.text-gray-500{color:#718096}
    .text-white{color:#fff}.text-navy{color:var(--navy)}
    .text-teal{color:var(--teal)}.text-terra{color:var(--terra)}
    .arr{display:inline-block;transition:transform .2s;font-size:.68rem;color:#a0aec0}
    details[open]>summary .arr{transform:rotate(90deg)}
    .sm-grid-2{display:grid;grid-template-columns:repeat(2,1fr);gap:1rem}
    @media(max-width:600px){.sm-grid-2{grid-template-columns:1fr}}
  </style>
</head>
<body>
<script>
(function(){
  var div=document.createElement('div');
  div.id='pre-probe';
  div.style.cssText='position:fixed;bottom:0;left:0;right:0;padding:6px 14px;font:12px monospace;z-index:99999;color:#fff';
  window.addEventListener('error',function(ev){
    div.style.background='#b91c1c';
    div.textContent='JS ERR L'+ev.lineno+': '+ev.message;
    if(!div.parentNode)document.body&&document.body.appendChild(div);
  });
  document.addEventListener('DOMContentLoaded',function(){
    if(!div.textContent)div.textContent='JS OK — main script parse OK';
    div.style.background=div.textContent.indexOf('ERR')>-1?'#b91c1c':'#7c3aed';
    if(!div.parentNode)document.body.appendChild(div);
  });
})();
</script>

<header>
  <div class="hd-inner">
    <div class="logo">
      <div class="logo-icon">🥗</div>
      <div>
        <div class="logo-name">__PLAN_NAME__</div>
        __NUT_LINE__
      </div>
    </div>
    <span class="hd-date">__WEEK_LABEL__</span>
  </div>
  <div class="hd-tabs">
    <button onclick="tab('resumen',this)" class="tab-btn active">📊 Resumen</button>
    <button id="btn-tab-semana" onclick="tab('semana',this)" class="tab-btn">📅 Semana</button>
    <button onclick="tab('compras',this)" class="tab-btn">🛒 Compras</button>
    <button onclick="tab('prep',this)" class="tab-btn">🍳 Meal Prep</button>
    <button onclick="tab('recprev',this)" class="tab-btn">📖 Recetas __PREV_RECIPES_LABEL__</button>
    <button onclick="tab('tracking',this)" class="tab-btn">📈 Seguimiento</button>
  </div>
</header>

<main>

  <!-- ── Resumen ──────────────────────────────────────────── -->
  <div id="tab-resumen" class="tab-pane active space-y-4">

    <div class="hero">
      <div class="hero-text">
        <div class="hero-title">Menú de la Semana</div>
        <div class="hero-sub">__WEEK_LABEL__ · Cocina gourmet en casa</div>
      </div>
    </div>

    <div class="card">
      <div class="card-pad" style="padding-bottom:.9rem">
        <div class="flex items-center justify-between mb-3">
          <span class="sec-label">Menú semanal</span>
          <span class="text-xs text-gray-400">Toca un día para ver sus recetas</span>
        </div>
        <div class="tile-grid" id="tile-gallery"></div>
      </div>
    </div>

    <div class="card overflow-x-auto">
      <div class="card-pad" style="padding-bottom:.9rem">
        <p class="sec-label mb-2" style="margin-bottom:.6rem">Vista rápida</p>
        <table class="week-tbl" id="week-table">
          <thead><tr>
            <th>Día</th><th>🌅 Desayuno</th><th>🍎 Col.AM</th>
            <th>🍽️ Comida</th><th>🌿 Col.PM</th><th>🌙 Cena</th>
          </tr></thead>
          <tbody id="week-tbody"></tbody>
        </table>
      </div>
    </div>

    <div id="fav-section" class="card">
      <div class="card-pad">
        <div class="flex items-center justify-between mb-3">
          <span class="sec-label">⭐ Valoraciones</span>
          <span id="autosave-status" style="font-size:.72rem;color:#9ca3af">
            <button id="autosave-btn" onclick="setupAutoSave()"
              class="badge badge-teal" style="cursor:pointer">
              Conectar carpeta
            </button>
          </span>
        </div>
        <div id="fav-list" class="space-y-1"></div>
        <p id="fav-hint" class="text-xs" style="color:#9ca3af;margin-top:.6rem">
          Califica los platos abriendo cada receta en la pestaña 📅 Semana.<br>
          Haz clic en <em>Conectar carpeta</em> y selecciona
          <code>data/ratings/</code> del proyecto para que las valoraciones
          se guarden automáticamente antes de cada actualización.
        </p>
      </div>
    </div>
  </div>

  <!-- ── Semana ───────────────────────────────────────────── -->
  <div id="tab-semana" class="tab-pane space-y-3">
    <div class="sec-banner">
      <img src="imagenes/semana.png" alt="">
      <div class="sec-banner-ov"></div>
      <div class="sec-banner-text">
        <div class="sec-banner-title">📅 Menú Detallado</div>
        <div class="sec-banner-sub">Recetas y preparación día a día</div>
      </div>
    </div>
    <div class="day-nav" id="day-tabs"></div>
    <div id="day-content"></div>
  </div>

  <!-- ── Compras ──────────────────────────────────────────── -->
  <div id="tab-compras" class="tab-pane space-y-3">
    <div class="sec-banner">
      <img src="imagenes/compras.png" alt="">
      <div class="sec-banner-ov"></div>
      <div class="sec-banner-text">
        <div class="sec-banner-title">🛒 Lista de Compras</div>
        <div class="sec-banner-sub">Costco · City Market</div>
      </div>
    </div>
    <div class="flex items-center justify-end gap-3" style="min-height:2rem">
      <span id="check-prog" class="text-xs text-gray-400 font-semibold"></span>
      <button onclick="clearChecks()" class="badge badge-terra"
        style="cursor:pointer">Limpiar ✕</button>
    </div>
    <div class="card">
      <div class="card-pad prose max-w-none">
        <div id="html-shopping">__SHOPPING_HTML__</div>
      </div>
    </div>
  </div>

  <!-- ── Meal Prep ────────────────────────────────────────── -->
  <div id="tab-prep" class="tab-pane space-y-3">
    <div class="sec-banner">
      <img src="imagenes/meal-prep.png" alt="">
      <div class="sec-banner-ov"></div>
      <div class="sec-banner-text">
        <div class="sec-banner-title">🍳 Meal Prep del Fin de Semana</div>
        <div class="sec-banner-sub">Prepara el domingo, disfruta toda la semana</div>
      </div>
    </div>
    <div class="card">
      <div class="card-pad prose max-w-none">__PREP_HTML__</div>
    </div>
  </div>

  <!-- ── Recetas semana anterior ────────────────────────────── -->
  <div id="tab-recprev" class="tab-pane space-y-3">
    <div class="sec-banner">
      <img src="imagenes/semana.png" alt="">
      <div class="sec-banner-ov"></div>
      <div class="sec-banner-text">
        <div class="sec-banner-title">📖 Recetas Semana Anterior</div>
        <div class="sec-banner-sub">__PREV_RECIPES_LABEL__</div>
      </div>
    </div>
    <div class="card">
      <div class="card-pad prose max-w-none">__PREV_RECIPES_HTML__</div>
    </div>
  </div>

  <!-- ── Seguimiento ──────────────────────────────────────── -->
  <div id="tab-tracking" class="tab-pane space-y-4">
    <div class="sec-banner">
      <img src="imagenes/tracking.png" alt="">
      <div class="sec-banner-ov"></div>
      <div class="sec-banner-text">
        <div class="sec-banner-title">📈 Seguimiento Nutricional</div>
        <div class="sec-banner-sub">Tendencias · Ingredientes · Peso</div>
      </div>
    </div>

    <div class="sm-grid-2" id="person-cards"></div>

    <!-- 0. Body composition (from Xiaomi scale) -->
    <div class="card" id="body-comp-card" style="display:none">
      <div class="card-pad">
        <div class="flex items-center justify-between mb-3">
          <span class="sec-label">⚖️ Composición Corporal</span>
          <div style="display:flex;gap:.25rem" id="bc-person-tabs">
            <button class="toggle-btn active" onclick="setBcPerson('atm',this)">ATM</button>
            <button class="toggle-btn" onclick="setBcPerson('iob',this)">IOB</button>
          </div>
        </div>
        <p id="bc-date-label" style="font-size:.7rem;color:#a0aec0;margin:-.5rem 0 .9rem"></p>
        <!-- Layer 1: Hero metrics -->
        <div id="bc-hero" class="bc-hero-grid"></div>
        <!-- Layer 2: Body composition stacked bar -->
        <div style="margin-bottom:1.1rem">
          <span class="sec-label" style="display:block;margin-bottom:.55rem">Distribución corporal</span>
          <canvas id="chart-bc-comp" height="52"></canvas>
        </div>
        <!-- Layer 3: Trend chart -->
        <div class="flex items-center justify-between mb-2">
          <span class="sec-label">Tendencia</span>
          <select id="bc-metric" class="ctrl-select" onchange="updateBcChart()">
            <option value="weight_kg">Peso (kg)</option>
            <option value="body_fat_pct">Grasa corporal (%)</option>
            <option value="muscle_mass_kg">Masa muscular (kg)</option>
            <option value="visceral_fat">Grasa visceral</option>
            <option value="lean_mass_kg">Masa magra (kg)</option>
            <option value="water_pct">Agua (%)</option>
            <option value="protein_pct">Proteína (%)</option>
            <option value="bmr">TMB (kcal)</option>
            <option value="metabolic_age">Edad metabólica</option>
            <option value="bmi">IMC</option>
            <option value="bone_mass_kg">Masa ósea (kg)</option>
            <option value="subcutaneous_fat_pct">G. subcutánea (%)</option>
            <option value="skeletal_muscle_pct">Músculo esq. (%)</option>
            <option value="fat_mass_kg">Masa grasa (kg)</option>
          </select>
        </div>
        <canvas id="chart-bc-trend" height="110"></canvas>
        <!-- Layer 4: Secondary metrics -->
        <div id="bc-secondary"></div>
      </div>
    </div>

    <!-- 1. Nutrient trend chart -->
    <div class="card">
      <div class="card-pad">
        <div class="flex items-center justify-between mb-3">
          <span class="sec-label">📊 Tendencia Semanal</span>
          <select id="trend-nutrient" class="ctrl-select" onchange="updateTrendChart()">
            <option value="calories">Calorías (kcal)</option>
            <option value="protein_g">Proteína (g)</option>
            <option value="carbs_g">Carbohidratos (g)</option>
            <option value="fat_g">Grasa (g)</option>
          </select>
        </div>
        <div id="trend-nodata" class="hidden text-center" style="padding:2rem 0;color:#a0aec0">
          <p class="text-sm">Usa <code style="background:#f4f2ee;padding:2px 6px;border-radius:4px">python main.py registrar</code> para ver tendencias.</p>
        </div>
        <canvas id="chart-trend" height="95"></canvas>
      </div>
    </div>

    <!-- macro donut -->
    <div class="card" id="macro-card">
      <div class="card-pad"><canvas id="chart-macro" height="220"></canvas></div>
    </div>

    <!-- 2. Ingredient word cloud -->
    <div class="card">
      <div class="card-pad">
        <div class="flex items-center justify-between mb-3">
          <span class="sec-label">🌿 Ingredientes de la Semana</span>
          <select id="cloud-week" class="ctrl-select" onchange="renderWordCloud(this.value)"></select>
        </div>
        <div id="word-cloud-wrap" style="width:100%;min-height:220px;display:flex;align-items:center;justify-content:center">
          <canvas id="word-cloud-canvas" style="max-width:100%"></canvas>
        </div>
      </div>
    </div>

    <!-- 3. Top 10 recipe rankings -->
    <div class="card" id="rankings-card">
      <div class="card-pad">
        <div class="flex items-center justify-between mb-3">
          <span class="sec-label">🏆 Top 10 Recetas</span>
          <div style="display:flex;gap:.25rem">
            <button class="toggle-btn active" onclick="setRankPerson('avg',this)">Total</button>
            <button class="toggle-btn" onclick="setRankPerson('atm',this)">ATM</button>
            <button class="toggle-btn" onclick="setRankPerson('iob',this)">IOB</button>
          </div>
        </div>
        <div id="rankings-list">
          <p class="text-xs" style="color:#9ca3af">Sin valoraciones todavía — califica platos en la pestaña 📅 Semana.</p>
        </div>
      </div>
    </div>

    <!-- 5. Weight trend -->
    <div class="card">
      <div class="card-pad">
        <div class="flex items-center justify-between mb-3">
          <span class="sec-label">📉 Tendencia de Peso</span>
          <div style="display:flex;gap:.25rem" id="weight-trend-tabs">
            <button class="toggle-btn active" onclick="setWeightTrendPerson('atm',this)">ATM</button>
            <button class="toggle-btn" onclick="setWeightTrendPerson('iob',this)">IOB</button>
          </div>
        </div>
        <div id="weight-chart-empty" style="display:none;padding:1.5rem 0;text-align:center;color:#a0aec0">
          <p class="text-sm">Sin datos de peso — registra mediciones arriba.</p>
        </div>
        <canvas id="chart-weight" height="140"></canvas>
      </div>
    </div>

  </div>

</main>

<script src="https://cdn.jsdelivr.net/npm/chart.js" async></script>
<script src="https://cdn.jsdelivr.net/npm/wordcloud@1.2.2/src/wordcloud2.js" async></script>
<script>
window.addEventListener('error', function(ev) {
  var b = document.createElement('div');
  b.style.cssText = 'position:fixed;top:0;left:0;right:0;background:#b91c1c;color:#fff;padding:10px 16px;z-index:9999;font:13px/1.5 monospace;white-space:pre-wrap';
  b.textContent = '⚠ Error JS (reportar a Adán):\n' + ev.message + '\n  línea ' + ev.lineno + ', col ' + ev.colno + (ev.filename ? '\n  ' + ev.filename : '');
  document.body.prepend(b);
});
// ── Data ──────────────────────────────────────────────────────────────────────
const PERSONS            = __PERSONS__;
const TRACKING           = __TRACKING__;
const DAYS               = __DAYS__;
const INGREDIENT_HISTORY = __INGREDIENT_HISTORY__;
const RATINGS_HISTORY    = __RATINGS_HISTORY__;
const SHOP_KEY           = 'ns___WEEK_KEY__';
const RATING_KEY         = 'nr___WEEK_KEY__';

// ── State ─────────────────────────────────────────────────────────────────────
function _lsGet(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key) || JSON.stringify(fallback)); }
  catch(e) { try { localStorage.removeItem(key); } catch(_){} return fallback; }
}
let checks  = _lsGet(SHOP_KEY,   {});
let ratings = _lsGet(RATING_KEY, {});
let weights = _lsGet('nw_weights', {atm:[],iob:[]});
let curDay  = 0;
let _trackingInited = false;
let _weightTrendPerson = 'atm';
let _rankPerson        = 'avg';
let _trendChart        = null;
let _wChart            = null;

// ── Tabs ──────────────────────────────────────────────────────────────────────
function tab(name, btn) {
  document.querySelectorAll('.tab-pane').forEach(e => e.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(e => e.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  btn.classList.add('active');
  if (name === 'compras') initShopChecks();
  if (name === 'tracking') initTracking();
}

// ── Debug probe (remove after fix) ───────────────────────────────────────────
(function() {
  var dbg = document.createElement('div');
  dbg.id = 'dbg-probe';
  dbg.style.cssText = 'background:#1e3a5f;color:#7dd3fc;padding:6px 14px;font:12px monospace;position:fixed;bottom:0;left:0;right:0;z-index:9998';
  dbg.textContent = 'JS OK — DAYS:' + DAYS.length + ' gallery:' + !!document.getElementById('tile-gallery') + ' tbody:' + !!document.getElementById('week-tbody');
  document.body.appendChild(dbg);
})();

// ── Tile gallery ──────────────────────────────────────────────────────────────
const TILE_COLORS = ['#212e53','#3a7a85','#3a6652','#ce6a6b','#2a5070','#9b4a40','#4a919e'];
const SLOT_EMOJI = {desayuno:'🌅', col_am:'🍎', comida:'🍽', col_pm:'🌿', cena:'🌙'};
const SLOT_KEYS  = ['desayuno','col_am','comida','col_pm','cena'];
const gallery    = document.getElementById('tile-gallery');

DAYS.forEach((d, di) => {
  const tile = document.createElement('div');
  tile.className = 'day-tile';
  tile.onclick = () => { document.getElementById('btn-tab-semana').click(); showDay(di); };

  tile.innerHTML = '<div class="tile-bg" style="background:' + TILE_COLORS[di % TILE_COLORS.length] + '"></div>';

  const body = document.createElement('div');
  body.className = 'tile-body';

  const label = document.createElement('div');
  label.className = 'tile-day';
  label.textContent = d.short;
  body.appendChild(label);

  [{key:'desayuno',em:'🌅'},{key:'comida',em:'🍽'},{key:'cena',em:'🌙'}].forEach(({key,em}) => {
    const name = d.dishes && d.dishes[key];
    if (name) {
      const row = document.createElement('div');
      row.className = 'tile-dish';
      row.innerHTML = '<span class="tile-em">' + em + '</span>' + name;
      body.appendChild(row);
    }
  });
  tile.appendChild(body);
  gallery.appendChild(tile);
});

// ── Compact week table ────────────────────────────────────────────────────────
const tbody = document.getElementById('week-tbody');
DAYS.forEach((d, di) => {
  const tr = document.createElement('tr');
  const tdDay = document.createElement('td');
  tdDay.className = 'dlabel';
  tdDay.textContent = d.short;
  tr.appendChild(tdDay);
  SLOT_KEYS.forEach(slot => {
    const td = document.createElement('td');
    const name = (d.dishes && d.dishes[slot]) || '';
    if (name) {
      td.innerHTML = '<span style="border-bottom:1px dotted #9ca3af">' + name + '</span>';
      td.title = 'Ver receta';
      td.onclick = () => { document.getElementById('btn-tab-semana').click(); showDay(di, slot); };
    } else {
      td.textContent = '—';
      td.style.color = '#d1d5db';
    }
    tr.appendChild(td);
  });
  tbody.appendChild(tr);
});

// ── Per-day view ──────────────────────────────────────────────────────────────
const dayTabsEl    = document.getElementById('day-tabs');
const dayContentEl = document.getElementById('day-content');

DAYS.forEach((d, i) => {
  const btn = document.createElement('button');
  btn.className = 'day-btn';
  btn.textContent = d.short;
  btn.onclick = () => showDay(i);
  dayTabsEl.appendChild(btn);
});

function showDay(i, targetSlot) {
  curDay = i;
  document.querySelectorAll('.day-btn').forEach((b, j) => b.classList.toggle('active', i === j));
  const d = DAYS[i];
  let html = '<div class="text-xs text-gray-400" style="padding:.2rem .25rem .7rem;font-weight:500">' +
    (d.name || '') + '</div>';

  const meals = d.meals || [];
  if (!meals.length) {
    html += '<div class="card" style="padding:1.5rem;color:#a0aec0;text-align:center">Sin menú.</div>';
  } else {
    for (const m of meals) {
      html +=
        '<div class="meal-card" data-emoji="' + (m.emoji || '') + '">' +
          '<div class="meal-card-header">' + m.label + '</div>' +
          '<div class="meal-card-body prose max-w-none">' + m.menu_html + '</div>';
      if (m.recipe_html) {
        const safe = m.recipe_title
          .replace(/&/g,'&amp;').replace(/</g,'&lt;')
          .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
        html +=
          '<details class="recipe-details">' +
            '<summary><span class="arr">▶</span> Ver receta: ' + safe + '</summary>' +
            '<div class="recipe-inner">' +
              '<div class="recipe-rating-placeholder" data-rkey="' + m.rkey +
                '" data-title="' + safe + '" data-day="' + d.short + '"></div>' +
              m.recipe_html +
            '</div></details>';
      }
      html += '</div>';
    }
  }
  dayContentEl.innerHTML = html;
  addRatingWidgets();

  if (targetSlot && SLOT_EMOJI[targetSlot]) {
    const targetEmoji = SLOT_EMOJI[targetSlot];
    dayContentEl.querySelectorAll('.meal-card').forEach(card => {
      if (card.dataset.emoji === targetEmoji) {
        const det = card.querySelector('details');
        if (det) {
          det.open = true;
          setTimeout(() => card.scrollIntoView({behavior:'smooth', block:'start'}), 60);
        }
      }
    });
  }
}

if (DAYS.length > 0) showDay(0);

// ── Shopping ──────────────────────────────────────────────────────────────────
function initShopChecks() {
  const section = document.getElementById('html-shopping');
  if (!section) return;
  let tot = 0, chk = 0;
  section.querySelectorAll('input[type=checkbox]').forEach((cb, i) => {
    const k = 'shop_' + i;
    cb.checked = !!checks[k];
    if (cb.checked) chk++;
    tot++;
    if (!cb.dataset.bound) {
      cb.dataset.bound = '1';
      cb.addEventListener('change', () => {
        checks[k] = cb.checked;
        localStorage.setItem(SHOP_KEY, JSON.stringify(checks));
        updateProgress();
      });
    }
  });
  updateProgress(tot, chk);
}

function updateProgress(tot, chk) {
  if (tot === undefined) {
    const boxes = document.getElementById('html-shopping').querySelectorAll('input[type=checkbox]');
    tot = boxes.length; chk = 0;
    boxes.forEach((cb, i) => { if (checks['shop_' + i]) chk++; });
  }
  const p = document.getElementById('check-prog');
  p.textContent = tot ? chk + ' / ' + tot + ' ítems' : '';
  p.style.color = (chk === tot && tot > 0) ? 'var(--teal)' : '#a0aec0';
}

function clearChecks() {
  Object.keys(checks).filter(k => k.startsWith('shop_')).forEach(k => delete checks[k]);
  localStorage.setItem(SHOP_KEY, JSON.stringify(checks));
  initShopChecks();
}

initShopChecks();

// ── Person cards ──────────────────────────────────────────────────────────────
function mbar(v, max, col) {
  const pct = Math.min(100, Math.round(v / max * 100));
  const colors = {blue:'#4a919e', orange:'#ce6a6b', yellow:'#ebaca2'};
  return '<div class="mbar-bg"><div class="mbar-fill" style="width:' + pct + '%;background:' +
    (colors[col] || col) + '"></div></div>';
}

PERSONS.forEach(p => {
  const badge = p.derived
    ? '<span class="badge badge-blush">Derivado</span>'
    : '<span class="badge badge-sage">Prescrito</span>';
  document.getElementById('person-cards').innerHTML +=
    '<div class="person-card">' +
      '<div class="flex items-center justify-between mb-4">' +
        '<div class="flex items-center gap-3">' +
          '<div class="person-avatar shrink-0">' + p.name + '</div>' +
          '<div><div class="font-semibold text-white">' + p.name + '</div>' +
            (p.goal ? '<div class="text-xs" style="color:rgba(190,211,195,.7);margin-top:1px">' + p.goal + '</div>' : '') +
          '</div>' +
        '</div>' + badge +
      '</div>' +
      '<div class="text-center mb-4">' +
        '<div style="font-size:2.4rem;font-weight:700;color:var(--sage)">' + p.calories + '</div>' +
        '<div class="text-xs" style="color:rgba(255,255,255,.45);margin-top:2px">kcal / día</div>' +
      '</div>' +
      '<div class="text-xs" style="color:rgba(255,255,255,.55)">' +
        '<div class="flex justify-between mb-1"><span>🥩 Proteína</span>' +
          '<span style="color:#fff;font-weight:600">' + p.protein_g + 'g</span></div>' +
        mbar(p.protein_g,300,'blue') +
        '<div class="flex justify-between mb-1"><span>🌾 Carbohidratos</span>' +
          '<span style="color:#fff;font-weight:600">' + p.carbs_g + 'g</span></div>' +
        mbar(p.carbs_g,400,'orange') +
        '<div class="flex justify-between mb-1"><span>🥑 Grasas</span>' +
          '<span style="color:#fff;font-weight:600">' + p.fat_g + 'g</span></div>' +
        mbar(p.fat_g,120,'yellow') +
      '</div>' +
    '</div>';
});

// ── File System Access API — auto-save ratings to data/ratings/ ───────────────
const IDB_NAME = 'nutricion_ratings';
const IDB_STORE = 'handles';
const IDB_KEY   = 'ratingsDir';

function _idbOpen() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(IDB_NAME, 1);
    req.onupgradeneeded = e => e.target.result.createObjectStore(IDB_STORE);
    req.onsuccess  = e => resolve(e.target.result);
    req.onerror    = () => reject(req.error);
  });
}
async function _idbGet(key) {
  const db = await _idbOpen();
  return new Promise((res, rej) => {
    const r = db.transaction(IDB_STORE,'readonly').objectStore(IDB_STORE).get(key);
    r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error);
  });
}
async function _idbSet(key, value) {
  const db = await _idbOpen();
  return new Promise((res, rej) => {
    const tx = db.transaction(IDB_STORE,'readwrite');
    tx.objectStore(IDB_STORE).put(value, key);
    tx.oncomplete = res; tx.onerror = () => rej(tx.error);
  });
}

let _dirHandle = null;

async function _writeRatingsFile() {
  if (!_dirHandle) return;
  try {
    const fh = await _dirHandle.getFileHandle('ratings___WEEK_KEY__.json', { create: true });
    const w  = await fh.createWritable();
    await w.write(JSON.stringify(ratings, null, 2));
    await w.close();
  } catch(e) {
    console.warn('auto-save failed:', e);
    _dirHandle = null;
    _updateSaveStatus(false);
  }
}

function _updateSaveStatus(connected) {
  const btn  = document.getElementById('autosave-btn');
  const hint = document.getElementById('fav-hint');
  if (!btn) return;
  if (connected) {
    btn.textContent = '✅ Auto-guardando';
    btn.style.background = 'var(--teal)';
    btn.style.color = '#fff';
    btn.onclick = null;
    if (hint) hint.style.display = 'none';
  } else {
    btn.textContent = 'Conectar carpeta';
    btn.style.background = '';
    btn.style.color = '';
    btn.onclick = setupAutoSave;
    if (hint) hint.style.display = '';
  }
}

async function setupAutoSave() {
  if (!('showDirectoryPicker' in window)) {
    alert('Tu navegador no soporta File System Access API.\nUsa Chrome o Edge para auto-guardar valoraciones.');
    return;
  }
  try {
    _dirHandle = await window.showDirectoryPicker({ mode: 'readwrite', startIn: 'documents' });
    await _idbSet(IDB_KEY, _dirHandle);
    await _writeRatingsFile();
    _updateSaveStatus(true);
  } catch(e) {
    if (e.name !== 'AbortError') console.error('Directory picker error:', e);
  }
}

async function _restoreAutoSave() {
  try {
    const h = await _idbGet(IDB_KEY);
    if (!h) return;
    const perm = await h.requestPermission({ mode: 'readwrite' });
    if (perm === 'granted') { _dirHandle = h; _updateSaveStatus(true); }
  } catch(e) { /* silently skip */ }
}
_restoreAutoSave();

// ── Ratings ───────────────────────────────────────────────────────────────────
function saveRatings() {
  localStorage.setItem(RATING_KEY, JSON.stringify(ratings));
  renderFavoritos();
  _writeRatingsFile();
}

function makePersonRatingRow(key, person, title, dayShort) {
  const pKey = person.toLowerCase();
  const r = (ratings[key] && ratings[key][pKey]) || { stars: 0, tag: '' };
  const row = document.createElement('div');
  row.className = 'rating-row';

  const lbl = document.createElement('span');
  lbl.className = 'person-lbl';
  lbl.textContent = person === 'ATM' ? '🧔 ATM' : '👤 IOB';
  row.appendChild(lbl);

  const sd = document.createElement('div');
  sd.style.cssText = 'display:flex;gap:1px';
  for (let s = 1; s <= 5; s++) {
    const sb = document.createElement('button');
    sb.className = 'star-btn' + (s <= r.stars ? ' lit' : '');
    sb.textContent = '★';
    sb.onclick = () => {
      const cur = (ratings[key] && ratings[key][pKey]) || {};
      const ns = cur.stars === s ? 0 : s;
      if (!ratings[key]) ratings[key] = { title, day: dayShort };
      ratings[key][pKey] = { ...cur, stars: ns };
      saveRatings();
      row.querySelectorAll('.star-btn').forEach((b, j) => b.classList.toggle('lit', j < ns));
    };
    sd.appendChild(sb);
  }
  row.appendChild(sd);

  [['favorito','❤️','active-fav'],['repetir','🔄','active-rep'],['no','🚫','active-no']].forEach(([t,l,ac]) => {
    const tb = document.createElement('button');
    tb.className = 'tag-btn' + (r.tag === t ? ' ' + ac : '');
    tb.dataset.tag = t; tb.textContent = l; tb.title = t;
    tb.onclick = () => {
      const cur = (ratings[key] && ratings[key][pKey]) || {};
      const newTag = cur.tag === t ? '' : t;
      if (!ratings[key]) ratings[key] = { title, day: dayShort };
      ratings[key][pKey] = { ...cur, tag: newTag };
      saveRatings();
      row.querySelectorAll('.tag-btn').forEach(b => {
        b.classList.remove('active-fav','active-rep','active-no');
        if (b.dataset.tag === newTag) b.classList.add(ac);
      });
    };
    row.appendChild(tb);
  });
  return row;
}

function addRatingWidgets() {
  dayContentEl.querySelectorAll('.recipe-rating-placeholder').forEach(ph => {
    if (ph.dataset.built) return;
    ph.dataset.built = '1';
    const key = ph.dataset.rkey, title = ph.dataset.title, day = ph.dataset.day;
    if (!ratings[key]) ratings[key] = { title, day };
    const block = document.createElement('div');
    block.style.cssText = 'border:1px solid #ede9e3;border-radius:.5rem;overflow:hidden;margin-bottom:.75rem';
    const persons = PERSONS.length > 0 ? PERSONS.map(p => p.name) : ['ATM','IOB'];
    persons.forEach(name => block.appendChild(makePersonRatingRow(key, name, title, day)));
    ph.replaceWith(block);
  });
}

// ── Favoritos ─────────────────────────────────────────────────────────────────
function renderFavoritos() {
  const favEntries = [];
  const allRated = [];
  for (const [key, r] of Object.entries(ratings)) {
    if (!r.title) continue;
    const persons = PERSONS.length > 0 ? PERSONS.map(p => p.name.toLowerCase()) : ['atm','iob'];
    persons.forEach(pk => {
      const pr = r[pk];
      if (!pr) return;
      if (pr.stars || pr.tag) {
        allRated.push({title:r.title, day:r.day, person:pk.toUpperCase(), stars:pr.stars||0, tag:pr.tag||''});
        if (pr.tag === 'favorito' || pr.tag === 'repetir' || pr.stars >= 4) {
          favEntries.push({title:r.title, day:r.day, person:pk.toUpperCase(), stars:pr.stars||0, tag:pr.tag||''});
        }
      }
    });
  }
  const list = document.getElementById('fav-list');
  const hint = document.getElementById('fav-hint');
  const connected = !!_dirHandle;
  if (!favEntries.length) {
    list.innerHTML = allRated.length
      ? '<p class="text-xs" style="color:#9ca3af">Aún no hay favoritos — califica platos con ≥4★ o márcalos ❤️/🔄.</p>'
      : '';
    if (hint) hint.style.display = connected ? 'none' : '';
    return;
  }
  if (hint) hint.style.display = 'none';
  list.innerHTML = favEntries.map(r => {
    const tagEl = r.tag === 'favorito'
      ? '<span class="badge badge-terra">❤️ fav</span>'
      : r.tag === 'repetir'
      ? '<span class="badge badge-teal">🔄 repetir</span>'
      : '';
    const stars = r.stars > 0
      ? '<span style="color:var(--terra);letter-spacing:-.05em">' + '★'.repeat(r.stars) + '</span>' : '';
    return '<div class="flex items-center justify-between" ' +
      'style="padding:.45rem 0;border-bottom:1px solid #f4f2ee">' +
      '<div class="flex items-center gap-2 min-w-0">' + tagEl +
        '<span class="text-xs font-semibold text-teal">' + r.person + '</span>' +
        '<span class="text-sm text-navy truncate">' + r.title + '</span>' +
        (r.day ? '<span class="text-xs text-gray-400 shrink-0">' + r.day + '</span>' : '') +
      '</div>' + stars + '</div>';
  }).join('');
}
renderFavoritos();

// ── Sort shopping lists alphabetically ───────────────────────────────────────
function sortShopLists() {
  const section = document.getElementById('html-shopping');
  if (!section) return;
  section.querySelectorAll('table').forEach(tbl => {
    const tbody = tbl.querySelector('tbody');
    if (!tbody) return;
    const rows = Array.from(tbody.querySelectorAll('tr'));
    rows.sort((a, b) => {
      const ta = (a.cells[0] && a.cells[0].textContent.trim()) || '';
      const tb2 = (b.cells[0] && b.cells[0].textContent.trim()) || '';
      return ta.localeCompare(tb2, 'es', {sensitivity:'base'});
    });
    rows.forEach(r => tbody.appendChild(r));
  });
  section.querySelectorAll('ul.shop-list').forEach(ul => {
    const items = Array.from(ul.querySelectorAll('li'));
    items.sort((a, b) => a.textContent.trim().localeCompare(b.textContent.trim(), 'es', {sensitivity:'base'}));
    items.forEach(li => ul.appendChild(li));
  });
}
sortShopLists();

// ── Tracking init ─────────────────────────────────────────────────────────────
function initTracking() {
  if (_trackingInited) return;
  _trackingInited = true;
  initBodyComp();
  _waitChart(initTrendChart);
  _waitChart(initMacroChart);
  initWordCloud();
  renderRankings();
  _waitChart(updateWeightChart);
}
function _waitChart(fn) {
  if (typeof Chart === 'undefined') { setTimeout(() => _waitChart(fn), 180); return; }
  Chart.defaults.font.family = 'ui-sans-serif,system-ui,-apple-system,sans-serif';
  fn();
}

// ── 1. Nutrient trend chart ───────────────────────────────────────────────────
const _NUTRIENT_LABELS = {calories:'Calorías (kcal)',protein_g:'Proteína (g)',carbs_g:'Carbohidratos (g)',fat_g:'Grasa (g)'};
const _NUTRIENT_COLORS = {calories:'#4a919e',protein_g:'#ce6a6b',carbs_g:'#ebaca2',fat_g:'#bed3c3'};
const _PERSON_KEYS     = {calories:'calories',protein_g:'protein_g',carbs_g:'carbs_g',fat_g:'fat_g'};

function initTrendChart() {
  const tr = TRACKING;
  const hasData = tr.weekly && tr.weekly.some(d => d && (d.calories||d.protein_g||d.carbs_g||d.fat_g));
  if (!hasData) {
    document.getElementById('trend-nodata').classList.remove('hidden');
    document.getElementById('chart-trend').style.display = 'none';
    return;
  }
  updateTrendChart();
}

function updateTrendChart() {
  const nutrient = document.getElementById('trend-nutrient').value;
  const tr = TRACKING;
  const dLabels = ['Lun','Mar','Mié','Jue','Vie','Sáb','Dom'];
  const data = dLabels.map((_, i) => { const d = tr.weekly && tr.weekly[i]; return d ? (d[nutrient]||0) : null; });
  const color = _NUTRIENT_COLORS[nutrient];
  const label = _NUTRIENT_LABELS[nutrient];
  const pKey  = _PERSON_KEYS[nutrient];
  const t_atm = PERSONS[0]?.[pKey] || null;
  const t_iob = PERSONS[1]?.[pKey] || null;
  const datasets = [{
    label, data, backgroundColor: color + 'c0',
    borderRadius: 6, borderSkipped: false, order: 2
  }];
  if (t_atm) datasets.push({ label:'Meta ATM', data:Array(7).fill(t_atm), type:'line',
    borderColor:'#212e53', borderWidth:1.5, borderDash:[5,4], pointRadius:0, fill:false, order:1 });
  if (t_iob) datasets.push({ label:'Meta IOB', data:Array(7).fill(t_iob), type:'line',
    borderColor:'#9b4a40', borderWidth:1.5, borderDash:[3,3], pointRadius:0, fill:false, order:1 });
  if (_trendChart) {
    _trendChart.data.datasets = datasets;
    _trendChart.options.plugins.title.text = label + ' · Esta semana';
    _trendChart.update();
    return;
  }
  _trendChart = new Chart(document.getElementById('chart-trend'), {
    type: 'bar',
    data: { labels: dLabels, datasets },
    options: { responsive:true,
      plugins:{ title:{ display:true, text:label+' · Esta semana',
        color:'#212e53',font:{weight:'600'} }, legend:{position:'bottom'} } }
  });
}

function initMacroChart() {
  const t = TRACKING.today?.totals || {};
  if (!(t.protein_g||t.carbs_g||t.fat_g)) {
    document.getElementById('macro-card').style.display = 'none';
    return;
  }
  new Chart(document.getElementById('chart-macro'), {
    type:'doughnut',
    data:{ labels:['Proteína','Carbs','Grasas'],
      datasets:[{ data:[t.protein_g||0,t.carbs_g||0,t.fat_g||0],
        backgroundColor:['#4a919e','#ebaca2','#ce6a6b'],borderWidth:0 }] },
    options:{ responsive:true,cutout:'62%',
      plugins:{ title:{display:true,text:'Macros · Hoy',color:'#212e53',font:{weight:'600'}},
        legend:{position:'bottom'} } }
  });
}

// ── 2. Ingredient word cloud ──────────────────────────────────────────────────
function initWordCloud() {
  const sel = document.getElementById('cloud-week');
  const weeks = Object.keys(INGREDIENT_HISTORY).sort().reverse();
  if (!weeks.length) {
    document.getElementById('word-cloud-wrap').innerHTML =
      '<p class="text-xs" style="color:#9ca3af;padding:1.5rem 0">Sin historial de ingredientes todavía — actualiza el sitio con un menú activo.</p>';
    return;
  }
  sel.innerHTML = weeks.map(w => `<option value="${w}">${w}</option>`).join('');
  renderWordCloud(weeks[0]);
}

function renderWordCloud(weekKey) {
  const canvas = document.getElementById('word-cloud-canvas');
  const wrap   = document.getElementById('word-cloud-wrap');
  if (!canvas || !wrap) return;
  const ingredients = INGREDIENT_HISTORY[weekKey] || {};
  const entries = Object.entries(ingredients).sort((a,b)=>b[1]-a[1]).slice(0,60);
  if (!entries.length) { wrap.innerHTML = '<p class="text-xs" style="color:#9ca3af">Sin datos.</p>'; return; }
  if (typeof WordCloud === 'undefined') { setTimeout(() => renderWordCloud(weekKey), 250); return; }
  const palette = ['#212e53','#4a919e','#3a6652','#ce6a6b','#2a5070','#9b4a40','#4a919e'];
  const max = entries[0][1];
  const words = entries.map(([w,c]) => [w, Math.max(12, Math.min(56, Math.round(c/max*48)+12))]);
  canvas.width  = wrap.offsetWidth || 500;
  canvas.height = 240;
  WordCloud(canvas, {
    list:words, gridSize:8, shrinkToFit:true, rotateRatio:0.2, minSize:10,
    fontFamily:'ui-sans-serif,system-ui,-apple-system,sans-serif',
    color:()=>palette[Math.floor(Math.random()*palette.length)],
    backgroundColor:'#ffffff'
  });
}

// ── 3. Top 10 recipe rankings ─────────────────────────────────────────────────
function setRankPerson(p, btn) {
  _rankPerson = p;
  document.querySelectorAll('#rankings-card .toggle-btn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  renderRankings();
}

function renderRankings() {
  const dishes = (RATINGS_HISTORY.dishes) || {};
  const list   = document.getElementById('rankings-list');
  if (!Object.keys(dishes).length) return;
  const scored = Object.entries(dishes).map(([title, data]) => {
    let score = 0;
    if (_rankPerson === 'avg') {
      score = data.avg_stars || 0;
    } else {
      const pr = (data.last_rating || {})[_rankPerson] || {};
      score = pr.stars || 0;
    }
    return { title, score, times: data.times_served||1, tags: data.all_tags||[] };
  }).filter(d => d.score > 0).sort((a,b)=>b.score-a.score).slice(0,10);
  if (!scored.length) {
    list.innerHTML = '<p class="text-xs" style="color:#9ca3af">Sin valoraciones para mostrar.</p>';
    return;
  }
  list.innerHTML = scored.map((d,i) => {
    const stars   = Math.round(d.score);
    const tagHtml = d.tags.includes('favorito') ? ' ❤️' : d.tags.includes('repetir') ? ' 🔄' : '';
    const times   = d.times > 1 ? ` <span style="color:#9ca3af;font-size:.68rem">(×${d.times})</span>` : '';
    return `<div class="rank-row">
      <span class="rank-num">${i+1}</span>
      <span class="rank-name">${d.title}${tagHtml}${times}</span>
      <span class="rank-stars">${'★'.repeat(stars)}</span>
      <span class="rank-score">${d.score.toFixed(1)}★</span>
    </div>`;
  }).join('');
}

// ── 5. Weight trend chart ─────────────────────────────────────────────────────
function setWeightTrendPerson(p, btn) {
  _weightTrendPerson = p;
  document.querySelectorAll('#weight-trend-tabs .toggle-btn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  updateWeightChart();
}

function _mergedWeightData(person) {
  const sqlKey  = 'weight_history_' + person;
  const fromDB  = (TRACKING[sqlKey] || []).map(e => ({ date:e.date, kg:e.weight_kg }));
  const fromLoc = weights[person] || [];
  const map = {};
  fromDB.forEach(e  => { map[e.date] = e.kg; });
  fromLoc.forEach(e => { map[e.date] = e.kg; });  // local takes priority
  return Object.entries(map).sort((a,b)=>a[0].localeCompare(b[0])).map(([date,kg])=>({date,kg}));
}

function updateWeightChart() {
  const data   = _mergedWeightData(_weightTrendPerson);
  const empty  = document.getElementById('weight-chart-empty');
  const canvas = document.getElementById('chart-weight');
  if (!data.length) {
    if (empty)  empty.style.display = 'block';
    if (canvas) canvas.style.display = 'none';
    if (_wChart) { _wChart.destroy(); _wChart = null; }
    return;
  }
  if (empty)  empty.style.display = 'none';
  if (canvas) canvas.style.display = '';
  const labels  = data.map(d => d.date.slice(5));
  const kgs     = data.map(d => d.kg);
  const plabel  = _weightTrendPerson.toUpperCase();
  if (_wChart) {
    _wChart.data.labels = labels;
    _wChart.data.datasets[0].data = kgs;
    _wChart.data.datasets[0].label = `Peso ${plabel} (kg)`;
    _wChart.update();
    return;
  }
  if (typeof Chart === 'undefined') { setTimeout(updateWeightChart, 180); return; }
  _wChart = new Chart(canvas, {
    type:'line',
    data:{ labels, datasets:[{
      label:`Peso ${plabel} (kg)`, data:kgs,
      borderColor:'#ce6a6b', backgroundColor:'rgba(206,106,107,.08)',
      fill:true, tension:0.3, pointRadius:4, pointBackgroundColor:'#ce6a6b'
    }]},
    options:{ responsive:true,
      plugins:{ title:{display:false}, legend:{display:false} },
      scales:{ y:{beginAtZero:false} } }
  });
}

// ── 0. Body composition (Xiaomi scale) ───────────────────────────────────────
let _bcPerson    = 'atm';
let _bcChart     = null;
let _bcCompChart = null;

const _BC_META = {
  weight_kg:            { label:'Peso',              unit:'kg',   icon:'⚖️'  },
  body_fat_pct:         { label:'Grasa corporal',    unit:'%',    icon:'🫧'  },
  muscle_mass_kg:       { label:'Músculo',           unit:'kg',   icon:'💪'  },
  lean_mass_kg:         { label:'Masa magra',        unit:'kg',   icon:'🏋️' },
  bone_mass_kg:         { label:'Masa ósea',         unit:'kg',   icon:'🦴'  },
  water_pct:            { label:'Agua',              unit:'%',    icon:'💧'  },
  protein_pct:          { label:'Proteína',          unit:'%',    icon:'🥩'  },
  bmr:                  { label:'TMB',               unit:'kcal', icon:'🔥'  },
  visceral_fat:         { label:'Grasa visceral',    unit:'',     icon:'🫀'  },
  metabolic_age:        { label:'Edad metabólica',   unit:'años', icon:'🧬'  },
  bmi:                  { label:'IMC',               unit:'',     icon:'📊'  },
  fat_mass_kg:          { label:'Masa grasa',        unit:'kg',   icon:'📉'  },
  subcutaneous_fat_pct: { label:'G. subcutánea',     unit:'%',    icon:'📍'  },
  skeletal_muscle_pct:  { label:'Músculo esq.',      unit:'%',    icon:'🦵'  },
};

// 'up_good' = higher is better, 'down_good' = lower is better, 'neutral' = context
const _BC_DIR = {
  weight_kg:'neutral', bmi:'down_good', body_fat_pct:'down_good',
  fat_mass_kg:'down_good', muscle_mass_kg:'up_good', lean_mass_kg:'up_good',
  bone_mass_kg:'up_good', water_pct:'up_good', protein_pct:'up_good',
  bmr:'up_good', visceral_fat:'down_good', metabolic_age:'down_good',
  subcutaneous_fat_pct:'down_good', skeletal_muscle_pct:'up_good',
};

function _bcSortedHist(person) {
  return (TRACKING['body_comp_' + person] || [])
    .slice().sort((a,b) => (a.date||'').localeCompare(b.date||''));
}

function _bcDeltaBadge(metric, curr, prev) {
  if (prev == null || curr == null) return '';
  const diff = curr - prev;
  if (Math.abs(diff) < 0.05) return '<span class="bc-delta bc-delta-neu">→</span>';
  const dir    = _BC_DIR[metric] || 'neutral';
  const isGood = dir === 'neutral' ? null : dir === 'up_good' ? diff > 0 : diff < 0;
  const cls    = isGood === null ? 'bc-delta-neu' : isGood ? 'bc-delta-good' : 'bc-delta-bad';
  const arrow  = diff > 0 ? '↑' : '↓';
  const sign   = diff > 0 ? '+' : '';
  const fmt    = Math.abs(diff) < 10 ? diff.toFixed(1) : String(Math.round(diff));
  return `<span class="bc-delta ${cls}">${arrow} ${sign}${fmt}</span>`;
}

function initBodyComp() {
  const hasAtm = _bcSortedHist('atm').length > 0;
  const hasIob = _bcSortedHist('iob').length > 0;
  if (!hasAtm && !hasIob) return;
  document.getElementById('body-comp-card').style.display = '';
  if (!hasIob) document.querySelector('#bc-person-tabs button:last-child')?.style.setProperty('display','none');
  if (!hasAtm) {
    _bcPerson = 'iob';
    document.querySelector('#bc-person-tabs button:first-child')?.classList.remove('active');
    document.querySelector('#bc-person-tabs button:last-child')?.classList.add('active');
  }
  _renderAllBc();
  _waitChart(updateBcChart);
}

function setBcPerson(person, btn) {
  _bcPerson = person;
  document.querySelectorAll('#bc-person-tabs .toggle-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  if (_bcCompChart) { _bcCompChart.destroy(); _bcCompChart = null; }
  if (_bcChart)     { _bcChart.destroy();     _bcChart     = null; }
  _renderAllBc();
  _waitChart(updateBcChart);
}

function _renderAllBc() {
  const hist   = _bcSortedHist(_bcPerson);
  if (!hist.length) return;
  const latest = hist[hist.length - 1];
  const prev   = hist.length > 1 ? hist[hist.length - 2] : null;
  const lbl    = document.getElementById('bc-date-label');
  if (lbl) lbl.textContent = 'Última lectura: ' + latest.date;
  _renderBcHero(latest, prev);
  _waitChart(() => _renderBcCompBar(latest));
  _renderBcSecondary(latest, prev);
}

// Layer 1 — four hero metric cards
const _BC_HERO_KEYS = ['weight_kg', 'body_fat_pct', 'muscle_mass_kg', 'visceral_fat'];

function _renderBcHero(latest, prev) {
  const grid = document.getElementById('bc-hero');
  if (!grid) return;
  grid.innerHTML = _BC_HERO_KEYS.map(k => {
    if (latest[k] == null) return '';
    const m     = _BC_META[k];
    const val   = latest[k].toFixed(1);
    const delta = _bcDeltaBadge(k, latest[k], prev?.[k]);
    return `<div class="bc-hero">
      <div class="bc-hero-label">${m.label}</div>
      <div class="bc-hero-val">${val}<span class="bc-hero-unit"> ${m.unit}</span></div>
      ${delta}
    </div>`;
  }).join('');
}

// Layer 2 — horizontal stacked composition bar
function _renderBcCompBar(latest) {
  const canvas = document.getElementById('chart-bc-comp');
  if (!canvas) return;
  const fat    = latest.body_fat_pct || 0;
  let   muscle = latest.skeletal_muscle_pct;
  if (muscle == null && latest.muscle_mass_kg && latest.weight_kg)
    muscle = (latest.muscle_mass_kg / latest.weight_kg) * 100;
  muscle      = muscle || 0;
  const water = latest.water_pct || 0;
  const rest  = Math.max(0, 100 - fat - muscle - water);
  const datasets = [
    { label:'Grasa',   data:[fat],    backgroundColor:'#ce6a6b' },
    { label:'Músculo', data:[muscle], backgroundColor:'#4a919e' },
    { label:'Agua',    data:[water],  backgroundColor:'#bed3c3' },
    { label:'Otro',    data:[rest],   backgroundColor:'#ebaca2' },
  ].filter(d => d.data[0] > 0.5);
  if (_bcCompChart) { _bcCompChart.data.datasets = datasets; _bcCompChart.update(); return; }
  _bcCompChart = new Chart(canvas, {
    type: 'bar',
    data: { labels: [''], datasets },
    options: {
      indexAxis: 'y', responsive: true,
      scales: {
        x: { stacked:true, display:false, max:100 },
        y: { stacked:true, display:false }
      },
      plugins: {
        legend: { position:'bottom', labels:{ font:{size:10}, padding:10, boxWidth:12 } },
        tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${ctx.parsed.x.toFixed(1)}%` } }
      }
    }
  });
}

// Layer 4 — secondary metrics list
const _BC_SECONDARY = [
  'bmi','lean_mass_kg','bone_mass_kg','water_pct','protein_pct',
  'bmr','metabolic_age','fat_mass_kg','subcutaneous_fat_pct','skeletal_muscle_pct'
];

function _renderBcSecondary(latest, prev) {
  const el = document.getElementById('bc-secondary');
  if (!el) return;
  const rows = _BC_SECONDARY.filter(k => latest[k] != null).map(k => {
    const m     = _BC_META[k];
    const val   = latest[k].toFixed(1);
    const delta = _bcDeltaBadge(k, latest[k], prev?.[k]);
    return `<div class="bc-sec-row">
      <span class="bc-sec-name">${m.icon} ${m.label}</span>
      <div class="bc-sec-right">
        <span class="bc-sec-val">${val}<span style="font-weight:400;color:#718096;font-size:.72rem"> ${m.unit}</span></span>
        ${delta}
      </div>
    </div>`;
  });
  if (!rows.length) { el.style.display = 'none'; return; }
  el.innerHTML = `<div style="margin-top:.85rem;border-top:1px solid var(--navy-08);padding-top:.6rem">
    <span class="sec-label" style="display:block;margin-bottom:.4rem">Métricas adicionales</span>
    ${rows.join('')}
  </div>`;
}

// Layer 3 — trend line chart
function updateBcChart() {
  if (typeof Chart === 'undefined') { setTimeout(updateBcChart, 180); return; }
  const metric = document.getElementById('bc-metric')?.value || 'weight_kg';
  const hist   = _bcSortedHist(_bcPerson).filter(r => r[metric] != null);
  const canvas = document.getElementById('chart-bc-trend');
  if (!canvas) return;
  const m      = _BC_META[metric] || { label:metric, unit:'' };
  const labels = hist.map(r => r.date ? r.date.slice(5) : '');
  const vals   = hist.map(r => r[metric]);
  const dir    = _BC_DIR[metric] || 'neutral';
  const color  = dir === 'down_good' ? '#ce6a6b' : dir === 'up_good' ? '#4a919e' : '#bed3c3';
  if (_bcChart) {
    _bcChart.data.labels = labels;
    _bcChart.data.datasets[0].data   = vals;
    _bcChart.data.datasets[0].label  = `${m.label}${m.unit ? ' (' + m.unit + ')' : ''}`;
    _bcChart.data.datasets[0].borderColor        = color;
    _bcChart.data.datasets[0].pointBackgroundColor = color;
    _bcChart.data.datasets[0].backgroundColor    = color + '14';
    _bcChart.update();
    return;
  }
  _bcChart = new Chart(canvas, {
    type: 'line',
    data: { labels, datasets: [{ label:`${m.label}${m.unit ? ' (' + m.unit + ')' : ''}`,
      data:vals, borderColor:color, backgroundColor:color+'14',
      fill:true, tension:0.3, pointRadius:3, pointBackgroundColor:color }] },
    options: { responsive:true,
      plugins:{ legend:{display:false} },
      scales:{ y:{beginAtZero:false} } }
  });
}
</script>
</body>
</html>"""
