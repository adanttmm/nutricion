from .base_skill import BaseSkill
from pathlib import Path
from datetime import date


class ShoppingValidatorSkill(BaseSkill):

    SYSTEM_PROMPT = """Eres un experto en supermercados de Ciudad de México Costco (Interlomas/Santa Fe) y City Market Santa Fe.

TU TAREA: Revisar una lista de compras, contrastar con el menu de la semana y asegurar que esta completa y no inventa ingredientes o cantidades no utilizadas. Revisar los sitios respectivos de las tiendas sugeridas para comprobar la disponibilidad de los ingredientes y  tienda asignada por fila. Corregir los errores de la lista o de asignación de tienda (si no hay disponibilidad sugerir "Amazon-MercadoLibre").

LÓGICA DE CORRECCIÓN (en orden):
1. Si falta ingredientes o cantidades agregar o modificar cantidades a la lista. 
2. Si el ingrediente no se usa en el menu de la semana, eliminar de la lista
3. Si la tienda asignada SÍ vende el ingrediente → mantener, Estado = ✅
4. Si la tienda asignada NO lo vende pero la otra tienda sí → cambiar tienda, Estado = ⚠️ Corregido
5. Si ninguna tienda física lo vende → cambiar a "Amazon-MercadoLibre" (elige el más lógico), Estado = 🌐 Online

COSTCO CDMX — Revisar sitio https://www.costco.com.mx/

CITY MARKET — Revisar sition https://www.lacomer.com.mx/lacomer/#!/home?succId=449&succFmt=200

MERCADO LIBRE / AMAZON MX — cuando ningún supermercado lo tiene:
Ingredientes muy específicos importados, especias ultra-nicho (galanga fresca, hojas pandanus, pimienta szechuan, asafétida, pasta shrimp fermentado), miso premium de importación, vinagres especiales (champaña, jerez añejo), licores/vinos para cocinar inusuales, utensilios especiales, ingredientes coreanos/japoneses de nicho

FORMATO DE SALIDA OBLIGATORIO:
1. Tabla completa corregida con UNA COLUMNA EXTRA al final: "Estado"
   | Ingrediente | Cantidad | Receta | Día | Tienda | Estado |
2. Sección de cambios: lista solo las filas modificadas con el motivo.
3. Si no hubo cambios, indicar "✅ Todas las asignaciones son correctas."

IMPORTANTE: No agregar ingredientes o cantidades que NO se utlicen en el menu."""

    def validate(self, shopping_path: str) -> Path:
        shopping_content = Path(shopping_path).read_text(encoding="utf-8")

        user_message = f"""Revisa la siguiente lista de compras y corrige las asignaciones de tienda incorrectas.

LISTA DE COMPRAS:
{shopping_content}

Genera la tabla corregida completa con la columna Estado, seguida del resumen de cambios."""

        content = self._call_claude(self.SYSTEM_PROMPT, user_message, max_tokens=8000)

        # Overwrite the same file with the validated version
        original_header = "\n".join(
            line for line in shopping_content.split("\n")[:3]
            if line.startswith("#")
        )
        validated_header = original_header + "\n\n> ✅ Validado por agente de verificación de tiendas\n\n"
        output_path = Path(shopping_path)
        output_path.write_text(validated_header + content, encoding="utf-8")
        return output_path
