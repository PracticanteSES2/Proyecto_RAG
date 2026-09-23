import json
import re
import unicodedata
from pathlib import Path


MONTH_NAMES = {
    1: "enero",
    2: "febrero",
    3: "marzo",
    4: "abril",
    5: "mayo",
    6: "junio",
    7: "julio",
    8: "agosto",
    9: "septiembre",
    10: "octubre",
    11: "noviembre",
    12: "diciembre",
}


# ============================================================
# UTILIDADES
# ============================================================

def normalize_name(value):

    if not value:
        return ""

    value = str(value).lower().strip()

    value = "".join(
        char
        for char in unicodedata.normalize(
            "NFD",
            value
        )
        if unicodedata.category(char) != "Mn"
    )

    value = re.sub(
        r"[^a-z0-9]",
        "",
        value
    )

    return value


def load_json(path):

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(file)


# ============================================================
# FILTER RESOLVER
# ============================================================

class FilterResolver:

    CONCEPT_ALIASES = {

        "year": [
            "ano",
            "anio",
            "year",
        ],

        "month": [
            "mes",
            "month",
            "numeromes",
            "mesnumero",
            "nromes",
        ],
    }


    PREFERRED_DATE_TABLES = [
        "calendario",
        "calendar",
        "fecha",
        "date",
        "dates",
    ]


    def __init__(
        self,
        technical_catalog_path,
        ambiguity_margin=10
    ):

        self.catalog = load_json(
            technical_catalog_path
        )

        self.ambiguity_margin = (
            ambiguity_margin
        )

        self.columns = (
            self._build_column_index()
        )


    # ========================================================
    # ÍNDICE DE COLUMNAS
    # ========================================================

    def _build_column_index(self):

        result = []

        for table in self.catalog.get(
            "tables",
            []
        ):

            table_name = table.get(
                "name"
            )

            if not table_name:
                continue

            for column in table.get(
                "columns",
                []
            ):

                column_name = column.get(
                    "name"
                )

                if not column_name:
                    continue

                result.append({

                    "table":
                        table_name,

                    "column":
                        column_name,

                    "description":
                        column.get(
                            "description"
                        ),

                    "data_type":
                        column.get(
                            "data_type"
                        ),

                    "is_hidden":
                        column.get(
                            "is_hidden",
                            False
                        ),

                    "normalized_table":
                        normalize_name(
                            table_name
                        ),

                    "normalized_column":
                        normalize_name(
                            column_name
                        )
                })

        return result


    # ========================================================
    # SCORE DE CANDIDATOS
    # ========================================================

    def _score_column(
        self,
        column,
        concept
    ):

        aliases = (
            self.CONCEPT_ALIASES[
                concept
            ]
        )

        column_name = (
            column[
                "normalized_column"
            ]
        )

        table_name = (
            column[
                "normalized_table"
            ]
        )

        score = 0


        # ----------------------------------------------------
        # NOMBRE DE COLUMNA
        # ----------------------------------------------------

        for alias in aliases:

            # Año = "ano"
            # Mes = "mes"
            if column_name == alias:
                score += 100

            elif alias in column_name:
                score += 50


        # ----------------------------------------------------
        # PREFERENCIA POR TABLA CALENDARIO
        # ----------------------------------------------------

        if table_name == "calendario":
            score += 60

        elif any(
            preferred in table_name
            for preferred
            in self.PREFERRED_DATE_TABLES
        ):
            score += 30


        # ----------------------------------------------------
        # COLUMNAS VISIBLES
        # ----------------------------------------------------

        if not column.get(
            "is_hidden"
        ):
            score += 5


        # ----------------------------------------------------
        # TIPO DE DATO
        # ----------------------------------------------------

        data_type = normalize_name(
            column.get(
                "data_type"
            )
        )

        if concept == "year":

            if any(
                item in data_type
                for item in [
                    "integer",
                    "int64",
                    "whole",
                    "number",
                ]
            ):
                score += 10


        return score


    # ========================================================
    # BUSCAR CANDIDATOS
    # ========================================================

    def _find_candidates(
        self,
        concept
    ):

        candidates = []

        for column in self.columns:

            score = self._score_column(
                column,
                concept
            )

            if score > 0:

                candidate = {
                    **column,
                    "score": score
                }

                candidates.append(
                    candidate
                )


        candidates.sort(
            key=lambda item:
                item["score"],
            reverse=True
        )

        return candidates


    # ========================================================
    # RESOLVER VALOR
    # ========================================================

    def _resolve_value(
        self,
        concept,
        raw_value,
        candidate
    ):

        if concept == "year":

            return int(
                raw_value
            )


        if concept == "month":

            data_type = normalize_name(
                candidate.get(
                    "data_type"
                )
            )

            column_name = normalize_name(
                candidate.get(
                    "column"
                )
            )

            # Ej:
            # MesNumero = 8
            if (
                any(
                    item in column_name
                    for item in [
                        "numero",
                        "num",
                        "nro",
                    ]
                )
                or any(
                    item in data_type
                    for item in [
                        "integer",
                        "int64",
                        "number",
                    ]
                )
            ):

                return int(
                    raw_value
                )

            # Ej:
            # Calendario[Mes] = "agosto"
            return MONTH_NAMES.get(
                int(raw_value)
            )


        return raw_value


    # ========================================================
    # RESOLVER UN CONCEPTO
    # ========================================================

    def resolve_concept(
        self,
        concept,
        raw_value
    ):

        candidates = (
            self._find_candidates(
                concept
            )
        )

        if not candidates:

            return {
                "status":
                    "not_found",

                "concept":
                    concept,

                "raw_value":
                    raw_value
            }


        best = candidates[0]


        # ----------------------------------------------------
        # AMBIGÜEDAD
        # ----------------------------------------------------

        if len(candidates) > 1:

            second = candidates[1]

            difference = (
                best["score"]
                - second["score"]
            )

            if (
                difference
                < self.ambiguity_margin
                and (
                    best["table"]
                    != second["table"]
                    or
                    best["column"]
                    != second["column"]
                )
            ):

                return {
                    "status":
                        "ambiguous",

                    "concept":
                        concept,

                    "raw_value":
                        raw_value,

                    "candidates":
                        candidates[:5]
                }


        value = self._resolve_value(
            concept,
            raw_value,
            best
        )


        return {

            "status":
                "resolved",

            "concept":
                concept,

            "table":
                best["table"],

            "column":
                best["column"],

            "operator":
                "=",

            "value":
                value,

            "raw_value":
                raw_value,

            "data_type":
                best["data_type"],

            "score":
                best["score"]
        }


    # ========================================================
    # RESOLVER TODOS LOS FILTROS
    # ========================================================

    def resolve(
        self,
        intent_data
    ):

        filters = []

        problems = []


        # ----------------------------------------------------
        # AÑO
        # ----------------------------------------------------

        year = intent_data.get(
            "year"
        )

        if year is not None:

            result = (
                self.resolve_concept(
                    "year",
                    year
                )
            )

            if (
                result["status"]
                == "resolved"
            ):

                filters.append(
                    result
                )

            else:

                problems.append(
                    result
                )


        # ----------------------------------------------------
        # MES
        # ----------------------------------------------------

        month = intent_data.get(
            "month"
        )

        if month is not None:

            result = (
                self.resolve_concept(
                    "month",
                    month
                )
            )

            if (
                result["status"]
                == "resolved"
            ):

                filters.append(
                    result
                )

            else:

                problems.append(
                    result
                )


        # ----------------------------------------------------
        # RESULTADO
        # ----------------------------------------------------

        if problems:

            return {

                "status":
                    "needs_review",

                "filters":
                    filters,

                "problems":
                    problems
            }


        return {

            "status":
                "resolved",

            "filters":
                filters,

            "problems":
                []
        }