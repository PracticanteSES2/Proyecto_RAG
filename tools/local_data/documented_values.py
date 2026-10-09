"""
Valores categóricos DOCUMENTADOS de las columnas de un modelo.

Fuentes (solo texto de la documentación; nunca datos de pacientes):
  - SQL documentado:  CASE ... THEN 'SURA' ... ELSE 'OTRAS' END AS ASEGURADORA
    -> ASEGURADORA ∈ {SURA, OTRAS}; y  COL IN ('A','B') / COL = 'A' cuando COL
    también es una columna de salida de la misma consulta.
  - DAX documentado (medidas y columnas calculadas):  T[C] = "X",
    T[C] IN {"A","B"} y los textos que devuelve una columna calculada con
    IF/SWITCH (TURNO_OK -> MAÑANA/TARDE/NOCHE).

Se escriben en data/model_metadata/<slug>/_documented_values.json para que el
simulador de Power BI (tests/realistic) genere dominios realistas y para que
la inferencia de indicadores reconozca calificadores («compras con aumento»
-> ESTADO = "AUMENTÓ"). Los nombres de columna del SQL no siempre dicen en qué
tabla del modelo terminan: si no se sabe, `table` queda en null y el valor
aplica a las columnas con ese nombre.
"""
import re
from collections import OrderedDict

from tools.local_data.infer_metadata import (
    _clean_identifier,
    _select_lists,
    _split_top_level,
    _strip_sql_comments,
    dax_references,
    sql_select_aliases,
)
from tools.local_data.metadata_format import save_json


# Columnas de personas/identificadores: nunca se guardan valores.
PERSON_RE = re.compile(
    r"paciente|nombre|apellido|medico|documento|identificacion|cedula|historia|telefono|"
    r"celular|direccion|correo|email|usuario|usu_|profesional|responsable",
    re.IGNORECASE,
)
NON_PERSON_RE = re.compile(
    r"servicio|entidad|asegura|eps|tercero|sede|especialidad|procedimiento|examen|"
    r"diagnostico|municipio|departamento|unidad|area|cama|empresa|convenio|prestador|grupo",
    re.IGNORECASE,
)

SQL_STRING_RE = re.compile(r"'((?:[^']|'')*)'")
THEN_ELSE_RE = re.compile(r"\b(?:THEN|ELSE)\s+'((?:[^']|'')*)'", re.IGNORECASE)
DAX_STRING_RE = re.compile(r'"((?:[^"]|"")*)"')


def is_person_column(name):
    text = str(name or "")
    return bool(PERSON_RE.search(text)) and not NON_PERSON_RE.search(text)


def plausible_value(value):
    """Etiqueta categórica razonable (no patrones LIKE, colores, SQL ni vacíos)."""
    text = str(value or "").strip()
    if not text or len(text) > 60 or "%" in text or text.startswith("#"):
        return False
    if re.search(r"[\[\]=(){}]|\bSELECT\b|\bFROM\b|\bAND\b", text, re.IGNORECASE):
        return False
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", text):
        return False
    return bool(re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ0-9]", text))


class DocumentedValues:

    def __init__(self):
        # (tabla|None, columna) -> {"values": [...], "origins": set()}
        self.items = OrderedDict()

    def add(self, table, column, value, origin):
        column = str(column or "").strip()
        value = str(value or "").strip()
        if not column or is_person_column(column) or not plausible_value(value):
            return
        entry = self.items.setdefault((table, column), {"values": [], "origins": []})
        if value not in entry["values"]:
            entry["values"].append(value)
        if origin not in entry["origins"]:
            entry["origins"].append(origin)

    # ---------------------- SQL ----------------------

    def ingest_sql(self, sql, table=None):
        text = _strip_sql_comments(sql)
        for select_list in _select_lists(text):
            items = _split_top_level(select_list)
            outputs = []
            for item in items:
                compact = " ".join(item.split())
                alias = self._item_alias(compact)
                if alias:
                    outputs.append(alias)
                if alias and re.search(r"\bCASE\b", compact, re.IGNORECASE):
                    for value in THEN_ELSE_RE.findall(compact):
                        self.add(table, alias, value.replace("''", "'"), "sql_case")
            self._ingest_conditions(text, outputs, table)

    @staticmethod
    def _item_alias(item):
        aliases = sql_select_aliases(f"SELECT {item} FROM X")
        return aliases[0] if aliases else None

    def _ingest_conditions(self, text, outputs, table):
        wanted = {alias.casefold(): alias for alias in outputs}
        if not wanted:
            return
        pattern = re.compile(
            r"(?:\b[\w]+\.)?\[?(\w+)\]?\s*(?:IN\s*\(([^()]*)\)|=\s*('(?:[^']|'')*'))",
            re.IGNORECASE,
        )
        for match in pattern.finditer(text):
            column = wanted.get(match.group(1).casefold())
            if not column:
                continue
            literals = SQL_STRING_RE.findall(match.group(2) or match.group(3) or "")
            for value in literals:
                self.add(table, column, value.replace("''", "'"), "sql_filter")

    # ---------------------- DAX ----------------------

    def ingest_dax(self, expression, *, output_table=None, output_column=None):
        expression = str(expression or "")
        # T[C] = "X" / T[C] <> "X" / T[C] IN {"A","B"}
        for match in re.finditer(
            r"('(?:[^']|'')+'|[A-Za-z_À-ÿ][\wÀ-ÿ]*)\s*\[([^\]]+)\]\s*(?:=|<>|==)\s*\"((?:[^\"]|\"\")*)\"",
            expression,
        ):
            table = match.group(1).strip("'")
            self.add(table, match.group(2), match.group(3).replace('""', '"'), "dax_literal")
        for match in re.finditer(
            r"('(?:[^']|'')+'|[A-Za-z_À-ÿ][\wÀ-ÿ]*)\s*\[([^\]]+)\]\s+IN\s*\{([^}]*)\}",
            expression, re.IGNORECASE,
        ):
            table = match.group(1).strip("'")
            for value in DAX_STRING_RE.findall(match.group(3)):
                self.add(table, match.group(2), value.replace('""', '"'), "dax_literal")
        # Textos que devuelve una columna calculada (IF/SWITCH): los literales
        # que no se comparan con ninguna columna son salidas.
        if output_column:
            compared = set()
            for match in re.finditer(r"(?:=|<>|IN\s*\{)\s*\"((?:[^\"]|\"\")*)\"", expression, re.IGNORECASE):
                compared.add(match.group(1))
            for value in DAX_STRING_RE.findall(expression):
                if value not in compared and value.strip() not in (" ", ""):
                    self.add(output_table, output_column, value.replace('""', '"'), "dax_output")

    # ---------------------- documentos ----------------------

    def ingest_documents(self, documents, sql_tables=None):
        """sql_tables: {id(sql): tabla} cuando la inferencia sabe dónde cayó cada SELECT."""
        sql_tables = sql_tables or {}
        for document in documents:
            for dashboard in document.get("dashboards", []) or []:
                for sql in dashboard.get("sql_queries", []) or []:
                    self.ingest_sql(sql, sql_tables.get(sql))
                for item in dashboard.get("documented_measures", []) or []:
                    self.ingest_dax(item.get("expression"))
                for item in dashboard.get("calculated_columns", []) or []:
                    expression = item.get("expression")
                    name = re.sub(r"\s*=\s*$", "", str(item.get("name") or "")).strip()
                    table = item.get("table")
                    if not table:
                        refs = dax_references(expression)
                        table = refs[0][0] if refs else None
                    self.ingest_dax(expression, output_table=table, output_column=name)
        return self

    def ingest_model(self, model):
        """DAX de las medidas y columnas calculadas del modelo intermedio."""
        for table in model.get("tables", []):
            for measure in table.get("measures", []):
                self.ingest_dax(measure.get("expression"))
            for column in table.get("columns", []):
                if column.get("type") == "Calculated":
                    self.ingest_dax(column.get("expression"), output_table=table["name"],
                                    output_column=column["name"])
        return self

    def by_table_column(self, model=None):
        """{(tabla, columna): valores}; las entradas sin tabla se reparten a
        las tablas del modelo que tienen esa columna."""
        result = OrderedDict()
        for (table, column), entry in self.items.items():
            targets = []
            if table:
                targets.append((table, column))
            elif model is not None:
                for model_table in model.get("tables", []):
                    for model_column in model_table.get("columns", []):
                        if model_column["name"].casefold() == column.casefold():
                            targets.append((model_table["name"], model_column["name"]))
            for target in targets:
                values = result.setdefault(target, [])
                for value in entry["values"]:
                    if value not in values:
                        values.append(value)
        return result

    def to_payload(self, model_name):
        columns = [
            {"table": table, "column": column, "values": entry["values"], "origins": entry["origins"]}
            for (table, column), entry in self.items.items()
        ]
        return {
            "semantic_model": model_name,
            "source": "documentation",
            "description": (
                "Valores categóricos citados en la documentación (CASE/IN del SQL y "
                "literales DAX). table=null: aplica a las columnas con ese nombre."
            ),
            "columns": columns,
        }

    def save(self, model_name, model_dir):
        payload = self.to_payload(model_name)
        if payload["columns"]:
            save_json(payload, model_dir / "_documented_values.json")
        return len(payload["columns"])
