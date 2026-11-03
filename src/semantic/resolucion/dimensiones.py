"""Etapa «filtros y agrupación» (base): dimensiones del indicador en el catálogo técnico.

Índice de dimensiones y alias, nombres de negocio de columnas, relaciones entre tablas
(_dimension_relation: nunca se agrupa por una tabla que no filtra la del indicador), columnas de la
propia tabla como respaldo (tmdl_real REFERENCIA[GEEDESCRI]) y _metric_dimensions. Mixin de
QueryPlanBuilder, métodos movidos sin cambios.
"""
import re

from src.semantic.resolucion.texto import (
    _exact_phrase,
    _original_phrase,
    _phrase_score,
    _unique_strings,
    canonical_tokens,
    DIMENSION_SYNONYMS,
    normalize_text,
    TECHNICAL_SUFFIXES,
    TEMPORAL_WORDS,
)


class DimensionesMixin:


    # ---------------- dimension index ----------------
    def _physical_column(self, field):
        if field.get("column"):
            return field.get("column")
        if field.get("kind") == "hierarchy_level":
            parts = [part for part in str(field.get("query_ref") or "").split(".") if part]
            if len(parts) >= 2:
                return parts[1]
        return None

    def _field_aliases(self, field):
        values = [
            field.get("display_name"), field.get("native_query_ref"),
            field.get("column"), field.get("level"), field.get("query_ref"),
        ]
        aliases = _unique_strings(values)
        normalized_aliases = {normalize_text(alias) for alias in aliases}
        # Sufijos técnicos (TURNO_OK, SERVICIO_ID): «turno» debe encontrar TURNO_OK.
        for alias in list(normalized_aliases):
            parts = alias.split()
            while len(parts) >= 2 and parts[-1] in TECHNICAL_SUFFIXES:
                parts = parts[:-1]
                aliases.append(" ".join(parts))
        normalized_aliases = {normalize_text(alias) for alias in aliases}
        for synonyms in DIMENSION_SYNONYMS.values():
            # Por palabra completa: OPORTUNIDAD no contiene «unidad».
            if any(
                re.search(r"(?<![a-z0-9])" + re.escape(synonym) + r"(?![a-z0-9])", alias)
                for alias in normalized_aliases for synonym in synonyms
            ):
                aliases.extend(sorted(synonyms))
        return _unique_strings(aliases)

    def _build_dimension_index(self):
        fields = []
        for report in self.reports:
            report_name = report.get("report") or report.get("semantic_model")
            semantic_model = report.get("semantic_model")
            source_group = report.get("source_group")
            for page in report.get("pages", []) or []:
                page_name = page.get("page_display_name") or page.get("page_name")
                for visual in page.get("visuals", []) or []:
                    for field in visual.get("fields", []) or []:
                        if field.get("kind") not in ("column", "hierarchy_level"):
                            continue
                        table = field.get("table")
                        column = self._physical_column(field)
                        if not table or not column:
                            continue
                        fields.append({
                            "semantic_model": semantic_model,
                            "report": report_name,
                            "source_group": source_group,
                            "page": page_name,
                            "visual_id": visual.get("visual_id"),
                            "visual_type": visual.get("visual_type"),
                            "role": field.get("role"),
                            "kind": field.get("kind"),
                            "table": table,
                            "column": column,
                            "level": field.get("level"),
                            "query_ref": field.get("query_ref"),
                            "display_name": field.get("display_name"),
                            "native_query_ref": field.get("native_query_ref"),
                            "aliases": self._field_aliases(field),
                        })
        # Campo sin nombre de negocio (la dona «HSUNOMBRE» de DETALLE OCUPACIÓN):
        # hereda los nombres con que otros visuales del modelo muestran esa
        # columna (HSUNOMBRE -> «SERVICIO»). Funciona con catálogos ya construidos.
        self._business_names_index = self._build_business_names_index(fields)
        for field in fields:
            names = [field.get("display_name"), field.get("native_query_ref")]
            if any(self._business_column_name(name, field.get("column")) for name in names):
                continue
            for name in self._column_business_names(
                field.get("semantic_model"), field.get("column"), field.get("table"),
            ):
                field["aliases"] = _unique_strings([*field["aliases"], *self._field_aliases({"display_name": name})])
        return fields

    @staticmethod
    def _business_column_name(name, column):
        """Nombre de negocio de una columna en un visual («ASEGURADORA» para
        TERNOMCOM), normalizado y sin dígitos finales («SERVICIO1»); None si es
        el nombre técnico, una agregación («Recuento de X», «Sum(T.C)») o vacío."""
        text = re.sub(r"\s*\d+$", "", str(name or "")).strip()
        norm = normalize_text(text)
        if (
            not norm or len(norm) < 3 or len(norm.split()) > 3 or "(" in text or "." in text
            or norm == normalize_text(column)
            or re.match(r"^(?:recuento|conteo|count|suma|sum|promedio|average|total)\b", norm)
        ):
            return None
        return text

    def _build_business_names_index(self, fields):
        index = {}
        for field in fields:
            key = (normalize_text(field.get("semantic_model")), normalize_text(field.get("column")))
            for name in (field.get("display_name"), field.get("native_query_ref")):
                business = self._business_column_name(name, field.get("column"))
                item = (normalize_text(field.get("table")), business)
                if business and item not in index.setdefault(key, []):
                    index[key].append(item)
                # Por nombre técnico en cualquier modelo (misma base de datos).
                if business and business not in index.setdefault(("*", key[1]), []):
                    index[("*", key[1])].append(business)
        return index

    @staticmethod
    def _technical_code_column(column):
        """Nombre técnico de una sola palabra que no es una palabra de negocio
        ni de tiempo (TERNOMCOM, HSUNOMBRE, HCACODIGO, GEEDESCRI): significa lo
        mismo en todas las tablas del modelo. FECHA o ESTADO no (cada tabla le
        da su propio sentido: «FECHA INGRESO», «ESTADO TRÁMITE»)."""
        norm = normalize_text(column)
        if not norm or " " in norm or len(norm) < 6 or norm in TEMPORAL_WORDS:
            return False
        return not any(norm in synonyms for synonyms in DIMENSION_SYNONYMS.values())

    def _column_business_names(self, semantic_model, column, table=None):
        """Nombres de negocio con que los visuales del modelo muestran una
        columna: los de la misma tabla y, si es un código técnico, los de
        cualquier tabla (TERNOMCOM -> «ASEGURADOR», «ASEGURADORA»; HSUNOMBRE
        -> «SERVICIO»). Sirve de alias en tiempo de ejecución sin reconstruir
        los catálogos (el catálogo visual ya guarda displayName/nativeQueryRef
        de cada columna)."""
        index = self.__dict__.get("_business_names_index")
        if index is None:
            index = self._business_names_index = self._build_business_names_index(self.dimension_fields or [])
        anywhere = self._technical_code_column(column)
        table = normalize_text(table)
        names = _unique_strings(
            name for owner, name in index.get((normalize_text(semantic_model), normalize_text(column)), [])
            if anywhere or not table or owner == table
        )
        if not names and anywhere:
            # Código técnico que este modelo nunca renombra (GEEDESCRI de
            # REFERENCIA): los nombres que le dan los visuales de otros modelos
            # («ESPECIALIDAD» en BRIEFING), si son pocos y coinciden.
            others = index.get(("*", normalize_text(column)), [])
            if 0 < len({normalize_text(name) for name in others}) <= 2:
                names = _unique_strings(others)
        return names

    def _iter_filters(self, value):
        if isinstance(value, list):
            for item in value:
                yield from self._iter_filters(item)
        elif isinstance(value, dict):
            if "field" in value and isinstance(value.get("field"), dict):
                yield value
            for item in value.values():
                yield from self._iter_filters(item)

    def _build_static_value_index(self):
        result = {}
        for report in self.reports:
            semantic_model = report.get("semantic_model")
            for page in report.get("pages", []) or []:
                for filter_item in self._iter_filters(page.get("filters", {})):
                    field = filter_item.get("field", {})
                    table = field.get("table")
                    column = field.get("column")
                    if not table or not column:
                        continue
                    key = (normalize_text(semantic_model), normalize_text(table), normalize_text(column))
                    result.setdefault(key, [])
                    for value in filter_item.get("values", []) or []:
                        if value is not None and str(value) not in result[key]:
                            result[key].append(str(value))
        return result

    def _relevant_dimensions(self, metric):
        semantic_model = metric.get("semantic_model")
        reports = {normalize_text(value) for value in self._metric_reports(metric)}
        pages = {normalize_text(value) for value in self._metric_pages(metric)}
        visual_ids = self._metric_visual_ids(metric)
        candidates = {}

        for field in self.dimension_fields:
            if normalize_text(field.get("semantic_model")) != normalize_text(semantic_model):
                continue
            if reports and normalize_text(field.get("report")) not in reports:
                continue

            score = 10
            if str(field.get("visual_id")) in visual_ids:
                score += 110
            if normalize_text(field.get("page")) in pages:
                score += 65
            if normalize_text(field.get("visual_type")) == "slicer":
                score += 35
            if normalize_text(field.get("role")) in {
                "category", "group", "rows", "legend", "series", "values"
            }:
                score += 15

            key = (
                normalize_text(field.get("table")),
                normalize_text(field.get("column")),
                normalize_text(field.get("level")),
            )
            item = {**field, "relevance_score": score}
            if key not in candidates or score > candidates[key]["relevance_score"]:
                candidates[key] = item

        values = list(candidates.values())
        values.sort(key=lambda item: item["relevance_score"], reverse=True)
        return values

    # ---------------- dimensiones del catálogo técnico ----------------
    _CALENDAR_TABLE_RE = re.compile(
        r"^(?:calendario|calendar|fecha|fechas|dates?|dim fecha|medidas|measures|"
        r"localdatetable.*|datetabletemplate.*)$"
    )
    # Columnas de personas/identificadores: nunca se ofrecen como dimensión
    # técnica (privacidad y ruido).
    _PRIVATE_COLUMN_PARTS = (
        "nombre", "apell", "docume", "cedula", "identif", "pacien", "telefon",
        "direcc", "correo", "email", "rownumber", "ternom", "ternum", "numdoc",
    )

    def _technical_catalog(self, semantic_model):
        """Catálogo técnico (tablas, columnas, relaciones) del modelo, con caché."""
        key = normalize_text(semantic_model)
        cache = self.__dict__.setdefault("_technical_catalog_cache", {})
        if key in cache:
            return cache[key]
        try:
            path = self.source_router.catalog_path_for_model(semantic_model, required=False)
            catalog = self._load_json(path, {}) if path else {}
        except Exception:
            catalog = {}
        cache[key] = catalog if isinstance(catalog, dict) else {}
        return cache[key]

    def _related_tables(self, semantic_model, table):
        """La tabla y las que la filtran (lado «uno» de sus relaciones activas)."""
        related = {normalize_text(table)}
        relations = [
            (normalize_text(relation.get("FromTable")), normalize_text(relation.get("ToTable")))
            for relation in self._technical_catalog(semantic_model).get("relationships", []) or []
            if relation.get("IsActive") is not False
        ]
        for _ in range(2):  # dimensión y dimensión de la dimensión (copo de nieve)
            related |= {target for source, target in relations if source in related and target}
        return related

    def _technical_field_aliases(self, column):
        """Alias de una columna técnica: su nombre y, solo si la PRIMERA palabra
        es un concepto de dimensión («CLASIFICACION_TRIAGE»), sus sinónimos
        («OID_TRIAGE» no hereda «clasificación» por contener «triage»)."""
        name = normalize_text(column)
        aliases = [column, name]
        parts = name.split()
        while len(parts) >= 2 and parts[-1] in TECHNICAL_SUFFIXES:
            parts = parts[:-1]
            aliases.append(" ".join(parts))
        head = parts[0] if parts else ""
        for synonyms in DIMENSION_SYNONYMS.values():
            if head in synonyms or name in synonyms:
                aliases.extend(sorted(synonyms))
        return _unique_strings(aliases)

    def _measure_expression(self, semantic_model, metric):
        """Expresión DAX de la métrica (la del catálogo técnico si es una medida)."""
        names = {normalize_text(metric.get("measure")), normalize_text(metric.get("label"))}
        for table in self._technical_catalog(semantic_model).get("tables", []) or []:
            for measure in table.get("measures", []) or []:
                if normalize_text(measure.get("name")) in names and measure.get("expression"):
                    return str(measure.get("expression"))
        return str(metric.get("dax_expression") or "")

    @staticmethod
    def _expression_uses_table(expression, table):
        return bool(re.search(
            r"(?<![\w'])'?" + re.escape(str(table)) + r"'?\s*[\[\)]", str(expression or ""),
        ))

    def _metric_fact_table(self, metric):
        """Tabla sobre la que se calcula el indicador: la suya o, si está
        guardado en el calendario/tabla de medidas, la que nombra su expresión."""
        table = metric.get("table")
        if table and self._CALENDAR_TABLE_RE.match(normalize_text(table)):
            cache = self.__dict__.setdefault("_fact_table_cache", {})
            key = (self._logical_key(metric), normalize_text(metric.get("label")))
            if key not in cache:
                cache[key] = self._expression_fact_table(metric.get("semantic_model"), metric) or table
            return cache[key]
        return table

    def _expression_fact_table(self, semantic_model, metric):
        """Única tabla (que no sea calendario/medidas) que la expresión de la
        medida referencia como 'TABLA'[columna] o TABLA[columna], o None."""
        used = self._expression_tables(semantic_model, metric)
        return next(iter(used)) if len(used) == 1 else None

    def _expression_tables(self, semantic_model, metric):
        """Tablas (que no sean calendario/medidas) que nombra la expresión de la medida."""
        expression = str(self._measure_expression(semantic_model, metric) or "")
        if not expression:
            return set()
        tables = {
            table.get("name") for table in self._technical_catalog(semantic_model).get("tables", []) or []
            if table.get("name") and not self._CALENDAR_TABLE_RE.match(normalize_text(table.get("name")))
        }
        used = {
            name for name in tables
            if re.search(r"(?:'" + re.escape(name) + r"'|(?<![\w'])" + re.escape(name) + r")\s*\[", expression,
                         re.IGNORECASE)
            or re.search(r"(?:COUNTROWS|RELATEDTABLE|VALUES|ALL|FILTER)\s*\(\s*'?" + re.escape(name) + r"'?\s*[),]",
                         expression, re.IGNORECASE)
        }
        return used

    def _with_technical_dimensions(self, metric, candidates):
        """Dimensiones del catálogo técnico para métricas SIN visual.

        Una medida que no aparece en ningún visual (TOTAL_TRIAGES) no tiene
        campos visuales propios. Se agregan las columnas de su tabla
        (CLASIFICACION_TRIAGE, MENORES, FECHA...). Si la medida se calcula
        sobre esa tabla, sus columnas van primero y los campos visuales de
        tablas que no la filtran pasan al final (un filtro allí no la
        afectaría); si no, solo se agregan al final como respaldo. Las
        métricas con visual no cambian.
        """
        if metric.get("appearances"):
            return candidates
        semantic_model = metric.get("semantic_model")
        table_name = metric.get("table")
        if table_name and self._CALENDAR_TABLE_RE.match(normalize_text(table_name)):
            # Medida guardada en el calendario o en una tabla de medidas
            # (TOTAL_CIRUGIAS = COUNT(CIRUGIAS[CEDULA])): su tabla real es la
            # única tabla de hechos que nombra su expresión.
            table_name = self._expression_fact_table(semantic_model, metric)
        if not table_name or self._CALENDAR_TABLE_RE.match(normalize_text(table_name)):
            return candidates
        catalog = self._technical_catalog(semantic_model)
        table = next(
            (item for item in catalog.get("tables", []) or []
             if normalize_text(item.get("name")) == normalize_text(table_name)),
            None,
        )
        if not table or not table.get("columns"):
            return candidates
        own_table = self._expression_uses_table(
            self._measure_expression(semantic_model, metric), table.get("name"),
        )
        related = self._related_tables(semantic_model, table.get("name"))
        adjusted = []
        for field in candidates:
            if own_table and normalize_text(field.get("table")) not in related:
                field = {**field, "relevance_score": field.get("relevance_score", 0) - 100,
                         "unrelated_table": True}
            adjusted.append(field)
        seen = {(normalize_text(f.get("table")), normalize_text(f.get("column"))) for f in adjusted}
        technical = []
        for column in table.get("columns", []) or []:
            name = column.get("name")
            lowered = str(name or "").lower()
            if not name or any(part in lowered for part in self._PRIVATE_COLUMN_PARTS):
                continue
            column_type = self._classify_data_type(column.get("data_type"))
            words = set(normalize_text(name).split())
            if column_type == "number" and not words & TEMPORAL_WORDS:
                continue
            key = (normalize_text(table.get("name")), normalize_text(name))
            if key in seen:
                continue
            seen.add(key)
            aliases = self._technical_column_aliases(semantic_model, table.get("name"), name)
            if column_type == "date" and not words & TEMPORAL_WORDS:
                aliases.append("fecha")  # «FechaParto»: es la fecha de la tabla
            technical.append({
                "semantic_model": semantic_model, "report": None, "source_group": None,
                "page": None, "visual_id": None, "visual_type": "technical_catalog",
                "role": None, "kind": "column", "table": table.get("name"), "column": name,
                "level": None, "query_ref": f"{table.get('name')}.{name}",
                "aliases": aliases,
                "relevance_score": 120 if own_table else 5, "technical": True,
            })
        result = adjusted + technical
        result.sort(key=lambda item: item.get("relevance_score", 0), reverse=True)
        return result

    def _group_label(self, field, metric=None):
        """Encabezado de la agrupación: su primer alias o, si es el nombre
        técnico (GEEDESCRI, TERNOMCOM), el nombre de negocio de los visuales.
        Un alias que solo repite palabras del indicador («VALOR ESTIMADO» para
        AREA_SERVICIO, tomado del título «VALOR ESTIMADO POR SERVICIO») no
        nombra la dimensión: se salta."""
        aliases = list(field.get("aliases") or [])
        own = {
            token for name in (self._metric_names(metric) if metric else []) if name
            for token in canonical_tokens(name)
        }
        column_tokens = set(canonical_tokens(field.get("column")))

        def names_metric(alias):
            tokens = set(canonical_tokens(alias))
            return bool(own and tokens and tokens <= own and not tokens & column_tokens)

        if own and aliases:
            aliases = [alias for alias in aliases if not names_metric(alias)] or [field.get("column")]
        column = normalize_text(field.get("column"))
        # «Primera fecha: DIA_SEMANA» (agregación implícita del visual sobre la
        # columna, tomada de su referencia nativa) no es un nombre de negocio.
        aliases = [
            alias for alias in aliases
            if not (":" in str(alias) and normalize_text(str(alias).split(":", 1)[1]) == column)
        ] or aliases
        label = (aliases or [field.get("column")])[0]
        # Una columna que ya se llama con la palabra de negocio (ESPECIALIDAD,
        # SERVICIO) conserva ese nombre: el de un visual puede calificarla de
        # más («ESPECIALIDAD CIRUGÍA» en DETALLE OCUPACIÓN) y la pregunta pide
        # «especialidades», no las de cirugía.
        if column and any(column in synonyms for synonyms in DIMENSION_SYNONYMS.values()):
            return label if normalize_text(label) == column else field.get("column")
        if normalize_text(label) == column:
            names = [
                name for name in self._column_business_names(
                    field.get("semantic_model"), field.get("column"), field.get("table"))
                if not names_metric(name)
            ]
            if names:
                return names[0]
            if own and "_" in str(field.get("column") or ""):
                return str(field.get("column")).replace("_", " ")
        return label

    def _technical_column_aliases(self, semantic_model, table, column):
        """Alias de una columna del catálogo técnico: su nombre, sus sinónimos
        y los nombres de negocio con que la muestran los visuales del modelo."""
        aliases = self._technical_field_aliases(column)
        for name in self._column_business_names(semantic_model, column, table):
            aliases.extend(self._field_aliases({"display_name": name}))
        return _unique_strings(aliases)

    # ---------------- relación de una columna con el indicador ----------------
    # Una columna solo sirve para agrupar, ordenar o filtrar un indicador si su
    # tabla lo filtra. Regla (`_dimension_relation`):
    # - «own»: la tabla del campo es la tabla de hechos del indicador. Siempre vale.
    # - «related»: la expresión del indicador nombra esa tabla, o las relaciones
    #   activas del modelo la conectan con la tabla de hechos (dimensión y
    #   dimensión de la dimensión, como `_related_tables`).
    # - «unrelated»: (a) el modelo declara sus relaciones (catálogo técnico con
    #   tablas y la clave «relationships», aunque la lista esté vacía:
    #   INFO.VIEW.RELATIONSHIPS las devuelve todas; BRIEFING no tiene ninguna y
    #   sus tablas son independientes) y ninguna conecta esa tabla; o (b) sin
    #   relaciones declaradas, la tabla de hechos tiene su PROPIA columna con el
    #   mismo significado (mismo alias de negocio, p. ej. ASEGURADOR frente al
    #   TERNOMCOM «ASEGURADOR» de otra tabla, o una fecha propia frente a la
    #   fecha de otra tabla): se prefiere la propia. Un calendario/tabla de
    #   fechas nunca se descarta en este caso (se supone conectado).
    # - «unknown»: falta información (tabla de hechos desconocida o de medidas,
    #   expresión que no la nombra, sin relaciones ni columna equivalente): el
    #   campo se conserva como antes, para no dejar sin dimensiones a los
    #   modelos sin metadata de relaciones.
    def _has_relationship_metadata(self, semantic_model):
        catalog = self._technical_catalog(semantic_model)
        return bool(catalog.get("tables")) and "relationships" in catalog

    def _fact_table_entry(self, metric):
        """Tabla de hechos del indicador en el catálogo técnico (o None)."""
        table_name = self._metric_fact_table(metric)
        if not table_name or self._CALENDAR_TABLE_RE.match(normalize_text(table_name)):
            return None
        return next(
            (item for item in self._technical_catalog(metric.get("semantic_model")).get("tables", []) or []
             if normalize_text(item.get("name")) == normalize_text(table_name)),
            None,
        )

    def _own_column_profiles(self, metric):
        """[(alias normalizados, es_temporal)] de las columnas de la tabla de
        hechos del indicador: las del catálogo técnico y las de los visuales."""
        model = metric.get("semantic_model")
        table_name = normalize_text(self._metric_fact_table(metric))
        profiles = []
        entry = self._fact_table_entry(metric)
        for column in (entry or {}).get("columns", []) or []:
            name = column.get("name")
            if not name:
                continue
            aliases = {normalize_text(a) for a in self._technical_column_aliases(model, entry.get("name"), name)}
            temporal = (
                self._classify_data_type(column.get("data_type")) == "date"
                or bool(set(normalize_text(name).split()) & TEMPORAL_WORDS)
            )
            profiles.append((aliases - {""}, temporal))
        for field in self.dimension_fields or []:
            if (
                normalize_text(field.get("semantic_model")) == normalize_text(model)
                and normalize_text(field.get("table")) == table_name
            ):
                aliases = {normalize_text(a) for a in field.get("aliases") or []}
                profiles.append((aliases - {""}, self._is_temporal_field(field)))
        return profiles

    def _own_equivalent_column(self, metric, field):
        """¿La tabla del indicador tiene su propia columna con el significado
        de `field` (otra tabla)? Fechas con fechas; el resto por alias común."""
        temporal = self._is_temporal_field(field)
        aliases = {normalize_text(alias) for alias in field.get("aliases") or []} - {""}
        aliases.discard(normalize_text(field.get("table")))
        for own_aliases, own_temporal in self._own_column_profiles(metric):
            if temporal or own_temporal:
                if temporal and own_temporal:
                    return True
                continue
            if aliases & own_aliases:
                return True
        return False

    def _dimension_relation(self, metric, field):
        """«own» | «related» | «unrelated» | «unknown» (ver la regla arriba)."""
        model = metric.get("semantic_model")
        table = self._metric_fact_table(metric)
        field_table = normalize_text(field.get("table"))
        if not table or not field_table or self._CALENDAR_TABLE_RE.match(normalize_text(table)):
            return "unknown"
        if field_table == normalize_text(table):
            return "own"
        cache = self.__dict__.setdefault("_dimension_relation_cache", {})
        metric_key = (self._logical_key(metric), normalize_text(metric.get("label")))
        if metric_key not in cache:
            # Por indicador: tablas de su expresión y, si el modelo declara sus
            # relaciones, las que filtran su tabla (None = sin esa metadata o
            # expresión que no nombra la tabla: se decide por columna).
            if len(cache) > 5000:
                cache.clear()
            used = {normalize_text(name) for name in self._expression_tables(model, metric)}
            if metric.get("visual_filters") and metric.get("base_dax_expression"):
                # Un filtro del visual sobre una tabla sin relación con la del
                # indicador no la conecta (TOTAL DE PACIENTES de PACIENTES
                # EMERGENCIA con un filtro de INTERCONSULTAS no se desglosa por
                # la especialidad de INTERCONSULTAS): solo cuenta la medida base
                # y las tablas de filtros que el modelo relaciona con ella.
                base = {**metric, "dax_expression": metric["base_dax_expression"], "visual_filters": None}
                base_used = {normalize_text(name) for name in self._expression_tables(model, base)}
                if self._has_relationship_metadata(model):
                    reachable = set()
                    for name in {normalize_text(table)} | base_used:
                        reachable |= {normalize_text(t) for t in self._related_tables(model, name)}
                    used = base_used | {name for name in used if name in reachable}
            related = None
            if self._has_relationship_metadata(model):
                if self._expression_uses_table(self._measure_expression(model, metric), table):
                    related = set()
                    for name in {normalize_text(table)} | used:
                        related |= self._related_tables(model, name)
                else:
                    related = "unknown"
            cache[metric_key] = {"used": used, "related": related, "columns": {}}
        info = cache[metric_key]
        if field_table in info["used"]:
            return "related"
        if info["related"] == "unknown":
            return "unknown"
        if info["related"] is not None:
            return "related" if field_table in info["related"] else "unrelated"
        # Sin relaciones declaradas, un calendario (Calendario[AÑO]) se supone
        # conectado: es la forma habitual de filtrar por periodo.
        if self._CALENDAR_TABLE_RE.match(field_table):
            return "unknown"
        column_key = (field_table, normalize_text(field.get("column")))
        if column_key not in info["columns"]:
            info["columns"][column_key] = (
                "unrelated" if self._own_equivalent_column(metric, field) else "unknown"
            )
        return info["columns"][column_key]

    def _own_table_fallback_fields(self, metric, existing):
        """Columnas de la tabla de hechos de un indicador CON visuales que no
        están entre sus campos visuales (ASEGURADOR de CONSULTAS PRIORITARIAS
        solo aparece agregado): respaldo para «por X», rankings, filtros
        explícitos. Van al final (relevancia baja), marcadas `own_fallback`;
        los valores implícitos no las recorren. Las fechas no se agregan: si
        los visuales del indicador no usan ninguna, la tabla es de estado
        actual para el tablero (FechaSalida de PACIENTES X ASEGURADORA no es
        la fecha de un periodo; ver `_snapshot_table`)."""
        entry = self._fact_table_entry(metric)
        if not entry:
            return []
        model = metric.get("semantic_model")
        seen = {(normalize_text(f.get("table")), normalize_text(f.get("column"))) for f in existing}
        # Después de las propias, las de las tablas que la filtran por una
        # relación activa declarada (REFERENCIA[GEEDESCRI] filtra
        # DETALLE_RECEPCIONES): «solicitudes por especialidad» se puede
        # desglosar aunque ningún visual muestre esa columna. Sin metadata de
        # relaciones no se supone ninguna.
        tables = [(entry, 8)]
        if self._has_relationship_metadata(model):
            own = normalize_text(entry.get("name"))
            related = self._related_tables(model, entry.get("name")) - {own}
            for item in self._technical_catalog(model).get("tables", []) or []:
                name = normalize_text(item.get("name"))
                if name in related and not self._CALENDAR_TABLE_RE.match(name.replace(" ", "")):
                    tables.append((item, 6))
        result = []
        for table, relevance in tables:
            for column in table.get("columns", []) or []:
                name = column.get("name")
                lowered = str(name or "").lower()
                if not name or any(part in lowered for part in self._PRIVATE_COLUMN_PARTS):
                    continue
                column_type = self._classify_data_type(column.get("data_type"))
                words = set(normalize_text(name).split())
                if column_type in ("number", "date") or words & TEMPORAL_WORDS:
                    continue
                key = (normalize_text(table.get("name")), normalize_text(name))
                if key in seen:
                    continue
                seen.add(key)
                aliases = self._technical_column_aliases(model, table.get("name"), name)
                result.append({
                    "semantic_model": model, "report": None, "source_group": None,
                    "page": None, "visual_id": None, "visual_type": "technical_catalog",
                    "role": None, "kind": "column", "table": table.get("name"), "column": name,
                    "level": None, "query_ref": f"{table.get('name')}.{name}",
                    "aliases": aliases, "relevance_score": relevance, "own_fallback": True,
                })
        return result

    def _metric_dimensions(self, metric, dropped=None):
        """Dimensiones candidatas del indicador para agrupar, ordenar, filtrar
        y elegir la fecha del periodo: las de sus visuales o del catálogo
        técnico (`_with_technical_dimensions`) SIN las de tablas que no lo
        filtran («unrelated»: un SUMMARIZECOLUMNS por EGRESOS_POR_SERVICIO
        [TERNOMCOM] repite el total de CONSULTAS PRIORITARIAS en cada fila) y,
        si tiene visuales, con las columnas de su propia tabla como respaldo.
        `dropped` (lista) recibe los campos descartados. Con caché por
        indicador (los catálogos no cambian durante la vida del planificador)."""
        cache = self.__dict__.setdefault("_metric_dimensions_cache", {})
        key = (self._logical_key(metric), normalize_text(metric.get("label")),
               tuple(sorted(self._metric_visual_ids(metric))), tuple(self._metric_pages(metric)),
               tuple(self._metric_reports(metric)))
        if key not in cache:
            if len(cache) > 2000:
                cache.clear()
            candidates = self._with_technical_dimensions(metric, self._relevant_dimensions(metric))
            kept, unrelated = [], []
            for field in candidates:
                (unrelated if self._dimension_relation(metric, field) == "unrelated" else kept).append(field)
            if metric.get("appearances"):
                kept.extend(self._own_table_fallback_fields(metric, kept))
            cache[key] = (kept, unrelated)
        kept, unrelated = cache[key]
        if dropped is not None:
            dropped.extend(unrelated)
        return list(kept)

    def _period_in_metric_note(self, question, temporal, metric, metric_result):
        """Nota visible cuando el periodo pedido forma parte del nombre del
        indicador («triages en 2025» -> TRIAGES_2025): no se agrega otro
        filtro de fecha, pero la respuesta lo dice en vez de callarlo."""
        if temporal.get("period"):
            return None
        period = self._period_parser().parse(normalize_text(question))
        if not period:
            return None
        phrase = normalize_text(period.get("phrase"))
        names = [metric_result.get("matched_name"), metric.get("label"), metric.get("measure")]
        name = next((n for n in names if n and _exact_phrase(normalize_text(n), phrase)), None)
        if not name:
            return None
        return (
            f"El periodo «{_original_phrase(question, period.get('phrase'))}» ya está incluido en "
            f"el indicador {name}; no se aplicó otro filtro de fecha."
        )

    @staticmethod
    def _technical_columns_used(candidates, filters, group_by):
        """«TABLA[COLUMNA]» del catálogo técnico usadas en filtros o agrupación
        (para el razonamiento: la métrica no tenía visual propio)."""
        technical = {
            (normalize_text(field.get("table")), normalize_text(field.get("column"))): field
            for field in candidates if field.get("technical")
        }
        used = []
        for item in [*(filters or []), *(group_by or [])]:
            key = (normalize_text(item.get("table")), normalize_text(item.get("column")))
            field = technical.get(key)
            label = f"{field['table']}[{field['column']}]" if field else None
            if label and label not in used:
                used.append(label)
        return used

    def _dimension_match_score(self, text, field):
        return max((_phrase_score(text, alias) for alias in field.get("aliases", [])), default=0.0)

    def _best_dimension(self, text, candidates, exclude_temporal=False):
        scored = []
        for field in candidates:
            if exclude_temporal and self._is_period_field(field):
                continue
            score = self._dimension_match_score(text, field)
            if score <= 0:
                continue
            score += min(0.12, field.get("relevance_score", 0) / 1000.0)
            scored.append((score, field))
        scored.sort(key=lambda item: item[0], reverse=True)
        return scored[0][1] if scored else None
