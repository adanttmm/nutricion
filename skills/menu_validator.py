from dataclasses import dataclass
from .base_skill import BaseSkill
from pathlib import Path
import yaml


@dataclass
class ValidationResult:
    passed: bool
    feedback: str   # Structured corrections → injected back into menu generator
    report: str     # Human-readable table → shown in console / stored


class MenuValidatorSkill(BaseSkill):

    SYSTEM_PROMPT = """Eres un nutriólogo clínico y analista de datos. Auditas menús semanales verificando cumplimiento exacto de metas calóricas y de macronutrientes.

CONTEXTO DEL HOGAR:
- ATM: Gym lunes/miércoles/viernes → meta base +150 kcal ese día (aplicado en colación PM).
         Salsa martes/jueves → meta base +100 kcal ese día (aplicado en colación PM).
- IOB: Salsa martes/jueves → meta base +100 kcal ese día (aplicado en colación PM).
- 3er comensal: aparece solo en la COMIDA de martes, miércoles y viernes con porción igual a IOB — no afecta las metas de ATM ni IOB.

TOLERANCIAS ACEPTABLES (fuera de estas → RECHAZADO):
- Excluye el sábado del analisis ya que es el dia de comida libre y no se considera, el promedio semanal sólo considera 6 dias.
- Calorías diarias por persona: ±5 % de la meta del día
- Proteína diaria: ±5 % (nutriente más crítico — defecto de proteína es falla automática)
- Carbohidratos diarios: ±5 %
- Grasa diaria: ±5 %
- Si todos los días pasan, el promedio semanal (sin sábado) también debe estar dentro de ±10 %.

PROCESO:
1. Lee los objetivos del plan nutricional (calories, protein_g, carbs_g, fat_g) para ATM y para IOB, por tiempo de comida y como total diario base.
2. Calcula la meta ajustada de cada día (base + bonos de actividad).
3. Busca en el menú la sección "TABLA RESUMEN SEMANAL" o los encabezados "Totales diarios". Extrae los totales reales de kcal, proteína, carbohidratos y grasa de cada día para cada persona.
   — Si la tabla resumen no aparece, suma los macros de cada tiempo de comida del día.
4. Compara meta ajustada vs. real para cada persona × día.
5. Marca cada celda ✅ si está dentro de tolerancia, ❌ si no.
6. Si el rechazo es por ±2 % de cualquier macronutriente, modifica ligeramente las cantidades de los alimentos en el menú para ajustarlos a la meta. Si se rechaza por más de ±2 %, se debe realizar una revisión más exhaustiva del menú.

FORMATO DE RESPUESTA — usa EXACTAMENTE esta estructura, sin variaciones:

VEREDICTO: APROBADO
(o VEREDICTO: RECHAZADO)

FEEDBACK_GENERADOR:
ninguno
(o, si RECHAZADO, lista específica y accionable:)
- ATM Lunes (meta 2950 kcal, real 2600): déficit 350 kcal. Aumentar cena: +50 g proteína (~200 kcal) y +35 g grano en carbohidrato (~130 kcal).
- IOB Jueves (meta 1800 kcal, real 2050): exceso 250 kcal. Reducir comida: -30 g carbohidrato y -15 g proteína.
(cada línea = un problema concreto con corrección concreta en qué tiempo de comida aplicarla)

REPORTE_HUMANO:
Tabla ATM:
| Día | Meta kcal | Real kcal | Δ% | Proteína meta | Proteína real | Δ% | Estado |
|---|---|---|---|---|---|---|---|
| Lunes | 2950 | XXXX | +X% | 192g | XXXg | +X% | ✅/❌ |
...
Promedio semanal ATM: meta XXX kcal · real XXX kcal · Δ X%

Tabla IOB:
(misma estructura)
Promedio semanal IOB: meta XXX kcal · real XXX kcal · Δ X%

Resumen: X/7 días ATM dentro de tolerancia · X/7 días IOB dentro de tolerancia.
Veredicto final: APROBADO / RECHAZADO — [una línea explicando el principal hallazgo]"""

    def validate(self, diet_plan_path: str, menu_path: str) -> ValidationResult:
        with open(diet_plan_path, encoding="utf-8") as f:
            diet_plan = yaml.safe_load(f)

        menu_content = Path(menu_path).read_text(encoding="utf-8")
        plan_summary = self._build_plan_summary(diet_plan)

        user_message = (
            "Audita el siguiente menú semanal contra el plan nutricional.\n\n"
            f"PLAN NUTRICIONAL — METAS POR PERSONA Y TIEMPO DE COMIDA:\n{plan_summary}\n\n"
            f"MENÚ A AUDITAR:\n{menu_content}\n\n"
            "Genera el reporte completo siguiendo el formato indicado."
        )

        raw = self._call_claude(self.SYSTEM_PROMPT, user_message, max_tokens=16000)
        return self._parse_result(raw)

    @staticmethod
    def _build_plan_summary(diet_plan: dict) -> str:
        lines = []
        slot_labels = {
            "desayuno":    "Desayuno",
            "colacion_am": "Colación AM",
            "comida":      "Comida",
            "colacion_pm": "Colación PM",
            "cena":        "Cena",
        }

        persons = diet_plan.get("persons", {})
        if not persons:
            # Single-person / template plan
            t = diet_plan.get("daily_targets", {})
            lines.append("Meta diaria base:")
            lines.append(f"  {t.get('calories')} kcal · P {t.get('protein_g')}g · C {t.get('carbs_g')}g · G {t.get('fat_g')}g")
            for sk, label in slot_labels.items():
                slot = diet_plan.get("meal_structure", {}).get(sk, {})
                if slot:
                    lines.append(
                        f"  {label}: {slot.get('calories')} kcal · "
                        f"P {slot.get('protein_g')}g · C {slot.get('carbs_g')}g · G {slot.get('fat_g')}g"
                    )
            return "\n".join(lines)

        for person_name, data in persons.items():
            t = data.get("daily_targets", {})
            lines.append(f"\n{person_name} — objetivo: {data.get('goal', 'no especificado')}")
            lines.append(
                f"  Total diario base: {t.get('calories')} kcal · "
                f"P {t.get('protein_g')}g · C {t.get('carbs_g')}g · G {t.get('fat_g')}g"
            )
            meal_structure = data.get("meal_structure", {})
            if meal_structure:
                lines.append("  Distribución por tiempo de comida:")
                for sk, label in slot_labels.items():
                    slot = meal_structure.get(sk, {})
                    if slot:
                        lines.append(
                            f"    {label}: {slot.get('calories')} kcal · "
                            f"P {slot.get('protein_g')}g · "
                            f"C {slot.get('carbs_g')}g · "
                            f"G {slot.get('fat_g')}g"
                        )

        return "\n".join(lines)

    @staticmethod
    def _parse_result(raw: str) -> ValidationResult:
        passed = "VEREDICTO: APROBADO" in raw

        feedback = ""
        report = raw

        try:
            if "FEEDBACK_GENERADOR:" in raw and "REPORTE_HUMANO:" in raw:
                fb_start = raw.index("FEEDBACK_GENERADOR:") + len("FEEDBACK_GENERADOR:")
                fb_end   = raw.index("REPORTE_HUMANO:")
                feedback = raw[fb_start:fb_end].strip()
                if feedback.lower() in ("ninguno", "ninguno."):
                    feedback = ""

                rpt_start = raw.index("REPORTE_HUMANO:") + len("REPORTE_HUMANO:")
                report = raw[rpt_start:].strip()
        except ValueError:
            # Malformed output — keep raw as report, treat as failed
            passed = False
            report = raw

        return ValidationResult(passed=passed, feedback=feedback, report=report)
