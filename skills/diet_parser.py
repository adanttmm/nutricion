import re
import base64
import yaml
from pathlib import Path
from datetime import date

from .base_skill import BaseSkill


class DietParserSkill(BaseSkill):

    PARSER_SYSTEM_PROMPT = """Eres un nutriólogo experto en analizar documentos nutricionales escaneados.

TAREA:
Lee las imágenes y extrae la información nutricional. Hay dos tipos de documento:

A) PLAN ALIMENTARIO — tiene tiempos de comida (desayuno, comida, cena…) con alimentos y cantidades.
   → Extrae alimentos, cantidades y calcula calorías + macros.

B) ANÁLISIS DE COMPOSICIÓN CORPORAL — solo tiene medidas corporales sin plan de comidas.
   → Deriva las metas nutricionales con las fórmulas de abajo.

DERIVACIÓN DE METAS DESDE COMPOSICIÓN CORPORAL:
1. TMB (Mifflin-St Jeor):
   Mujer: 10×peso_kg + 6.25×altura_cm − 5×edad − 161
   Hombre: 10×peso_kg + 6.25×altura_cm − 5×edad + 5
   Si la altura no aparece o es inválida: estimar 165 cm (mujer) / 175 cm (hombre).
2. GET = TMB × 1.55 (si no se especifica actividad)
3. Ajuste por objetivo (leer sección "Control Músculo-Grasa" o equivalente):
   Solo perder grasa → GET − 400 kcal
   Solo ganar músculo → GET + 300 kcal
   Recomposición (ambos) → GET sin cambio
4. Macros:
   Recomposición: proteína 2.0 g/kg · carbs 4 g/kg · grasas = kcal restantes ÷ 9
   Pérdida grasa:  proteína 1.8 g/kg · carbs 3 g/kg · grasas = kcal restantes ÷ 9
   Ganancia músculo: proteína 2.2 g/kg · carbs 5 g/kg · grasas = kcal restantes ÷ 9
5. Distribuir en tiempos: desayuno 20 % · colacion_am 10 % · comida 30 % · colacion_pm 10 % · cena 25 %
6. Marcar derived_from_body_composition: true y foods: [] en todos los tiempos.

VALORES NUTRICIONALES DE REFERENCIA (por 100 g salvo indicación):
Proteína en polvo (1 porción 30g): 120kcal P24 C3 G1.5
Pechuga de pollo/pavo (cocida): 165kcal P31 C0 G3.6
Filete de res magro (cocido): 215kcal P26 C0 G12
Salmón (cocido): 208kcal P20 C0 G13
Huevo entero (1 pza 50g): 77kcal P6 C0.6 G5.3
Avena cruda (1 cda sopera 10g): 38kcal P1.7 C6.6 G0.7
Arroz cocido (1 taza 200g): 260kcal P5.4 C56 G0.6
Tortilla maíz (1 pza 30g): 65kcal P1.5 C13 G0.8
Pan integral (1 rebanada 30g): 80kcal P3 C14 G1.2
Chapata (1 pza 80g): 210kcal P7 C40 G2.5
Pasta cocida (1 taza 150g): 220kcal P8 C43 G1.3
Fresas (1 taza 150g): 50kcal P1 C12 G0.5
Manzana (1 pza 180g): 95kcal P0.5 C25 G0.3
Aguacate (1/4 pza 45g): 72kcal P0.9 C3.9 G6.5
Nueces (2 cdas 20g): 130kcal P3 C2.7 G13
Mantequilla de cacahuate (1 cda 16g): 96kcal P4 C3.4 G8
Miel de agave (1 cdita 7g): 21kcal P0 C5.8 G0
Jícama (1 taza 130g): 50kcal P1 C12 G0.1
Espárragos (1 taza 134g): 27kcal P3 C5 G0.2
Espinaca cruda (1 taza 30g): 7kcal P0.9 C1.1 G0.1
Gelatina light (1 taza 240ml): 10kcal P1 C1 G0

REGLAS:
- Si hay opciones ("A o B"), calcular el promedio.
- Ignorar suplementos (vitaminas, L-carnitina) en el conteo calórico de comidas.
- Para cantidades sin gramaje exacto, usar porción estándar mexicana.
- Mapeo de términos → clave estándar:
  DESAYUNO → desayuno
  ALMUERZO / COLACIÓN AM → colacion_am
  COMIDA / ALMUERZO PRINCIPAL → comida
  MERIENDA / COLACIÓN PM → colacion_pm
  CENA → cena

RESPONDE ÚNICAMENTE con YAML válido. Sin texto adicional. Sin markdown fences.

document_type: "diet_plan"
person: "[nombre o iniciales]"
document_date: "[YYYY-MM-DD o null]"
plan_number: "[número si aparece, null si no]"
goal: "[pérdida de grasa / ganancia muscular / recomposición / mantenimiento]"
nutritionist: "[nombre o null]"
derived_from_body_composition: false

daily_targets:
  calories: float
  protein_g: float
  carbs_g: float
  fat_g: float

meal_structure:
  desayuno:
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    foods:
      - name: "[alimento]"
        quantity: "[cantidad exacta del documento]"
        quantity_g: float
        calories: float
        protein_g: float
        carbs_g: float
        fat_g: float
  colacion_am:
    [mismo esquema — omitir si no existe]
  comida:
    [mismo esquema]
  colacion_pm:
    [mismo esquema — omitir si no existe]
  cena:
    [mismo esquema]

supplements:
  - name: "[suplemento]"
    dose: "[dosis]"
    timing: "[cuándo]"

special_instructions:
  - "[instrucción]"
"""

    COMBINER_SYSTEM_PROMPT = """Eres un nutriólogo experto. Tienes los planes de dos personas que viven juntas y comen los MISMOS platillos con PORCIONES distintas.

Un plan puede tener alimentos específicos prescritos (foods con gramos exactos) y el otro puede tener solo metas calóricas (foods vacío). Ambos son válidos.

ESTRUCTURA OBLIGATORIA:

document_type: combined_diet_plan
persons:
  [INICIALES]:
    goal: string
    derived_from_body_composition: bool
    daily_targets:
      calories: float
      protein_g: float
      carbs_g: float
      fat_g: float
    meal_structure:
      desayuno:
        calories: float
        protein_g: float
        carbs_g: float
        fat_g: float
        foods:
          - name: string
            quantity: string
            quantity_g: float
      [mismo esquema para colacion_am, comida, colacion_pm, cena — omitir si no existe]
    supplements: []
    special_instructions: []
  [INICIALES_2]:
    [misma estructura]

household:
  shopping_daily_totals:
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float

REGLAS:
- Preservar metas individuales exactamente — NO promediar.
- Para la persona sin foods prescritos: distribuir sus metas en los mismos tiempos que la otra persona, foods: [].
- household.shopping_daily_totals = SUMA de ambas personas.

RESPONDE ÚNICAMENTE con el YAML. Sin texto adicional. Sin markdown fences."""

    def _render_pdf_to_images(self, pdf_path: Path) -> list:
        import fitz
        doc = fitz.open(str(pdf_path))
        images = []
        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img_b64 = base64.standard_b64encode(pix.tobytes("png")).decode()
            images.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": img_b64},
            })
        doc.close()
        return images

    @staticmethod
    def _clean_yaml_response(text: str) -> str:
        text = text.strip()
        # Strip markdown code fences
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()
        # If Claude added explanatory prose before the YAML, strip it.
        # YAML root keys always start at column 0 with a known key name.
        yaml_start = re.search(
            r'^(document_type|person|persons|meal_structure|daily_targets)\s*:',
            text, re.MULTILINE,
        )
        if yaml_start and yaml_start.start() > 0:
            text = text[yaml_start.start():]
        return text.strip()

    def _apply_profile_overrides(self, yaml_path: Path) -> None:
        """Apply target_overrides from user_profile.yaml to a parsed plan, in-place."""
        profile_path = Path("config/user_profile.yaml")
        if not profile_path.exists():
            return
        with open(profile_path, encoding="utf-8") as f:
            profile = yaml.safe_load(f) or {}
        persons_cfg = profile.get("persons", {})
        if not persons_cfg:
            return

        with open(yaml_path, encoding="utf-8") as f:
            plan = yaml.safe_load(f) or {}

        meal_pct = {"desayuno": 0.20, "colacion_am": 0.10, "comida": 0.30,
                    "colacion_pm": 0.10, "cena": 0.25}
        changed = False

        def _override_person(person_data: dict, overrides: dict):
            person_data["goal"] = overrides.get("goal", person_data.get("goal", ""))
            t = person_data.setdefault("daily_targets", {})
            for key in ("calories", "protein_g", "carbs_g", "fat_g"):
                if key in overrides:
                    t[key] = overrides[key]
            for meal_name, meal_info in person_data.get("meal_structure", {}).items():
                pct = meal_pct.get(meal_name, 0.20)
                meal_info["calories"]  = round(t["calories"]  * pct, 1)
                meal_info["protein_g"] = round(t["protein_g"] * pct, 1)
                meal_info["carbs_g"]   = round(t["carbs_g"]   * pct, 1)
                meal_info["fat_g"]     = round(t["fat_g"]     * pct, 1)

        if plan.get("document_type") == "combined_diet_plan":
            for person_key, person_data in plan.get("persons", {}).items():
                cfg = persons_cfg.get(person_key, {})
                ov = cfg.get("target_overrides")
                if ov:
                    _override_person(person_data, ov)
                    changed = True
            if changed:
                totals = {"calories": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}
                for person_data in plan["persons"].values():
                    for k in totals:
                        totals[k] += person_data["daily_targets"].get(k, 0)
                plan.setdefault("household", {})["shopping_daily_totals"] = {
                    k: round(v, 1) for k, v in totals.items()
                }
        else:
            person_key = (plan.get("person") or "").split()[0].upper()
            if not person_key:
                for k in persons_cfg:
                    if k in str(yaml_path).upper():
                        person_key = k
                        break
            cfg = persons_cfg.get(person_key, {})
            ov = cfg.get("target_overrides")
            if ov:
                _override_person(plan, ov)
                changed = True

        if changed:
            yaml_path.write_text(
                yaml.dump(plan, allow_unicode=True, default_flow_style=False, indent=2),
                encoding="utf-8",
            )

    def _safe_load_with_retry(self, yaml_text: str, source_name: str) -> tuple:
        """Return (parsed_dict, final_yaml_text). Retries once via text call if YAML is invalid."""
        try:
            parsed = yaml.safe_load(yaml_text)
            if isinstance(parsed, dict):
                return parsed, yaml_text
            raise ValueError("not a dict")
        except (yaml.YAMLError, ValueError) as first_err:
            fix_response = self.client.messages.create(
                model=self.MODEL,
                max_tokens=4096,
                messages=[{"role": "user", "content": (
                    f"El siguiente texto debería ser YAML puro pero contiene texto adicional "
                    f"o errores de sintaxis: {first_err}\n\n"
                    f"Texto a corregir:\n{yaml_text}\n\n"
                    "Extrae y devuelve ÚNICAMENTE el bloque YAML válido con los datos nutricionales. "
                    "Sin explicaciones, sin markdown fences, sin texto adicional."
                )}],
            )
            fixed = self._clean_yaml_response(fix_response.content[0].text)
            parsed = yaml.safe_load(fixed)
            if not isinstance(parsed, dict):
                raise ValueError(f"El parser no devolvió YAML válido para {source_name}")
            return parsed, fixed

    def parse_pdf(self, pdf_path: str) -> Path:
        """Parse a nutritionist's scanned PDF via Claude Vision. Returns path to saved YAML."""
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"Archivo no encontrado: {pdf_path}")

        parts = pdf_path.stem.split("_", 1)
        person = parts[1].upper() if len(parts) >= 2 else "UNKNOWN"
        file_date = parts[0] if len(parts[0]) == 8 and parts[0].isdigit() else date.today().strftime("%Y%m%d")

        images = self._render_pdf_to_images(pdf_path)
        content = images + [{
            "type": "text",
            "text": (
                f"Documento del nutriólogo para: {person}. "
                f"Fecha del archivo: {file_date[:4]}-{file_date[4:6]}-{file_date[6:]}. "
                "Extrae toda la información nutricional y genera el YAML."
            ),
        }]

        response = self.client.messages.create(
            model=self.MODEL,
            max_tokens=8192,
            system=[{"type": "text", "text": self.PARSER_SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": content}],
        )

        yaml_text = self._clean_yaml_response(response.content[0].text)
        _, clean_yaml = self._safe_load_with_retry(yaml_text, pdf_path.name)

        output_dir = Path("config/parsed_diets")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{file_date}_{person}.yaml"
        output_path.write_text(clean_yaml, encoding="utf-8")
        self._apply_profile_overrides(output_path)
        return output_path

    def create_combined_plan(self, parsed_paths: dict) -> Path:
        """Merge per-person parsed YAMLs into one combined household plan."""
        plans = {}
        for person, path in parsed_paths.items():
            with open(path, encoding="utf-8") as f:
                plans[person] = yaml.safe_load(f)

        output_dir = Path("config/parsed_diets")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"combined_{date.today().strftime('%Y%m%d')}.yaml"

        if len(plans) == 1:
            person, plan = next(iter(plans.items()))
            output_path.write_text(
                yaml.dump(plan, allow_unicode=True, default_flow_style=False, indent=2),
                encoding="utf-8",
            )
            return output_path

        plans_yaml = "\n\n".join(
            f"# PLAN {person}:\n{yaml.dump(plan, allow_unicode=True, indent=2)}"
            for person, plan in plans.items()
        )

        response = self.client.messages.create(
            model=self.MODEL,
            max_tokens=6000,
            system=[{"type": "text", "text": self.COMBINER_SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": plans_yaml}],
        )

        combined_yaml = self._clean_yaml_response(response.content[0].text)
        _, combined_yaml = self._safe_load_with_retry(combined_yaml, "combined plan")
        output_path.write_text(combined_yaml, encoding="utf-8")
        self._apply_profile_overrides(output_path)
        return output_path

    @staticmethod
    def find_latest_diets(dietas_dir: str = "Dietas") -> dict:
        """Return {PERSON: Path} for the most recent PDF per person in dietas_dir."""
        dietas_path = Path(dietas_dir)
        if not dietas_path.exists():
            raise FileNotFoundError(
                f"Carpeta '{dietas_dir}' no encontrada. "
                "Créala y coloca los PDFs del nutriólogo con el nombre YYYYMMDD_INICIALES.pdf"
            )

        pattern = re.compile(r"^(\d{8})_([A-Za-z]+)$", re.IGNORECASE)
        latest: dict = {}

        for f in sorted(dietas_path.iterdir()):
            if not f.is_file() or f.suffix.lower() not in (".pdf", ""):
                continue
            match = pattern.match(f.stem)
            if not match:
                continue
            file_date, person = match.group(1), match.group(2).upper()
            if person not in latest or file_date > latest[person]["date"]:
                latest[person] = {"date": file_date, "path": f}

        return {person: info["path"] for person, info in latest.items()}
