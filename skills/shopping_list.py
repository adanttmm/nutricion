from .base_skill import BaseSkill
from pathlib import Path
from datetime import date


class ShoppingListSkill(BaseSkill):

    SYSTEM_PROMPT = """Eres un experto en cocina gourmet amateur y supermercados de Ciudad de México.

TU TAREA: Generar la lista de compras semanal como una sola tabla Markdown, ordenada ESTRICTAMENTE ALFABÉTICO por nombre de ingrediente (A→Z).

COLUMNAS EXACTAS:
| Ingrediente | Cantidad | Receta | Día | Tienda |

REGLAS:
1. Una fila por ingrediente, consolidando TODOS sus usos en la semana.
2. Ordenar A→Z por Ingrediente, sin excepción.
3. Cantidad: en la unidad correcta (g, kg, piezas, ml). Redondear hacia arriba a presentación comercial. Incluir TODOS los días y nombre de recetas de uso en renglones separados.
4. Receta: nombre corto del platillo.
5. Día: abreviar Lun/Mar/Mié/Jue/Vie/Sáb/Dom. Varios días: "Lun+Jue".
6. Tienda: "Costco" o "City Market" según disponibilidad real.
7. Incluir ABSOLUTAMENTE TODOS los ingredientes: proteínas principales, granos, verduras, lácteos, especias, ingredientes de salsas, marinados y preparaciones componente del meal prep.
8. No omitir ningún ingrediente por ser "básico" — si se necesita esta semana, va en la lista.
9. No agregar ningún ingrediente que no esté en el menú, recetas o meal prep de la semana.

CANTIDADES BASE:
- 2 personas todos los tiempos (ATM + IOB)
- 3 personas en la comida de martes, miércoles y viernes (3er comensal = porción IOB)

CRITERIO DE TIENDA:
COSTCO: pollo (pechuga/muslo), salmón, camarones congelados, atún en agua, res molida, huevos, leche, yogurt griego, mantequilla, queso crema, mozzarella, cheddar, parmesano Kraft, jitomate, cebolla, ajo, limones, aguacate, espinaca, zanahoria, pimiento, plátano, fresas, arroz, pasta regular, avena, aceite de oliva, aceite de coco, vinagre balsámico, soya Kikkoman, mostaza Dijon, garbanzos/frijoles en lata, leche de coco, caldo Kirkland, almendras, nueces, proteína whey, chile en polvo, especias secas comunes
CITY MARKET: pato, cordero, wagyu, bacalao, pulpo, callo de hacha, trucha, burrata, queso de cabra, brie, ricotta fresca, halloumi, mascarpone, crème fraîche, hierbas frescas premium, miso, mirin, sake, vinagre de arroz, pasta curry, za'atar, sumac, harissa, tahini artesanal, aceite de sésamo, hongos frescos, chiles secos especiales (mulato/negro/chihuacle/pasilla), chocolate de Oaxaca, pasta italiana premium
En caso de duda → City Market."""

    def generate(self, menu_path: str, recipes_path: str = None,
                 meal_prep_path: str = None, week_date: date = None) -> Path:
        if week_date is None:
            week_date = date.today()

        sections = [Path(menu_path).read_text(encoding="utf-8")]

        if recipes_path and Path(recipes_path).exists():
            sections.append(
                "RECETAS:\n" + Path(recipes_path).read_text(encoding="utf-8")
            )
        if meal_prep_path and Path(meal_prep_path).exists():
            sections.append(
                "PLAN DE MEAL PREP (contiene ingredientes de salsas y preparaciones componente):\n"
                + Path(meal_prep_path).read_text(encoding="utf-8")
            )

        user_message = (
            "Genera la lista de compras completa para esta semana.\n\n"
            + "\n\n---\n\n".join(sections)
            + "\n\n---\n\n"
            "Genera la tabla completa ordenada A→Z: | Ingrediente | Cantidad | Receta | Día | Tienda |"
        )

        content = self._call_claude(self.SYSTEM_PROMPT, user_message, max_tokens=8000)

        header = (
            f"# 🛒 Lista de Compras\n"
            f"## Semana del {week_date.strftime('%d de %B de %Y')}\n\n"
        )
        filename = f"compras_{week_date.strftime('%Y-%m-%d')}.md"
        return self._save_output(header + content, "outputs/shopping", filename)
