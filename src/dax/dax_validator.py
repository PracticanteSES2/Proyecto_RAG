import json
import re
import unicodedata
from pathlib import Path


class DAXValidator:

    ALLOWED_OPERATORS = {
        "=",
        "<>",
        ">",
        "<",
        ">=",
        "<="
    }

    # Como nuestras consultas las genera nuestro propio
    # DAXGenerator, podemos ser bastante restrictivos.
    FORBIDDEN_PATTERNS = [
        r"\bDEFINE\b",
        r"\bINFO\.",
        r"\bEVALUATEANDLOG\b",
    ]

    MAX_FILTERS = 15

    def __init__(
        self,
        technical_catalog_path
    ):

        self.catalog = self._load_json(
            technical_catalog_path
        )

        self.tables = {}
        self.measures = {}

        self._build_indexes()


    # ========================================================
    # UTILIDADES
    # ========================================================

    def _load_json(self, path):

        with open(
            path,
            "r",
            encoding="utf-8"
        ) as file:

            return json.load(file)


    def _normalize(self, value):

        if value is None:
            return ""

        value = str(value).strip().lower()

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


    # ========================================================
    # ÍNDICES DEL MODELO
    # ========================================================

    def _build_indexes(self):

        for table in self.catalog.get(
            "tables",
            []
        ):

            table_name = table.get(
                "name"
            )

            if not table_name:
                continue

            normalized_table = (
                self._normalize(
                    table_name
                )
            )

            self.tables[
                normalized_table
            ] = {
                "name": table_name,
                "columns": {}
            }

            # Columnas
            for column in table.get(
                "columns",
                []
            ):

                column_name = column.get(
                    "name"
                )

                if not column_name:
                    continue

                normalized_column = (
                    self._normalize(
                        column_name
                    )
                )

                self.tables[
                    normalized_table
                ]["columns"][
                    normalized_column
                ] = column_name

            # Medidas
            for measure in table.get(
                "measures",
                []
            ):

                measure_name = measure.get(
                    "name"
                )

                if not measure_name:
                    continue

                normalized_measure = (
                    self._normalize(
                        measure_name
                    )
                )

                self.measures[
                    normalized_measure
                ] = {
                    "name":
                        measure_name,

                    "table":
                        table_name
                }


    # ========================================================
    # VALIDAR MEDIDA
    # ========================================================

    def _validate_measure(
        self,
        metric_result,
        errors
    ):

        measure = metric_result.get(
            "measure"
        )

        if not measure:

            errors.append(
                "La consulta no contiene "
                "una medida resuelta."
            )

            return

        normalized_measure = (
            self._normalize(
                measure
            )
        )

        if (
            normalized_measure
            not in self.measures
        ):

            errors.append(
                f"La medida '{measure}' "
                "no existe en el catálogo "
                "del modelo semántico."
            )


    # ========================================================
    # VALIDAR FILTROS
    # ========================================================

    def _validate_filters(
        self,
        filter_result,
        errors
    ):

        filters = filter_result.get(
            "filters",
            []
        )

        if len(filters) > self.MAX_FILTERS:

            errors.append(
                "La consulta contiene demasiados "
                f"filtros ({len(filters)}). "
                f"Máximo permitido: "
                f"{self.MAX_FILTERS}."
            )

            return


        for index, filter_data in enumerate(
            filters,
            start=1
        ):

            table = filter_data.get(
                "table"
            )

            column = filter_data.get(
                "column"
            )

            operator = filter_data.get(
                "operator"
            )

            value = filter_data.get(
                "value"
            )


            # --------------------------------------------
            # TABLA
            # --------------------------------------------

            normalized_table = (
                self._normalize(
                    table
                )
            )

            if (
                normalized_table
                not in self.tables
            ):

                errors.append(
                    f"Filtro {index}: "
                    f"la tabla '{table}' "
                    "no existe."
                )

                continue


            # --------------------------------------------
            # COLUMNA
            # --------------------------------------------

            normalized_column = (
                self._normalize(
                    column
                )
            )

            table_columns = (
                self.tables[
                    normalized_table
                ]["columns"]
            )

            if (
                normalized_column
                not in table_columns
            ):

                errors.append(
                    f"Filtro {index}: "
                    f"la columna "
                    f"'{table}[{column}]' "
                    "no existe."
                )


            # --------------------------------------------
            # OPERADOR
            # --------------------------------------------

            if (
                operator
                not in self.ALLOWED_OPERATORS
            ):

                errors.append(
                    f"Filtro {index}: "
                    f"operador '{operator}' "
                    "no permitido."
                )


            # --------------------------------------------
            # VALOR
            # --------------------------------------------

            if value is None:

                errors.append(
                    f"Filtro {index}: "
                    "el valor del filtro "
                    "es nulo."
                )


    # ========================================================
    # VALIDAR TEXTO DAX
    # ========================================================

    def _validate_dax_text(
        self,
        dax,
        errors
    ):

        if not dax:

            errors.append(
                "No existe una consulta DAX."
            )

            return


        normalized_dax = (
            dax.strip()
        )


        # Debe ser una consulta
        if not normalized_dax.upper().startswith(
            "EVALUATE"
        ):

            errors.append(
                "La consulta DAX debe "
                "comenzar con EVALUATE."
            )


        # Nuestra versión inicial exige ROW
        if not re.search(
            r"\bROW\s*\(",
            normalized_dax,
            flags=re.IGNORECASE
        ):

            errors.append(
                "La consulta no utiliza "
                "la estructura ROW esperada."
            )


        # Patrones que no permitiremos
        for pattern in self.FORBIDDEN_PATTERNS:

            if re.search(
                pattern,
                normalized_dax,
                flags=re.IGNORECASE
            ):

                errors.append(
                    "La consulta contiene "
                    f"una construcción no permitida: "
                    f"{pattern}"
                )


    # ========================================================
    # VALIDACIÓN PRINCIPAL
    # ========================================================

    def validate(
        self,
        dax_result,
        metric_result,
        filter_result
    ):

        errors = []
        warnings = []


        # --------------------------------------------
        # ESTADOS PREVIOS
        # --------------------------------------------

        if (
            metric_result.get("status")
            != "resolved"
        ):

            errors.append(
                "La métrica no fue resuelta "
                "correctamente."
            )


        if (
            filter_result.get("status")
            != "resolved"
        ):

            errors.append(
                "Los filtros no fueron "
                "resueltos correctamente."
            )


        if (
            dax_result.get("status")
            != "generated"
        ):

            errors.append(
                "El DAX Generator no generó "
                "una consulta válida."
            )


        # --------------------------------------------
        # VALIDACIONES
        # --------------------------------------------

        self._validate_measure(
            metric_result,
            errors
        )

        self._validate_filters(
            filter_result,
            errors
        )

        self._validate_dax_text(
            dax_result.get(
                "dax"
            ),
            errors
        )


        # --------------------------------------------
        # ADVERTENCIAS
        # --------------------------------------------

        if not filter_result.get(
            "filters"
        ):

            warnings.append(
                "La consulta no contiene filtros. "
                "Se calculará la medida sobre "
                "todo el contexto disponible."
            )


        # --------------------------------------------
        # RESULTADO
        # --------------------------------------------

        if errors:

            return {
                "status": "rejected",
                "valid": False,
                "errors": errors,
                "warnings": warnings,
                "dax": dax_result.get(
                    "dax"
                )
            }


        return {
            "status": "validated",
            "valid": True,
            "errors": [],
            "warnings": warnings,
            "dax": dax_result.get(
                "dax"
            )
        }