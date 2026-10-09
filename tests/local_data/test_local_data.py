"""Pruebas offline de tools/local_data (TMDL -> INFO.VIEW e inferencia).

Ejecutar:  python -m tests.local_data.test_local_data   (compatible con pytest)
"""
import csv
import io
import sys
import tempfile
import traceback
from pathlib import Path

from tools.local_data.infer_metadata import (
    InferredModelBuilder,
    dax_references,
    sql_select_aliases,
)
from tools.local_data.metadata_format import ROW_NUMBER_COLUMN
from tools.local_data.tmdl_to_metadata import convert, parse_column_reference


TABLE_VENTAS = """table VENTAS
\tlineageTag: 11111111-1111-1111-1111-111111111111

\tmeasure 'Total Ventas' = SUM(VENTAS[VALOR])
\t\tformatString: 0
\t\tlineageTag: 22222222-2222-2222-2222-222222222222

\tmeasure moda =
\t\t\t
\t\t\tvar g = SUMMARIZE(VENTAS, VENTAS[EDAD], "Total", COUNTROWS(VENTAS))
\t\t\treturn
\t\t\tCONCATENATEX(g, [EDAD], "/")
\t\tlineageTag: 33333333-3333-3333-3333-333333333333

\tcolumn OID
\t\tdataType: int64
\t\tformatString: 0
\t\tsummarizeBy: sum
\t\tsourceColumn: OID

\tcolumn FECHA
\t\tdataType: dateTime
\t\tformatString: General Date
\t\tsummarizeBy: none
\t\tsourceColumn: FECHA

\t\tvariation Variación
\t\t\tisDefault
\t\t\trelationship: abc

\tcolumn NOMBRE_OK = ```
\t\t\t
\t\t\tUPPER ( VENTAS[NOMBRE] )
\t\t\t```
\t\tsummarizeBy: none

\tpartition VENTAS = m
\t\tmode: import
\t\tsource =
\t\t\t\tlet
\t\t\t\t    Origen = 1
\t\t\t\tin
\t\t\t\t    Origen
"""

TABLE_DIM = """table 'DIM SEDE'
\tisHidden

\tcolumn OID
\t\tdataType: int64
\t\tsourceColumn: OID
"""

RELATIONSHIPS = """relationship r-many
\tfromColumn: VENTAS.OID
\ttoColumn: 'DIM SEDE'.OID

relationship r-one
\tcrossFilteringBehavior: bothDirections
\ttoCardinality: one
\tfromCardinality: one
\tfromColumn: VENTAS.FECHA
\ttoColumn: 'DIM SEDE'.OID
"""


def _rows(path):
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "sin BOM"
    assert b"\r\n" in raw and raw.count(b"\n") == raw.count(b"\r\n"), "solo CRLF"
    return list(csv.DictReader(io.StringIO(raw.decode("utf-8"), newline=""), delimiter=";"))


def _write_model(root):
    definition = root / "Demo.SemanticModel" / "definition"
    (definition / "tables").mkdir(parents=True)
    (definition / "tables" / "VENTAS.tmdl").write_text(TABLE_VENTAS, encoding="utf-8")
    (definition / "tables" / "DIM SEDE.tmdl").write_text(TABLE_DIM, encoding="utf-8")
    (definition / "relationships.tmdl").write_text(RELATIONSHIPS, encoding="utf-8")
    return root / "Demo.SemanticModel"


def test_tmdl_to_info_view_format():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        result = convert(_write_model(root), root / "out")
        assert result["semantic_model_key"] == "demo"
        model_dir = root / "out" / "demo"

        header = (model_dir / "tables.csv").read_bytes().split(b"\r\n")[0]
        assert header.startswith(b"ID;Name;Model;DataCategory;"), header
        line = next(
            row for row in (model_dir / "tables.csv").read_bytes().split(b"\r\n")
            if b';"VENTAS";' in row
        )
        # Textos entre comillas; booleanos y enteros sin ellas.
        assert b';"Regular";"";False;"Import";' in line, line

        tables = {t["Name"]: t for t in _rows(model_dir / "tables.csv")}
        assert set(tables) == {"VENTAS", "DIM SEDE"}
        assert tables["DIM SEDE"]["IsHidden"] == "True"
        assert tables["VENTAS"]["Expression"] == ""

        columns = _rows(model_dir / "columns.csv")
        by_name = {(c["Table"], c["Name"]): c for c in columns}
        assert (("VENTAS", ROW_NUMBER_COLUMN)) in by_name
        assert by_name[("VENTAS", "OID")]["DataType"] == "Integer"
        assert by_name[("VENTAS", "OID")]["IsUnique"] == "False"
        assert by_name[("VENTAS", "FECHA")]["DataType"] == "Date"
        # Lado "uno" de una relación => IsUnique / no anulable.
        assert by_name[("DIM SEDE", "OID")]["IsUnique"] == "True"
        assert by_name[("DIM SEDE", "OID")]["IsNullable"] == "False"
        calculated = by_name[("VENTAS", "NOMBRE_OK")]
        assert calculated["Type"] == "Calculated" and calculated["DataType"] == "Text"
        assert calculated["Expression"] == "\r\nUPPER ( VENTAS[NOMBRE] )", repr(calculated["Expression"])
        assert calculated["ColumnStorage"].startswith("VENTAS (")

        measures = {m["Name"]: m for m in _rows(model_dir / "measures.csv")}
        assert measures["Total Ventas"]["FormatString"] == ""
        assert measures["Total Ventas"]["FormatStringDefinition"] == '"0"'
        assert measures["Total Ventas"]["DataType"] == "Integer"
        assert measures["moda"]["Expression"].startswith("\r\nvar g = SUMMARIZE")
        assert measures["moda"]["DataType"] == "Text"

        relationships = _rows(model_dir / "relationships.csv")
        texts = [r["Relationship"] for r in relationships]
        assert "'VENTAS'[OID] *[<-]1 'DIM SEDE'[OID]" in texts, texts
        # Las 1:1 se listan en ambos sentidos con el mismo ID.
        one_to_one = [r for r in relationships if r["Name"] == "r-one"]
        assert len(one_to_one) == 2 and one_to_one[0]["ID"] == one_to_one[1]["ID"]
        assert "'VENTAS'[FECHA] 1[<->]1 'DIM SEDE'[OID]" in texts


def test_parse_column_reference_quoted():
    assert parse_column_reference("'MATRIZ 2024'.Ingreso") == ("MATRIZ 2024", "Ingreso")
    assert parse_column_reference("T.'Col X'") == ("T", "Col X")
    assert parse_column_reference("LocalDateTable_1-2.Date") == ("LocalDateTable_1-2", "Date")


def test_sql_aliases_and_dax_references():
    sql = (
        "SELECT * FROM (SELECT A.OID OID_CITA, B.GEEDESCRI, CAST(X AS DATE) AS FECHA,\n"
        "CASE WHEN 1=1 THEN 'A' END MAGISTERIO, COUNT(*) OVER() TOTAL,\n"
        "(SELECT 1 FROM T) SUB FROM CITAS A) P"
    )
    assert sql_select_aliases(sql) == [
        "OID_CITA", "GEEDESCRI", "FECHA", "MAGISTERIO", "TOTAL", "SUB",
    ], sql_select_aliases(sql)
    refs = dax_references("CALCULATE(SUM('MATRIZ 2024'[X]), T[Y] = \"a[b]\")")
    assert refs == [("MATRIZ 2024", "X"), ("T", "Y")], refs


def test_inference_measure_vs_calculated_column():
    builder = InferredModelBuilder("Demo")
    builder.ingest_documents([{
        "dashboards": [{
            "name": "Demo",
            "documented_measures": [
                {"table": None, "name": "TOTAL ATB =", "expression": "COUNTROWS(ANTIBIOTICOS)"},
                {"table": "LAVANDERIA", "name": "NOMBRE_COMPLETO",
                 "expression": 'CONCATENATE(LAVANDERIA[usu_nombres], " ")'},
            ],
            "calculated_columns": [],
            "sql_queries": ["SELECT A.Peso, B.Turno FROM X A"],
        }],
    }])
    model = builder.finalize()
    tables = {t["name"]: t for t in model["tables"]}
    assert [m["name"] for m in tables["MEDIDAS"]["measures"]] == ["TOTAL ATB"]
    lavanderia = {c["name"]: c for c in tables["LAVANDERIA"]["columns"]}
    assert lavanderia["NOMBRE_COMPLETO"]["type"] == "Calculated"
    assert "usu_nombres" in lavanderia
    # Sin reporte y con una sola tabla citada por el DAX del tablero, las
    # columnas del SQL van a esa tabla.
    assert {"Peso", "Turno"} <= set(lavanderia), lavanderia

    # Sin ninguna pista => tabla sintetizada con el nombre del tablero.
    builder = InferredModelBuilder("Demo")
    builder.ingest_documents([{"dashboards": [{
        "name": "% Atenciones / Admisiones",
        "sql_queries": ["SELECT T.OID AS OID_TRIAGE, T.GPADOCUME FROM DIM_TRIAGE T"],
    }]}])
    tables = {t["name"]: t for t in builder.finalize()["tables"]}
    assert list(tables) == ["ATENCIONES_ADMISIONES"], list(tables)
    assert [c["name"] for c in tables["ATENCIONES_ADMISIONES"]["columns"]] == ["OID_TRIAGE", "GPADOCUME"]


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, func in tests:
        try:
            func()
            print(f"[PASS] {name}")
        except Exception:
            failed += 1
            print(f"[FAIL] {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
