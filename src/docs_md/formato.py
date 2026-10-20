"""
Formato estándar de la documentación viva de tableros (un archivo .md por página).

Estructura (forma canónica que produce `serializar`):

    ---
    tablero: TABLERO TIEMPOS URGENCIAS
    pagina: CONSULTAS DIA
    nombre_funcional: Oportunidad en la atención de consultas del día
    bloque: Día
    tablas: [CONSULTAS_DIA, EN_ESPERA_CONSULTA]
    actualizado: 2026-10-20
    version: 1
    ---

    # CONSULTAS DIA

    ## Propósito
    Texto libre (uno o varios párrafos).

    ## Indicadores
    - **Tiempo promedio para consulta**: Minutos entre ... Unidad: minutos.

    ## Historial de cambios
    - **2026-10-20 · v1**: Documentación inicial.

Reglas:
- Las secciones permitidas y su orden están en SECCIONES_PAGINA / SECCIONES_GENERAL.
- Toda sección, salvo «Propósito», es una lista de entradas `- **Nombre**: texto`.
  El nombre identifica la entrada (único en su sección, sin distinguir mayúsculas
  ni tildes) y es lo que usan las operaciones para modificarla o eliminarla.
- Una entrada ocupa una sola línea en la forma canónica; el texto termina en punto.
- Los nombres de sección coinciden con los que reconoce el normalizador del RAG
  (document_normalizer.classify_heading), así la ingesta no necesita mapeos.
"""

from __future__ import annotations

import copy
import difflib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date

SECCIONES_PAGINA = [
    "Propósito",
    "Fuentes de datos",
    "Indicadores",
    "Visuales",
    "Reglas de negocio",
    "Observaciones",
    "Historial de cambios",
]

SECCIONES_GENERAL = [
    "Propósito",
    "Fuentes de datos",
    "Definiciones",
    "Reglas de negocio",
    "Observaciones",
    "Historial de cambios",
]

SECCION_TEXTO = "Propósito"
SECCION_HISTORIAL = "Historial de cambios"
SECCIONES_OBLIGATORIAS = (SECCION_TEXTO, SECCION_HISTORIAL)

CAMPOS_META = ["tablero", "pagina", "nombre_funcional", "bloque", "tablas", "actualizado", "version"]
BLOQUES = ("General", "Día", "Histórico")

ACCIONES = ("agregar", "modificar", "eliminar")

MAX_NOMBRE = 90

_ENTRADA_RE = re.compile(r"^\s*[-*]\s+\*\*(?P<nombre>.+?)\*\*\s*[:：]\s*(?P<texto>.*)$")


class ErrorFormato(ValueError):
    """El texto no cumple el formato estándar."""


class ErrorOperacion(ValueError):
    """Una operación no se puede aplicar al documento."""


def normalizar_nombre(texto: str) -> str:
    """Clave de comparación: sin tildes, minúsculas y espacios simples."""
    texto = unicodedata.normalize("NFD", str(texto or ""))
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", texto).strip().casefold()


def secciones_para(meta: dict) -> list[str]:
    return SECCIONES_GENERAL if meta.get("bloque") == "General" else SECCIONES_PAGINA


@dataclass
class Entrada:
    nombre: str
    texto: str


@dataclass
class Documento:
    meta: dict
    titulo: str
    proposito: str = ""
    secciones: dict[str, list[Entrada]] = field(default_factory=dict)

    @property
    def pagina(self) -> str:
        return str(self.meta.get("pagina") or self.titulo)

    def entradas(self, seccion: str) -> list[Entrada]:
        return self.secciones.get(seccion, [])

    def buscar(self, seccion: str, nombre: str) -> Entrada | None:
        clave = normalizar_nombre(nombre)
        for entrada in self.entradas(seccion):
            if normalizar_nombre(entrada.nombre) == clave:
                return entrada
        return None


@dataclass
class Operacion:
    accion: str
    seccion: str
    entrada: str = ""
    texto: str = ""

    @classmethod
    def desde_dict(cls, data: dict) -> "Operacion":
        return cls(
            accion=str(data.get("accion") or "").strip().lower(),
            seccion=str(data.get("seccion") or "").strip(),
            entrada=str(data.get("entrada") or "").strip(),
            texto=str(data.get("texto") or "").strip(),
        )

    def a_dict(self) -> dict:
        return {"accion": self.accion, "seccion": self.seccion, "entrada": self.entrada, "texto": self.texto}


# ---------------------------------------------------------------------------
# Metadatos (subconjunto mínimo de YAML: clave: valor y listas [a, b])
# ---------------------------------------------------------------------------

def _parsear_valor(valor: str):
    valor = valor.strip()
    if valor.startswith("[") and valor.endswith("]"):
        interior = valor[1:-1].strip()
        return [v.strip().strip("'\"") for v in interior.split(",") if v.strip()] if interior else []
    if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "'\"":
        return valor[1:-1]
    if re.fullmatch(r"\d+", valor):
        return int(valor)
    return valor


def _serializar_valor(valor) -> str:
    if isinstance(valor, (list, tuple)):
        return "[" + ", ".join(str(v) for v in valor) + "]"
    return str(valor)


# ---------------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------------

def parsear(texto: str) -> Documento:
    """Convierte el texto .md en Documento. Tolera espacios extra y entradas en
    varias líneas (las líneas siguientes sin viñeta se unen a la entrada)."""
    lineas = str(texto or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    meta: dict = {}
    i = 0
    while i < len(lineas) and not lineas[i].strip():
        i += 1
    if i < len(lineas) and lineas[i].strip() == "---":
        i += 1
        while i < len(lineas) and lineas[i].strip() != "---":
            linea = lineas[i]
            if linea.strip() and ":" in linea:
                clave, valor = linea.split(":", 1)
                meta[clave.strip()] = _parsear_valor(valor)
            i += 1
        if i >= len(lineas):
            raise ErrorFormato("Los metadatos no se cierran con '---'.")
        i += 1

    titulo = ""
    proposito: list[str] = []
    secciones: dict[str, list[Entrada]] = {}
    actual: str | None = None
    ultima: Entrada | None = None

    for linea in lineas[i:]:
        limpia = linea.strip()
        if limpia.startswith("# ") and not titulo and actual is None:
            titulo = limpia[2:].strip()
            continue
        if limpia.startswith("## "):
            actual = limpia[3:].strip()
            ultima = None
            if actual != SECCION_TEXTO:
                secciones.setdefault(actual, [])
            continue
        if actual is None:
            if limpia:
                raise ErrorFormato(f"Texto fuera de sección: «{limpia[:60]}».")
            continue
        if actual == SECCION_TEXTO:
            proposito.append(linea.rstrip())
            continue
        if not limpia:
            ultima = None
            continue
        m = _ENTRADA_RE.match(linea)
        if m:
            ultima = Entrada(m.group("nombre").strip(), m.group("texto").strip())
            secciones[actual].append(ultima)
        elif ultima is not None and not limpia.startswith(("-", "*", "#")):
            ultima.texto = (ultima.texto + " " + limpia).strip()
        else:
            raise ErrorFormato(f"Línea con formato no válido en «{actual}»: «{limpia[:60]}».")

    texto_proposito = "\n".join(proposito).strip()
    texto_proposito = re.sub(r"\n{3,}", "\n\n", texto_proposito)
    return Documento(meta=meta, titulo=titulo, proposito=texto_proposito, secciones=secciones)


# ---------------------------------------------------------------------------
# Escritura
# ---------------------------------------------------------------------------

def serializar(doc: Documento) -> str:
    """Forma canónica: metadatos en orden fijo, secciones en el orden del formato
    y una entrada por línea."""
    partes = ["---"]
    claves = [c for c in CAMPOS_META if c in doc.meta] + [c for c in doc.meta if c not in CAMPOS_META]
    for clave in claves:
        partes.append(f"{clave}: {_serializar_valor(doc.meta[clave])}")
    partes += ["---", "", f"# {doc.titulo or doc.pagina}", ""]

    orden = secciones_para(doc.meta)
    extra = [s for s in doc.secciones if s not in orden]
    for seccion in orden + extra:
        if seccion == SECCION_TEXTO:
            partes += [f"## {SECCION_TEXTO}", doc.proposito.strip(), ""]
            continue
        entradas = doc.secciones.get(seccion)
        if not entradas and seccion != SECCION_HISTORIAL:
            continue
        partes.append(f"## {seccion}")
        for e in entradas or []:
            texto = re.sub(r"\s+", " ", e.texto).strip()
            partes.append(f"- **{e.nombre.strip()}**: {texto}")
        partes.append("")
    return "\n".join(partes).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Validación
# ---------------------------------------------------------------------------

def validar(doc_o_texto) -> list[str]:
    """Lista de errores (vacía si el documento cumple el formato)."""
    errores: list[str] = []
    if isinstance(doc_o_texto, str):
        try:
            doc = parsear(doc_o_texto)
        except ErrorFormato as exc:
            return [str(exc)]
    else:
        doc = doc_o_texto

    for campo in ("tablero", "pagina", "bloque"):
        if not str(doc.meta.get(campo) or "").strip():
            errores.append(f"Falta el metadato «{campo}».")
    bloque = doc.meta.get("bloque")
    if bloque and bloque not in BLOQUES:
        errores.append(f"Bloque «{bloque}» no válido; use {', '.join(BLOQUES)}.")
    if doc.titulo and doc.meta.get("pagina") and doc.titulo != doc.meta.get("pagina"):
        errores.append("El título (# ...) debe ser igual al metadato «pagina».")
    if not doc.proposito.strip():
        errores.append("La sección «Propósito» está vacía.")

    permitidas = secciones_para(doc.meta)
    for seccion, entradas in doc.secciones.items():
        if seccion not in permitidas:
            errores.append(f"Sección «{seccion}» no permitida; use: {', '.join(permitidas)}.")
            continue
        vistos = set()
        for e in entradas:
            clave = normalizar_nombre(e.nombre)
            if not clave:
                errores.append(f"Entrada sin nombre en «{seccion}».")
            if len(e.nombre) > MAX_NOMBRE:
                errores.append(f"Nombre demasiado largo en «{seccion}»: «{e.nombre[:40]}…».")
            if clave in vistos:
                errores.append(f"Entrada repetida en «{seccion}»: «{e.nombre}».")
            vistos.add(clave)
            if not e.texto.strip():
                errores.append(f"La entrada «{e.nombre}» de «{seccion}» no tiene texto.")
            elif not e.texto.rstrip().endswith((".", "?", "!", ")", "»")):
                errores.append(f"El texto de «{e.nombre}» ({seccion}) debe terminar en punto.")
    if SECCION_HISTORIAL not in doc.secciones:
        errores.append("Falta la sección «Historial de cambios».")
    return errores


# ---------------------------------------------------------------------------
# Operaciones
# ---------------------------------------------------------------------------

def _seccion_canonica(nombre: str, permitidas: list[str]) -> str | None:
    clave = normalizar_nombre(nombre)
    for s in permitidas:
        if normalizar_nombre(s) == clave:
            return s
    return None


def _cerrar_texto(texto: str) -> str:
    texto = re.sub(r"\s+", " ", texto or "").strip()
    if texto and not texto.endswith((".", "?", "!", ")", "»")):
        texto += "."
    return texto


def aplicar_operaciones(
    doc: Documento,
    operaciones: list[Operacion],
    resumen: str,
    autor: str = "",
    fecha: str | None = None,
) -> Documento:
    """Aplica las operaciones sobre una copia del documento y agrega la entrada
    del historial (fecha · versión). Lanza ErrorOperacion si alguna no aplica;
    en ese caso el documento original no cambia."""
    if not operaciones:
        raise ErrorOperacion("No hay operaciones para aplicar.")
    nuevo = copy.deepcopy(doc)
    permitidas = secciones_para(nuevo.meta)

    for op in operaciones:
        if op.accion not in ACCIONES:
            raise ErrorOperacion(f"Acción «{op.accion}» no válida; use {', '.join(ACCIONES)}.")
        seccion = _seccion_canonica(op.seccion, permitidas)
        if seccion is None:
            raise ErrorOperacion(f"Sección «{op.seccion}» no existe; use: {', '.join(permitidas)}.")
        if seccion == SECCION_HISTORIAL:
            raise ErrorOperacion("El historial se actualiza automáticamente; no se edita con operaciones.")

        if seccion == SECCION_TEXTO:
            if op.accion != "modificar" or not op.texto.strip():
                raise ErrorOperacion("«Propósito» solo admite la acción modificar con el texto completo nuevo.")
            nuevo.proposito = op.texto.strip()
            continue

        entradas = nuevo.secciones.setdefault(seccion, [])
        existente = nuevo.buscar(seccion, op.entrada)
        if not op.entrada.strip():
            raise ErrorOperacion(f"La operación en «{seccion}» no indica el nombre de la entrada.")
        if len(op.entrada) > MAX_NOMBRE:
            raise ErrorOperacion(f"El nombre de la entrada es demasiado largo: «{op.entrada[:40]}…».")

        if op.accion == "agregar":
            if existente is not None:
                raise ErrorOperacion(f"Ya existe la entrada «{existente.nombre}» en «{seccion}»; use modificar.")
            if not op.texto.strip():
                raise ErrorOperacion(f"La entrada nueva «{op.entrada}» no tiene texto.")
            entradas.append(Entrada(op.entrada.strip(), _cerrar_texto(op.texto)))
        elif op.accion == "modificar":
            if existente is None:
                raise ErrorOperacion(f"No existe la entrada «{op.entrada}» en «{seccion}».")
            if not op.texto.strip():
                raise ErrorOperacion(f"La modificación de «{op.entrada}» no trae el texto nuevo.")
            existente.texto = _cerrar_texto(op.texto)
        else:  # eliminar
            if existente is None:
                raise ErrorOperacion(f"No existe la entrada «{op.entrada}» en «{seccion}».")
            entradas.remove(existente)

    fecha = fecha or date.today().isoformat()
    version = int(nuevo.meta.get("version") or 0) + 1
    nuevo.meta["version"] = version
    nuevo.meta["actualizado"] = fecha
    detalle = _cerrar_texto(resumen) or "Cambio sin resumen."
    if autor:
        detalle = f"{detalle} Autor: {autor.strip()}."
    nuevo.secciones.setdefault(SECCION_HISTORIAL, []).append(Entrada(f"{fecha} · v{version}", detalle))
    return nuevo


def diferencias(antes: str, despues: str, nombre: str = "documento.md") -> str:
    """Diff unificado entre dos versiones del texto."""
    return "".join(
        difflib.unified_diff(
            antes.splitlines(keepends=True),
            despues.splitlines(keepends=True),
            fromfile=f"antes/{nombre}",
            tofile=f"despues/{nombre}",
        )
    )
