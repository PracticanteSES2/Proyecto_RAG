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
    "grupo": "Grupo de visuales",
}
DECORATIVOS = {"shape", "basicShape", "image"}
SEGMENTACIONES = {"slicer", "advancedSlicerVisual"}
TABLAS_AUTOMATICAS = ("LocalDateTable_", "DateTableTemplate_")
OCULTA = "HiddenInViewMode"
MODOS = {"directquery": "DirectQuery", "import": "Import", "dual": "Dual", "push": "Push"}

# Un límite superior así de grande en una regla de color es un centinela («o más»).
CENTINELA = 999


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _leer_json(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8-sig"))


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
    if "HierarchyLevel" in campo:
        jer = (campo["HierarchyLevel"].get("Expression") or {}).get("Hierarchy") or {}
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
                if not isinstance(expr, dict) or not ({"Conditional", "FillRule"} & set(expr)):
                    continue
                regla = {"objeto": clave, "propiedad": {"backColor": "fondo", "fontColor": "texto"}.get(propiedad, propiedad)}
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
        for caso in r["casos"]:
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
    if not v:
        grupo = datos.get("visualGroup") or {}
        return {"id": datos.get("name"), "tipo": "grupo", "titulo": grupo.get("displayName"), "campos": [],
                "campos_detalle": [], "filtros": [], "semaforo": [], "formato_condicional": [], "texto": None,
                "destino": None, "destino_id": None, "accion": None, "tablas": [], "oculto": bool(datos.get("isHidden"))}
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

    titulo = None
    for t in vco.get("title") or []:
        valor = _valor_propiedad((t.get("properties") or {}).get("text"))
        if valor:
            titulo = str(valor).strip()

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
            destino_id = destino_id or _valor_propiedad(props.get("webUrl"))

    filtros, _, tablas_filtro = _filtros(datos.get("filterConfig"))
    reglas = _formato_condicional(objetos, proyecciones)
    tablas = {p["base"][0] for p in proyecciones if p.get("base")} | tablas_filtro
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


def _paginas(lector, referencias: set | None = None) -> tuple[list[dict], list[str]]:
    orden = list((lector.json("pages/pages.json") or {}).get("pageOrder") or [])
    existentes = [p for p in lector.subcarpetas("pages") if lector.json(f"pages/{p}/page.json") is not None]
    orden = [p for p in orden if p in existentes] + [p for p in existentes if p not in orden]
    referencias = referencias if referencias is not None else set()

    paginas = []
    for i, pid in enumerate(orden, start=1):
        datos = lector.json(f"pages/{pid}/page.json")
        filtros, detalles, _ = _filtros(datos.get("filterConfig"))
        _referencias_visual(datos, referencias)
        visuales = []
        for vid in lector.subcarpetas(f"pages/{pid}/visuals"):
            vd = lector.json(f"pages/{pid}/visuals/{vid}/visual.json")
            if vd is None:
                continue
            _referencias_visual(vd, referencias)
            pos = vd.get("position") or {}
            visuales.append((round(float(pos.get("y", 0)) / 10), float(pos.get("x", 0)), _visual(vd)))
        visuales.sort(key=lambda t: (t[0], t[1], t[2]["id"] or ""))
        paginas.append({
            "id": datos.get("name") or pid,
            "nombre": datos.get("displayName") or pid,
            "visible": datos.get("visibility") != OCULTA,
            "orden": i,
            "filtros": filtros,
            "obtener_detalles": detalles,
            "visuales": [t[2] for t in visuales],
        })

    nombres = {p["id"]: p["nombre"] for p in paginas}
    for p in paginas:
        for v in p["visuales"]:
            if v["destino_id"] in nombres:
                v["destino"] = nombres[v["destino_id"]]
            elif v["accion"] == "Back":
                v["destino"] = "página anterior"

    reporte = lector.json("report.json") or {}
    filtros_reporte, _, _ = _filtros(reporte.get("filterConfig"))
    _referencias_visual(reporte, referencias)
    return paginas, filtros_reporte


# ---------------------------------------------------------------------------
# Modelo semántico (TMDL)
# ---------------------------------------------------------------------------

def _nivel(linea: str) -> int:
    tabs = len(linea) - len(linea.lstrip("\t"))
    if tabs:
        return tabs
    return (len(linea) - len(linea.lstrip(" "))) // 4


def _separar_nombre(resto: str) -> tuple[str, str | None]:
    """«'EN ESPERA' = expr» -> ("EN ESPERA", "expr"); «X» -> ("X", None)."""
    resto = resto.strip()
    if resto.startswith("'"):
        i, buf = 1, []
        while i < len(resto):
            if resto[i] == "'":
                if i + 1 < len(resto) and resto[i + 1] == "'":
                    buf.append("'")
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


def _expresion(lineas: list[str], j: int, primera: str, nivel_minimo: int) -> tuple[str, int]:
    """Expresión que sigue a «= ...»: en la misma línea, en líneas más indentadas
    o entre ``` ... ```. Devuelve (texto, índice de la siguiente línea)."""
    if primera.startswith("```"):
        buf = []
        while j < len(lineas) and not lineas[j].strip().startswith("```"):
            buf.append(lineas[j])
            j += 1
        return _desindentar(buf), j + 1
    if primera:
        return primera, j
    buf = []
    while j < len(lineas) and (not lineas[j].strip() or _nivel(lineas[j]) >= nivel_minimo):
        buf.append(lineas[j])
        j += 1
    while buf and not buf[-1].strip():
        buf.pop()
    return _desindentar(buf), j


def _parsear_tabla_tmdl(texto: str) -> dict:
    lineas = texto.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    tabla = {"nombre": None, "columnas": [], "calculadas": {}, "medidas": {}, "particiones": []}
    i = 0
    while i < len(lineas):
        linea = lineas[i]
        contenido = linea.strip()
        nivel = _nivel(linea)
        if not contenido:
            i += 1
            continue
        palabra, _, resto = contenido.partition(" ")
        if nivel == 0 and palabra == "table":
            tabla["nombre"], _ = _separar_nombre(resto)
            i += 1
            continue
        if nivel == 1 and palabra in ("column", "measure", "partition"):
            nombre, expr = _separar_nombre(resto)
            i += 1
            if expr is not None:
                expr, i = _expresion(lineas, i, expr, 3)
            props = {}
            while i < len(lineas) and (not lineas[i].strip() or _nivel(lineas[i]) >= 2):
                prop = lineas[i]
                if not prop.strip() or _nivel(prop) != 2:
                    i += 1
                    continue
                pc = prop.strip()
                m = re.match(r"^([A-Za-z]+)\s*([:=])\s*(.*)$", pc)
                i += 1
                if not m:
                    continue
                clave, signo, valor = m.groups()
                if signo == "=":
                    valor, i = _expresion(lineas, i, valor.strip(), 3)
                props[clave] = valor.strip()
            if palabra == "column":
                tabla["columnas"].append(nombre)
                if expr:
                    tabla["calculadas"][nombre] = expr
            elif palabra == "measure":
                tabla["medidas"][nombre] = expr or ""
            else:
                tipo = (expr or "").strip()
                tabla["particiones"].append({"nombre": nombre, "tipo": tipo, "modo": props.get("mode", "import"),
                                             "fuente": props.get("source", "")})
            continue
        i += 1
    return tabla


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


def _analizar_m(fuente: str) -> dict:
    """Origen, servidor, base y SQL nativo de una consulta Power Query."""
    info = {"origen": None, "servidor": None, "base_datos": None, "sql": None}
    m = re.search(r"\b([A-Z][A-Za-z]*\.[A-Z][A-Za-z]*)\s*\(", fuente)
    if m:
        info["origen"] = m.group(1)
    m = re.search(r"Sql\.Databases?\s*\(", fuente)
    if m:
        info["origen"] = "Sql.Database"
        servidor, fin = _siguiente_cadena(fuente, m.end())
        info["servidor"] = servidor
        resto = fuente[fin:]
        m2 = re.match(r"\s*,\s*\"", resto)
        if m2:
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
        info["sql"] = info["sql"].strip()
    return info


def _modelo(modelo: Path | None) -> tuple[dict, dict, list[str]]:
    tablas, medidas, relaciones = {}, {}, []
    if modelo is None:
        return tablas, medidas, relaciones
    definicion = modelo / "definition"
    for archivo in sorted((definicion / "tables").glob("*.tmdl")):
        t = _parsear_tabla_tmdl(archivo.read_text(encoding="utf-8-sig"))
        nombre = t["nombre"] or archivo.stem
        if _es_automatica(nombre):
            continue
        part = t["particiones"][0] if t["particiones"] else {"tipo": "", "modo": "import", "fuente": ""}
        datos = {
            "modo": MODOS.get(str(part["modo"]).lower(), part["modo"]),
            "origen": None, "servidor": None, "base_datos": None, "sql": None, "m": None, "dax": None,
            "columnas": t["columnas"],
            "calculadas": t["calculadas"],
        }
        if part["tipo"] == "calculated":
            datos["origen"] = "DAX"
            datos["dax"] = part["fuente"] or None
        elif part["fuente"]:
            info = _analizar_m(part["fuente"])
            datos.update(info)
            if info["sql"] is None:
                datos["m"] = part["fuente"]
        tablas[nombre] = datos
        for m_nombre, dax in t["medidas"].items():
            medidas[f"{nombre}[{m_nombre}]"] = dax

    archivo_rel = definicion / "relationships.tmdl"
    if archivo_rel.exists():
        for bloque in re.split(r"(?m)^relationship\s", archivo_rel.read_text(encoding="utf-8-sig"))[1:]:
            props = dict(re.findall(r"(?m)^\s+(\w+)\s*:\s*(.+?)\s*$", bloque))
            origen, destino = _columna_rel(props.get("fromColumn", "")), _columna_rel(props.get("toColumn", ""))
            if not origen or not destino or _es_automatica(origen[0]) or _es_automatica(destino[0]):
                continue
            texto = f"{origen[0]}[{origen[1]}] -> {destino[0]}[{destino[1]}]"
            if props.get("isActive", "").lower() == "false":
                texto += " (inactiva)"
            if props.get("crossFilteringBehavior", "").lower() == "bothdirections":
                texto += " (filtro en ambos sentidos)"
            relaciones.append(texto)
    return tablas, medidas, sorted(relaciones)


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
    if ruta.is_file() and ruta.suffix.lower() == ".pbix":
        with zipfile.ZipFile(ruta) as zf:
            lector = _LectorZip(zf)
            if not lector.nombres:
                raise FileNotFoundError(f"«{ruta}» no trae el informe en formato PBIR (Report/definition/).")
            paginas, filtros_reporte = _paginas(lector, referencias)
        nombre, modelo = ruta.stem, None
    else:
        nombre, informe, modelo = _ubicar(ruta)
        paginas, filtros_reporte = _paginas(_LectorCarpeta(informe / "definition"), referencias)
    if modelo is not None:
        tablas, medidas, relaciones = _modelo(modelo)
    else:
        (tablas, medidas), relaciones = _tablas_desde_referencias(referencias), []
    return {
        "version_hechos": VERSION_HECHOS,
        "tablero": nombre,
        "modelo_disponible": modelo is not None,
        "paginas": paginas,
        "filtros_reporte": filtros_reporte,
        "tablas": tablas,
        "medidas": medidas,
        "relaciones": relaciones,
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

def _nombre_tipo(tipo: str) -> str:
    return TIPOS_VISUAL.get(tipo, tipo)


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
    if detalle and v.get("tipo") not in SEGMENTACIONES:
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
        if v["tipo"] in SEGMENTACIONES:
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
        if tipo in SEGMENTACIONES:
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
