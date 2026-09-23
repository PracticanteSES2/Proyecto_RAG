import json
from pathlib import Path

import pandas as pd


def load_csv(file_path: Path) -> pd.DataFrame:
    """
    Carga un CSV exportado desde SSMS.
    Detecta el separador y limpia los nombres
    de las columnas.
    """

    try:
        df = pd.read_csv(
            file_path,
            sep=None,
            engine="python",
            encoding="utf-8-sig"
        )

    except UnicodeDecodeError:

        df = pd.read_csv(
            file_path,
            sep=None,
            engine="python",
            encoding="latin-1"
        )

    df.columns = [
        str(column)
        .strip()
        .replace("[", "")
        .replace("]", "")
        for column in df.columns
    ]

    df = df.where(
        pd.notnull(df),
        None
    )

    return df


def clean_value(value):

    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    return value


def dataframe_to_records(df):

    return [
        {
            str(key): clean_value(value)
            for key, value
            in row.to_dict().items()
        }
        for _, row in df.iterrows()
    ]


def row_to_dict(row):

    return {
        str(key): clean_value(value)
        for key, value
        in row.to_dict().items()
    }


def get_column(
    df,
    possible_names
):

    normalized = {
        str(column)
        .replace("[", "")
        .replace("]", "")
        .strip()
        .lower(): column

        for column in df.columns
    }

    for name in possible_names:

        key = name.lower()

        if key in normalized:
            return normalized[key]

    return None


def normalize_bool(value):

    if value is None:
        return False

    if isinstance(value, bool):
        return value

    return (
        str(value)
        .strip()
        .lower()
        in [
            "true",
            "1",
            "yes"
        ]
    )


def is_system_table(table_name):

    if not table_name:
        return True

    name = str(
        table_name
    ).lower()

    system_patterns = [
        "localdatetable",
        "datetabletemplate"
    ]

    return any(
        pattern in name
        for pattern
        in system_patterns
    )


def save_json(
    data,
    output_file
):

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        output_file,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
            default=str
        )