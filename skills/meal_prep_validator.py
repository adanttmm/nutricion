from .base_skill import BaseSkill
from pathlib import Path


class MealPrepValidatorSkill(BaseSkill):

    SYSTEM_PROMPT = """Eres un experto en planificación de cocina y meal prep profesional. Tu tarea es auditar un plan de meal prep dominical comparándolo con el menú de la semana para garantizar que están perfectamente alineados.

VERIFICA ESTOS PUNTOS EN ORDEN:

1. COBERTURA DE PROTEÍNAS: ¿Cada proteína del menú está en el plan de prep? Lista las que faltan. Recuerda que pescados y mariscos delicados no aguantan más de 2 días refrigerados — deben congelarse en crudo marinado o cocinarse en 2 tandas.

2. GRANOS Y CARBOHIDRATOS: ¿Todos los granos/carbohidratos (arroz, pasta, quinoa, camote, etc.) del menú están incluidos en el prep? ¿Las cantidades son coherentes?

3. SALSAS, CALDOS Y ADEREZOS: ¿Se preparan el domingo todas las bases líquidas que requieren los platillos de la semana?

4. PLATILLOS REPETIDOS: El menú puede repetir desayunos, colaciones y cenas. ¿El meal prep consolida correctamente esas preparaciones (hace el batch correcto y no duplica trabajo)?

5. CANTIDADES EXACTAS: Se te da una tabla "TOTALES SEMANALES CALCULADOS" con las sumas exactas (calculadas por código, no estimadas) de cada ingrediente que aparece en las recetas, en gramos crudos, por persona. Esta tabla es la referencia autoritativa — NO la recalcules ni la reestimes.
   Para cada ingrediente que el plan de meal prep mencione con una cantidad total (ej. "Total salmón: ~2,040g"), compara ese número contra la fila correspondiente de la tabla:
   - Si coincide (±10% de tolerancia, para redondeos de compra), está correcto.
   - Si NO coincide, repórtalo como discrepancia de cantidad en ❌ Problemas Críticos, citando el número exacto del plan de prep vs. el número exacto de la tabla.
   - Si el plan de prep no da un total consolidado para un ingrediente que sí está en la tabla (y ese ingrediente requiere prep dominical — proteínas, granos, salsas), repórtalo como elemento ausente.

6. TIEMPOS DE CONSERVACIÓN: ¿Hay algún ingrediente que no aguantará hasta el día que se consume? (proteínas cocidas: 3-4 días; granos: 4-5 días; salsas: 5-7 días)

7. ELEMENTOS AUSENTES: ¿Hay ingredientes o preparaciones del menú que no aparecen en ningún paso del cronograma del domingo?

8. COHERENCIA TEMPORAL: ¿Los turnos del domingo tienen sentido en tiempo y paralelismo? ¿El cronograma total es realista (≤5 horas)?

FORMATO DEL REPORTE:

## ✅ Correcto
Lista concisa de lo que está bien cubierto.

## ⚠️ Advertencias
Posibles problemas menores, ajustes de cantidad, o sugerencias de optimización.

## ❌ Problemas Críticos
Preparaciones faltantes o errores que causarían problemas reales durante la semana. Incluye aquí toda discrepancia de cantidad detectada en el punto 5, citando ambos números.

## 📝 Veredicto
Calificación (1–10) y una línea: ¿está listo para ejecutar o necesita correcciones?"""

    def validate(self, menu_path: str, meal_prep_path: str, recipes_path: str = None) -> str:
        menu_content = Path(menu_path).read_text(encoding="utf-8")
        prep_content = Path(meal_prep_path).read_text(encoding="utf-8")

        recipes_section = ""
        totals_section = ""
        if recipes_path and Path(recipes_path).exists():
            # Pass the whole file — truncating here blinds the audit to exactly the
            # back half of the week whose quantities most need checking.
            recipes_content = Path(recipes_path).read_text(encoding="utf-8")
            recipes_section = f"\n\nRECETAS (ingredientes y técnicas de referencia):\n{recipes_content}"
            totals_section = self._build_totals_reference(recipes_content)

        user_message = f"""Audita el siguiente plan de meal prep comparándolo con el menú de la semana.

MENÚ DE LA SEMANA:
{menu_content}
{recipes_section}
{totals_section}

PLAN DE MEAL PREP A AUDITAR:
{prep_content}

Genera el reporte de auditoría completo."""

        return self._call_claude(self.SYSTEM_PROMPT, user_message, max_tokens=16000)

    @staticmethod
    def _build_totals_reference(recipes_content: str) -> str:
        """Deterministically compute each ingredient's exact weekly raw-gram total
        from the recipes (same canonicalization the site uses, so name variants
        like "Salmón" / "Salmón filete" / "Filete de salmón" are already merged),
        and format it as an authoritative reference block for the audit prompt —
        code-computed sums instead of asking the model to re-derive them itself."""
        from .site_builder import SiteBuilderSkill

        totals = SiteBuilderSkill._parse_recipe_ingredient_totals(recipes_content)
        if not totals:
            return ""

        rows = "\n".join(
            f"| {v['name']} | {v['atm_g']:.0f}g | {v['iob_g']:.0f}g |"
            for v in sorted(totals.values(), key=lambda x: x['name'].lower())
        )
        return (
            "\n\nTOTALES SEMANALES CALCULADOS (crudo, suma exacta por código a partir de "
            "las recetas — usa esta tabla como referencia autoritativa para el punto 5, "
            "no la recalcules):\n"
            "| Ingrediente | 🧔 ATM total | 👤 IOB total |\n"
            "|---|---|---|\n"
            f"{rows}"
        )