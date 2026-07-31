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
- Excluye el sábado del analisis ya que es el dia de comida libre y no se considera, el promedio semanal sólo considera los días de plan completo.
- DÍAS ESPECIALES (viaje, salida, comida fuera, etc.): si la NOTA DE LA SEMANA menciona que el cocinero estará fuera o que solo necesita ciertos tiempos de comida en algún día, y el menú documenta explícitamente esa excepción para ese día (marcador †, "(viaje)", una nota junto al día, o simplemente ese tiempo de comida ausente del día en el menú), trata ese día igual que el sábado: EXCLÚYELO del análisis estricto diario y del promedio semanal. Nunca lo marques ❌ por no alcanzar la meta diaria completa — esa meta nunca aplicó para ese día.
- Calorías diarias por persona: ±5 % de la meta del día (rechazo tanto por defecto como por exceso)
- Proteína diaria: ±5 % (nutriente más crítico — rechazo tanto por defecto como por exceso; el defecto de proteína es falla automática)
- Carbohidratos diarios: TOLERANCIA ASIMÉTRICA — quedarse POR DEBAJO de la meta nunca es motivo de rechazo (sin importar cuánto por debajo). Rechazar SOLO si el real excede la meta en más de +5 %.
- Grasa diaria: misma tolerancia asimétrica que carbohidratos — por debajo de la meta siempre ✅; rechazar SOLO si excede +5 %.
- Si todos los días pasan, el promedio semanal (excluyendo sábado y cualquier día especial) también debe estar dentro de ±10 % para calorías/proteína, y dentro del mismo criterio asimétrico (solo exceso +10 %) para carbohidratos/grasa.

PROCESO:
1. Si se incluyó una NOTA DE LA SEMANA, léela primero e identifica qué días (si los hay) son especiales/incompletos por indicación del cocinero (viaje, salida, tiempo limitado que implique omitir un tiempo de comida, etc.). Confirma en el menú qué tiempos de comida aparecen realmente ese día — esos son los únicos que cuentan.
2. Lee los objetivos del plan nutricional (calories, protein_g, carbs_g, fat_g) para ATM y para IOB, por tiempo de comida y como total diario base.
3. Calcula la meta ajustada de cada día (base + bonos de actividad). Para un día especial identificado en el paso 1, la meta ajustada NO es la meta diaria completa — es SOLO la suma de las metas de los tiempos de comida (desayuno, colación AM, comida, colación PM, cena) que el menú realmente incluye ese día. Nunca inventes ni exijas un tiempo de comida que el menú omitió intencionalmente.
4. Busca en el menú la sección "TABLA RESUMEN SEMANAL" o los encabezados "Totales diarios". Extrae los totales reales de kcal, proteína, carbohidratos y grasa de cada día para cada persona.
   — Si la tabla resumen no aparece, suma los macros de cada tiempo de comida del día — solo los tiempos de comida que el menú realmente incluye ese día, nunca asumas los 5 tiempos estándar si el día es especial.
5. Compara meta ajustada vs. real para cada persona × día.
6. Marca cada celda ✅ si está dentro de tolerancia, ❌ si no. IMPORTANTE: para carbohidratos y grasa, un valor real POR DEBAJO de la meta es SIEMPRE ✅ sin importar la magnitud — solo un valor por ENCIMA de +5% (día) o +10% (promedio semanal) es ❌. Calorías y proteína siguen siendo simétricas (±5%/±10% en ambas direcciones). Los días especiales identificados en el paso 1 no se marcan ❌ ni ✅ por meta diaria completa — anótalos aparte (ver formato de reporte) usando su meta ajustada del paso 3.
7. Si el rechazo es por ±2 % de calorías o proteína (en cualquier dirección), o por exceso de +2 % de carbohidratos/grasa, modifica ligeramente las cantidades de los alimentos en el menú para ajustarlos a la meta. Si se rechaza por más de esos márgenes, se debe realizar una revisión más exhaustiva del menú. Nunca "corrijas" un carbohidrato o grasa que está por debajo de la meta — eso no es un defecto. Nunca generes feedback pidiendo "completar" un tiempo de comida que fue omitido intencionalmente en un día especial.

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
Días especiales excluidos del análisis (si los hay): [Día — motivo, p. ej. "Viernes — viaje, solo desayuno y cena"] o "ninguno".

Tabla ATM:
| Día | Meta kcal | Real kcal | Δ% | Proteína meta | Proteína real | Δ% | Estado |
|---|---|---|---|---|---|---|---|
| Lunes | 2950 | XXXX | +X% | 192g | XXXg | +X% | ✅/❌ |
...
(para un día especial, usa su meta ajustada del paso 3 y marca Estado como "— especial", nunca ❌)
Promedio semanal ATM (excluye sábado y días especiales): meta XXX kcal · real XXX kcal · Δ X%

Tabla IOB:
(misma estructura)
Promedio semanal IOB (excluye sábado y días especiales): meta XXX kcal · real XXX kcal · Δ X%

Resumen: X/N días ATM dentro de tolerancia · X/N días IOB dentro de tolerancia (N = días de plan completo, excluyendo sábado y especiales).
Veredicto final: APROBADO / RECHAZADO — [una línea explicando el principal hallazgo]"""

    def validate(self, diet_plan_path: str, menu_path: str, week_notes: str = "") -> ValidationResult:
        with open(diet_plan_path, encoding="utf-8") as f:
            diet_plan = yaml.safe_load(f)

        menu_content = Path(menu_path).read_text(encoding="utf-8")
        plan_summary = self._build_plan_summary(diet_plan)

        notes_block = (
            f"NOTA DE LA SEMANA (excepciones a considerar — identifica días especiales/incompletos):\n{week_notes}\n\n"
            if week_notes else ""
        )

        user_message = (
            "Audita el siguiente menú semanal contra el plan nutricional.\n\n"
            f"{notes_block}"
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
