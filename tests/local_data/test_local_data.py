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


LAVANDERIA_DOC = {
    "dashboards": [{
        "name": "LAVANDERIA",
        "sql_queries": [
            "SELECT A.OID, A.Peso, A.FechaRegistro, B.Fecha, B.Turno, C.Nombre SERVICIO, "
            "D.usu_nombres, D.usu_apellidos FROM PESAJE A"
        ],
        "documented_measures": [],
        "calculated_columns": [
            {"table": "LAVANDERIA", "name": "NOMBRE_COMPLETO",
             "expression": 'CONCATENATE(LAVANDERIA[usu_nombres],CONCATENATE(" ",LAVANDERIA[usu_apellidos]))'},
            {"table": "LAVANDERIA", "name": "TURNO_OK",
             "expression": 'IF(LAVANDERIA[Turno]=1, "MAÑANA", IF(LAVANDERIA[Turno]=2,"TARDE", '
                           'IF(LAVANDERIA[Turno]=3,"NOCHE")))'},
        ],
        "visuals": [
            "Filtros por Años y Mes: Permiten segmentar la información por Año y Mes.",
            "Tabla de Participación por Servicio: Muestra la distribución de pesos registrados "
            "mensualmente por cada área de servicios, obteniendo también su porcentaje de participación.",
            "Tabla de registro de Usuarios: Muestra la distribución de peso registrados para lavandería "
            "por cada colaborador de las áreas del hospital.",
            "Gráfico Circular de Peso por Turno Laboral: Muestra la distribución de cargas teniendo en "
            "cuenta los turnos laborales.",
            "Gráfico de Barras por Distribución Mensual: Muestra el total de distribución de cargas mensuales.",
        ],
    }],
}

ANTIBIOTICOS_DOC = {
    "dashboards": [{
        "name": "ANTIBIOTICOS",
        "sql_queries": [
            "SELECT C.PACNUMDOC AS DOCUMENTO, S.HSUNOMBRE AS SERVICIO, J.IPRDESCOR AS ANTIBIOTICO, "
            "CAST(G.hcrhorreg AS DATE) AS HORA_APLICACION, CASE WHEN X = 1 THEN 'SUSPENDIDO' "
            "WHEN Y > 0 THEN 'ACTIVO' ELSE 'FINALIZADO' END AS Suspension FROM T"
        ],
        "documented_measures": [
            {"table": "ANTIBIOTICOS", "name": "Dias Suministrados",
             "expression": "DISTINCTCOUNT( ANTIBIOTICOS[HORA_APLICACION] )",
             "description": "Número de aplicaciones registradas del antibiótico en el periodo filtrado."},
            {"table": "ANTIBIOTICOS", "name": "PAC_ACT",
             "expression": 'CALCULATE(DISTINCTCOUNT(ANTIBIOTICOS[DOCUMENTO]), ANTIBIOTICOS[Suspension] = "ACTIVO")',
             "description": "Número de pacientes únicos con tratamiento antibiótico en estado ACTIVO."},
            {"table": "ANTIBIOTICOS", "name": "TOTAL ATB",
             "expression": "COUNTROWS(ANTIBIOTICOS)",
             "description": "Número total de dosis de antibióticos administradas en el periodo seleccionado."},
        ],
        "calculated_columns": [],
        "visuals": [
            "Tarjetas – Indicadores principales: Las tarjetas muestran el total de dosis de antibióticos "
            "suministradas y la cantidad de pacientes activos de acuerdo con los filtros seleccionados.",
            "Gráfico – Pacientes activos por servicio: Muestra la distribución de pacientes activos según "
            "el servicio hospitalario.",
        ],
    }],
}

CVC_DOC = {
    "dashboards": [{
        "name": "CVC",
        "sql_queries": ["SELECT A.OIDPRODUCTO, A.CANTIDAD, A.ULTIMOCOSTO, B.IPRDESCOR FROM COSTOS A"],
        "documented_measures": [],
        "calculated_columns": [
            {"table": "COSTOS_PRODUCTOS", "name": "ESTADO",
             "expression": 'IF(COSTOS_PRODUCTOS[ULTIMOCOSTO]-COSTOS_PRODUCTOS[COSTO_ANTERIOR]>0,"AUMENTÓ",'
                           'IF(COSTOS_PRODUCTOS[ULTIMOCOSTO]-COSTOS_PRODUCTOS[COSTO_ANTERIOR]<0,"DISMINUYÓ","ESTABLE"))'},
        ],
        "visuals": [
            "Tarjetas de Indicadores: Muestra los indicadores de total de productos, el Total de compras "
            "con aumento y el Total de compras con disminución.",
            "Gráfico de Líneas de Tendencia de Costos",
            "Muestra el índice de desviación estándar de la tendencia de costos de los productos",
        ],
    }],
}


def _inferred(name, document):
    from tools.local_data.infer_metadata import build_inferred_metadata

    with tempfile.TemporaryDirectory() as tmp:
        result = build_inferred_metadata(name, Path(tmp) / "m", documents=[document])
        values_file = Path(tmp) / "m" / "_documented_values.json"
        values = values_file.read_text(encoding="utf-8") if values_file.exists() else ""
        measures = _rows(Path(tmp) / "m" / "measures.csv")
        columns = _rows(Path(tmp) / "m" / "columns.csv")
    return result, values, measures, columns


def _fields(result):
    return [
        (visual["visual_type"], visual["title"], [field["queryRef"] for field in visual["fields"]])
        for page in result["inferred_report"]["pages"] for visual in page["visuals"]
    ]


def test_documented_report_numeric_column_and_types():
    result, values, _measures, columns = _inferred("TABLERO LAVANDERIA", LAVANDERIA_DOC)
    fields = _fields(result)
    # SUM(Peso) implícito, sin título (una sola métrica «Peso»), por SERVICIO,
    # colaborador (NOMBRE_COMPLETO) y turno (la columna calculada legible).
    assert ("tableEx", None, ["LAVANDERIA.SERVICIO", "Sum(LAVANDERIA.Peso)"]) in fields, fields
    assert ("tableEx", None, ["LAVANDERIA.NOMBRE_COMPLETO", "Sum(LAVANDERIA.Peso)"]) in fields, fields
    assert ("clusteredBarChart", None, ["LAVANDERIA.TURNO_OK", "Sum(LAVANDERIA.Peso)"]) in fields, fields
    # «cargas mensuales» no nombra ninguna columna: no se inventa un visual.
    assert len(fields) == 3, fields
    assert result["inferred_report"]["summary"]["added_measures"] == []
    by_name = {c["Name"]: c for c in columns}
    # LAVANDERIA[Turno]=1 en el DAX documentado -> entero (no texto).
    assert by_name["Turno"]["DataType"] == "Integer"
    assert '"MAÑANA"' in values and '"NOCHE"' in values


def test_documented_report_links_cards_to_documented_measures():
    result, values, measures, _columns = _inferred("TABLERO ANTIBIOTICOS", ANTIBIOTICOS_DOC)
    fields = _fields(result)
    assert ("card", "Total de dosis de antibióticos suministradas", ["ANTIBIOTICOS.TOTAL ATB"]) in fields, fields
    assert ("card", "Cantidad de pacientes activos", ["ANTIBIOTICOS.PAC_ACT"]) in fields, fields
    assert ("clusteredBarChart", "Pacientes activos por servicio",
            ["ANTIBIOTICOS.SERVICIO", "ANTIBIOTICOS.PAC_ACT"]) in fields, fields
    assert {m["Name"] for m in measures} == {"Dias Suministrados", "PAC_ACT", "TOTAL ATB"}
    assert '"SUSPENDIDO"' in values and '"FINALIZADO"' in values


def test_documented_report_qualified_count_measure():
    result, _values, measures, _columns = _inferred("TABLERO CVC", CVC_DOC)
    fields = _fields(result)
    by_name = {m["Name"]: m for m in measures}
    aumento = by_name["Total de compras con aumento"]
    assert aumento["Expression"] == (
        "CALCULATE(COUNTROWS('COSTOS_PRODUCTOS'), 'COSTOS_PRODUCTOS'[ESTADO] = \"AUMENTÓ\")"
    ), aumento["Expression"]
    assert aumento["DisplayFolder"] == "inferred_from_documentation"
    assert "DISMINUYÓ" in by_name["Total de compras con disminución"]["Expression"]
    # «total de productos» -> conteo distinto del OID del producto.
    assert ("card", "Total de productos", ["CountNonNull(COSTOS_PRODUCTOS.OIDPRODUCTO)"]) in fields, fields
    # «Tendencia de Costos» no es una entidad contable: sin visual ni medida.
    assert not any("endencia" in str(title) for _kind, title, _f in fields), fields
    assert len(by_name) == 2, sorted(by_name)


def test_inferred_pbir_feeds_owner_visual_catalog():
    from src.semantic.visual_catalog_builder import PBIRVisualCatalogBuilder
    from tools.local_data.infer_metadata import build_inferred_metadata
    from tools.local_data.infer_visuals import write_inferred_report

    with tempfile.TemporaryDirectory() as tmp:
        result = build_inferred_metadata("TABLERO LAVANDERIA", Path(tmp) / "m", documents=[LAVANDERIA_DOC])
        report = write_inferred_report(
            "TABLERO LAVANDERIA", result["inferred_report"]["pages"], Path(tmp) / "pbir",
        )
        catalog = PBIRVisualCatalogBuilder(report, metadata_dir=Path(tmp) / "m",
                                           semantic_model="TABLERO LAVANDERIA").build()
    metrics = catalog["metrics"]
    assert metrics and all(m["dax_expression"] == "SUM('LAVANDERIA'[Peso])" for m in metrics), metrics
    assert all(m["validation_status"] == "approved" for m in metrics)


def test_documented_values_sql_case_and_filters():
    from tools.local_data.documented_values import DocumentedValues

    values = DocumentedValues()
    values.ingest_sql(
        "SELECT CASE WHEN E.X LIKE '%SURA%' THEN 'SURA' WHEN E.X = 'N' THEN 'NUEVA EPS' ELSE 'OTRAS' END "
        "AS ASEGURADORA, CASE WHEN EDAD < 18 THEN 'MENORES DE EDAD' ELSE 'MAYORES DE EDAD' END MENORES, "
        "P.GPANOMCOM AS NOMBRE_PACIENTE, T.HCCODIGO FROM T WHERE T.HCCODIGO IN ('I','II') "
        "AND C.IALCODIGO IN ('062')"
    )
    items = {column: entry["values"] for (_table, column), entry in values.items.items()}
    assert items["ASEGURADORA"] == ["SURA", "NUEVA EPS", "OTRAS"], items
    assert items["MENORES"] == ["MENORES DE EDAD", "MAYORES DE EDAD"], items
    assert items["HCCODIGO"] == ["I", "II"], items
    assert "IALCODIGO" not in items and "NOMBRE_PACIENTE" not in items, items


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
