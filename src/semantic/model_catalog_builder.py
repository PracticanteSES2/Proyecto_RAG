from pathlib import Path

import pandas as pd

from src.semantic.catalog_utils import (
    clean_value,
    dataframe_to_records,
    get_column,
    is_system_table,
    normalize_bool,
    row_to_dict,
    load_csv,
    save_json
)


# ============================================================
# CONFIGURACIÓN
# ============================================================

PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)


WORKSPACE_NAME = (
    "Gestion Clinica"
)

SEMANTIC_MODEL_NAME = (
    "TABLERO DE ATENCIONES INSTITUCIONALES"
)


MODEL_SLUG = (
    "tablero_de_atenciones_institucionales"
)


BASE_DIR = (
    PROJECT_ROOT
    / "data"
    / "model_metadata"
    / MODEL_SLUG
)


OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "catalog"
)

def load_metadata():

    print(
        "Leyendo metadata de Power BI...\n"
    )

    tables = load_csv(
        BASE_DIR / "tables.csv"
    )

    columns = load_csv(
        BASE_DIR / "columns.csv"
    )

    measures = load_csv(
        BASE_DIR / "measures.csv"
    )

    relationships = load_csv(
        BASE_DIR / "relationships.csv"
    )


    print(
        f"Tablas encontradas:       "
        f"{len(tables)}"
    )

    print(
        f"Columnas encontradas:     "
        f"{len(columns)}"
    )

    print(
        f"Medidas encontradas:      "
        f"{len(measures)}"
    )

    print(
        f"Relaciones encontradas:   "
        f"{len(relationships)}"
    )


    return {
        "tables": tables,
        "columns": columns,
        "measures": measures,
        "relationships": relationships
    }

def build_raw_catalog(
    metadata
):

    catalog = {

        "workspace":
            WORKSPACE_NAME,

        "semantic_model":
            SEMANTIC_MODEL_NAME,

        "metadata": {

            "tables":
                dataframe_to_records(
                    metadata["tables"]
                ),

            "columns":
                dataframe_to_records(
                    metadata["columns"]
                ),

            "measures":
                dataframe_to_records(
                    metadata["measures"]
                ),

            "relationships":
                dataframe_to_records(
                    metadata[
                        "relationships"
                    ]
                )
        }
    }


    output_file = (
        OUTPUT_DIR
        / f"{MODEL_SLUG}.json"
    )


    save_json(
        catalog,
        output_file
    )


    print(
        "\nCatálogo bruto generado:"
    )

    print(
        output_file
    )


    return catalog

def build_normalized_catalog(
    metadata
):

    tables = metadata["tables"]
    columns = metadata["columns"]
    measures = metadata["measures"]
    relationships = (
        metadata["relationships"]
    )


    table_name_col = get_column(
        tables,
        ["Name"]
    )

    column_table_col = get_column(
        columns,
        ["Table"]
    )

    measure_table_col = get_column(
        measures,
        ["Table"]
    )


    catalog_tables = []


    for _, table_row in (
        tables.iterrows()
    ):

        table_name = clean_value(
            table_row[
                table_name_col
            ]
        )


        if not table_name:
            continue


        if column_table_col:

            table_columns = columns[
                columns[
                    column_table_col
                ]
                == table_name
            ]

        else:

            table_columns = (
                pd.DataFrame()
            )


        if measure_table_col:

            table_measures = measures[
                measures[
                    measure_table_col
                ]
                == table_name
            ]

        else:

            table_measures = (
                pd.DataFrame()
            )


        table_object = {

            "name":
                table_name,

            "metadata":
                row_to_dict(
                    table_row
                ),

            "columns": [
                row_to_dict(row)
                for _, row
                in table_columns.iterrows()
            ],

            "measures": [
                row_to_dict(row)
                for _, row
                in table_measures.iterrows()
            ]
        }


        catalog_tables.append(
            table_object
        )


    catalog = {

        "workspace":
            WORKSPACE_NAME,

        "semantic_model":
            SEMANTIC_MODEL_NAME,

        "tables":
            catalog_tables,

        "relationships":
            dataframe_to_records(
                relationships
            )
    }


    output_file = (
        OUTPUT_DIR
        / (
            f"{MODEL_SLUG}"
            "_normalized.json"
        )
    )


    save_json(
        catalog,
        output_file
    )


    print(
        "\nCatálogo normalizado generado:"
    )

    print(
        output_file
    )


    return catalog

def build_rag_catalog(
    metadata
):

    tables = metadata["tables"]
    columns = metadata["columns"]
    measures = metadata["measures"]
    relationships = (
        metadata["relationships"]
    )


    # ========================================================
    # COLUMNAS DE TABLES
    # ========================================================

    table_name_col = get_column(
        tables,
        ["Name"]
    )

    table_description_col = get_column(
        tables,
        ["Description"]
    )

    table_hidden_col = get_column(
        tables,
        ["IsHidden"]
    )

    table_storage_col = get_column(
        tables,
        ["StorageMode"]
    )


    # ========================================================
    # COLUMNAS DE COLUMNS
    # ========================================================

    column_name_col = get_column(
        columns,
        ["Name"]
    )

    column_table_col = get_column(
        columns,
        ["Table"]
    )

    column_description_col = get_column(
        columns,
        ["Description"]
    )

    column_datatype_col = get_column(
        columns,
        ["DataType"]
    )

    column_expression_col = get_column(
        columns,
        ["Expression"]
    )

    column_hidden_col = get_column(
        columns,
        ["IsHidden"]
    )


    # ========================================================
    # COLUMNAS DE MEASURES
    # ========================================================

    measure_name_col = get_column(
        measures,
        ["Name"]
    )

    measure_table_col = get_column(
        measures,
        ["Table"]
    )

    measure_description_col = get_column(
        measures,
        ["Description"]
    )

    measure_datatype_col = get_column(
        measures,
        ["DataType"]
    )

    measure_expression_col = get_column(
        measures,
        ["Expression"]
    )

    measure_format_col = get_column(
        measures,
        ["FormatString"]
    )

    measure_hidden_col = get_column(
        measures,
        ["IsHidden"]
    )

    measure_state_col = get_column(
        measures,
        ["State"]
    )


    # ========================================================
    # TABLAS ÚTILES
    # ========================================================

    rag_tables = []


    for _, table_row in (
        tables.iterrows()
    ):

        table_name = clean_value(
            table_row[
                table_name_col
            ]
        )


        if not table_name:
            continue


        if is_system_table(
            table_name
        ):
            continue


        table_columns_df = (
            columns[
                columns[
                    column_table_col
                ]
                == table_name
            ]
            if column_table_col
            else pd.DataFrame()
        )


        table_measures_df = (
            measures[
                measures[
                    measure_table_col
                ]
                == table_name
            ]
            if measure_table_col
            else pd.DataFrame()
        )


        clean_columns = []


        for _, column_row in (
            table_columns_df.iterrows()
        ):

            clean_columns.append({

                "name":
                    clean_value(
                        column_row[
                            column_name_col
                        ]
                    )
                    if column_name_col
                    else None,

                "description":
                    clean_value(
                        column_row[
                            column_description_col
                        ]
                    )
                    if column_description_col
                    else None,

                "data_type":
                    clean_value(
                        column_row[
                            column_datatype_col
                        ]
                    )
                    if column_datatype_col
                    else None,

                "expression":
                    clean_value(
                        column_row[
                            column_expression_col
                        ]
                    )
                    if column_expression_col
                    else None,

                "is_hidden":
                    normalize_bool(
                        column_row[
                            column_hidden_col
                        ]
                    )
                    if column_hidden_col
                    else False
            })


        clean_measures = []


        for _, measure_row in (
            table_measures_df.iterrows()
        ):

            clean_measures.append({

                "name":
                    clean_value(
                        measure_row[
                            measure_name_col
                        ]
                    )
                    if measure_name_col
                    else None,

                "description":
                    clean_value(
                        measure_row[
                            measure_description_col
                        ]
                    )
                    if measure_description_col
                    else None,

                "data_type":
                    clean_value(
                        measure_row[
                            measure_datatype_col
                        ]
                    )
                    if measure_datatype_col
                    else None,

                "expression":
                    clean_value(
                        measure_row[
                            measure_expression_col
                        ]
                    )
                    if measure_expression_col
                    else None,

                "format_string":
                    clean_value(
                        measure_row[
                            measure_format_col
                        ]
                    )
                    if measure_format_col
                    else None,

                "is_hidden":
                    normalize_bool(
                        measure_row[
                            measure_hidden_col
                        ]
                    )
                    if measure_hidden_col
                    else False,

                "state":
                    clean_value(
                        measure_row[
                            measure_state_col
                        ]
                    )
                    if measure_state_col
                    else None
            })


        rag_tables.append({

            "name":
                table_name,

            "description":
                clean_value(
                    table_row[
                        table_description_col
                    ]
                )
                if table_description_col
                else None,

            "storage_mode":
                clean_value(
                    table_row[
                        table_storage_col
                    ]
                )
                if table_storage_col
                else None,

            "is_hidden":
                normalize_bool(
                    table_row[
                        table_hidden_col
                    ]
                )
                if table_hidden_col
                else False,

            "columns":
                clean_columns,

            "measures":
                clean_measures
        })


    rag_catalog = {

        "workspace":
            WORKSPACE_NAME,

        # MUY IMPORTANTE:
        # no volver a escribir aquí
        # el nombre manualmente.
        "semantic_model":
            SEMANTIC_MODEL_NAME,

        "tables":
            rag_tables,

        "relationships":
            dataframe_to_records(
                relationships
            )
    }


    output_file = (
        OUTPUT_DIR
        / f"{MODEL_SLUG}_rag.json"
    )


    save_json(
        rag_catalog,
        output_file
    )


    print(
        "\nCatálogo RAG generado:"
    )

    print(
        output_file
    )


    return rag_catalog

def main():

    metadata = load_metadata()


    build_raw_catalog(
        metadata
    )


    build_normalized_catalog(
        metadata
    )


    rag_catalog = (
        build_rag_catalog(
            metadata
        )
    )


    total_columns = sum(
        len(table["columns"])
        for table
        in rag_catalog["tables"]
    )

    total_measures = sum(
        len(table["measures"])
        for table
        in rag_catalog["tables"]
    )


    print(
        "\n=============================="
    )

    print(
        "RESUMEN DEL CATÁLOGO"
    )

    print(
        "=============================="
    )

    print(
        "Tablas útiles:",
        len(
            rag_catalog[
                "tables"
            ]
        )
    )

    print(
        "Columnas:",
        total_columns
    )

    print(
        "Medidas:",
        total_measures
    )

    print(
        "Relaciones:",
        len(
            rag_catalog[
                "relationships"
            ]
        )
    )


if __name__ == "__main__":

    main()