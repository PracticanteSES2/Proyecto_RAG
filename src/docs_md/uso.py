"""
Uso de campos (columnas y medidas) en las páginas y visuales de un tablero.

    uso = uso_de_campos(hechos)
    # {"ANTIBIOTICOS[SERVICIO]": [{"pagina": "ANTIBIOTICOS", "visual": "Segmentación de ANTIBIOTICOS[SERVICIO]",
    #                              "tipo": "slicer", "titulo": None}],
    #  "[PAC_ACT]": [{"pagina": "ANTIBIOTICOS", "visual": "Tarjeta «PACIENTES ACTIVOS»", "tipo": "card",
    #                 "titulo": "PACIENTES ACTIVOS"}]}

`hechos` es lo que devuelve `pbip.extraer_hechos`. La clave es `Tabla[col]` para
columnas y `[Medida]` para medidas (se distinguen con `hechos["medidas"]`).
Cuentan los campos de los visuales, sus filtros, los filtros de página
(visual «filtro de la página») y los del informe (página «TODO EL INFORME»).
No se leen datos: solo los hechos del informe.
"""

from __future__ import annotations

import re

from . import pbip

PAGINA_INFORME = "TODO EL INFORME"
VISUAL_FILTRO_PAGINA = "Filtro de la página"
VISUAL_FILTRO_INFORME = "Filtro del informe"


_HEX_LARGO = re.compile(r"[_-]?(?:[0-9A-Fa-f]{4,}[_-]?){3,}")


def etiqueta_visual(v: dict) -> str:
    """Nombre legible del visual; los identificadores internos (visuales
    personalizados) se quitan: «textFilter25A4… «NOMBRE»» -> «textFilter «NOMBRE»»."""
    nombre = pbip._nombre_visual(v)
    limpio = re.sub(r"\s+", " ", _HEX_LARGO.sub("", nombre)).strip(" _-")
    return limpio or "Visual personalizado"


def _patron_campos(tablas: list[str]) -> re.Pattern:
    """«Tabla[col]»: primero las tablas conocidas (pueden tener espacios), luego
    cualquier identificador sin espacios."""
    conocidas = sorted({t for t in tablas if t}, key=len, reverse=True)
    alternativas = [re.escape(t) for t in conocidas] + [r"[\w.]+"]
    return re.compile(r"(?<![\w.])(?P<tabla>" + "|".join(alternativas) + r")\[(?P<campo>[^\[\]]+)\]")


def referencias(expresion: str, patron: re.Pattern, medidas: set[str]) -> list[str]:
    """Claves de campo citadas en una expresión de los hechos
    («AVERAGE(T[c])», «T[c] > 5», «T[Date] (Año)»)."""
    claves = []
    for m in patron.finditer(str(expresion or "")):
        tabla, campo = m.group("tabla").strip().strip("'"), m.group("campo").strip()
        if not tabla or not campo:
            continue
        clave = f"[{campo}]" if f"{tabla}[{campo}]" in medidas else f"{tabla}[{campo}]"
        if clave not in claves:
            claves.append(clave)
    return claves


def uso_de_campos(hechos: dict) -> dict[str, list[dict]]:
    """{clave: [{"pagina", "visual", "tipo", "titulo"}]} sin repetidos, en el orden de las páginas."""
    medidas = set((hechos.get("medidas") or {}).keys())
    patron = _patron_campos(list((hechos.get("tablas") or {}).keys()))
    uso: dict[str, list[dict]] = {}
    vistos: set = set()

    def registrar(clave: str, pagina: str, visual: str, tipo: str, titulo):
        llave = (clave, pagina, visual)
        if llave in vistos:
            return
        vistos.add(llave)
        uso.setdefault(clave, []).append({"pagina": pagina, "visual": visual, "tipo": tipo, "titulo": titulo})

    def registrar_textos(textos, pagina, visual, tipo, titulo):
        for texto in textos:
            for clave in referencias(texto, patron, medidas):
                registrar(clave, pagina, visual, tipo, titulo)

    for texto_filtro in hechos.get("filtros_reporte") or []:
        registrar_textos([texto_filtro], PAGINA_INFORME, VISUAL_FILTRO_INFORME, "filtro", None)

    for pagina in hechos.get("paginas") or []:
        nombre = pagina.get("nombre") or pagina.get("id") or "?"
        registrar_textos(
            list(pagina.get("filtros") or []) + list(pagina.get("obtener_detalles") or []),
            nombre, VISUAL_FILTRO_PAGINA, "filtro", None,
        )
        for v in pagina.get("visuales") or []:
            textos = list(v.get("campos") or [])
            textos += [d.get("expresion") for d in v.get("campos_detalle") or []]
            textos += list(v.get("filtros") or [])
            if not textos:
                continue
            registrar_textos(textos, nombre, etiqueta_visual(v), v.get("tipo") or "", v.get("titulo"))
    return uso


def texto_uso(usos: list[dict] | None, maximo: int = 6) -> str:
    """«PÁGINA › visual; PÁGINA › visual y N más» o «no aparece en visuales ni filtros»."""
    if not usos:
        return "no aparece en visuales ni filtros del informe"
    items = []
    for u in usos:
        item = f"{u['pagina']} › {u['visual']}"
        if item not in items:
            items.append(item)
    texto = "; ".join(items[:maximo])
    if len(items) > maximo:
        texto += f" y {len(items) - maximo} más"
    return texto
