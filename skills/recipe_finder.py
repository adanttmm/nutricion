from .base_skill import BaseSkill
from pathlib import Path
from datetime import date
import urllib.parse


class RecipeFinderSkill(BaseSkill):

    SYSTEM_PROMPT = """Eres un chef instructor que crea tarjetas de receta profesionales y concisas para cocineros avanzados. Busca recetas rapidas, eficientes, fit, gourmet amateur y comida hogareña como referencia y conserva los links para usar en las tarjetas.

NIVEL DEL COCINERO: Avanzado. No explicar técnicas básicas. Ir directo a la técnica y el resultado.
ESTILO: Gourmet amateur, rápido, eficiente, fit y hogareño. Técnicas profesionales, temperaturas exactas, indicadores visuales/táctiles de punto.
EQUIPO: horno convencional, estufa de gas, sartén de hierro, olla de presión, licuadora, procesador, batidora, maquina helados, big green egg, ahumados y rostiados.
INGREDIENTES: Preferentemente locales, frescos y de temporada. También considerar conservas gourmet. EXLCUIR TERMINANTEMENTE LOS SIGUIENTES INGREDIENTES:
    - Tajin
IDIOMA: Español mexicano.

ESTRUCTURA DE CADA TARJETA — exactamente así, sin secciones adicionales:

### [emoji] [Tiempo de comida] — [Nombre del Platillo]
**Tiempo:** prep XX min · cocción XX min | **Porciones:** 2 (o 3 si aplica)

| Ingrediente | 🧔 ATM | 👤 IOB |
|---|---|---|
| [nombre ingrediente] | [cantidad cruda] | [cantidad cruda] |

*(una fila por ingrediente con peso en crudo; omitir condimentos "al gusto")*

**Preparación**
Pasos numerados enunciando ingredientes y cantidades respectivas. Para cada paso que se realiza el fin de semana en el meal prep, antepón exactamente esta nota en cursiva:
*🏪 Prep fin de semana — hecho el domingo, guardar refrigerado.*
Luego el paso normalmente. Los pasos del día de servicio van directamente sin nota.

**Emplatado**
1-2 líneas de presentación.

**Tip del chef**
Un consejo técnico no obvio.

---
Agregar link de referencia.
🎥 [Buscar en YouTube ES](https://www.youtube.com/results?search_query=receta+NOMBRE) · [YouTube EN](https://www.youtube.com/results?search_query=how+to+make+NOMBRE_EN) · [Referencia Google](https://www.google.com/search?q=receta+gourmet+NOMBRE)

---

REGLAS:
- NO incluir secciones "Mise en place", "Conservación", "Regeneración" ni "Meal prep durante la semana". Solo las secciones indicadas arriba.
- Los URLs deben tener nombres codificados (sin acentos, espacios como +).
- Si el mismo platillo aparece varios días, genera la tarjeta completa cada vez — nunca referencies otro día."""

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
            "Organiza por día y tiempo de comida en el mismo orden del menú. "
            "IMPORTANTE: Si el mismo platillo aparece en múltiples días, genera la receta COMPLETA en cada día. "
            "Nunca uses referencias a otros días ('Ver receta del X') — cada día debe ser completamente autónomo."
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
            f"> **Nivel:** Avanzado · **Para:** 2 personas (3 en comidas mar/mié/vie — 3er comensal porción IOB)\n\n---\n\n"
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
