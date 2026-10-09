"""
Carga de metadata de modelos semánticos en el formato de EVALUATE INFO.VIEW.*.

Lee  <raíz>/<slug>/{tables,columns,measures,relationships}.csv  tal como los escribe
sync_powerbi_metadata.py (coma, cabeceras con o sin corchetes) o como los exporta
SSMS / DAX Studio (punto y coma). Varias raíces se fusionan (p. ej. data/model_metadata
real + el overlay versionado tests/realistic/synthetic_models); si un slug se repite,
gana la primera raíz.

Nombre del modelo semántico, por prioridad:
  1. data/catalog/model_registry.json  (semantic_model_key -> semantic_model)
  2. <slug>/_metadata_sync.json        ("semantic_model")
  3. display_name_from_slug(slug)      (igual que powerbi_catalog_manager)
"""
import csv
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

CSV_FILES = ("tables.csv", "columns.csv", "measures.csv", "relationships.csv")


def normalize_text(value):
    text = str(value or "").strip().lower()
    text = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def display_name_from_slug(value):
    """Copia de powerbi_catalog_manager.display_name_from_slug."""
    return str(value).replace("_", " ").replace("-", " ").strip().upper()


def key(name):
    """Clave de búsqueda: DAX no distingue mayúsculas en nombres de objetos."""
    return str(name or "").strip().casefold()


# ----------------------------------------------------------------------------
# Lectura de CSV
# ----------------------------------------------------------------------------

def read_csv(path):
    """Devuelve (cabeceras, filas). Cabeceras sin corchetes; detecta el separador."""
    raw = Path(path).read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    if not text.strip():
        return [], []
    header_line = text.splitlines()[0]
    counts = {d: header_line.count(d) for d in (",", ";", "\t")}
    delimiter = max(counts, key=counts.get)
    reader = csv.reader(text.splitlines(keepends=True), delimiter=delimiter)
    rows = list(reader)
    headers = [h.strip().strip("[]") for h in rows[0]]
    out = []
    for values in rows[1:]:
        if not any(v.strip() for v in values):
            continue
        out.append({h: (values[i] if i < len(values) else "") for i, h in enumerate(headers)})
    return headers, out


def _bool(value):
    return str(value).strip().lower() in ("true", "1", "yes", "verdadero")


# ----------------------------------------------------------------------------
# Esquema
# ----------------------------------------------------------------------------

# Tipos de INFO.VIEW.COLUMNS / MEASURES -> tipo interno del simulador
_TYPE_MAP = {
    "integer": "int", "int64": "int", "whole number": "int", "int": "int",
    "number": "float", "double": "float", "decimal number": "float", "float": "float",
    "decimal": "decimal", "currency": "decimal", "fixed decimal number": "decimal",
    "date": "date", "datetime": "date", "date/time": "date", "time": "date",
    "text": "text", "string": "text",
    "true/false": "bool", "boolean": "bool",
    "variant": "variant", "binary": "variant", "unknown": "variant", "": "variant",
}

# Nombre de tipo como lo muestra el motor en los mensajes de error
TYPE_LABEL = {"int": "Integer", "float": "Number", "decimal": "Currency", "date": "Date",
              "text": "Text", "bool": "True/False", "variant": "Variant"}


def map_type(value):
    return _TYPE_MAP.get(str(value or "").strip().lower(), "variant")


@dataclass
class Column:
    name: str
    table: str
    dtype: str
    kind: str = "data"            # data | calculated | rownumber | calctable
    expression: str = ""
    hidden: bool = False
    unique: bool = False
    format_string: str = ""
    raw_type: str = ""


@dataclass
class Table:
    name: str
    hidden: bool = False
    expression: str = ""
    columns: dict = field(default_factory=dict)    # key(col) -> Column (orden de metadata)

    @property
    def is_auto_date(self):
        lower = self.name.lower()
        return lower.startswith("localdatetable_") or lower.startswith("datetabletemplate_")

    def visible_columns(self):
        return [c for c in self.columns.values() if c.kind != "rownumber"]


@dataclass
class Measure:
    name: str
    table: str
    expression: str
    dtype: str = "variant"
    format_string: str = ""
    raw_type: str = ""


@dataclass
class Relationship:
    rid: str
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    from_card: str = "Many"
    to_card: str = "One"
    active: bool = True
    cross: str = "OneDirection"

    @property
    def both(self):
        return self.cross.lower().startswith("both") or (
            self.from_card.lower() == "one" and self.to_card.lower() == "one")


@dataclass
class ModelSchema:
    name: str
    slug: str
    path: Path
    origin: str = "real"                          # real | synthetic
    tables: dict = field(default_factory=dict)     # key -> Table
    measures: dict = field(default_factory=dict)   # key -> Measure
    relationships: list = field(default_factory=list)
    info_rows: dict = field(default_factory=dict)  # "tables" -> (headers, rows) para INFO.VIEW.*

    def table(self, name):
        return self.tables.get(key(name))

    def column(self, table, column):
        t = self.table(table)
        return t.columns.get(key(column)) if t else None

    def measure(self, name):
        return self.measures.get(key(name))


def _first(row, *names):
    lowered = {k.strip().lower(): v for k, v in row.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value not in (None, ""):
            return value
    return ""


def load_model(path, name=None, slug=None, origin="real"):
    path = Path(path)
    slug = slug or path.name
    schema = ModelSchema(name=name or display_name_from_slug(slug), slug=slug, path=path, origin=origin)

    for filename in CSV_FILES:
        file = path / filename
        schema.info_rows[filename[:-4]] = read_csv(file) if file.exists() else ([], [])

    for row in schema.info_rows["tables"][1]:
        tname = _first(row, "Name", "Table", "TableName")
        if not tname:
            continue
        schema.tables[key(tname)] = Table(
            name=tname, hidden=_bool(_first(row, "IsHidden")),
            expression=_first(row, "Expression"),
        )

    for row in schema.info_rows["columns"][1]:
        tname = _first(row, "Table", "TableName")
        cname = _first(row, "Name", "Column", "ColumnName")
        if not tname or not cname:
            continue
        table = schema.tables.get(key(tname))
        if table is None:
            table = schema.tables[key(tname)] = Table(name=tname)
        kind_raw = _first(row, "Type").lower()
        kind = {"data": "data", "calculated": "calculated", "rownumber": "rownumber",
                "calculatedtablecolumn": "calctable"}.get(kind_raw, "data")
        if cname.lower().startswith("rownumber-"):
            kind = "rownumber"
        raw_type = _first(row, "DataType")
        table.columns[key(cname)] = Column(
            name=cname, table=table.name, dtype=map_type(raw_type), kind=kind,
            expression=_first(row, "Expression"), hidden=_bool(_first(row, "IsHidden")),
            unique=_bool(_first(row, "IsUnique")) or _bool(_first(row, "IsKey")),
            format_string=_first(row, "FormatString"), raw_type=raw_type,
        )

    for row in schema.info_rows["measures"][1]:
        mname = _first(row, "Name", "Measure", "MeasureName")
        if not mname:
            continue
        raw_type = _first(row, "DataType")
        schema.measures[key(mname)] = Measure(
            name=mname, table=_first(row, "Table", "TableName"),
            expression=_first(row, "Expression"), dtype=map_type(raw_type),
            format_string=_first(row, "FormatString"), raw_type=raw_type,
        )

    for index, row in enumerate(schema.info_rows["relationships"][1]):
        ft, fc = _first(row, "FromTable"), _first(row, "FromColumn")
        tt, tc = _first(row, "ToTable"), _first(row, "ToColumn")
        if not (ft and fc and tt and tc):
            continue
        schema.relationships.append(Relationship(
            rid=_first(row, "ID", "Name") or str(index),
            from_table=ft, from_column=fc, to_table=tt, to_column=tc,
            from_card=_first(row, "FromCardinality") or "Many",
            to_card=_first(row, "ToCardinality") or "One",
            active=_bool(_first(row, "IsActive") or "True"),
            cross=_first(row, "CrossFilteringBehavior") or "OneDirection",
        ))
    return schema


def _registry_names(registry_path):
    names = {}
    if not registry_path or not Path(registry_path).exists():
        return names
    try:
        payload = json.loads(Path(registry_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return names
    for item in payload.get("models", []) or []:
        name = item.get("semantic_model")
        slug = item.get("semantic_model_key")
        metadata_path = item.get("metadata_path")
        if not slug and metadata_path:
            slug = Path(metadata_path).name
        if name and slug:
            names[slug] = name
    return names


def discover_models(metadata_roots, registry_path=None):
    """Devuelve {nombre_modelo: ModelSchema} fusionando las raíces dadas.

    metadata_roots: lista de rutas o de (ruta, origen).
    """
    registry = _registry_names(registry_path)
    models = {}
    seen_slugs = set()
    for item in metadata_roots:
        root, origin = (item if isinstance(item, tuple) else (item, "real"))
        root = Path(root)
        if not root.exists():
            continue
        for folder in sorted(p for p in root.iterdir() if p.is_dir()):
            if folder.name in seen_slugs:
                continue
            if not all((folder / f).exists() for f in CSV_FILES):
                continue
            name = registry.get(folder.name)
            sync_file = folder / "_metadata_sync.json"
            if not name and sync_file.exists():
                try:
                    name = json.loads(sync_file.read_text(encoding="utf-8")).get("semantic_model")
                except (OSError, ValueError):
                    name = None
            schema = load_model(folder, name=name, slug=folder.name, origin=origin)
            seen_slugs.add(folder.name)
            models[schema.name] = schema
    return models
