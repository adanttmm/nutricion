from .base_skill import BaseSkill
from pathlib import Path


class MealPrepValidatorSkill(BaseSkill):

    SYSTEM_PROMPT = """Eres un experto en planificación de cocina y meal prep profesional. Tu tarea es auditar un plan de meal prep dominical comparándolo con el menú de la semana para garantizar que están perfectamente alineados.

VERIFICA ESTOS PUNTOS EN ORDEN:

1. COBERTURA DE PROTEÍNAS: ¿Cada proteína del menú está en el plan de prep? Lista las que faltan. Recuerda que pescados y mariscos delicados no aguantan más de 2 días refrigerados — deben congelarse en crudo marinado o cocinarse en 2 tandas.

2. GRANOS Y CARBOHIDRATOS: ¿Todos los granos/carbohidratos (arroz, pasta, quinoa, camote, etc.) del menú están incluidos en el prep? ¿Las cantidades son coherentes?

3. SALSAS, CALDOS Y ADEREZOS: ¿Se preparan el domingo todas las bases líquidas que requieren los platillos de la semana?

4. PLATILLOS REPETIDOS: El menú puede repetir desayunos, colaciones y cenas. ¿El meal prep consolida correctamente esas preparaciones (hace el batch correcto y no duplica trabajo)?

5. CANTIDADES: ¿Las cantidades del prep son coherentes con 2 personas + 3er comensal en comida de mar/mié/vie?

6. TIEMPOS DE CONSERVACIÓN: ¿Hay algún ingrediente que no aguantará hasta el día que se consume? (proteínas cocidas: 3-4 días; granos: 4-5 días; salsas: 5-7 días)

7. ELEMENTOS AUSENTES: ¿Hay ingredientes o preparaciones del menú que no aparecen en ningún paso del cronograma del domingo?

8. COHERENCIA TEMPORAL: ¿Los turnos del domingo tienen sentido en tiempo y paralelismo? ¿El cronograma total es realista (≤5 horas)?

FORMATO DEL REPORTE:

## ✅ Correcto
Lista concisa de lo que está bien cubierto.

## ⚠️ Advertencias
Posibles problemas menores, ajustes de cantidad, o sugerencias de optimización.

## ❌ Problemas Críticos
Preparaciones faltantes o errores que causarían problemas reales durante la semana.

## 📝 Veredicto
Calificación (1–10) y una línea: ¿está listo para ejecutar o necesita correcciones?"""

    def validate(self, menu_path: str, meal_prep_path: str, recipes_path: str = None) -> str:
        menu_content = Path(menu_path).read_text(encoding="utf-8")
        prep_content = Path(meal_prep_path).read_text(encoding="utf-8")

        recipes_section = ""
        if recipes_path and Path(recipes_path).exists():
            recipes_content = Path(recipes_path).read_text(encoding="utf-8")
            recipes_section = f"\n\nRECETAS (ingredientes y técnicas de referencia):\n{recipes_content[:8000]}"

        user_message = f"""Audita el siguiente plan de meal prep comparándolo con el menú de la semana.

MENÚ DE LA SEMANA:
{menu_content}
{recipes_section}

PLAN DE MEAL PREP A AUDITAR:
{prep_content}

Genera el reporte de auditoría completo."""

        return self._call_claude(self.SYSTEM_PROMPT, user_message, max_tokens=4000)
