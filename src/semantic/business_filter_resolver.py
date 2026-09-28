import json
import re
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher


CONNECTOR_WORDS = {
    "a", "al", "de", "del", "el", "en",
    "la", "las", "los", "por", "para",
    "un", "una", "y",
}


def normalize_text(value):
    value = str(value or "").lower().strip()

    value = "".join(
        char
        for char in unicodedata.normalize(
            "NFD",
            value,
        )
        if unicodedata.category(char) != "Mn"
    )

    value = re.sub(
        r"[^a-z0-9]+",
        " ",
        value,
    )

    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip()


def canonical_token(token):
    token = normalize_text(
        token
    )

    if not token:
        return ""

    if (
        token.endswith("iones")
        and len(token) > 6
    ):
        return (
            token[:-5]
            + "ion"
        )

    if (
        token.endswith("ales")
        and len(token) > 5
    ):
        return token[:-2]

    if (
        token.endswith("entes")
        and len(token) > 6
    ):
        return token[:-1]

    if (
        token.endswith("s")
        and len(token) > 4
    ):
        return token[:-1]

    return token


def semantic_tokens(value):
    result = []

    for raw in normalize_text(
        value
    ).split():

        if raw in CONNECTOR_WORDS:
            continue

        token = canonical_token(
            raw
        )

        if (
            token
            and token
            not in CONNECTOR_WORDS
        ):
            result.append(
                token
            )

    return result


def token_similarity(
    left,
    right,
):
    if left == right:
        return 1.0

    if (
        len(left) >= 5
        and len(right) >= 5
        and (
            left.startswith(
                right[:5]
            )
            or right.startswith(
                left[:5]
            )
        )
    ):
        return 0.90

    return SequenceMatcher(
        None,
        left,
        right,
    ).ratio()


def phrase_match_score(
    question,
    value,
):
    q_tokens = (
        semantic_tokens(
            question
        )
    )

    v_tokens = (
        semantic_tokens(
            value
        )
    )

    if not q_tokens or not v_tokens:
        return 0.0

    matched = []

    for v_token in v_tokens:

        best = max(
            (
                token_similarity(
                    v_token,
                    q_token,
                )
                for q_token
                in q_tokens
            ),
            default=0.0,
        )

        matched.append(
            best
        )

    coverage = (
        sum(
            1
            for score in matched
            if score >= 0.80
        )
        / len(v_tokens)
    )

    # Evita falsos positivos como:
    # "cirugías" -> "CIRUGIA GENERAL".
    if coverage < 0.74:
        return 0.0

    average_similarity = (
        sum(matched)
        / len(matched)
    )

    specificity_bonus = (
        0.05
        if (
            len(v_tokens) >= 2
            and coverage == 1.0
        )
        else 0.0
    )

    return min(
        1.0,
        (
            0.74 * coverage
            + 0.26
            * average_similarity
            + specificity_bonus
        ),
    )


class BusinessFilterResolver:
    """
    Resuelve filtros de negocio usando:
      1. campos realmente presentes en los visuales/página;
      2. columnas del catálogo técnico como fallback;
      3. valores reales consultados a Power BI.

    visual_metrics_catalog_path es opcional para mantener compatibilidad,
    pero se recomienda pasarlo siempre.
    """

    CONCEPTS = {
        "aseguradora": [
            "asegurador",
            "aseguradora",
            "eps",
            "pagador",
            "ternomcom",
        ],
        "especialidad": [
            "especialidad",
            "especialidad medica",
        ],
        "cirujano": [
            "cirujano",
            "medico",
            "doctor",
        ],
        "tipo_cirugia": [
            "tipo",
            "tipo cirugia",
            "tipo de cirugia",
            "origen cirugia",
        ],
        "servicio": [
            "servicio",
            "unidad",
            "area",
        ],
        "estado": [
            "estado",
            "estado cita",
            "situacion",
        ],
        "causa": [
            "causa",
            "motivo",
        ],
        "modalidad": [
            "modalidad",
            "tipo atencion",
            "tipo de atencion",
        ],
        "sede": [
            "sede",
            "ubicacion",
        ],
        "origen": [
            "origen",
            "procedencia",
        ],
    }

    DIMENSION_ROLES = {
        "group",
        "category",
        "legend",
        "details",
        "rows",
        "columns",
    }

    EXCLUDED_COLUMNS = {
        "date",
        "fecha",
        "ano",
        "año",
        "mes",
        "dia",
        "día",
    }

    SENSITIVE_PATTERNS = {
        "paciente",
        "documento",
        "identificacion",
        "identificación",
        "cedula",
        "cédula",
        "historia clinica",
        "historia clínica",
        "telefono",
        "teléfono",
        "correo",
        "direccion",
        "dirección",
    }

    def __init__(
        self,
        technical_catalog_path,
        powerbi_provider,
        visual_metrics_catalog_path=None,
        max_domain_size=2000,
    ):
        with open(
            technical_catalog_path,
            "r",
            encoding="utf-8",
        ) as file:
            self.catalog = json.load(
                file
            )

        self.powerbi_provider = (
            powerbi_provider
        )

        self.max_domain_size = int(
            max_domain_size
        )

        self.value_cache = {}
        self.domain_cache_loaded = (
            set()
        )

        self.columns = (
            self._build_column_index()
        )

        self.visual_catalog = None
        self.visual_dimensions = (
            defaultdict(list)
        )

        if visual_metrics_catalog_path:

            try:
                with open(
                    visual_metrics_catalog_path,
                    "r",
                    encoding="utf-8",
                ) as file:
                    self.visual_catalog = (
                        json.load(file)
                    )

                self._build_visual_dimension_index()

            except Exception:
                # El resolver conserva compatibilidad
                # con el catálogo técnico si el visual
                # no está disponible.
                self.visual_catalog = None

    # ========================================================
    # NORMALIZACIÓN
    # ========================================================

    def _normalize(
        self,
        value,
    ):
        return normalize_text(
            value
        )

    # ========================================================
    # ÍNDICE TÉCNICO
    # ========================================================

    def _build_column_index(
        self,
    ):
        result = []

        for table in self.catalog.get(
            "tables",
            [],
        ):
            table_name = table.get(
                "name"
            )

            if not table_name:
                continue

            for column in table.get(
                "columns",
                [],
            ):
                column_name = column.get(
                    "name"
                )

                if not column_name:
                    continue

                result.append(
                    {
                        "table":
                            table_name,
                        "column":
                            column_name,
                        "normalized_table":
                            self._normalize(
                                table_name
                            ),
                        "normalized_column":
                            self._normalize(
                                column_name
                            ),
                        "data_type":
                            column.get(
                                "data_type"
                            ),
                    }
                )

        return result

    # ========================================================
    # ÍNDICE DE DIMENSIONES DE LOS VISUALES
    # ========================================================

    def _is_safe_dimension(
        self,
        table,
        column,
    ):
        normalized = self._normalize(
            column
        )

        if (
            normalized
            in {
                self._normalize(value)
                for value
                in self.EXCLUDED_COLUMNS
            }
        ):
            return False

        full = self._normalize(
            f"{table} {column}"
        )

        for pattern in (
            self.SENSITIVE_PATTERNS
        ):
            if (
                self._normalize(
                    pattern
                )
                in full
            ):
                return False

        # Llaves técnicas.
        if (
            normalized == "id"
            or normalized.endswith(
                " id"
            )
            or normalized.endswith(
                "_id"
            )
            or normalized in {
                "oid",
                "consecutivo",
            }
        ):
            return False

        return True

    def _add_visual_dimension(
        self,
        dashboard,
        table,
        column,
        source,
        priority,
    ):
        if (
            not dashboard
            or not table
            or not column
        ):
            return

        if not self._is_safe_dimension(
            table,
            column,
        ):
            return

        key = self._normalize(
            dashboard
        )

        existing = (
            self.visual_dimensions[
                key
            ]
        )

        for item in existing:
            if (
                item["table"]
                == table
                and item["column"]
                == column
            ):
                item["priority"] = max(
                    item["priority"],
                    priority,
                )
                return

        existing.append(
            {
                "dashboard":
                    dashboard,
                "table":
                    table,
                "column":
                    column,
                "source":
                    source,
                "priority":
                    priority,
            }
        )

    def _build_visual_dimension_index(
        self,
    ):
        if not self.visual_catalog:
            return

        for page in self.visual_catalog.get(
            "pages",
            [],
        ):
            dashboard = page.get(
                "page_display_name"
            )

            if not dashboard:
                continue

            for visual in page.get(
                "visuals",
                [],
            ):
                visual_type = (
                    self._normalize(
                        visual.get(
                            "visual_type"
                        )
                    )
                )

                is_hidden = bool(
                    visual.get(
                        "is_hidden",
                        False,
                    )
                )

                for field in visual.get(
                    "fields",
                    [],
                ):
                    if (
                        field.get(
                            "kind"
                        )
                        != "column"
                    ):
                        continue

                    table = field.get(
                        "table"
                    )

                    column = field.get(
                        "column"
                    )

                    role = self._normalize(
                        field.get(
                            "role"
                        )
                    )

                    # Slicer = dimensión de negocio muy fuerte.
                    if visual_type == "slicer":
                        priority = (
                            120
                            if not is_hidden
                            else 82
                        )

                    # Agrupaciones reales de gráficos.
                    elif role in (
                        self.DIMENSION_ROLES
                    ):
                        priority = (
                            110
                            if not is_hidden
                            else 78
                        )

                    else:
                        continue

                    self._add_visual_dimension(
                        dashboard=
                            dashboard,
                        table=
                            table,
                        column=
                            column,
                        source=(
                            f"visual:{visual_type}:"
                            f"{role}"
                        ),
                        priority=
                            priority,
                    )

        for key in list(
            self.visual_dimensions
        ):
            self.visual_dimensions[
                key
            ].sort(
                key=lambda item:
                    item["priority"],
                reverse=True,
            )

    def get_available_dashboards(
        self,
    ):
        result = []

        for items in (
            self.visual_dimensions
            .values()
        ):
            if not items:
                continue

            dashboard = items[0].get(
                "dashboard"
            )

            if (
                dashboard
                and dashboard not in result
            ):
                result.append(
                    dashboard
                )

        return result

    def get_dashboard_dimensions(
        self,
        dashboard,
    ):
        return list(
            self.visual_dimensions.get(
                self._normalize(
                    dashboard
                ),
                [],
            )
        )

    # ========================================================
    # CONCEPTO DE UNA COLUMNA
    # ========================================================

    def _concept_for_column(
        self,
        column,
    ):
        normalized_column = (
            self._normalize(
                column
            )
        )

        best_concept = None
        best_score = 0

        for concept, aliases in (
            self.CONCEPTS.items()
        ):
            for alias in aliases:
                normalized_alias = (
                    self._normalize(
                        alias
                    )
                )

                score = 0

                if (
                    normalized_column
                    == normalized_alias
                ):
                    score = 100

                elif (
                    normalized_alias
                    in normalized_column
                    or normalized_column
                    in normalized_alias
                ):
                    score = 60

                if score > best_score:
                    best_score = score
                    best_concept = (
                        concept
                    )

        return (
            best_concept
            or normalized_column
            .replace(
                " ",
                "_",
            )
        )

    # ========================================================
    # BUSCAR COLUMNA CONOCIDA
    # ========================================================

    def _find_column(
        self,
        concept,
        dashboard,
    ):
        aliases = (
            self.CONCEPTS.get(
                concept,
                [],
            )
        )

        normalized_dashboard = (
            self._normalize(
                dashboard
            )
        )

        candidates = []

        # 1. Primero: dimensiones realmente usadas
        # en esa página/visual.
        for item in (
            self.visual_dimensions.get(
                normalized_dashboard,
                [],
            )
        ):
            normalized_column = (
                self._normalize(
                    item["column"]
                )
            )

            score = item.get(
                "priority",
                0,
            )

            for alias in aliases:
                normalized_alias = (
                    self._normalize(
                        alias
                    )
                )

                if (
                    normalized_column
                    == normalized_alias
                ):
                    score += 200

                elif (
                    normalized_alias
                    in normalized_column
                ):
                    score += 100

            if score > item.get(
                "priority",
                0,
            ):
                candidates.append(
                    {
                        **item,
                        "score":
                            score,
                    }
                )

        if candidates:
            candidates.sort(
                key=lambda item:
                    item["score"],
                reverse=True,
            )

            return candidates[0]

        # 2. Fallback: catálogo técnico.
        candidates = []

        for column in self.columns:

            column_name = column[
                "normalized_column"
            ]

            table_name = column[
                "normalized_table"
            ]

            score = 0

            for alias in aliases:
                normalized_alias = (
                    self._normalize(
                        alias
                    )
                )

                if (
                    column_name
                    == normalized_alias
                ):
                    score += 100

                elif (
                    normalized_alias
                    in column_name
                ):
                    score += 50

            if (
                table_name
                == normalized_dashboard
            ):
                score += 80

            elif (
                normalized_dashboard
                in table_name
                or table_name
                in normalized_dashboard
            ):
                score += 40

            if score > 0:
                candidates.append(
                    {
                        **column,
                        "score":
                            score,
                    }
                )

        candidates.sort(
            key=lambda item:
                item["score"],
            reverse=True,
        )

        if not candidates:
            return None

        return candidates[0]

    # ========================================================
    # DAX
    # ========================================================

    def _table_reference(
        self,
        table,
    ):
        table = str(
            table
        ).replace(
            "'",
            "''",
        )

        return f"'{table}'"

    def _column_reference(
        self,
        column,
    ):
        column = str(
            column
        ).replace(
            "]",
            "]]",
        )

        return f"[{column}]"

    def _get_values(
        self,
        semantic_model,
        table,
        column,
    ):
        cache_key = (
            semantic_model,
            table,
            column,
        )

        if (
            cache_key
            in self.value_cache
        ):
            return self.value_cache[
                cache_key
            ]

        table_ref = (
            self._table_reference(
                table
            )
        )

        column_ref = (
            self._column_reference(
                column
            )
        )

        dax = f"""
EVALUATE
TOPN(
    {self.max_domain_size},
    FILTER(
        SELECTCOLUMNS(
            VALUES(
                {table_ref}{column_ref}
            ),
            "Value",
            {table_ref}{column_ref}
        ),
        NOT ISBLANK([Value])
    ),
    [Value],
    ASC
)
"""

        result = (
            self.powerbi_provider
            .execute_dax(
                dax=dax,
                semantic_model=
                    semantic_model,
            )
        )

        if (
            result.get(
                "status"
            )
            != "success"
        ):
            # Cacheamos también el fallo. Así una columna que
            # produjo error no vuelve a ejecutar el mismo DAX
            # repetidamente durante la misma sesión.
            self.value_cache[
                cache_key
            ] = []

            return []

        values = []

        for row in result.get(
            "rows",
            [],
        ):
            if not row:
                continue

            value = next(
                iter(
                    row.values()
                ),
                None,
            )

            if value is not None:
                values.append(
                    str(value)
                )

        self.value_cache[
            cache_key
        ] = values

        return values

    def _table_context_score(
        self,
        question,
        table,
    ):
        question_tokens = set(
            semantic_tokens(
                question
            )
        )

        table_tokens = set(
            semantic_tokens(
                table
            )
        )

        if (
            not question_tokens
            or not table_tokens
        ):
            return 0.0

        common = (
            question_tokens
            & table_tokens
        )

        if not common:
            return 0.0

        return (
            len(common)
            / len(table_tokens)
        )

    # ========================================================
    # MATCHING DE VALORES
    # ========================================================

    def _match_value_fuzzy(
        self,
        question,
        values,
        min_score=0.82,
    ):
        best_value = None
        best_score = 0.0

        for value in values:

            if (
                len(
                    normalize_text(
                        value
                    )
                )
                < 2
            ):
                continue

            score = phrase_match_score(
                question,
                value,
            )

            if score > best_score:
                best_score = score
                best_value = value

        if (
            best_value is None
            or best_score
            < min_score
        ):
            return None

        return {
            "value":
                best_value,
            "score":
                round(
                    best_score,
                    4,
                ),
        }

    def _candidate_dimension_columns(
        self,
        dashboard,
    ):
        result = []
        seen = set()

        # Primero campos realmente presentes
        # en visuales/slicers de la página.
        for item in (
            self.get_dashboard_dimensions(
                dashboard
            )
        ):
            key = (
                item["table"],
                item["column"],
            )

            if key in seen:
                continue

            seen.add(
                key
            )

            result.append(
                item
            )

        # Luego conceptos conocidos como fallback.
        for concept in self.CONCEPTS:

            column = self._find_column(
                concept,
                dashboard,
            )

            if not column:
                continue

            key = (
                column["table"],
                column["column"],
            )

            if key in seen:
                continue

            if not self._is_safe_dimension(
                column["table"],
                column["column"],
            ):
                continue

            seen.add(
                key
            )

            result.append(
                {
                    **column,
                    "dashboard":
                        dashboard,
                    "source":
                        "technical_fallback",
                    "priority":
                        50,
                }
            )

        result.sort(
            key=lambda item:
                item.get(
                    "priority",
                    0,
                ),
            reverse=True,
        )

        return result

    def find_dimension_matches(
        self,
        question,
        dashboard,
        semantic_model,
        min_score=0.82,
        max_matches=6,
        preferred_tables=None,
    ):
        matches = []

        preferred_tables = {
            self._normalize(value)
            for value in (
                preferred_tables
                or []
            )
            if value
        }

        candidate_columns = (
            self._candidate_dimension_columns(
                dashboard
            )
        )

        candidate_columns.sort(
            key=lambda item:
                (
                    1
                    if self._normalize(
                        item.get(
                            "table"
                        )
                    )
                    in preferred_tables
                    else 0,
                    item.get(
                        "priority",
                        0,
                    ),
                ),
            reverse=True,
        )

        for column in candidate_columns:
            values = self._get_values(
                semantic_model,
                column["table"],
                column["column"],
            )

            if not values:
                continue

            matched = (
                self._match_value_fuzzy(
                    question,
                    values,
                    min_score=
                        min_score,
                )
            )

            if not matched:
                continue

            matches.append(
                {
                    "status":
                        "resolved",
                    "concept":
                        self._concept_for_column(
                            column["column"]
                        ),
                    "dashboard":
                        dashboard,
                    "table":
                        column["table"],
                    "column":
                        column["column"],
                    "operator":
                        "=",
                    "value":
                        matched["value"],
                    "score":
                        matched["score"],
                    "table_context_score":
                        round(
                            self._table_context_score(
                                question,
                                column.get(
                                    "table"
                                ),
                            ),
                            4,
                        ),
                    "source":
                        column.get(
                            "source",
                            "powerbi_value",
                        ),
                    "priority":
                        column.get(
                            "priority",
                            0,
                        ),
                    "preferred_table":
                        (
                            self._normalize(
                                column.get(
                                    "table"
                                )
                            )
                            in preferred_tables
                        ),
                }
            )

            matches[-1][
                "rank_score"
            ] = round(
                matches[-1][
                    "score"
                ]
                + 0.12
                * matches[-1][
                    "table_context_score"
                ]
                + 0.001
                * matches[-1][
                    "priority"
                ]
                + (
                    0.08
                    if matches[-1][
                        "preferred_table"
                    ]
                    else 0.0
                ),
                4,
            )

        matches.sort(
            key=lambda item:
                item.get(
                    "rank_score",
                    item.get(
                        "score",
                        0.0,
                    ),
                ),
            reverse=True,
        )

        # Si existe una coincidencia en la misma tabla de la métrica,
        # descartamos coincidencias equivalentes de tablas ajenas.
        preferred_values = {
            normalize_text(
                item.get(
                    "value"
                )
            )
            for item in matches
            if item.get(
                "preferred_table"
            )
        }

        if preferred_values:
            matches = [
                item
                for item in matches
                if (
                    item.get(
                        "preferred_table"
                    )
                    or normalize_text(
                        item.get(
                            "value"
                        )
                    )
                    not in preferred_values
                )
            ]

        # Un mismo valor/concepto no debe producir varios filtros
        # simultáneos desde tablas diferentes. Conservamos el candidato
        # mejor rankeado.
        unique = []
        seen = set()

        for item in matches:

            key = (
                item.get(
                    "concept"
                ),
                normalize_text(
                    item["value"]
                ),
            )

            if key in seen:
                continue

            seen.add(
                key
            )

            unique.append(
                item
            )

        return unique[
            :max_matches
        ]

    # ========================================================
    # COMPATIBILIDAD / PRECARGA
    # ========================================================

    def preload_domains(
        self,
        semantic_model,
        dashboard,
    ):
        cache_key = (
            semantic_model,
            dashboard,
        )

        if (
            cache_key
            in self.domain_cache_loaded
        ):
            return

        for column in (
            self._candidate_dimension_columns(
                dashboard
            )
        ):
            self._get_values(
                semantic_model,
                column["table"],
                column["column"],
            )

        self.domain_cache_loaded.add(
            cache_key
        )

    # ========================================================
    # RESOLVER
    # ========================================================

    def resolve(
        self,
        question,
        dashboard,
        semantic_model,
        preferred_tables=None,
    ):
        filters = (
            self.find_dimension_matches(
                question=
                    question,
                dashboard=
                    dashboard,
                semantic_model=
                    semantic_model,
                preferred_tables=
                    preferred_tables,
            )
        )

        return {
            "status":
                "resolved",
            "filters":
                filters,
        }
