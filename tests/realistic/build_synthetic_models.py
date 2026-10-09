"""
Genera el overlay versionado de modelos sintéticos:  tests/realistic/synthetic_models/

Son modelos del workspace del propietario cuya metadata real no tenemos (los NOMBRES son reales;
las tablas/medidas son inventadas reutilizando nombres de los modelos reales) para que el entorno
tenga tableros redundantes y se pueda probar la ambigüedad del chatbot:

  - "Total Atenciones", "Total Egresos"/"Egresos", "Cirugías realizadas", "% Ocupación",
    "Consultas"/"Total Consultas", "PROMEDIO_ESTANCIA" existen en varios modelos.
  - Tablas CIRUGIAS, EGRESOS, CONSULTAS_AMBULATORIAS, ASEGURADORAS, DIM_SERVICIO y Calendario
    se repiten con el modelo real TABLERO DE ATENCIONES INSTITUCIONALES.

Por cada modelo escribe:
  <slug>/{tables,columns,measures,relationships}.csv   formato EVALUATE INFO.VIEW.* (coma, cabeceras
                                                       "[ID]" como las devuelve ADOMD)
  <slug>/_metadata_sync.json                           nombre del modelo semántico
  <slug>/source.json                                   manifiesto de la fuente + páginas/visuales + documentación;
                                                       overlay.py materializa con él el PBIR y los chunks RAG

Ejecutar (desde la raíz del repo):  python -m tests.realistic.build_synthetic_models
"""
import csv
import hashlib
import json
import shutil
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "synthetic_models"

CALENDARIO = {
    "expression": 'CALENDAR("2023-01-01", DATE(YEAR(TODAY()), 12, 31))',
    "columns": [
        ("Date", "Date", "calctable", "", {"format": "Short Date"}),
        ("AÑO", "Integer", "calc", "YEAR('Calendario'[Date])"),
        ("MES", "Integer", "calc", "MONTH('Calendario'[Date])"),
        ("NOMBRE_MES", "Text", "calc", "FORMAT('Calendario'[Date], \"MMMM\")"),
        ("TRIMESTRE", "Text", "calc", "\"Trim. \" & INT((MONTH('Calendario'[Date]) + 2) / 3)"),
    ],
}

ASEGURADORAS = {"columns": [("OID", "Integer", "data", "", {"unique": True}), ("NOMBRE", "Text"),
                            ("REGIMEN", "Text")]}
DIM_SERVICIO = {"columns": [("SERVICIO_HOMOLOGADO", "Text", "data", "", {"unique": True}), ("AREA", "Text")]}

MODELS = [
    # ------------------------------------------------------------------
    {
        "slug": "consolidado_de_atenciones_institucionales",
        "name": "CONSOLIDADO DE ATENCIONES INSTITUCIONALES",
        "report": "CONSOLIDADO DE ATENCIONES INSTITUCIONALES",
        "source_group": "consolidado_de_atenciones_institucionales",
        "aliases": ["consolidado de atenciones", "consolidado institucional"],
        "description": ("Tablero consolidado con el total de atenciones institucionales: egresos hospitalarios, "
                        "cirugías realizadas, consultas de urgencias y porcentaje de ocupación por servicio, "
                        "aseguradora, año y mes."),
        "tables": {
            "Calendario": CALENDARIO,
            "ASEGURADORAS": ASEGURADORAS,
            "DIM_SERVICIO": DIM_SERVICIO,
            "EGRESOS": {"columns": [
                ("OID_EGRESO", "Integer", "data", "", {"unique": True}), ("FECHA", "Date"),
                ("OID_ASEGURADORA", "Integer"), ("SERVICIO_HOMOLOGADO", "Text"), ("DIAS_ESTANCIA", "Integer"),
                ("TIPO_EGRESO", "Text"), ("SEXO", "Text"), ("EDAD", "Integer")]},
            "CIRUGIAS": {"columns": [
                ("OID", "Integer", "data", "", {"unique": True}), ("FECHA", "Date"), ("ESPECIALIDAD", "Text"),
                ("ESTADO_CIRUGIA", "Text"), ("OID_ASEGURADORA", "Integer"), ("QUIROFANO", "Text")]},
            "CONSULTA_URGENCIAS": {"columns": [
                ("OID", "Integer", "data", "", {"unique": True}), ("FECHA_ADMISION", "Date"),
                ("CLASIFICACION_TRIAGE", "Text"), ("OID_ASEGURADORA", "Integer"), ("DOCUMENTO", "Text")]},
            "PORCENTAJE_OCUPACIONAL": {"columns": [
                ("FECHADES", "Date"), ("SERVICIO_HOMOLOGADO", "Text"), ("DIAS_CAMA_OCUPADA", "Integer"),
                ("CAMAS_HABILITADAS", "Integer")]},
        },
        "relationships": [
            ("EGRESOS", "FECHA", "Calendario", "Date"), ("CIRUGIAS", "FECHA", "Calendario", "Date"),
            ("CONSULTA_URGENCIAS", "FECHA_ADMISION", "Calendario", "Date"),
            ("PORCENTAJE_OCUPACIONAL", "FECHADES", "Calendario", "Date"),
            ("EGRESOS", "OID_ASEGURADORA", "ASEGURADORAS", "OID"), ("CIRUGIAS", "OID_ASEGURADORA", "ASEGURADORAS", "OID"),
            ("CONSULTA_URGENCIAS", "OID_ASEGURADORA", "ASEGURADORAS", "OID"),
            ("EGRESOS", "SERVICIO_HOMOLOGADO", "DIM_SERVICIO", "SERVICIO_HOMOLOGADO"),
            ("PORCENTAJE_OCUPACIONAL", "SERVICIO_HOMOLOGADO", "DIM_SERVICIO", "SERVICIO_HOMOLOGADO"),
        ],
        "measures": [
            ("EGRESOS", "Total Egresos", "COUNTROWS('EGRESOS')", "Integer", "#,0",
             "Número de egresos hospitalarios."),
            ("EGRESOS", "Egresos", "[Total Egresos]", "Integer", "#,0", "Egresos hospitalarios del periodo."),
            ("EGRESOS", "EGRESOS AÑO ANTERIOR", "CALCULATE([Total Egresos], SAMEPERIODLASTYEAR('Calendario'[Date]))",
             "Integer", "#,0", "Egresos del mismo periodo del año anterior."),
            ("EGRESOS", "PROMEDIO_ESTANCIA", "DIVIDE(SUM(EGRESOS[DIAS_ESTANCIA]), [Total Egresos], BLANK())",
             "Number", "0.00", "Días de estancia promedio por egreso."),
            ("CIRUGIAS", "TOTAL_CIRUGIAS", "COUNTROWS('CIRUGIAS')", "Integer", "#,0", "Total de cirugías registradas."),
            ("CIRUGIAS", "Cirugías realizadas",
             "CALCULATE(COUNTROWS('CIRUGIAS'), CIRUGIAS[ESTADO_CIRUGIA] = \"REALIZADA\")", "Integer", "#,0",
             "Cirugías con estado REALIZADA."),
            ("CONSULTA_URGENCIAS", "Total_consultas_urgencias", "COUNT(CONSULTA_URGENCIAS[DOCUMENTO])", "Integer",
             "#,0", "Consultas atendidas en urgencias."),
            ("PORCENTAJE_OCUPACIONAL", "% Ocupación",
             "DIVIDE(SUM(PORCENTAJE_OCUPACIONAL[DIAS_CAMA_OCUPADA]), SUM(PORCENTAJE_OCUPACIONAL[CAMAS_HABILITADAS]))",
             "Number", "0.00%", "Porcentaje de ocupación de camas."),
            ("EGRESOS", "Total Atenciones",
             "[Total Egresos] + [TOTAL_CIRUGIAS] + [Total_consultas_urgencias]", "Integer", "#,0",
             "Suma de egresos, cirugías y consultas de urgencias."),
        ],
        "pages": [
            {"name": "Resumen", "visuals": [
                ("card", "Total atenciones", [("measure", "EGRESOS", "Total Atenciones")]),
                ("card", "Egresos", [("measure", "EGRESOS", "Total Egresos")]),
                ("card", "Cirugías realizadas", [("measure", "CIRUGIAS", "Cirugías realizadas")]),
                ("card", "% Ocupación", [("measure", "PORCENTAJE_OCUPACIONAL", "% Ocupación")]),
                ("clusteredBarChart", "Egresos por servicio", [("column", "DIM_SERVICIO", "SERVICIO_HOMOLOGADO", "Category"),
                                                              ("measure", "EGRESOS", "Total Egresos", "Y")]),
                ("slicer", None, [("column", "Calendario", "AÑO")]),
                ("slicer", None, [("column", "Calendario", "NOMBRE_MES")]),
                ("slicer", None, [("column", "ASEGURADORAS", "NOMBRE")]),
            ]},
            {"name": "Cirugías", "visuals": [
                ("card", "Total cirugías", [("measure", "CIRUGIAS", "TOTAL_CIRUGIAS")]),
                ("clusteredColumnChart", "Cirugías por especialidad", [("column", "CIRUGIAS", "ESPECIALIDAD", "Category"),
                                                                      ("measure", "CIRUGIAS", "Cirugías realizadas", "Y")]),
                ("slicer", None, [("column", "CIRUGIAS", "ESPECIALIDAD")]),
                ("slicer", None, [("column", "Calendario", "AÑO")]),
            ]},
            {"name": "Urgencias", "visuals": [
                ("card", "Consultas de urgencias", [("measure", "CONSULTA_URGENCIAS", "Total_consultas_urgencias")]),
                ("clusteredBarChart", "Consultas por triage", [("column", "CONSULTA_URGENCIAS", "CLASIFICACION_TRIAGE", "Category"),
                                                              ("measure", "CONSULTA_URGENCIAS", "Total_consultas_urgencias", "Y")]),
                ("slicer", None, [("column", "Calendario", "AÑO")]),
            ]},
        ],
    },
    # ------------------------------------------------------------------
    {
        "slug": "informes_ejecutivos_2026",
        "name": "INFORMES EJECUTIVOS 2026",
        "report": "INFORMES EJECUTIVOS 2026",
        "source_group": "informes_ejecutivos_2026",
        "aliases": ["informe ejecutivo", "informes ejecutivos", "indicadores gerenciales"],
        "description": ("Informe ejecutivo para la gerencia con los indicadores trazadores del año: total de "
                        "atenciones, egresos, cirugías realizadas, consultas y porcentaje de ocupación por sede y servicio."),
        "tables": {
            "Calendario": CALENDARIO,
            "DIM_SEDE": {"columns": [("SEDE", "Text", "data", "", {"unique": True}), ("CIUDAD", "Text")]},
            "FACT_INDICADORES": {"columns": [
                ("FECHA", "Date"), ("SEDE", "Text"), ("SERVICIO", "Text"), ("INDICADOR", "Text"),
                ("CANTIDAD", "Integer")]},
            "FACT_OCUPACION": {"columns": [("FECHA", "Date"), ("SEDE", "Text"), ("PORCENTAJE", "Number")]},
        },
        "relationships": [
            ("FACT_INDICADORES", "FECHA", "Calendario", "Date"), ("FACT_OCUPACION", "FECHA", "Calendario", "Date"),
            ("FACT_INDICADORES", "SEDE", "DIM_SEDE", "SEDE"), ("FACT_OCUPACION", "SEDE", "DIM_SEDE", "SEDE"),
        ],
        "measures": [
            ("FACT_INDICADORES", "Total Atenciones", "SUM(FACT_INDICADORES[CANTIDAD])", "Integer", "#,0",
             "Total de atenciones de todos los indicadores trazadores."),
            ("FACT_INDICADORES", "Egresos",
             "CALCULATE(SUM(FACT_INDICADORES[CANTIDAD]), FACT_INDICADORES[INDICADOR] = \"EGRESOS\")",
             "Integer", "#,0", "Egresos hospitalarios reportados en el informe ejecutivo."),
            ("FACT_INDICADORES", "Cirugías realizadas",
             "CALCULATE(SUM(FACT_INDICADORES[CANTIDAD]), FACT_INDICADORES[INDICADOR] = \"CIRUGIAS\")",
             "Integer", "#,0", "Cirugías realizadas reportadas en el informe ejecutivo."),
            ("FACT_INDICADORES", "Consultas",
             "CALCULATE(SUM(FACT_INDICADORES[CANTIDAD]), FACT_INDICADORES[INDICADOR] = \"CONSULTAS\")",
             "Integer", "#,0", "Consultas (externas y de urgencias) del informe ejecutivo."),
            ("FACT_INDICADORES", "Urgencias",
             "CALCULATE(SUM(FACT_INDICADORES[CANTIDAD]), FACT_INDICADORES[INDICADOR] = \"URGENCIAS\")",
             "Integer", "#,0", "Atenciones de urgencias del informe ejecutivo."),
            ("FACT_OCUPACION", "% Ocupación", "AVERAGE(FACT_OCUPACION[PORCENTAJE])", "Number", "0.0%",
             "Ocupación promedio de camas por sede."),
            ("FACT_INDICADORES", "Variación Egresos vs Año Anterior",
             "VAR Actual = [Egresos] VAR Anterior = CALCULATE([Egresos], SAMEPERIODLASTYEAR('Calendario'[Date])) "
             "RETURN DIVIDE(Actual - Anterior, Anterior)", "Number", "0.0%",
             "Variación porcentual de egresos frente al mismo periodo del año anterior."),
        ],
        "pages": [
            {"name": "Indicadores trazadores", "visuals": [
                ("card", "Total atenciones", [("measure", "FACT_INDICADORES", "Total Atenciones")]),
                ("card", "Egresos", [("measure", "FACT_INDICADORES", "Egresos")]),
                ("card", "Cirugías realizadas", [("measure", "FACT_INDICADORES", "Cirugías realizadas")]),
                ("card", "Consultas", [("measure", "FACT_INDICADORES", "Consultas")]),
                ("card", "% Ocupación", [("measure", "FACT_OCUPACION", "% Ocupación")]),
                ("clusteredColumnChart", "Atenciones por sede", [("column", "DIM_SEDE", "SEDE", "Category"),
                                                                ("measure", "FACT_INDICADORES", "Total Atenciones", "Y")]),
                ("slicer", None, [("column", "DIM_SEDE", "SEDE")]),
                ("slicer", None, [("column", "Calendario", "AÑO")]),
                ("slicer", None, [("column", "Calendario", "NOMBRE_MES")]),
            ]},
        ],
    },
    # ------------------------------------------------------------------
    {
        "slug": "tablero_gestion_camas",
        "name": "TABLERO GESTION CAMAS",
        "report": "TABLERO GESTION CAMAS",
        "source_group": "tablero_gestion_camas",
        "aliases": ["gestion de camas", "tablero de camas", "ocupacion de camas"],
        "description": ("Seguimiento diario de camas hospitalarias: ocupación, camas disponibles, egresos, giro "
                        "cama, estancia promedio y solicitudes de cama por servicio."),
        "tables": {
            "Calendario": CALENDARIO,
            "CAMAS": {"columns": [("OID", "Integer", "data", "", {"unique": True}), ("CODIGO_CAMA", "Text"),
                                  ("SERVICIO", "Text"), ("TIPO_CAMA", "Text")]},
            "OCUPACION_DIARIA": {"columns": [("FECHA", "Date"), ("OID_CAMA", "Integer"), ("ESTADO_CAMA", "Text")]},
            "EGRESOS": {"columns": [("OID_EGRESO", "Integer", "data", "", {"unique": True}), ("FECHA_EGRESO", "Date"),
                                    ("OID_CAMA", "Integer"), ("DIAS_ESTANCIA", "Integer"), ("TIPO_EGRESO", "Text")]},
            "SOLICITUD_CAMAS": {"columns": [("FECHA_SOLICITUD", "Date"), ("SERVICIO", "Text"),
                                            ("ESTADO_SOLICITUD", "Text")]},
        },
        "relationships": [
            ("OCUPACION_DIARIA", "FECHA", "Calendario", "Date"), ("EGRESOS", "FECHA_EGRESO", "Calendario", "Date"),
            ("SOLICITUD_CAMAS", "FECHA_SOLICITUD", "Calendario", "Date"),
            ("OCUPACION_DIARIA", "OID_CAMA", "CAMAS", "OID"), ("EGRESOS", "OID_CAMA", "CAMAS", "OID"),
        ],
        "measures": [
            ("OCUPACION_DIARIA", "% Ocupación",
             "DIVIDE(CALCULATE(COUNTROWS('OCUPACION_DIARIA'), OCUPACION_DIARIA[ESTADO_CAMA] = \"OCUPADA\"), "
             "COUNTROWS('OCUPACION_DIARIA'))", "Number", "0.0%", "Porcentaje de camas ocupadas."),
            ("OCUPACION_DIARIA", "Camas Disponibles",
             "CALCULATE(DISTINCTCOUNT(OCUPACION_DIARIA[OID_CAMA]), OCUPACION_DIARIA[ESTADO_CAMA] = \"DISPONIBLE\")",
             "Integer", "#,0", "Camas en estado disponible."),
            ("EGRESOS", "Egresos", "COUNTROWS('EGRESOS')", "Integer", "#,0", "Egresos registrados en gestión de camas."),
            ("EGRESOS", "Total Egresos", "[Egresos]", "Integer", "#,0", "Total de egresos."),
            ("EGRESOS", "Promedio Estancia", "AVERAGE(EGRESOS[DIAS_ESTANCIA])", "Number", "0.0",
             "Días promedio de estancia."),
            ("EGRESOS", "Giro Cama", "DIVIDE([Egresos], DISTINCTCOUNT(CAMAS[OID]))", "Number", "0.00",
             "Egresos por cama en el periodo."),
            ("SOLICITUD_CAMAS", "Solicitudes de cama", "COUNTROWS('SOLICITUD_CAMAS')", "Integer", "#,0",
             "Solicitudes de cama recibidas."),
        ],
        "pages": [
            {"name": "Ocupación", "visuals": [
                ("card", "% Ocupación", [("measure", "OCUPACION_DIARIA", "% Ocupación")]),
                ("card", "Camas disponibles", [("measure", "OCUPACION_DIARIA", "Camas Disponibles")]),
                ("clusteredBarChart", "Ocupación por servicio", [("column", "CAMAS", "SERVICIO", "Category"),
                                                                ("measure", "OCUPACION_DIARIA", "% Ocupación", "Y")]),
                ("slicer", None, [("column", "CAMAS", "SERVICIO")]),
                ("slicer", None, [("column", "Calendario", "AÑO")]),
                ("slicer", None, [("column", "Calendario", "NOMBRE_MES")]),
            ]},
            {"name": "Egresos y estancia", "visuals": [
                ("card", "Egresos", [("measure", "EGRESOS", "Egresos")]),
                ("card", "Promedio estancia", [("measure", "EGRESOS", "Promedio Estancia")]),
                ("card", "Giro cama", [("measure", "EGRESOS", "Giro Cama")]),
                ("card", "Solicitudes de cama", [("measure", "SOLICITUD_CAMAS", "Solicitudes de cama")]),
                ("slicer", None, [("column", "Calendario", "AÑO")]),
            ]},
        ],
    },
    # ------------------------------------------------------------------
    {
        "slug": "tablero_consulta_externa",
        "name": "TABLERO CONSULTA EXTERNA",
        "report": "TABLERO CONSULTA EXTERNA",
        "source_group": "tablero_consulta_externa",
        "aliases": ["consulta externa", "consultas ambulatorias", "citas medicas"],
        "description": ("Tablero de consulta externa: consultas programadas y cumplidas por especialidad, "
                        "inasistencia, oportunidad de la cita en días y consultas de primera vez por aseguradora."),
        "tables": {
            "Calendario": CALENDARIO,
            "ASEGURADORAS": ASEGURADORAS,
            "CONSULTAS_AMBULATORIAS": {"columns": [
                ("FECHA_CITA", "Date"), ("ESPECIALIDAD", "Text"), ("ESTADO_CITA", "Text"), ("TIPO_CONSULTA", "Text"),
                ("OID_ASEGURADORA", "Integer"), ("IDENTIFICACION", "Text"), ("DIAS_OPORTUNIDAD", "Integer")]},
        },
        "relationships": [
            ("CONSULTAS_AMBULATORIAS", "FECHA_CITA", "Calendario", "Date"),
            ("CONSULTAS_AMBULATORIAS", "OID_ASEGURADORA", "ASEGURADORAS", "OID"),
        ],
        "measures": [
            ("CONSULTAS_AMBULATORIAS", "Total Consultas", "COUNT(CONSULTAS_AMBULATORIAS[IDENTIFICACION])", "Integer",
             "#,0", "Total de citas de consulta externa."),
            ("CONSULTAS_AMBULATORIAS", "Consultas",
             "CALCULATE([Total Consultas], CONSULTAS_AMBULATORIAS[ESTADO_CITA] = \"CUMPLIDA\")", "Integer", "#,0",
             "Consultas cumplidas."),
            ("CONSULTAS_AMBULATORIAS", "Total Atenciones", "[Consultas]", "Integer", "#,0",
             "Atenciones de consulta externa (consultas cumplidas)."),
            ("CONSULTAS_AMBULATORIAS", "% Inasistencia",
             "DIVIDE(CALCULATE([Total Consultas], CONSULTAS_AMBULATORIAS[ESTADO_CITA] = \"INASISTENCIA\"), "
             "[Total Consultas])", "Number", "0.0%", "Porcentaje de citas con inasistencia."),
            ("CONSULTAS_AMBULATORIAS", "Oportunidad promedio (días)",
             "AVERAGE(CONSULTAS_AMBULATORIAS[DIAS_OPORTUNIDAD])", "Number", "0.0",
             "Días promedio entre la solicitud y la cita."),
            ("CONSULTAS_AMBULATORIAS", "Consultas Primera Vez",
             "CALCULATE([Total Consultas], CONSULTAS_AMBULATORIAS[TIPO_CONSULTA] = \"PRIMERA VEZ\")", "Integer",
             "#,0", "Consultas de primera vez."),
        ],
        "pages": [
            {"name": "Consulta externa", "visuals": [
                ("card", "Total consultas", [("measure", "CONSULTAS_AMBULATORIAS", "Total Consultas")]),
                ("card", "Consultas cumplidas", [("measure", "CONSULTAS_AMBULATORIAS", "Consultas")]),
                ("card", "% Inasistencia", [("measure", "CONSULTAS_AMBULATORIAS", "% Inasistencia")]),
                ("card", "Oportunidad (días)", [("measure", "CONSULTAS_AMBULATORIAS", "Oportunidad promedio (días)")]),
                ("clusteredBarChart", "Consultas por especialidad",
                 [("column", "CONSULTAS_AMBULATORIAS", "ESPECIALIDAD", "Category"),
                  ("measure", "CONSULTAS_AMBULATORIAS", "Total Consultas", "Y")]),
                ("slicer", None, [("column", "CONSULTAS_AMBULATORIAS", "ESPECIALIDAD")]),
                ("slicer", None, [("column", "ASEGURADORAS", "NOMBRE")]),
                ("slicer", None, [("column", "Calendario", "AÑO")]),
                ("slicer", None, [("column", "Calendario", "NOMBRE_MES")]),
            ]},
        ],
    },
]

TABLE_HEADERS = ["ID", "Name", "Model", "DataCategory", "Description", "IsHidden", "StorageMode", "TableStorage",
                 "Expression", "ShowAsVariationOnly", "IsPrivate", "CalculationGroupPrecedence", "LineageTag"]
COLUMN_HEADERS = ["ID", "Name", "Table", "DataType", "DataCategory", "Description", "IsHidden", "IsUnique", "IsKey",
                  "IsNullable", "Alignment", "SummarizeBy", "ColumnStorage", "Type", "SourceColumn", "Expression",
                  "FormatString", "IsAvailableInMDX", "SortByColumn", "GroupingBehavior", "SourceProviderType",
                  "DisplayFolder", "AlternateOf", "LineageTag"]
MEASURE_HEADERS = ["ID", "Name", "Table", "Description", "DataType", "Expression", "FormatString", "IsHidden", "State",
                   "KPIID", "IsSimpleMeasure", "DisplayFolder", "DetailRowsDefinition", "DataCategory",
                   "FormatStringDefinition", "LineageTag"]
REL_HEADERS = ["ID", "Name", "Relationship", "Model", "IsActive", "CrossFilteringBehavior",
               "RelyOnReferentialIntegrity", "FromTable", "FromColumn", "FromCardinality", "ToTable", "ToColumn",
               "ToCardinality", "State", "SecurityFilteringBehavior"]


def _uuid(*parts):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "|".join(parts)))


def _id(*parts):
    return int(hashlib.sha1("|".join(parts).encode()).hexdigest()[:7], 16)


def _write_csv(path, headers, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow([f"[{h}]" for h in headers])
        for row in rows:
            writer.writerow([row.get(h, "") for h in headers])


def _column_tuple(item):
    name, dtype = item[0], item[1]
    kind = item[2] if len(item) > 2 else "data"
    expression = item[3] if len(item) > 3 else ""
    extra = item[4] if len(item) > 4 else {}
    return name, dtype, kind, expression, extra


def write_metadata(spec):
    folder = OUT / spec["slug"]
    folder.mkdir(parents=True, exist_ok=True)
    model_id = _uuid(spec["slug"])
    tables, columns, measures, rels = [], [], [], []
    for tname, table in spec["tables"].items():
        tables.append({
            "ID": _id(spec["slug"], tname), "Name": tname, "Model": model_id, "DataCategory": "Regular",
            "IsHidden": "False", "StorageMode": "Import", "TableStorage": f"{tname} ({_id(spec['slug'], tname)})",
            "Expression": table.get("expression", ""), "ShowAsVariationOnly": "False", "IsPrivate": "False",
            "LineageTag": _uuid(spec["slug"], tname),
        })
        columns.append({
            "ID": _id(spec["slug"], tname, "rownumber"), "Name": "RowNumber-2662979B-1795-4F74-8F37-6A1BA8059B61",
            "Table": tname, "DataType": "Integer", "DataCategory": "RowNumber", "IsHidden": "True", "IsUnique": "True",
            "IsKey": "True", "IsNullable": "False", "Type": "RowNumber", "IsAvailableInMDX": "True",
        })
        for item in table["columns"]:
            name, dtype, kind, expression, extra = _column_tuple(item)
            columns.append({
                "ID": _id(spec["slug"], tname, name), "Name": name, "Table": tname, "DataType": dtype,
                "DataCategory": "Regular", "IsHidden": "False", "IsUnique": str(bool(extra.get("unique"))),
                "IsKey": "False", "IsNullable": "True", "Alignment": "Default",
                "SummarizeBy": "Sum" if dtype in ("Integer", "Number") else "None",
                "Type": {"data": "Data", "calc": "Calculated", "calctable": "CalculatedTableColumn"}[kind],
                "SourceColumn": name if kind == "data" else "", "Expression": expression,
                "FormatString": extra.get("format", "0" if dtype == "Integer" else ""),
                "IsAvailableInMDX": "True", "GroupingBehavior": "GroupOnValue",
                "LineageTag": _uuid(spec["slug"], tname, name),
            })
    for tname, mname, expression, dtype, fmt, description in spec["measures"]:
        measures.append({
            "ID": _id(spec["slug"], "m", mname), "Name": mname, "Table": tname, "Description": description,
            "DataType": dtype, "Expression": expression, "FormatString": fmt, "IsHidden": "False", "State": "Ready",
            "IsSimpleMeasure": "False", "LineageTag": _uuid(spec["slug"], "m", mname),
        })
    for ft, fc, tt, tc in spec["relationships"]:
        rels.append({
            "ID": _id(spec["slug"], ft, fc, tt, tc), "Name": _uuid(spec["slug"], ft, fc, tt, tc),
            "Relationship": f"'{ft}'[{fc}] *[<-]1 '{tt}'[{tc}]", "Model": model_id, "IsActive": "True",
            "CrossFilteringBehavior": "OneDirection", "RelyOnReferentialIntegrity": "False",
            "FromTable": ft, "FromColumn": fc, "FromCardinality": "Many", "ToTable": tt, "ToColumn": tc,
            "ToCardinality": "One", "State": "Ready", "SecurityFilteringBehavior": "Single",
        })
    _write_csv(folder / "tables.csv", TABLE_HEADERS, tables)
    _write_csv(folder / "columns.csv", COLUMN_HEADERS, columns)
    _write_csv(folder / "measures.csv", MEASURE_HEADERS, measures)
    _write_csv(folder / "relationships.csv", REL_HEADERS, rels)
    (folder / "_metadata_sync.json").write_text(json.dumps({
        "semantic_model": spec["name"], "status": "success", "origin": "synthetic",
        "note": "Modelo sintético para pruebas (tests/realistic/build_synthetic_models.py).",
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def _field(item):
    kind, table, name = item[0], item[1], item[2]
    if kind == "measure":
        return {"Measure": {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}}, f"{table}.{name}", name
    return {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}}, f"{table}.{name}", name


def write_report(source, report_root):
    """Materializa el PBIR mínimo de una fuente sintética (source.json) bajo report_root.

    Se genera en la caché del overlay (no se versiona: las rutas PBIR superan MAX_PATH en Windows).
    Devuelve la ruta de la carpeta <Reporte>.Report.
    """
    slug = source["semantic_model_key"]
    report = Path(report_root) / f"{source['report']}.Report"
    definition = report / "definition"
    (definition / "pages").mkdir(parents=True, exist_ok=True)
    (definition / "report.json").write_text("{}", encoding="utf-8")
    pages_meta = []
    for page in source["pages"]:
        page_name = f"ReportSection{_id(slug, page['name']):x}"
        pages_meta.append(page_name)
        page_dir = definition / "pages" / page_name
        (page_dir / "visuals").mkdir(parents=True, exist_ok=True)
        (page_dir / "page.json").write_text(json.dumps(
            {"name": page_name, "displayName": page["name"]}, ensure_ascii=False, indent=2), encoding="utf-8")
        for v_index, (vtype, title, fields) in enumerate(page["visuals"], 1):
            visual_name = f"{_id(slug, page['name'], str(v_index)):x}"
            roles = {}
            for item in fields:
                role = item[3] if len(item) > 3 else "Values"
                field, query_ref, native = _field(item)
                roles.setdefault(role, {"projections": []})["projections"].append(
                    {"field": field, "queryRef": query_ref, "nativeQueryRef": native})
            visual = {"visualType": vtype, "query": {"queryState": roles}}
            if title:
                visual["visualContainerObjects"] = {"title": [{"properties": {
                    "text": {"expr": {"Literal": {"Value": f"'{title}'"}}}}}]}
            v_dir = page_dir / "visuals" / visual_name
            v_dir.mkdir(parents=True, exist_ok=True)
            (v_dir / "visual.json").write_text(json.dumps(
                {"name": visual_name, "visual": visual}, ensure_ascii=False, indent=2), encoding="utf-8")
    (definition / "pages" / "pages.json").write_text(json.dumps(
        {"pageOrder": pages_meta, "activePageName": pages_meta[0]}, indent=2), encoding="utf-8")
    return report


def write_source(spec):
    """source.json: manifiesto de la fuente + páginas/visuales (PBIR) + documentación para chunks."""
    filters = []
    for page in spec["pages"]:
        for vtype, title, fields in page["visuals"]:
            if vtype == "slicer":
                filters.append(f"Filtro por {fields[0][2]} ({fields[0][1]}) en la página {page['name']}.")
    source = {
        "source_group": spec["source_group"], "report": spec["report"], "semantic_model": spec["name"],
        "semantic_model_key": spec["slug"], "aliases": spec["aliases"], "default_dashboard": spec["report"],
        "document_type": "dashboard_documentation", "workspace": "Gestion Clinica",
        "pages": spec["pages"],
        "documentation": {
            "name": spec["report"],
            "description": spec["description"],
            "aliases": spec["aliases"],
            "filters": sorted(set(filters)),
            "visuals": [f"{page['name']}: {title}." for page in spec["pages"]
                        for vtype, title, _ in page["visuals"] if title],
            "indicators": [f"{m[1]}: {m[5]}" for m in spec["measures"]],
            "measures": [{"table": m[0], "name": m[1], "expression": m[2], "data_type": m[3],
                          "format_string": m[4], "description": m[5]} for m in spec["measures"]],
        },
    }
    (OUT / spec["slug"] / "source.json").write_text(json.dumps(source, ensure_ascii=False, indent=2),
                                                    encoding="utf-8")


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    (OUT / "README.md").write_text(
        "# Modelos sintéticos (overlay)\n\nGenerados por `python -m tests.realistic.build_synthetic_models`. "
        "No editar a mano. Ver `tests/realistic/README.md`.\n", encoding="utf-8")
    for spec in MODELS:
        write_metadata(spec)
        write_source(spec)
        print("escrito", spec["slug"])


if __name__ == "__main__":
    main()
