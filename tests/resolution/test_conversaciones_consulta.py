"""
Conversaciones reales del 2026-10-29 (Power BI real, MedGemma caído):

1. «interconsultas respondidas ayer» generó FILTER(ALL('Calendario'[Date]) ...)
   en TABLERO TIEMPOS URGENCIAS, donde la columna es Calendario[FECHA]: el
   informe nombra la jerarquía de fechas «Calendario.Date.Variación…» (nombre
   viejo) y el Query Plan tomó «Date» como columna. La fecha se elige ahora del
   modelo de la medida (src/dax/column_guard.py) y toda columna del DAX se
   verifica contra la metadata antes de enviarlo.
2. «dame una lista de las áreas que tiene el hospital» fue al RAG: ahora se
   listan los valores de la columna de la dimensión en Power BI
   (src/semantic/detail_list.py + QueryEngine._dimension_listing).
3. Respuesta extractiva sin LLM: entrada más pertinente primero, frases
   completas, fuente legible y un solo tablero (src/rag/extractive.py).

Ejecutar:  python -m tests.resolution.test_conversaciones_consulta
"""
import json
import os
import sys
import traceback
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.chatbot.query_engine import QueryEngine  # noqa: E402
from src.dax.column_guard import (  # noqa: E402
    GuardedQueryPlanDAXGenerator, ModelSchema, references, repair_plan, unknown_references,
)
from src.dax.query_plan_dax_generator import QueryPlanDAXGenerator  # noqa: E402
from src.rag.extractive import readable_fallback  # noqa: E402
from src.semantic.detail_list import (  # noqa: E402
    dimension_list_request, dimension_plural, dimension_values, rank_dimension_columns,
)

TIEMPOS = "TABLERO TIEMPOS URGENCIAS"


def _col(name, data_type="String"):
    return {"name": name, "data_type": data_type}


def _rel(source, source_column, target, target_column, active=True):
    return {"FromTable": source, "FromColumn": source_column, "ToTable": target,
            "ToColumn": target_column, "IsActive": active}


# Lo esencial de data/catalog/tablero_tiempos_urgencias_rag.json (export INFO.VIEW).
TIEMPOS_CATALOG = {
    "semantic_model": TIEMPOS,
    "tables": [
        {"name": "Calendario", "columns": [_col("FECHA", "Date")], "measures": []},
        {"name": "INTERCONSULTA", "columns": [
            _col("FECHA", "Date"), _col("FECHA_SOLICITUD", "Date"), _col("FECHA_RESPUESTA", "Date"),
            _col("RESPUESTAS", "Integer"), _col("SOLICITUDES", "Integer"), _col("GEEDESCRI"),
        ], "measures": [{"name": "%ATENDIDO"}]},
        {"name": "Fechas", "columns": [_col("Date", "Date")], "measures": []},
        {"name": "SIN_RELACION", "columns": [_col("FECHA", "Date"), _col("VALOR", "Integer")], "measures": []},
        {"name": "SIN_FECHA", "columns": [_col("VALOR", "Integer"), _col("TIPO")], "measures": []},
    ],
    "relationships": [
        _rel("INTERCONSULTA", "FECHA", "Calendario", "FECHA"),
        _rel("INTERCONSULTA", "FECHA_RESPUESTA", "LocalDateTable_cb55", "Date"),
        _rel("INTERCONSULTA", "FECHA_SOLICITUD", "Fechas", "Date", active=False),
    ],
}


def _plan(table="INTERCONSULTA", expression="SUM('INTERCONSULTA'[RESPUESTAS])", filters=None):
    return {
        "status": "ready", "mode": "scalar", "semantic_model": TIEMPOS,
        "metric": {"label": "INTERCONSULTAS RESPONDIDAS", "table": table, "dax_expression": expression,
                   "validation_status": "approved", "metric_id": "m1"},
        "filters": filters if filters is not None else [{
            "type": "date_range", "table": "Calendario", "column": "Date",
            "start": "2026-10-28", "end": "2026-10-29", "label": "28 de octubre de 2026 (ayer)",
            "source": "query_plan_temporal",
        }],
        "group_by": [],
    }


def _guarded():
    return GuardedQueryPlanDAXGenerator(QueryPlanDAXGenerator(), lambda model: TIEMPOS_CATALOG)


# ---------------------------------------------------------------- 1) columna de fecha
def test_stale_hierarchy_date_uses_the_related_calendar_column():
    result = _guarded().generate(_plan())
    assert result["status"] == "generated", result
    assert "'Calendario'[FECHA] >= DATE(2026, 10, 28)" in result["dax"], result["dax"]
    assert "[Date]" not in result["dax"], result["dax"]
    assert result["column_repairs"][0]["from"] == "Calendario[Date]"
    assert result["column_repairs"][0]["to"] == "Calendario[FECHA]"


def test_existing_but_unrelated_date_table_is_replaced():
    plan = _plan()
    plan["filters"][0].update({"table": "Fechas", "column": "Date"})   # relación inactiva
    result = _guarded().generate(plan)
    assert "'Calendario'[FECHA]" in result["dax"] and "'Fechas'" not in result["dax"], result


def test_correct_date_column_is_kept_and_plan_not_mutated():
    plan = _plan()
    plan["filters"][0]["column"] = "FECHA"
    result = _guarded().generate(plan)
    assert "column_repairs" not in result and "'Calendario'[FECHA]" in result["dax"]
    broken = _plan()
    _guarded().generate(broken)
    assert broken["filters"][0]["column"] == "Date", "el plan original no se modifica"


def test_without_relationship_uses_the_own_table_date():
    plan = _plan(table="SIN_RELACION", expression="SUM('SIN_RELACION'[VALOR])")
    result = _guarded().generate(plan)
    assert "'SIN_RELACION'[FECHA]" in result["dax"], result


def test_without_any_date_the_plan_is_rejected():
    plan = _plan(table="SIN_FECHA", expression="SUM('SIN_FECHA'[VALOR])")
    result = _guarded().generate(plan)
    assert result["status"] == "rejected" and result["reason"] == "unknown_columns", result
    assert result["unknown_columns"] == ["Calendario[Date]"]


def test_unknown_categorical_column_is_rejected_and_explained():
    plan = _plan(filters=[{"type": "categorical", "table": "INTERCONSULTA", "column": "ESPECIALIDAD",
                           "value": "PEDIATRIA"}])
    _, repairs, unresolved = repair_plan(plan, ModelSchema(TIEMPOS_CATALOG))
    assert not repairs and unresolved == ["INTERCONSULTA[ESPECIALIDAD]"]


def test_explicit_measure_fact_table_comes_from_model_expression():
    plan = _plan(table="Calendario", expression="[INTERCONSULTAS RESPONDIDAS]")
    plan["metric"]["model_expression"] = "SUM('INTERCONSULTA'[RESPUESTAS])"
    result = _guarded().generate(plan)
    assert "'Calendario'[FECHA]" in result["dax"], result


# ---------------------------------------------------------------- 1b) validación del texto DAX
def test_unknown_references_in_dax_text():
    schema = ModelSchema(TIEMPOS_CATALOG)
    dax = (
        "EVALUATE ROW(\"__value\", CALCULATE(SUM('INTERCONSULTA'[RESPUESTAS]), "
        "FILTER(ALL('Calendario'[Date]), 'Calendario'[Date] >= DATE(2026,10,28)), "
        "TREATAS({\"x'[y]\"}, INTERCONSULTA[GEEDESCRI]), 'INTERCONSULTA'[%ATENDIDO], "
        "'LocalDateTable_cb55'[Date], [__value]))"
    )
    assert unknown_references(dax, schema) == ["Calendario[Date]"]
    assert ("INTERCONSULTA", "GEEDESCRI") in references(dax)
    assert unknown_references(dax, ModelSchema({})) == [], "sin metadata no se bloquea"
    # Palabras clave antes de un corchete no son tablas («ORDER BY [__orden]», «, [__value], DESC»).
    grouped = _guarded().generate({**_plan(), "mode": "grouped", "temporal_buckets": [
        {"order": 1, "label": "ene", "filters": [{"type": "date_range", "table": "Calendario", "column": "FECHA",
                                                   "start": "2026-01-01", "end": "2026-02-01"}]},
    ], "group_by": [{"column": "Mes"}]})
    assert "ORDER BY [__orden]" in grouped["dax"] and unknown_references(grouped["dax"], schema) == [], grouped


class _Provider:
    default_semantic_model = TIEMPOS

    def __init__(self):
        self.calls = []

    def execute_dax(self, dax, semantic_model=None, **kwargs):
        self.calls.append(dax)
        return {"status": "success", "rows": [{"[__value]": 7}]}


class _Builder:
    dimension_fields = []

    def _technical_catalog(self, model):
        return TIEMPOS_CATALOG


def _engine(provider=None, builder=None):
    return QueryEngine(
        conversation_manager=None, master_metric_resolver=None, master_metric_dax_generator=None,
        metric_resolver=None, filter_resolver=None, business_filter_resolver=None,
        dax_generator=None, dax_validator=None, powerbi_provider=provider or _Provider(),
        rag_answer_engine=None, query_plan_builder=builder or _Builder(),
        query_plan_dax_generator=QueryPlanDAXGenerator(),
    )


def test_engine_repairs_date_and_never_sends_unknown_columns():
    provider = _Provider()
    engine = _engine(provider)
    result = engine._execute_query_plan(_plan())
    assert result["status"] == "success" and result["value"] == 7, result
    assert "'Calendario'[FECHA]" in provider.calls[0] and "[Date]" not in provider.calls[0]

    blocked = engine._execute_dax("EVALUATE ROW(\"v\", COUNTROWS(FILTER(ALL('Calendario'[Date]), TRUE())))", TIEMPOS)
    assert blocked["status"] == "error" and blocked["error_type"] == "unknown_columns"
    assert len(provider.calls) == 1, "la consulta inválida no llega a Power BI"
    assert "Calendario[Date]" in blocked["error"] and "cannot be found" not in blocked["error"]


def test_engine_explains_unknown_columns_without_raw_error():
    provider = _Provider()
    engine = _engine(provider)
    plan = _plan(table="SIN_FECHA", expression="SUM('SIN_FECHA'[VALOR])")
    result = engine._execute_query_plan(plan)
    assert not provider.calls, "no se consulta Power BI"
    assert result["status"] == "unsupported_filter", result
    explanation = result["details"]["explanation"]
    assert result["details"]["reason"] == "date_dimension_not_found_in_report"
    assert "Calendario[Date]" in explanation and "no consulté Power BI" in explanation, explanation


def test_real_tiempos_metadata_has_fecha_not_date():
    """Con la metadata real sincronizada (si está disponible en este equipo)."""
    candidates = [os.getenv("SIM_DATA_ROOT"), ROOT / "data"]
    try:
        from tests.realistic.harness import main_checkout
        candidates.append(main_checkout() / "data")
    except Exception:
        pass
    path = next((Path(c) / "catalog" / "tablero_tiempos_urgencias_rag.json" for c in candidates
                 if c and (Path(c) / "catalog" / "tablero_tiempos_urgencias_rag.json").exists()), None)
    if path is None:
        print("      (sin data/catalog: se omite)")
        return
    schema = ModelSchema(json.loads(path.read_text(encoding="utf-8")))
    assert schema.column("Calendario", "FECHA") and not schema.column("Calendario", "Date")
    assert schema.date_column_for(["INTERCONSULTA"])[:2] == ("Calendario", "FECHA")


# ---------------------------------------------------------------- 2) lista de una dimensión
def test_dimension_list_request_only_for_plain_lists():
    request = dimension_list_request("dame una lista de las areas que tiene el hospital")
    assert request and request["concept"] == "servicio" and dimension_plural(request) == "áreas", request
    assert dimension_list_request("cuáles son las especialidades del hospital")["concept"] == "especialidad"
    assert dimension_list_request("qué aseguradoras hay")["concept"] == "aseguradora"
    for question in (
        "qué camas están disponibles",                      # entidad, no dimensión
        "lista de servicios con egresos en 2025",           # indicador y periodo
        "qué servicios tienen pacientes hospitalizados",    # filtro
        "cuales son los medicos",                           # personas (PII)
        "cuantas aseguradoras hay",                         # total, no lista explícita
    ):
        assert dimension_list_request(question) is None, question


def _field(model, table, column, visual_type="slicer", header=None, page="P"):
    aliases = [column, header or column]
    for word in ("servicio", "area", "areas", "especialidad", "aseguradora", "aseguradoras"):
        if word[:6] in (header or column).lower():
            aliases.append(word)
    return {"semantic_model": model, "table": table, "column": column, "visual_type": visual_type,
            "display_name": header, "page": page, "aliases": aliases}


def test_rank_prefers_literal_dimension_columns_and_skips_private():
    fields = [
        _field("BRIEF", "ATENCIONES_SERVICIO", "SERVICIO", header="SERVICIO"),
        _field("ATEN", "DIM_SERVICIO", "SERVICIO_HOMOLOGADO", header="SERVICIO"),
        _field("FACT", "ULT_GESTION", "AREA_SERVICIO", header="AREA SERVICIO"),
        _field("FACT", "ULT_GESTION", "AREA_SERVICIO", visual_type="clusteredBarChart", header="AREA SERVICIO"),
        _field("RT", "PENDIENTES", "NOMBRE_PACIENTE", header="SERVICIO"),   # PII: nunca
        _field("RT", "PENDIENTES", "COD_AREA", header="AREA"),              # número: no se lista
    ]
    types = {("RT", "PENDIENTES", "COD_AREA"): "number"}
    column_type = lambda model, table, column: types.get((model, table, column), "text")  # noqa: E731
    areas = rank_dimension_columns(fields, dimension_list_request("listado de areas"), column_type=column_type)
    assert [(item["table"], item["column"]) for item in areas][:1] == [("ULT_GESTION", "AREA_SERVICIO")], areas
    assert all(item["column"] not in ("NOMBRE_PACIENTE", "COD_AREA") for item in areas)
    servicios = rank_dimension_columns(fields, dimension_list_request("que servicios tiene el hospital"),
                                       column_type=column_type)
    assert servicios[0]["table"] == "DIM_SERVICIO", servicios
    exists = lambda model, table, column: table != "DIM_SERVICIO"  # noqa: E731
    assert rank_dimension_columns(fields, dimension_list_request("que servicios hay"), exists=exists)[0][
        "table"] != "DIM_SERVICIO"


def test_dimension_values_clean_and_cap():
    values, total, truncated = dimension_values(["UCI", None, "", "uci", "Urgencias", "(En blanco)", "Cirugía"], 2)
    assert values == ["Cirugía", "UCI"] and total == 3 and truncated


class _ListingBuilder(_Builder):
    dimension_fields = [
        _field(TIEMPOS, "INTERCONSULTA", "GEEDESCRI", header="ESPECIALIDAD"),
        _field("ASIGNACION", "ESPECIALIDADES", "GEEDESCRI", header="ESPECIALIDAD", page="DISPO"),
    ]

    def __init__(self):
        self.asked = []

    def _technical_catalog(self, model):
        return TIEMPOS_CATALOG if model == TIEMPOS else {
            "tables": [{"name": "ESPECIALIDADES", "columns": [_col("GEEDESCRI")]}],
        }

    def _column_type(self, model, table, column):
        return "text"

    def _get_values(self, model, table, column, essential=False, limit=None):
        self.asked.append((model, table, column))
        return ["PEDIATRIA", "CARDIOLOGIA", None, "PEDIATRIA"]


def test_engine_lists_dimension_values_with_source():
    builder = _ListingBuilder()
    engine = _engine(builder=builder)
    result = engine._dimension_listing("cuáles son las especialidades del hospital")
    assert result and result["status"] == "success" and result["route"] == "powerbi", result
    assert builder.asked == [("ASIGNACION", "ESPECIALIDADES", "GEEDESCRI")], builder.asked
    answer = result["answer"]
    assert "Power BI registra 2 especialidades" in answer and "- CARDIOLOGIA\n- PEDIATRIA" in answer, answer
    assert "ESPECIALIDADES[GEEDESCRI]" in answer and "«ASIGNACION»" in answer, answer
    assert f"«{TIEMPOS}» (INTERCONSULTA[GEEDESCRI])" in answer, "menciona el otro tablero"
    assert engine._dimension_listing("cuántas interconsultas respondidas hubo ayer") is None


# ---------------------------------------------------------------- 3) respaldo extractivo
SOURCES = [
    {"chunk_type": "dashboard_overview", "dashboard": "DETALLE BRIEFING", "score": 0.61,
     "source_group": "tablero_briefing", "semantic_model": "BRIEFING HOSPITALARIO",
     "text": "Tablero: DETALLE BRIEFING Alias: Descripción: Casos abiertos reportados por las áreas para el "
             "briefing diario. Lista los casos y novedades que las áreas reportan, con el último…"},
    {"chunk_type": "document_section", "dashboard": "DICCIONARIO TABLERO FARMACIA", "score": 0.57,
     "source_group": "tablero_farmacia", "semantic_model": "TABLERO_FARMACIA",
     "text": "Tablero: DICCIONARIO TABLERO FARMACIA Sección: Columnas clave Contenido: "
             "TIEMPOS_DISPENSACIÓN[gasnombre]: Nombre del área de servicio (GENARESER) del folio. Tipo: texto. "
             "Se usa en: OPORTUNIDAD DISPENSACIÓN › Segmentación de TIEMPOS_DISPENSACIÓN[gasnombre]"},
    {"chunk_type": "document_section", "dashboard": "DICCIONARIO COLUMNAS BRIEFING HOSPITALARIO", "score": 0.56,
     "source_group": "tablero_briefing", "semantic_model": "BRIEFING HOSPITALARIO",
     "text": "Tablero: DICCIONARIO COLUMNAS BRIEFING HOSPITALARIO Sección: Columnas clave Contenido: "
             "BOLETIN[SERVICIO]: Área o dependencia que reporta la solicitud del briefing. Tipo: texto. "
             "Se usa en: INICIO › Gráfico de anillos «SERVICIO»"},
    {"chunk_type": "document_section", "dashboard": "DETALLE BRIEFING", "score": 0.7,
     "source_group": "tablero_briefing", "semantic_model": "BRIEFING HOSPITALARIO",
     "text": "Tablero: DETALLE BRIEFING Sección: Historial de cambios Contenido: 2026-10-28 · v2: revisión."},
]


def test_extractive_fallback_is_pertinent_complete_and_single_board():
    answer = readable_fallback(SOURCES, question="dame una lista de las areas que tiene el hospital")
    assert answer.startswith("Según la documentación de los tableros:\n- DETALLE BRIEFING: Casos abiertos"), answer
    assert "TIEMPOS_DISPENSACIÓN" not in answer, "no mezcla otro tablero"
    assert "Historial de cambios" not in answer and "Se usa en" not in answer, answer
    assert "el último…" not in answer and "…" not in answer, "sin frases cortadas"
    assert "BOLETIN[SERVICIO] (Diccionario de variables · COLUMNAS BRIEFING HOSPITALARIO): Área" in answer, answer
    assert answer.endswith("Fuente: tablero BRIEFING HOSPITALARIO."), answer


def test_extractive_fallback_puts_the_named_entry_first():
    sources = [
        {"chunk_type": "document_section", "dashboard": "DICCIONARIO TABLERO LAVANDERIA", "score": 0.6,
         "text": "Tablero: DICCIONARIO TABLERO LAVANDERIA Sección: Columnas clave Contenido: LAVANDERIA[Turno]: "
                 "Código del turno laboral. Tipo: entero."},
        {"chunk_type": "document_section", "dashboard": "DICCIONARIO TABLERO LAVANDERIA", "score": 0.58,
         "text": "Tablero: DICCIONARIO TABLERO LAVANDERIA Sección: Columnas calculadas Contenido: "
                 "LAVANDERIA[TURNO_OK]: Turno laboral en texto: 1 es MAÑANA, 2 es TARDE y 3 es NOCHE."},
    ]
    answer = readable_fallback(sources, question="que significa turno ok en lavanderia")
    assert answer.split("\n")[1].startswith("- LAVANDERIA[TURNO_OK]"), answer


def test_long_description_is_cut_at_sentence_end():
    sentence = "Primera frase con bastante detalle sobre el indicador y su cálculo mensual. "
    source = {"chunk_type": "indicator", "dashboard": "X",
              "text": "Tablero: X Indicador: Y Descripción: " + sentence * 8 + "Última frase sin cortar"}
    answer = readable_fallback([source], question="que es y")
    body = answer.split(": ", 1)[1]
    assert body.endswith("mensual.") and "…" not in body and len(body) <= 360, answer


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except Exception:
            failed += 1
            print(f"FAIL  {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
