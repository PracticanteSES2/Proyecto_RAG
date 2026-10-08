"""
Genera los datos falsos (fixtures) que necesita el runtime de app.py.

Todo se escribe bajo  tests/sim/fixtures/  (los fixtures generados se versionan para poder revisarlos):

  fixtures/
    app.py                                   (no existe; solo se usa como __file__ virtual => PROJECT_ROOT)
    data/catalog/source_registry.json        -> SourceModelRouter
    data/catalog/<model_key>_rag.json        -> FilterResolver / BusinessFilterResolver / DAXValidator
    data/rag/visual_metrics_catalog.json     -> SourceModelRouter + QueryPlanBuilder
    data/rag/master_metrics.json             -> MasterMetricResolver + QueryPlanBuilder
    data/vector_db/qdrant/points.json        -> FakeQdrantClient (chunks RAG, se embeben al cargar)
    powerbi_model.json                       -> FakeAdomd (esquema + dominios + valores base de medidas)
    adomd/*.dll                              -> archivos vacíos para pasar el chequeo de PowerBIProvider

Ejecutar (desde la raíz del repo):  python -m tests.sim.build_fixtures
"""
import hashlib
import json
import re
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE / "fixtures"

# ----------------------------------------------------------------------------
# 1. "Power BI": dos modelos semánticos con tablas, columnas, dominios y medidas
# ----------------------------------------------------------------------------

ESPECIALIDADES = [
    "CIRUGIA GENERAL",
    "CIRUGIA PLASTICA",
    "GINECOLOGIA Y OBSTETRICIA",
    "ORTOPEDIA Y TRAUMATOLOGIA",
    "OTORRINOLARINGOLOGIA",
    "UROLOGIA",
]
SEDES = ["SEDE PRINCIPAL", "SEDE NORTE", "SEDE SUR"]
ASEGURADORES = [
    "NUEVA EMPRESA PROMOTORA DE SALUD EPS S.A",
    "SANITAS EPS",
    "SURA EPS",
    "PARTICULAR",
]
SERVICIOS = ["URGENCIAS", "HOSPITALIZACION", "CONSULTA EXTERNA", "CIRUGIA"]
ESTADOS_QX = [
    "Paciente Programado",
    "Paciente en Quirofano",
    "Paciente Cancelado",
    "Paciente En Espera Programacion",
]
FECHAS = [f"{y}-{m:02d}-01T00:00:00" for y in (2023, 2024, 2025) for m in range(1, 13)]
MESES_NOMBRE = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
                "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

MODEL_A = "Atenciones Institucionales"
MODEL_B = "Gestion Quirurgica"
KEY_A = "atenciones_institucionales"
KEY_B = "gestion_quirurgica"
REPORT_A = "Tablero de Atenciones Institucionales"
REPORT_B = "Tablero Quirurgico"

POWERBI_MODEL = {
    "data_years": [2023, 2024, 2025],
    "models": {
        MODEL_A: {
            "tables": {
                "ATENCIONES": {
                    "ID_ATENCION": {"type": "Int64", "values": []},
                    "SEDE": {"type": "String", "values": SEDES},
                    "SERVICIO": {"type": "String", "values": SERVICIOS},
                    "ASEGURADOR": {"type": "String", "values": ASEGURADORES},
                    "FECHA": {"type": "DateTime", "values": FECHAS},
                },
                "CIRUGIAS_DWSES": {
                    "ID_CIRUGIA": {"type": "Int64", "values": []},
                    "ESPECIALIDAD": {"type": "String", "values": ESPECIALIDADES},
                    "SEDE": {"type": "String", "values": SEDES},
                    "EPS": {"type": "String", "values": ASEGURADORES},
                    "FECHA": {"type": "DateTime", "values": FECHAS},
                },
                "Calendario": {
                    "Date": {"type": "DateTime", "values": FECHAS},
                    "Año": {"type": "Int64", "values": [2023, 2024, 2025]},
                    "Mes": {"type": "String", "values": MESES_NOMBRE},
                    "MesNumero": {"type": "Int64", "values": list(range(1, 13))},
                },
            },
            "measures": {
                "Total Atenciones": {"table": "ATENCIONES", "base": 152340},
                "Cirugías Realizadas": {"table": "CIRUGIAS_DWSES", "base": 18240},
            },
        },
        MODEL_B: {
            "tables": {
                "QX_SOLICITUDES": {
                    "ID_SOLICITUD": {"type": "Int64", "values": []},
                    "ESPECIALIDAD": {"type": "String", "values": ESPECIALIDADES},
                    "SEDE": {"type": "String", "values": SEDES},
                    "ESTADO ACTUAL": {"type": "String", "values": ESTADOS_QX},
                    "FECHA_PLANEADA": {"type": "DateTime", "values": FECHAS},
                },
                # Calendario SIN columna de fecha expuesta en visuales: solo AÑO / MES
                "Calendario": {
                    "AÑO": {"type": "Int64", "values": [2023, 2024, 2025]},
                    "MES": {"type": "Int64", "values": list(range(1, 13))},
                },
            },
            "measures": {
                "Total Cirugías": {"table": "QX_SOLICITUDES", "base": 21980},
                "Cirugías Programadas": {"table": "QX_SOLICITUDES", "base": 20410},
                "Cirugías Realizadas": {"table": "QX_SOLICITUDES", "base": 17905},
            },
        },
    },
}


def technical_catalog(model_name, key):
    model = POWERBI_MODEL["models"][model_name]
    tables = []
    for table_name, columns in model["tables"].items():
        tables.append({
            "name": table_name,
            "columns": [
                {"name": col, "description": None, "data_type": meta["type"],
                 "expression": meta.get("expression"),
                 "is_hidden": col.startswith("ID_") or bool(meta.get("hidden"))}
                for col, meta in columns.items()
            ],
            "measures": [
                {"name": m, "expression": f"COUNTROWS('{meta['table']}')", "table": meta["table"]}
                for m, meta in model.get("measures", {}).items()
                if meta["table"] == table_name
            ],
        })
    return {"semantic_model": model_name, "semantic_model_key": key, "tables": tables}


# ----------------------------------------------------------------------------
# 2. source_registry.json
# ----------------------------------------------------------------------------

SOURCE_REGISTRY = {
    "models": [
        {"semantic_model": MODEL_A, "semantic_model_key": KEY_A,
         "technical_catalog": f"data/catalog/{KEY_A}_rag.json"},
        {"semantic_model": MODEL_B, "semantic_model_key": KEY_B,
         "technical_catalog": f"data/catalog/{KEY_B}_rag.json"},
    ],
    "sources": [
        {"source_group": "tablero_de_atenciones_institucionales", "report": REPORT_A,
         "semantic_model": MODEL_A, "default_dashboard": "Inicio",
         "aliases": ["atenciones institucionales", "tablero de atenciones"],
         "technical_catalog": f"data/catalog/{KEY_A}_rag.json"},
        {"source_group": "tablero_quirurgico", "report": REPORT_B,
         "semantic_model": MODEL_B, "default_dashboard": "Programacion Quirurgica",
         "aliases": ["tablero de cirugias", "tablero quirurgico", "gestion quirurgica"],
         "technical_catalog": f"data/catalog/{KEY_B}_rag.json"},
    ],
}


# ----------------------------------------------------------------------------
# 3. visual_metrics_catalog.json  (schema_version 2, multi-report)
# ----------------------------------------------------------------------------

def col(table, column, role="Values", display=None):
    return {"role": role, "kind": "column", "table": table, "column": column,
            "display_name": display or column, "native_query_ref": display or column,
            "query_ref": f"{table}.{column}"}


def meas(table, measure, role="Values"):
    return {"role": role, "kind": "measure", "table": table, "measure": measure,
            "display_name": measure, "native_query_ref": measure,
            "query_ref": f"{table}.{measure}"}


def hier(table, level):
    return {"role": "Values", "kind": "hierarchy_level", "table": table, "level": level,
            "query_ref": f"{table}.Date.Variación.Jerarquía de fechas.{level}",
            "native_query_ref": f"Date {level}", "display_name": level}


VISUAL_CATALOG = {
    "schema_version": 2,
    "reports": [
        {
            "report": REPORT_A, "semantic_model": MODEL_A,
            "source_group": "tablero_de_atenciones_institucionales",
            "pages": [
                {
                    "page_name": "ReportSection1", "page_display_name": "Inicio",
                    "filters": {},
                    "visuals": [
                        {"visual_id": "a_card_atenciones", "visual_type": "card", "title": "Total atenciones",
                         "fields": [meas("ATENCIONES", "Total Atenciones")]},
                        {"visual_id": "a_bar_sede", "visual_type": "clusteredBarChart", "title": "Atenciones por sede",
                         "fields": [col("ATENCIONES", "SEDE", role="Category"),
                                    meas("ATENCIONES", "Total Atenciones", role="Y")]},
                        {"visual_id": "a_slicer_sede", "visual_type": "slicer",
                         "fields": [col("ATENCIONES", "SEDE")]},
                        {"visual_id": "a_slicer_servicio", "visual_type": "slicer",
                         "fields": [col("ATENCIONES", "SERVICIO")]},
                        {"visual_id": "a_slicer_anio", "visual_type": "slicer", "fields": [hier("Calendario", "Año")]},
                        {"visual_id": "a_slicer_mes", "visual_type": "slicer", "fields": [hier("Calendario", "Mes")]},
                    ],
                },
                {
                    "page_name": "ReportSection2", "page_display_name": "Cirugias",
                    "filters": {},
                    "visuals": [
                        {"visual_id": "a_card_cx", "visual_type": "card", "title": "Cirugías realizadas",
                         "fields": [meas("CIRUGIAS_DWSES", "Cirugías Realizadas")]},
                        {"visual_id": "a_bar_esp", "visual_type": "clusteredColumnChart",
                         "title": "Cirugías por especialidad",
                         "fields": [col("CIRUGIAS_DWSES", "ESPECIALIDAD", role="Category"),
                                    meas("CIRUGIAS_DWSES", "Cirugías Realizadas", role="Y")]},
                        {"visual_id": "a_slicer_cx_sede", "visual_type": "slicer",
                         "fields": [col("CIRUGIAS_DWSES", "SEDE")]},
                        {"visual_id": "a_slicer_cx_anio", "visual_type": "slicer", "fields": [hier("Calendario", "Año")]},
                    ],
                },
            ],
            "metrics": [],
        },
        {
            "report": REPORT_B, "semantic_model": MODEL_B, "source_group": "tablero_quirurgico",
            "pages": [
                {
                    "page_name": "ReportSectionQ1", "page_display_name": "Programacion Quirurgica",
                    "filters": {"filters": [
                        {"field": {"table": "QX_SOLICITUDES", "column": "ESTADO ACTUAL"},
                         "values": ["Paciente Programado", "Paciente en Quirofano"]},
                    ]},
                    "visuals": [
                        {"visual_id": "b_card_prog", "visual_type": "card", "title": "Cirugías programadas",
                         "fields": [meas("QX_SOLICITUDES", "Cirugías Programadas")]},
                        {"visual_id": "b_card_total", "visual_type": "card", "title": "Total cirugías",
                         "fields": [meas("QX_SOLICITUDES", "Total Cirugías")]},
                        {"visual_id": "b_slicer_esp", "visual_type": "slicer",
                         "fields": [col("QX_SOLICITUDES", "ESPECIALIDAD")]},
                        {"visual_id": "b_slicer_sede", "visual_type": "slicer",
                         "fields": [col("QX_SOLICITUDES", "SEDE")]},
                        # AÑO / MES como columnas planas (no jerarquía de fecha)
                        {"visual_id": "b_slicer_anio", "visual_type": "slicer",
                         "fields": [col("Calendario", "AÑO")]},
                        {"visual_id": "b_slicer_mes", "visual_type": "slicer",
                         "fields": [col("Calendario", "MES")]},
                        {"visual_id": "b_table_estado", "visual_type": "tableEx",
                         "fields": [col("QX_SOLICITUDES", "ESTADO ACTUAL", role="Values"),
                                    meas("QX_SOLICITUDES", "Cirugías Programadas")]},
                    ],
                },
                {
                    "page_name": "ReportSectionQ2", "page_display_name": "Cirugias Realizadas",
                    "filters": {},
                    "visuals": [
                        {"visual_id": "b_card_real", "visual_type": "card", "title": "Cirugías realizadas",
                         "fields": [meas("QX_SOLICITUDES", "Cirugías Realizadas")]},
                        {"visual_id": "b_bar_esp", "visual_type": "clusteredBarChart",
                         "title": "Cirugías realizadas por especialidad",
                         "fields": [col("QX_SOLICITUDES", "ESPECIALIDAD", role="Category"),
                                    meas("QX_SOLICITUDES", "Cirugías Realizadas", role="Y")]},
                    ],
                },
            ],
            "metrics": [],
        },
    ],
    "metrics": [],
}


# ----------------------------------------------------------------------------
# 4. master_metrics.json
# ----------------------------------------------------------------------------

def metric(mid, label, measure, table, model, report, pages_visuals, aliases=None, status="approved"):
    return {
        "metric_id": mid,
        "label": label,
        "measure": measure,
        "aliases": aliases or [label],
        "source_type": "explicit_measure",
        "semantic_model": model,
        "report": report,
        "reports": [report],
        "table": table,
        "aggregation": None,
        "dax_expression": f"[{measure}]",
        "validation_status": status,
        "appearances": [
            {"report": report, "page_display_name": page, "visual_id": vid, "visual_title": title}
            for page, vid, title in pages_visuals
        ],
    }


MASTER_METRICS = {
    "schema_version": 1,
    "metrics": [
        metric("a_total_atenciones", "TOTAL ATENCIONES", "Total Atenciones", "ATENCIONES", MODEL_A, REPORT_A,
               [("Inicio", "a_card_atenciones", "Total atenciones"), ("Inicio", "a_bar_sede", "Atenciones por sede")]),
        metric("a_cx_realizadas", "CIRUGÍAS REALIZADAS", "Cirugías Realizadas", "CIRUGIAS_DWSES", MODEL_A, REPORT_A,
               [("Cirugias", "a_card_cx", "Cirugías realizadas"), ("Cirugias", "a_bar_esp", "Cirugías por especialidad")]),
        metric("b_total_cx", "TOTAL CIRUGÍAS", "Total Cirugías", "QX_SOLICITUDES", MODEL_B, REPORT_B,
               [("Programacion Quirurgica", "b_card_total", "Total cirugías")]),
        metric("b_cx_programadas", "CIRUGÍAS PROGRAMADAS", "Cirugías Programadas", "QX_SOLICITUDES", MODEL_B, REPORT_B,
               [("Programacion Quirurgica", "b_card_prog", "Cirugías programadas"),
                ("Programacion Quirurgica", "b_table_estado", "Estado de solicitudes")]),
        metric("b_cx_realizadas", "CIRUGÍAS REALIZADAS", "Cirugías Realizadas", "QX_SOLICITUDES", MODEL_B, REPORT_B,
               [("Cirugias Realizadas", "b_card_real", "Cirugías realizadas"),
                ("Cirugias Realizadas", "b_bar_esp", "Cirugías realizadas por especialidad")]),
        # Una métrica pendiente: nunca debe ejecutarse
        metric("b_cx_canceladas", "CIRUGÍAS CANCELADAS", "Cirugías Canceladas", "QX_SOLICITUDES", MODEL_B, REPORT_B,
               [("Programacion Quirurgica", "b_card_canc", "Cirugías canceladas")], status="pending_review"),
    ],
}


# ----------------------------------------------------------------------------
# 5. Chunks RAG (payload Qdrant plano, como embedding_indexer.build_vector_index)
# ----------------------------------------------------------------------------

def chunk(cid, chunk_type, dashboard, aliases, model, key, group, text, section=None, measure=None, table=None):
    payload = {
        "text": text.strip(),
        "chunk_type": chunk_type,
        "dashboard": dashboard,
        "dashboard_aliases": aliases,
        "semantic_model": model,
        "semantic_model_key": key,
        "source_group": group,
        "source_file": f"{dashboard}.docx",
        "relative_path": f"raw/{group}/{dashboard}.docx",
        "document_type": "docx",
        "technical_catalog": f"data/catalog/{key}_rag.json",
    }
    if section:
        payload["section"] = section
    if measure:
        payload["measure"] = measure
    if table:
        payload["table"] = table
    return {"id": cid, "payload": payload}


ALIAS_A = ["atenciones institucionales", "tablero de atenciones"]
ALIAS_B = ["tablero de cirugias", "tablero quirurgico", "gestion quirurgica"]
GA, GB = "tablero_de_atenciones_institucionales", "tablero_quirurgico"

POINTS = [
    chunk(1, "dashboard_overview", REPORT_A, ALIAS_A, MODEL_A, KEY_A, GA, """
Tablero: Tablero de Atenciones Institucionales
Alias: atenciones institucionales, tablero de atenciones
Descripción: Este tablero muestra el volumen de atenciones institucionales por sede, servicio y aseguradora,
y el comportamiento mensual de las cirugías realizadas, comparando diferentes años.
Filtros disponibles: SEDE, SERVICIO, AÑO, MES.
Visualizaciones: tarjeta Total atenciones, gráfico de barras Atenciones por sede, página Cirugías con
cirugías por especialidad.
Indicadores: Total atenciones, Cirugías realizadas.
""", section="overview"),
    chunk(2, "measure", REPORT_A, ALIAS_A, MODEL_A, KEY_A, GA, """
Tablero: Tablero de Atenciones Institucionales
Medida: Total Atenciones
Descripción: cantidad total de atenciones registradas (recuento de ID_ATENCION) en la tabla ATENCIONES.
""", measure="Total Atenciones", table="ATENCIONES"),
    chunk(3, "measure", REPORT_A, ALIAS_A, MODEL_A, KEY_A, GA, """
Tablero: Tablero de Atenciones Institucionales
Medida: Cirugías Realizadas
Descripción: número de cirugías realizadas según FECHA_CIRUGIA en CIRUGIAS_DWSES, por especialidad y sede.
""", measure="Cirugías Realizadas", table="CIRUGIAS_DWSES"),
    chunk(4, "dashboard_overview", REPORT_B, ALIAS_B, MODEL_B, KEY_B, GB, """
Tablero: Tablero Quirurgico
Alias: tablero de cirugias, tablero quirurgico, gestion quirurgica
Descripción: Este tablero permite hacer seguimiento a las solicitudes quirúrgicas: cirugías programadas,
cirugías realizadas y total de cirugías, junto con el estado actual de cada solicitud.
Filtros disponibles: ESPECIALIDAD, SEDE, AÑO, MES, ESTADO ACTUAL.
Visualizaciones: tarjetas Cirugías programadas y Total cirugías, tabla de estado de solicitudes,
barras de cirugías realizadas por especialidad.
Indicadores: Total cirugías, Cirugías programadas, Cirugías realizadas.
""", section="overview"),
    chunk(5, "measure", REPORT_B, ALIAS_B, MODEL_B, KEY_B, GB, """
Tablero: Tablero Quirurgico
Medida: Cirugías Programadas
Descripción: solicitudes quirúrgicas con estado Paciente Programado en QX_SOLICITUDES. Se calcula con la
fecha planeada de la cirugía.
""", measure="Cirugías Programadas", table="QX_SOLICITUDES"),
    chunk(6, "measure", REPORT_B, ALIAS_B, MODEL_B, KEY_B, GB, """
Tablero: Tablero Quirurgico
Medida: Total Cirugías
Descripción: total de solicitudes quirúrgicas registradas, sin importar su estado.
""", measure="Total Cirugías", table="QX_SOLICITUDES"),
    chunk(7, "sql_query", REPORT_B, ALIAS_B, MODEL_B, KEY_B, GB, """
Tablero: Tablero Quirurgico
Consulta técnica documentada: SELECT ESPECIALIDAD, SEDE, ESTADO_ACTUAL, FECHA_PLANEADA FROM Qx_SolicitudProgramacion
""", section="sql_queries"),
]


# ----------------------------------------------------------------------------
# 6. Tablero Lavandería (réplica del tablero real documentado en
#    "39 DOCUMENTACION TABLERO LAVANDERIA / 1 Documentacion Tablero Lavanderia.docx")
#
#    - Una sola tabla LAVANDERIA (consulta SQL del documento) con 2 columnas
#      calculadas (NOMBRE_COMPLETO, TURNO_OK). No hay tabla Calendario: los
#      segmentadores Año / Mes son la jerarquía de fechas de LAVANDERIA[Fecha]
#      (tipo fecha), igual que emite visual_catalog_builder (HierarchyLevel).
#    - Métrica: agregación visual "Suma de Peso" -> source_type
#      "visual_aggregation", dax_expression SUM('LAVANDERIA'[Peso]),
#      como la genera global_master_metric_builder.
#    - Datos a nivel de fila (determinísticos) para que las sumas con filtros
#      sean consistentes: SUM(Peso) SERVICIO=ANTIFLUIDOS ene-2026 = 488.3 y
#      total ene-2026 = 3906.4 (participación 12.5 %).
# ----------------------------------------------------------------------------

MODEL_C = "Lavanderia"
KEY_C = "lavanderia"
REPORT_C = "Tablero Lavanderia"
GROUP_C = "tablero_lavanderia"
PAGE_C = "Lavanderia"

LAV_SERVICIOS = ["ANTIFLUIDOS", "CIRUGIA", "URGENCIAS", "HOSPITALIZACION", "UCI ADULTOS", "CONSULTA EXTERNA"]
# Peso (décimas de kg) de enero 2026 por servicio. Suma 39064 = 3906.4 kg; 4883 = 12.5 %.
LAV_JAN2026_TENTHS = {"ANTIFLUIDOS": 4883, "CIRUGIA": 7813, "URGENCIAS": 7031,
                      "HOSPITALIZACION": 5859, "UCI ADULTOS": 8203, "CONSULTA EXTERNA": 5275}
LAV_MONTHS = [(2025, m) for m in range(1, 13)] + [(2026, m) for m in (1, 2, 3)]
LAV_USERS = [
    (101, "Ana Maria", "Gomez Rojas"), (102, "Carlos", "Perez Diaz"),
    (103, "Luisa", "Martinez Cruz"), (104, "Jorge", "Ramirez Soto"),
    (105, "Marta", "Lopez Vega"), (106, "Pedro", "Castro Mora"),
]


def _h(*parts):
    return int(hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:8], 16)


def lavanderia_rows():
    """Filas determinísticas. Peso en décimas enteras -> sin errores de flotante."""
    rows, oid = [], 1000
    for (year, month) in LAV_MONTHS:
        for si, servicio in enumerate(LAV_SERVICIOS):
            base = LAV_JAN2026_TENTHS[servicio]
            if (year, month) == (2026, 1):
                total = base
            else:
                total = int(round(base * (0.70 + 0.60 * (_h("tot", year, month, servicio) % 1000) / 1000.0)))
            weights = [1 + _h("w", year, month, servicio, i) % 5 for i in range(4)]
            parts = [max(1, total * w // sum(weights)) for w in weights]
            parts[-1] = total - sum(parts[:-1])
            assert all(p > 0 for p in parts) and sum(parts) == total
            for i, tenths in enumerate(parts):
                oid += 1
                day = 1 + (i * 7 + si * 3 + month) % 28
                turno = (i + si) % 3 + 1
                uid, nombres, apellidos = LAV_USERS[(i + si + month) % len(LAV_USERS)]
                fecha = datetime(year, month, day)
                rows.append({
                    "OID": oid,
                    "Peso": tenths / 10.0,
                    "OidUsuario": uid,
                    "FechaRegistro": (fecha + timedelta(hours=7 + (i * 5 + si) % 12, minutes=(i * 17) % 60)).isoformat(),
                    "Fecha": fecha.isoformat(),
                    "Turno": turno,
                    "SERVICIO": servicio,
                    "usu_nombres": nombres,
                    "usu_apellidos": apellidos,
                })
    return rows


NOMBRE_COMPLETO_DAX = 'CONCATENATE(LAVANDERIA[usu_nombres],CONCATENATE(" ",LAVANDERIA[usu_apellidos]))'
TURNO_OK_DAX = ('IF(LAVANDERIA[Turno]=1, "MAÑANA", IF(LAVANDERIA[Turno]=2,"TARDE", '
                'IF(LAVANDERIA[Turno]=3,"NOCHE")))')

POWERBI_MODEL["models"][MODEL_C] = {
    "tables": {
        "LAVANDERIA": {
            "OID": {"type": "Int64", "values": []},
            "Peso": {"type": "Double", "values": []},
            "OidUsuario": {"type": "Int64", "values": []},
            "FechaRegistro": {"type": "DateTime", "values": []},
            "Fecha": {"type": "DateTime", "values": []},
            "Turno": {"type": "Int64", "values": []},
            "SERVICIO": {"type": "String", "values": LAV_SERVICIOS},
            "usu_nombres": {"type": "String", "values": []},
            "usu_apellidos": {"type": "String", "values": []},
            "NOMBRE_COMPLETO": {"type": "String", "values": [], "calculated": "NOMBRE_COMPLETO",
                                "expression": NOMBRE_COMPLETO_DAX},
            "TURNO_OK": {"type": "String", "values": ["MAÑANA", "TARDE", "NOCHE"], "calculated": "TURNO_OK",
                         "expression": TURNO_OK_DAX},
        },
    },
    "measures": {},
    "data": {"LAVANDERIA": lavanderia_rows()},
}

SOURCE_REGISTRY["models"].append(
    {"semantic_model": MODEL_C, "semantic_model_key": KEY_C,
     "technical_catalog": f"data/catalog/{KEY_C}_rag.json"})
SOURCE_REGISTRY["sources"].append(
    {"source_group": GROUP_C, "report": REPORT_C, "semantic_model": MODEL_C,
     "default_dashboard": PAGE_C,
     "aliases": ["lavanderia", "tablero lavanderia", "tablero de lavanderia"],
     "technical_catalog": f"data/catalog/{KEY_C}_rag.json"})


def agg_sum(table, column, role="Values"):
    """Campo agregado tal como lo emite visual_catalog_builder._parse_field."""
    return {"role": role, "query_ref": f"Sum({table}.{column})", "native_query_ref": f"Sum of {column}",
            "kind": "aggregation", "table": table, "column": column,
            "aggregation_id": 0, "aggregation": "Sum",
            "dax_expression": f"SUM('{table}'[{column}])",
            "model_valid": True, "auto_executable": True}


def _lav_visual(vid, vtype, fields, title=None):
    metrics = [{"page_name": "ReportSectionLav", "page_display_name": PAGE_C, "visual_id": vid,
                "visual_type": vtype, "visual_title": title, "role": f["role"],
                "query_ref": f["query_ref"], "native_query_ref": f["native_query_ref"],
                "aliases": [f"{f['aggregation']} de {f['column']}"], **{
                    k: f[k] for k in ("kind", "table", "column", "aggregation_id", "aggregation",
                                      "dax_expression", "model_valid", "auto_executable")},
                "validation_status": "approved"}
               for f in fields if f.get("kind") == "aggregation"]
    return {"visual_id": vid, "visual_type": vtype, "title": title, "fields": fields, "metrics": metrics}


def _hier_fecha(level, role="Values"):
    return {"role": role, "kind": "hierarchy_level", "table": "LAVANDERIA", "level": level,
            "query_ref": f"LAVANDERIA.Fecha.Variación.Jerarquía de fechas.{level}",
            "native_query_ref": f"Fecha {level}", "display_name": level}


VISUAL_CATALOG["reports"].append({
    "report": REPORT_C, "semantic_model": MODEL_C, "source_group": GROUP_C,
    "pages": [{
        "page_name": "ReportSectionLav", "page_display_name": PAGE_C, "filters": {},
        "visuals": [
            _lav_visual("lav_slicer_anio", "slicer", [_hier_fecha("Año")]),
            _lav_visual("lav_slicer_mes", "slicer", [_hier_fecha("Mes")]),
            # "Tabla de Participación por Servicio": SERVICIO + Sum of Peso (+ % del total)
            _lav_visual("lav_tabla_participacion_servicio", "tableEx",
                        [col("LAVANDERIA", "SERVICIO"), agg_sum("LAVANDERIA", "Peso")]),
            # "Tabla de registro de Usuarios": NOMBRE_COMPLETO + Sum of Peso
            _lav_visual("lav_tabla_usuarios", "tableEx",
                        [col("LAVANDERIA", "NOMBRE_COMPLETO"), agg_sum("LAVANDERIA", "Peso")]),
            # "Gráfico Circular de Peso por Turno Laboral": TURNO_OK + Sum of Peso
            _lav_visual("lav_pie_turno", "pieChart",
                        [col("LAVANDERIA", "TURNO_OK", role="Category"), agg_sum("LAVANDERIA", "Peso", role="Y")]),
            # "Gráfico de Barras por Distribución Mensual": mes + Sum of Peso
            _lav_visual("lav_barras_mensual", "clusteredBarChart",
                        [_hier_fecha("Mes", role="Category"), agg_sum("LAVANDERIA", "Peso", role="Y")]),
        ],
    }],
    "metrics": [],
})


def _norm_id(value):
    text = "".join(c for c in unicodedata.normalize("NFD", str(value or "").lower().strip())
                   if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text)).strip()


def _make_id(*parts):
    """Copia de global_master_metric_builder.make_id (sha1 de las partes normalizadas)."""
    raw = "|".join(_norm_id(p) for p in parts if p is not None)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


PESO_LABEL = "PESO"
PESO_DAX = "SUM('LAVANDERIA'[Peso])"
PESO_METRIC_ID = _make_id("visual_aggregation", MODEL_C, REPORT_C, PESO_LABEL, PESO_DAX)

_LAV_APPEARANCES = [
    ("lav_tabla_participacion_servicio", "tableEx", "Values"),
    ("lav_tabla_usuarios", "tableEx", "Values"),
    ("lav_pie_turno", "pieChart", "Y"),
    ("lav_barras_mensual", "clusteredBarChart", "Y"),
]

MASTER_METRICS["metrics"].append({
    "metric_id": PESO_METRIC_ID,
    "label": PESO_LABEL,
    # aliases como los acumula el builder: native_query_ref, query_ref y "<Agg> de <col>"
    "aliases": ["Sum of Peso", "Sum(LAVANDERIA.Peso)", "Sum de Peso", "Suma de Peso", "Peso"],
    "source_type": "visual_aggregation",
    "semantic_model": MODEL_C,
    "report": REPORT_C,
    "source_group": GROUP_C,
    "table": "LAVANDERIA",
    "measure": None,
    "column": "Peso",
    "aggregation": "Sum",
    "dax_expression": PESO_DAX,
    "model_expression": None,
    "description": None,
    "validation_status": "approved",
    "reports": [REPORT_C],
    "source_groups": [GROUP_C],
    "appearances": [
        {"report": REPORT_C, "source_group": GROUP_C, "page_name": "ReportSectionLav",
         "page_display_name": PAGE_C, "visual_id": vid, "visual_title": None,
         "visual_type": vtype, "role": role, "query_ref": "Sum(LAVANDERIA.Peso)"}
        for vid, vtype, role in _LAV_APPEARANCES
    ],
})

ALIAS_C = ["lavanderia", "tablero lavanderia", "tablero de lavanderia"]

POINTS.extend([
    chunk(8, "dashboard_overview", REPORT_C, ALIAS_C, MODEL_C, KEY_C, GROUP_C, """
Tablero: Tablero Lavanderia
Alias: lavanderia, tablero lavanderia, tablero de lavanderia
Descripción: Este tablero monitorea la gestión y distribución del peso de ropa hospitalaria que ingresa al
área de lavandería, teniendo en cuenta las personas que registran, las distribuciones de peso por turno
laboral y los pesos totales por mes.
Filtros disponibles: Año, Mes.
Visualizaciones: Tabla de Participación por Servicio, Tabla de registro de Usuarios, Gráfico Circular de
Peso por Turno Laboral, Gráfico de Barras por Distribución Mensual.
Indicadores: Peso (suma de Peso en kg).
""", section="overview"),
    chunk(9, "document_section", REPORT_C, ALIAS_C, MODEL_C, KEY_C, GROUP_C, """
Tablero: Tablero Lavanderia
Sección: Filtros por Años y Mes
Contenido: Permiten segmentar la información por Aseguradora, Año y Mes, facilitando el análisis de la
lavandería según los criterios seleccionados.
""", section="Filtros por Años y Mes"),
    chunk(10, "document_section", REPORT_C, ALIAS_C, MODEL_C, KEY_C, GROUP_C, """
Tablero: Tablero Lavanderia
Sección: Tabla de Participación por Servicio
Contenido: Muestra la distribución de pesos registrados mensualmente por cada área de servicios, obteniendo
también su porcentaje de participación.
""", section="Tabla de Participación por Servicio"),
    chunk(11, "document_section", REPORT_C, ALIAS_C, MODEL_C, KEY_C, GROUP_C, """
Tablero: Tablero Lavanderia
Sección: Tabla de registro de Usuarios
Contenido: Muestra la distribución de peso registrados para lavandería por cada colaborador de las áreas
del hospital.
""", section="Tabla de registro de Usuarios"),
    chunk(12, "document_section", REPORT_C, ALIAS_C, MODEL_C, KEY_C, GROUP_C, """
Tablero: Tablero Lavanderia
Sección: Gráfico Circular de Peso por Turno Laboral
Contenido: Muestra la distribución de cargas teniendo en cuenta los turnos laborales que rotan en el hospital.
""", section="Gráfico Circular de Peso por Turno Laboral"),
    chunk(13, "document_section", REPORT_C, ALIAS_C, MODEL_C, KEY_C, GROUP_C, """
Tablero: Tablero Lavanderia
Sección: Gráfico de Barras por Distribución Mensual
Contenido: Muestra el total de distribución de cargas mensuales asignadas a lavandería.
""", section="Gráfico de Barras por Distribución Mensual"),
    chunk(14, "calculated_column", REPORT_C, ALIAS_C, MODEL_C, KEY_C, GROUP_C, f"""
Tablero: Tablero Lavanderia
Columna calculada: NOMBRE_COMPLETO
Tabla: LAVANDERIA
Expresión DAX: NOMBRE_COMPLETO = {NOMBRE_COMPLETO_DAX}
""", section="calculated_columns", table="LAVANDERIA"),
    chunk(15, "calculated_column", REPORT_C, ALIAS_C, MODEL_C, KEY_C, GROUP_C, f"""
Tablero: Tablero Lavanderia
Columna calculada: TURNO_OK (1 = MAÑANA, 2 = TARDE, 3 = NOCHE)
Tabla: LAVANDERIA
Expresión DAX: TURNO_OK = {TURNO_OK_DAX}
""", section="calculated_columns", table="LAVANDERIA"),
    chunk(16, "sql_query", REPORT_C, ALIAS_C, MODEL_C, KEY_C, GROUP_C, """
Tablero: Tablero Lavanderia
Consulta técnica documentada: SELECT A.OID, A.Peso, A.OidUsuario, A.FechaRegistro, B.Fecha, B.Turno,
C.Nombre SERVICIO, D.usu_nombres, D.usu_apellidos FROM PLANILLAUSUARIO.DBO.Cp_PesajeLavanderia A
LEFT JOIN PLANILLAUSUARIO.DBO.Cp_EncabezadoLavanderia B ON A.OidEncabezadoLavanderia=B.Oid
LEFT JOIN PLANILLAUSUARIO.DBO.Cp_Medicion C ON A.OidCpMedicion=C.Oid
LEFT JOIN PLANILLAUSUARIO.DBO.USUARIO D ON A.OidUsuario=D.usu_oid
""", section="sql_queries"),
])


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("escrito", path.relative_to(HERE.parents[1]).as_posix())


def main():
    write(ROOT / "powerbi_model.json", POWERBI_MODEL)
    write(ROOT / "data" / "catalog" / "source_registry.json", SOURCE_REGISTRY)
    write(ROOT / "data" / "catalog" / f"{KEY_A}_rag.json", technical_catalog(MODEL_A, KEY_A))
    write(ROOT / "data" / "catalog" / f"{KEY_B}_rag.json", technical_catalog(MODEL_B, KEY_B))
    write(ROOT / "data" / "catalog" / f"{KEY_C}_rag.json", technical_catalog(MODEL_C, KEY_C))
    write(ROOT / "data" / "rag" / "visual_metrics_catalog.json", VISUAL_CATALOG)
    write(ROOT / "data" / "rag" / "master_metrics.json", MASTER_METRICS)
    write(ROOT / "data" / "vector_db" / "qdrant" / "points.json",
          {"collection": "gestion_clinica_rag", "points": POINTS})
    adomd = ROOT / "adomd"
    adomd.mkdir(parents=True, exist_ok=True)
    for name in ("Microsoft.AnalysisServices.AdomdClient.dll", "Microsoft.Identity.Client.dll"):
        (adomd / name).write_bytes(b"")
    print("escrito fixtures/adomd/*.dll (vacíos)")


if __name__ == "__main__":
    main()
