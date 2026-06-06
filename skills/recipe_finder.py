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
        chunks = self._split_menu_into_chunks(menu_content, chunk_size=2)

        day_hdr = (
            "Usa encabezados de sección exactamente así antes de cada grupo de recetas: "
            "'# 🗓️ NOMBRE_DÍA DD DE MES' con el nombre del día en mayúsculas igual que en el menú "
            "(ej: # 🗓️ LUNES 8 DE JUNIO, # 🗓️ JUEVES 11 DE JUNIO)."
        )
        base = (
            "Crea las tarjetas de receta para todos los platillos indicados (excepto comida trampa 🎉). "
            "Organiza por día y tiempo de comida en el mismo orden del menú."
        )

        parts = []
        for i, chunk in enumerate(chunks):
            extra = (
                "\nAl final incluye '## Preparaciones Base Compartidas' si alguna base del domingo se reutiliza."
                if i == len(chunks) - 1 else ""
            )
            parts.append(self._call_claude(
                self.SYSTEM_PROMPT,
                f"{base} {day_hdr}\n\n{chunk}{extra}",
                max_tokens=16000,
            ))

        content = "\n\n---\n\n".join(parts)
        header = (
            f"# 📖 Recetario Semanal\n"
            f"## Semana del {week_date.strftime('%d de %B de %Y')}\n\n"
            f"> **Nivel:** Avanzado · **Para:** 2 personas (3 en comidas mar/mié/vie)\n\n---\n\n"
        )
        filename = f"recetas_{week_date.strftime('%Y-%m-%d')}.md"
        return self._save_output(header + content, "outputs/recipes", filename)

    @staticmethod
    def _split_menu_into_chunks(menu_content: str, chunk_size: int = 2) -> list:
        """Split menu into chunks of `chunk_size` days each."""
        import re
        day_re = re.compile(
            r'^#{1,2} [^a-zA-Z\n]{0,10}(LUNES|MARTES|MI[ÉE]RCOLES|JUEVES|VIERNES|S[ÁA]BADO|DOMINGO)',
            re.MULTILINE | re.IGNORECASE,
        )
        matches = list(day_re.finditer(menu_content))
        if not matches:
            return [menu_content]
        chunks = []
        for i in range(0, len(matches), chunk_size):
            start = matches[i].start()
            end = matches[i + chunk_size].start() if i + chunk_size < len(matches) else len(menu_content)
            chunks.append(menu_content[start:end].strip())
        return chunks

    def find_single(self, dish_name: str) -> str:
        user_message = f"Crea la tarjeta de receta completa para: **{dish_name}**"
        return self._call_claude(self.SYSTEM_PROMPT, user_message, max_tokens=2000)
