# Nutrición

AI-powered weekly meal planner. Reads diet PDFs from your nutritionist, generates menus, shopping lists, recipes, and a meal prep schedule, and publishes everything to a GitHub Pages site.

## First-time setup

```bash
bash setup.sh
source venv/bin/activate
# Add your ANTHROPIC_API_KEY to .env
```

---

## Typical weekly workflow

### 1. Parse new diet PDFs
Drop the PDFs from your nutritionist into `Dietas/` (naming: `YYYYMMDD_ATM.pdf`, `YYYYMMDD_IOB.pdf`), then:
```bash
python main.py parsear-dietas           # both people
python main.py parsear-dietas --persona ATM   # one person only
```
Outputs parsed YAML files to `config/parsed_diets/`.

### 2. Generate everything for the week
```bash
python main.py semana-completa
```
This runs all four generation steps in order: menu → shopping list → recipes → meal prep.

### 3. Publish the site
```bash
bash actualizar_site.sh
```
Imports ratings, rebuilds the static site in `docs/`, commits, and pushes to GitHub Pages.  
Live at: **https://adanttmm.github.io/nutricion/**

---

## Step-by-step commands (run individually)

```bash
# Parse PDFs
python main.py parsear-dietas [--persona ATM|IOB]

# Generate outputs — all accept --plan and --semana overrides
python main.py generar-menu      [--plan config/parsed_diets/combined_YYYYMMDD.yaml] [--semana YYYY-MM-DD]
python main.py generar-compras   --menu outputs/menus/menu_YYYY-MM-DD.md
python main.py generar-recetas   --menu outputs/menus/menu_YYYY-MM-DD.md
python main.py planear-prep      --menu outputs/menus/menu_YYYY-MM-DD.md [--recetas outputs/recipes/recetas_YYYY-MM-DD.md]

# Single recipe lookup
python main.py receta "Salmón en costra de hierbas"

# Validation — audit generated outputs against the diet plan
python main.py validar-menu      --menu outputs/menus/menu_YYYY-MM-DD.md
python main.py verificar-compras --compras outputs/shopping/compras_YYYY-MM-DD.md
python main.py verificar-prep    --prep outputs/meal_prep/meal_prep_YYYY-MM-DD.md

# Site
python main.py generar-sitio    # rebuilds docs/ only (no git push)
python main.py importar-ratings # pulls ratings saved from the web UI into the DB
```

---

## Special instructions for the week (`--nota`)

Pass one-off constraints directly into the AI prompt for any generation step. The note is not saved — it only applies to that run.

```bash
# Full week with a note
python main.py semana-completa --nota "Hay sobras de pollo del martes. El jueves cenamos fuera. Evitar mariscos esta semana."

# Individual steps
python main.py generar-menu --nota "Tiempo limitado entre semana, preferir técnicas rápidas. Hay camote sobrante."
python main.py planear-prep --menu outputs/menus/menu_YYYY-MM-DD.md --nota "El domingo salgo a las 2pm, el prep tiene que terminar antes."
```

Use it for: leftover ingredients, schedule changes, missing appliances, dietary adjustments, or any constraint specific to that week.

---

## Body composition imports (manual)

```bash
# From a Mi Fitness JSON export file
python main.py importar-mifitness --archivo export.json --persona ATM

# From a Xiaomi Smart Scale CSV export
python main.py importar-smartscale --archivo export.csv --persona IOB
```

---

## Site features

The static site (`docs/`) shows:
- **Weekly menu** — per-day meal cards with expandable recipe instructions
  - Each recipe card shows cooked quantities (for serving reference)
  - Clicking the recipe shows a raw ingredient table (quantities weighed raw, per person)
- **Meal prep tab** — weekly raw ingredient totals table + all prep steps extracted from recipes
- **Trends tab** — weight history, macro trends
- **Ratings** — star ratings saved locally and synced to the DB via `importar-ratings`

---

## Lunch rotation

Lunch is planned as **3 unique dishes rotating all week**:
- Variant A: Monday + Thursday (same dish)
- Variant B: Tuesday + Friday (same dish)
- Variant C: Wednesday + Saturday + Sunday (same dish — zero extra cooking on weekends)

---

## File naming convention

```
Dietas/YYYYMMDD_INICIALES.pdf
  e.g.  20260609_ATM.pdf   ← Adán's diet plan for week of June 9
        20260609_IOB.pdf   ← IOB's plan or body composition
```

The parser always picks the most recent file per person (by date in filename).

---

## Key output locations

```
outputs/menus/       menu_YYYY-MM-DD.md
outputs/shopping/    compras_YYYY-MM-DD.md
outputs/recipes/     recetas_YYYY-MM-DD.md
outputs/meal_prep/   meal_prep_YYYY-MM-DD.md
docs/                static site (committed to GitHub)
data/                SQLite DB + ratings
config/parsed_diets/ parsed diet YAMLs
```

## SQLite database exploration

```
sqlitebrowser /home/adan/Documentos/Nutricion/data/tracking/nutricion.db
```
