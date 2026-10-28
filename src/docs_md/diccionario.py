"""
Diccionario de variables de un tablero (`docs_tableros/<grupo>/md/_diccionario.md`).

Qué es cada tabla, medida y columna del modelo, para que el RAG no tenga que
adivinarlo. El esqueleto se genera de forma determinista desde el modelo y el
informe; la redacción de negocio la completa una persona (todo lo que no se
sabe queda «Por confirmar», nunca se inventa).

    from src.docs_md import diccionario
    doc = diccionario.generar_esqueleto("tablero_antibioticos")      # Documento (formato.py)
    archivos = diccionario.generar_esqueleto_archivos("tablero_antibioticos")   # {archivo: Documento}
    diccionario.cobertura("tablero_antibioticos")                    # qué falta documentar
    diccionario.comparar_con_modelo("tablero_antibioticos")          # obsoleto / nuevo

CLI (desde la raíz del proyecto):

    python -m src.docs_md.diccionario cobertura [grupo | --todos] [--json]
    python -m src.docs_md.diccionario esqueleto <grupo> [--escribir]
    python -m src.docs_md.diccionario comparar <grupo>

Fuentes (solo lectura): `data/model_metadata/<modelo>/{tables,columns,measures,relationships}.csv`
(formato INFO.VIEW, separador «;») y el PBIP en `tableros/<carpeta>/` (con
`pbip.extraer_hechos`, nunca `.pbi/cache.abf`). La raíz que contiene `data/` y
`tableros/` es `project_root`, si no la variable `DOCS_MD_DATA_ROOT`, si no la
raíz de este repositorio (útil cuando se trabaja desde un worktree).

`--escribir` nunca pisa texto ya redactado: conserva las entradas existentes,
agrega las nuevas y marca como obsoletas las que ya no están en el modelo.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

from . import formato as F
from . import pbip, repositorio as R
from .uso import texto_uso, uso_de_campos

POR_CONFIRMAR = "Por confirmar"
MARCA_OBSOLETA = "Obsoleta: ya no existe en el modelo."

# Por encima de estos tamaños solo se detalla lo usado en visuales, lo descrito y
# lo que alimenta a lo usado; el resto se resume por tabla en «Observaciones».
MAX_MEDIDAS_COMPLETAS = 250
MAX_COLUMNAS_CALCULADAS_COMPLETAS = 150
MAX_TABLAS_COMPLETAS = 80
MAX_NOMBRES_RESUMEN = 12
MAX_RESUMENES = 60
# Si hay más columnas que esto, van a `_diccionario_columnas.md`.
MAX_COLUMNAS_EN_PRINCIPAL = 120

PAGINA_COLUMNAS = f"{F.PAGINA_DICCIONARIO} COLUMNAS"

TIPOS_DATO = {
    "integer": "entero", "int64": "entero", "whole": "entero",
    "string": "texto", "text": "texto",
    "number": "decimal", "double": "decimal", "decimal": "decimal", "float": "decimal",
    "datetime": "fecha", "date": "fecha", "time": "hora",
    "boolean": "lógico", "bool": "lógico",
    "currency": "moneda", "variant": "variante", "binary": "binario",
}

_SECCIONES_DOC = ("Medidas", "Columnas calculadas", "Columnas clave", "Tablas", "Relaciones")
_csv_listo = False


# ---------------------------------------------------------------------------
# Ubicación de las fuentes
# ---------------------------------------------------------------------------

def raiz_datos(project_root: str | Path | None = None) -> Path:
    if project_root is not None:
        return Path(project_root)
    env = os.getenv("DOCS_MD_DATA_ROOT", "").strip()
    return Path(env) if env else R.PROJECT_ROOT


def _leer_manifest(source_group: str, project_root: Path, raiz_docs) -> dict:
    for base in (R.raiz_documentos(raiz_docs), project_root / "docs_tableros", project_root / "data" / "raw"):
        ruta = Path(base) / source_group / "manifest.json"
        if ruta.exists():
            try:
                return json.loads(ruta.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError):
                continue
    return {}


def carpeta_metadata(source_group: str, project_root: Path, manifest: dict) -> Path | None:
    base = project_root / "data" / "model_metadata"
    for nombre in (manifest.get("semantic_model_key"), source_group,
                   source_group[len("tablero_"):] if source_group.startswith("tablero_") else None):
        if nombre and (base / nombre / "measures.csv").exists():
            return base / nombre
    return None


def carpeta_pbip(source_group: str, project_root: Path, manifest: dict) -> Path | None:
    """Carpeta de `tableros/` cuyo nombre (en slug) coincide con el grupo, el
    informe o el modelo del manifest."""
    base = project_root / "tableros"
    if not base.is_dir():
        return None
    claves = {R.slug(x) for x in (source_group, manifest.get("report"), manifest.get("semantic_model"),
                                  manifest.get("semantic_model_key")) if x}
    claves |= {c[len("tablero_"):] for c in set(claves) if c.startswith("tablero_")}
    for carpeta in sorted(p for p in base.iterdir() if p.is_dir()):
        if R.slug(carpeta.name) in claves and any(carpeta.glob("*.Report")):
            return carpeta
    return None


# ---------------------------------------------------------------------------
# Modelo (CSV de INFO.VIEW + hechos del PBIP)
# ---------------------------------------------------------------------------

def _leer_csv(ruta: Path) -> list[dict]:
    global _csv_listo
    if not _csv_listo:
        csv.field_size_limit(2**31 - 1)
        _csv_listo = True
    if not ruta.exists():
        return []
    with open(ruta, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh, delimiter=";"))


def _bool(valor) -> bool:
    return str(valor or "").strip().lower() in ("true", "1", "si", "sí")


def _tipo_dato(valor: str) -> str:
    valor = str(valor or "").strip()
    return TIPOS_DATO.get(valor.lower(), valor.lower())


def dax_en_una_linea(dax: str) -> str:
    """DAX literal en una sola línea: sin comentarios (// y --, fuera de cadenas),
    espacios simples y sin comillas invertidas (reservadas para delimitarlo)."""
    lineas = []
    for linea in str(dax or "").replace("\r", "").split("\n"):
        en_cadena, corte = False, len(linea)
        for i, c in enumerate(linea):
            if c == '"':
                en_cadena = not en_cadena
            elif not en_cadena and (linea[i:i + 2] in ("//", "--")):
                corte = i
                break
        lineas.append(linea[:corte])
    texto = re.sub(r"/\*.*?\*/", " ", " ".join(lineas), flags=re.S)
    return re.sub(r"\s+", " ", texto.replace("`", "'")).strip()


def _modelo_desde_csv(carpeta: Path) -> dict:
    modelo = {"tablas": {}, "medidas": {}, "columnas": {}, "relaciones": []}
    for t in _leer_csv(carpeta / "tables.csv"):
        nombre = t.get("Name", "")
        if not nombre or pbip._es_automatica(nombre):
            continue
        modelo["tablas"][nombre] = {
            "descripcion": (t.get("Description") or "").strip(), "oculta": _bool(t.get("IsHidden")),
            "modo": t.get("StorageMode") or None, "dax": (t.get("Expression") or "").strip() or None,
        }
    for c in _leer_csv(carpeta / "columns.csv"):
        tabla, nombre = c.get("Table", ""), c.get("Name", "")
        if not tabla or not nombre or pbip._es_automatica(tabla) or c.get("Type") == "RowNumber":
            continue
        modelo["columnas"][(tabla, nombre)] = {
            "tipo_dato": _tipo_dato(c.get("DataType")), "descripcion": (c.get("Description") or "").strip(),
            "oculta": _bool(c.get("IsHidden")), "calculada": c.get("Type") == "Calculated",
            "dax": (c.get("Expression") or "").strip() or None,
        }
    for m in _leer_csv(carpeta / "measures.csv"):
        nombre, tabla = m.get("Name", ""), m.get("Table", "")
        if not nombre or pbip._es_automatica(tabla):
            continue
        modelo["medidas"][nombre] = {
            "tabla": tabla, "descripcion": (m.get("Description") or "").strip(),
            "dax": (m.get("Expression") or "").strip() or None, "formato": (m.get("FormatString") or "").strip(),
            "tipo_dato": _tipo_dato(m.get("DataType")), "oculta": _bool(m.get("IsHidden")),
            "carpeta": (m.get("DisplayFolder") or "").strip(),
        }
    for r in _leer_csv(carpeta / "relationships.csv"):
        if pbip._es_automatica(r.get("FromTable")) or pbip._es_automatica(r.get("ToTable")):
            continue
        modelo["relaciones"].append({
            "desde": (r.get("FromTable", ""), r.get("FromColumn", "")), "hacia": (r.get("ToTable", ""), r.get("ToColumn", "")),
            "activa": _bool(r.get("IsActive")), "ambos": (r.get("CrossFilteringBehavior") or "").lower().startswith("both"),
            "card_desde": r.get("FromCardinality") or "", "card_hacia": r.get("ToCardinality") or "",
        })
    return modelo


_REL_HECHOS = re.compile(r"^(?P<t1>.+?)\[(?P<c1>[^\]]+)\] -> (?P<t2>.+?)\[(?P<c2>[^\]]+)\](?P<resto>.*)$")


def _modelo_desde_hechos(hechos: dict) -> dict:
    modelo = {"tablas": {}, "medidas": {}, "columnas": {}, "relaciones": []}
    for nombre, t in (hechos.get("tablas") or {}).items():
        modelo["tablas"][nombre] = {"descripcion": "", "oculta": False, "modo": t.get("modo"), "dax": t.get("dax")}
        calculadas = t.get("calculadas") or {}
        for col in t.get("columnas") or []:
            modelo["columnas"][(nombre, col)] = {"tipo_dato": "", "descripcion": "", "oculta": False,
                                                 "calculada": col in calculadas, "dax": calculadas.get(col)}
        for col, dax in calculadas.items():
            modelo["columnas"].setdefault((nombre, col), {"tipo_dato": "", "descripcion": "", "oculta": False,
                                                          "calculada": True, "dax": dax})
    for clave, dax in (hechos.get("medidas") or {}).items():
        tabla, _, resto = clave.partition("[")
        modelo["medidas"][resto.rstrip("]")] = {"tabla": tabla, "descripcion": "", "dax": dax, "formato": "",
                                               "tipo_dato": "", "oculta": False, "carpeta": ""}
    for texto in hechos.get("relaciones") or []:
        m = _REL_HECHOS.match(texto)
        if m:
            modelo["relaciones"].append({
                "desde": (m["t1"], m["c1"]), "hacia": (m["t2"], m["c2"]),
                "activa": "(inactiva)" not in m["resto"], "ambos": "ambos sentidos" in m["resto"],
                "card_desde": "", "card_hacia": "",
            })
    return modelo


def cargar_modelo(source_group: str, project_root=None, *, raiz_docs=None, hechos=None) -> dict:
    """Modelo unificado del grupo: {tablero, tablas, medidas, columnas, relaciones,
    hechos, fuentes}. Lanza FileNotFoundError si no hay ni metadatos ni PBIP."""
    raiz = raiz_datos(project_root)
    manifest = _leer_manifest(source_group, raiz, raiz_docs)
    fuentes = []
    carpeta = carpeta_metadata(source_group, raiz, manifest)
    if hechos is None:
        ruta_pbip = carpeta_pbip(source_group, raiz, manifest)
        if ruta_pbip is not None:
            try:
                hechos = pbip.extraer_hechos(ruta_pbip)
                fuentes.append(f"PBIP {ruta_pbip.name}")
            except (OSError, ValueError, FileNotFoundError):
                hechos = None
    elif hechos:
        fuentes.append("hechos del PBIP")
    if carpeta is not None:
        modelo = _modelo_desde_csv(carpeta)
        fuentes.insert(0, f"data/model_metadata/{carpeta.name}")
    elif hechos is not None and hechos.get("modelo_disponible", True):
        modelo = _modelo_desde_hechos(hechos)
    else:
        raise FileNotFoundError(
            f"No hay metadatos del modelo de «{source_group}» (data/model_metadata) ni PBIP en {raiz}.")
    modelo["tablero"] = manifest.get("report") or (hechos or {}).get("tablero") or source_group
    modelo["modelo_nombre"] = manifest.get("semantic_model") or modelo["tablero"]
    modelo["hechos"] = hechos
    modelo["fuentes"] = fuentes
    if hechos is not None:  # origen de las tablas y respaldo de DAX
        for nombre, t in (hechos.get("tablas") or {}).items():
            if nombre in modelo["tablas"]:
                modelo["tablas"][nombre]["origen"] = t
        for clave, dax in (hechos.get("medidas") or {}).items():
            nombre = clave.partition("[")[2].rstrip("]")
            if nombre in modelo["medidas"] and not modelo["medidas"][nombre].get("dax"):
                modelo["medidas"][nombre]["dax"] = dax
        for (tabla, col), c in modelo["columnas"].items():
            calc = ((hechos.get("tablas") or {}).get(tabla) or {}).get("calculadas") or {}
            if c["calculada"] and not c.get("dax") and col in calc:
                c["dax"] = calc[col]
    return modelo


# ---------------------------------------------------------------------------
# Relaciones entre campos (dependencias en DAX)
# ---------------------------------------------------------------------------

def _dependencias(modelo: dict) -> tuple[dict[str, set], dict[tuple, set]]:
    """({medida: {medidas que la usan}}, {(tabla, col): {medidas que la usan}})."""
    nombres_medidas = {n: n for n in modelo["medidas"]}
    tablas = sorted(modelo["tablas"], key=len, reverse=True)
    patron_col = re.compile(r"(?<![\w.])'?(" + "|".join(re.escape(t) for t in tablas) + r")'?\[([^\[\]]+)\]") if tablas else None
    patron_med = re.compile(r"(?<![\w'\]])\[([^\[\]]+)\]")
    medida_usada_por: dict[str, set] = {}
    col_usada_por: dict[tuple, set] = {}
    for nombre, m in modelo["medidas"].items():
        dax = m.get("dax") or ""
        sin_cols = dax
        if patron_col:
            for mm in patron_col.finditer(dax):
                col_usada_por.setdefault((mm.group(1), mm.group(2)), set()).add(nombre)
            sin_cols = patron_col.sub(" ", dax)
        for mm in patron_med.finditer(sin_cols):
            ref = mm.group(1)
            if ref in nombres_medidas and ref != nombre:
                medida_usada_por.setdefault(ref, set()).add(nombre)
    return medida_usada_por, col_usada_por


# ---------------------------------------------------------------------------
# Conocimiento ya redactado en la documentación .md del grupo
# ---------------------------------------------------------------------------

def _documentos_md(source_group: str, raiz_docs=None) -> tuple[list[tuple[str, F.Documento]], list[tuple[str, F.Documento]]]:
    """([(archivo, doc) de páginas y general], [(archivo, doc) del diccionario])."""
    carpeta = R.carpeta_md(source_group, raiz_docs)
    paginas, diccionario = [], []
    for archivo in sorted(carpeta.glob("*.md")) if carpeta.is_dir() else []:
        try:
            doc = F.parsear(archivo.read_text(encoding="utf-8"))
        except (OSError, F.ErrorFormato):
            continue
        (diccionario if R.es_archivo_diccionario(archivo.name) else paginas).append((archivo.name, doc))
    return paginas, diccionario


def _primera_frase(texto: str, maximo: int = 260) -> str:
    texto = re.sub(r"\s+", " ", texto or "").strip()
    if len(texto) > maximo:
        corte = texto.rfind(". ", 0, maximo)
        if corte > 40:
            return texto[: corte + 1]
        corte = texto.rfind(" ", 0, maximo - 1)
        texto = texto[: corte if corte > 40 else maximo - 1].rstrip(" ,;:") + "…"
    return texto


def _quitar_punto(texto: str) -> str:
    return re.sub(r"[\s.]+$", "", texto or "")


def conocimiento_md(paginas: list[tuple[str, F.Documento]], modelo: dict) -> dict:
    """Descripciones ya escritas en las páginas .md: {medidas, tablas, columnas}
    con claves normalizadas. Solo se aceptan nombres que existen en el modelo."""
    medidas_norm = {F.normalizar_nombre(n): n for n in modelo["medidas"]}
    tablas_norm = {F.normalizar_nombre(n): n for n in modelo["tablas"]}
    res = {"medidas": {}, "tablas": {}, "columnas": {}, "unidades": {}}
    patron_medida = re.compile(r"\bMedidas?\s+\[?([^\]=\n]+?)\]?\s*=")
    for _, doc in paginas:
        for e in doc.entradas("Fuentes de datos"):
            tabla = tablas_norm.get(F.normalizar_nombre(e.nombre))
            if tabla and tabla not in res["tablas"]:
                res["tablas"][tabla] = _primera_frase(e.texto)
        for seccion in ("Indicadores", "Visuales", "Definiciones", "Reglas de negocio"):
            for e in doc.entradas(seccion):
                candidatas = [m.group(1).strip() for m in patron_medida.finditer(e.texto)]
                candidatas += [m.group(1) for m in re.finditer(r"(?<![\w\]'])\[([^\[\]]{2,80})\]", e.texto)]
                for cand in candidatas:
                    medida = medidas_norm.get(F.normalizar_nombre(cand))
                    if not medida or medida in res["medidas"]:
                        continue
                    previo = re.split(r"\bMedidas?\b\s|\[", e.texto, maxsplit=1)[0]
                    previo = _quitar_punto(previo)
                    nombre = _quitar_punto(e.nombre)
                    res["medidas"][medida] = _primera_frase(f"{nombre}. {previo}." if previo else f"{nombre}.")
                    unidad = re.search(r"Unidad:\s*([^.]+)\.", e.texto)
                    if unidad:
                        res["unidades"][medida] = unidad.group(1).strip()
                if seccion in ("Definiciones", "Reglas de negocio"):
                    for tabla, col in modelo["columnas"]:
                        if f"{tabla}[{col}]" in e.texto or F.normalizar_nombre(e.nombre) == F.normalizar_nombre(col):
                            res["columnas"].setdefault((tabla, col), _primera_frase(e.texto, 200))
    return res


# ---------------------------------------------------------------------------
# Entradas del diccionario
# ---------------------------------------------------------------------------

def _texto_final(texto: str) -> str:
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto if texto.endswith((".", "?", "!", ")", "»")) else texto + "."


def _unidad(medida: dict, conocido: str | None) -> str:
    if conocido:
        return conocido
    if "%" in (medida.get("formato") or ""):
        return "porcentaje"
    if medida.get("tipo_dato") == "fecha":
        return "fecha"
    return POR_CONFIRMAR


def _uso_completo(visuales: list[dict] | None, dependientes: set | None, uso_conocido: bool) -> str:
    partes = []
    if visuales:
        partes.append(texto_uso(visuales))
    if dependientes:
        lista = sorted(dependientes)
        partes.append("las medidas " + ", ".join(f"[{d}]" for d in lista[:5]) + (f" y {len(lista) - 5} más" if len(lista) > 5 else ""))
    if partes:
        return "; ".join(partes)
    return "no aparece en visuales ni filtros del informe" if uso_conocido else POR_CONFIRMAR


def _origen_tabla(tabla: dict) -> str:
    modo = tabla.get("modo")
    hecho = tabla.get("origen") or {}
    sufijo = f" ({modo})" if modo else ""
    dax = tabla.get("dax") or hecho.get("dax")
    if dax:
        return f"tabla calculada con DAX `{_corto(dax_en_una_linea(dax), 140)}`{sufijo}"
    sql = hecho.get("sql")
    if sql:
        fuentes = []
        for m in re.finditer(r"\b(?:FROM|JOIN)\s+([A-Za-z0-9_.\[\]\"#]+)", dax_en_una_linea(sql), flags=re.I):
            if m.group(1) not in fuentes:
                fuentes.append(m.group(1))
        base = f" en la base {hecho['base_datos']}" if hecho.get("base_datos") else ""
        lista = f" sobre {', '.join(fuentes[:5])}" if fuentes else ""
        return f"consulta SQL{lista}{base}{sufijo}"
    if hecho.get("m"):
        return f"consulta de Power Query (M){sufijo}"
    if hecho.get("origen"):
        return f"{hecho['origen']}{sufijo}"
    return f"{POR_CONFIRMAR}{sufijo}"


def _corto(texto: str, maximo: int) -> str:
    return texto if len(texto) <= maximo else texto[: maximo - 1].rstrip() + "…"


class _Plan:
    """Entradas deseadas del diccionario y qué se dejó fuera (para resumir)."""

    def __init__(self):
        self.secciones: dict[str, list[F.Entrada]] = {s: [] for s in _SECCIONES_DOC}
        self.observaciones: list[F.Entrada] = []
        self.conteos: dict = {}

    def agregar(self, seccion: str, nombre: str, texto: str, vistos: dict):
        clave = F.normalizar_nombre(nombre)
        if clave in vistos.setdefault(seccion, set()):
            self.observaciones.append(F.Entrada(f"Nombre repetido: {nombre}"[:150],
                                                f"En «{seccion}» hay otro elemento con el mismo nombre sin distinguir tildes ni mayúsculas; solo se documenta el primero."))
            return
        vistos[seccion].add(clave)
        self.secciones[seccion].append(F.Entrada(nombre, _texto_final(texto)))


def construir_plan(modelo: dict, md_paginas=None) -> _Plan:
    hechos = modelo.get("hechos")
    uso_conocido = hechos is not None
    uso = uso_de_campos(hechos) if uso_conocido else {}
    medida_usada_por, col_usada_por = _dependencias(modelo)
    conocido = conocimiento_md(md_paginas or [], modelo)
    plan, vistos = _Plan(), {}

    # --- Medidas -----------------------------------------------------------
    medidas = modelo["medidas"]
    def clase(nombre, m):
        if m.get("oculta"):
            return "oculta"
        if f"[{nombre}]" not in uso and medida_usada_por.get(nombre):
            return "auxiliar"
        return ""
    descrita = lambda n, m: bool(m.get("descripcion") or conocido["medidas"].get(n))
    usada = lambda n: f"[{n}]" in uso
    if len(medidas) <= MAX_MEDIDAS_COMPLETAS:
        elegidas = list(medidas)
    else:
        feed = {d for n in medidas if usada(n) for d in _usadas_por_directo(modelo, n)}
        elegidas = [n for n, m in medidas.items() if usada(n) or descrita(n, m) or n in feed]
        if not uso_conocido:
            elegidas = [n for n, m in medidas.items() if not m.get("oculta")][:MAX_MEDIDAS_COMPLETAS]
    elegidas = sorted(elegidas, key=lambda n: (not usada(n), medidas[n]["tabla"].casefold(), n.casefold()))
    for nombre in elegidas:
        m = medidas[nombre]
        desc = m.get("descripcion") or conocido["medidas"].get(nombre) or POR_CONFIRMAR
        partes = [f"{_quitar_punto(desc)}.", f"Unidad: {_unidad(m, conocido['unidades'].get(nombre))}."]
        partes.append(f"Tabla: {m['tabla']}.")
        cl = clase(nombre, m)
        if cl:
            partes.append(f"Clase: {cl}.")
        dax = dax_en_una_linea(m.get("dax") or "")
        partes.append(f"Cálculo: `{dax}`." if dax else f"Cálculo: {POR_CONFIRMAR}.")
        partes.append(f"Se usa en: {_uso_completo(uso.get(f'[{nombre}]'), medida_usada_por.get(nombre), uso_conocido)}.")
        plan.agregar("Medidas", f"[{nombre}]", " ".join(partes), vistos)
    omitidas = [n for n in medidas if n not in set(elegidas)]
    plan.conteos["medidas_omitidas"] = len(omitidas)
    _resumir_omitidas(plan, "Medidas", omitidas, lambda n: medidas[n]["tabla"], "medidas sin uso en visuales ni descripción")

    # --- Columnas calculadas ------------------------------------------------
    calculadas = [(k, c) for k, c in modelo["columnas"].items() if c["calculada"] and c.get("dax")]
    usadas_col = lambda k: f"{k[0]}[{k[1]}]" in uso
    describ_col = lambda k, c: bool(c.get("descripcion") or conocido["columnas"].get(k))
    if len(calculadas) <= MAX_COLUMNAS_CALCULADAS_COMPLETAS or not uso_conocido:
        sel = calculadas if len(calculadas) <= MAX_COLUMNAS_CALCULADAS_COMPLETAS else calculadas[:MAX_COLUMNAS_CALCULADAS_COMPLETAS]
    else:
        sel = [(k, c) for k, c in calculadas if usadas_col(k) or describ_col(k, c)]
    sel = sorted(sel, key=lambda kc: (not usadas_col(kc[0]), kc[0][0].casefold(), kc[0][1].casefold()))
    for (tabla, col), c in sel:
        desc = c.get("descripcion") or conocido["columnas"].get((tabla, col)) or POR_CONFIRMAR
        partes = [f"{_quitar_punto(desc)}."]
        if c.get("tipo_dato"):
            partes.append(f"Tipo: {c['tipo_dato']}.")
        partes.append(f"Cálculo: `{dax_en_una_linea(c['dax'])}`.")
        deps = col_usada_por.get((tabla, col))
        partes.append(f"Se usa en: {_uso_completo(uso.get(f'{tabla}[{col}]'), deps, uso_conocido)}.")
        plan.agregar("Columnas calculadas", f"{tabla}[{col}]", " ".join(partes), vistos)
    elegidas_cc = {k for k, _ in sel}
    omitidas_cc = [k for k, _ in calculadas if k not in elegidas_cc]
    _resumir_omitidas(plan, "Columnas calculadas", omitidas_cc, lambda k: k[0], "columnas calculadas sin uso en visuales ni descripción",
                      nombre=lambda k: k[1])

    # --- Columnas clave (no calculadas, usadas en visuales o filtros) --------
    clave = []
    for k, c in modelo["columnas"].items():
        if (c["calculada"] and c.get("dax")) or not usadas_col(k):
            continue
        clave.append((k, c))
    for (tabla, col), c in sorted(clave, key=lambda kc: (kc[0][0].casefold(), kc[0][1].casefold())):
        desc = c.get("descripcion") or conocido["columnas"].get((tabla, col)) or POR_CONFIRMAR
        partes = [f"{_quitar_punto(desc)}."]
        if c.get("tipo_dato"):
            partes.append(f"Tipo: {c['tipo_dato']}.")
        if c.get("tipo_dato") in ("texto", ""):
            partes.append(f"Valores: {POR_CONFIRMAR}.")
        partes.append(f"Se usa en: {_uso_completo(uso.get(f'{tabla}[{col}]'), col_usada_por.get((tabla, col)), uso_conocido)}.")
        plan.agregar("Columnas clave", f"{tabla}[{col}]", " ".join(partes), vistos)

    # --- Tablas ---------------------------------------------------------------
    con_medidas = {m["tabla"] for m in medidas.values()}
    en_relacion = {t for r in modelo["relaciones"] for t in (r["desde"][0], r["hacia"][0])}
    usadas_tabla = {k.partition("[")[0] for k in uso if not k.startswith("[")}
    def relevante(t):
        return (t in usadas_tabla or t in con_medidas or bool(modelo["tablas"][t].get("descripcion"))
                or t in conocido["tablas"])
    todas = list(modelo["tablas"])
    if len(todas) <= MAX_TABLAS_COMPLETAS:
        tablas = todas
    else:
        tablas = [t for t in todas if relevante(t)]
    columnas_por_tabla: dict[str, list[str]] = {}
    for (tabla, col), c in modelo["columnas"].items():
        if not c.get("oculta"):
            columnas_por_tabla.setdefault(tabla, []).append(col)
    for tabla in sorted(tablas, key=str.casefold):
        t = modelo["tablas"][tabla]
        desc = t.get("descripcion") or conocido["tablas"].get(tabla) or POR_CONFIRMAR
        cols = sorted(columnas_por_tabla.get(tabla, []), key=lambda c: (f"{tabla}[{c}]" not in uso, c.casefold()))
        extra = f" y {len(cols) - 8} más" if len(cols) > 8 else ""
        partes = [f"{_quitar_punto(desc)}.", f"Origen: {_origen_tabla(t)}.", f"Granularidad: {POR_CONFIRMAR}."]
        if cols:
            partes.append(f"Columnas principales: {', '.join(cols[:8])}{extra}.")
        plan.agregar("Tablas", tabla, " ".join(partes), vistos)
    resto = [t for t in todas if t not in set(tablas)]
    if resto:
        plan.observaciones.append(F.Entrada(
            "Tablas no detalladas",
            _texto_final(f"{len(resto)} tablas sin medidas, descripción ni uso en visuales no se detallan aquí: "
                         + ", ".join(sorted(resto, key=str.casefold)[:MAX_NOMBRES_RESUMEN]) + (" y otras" if len(resto) > MAX_NOMBRES_RESUMEN else ""))))
    plan.conteos["tablas_omitidas"] = len(resto)

    # --- Relaciones --------------------------------------------------------------
    for r in modelo["relaciones"]:
        (t1, c1), (t2, c2) = r["desde"], r["hacia"]
        cardinalidad = _cardinalidad(r)
        direccion = f"filtro en ambos sentidos entre {t1} y {t2}" if r["ambos"] else f"{t2} filtra a {t1}"
        texto = f"{cardinalidad}, {direccion}, {'activa' if r['activa'] else 'inactiva'}."
        plan.agregar("Relaciones", f"{t1}[{c1}] → {t2}[{c2}]", texto, vistos)

    if not uso_conocido:
        plan.observaciones.append(F.Entrada(
            "Sin informe PBIP", "No se encontró el PBIP del tablero; no se pudo calcular dónde se usa cada campo («Se usa en»)."))
    return plan


def _usadas_por_directo(modelo: dict, nombre: str) -> set[str]:
    """Medidas de las que depende directamente la medida `nombre` (su DAX las cita)."""
    dax = (modelo["medidas"][nombre].get("dax") or "")
    return {ref for ref in re.findall(r"(?<![\w'\]])\[([^\[\]]+)\]", dax) if ref in modelo["medidas"] and ref != nombre}


def _resumir_omitidas(plan: _Plan, seccion: str, omitidas: list, tabla_de, motivo: str, nombre=lambda x: x):
    if not omitidas:
        return
    por_tabla: dict[str, list[str]] = {}
    for item in omitidas:
        por_tabla.setdefault(tabla_de(item), []).append(nombre(item))
    ordenadas = sorted(por_tabla.items(), key=lambda kv: (-len(kv[1]), kv[0].casefold()))
    for tabla, nombres in ordenadas[:MAX_RESUMENES]:
        ejemplos = ", ".join(sorted(nombres, key=str.casefold)[:MAX_NOMBRES_RESUMEN])
        mas = " y otras" if len(nombres) > MAX_NOMBRES_RESUMEN else ""
        plan.observaciones.append(F.Entrada(
            f"{seccion} no detalladas en {tabla}"[:150],
            _texto_final(f"{len(nombres)} {motivo}; por ejemplo {ejemplos}{mas}. El cálculo está en el modelo")))
    resto = ordenadas[MAX_RESUMENES:]
    if resto:
        total = sum(len(n) for _, n in resto)
        plan.observaciones.append(F.Entrada(
            f"{seccion} no detalladas en otras tablas",
            _texto_final(f"{total} {motivo} en {len(resto)} tablas más")))


def _cardinalidad(r: dict) -> str:
    desde, hacia = (r.get("card_desde") or "").lower(), (r.get("card_hacia") or "").lower()
    nombres = {"many": "muchos", "one": "uno"}
    if desde in nombres and hacia in nombres:
        return f"{nombres[desde]} a {nombres[hacia]}".capitalize()
    return f"Cardinalidad {POR_CONFIRMAR.lower()}"


# ---------------------------------------------------------------------------
# Documentos
# ---------------------------------------------------------------------------

def _meta(modelo: dict, pagina: str, tablas: list[str], fecha: str, nombre_funcional: str) -> dict:
    return {
        "tablero": modelo["tablero"], "pagina": pagina, "nombre_funcional": nombre_funcional,
        "bloque": F.BLOQUE_DICCIONARIO, "tablas": tablas[:20], "actualizado": fecha, "version": 1,
    }


def _proposito(modelo: dict, plan: _Plan, con_columnas: bool = True, hay_otro_archivo: bool = False) -> str:
    texto = (f"Diccionario de variables del tablero {modelo['tablero']}: qué es cada tabla, medida y columna clave del "
             f"modelo «{modelo['modelo_nombre']}», con su cálculo y dónde se usa. Se genera del modelo y de los visuales; "
             f"las descripciones de negocio marcadas «{POR_CONFIRMAR}» las completa quien conoce el tablero.")
    if plan.conteos.get("medidas_omitidas") or plan.conteos.get("tablas_omitidas"):
        texto += " El modelo es grande: solo se detallan las medidas usadas en visuales o con descripción; el resto se resume en Observaciones."
    if hay_otro_archivo:
        texto += " Las columnas están en _diccionario_columnas.md."
    return texto


def _historial(fecha: str, detalle: str, version: int = 1) -> F.Entrada:
    return F.Entrada(f"{fecha} · v{version}", detalle)


def generar_esqueleto_archivos(source_group: str, project_root=None, *, raiz_docs=None, hechos=None,
                               fecha: str | None = None) -> dict[str, F.Documento]:
    """{archivo: Documento}: `_diccionario.md` y, si hay muchas columnas,
    `_diccionario_columnas.md`."""
    modelo = cargar_modelo(source_group, project_root, raiz_docs=raiz_docs, hechos=hechos)
    paginas, _ = _documentos_md(source_group, raiz_docs)
    plan = construir_plan(modelo, paginas)
    fecha = fecha or date.today().isoformat()
    columnas = len(plan.secciones["Columnas calculadas"]) + len(plan.secciones["Columnas clave"])
    separar = columnas > MAX_COLUMNAS_EN_PRINCIPAL
    detalle = "Esqueleto generado desde " + (" y ".join(modelo["fuentes"]) or "el modelo") + "."

    principal = F.Documento(
        meta=_meta(modelo, F.PAGINA_DICCIONARIO, [e.nombre for e in plan.secciones["Tablas"]], fecha,
                   "Diccionario de variables del tablero"),
        titulo=F.PAGINA_DICCIONARIO,
        proposito=_proposito(modelo, plan, hay_otro_archivo=separar),
    )
    for seccion in ("Tablas", "Medidas", "Relaciones") + (() if separar else ("Columnas calculadas", "Columnas clave")):
        if plan.secciones[seccion]:
            principal.secciones[seccion] = plan.secciones[seccion]
    if plan.observaciones:
        principal.secciones["Observaciones"] = plan.observaciones
    principal.secciones[F.SECCION_HISTORIAL] = [_historial(fecha, detalle)]
    archivos = {R.archivo_para(principal): principal}

    if separar:
        extra = F.Documento(
            meta=_meta(modelo, PAGINA_COLUMNAS, [], fecha, "Diccionario de columnas del tablero"),
            titulo=PAGINA_COLUMNAS,
            proposito=(f"Columnas calculadas y columnas clave (usadas en visuales o filtros) del tablero {modelo['tablero']}. "
                       f"Las tablas, medidas y relaciones están en _diccionario.md."),
        )
        for seccion in ("Columnas calculadas", "Columnas clave"):
            if plan.secciones[seccion]:
                extra.secciones[seccion] = plan.secciones[seccion]
        extra.secciones[F.SECCION_HISTORIAL] = [_historial(fecha, detalle)]
        archivos[R.archivo_para(extra)] = extra
    return archivos


def generar_esqueleto(source_group: str, project_root=None, *, raiz_docs=None, hechos=None,
                      fecha: str | None = None) -> F.Documento:
    """Documento principal del diccionario (`_diccionario.md`) del grupo."""
    archivos = generar_esqueleto_archivos(source_group, project_root, raiz_docs=raiz_docs, hechos=hechos, fecha=fecha)
    return archivos[R.archivo_para(F.Documento(meta={"bloque": F.BLOQUE_DICCIONARIO, "pagina": F.PAGINA_DICCIONARIO}, titulo=""))]


# ---------------------------------------------------------------------------
# Fusión con lo ya redactado (--escribir)
# ---------------------------------------------------------------------------

def _claves_modelo(modelo: dict) -> dict[str, set]:
    return {
        "Medidas": {F.normalizar_nombre(f"[{n}]") for n in modelo["medidas"]},
        "Columnas calculadas": {F.normalizar_nombre(f"{t}[{c}]") for (t, c) in modelo["columnas"]},
        "Columnas clave": {F.normalizar_nombre(f"{t}[{c}]") for (t, c) in modelo["columnas"]},
        "Tablas": {F.normalizar_nombre(t) for t in modelo["tablas"]},
        "Relaciones": {_clave_relacion(r["desde"], r["hacia"]) for r in modelo["relaciones"]},
    }


def _clave_relacion(desde: tuple, hacia: tuple) -> str:
    return F.normalizar_nombre(f"{desde[0]}[{desde[1]}]|{hacia[0]}[{hacia[1]}]")


def _clave_entrada(seccion: str, nombre: str) -> str:
    if seccion == "Relaciones":
        partes = re.split(r"\s*(?:→|->)\s*", nombre)
        if len(partes) == 2:
            return F.normalizar_nombre("|".join(partes))
    return F.normalizar_nombre(nombre)


def fusionar(existentes: dict[str, F.Documento], nuevos: dict[str, F.Documento], modelo: dict,
             fecha: str | None = None) -> tuple[dict[str, F.Documento], dict]:
    """Fusiona el esqueleto con los diccionarios existentes sin pisar texto:
    las entradas ya redactadas se conservan, las nuevas se agregan y las que ya
    no existen en el modelo se marcan «Obsoleta». Devuelve (documentos, resumen)."""
    import copy
    fecha = fecha or date.today().isoformat()
    vigentes = _claves_modelo(modelo)
    resumen = {"nuevas": 0, "obsoletas": 0, "archivos": []}
    resultado: dict[str, F.Documento] = {}

    presentes: dict[str, set] = {s: set() for s in _SECCIONES_DOC}
    for doc in existentes.values():
        for seccion in _SECCIONES_DOC:
            for e in doc.entradas(seccion):
                presentes[seccion].add(_clave_entrada(seccion, e.nombre))
                if seccion in ("Columnas calculadas", "Columnas clave"):
                    presentes["Columnas calculadas"].add(_clave_entrada(seccion, e.nombre))
                    presentes["Columnas clave"].add(_clave_entrada(seccion, e.nombre))

    for archivo in list(nuevos) + [a for a in existentes if a not in nuevos]:
        nuevo = nuevos.get(archivo) or F.Documento(meta={}, titulo="")
        actual = copy.deepcopy(existentes.get(archivo))
        if actual is None:
            doc = copy.deepcopy(nuevo)
            for seccion in _SECCIONES_DOC:  # no repetir lo que otro archivo ya documenta
                doc.secciones[seccion] = [e for e in doc.entradas(seccion)
                                          if _clave_entrada(seccion, e.nombre) not in presentes[seccion]]
                if not doc.secciones[seccion]:
                    doc.secciones.pop(seccion)
            conteo = sum(len(doc.entradas(s)) for s in _SECCIONES_DOC)
            resumen["nuevas"] += conteo
            resultado[archivo] = doc
            resumen["archivos"].append(archivo)
            continue
        cambios = 0
        for seccion in _SECCIONES_DOC:
            lista = actual.secciones.setdefault(seccion, [])
            for e in lista:
                if (_clave_entrada(seccion, e.nombre) not in vigentes[seccion]
                        and MARCA_OBSOLETA not in e.texto):
                    e.texto = f"{e.texto.rstrip()} {MARCA_OBSOLETA}"
                    resumen["obsoletas"] += 1
                    cambios += 1
            for e in nuevo.entradas(seccion):
                if _clave_entrada(seccion, e.nombre) not in presentes[seccion]:
                    lista.append(copy.deepcopy(e))
                    presentes[seccion].add(_clave_entrada(seccion, e.nombre))
                    resumen["nuevas"] += 1
                    cambios += 1
            if not lista:
                actual.secciones.pop(seccion)
        obs = actual.secciones.setdefault("Observaciones", [])
        nombres_obs = {F.normalizar_nombre(e.nombre) for e in obs}
        for e in nuevo.entradas("Observaciones"):
            if F.normalizar_nombre(e.nombre) not in nombres_obs:
                obs.append(copy.deepcopy(e))
                cambios += 1
        if not obs:
            actual.secciones.pop("Observaciones")
        if cambios:
            version = int(actual.meta.get("version") or 0) + 1
            actual.meta["version"] = version
            actual.meta["actualizado"] = fecha
            actual.secciones.setdefault(F.SECCION_HISTORIAL, []).append(
                _historial(fecha, f"Esqueleto actualizado con el modelo: {resumen['nuevas']} entradas nuevas y {resumen['obsoletas']} obsoletas.", version))
            resumen["archivos"].append(archivo)
        resultado[archivo] = actual
    return resultado, resumen


def escribir_esqueleto(source_group: str, project_root=None, *, raiz_docs=None, hechos=None,
                       fecha: str | None = None) -> dict:
    """Escribe/actualiza los `_diccionario*.md` del grupo sin pisar texto redactado.
    Devuelve {"escritos": [rutas], "nuevas", "obsoletas"}."""
    modelo = cargar_modelo(source_group, project_root, raiz_docs=raiz_docs, hechos=hechos)
    nuevos = generar_esqueleto_archivos(source_group, project_root, raiz_docs=raiz_docs, hechos=modelo["hechos"] if hechos is None else hechos, fecha=fecha)
    _, existentes_lista = _documentos_md(source_group, raiz_docs)
    existentes = {nombre: doc for nombre, doc in existentes_lista}
    fusion, resumen = fusionar(existentes, nuevos, modelo, fecha)
    escritos = []
    for archivo in resumen["archivos"]:
        escritos.append(str(R.guardar_pagina(source_group, fusion[archivo], raiz_docs)))
    return {"escritos": escritos, "nuevas": resumen["nuevas"], "obsoletas": resumen["obsoletas"]}


# ---------------------------------------------------------------------------
# Comparación con el modelo
# ---------------------------------------------------------------------------

def _normalizar_dax(dax: str | None) -> str:
    return re.sub(r"\s+", "", dax_en_una_linea(dax or "")).casefold()


def _dax_de_entrada(texto: str) -> str | None:
    from .ingesta import campos_entrada_diccionario
    return campos_entrada_diccionario(texto)["calculo"]


def comparar_con_modelo(source_group: str, project_root=None, *, raiz_docs=None, hechos=None) -> dict:
    """Qué cambió entre el diccionario escrito y el modelo actual.

    {"hay_diccionario": bool,
     "obsoletas": {"medidas": [...], "columnas": [...], "tablas": [...], "relaciones": [...]},
     "nuevas": {"medidas": [...], "columnas_calculadas": [...], "columnas_clave": [...], "tablas": [...], "relaciones": [...]},
     "renombradas_probables": [{"antes", "despues", "motivo"}],
     "cambios_calculo": [{"medida", "antes", "ahora"}]}

    «obsoletas»: entradas del diccionario que ya no existen en el modelo.
    «nuevas»: elementos que el esqueleto incluiría y el diccionario no tiene."""
    modelo = cargar_modelo(source_group, project_root, raiz_docs=raiz_docs, hechos=hechos)
    paginas, diccionarios = _documentos_md(source_group, raiz_docs)
    vigentes = _claves_modelo(modelo)
    obsoletas = {"medidas": [], "columnas": [], "tablas": [], "relaciones": []}
    presentes: dict[str, set] = {s: set() for s in _SECCIONES_DOC}
    dax_doc: dict[str, str | None] = {}
    for _, doc in diccionarios:
        for seccion in _SECCIONES_DOC:
            for e in doc.entradas(seccion):
                clave = _clave_entrada(seccion, e.nombre)
                presentes[seccion].add(clave)
                if seccion == "Medidas":
                    dax_doc[e.nombre.strip("[]")] = _dax_de_entrada(e.texto)
                if clave in vigentes[seccion]:
                    continue
                destino = {"Medidas": "medidas", "Columnas calculadas": "columnas", "Columnas clave": "columnas",
                           "Tablas": "tablas", "Relaciones": "relaciones"}[seccion]
                obsoletas[destino].append(e.nombre)
    plan = construir_plan(modelo, paginas)
    nuevas = {"medidas": [], "columnas_calculadas": [], "columnas_clave": [], "tablas": [], "relaciones": []}
    for seccion, destino in (("Medidas", "medidas"), ("Columnas calculadas", "columnas_calculadas"),
                             ("Columnas clave", "columnas_clave"), ("Tablas", "tablas"), ("Relaciones", "relaciones")):
        for e in plan.secciones[seccion]:
            if _clave_entrada(seccion, e.nombre) not in presentes[seccion]:
                nuevas[destino].append(e.nombre)
    # Una medida «obsoleta» con el mismo cálculo que una «nueva» es un cambio de nombre.
    renombradas = []
    if obsoletas["medidas"] and nuevas["medidas"]:
        por_dax = {}
        for nombre in nuevas["medidas"]:
            m = modelo["medidas"].get(nombre.strip("[]"))
            if m and m.get("dax"):
                por_dax.setdefault(_normalizar_dax(m["dax"]), []).append(nombre)
        for antes in obsoletas["medidas"]:
            dax = dax_doc.get(antes.strip("[]"))
            candidatas = por_dax.get(_normalizar_dax(dax), []) if dax else []
            if len(candidatas) == 1:
                renombradas.append({"antes": antes, "despues": candidatas[0], "motivo": "mismo cálculo DAX"})
    cambios = []
    for nombre, dax in dax_doc.items():
        m = modelo["medidas"].get(nombre)
        if m and dax and m.get("dax") and _normalizar_dax(dax) != _normalizar_dax(m["dax"]):
            cambios.append({"medida": f"[{nombre}]", "antes": dax, "ahora": dax_en_una_linea(m["dax"])})
    return {"hay_diccionario": bool(diccionarios), "obsoletas": obsoletas, "nuevas": nuevas,
            "renombradas_probables": renombradas, "cambios_calculo": cambios}


# ---------------------------------------------------------------------------
# Cobertura
# ---------------------------------------------------------------------------

def _sin_sufijo_numero(nombre: str) -> str:
    return re.sub(r"\s*\(\d+\)$", "", nombre or "")


def _menciona(texto_norm: str, nombre: str) -> bool:
    n = F.normalizar_nombre(nombre)
    return bool(n) and re.search(r"(?<![a-z0-9_])" + re.escape(n) + r"(?![a-z0-9_])", texto_norm) is not None


def _bloque(total: list, documentados: list) -> dict:
    faltantes = [x for x in total if x not in set(documentados)]
    return {"total": len(total), "documentados": len(total) - len(faltantes),
            "porcentaje": round(100 * (len(total) - len(faltantes)) / len(total), 1) if total else 100.0,
            "faltantes": faltantes}


_VISUALES_SIN_DATOS = {"shape", "basicShape", "image", "textbox", "grupo", "actionButton"}


def cobertura(source_group: str, project_root=None, *, raiz_docs=None, hechos=None) -> dict:
    """Qué del modelo y del PBIP NO está documentado en los .md del grupo.

    Un elemento cuenta como documentado si su nombre (normalizado: sin tildes ni
    mayúsculas, con límites de palabra) aparece en algún .md del grupo; las
    columnas, además, deben aparecer junto a su tabla. Del diccionario solo
    cuentan las entradas ya redactadas (las que empiezan por «Por confirmar» no). Devuelve
    {"source_group", "tablero", "modelo", "pbip", "medidas", "columnas_clave", "tablas",
     "relaciones", "paginas", "visuales", "diccionario": {...}, "porcentaje"} con
    {"total", "documentados", "porcentaje", "faltantes"} en cada bloque."""
    modelo = cargar_modelo(source_group, project_root, raiz_docs=raiz_docs, hechos=hechos)
    paginas_md, dicc_md = _documentos_md(source_group, raiz_docs)
    hechos = modelo["hechos"]
    textos = [(doc, F.normalizar_nombre(F.serializar(doc))) for _, doc in paginas_md]
    # Del diccionario solo cuentan las entradas ya redactadas (no las «Por confirmar»).
    for _, doc in dicc_md:
        redactadas = " ".join(f"{e.nombre} {e.texto}" for s in _SECCIONES_DOC for e in doc.entradas(s)
                              if not e.texto.casefold().startswith(POR_CONFIRMAR.casefold()))
        textos.append((doc, F.normalizar_nombre(redactadas)))
    todo = " ".join(t for _, t in textos)

    medidas = [f"[{n}]" for n in modelo["medidas"]]
    doc_medidas = [f"[{n}]" for n in modelo["medidas"] if _menciona(todo, n)]
    tablas = list(modelo["tablas"])
    doc_tablas = [t for t in tablas if _menciona(todo, t)]

    relaciones = [f"{r['desde'][0]}[{r['desde'][1]}] → {r['hacia'][0]}[{r['hacia'][1]}]" for r in modelo["relaciones"]]
    doc_rel = []
    for r, nombre in zip(modelo["relaciones"], relaciones):
        a, b = F.normalizar_nombre(f"{r['desde'][0]}[{r['desde'][1]}]"), F.normalizar_nombre(f"{r['hacia'][0]}[{r['hacia'][1]}]")
        if any(a in t and b in t for _, t in textos):
            doc_rel.append(nombre)

    resultado = {"source_group": source_group, "tablero": modelo["tablero"], "modelo": bool(modelo["medidas"] or modelo["columnas"]),
                 "pbip": hechos is not None, "fuentes": modelo["fuentes"]}
    resultado["medidas"] = _bloque(medidas, doc_medidas)
    resultado["tablas"] = _bloque(tablas, doc_tablas)
    resultado["relaciones"] = _bloque(relaciones, doc_rel)

    columnas_clave, doc_cols = [], []
    paginas_pbip, doc_pag, visuales, doc_vis = [], [], [], []
    if hechos is not None:
        uso = uso_de_campos(hechos)
        for clave in sorted(k for k in uso if not k.startswith("[")):
            columnas_clave.append(clave)
            tabla, _, col = clave.partition("[")
            col = col.rstrip("]")
            if any(_menciona(t, col) and _menciona(t, tabla) for _, t in textos):
                doc_cols.append(clave)
        por_pagina = {F.normalizar_nombre(doc.pagina): t for doc, t in textos
                      if not F.es_diccionario(doc.meta) and doc.meta.get("bloque") != "General"}
        for p in hechos.get("paginas") or []:
            nombre = p.get("nombre") or p.get("id")
            paginas_pbip.append(nombre)
            texto_pag = por_pagina.get(F.normalizar_nombre(nombre)) or por_pagina.get(F.normalizar_nombre(_sin_sufijo_numero(nombre)))
            if texto_pag is not None:
                doc_pag.append(nombre)
            for v in p.get("visuales") or []:
                if v.get("tipo") in _VISUALES_SIN_DATOS or v.get("oculto") or not (v.get("campos") or v.get("titulo")):
                    continue
                etiqueta = f"{nombre} › {pbip._nombre_visual(v)}"
                visuales.append(etiqueta)
                fichas = [v.get("titulo")] + [d.get("nombre") for d in v.get("campos_detalle") or []]
                if texto_pag is not None and any(f and _menciona(texto_pag, f) for f in fichas):
                    doc_vis.append(etiqueta)
    resultado["columnas_clave"] = _bloque(columnas_clave, doc_cols)
    resultado["paginas"] = _bloque(paginas_pbip, doc_pag)
    resultado["visuales"] = _bloque(visuales, doc_vis)

    entradas = por_confirmar = 0
    for _, doc in dicc_md:
        for seccion in _SECCIONES_DOC:
            for e in doc.entradas(seccion):
                entradas += 1
                if e.texto.casefold().startswith(POR_CONFIRMAR.casefold()):
                    por_confirmar += 1
    resultado["diccionario"] = {"existe": bool(dicc_md), "entradas": entradas, "por_confirmar": por_confirmar}
    bloques = [resultado[k] for k in ("medidas", "columnas_clave", "tablas", "relaciones", "paginas", "visuales")]
    total = sum(b["total"] for b in bloques)
    resultado["porcentaje"] = round(100 * sum(b["documentados"] for b in bloques) / total, 1) if total else 100.0
    return resultado


def listar_grupos(project_root=None, raiz_docs=None) -> list[str]:
    return [t["source_group"] for t in R.listar_tableros(raiz_docs)]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _imprimir_cobertura(c: dict, detalle: int = 8):
    print(f"{c['source_group']} ({c['tablero']}): {c['porcentaje']}% documentado"
          + ("" if c["pbip"] else " [sin PBIP: páginas, visuales y columnas clave no evaluadas]"))
    for clave, etiqueta in (("medidas", "Medidas"), ("columnas_clave", "Columnas clave"), ("tablas", "Tablas"),
                            ("relaciones", "Relaciones"), ("paginas", "Páginas"), ("visuales", "Visuales")):
        b = c[clave]
        print(f"  {etiqueta:15} {b['documentados']:>4}/{b['total']:<4} {b['porcentaje']:>5}%")
        for f in b["faltantes"][:detalle]:
            print(f"      - falta: {f}")
        if len(b["faltantes"]) > detalle:
            print(f"      ... y {len(b['faltantes']) - detalle} más")
    d = c["diccionario"]
    print(f"  Diccionario: {'sí' if d['existe'] else 'no'}"
          + (f" ({d['entradas']} entradas, {d['por_confirmar']} por confirmar)" if d["existe"] else ""))


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    parser = argparse.ArgumentParser(prog="python -m src.docs_md.diccionario",
                                     description="Diccionario de variables de los tableros.")
    parser.add_argument("--raiz", default=None, help="Raíz con data/ y tableros/ (por defecto DOCS_MD_DATA_ROOT o este repositorio)")
    sub = parser.add_subparsers(dest="orden", required=True)
    p_cob = sub.add_parser("cobertura", help="Qué falta documentar")
    p_cob.add_argument("grupo", nargs="?")
    p_cob.add_argument("--todos", action="store_true")
    p_cob.add_argument("--json", action="store_true")
    p_esq = sub.add_parser("esqueleto", help="Genera el esqueleto del diccionario")
    p_esq.add_argument("grupo")
    p_esq.add_argument("--escribir", action="store_true", help="Escribe en docs_tableros sin pisar texto redactado")
    p_cmp = sub.add_parser("comparar", help="Diccionario contra modelo: obsoleto y nuevo")
    p_cmp.add_argument("grupo")
    args = parser.parse_args(argv)

    if args.orden == "cobertura":
        if not args.grupo and not args.todos:
            parser.error("indique un grupo o --todos")
        grupos = listar_grupos() if args.todos else [args.grupo]
        resultados = []
        for g in grupos:
            try:
                resultados.append(cobertura(g, args.raiz))
            except FileNotFoundError as exc:
                print(f"{g}: sin datos del modelo ({exc})", file=sys.stderr)
        if args.json:
            print(json.dumps(resultados, ensure_ascii=False, indent=2))
        else:
            for c in resultados:
                _imprimir_cobertura(c, detalle=3 if args.todos else 8)
        return 0
    if args.orden == "esqueleto":
        if args.escribir:
            res = escribir_esqueleto(args.grupo, args.raiz)
            print(f"{len(res['escritos'])} archivo(s): {res['nuevas']} entradas nuevas, {res['obsoletas']} obsoletas.")
            for ruta in res["escritos"]:
                print("  ", ruta)
        else:
            for archivo, doc in generar_esqueleto_archivos(args.grupo, args.raiz).items():
                print(f"<!-- {archivo} -->")
                print(F.serializar(doc))
        return 0
    print(json.dumps(comparar_con_modelo(args.grupo, args.raiz), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
