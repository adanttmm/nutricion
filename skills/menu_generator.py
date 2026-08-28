from .base_skill import BaseSkill
from pathlib import Path
from datetime import date, timedelta
import re
import yaml


class MenuGeneratorSkill(BaseSkill):

    SYSTEM_PROMPT = """Eres un chef amateur gourmet y nutriólogo profesional. Creas menús semanales variados, elegantes, con porciones individualizadas por persona.

PERFIL DEL COCINERO:
- Nivel avanzado, gourmet amateur cómodo con técnicas profesionales (confitado, reducciones, emulsiones, fermentados, braseado, sellado a fuego alto, cocción al vapor, horneado a baja temperatura, helados, ahumado, rostizado, carbón).
- Equipamiento completo incluye: horno, 4+ quemadores, procesador, batidora, sartenes de hierro y antiadherente, vaporera, CIRCULADOR SOUS VIDE (disponible para cualquier platillo), MÁQUINA DE PASTA (para pasta fresca artesanal), Maquina de helados.
- Cualquier gastronomía cuyos ingredientes se encuentren en México. En orden de preferencia:
    1 - Mexicana
    2 - Japonesa
    3 - Thai
    4 - Italiana
    5 - Francesa
    6 - China
    7 - Peruana
    8 - Mediterránea
    9 - Alemana
    10 - Turca
    11 - Libanesa
- El mensaje SIEMPRE incluye una sección "PLATILLOS DE SEMANAS ANTERIORES" con lo cocinado recientemente — REGLA DURA, no opcional: NINGÚN platillo del menú nuevo puede coincidir, ni exacta ni aproximadamente, con algo de esa lista. "Aproximadamente" significa: misma proteína principal + misma técnica + salsa/sabor equivalente aunque el nombre cambie (ej. "Salmón en Miso Sous Vide" y "Salmón en Miso Glaseado" cuentan como EL MISMO platillo — prohibido repetir). Si notas que sigues regresando a los mismos platillos favoritos semana tras semana (salmón en miso, tacos de camarón/chuleta ahumada, bowls de atún, batidos de mango/kiwi, parfait de skyr), estás fallando esta regla — elige activamente otra proteína, técnica o gastronomía distinta esta semana.
- Cocina para 2 personas (ATM e IOB) en todos los tiempos; martes, miércoles y viernes hay un 3er comensal a la comida con la misma porción que IOB; evitar ingredientes premium o demasiado exoticos los dias del tercer comensal
- 1 comida trampa por semana (restaurante o platillo especial sin restricciones)
- Meal prep con equilibrio inteligente: la mayor parte se cocina el domingo, PERO puedo dedicar algun tiempo para cocinar en la semana. El objetivo es ≤30 min activos de cocción entre semana.

REGLAS DEL MENÚ:
1. Generar los 7 días completos: lunes, martes, miércoles, jueves, viernes, sábado y domingo sin excepción.
2. No repetir la proteína principal más de 2 veces por semana en comida y cena.
3. CERO repetición contra "PLATILLOS DE SEMANAS ANTERIORES" (ver regla dura arriba) — varía activamente proteína, técnica y gastronomía respecto a esa lista.
4. Las calorías y macros de CADA PERSONA deben coincidir con SUS metas (±5%). Los NÚMEROS son la ley; los alimentos son libres.
5. Se cocina UN SOLO PLATILLO para ambas personas — las porciones varían por persona.
6. Ingredientes accesibles en Costco Ciudad de México + City Market Santa Fe + Mercado Libre.
7. Nombres de platillos elegantes y descriptivos, al estilo de menú de restaurante.
8. DISEÑO PARA MEAL PREP INTELIGENTE: proteínas, granos y salsas de TODOS los días deben llevar 🏪 o 🌊 (sous vide entre semana). Los únicos elementos frescos entre semana son aguacate, huevo al momento, hierbas frescas o ensalada cruda.
9. Ajusta ingredientes y platillos a la temporada del mes indicado en el mensaje (frutas/verduras de temporada en México).
10. ASEGURA QUE CUMPLES CON LAS NOTAS DE LA SEMANA RECIBIDAS EN notas_semana.txt

OPTIMIZACIÓN DE CARGA DE COCINA — REPETICIÓN CONTROLADA:
Para reducir el número de recetas únicas a preparar, usa este esquema OBLIGATORIO:
- DESAYUNO: exactamente 2 variantes. Variante A: lunes+martes+miércoles. Variante B: jueves+viernes+sábado+domingo. Nombrarlos idéntico en todos los días que los usan.
- COLACIÓN AM: exactamente 2 variantes. Variante A: lunes+martes+miércoles+jueves. Variante B: viernes+sábado+domingo.
- COLACIÓN PM: exactamente 2 variantes de PLATILLO. Variante A: lunes+miércoles+viernes (días de gym). Variante B: martes+jueves+sábado+domingo (días de salsa o descanso). El PLATILLO es el mismo dentro de cada variante, pero la PORCIÓN no: martes/jueves (salsa, IOB) llevan más cantidad que sábado/domingo (descanso) del mismo platillo. La sección "ACTIVIDAD DE LA SEMANA" del mensaje te da, para cada día, el objetivo EXACTO en kcal de Colación PM por persona (base + bono ya sumado) — usa ese número directamente, no vuelvas a sumar el bono tú mismo.
- COMIDA: exactamente 3 platillos únicos de comida rotando toda la semana: Variante A: lunes+jueves (mismo platillo exacto); Variante B: martes+viernes (mismo platillo exacto); Variante C: miércoles+sábado+domingo (mismo platillo exacto). Total: solo 3 recetas únicas de comida. El sábado y domingo reutilizan el prep del miércoles — cero cocción adicional el fin de semana.
- CENA: exactamente 2 variantes. Variante A: lunes+martes+miércoles. Variante B: jueves+viernes+domingo. Sábado: comida trampa 🎉 (no requiere cena de prep).
Esta optimización significa solo ~11 recetas únicas. El fin de semana se libera significativamente al tener solo 3 comidas únicas en lugar de 4.

USO DEL PLAN NUTRICIONAL:
- El plan del nutriólogo define METAS NUMÉRICAS por tiempo de comida (kcal, proteína, carbohidratos, grasa). Esos números son obligatorios.
- Los ALIMENTOS que el nutriólogo listó son solo una referencia de qué tan saciante o denso es el plan — NO son el menú a reproducir.
- Diseña platillos ORIGINALES y CREATIVOS cada semana que alcancen los mismos macros. Varía proteínas, granos, verduras, técnicas y gastronomías libremente.

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
(estas cantidades SIEMPRE son peso COCIDO / como se sirve en el plato — igual que las metas de kcal/macros, que están calculadas sobre el alimento ya cocido. NUNCA escribas "crudo" aquí ni uses peso crudo; el peso crudo/de compra vive únicamente en la tarjeta de receta aparte)

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
Al final: tabla resumen con totales diarios por persona y promedios semanales.

NO incluyas una lista de compras ni resumen de ingredientes a comprar en este documento — eso lo genera un skill aparte con cálculo exacto de cantidades. Termina el documento en la tabla resumen semanal."""

    def generate(
        self, diet_plan_path: str, week_start: date = None, feedback: str = "",
        ratings_context: str = "", week_notes: str = "", use_history: bool = True,
    ) -> Path:
        if week_start is None:
            today = date.today()
            days_until_monday = (7 - today.weekday()) % 7 or 7
            week_start = today + timedelta(days=days_until_monday)

        with open(diet_plan_path, encoding="utf-8") as f:
            diet_plan = yaml.safe_load(f)

        # menu_history.txt is written every run (see bottom of this method) and,
        # by default, always read back — this is the anti-repetition mechanism
        # (the model drifts back to the same handful of favorite dishes without
        # an explicit "don't repeat this" list). use_history=False exists only
        # for one-off testing/exploration, never for real weekly runs.
        history = ""
        history_path = Path("data/menu_history.txt")
        if use_history and history_path.exists():
            text = history_path.read_text(encoding="utf-8").strip()
            if text:
                history = (
                    "\n\nPLATILLOS DE SEMANAS ANTERIORES (REGLA DURA — ver arriba, "
                    f"prohibido repetir exacta o aproximadamente):\n{self._recent_history_weeks(text, weeks=4)}"
                )

        gym_days = self.user_profile.get("activity", {}).get("gym", {}).get("days", [])
        salsa_days = self.user_profile.get("activity", {}).get("salsa_dancing", {}).get("days", [])
        gym_bonus = diet_plan.get("context", {}).get("gym_calorie_bonus", 150)
        salsa_bonus = diet_plan.get("context", {}).get("salsa_calorie_bonus", 100)
        # Convention already fixed by the system prompt: the gym bonus applies to
        # ATM (who does gym), the salsa bonus to IOB (who does salsa dancing).
        colacion_pm_base = self._colacion_pm_base(diet_plan)
        day_names = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
        days_info = []
        for i, day_name in enumerate(day_names):
            d = week_start + timedelta(days=i)
            notes = []
            if day_name in gym_days:
                notes.append(f"+{gym_bonus} kcal (gym, ATM)")
            if day_name in salsa_days:
                notes.append(f"+{salsa_bonus} kcal (salsa, IOB)")
            line = f"- {day_name.capitalize()} {d.strftime('%d/%m')}: {', '.join(notes) if notes else 'día normal'}"

            # Compute the EXACT Colación PM target per person for this day —
            # don't leave the addition to the model, that's exactly what was
            # landing wrong (validator kept rejecting gym/salsa days for under-
            # shooting calories because the bonus wasn't reliably applied).
            if colacion_pm_base:
                exact = []
                for person, base in colacion_pm_base.items():
                    bonus = 0
                    if person == "ATM" and day_name in gym_days:
                        bonus = gym_bonus
                    elif person == "IOB" and day_name in salsa_days:
                        bonus = salsa_bonus
                    total = base + bonus
                    detail = f"{base:.0f}+{bonus} bono" if bonus else f"{base:.0f}, sin bono"
                    exact.append(f"{person}={total:.0f} kcal ({detail})")
                line += f"\n    → Colación PM OBJETIVO EXACTO (usa este número, no recalcules): {' · '.join(exact)}"
            days_info.append(line)

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

        content = self._call_claude(self.SYSTEM_PROMPT, user_message, max_tokens=24000)

        header = f"# 🍽️ Menú Semanal\n## Semana del {week_start.strftime('%d de %B de %Y')}\n\n"
        filename = f"menu_{week_start.strftime('%Y-%m-%d')}.md"
        output_path = self._save_output(header + content, "outputs/menus", filename)

        history_path.parent.mkdir(parents=True, exist_ok=True)
        # Only genuine dish-title lines: exactly one bold span covering the whole
        # line, AND not a nutrition-summary line. The bold-span check alone isn't
        # enough — some generations wrap an entire "Totales ... kcal" line in a
        # single bold span too, which would otherwise pass and crowd out real
        # dish names in the history the next generation sees.
        # `:` at the end (outside the bold markers) means it's a section label like
        # "**Proteínas:**" or "**Preparar el domingo:**", not a dish title — those
        # slipped into menu_history.txt and polluted the "don't repeat" list with
        # junk that isn't a repeatable dish.
        _SUMMARY_RE = re.compile(r'(?i)totales?\b|\bkcal\b')
        dish_lines = [
            line.strip()
            for line in content.split("\n")
            if (s := line.strip()).startswith("**") and s.endswith("**") and s.count("**") == 2
            and not s[2:-2].strip().endswith(":")
            and not _SUMMARY_RE.search(s)
        ]
        # De-dupe: the same dish legitimately appears on 2-4 days within one week
        # by design (meal-prep variant reuse) — write each unique dish once, not
        # once per day, so a week's own repeats don't crowd out older weeks.
        unique_dishes = list(dict.fromkeys(dish_lines))
        with open(history_path, "a", encoding="utf-8") as f:
            f.write(f"\n=== Semana {week_start.strftime('%Y-%m-%d')} ===\n")
            f.write("\n".join(unique_dishes) + "\n")

        return output_path

    @staticmethod
    def _recent_history_weeks(history_text: str, weeks: int = 3) -> str:
        """Return the last N *distinct* week-blocks (marked by '=== Semana
        YYYY-MM-DD ==='), not a raw character-count tail.

        A fixed character tail silently starves this once the file grows: one
        week's own intentionally-repeated dishes (same recipe reused 2-4x across
        days, by design, for meal-prep efficiency) alone can fill a few thousand
        characters, pushing genuinely older weeks out of view — which is exactly
        why specific dishes kept recurring for months (some appeared 15-20+
        times across the accumulated history without ever being visible to the
        model as "already used").

        Also collapses repeated blocks for the *same* week (retries within one
        run, or re-running the script for a week already generated, each append
        another block) down to the latest one, so "last 3 weeks" means 3
        distinct calendar weeks — not 3 duplicate attempts at the same week.
        """
        import re
        matches = list(re.finditer(r'^=== Semana (\S+) ===\s*\n', history_text, re.MULTILINE))
        if not matches:
            return history_text
        blocks: dict[str, str] = {}
        for i, m in enumerate(matches):
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(history_text)
            blocks.pop(m.group(1), None)  # drop earlier attempt's position, if any
            blocks[m.group(1)] = history_text[start:end].strip()
        return "\n\n".join(list(blocks.values())[-weeks:])

    @staticmethod
    def _colacion_pm_base(diet_plan: dict) -> dict:
        """Return {person: base_colacion_pm_kcal} straight from the parsed diet
        plan, for both combined (two-person) and single-person plan formats.
        Empty dict if the plan doesn't carry a parsed meal_structure (e.g. the
        template plan) — callers must treat that as "can't compute, skip"."""
        out = {}
        if diet_plan.get("document_type") == "combined_diet_plan" and "persons" in diet_plan:
            for person, data in diet_plan.get("persons", {}).items():
                cal = data.get("meal_structure", {}).get("colacion_pm", {}).get("calories")
                if cal:
                    out[person] = cal
        else:
            person = diet_plan.get("person", "")
            cal = diet_plan.get("meal_structure", {}).get("colacion_pm", {}).get("calories")
            if person and cal:
                out[person] = cal
        return out

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
