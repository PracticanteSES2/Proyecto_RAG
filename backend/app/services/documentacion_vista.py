"""Vista de la documentación viva para la API: estructuras que el frontend pinta
sin decidir nada (ficha, cuerpo, historial, operaciones, diff por tramos y los
textos de la revisión).

Es la lógica pura de presentación que en Streamlit vive en
`src/docs_md/interfaz.py` (legado congelado que importa `streamlit`, así que el
backend no puede usarlo). Muere con él: ver docs/ARQUITECTURA.md §9.
"""
from __future__ import annotations

import difflib
from dataclasses import replace

from src.docs_md import repositorio
from src.docs_md.formato import (
    SECCION_HISTORIAL,
    SECCION_TEXTO,
    Documento,
    ErrorFormato,
    ErrorOperacion,
    Operacion,
    aplicar_operaciones,
    diferencias,
    parsear,
    secciones_para,
    serializar,
    validar,
)

SIN_VALOR = "—"
ACCION_TEXTO = {"agregar": "Agregar", "modificar": "Cambiar", "eliminar": "Quitar"}
CONTEXTO_DIFF = 1


# ---------------------------------------------------------------- documento

def etiqueta_pagina(item: dict) -> str:
    """«CONSULTAS DIA — Oportunidad … · Día» («General del tablero» para _general.md)."""
    if item.get("archivo") == repositorio.ARCHIVO_GENERAL:
        nombre = "General del tablero"
    else:
        nombre = item.get("pagina") or item.get("archivo", "")
    detalle = item.get("nombre_funcional") or ""
    texto = f"{nombre} — {detalle}" if detalle else nombre
    if item.get("bloque") and item.get("bloque") != "General":
        texto += f" · {item['bloque']}"
    return texto


def _valor(valor) -> str:
    if isinstance(valor, (list, tuple)):
        valor = ", ".join(str(v) for v in valor)
    return str(valor) if valor not in (None, "") else SIN_VALOR


def ficha(doc: Documento) -> list[dict]:
    filas = (
        ("Tablero", doc.meta.get("tablero")),
        ("Página", doc.pagina),
        ("Nombre funcional", doc.meta.get("nombre_funcional")),
        ("Bloque", doc.meta.get("bloque")),
        ("Tablas", doc.meta.get("tablas")),
        ("Versión", doc.meta.get("version")),
        ("Última actualización", doc.meta.get("actualizado")),
    )
    return [{"dato": dato, "valor": _valor(valor)} for dato, valor in filas]


def cuerpo(doc: Documento) -> dict:
    """Propósito y secciones con entradas, sin metadatos ni historial, en el
    orden del formato (y después las secciones extra del archivo)."""
    orden = secciones_para(doc.meta)
    secciones = []
    for seccion in orden + [s for s in doc.secciones if s not in orden]:
        if seccion in (SECCION_TEXTO, SECCION_HISTORIAL):
            continue
        entradas = doc.entradas(seccion)
        if entradas:
            secciones.append({"titulo": seccion,
                              "entradas": [{"nombre": e.nombre, "texto": e.texto} for e in entradas]})
    return {"proposito": doc.proposito.strip(), "secciones": secciones}


def historial(doc: Documento) -> list[dict]:
    """Historial de cambios, el más reciente primero."""
    return [{"nombre": e.nombre, "texto": e.texto} for e in reversed(doc.entradas(SECCION_HISTORIAL))]


def documento(grupo: str, tablero: str, archivo: str, texto: str) -> dict:
    base = {"grupo": grupo, "tablero": tablero, "archivo": archivo, "texto": texto,
            "ruta": f"{grupo}/{repositorio.CARPETA_MD}/{archivo}"}
    try:
        doc = parsear(texto)
    except ErrorFormato as exc:
        return {**base, "pagina": archivo.removesuffix(".md"), "interpretable": False, "valido": False,
                "errores_formato": [f"No se pudo interpretar la página: {exc}"], "ficha": [],
                "cuerpo": {"proposito": "", "secciones": []}, "historial": []}
    errores = validar(doc)
    return {**base, "pagina": doc.pagina, "interpretable": True, "valido": not errores, "errores_formato": errores,
            "ficha": ficha(doc), "cuerpo": cuerpo(doc), "historial": historial(doc)}


# ---------------------------------------------------------------- operaciones

def _es_proposito(op: Operacion) -> bool:
    return op.seccion.strip().casefold() == SECCION_TEXTO.casefold()


def describir_operacion(op: Operacion) -> str:
    """«Cambiar la entrada **«X»** de **Reglas de negocio**» (Markdown)."""
    if _es_proposito(op):
        return "Reescribir el **Propósito** de la página"
    verbo = ACCION_TEXTO.get(op.accion, op.accion.capitalize() or "¿?")
    preposicion = "en" if op.accion == "agregar" else "de"
    return f"{verbo} la entrada **«{op.entrada}»** {preposicion} **{op.seccion}**"


def texto_actual(antes: str, op: Operacion) -> str | None:
    """Texto que tiene hoy la entrada que la operación toca (None si no existe)."""
    try:
        doc = parsear(antes)
    except ErrorFormato:
        return None
    if _es_proposito(op):
        return doc.proposito
    for seccion in doc.secciones:
        if seccion.casefold() == op.seccion.strip().casefold():
            entrada = doc.buscar(seccion, op.entrada)
            return entrada.texto if entrada else None
    return None


def operaciones(propuesta) -> list[dict]:
    salida = []
    for indice, op in enumerate(propuesta.operaciones or []):
        actual = texto_actual(propuesta.antes, op) if op.accion in ("modificar", "eliminar") else None
        salida.append({"indice": indice, "accion": op.accion, "seccion": op.seccion, "entrada": op.entrada,
                       "descripcion": describir_operacion(op), "texto": op.texto, "texto_actual": actual or None,
                       "editable": op.accion != "eliminar"})
    return salida


def reaplicar(propuesta, nuevas: list[Operacion]):
    """Aplica las operaciones (corregidas a mano) sobre el texto «antes» y
    devuelve la propuesta con texto, diff y validación al día. Lanza
    ErrorOperacion / ErrorFormato si no aplican o rompen el formato."""
    doc = parsear(propuesta.antes)
    nuevo = aplicar_operaciones(doc, nuevas, propuesta.resumen)
    errores = validar(nuevo)
    if errores:
        raise ErrorOperacion("El resultado no cumple el formato: " + " ".join(errores))
    despues = serializar(nuevo)
    return replace(propuesta, operaciones=list(nuevas), despues=despues,
                   diff=diferencias(propuesta.antes, despues, repositorio.archivo_para(doc)), errores=[])


# ---------------------------------------------------------------- diff

def _lineas(texto: str) -> list[str]:
    return (texto or "").replace("\r\n", "\n").splitlines()


def bloques_diff(antes: str, despues: str, contexto: int = CONTEXTO_DIFF) -> list[dict]:
    """Solo los tramos cambiados, con `contexto` líneas iguales alrededor:
    [{"lineas": [{"tipo": "igual"|"sale"|"entra", "texto"}]}]."""
    a, b = _lineas(antes), _lineas(despues)
    bloques = []
    for grupo in difflib.SequenceMatcher(None, a, b, autojunk=False).get_grouped_opcodes(contexto):
        lineas = []
        for etiqueta, i1, i2, j1, j2 in grupo:
            if etiqueta == "equal":
                lineas += [{"tipo": "igual", "texto": t} for t in a[i1:i2]]
                continue
            if etiqueta in ("replace", "delete"):
                lineas += [{"tipo": "sale", "texto": t} for t in a[i1:i2]]
            if etiqueta in ("replace", "insert"):
                lineas += [{"tipo": "entra", "texto": t} for t in b[j1:j2]]
        bloques.append({"lineas": lineas})
    return bloques


def lineas_cambiadas(antes: str, despues: str) -> tuple[int, int]:
    """(agregadas, eliminadas)."""
    agregadas = eliminadas = 0
    for linea in difflib.unified_diff(_lineas(antes), _lineas(despues), lineterm="", n=0):
        if linea.startswith("+") and not linea.startswith("+++"):
            agregadas += 1
        elif linea.startswith("-") and not linea.startswith("---"):
            eliminadas += 1
    return agregadas, eliminadas


def diff(propuesta) -> dict:
    agregadas, eliminadas = lineas_cambiadas(propuesta.antes, propuesta.despues)
    return {"agregadas": agregadas, "eliminadas": eliminadas,
            "unificado": propuesta.diff or diferencias(propuesta.antes, propuesta.despues),
            "bloques": bloques_diff(propuesta.antes, propuesta.despues)}


def vista_previa(despues: str) -> dict | None:
    try:
        doc = parsear(despues)
    except ErrorFormato:
        return None
    return {"cuerpo": cuerpo(doc), "historial": historial(doc)}


# ---------------------------------------------------------------- textos de la revisión

METODOS_PAGINA = {
    "indicada": "la elegiste tú en el formulario",
    "reglas": "la nota la nombra o usa palabras que solo están en esa página",
    "medgemma": "MedGemma la eligió entre varias parecidas",
}


def como_se_eligio(propuesta) -> str:
    """Cómo se eligió la página, en palabras sencillas (vacío si no se sabe)."""
    metodo = getattr(propuesta, "metodo_pagina", "") or ""
    texto = METODOS_PAGINA.get(metodo, "")
    otras = [c for c in (getattr(propuesta, "candidatas", None) or []) if c != propuesta.pagina]
    if metodo == "medgemma" and otras:
        texto += f" (también: {', '.join(otras[:4])})"
    return texto


def tiempos_texto(segundos, tiempos_llm) -> str:
    """«preparada en 9.8 s · 2 llamadas a MedGemma (4.1 s + 5.2 s)»."""
    partes = []
    if segundos is not None:
        partes.append(f"preparada en {float(segundos):.1f} s")
    tiempos = [float(t) for t in (tiempos_llm or [])]
    if tiempos:
        llamadas = "1 llamada" if len(tiempos) == 1 else f"{len(tiempos)} llamadas"
        partes.append(f"{llamadas} a MedGemma (" + " + ".join(f"{t:.1f} s" for t in tiempos) + ")")
    return " · ".join(partes)


def formato_resultado(propuesta) -> list[str]:
    """Errores de formato del texto propuesto ([] si cumple)."""
    if not propuesta.despues:
        return ["La propuesta no trae el texto nuevo."]
    return validar(propuesta.despues)
