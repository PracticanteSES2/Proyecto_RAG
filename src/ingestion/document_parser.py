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


def _relative_to_any(path: Path, *bases) -> str:
    for base in bases:
        try:
            return str(Path(path).relative_to(base))
        except ValueError:
            continue
    return str(path)


def resolve_document_config(
    file_path: Path,
    raw_dir: Path,
    manifest_path: Path | None = None,
    base_dir: Path | None = None,
) -> dict:
    """
    Resuelve metadata explícita sin confundir carpeta documental con
    modelo semántico.

    Prioridad:
      1. manifest.json del grupo
      2. registro de fuentes/modelos (data/catalog)
      3. compatibilidad legacy
    Ya no se usa POWERBI_SEMANTIC_MODEL para agrupar: asignaba el mismo modelo
    a todo documento sin manifest.

    base_dir: raíz de la que cuelga el archivo si no es raw_dir (páginas .md
    fuera de data/raw); manifest_path: manifest ya elegido (si no, el más
    cercano dentro de base_dir).
    """
    base_dir = Path(base_dir) if base_dir is not None else Path(raw_dir)
    relative_path = file_path.relative_to(base_dir)
    path_parts = relative_path.parts

    if manifest_path is None:
        manifest_path = find_manifest(file_path, base_dir)
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
            _relative_to_any(manifest_path, raw_dir, base_dir)
            if manifest_path
            else None
        ),
        "report": clean_text(manifest.get("report")) or None,
        "manifest_default_dashboard": clean_text(manifest.get("default_dashboard")) or None,
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
# DOCUMENTACIÓN VIVA EN MARKDOWN (<raíz md>/<grupo>/md/*.md)
# ============================================================

MARKDOWN_FOLDER = "md"


def markdown_root(raw_dir: Path, md_root: Path | None = None) -> Path:
    """Raíz de la documentación .md: la indicada, si no DOCS_MD_ROOT
    (repositorio.raiz_documentos) y si no data/raw (raw_dir)."""
    if md_root is not None:
        return Path(md_root)
    if os.getenv("DOCS_MD_ROOT", "").strip():
        from src.docs_md.repositorio import raiz_documentos

        return raiz_documentos()
    return Path(raw_dir)


def markdown_files(group_dir: Path) -> list:
    """Páginas .md del grupo (sin temporales ni archivos ocultos)."""
    folder = Path(group_dir) / MARKDOWN_FOLDER
    if not folder.is_dir():
        return []
    return sorted(
        path
        for path in folder.glob("*.md")
        if path.is_file() and not path.name.startswith(("~$", "."))
    )


def markdown_groups(md_root: Path) -> dict:
    """{carpeta del grupo: [páginas .md]} de los grupos con documentación .md.

    En esos grupos el .md es la fuente vigente: sus .docx se ignoran para que
    la documentación vieja no contradiga la nueva.
    """
    md_root = Path(md_root)
    groups = {}
    if not md_root.is_dir():
        return groups
    for group_dir in sorted(p for p in md_root.iterdir() if p.is_dir()):
        files = markdown_files(group_dir)
        if files:
            groups[group_dir] = files
    return groups


def group_folder(file_path: Path, raw_dir: Path) -> Path | None:
    """Carpeta de primer nivel (grupo documental) que contiene el archivo."""
    try:
        relative = Path(file_path).relative_to(raw_dir)
    except ValueError:
        return None
    if len(relative.parts) < 2:
        return None
    return Path(raw_dir) / relative.parts[0]


def markdown_manifest(group_name: str, md_root: Path, raw_dir: Path) -> Path | None:
    """manifest.json del grupo: primero junto a los .md y si no en data/raw/<grupo>."""
    for base in (Path(md_root), Path(raw_dir)):
        candidate = base / group_name / "manifest.json"
        if candidate.exists():
            return candidate
    return None


def folder_source_group(group_dir: Path, manifest: Path | None = None) -> str:
    """source_group de una carpeta: el del manifest.json o el nombre de la carpeta."""
    manifest = Path(manifest) if manifest is not None else Path(group_dir) / "manifest.json"
    if manifest.exists():
        try:
            value = clean_text(load_json(manifest).get("source_group"))
            if value:
                return value
        except Exception:
            pass
    return Path(group_dir).name


def process_markdown_document(
    file_path: Path,
    raw_dir: Path,
    md_root: Path | None = None,
) -> dict:
    """Una página .md -> JSON procesado (el texto se normaliza en
    document_normalizer con src.docs_md.ingesta, sin heurísticas)."""
    from src.docs_md.formato import parsear, validar
    from src.docs_md.ingesta import es_general

    raw_dir = Path(raw_dir)
    md_root = Path(md_root) if md_root is not None else raw_dir
    relative_path = file_path.relative_to(md_root)
    config = resolve_document_config(
        file_path,
        raw_dir,
        manifest_path=markdown_manifest(relative_path.parts[0], md_root, raw_dir),
        base_dir=md_root,
    )

    text = file_path.read_text(encoding="utf-8")
    doc = parsear(text)  # ErrorFormato -> error de extracción del archivo
    general = es_general(doc, file_path.name)

    aliases = []
    if general:
        # El bloque General es el tablero completo: se llama como el informe
        # del manifest (nunca «GENERAL», que chocaría entre grupos y el
        # enrutador tomaría por una página) y lleva los alias del manifest,
        # como el tablero por defecto del flujo .docx.
        name = (
            config.get("manifest_default_dashboard")
            or config.get("report")
            or clean_text(config.get("default_dashboard"))
            or clean_text(doc.meta.get("tablero"))
        )
        aliases = _normalize_aliases(
            [config.get("report"), config.get("default_dashboard"), doc.meta.get("tablero")]
            + list(config.get("aliases") or [])
            + ([doc.pagina] if _plain(doc.pagina) not in {"", "general"} else [])
        )
    else:
        name = clean_text(doc.pagina) or folder_to_display_name(file_path.stem)

    return {
        "schema_version": 2,
        "source_format": "md",
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
        "format_warnings": validar(doc),
        "dashboards": [{
            "name": name,
            "aliases": aliases,
            "source_file": file_path.name,
            "markdown": text,
        }],
    }


def plan_documents(
    raw_dir: Path,
    source_group: str | None = None,
    md_root: Path | None = None,
) -> dict:
    """Archivos a procesar: .docx de los grupos sin .md y .md de los grupos
    con documentación viva. Con source_group solo los de ese grupo.

    Un grupo .md (<raíz md>/<carpeta>/md/) anula los .docx de la carpeta de
    data/raw con el mismo nombre o el mismo source_group."""
    raw_dir = Path(raw_dir)
    md_root = markdown_root(raw_dir, md_root)
    md_groups = {
        folder: {
            "files": files,
            "source_group": folder_source_group(
                folder, markdown_manifest(folder.name, md_root, raw_dir)
            ),
        }
        for folder, files in markdown_groups(md_root).items()
    }
    md_names = {folder.name for folder in md_groups}
    md_source_groups = {info["source_group"] for info in md_groups.values()}

    def in_scope(names):
        return source_group is None or source_group in names

    docx = []
    ignored = []
    for path in sorted(raw_dir.rglob("*.docx")):
        if path.name.startswith("~$"):
            continue
        folder = group_folder(path, raw_dir)
        names = (
            {folder.name, folder_source_group(folder)}
            if folder is not None
            else set()
        )
        if not in_scope(names):
            continue
        if names & md_names or names & md_source_groups:
            ignored.append(path)
        else:
            docx.append(path)

    selected = [
        folder
        for folder, info in md_groups.items()
        if in_scope({folder.name, info["source_group"]})
    ]

    return {
        "docx": docx,
        "markdown": [path for folder in selected for path in md_groups[folder]["files"]],
        "ignored_docx": ignored,
        "markdown_groups": [folder.name for folder in selected],
        "markdown_root": md_root,
    }


# ============================================================
# PROCESAMIENTO MASIVO Y RECURSIVO
# ============================================================

def process_all_documents(
    raw_dir: Path,
    output_dir: Path,
    source_group: str | None = None,
    md_root: Path | None = None,
):
    """Extrae la documentación de data/raw.

    Los grupos con páginas en `<raíz md>/<grupo>/md/*.md` se ingieren desde el
    .md y sus .docx se ignoran (con aviso). La raíz md es `md_root`, si no
    DOCS_MD_ROOT y si no el mismo raw_dir. Con source_group solo se procesa
    ese grupo.
    """
    configure_console_utf8()
    raw_dir = Path(raw_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    plan = plan_documents(raw_dir, source_group=source_group, md_root=md_root)
    md_root = plan["markdown_root"]
    documents = plan["docx"] + plan["markdown"]

    print(f"Documentos encontrados: {len(documents)}")

    if plan["ignored_docx"]:
        print(
            "\n[AVISO] Grupos con documentación .md "
            f"({', '.join(plan['markdown_groups'])}): se ignoran sus .docx:"
        )
        for path in plan["ignored_docx"]:
            print("   -", path.relative_to(raw_dir))
            # Sin limpieza previa (--no-clean-derived) quedaría el JSON del
            # .docx de una corrida anterior contradiciendo al .md.
            stale = (output_dir / path.relative_to(raw_dir)).with_suffix(".json")
            if stale.exists():
                stale.unlink()

    # Páginas .md eliminadas: su JSON de una corrida anterior también sobra.
    current = {path.relative_to(md_root).with_suffix(".json") for path in plan["markdown"]}
    for group_name in plan["markdown_groups"]:
        for stale in sorted((output_dir / group_name / MARKDOWN_FOLDER).glob("*.json")):
            if stale.relative_to(output_dir) not in current:
                stale.unlink()

    total_dashboards = 0
    processed = 0
    errors = []

    for document_path in documents:
        is_markdown = document_path.suffix.lower() == ".md"
        relative_path = document_path.relative_to(md_root if is_markdown else raw_dir)
        print("\nProcesando:", relative_path)

        try:
            if is_markdown:
                result = process_markdown_document(document_path, raw_dir, md_root)
            else:
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

        for warning in result.get("format_warnings") or []:
            print("  [AVISO] Formato .md:", warning)

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
        "markdown_groups": plan["markdown_groups"],
        "ignored_docx": [
            str(path.relative_to(raw_dir))
            for path in plan["ignored_docx"]
        ],
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
