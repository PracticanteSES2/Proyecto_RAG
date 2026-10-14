"""
Pruebas del «total + listado» (sin servicios externos).

- Forma de la respuesta (src/semantic/answer_shape.py): escalar, agrupada y
  listado explícito o condicionado.
- Columnas del listado (src/semantic/detail_list.py): entidad contada, tabla de
  detalle del catálogo, respaldo por reglas sin catálogo y exclusión de datos de
  personas.
- DAX del listado (QueryPlanDAXGenerator.generate_detail) y su validación.
- Redacción (format_query_plan_answer con `detail`).
- Catálogo visual: campo opcional detail_tables.
- QueryEngine._detail_listing: una sola consulta extra, tope y fallo de Power BI.

Ejecutar:
  PYTHONDONTWRITEBYTECODE=1 PYTHONIOENCODING=utf-8 python -m tests.detalle.test_detalle
"""
import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.chatbot.response_formatter import format_query_plan_answer  # noqa: E402
from src.dax.query_plan_dax_generator import QueryPlanDAXGenerator  # noqa: E402
from src.semantic.answer_shape import answer_shape, detail_request  # noqa: E402
from src.semantic.detail_list import (  # noqa: E402
    consistency,
    counted_entity,
    detail_max_rows,
    detail_rows,
    is_private_column,
    listable_entity,
    plan_detail,
    validate_detail_dax,
)

CAMAS_T = "CAMAS DISPONIBLES"
MODEL = "BRIEFING HOSPITALARIO"

TECHNICAL = {"tables": [
    {"name": CAMAS_T, "columns": [
        {"name": "RowNumber-2662979B", "data_type": "Int64"},
        {"name": "MOSTRAR_6TO", "data_type": "Int64"},
        {"name": "HCACODIGO", "data_type": "String"},
        {"name": "Orden", "data_type": "String"},
        {"name": "ESTADOS_CAM", "data_type": "String"},
        {"name": "SERVICIOS", "data_type": "String"},
    ], "measures": [{"name": "CAMAS", "expression": "COUNT('CAMAS DISPONIBLES'[HCACODIGO])"}]},
    {"name": "PACIENTES X ASEGURADORA", "columns": [
        {"name": c, "data_type": "String"} for c in
        ("PACNUMDOC", "GPANOMCOM", "HCACODIGO", "HSUNOMBRE", "TERNOMCOM", "GDENOMBRE", "ADNINGRESO", "ORDEN_CAMAS")
    ]},
]}


def _field(table, column, header, kind="column"):
    return {"kind": kind, "table": table, "column": column, "native_query_ref": header, "display_name": header}


VISUAL_CATALOG = {"reports": [{
    "report": MODEL, "semantic_model": MODEL,
    "pages": [
        {"page_display_name": "GESTIÓN CAMAS", "visuals": [
            {"visual_type": "pivotTable", "fields": [
                _field(CAMAS_T, "SERVICIOS", "SERVICIO"), _field(CAMAS_T, "ESTADOS_CAM", "ESTADO"),
                {"kind": "measure", "table": CAMAS_T, "measure": "CAMAS"}]},
            {"visual_type": "tableEx", "visual_title": "CAMAS OCUPADAS", "fields": [
                _field("GESTIÓN CAMAS", "HSUNOMBRE", "SERVICIO"), _field("GESTIÓN CAMAS", "HCACODIGO", "CAMA"),
                _field("GESTIÓN CAMAS", "NOMBRE_COMP", "ULTIMO USUARIO EN MARCAR")]},
        ]},
        {"page_display_name": "DETALLE OCUPACIÓN", "visuals": [
            {"visual_type": "tableEx", "fields": [
                _field("PACIENTES X ASEGURADORA", "PACNUMDOC", "CEDULA"),
                _field("PACIENTES X ASEGURADORA", "GPANOMCOM", "PACIENTE"),
                _field("PACIENTES X ASEGURADORA", "HCACODIGO", "CAMA"),
                _field("PACIENTES X ASEGURADORA", "HSUNOMBRE", "SERVICIO"),
                _field("PACIENTES X ASEGURADORA", "TERNOMCOM", "ASEGURADORA"),
                _field("PACIENTES X ASEGURADORA", "GDENOMBRE", "PLAN DE BENEFICIOS"),
                _field("PACIENTES X ASEGURADORA", "ORDEN_CAMAS", " ")]},
        ]},
    ],
}]}


class FakeBuilder:
    def __init__(self, visual_catalog=None, technical=None):
        self.visual_catalog = visual_catalog if visual_catalog is not None else VISUAL_CATALOG
        self.technical = technical if technical is not None else TECHNICAL

    def _technical_catalog(self, model):
        return self.technical

    def _column_type(self, model, table, column):
        for item in self.technical.get("tables") or []:
            if item["name"] == table:
                for col in item["columns"]:
                    if col["name"] == column:
                        return "number" if "Int" in col["data_type"] else "text"
        return None


CAMAS_METRIC = {"metric_id": "c1", "label": "CAMAS", "semantic_model": MODEL, "table": CAMAS_T,
                "measure": "CAMAS", "dax_expression": "[CAMAS]", "validation_status": "approved",
                "model_expression": "COUNT('CAMAS DISPONIBLES'[HCACODIGO])"}


def _plan(question, metric=None, filters=(), **extra):
    return {"status": "ready", "mode": "scalar", "question": question, "semantic_model": MODEL,
            "metric": metric or CAMAS_METRIC, "filters": list(filters), "group_by": [], **extra}


def _cat(column, value, concept=None, table=CAMAS_T):
    return {"type": "categorical", "table": table, "column": column, "value": value, "concept": concept}


# ============================================================
# FORMA DE LA RESPUESTA
# ============================================================

def test_shape_rules():
    cases = {
        "qué camas están disponibles en UCI": ("detail", "explicit"),
        "lista de camas bloqueadas": ("detail", "explicit"),
        "listado de pacientes en UCI": ("detail", "explicit"),
        "cuáles son las camas disponibles": ("detail", "explicit"),
        "detalle de las camas bloqueadas": ("detail", "explicit"),
        "muéstrame las camas disponibles": ("detail", "soft"),
        "cuántas camas hay disponibles en hospitalización general": ("detail", "soft"),
        "cuantas camas bloqueadas hay": ("detail", "soft"),
        "cuántas cirugías hubo en 2024": ("scalar", None),
        "cuantas camas hay disponibles este mes": ("scalar", None),
        "¿Cuántos pacientes hay por aseguradora?": ("grouped", None),
        "necesito el detalle de ocupación por aseguradores": ("grouped", None),
        "distribución de camas disponibles": ("grouped", None),
        "qué servicios tienen más egresos": ("scalar", None),
        "cuales son los rangos del nedocs": ("scalar", None),
        "que filtros tiene el tablero de lavanderia": ("scalar", None),
        "escribeme un codigo en python para ordenar una lista": ("scalar", None),
        "dame los egresos de 2025": ("scalar", None),
    }
    for question, (shape, strength) in cases.items():
        assert answer_shape(question) == shape, (question, answer_shape(question))
        request = detail_request(question)
        assert (request or {}).get("strength") == strength, (question, request)
    assert detail_request("qué camas están disponibles en UCI")["entity"] == "camas"


# ============================================================
# ENTIDAD Y COLUMNAS
# ============================================================

def test_counted_entity_and_listable():
    assert counted_entity("COUNT('CAMAS DISPONIBLES'[HCACODIGO])") == {
        "function": "COUNT", "table": CAMAS_T, "column": "HCACODIGO"}
    filtered = counted_entity("CALCULATE(\nDISTINCTCOUNT('CAMAS DISPONIBLES'[HCACODIGO]),\nFILTER(...))")
    assert filtered["function"] == "DISTINCTCOUNT" and filtered["column"] == "HCACODIGO"
    assert counted_entity("COUNTROWS(FILTER('EGRESOS', 'EGRESOS'[X] = 1))") == {
        "function": "COUNTROWS", "table": "EGRESOS", "column": None}
    assert counted_entity("SUM('SOLICITUD_CAMAS'[DEMANDA_INS])") is None
    builder = FakeBuilder()
    assert listable_entity(CAMAS_METRIC, builder)["column"] == "HCACODIGO"
    assert listable_entity({**CAMAS_METRIC, "model_expression": "SUM('SOLICITUD_CAMAS'[DEMANDA_INS])"}, builder) is None
    # Un conteo de una cifra (no un código) no identifica registros.
    assert listable_entity({**CAMAS_METRIC, "model_expression": "COUNT('CAMAS DISPONIBLES'[MOSTRAR_6TO])"},
                           builder) is None
    # COUNT de una columna descriptiva cuenta filas, no entidades; DISTINCTCOUNT de texto sí.
    assert listable_entity({**CAMAS_METRIC, "model_expression": "COUNT('CONSULTAS PRIORITARIAS'[ASEGURADOR])"},
                           builder) is None
    assert listable_entity({**CAMAS_METRIC, "model_expression": "DISTINCTCOUNT('X'[ASEGURADOR])"}, builder)
    assert listable_entity({**CAMAS_METRIC, "model_expression": "DISTINCTCOUNT('PENDIENTES'[HCNFOLIO])"}, builder)


def test_listable_choice_only_for_explicit_lists():
    """Desempate: solo con lista explícita y solo entre las opciones que se ofrecerían."""
    suma = {"metric_id": "h1", "label": "HOSPITALIZACIÓN", "table": "SOLICITUD_CAMAS",
            "model_expression": "SUM('SOLICITUD_CAMAS'[DEMANDA_INS])"}
    filtradas = {**CAMAS_METRIC, "metric_id": "f1", "label": "CamasFiltradas",
                 "model_expression": "CALCULATE(DISTINCTCOUNT('CAMAS DISPONIBLES'[HCACODIGO]), FILTER(...))"}
    plan = {"status": "ambiguous", "metric_resolution": {"candidates": [
        {"metric": suma, "score": 1.21}, {"metric": CAMAS_METRIC, "score": 1.19},
        {"metric": filtradas, "score": 0.43}]}}
    engine = _engine(FakeProvider({}))
    assert engine._listable_choice("lista de camas bloqueadas", plan)["metric_id"] == "c1"
    assert engine._listable_choice("cuántas camas hay disponibles en UCI", plan) is None
    close = json.loads(json.dumps(plan))
    close["metric_resolution"]["candidates"][2]["score"] = 1.2
    assert engine._listable_choice("lista de camas bloqueadas", close) is None, "dos listables: se pregunta"


def test_private_columns_policy():
    for column, header in [("PACNUMDOC", "CEDULA"), ("GPANOMCOM", "PACIENTE"), ("Identificacion", "DOCUMENTO"),
                           ("NOMBRE_COMP", "ULTIMO USUARIO EN MARCAR"), ("TELEFONO", None), ("ADNINGRESO", None),
                           ("NOMBRE_PACIENTE", "PACIENTE")]:
        assert is_private_column(column, header), column
    for column, header in [("HCACODIGO", "CAMA"), ("HSUNOMBRE", "SERVICIO"), ("TERNOMCOM", "ASEGURADORA"),
                           ("SERVICIOS", "SERVICIO"), ("ESTADOS_CAM", "ESTADO")]:
        assert not is_private_column(column, header), column
    previous = os.environ.get("POWERBI_DETAIL_ALLOWED_COLUMNS")
    os.environ["POWERBI_DETAIL_ALLOWED_COLUMNS"] = "'PACIENTES X ASEGURADORA'[GPANOMCOM]"
    try:
        assert not is_private_column("GPANOMCOM", "PACIENTE", "PACIENTES X ASEGURADORA")
        assert is_private_column("GPANOMCOM", "PACIENTE", "OTRA TABLA")
    finally:
        if previous is None:
            os.environ.pop("POWERBI_DETAIL_ALLOWED_COLUMNS", None)
        else:
            os.environ["POWERBI_DETAIL_ALLOWED_COLUMNS"] = previous


def test_columns_fallback_location_and_entity_with_business_names():
    spec = plan_detail(_plan("lista de camas bloqueadas", filters=[_cat("ESTADOS_CAM", "BLOQUEADA", "ESTADO")]),
                       FakeBuilder())
    assert spec["status"] == "ready" and spec["source"] == "reglas", spec
    # La ubicación (SERVICIOS «SERVICIO», nombre del visual) y la cama («CAMA», nombre de otra
    # tabla de detalle del mismo modelo); el estado filtrado con un valor no se repite.
    assert [(c["column"], c["header"], c["role"]) for c in spec["columns"]] == [
        ("SERVICIOS", "SERVICIO", "location"), ("HCACODIGO", "CAMA", "entity")]


def test_columns_filter_location_first_and_multivalued_filters():
    filters = [_cat("SERVICIOS", "HOSPITALIZACIÓN GENERAL", "SERVICIO"),
               {"type": "categorical", "table": CAMAS_T, "column": "ESTADOS_CAM", "value": None,
                "values": ["DISPONIBLE", "EN TRANSICIÓN"], "concept": "ESTADO"}]
    spec = plan_detail(_plan("cuántas camas hay disponibles en hospitalización general", filters=filters),
                       FakeBuilder())
    assert [c["column"] for c in spec["columns"]] == ["SERVICIOS", "ESTADOS_CAM", "HCACODIGO"], spec["columns"]


def test_columns_without_any_catalog():
    """Sin catálogo visual ni técnico (nada que reconstruir): entidad con nombre legible."""
    spec = plan_detail(_plan("lista de camas bloqueadas"), FakeBuilder(visual_catalog={}, technical={}))
    assert spec["status"] == "ready" and [(c["column"], c["header"]) for c in spec["columns"]] == [
        ("HCACODIGO", "HCACODIGO")]


def test_columns_from_catalog_detail_table_exclude_patients():
    metric = {**CAMAS_METRIC, "label": "PACIENTES", "table": "PACIENTES X ASEGURADORA",
              "model_expression": "COUNT('PACIENTES X ASEGURADORA'[HCACODIGO])"}
    spec = plan_detail(_plan("lista de pacientes hospitalizados", metric), FakeBuilder())
    assert spec["source"] == "catalogo" and "DETALLE OCUPACIÓN" in spec["visual"], spec
    assert [c["header"] for c in spec["columns"]] == ["CAMA", "SERVICIO", "ASEGURADORA", "PLAN DE BENEFICIOS"]
    assert spec["excluded_private"] == ["CEDULA", "PACIENTE"]
    # Catálogo reconstruido: detail_tables tiene prioridad sobre pages.
    rebuilt = json.loads(json.dumps(VISUAL_CATALOG))
    rebuilt["reports"][0]["detail_tables"] = [{"visual_title": "NUEVA", "columns": [
        {"table": "PACIENTES X ASEGURADORA", "column": "HCACODIGO", "header": "CAMA"},
        {"table": "PACIENTES X ASEGURADORA", "column": "TERNOMCOM", "header": "EPS"}]}]
    spec = plan_detail(_plan("lista de pacientes hospitalizados", metric), FakeBuilder(visual_catalog=rebuilt))
    assert [c["header"] for c in spec["columns"]] == ["CAMA", "EPS"]


def test_not_listable_and_not_requested():
    builder = FakeBuilder()
    assert plan_detail(_plan("cuántas camas hay en 2024"), builder)["status"] == "not_requested"
    assert plan_detail(_plan("lista de camas", group_by=[{"table": CAMAS_T, "column": "SERVICIOS"}],
                             mode="grouped"), builder)["status"] == "not_requested"
    suma = {**CAMAS_METRIC, "model_expression": "SUM('SOLICITUD_CAMAS'[DEMANDA_INS])"}
    assert plan_detail(_plan("lista de camas", suma), builder)["status"] == "not_listable"


# ============================================================
# DAX Y VALIDACIÓN
# ============================================================

def test_detail_dax_uses_same_filters_and_topn():
    plan = _plan("lista de camas bloqueadas", filters=[_cat("ESTADOS_CAM", "BLOQUEADA")])
    columns = [{"table": CAMAS_T, "column": "SERVICIOS"}, {"table": CAMAS_T, "column": "HCACODIGO"}]
    result = QueryPlanDAXGenerator().generate_detail(plan, columns, 51)
    dax = result["dax"]
    assert result["status"] == "generated" and dax.startswith("EVALUATE\nTOPN(\n    51,")
    assert "TREATAS({\"BLOQUEADA\"}, 'CAMAS DISPONIBLES'[ESTADOS_CAM])" in dax
    assert "\"__value\",\n        [CAMAS]" in dax
    assert dax.endswith("ORDER BY 'CAMAS DISPONIBLES'[SERVICIOS] ASC, 'CAMAS DISPONIBLES'[HCACODIGO] ASC")
    assert validate_detail_dax(dax, columns, TECHNICAL, 51)["valid"]
    bad = validate_detail_dax(dax, [{"table": CAMAS_T, "column": "NO_EXISTE"}], TECHNICAL, 51)
    assert not bad["valid"] and "NO_EXISTE" in bad["errors"][0]
    assert not validate_detail_dax("DEFINE MEASURE x = 1 " + dax, columns, TECHNICAL, 51)["valid"]
    assert not validate_detail_dax(dax, columns, TECHNICAL, 10)["valid"], "el tope debe coincidir"
    unapproved = dict(plan, metric={**CAMAS_METRIC, "validation_status": "needs_review"})
    assert QueryPlanDAXGenerator().generate_detail(unapproved, columns, 51)["status"] == "rejected"


def test_rows_and_consistency():
    columns = [{"table": CAMAS_T, "column": "SERVICIOS"}, {"table": CAMAS_T, "column": "HCACODIGO"}]
    rows = [{"CAMAS DISPONIBLES[SERVICIOS]": "UCI ADULTOS", "CAMAS DISPONIBLES[HCACODIGO]": "UCI-06",
             "[__value]": 1},
            {"CAMAS DISPONIBLES[SERVICIOS]": "UCI ADULTOS", "CAMAS DISPONIBLES[HCACODIGO]": "UCI-07",
             "[__value]": 1}]
    cells, counts, truncated, all_counts = detail_rows(rows, columns, 1)
    assert cells == [["UCI ADULTOS", "UCI-06"]] and truncated and counts == [1]
    assert consistency(2, all_counts, False, "COUNT") == "ok"
    assert consistency(3, all_counts, False, "COUNT") == "mismatch"
    assert consistency(5, [5, 5, 5], False, "COUNT") == "constant"
    assert consistency(80, all_counts, True, "COUNT") == "unknown"
    assert detail_max_rows() == int(os.environ.get("POWERBI_DETAIL_MAX_ROWS") or 50)


# ============================================================
# REDACCIÓN
# ============================================================

def _result(question, value, detail, filters):
    plan = _plan(question, filters=filters)
    return {"status": "success", "route": "powerbi", "result_type": "scalar", "metric": "CAMAS",
            "value": value, "filters": filters, "query_plan": plan, "question": question, "detail": detail}


def _detail(rows, **extra):
    base = {"status": "ok", "entity_word": "camas", "cap": 50, "rows": rows, "counts": [1] * len(rows),
            "truncated": False, "consistency": "ok", "show_counts": False, "excluded_private": [],
            "columns": [{"table": CAMAS_T, "column": "SERVICIOS", "header": "SERVICIO", "role": "location"},
                        {"table": CAMAS_T, "column": "HCACODIGO", "header": "CAMA", "role": "entity"}]}
    return {**base, **extra}


def test_format_total_plus_list():
    filters = [_cat("ESTADOS_CAM", "DISPONIBLE", "ESTADO"), _cat("SERVICIOS", "HOSPITALIZACIÓN GENERAL", "SERVICIO")]
    rows = [["HOSPITALIZACIÓN GENERAL", code] for code in ("403", "407", "411", "415", "419", "422")]
    text = format_query_plan_answer(_result(
        "cuántas camas hay disponibles en hospitalización general", 6, _detail(rows), filters))
    assert text.startswith("**6 camas disponibles** en HOSPITALIZACIÓN GENERAL (indicador CAMAS):"), text
    assert "| SERVICIO | CAMA |" in text and "| HOSPITALIZACIÓN GENERAL | 422 |" in text
    assert "Filtros: ESTADO = DISPONIBLE · SERVICIO = HOSPITALIZACIÓN GENERAL." in text
    # Un solo resultado: concordancia en singular.
    one = format_query_plan_answer(_result(
        "qué camas están disponibles en UCI", 1, _detail([["UCI ADULTOS", "UCI-06"]]),
        [_cat("ESTADOS_CAM", "DISPONIBLE", "ESTADO"), _cat("SERVICIOS", "UCI ADULTOS", "SERVICIO")]))
    assert one.startswith("**1 cama disponible** en UCI ADULTOS"), one
    # Sin el filtro de estado aplicado, la frase no dice «disponibles».
    plain = format_query_plan_answer(_result(
        "qué camas están disponibles en UCI", 2, _detail([["UCI ADULTOS", "UCI-01"], ["UCI ADULTOS", "UCI-02"]]),
        [_cat("SERVICIOS", "UCI ADULTOS", "SERVICIO")]))
    assert plain.startswith("**2 camas** en UCI ADULTOS"), plain


def test_format_notes_truncated_long_error_privacy():
    filters = [_cat("ESTADOS_CAM", "OCUPADA", "ESTADO")]
    rows = [["HOSPITALIZACIÓN GENERAL", str(400 + i)] for i in range(50)]
    truncated = format_query_plan_answer(_result(
        "lista de camas ocupadas", 80, _detail(rows, truncated=True, consistency="unknown"), filters))
    assert "Muestro las primeras 50 filas de 80 camas" in truncated and "Indica un servicio" in truncated
    long = format_query_plan_answer(_result(
        "cuántas camas ocupadas hay", 80, _detail([], status="too_long"), filters))
    assert "**80 camas ocupadas**" in long and "demasiado larga" in long and "|" not in long
    error = format_query_plan_answer(_result(
        "lista de camas ocupadas", 80, _detail([], status="error", error="tiempo agotado"), filters))
    assert "**CAMAS**" in error and "No pude traer la lista de detalle (tiempo agotado)" in error
    private = format_query_plan_answer(_result(
        "lista de camas ocupadas", 2, _detail([["X", "1"], ["X", "2"]], excluded_private=["CEDULA", "PACIENTE"]),
        filters))
    assert "Por privacidad" in private and "CEDULA, PACIENTE" in private
    mismatch = format_query_plan_answer(_result(
        "lista de camas ocupadas", 3, _detail([["X", "1"], ["X", "2"]], consistency="mismatch"), filters))
    assert "suman 2" in mismatch


# ============================================================
# CATÁLOGO VISUAL
# ============================================================

def test_visual_catalog_records_detail_tables():
    from src.semantic.visual_catalog_builder import PBIRVisualCatalogBuilder

    with tempfile.TemporaryDirectory() as temp:
        page = Path(temp) / "Demo.Report" / "definition" / "pages" / "p1"
        visual = page / "visuals" / "v1"
        visual.mkdir(parents=True)
        (page / "page.json").write_text(json.dumps({"name": "p1", "displayName": "DETALLE"}), encoding="utf-8")

        def column(table, name, header):
            return {"field": {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}},
                    "queryRef": f"{table}.{name}", "nativeQueryRef": header}

        (visual / "visual.json").write_text(json.dumps({"name": "v1", "visual": {
            "visualType": "tableEx", "query": {"queryState": {"Values": {"projections": [
                column("PACIENTES", "PACNUMDOC", "CEDULA"), column("PACIENTES", "HCACODIGO", "CAMA"),
                column("PACIENTES", "HSUNOMBRE", "SERVICIO")]}}}}}), encoding="utf-8")
        catalog = PBIRVisualCatalogBuilder(Path(temp) / "Demo.Report").build()
    tables = catalog["detail_tables"]
    assert catalog["stats"]["detail_tables"] == 1 and len(tables) == 1
    assert [(c["column"], c["header"], c["private"]) for c in tables[0]["columns"]] == [
        ("PACNUMDOC", "CEDULA", True), ("HCACODIGO", "CAMA", False), ("HSUNOMBRE", "SERVICIO", False)]
    assert catalog["metrics"] == [] and catalog["pages"][0]["visuals"], "lo existente no cambia"


# ============================================================
# MOTOR: una consulta extra, tope y fallos
# ============================================================

class FakeProvider:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def execute_dax(self, dax, semantic_model=None, timeout_s=None):
        self.calls.append((dax, timeout_s))
        return self.result


class FakeValidator:
    def validate_detail_query(self, dax, columns, limit, semantic_model=None):
        return validate_detail_dax(dax, columns, TECHNICAL, limit)


def _engine(provider):
    from src.chatbot.query_engine import QueryEngine

    engine = QueryEngine.__new__(QueryEngine)
    engine._trace = None
    engine.query_plan_builder = FakeBuilder()
    engine.query_plan_dax_generator = QueryPlanDAXGenerator()
    engine.dax_validator = FakeValidator()
    engine.powerbi_provider = provider
    return engine


def test_engine_detail_listing_one_query_cap_and_errors():
    rows = [{"CAMAS DISPONIBLES[SERVICIOS]": "PEDIATRÍA", "CAMAS DISPONIBLES[HCACODIGO]": c, "[__value]": 1}
            for c in ("609", "610")]
    plan = _plan("lista de camas bloqueadas", filters=[_cat("ESTADOS_CAM", "BLOQUEADA", "ESTADO")])
    provider = FakeProvider({"status": "success", "rows": rows})
    detail = _engine(provider)._detail_listing(plan, 2)
    assert detail["status"] == "ok" and detail["rows"] == [["PEDIATRÍA", "609"], ["PEDIATRÍA", "610"]]
    assert len(provider.calls) == 1 and provider.calls[0][1], "una sola consulta, con tiempo límite"
    # «cuántas … hay» con un total mayor que el tope: sin consulta extra.
    soft = _plan("cuantas camas bloqueadas hay", filters=[_cat("ESTADOS_CAM", "BLOQUEADA", "ESTADO")])
    provider = FakeProvider({"status": "success", "rows": rows})
    assert _engine(provider)._detail_listing(soft, 500)["status"] == "too_long" and not provider.calls
    # Error o tiempo agotado: el total se conserva y se avisa.
    provider = FakeProvider({"status": "error", "timed_out": True, "error": "timeout"})
    failed = _engine(provider)._detail_listing(plan, 2)
    assert failed["status"] == "error" and failed["error"] == "tiempo agotado"
    # Pregunta sin listado: nada.
    assert _engine(FakeProvider({})) ._detail_listing(_plan("cuántas camas hubo en 2024"), 5) is None


def _run_all():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, func in tests:
        try:
            func()
            print("PASS ", name)
        except Exception:  # noqa: BLE001
            failed += 1
            print("FAIL ", name)
            traceback.print_exc()
    print(f"{len(tests) - failed}/{len(tests)} OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run_all())
