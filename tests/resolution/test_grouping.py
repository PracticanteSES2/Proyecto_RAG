"""
Agrupación y columnas que filtran el indicador en QueryPlanBuilder (offline).

1) Relación columna-indicador (`_dimension_relation`): la columna de la propia
   tabla siempre vale; con relaciones declaradas (aunque la lista esté vacía,
   como BRIEFING) una tabla no conectada no agrupa ni filtra; sin relaciones
   declaradas solo se descarta si la tabla del indicador tiene su propia
   columna equivalente.
2) «por X»: se agrupa por la columna de la tabla del indicador (ASEGURADOR de
   CONSULTAS) y no por la de otra tabla (TERNOMCOM de EGRESOS), con plural y
   género («aseguradores») y con el nombre de negocio de los visuales
   (HSUNOMBRE «SERVICIO» aunque la dona no lo renombre).
3) «hoy» sobre una tabla sin fecha (estado actual de las camas): no se filtra
   con la fecha de otra tabla; se responde el valor actual y se dice.
4) «detalle de ocupación por aseguradores»: %OCUPACION no se desglosa por
   aseguradora; se responde con el indicador de la página DETALLE OCUPACIÓN
   que sí (también si el usuario eligió %OCUPACION con un botón).

Ejecutar:  python -m tests.resolution.test_grouping      (o pytest tests/resolution)
"""
import json
import sys
import tempfile
import traceback
from datetime import date
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.semantic.query_plan_builder import QueryPlanBuilder, _alias_prefix  # noqa: E402
from src.semantic.source_model_router import SourceModelRouter  # noqa: E402
from tests.resolution.test_resolution import _metric, _source  # noqa: E402

HOSP, ATEN, VENT = "Modelo Hospital", "Modelo Atenciones", "Modelo Ventas"
TODAY = date(2026, 10, 14)


def _field(table, column, display=None, kind="column", role="Values"):
    return {"role": role, "kind": kind, "table": table, "column": column,
            "display_name": display, "native_query_ref": display or column,
            "query_ref": f"{table}.{column}"}


def _visual(visual_id, visual_type, *fields):
    return {"visual_id": visual_id, "visual_type": visual_type, "fields": list(fields)}


def _columns(*specs):
    return [{"name": name, "data_type": data_type} for name, data_type in specs]


def _build_fixture(root):
    catalog = root / "data" / "catalog"
    rag = root / "data" / "rag"
    for folder in (catalog, rag):
        folder.mkdir(parents=True)
    sources = [
        _source("hosp", "Tablero Hospital", HOSP, ["tablero hospital"]),
        _source("aten", "Tablero Atenciones", ATEN, ["tablero atenciones"]),
        _source("vent", "Tablero Ventas", VENT, ["tablero ventas"]),
    ]
    registry = {
        "models": [
            {"semantic_model": s["semantic_model"], "semantic_model_key": s["source_group"],
             "technical_catalog": s["technical_catalog"]}
            for s in sources
        ],
        "sources": sources,
    }
    technical = {
        # Como BRIEFING HOSPITALARIO: relaciones declaradas, ninguna (tablas independientes).
        "hosp": {"semantic_model": HOSP, "relationships": [], "tables": [
            {"name": "CAMAS DISPONIBLES", "columns": _columns(
                ("SERVICIOS", "String"), ("HCACODIGO", "String"), ("OCUPADAS", "Int64"))},
            {"name": "PACIENTES X ASEGURADORA", "columns": _columns(
                ("TERNOMCOM", "String"), ("HSUNOMBRE", "String"), ("ADNINGRESO", "String"))},
            {"name": "ATENCIONES_SERVICIO", "columns": _columns(
                ("FECHA", "DateTime"), ("SERVICIO", "String"))},
        ]},
        # Relaciones declaradas: CONSULTAS -> Calendario; EGRESOS no filtra CONSULTAS.
        "aten": {"semantic_model": ATEN, "tables": [
            {"name": "CONSULTAS PRIORITARIAS", "columns": _columns(
                ("ASEGURADOR", "String"), ("FECHA", "DateTime"))},
            {"name": "EGRESOS_POR_SERVICIO", "columns": _columns(("TERNOMCOM", "String"))},
            {"name": "Calendario", "columns": _columns(("Date", "DateTime"))},
        ], "relationships": [
            {"FromTable": "CONSULTAS PRIORITARIAS", "FromColumn": "FECHA", "ToTable": "Calendario",
             "ToColumn": "Date", "IsActive": True},
        ]},
        # Sin metadata de relaciones.
        "vent": {"semantic_model": VENT, "tables": [
            {"name": "VENTAS", "columns": _columns(("SEDE", "String"), ("VALOR", "Double"))},
            {"name": "OTRA", "columns": _columns(("SEDE", "String"), ("ZONA", "String"))},
        ]},
    }
    visuals_catalog = {"schema_version": 2, "reports": [
        {"report": "Tablero Hospital", "semantic_model": HOSP, "source_group": "hosp", "pages": [
            {"page_name": "h1", "page_display_name": "Inicio", "filters": {}, "visuals": [
                _visual("ocup_0", "gauge"),
                _visual("h_fecha", "slicer", _field("ATENCIONES_SERVICIO", "FECHA")),
                _visual("h_aseg", "slicer", _field("PACIENTES X ASEGURADORA", "TERNOMCOM", "ASEGURADORA")),
            ]},
            {"page_name": "h2", "page_display_name": "Gestion camas", "filters": {}, "visuals": [
                _visual("h_mat", "pivotTable", _field("CAMAS DISPONIBLES", "SERVICIOS", role="Rows")),
            ]},
            {"page_name": "h3", "page_display_name": "Detalle ocupacion", "filters": {}, "visuals": [
                _visual("h_tabla", "tableEx",
                        _field("PACIENTES X ASEGURADORA", "TERNOMCOM", "ASEGURADORA"),
                        _field("PACIENTES X ASEGURADORA", "HSUNOMBRE", "SERVICIO")),
                # Dona sin renombrar: HSUNOMBRE hereda «SERVICIO» de la tabla.
                _visual("h_dona", "donutChart",
                        _field("PACIENTES X ASEGURADORA", "HSUNOMBRE", role="Category")),
            ]},
        ]},
        {"report": "Tablero Atenciones", "semantic_model": ATEN, "source_group": "aten", "pages": [
            {"page_name": "a1", "page_display_name": "Consultas prioritarias", "filters": {}, "visuals": [
                _visual("a_aseg", "slicer", _field("EGRESOS_POR_SERVICIO", "TERNOMCOM", "ASEGURADOR")),
                _visual("a_fecha", "slicer", _field("Calendario", "Date")),
            ]},
        ]},
        {"report": "Tablero Ventas", "semantic_model": VENT, "source_group": "vent", "pages": [
            {"page_name": "v1", "page_display_name": "Ventas", "filters": {}, "visuals": [
                _visual("v_sede", "slicer", _field("OTRA", "SEDE")),
                _visual("v_zona", "slicer", _field("OTRA", "ZONA")),
            ]},
        ]},
    ]}
    ocupacion = _metric("m_ocup", HOSP, "Tablero Hospital", "%OCUPACION", "CAMAS DISPONIBLES",
                        pages=["Inicio", "Gestion camas"])
    ocupacion["dax_expression"] = (
        "DIVIDE(SUM('CAMAS DISPONIBLES'[OCUPADAS]), DISTINCTCOUNT('CAMAS DISPONIBLES'[HCACODIGO]))"
    )
    pacientes = _metric("m_pac", HOSP, "Tablero Hospital", "TOTAL PACIENTES", "PACIENTES X ASEGURADORA",
                        pages=["Detalle ocupacion"])
    pacientes["dax_expression"] = "DISTINCTCOUNT('PACIENTES X ASEGURADORA'[ADNINGRESO])"
    observados = _metric("m_obs", ATEN, "Tablero Atenciones", "PACIENTES OBSERVADOS",
                         "CONSULTAS PRIORITARIAS", pages=["Consultas prioritarias"])
    observados["dax_expression"] = "COUNT('CONSULTAS PRIORITARIAS'[ASEGURADOR])"
    ventas = _metric("m_ventas", VENT, "Tablero Ventas", "VALOR VENTAS", "VENTAS", pages=["Ventas"])
    ventas["dax_expression"] = "SUM('VENTAS'[VALOR])"
    files = {
        catalog / "source_registry.json": registry,
        rag / "visual_metrics_catalog.json": visuals_catalog,
        rag / "master_metrics.json": {"metrics": [ocupacion, pacientes, observados, ventas]},
        **{catalog / f"{key}_rag.json": value for key, value in technical.items()},
    }
    for path, data in files.items():
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


class FakeProvider:
    def execute_dax(self, dax, semantic_model=None):
        return {"status": "success", "rows": []}


_STATE = {}


def builder():
    if "builder" not in _STATE:
        tmp = tempfile.TemporaryDirectory()
        _STATE["tmp"] = tmp
        root = Path(tmp.name)
        _build_fixture(root)
        router = SourceModelRouter(
            root / "data" / "catalog" / "source_registry.json",
            root / "data" / "rag" / "visual_metrics_catalog.json", project_root=root,
        )
        _STATE["builder"] = QueryPlanBuilder(
            root / "data" / "rag" / "master_metrics.json",
            root / "data" / "rag" / "visual_metrics_catalog.json",
            router, FakeProvider(), project_root=root, today=TODAY,
        )
    return _STATE["builder"]


def metric(metric_id):
    return next(m for m in builder().metrics if m["metric_id"] == metric_id)


def grouped(plan):
    return [(g["table"], g["column"]) for g in plan.get("group_by") or []]


def describe(plan):
    return (plan.get("status"), plan.get("reason"), (plan.get("metric") or {}).get("metric_id"),
            grouped(plan), plan.get("filters"), plan.get("notes"))


# ---------------------------------------------------------------- 1) regla de relación
def test_relation_rule():
    b = builder()
    field = {"aliases": []}
    ocup, obs, ventas = metric("m_ocup"), metric("m_obs"), metric("m_ventas")
    assert b._dimension_relation(ocup, {**field, "table": "CAMAS DISPONIBLES", "column": "SERVICIOS"}) == "own"
    # Relaciones declaradas (vacías): otra tabla no filtra CAMAS DISPONIBLES.
    assert b._dimension_relation(ocup, {**field, "table": "ATENCIONES_SERVICIO", "column": "FECHA"}) == "unrelated"
    # Relación activa CONSULTAS PRIORITARIAS -> Calendario.
    assert b._dimension_relation(obs, {**field, "table": "Calendario", "column": "Date"}) == "related"
    assert b._dimension_relation(obs, {**field, "table": "EGRESOS_POR_SERVICIO", "column": "TERNOMCOM"}) \
        == "unrelated"
    # Sin relaciones declaradas: solo se descarta si VENTAS tiene su propia SEDE.
    assert b._dimension_relation(ventas, {"table": "OTRA", "column": "SEDE", "aliases": ["SEDE"]}) == "unrelated"
    assert b._dimension_relation(ventas, {"table": "OTRA", "column": "ZONA", "aliases": ["ZONA"]}) == "unknown"
    # El filtro implícito usa la misma regla.
    assert not b._field_filters_metric(ocup, {"table": "ATENCIONES_SERVICIO", "column": "FECHA"})


def test_candidates_drop_unrelated_tables_and_add_own_columns():
    b = builder()
    dropped = []
    fields = b._metric_dimensions(metric("m_obs"), dropped)
    keys = {(f["table"], f["column"]) for f in fields}
    assert ("CONSULTAS PRIORITARIAS", "ASEGURADOR") in keys, keys
    assert ("EGRESOS_POR_SERVICIO", "TERNOMCOM") not in keys, keys
    assert ("EGRESOS_POR_SERVICIO", "TERNOMCOM") in {(f["table"], f["column"]) for f in dropped}
    own = next(f for f in fields if f["column"] == "ASEGURADOR")
    assert own.get("own_fallback") and "aseguradora" in [a.lower() for a in own["aliases"]], own
    # Ya hay una fecha relacionada (Calendario): la FECHA propia no se agrega como respaldo.
    assert ("CONSULTAS PRIORITARIAS", "FECHA") not in keys, keys


# ---------------------------------------------------------------- 2) «por X»
def test_alias_prefix_accepts_plural_and_gender():
    assert _alias_prefix("aseguradores", "ASEGURADORA") == "aseguradores"
    assert _alias_prefix("aseguradores de sura", "asegurador") == "aseguradores"
    assert _alias_prefix("servicios", "SERVICIO") == "servicios"
    assert _alias_prefix("sedes", "SEXO") is None
    assert _alias_prefix("tipo", "tipo de atencion") is None


def test_group_by_uses_the_metric_own_column():
    plan = builder().build("cuantos pacientes observados hay por aseguradora")
    assert plan["status"] == "ready", describe(plan)
    assert grouped(plan) == [("CONSULTAS PRIORITARIAS", "ASEGURADOR")], describe(plan)


def test_group_by_plural_and_business_name():
    plan = builder().build("total pacientes por aseguradores")
    assert plan["status"] == "ready", describe(plan)
    assert grouped(plan) == [("PACIENTES X ASEGURADORA", "TERNOMCOM")], describe(plan)
    b = builder()
    dona = next(f for f in b.dimension_fields if f["visual_id"] == "h_dona")
    assert "servicio" in [a.lower() for a in dona["aliases"]], dona["aliases"]
    assert b._column_business_names(HOSP, "TERNOMCOM") == ["ASEGURADORA"]


def test_business_names_of_technical_codes_and_group_label():
    b = builder()
    # Un código técnico que este modelo no renombra toma los nombres de otros modelos.
    assert sorted(b._column_business_names(VENT, "TERNOMCOM")) == ["ASEGURADOR", "ASEGURADORA"]
    # FECHA/SEDE no son códigos técnicos: no heredan nombres de otras tablas.
    assert not b._technical_code_column("FECHA") and not b._technical_code_column("SERVICIO")
    field = {"semantic_model": HOSP, "table": "PACIENTES X ASEGURADORA", "column": "TERNOMCOM",
             "aliases": ["TERNOMCOM"]}
    assert b._group_label(field) == "ASEGURADORA"
    # «por areas de servicio»: la coincidencia más larga (AREA DE SERVICIO entero).
    assert _alias_prefix("areas de servicio", "AREA DE SERVICIO") == "areas de servicio"


def test_unrelated_dimension_is_never_grouped_silently():
    # Sin relaciones declaradas, OTRA[SEDE] no se usa: VENTAS tiene su propia SEDE.
    plan = builder().build("valor ventas por sede")
    assert plan["status"] == "ready", describe(plan)
    assert grouped(plan) == [("VENTAS", "SEDE")], describe(plan)
    # Sin columna equivalente propia (sin relaciones declaradas) se conserva.
    plan = builder().build("valor ventas por zona")
    assert grouped(plan) == [("OTRA", "ZONA")], describe(plan)


# ---------------------------------------------------------------- 3) «hoy» en una tabla de estado actual
def test_today_on_a_snapshot_table_answers_the_current_state():
    plan = builder().build("%ocupacion por servicio hoy")
    assert plan["status"] == "ready", describe(plan)
    assert grouped(plan) == [("CAMAS DISPONIBLES", "SERVICIOS")], describe(plan)
    assert not [f for f in plan["filters"] if f.get("table") == "ATENCIONES_SERVICIO"], plan["filters"]
    assert any("estado actual" in note for note in plan["notes"]), plan["notes"]
    assert not any("no tiene una fecha" in note for note in plan["notes"]), plan["notes"]
    # Otro periodo (un año) en esa tabla sigue sin poder aplicarse.
    plan = builder().build("%ocupacion en 2024")
    assert plan["status"] == "unsupported_filter", describe(plan)


# ---------------------------------------------------------------- 4) indicador hermano
def test_detail_by_a_dimension_the_metric_lacks_uses_the_sibling():
    plan = builder().build("necesito el detalle de ocupacion por aseguradores")
    assert plan["status"] == "ready", describe(plan)
    assert plan["metric"]["metric_id"] == "m_pac", describe(plan)
    assert grouped(plan) == [("PACIENTES X ASEGURADORA", "TERNOMCOM")], describe(plan)
    note = " ".join(plan["notes"])
    assert "%OCUPACION no se puede desglosar" in note and "Detalle ocupacion" in note, note
    assert not plan["unapplied_terms"], plan["unapplied_terms"]


def test_selected_metric_without_the_dimension_uses_the_sibling():
    plan = builder().build("necesito el detalle de ocupacion por aseguradores", selected_metric_id="m_ocup")
    assert plan["status"] == "ready", describe(plan)
    assert plan["metric"]["metric_id"] == "m_pac", describe(plan)
    assert grouped(plan) == [("PACIENTES X ASEGURADORA", "TERNOMCOM")], describe(plan)
    assert any("no se puede desglosar" in note for note in plan["notes"]), plan["notes"]


def test_without_sibling_the_dimension_is_declared():
    # VALOR VENTAS no tiene aseguradora ni hay otro indicador de ventas que la tenga.
    plan = builder().build("valor ventas por aseguradora")
    assert plan["status"] == "unsupported_filter", describe(plan)
    assert "no se puede desglosar por aseguradora" in plan["explanation"], plan.get("explanation")


# ---------------------------------------------------------------- Runner mínimo
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
