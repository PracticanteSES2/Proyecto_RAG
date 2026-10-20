"""
Ubicación y acceso a la documentación .md de los tableros.

Cada tablero (grupo documental, el mismo `source_group` del RAG) guarda sus
páginas en `data/raw/<source_group>/md/`:

    data/raw/tablero_tiempos_urgencias/
        manifest.json
        md/
            _general.md          <- bloque General (una por tablero)
            resumen_d.md
            consultas_dia.md
            ...

La raíz se puede cambiar con la variable de entorno DOCS_MD_ROOT (pruebas).
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import unicodedata
from pathlib import Path

from .formato import Documento, ErrorFormato, normalizar_nombre, parsear, serializar, validar

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CARPETA_MD = "md"
ARCHIVO_GENERAL = "_general.md"


class ErrorRepositorio(ValueError):
    pass


def raiz_documentos(raiz: str | Path | None = None) -> Path:
    if raiz is not None:
        return Path(raiz)
    env = os.getenv("DOCS_MD_ROOT", "").strip()
    return Path(env) if env else PROJECT_ROOT / "data" / "raw"


def slug(texto: str) -> str:
    texto = unicodedata.normalize("NFD", str(texto or ""))
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"[^a-z0-9]+", "_", texto).strip("_") or "pagina"


def archivo_para(doc: Documento) -> str:
    if doc.meta.get("bloque") == "General":
        return ARCHIVO_GENERAL
    return slug(doc.pagina) + ".md"


def carpeta_md(source_group: str, raiz: str | Path | None = None) -> Path:
    return raiz_documentos(raiz) / source_group / CARPETA_MD


def listar_tableros(raiz: str | Path | None = None) -> list[dict]:
    """Grupos que tienen documentación .md: [{source_group, tablero, paginas}]."""
    base = raiz_documentos(raiz)
    resultado = []
    if not base.exists():
        return resultado
    for grupo in sorted(p for p in base.iterdir() if p.is_dir()):
        carpeta = grupo / CARPETA_MD
        archivos = sorted(carpeta.glob("*.md")) if carpeta.exists() else []
        if not archivos:
            continue
        tablero = grupo.name
        manifest = grupo / "manifest.json"
        if manifest.exists():
            try:
                tablero = json.loads(manifest.read_text(encoding="utf-8")).get("report") or tablero
            except (OSError, ValueError):
                pass
        resultado.append({"source_group": grupo.name, "tablero": tablero, "paginas": len(archivos)})
    return resultado


def listar_paginas(source_group: str, raiz: str | Path | None = None) -> list[dict]:
    """Páginas documentadas de un grupo, la general primero.
    [{pagina, archivo, nombre_funcional, bloque, valido}]"""
    carpeta = carpeta_md(source_group, raiz)
    paginas = []
    for archivo in sorted(carpeta.glob("*.md")):
        try:
            doc = parsear(archivo.read_text(encoding="utf-8"))
            paginas.append({
                "pagina": doc.pagina,
                "archivo": archivo.name,
                "nombre_funcional": doc.meta.get("nombre_funcional", ""),
                "bloque": doc.meta.get("bloque", ""),
                "valido": not validar(doc),
            })
        except (OSError, ErrorFormato):
            paginas.append({"pagina": archivo.stem, "archivo": archivo.name, "nombre_funcional": "",
                            "bloque": "", "valido": False})
    paginas.sort(key=lambda p: (p["archivo"] != ARCHIVO_GENERAL,))
    return paginas


def ruta_pagina(source_group: str, pagina: str, raiz: str | Path | None = None) -> Path:
    """Archivo de una página por su nombre exacto (sin distinguir tildes ni
    mayúsculas) o por nombre de archivo."""
    clave = normalizar_nombre(pagina)
    for item in listar_paginas(source_group, raiz):
        if normalizar_nombre(item["pagina"]) == clave or normalizar_nombre(item["archivo"]) == clave:
            return carpeta_md(source_group, raiz) / item["archivo"]
    raise ErrorRepositorio(f"No hay documentación de la página «{pagina}» en «{source_group}».")


def leer_texto(source_group: str, pagina: str, raiz: str | Path | None = None) -> str:
    return ruta_pagina(source_group, pagina, raiz).read_text(encoding="utf-8")


def leer_pagina(source_group: str, pagina: str, raiz: str | Path | None = None) -> Documento:
    return parsear(leer_texto(source_group, pagina, raiz))


def guardar_pagina(source_group: str, doc: Documento, raiz: str | Path | None = None) -> Path:
    """Valida y escribe la página de forma atómica (archivo temporal + reemplazo)."""
    errores = validar(doc)
    if errores:
        raise ErrorRepositorio("El documento no cumple el formato: " + " ".join(errores))
    carpeta = carpeta_md(source_group, raiz)
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / archivo_para(doc)
    contenido = serializar(doc)
    fd, tmp = tempfile.mkstemp(dir=carpeta, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(contenido)
        os.replace(tmp, destino)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return destino
