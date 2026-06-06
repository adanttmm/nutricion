from .base_skill import BaseSkill
from pathlib import Path
from datetime import date
import urllib.parse


class RecipeFinderSkill(BaseSkill):

    SYSTEM_PROMPT = """Eres un chef instructor que crea tarjetas de receta profesionales y concisas para cocineros avanzados.

NIVEL DEL COCINERO: Avanzado. No explicar técnicas básicas como "cortar la cebolla". Ir directo a la técnica y el resultado.
ESTILO: Gourmet. Incluir técnicas profesionales, consejos de temperatura, texturas y presentación elegante.
IDIOMA: Español mexicano.

ESTRUCTURA DE CADA TARJETA DE RECETA:

### [Nombre del Platillo]
**Tiempo:** prep XX min · cocción XX min | **Porciones:** 2 (ajustar si aplica)
**Macros por porción:** XXX kcal · P XXg · C XXg · G XXg

**Ingredientes**
Lista precisa con gramajes cuando importa

**Mise en place** *(qué adelantar el domingo)*
Lista de lo que se puede preparar con anticipación

**Elaboración**
Pasos numerados al estilo profesional — temperatura, técnica, indicadores visuales/táctiles de punto

**Emplatado**
Sugerencia de presentación de 1-2 líneas

**Conservación** *(si aplica para meal prep)*
Cómo y cuánto tiempo conservar

**Tip del chef**
Un consejo técnico no obvio

---
🎥 **Video tutorial:** [Buscar en YouTube](URL_YOUTUBE_ES) · [English version](URL_YOUTUBE_EN)
📖 **Receta de referencia:** [Buscar en Google](URL_GOOGLE)

---

IMPORTANTE para los URLs:
- YouTube ES: https://www.youtube.com/results?search_query=receta+[nombre-con-guiones]
- YouTube EN: https://www.youtube.com/results?search_query=how+to+make+[english-name-hyphens]
- Google: https://www.google.com/search?q=receta+gourmet+[nombre-con-guiones]
Los nombres en las URLs deben estar codificados (sin acentos, espacios como +)"""

    def generate_for_menu(self, menu_path: str, week_date: date = None) -> Path:
        if week_date is None:
            week_date = date.today()

        menu_content = Path(menu_path).read_text(encoding="utf-8")
        first_half, second_half = self._split_menu_days(menu_content)

        base_instruction = (
            "Crea las tarjetas de receta para todos los platillos indicados (excepto comida trampa 🎉). "
            "Organiza por día y tiempo de comida en el mismo orden del menú."
        )

        day_hdr = "Usa encabezados de sección exactamente así antes de cada grupo de recetas: '## 📅 NOMBRE_DÍA DD DE MES' con el nombre del día en mayúsculas igual que en el menú (ej: ## 📅 LUNES 8 DE JUNIO, ## 📅 JUEVES 11 DE JUNIO)."
        part1 = self._call_claude(
            self.SYSTEM_PROMPT,
            f"{base_instruction} {day_hdr}\n\n{first_half}",
            max_tokens=8000,
        )
        part2 = self._call_claude(
            self.SYSTEM_PROMPT,
            f"{base_instruction} {day_hdr}\n\n{second_half}\n\n"
            "Al final incluye '## Preparaciones Base Compartidas' si alguna base del domingo se reutiliza.",
            max_tokens=8000,
        )

        content = part1 + "\n\n---\n\n" + part2
        header = (
            f"# 📖 Recetario Semanal\n"
            f"## Semana del {week_date.strftime('%d de %B de %Y')}\n\n"
            f"> **Nivel:** Avanzado · **Para:** 2 personas (3 en comidas mar/mié/vie)\n\n---\n\n"
        )
        filename = f"recetas_{week_date.strftime('%Y-%m-%d')}.md"
        return self._save_output(header + content, "outputs/recipes", filename)

    @staticmethod
    def _split_menu_days(menu_content: str):
        """Split menu at day 4 (Thursday) so each half fits in one API call."""
        import re
        # Match only top-level day section headers (single # at start of line,
        # followed by the day name as a standalone word — not inside a table cell)
        day_re = re.compile(
            r'^## (?:📅\s*)?(LUNES|MARTES|MI[ÉE]RCOLES|JUEVES|VIERNES|S[ÁA]BADO|DOMINGO)',
            re.MULTILINE | re.IGNORECASE,
        )
        matches = list(day_re.finditer(menu_content))
        if len(matches) >= 4:
            split_pos = matches[3].start()   # split before day 4 (Thursday)
            return menu_content[:split_pos], menu_content[split_pos:]
        # Fallback: split roughly in half by character count
        mid = len(menu_content) // 2
        return menu_content[:mid], menu_content[mid:]

    def find_single(self, dish_name: str) -> str:
        user_message = f"Crea la tarjeta de receta completa para: **{dish_name}**"
        return self._call_claude(self.SYSTEM_PROMPT, user_message, max_tokens=2000)
