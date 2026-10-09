"""
Indicadores y visuales INFERIDOS de la documentación, para modelos que solo
tienen documentación (sin TMDL, sin export de INFO.VIEW y sin reporte PBIR).

Sin visuales, las medidas de esos modelos quedan como "auxiliares" (sin
apariciones en un tablero) y sus columnas numéricas no generan ninguna
métrica: el chatbot no puede responder «cuánto peso hay en lavandería».
En Power BI el propietario sí tiene esos indicadores; aquí se reconstruyen
SOLO a partir de lo que el docx describe:

  1. Indicadores de tarjetas/visuales documentados («Las tarjetas muestran el
     total de dosis de antibióticos suministradas y la cantidad de pacientes
     activos») -> se enlazan a una medida documentada cuya descripción
     comparte el sustantivo principal (TOTAL ATB: «Número total de dosis...»).
  2. Una columna numérica citada por el visual («distribución de pesos
     registrados», «Peso por Turno Laboral») -> agregación implícita del
     visual (SUM; AVERAGE si se habla de promedio/tiempo), como hace Power BI
     al arrastrar la columna.
  3. «Total/cantidad/número de <entidad> [con <calificador>]» -> conteo de la
     tabla de esa entidad (DISTINCTCOUNT de su OID o COUNTROWS) y, si el
     calificador coincide con un único valor literal documentado de una
     columna («con aumento» -> ESTADO = "AUMENTÓ"), una medida con ese filtro.
  4. «... por <X>» -> columna de categoría X del visual; «Filtros por A, B y
     C» -> segmentadores.

Todo lo creado queda marcado con el origen `inferred_from_documentation`
(DisplayFolder de las medidas, `inferred` en cada visual.json y resumen en
_metadata_sync.json). Si la documentación no respalda una pieza, no se crea.

El resultado (`InferredReport`) se materializa como un PBIR mínimo en
data/pbir/<Reporte>.Report: así el pipeline del propietario
(PowerBICatalogManager) construye el catálogo visual y master_metrics.json
igual que con un reporte real.
"""
import hashlib
import json
import re
from pathlib import Path

from tools.local_data.metadata_format import (
    find_column,
    find_measure,
    infer_measure_data_type,
    new_column,
    new_measure,
    normalize_text,
)


ORIGIN = "inferred_from_documentation"

# Palabras sin contenido para comparar frases de la documentación con
# nombres de medidas, tablas y columnas.
STOPWORDS = {
    "a", "al", "con", "de", "del", "e", "el", "en", "la", "las", "lo", "los",
    "o", "para", "por", "segun", "su", "sus", "un", "una", "y", "que", "se",
    "cada", "total", "totales", "cantidad", "numero", "n", "registrado",
    "registrados", "registradas", "registrada", "periodo", "seleccionado",
    "seleccionados", "filtros", "filtro", "aplicados", "acuerdo", "general",
    "mensual", "mensuales", "mensualmente", "valor", "indicador", "indicadores",
    "muestra", "muestran", "presenta", "presentan", "areas", "area", "tipo",
}

# Palabras de periodo: una agrupación «por mes» la resuelve el chatbot con
# las columnas de fecha, no es una categoría del visual.
DATE_WORDS = {
    "ano", "anos", "anio", "mes", "meses", "mensual", "dia", "dias", "fecha",
    "trimestre", "semana", "semanal", "periodo", "hora", "tramo", "horario",
}

# Sustantivos que no nombran una entidad contable («detalle de solicitudes»,
# «porcentaje de atenciones», «tendencia de costos»).
NON_ENTITY_HEADS = {
    "detalle", "listado", "registro", "distribucion", "porcentaje", "tendencia",
    "comportamiento", "relacion", "informacion", "indice", "volatilidad",
    "participacion", "variacion", "promedio", "proporcion", "evolucion", "carga",
    "consolidado", "resumen", "estado", "tiempo",
}

# Columnas de personas: solo se aceptan como categoría vía sinónimo explícito
# («por cada colaborador» -> NOMBRE_COMPLETO).
PERSON_COLUMN_RE = re.compile(
    r"nombre|apellido|documento|identificacion|cedula|usuario|usu_|medico|gpanom|pacnum",
    re.IGNORECASE,
)

# Sinónimos de negocio -> fragmentos de nombres de columna habituales (en
# orden de preferencia).
DIMENSION_SYNONYMS = {
    "asegurador": ("asegura", "eps", "ternom", "tercero", "entidad", "entnombre", "pagador"),
    "aseguradora": ("asegura", "eps", "ternom", "tercero", "entidad", "entnombre", "pagador"),
    "eps": ("eps", "asegura", "ternom", "tercero", "entidad"),
    "servicio": ("servicio", "hsunombre", "gdpnombre"),
    "colaborador": ("nombre_completo", "nombre completo"),
    "usuario": ("nombre_completo", "nombre completo"),
    "antibiotico": ("antibiotico",),
    "clasificacion": ("clasificacion",),
    "especialidad": ("especialidad", "geedescri"),
    "estado": ("estado",),
    "causa": ("causa",),
    "turno": ("turno",),
    "producto": ("iprdescor", "producto"),
}

LEAD_RE = re.compile(
    r"\b(total|cantidad|n[uú]mero|promedio)(?:\s+(?:mensual|total|diari[ao]|anual))?\s+de\s+",
    re.IGNORECASE,
)
DISTRIBUTION_RE = re.compile(
    r"\bdistribuci[oó]n(?:\s+porcentual)?(?:\s+y\s+cantidad)?\s+de\s+",
    re.IGNORECASE,
)
PHRASE_END_RE = re.compile(
    r",|;|\.(?:\s|$)|:|\(|"
    r"\s+y\s+(?:el|la|los|las|cuenta|incluye|permite|muestra|presenta|su)\b|"
    r"\s+(?:de\s+acuerdo|seg[uú]n|permitiendo|junto|ofreciendo|facilitando|"
    r"que\s+permite|en\s+el\s+per[ií]odo|en\s+la\s+instituci[oó]n|dentro|"
    r"teniendo|obteniendo|utilizando|desagregad[oa]s?|asignad[oa]s?\s+a)\b",
    re.IGNORECASE,
)
TYPE_PREFIX_RE = re.compile(
    r"^\s*(?:tablas?|gr[aá]fic[oa]s?|treemap|matriz|tarjetas?|mapa|diagrama)"
    r"(?:\s+(?:circular|de\s+barras|de\s+columnas|de\s+l[ií]neas|de\s+dispersi[oó]n|"
    r"de\s+calor|de\s+detalle|de\s+registro))*"
    r"\s*(?:[–\-:]\s*|\bdel?\s+)?",
    re.IGNORECASE,
)
FILTER_LIST_RE = re.compile(
    r"\b(?:filtros?|segmentaciones|segmentadores?|segmentar(?:\s+la\s+informaci[oó]n)?)"
    r"\s+(?:de|por)\s+(.+?)(?:,\s+(?:que|permit|facilit)|\s+que\b|\s+permit|\s+facilit|\.|$)",
    re.IGNORECASE,
)


# ============================================================
# TEXTO
# ============================================================

def split_identifier(name):
    """'OidUsuario' -> 'oid usuario'; 'NOMBRE_COMPLETO' -> 'nombre completo'."""
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", str(name or ""))
    return normalize_text(text.replace("_", " "))


def stem(token):
    token = normalize_text(token)
    if len(token) > 5 and token.endswith("es") and token[-3] in "dlnrz":
        return token[:-2]
    if len(token) > 4 and token.endswith("s"):
        return token[:-1]
    return token


def tokens(text, *, keep_stopwords=False):
    result = []
    for token in normalize_text(text).split():
        if not keep_stopwords and (token in STOPWORDS or len(token) < 2):
            continue
        result.append(stem(token))
    return result


def similar(left, right):
    """Igualdad de raíces o prefijo común largo («disminución» ~ «disminuyó»)."""
    if not left or not right:
        return False
    if left == right:
        return True
    common = 0
    for a, b in zip(left, right):
        if a != b:
            break
        common += 1
    return common >= 5 and common >= 0.75 * min(len(left), len(right))


def overlap(phrase_tokens, other_tokens):
    return [token for token in phrase_tokens if any(similar(token, o) for o in other_tokens)]


def _capitalize(text):
    text = " ".join(str(text or "").split())
    return text[:1].upper() + text[1:]


def _visual_id(*parts):
    return hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:20]


# ============================================================
# VISUALES DOCUMENTADOS
# ============================================================

def parse_documented_visuals(dashboard):
    """[{title, description}] desde dashboard['visuals'] ('Título: descripción')."""
    items = []
    for raw in dashboard.get("visuals", []) or []:
        text = " ".join(str(raw or "").split())
        if not text:
            continue
        title, separator, description = text.partition(":")
        starts_like_description = re.match(
            r"^(muestra|presenta|incluye|permite|filtran|las?\s|los?\s)", normalize_text(text)
        )
        if separator and len(title) <= 120 and not starts_like_description:
            items.append({"title": title.strip(), "description": description.strip()})
        elif items and starts_like_description:
            previous = items[-1]
            previous["description"] = f"{previous['description']} {text}".strip()
        else:
            items.append({"title": text, "description": ""})
    return items


NAVIGATION_RE = r"\b(boton|botones|navegacion|marcador|control|encabezado|resumen|seccion)\b"


def visual_kind(title):
    text = normalize_text(title)
    if re.search(r"\b(tarjeta|tarjetas|indicador|indicadores)\b", text):
        return "card"
    if re.search(r"\b(filtro|filtros|segmentacion|segmentaciones|segmentador)\b", text):
        return "slicer"
    if re.search(NAVIGATION_RE, text):
        return "other"
    if re.search(r"\b(tabla|matriz)\b", text):
        return "table"
    if re.search(r"\b(grafico|treemap|mapa|diagrama)\b", text):
        return "chart"
    return "other"


def clean_title(title):
    text = TYPE_PREFIX_RE.sub("", str(title or ""), count=1).strip(" –-:")
    text = re.sub(r"^(?:por|de)\s+", "", text, flags=re.IGNORECASE)
    return _capitalize(text)


def split_dimensions(text):
    """'Año, Mes y Causa' -> ['Año', 'Mes', 'Causa']."""
    parts = re.split(r",|\s+y\s+|\s+e\s+|\(", str(text or ""))
    result = []
    for part in parts:
        # «cada colaborador de las áreas del hospital» -> «cada colaborador»
        part = re.split(r"\s+(?:de\s+(?:la|las|los|el)|del)\s+", part, maxsplit=1)[0]
        part = part.strip(" .)")
        if part and len(part.split()) <= 4:
            result.append(part)
    return result


def indicator_phrases(text, *, distribution=False):
    """[(lead, frase, dimensiones)] de una descripción («el total de X por Y»)."""
    results = []
    patterns = [LEAD_RE] + ([DISTRIBUTION_RE] if distribution else [])
    spans = []
    for pattern in patterns:
        for match in pattern.finditer(str(text or "")):
            spans.append((match.start(), match.end(), match.group(1) if pattern is LEAD_RE else "Total"))
    spans.sort()
    for start, end, lead in spans:
        rest = str(text)[end:]
        stop = PHRASE_END_RE.search(rest)
        phrase = rest[: stop.start()] if stop else rest
        phrase, _, dims = phrase.partition(" por ")
        phrase = re.sub(r"^(?:el|la|los|las)\s+", "", phrase.strip(), flags=re.IGNORECASE)
        if not phrase or len(phrase) > 90:
            continue
        lead_word = normalize_text(lead)
        lead_word = {"numero": "Número", "cantidad": "Cantidad",
                     "promedio": "Promedio"}.get(lead_word, "Total")
        results.append((lead_word, phrase, split_dimensions(dims)))
    return results


def filter_dimensions(text):
    """Columnas citadas en «Filtros por A, B y C» / «segmentaciones de A, B y C»."""
    result = []
    for match in FILTER_LIST_RE.finditer(str(text or "")):
        for item in split_dimensions(match.group(1)):
            if item not in result:
                result.append(item)
    return result


# ============================================================
# INFERENCIA
# ============================================================

class DocumentedReportInference:
    """Indicadores y visuales de un modelo inferido solo de documentación."""

    def __init__(self, model, origins=None, documented_values=None):
        self.model = model
        self.origins = origins or {}
        # {(tabla, columna): [valores literales documentados]}
        self.documented_values = documented_values or {}
        self.pages = []
        self.added_measures = []
        self.added_columns = []
        self.links = []

    # ---------------------- índices del modelo ----------------------

    def _tables(self):
        return [
            table for table in self.model["tables"]
            if not table["name"].lower().startswith(("localdatetable_", "datetabletemplate_"))
        ]

    @staticmethod
    def _is_id(column_name):
        words = split_identifier(column_name).split()
        compact = normalize_text(column_name).replace(" ", "")
        return bool(words) and (
            words[0] in {"oid", "id"} or words[-1] in {"oid", "id"}
            or compact.startswith("oid") or compact.endswith("oid")
        )

    def _exact_id(self, table):
        names = {normalize_text(table["name"]).replace(" ", "")}
        for column in table["columns"]:
            words = split_identifier(column["name"]).split()
            if words in (["oid"], ["id"]):
                return column
            if len(words) == 2 and "oid" in words and words[1 - words.index("oid")].replace(" ", "") in names:
                return column
        return None

    def _numeric_columns(self):
        for table in self._tables():
            for column in table["columns"]:
                if column["data_type"] not in ("Integer", "Number", "Decimal"):
                    continue
                if self._is_id(column["name"]):
                    continue
                words = split_identifier(column["name"]).split()
                if not words or set(words) & DATE_WORDS or words[0] in {"rn", "validador"}:
                    continue
                yield table, column

    def _table_tokens(self, table):
        return tokens(split_identifier(table["name"]))

    def _schema_unknown(self, table):
        """Tabla sin columnas del SQL ni del reporte (solo citadas en DAX)."""
        return not any(
            self.origins.get((table["name"], column["name"])) in ("sql", "report")
            for column in table["columns"]
        )

    def _schema_unknown_by_name(self, table_name):
        table = next((t for t in self.model["tables"] if t["name"] == table_name), None)
        return table is not None and self._schema_unknown(table)

    def _documented_measures(self):
        for table in self.model["tables"]:
            for measure in table["measures"]:
                yield table, measure

    # ---------------------- resolución de un indicador ----------------------

    def _match_measure(self, phrase_tokens):
        if not phrase_tokens:
            return None
        head = phrase_tokens[0]
        best, best_score, tie = None, 0, False
        for table, measure in self._documented_measures():
            name_tokens = tokens(split_identifier(measure["name"]))
            other = name_tokens + tokens(measure.get("description") or "")
            if not any(similar(head, token) for token in other):
                continue
            score = len(overlap(phrase_tokens, other)) + len(overlap(phrase_tokens, name_tokens))
            if score < 2:
                continue
            if score > best_score:
                best, best_score, tie = (table, measure), score, False
            elif score == best_score:
                tie = True
        return None if tie else best

    def _match_numeric_column(self, phrase_tokens):
        """Columna numérica cuyo nombre completo describe la frase («pesos» ~ Peso)."""
        if not phrase_tokens:
            return None
        head = phrase_tokens[0]
        matches = []
        for table, column in self._numeric_columns():
            column_tokens = tokens(split_identifier(column["name"]))
            if column_tokens and any(similar(head, token) for token in column_tokens) and all(
                any(similar(token, p) for p in phrase_tokens) for token in column_tokens
            ):
                matches.append((table, column))
        return matches[0] if len(matches) == 1 else None

    def _ids_for(self, head, table=None):
        """Columnas OID cuyo nombre nombra la entidad (OID_TRIAGE, OIDPRODUCTO)."""
        tables = [table] if table is not None else self._tables()
        result = []
        for t in tables:
            for column in t["columns"]:
                if not self._is_id(column["name"]):
                    continue
                words = tokens(split_identifier(column["name"]))
                compact = normalize_text(column["name"]).replace(" ", "")
                core = re.sub(r"^oid|oid$", "", compact)
                if any(similar(head, token) for token in words + ([stem(core)] if core else [])):
                    result.append((t, column))
        return result

    def _match_entity_table(self, phrase_tokens, dashboard_name, *, fallback):
        head = phrase_tokens[0] if phrase_tokens else None
        if head and head not in NON_ENTITY_HEADS:
            scored = []
            for table in self._tables():
                table_tokens = self._table_tokens(table)
                if any(similar(head, token) for token in table_tokens):
                    scored.append((len(overlap(phrase_tokens, table_tokens)), -len(table_tokens), table))
            if scored:
                scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
                if len(scored) == 1 or scored[0][:2] != scored[1][:2]:
                    table = scored[0][2]
                    # «productos» en COSTOS_PRODUCTOS: la entidad es solo parte
                    # de la tabla -> conteo distinto de su OID (OIDPRODUCTO).
                    ids = self._ids_for(head, table)
                    if len(self._table_tokens(table)) > 1 and len(ids) == 1:
                        return ids[0], "entity_id"
                    return table, "entity_table"

            ids = self._ids_for(head)
            if len(ids) == 1:
                return ids[0], "entity_id"

        if not fallback:
            return None, None

        dashboard_tokens = tokens(dashboard_name)
        for table in self._tables():
            table_tokens = self._table_tokens(table)
            if table_tokens and dashboard_tokens and all(
                any(similar(t, d) for d in dashboard_tokens) for t in table_tokens
            ):
                return table, "dashboard_table"

        tables = [table for table in self._tables() if table["columns"]]
        if len(tables) == 1:
            return tables[0], "single_table"
        return None, None

    def _qualifier_filter(self, table_name, qualifier_tokens, raw_phrase):
        """Único (tabla, columna, valor) documentado que coincide con el calificador."""
        if not qualifier_tokens or re.search(r"\bno\b|\bsin\b", normalize_text(raw_phrase)):
            return None
        matches = []
        for (value_table, column_name), values in self.documented_values.items():
            if table_name and value_table.casefold() != table_name.casefold():
                continue
            for value in values:
                value_tokens = tokens(value)
                if value_tokens and all(any(similar(q, v) for v in value_tokens) for q in qualifier_tokens):
                    matches.append((value_table, column_name, value))
        unique = sorted(set(matches))
        return unique[0] if len(unique) == 1 else None

    def resolve(self, lead, phrase, dashboard_name, *, fallback=False):
        """
        Valor de un indicador documentado. Las medidas nuevas no se crean aquí:
        el resultado trae `new_measure` y se agregan al emitir el visual.
        fallback: solo para tarjetas («el total de X»), permite contar la tabla
        del tablero o la única tabla del modelo cuando X no nombra una tabla.
        """
        phrase_tokens = tokens(phrase)
        if not phrase_tokens:
            return None
        head = phrase_tokens[0]

        match = self._match_measure(phrase_tokens)
        if match:
            table, measure = match
            return {"kind": "measure", "table": table["name"], "measure": measure["name"],
                    "rule": "documented_measure"}

        # «compras con aumento»: un calificador que es un valor documentado
        # convierte el indicador en un conteo filtrado (no en una suma).
        qualifier_any = self._qualifier_filter(None, phrase_tokens[1:], phrase)

        match = None if qualifier_any else self._match_numeric_column(phrase_tokens)
        if match:
            table, column = match
            text = normalize_text(f"{lead} {phrase} {column['name']}")
            aggregation = "Average" if re.search(r"\b(promedio|tiempo|media)\b", text) else "Sum"
            return {"kind": "aggregation", "table": table["name"], "column": column["name"],
                    "aggregation": aggregation, "rule": "numeric_column"}

        # Un promedio sin columna numérica que lo respalde no se convierte en conteo.
        if lead == "Promedio":
            return None
        if head in NON_ENTITY_HEADS and not fallback:
            return None

        target, rule = self._match_entity_table(phrase_tokens, dashboard_name, fallback=fallback)
        if target is None:
            return None
        if rule == "entity_id":
            table, column = target
            return {"kind": "aggregation", "table": table["name"], "column": column["name"],
                    "aggregation": "DistinctCount", "rule": rule}

        table = target
        qualifier = [token for token in phrase_tokens[1:]
                     if not any(similar(token, t) for t in self._table_tokens(table))]
        condition = self._qualifier_filter(table["name"], qualifier, phrase)
        id_column = self._exact_id(table)
        table_ref = "'" + table["name"].replace("'", "''") + "'"
        if id_column is not None:
            base = f"DISTINCTCOUNT({table_ref}[{id_column['name']}])"
        else:
            base = f"COUNTROWS({table_ref})"

        if condition is None and id_column is not None:
            return {"kind": "aggregation", "table": table["name"], "column": id_column["name"],
                    "aggregation": "DistinctCount", "rule": rule}

        if condition is not None:
            _table, column_name, value = condition
            escaped = str(value).replace('"', '""')
            expression = f'CALCULATE({base}, {table_ref}[{column_name}] = "{escaped}")'
        else:
            expression = base
        name = _capitalize(f"{lead} de {phrase}")
        return {"kind": "measure", "table": table["name"], "measure": name,
                "rule": rule + ("+documented_value" if condition else ""),
                "new_measure": {"expression": expression, "phrase": phrase}}

    def _materialize(self, value):
        """Crea la medida inferida de un valor (si hace falta). False si no se puede."""
        spec = value.get("new_measure")
        if not spec:
            return True
        table = next(t for t in self.model["tables"] if t["name"] == value["table"])
        name = value["measure"]
        owner, existing = find_measure(self.model, name)
        if existing is not None:
            return True
        if any(find_column(t, name) is not None for t in self.model["tables"]):
            return False
        measure = new_measure(
            name,
            expression=spec["expression"],
            description=f"Inferida de la documentación: {spec['phrase']}.",
            display_folder=ORIGIN,
        )
        measure["data_type"] = infer_measure_data_type(spec["expression"])
        table["measures"].append(measure)
        self.added_measures.append({"table": table["name"], "measure": name,
                                    "expression": spec["expression"], "rule": value["rule"]})
        return True

    # ---------------------- dimensiones ----------------------

    def resolve_dimension(self, text, table_name=None, *, allow_add=False):
        words = [w for w in normalize_text(text).split() if w not in STOPWORDS]
        if not words or set(words) & DATE_WORDS or set(stem(w) for w in words) & DATE_WORDS:
            return None
        dim_tokens = [stem(w) for w in words]
        synonyms = []
        for word in words:
            synonyms.extend(DIMENSION_SYNONYMS.get(word, ()))
            synonyms.extend(DIMENSION_SYNONYMS.get(stem(word), ()))

        # Sin relaciones (metadata inferida), una categoría de otra tabla no
        # filtraría el valor: con tabla dada solo se busca en ella.
        tables = self._tables()
        if table_name:
            tables = [t for t in tables if t["name"].casefold() == table_name.casefold()]

        for table in tables:
            candidates = []
            for column in table["columns"]:
                if column["data_type"] not in ("Text", "String") or self._is_id(column["name"]):
                    continue
                column_text = split_identifier(column["name"])
                compact = normalize_text(column["name"])
                column_tokens = tokens(column_text)
                direct = bool(column_tokens) and all(
                    any(similar(d, c) for c in column_tokens) for d in dim_tokens
                )
                synonym_rank = next(
                    (rank for rank, s in enumerate(synonyms) if s in column_text or s in compact),
                    None,
                )
                person = bool(PERSON_COLUMN_RE.search(column["name"]))
                if person and synonym_rank is None:
                    continue
                if direct or synonym_rank is not None:
                    candidates.append((
                        0 if direct else 1,
                        synonym_rank if synonym_rank is not None else 0,
                        0 if column["type"] == "Calculated" else 1,
                        len(column["name"]),
                        column["name"],
                    ))
            if candidates:
                candidates.sort()
                return table["name"], candidates[0][-1]
            if table_name and allow_add and self._schema_unknown(table):
                # Tabla cuyo esquema no documenta el SQL (SELECT * ...): la
                # categoría que el visual describe se agrega como columna.
                name = "_".join(normalize_text(text).upper().split())
                if not name:
                    return None
                column = new_column(name, data_type="Text", summarize_by="None",
                                    description=f"Inferida de la documentación: «{text}».")
                table["columns"].append(column)
                self.origins[(table["name"], name)] = "documented_visual"
                self.added_columns.append({"table": table["name"], "column": name})
                return table["name"], name
        return None

    # ---------------------- recorrido de la documentación ----------------------

    @staticmethod
    def _page_indicator(page_indicators, phrase):
        """Valor de una tarjeta de la página que cubre todas las palabras de la frase."""
        phrase_tokens = tokens(phrase)
        if not phrase_tokens:
            return None
        matches = [
            value for card_tokens, value in page_indicators
            if all(any(similar(token, c) for c in card_tokens) for token in phrase_tokens)
        ]
        return matches[0] if len(matches) == 1 else None

    def ingest(self, documents):
        for document in documents:
            for dashboard in document.get("dashboards", []) or []:
                self._ingest_dashboard(dashboard)
        return self

    def _ingest_dashboard(self, dashboard):
        page_name = str(dashboard.get("name") or "Tablero").strip()
        visuals = []
        slicer_columns = []
        page_indicators = []   # [(tokens de la tarjeta, valor)]

        for item in parse_documented_visuals(dashboard):
            title, description = item["title"], item["description"]
            kind = visual_kind(title)

            for dimension in filter_dimensions(f"{title}. {description}"):
                resolved = self.resolve_dimension(dimension)
                if resolved and resolved not in slicer_columns:
                    slicer_columns.append(resolved)

            if kind == "slicer":
                continue
            # Las tablas de detalle listan registros: no documentan un indicador.
            if kind == "table" and re.search(r"\b(detalle|listado)\b", normalize_text(title)):
                continue

            phrases = [
                (lead, phrase, dims, kind in ("card", "other"))
                for lead, phrase, dims in indicator_phrases(
                    description, distribution=kind in ("chart", "table"))
            ]
            if kind in ("chart", "table"):
                cleaned = clean_title(title)
                indicator, _, dims = cleaned.partition(" por ")
                phrases.append(("Total", indicator.strip(), split_dimensions(dims), False))

            resolved_values = []
            for lead, phrase, dims, fallback in phrases:
                if not phrase:
                    continue
                value = self.resolve(lead, phrase, page_name, fallback=fallback)
                if value is None and not fallback:
                    # «No aceptados por causa» / «pacientes no aceptados»: el
                    # mismo indicador que una tarjeta de la página.
                    value = self._page_indicator(page_indicators, phrase)
                if value is None:
                    continue
                key = (value["kind"], value["table"], value.get("measure"), value.get("column"),
                       value.get("aggregation"))
                if any(existing[0] == key for existing in resolved_values):
                    continue
                resolved_values.append((key, value, lead, phrase, dims))

            if not resolved_values:
                continue

            if kind in ("card", "other"):
                # «Cantidad de solicitudes: muestra el total de ...» -> la
                # tarjeta se llama como el indicador documentado.
                named = (
                    kind == "other" and len(resolved_values) == 1 and len(title.split()) <= 6
                    and not re.search(NAVIGATION_RE, normalize_text(title))
                )
                for key, value, lead, phrase, _dims in resolved_values:
                    if not self._materialize(value):
                        continue
                    card_title = _capitalize(title) if named else _capitalize(f"{lead} de {phrase}")
                    page_indicators.append((tokens(phrase) + tokens(card_title), value))
                    visuals.append(self._visual(
                        page_name, "card", card_title,
                        [self._value_field(value, "Values")],
                        source=f"{title}: {description}",
                    ))
                continue

            # Gráficos y tablas: un valor (el primero resuelto) + categorías.
            key, value, lead, phrase, dims = resolved_values[0]
            all_dims = list(dims)
            for _lead, _phrase, extra, _fallback in phrases:
                for dimension in extra:
                    if dimension not in all_dims:
                        all_dims.append(dimension)
            # Una tabla sin categoría reconocible no se reconstruye.
            if kind == "table" and not self._schema_unknown_by_name(value["table"]) and not any(
                self.resolve_dimension(dimension, value["table"]) for dimension in all_dims
            ):
                continue
            if not self._materialize(value):
                continue
            categories = []
            for dimension in all_dims:
                resolved = self.resolve_dimension(dimension, value["table"], allow_add=True)
                if resolved and resolved not in categories:
                    categories.append(resolved)
            # Las agregaciones implícitas de una columna numérica se dejan sin
            # título (Power BI muestra «Suma de Peso por SERVICIO»): todas las
            # apariciones forman una sola métrica «Peso».
            title_text = None if value["kind"] == "aggregation" and value["rule"] == "numeric_column" \
                else clean_title(title)
            fields = [self._column_field(t, c, "Category" if kind == "chart" else "Values")
                      for t, c in categories]
            fields.append(self._value_field(value, "Y" if kind == "chart" else "Values"))
            visuals.append(self._visual(
                page_name,
                "clusteredBarChart" if kind == "chart" else "tableEx",
                title_text,
                fields,
                source=f"{title}: {description}",
            ))

        for table_name, column_name in slicer_columns:
            visuals.append(self._visual(
                page_name, "slicer", None,
                [self._column_field(table_name, column_name, "Values")],
                source="filtros documentados",
            ))

        if visuals:
            self.pages.append({"name": page_name, "visuals": visuals})

    # ---------------------- campos PBIR ----------------------

    @staticmethod
    def _source_ref(table):
        return {"SourceRef": {"Entity": table}}

    def _column_field(self, table, column, role):
        return {
            "role": role,
            "field": {"Column": {"Expression": self._source_ref(table), "Property": column}},
            "queryRef": f"{table}.{column}",
            "nativeQueryRef": column,
        }

    def _value_field(self, value, role):
        table = value["table"]
        if value["kind"] == "measure":
            return {
                "role": role,
                "field": {"Measure": {"Expression": self._source_ref(table), "Property": value["measure"]}},
                "queryRef": f"{table}.{value['measure']}",
                "nativeQueryRef": value["measure"],
            }
        function = {"Sum": 0, "Average": 1, "DistinctCount": 2, "Count": 5}[value["aggregation"]]
        query_name = {"Sum": "Sum", "Average": "Avg", "DistinctCount": "CountNonNull", "Count": "Count"}
        return {
            "role": role,
            "field": {"Aggregation": {
                "Expression": {"Column": {"Expression": self._source_ref(table), "Property": value["column"]}},
                "Function": function,
            }},
            "queryRef": f"{query_name[value['aggregation']]}({table}.{value['column']})",
            "nativeQueryRef": value["column"],
        }

    def _visual(self, page, visual_type, title, fields, *, source):
        visual = {
            "page": page,
            "visual_type": visual_type,
            "title": title,
            "fields": fields,
            "source": " ".join(str(source).split())[:300],
        }
        for field in fields:
            entry = {"page": page, "title": title, "visual_type": visual_type,
                     "query_ref": field["queryRef"], "role": field["role"]}
            self.links.append(entry)
        return visual

    def summary(self):
        return {
            "origin": ORIGIN,
            "pages": len(self.pages),
            "visuals": sum(len(page["visuals"]) for page in self.pages),
            "added_measures": self.added_measures,
            "added_columns": self.added_columns,
            "fields": self.links,
        }


def infer_documented_report(model, documents, *, origins=None, documented_values=None):
    inference = DocumentedReportInference(model, origins=origins, documented_values=documented_values)
    inference.ingest(documents)
    return inference


# ============================================================
# PBIR MÍNIMO
# ============================================================

def write_inferred_report(report_name, pages, report_root, *, semantic_model=None):
    """
    Materializa las páginas inferidas como PBIR (definition/pages/*/visuals/*)
    en report_root/<report_name>.Report. Devuelve la carpeta del reporte.
    """
    report = Path(report_root) / f"{report_name}.Report"
    definition = report / "definition"
    (definition / "pages").mkdir(parents=True, exist_ok=True)
    marker = {"origin": ORIGIN, "semantic_model": semantic_model,
              "note": "Reporte reconstruido de la documentación; no es el PBIR real."}
    (definition / "report.json").write_text(
        json.dumps({"inferred": marker}, ensure_ascii=False, indent=2), encoding="utf-8")

    order = []
    for page in pages:
        page_name = f"ReportSection{_visual_id(report_name, page['name'])}"
        order.append(page_name)
        page_dir = definition / "pages" / page_name
        (page_dir / "visuals").mkdir(parents=True, exist_ok=True)
        (page_dir / "page.json").write_text(json.dumps(
            {"name": page_name, "displayName": page["name"], "inferred": marker},
            ensure_ascii=False, indent=2), encoding="utf-8")
        for index, item in enumerate(page["visuals"], 1):
            visual_name = _visual_id(report_name, page["name"], index, item["visual_type"], item["title"])
            roles = {}
            for field in item["fields"]:
                roles.setdefault(field["role"], {"projections": []})["projections"].append({
                    "field": field["field"],
                    "queryRef": field["queryRef"],
                    "nativeQueryRef": field["nativeQueryRef"],
                })
            visual = {"visualType": item["visual_type"], "query": {"queryState": roles}}
            if item["title"]:
                visual["visualContainerObjects"] = {"title": [{"properties": {
                    "text": {"expr": {"Literal": {"Value": "'" + item["title"].replace("'", "''") + "'"}}},
                }}]}
            visual_dir = page_dir / "visuals" / visual_name
            visual_dir.mkdir(parents=True, exist_ok=True)
            (visual_dir / "visual.json").write_text(json.dumps({
                "name": visual_name,
                "visual": visual,
                "inferred": dict(marker, documented_as=item["source"]),
            }, ensure_ascii=False, indent=2), encoding="utf-8")

    (definition / "pages" / "pages.json").write_text(json.dumps(
        {"pageOrder": order, "activePageName": order[0] if order else None}, indent=2), encoding="utf-8")
    return report
