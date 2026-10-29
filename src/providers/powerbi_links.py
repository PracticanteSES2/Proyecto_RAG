"""
Enlaces «Abrir en Power BI» a partir de data/catalog/report_links.json.

El archivo lo genera `sync_powerbi_links.py` (solo GET a la API REST). Este
módulo no usa la red: solo lee el JSON.

    enlace_para("BRIEFING HOSPITALARIO", page="Inicio")
    -> {"url": "https://app.powerbi.com/groups/<ws>/reports/<id>/<página>",
        "etiqueta": "Abrir BRIEFING HOSPITALARIO › INICIO",
        "nivel": "pagina", "modelo": ..., "informe": ..., "pagina": ...}

- Los nombres se comparan normalizados (mayúsculas, sin tildes, «_», «-» y
  espacios repetidos como un espacio), y también sin espacios.
- La página puede venir por su nombre visible («INICIO») o por su id interno
  («ReportSection…», el name del PBIR).
- Si la página no aparece, cae al informe (nivel «informe»). Si el modelo no
  tiene informe propio (p. ej. «Dashboard Gestion»), devuelve None.

Filtro por URL (opcional, `con_filtros`): agrega
`?filter=Tabla/Columna eq 'X'` (o `in ('A','B')`) solo con filtros simples y
ya verificados contra el modelo (los categóricos del plan de consulta, con
operador = o IN y valores de texto o número). Los nombres de tabla y columna
se escapan como pide Power BI (`_x0020_` para el espacio, `_x00F1_` para la
ñ…) y las comillas del valor se duplican. Fechas, rangos y medidas no se
traducen: el enlace queda sin ese filtro. El filtro de URL se suma a los
segmentadores guardados del informe; no los reemplaza.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
import urllib.parse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = PROJECT_ROOT / "data" / "catalog" / "report_links.json"
SEPARADOR = " › "
MAX_FILTER_VALUES = 10

_cache: dict = {"path": None, "mtime": None, "data": None}


def normalizar(texto) -> str:
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[_\-.]+", " ", texto.upper())
    return " ".join(texto.split())


def _compacto(texto) -> str:
    return normalizar(texto).replace(" ", "")


def _ruta() -> Path:
    ruta = os.getenv("POWERBI_LINKS_PATH", "").strip()
    return Path(ruta) if ruta else DEFAULT_PATH


def cargar_enlaces(path: Path | str | None = None) -> dict | None:
    """Catálogo de enlaces (en caché mientras el archivo no cambie)."""
    path = Path(path) if path else _ruta()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    if _cache["path"] == path and _cache["mtime"] == mtime:
        return _cache["data"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = None
    _cache.update(path=path, mtime=mtime, data=data)
    return data


def _igual(a, b) -> bool:
    return bool(a and b) and (normalizar(a) == normalizar(b) or _compacto(a) == _compacto(b))


def _buscar_modelo(models: dict, nombre):
    if not nombre:
        return None
    for key, entry in models.items():
        if _igual(key, nombre):
            return entry
    return None


def _buscar_pagina(report: dict, page):
    if not page:
        return None
    for item in report.get("pages") or []:
        if item.get("name") == page:
            return item
    for item in report.get("pages") or []:
        if _igual(item.get("display_name"), page):
            return item
    return None


def _separar(report, page):
    # «INFORME › PÁGINA» en un solo campo (así lo trae a veces «dashboard»).
    if page and SEPARADOR.strip() in str(page):
        partes = [p.strip() for p in str(page).split(SEPARADOR.strip()) if p.strip()]
        if len(partes) >= 2:
            return report or partes[0], partes[-1]
    return report, page


def enlace_para(semantic_model, report=None, page=None, links: dict | None = None) -> dict | None:
    """Enlace al informe y, si se encuentra, a la página exacta."""
    data = links if links is not None else cargar_enlaces()
    if not data:
        return None
    models = data.get("models") or {}
    report, page = _separar(report, page)

    entry = _buscar_modelo(models, semantic_model)
    candidatos = list(entry["reports"]) if entry else []
    if not candidatos and report:
        # Sin modelo conocido: se busca el informe por nombre en todo el catálogo.
        candidatos = [r for m in models.values() for r in m.get("reports") or [] if _igual(r.get("name"), report)]
        entry = next((m for m in models.values() if any(r in m.get("reports", []) for r in candidatos)), None)
    if not candidatos and not semantic_model and not report and page:
        # Solo la página: vale si un único informe del catálogo la tiene.
        con_pagina = [
            (m, r) for m in models.values() for r in m.get("reports") or [] if _buscar_pagina(r, page)
        ]
        if len(con_pagina) == 1:
            entry, unico = con_pagina[0]
            candidatos = [unico]
    if not candidatos:
        return None

    elegido, pagina = None, None
    if report:
        elegido = next((r for r in candidatos if _igual(r.get("name"), report)), None)
    if page:
        orden = [elegido] if elegido else []
        orden += [r for r in candidatos if r is not elegido]
        for item in orden:
            pagina = _buscar_pagina(item, page)
            if pagina:
                elegido = item
                break
    if elegido is None:
        # El sincronizador ordena primero el informe que se llama como el modelo.
        elegido = candidatos[0]

    nombre_informe = elegido.get("name") or (entry or {}).get("semantic_model") or ""
    if pagina:
        return {
            "url": pagina["url"],
            "etiqueta": f"Abrir {nombre_informe}{SEPARADOR}{pagina.get('display_name') or pagina['name']}",
            "nivel": "pagina",
            "modelo": (entry or {}).get("semantic_model"),
            "informe": nombre_informe,
            "pagina": pagina.get("display_name") or pagina["name"],
        }
    return {
        "url": elegido["url"],
        "etiqueta": f"Abrir {nombre_informe}",
        "nivel": "informe",
        "modelo": (entry or {}).get("semantic_model"),
        "informe": nombre_informe,
        "pagina": None,
    }


# ----------------------------------------------------------------------------
# Filtro por URL
# ----------------------------------------------------------------------------

def _escapar_nombre(nombre: str) -> str:
    """Tabla/columna para ?filter=: todo lo que no sea letra ASCII, dígito o
    «_» se escribe como _xHHHH_ (espacio -> _x0020_, ñ -> _x00F1_)."""
    return "".join(
        c if (c.isascii() and (c.isalnum() or c == "_")) else f"_x{ord(c):04X}_"
        for c in str(nombre)
    )


def _literal(valor):
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return str(valor)
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    if isinstance(valor, str) and valor.strip() and "\n" not in valor:
        return "'" + valor.replace("'", "''") + "'"
    return None


def expresion_filtro(filtro: dict) -> str | None:
    """Expresión de un filtro verificado, o None si no es simple."""
    if not isinstance(filtro, dict) or filtro.get("type") != "categorical":
        return None
    tabla, columna = filtro.get("table"), filtro.get("column")
    if not tabla or not columna:
        return None
    operador = str(filtro.get("operator") or "").strip().lower()
    campo = f"{_escapar_nombre(tabla)}/{_escapar_nombre(columna)}"
    if operador in {"=", "eq"}:
        literal = _literal(filtro.get("value"))
        return f"{campo} eq {literal}" if literal else None
    if operador == "in":
        valores = filtro.get("values") or []
        literales = [_literal(v) for v in valores]
        if not literales or len(literales) > MAX_FILTER_VALUES or None in literales:
            return None
        return f"{campo} in ({','.join(literales)})"
    return None


def con_filtros(enlace: dict | None, filtros) -> dict | None:
    """Copia del enlace con ?filter= de los filtros simples (unidos con «and»).
    Si ninguno es simple, devuelve el enlace sin cambios."""
    if not enlace:
        return enlace
    expresiones = [e for e in (expresion_filtro(f) for f in (filtros or [])) if e]
    if not expresiones:
        return enlace
    consulta = urllib.parse.quote(" and ".join(expresiones), safe="/'(),_")
    separador = "&" if "?" in enlace["url"] else "?"
    return {**enlace, "url": f"{enlace['url']}{separador}filter={consulta}", "filtrado": True}


# ----------------------------------------------------------------------------
# A partir del resultado del motor (QueryEngine) y de sus contrapreguntas
# ----------------------------------------------------------------------------

_POWERBI_STATUS = {"success", "empty_result"}


def enlace_para_resultado(result: dict | None, links: dict | None = None) -> dict | None:
    """Enlace para una respuesta del motor, o None si no cita un tablero.

    - Ruta «powerbi» (éxito o sin datos): modelo semántico, informe y página
      (`dashboard`) del resultado, con los filtros simples en la URL.
    - Ruta «rag»: la página detectada en la pregunta (`dashboard`) con el
      modelo de las fuentes que la citan; si no hay página detectada, solo
      cuando todas las fuentes vienen de un mismo modelo.
    """
    if not isinstance(result, dict):
        return None
    route, status = result.get("route"), result.get("status")
    if route == "powerbi" and status in _POWERBI_STATUS:
        plan = result.get("query_plan") or {}
        enlace = enlace_para(
            result.get("semantic_model") or plan.get("semantic_model"),
            result.get("report") or plan.get("report"),
            result.get("dashboard") or plan.get("dashboard"),
            links=links,
        )
        return con_filtros(enlace, result.get("filters") or plan.get("filters"))
    if route == "rag" and status == "success":
        sources = [s for s in result.get("sources") or [] if isinstance(s, dict)]
        dashboard = result.get("dashboard")
        if dashboard:
            modelos = {s.get("semantic_model") for s in sources
                       if s.get("semantic_model") and _igual(s.get("dashboard"), dashboard)}
            modelo = next(iter(modelos)) if len(modelos) == 1 else None
            # «dashboard» puede ser una página («TRIAGE») o el informe entero.
            return (enlace_para(modelo, page=dashboard, links=links)
                    or enlace_para(modelo, report=dashboard, links=links))
        modelos = {s.get("semantic_model") for s in sources}
        if len(modelos) != 1 or None in modelos or "" in modelos:
            return None
        paginas = {normalizar(s.get("dashboard")) for s in sources}
        pagina = sources[0].get("dashboard") if len(paginas) == 1 else None
        return enlace_para(next(iter(modelos)), page=pagina, links=links)
    return None


def enlace_para_opcion(option: dict | None, links: dict | None = None) -> dict | None:
    """Enlace de una opción de contrapregunta. Usa `semantic_model`/`report`/
    `page` si la opción los trae; si no, su `detail` («INFORME › PÁGINA ·
    MODELO»), que es como el motor describe dónde está cada indicador."""
    if not isinstance(option, dict):
        return None
    model, report, page = option.get("semantic_model"), option.get("report"), option.get("page")
    if not (model or report or page):
        detail = str(option.get("detail") or "").strip()
        if not detail:
            return None
        partes = [p.strip() for p in detail.split(" · ") if p.strip()]
        if len(partes) > 2:
            return None
        if len(partes) == 2:
            model = partes[1]
        donde = [p.strip() for p in partes[0].split(SEPARADOR.strip()) if p.strip()]
        if len(donde) > 2:
            return None
        report = donde[0]
        page = donde[1] if len(donde) == 2 else None
    return enlace_para(model, report, page, links=links)
