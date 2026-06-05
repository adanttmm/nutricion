# Nutrición

AI-powered weekly meal planner. Reads diet PDFs from your nutritionist, generates menus, shopping lists, recipes, and a meal prep schedule, and publishes everything to a GitHub Pages site.

## Weekly workflow

1. Drop the new PDFs into `Dietas/` — name them like `20260609_ATM.pdf`
2. Parse the PDFs:
   ```bash
   python main.py parsear-dietas
   ```
3. Generate everything for the week:
   ```bash
   python main.py semana-completa
   ```
4. Rebuild and publish the site:
   ```bash
   python main.py generar-sitio
   git add docs/ && git commit -m "update week" && git push
   ```
5. View it at **https://adanttmm.github.io/nutricion/** (Ctrl+Shift+R to refresh)

## First-time setup

```bash
bash setup.sh
source venv/bin/activate
# Add your ANTHROPIC_API_KEY to .env
```

## Other useful commands

```bash
# Parse only one person
python main.py parsear-dietas --persona ATM

# Run steps individually
python main.py generar-menu
python main.py generar-compras  --menu outputs/menus/menu_YYYY-MM-DD.md
python main.py generar-recetas  --menu outputs/menus/menu_YYYY-MM-DD.md
python main.py planear-prep     --menu outputs/menus/menu_YYYY-MM-DD.md

# Look up a single recipe
python main.py receta "Salmón en costra de hierbas"

# Daily tracking
python main.py registrar
python main.py resumen
python main.py peso --kg 80.5
```

## Site features

- **Semana tab** — click any day (Lun–Dom) to see the menu and recipes for that day
- **Recipes** — rate dishes with ★ stars and tag as ❤️ fav / 🔄 repetir / 🚫 no (saved in browser)
- **Resumen tab** — shows your favorited and top-rated recipes
- **Compras tab** — Costco and City Market checklists with persistent checkboxes
