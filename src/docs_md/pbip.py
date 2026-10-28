"""
Hechos de un tablero leídos de su PBIP y comparación entre versiones.

CONTRATO (lo implementa el agente «pbip»):

    hechos = extraer_hechos(ruta_pbip)
    # {"tablero": "TABLERO ...", "modelo_disponible": True,
    #  "paginas": [{"id", "nombre", "visible", "orden", "filtros": [...], "obtener_detalles": [...],
    #               "visuales": [{"id", "tipo", "titulo", "campos": ["AVERAGE(T[c])", ...],
    #                 "campos_detalle": [{"rol", "expresion", "nombre"}], "filtros": ["T[c] no está vacío", ...],
    #                 "semaforo": ["NOMBRE: verde 0–15", ...], "formato_condicional": [...],
    #                 "texto": str | None, "destino": "PAGINA" | None, "destino_id", "tablas": [...],
    #                 "oculto": bool}]}],
    #  "tablas": {"T": {"modo", "origen", "servidor", "base_datos", "sql", "m", "dax",
    #                   "columnas": [...], "calculadas": {"c": "DAX"}}},
    #  "medidas": {"T[m]": "DAX"},
    #  "relaciones": ["A[x] -> B[y]", ...]}

    # CAMPOS OPCIONALES (se añaden sin cambiar lo anterior; quien no los conozca los ignora):
    #  raíz:   "marcadores": [{"id", "nombre", "pagina_id", "pagina", "visuales": [ids]}],
    #          "medidas_detalle": {"T[m]": {"nombre", "tabla", "dax", "descripcion", "formato", "carpeta",
    #                                      "oculta", "tipo"}},
    #          "relaciones_detalle": [{"texto", "desde", "hacia", "activa", "ambos_sentidos",
    #                                  "cardinalidad_desde", "cardinalidad_hacia"}],
    #          "modelo": {"nombre", "descripcion", "cultura"},   # descripción = comentario /// del TMDL
    #          "expresiones": {"Nombre": {"descripcion", "origen", "servidor", "base_datos", "m", "parametro"}},
    #          "roles": {"Rol": {"permiso", "filtros": {"T": "DAX"}}},
    #          "advertencias": ["archivo ilegible, tabla citada que no existe, ..."]
    #  tablas["T"]: "columnas_detalle": [{"nombre", "tabla", "tipo", "oculta", "calculada", "dax", "descripcion",
    #                  "resumen_por" (summarizeBy), "columna_origen" (sourceColumn), "formato", "carpeta",
    #                  "categoria", "ordenar_por", "clave"}],
    #          "medidas": [nombres], "jerarquias": [{"nombre", "oculta", "niveles"}],
    #          "particiones": [{"nombre", "tipo": "m|calculated|entity|query", "modo"}],
    #          "calculada": bool (tabla calculada; su DAX está en "dax"), "oculta", "descripcion",
    #          "origen_resumen": "SQL Server, base X, servidor Y; consulta SQL de N caracteres" (nunca credenciales),
    #          "referencia": nombre de la consulta de la que parte (origen "referencia"), "grupo_calculo": [...].
    #          "m", "sql" y "servidor" salen sin contraseñas, usuarios de conexión ni tokens (se reemplazan por ***).
    #  página: "tipo_pagina": "Normal" | "Tooltip" | "Drillthrough".
    #  visual: "grupo" (nombre del grupo que lo contiene), "oculto" (propio o de un grupo), "accion"
    #          (PageNavigation | Bookmark | Back | WebUrl...), "titulo_dinamico" (título que sale de un campo),
    #          "texto_alternativo", "orden": ["T[c] descendente"], "segmentador": {"modo", "seleccion_unica"},
    #          "formato_condicional" con "tipo": "reglas" | "degradado" | "campo" (color tomado de un campo).
    #  Un botón a un marcador lleva "destino": "el marcador «X» (PÁGINA)".

    cambios = comparar(hechos_antes, hechos_despues)
    # -> ["Página CONSULTAS DIA: se agregó el visual Tarjeta «X» (AVERAGE(T[c])).", ...]

    archivos = esqueleto(ruta_pbip, tablero, source_group)
    # -> {"_general.md": texto, "consultas_dia.md": texto, ...}  borradores en el formato estándar

`comparar` alimenta al actualizador: los cambios detectados en el PBIP dicen QUÉ
cambió; la nota de la persona explica POR QUÉ.

`ruta_pbip` es la carpeta que contiene `<Nombre>.Report` y `<Nombre>.SemanticModel`
(también se acepta el archivo .pbip o la carpeta .Report). Solo se leen los .json
del informe (PBIR) y los .tmdl del modelo; nunca `.pbi/cache.abf` (datos).

También acepta un `.pbix` cuyo informe venga en formato PBIR: se lee con zipfile,
sin extraer a disco y solo las entradas `Report/...`; nunca `DataModel` (datos).
Como no trae TMDL, `modelo_disponible` es False y las tablas y medidas quedan solo
con los nombres que citan los visuales (sin modo, SQL ni DAX).

Instantánea: `guardar_instantanea` deja los hechos en
`data/raw/<source_group>/pbip_hechos.json`; `cambios_desde_instantanea` compara el
PBIP actual contra ella.
"""

from __future__ import annotations

import colorsys
import json
import re
import zipfile
from collections import Counter
from datetime import date
from pathlib import Path

from . import formato as F
from .repositorio import ARCHIVO_GENERAL, raiz_documentos, slug

VERSION_HECHOS = 1
ARCHIVO_INSTANTANEA = "pbip_hechos.json"

# La agregación real está en "Aggregation": {"Function": n}; el queryRef a veces quedó obsoleto.
AGREGACIONES = {0: "SUM", 1: "AVERAGE", 2: "DISTINCTCOUNT", 3: "MIN", 4: "MAX", 5: "COUNT", 6: "MEDIAN"}
COMPARADORES = {0: "=", 1: ">", 2: ">=", 3: "<", 4: "<="}
UNIDADES_TIEMPO = {0: "día", 1: "semana", 2: "mes", 3: "año", 4: "década", 5: "segundo", 6: "minuto", 7: "hora"}

TIPOS_VISUAL = {
    "card": "Tarjeta",
    "multiRowCard": "Tarjeta de varias filas",
    "cardVisual": "Tarjeta",
    "tableEx": "Tabla",
    "pivotTable": "Matriz",
    "slicer": "Segmentación",
    "advancedSlicerVisual": "Segmentación",
    "actionButton": "Botón",
    "textbox": "Cuadro de texto",
    "shape": "Forma",
    "basicShape": "Forma",
    "image": "Imagen",
    "gauge": "Medidor",
    "kpi": "KPI",
    "lineChart": "Gráfico de líneas",
    "areaChart": "Gráfico de áreas",
    "stackedAreaChart": "Gráfico de áreas apiladas",
    "pieChart": "Gráfico circular",
    "donutChart": "Gráfico de anillos",
    "clusteredColumnChart": "Gráfico de columnas agrupadas",
    "columnChart": "Gráfico de columnas",
    "clusteredBarChart": "Gráfico de barras agrupadas",
    "barChart": "Gráfico de barras",
    "lineClusteredColumnComboChart": "Gráfico combinado de líneas y columnas",
    "lineStackedColumnComboChart": "Gráfico combinado de líneas y columnas apiladas",
    "scatterChart": "Gráfico de dispersión",
    "waterfallChart": "Gráfico de cascada",
    "funnel": "Embudo",
    "map": "Mapa",
    "filledMap": "Mapa coroplético",
    "treemap": "Mapa de árbol",
    "ribbonChart": "Gráfico de cintas",
    "hundredPercentStackedBarChart": "Gráfico de barras 100% apiladas",
    "hundredPercentStackedColumnChart": "Gráfico de columnas 100% apiladas",
    "stackedBarChart": "Gráfico de barras apiladas",
    "stackedColumnChart": "Gráfico de columnas apiladas",
    "azureMap": "Mapa de Azure",
    "shapeMap": "Mapa de formas",
    "decompositionTreeVisual": "Árbol de descomposición",
    "keyDriversVisual": "Influenciadores clave",
    "qnaVisual": "Preguntas y respuestas",
    "scriptVisual": "Visual de R",
    "pythonVisual": "Visual de Python",
    "paginator": "Paginador",
    "grupo": "Grupo de visuales",
}
# Visuales personalizados: el tipo lleva un identificador hexadecimal al final.
PERSONALIZADOS = {"textFilter": "Filtro de texto (visual personalizado)", "htmlContent": "Visual HTML (personalizado)"}
DECORATIVOS = {"shape", "basicShape", "image"}
SEGMENTACIONES = {"slicer", "advancedSlicerVisual"}
TABLAS_AUTOMATICAS = ("LocalDateTable_", "DateTableTemplate_")
OCULTA = "HiddenInViewMode"
MODOS = {"directquery": "DirectQuery", "import": "Import", "dual": "Dual", "push": "Push", "directlake": "DirectLake"}

# Un límite superior así de grande en una regla de color es un centinela («o más»).
CENTINELA = 999


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _leer_json(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8-sig"))


def _es_segmentador(tipo: str) -> bool:
    return tipo in SEGMENTACIONES or _tipo_base(tipo) == "textFilter"


def _es_automatica(tabla: str | None) -> bool:
    return bool(tabla) and str(tabla).startswith(TABLAS_AUTOMATICAS)


def _numero(valor) -> str:
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    return str(valor)


def _corto(texto: str, maximo: int = 160) -> str:
    texto = re.sub(r"\s+", " ", str(texto or "")).strip()
    return texto if len(texto) <= maximo else texto[: maximo - 1].rstrip() + "…"


def _lista_es(items) -> str:
    """«a», «a y b», «a, b y c»."""
    items = [str(i) for i in items if str(i)]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " y " + items[-1]


def _ubicar(ruta_pbip) -> tuple[str, Path, Path | None]:
    """(nombre, carpeta .Report, carpeta .SemanticModel o None)."""
    ruta = Path(ruta_pbip)
    if ruta.is_file() and ruta.suffix.lower() == ".pbip":
        base, nombre = ruta.parent, ruta.stem
    elif ruta.name.endswith(".Report"):
        base, nombre = ruta.parent, ruta.name[: -len(".Report")]
    elif ruta.name.endswith(".SemanticModel"):
        base, nombre = ruta.parent, ruta.name[: -len(".SemanticModel")]
    else:
        base = ruta
        informes = sorted(base.glob("*.Report"))
        if not informes:
            raise FileNotFoundError(f"No hay una carpeta *.Report en «{ruta}».")
        pbips = {p.stem for p in base.glob("*.pbip")}
        elegido = next((i for i in informes if i.name[: -len(".Report")] in pbips), informes[0])
        nombre = elegido.name[: -len(".Report")]
    informe = base / f"{nombre}.Report"
    if not (informe / "definition").is_dir():
        raise FileNotFoundError(f"«{informe}» no tiene la carpeta definition/ (formato PBIR).")

    modelo = None
    pbir = informe / "definition.pbir"
    if pbir.exists():
        try:
            ref = (_leer_json(pbir).get("datasetReference") or {}).get("byPath") or {}
            if ref.get("path"):
                candidato = (informe / ref["path"]).resolve()
                if candidato.is_dir():
                    modelo = candidato
        except (OSError, ValueError):
            pass
    if modelo is None and (base / f"{nombre}.SemanticModel").is_dir():
        modelo = base / f"{nombre}.SemanticModel"
    return nombre, informe, modelo


# ---------------------------------------------------------------------------
# Expresiones del informe (PBIR)
# ---------------------------------------------------------------------------

def _literal(valor):
    """Literal de Power BI ('texto', 15D, 1L, null, true, datetime'...') a Python."""
    v = str(valor)
    if v == "null":
        return None
    if v in ("true", "false"):
        return v == "true"
    m = re.fullmatch(r"datetime'(\d{4}-\d{2}-\d{2})(?:T(\d{2}:\d{2})(?::\d{2}(?:\.\d+)?)?)?'", v)
    if m:
        hora = m.group(2)
        return m.group(1) + (f" {hora}" if hora and hora != "00:00" else "")
    if len(v) >= 2 and v[0] == "'" and v[-1] == "'":
        return v[1:-1].replace("''", "'")
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)(?:[LDM])?", v)
    if m:
        n = float(m.group(1))
        return int(n) if n.is_integer() else n
    return v


def _texto_literal(valor) -> str:
    if valor is None:
        return "vacío"
    if isinstance(valor, bool):
        return "verdadero" if valor else "falso"
    if isinstance(valor, (int, float)):
        return _numero(valor)
    return f"'{valor}'"


def _valor_propiedad(prop):
    """Valor literal de una propiedad de objetos ({"expr": {"Literal": {"Value": ...}}})."""
    if isinstance(prop, dict):
        lit = (prop.get("expr") or {}).get("Literal")
        if isinstance(lit, dict) and "Value" in lit:
            return _literal(lit["Value"])
    return None


class _Contexto:
    """Alias del From de un filtro y columna que lo reemplaza si apunta a una
    tabla de fechas automática (LocalDateTable_...)."""

    def __init__(self, alias: dict | None = None, reemplazo: str | None = None):
        self.alias = alias or {}
        self.reemplazo = reemplazo

    def entidad(self, ref: dict) -> str:
        sr = (ref or {}).get("SourceRef") or {}
        if "Entity" in sr:
            return sr["Entity"]
        return self.alias.get(sr.get("Source"), sr.get("Source") or "?")


def _base_campo(campo: dict, ctx: _Contexto | None = None) -> tuple[str, str] | None:
    """(tabla, columna) de la columna o medida sobre la que se construye un campo."""
    ctx = ctx or _Contexto()
    if not isinstance(campo, dict):
        return None
    if "Column" in campo or "Measure" in campo:
        nodo = campo.get("Column") or campo.get("Measure")
        return ctx.entidad(nodo.get("Expression")), nodo.get("Property")
    if "Aggregation" in campo:
        return _base_campo(campo["Aggregation"].get("Expression"), ctx)
    if "Arithmetic" in campo:
        ar = campo["Arithmetic"]
        return _base_campo(ar.get("Left"), ctx) or _base_campo(ar.get("Right"), ctx)
    if "ScopedEval" in campo:
        return _base_campo(campo["ScopedEval"].get("Expression"), ctx)
    if "HierarchyLevel" in campo:
        jer =(campo["HierarchyLevel"].get("Expression") or {}).get("Hierarchy") or {}
        fuente = jer.get("Expression") or {}
        if "PropertyVariationSource" in fuente:
            pvs = fuente["PropertyVariationSource"]
            return ctx.entidad(pvs.get("Expression")), pvs.get("Property")
        return ctx.entidad(fuente), jer.get("Hierarchy")
    return None


def _expr(campo, ctx: _Contexto | None = None) -> str:
    """Texto legible de una expresión de campo: T[c], AVERAGE(T[c]), T[c] (Día)."""
    ctx = ctx or _Contexto()
    if not isinstance(campo, dict):
        return str(campo)
    if "Column" in campo or "Measure" in campo:
        nodo = campo.get("Column") or campo.get("Measure")
        tabla, col = ctx.entidad(nodo.get("Expression")), nodo.get("Property")
        if _es_automatica(tabla) and ctx.reemplazo:
            # El filtro ya puede nombrar el nivel: «T[Date] (Mes)» no se repite como «(Mes) (Mes)».
            return ctx.reemplazo if ctx.reemplazo.endswith(f"({col})") else f"{ctx.reemplazo} ({col})"
        return f"{tabla}[{col}]"
    if "Aggregation" in campo:
        ag = campo["Aggregation"]
        funcion = AGREGACIONES.get(ag.get("Function"), f"AGREGACION_{ag.get('Function')}")
        return f"{funcion}({_expr(ag.get('Expression'), ctx)})"
    if "HierarchyLevel" in campo:
        base = _base_campo(campo, ctx)
        nivel = campo["HierarchyLevel"].get("Level")
        return f"{base[0]}[{base[1]}] ({nivel})" if base else str(nivel)
    if "Literal" in campo:
        return _texto_literal(_literal(campo["Literal"].get("Value")))
    if "DateSpan" in campo:
        ds = campo["DateSpan"]
        unidad = UNIDADES_TIEMPO.get(ds.get("TimeUnit"), "periodo")
        interior = ds.get("Expression") or {}
        if "Now" in interior:
            return "hoy" if unidad == "día" else f"el {unidad} actual"
        if "DateAdd" in interior and "Now" in (interior["DateAdd"].get("Expression") or {}):
            n = interior["DateAdd"].get("Amount", 0)
            unidad_da = UNIDADES_TIEMPO.get(interior["DateAdd"].get("TimeUnit"), "periodo")
            if unidad_da == unidad and n == -1:
                return "ayer" if unidad == "día" else f"el {unidad} anterior"
            if unidad_da == unidad and n == 1:
                return "mañana" if unidad == "día" else f"el {unidad} siguiente"
        return f"el {unidad} de {_expr(interior, ctx)}"
    if "DateAdd" in campo:
        da = campo["DateAdd"]
        unidad = UNIDADES_TIEMPO.get(da.get("TimeUnit"), "periodo")
        return f"{_expr(da.get('Expression'), ctx)} {'+' if da.get('Amount', 0) >= 0 else '-'} {abs(da.get('Amount', 0))} {unidad}(s)"
    if "Now" in campo:
        return "ahora"
    if "NativeVisualCalculation" in campo:
        nv = campo["NativeVisualCalculation"]
        return f"cálculo visual {nv.get('Name') or ''}".strip()
    if "ScopedEval" in campo:
        return f"total de {_expr(campo['ScopedEval'].get('Expression'), ctx)}"
    if "Arithmetic" in campo:
        ar = campo["Arithmetic"]
        op = {0: "+", 1: "-", 2: "*", 3: "/"}.get(ar.get("Operator"), "?")
        return f"({_expr(ar.get('Left'), ctx)} {op} {_expr(ar.get('Right'), ctx)})"
    return _corto(json.dumps(campo, ensure_ascii=False), 80)


def _condicion(c: dict, ctx: _Contexto, negada: bool = False) -> str:
    """Condición de un filtro (Where[].Condition) en español."""
    if not isinstance(c, dict):
        return str(c)
    if "And" in c:
        return f"{_condicion(c['And']['Left'], ctx)} y {_condicion(c['And']['Right'], ctx)}"
    if "Or" in c:
        return f"({_condicion(c['Or']['Left'], ctx)} o {_condicion(c['Or']['Right'], ctx)})"
    if "Not" in c:
        interior = c["Not"].get("Expression") or {}
        if "In" in interior or "Comparison" in interior:
            return _condicion(interior, ctx, negada=not negada)
        return f"no ({_condicion(interior, ctx)})"
    if "In" in c:
        nodo = c["In"]
        columnas = ", ".join(_expr(e, ctx) for e in nodo.get("Expressions") or [])
        filas = nodo.get("Values") or []
        valores = []
        for fila in filas:
            partes = [_texto_literal(_literal((x.get("Literal") or {}).get("Value"))) if "Literal" in x else _expr(x, ctx)
                      for x in fila]
            valores.append(partes[0] if len(partes) == 1 else "(" + ", ".join(partes) + ")")
        if valores == ["vacío"]:
            return f"{columnas} {'no está vacío' if negada else 'está vacío'}"
        if "Table" in nodo or "Subquery" in str(nodo):
            return f"{columnas} {'no ' if negada else ''}en una selección (Top N)"
        if len(valores) == 1:
            return f"{columnas} {'≠' if negada else '='} {valores[0]}"
        return f"{columnas} {'no en' if negada else 'en'} ({', '.join(valores)})"
    if "Comparison" in c:
        cmp = c["Comparison"]
        izq, der = _expr(cmp.get("Left"), ctx), cmp.get("Right") or {}
        tipo = cmp.get("ComparisonKind", 0)
        if "DateSpan" in der and tipo == 0:
            return f"{izq} {'no es' if negada else 'es'} {_expr(der, ctx)}"
        op = COMPARADORES.get(tipo, "?")
        if negada:
            op = {"=": "≠", ">": "<=", ">=": "<", "<": ">=", "<=": ">"}.get(op, op)
        return f"{izq} {op} {_expr(der, ctx)}"
    if "Between" in c:
        b = c["Between"]
        izq, lo, hi = _expr(b.get("Expression"), ctx), _expr(b.get("LowerBound"), ctx), _expr(b.get("UpperBound"), ctx)
        if lo == hi:
            return f"{izq} {'no es' if negada else 'es'} {lo}"
        return f"{izq} {'no está ' if negada else ''}entre {lo} y {hi}"
    for clave, verbo in (("Contains", "contiene"), ("StartsWith", "empieza por"), ("EndsWith", "termina en")):
        if clave in c:
            nodo = c[clave]
            return f"{_expr(nodo.get('Left'), ctx)} {'no ' if negada else ''}{verbo} {_expr(nodo.get('Right'), ctx)}"
    if "Exists" in c:
        return "existe una fila relacionada"
    return _corto(json.dumps(c, ensure_ascii=False), 80)


def _filtros(config: dict | None) -> tuple[list[str], list[str], set[str]]:
    """(filtros legibles, campos de obtener detalles, tablas) de un filterConfig.
    Los filtros sin condición (nadie eligió valores) no filtran y se omiten."""
    textos, detalles, tablas = [], [], set()
    for f in (config or {}).get("filters") or []:
        base = _base_campo(f.get("field") or {})
        if base and not _es_automatica(base[0]):
            tablas.add(base[0])
        campo_txt = _expr(f.get("field")) if f.get("field") else None
        if f.get("howCreated") == "Drillthrough" and not f.get("filter"):
            if campo_txt:
                detalles.append(campo_txt)
            continue
        filtro = f.get("filter")
        if not filtro:
            continue
        alias = {d.get("Name"): d.get("Entity") for d in filtro.get("From") or []}
        for entidad in alias.values():
            if entidad and not _es_automatica(entidad):
                tablas.add(entidad)
        ctx = _Contexto(alias, reemplazo=campo_txt)
        partes = [_condicion(w.get("Condition") or {}, ctx) for w in filtro.get("Where") or []]
        if f.get("type") == "TopN":
            partes = [f"Top N sobre {campo_txt}"]
        if partes:
            textos.append(" y ".join(partes))
    return textos, detalles, tablas


# ---------------------------------------------------------------------------
# Formato condicional (semáforos)
# ---------------------------------------------------------------------------

def _nombre_color(valor) -> str:
    texto = str(valor or "").strip().strip("'")
    h = texto.lstrip("#").lower()
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if not re.fullmatch(r"[0-9a-f]{6}(?:[0-9a-f]{2})?", h):
        return texto or "color"
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    tono, luz, sat = colorsys.rgb_to_hls(r, g, b)
    if luz >= 0.93:
        return "blanco"
    if luz <= 0.12:
        return "negro"
    if sat < 0.15:
        return "gris"
    grados = tono * 360
    for limite, nombre in ((15, "rojo"), (40, "naranja"), (70, "amarillo"), (170, "verde"),
                           (200, "turquesa"), (260, "azul"), (300, "morado"), (345, "rosado"), (361, "rojo")):
        if grados < limite:
            return nombre
    return "rojo"


def _color_de(valor: dict) -> tuple[str, str]:
    """(nombre, código) del Value de un caso o de un punto del degradado."""
    valor = valor or {}
    if "Literal" in valor:
        codigo = str(_literal(valor["Literal"].get("Value")))
        return _nombre_color(codigo), codigo
    if "ThemeDataColor" in valor:
        return f"color {valor['ThemeDataColor'].get('ColorId')} del tema", ""
    return "color", ""


def _comparaciones(c: dict, salida: list) -> bool:
    """Aplana un árbol And de comparaciones; False si hay otra cosa."""
    if "And" in c:
        return _comparaciones(c["And"]["Left"], salida) and _comparaciones(c["And"]["Right"], salida)
    if "Comparison" in c:
        cmp = c["Comparison"]
        der = cmp.get("Right") or {}
        if "Literal" not in der:
            return False
        valor = _literal(der["Literal"].get("Value"))
        if not isinstance(valor, (int, float)) or isinstance(valor, bool):
            return False
        salida.append((cmp.get("ComparisonKind", 0), valor, cmp.get("Left")))
        return True
    return False


def _rango(comparaciones: list) -> dict:
    r = {"min": None, "min_incluido": True, "max": None, "max_incluido": True, "igual": None}
    for tipo, valor, _ in comparaciones:
        if tipo == 0:
            r["igual"] = valor
        elif tipo in (1, 2):
            r["min"], r["min_incluido"] = valor, tipo == 2
        elif tipo in (3, 4):
            r["max"], r["max_incluido"] = valor, tipo == 4
    # Centinelas: «< 1000» o «< 100000000» significan «o más».
    if r["max"] is not None and r["max"] >= CENTINELA and (r["min"] is None or r["max"] >= 10 * max(abs(r["min"]), 1)):
        r["max"] = None
    if r["min"] is not None and r["min"] <= -CENTINELA:
        r["min"] = None
    return r


def _texto_rango(r: dict) -> str:
    if r.get("igual") is not None:
        return f"= {_numero(r['igual'])}"
    lo, hi = r.get("min"), r.get("max")
    if lo is not None and hi is not None:
        if r["min_incluido"] and r["max_incluido"]:
            return f"{_numero(lo)}–{_numero(hi)}"
        return f"{'≥' if r['min_incluido'] else '>'}{_numero(lo)} y {'≤' if r['max_incluido'] else '<'}{_numero(hi)}"
    if lo is not None:
        return f"{'≥' if r['min_incluido'] else '>'}{_numero(lo)}"
    if hi is not None:
        return f"{'≤' if r['max_incluido'] else '<'}{_numero(hi)}"
    return "siempre"


def _rango_en_palabras(r: dict) -> str:
    if r.get("igual") is not None:
        return f"igual a {_numero(r['igual'])}"
    lo, hi = r.get("min"), r.get("max")
    partes = []
    if lo is not None and hi is not None and r["min_incluido"] and r["max_incluido"]:
        return f"de {_numero(lo)} a {_numero(hi)}"
    if lo is not None:
        partes.append(f"de {_numero(lo)} o más" if r["min_incluido"] and hi is None
                      else (f"desde {_numero(lo)}" if r["min_incluido"] else f"más de {_numero(lo)}"))
    if hi is not None:
        partes.append(f"hasta {_numero(hi)}" if r["max_incluido"] else f"menos de {_numero(hi)}")
    return " y ".join(partes) or "siempre"


def _formato_condicional(objetos: dict, proyecciones: list[dict]) -> list[dict]:
    """Reglas de color de un visual. Ignora las reglas heredadas sobre columnas que
    ya no están en el visual (ni el selector ni la columna evaluada aparecen)."""
    por_ref = {p["query_ref"]: p for p in proyecciones if p.get("query_ref")}
    por_base = {}
    for p in proyecciones:
        if p.get("base"):
            por_base.setdefault(tuple(p["base"]), p)
    reglas = []
    for clave, lista in (objetos or {}).items():
        for obj in lista or []:
            selector = (obj.get("selector") or {}).get("metadata")
            for propiedad, valor in (obj.get("properties") or {}).items():
                if not isinstance(valor, dict):
                    continue
                expr = ((valor.get("solid") or {}).get("color") or {}).get("expr")
                if not isinstance(expr, dict):
                    continue
                regla = {"objeto": clave, "propiedad": {"backColor": "fondo", "fontColor": "texto"}.get(propiedad, propiedad)}
                if {"Measure", "Column", "Aggregation"} & set(expr):
                    # El color sale del valor de un campo (p. ej. una medida que devuelve «#00FF00»).
                    destino = por_ref.get(selector) or (por_base.get(tuple(_base_campo(expr) or ())) if _base_campo(expr) else None)
                    if destino is None and not selector and proyecciones:
                        destino = proyecciones[0]
                    if destino is None:
                        continue
                    regla.update(tipo="campo", casos=[], puntos=[], campo=destino["nombre"], evalua=_expr(expr))
                    reglas.append(regla)
                    continue
                if not ({"Conditional", "FillRule"} & set(expr)):
                    continue
                if "FillRule" in expr:
                    fr = expr["FillRule"]
                    operando = fr.get("Input")
                    tipo_fr = next(iter(fr.get("FillRule") or {}), "")
                    puntos = []
                    for punto in ("min", "mid", "max"):
                        datos = (fr.get("FillRule") or {}).get(tipo_fr, {}).get(punto)
                        if datos:
                            nombre, codigo = _color_de(datos.get("color"))
                            if codigo.lower() == "midcolor":
                                continue
                            puntos.append({"punto": punto, "color": nombre, "codigo": codigo})
                    regla.update(tipo="degradado", puntos=puntos)
                else:
                    casos, operando = [], None
                    for caso in expr["Conditional"].get("Cases") or []:
                        nombre, codigo = _color_de(caso.get("Value"))
                        comps = []
                        if _comparaciones(caso.get("Condition") or {}, comps) and comps:
                            operando = operando or comps[0][2]
                            r = _rango(comps)
                            casos.append({"color": nombre, "codigo": codigo, "rango": _texto_rango(r), **r})
                        else:
                            casos.append({"color": nombre, "codigo": codigo,
                                          "rango": _condicion(caso.get("Condition") or {}, _Contexto())})
                    casos.sort(key=lambda c: (c.get("min") is None and c.get("igual") is None and c.get("max") is None,
                                              c.get("igual") if c.get("igual") is not None else
                                              (c.get("min") if c.get("min") is not None else float("-inf"))))
                    regla.update(tipo="reglas", casos=casos)
                base = _base_campo(operando) if operando else None
                destino = por_ref.get(selector) or (por_base.get(tuple(base)) if base else None)
                if destino is None:
                    continue  # regla heredada de una columna que ya no está en el visual
                regla["campo"] = destino["nombre"]
                regla["evalua"] = _expr(operando) if operando else destino["expresion"]
                reglas.append(regla)
    return reglas


def _semaforo(reglas: list[dict]) -> list[str]:
    """Resumen corto: 'CAMPO: verde 0–15', 'CAMPO: degradado verde → rojo'.
    Las reglas de color de texto solo cuentan si el campo no tiene reglas de fondo
    y no son blanco/negro (contraste)."""
    con_fondo = {r["campo"] for r in reglas if r["propiedad"] == "fondo"}
    salida = []
    for r in reglas:
        if r["propiedad"] != "fondo" and r["campo"] in con_fondo:
            continue
        sufijo = "" if r["propiedad"] == "fondo" else f" ({r['propiedad']})"
        if r["tipo"] == "degradado":
            colores = " → ".join(p["color"] for p in r["puntos"])
            salida.append(f"{r['campo']}{sufijo}: degradado {colores}".rstrip())
            continue
        if r["tipo"] == "campo":
            salida.append(f"{r['campo']}{sufijo}: color según {r['evalua']}")
            continue
        for caso in r.get("casos") or []:
            if r["propiedad"] != "fondo" and caso["color"] in ("blanco", "negro"):
                continue
            salida.append(f"{r['campo']}{sufijo}: {caso['color']} {caso['rango']}")
    return list(dict.fromkeys(salida))


# ---------------------------------------------------------------------------
# Visuales y páginas
# ---------------------------------------------------------------------------

def _textos_parrafos(parrafos) -> str:
    lineas = []
    for p in parrafos or []:
        texto = "".join(str(r.get("value") or "") for r in p.get("textRuns") or [])
        texto = re.sub(r"\t+", " / ", texto)
        texto = re.sub(r"\s+", " ", texto).strip(" /")
        if texto:
            lineas.append(texto)
    return " | ".join(lineas)


def _visual(datos: dict) -> dict:
    v = datos.get("visual")
    grupo_padre = datos.get("parentGroupName")
    if not v:
        grupo = datos.get("visualGroup") or {}
        return {"id": datos.get("name"), "tipo": "grupo", "titulo": grupo.get("displayName"), "campos": [],
                "campos_detalle": [], "filtros": [], "semaforo": [], "formato_condicional": [], "texto": None,
                "destino": None, "destino_id": None, "accion": None, "tablas": [], "oculto": bool(datos.get("isHidden")),
                "grupo": grupo_padre, "grupo_id": grupo_padre}
    tipo = v.get("visualType") or "?"
    proyecciones = []
    for rol, estado in ((v.get("query") or {}).get("queryState") or {}).items():
        for p in estado.get("projections") or []:
            campo = p.get("field") or {}
            expresion = _expr(campo)
            proyecciones.append({
                "rol": rol,
                "expresion": expresion,
                "nombre": p.get("displayName") or p.get("nativeQueryRef") or expresion,
                "query_ref": p.get("queryRef"),
                "base": _base_campo(campo),
            })
    vco = v.get("visualContainerObjects") or {}
    objetos = v.get("objects") or {}

    titulo, titulo_dinamico = None, None
    for t in vco.get("title") or []:
        prop = (t.get("properties") or {}).get("text")
        valor = _valor_propiedad(prop)
        if valor:
            titulo = str(valor).strip()
        elif isinstance(prop, dict) and isinstance(prop.get("expr"), dict) and "Literal" not in prop["expr"]:
            titulo_dinamico = _expr(prop["expr"])
    alt = None
    for g in vco.get("general") or []:
        alt = _valor_propiedad((g.get("properties") or {}).get("altText")) or alt

    ordenes = []
    for o in ((v.get("query") or {}).get("sortDefinition") or {}).get("sort") or []:
        ordenes.append(f"{_expr(o.get('field'))} {'descendente' if o.get('direction') == 'Descending' else 'ascendente'}")

    segmentador = None
    if _es_segmentador(tipo):
        segmentador = {}
        for d in objetos.get("data") or []:
            modo = _valor_propiedad((d.get("properties") or {}).get("mode"))
            if modo:
                segmentador["modo"] = str(modo)
        for s in objetos.get("selection") or []:
            unica = _valor_propiedad((s.get("properties") or {}).get("singleSelect"))
            if unica is not None:
                segmentador["seleccion_unica"] = bool(unica)

    texto = None
    if tipo == "textbox":
        for g in objetos.get("general") or []:
            texto = _textos_parrafos((g.get("properties") or {}).get("paragraphs")) or texto
    else:
        for t in objetos.get("text") or []:
            valor = _valor_propiedad((t.get("properties") or {}).get("text"))
            if valor:
                texto = str(valor).strip()

    destino_id, accion = None, None
    for enlace in vco.get("visualLink") or []:
        props = enlace.get("properties") or {}
        if _valor_propiedad(props.get("show")) is False:
            continue
        accion = _valor_propiedad(props.get("type")) or accion
        destino_id = _valor_propiedad(props.get("navigationSection")) or _valor_propiedad(props.get("drillthroughSection")) or destino_id
        if accion == "Bookmark":
            destino_id = destino_id or _valor_propiedad(props.get("bookmark"))
        if accion == "WebUrl":
            destino_id = destino_id or _sanear(_valor_propiedad(props.get("webUrl")))

    filtros, _, tablas_filtro = _filtros(datos.get("filterConfig"))
    reglas = _formato_condicional(objetos, proyecciones)
    citadas: set = set()
    _referencias(v, {}, citadas)
    tablas = ({p["base"][0] for p in proyecciones if p.get("base")} | tablas_filtro
              | {t for _, t, _ in citadas})
    return {
        "id": datos.get("name"),
        "tipo": tipo,
        "titulo": titulo,
        "campos": [p["expresion"] for p in proyecciones],
        "campos_detalle": [{"rol": p["rol"], "expresion": p["expresion"], "nombre": p["nombre"]} for p in proyecciones],
        "filtros": filtros,
        "semaforo": _semaforo(reglas),
        "formato_condicional": reglas,
        "texto": texto,
        "destino": None,
        "destino_id": destino_id,
        "accion": accion,
        "tablas": sorted(t for t in tablas if t and not _es_automatica(t)),
        "oculto": bool(datos.get("isHidden")),
        "grupo": grupo_padre,
        "grupo_id": grupo_padre,
        "titulo_dinamico": titulo_dinamico,
        "texto_alternativo": alt,
        "orden": ordenes,
        "segmentador": segmentador,
    }


class _LectorCarpeta:
    """Lee el informe PBIR desde la carpeta <Nombre>.Report/definition."""

    def __init__(self, definicion: Path):
        self.definicion = definicion

    def json(self, relativa: str) -> dict | None:
        ruta = self.definicion / relativa
        return _leer_json(ruta) if ruta.is_file() else None

    def subcarpetas(self, relativa: str) -> list[str]:
        carpeta = self.definicion / relativa
        return sorted(p.name for p in carpeta.iterdir() if p.is_dir()) if carpeta.is_dir() else []

    def archivos(self, relativa: str, sufijo: str) -> list[str]:
        carpeta = self.definicion / relativa
        return sorted(p.name for p in carpeta.iterdir() if p.is_file() and p.name.endswith(sufijo)) if carpeta.is_dir() else []


class _LectorZip:
    """Lee el informe PBIR dentro de un .pbix sin extraerlo. Solo abre entradas
    que empiezan por «Report/»: nunca DataModel (datos reales)."""

    PREFIJO = "Report/definition/"

    def __init__(self, zf):
        self.zf = zf
        self.nombres = {n for n in zf.namelist() if n.startswith(self.PREFIJO)}

    def json(self, relativa: str) -> dict | None:
        nombre = self.PREFIJO + relativa
        if nombre not in self.nombres:
            return None
        return json.loads(self.zf.read(nombre).decode("utf-8-sig"))

    def subcarpetas(self, relativa: str) -> list[str]:
        base = self.PREFIJO + relativa.rstrip("/") + "/"
        return sorted({n[len(base):].split("/", 1)[0] for n in self.nombres
                       if n.startswith(base) and "/" in n[len(base):]})

    def archivos(self, relativa: str, sufijo: str) -> list[str]:
        base = self.PREFIJO + relativa.rstrip("/") + "/"
        return sorted(n[len(base):] for n in self.nombres
                      if n.startswith(base) and "/" not in n[len(base):] and n.endswith(sufijo))


def _referencias(nodo, alias: dict, salida: set):
    """Columnas y medidas citadas en cualquier parte de un JSON del informe:
    {("columna" | "medida", tabla, nombre)}."""
    if isinstance(nodo, dict):
        for clave, tipo in (("Column", "columna"), ("Measure", "medida")):
            interior = nodo.get(clave)
            if isinstance(interior, dict) and "Property" in interior:
                sr = ((interior.get("Expression") or {}).get("SourceRef") or {})
                tabla = sr.get("Entity") or alias.get(sr.get("Source"))
                if tabla and not _es_automatica(tabla):
                    salida.add((tipo, tabla, interior["Property"]))
        for valor in nodo.values():
            _referencias(valor, alias, salida)
    elif isinstance(nodo, list):
        for valor in nodo:
            _referencias(valor, alias, salida)


def _referencias_visual(datos: dict, salida: set):
    _referencias(datos.get("visual") or {}, {}, salida)
    for f in (datos.get("filterConfig") or {}).get("filters") or []:
        alias = {d.get("Name"): d.get("Entity") for d in (f.get("filter") or {}).get("From") or []}
        _referencias(f, alias, salida)


def _json_seguro(lector, relativa: str, advertencias: list):
    """JSON del informe o None; un archivo ilegible se anota y no detiene el resto."""
    try:
        return lector.json(relativa)
    except (OSError, ValueError, KeyError) as e:
        advertencias.append(f"No se pudo leer {relativa}: {type(e).__name__}")
        return None


def _marcadores(lector, advertencias: list) -> list[dict]:
    """Marcadores del informe (bookmarks/*.bookmark.json) en el orden de bookmarks.json."""
    meta = _json_seguro(lector, "bookmarks/bookmarks.json", advertencias) or {}
    orden = []
    for item in meta.get("items") or []:
        orden.append(item.get("name"))
        orden += list(item.get("children") or [])
    por_id = {}
    for archivo in lector.archivos("bookmarks", ".bookmark.json"):
        d = _json_seguro(lector, f"bookmarks/{archivo}", advertencias)
        if not d:
            continue
        estado = d.get("explorationState") or {}
        bid = d.get("name") or archivo[: -len(".bookmark.json")]
        por_id[bid] = {
            "id": bid,
            "nombre": d.get("displayName") or bid,
            "pagina_id": estado.get("activeSection"),
            "pagina": None,
            "visuales": list((d.get("options") or {}).get("targetVisualNames") or []),
        }
    ordenados = [por_id[b] for b in orden if b in por_id] + [m for b, m in por_id.items() if b not in orden]
    return ordenados


def _paginas(lector, referencias: set | None = None, advertencias: list | None = None,
             marcadores: list | None = None) -> tuple[list[dict], list[str]]:
    advertencias = advertencias if advertencias is not None else []
    orden = list((_json_seguro(lector, "pages/pages.json", advertencias) or {}).get("pageOrder") or [])
    existentes = [p for p in lector.subcarpetas("pages") if _json_seguro(lector, f"pages/{p}/page.json", advertencias) is not None]
    orden = [p for p in orden if p in existentes] + [p for p in existentes if p not in orden]
    referencias = referencias if referencias is not None else set()

    paginas = []
    for i, pid in enumerate(orden, start=1):
        datos = _json_seguro(lector, f"pages/{pid}/page.json", advertencias)
        filtros, detalles, _ = _filtros(datos.get("filterConfig"))
        _referencias_visual(datos, referencias)
        crudos = []
        for vid in lector.subcarpetas(f"pages/{pid}/visuals"):
            vd = _json_seguro(lector, f"pages/{pid}/visuals/{vid}/visual.json", advertencias)
            if vd is None:
                continue
            try:
                _referencias_visual(vd, referencias)
                pos = vd.get("position") or {}
                crudos.append((round(float(pos.get("y", 0)) / 10), float(pos.get("x", 0)), _visual(vd), vd))
            except Exception as e:  # un visual raro no debe tumbar el informe
                advertencias.append(f"Página {datos.get('displayName') or pid}, visual {vid}: {type(e).__name__}: {e}")
        # Grupos: el visual hereda lo oculto del grupo que lo contiene.
        grupos = {t[2]["id"]: (t[2], t[3].get("parentGroupName")) for t in crudos if t[2]["tipo"] == "grupo"}

        def ancestros_ocultos(v):
            visto, actual = set(), v.get("grupo_id")
            while actual and actual in grupos and actual not in visto:
                visto.add(actual)
                if grupos[actual][0]["oculto"]:
                    return True
                actual = grupos[actual][1]
            return False

        for _, _, v, _ in crudos:
            if v.get("grupo_id") in grupos:
                v["grupo"] = grupos[v["grupo_id"]][0].get("titulo") or v["grupo_id"]
            if ancestros_ocultos(v):
                v["oculto"] = True
        crudos.sort(key=lambda t: (t[0], t[1], t[2]["id"] or ""))
        binding = (datos.get("pageBinding") or {}).get("type")
        paginas.append({
            "id": datos.get("name") or pid,
            "nombre": datos.get("displayName") or pid,
            "visible": datos.get("visibility") != OCULTA,
            "orden": i,
            "tipo_pagina": datos.get("type") or (binding if binding not in (None, "Default") else "Normal"),
            "filtros": filtros,
            "obtener_detalles": detalles,
            "visuales": [t[2] for t in crudos],
        })

    lista_marcadores = _marcadores(lector, advertencias)
    nombres = {p["id"]: p["nombre"] for p in paginas}
    por_marcador = {m["id"]: m for m in lista_marcadores}
    for m in lista_marcadores:
        m["pagina"] = nombres.get(m["pagina_id"])
    for p in paginas:
        for v in p["visuales"]:
            if v["destino_id"] in nombres:
                v["destino"] = nombres[v["destino_id"]]
            elif v["destino_id"] in por_marcador:
                m = por_marcador[v["destino_id"]]
                v["destino"] = f"el marcador «{m['nombre']}»" + (f" ({m['pagina']})" if m.get("pagina") else "")
            elif v["accion"] == "Back":
                v["destino"] = "página anterior"
    if marcadores is not None:
        marcadores.extend(lista_marcadores)

    reporte = _json_seguro(lector, "report.json", advertencias) or {}
    filtros_reporte, _, _ = _filtros(reporte.get("filterConfig"))
    _referencias_visual(reporte, referencias)
    return paginas, filtros_reporte


# ---------------------------------------------------------------------------
# Modelo semántico (TMDL)
# ---------------------------------------------------------------------------

# Palabras que abren un objeto TMDL (con nombre y, a veces, «= expresión»).
OBJETOS_TMDL = {
    "model", "database", "table", "column", "measure", "partition", "hierarchy", "level",
    "calculationGroup", "calculationItem", "expression", "relationship", "role", "tablePermission",
    "perspective", "culture", "cultureInfo", "annotation", "ref", "queryGroup", "extendedProperty",
    "dataSource", "function", "calendar", "calendarColumnGroup", "variation", "member", "translation",
}
# Propiedades sin valor (banderas).
BANDERAS_TMDL = {"isHidden", "isKey", "isNullable", "isDefault", "isActive", "isPrivate", "isNameInferred",
                 "isDataTypeInferred", "showAsVariationsOnly", "isDefaultImage", "isAvailableInMdx"}

_RE_PROP = re.compile(r"^([A-Za-z_]\w*)\s*:\s*(.*)$")
_RE_IGUAL = re.compile(r"^([A-Za-z_]\w*)\s*=\s*(.*)$")


class _Nodo:
    """Objeto TMDL: tipo, nombre, expresión («= ...»), propiedades, comentario /// e hijos."""

    __slots__ = ("tipo", "nombre", "nivel", "expr", "doc", "props", "hijos")

    def __init__(self, tipo, nombre, nivel, expr=None, doc=""):
        self.tipo, self.nombre, self.nivel, self.expr, self.doc = tipo, nombre, nivel, expr, doc
        self.props: dict = {}
        self.hijos: list[_Nodo] = []

    def hijos_de(self, tipo: str):
        return [h for h in self.hijos if h.tipo == tipo]

    def bandera(self, clave: str) -> bool:
        v = self.props.get(clave)
        return v is True or (isinstance(v, str) and v.strip().lower() == "true")

    def texto(self, clave: str):
        v = self.props.get(clave)
        return None if v is None or v is True else _sin_comillas(str(v))


def _nivel(linea: str) -> int:
    tabs = len(linea) - len(linea.lstrip("\t"))
    if tabs:
        return tabs
    return (len(linea) - len(linea.lstrip(" "))) // 4


def _sin_comillas(valor: str) -> str:
    valor = valor.strip()
    m = re.fullmatch(r"'((?:[^']|'')*)'", valor)
    return m.group(1).replace("''", "'") if m else valor


def _separar_nombre(resto: str) -> tuple[str, str | None]:
    """«'EN ESPERA' = expr» -> ("EN ESPERA", "expr"); «X» -> ("X", None)."""
    resto = resto.strip()
    if resto[:1] in ("'", '"'):
        comilla = resto[0]
        i, buf = 1, []
        while i < len(resto):
            if resto[i] == comilla:
                if i + 1 < len(resto) and resto[i + 1] == comilla:
                    buf.append(comilla)
                    i += 2
                    continue
                i += 1
                break
            buf.append(resto[i])
            i += 1
        nombre, cola = "".join(buf), resto[i:].strip()
    else:
        nombre, signo, cola = resto.partition("=")
        nombre, cola = nombre.strip(), (signo + cola).strip()
    expresion = cola[1:].strip() if cola.startswith("=") else None
    return nombre, expresion


def _desindentar(lineas: list[str]) -> str:
    utiles = [l for l in lineas if l.strip()]
    if not utiles:
        return ""
    comun = min(len(l) - len(l.lstrip("\t ")) for l in utiles)
    return "\n".join(l[comun:] if l.strip() else "" for l in lineas).strip()


def _es_linea_propiedad(contenido: str) -> bool:
    palabra = re.match(r"[A-Za-z_]\w*", contenido)
    if not palabra:
        return False
    return bool(_RE_PROP.match(contenido)) or palabra.group(0) in OBJETOS_TMDL | BANDERAS_TMDL | {"changedProperty"}


def _cuerpo(lineas: list[str], j: int, primera: str, nivel: int, objeto: bool) -> tuple[str, int]:
    """Texto que sigue a «= ...»: en la misma línea, en líneas más indentadas o entre
    ``` ... ```. `nivel` es el del encabezado; el cuerpo de un objeto (medida, columna)
    va dos niveles más adentro (las propiedades, uno); el de una propiedad, uno.
    Devuelve (texto, índice de la siguiente línea)."""
    primera = primera.strip()
    if primera.startswith("```"):
        resto = primera[3:]
        if "```" in resto:
            return resto.split("```")[0].strip(), j
        buf = [resto] if resto.strip() else []
        while j < len(lineas):
            l = lineas[j]
            if l.strip().startswith("```"):
                return _desindentar(buf), j + 1
            if l.rstrip().endswith("```"):
                buf.append(l.rstrip()[:-3])
                return _desindentar(buf), j + 1
            buf.append(l)
            j += 1
        return _desindentar(buf), j
    minimo = nivel + (2 if objeto else 1)
    buf = []
    while j < len(lineas):
        l = lineas[j]
        if not l.strip():
            buf.append(l)
            j += 1
            continue
        niv = _nivel(l)
        if niv >= minimo or (objeto and niv == nivel + 1 and not _es_linea_propiedad(l.strip())):
            buf.append(l)
            j += 1
            continue
        break
    while buf and not buf[-1].strip():
        buf.pop()
    # Las líneas en blanco finales las consumió el cuerpo: no importa, el lector las salta.
    cuerpo = _desindentar(buf)
    if primera:
        return primera + ("\n" + cuerpo if cuerpo else ""), j
    return cuerpo, j


def _nodos_tmdl(texto: str) -> _Nodo:
    """Árbol de objetos de un archivo TMDL (tablas, expresiones, relaciones, roles...)."""
    lineas = texto.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    raiz = _Nodo("raiz", None, -1)
    pila = [raiz]
    doc: list[str] = []
    i = 0
    while i < len(lineas):
        linea = lineas[i]
        contenido = linea.strip()
        i += 1
        if not contenido:
            continue
        if contenido.startswith("///"):
            doc.append(contenido[3:].strip())
            continue
        if contenido.startswith("//"):
            continue
        nivel = _nivel(linea)
        while len(pila) > 1 and pila[-1].nivel >= nivel:
            pila.pop()
        padre = pila[-1]
        m = _RE_PROP.match(contenido)
        if m:
            padre.props[m.group(1)] = m.group(2).strip()
            doc = []
            continue
        palabra = re.match(r"\S+", contenido).group(0)
        if palabra in OBJETOS_TMDL:
            nombre, expr = _separar_nombre(contenido[len(palabra):])
            if expr is not None:
                expr, i = _cuerpo(lineas, i, expr, nivel, True)
            nodo = _Nodo(palabra, nombre, nivel, expr, "\n".join(doc).strip())
            padre.hijos.append(nodo)
            pila.append(nodo)
            doc = []
            continue
        m = _RE_IGUAL.match(contenido)
        if m:
            valor, i = _cuerpo(lineas, i, m.group(2), nivel, False)
            padre.props[m.group(1)] = valor
        else:
            padre.props[contenido] = True
        doc = []
    return raiz


def _parsear_tabla_tmdl(texto: str) -> dict:
    """Lectura mínima de un archivo de tabla (nombre, columnas, calculadas, medidas,
    particiones); `_convertir_tabla` da el detalle completo."""
    raiz = _nodos_tmdl(texto)
    nodo = next(iter(raiz.hijos_de("table")), None)
    if nodo is None:
        return {"nombre": None, "columnas": [], "calculadas": {}, "medidas": {}, "particiones": []}
    t = _convertir_tabla(nodo)
    return {
        "nombre": t["nombre"],
        "columnas": [c["nombre"] for c in t["columnas_detalle"]],
        "calculadas": {c["nombre"]: c["dax"] for c in t["columnas_detalle"] if c["calculada"] and c["dax"]},
        "medidas": {m["nombre"]: m["dax"] for m in t["medidas_detalle"]},
        "particiones": [{"nombre": p["nombre"], "tipo": p["tipo"], "modo": p["modo_tmdl"], "fuente": p["fuente"]}
                        for p in t["particiones"]],
        "detalle": t,
    }


def _convertir_tabla(nodo: _Nodo) -> dict:
    """Hechos de una tabla TMDL: columnas, medidas, jerarquías y particiones con todos sus atributos."""
    tabla = nodo.nombre
    columnas, medidas, jerarquias, particiones, items = [], [], [], [], []
    for h in nodo.hijos:
        if h.tipo == "column":
            calculada = h.expr is not None or h.texto("type") == "calculated"
            columnas.append({
                "nombre": h.nombre, "tabla": tabla, "tipo": h.texto("dataType"),
                "oculta": h.bandera("isHidden"), "calculada": bool(calculada),
                "dax": (h.expr or None) if calculada else None,
                "descripcion": h.doc or h.texto("description") or None,
                "resumen_por": h.texto("summarizeBy"), "columna_origen": h.texto("sourceColumn"),
                "formato": h.texto("formatString"), "carpeta": h.texto("displayFolder"),
                "categoria": h.texto("dataCategory"), "ordenar_por": h.texto("sortByColumn"),
                "clave": h.bandera("isKey"),
            })
        elif h.tipo == "measure":
            medidas.append({
                "nombre": h.nombre, "tabla": tabla, "dax": h.expr or "",
                "descripcion": h.doc or h.texto("description") or None,
                "formato": h.texto("formatString"), "carpeta": h.texto("displayFolder"),
                "oculta": h.bandera("isHidden"), "tipo": h.texto("dataType"),
            })
        elif h.tipo == "hierarchy":
            jerarquias.append({"nombre": h.nombre, "oculta": h.bandera("isHidden"),
                               "niveles": [n.nombre for n in h.hijos_de("level")]})
        elif h.tipo == "partition":
            propios = h.props
            fuente = propios.get("source")
            particiones.append({
                "nombre": h.nombre, "tipo": (h.expr or "").strip().lower(),
                "modo_tmdl": h.texto("mode") or "import",
                "fuente": "" if fuente in (None, True) else str(fuente),
                "entidad": h.texto("entityName"), "esquema": h.texto("schemaName"),
            })
        elif h.tipo == "calculationGroup":
            for it in h.hijos_de("calculationItem"):
                items.append({"nombre": it.nombre, "dax": it.expr or "", "formato": None})
    return {
        "nombre": tabla, "oculta": nodo.bandera("isHidden"),
        "descripcion": nodo.doc or nodo.texto("description") or None,
        "columnas_detalle": columnas, "medidas_detalle": medidas, "jerarquias": jerarquias,
        "particiones": particiones, "elementos_calculo": items,
        "grupo_calculo": bool(nodo.hijos_de("calculationGroup")),
    }


def _cadena_m(texto: str, inicio: int) -> tuple[str, int]:
    """Lee el literal de texto M que empieza en texto[inicio] == '"'."""
    i, partes = inicio + 1, []
    while i < len(texto):
        ch = texto[i]
        if ch == '"':
            if i + 1 < len(texto) and texto[i + 1] == '"':
                partes.append('"')
                i += 2
                continue
            return "".join(partes), i + 1
        partes.append(ch)
        i += 1
    return "".join(partes), i


_ESCAPES_M = {"lf": "\n", "cr": "\r", "tab": "\t"}


def _decodificar_m(valor: str) -> str:
    def reemplazo(m):
        salida = []
        for token in m.group(1).split(","):
            token = token.strip()
            if token.lower() in _ESCAPES_M:
                salida.append(_ESCAPES_M[token.lower()])
            elif re.fullmatch(r"[0-9A-Fa-f]{4}|[0-9A-Fa-f]{8}", token):
                salida.append(chr(int(token, 16)))
            else:
                return m.group(0)
        return "".join(salida)

    texto = re.sub(r"#\(([^)]*)\)", reemplazo, valor)
    return texto.replace("\r\n", "\n").replace("\r", "\n")


def _siguiente_cadena(texto: str, desde: int) -> tuple[str | None, int]:
    j = texto.find('"', desde)
    if j < 0:
        return None, desde
    valor, fin = _cadena_m(texto, j)
    return _decodificar_m(valor), fin


# Datos que no deben quedar en los hechos: contraseñas, usuarios, tokens y claves en
# cadenas de conexión, registros de credenciales de M y direcciones con usuario:clave@.
_SECRETO = r"(?:password|pwd|passwd|secret|token|api[_-]?key|apikey|access[_-]?key|account[_-]?key|client[_-]?secret|authorization|bearer)"
_RE_SECRETOS = [
    # Password=abc; / Pwd='abc' / "Password": "abc"
    (re.compile(r"(?i)(\b" + _SECRETO + r"\b[\"']?\s*[=:]\s*)(\"\"[^\"]*\"\"|\"[^\"]*\"|'[^']*'|[^;&\s,\]\)\"]+)"), r"\1***"),
    # https://usuario:clave@host
    (re.compile(r"(?i)(\b[a-z][a-z0-9+.-]*://)[^/\s:@\"']+:[^/\s@\"']+@"), r"\1***@"),
]
# Usuario de la cadena de conexión; no se aplica al SQL (user, username pueden ser columnas).
_RE_USUARIO = re.compile(r"(?i)(\b(?:user\s*id|uid|username)\b[\"']?\s*=\s*)(\"\"[^\"]*\"\"|\"[^\"]*\"|'[^']*'|[^;&\s,\]\)\"]+)")


def _sanear(texto, sql: bool = False):
    """Quita credenciales (contraseñas, usuarios, tokens) de un texto de conexión, M o SQL."""
    if not texto:
        return texto
    for patron, reemplazo in _RE_SECRETOS:
        texto = patron.sub(reemplazo, texto)
    if not sql:
        texto = _RE_USUARIO.sub(r"\1***", texto)
    return texto


# Funciones de M que transforman datos: no son el origen.
_NO_ORIGEN = ("Table.", "List.", "Text.", "Record.", "Number.", "Date.", "DateTime.", "DateTimeZone.", "Time.",
              "Duration.", "Type.", "Splitter.", "Combiner.", "Replacer.", "Comparer.", "Int64.", "Logical.",
              "Expression.", "Function.", "Value.", "Error.", "Currency.", "Percentage.", "Single.", "Double.",
              "Decimal.", "Binary.", "Character.", "Uri.", "Culture.", "Diagnostics.", "Lines.", "Action.",
              "Variable.", "Odbc.Query", "Sql.Native")
_ORIGENES = {
    "Sql.Database": "SQL Server", "Sql.Databases": "SQL Server", "Oracle.Database": "Oracle",
    "PostgreSQL.Database": "PostgreSQL", "MySQL.Database": "MySQL", "Odbc.DataSource": "ODBC", "Odbc.Query": "ODBC",
    "OleDb.DataSource": "OLE DB", "OleDb.Query": "OLE DB", "Excel.Workbook": "Excel", "Excel.CurrentWorkbook": "Excel",
    "Csv.Document": "CSV", "Json.Document": "JSON", "Xml.Tables": "XML", "Xml.Document": "XML",
    "SharePoint.Files": "SharePoint", "SharePoint.Tables": "SharePoint", "SharePoint.Contents": "SharePoint",
    "Web.Contents": "Web", "Web.Page": "Web", "Folder.Files": "Carpeta", "Folder.Contents": "Carpeta",
    "File.Contents": "Archivo", "AnalysisServices.Database": "Analysis Services", "Access.Database": "Access",
    "Snowflake.Databases": "Snowflake", "GoogleBigQuery.Database": "BigQuery", "Teradata.Database": "Teradata",
    "Databricks.Catalogs": "Databricks", "Lakehouse.Contents": "Lakehouse", "Fabric.Warehouse": "Warehouse",
    "OData.Feed": "OData", "Parquet.Document": "Parquet", "Pdf.Tables": "PDF",
}


def _resumen_origen(info: dict, fuente: str) -> str | None:
    """Frase corta del origen (sin credenciales) para documentar la tabla."""
    origen = info.get("origen")
    if not origen:
        return None
    if origen == "referencia":
        return f"Referencia a la consulta {info.get('referencia')}"
    if origen == "manual":
        return "Datos escritos a mano en Power Query"
    nombre = _ORIGENES.get(origen, origen)
    partes = [nombre]
    if info.get("base_datos"):
        partes.append(f"base {info['base_datos']}")
    if info.get("servidor"):
        partes.append(f"servidor {info['servidor']}")
    elif origen in ("Excel.Workbook", "Csv.Document", "File.Contents", "Folder.Files", "Web.Contents"):
        destino = re.search(r"(?:File|Folder)\.(?:Contents|Files)\(\s*\"([^\"]*)\"|Web\.Contents\(\s*\"([^\"]*)\"", fuente)
        if destino:
            ruta = _sanear(destino.group(1) or destino.group(2))
            host = re.match(r"(?i)https?://([^/?#]+)", ruta)
            partes.append(f"sitio {host.group(1)}" if host else _corto(ruta, 100))
    texto = ", ".join(partes)
    if info.get("sql"):
        texto += f"; consulta SQL de {len(info['sql'])} caracteres"
    return texto


def _analizar_m(fuente: str) -> dict:
    """Origen, servidor, base y SQL nativo de una consulta Power Query. Nada de lo
    devuelto incluye credenciales."""
    info = {"origen": None, "servidor": None, "base_datos": None, "sql": None}
    for m in re.finditer(r"(?<![\w.#\"])([A-Z][A-Za-z0-9]*\.[A-Z][A-Za-z0-9]*)\s*\(", fuente):
        if m.group(1) in _ORIGENES or not m.group(1).startswith(_NO_ORIGEN):
            info["origen"] = m.group(1)
            break
    m = re.search(r"Sql\.Databases?\s*\(", fuente)
    if m:
        info["origen"] = "Sql.Database"
        servidor, fin = _siguiente_cadena(fuente, m.end())
        info["servidor"] = servidor
        if re.match(r"\s*,\s*\"", fuente[fin:]):
            info["base_datos"], _ = _siguiente_cadena(fuente, fin)
    m = re.search(r"Value\.NativeQuery\s*\(", fuente)
    if m:
        # Primer argumento (la conexión) hasta la coma de nivel 0; luego el texto SQL.
        i, nivel = m.end(), 0
        while i < len(fuente):
            ch = fuente[i]
            if ch == '"':
                _, i = _cadena_m(fuente, i)
                continue
            if ch in "([{":
                nivel += 1
            elif ch in ")]}":
                nivel -= 1
            elif ch == "," and nivel == 0:
                break
            i += 1
        sql, _ = _siguiente_cadena(fuente, i)
        info["sql"] = sql
    else:
        m = re.search(r"\bQuery\s*=\s*\"", fuente)
        if m:
            info["sql"], _ = _siguiente_cadena(fuente, m.end() - 1)
    if info["sql"] is not None:
        info["sql"] = _sanear(info["sql"].strip(), sql=True)
    if info["servidor"]:
        info["servidor"] = _sanear(info["servidor"])
    if info["origen"] is None:
        if re.search(r"#table\s*\(|\bTable\.From(?:Rows|Records|Columns)\s*\(", fuente):
            info["origen"] = "manual"
        else:
            r = re.search(r"\blet\s+[^=\n]+=\s*(#\"([^\"]+)\"|([A-Za-z_]\w*))\s*[,\n]", fuente)
            if r and (r.group(2) or r.group(3)) not in ("true", "false", "null"):
                info["origen"] = "referencia"
                info["referencia"] = r.group(2) or r.group(3)
    return info


def _datos_tabla(t: dict) -> dict:
    """Entrada de `tablas` a partir de la tabla convertida."""
    parts = t["particiones"]
    part = parts[0] if parts else {"tipo": "", "modo_tmdl": "import", "fuente": "", "nombre": None, "entidad": None, "esquema": None}
    modo = MODOS.get(str(part["modo_tmdl"]).lower(), part["modo_tmdl"])
    datos = {
        "modo": modo,
        "origen": None, "servidor": None, "base_datos": None, "sql": None, "m": None, "dax": None,
        "columnas": [c["nombre"] for c in t["columnas_detalle"]],
        "calculadas": {c["nombre"]: c["dax"] for c in t["columnas_detalle"] if c["calculada"] and c["dax"]},
        "columnas_detalle": t["columnas_detalle"],
        "medidas": [m["nombre"] for m in t["medidas_detalle"]],
        "jerarquias": t["jerarquias"],
        "particiones": [{"nombre": p["nombre"], "tipo": p["tipo"], "modo": MODOS.get(str(p["modo_tmdl"]).lower(), p["modo_tmdl"])}
                        for p in parts],
        "descripcion": t["descripcion"],
        "oculta": t["oculta"],
        "calculada": part["tipo"] == "calculated",
        "origen_resumen": None,
    }
    if t["grupo_calculo"]:
        datos["grupo_calculo"] = t["elementos_calculo"]
    if part["tipo"] == "calculated":
        datos["origen"] = "DAX"
        datos["dax"] = part["fuente"] or None
        datos["origen_resumen"] = "Tabla calculada con DAX"
    elif part["tipo"] == "entity" or part.get("entidad"):
        datos["origen"] = "Entity"
        datos["origen_resumen"] = f"Entidad {part.get('esquema') + '.' if part.get('esquema') else ''}{part.get('entidad')}"
    elif part["fuente"]:
        info = _analizar_m(part["fuente"])
        resumen = _resumen_origen(info, part["fuente"])
        for k in ("origen", "servidor", "base_datos", "sql"):
            datos[k] = info[k]
        if info["sql"] is None:
            datos["m"] = _sanear(part["fuente"])
        if info.get("referencia"):
            datos["referencia"] = info["referencia"]
        datos["origen_resumen"] = resumen
    return datos


_PROPIEDADES_REL = re.compile(r"(?m)^[ \t]+(\w+)\s*:\s*(.+?)\s*$")


def _relaciones(archivo_rel: Path) -> tuple[list[str], list[dict]]:
    textos, detalle = [], []
    raiz = _nodos_tmdl(archivo_rel.read_text(encoding="utf-8-sig"))
    for r in raiz.hijos_de("relationship"):
        origen, destino = _columna_rel(r.texto("fromColumn") or ""), _columna_rel(r.texto("toColumn") or "")
        if not origen or not destino or _es_automatica(origen[0]) or _es_automatica(destino[0]):
            continue
        activa = (r.texto("isActive") or "true").lower() != "false"
        ambos = (r.texto("crossFilteringBehavior") or "").lower() == "bothdirections"
        texto = f"{origen[0]}[{origen[1]}] -> {destino[0]}[{destino[1]}]"
        if not activa:
            texto += " (inactiva)"
        if ambos:
            texto += " (filtro en ambos sentidos)"
        textos.append(texto)
        detalle.append({
            "texto": texto, "desde": f"{origen[0]}[{origen[1]}]", "hacia": f"{destino[0]}[{destino[1]}]",
            "activa": activa, "ambos_sentidos": ambos,
            "cardinalidad_desde": r.texto("fromCardinality") or "many",
            "cardinalidad_hacia": r.texto("toCardinality") or "one",
        })
    orden = sorted(range(len(textos)), key=lambda k: textos[k])
    return [textos[k] for k in orden], [detalle[k] for k in orden]


def _modelo(modelo: Path | None, advertencias: list | None = None) -> dict:
    """Tablas, medidas, relaciones, expresiones compartidas y roles de la carpeta
    <Modelo>.SemanticModel/definition. Un archivo ilegible se anota en
    `advertencias` y no detiene el resto."""
    salida = {"tablas": {}, "medidas": {}, "medidas_detalle": {}, "relaciones": [], "relaciones_detalle": [],
              "modelo": {}, "expresiones": {}, "roles": {}}
    advertencias = advertencias if advertencias is not None else []
    if modelo is None:
        return salida
    definicion = modelo / "definition"
    for archivo in sorted((definicion / "tables").glob("*.tmdl")):
        try:
            raiz = _nodos_tmdl(archivo.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as e:
            advertencias.append(f"No se pudo leer la tabla {archivo.name}: {e}")
            continue
        for nodo in raiz.hijos_de("table"):
            nombre = nodo.nombre or archivo.stem
            if _es_automatica(nombre):
                continue
            t = _convertir_tabla(nodo)
            salida["tablas"][nombre] = _datos_tabla(t)
            for m in t["medidas_detalle"]:
                clave = f"{nombre}[{m['nombre']}]"
                salida["medidas"][clave] = m["dax"]
                salida["medidas_detalle"][clave] = m

    archivo_rel = definicion / "relationships.tmdl"
    if archivo_rel.exists():
        try:
            salida["relaciones"], salida["relaciones_detalle"] = _relaciones(archivo_rel)
        except (OSError, ValueError) as e:
            advertencias.append(f"No se pudo leer relationships.tmdl: {e}")

    archivo_modelo = definicion / "model.tmdl"
    if archivo_modelo.exists():
        try:
            for m in _nodos_tmdl(archivo_modelo.read_text(encoding="utf-8-sig")).hijos_de("model"):
                salida["modelo"] = {
                    "nombre": m.nombre, "descripcion": m.doc or m.texto("description") or None,
                    "cultura": m.texto("culture"), "modo_defecto": m.texto("defaultMode"),
                }
        except (OSError, ValueError) as e:
            advertencias.append(f"No se pudo leer model.tmdl: {e}")

    archivo_expr = definicion / "expressions.tmdl"
    if archivo_expr.exists():
        try:
            for e in _nodos_tmdl(archivo_expr.read_text(encoding="utf-8-sig")).hijos_de("expression"):
                info = _analizar_m(e.expr or "")
                salida["expresiones"][e.nombre] = {
                    "descripcion": e.doc or None, "origen": info["origen"], "servidor": info["servidor"],
                    "base_datos": info["base_datos"], "m": _sanear(e.expr or ""),
                    "parametro": bool(re.search(r"meta\s*\[[^\]]*IsParameterQuery\s*=\s*true", e.expr or "", re.I)),
                }
        except (OSError, ValueError) as e:
            advertencias.append(f"No se pudo leer expressions.tmdl: {e}")

    for archivo in sorted((definicion / "roles").glob("*.tmdl")):
        try:
            for r in _nodos_tmdl(archivo.read_text(encoding="utf-8-sig")).hijos_de("role"):
                salida["roles"][r.nombre] = {
                    "permiso": r.texto("modelPermission"),
                    "filtros": {p.nombre: p.props.get("filterExpression") or p.expr for p in r.hijos_de("tablePermission")},
                }
        except (OSError, ValueError) as e:
            advertencias.append(f"No se pudo leer el rol {archivo.name}: {e}")
    return salida


_COLUMNA_REL = re.compile(r"^(?:'((?:[^']|'')*)'|([^.']+))\.(?:'((?:[^']|'')*)'|(.+))$")


def _columna_rel(valor: str) -> tuple[str, str] | None:
    """«'EN ESPERA'.'COL'» o «T.COL» -> (tabla, columna)."""
    m = _COLUMNA_REL.match(valor.strip())
    if not m:
        return None
    tabla = (m.group(1) if m.group(1) is not None else m.group(2)).replace("''", "'")
    columna = (m.group(3) if m.group(3) is not None else m.group(4)).replace("''", "'")
    return tabla.strip(), columna.strip()


# ---------------------------------------------------------------------------
# API: hechos
# ---------------------------------------------------------------------------

def _tablas_desde_referencias(referencias: set) -> tuple[dict, dict]:
    """Sin modelo (.pbix): tablas y medidas solo con los nombres que citan los visuales."""
    tablas, medidas = {}, {}
    for tipo, tabla, nombre in sorted(referencias):
        datos = tablas.setdefault(tabla, {"modo": None, "origen": None, "servidor": None, "base_datos": None,
                                          "sql": None, "m": None, "dax": None, "columnas": [], "calculadas": {}})
        if tipo == "medida":
            medidas[f"{tabla}[{nombre}]"] = None
        elif nombre not in datos["columnas"]:
            datos["columnas"].append(nombre)
    return tablas, medidas


def extraer_hechos(ruta_pbip) -> dict:
    """Hechos del tablero (páginas, visuales, tablas, medidas y relaciones) en un
    dict serializable con json. Ver el contrato al inicio del módulo.

    Acepta la carpeta del PBIP, el archivo .pbip, la carpeta .Report o un .pbix.
    Del .pbix solo se leen (sin extraer a disco) las entradas «Report/...»; nunca
    DataModel. Como el .pbix no trae el modelo en texto, las tablas y medidas
    quedan solo con los nombres que citan los visuales y
    `modelo_disponible` es False."""
    ruta = Path(ruta_pbip)
    referencias: set = set()
    advertencias: list[str] = []
    marcadores: list[dict] = []
    if ruta.is_file() and ruta.suffix.lower() == ".pbix":
        with zipfile.ZipFile(ruta) as zf:
            lector = _LectorZip(zf)
            if not lector.nombres:
                raise FileNotFoundError(f"«{ruta}» no trae el informe en formato PBIR (Report/definition/).")
            paginas, filtros_reporte = _paginas(lector, referencias, advertencias, marcadores)
        nombre, modelo = ruta.stem, None
    else:
        nombre, informe, modelo = _ubicar(ruta)
        paginas, filtros_reporte = _paginas(_LectorCarpeta(informe / "definition"), referencias, advertencias, marcadores)
    extra = {}
    if modelo is not None:
        m = _modelo(modelo, advertencias)
        tablas, medidas, relaciones = m["tablas"], m["medidas"], m["relaciones"]
        extra = {"medidas_detalle": m["medidas_detalle"], "relaciones_detalle": m["relaciones_detalle"],
                 "modelo": m["modelo"], "expresiones": m["expresiones"], "roles": m["roles"]}
        citadas = {t for p in paginas for v in p["visuales"] for t in v.get("tablas") or []}
        # Referencias de visuales o filtros que quedaron de tablas ya renombradas o borradas.
        huerfanas = sorted(t for t in citadas if t not in tablas)
        if huerfanas:
            advertencias.append("El informe cita tablas que no están en el modelo (referencias obsoletas): "
                                + ", ".join(huerfanas))
    else:
        (tablas, medidas), relaciones = _tablas_desde_referencias(referencias), []
    return {
        "version_hechos": VERSION_HECHOS,
        "tablero": nombre,
        "modelo_disponible": modelo is not None,
        "paginas": paginas,
        "filtros_reporte": filtros_reporte,
        "marcadores": marcadores,
        "tablas": tablas,
        "medidas": medidas,
        "relaciones": relaciones,
        **extra,
        "advertencias": advertencias,
    }


def ruta_instantanea(source_group: str, raiz=None) -> Path:
    return raiz_documentos(raiz) / source_group / ARCHIVO_INSTANTANEA


def guardar_instantanea(hechos: dict, source_group: str, raiz=None) -> Path:
    """Guarda los hechos como referencia para la próxima comparación."""
    destino = ruta_instantanea(source_group, raiz)
    destino.parent.mkdir(parents=True, exist_ok=True)
    datos = dict(hechos)
    datos["instantanea"] = date.today().isoformat()
    destino.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    return destino


def cargar_instantanea(source_group: str, raiz=None) -> dict | None:
    origen = ruta_instantanea(source_group, raiz)
    if not origen.exists():
        return None
    return json.loads(origen.read_text(encoding="utf-8"))


def cambios_desde_instantanea(ruta_pbip, source_group: str, raiz=None) -> list[str]:
    """Frases de lo que cambió en el PBIP desde la última instantánea guardada
    (lista vacía si no hay instantánea)."""
    antes = cargar_instantanea(source_group, raiz)
    if antes is None:
        return []
    return comparar(antes, extraer_hechos(ruta_pbip))


# ---------------------------------------------------------------------------
# API: comparar
# ---------------------------------------------------------------------------

def _tipo_base(tipo: str) -> str:
    """«textFilter25A4...» -> «textFilter»; «PBI_CV_16948668_...» se queda igual."""
    m = re.fullmatch(r"([A-Za-z]+?)([0-9A-Fa-f]{32})", tipo or "")
    return m.group(1) if m else (tipo or "")


def _nombre_tipo(tipo: str) -> str:
    if tipo in TIPOS_VISUAL:
        return TIPOS_VISUAL[tipo]
    base = _tipo_base(tipo)
    if base in PERSONALIZADOS:
        return PERSONALIZADOS[base]
    if base != tipo or str(tipo).startswith("PBI_CV_"):
        return f"Visual personalizado ({base[:30]})"
    return tipo


def _nombre_visual(v: dict) -> str:
    """Tarjeta «TIEMPO PROMEDIO PARA TRIAGE», Botón hacia RESUMEN_D, Forma 4e937b7d40de68441146."""
    tipo = _nombre_tipo(v.get("tipo", ""))
    if v.get("titulo"):
        return f"{tipo} «{_corto(v['titulo'], 60)}»"
    if v.get("texto"):
        return f"{tipo} «{_corto(v['texto'], 60)}»"
    if v.get("tipo") == "actionButton" and v.get("destino"):
        return f"{tipo} hacia {v['destino']}"
    detalle = v.get("campos_detalle") or []
    if detalle and not _es_segmentador(v.get("tipo") or ""):
        return f"{tipo} «{_corto(detalle[0]['nombre'], 60)}»"
    if detalle:
        return f"{tipo} de {detalle[0]['expresion']}"
    return f"{tipo} {v.get('id')}"


def _base_texto(expresion: str) -> str:
    """AVERAGE(T[c]) -> T[c]; T[c] (Día) -> T[c] (Día)."""
    m = re.fullmatch(r"[A-Z_]+\((.*)\)", expresion)
    return m.group(1) if m else expresion


def _agregacion(expresion: str) -> str:
    m = re.fullmatch(r"([A-Z_]+)\(.*\)", expresion)
    return m.group(1) if m else "sin agregación"


def _clave_filtro(filtro: str) -> str:
    m = re.match(r"^(.+?\[[^\]]*\](?: \([^)]*\))?)", filtro)
    return m.group(1) if m else filtro


def _por_campo(semaforo: list[str]) -> dict[str, list[str]]:
    grupos: dict[str, list[str]] = {}
    for s in semaforo:
        campo, _, regla = s.rpartition(": ")
        grupos.setdefault(campo, []).append(regla)
    return grupos


def _comparar_visual(prefijo: str, a: dict, d: dict) -> list[str]:
    frases = []
    etiqueta = f"{prefijo}, {_nombre_visual(a)}"
    if a.get("tipo") != d.get("tipo"):
        frases.append(f"{etiqueta}: cambió de tipo a {_nombre_tipo(d.get('tipo'))}.")
    if (a.get("titulo") or "") != (d.get("titulo") or ""):
        frases.append(f"{etiqueta}: cambió el título a «{d['titulo']}»." if d.get("titulo")
                      else f"{etiqueta}: se quitó el título.")

    # Campos: primero cambios de agregación sobre la misma columna.
    antes, despues = list(a.get("campos") or []), list(d.get("campos") or [])
    for expr in list(antes):
        if expr in despues:
            antes.remove(expr)
            despues.remove(expr)
    for expr in list(antes):
        base = _base_texto(expr)
        pareja = next((x for x in despues if _base_texto(x) == base), None)
        if pareja is not None:
            frases.append(f"{etiqueta}: la agregación de {base} cambió de {_agregacion(expr)} a {_agregacion(pareja)}.")
            antes.remove(expr)
            despues.remove(pareja)
    for expr in antes:
        frases.append(f"{etiqueta}: se quitó el campo {expr}.")
    for expr in despues:
        frases.append(f"{etiqueta}: se agregó el campo {expr}.")
    nombres_a = {c["expresion"]: c["nombre"] for c in a.get("campos_detalle") or []}
    for c in d.get("campos_detalle") or []:
        previo = nombres_a.get(c["expresion"])
        if previo is not None and previo != c["nombre"]:
            frases.append(f"{etiqueta}: el campo {c['expresion']} ahora se muestra como «{c['nombre']}» (antes «{previo}»).")

    # Filtros: si cambia la condición sobre la misma columna se dice «cambió».
    fa = [f for f in a.get("filtros") or [] if f not in (d.get("filtros") or [])]
    fd = [f for f in d.get("filtros") or [] if f not in (a.get("filtros") or [])]
    for f in list(fa):
        pareja = next((x for x in fd if _clave_filtro(x) == _clave_filtro(f)), None)
        if pareja is not None:
            frases.append(f"{etiqueta}: cambió el filtro de {_clave_filtro(f)}: antes «{f}»; ahora «{pareja}».")
            fa.remove(f)
            fd.remove(pareja)
    for f in fa:
        frases.append(f"{etiqueta}: se quitó el filtro «{f}».")
    for f in fd:
        frases.append(f"{etiqueta}: se agregó el filtro «{f}».")

    sa, sd = _por_campo(a.get("semaforo") or []), _por_campo(d.get("semaforo") or [])
    for campo in list(sa) + [c for c in sd if c not in sa]:
        if campo not in sd:
            frases.append(f"{etiqueta}: se quitó el semáforo de {campo} («{', '.join(sa[campo])}»).")
        elif campo not in sa:
            frases.append(f"{etiqueta}: se agregó semáforo en {campo}: «{', '.join(sd[campo])}».")
        elif sa[campo] != sd[campo]:
            frases.append(f"{etiqueta}: cambió el semáforo de {campo}: antes «{', '.join(sa[campo])}»; "
                          f"ahora «{', '.join(sd[campo])}».")

    if (a.get("texto") or "") != (d.get("texto") or ""):
        frases.append(f"{etiqueta}: el texto cambió a «{_corto(d.get('texto') or '', 200)}».")
    if (a.get("destino_id") or "") != (d.get("destino_id") or ""):
        nuevo = d.get("destino") or d.get("destino_id")
        frases.append(f"{etiqueta}: ahora lleva a {nuevo} (antes {a.get('destino') or a.get('destino_id') or 'ninguna'})."
                      if nuevo else f"{etiqueta}: ya no lleva a ninguna página.")
    if bool(a.get("oculto")) != bool(d.get("oculto")):
        frases.append(f"{etiqueta}: {'quedó oculto' if d.get('oculto') else 'ahora es visible'}.")
    return frases


def _resumen_campos(v: dict) -> str:
    campos = v.get("campos") or []
    return f" ({', '.join(campos)})" if campos else ""


def _sin_comentarios_sql(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql or "", flags=re.S)
    return re.sub(r"--[^\n]*", " ", sql)


def _normalizar_sql(sql: str) -> str:
    return re.sub(r"\s+", " ", _sin_comentarios_sql(sql)).strip()


_FIN_WHERE = re.compile(r"\b(GROUP\s+BY|ORDER\s+BY|HAVING|UNION|EXCEPT|INTERSECT|OPTION|WHERE|SELECT|FROM)\b", re.I)
_AND = re.compile(r"AND\b", re.I)
_BETWEEN = re.compile(r"BETWEEN\b", re.I)


def _condiciones_where(sql: str) -> list[str]:
    """Condiciones (separadas por AND de primer nivel) de todas las cláusulas WHERE."""
    s = _normalizar_sql(sql)
    condiciones = []
    for m in re.finditer(r"\bWHERE\b", s, re.I):
        i, nivel, inicio = m.end(), 0, m.end()
        partes, actual, entre = [], inicio, False
        while i < len(s):
            ch = s[i]
            if ch == "'":
                j = s.find("'", i + 1)
                i = len(s) if j < 0 else j + 1
                continue
            if ch == "(":
                nivel += 1
            elif ch == ")":
                if nivel == 0:
                    break
                nivel -= 1
            elif nivel == 0:
                fin = _FIN_WHERE.match(s, i)
                if fin and (i == 0 or not (s[i - 1].isalnum() or s[i - 1] == "_")):
                    break
                limite = not (s[i - 1].isalnum() or s[i - 1] == "_")
                if limite and _BETWEEN.match(s, i):
                    entre = True  # el AND que sigue es el de BETWEEN x AND y
                elif limite and _AND.match(s, i):
                    if entre:
                        entre = False
                    else:
                        partes.append(s[actual:i].strip())
                        actual = i + 3
            i += 1
        partes.append(s[actual:i].strip())
        condiciones += [p for p in partes if p]
    return list(dict.fromkeys(condiciones))


def _cambio_sql(tabla: str, sql_a: str, sql_d: str) -> str:
    frase = f"Cambió la sentencia SQL de la tabla {tabla}."
    ca, cd = _condiciones_where(sql_a), _condiciones_where(sql_d)
    nuevas = [c for c in cd if c not in ca]
    quitadas = [c for c in ca if c not in cd]
    detalles = []
    if nuevas:
        detalles.append("condiciones WHERE nuevas: " + "; ".join(f"«{_corto(c, 150)}»" for c in nuevas[:4]))
    if quitadas:
        detalles.append("condiciones WHERE quitadas: " + "; ".join(f"«{_corto(c, 150)}»" for c in quitadas[:4]))
    if detalles:
        frase = frase[:-1] + "; " + "; ".join(detalles) + "."
    return frase


def _dax_corto(dax: str) -> str:
    return _corto(dax, 200)


def comparar(hechos_antes, hechos_despues) -> list:
    """Frases en español, una por cambio, entre dos versiones de los hechos."""
    a, d = hechos_antes or {}, hechos_despues or {}
    frases: list[str] = []

    pa = {p["id"]: p for p in a.get("paginas") or []}
    pd = {p["id"]: p for p in d.get("paginas") or []}
    # Páginas con el mismo nombre (dos «INTERCONSULTAS»): se nombran con su id.
    conteo = Counter(p["nombre"] for p in pd.values())
    conteo_a = Counter(p["nombre"] for p in pa.values())

    def nombre_pagina(p: dict, cuenta: Counter) -> str:
        return f"{p['nombre']} (id {p['id']})" if cuenta[p["nombre"]] > 1 else p["nombre"]

    for pid, p in pa.items():
        if pid not in pd:
            frases.append(f"Se eliminó la página {nombre_pagina(p, conteo_a)}.")
    for pid, p in pd.items():
        if pid not in pa:
            estado = "visible" if p.get("visible") else "oculta"
            frases.append(f"Se agregó la página {nombre_pagina(p, conteo)} ({estado}) con {len(p.get('visuales') or [])} visuales.")
    for pid, p in pd.items():
        previa = pa.get(pid)
        if previa is None:
            continue
        nombre = nombre_pagina(p, conteo)
        if previa["nombre"] != p["nombre"]:
            frases.append(f"Se renombró la página {nombre_pagina(previa, conteo_a)} a «{p['nombre']}».")
        if bool(previa.get("visible")) != bool(p.get("visible")):
            frases.append(f"La página {nombre} ahora es {'visible' if p.get('visible') else 'oculta'}.")
        for f in p.get("filtros") or []:
            if f not in (previa.get("filtros") or []):
                frases.append(f"Página {nombre}: se agregó el filtro de página «{f}».")
        for f in previa.get("filtros") or []:
            if f not in (p.get("filtros") or []):
                frases.append(f"Página {nombre}: se quitó el filtro de página «{f}».")
        if (previa.get("obtener_detalles") or []) != (p.get("obtener_detalles") or []):
            campos = ", ".join(p.get("obtener_detalles") or []) or "ninguno"
            frases.append(f"Página {nombre}: cambiaron los campos de obtener detalles (ahora {campos}).")

        va = {v["id"]: v for v in previa.get("visuales") or []}
        vd = {v["id"]: v for v in p.get("visuales") or []}
        prefijo = f"Página {nombre}"
        for vid, v in va.items():
            if vid not in vd:
                frases.append(f"{prefijo}: se eliminó el visual {_nombre_visual(v)}.")
        for vid, v in vd.items():
            if vid not in va:
                extra = ""
                if v.get("filtros"):
                    extra += f" con filtro {'; '.join('«' + f + '»' for f in v['filtros'])}"
                if v.get("semaforo"):
                    extra += f" y semáforo «{', '.join(v['semaforo'])}»" if extra else f" con semáforo «{', '.join(v['semaforo'])}»"
                frases.append(f"{prefijo}: se agregó el visual {_nombre_visual(v)}{_resumen_campos(v)}{extra}.")
        for vid, v in vd.items():
            if vid in va:
                frases += _comparar_visual(prefijo, va[vid], v)

    comunes_a = [p for p in pa if p in pd]
    comunes_d = [p for p in pd if p in pa]
    if comunes_a != comunes_d:
        frases.append("Cambió el orden de las páginas.")

    for f in d.get("filtros_reporte") or []:
        if f not in (a.get("filtros_reporte") or []):
            frases.append(f"Se agregó el filtro de todo el informe «{f}».")
    for f in a.get("filtros_reporte") or []:
        if f not in (d.get("filtros_reporte") or []):
            frases.append(f"Se quitó el filtro de todo el informe «{f}».")

    # Sin modelo en alguno de los lados (.pbix) las tablas solo reflejan lo que
    # citan los visuales: compararlas repetiría los cambios de visuales como ruido.
    if a.get("modelo_disponible") is False or d.get("modelo_disponible") is False:
        return frases

    ta, td = a.get("tablas") or {}, d.get("tablas") or {}
    for t in ta:
        if t not in td:
            frases.append(f"Se eliminó la tabla {t}.")
    for t, datos in td.items():
        if t not in ta:
            origen = f", consulta SQL a {datos['base_datos']}" if datos.get("sql") and datos.get("base_datos") else ""
            frases.append(f"Se agregó la tabla {t} ({datos.get('modo')}{origen}).")
            continue
        previa = ta[t]
        if previa.get("modo") != datos.get("modo"):
            frases.append(f"La tabla {t} pasó de {previa.get('modo')} a {datos.get('modo')}.")
        if _normalizar_sql(previa.get("sql") or "") != _normalizar_sql(datos.get("sql") or ""):
            frases.append(_cambio_sql(t, previa.get("sql") or "", datos.get("sql") or ""))
        if (previa.get("base_datos"), previa.get("servidor")) != (datos.get("base_datos"), datos.get("servidor")):
            frases.append(f"La tabla {t} ahora lee de la base {datos.get('base_datos')} en {datos.get('servidor')}.")
        if re.sub(r"\s+", " ", previa.get("m") or "") != re.sub(r"\s+", " ", datos.get("m") or ""):
            frases.append(f"Cambió la consulta Power Query de la tabla {t}.")
        if re.sub(r"\s+", " ", previa.get("dax") or "") != re.sub(r"\s+", " ", datos.get("dax") or ""):
            frases.append(f"Cambió la definición DAX de la tabla calculada {t}: «{_dax_corto(datos.get('dax') or '')}».")
        calc_a, calc_d = previa.get("calculadas") or {}, datos.get("calculadas") or {}
        nuevas = [c for c in datos.get("columnas") or [] if c not in (previa.get("columnas") or []) and c not in calc_d]
        quitadas = [c for c in previa.get("columnas") or [] if c not in (datos.get("columnas") or []) and c not in calc_a]
        if nuevas:
            frases.append(f"Tabla {t}: se agregaron las columnas {_lista_es(nuevas)}.")
        if quitadas:
            frases.append(f"Tabla {t}: se quitaron las columnas {_lista_es(quitadas)}.")
        for c, dax in calc_d.items():
            if c not in calc_a:
                frases.append(f"Tabla {t}: nueva columna calculada {t}[{c}] = {_dax_corto(dax)}.")
            elif re.sub(r"\s+", " ", calc_a[c]) != re.sub(r"\s+", " ", dax):
                frases.append(f"Tabla {t}: cambió la columna calculada {t}[{c}]: antes «{_dax_corto(calc_a[c])}»; "
                              f"ahora «{_dax_corto(dax)}».")
        for c in calc_a:
            if c not in calc_d:
                frases.append(f"Tabla {t}: se eliminó la columna calculada {t}[{c}].")

    ma, md = a.get("medidas") or {}, d.get("medidas") or {}
    for m, dax in md.items():
        dax = dax or ""
        if m not in ma:
            frases.append(f"Nueva medida {m} = {_dax_corto(dax)}.")
        elif re.sub(r"\s+", " ", ma[m] or "") != re.sub(r"\s+", " ", dax):
            frases.append(f"Cambió la medida {m}: antes «{_dax_corto(ma[m])}»; ahora «{_dax_corto(dax)}».")
    for m in ma:
        if m not in md:
            frases.append(f"Se eliminó la medida {m}.")

    ra, rd = a.get("relaciones") or [], d.get("relaciones") or []
    for r in rd:
        if r not in ra:
            frases.append(f"Nueva relación {r}.")
    for r in ra:
        if r not in rd:
            frases.append(f"Se eliminó la relación {r}.")
    return frases


# ---------------------------------------------------------------------------
# API: esqueleto
# ---------------------------------------------------------------------------

POR_CONFIRMAR = "Por confirmar."


class _Seccion:
    """Entradas de una sección con nombres únicos y textos cerrados en punto."""

    def __init__(self):
        self.entradas: list[F.Entrada] = []
        self._claves: set[str] = set()

    def agregar(self, nombre: str, texto: str):
        nombre = re.sub(r"\s+", " ", str(nombre)).replace("**", "").strip() or "Sin nombre"
        if len(nombre) > F.MAX_NOMBRE - 5:
            nombre = nombre[: F.MAX_NOMBRE - 6].rstrip() + "…"
        base, n = nombre, 2
        while F.normalizar_nombre(nombre) in self._claves:
            nombre = f"{base} ({n})"
            n += 1
        self._claves.add(F.normalizar_nombre(nombre))
        texto = F._cerrar_texto(str(texto).replace("**", "*"))
        self.entradas.append(F.Entrada(nombre, texto))


def _descripcion_tabla(t: str, datos: dict) -> str:
    if not datos.get("modo") and not datos.get("origen"):
        columnas = datos.get("columnas") or []
        texto = "Por confirmar. Modo y origen desconocidos: el archivo no trae el modelo semántico en texto"
        return texto + (f". Columnas usadas en los visuales: {_corto(', '.join(columnas), 200)}" if columnas else "")
    modo = datos.get("modo") or "modo desconocido"
    if datos.get("origen") == "DAX":
        return f"Por confirmar. Tabla calculada con DAX: {_corto(datos.get('dax') or '', 160)}"
    partes = [f"Por confirmar. Tabla en {modo}"]
    if datos.get("sql") is not None:
        partes[0] += f" con consulta SQL a la base {datos.get('base_datos') or 'por confirmar'}"
        condiciones = _condiciones_where(datos["sql"])
        if condiciones:
            partes.append("Condiciones SQL: " + "; ".join(_corto(c, 120) for c in condiciones[:3])
                          + ("; …" if len(condiciones) > 3 else ""))
    elif datos.get("origen"):
        partes[0] += f" con origen {datos['origen']}"
    return ". ".join(partes)


def _huecos(casos: list[dict]) -> list[str]:
    """Valores enteros que ninguna regla colorea entre dos rangos consecutivos."""
    intervalos = []
    for c in casos:
        lo, hi = c.get("min"), c.get("max")
        if c.get("igual") is not None:
            lo = hi = c["igual"]
        if lo is None and hi is None:
            continue
        if any(isinstance(x, float) and not x.is_integer() for x in (lo, hi) if x is not None):
            return []
        a = None if lo is None else (int(lo) if c.get("min_incluido", True) or c.get("igual") is not None else int(lo) + 1)
        b = None if hi is None else (int(hi) if c.get("max_incluido", True) or c.get("igual") is not None else int(hi) - 1)
        intervalos.append((a, b))
    intervalos.sort(key=lambda x: float("-inf") if x[0] is None else x[0])
    huecos = []
    for (a1, b1), (a2, b2) in zip(intervalos, intervalos[1:]):
        if b1 is None or a2 is None:
            continue
        if a2 > b1 + 1:
            faltan = list(range(b1 + 1, a2))
            huecos.append(_numero(faltan[0]) if len(faltan) == 1 else f"{faltan[0]} a {faltan[-1]}")
    return huecos


def _texto_semaforo(regla: dict) -> str:
    if regla["tipo"] == "degradado":
        puntos = {"min": "mínimo", "mid": "medio", "max": "máximo"}
        return "Degradado de color: " + ", ".join(f"{p['color']} en el {puntos.get(p['punto'], p['punto'])}"
                                                  for p in regla["puntos"])
    if regla["tipo"] == "campo":
        return f"El color se toma del campo {regla.get('evalua')}"
    casos = [c for c in regla["casos"] if not (regla["propiedad"] != "fondo" and c["color"] in ("blanco", "negro"))]
    if not casos:
        return ""
    partes = [f"{c['color']} {_rango_en_palabras(c) if 'min' in c else c['rango']}" for c in casos]
    texto = _lista_es(partes)
    return texto[0].upper() + texto[1:]


def _bloque_pagina(pagina: dict, tablas: dict) -> str:
    usadas = {t for v in pagina["visuales"] for c in v.get("campos_detalle") or []
              for t in [_base_texto(c["expresion"]).split("[")[0]] if (tablas.get(t) or {}).get("modo")}
    if usadas:
        en_vivo = sum(1 for t in usadas if tablas[t].get("modo") == "DirectQuery")
        return ("Día" if en_vivo * 2 >= len(usadas) else "Histórico"), "el modo de las tablas de la página"
    nombre = pagina["nombre"].upper()
    return ("Día" if re.search(r"(\bDIA\b|_D$)", nombre) else "Histórico"), "el nombre de la página"


def _documento(meta: dict, titulo: str, proposito: str, secciones: dict[str, _Seccion]) -> str:
    doc = F.Documento(meta=meta, titulo=titulo, proposito=proposito,
                      secciones={k: s.entradas for k, s in secciones.items() if s.entradas})
    return F.serializar(doc)


def _pagina_md(pagina: dict, hechos: dict, tablero: str, nombre_doc: str, llegadas: list[str],
               duplicada: bool, fecha: str) -> str:
    tablas = hechos.get("tablas") or {}
    medidas = hechos.get("medidas") or {}
    secciones = {s: _Seccion() for s in F.SECCIONES_PAGINA if s != F.SECCION_TEXTO}

    usadas = sorted({t for v in pagina["visuales"] for t in v.get("tablas") or []})
    for t in usadas:
        if t in tablas:
            secciones["Fuentes de datos"].agregar(t, _descripcion_tabla(t, tablas[t]))
        else:
            secciones["Fuentes de datos"].agregar(t, "Por confirmar. La tabla no está en el modelo semántico")

    # Indicadores: campos agregados o medidas de los visuales con datos.
    vistos = set()
    for v in pagina["visuales"]:
        if _es_segmentador(v["tipo"]):
            continue
        for c in v.get("campos_detalle") or []:
            expr = c["expresion"]
            es_medida = expr in medidas
            if expr in vistos or not (es_medida or _agregacion(expr) != "sin agregación"):
                continue
            vistos.add(expr)
            texto = f"Por confirmar qué mide y su unidad. Cálculo: {expr}"
            base = _base_texto(expr)
            tabla, _, col = base.partition("[")
            col = col.rstrip("]")
            calc = (tablas.get(tabla) or {}).get("calculadas", {}).get(col)
            if calc:
                texto += f"; {base} es una columna calculada: {_corto(calc, 200)}"
            if es_medida and medidas[expr]:
                texto += f"; medida: {_corto(medidas[expr], 200)}"
            secciones["Indicadores"].agregar(c["nombre"], texto)

    botones, segmentaciones, reglas_semaforo = [], [], []
    for v in pagina["visuales"]:
        tipo = v["tipo"]
        if tipo == "actionButton" or (v.get("destino") and tipo in DECORATIVOS):
            if v.get("destino"):
                botones.append(f"«{v['texto']}» lleva a {v['destino']}" if v.get("texto") else f"un botón lleva a {v['destino']}")
            continue
        if tipo in DECORATIVOS or tipo == "grupo":
            continue
        if _es_segmentador(tipo):
            segmentaciones += v.get("campos") or []
            continue
        nombre = _nombre_visual(v).replace("«", "").replace("»", "")
        partes = []
        if tipo == "textbox":
            partes.append(f"Texto: «{_corto(v.get('texto') or '', 200)}»")
        detalle = v.get("campos_detalle") or []
        if detalle:
            campos = [c["nombre"] if c["nombre"] == c["expresion"] else f"{c['nombre']} ({c['expresion']})" for c in detalle]
            partes.append("Campos: " + ", ".join(campos))
        if v.get("filtros"):
            partes.append("Filtros: " + "; ".join(v["filtros"]))
        semaforos = sorted({r["campo"] for r in v.get("formato_condicional") or []})
        if semaforos:
            partes.append("Con semáforo en " + _lista_es(semaforos))
        if v.get("oculto"):
            partes.append("Visual oculto")
        secciones["Visuales"].agregar(nombre, ". ".join(partes) or POR_CONFIRMAR)
        for r in v.get("formato_condicional") or []:
            reglas_semaforo.append((r, nombre))
    if segmentaciones:
        secciones["Visuales"].agregar("Segmentaciones", "Filtran la página por " + _lista_es(list(dict.fromkeys(segmentaciones))))
    if botones:
        texto = _lista_es(list(dict.fromkeys(botones)))
        secciones["Visuales"].agregar("Botones de navegación", texto[:1].upper() + texto[1:])

    # Reglas de negocio: un semáforo por campo y rangos (se juntan los visuales que lo repiten).
    agrupados: dict[tuple, list] = {}
    for r, visual in reglas_semaforo:
        texto = _texto_semaforo(r)
        if not texto:
            continue
        agrupados.setdefault((r["campo"], texto), [r, []])[1].append(visual)
    for (campo, texto), (regla, visuales) in agrupados.items():
        secciones["Reglas de negocio"].agregar(
            f"Semáforo {campo}",
            f"{texto}. Unidad por confirmar. Se aplica en {_lista_es(list(dict.fromkeys(visuales)))}")
        if regla["tipo"] == "reglas":
            huecos = _huecos(regla["casos"])
            if huecos:
                secciones["Observaciones"].agregar(
                    f"Huecos en el semáforo {campo}",
                    f"Los valores {_lista_es(huecos)} quedan sin color. Por confirmar si es intencional")
    for f in pagina.get("filtros") or []:
        secciones["Reglas de negocio"].agregar("Filtro de página", f)

    bloque, motivo = _bloque_pagina(pagina, tablas)
    secciones["Observaciones"].agregar(
        "Bloque deducido", f"Se asignó el bloque {bloque} según {motivo}. Por confirmar")
    if duplicada:
        secciones["Observaciones"].agregar(
            "Nombre repetido",
            f"En Power BI hay otra página llamada {pagina['nombre']}; esta es la de id {pagina['id']}")
    secciones["Historial de cambios"].agregar(f"{fecha} · v1", "Borrador generado automáticamente a partir del PBIP")

    estado = "Página visible del informe" if pagina.get("visible") else "Página oculta en el informe"
    if llegadas:
        estado += f"; se llega desde {_lista_es(llegadas)}"
    if pagina.get("obtener_detalles"):
        estado += f"; es página de obtener detalles por {_lista_es(pagina['obtener_detalles'])}"
    proposito = f"{POR_CONFIRMAR} {estado}."

    meta = {
        "tablero": tablero,
        "pagina": nombre_doc,
        "nombre_funcional": "Por confirmar",
        "bloque": bloque,
        "tablas": usadas,
        "actualizado": fecha,
        "version": 1,
        "id_pagina": pagina["id"],
    }
    return _documento(meta, nombre_doc, proposito, secciones)


def _general_md(hechos: dict, tablero: str, fecha: str) -> str:
    tablas = hechos.get("tablas") or {}
    secciones = {s: _Seccion() for s in F.SECCIONES_GENERAL if s != F.SECCION_TEXTO}
    for t, datos in sorted(tablas.items()):
        secciones["Fuentes de datos"].agregar(t, _descripcion_tabla(t, datos))
    for m, dax in (hechos.get("medidas") or {}).items():
        secciones["Definiciones"].agregar(m, f"Por confirmar. Medida DAX: {_corto(dax, 200)}" if dax else
                                          "Por confirmar. Medida del modelo; su DAX no está disponible en el archivo")
    if hechos.get("modelo_disponible") is False:
        secciones["Observaciones"].agregar(
            "Modelo no disponible",
            "El archivo no trae el modelo semántico en texto (TMDL); fuentes, modos, SQL y DAX quedan por confirmar")
    if hechos.get("relaciones"):
        secciones["Reglas de negocio"].agregar("Relaciones del modelo", "; ".join(hechos["relaciones"]))
    for f in hechos.get("filtros_reporte") or []:
        secciones["Reglas de negocio"].agregar("Filtro de todo el informe", f)
    conteo = Counter(p["nombre"] for p in hechos.get("paginas") or [])
    for nombre, n in conteo.items():
        if n > 1:
            secciones["Observaciones"].agregar(
                f"Páginas repetidas {nombre}",
                f"Hay {n} páginas llamadas {nombre}; la documentación las distingue con un sufijo numérico")
    secciones["Historial de cambios"].agregar(f"{fecha} · v1", "Borrador generado automáticamente a partir del PBIP")

    paginas = hechos.get("paginas") or []
    visibles = [p["nombre"] for p in paginas if p.get("visible")]
    proposito = (f"{POR_CONFIRMAR} El tablero tiene {len(paginas)} páginas y {len(tablas)} tablas. "
                 + (f"Páginas visibles: {_lista_es(visibles)}; las demás están ocultas y se recorren con botones."
                    if visibles else "Todas las páginas están ocultas."))
    meta = {
        "tablero": tablero,
        "pagina": "GENERAL",
        "nombre_funcional": "Por confirmar",
        "bloque": "General",
        "tablas": sorted(tablas),
        "actualizado": fecha,
        "version": 1,
    }
    return _documento(meta, "GENERAL", proposito, secciones)


def esqueleto(ruta_pbip, tablero, source_group) -> dict:
    """Borradores .md (formato estándar) del tablero: `_general.md` y un archivo por
    página. Lo que se deduce del PBIP queda escrito; lo que requiere redacción humana
    queda marcado «Por confirmar.». `source_group` solo se usa para ubicar la carpeta
    destino del lado de quien llama (data/raw/<source_group>/md/)."""
    hechos = extraer_hechos(ruta_pbip)
    tablero = tablero or hechos.get("tablero") or source_group
    fecha = date.today().isoformat()
    paginas = hechos.get("paginas") or []

    llegadas: dict[str, list[str]] = {}
    for p in paginas:
        for v in p["visuales"]:
            if v.get("destino_id") and v["destino_id"] != p["id"]:
                llegadas.setdefault(v["destino_id"], [])
                if p["nombre"] not in llegadas[v["destino_id"]]:
                    llegadas[v["destino_id"]].append(p["nombre"])

    conteo = Counter(p["nombre"] for p in paginas)
    vistos: Counter = Counter()
    archivos = {ARCHIVO_GENERAL: _general_md(hechos, tablero, fecha)}
    for p in paginas:
        vistos[p["nombre"]] += 1
        nombre_doc = p["nombre"] if vistos[p["nombre"]] == 1 else f"{p['nombre']} ({vistos[p['nombre']]})"
        archivo = slug(nombre_doc) + ".md"
        archivos[archivo] = _pagina_md(p, hechos, tablero, nombre_doc, llegadas.get(p["id"], []),
                                       conteo[p["nombre"]] > 1, fecha)
    return archivos
