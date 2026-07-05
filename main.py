#!/usr/bin/env python3
"""
Asistente Nutricional — CLI principal
Uso: python main.py --help
"""
import atexit
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from pathlib import Path
from datetime import date

console = Console()

# Print token/cost summary whenever this process used the API
def _print_token_summary():
    from skills import token_tracker
    token_tracker.print_summary()

atexit.register(_print_token_summary)


@click.group()
def cli():
    """🥗 Asistente Nutricional · Menús · Compras · Recetas · Meal Prep · Seguimiento"""
    pass


@cli.command("parsear-dietas")
@click.option("--dietas-dir", "-d", default="Dietas",
              help="Carpeta con los PDFs del nutriólogo (default: Dietas/)")
@click.option("--persona", "-p", default=None,
              help="Parsear solo a una persona (ej: ATM). Default: todas.")
def parsear_dietas(dietas_dir, persona):
    """Lee los PDFs del nutriólogo en ./Dietas/ y genera YAMLs estructurados con calorías calculadas."""
    from skills.diet_parser import DietParserSkill
    from rich.table import Table as RTable

    parser = DietParserSkill()

    with console.status("[bold]Buscando archivos en la carpeta Dietas/...", spinner="dots"):
        diets = parser.find_latest_diets(dietas_dir)

    if not diets:
        console.print("[yellow]No se encontraron archivos con el formato YYYYMMDD_INICIALES.pdf[/yellow]")
        return

    if persona:
        persona = persona.upper()
        if persona not in diets:
            console.print(f"[red]No se encontró archivo para '{persona}'. Disponibles: {list(diets.keys())}[/red]")
            return
        diets = {persona: diets[persona]}

    table = RTable(title="Archivos encontrados", show_lines=True)
    table.add_column("Persona", style="cyan")
    table.add_column("Archivo", style="white")
    for p, path in diets.items():
        table.add_row(p, str(path))
    console.print(table)

    parsed_paths = {}
    for person, pdf_path in diets.items():
        with console.status(f"[bold green]Parseando {person} ({pdf_path.name}) con Claude Vision...", spinner="dots"):
            try:
                out = parser.parse_pdf(str(pdf_path))
                parsed_paths[person] = out
                console.print(f"  [green]✅[/green] {person}: {out}")
            except Exception as e:
                console.print(f"  [red]❌ Error parseando {person}: {e}[/red]")

    if len(parsed_paths) == 0:
        console.print("[red]No se pudo parsear ningún archivo.[/red]")
        return

    with console.status("[bold blue]Creando plan combinado...", spinner="dots"):
        try:
            combined = parser.create_combined_plan(parsed_paths)
            console.print(f"\n[green]✅ Plan combinado:[/green] [bold]{combined}[/bold]")
        except ValueError as e:
            console.print(f"[yellow]⚠️  Plan combinado no generado: {e}[/yellow]")
            combined = None

    console.print(Panel(
        "\n".join(f"• {p}: {path}" for p, path in parsed_paths.items())
        + (f"\n• Combined: [bold]{combined}[/bold]" if combined else ""),
        title="[bold green]✅ Dietas parseadas[/bold green]",
        border_style="green",
    ))
    console.print(
        "\n💡 Siguiente paso:\n"
        f"   [yellow]python main.py semana-completa --plan {combined or list(parsed_paths.values())[0]}[/yellow]"
    )


def _find_latest_combined_plan() -> str | None:
    """Return path to the most recently generated combined plan, or None."""
    parsed_dir = Path("config/parsed_diets")
    if not parsed_dir.exists():
        return None
    candidates = sorted(parsed_dir.glob("combined_*.yaml"), reverse=True)
    if candidates:
        return str(candidates[0])
    candidates = sorted(parsed_dir.glob("*.yaml"), reverse=True)
    return str(candidates[0]) if candidates else None


def _find_latest_output(subdir: str, pattern: str) -> str | None:
    """Return the most recent file matching pattern in outputs/<subdir>/."""
    p = Path("outputs") / subdir
    candidates = sorted(p.glob(pattern), reverse=True) if p.exists() else []
    return str(candidates[0]) if candidates else None


@cli.command("generar-menu")
@click.option("--plan", "-p", default="config/diet_plan_example.yaml",
              help="Ruta al plan nutricional (YAML)")
@click.option("--semana", "-s", default=None,
              help="Lunes de la semana a generar (YYYY-MM-DD). Default: próximo lunes.")
@click.option("--nota", "-n", default="",
              help="Indicaciones especiales para esta semana (sobras, tiempo disponible, equipos, etc.)")
def generar_menu(plan, semana, nota):
    """Genera el menú de la semana a partir del plan nutricional."""
    from skills.menu_generator import MenuGeneratorSkill

    week_start = date.fromisoformat(semana) if semana else None
    with console.status("[bold green]Generando menú con IA...", spinner="dots"):
        output = MenuGeneratorSkill().generate(plan, week_start, week_notes=nota)
    console.print(Panel(
        f"[green]✅ Menú generado[/green]\n\n"
        f"📄 [bold]{output}[/bold]\n\n"
        f"Siguiente: [yellow]python main.py generar-compras --menu {output}[/yellow]",
        title="Menú Semanal", border_style="green",
    ))


@cli.command("generar-compras")
@click.option("--menu", "-m", default=None, help="Ruta al menú (default: el más reciente en outputs/menus/)")
@click.option("--recetas", "-r", default=None, help="Ruta al recetario (default: el más reciente en outputs/recipes/)")
@click.option("--prep", "-p", default=None, help="Ruta al plan de meal prep (default: el más reciente en outputs/meal_prep/)")
def generar_compras(menu, recetas, prep):
    """Genera la lista de compras semanal ordenada alfabéticamente."""
    from skills.shopping_list import ShoppingListSkill

    menu    = menu    or _find_latest_output("menus",     "menu_*.md")
    recetas = recetas or _find_latest_output("recipes",   "recetas_*.md")
    prep    = prep    or _find_latest_output("meal_prep", "meal_prep_*.md")
    if not menu:
        console.print("[red]No se encontró ningún menú. Genera uno primero con 'generar-menu'.[/red]")
        raise SystemExit(1)
    console.print(f"[dim]Usando menú: {menu}[/dim]")
    if recetas:
        console.print(f"[dim]Usando recetas: {recetas}[/dim]")
    if prep:
        console.print(f"[dim]Usando meal prep: {prep}[/dim]")

    with console.status("[bold blue]Generando lista de compras...", spinner="dots"):
        output = ShoppingListSkill().generate(menu, recetas, prep)
    console.print(Panel(
        f"[green]✅ Lista de compras generada[/green]\n\n📄 [bold]{output}[/bold]",
        title="Lista de Compras", border_style="blue",
    ))


@cli.command("verificar-compras")
@click.option("--compras", "-c", default=None, help="Ruta a la lista de compras (default: la más reciente)")
def verificar_compras(compras):
    """Verifica que cada ingrediente esté en la tienda correcta; sugiere Mercado Libre o Amazon si no."""
    from skills.shopping_validator import ShoppingValidatorSkill

    compras = compras or _find_latest_output("shopping", "compras_*.md")
    if not compras:
        console.print("[red]No se encontró ninguna lista. Genera una primero con 'generar-compras'.[/red]")
        raise SystemExit(1)
    console.print(f"[dim]Verificando: {compras}[/dim]")

    with console.status("[bold cyan]Verificando asignaciones de tienda...", spinner="dots"):
        output = ShoppingValidatorSkill().validate(compras)
    console.print(Panel(
        f"[green]✅ Lista verificada y corregida[/green]\n\n📄 [bold]{output}[/bold]",
        title="Verificación de Compras", border_style="cyan",
    ))


@cli.command("generar-recetas")
@click.option("--menu", "-m", default=None, help="Ruta al menú (default: el más reciente en outputs/menus/)")
def generar_recetas(menu):
    """Genera el recetario completo con instrucciones y links de video."""
    from skills.recipe_finder import RecipeFinderSkill

    menu = menu or _find_latest_output("menus", "menu_*.md")
    if not menu:
        console.print("[red]No se encontró ningún menú. Genera uno primero con 'generar-menu'.[/red]")
        raise SystemExit(1)
    console.print(f"[dim]Usando menú: {menu}[/dim]")

    with console.status("[bold yellow]Generando recetas...", spinner="dots"):
        output = RecipeFinderSkill().generate_for_menu(menu)
    console.print(Panel(
        f"[green]✅ Recetario generado[/green]\n\n"
        f"📄 [bold]{output}[/bold]\n\n"
        f"Siguiente: [yellow]python main.py planear-prep --recetas {output}[/yellow]",
        title="Recetario", border_style="yellow",
    ))


@cli.command("planear-prep")
@click.option("--menu", "-m", default=None, help="Ruta al menú (default: el más reciente en outputs/menus/)")
@click.option("--recetas", "-r", default=None, help="Ruta al recetario (default: el más reciente en outputs/recipes/)")
@click.option("--nota", "-n", default="",
              help="Indicaciones especiales para esta semana (sobras, tiempo disponible, etc.)")
def planear_prep(menu, recetas, nota):
    """Crea el cronograma de meal prep para el fin de semana."""
    from skills.meal_prep_planner import MealPrepPlannerSkill

    menu    = menu    or _find_latest_output("menus",   "menu_*.md")
    recetas = recetas or _find_latest_output("recipes", "recetas_*.md")
    if not menu:
        console.print("[red]No se encontró ningún menú. Genera uno primero con 'generar-menu'.[/red]")
        raise SystemExit(1)
    console.print(f"[dim]Usando menú: {menu}[/dim]")
    if recetas:
        console.print(f"[dim]Usando recetas: {recetas}[/dim]")

    with console.status("[bold magenta]Creando plan de meal prep...", spinner="dots"):
        output = MealPrepPlannerSkill().generate(menu, recetas, week_notes=nota)
    console.print(Panel(
        f"[green]✅ Plan de meal prep listo[/green]\n\n📄 [bold]{output}[/bold]",
        title="Meal Prep", border_style="magenta",
    ))


@cli.command("validar-menu")
@click.option("--plan", "-p", default=None,
              help="Ruta al plan nutricional YAML (default: el más reciente en config/parsed_diets/)")
@click.option("--menu", "-m", default=None,
              help="Ruta al menú (default: el más reciente en outputs/menus/)")
def validar_menu(plan, menu):
    """Audita el menú semanal contra el plan nutricional del nutriólogo. Muestra tabla de cumplimiento."""
    from skills.menu_validator import MenuValidatorSkill

    plan = plan or _find_latest_combined_plan() or "config/diet_plan_example.yaml"
    menu = menu or _find_latest_output("menus", "menu_*.md")
    if not menu:
        console.print("[red]No se encontró ningún menú. Genera uno primero con 'generar-menu'.[/red]")
        raise SystemExit(1)

    console.print(f"[dim]Plan: {plan}[/dim]")
    console.print(f"[dim]Menú: {menu}[/dim]")

    with console.status("[yellow]Auditando calorías y macronutrientes...", spinner="dots"):
        result = MenuValidatorSkill().validate(plan, menu)

    color = "green" if result.passed else "red"
    icon  = "✅" if result.passed else "❌"
    console.print(Panel(
        result.report,
        title=f"[{color}]{icon} Auditoría Nutricional[/{color}]",
        border_style=color,
    ))
    if not result.passed and result.feedback:
        console.print(Panel(
            result.feedback,
            title="[yellow]Correcciones para el generador[/yellow]",
            border_style="yellow",
        ))


@cli.command("semana-completa")
@click.option("--plan", "-p", default=None,
              help="Ruta al plan nutricional YAML. Si se omite, usa el plan más reciente parseado del nutriólogo.")
@click.option("--semana", "-s", default=None, help="Lunes de la semana (YYYY-MM-DD)")
@click.option("--sin-sitio", is_flag=True, default=False, help="Omite la generación del sitio web.")
@click.option("--nota", "-n", default="",
              help="Indicaciones especiales para esta semana (sobras, tiempo disponible, ingredientes extra, etc.)")
def semana_completa(plan, semana, sin_sitio, nota):
    """Genera TODO de una vez: menú · compras · recetas · plan de prep.

    Si no se especifica --plan, busca automáticamente el último plan parseado en
    config/parsed_diets/. Si no hay ninguno, usa config/diet_plan_example.yaml.
    """
    from skills.menu_generator import MenuGeneratorSkill
    from skills.shopping_list import ShoppingListSkill
    from skills.recipe_finder import RecipeFinderSkill
    from skills.meal_prep_planner import MealPrepPlannerSkill
    from skills.ratings_loader import RatingsLoader

    # Auto-detect plan
    if plan is None:
        plan = _find_latest_combined_plan() or "config/diet_plan_example.yaml"
        console.print(f"[dim]Usando plan: {plan}[/dim]")

    week_start = date.fromisoformat(semana) if semana else None
    outputs = {}

    from skills.menu_validator import MenuValidatorSkill

    console.print(Panel("🚀 Generando paquete completo para la semana...", border_style="bold green"))

    # Load ratings — ingest any pending files first, then build context
    ratings_loader = RatingsLoader()
    n_new = ratings_loader.ingest_pending()
    ratings_context = ratings_loader.build_menu_context()
    if ratings_context:
        s = ratings_loader.summary()
        console.print(
            f"  [cyan]⭐[/cyan] Valoraciones cargadas — "
            f"{s['favorites']} favoritos · {s['avoid']} a evitar "
            f"({s['weeks_ingested']} semanas)"
        )
    elif n_new == 0:
        console.print("  [dim]⭐ Sin valoraciones previas — omitiendo contexto[/dim]")

    if nota:
        console.print(f"  [cyan]📋[/cyan] Nota de semana: [dim]{nota[:120]}{'…' if len(nota) > 120 else ''}[/dim]")

    MAX_MENU_RETRIES = 3
    feedback = ""
    for attempt in range(MAX_MENU_RETRIES):
        attempt_label = "1/5 · Menú semanal" if attempt == 0 else f"  ↺ Corrección #{attempt} · Menú"
        with console.status(f"[green]{attempt_label}...", spinner="dots"):
            outputs["menu"] = MenuGeneratorSkill().generate(
                plan, week_start, feedback=feedback, ratings_context=ratings_context, week_notes=nota
            )
        console.print(f"  [green]✅[/green] Menú generado (intento {attempt + 1}/{MAX_MENU_RETRIES}): {outputs['menu']}")

        with console.status("[yellow]  Validando calorías y macros...", spinner="dots"):
            val = MenuValidatorSkill().validate(plan, str(outputs["menu"]))

        if val.passed:
            console.print("  [green]✅[/green] Menú validado — calorías y macros dentro de tolerancia")
            break

        console.print(f"  [yellow]⚠️[/yellow]  Menú rechazado (intento {attempt + 1}/{MAX_MENU_RETRIES})")
        console.print(Panel(val.report, title="[yellow]Auditoría nutricional[/yellow]", border_style="yellow"))
        feedback = val.feedback

        if attempt == MAX_MENU_RETRIES - 1:
            console.print(
                "[red]❌ No se pudo validar el menú en 3 intentos. "
                "Se usará el último generado — revisa manualmente.[/red]"
            )

    with console.status("[yellow]2/5 · Recetario...", spinner="dots"):
        outputs["recetas"] = RecipeFinderSkill().generate_for_menu(str(outputs["menu"]), week_start)
    console.print(f"  [green]✅[/green] Recetas: {outputs['recetas']}")

    # Meal prep before shopping so all sauce/marinade ingredients are captured
    with console.status("[magenta]3/5 · Plan de meal prep...", spinner="dots"):
        outputs["prep"] = MealPrepPlannerSkill().generate(
            str(outputs["menu"]), str(outputs["recetas"]), week_notes=nota
        )
    console.print(f"  [green]✅[/green] Meal prep: {outputs['prep']}")

    with console.status("[blue]4/5 · Lista de compras...", spinner="dots"):
        outputs["compras"] = ShoppingListSkill().generate(
            str(outputs["menu"]), str(outputs["recetas"]), str(outputs["prep"])
        )
    console.print(f"  [green]✅[/green] Compras: {outputs['compras']}")

    if not sin_sitio:
        with console.status("[cyan]5/5 · Sitio web...", spinner="dots"):
            from skills.site_builder import SiteBuilderSkill
            site_output = SiteBuilderSkill().build(week_start)
        console.print(f"  [green]✅[/green] Sitio: {site_output}")
        site_line = f"\n• Sitio: [bold]{site_output}[/bold]"
    else:
        console.print("  [dim]⏭  Sitio omitido (--sin-sitio)[/dim]")
        site_line = ""

    console.print(Panel(
        "\n".join(f"• {k.capitalize()}: [bold]{v}[/bold]" for k, v in outputs.items())
        + site_line,
        title="[bold green]¡Semana lista! 🎉[/bold green]",
        border_style="green",
    ))


@cli.command("verificar-prep")
@click.option("--menu", "-m", default=None, help="Ruta al menú (default: el más reciente)")
@click.option("--prep", "-p", default=None, help="Ruta al plan de meal prep (default: el más reciente)")
@click.option("--recetas", "-r", default=None, help="Ruta al recetario (default: el más reciente)")
def verificar_prep(menu, prep, recetas):
    """Audita el plan de meal prep y verifica que esté alineado con el menú de la semana."""
    from skills.meal_prep_validator import MealPrepValidatorSkill

    menu    = menu    or _find_latest_output("menus",     "menu_*.md")
    prep    = prep    or _find_latest_output("meal_prep", "meal_prep_*.md")
    recetas = recetas or _find_latest_output("recipes",   "recetas_*.md")

    if not menu or not prep:
        console.print("[red]Se necesita un menú y un plan de prep. Genera ambos primero.[/red]")
        raise SystemExit(1)

    console.print(f"[dim]Menú: {menu}[/dim]")
    console.print(f"[dim]Meal prep: {prep}[/dim]")
    if recetas:
        console.print(f"[dim]Recetas: {recetas}[/dim]")

    with console.status("[bold cyan]Auditando plan de meal prep...", spinner="dots"):
        report = MealPrepValidatorSkill().validate(menu, prep, recetas)

    console.print(Panel(report, title="[bold cyan]🔍 Auditoría del Meal Prep[/bold cyan]", border_style="cyan"))


@cli.command("importar-ratings")
@click.argument("archivo", required=False, default=None,
                metavar="[ARCHIVO]",
                type=click.Path(exists=False))
def importar_ratings(archivo):
    """Ingresa valoraciones exportadas desde el sitio web.

    Sin argumentos escanea data/ratings/ratings_*.json.
    Con ARCHIVO copia el JSON indicado a data/ratings/ y lo procesa.
    """
    from skills.ratings_loader import RatingsLoader
    from pathlib import Path
    import shutil

    loader = RatingsLoader()

    if archivo:
        src = Path(archivo)
        if not src.exists():
            console.print(f"[red]Archivo no encontrado: {archivo}[/red]")
            raise SystemExit(1)
        dest = Path("data/ratings") / src.name
        shutil.copy2(src, dest)
        console.print(f"[dim]Copiado a {dest}[/dim]")

    with console.status("[cyan]Ingresando valoraciones...", spinner="dots"):
        n = loader.ingest_pending()

    if n == 0:
        console.print("[yellow]Sin archivos nuevos en data/ratings/.[/yellow]")
        console.print("  Exporta las valoraciones desde el sitio web y coloca el JSON en data/ratings/")
    else:
        s = loader.summary()
        console.print(Panel(
            f"[green]✅ {n} archivo(s) procesado(s)[/green]\n\n"
            f"Platos en historial : [bold]{s['total_dishes']}[/bold]\n"
            f"Favoritos / repetir : [bold]{s['favorites']}[/bold]\n"
            f"A evitar            : [bold]{s['avoid']}[/bold]\n"
            f"Semanas registradas : [bold]{s['weeks_ingested']}[/bold]\n"
            f"Última actualización: [bold]{s['last_updated']}[/bold]\n\n"
            "El contexto de valoraciones se aplicará al próximo menú generado.",
            title="[cyan]⭐ Valoraciones importadas[/cyan]",
            border_style="cyan",
        ))


@cli.command("importar-mifitness")
@click.argument("archivo", type=click.Path(exists=True))
@click.option("--persona", "-p", default="ATM",
              type=click.Choice(["ATM", "IOB"], case_sensitive=False),
              help="Persona a quien pertenecen los datos (default: ATM)")
@click.option("--dry-run", is_flag=True, default=False,
              help="Muestra qué se importaría sin escribir a la base de datos")
def importar_mifitness(archivo, persona, dry_run):
    """Importa composición corporal desde un export de Mi Fitness / Zepp Life.

    ARCHIVO puede ser un .zip (export completo) o un .json suelto.

    Cómo exportar desde la app:
      Mi Fitness  → Perfil → Ajustes → Cuenta → Exportar datos de salud
      Zepp Life   → Perfil → Mi cuenta → Privacidad → Exportar datos
      Mi Home     → account.xiaomi.com → Privacidad → Gestionar datos
    """
    from skills.mifitness_importer import MiFitnessImporter
    from pathlib import Path

    importer = MiFitnessImporter()
    path = Path(archivo)
    action = "[yellow]SIMULACIÓN[/yellow] —" if dry_run else ""

    try:
        with console.status(f"[cyan]{action} Leyendo {path.name}...", spinner="dots"):
            if path.suffix.lower() == '.zip':
                result = importer.import_zip(path, person=persona, dry_run=dry_run)
            else:
                result = importer.import_json(path, person=persona, dry_run=dry_run)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]❌ {e}[/red]")
        raise SystemExit(1)
    finally:
        importer.close()

    total    = result['total']
    imported = result['imported']
    skipped  = result['skipped']
    errors   = result['errors']

    if dry_run and result.get('records'):
        console.print(f"\n[yellow]Vista previa — {total} registros encontrados:[/yellow]\n")
        for rec in result['records'][:10]:
            console.print(MiFitnessImporter.format_record(rec))
            console.print()
        if total > 10:
            console.print(f"  [dim]... y {total - 10} más[/dim]\n")
        console.print(f"[dim]Ejecuta sin --dry-run para importar a la base de datos.[/dim]")
        return

    if errors:
        console.print(f"[yellow]⚠ {len(errors)} error(es):[/yellow]")
        for e in errors[:5]:
            console.print(f"  [dim]{e}[/dim]")

    if imported == 0:
        console.print("[yellow]Sin registros nuevos para importar.[/yellow]")
        return

    console.print(Panel(
        f"[green]✅ {imported} medición(es) importadas para [bold]{persona}[/bold][/green]\n\n"
        f"Total encontrados : [bold]{total}[/bold]\n"
        f"Importados        : [bold]{imported}[/bold]\n"
        f"Errores/omitidos  : [bold]{skipped}[/bold]\n\n"
        "Reconstruye el sitio para ver las métricas en Seguimiento:\n"
        "  [yellow]bash actualizar_site.sh[/yellow]",
        title="[cyan]⚖️  Composición Corporal importada[/cyan]",
        border_style="cyan",
    ))




@cli.command("sincronizar-xiaomi")
@click.option("--persona", "-p", default="ATM",
              type=click.Choice(["ATM", "IOB"], case_sensitive=False))
@click.option("--region", "-r", default=None,
              help="Región Xiaomi: cn, us, eu, sg (default: usa XIAOMI_REGION de .env o cn)")
@click.option("--dias", "-d", default=180, type=int,
              help="Días de historial a importar (default: 180)")
@click.option("--dry-run", is_flag=True, default=False)
@click.option("--forzar-login", is_flag=True, default=False,
              help="Ignorar token cacheado y re-autenticar")
def sincronizar_xiaomi(persona, region, dias, dry_run, forzar_login):
    """Descarga composición corporal desde Mi Fitness cloud (sin Docker)."""
    import os
    from skills.xiaomi_sync import XiaomiSyncClient

    email = os.environ.get("XIAOMI_EMAIL", "")
    password = os.environ.get("XIAOMI_PASSWORD", "")
    region = region or os.environ.get("XIAOMI_REGION", "cn")

    if not email or not password:
        console.print("[red]Falta XIAOMI_EMAIL o XIAOMI_PASSWORD en .env[/red]")
        raise SystemExit(1)

    client = XiaomiSyncClient(email, password, region=region)

    with console.status("[cyan]Autenticando con Xiaomi...", spinner="dots"):
        try:
            client.login(force=forzar_login)
        except ValueError as e:
            console.print(f"[red]❌ {e}[/red]")
            raise SystemExit(1)

    console.print(f"  [green]✅[/green] Autenticado (user_id: {client.user_id})")

    with console.status(f"[cyan]Descargando registros ({dias} días)...", spinner="dots"):
        records = client.get_weight_records(days_back=dias)

    if not records:
        console.print("[yellow]Sin registros de composición corporal en Mi Fitness.[/yellow]")
        console.print(f"  [dim]Región: {region} · user_id: {client.user_id}[/dim]")
        console.print("  Prueba --region cn, --region us o --forzar-login")
        return

    console.print(f"  [green]✅[/green] {len(records)} registro(s) encontrados")

    if dry_run:
        console.print("\n[yellow]Vista previa (--dry-run, sin guardar):[/yellow]\n")
        from skills.smartscale_importer import SmartScaleImporter
        for rec in records[:10]:
            console.print(SmartScaleImporter.format_record(rec))
            console.print()
        if len(records) > 10:
            console.print(f"  [dim]... y {len(records) - 10} más[/dim]")
        return

    from tracker.daily_log import DailyLog
    log = DailyLog()
    imported = skipped = 0
    for rec in records:
        try:
            log.log_body_composition(rec, person=persona.upper(), source="xiaomi_cloud")
            imported += 1
        except Exception:
            skipped += 1
    log.close()

    console.print(f"  [green]✅[/green] {imported} importados · {skipped} duplicados/errores")


@cli.command("importar-smartscale")
@click.argument("archivo", default="-")
@click.option("--persona", "-p", default="ATM",
              type=click.Choice(["ATM", "IOB"], case_sensitive=False),
              help="Persona a quien pertenecen los datos (default: ATM)")
@click.option("--dry-run", is_flag=True, default=False,
              help="Muestra qué se importaría sin guardar en la base de datos")
def importar_smartscale(archivo, persona, dry_run):
    """Importa composición corporal desde SmartScaleConnect (Xiaomi Home).

    ARCHIVO es la ruta al JSON exportado, o '-' para leer desde stdin.
    Úsalo junto con actualizar_xiaomi.sh que descarga el JSON vía Docker.
    """
    import sys
    from skills.smartscale_importer import SmartScaleImporter

    importer = SmartScaleImporter()
    action = "[yellow]SIMULACIÓN[/yellow] —" if dry_run else ""

    try:
        with console.status(f"[cyan]{action} Leyendo datos Xiaomi...", spinner="dots"):
            data = sys.stdin.read() if archivo == "-" else Path(archivo).read_text()
            result = importer.import_json_str(data, person=persona, dry_run=dry_run)
    except Exception as e:
        console.print(f"[red]❌ {e}[/red]")
        raise SystemExit(1)
    finally:
        importer.close()

    if dry_run and result.get('records'):
        console.print(f"\n[yellow]Vista previa — {result['normalized']} registros normalizados:[/yellow]\n")
        for rec in result['records'][:10]:
            console.print(SmartScaleImporter.format_record(rec))
            console.print()
        if result['total'] > 10:
            console.print(f"  [dim]... y {result['total'] - 10} más[/dim]\n")
        console.print("[dim]Ejecuta sin --dry-run para importar.[/dim]")
        return

    if result.get('errors'):
        console.print(f"[yellow]⚠ {len(result['errors'])} error(es):[/yellow]")
        for e in result['errors'][:5]:
            console.print(f"  [dim]{e}[/dim]")

    if result['imported'] == 0:
        console.print("[yellow]Sin registros nuevos para importar.[/yellow]")
        return

    console.print(Panel(
        f"[green]✅ {result['imported']} medición(es) importadas para [bold]{persona}[/bold][/green]\n\n"
        f"Recibidos     : [bold]{result['total']}[/bold]\n"
        f"Normalizados  : [bold]{result['normalized']}[/bold]\n"
        f"Importados    : [bold]{result['imported']}[/bold]\n"
        f"Errores       : [bold]{result['skipped']}[/bold]\n\n"
        "Reconstruye el sitio para ver las métricas:\n"
        "  [yellow]bash actualizar_site.sh[/yellow]",
        title="[cyan]⚖️  Xiaomi Home importado[/cyan]",
        border_style="cyan",
    ))


@cli.command("importar-xiaomi-zip")
@click.argument("archivo")
@click.option("--persona", "-p", default="ATM",
              type=click.Choice(["ATM", "IOB"], case_sensitive=False),
              help="Persona a quien pertenecen los datos (default: ATM)")
@click.option("--dry-run", is_flag=True, default=False,
              help="Muestra qué se importaría sin guardar en la base de datos")
def importar_xiaomi_zip(archivo, persona, dry_run):
    """Importa composición corporal desde el ZIP de exportación de Xiaomi.

    ARCHIVO es la ruta al ZIP descargado desde Mi Fitness o la cuenta Xiaomi.

    Cómo obtener el ZIP:
      1. Abre Mi Fitness → Yo → Configuración → Privacidad → Exportar datos
      2. Descarga el ZIP y pásalo como argumento.
    """
    from skills.xiaomi_importer import parse_zip, import_to_db

    zip_path = Path(archivo)
    if not zip_path.exists():
        console.print(f"[red]❌ Archivo no encontrado: {archivo}[/red]")
        raise SystemExit(1)

    with console.status("[cyan]Leyendo ZIP...", spinner="dots"):
        records = parse_zip(str(zip_path))

    if not records:
        console.print("[yellow]No se encontraron registros de composición corporal en el ZIP.[/yellow]")
        console.print("[dim]El ZIP debe contener archivos como BODY_WEIGHT.json, body_record.csv, etc.[/dim]")
        return

    # Deduplicate by date (keep latest reading per date)
    by_date = {}
    for r in records:
        if r.get("date"):
            by_date[r["date"]] = r
    unique = sorted(by_date.values(), key=lambda r: r["date"])

    if dry_run:
        console.print(f"\n[yellow]Vista previa — {len(unique)} registros únicos para [bold]{persona}[/bold]:[/yellow]\n")
        for r in unique[-10:]:
            parts = [f"[bold]{r['date']}[/bold]", f"{r['weight_kg']} kg"]
            if r.get("body_fat_pct"): parts.append(f"grasa {r['body_fat_pct']}%")
            if r.get("muscle_mass_kg"): parts.append(f"músculo {r['muscle_mass_kg']} kg")
            console.print("  " + "  ·  ".join(parts))
        if len(unique) > 10:
            console.print(f"  [dim]... ({len(unique)} total, mostrando últimos 10)[/dim]")
        console.print("\n[dim]Ejecuta sin --dry-run para importar.[/dim]")
        return

    saved = import_to_db(unique, person=persona)

    console.print(Panel(
        f"[green]✅ {saved} medición(es) importadas para [bold]{persona}[/bold][/green]\n\n"
        f"Archivo       : [bold]{zip_path.name}[/bold]\n"
        f"Registros     : [bold]{len(records)}[/bold] raw → [bold]{len(unique)}[/bold] únicos\n"
        f"Guardados     : [bold]{saved}[/bold]\n\n"
        "Reconstruye el sitio para ver las métricas:\n"
        "  [yellow]bash actualizar_site.sh[/yellow]",
        title="[cyan]⚖️  ZIP Xiaomi importado[/cyan]",
        border_style="cyan",
    ))


@cli.command("generar-sitio")
@click.option("--semana", "-s", default=None, help="Fecha de referencia YYYY-MM-DD (default: hoy)")
def generar_sitio(semana):
    """Genera el sitio estático en docs/ para publicar en GitHub Pages."""
    from skills.site_builder import SiteBuilderSkill

    week_date = date.fromisoformat(semana) if semana else None
    with console.status("[bold green]Construyendo sitio...", spinner="dots"):
        output = SiteBuilderSkill().build(week_date)

    console.print(Panel(
        f"[green]✅ Sitio generado:[/green] [bold]{output}[/bold]\n\n"
        "Para publicar en [bold]GitHub Pages[/bold]:\n"
        "  1. Crea un repositorio en GitHub (puede ser privado)\n"
        "  2. [yellow]git init && git add docs/ && git commit -m 'site'[/yellow]\n"
        "  3. [yellow]git remote add origin <url> && git push -u origin main[/yellow]\n"
        "  4. En GitHub → Settings → Pages → Source: [bold]docs/[/bold] → branch [bold]main[/bold]\n\n"
        "Vista previa local:\n"
        "  [yellow]python -m http.server --directory docs 8080[/yellow]\n"
        "  Abre: [dim]http://localhost:8080[/dim]",
        title="🌐 GitHub Pages", border_style="cyan",
    ))


@cli.command("receta")
@click.argument("platillo")
def receta(platillo):
    """Genera la receta de un platillo específico. Ej: python main.py receta 'Salmón en costra de hierbas'"""
    from skills.recipe_finder import RecipeFinderSkill

    with console.status(f"[yellow]Generando receta: {platillo}...", spinner="dots"):
        content = RecipeFinderSkill().find_single(platillo)
    console.print(content)


@cli.command("registrar")
@click.option("--tiempo", "-t",
              type=click.Choice(["desayuno", "colacion_am", "comida", "colacion_pm", "cena"]),
              prompt="Tiempo de comida")
@click.option("--platillo", "-n", prompt="Nombre del platillo")
@click.option("--kcal", "-k", default=None, type=float, prompt="Calorías (Enter para omitir)", prompt_required=False)
@click.option("--proteina", "-p", default=None, type=float, help="Proteína en gramos")
@click.option("--carbs", "-c", default=None, type=float, help="Carbohidratos en gramos")
@click.option("--grasas", "-g", default=None, type=float, help="Grasas en gramos")
@click.option("--notas", default=None, help="Notas adicionales")
def registrar(tiempo, platillo, kcal, proteina, carbs, grasas, notas):
    """Registra una comida del día en el tracker."""
    from tracker.daily_log import DailyLog

    log = DailyLog()
    log.log_meal(tiempo, platillo, kcal, proteina, carbs, grasas, notas)
    log.close()
    console.print(f"[green]✅ Registrado:[/green] [bold]{platillo}[/bold]"
                  + (f" — {kcal:.0f} kcal" if kcal else ""))


@cli.command("resumen")
@click.option("--fecha", "-f", default=None, help="Fecha YYYY-MM-DD (default: hoy)")
def resumen(fecha):
    """Muestra el resumen nutricional del día."""
    from tracker.daily_log import DailyLog

    log_date = date.fromisoformat(fecha) if fecha else date.today()
    log = DailyLog()
    summary = log.get_daily_summary(log_date)
    log.close()

    table = Table(title=f"Resumen · {log_date.strftime('%d/%m/%Y')}", show_lines=True)
    table.add_column("Tiempo", style="cyan", min_width=12)
    table.add_column("Platillo", style="white")
    table.add_column("kcal", justify="right", style="yellow")
    table.add_column("Prot.", justify="right", style="blue")
    table.add_column("Carbs", justify="right", style="green")
    table.add_column("Grasas", justify="right", style="red")

    for m in summary["meals"]:
        table.add_row(
            m["type"], m["name"],
            f"{m['calories']:.0f}" if m["calories"] else "—",
            f"{m['protein_g']:.0f}g" if m["protein_g"] else "—",
            f"{m['carbs_g']:.0f}g" if m["carbs_g"] else "—",
            f"{m['fat_g']:.0f}g" if m["fat_g"] else "—",
        )

    t = summary["totals"]
    table.add_section()
    table.add_row(
        "[bold]TOTAL[/bold]", "",
        f"[bold]{t['calories']:.0f}[/bold]",
        f"[bold]{t['protein_g']:.0f}g[/bold]",
        f"[bold]{t['carbs_g']:.0f}g[/bold]",
        f"[bold]{t['fat_g']:.0f}g[/bold]",
    )

    if summary["goals"]:
        g = summary["goals"]
        diff_cal = t["calories"] - g["calories"]
        diff_color = "green" if abs(diff_cal) <= g["calories"] * 0.1 else "red"
        table.add_row(
            "[dim]META[/dim]", "",
            f"[dim]{g['calories']:.0f}[/dim]",
            f"[dim]{g['protein_g']:.0f}g[/dim]",
            f"[dim]{g['carbs_g']:.0f}g[/dim]",
            f"[dim]{g['fat_g']:.0f}g[/dim]",
        )
        table.add_row(
            "[dim]DIFERENCIA[/dim]", "",
            f"[{diff_color}]{diff_cal:+.0f}[/{diff_color}]",
            f"[dim]{t['protein_g'] - g['protein_g']:+.0f}g[/dim]",
            f"[dim]{t['carbs_g'] - g['carbs_g']:+.0f}g[/dim]",
            f"[dim]{t['fat_g'] - g['fat_g']:+.0f}g[/dim]",
        )

    console.print(table)


@cli.command("peso")
@click.option("--kg", "-k", required=True, type=float, prompt="Peso en kg")
@click.option("--persona", "-p", default="ATM", show_default=True, help="ATM o IOB")
@click.option("--notas", "-n", default=None, help="Notas (ej: 'en ayunas')")
def peso(kg, persona, notas):
    """Registra el peso corporal."""
    from tracker.daily_log import DailyLog

    log = DailyLog()
    log.log_weight(kg, person=persona, notes=notas)
    log.close()
    console.print(f"[green]✅[/green] Peso registrado: [bold]{kg} kg[/bold] ({persona})"
                  + (f" — {notas}" if notas else ""))


@cli.command("graficas")
@click.option("--semana", "-s", default=None, help="Inicio de semana YYYY-MM-DD (default: esta semana)")
def graficas(semana):
    """Genera gráficas PNG de calorías, macros y peso."""
    from tracker.daily_log import DailyLog
    from visualizations.charts import NutritionCharts
    import yaml
    from datetime import timedelta

    if semana:
        week_start = date.fromisoformat(semana)
    else:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())

    try:
        with open("config/diet_plan_example.yaml", encoding="utf-8") as f:
            plan = yaml.safe_load(f)
        targets = {k: plan["daily_targets"][k] for k in ("calories", "protein_g", "carbs_g", "fat_g")}
    except Exception:
        targets = {"calories": 2200, "protein_g": 165, "carbs_g": 220, "fat_g": 73}

    log = DailyLog()
    weekly = log.get_weekly_data(week_start)
    daily = log.get_daily_summary(date.today())
    weight_history = log.get_weight_history()
    log.close()

    charts = NutritionCharts()
    generated = []

    with console.status("[bold]Generando gráficas...", spinner="dots"):
        p = charts.weekly_calories_bar(weekly, targets, week_start)
        if p:
            generated.append(p)
        p = charts.macro_donut(daily["totals"], targets, date.today())
        if p:
            generated.append(p)
        p = charts.weight_trend(weight_history)
        if p:
            generated.append(p)

    for p in generated:
        console.print(f"[green]✅[/green] {p}")

    if not generated:
        console.print("[yellow]No hay datos suficientes para generar gráficas. Registra comidas primero.[/yellow]")


@cli.command("configurar-meta")
@click.option("--kcal", required=True, type=float, prompt="Calorías meta del día")
@click.option("--proteina", required=True, type=float, prompt="Proteína meta (g)")
@click.option("--carbs", required=True, type=float, prompt="Carbohidratos meta (g)")
@click.option("--grasas", required=True, type=float, prompt="Grasas meta (g)")
@click.option("--plan", default="Plan actual", help="Nombre del plan")
def configurar_meta(kcal, proteina, carbs, grasas, plan):
    """Establece las metas nutricionales diarias del tracker para hoy."""
    from tracker.daily_log import DailyLog

    log = DailyLog()
    log.set_daily_goal(kcal, proteina, carbs, grasas, plan)
    log.close()
    console.print(f"[green]✅[/green] Meta configurada: {kcal:.0f} kcal · P {proteina:.0f}g · C {carbs:.0f}g · G {grasas:.0f}g")


if __name__ == "__main__":
    cli()
