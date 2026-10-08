import difflib
import hashlib
import json
import logging
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Iterator, Union

from docx import Document
from docx.document import Document as DocumentClass
from docx.table import Table
from docx.text.paragraph import Paragraph

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - compatibilidad si dotenv no está instalado
    load_dotenv = None


logger = logging.getLogger(__name__)


def configure_console_utf8():
    """Evita UnicodeEncodeError con stdout cp1252 o redirigido."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if load_dotenv is not None:
    load_dotenv(PROJECT_ROOT / ".env")


# ============================================================
# UTILIDADES
# ============================================================

def clean_text(text: str) -> str:
    """Limpia espacios sin alterar el contenido semántico."""
    if not text:
        return ""

    text = str(text).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def slugify(value: str) -> str:
    """Convierte un nombre humano en una clave estable de carpeta/configuración."""
    value = clean_text(value).lower()
    value = "".join(
        char
        for char in unicodedata.normalize("NFD", value)
        if unicodedata.category(char) != "Mn"
    )
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def folder_to_display_name(folder_name: str) -> str:
    return clean_text(folder_name).replace("_", " ").upper()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)
    return data if isinstance(data, dict) else {}


def _normalize_aliases(values) -> list:
    if not values:
        return []
    if isinstance(values, str):
        values = [values]

    result = []
    for value in values:
        value = clean_text(value)
        if value and value not in result:
            result.append(value)
    return result


# ============================================================
# MANIFEST POR GRUPO DOCUMENTAL
# ============================================================

def find_manifest(file_path: Path, raw_dir: Path) -> Path | None:
    """
    Busca el manifest.json más cercano al documento, sin salir de data/raw.

    Esto permite tener configuración por grupo documental:
      data/raw/tablero_briefing_hospitalario/manifest.json
    """
    raw_dir = raw_dir.resolve()
    current = file_path.parent.resolve()

    while True:
        candidate = current / "manifest.json"
        if candidate.exists():
            return candidate

        if current == raw_dir:
            break

        try:
            current.relative_to(raw_dir)
        except ValueError:
            break

        parent = current.parent
        if parent == current:
            break
        current = parent

    return None


def lookup_registry_model(source_group: str, raw_dir: Path) -> dict:
    """
    Resuelve el modelo semántico de un grupo documental usando el registro de
    fuentes/modelos generado por powerbi_catalog_manager (sin variables de
    entorno). Devuelve {} si no hay coincidencia.
    """
    try:
        catalog_dir = raw_dir.parents[1] / "data" / "catalog"
    except IndexError:
        return {}

    group_key = slugify(source_group)

    for registry_name, list_key in (
        ("source_registry.json", "sources"),
        ("model_registry.json", "models"),
    ):
        registry_path = catalog_dir / registry_name
        if not registry_path.exists():
            continue

        try:
            registry = load_json(registry_path)
        except Exception:
            continue

        for item in registry.get(list_key, []) or []:
            candidates = {
                slugify(item.get("source_group") or ""),
                slugify(item.get("semantic_model_key") or ""),
            }
            candidates.discard("")
            if group_key and group_key in candidates:
                model = clean_text(item.get("semantic_model")) or None
                key = clean_text(item.get("semantic_model_key")) or None
                if model or key:
                    return {
                        "semantic_model": model,
                        "semantic_model_key": key,
                    }

    return {}


def resolve_document_config(file_path: Path, raw_dir: Path) -> dict:
    """
    Resuelve metadata explícita sin confundir carpeta documental con
    modelo semántico.

    Prioridad:
      1. manifest.json del grupo
      2. registro de fuentes/modelos (data/catalog)
      3. compatibilidad legacy
    Ya no se usa POWERBI_SEMANTIC_MODEL para agrupar: asignaba el mismo modelo
    a todo documento sin manifest.
    """
    relative_path = file_path.relative_to(raw_dir)
    path_parts = relative_path.parts

    manifest_path = find_manifest(file_path, raw_dir)
    manifest = load_json(manifest_path) if manifest_path else {}

    legacy_group = (
        path_parts[0]
        if len(path_parts) > 1
        else slugify(file_path.stem) or "documentacion"
    )

    source_group = clean_text(
        manifest.get("source_group") or legacy_group
    )

    workspace = clean_text(
        manifest.get("workspace")
        or os.getenv("POWERBI_WORKSPACE_NAME")
        or "Gestion Clinica"
    )

    semantic_model = clean_text(
        manifest.get("semantic_model")
    ) or None

    semantic_model_key = clean_text(
        manifest.get("semantic_model_key")
    ) or None

    if not semantic_model and not semantic_model_key:
        registry_hit = lookup_registry_model(source_group, raw_dir)
        semantic_model = registry_hit.get("semantic_model")
        semantic_model_key = registry_hit.get("semantic_model_key")

    if not semantic_model_key and semantic_model:
        semantic_model_key = slugify(semantic_model)

    if not semantic_model:
        logger.warning(
            "Sin modelo semántico para '%s' (sin manifest ni registro); "
            "semantic_model queda en None.",
            relative_path,
        )

    technical_catalog = clean_text(
        manifest.get("technical_catalog")
    ) or None

    if not technical_catalog and semantic_model_key:
        candidate = (
            raw_dir.parents[1]
            / "data"
            / "catalog"
            / f"{semantic_model_key}_rag.json"
        )
        if candidate.exists():
            technical_catalog = str(
                candidate.relative_to(raw_dir.parents[1])
            )

    default_dashboard = clean_text(
        manifest.get("default_dashboard")
        or folder_to_display_name(source_group)
    )

    aliases = _normalize_aliases(
        manifest.get("aliases")
        or manifest.get("dashboard_aliases")
    )

    document_type = clean_text(
        manifest.get("document_type")
        or "dashboard_documentation"
    )

    return {
        "workspace": workspace,
        "semantic_model": semantic_model,
        "semantic_model_key": semantic_model_key,
        "technical_catalog": technical_catalog,
        "source_group": source_group,
        "default_dashboard": default_dashboard,
        "aliases": aliases,
        "document_type": document_type,
        "manifest_path": (
            str(manifest_path.relative_to(raw_dir))
            if manifest_path
            else None
        ),
    }


# ============================================================
# LECTURA DEL DOCX
# ============================================================

def iter_blocks(
    parent: DocumentClass,
) -> Iterator[Union[Paragraph, Table]]:
    """Recorre párrafos y tablas respetando el orden original."""
    for child in parent.element.body.iterchildren():
        if child.tag.endswith("}p"):
            yield Paragraph(child, parent)
        elif child.tag.endswith("}tbl"):
            yield Table(child, parent)


def extract_table(table: Table) -> dict:
    rows = []
    for row in table.rows:
        rows.append([
            clean_text(cell.text)
            for cell in row.cells
        ])

    return {
        "type": "table",
        "rows": rows,
    }


def extract_document_blocks(file_path: Path) -> list:
    document = Document(file_path)
    blocks = []

    for block_index, block in enumerate(iter_blocks(document)):
        if isinstance(block, Paragraph):
            text = clean_text(block.text)
            if not text:
                continue

            blocks.append({
                "index": block_index,
                "type": "paragraph",
                "text": text,
                "style": (
                    block.style.name
                    if block.style
                    else None
                ),
            })

        elif isinstance(block, Table):
            table_data = extract_table(block)
            table_data["index"] = block_index
            blocks.append(table_data)

    return blocks


# ============================================================
# DETECCIÓN DE TABLEROS
# ============================================================

def is_dashboard_heading(text: str) -> bool:
    """Detecta encabezados de documentación de tablero/página."""
    text = clean_text(text).upper()

    patterns = [
        (
            r"^DOCUMENTACI[ÓO]N"
            r"\s*(?:[-–—:]\s*)?"
            r"TABLERO\b"
        ),
        (
            r"^TABLERO\s*(?:[-–—:]\s*)?"
        ),
    ]

    return any(
        re.search(pattern, text)
        for pattern in patterns
    )


def extract_dashboard_name(text: str) -> str:
    text = clean_text(text)

    name = re.sub(
        r"^DOCUMENTACI[ÓO]N"
        r"\s*(?:[-–—:]\s*)?"
        r"TABLERO\s*(?:[-–—:]\s*)?",
        "",
        text,
        flags=re.IGNORECASE,
    )

    if name == text:
        name = re.sub(
            r"^TABLERO\s*(?:[-–—:]\s*)?",
            "",
            text,
            flags=re.IGNORECASE,
        )

    return strip_leading_prepositions(clean_text(name))


LEADING_PREPOSITION_RE = re.compile(
    r"^(?:DE|DEL|LA|LAS|LOS|EL)\s+",
    re.IGNORECASE,
)


def strip_leading_prepositions(name: str) -> str:
    """'DE FACTURADORES' -> 'FACTURADORES' (sin vaciar el nombre)."""
    name = clean_text(name)
    while True:
        stripped = LEADING_PREPOSITION_RE.sub("", name, count=1)
        if stripped == name or not stripped:
            return name
        name = stripped


def folder_derived_name(file_path: Path) -> str:
    """'39 DOCUMENTACION TABLERO LAVANDERIA' -> 'LAVANDERIA'."""
    name = clean_text(file_path.parent.name).replace("_", " ")
    name = re.sub(r"^\d+[\s.\-_]*", "", name)
    name = re.sub(
        r"^DOCUMENTACI[ÓO]N\s*(?:DE\s+)?(?:TABLEROS?)?\s*",
        "",
        name,
        flags=re.IGNORECASE,
    )
    name = re.sub(r"^TABLEROS?\s+", "", name, flags=re.IGNORECASE)
    return strip_leading_prepositions(name).upper()


def _plain(value: str) -> str:
    return slugify(value).replace("_", " ")


def add_folder_aliases(dashboards: list, file_path: Path) -> None:
    """Agrega como alias el nombre derivado de la carpeta (corrige typos)."""
    folder_name = folder_derived_name(file_path)
    if not folder_name or _plain(folder_name) in {
        "documentacion", "tablero", "tableros",
    }:
        return

    for dashboard in dashboards:
        name = dashboard.get("name") or ""
        similar = (
            len(dashboards) == 1
            or difflib.SequenceMatcher(
                None, _plain(name), _plain(folder_name)
            ).ratio() >= 0.8
        )
        aliases = dashboard.setdefault("aliases", [])
        if (
            similar
            and _plain(folder_name) != _plain(name)
            and folder_name not in aliases
        ):
            aliases.append(folder_name)


def split_into_dashboards(
    blocks: list,
    file_name: str,
    default_dashboard: str | None = None,
    aliases: list | None = None,
) -> list:
    """
    Soporta dos casos:
      - un DOCX con varios encabezados de tablero;
      - un DOCX dedicado a un solo tablero, usando default_dashboard.

    Si hay texto introductorio antes del primer encabezado, se conserva en el
    primer tablero explícito en vez de crear un tablero espurio con el filename.
    """
    aliases = _normalize_aliases(aliases)
    explicit_headings = []

    for index, block in enumerate(blocks):
        if block.get("type") != "paragraph":
            continue
        if is_dashboard_heading(block.get("text", "")):
            explicit_headings.append(index)

    if not explicit_headings:
        dashboard_name = (
            clean_text(default_dashboard)
            or clean_text(Path(file_name).stem)
        )
        return [{
            "name": dashboard_name,
            "aliases": aliases,
            "source_file": file_name,
            "blocks": blocks,
        }]

    dashboards = []
    preamble = []
    current_dashboard = None

    for index, block in enumerate(blocks):
        if (
            block.get("type") == "paragraph"
            and is_dashboard_heading(block.get("text", ""))
        ):
            if current_dashboard is not None:
                dashboards.append(current_dashboard)

            dashboard_name = extract_dashboard_name(
                block.get("text", "")
            )

            if not dashboard_name:
                dashboard_name = (
                    clean_text(default_dashboard)
                    or clean_text(Path(file_name).stem)
                )

            dashboard_aliases = []
            if (
                default_dashboard
                and clean_text(dashboard_name).casefold()
                == clean_text(default_dashboard).casefold()
            ):
                dashboard_aliases = aliases

            current_dashboard = {
                "name": dashboard_name,
                "aliases": dashboard_aliases,
                "source_file": file_name,
                "blocks": [],
            }

            if preamble:
                current_dashboard["blocks"].extend(preamble)
                preamble = []

            continue

        if current_dashboard is None:
            preamble.append(block)
        else:
            current_dashboard["blocks"].append(block)

    if current_dashboard is not None:
        dashboards.append(current_dashboard)

    return dashboards


# ============================================================
# PROCESAMIENTO INDIVIDUAL
# ============================================================

def process_document(
    file_path: Path,
    raw_dir: Path,
) -> dict:
    relative_path = file_path.relative_to(raw_dir)
    config = resolve_document_config(file_path, raw_dir)

    blocks = extract_document_blocks(file_path)
    dashboards = split_into_dashboards(
        blocks=blocks,
        file_name=file_path.name,
        default_dashboard=config.get("default_dashboard"),
        aliases=config.get("aliases"),
    )
    add_folder_aliases(dashboards, file_path)

    return {
        "schema_version": 2,
        "source_file": file_path.name,
        "relative_path": str(relative_path),
        "source_folder": str(relative_path.parent),
        "source_group": config.get("source_group"),
        "source_hash": file_sha256(file_path),
        "document_type": config.get("document_type"),
        "manifest_path": config.get("manifest_path"),
        "workspace": config.get("workspace"),
        "semantic_model_key": config.get("semantic_model_key"),
        "semantic_model": config.get("semantic_model"),
        "technical_catalog": config.get("technical_catalog"),
        "default_dashboard": config.get("default_dashboard"),
        "dashboard_aliases": config.get("aliases", []),
        "dashboards": dashboards,
    }


# ============================================================
# PROCESAMIENTO MASIVO Y RECURSIVO
# ============================================================

def process_all_documents(
    raw_dir: Path,
    output_dir: Path,
):
    configure_console_utf8()
    raw_dir = Path(raw_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    documents = sorted(
        path
        for path in raw_dir.rglob("*.docx")
        if not path.name.startswith("~$")
    )

    print(f"Documentos encontrados: {len(documents)}")

    total_dashboards = 0
    processed = 0
    errors = []

    for document_path in documents:
        relative_path = document_path.relative_to(raw_dir)
        print("\nProcesando:", relative_path)

        try:
            result = process_document(document_path, raw_dir)

            output_path = (
                output_dir / relative_path
            ).with_suffix(".json")

            output_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            with open(output_path, "w", encoding="utf-8") as file:
                json.dump(
                    result,
                    file,
                    ensure_ascii=False,
                    indent=2,
                )

            dashboard_count = len(result.get("dashboards", []))
            total_dashboards += dashboard_count
            processed += 1

        except Exception as error:
            errors.append({
                "file": str(relative_path),
                "error_type": type(error).__name__,
                "error": str(error),
            })
            print(f"  [ERROR] Error procesando {relative_path}")
            print(f"    {type(error).__name__}: {error}")
            continue

        # Los prints van fuera del try que decide éxito/fallo.
        print(f"  [OK] JSON generado: {output_path}")
        print(f"  [OK] Grupo: {result.get('source_group')}")
        print(f"  [OK] Tableros detectados: {dashboard_count}")

        for dashboard in result.get("dashboards", []):
            print("     ->", dashboard.get("name"))

    print("\n==============================")
    print("PROCESAMIENTO FINALIZADO")
    print("==============================")
    print("Documentos procesados:", processed)
    print("Tableros detectados:", total_dashboards)
    print("Errores:", len(errors))

    return {
        "documents_found": len(documents),
        "documents_processed": processed,
        "dashboards": total_dashboards,
        "errors": errors,
    }


# ============================================================
# EJECUCIÓN
# ============================================================

if __name__ == "__main__":
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    RAW_DIR = PROJECT_ROOT / "data" / "raw"
    OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"

    process_all_documents(
        RAW_DIR,
        OUTPUT_DIR,
    )
