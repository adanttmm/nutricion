from .base_skill import BaseSkill
from pathlib import Path
from datetime import date, timedelta
import yaml


class MenuGeneratorSkill(BaseSkill):

    SYSTEM_PROMPT = """Eres un chef amateur gourmet y nutriólogo profesional. Creas menús semanales variados, elegantes, con porciones individualizadas por persona.

PERFIL DEL COCINERO:
- Nivel avanzado, cómodo con técnicas profesionales (confitado, reducciones, emulsiones, fermentados, braseado, sellado a fuego alto, cocción al vapor, horneado a baja temperatura, helados, ahumado, rostizado, carbón).
- Equipamiento completo incluye: horno, 4+ quemadores, procesador, batidora, sartenes de hierro y antiadherente, vaporera, CIRCULADOR SOUS VIDE (disponible para cualquier platillo), MÁQUINA DE PASTA (para pasta fresca artesanal).
- Preferencia por cocina gourmet de cualquier gastronomía cuyos ingredientes se encuentren en México.
- Revisa los menús de las tres semanas anteriores para evitar repetir demasiado.
- Busca recetas rápidas, eficientes, fit y gourmet amateur en internet para referencia y agrega los links de referencia.
- Cocina para 2 personas (ATM e IOB) en todos los tiempos; martes, miércoles y viernes hay un 3er comensal a la comida con la misma porción que IOB; evitar ingredientes premium o demasiado exoticos los dias del tercer comensal
- 1 comida trampa por semana (restaurante o platillo especial sin restricciones)
- Meal prep con equilibrio inteligente: la mayor parte se cocina el domingo, PERO puedo dedicar algun tiempo para cocinar en la semana. El objetivo es ≤30 min activos de cocción entre semana.

REGLAS DEL MENÚ:
1. Generar los 7 días completos: lunes, martes, miércoles, jueves, viernes, sábado y domingo sin excepción.
2. No repetir la proteína principal más de 2 veces por semana en comida y cena.
3. Evitar repetir recetas de hace dos semanas.
4. Las calorías y macros de CADA PERSONA deben coincidir con SUS metas (±5%). Los NÚMEROS son la ley; los alimentos son libres.
5. Se cocina UN SOLO PLATILLO para ambas personas — las porciones varían por persona.
6. Ingredientes accesibles en Costco Ciudad de México + City Market Santa Fe.
7. Los días de gym (+150 kcal ATM) y salsa (+100 kcal ambos) ajustar la colación vespertina.
8. Nombres de platillos elegantes y descriptivos, al estilo de menú de restaurante.
9. DISEÑO PARA MEAL PREP INTELIGENTE: proteínas, granos y salsas de TODOS los días deben llevar 🏪 o 🌊 (sous vide entre semana). Los únicos elementos frescos entre semana son aguacate, huevo al momento, hierbas frescas o ensalada cruda.
10. Consulta el sitio https://smn.conagua.gob.mx/es/ para obtener información sobre el clima en Cuajimalpa de Morelos y ajustar las recetas según la temporada.

OPTIMIZACIÓN DE CARGA DE COCINA — REPETICIÓN CONTROLADA:
Para reducir el número de recetas únicas a preparar, usa este esquema OBLIGATORIO:
- DESAYUNO: exactamente 2 variantes. Variante A: lunes+martes+miércoles. Variante B: jueves+viernes+sábado+domingo. Nombrarlos idéntico en todos los días que los usan.
- COLACIÓN AM: exactamente 2 variantes. Variante A: lunes+martes+miércoles+jueves. Variante B: viernes+sábado+domingo.
- COLACIÓN PM: exactamente 2 variantes. Variante A: lunes+miércoles+viernes (días de gym, +150 kcal ATM). Variante B: martes+jueves+sábado+domingo (días de salsa o descanso).
- COMIDA: exactamente 3 platillos únicos de comida rotando toda la semana: Variante A: lunes+jueves (mismo platillo exacto); Variante B: martes+viernes (mismo platillo exacto); Variante C: miércoles+sábado+domingo (mismo platillo exacto). Total: solo 3 recetas únicas de comida. El sábado y domingo reutilizan el prep del miércoles — cero cocción adicional el fin de semana.
- CENA: exactamente 2 variantes. Variante A: lunes+martes+miércoles. Variante B: jueves+viernes+domingo. Sábado: comida trampa 🎉 (no requiere cena de prep).
Esta optimización significa solo ~11 recetas únicas. El fin de semana se libera significativamente al tener solo 3 comidas únicas en lugar de 4.

USO DEL PLAN NUTRICIONAL:
- El plan del nutriólogo define METAS NUMÉRICAS por tiempo de comida (kcal, proteína, carbohidratos, grasa). Esos números son obligatorios.
- Los ALIMENTOS que el nutriólogo listó son solo una referencia de qué tan saciante o denso es el plan — NO son el menú a reproducir.
- Diseña platillos ORIGINALES y CREATIVOS cada semana que alcancen los mismos macros. Varía proteínas, granos, verduras, técnicas y gastronomías libremente.
- Un cocinero avanzado no come lo mismo cada semana: usa el perfil completo (confitado, braseado, emulsiones, fermentados, sous vide, cocción a baja temperatura en horno, técnicas japonesas, peruanas, árabes, francesas, pasta fresca) para crear menús que un nutriólogo básico jamás prescribiría. El sous vide y la pasta fresca son bienvenidos y se integran al plan de prep.

LEYENDA:
🏪 = Preparar el domingo (meal prep)
🌊 = Sous vide entre semana (bolsa sellada el domingo, cocción de 45-90 min durante la semana)
🍝 = Pasta fresca con máquina (sábado o domingo, se congela el excedente)
🎉 = Comida trampa
Bandera = gastronomía del platillo

FORMATO OBLIGATORIO — cada tiempo de comida:

### 🌅 Desayuno 🏪 [bandera]
**[Nombre del platillo]**
*[descripción gourmet 1 línea]*
| | 🧔 ATM | 👤 IOB |
|---|---|---|
| kcal · P · C · G | XXX · XXg · XXg · XXg | XXX · XXg · XXg · XXg |
| [ingrediente clave 1] | XXg / X porciones | XXg / X porciones |
| [ingrediente clave 2] | XXg | XXg |

(solo mostrar filas de ingredientes donde la cantidad difiere entre personas; omitir los que son iguales)

### 🍎 Colación AM
**[Nombre]**
| | 🧔 ATM | 👤 IOB |
|---|---|---|
| kcal · P · C · G | ... | ... |
[ajuste de porción si difiere]

### 🍽️ Comida *(mar/mié/vie: 3er comensal — misma porción que IOB)*
**[Nombre del platillo]** [bandera]
| | 🧔 ATM | 👤 IOB |
|---|---|---|
| kcal · P · C · G | ... | ... |
[ajuste de porción]

### 🌿 Colación PM *(pre-entreno si aplica)*
**[Nombre]**
| | 🧔 ATM | 👤 IOB |
|---|---|---|
| kcal · P · C · G | ... | ... |

### 🌙 Cena 🏪
**[Nombre del platillo]** [bandera]
| | 🧔 ATM | 👤 IOB |
|---|---|---|
| kcal · P · C · G | ... | ... |
[ajuste de porción]

---
Al final: tabla resumen con totales diarios por persona y promedios semanales."""

    def generate(self, diet_plan_path: str, week_start: date = None, feedback: str = "", ratings_context: str = "", week_notes: str = "") -> Path:
        if week_start is None:
            today = date.today()
            days_until_monday = (7 - today.weekday()) % 7 or 7
            week_start = today + timedelta(days=days_until_monday)

        with open(diet_plan_path, encoding="utf-8") as f:
            diet_plan = yaml.safe_load(f)

        history = ""
        history_path = Path("data/menu_history.txt")
        if history_path.exists():
            text = history_path.read_text(encoding="utf-8").strip()
            if text:
                history = f"\n\nPLATILLOS DE SEMANAS ANTERIORES (no repetir los mismos):\n{text[-3000:]}"

        gym_days = self.user_profile.get("activity", {}).get("gym", {}).get("days", [])
        salsa_days = self.user_profile.get("activity", {}).get("salsa_dancing", {}).get("days", [])
        day_names = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
        days_info = []
        for i, day_name in enumerate(day_names):
            d = week_start + timedelta(days=i)
            notes = []
            if day_name in gym_days:
                notes.append(f"+{diet_plan.get('context', {}).get('gym_calorie_bonus', 150)} kcal (gym)")
            if day_name in salsa_days:
                notes.append(f"+{diet_plan.get('context', {}).get('salsa_calorie_bonus', 100)} kcal (salsa)")
            days_info.append(
                f"- {day_name.capitalize()} {d.strftime('%d/%m')}: {', '.join(notes) if notes else 'día normal'}"
            )

        is_parsed = self._is_parsed_diet(diet_plan)
        plan_context = self._build_plan_context(diet_plan, is_parsed)

        cheat_day = (
            diet_plan.get("cheat_meal", {}).get("preferred_day")
            or diet_plan.get("context", {}).get("cheat_meal", {}).get("preferred_day", "sábado")
        )
        cheat_time = (
            diet_plan.get("cheat_meal", {}).get("preferred_time")
            or diet_plan.get("context", {}).get("cheat_meal", {}).get("preferred_time", "cena")
        )

        notes_block = ""
        if week_notes:
            notes_block = (
                f"\n\n📋 INDICACIONES ESPECIALES DEL COCINERO PARA ESTA SEMANA:\n{week_notes}\n"
                "Adapta el menú teniendo en cuenta estas indicaciones — tienen prioridad sobre las preferencias generales."
            )

        correction_block = ""
        if feedback:
            correction_block = (
                f"\n\n⚠️  CORRECCIONES OBLIGATORIAS — EL MENÚ ANTERIOR FUE RECHAZADO POR EL VALIDADOR:\n"
                f"{feedback}\n\n"
                "Diseña un menú NUEVO corrigiendo EXACTAMENTE cada punto anterior. "
                "Las metas calóricas y de macros son innegociables — ajusta porciones hasta cumplirlas."
            )

        ratings_block = f"\n\n{ratings_context}" if ratings_context else ""

        user_message = (
            f"Genera el menú completo para la semana del {week_start.strftime('%d de %B de %Y')} (lunes a domingo).\n\n"
            f"{plan_context}\n\n"
            f"ACTIVIDAD DE LA SEMANA:\n{chr(10).join(days_info)}\n\n"
            f"Comida trampa: {cheat_day.capitalize()} en la {cheat_time}"
            f"{history}"
            f"{ratings_block}"
            f"{notes_block}"
            f"{correction_block}\n\n"
            "Genera los 7 días completos con todos los tiempos de comida según el formato indicado."
        )

        content = self._call_claude(self.SYSTEM_PROMPT, user_message, max_tokens=16000)

        header = f"# 🍽️ Menú Semanal\n## Semana del {week_start.strftime('%d de %B de %Y')}\n\n"
        filename = f"menu_{week_start.strftime('%Y-%m-%d')}.md"
        output_path = self._save_output(header + content, "outputs/menus", filename)

        history_path.parent.mkdir(parents=True, exist_ok=True)
        dish_lines = [
            line.strip()
            for line in content.split("\n")
            if "**" in line and line.strip().startswith("**")
        ]
        with open(history_path, "a", encoding="utf-8") as f:
            f.write(f"\n=== Semana {week_start.strftime('%Y-%m-%d')} ===\n")
            f.write("\n".join(dish_lines[:60]) + "\n")

        return output_path

    @staticmethod
    def _is_parsed_diet(diet_plan: dict) -> bool:
        if diet_plan.get("document_type") in ("combined_diet_plan", "diet_plan"):
            return True
        meal_structure = diet_plan.get("meal_structure", {})
        for meal in meal_structure.values():
            if isinstance(meal, dict) and "foods" in meal:
                return True
        return False

    @staticmethod
    def _person_has_foods(person_data: dict) -> bool:
        for meal in person_data.get("meal_structure", {}).values():
            if isinstance(meal, dict) and meal.get("foods"):
                return True
        return False

    def _build_plan_context(self, diet_plan: dict, is_parsed: bool) -> str:
        """Build the diet plan section of the user message based on plan type."""
        if not is_parsed:
            return (
                "PLAN NUTRICIONAL (template):\n"
                + yaml.dump(diet_plan, allow_unicode=True, default_flow_style=False, indent=2)
            )

        doc_type = diet_plan.get("document_type", "diet_plan")

        # ── Combined plan: two people with individual targets ─────────────────
        if doc_type == "combined_diet_plan" and "persons" in diet_plan:
            return self._build_combined_context(diet_plan)

        # ── Single parsed plan ────────────────────────────────────────────────
        return self._build_single_context(diet_plan)

    @staticmethod
    def _fmt_meal(meal: dict, label: str) -> list:
        """Format one meal block: macro targets first, foods as brief reference."""
        if not meal:
            return []
        lines = [f"\n  {label} → OBJETIVO: {meal.get('calories','?')} kcal · "
                 f"P {meal.get('protein_g','?')}g · "
                 f"C {meal.get('carbs_g','?')}g · "
                 f"G {meal.get('fat_g','?')}g"]
        foods = meal.get("foods", [])
        if foods:
            ref = ", ".join(f.get('name','') for f in foods if f.get('name'))
            if ref:
                lines.append(f"    (referencia nutric. del médico: {ref} — diseñar platillo DIFERENTE)")
        return lines

    def _build_single_context(self, diet_plan: dict) -> str:
        person = diet_plan.get("person", "")
        goal = diet_plan.get("goal", "")
        nutritionist = diet_plan.get("nutritionist", "")
        targets = diet_plan.get("daily_targets", {})
        meal_structure = diet_plan.get("meal_structure", {})

        lines = [f"PLAN NUTRICIONAL DEL NUTRIÓLOGO — {person}"]
        if nutritionist:
            lines.append(f"Nutriólogo: {nutritionist}")
        if goal:
            lines.append(f"Objetivo: {goal}")
        lines.append(
            f"\nMETAS DIARIAS: {targets.get('calories','?')} kcal · "
            f"P {targets.get('protein_g','?')}g · "
            f"C {targets.get('carbs_g','?')}g · "
            f"G {targets.get('fat_g','?')}g"
        )
        lines.append("\nOBJETIVOS DE MACROS POR TIEMPO (diseñar platillos originales que alcancen estos valores):")
        meal_labels = {
            "desayuno": "Desayuno", "colacion_am": "Colación AM",
            "comida": "Comida", "colacion_pm": "Colación PM", "cena": "Cena",
        }
        for key, label in meal_labels.items():
            lines += self._fmt_meal(meal_structure.get(key), label)

        for s in diet_plan.get("supplements", []):
            lines.append(f"\n  Suplemento: {s.get('name','')} {s.get('dose','')} — {s.get('timing','')}")
        for inst in diet_plan.get("special_instructions", []):
            lines.append(f"  Instrucción: {inst}")
        return "\n".join(lines)

    def _build_combined_context(self, diet_plan: dict) -> str:
        persons = diet_plan.get("persons", {})
        household = diet_plan.get("household", {})
        shopping = household.get("shopping_daily_totals", {})

        lines = [
            "PLAN NUTRICIONAL COMBINADO — dos personas con PORCIONES INDIVIDUALES",
            "Se cocina UN SOLO PLATILLO para ambas; las cantidades de ingredientes varían por persona.",
            "",
        ]

        meal_labels = {
            "desayuno": "Desayuno", "colacion_am": "Colación AM",
            "comida": "Comida", "colacion_pm": "Colación PM", "cena": "Cena",
        }

        for person, data in persons.items():
            targets = data.get("daily_targets", {})
            meal_structure = data.get("meal_structure", {})
            goal = data.get("goal", "")
            has_foods = self._person_has_foods(data)
            lines.append(f"── {person} {'(objetivo: ' + goal + ')' if goal else ''}")
            lines.append(
                f"  META DIARIA: {targets.get('calories','?')} kcal · "
                f"P {targets.get('protein_g','?')}g · "
                f"C {targets.get('carbs_g','?')}g · "
                f"G {targets.get('fat_g','?')}g"
            )
            lines.append("  Objetivos por tiempo de comida (crear platillos creativos que alcancen estos macros):")
            for key, label in meal_labels.items():
                lines += self._fmt_meal(meal_structure.get(key), label)
            for s in data.get("supplements", []):
                lines.append(f"  Suplemento: {s.get('name','')} {s.get('dose','')} — {s.get('timing','')}")
            for inst in data.get("special_instructions", []):
                lines.append(f"  Instrucción: {inst}")
            lines.append("")

        if shopping:
            lines.append(
                f"TOTALES PARA COMPRAS (ATM+IOB): {shopping.get('calories','?')} kcal · "
                f"P {shopping.get('protein_g','?')}g · "
                f"C {shopping.get('carbs_g','?')}g · "
                f"G {shopping.get('fat_g','?')}g"
            )

        lines.append(
            "\nREGLAS DE PORCIONES:"
            "\n• Diseñar platillos ORIGINALES para cada tiempo. Los alimentos del nutriólogo son referencia nutricional, no recetas a reproducir."
            "\n• Para AMBAS personas: elegir los ingredientes que quieras, pero calcular los gramos para que los macros del tiempo de comida coincidan con sus OBJETIVOS individuales (±3%)."
            "\nEjemplo de escala: si ATM necesita 520 kcal en comida y IOB necesita 400 kcal, y el platillo elegido es salmón (208 kcal/100g) → ATM 250g, IOB 192g."
            "\n• Cada tiempo de comida DEBE mostrar la tabla con macros y porciones de cada persona por separado."
        )
        return "\n".join(lines)
