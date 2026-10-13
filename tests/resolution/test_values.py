"""
Valores de filtro en QueryPlanBuilder (offline).

1) Un filtro nunca elige un valor que contradice la palabra distintiva de la
   pregunta: «triages de menores de edad» con {MENORES DE EDAD, MAYORES DE
   EDAD} nunca aplica MAYORES DE EDAD (la parte compartida «de edad» no
   cuenta); «remisiones no aceptadas» aplica NO ACEPTADO; «triages» no elige
   un nivel de {TRIAGE I..V}. Se revisan los caminos que eligen valores:
   filtro explícito (`_resolve_value`), valor implícito
   (`_resolve_implicit_filter`), calificativo aproximado
   (`_fuzzy_qualifier_filters`) y el seguimiento (`selected_metric_id`).
2) «peso por servicio en lavandería»: lo que sigue a «por <dimensión>» es el
   tablero, no un valor de SERVICIO.
3) Calificativos: «aumento de precio» (la documentación del indicador habla
   de precios), «uci» (familia UCI ADULTOS/UCI NEONATAL: se suman), «sin
   responder» = «sin respuesta», frase nominal + valor -> Power BI, y un valor
   de una tabla que no filtra al indicador no se aplica.
4) Farmacia: «suministros pendientes» = NÚMERO DE SUMINISTROS PENDIENTES y las
   opciones de «medicamentos vencidos» no incluyen indicadores sin la palabra
   distintiva.

Ejecutar:  python -m tests.resolution.test_values      (o pytest tests/resolution)
"""
import json
import sys
import tempfile
import traceback
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.semantic.query_plan_builder import QueryPlanBuilder, value_contradiction  # noqa: E402
from src.semantic.source_model_router import SourceModelRouter  # noqa: E402
from tests.resolution.test_resolution import _column, _metric, _source  # noqa: E402
from tests.resolution.test_resolution import builder as resolution_builder  # noqa: E402

MODEL, REPORT = "Modelo Urgencias", "Tablero Urgencias"
FARM, FARM_REPORT = "Modelo Farmacia", "Tablero Farmacia"
CVC, CVC_REPORT = "Modelo CVC", "Tablero CVC"
EDAD = ["MAYORES DE EDAD", "MENORES DE EDAD"]
ESTADOS = ["ACEPTADO", "NO ACEPTADO"]
NIVELES = ["TRIAGE I", "TRIAGE II", "TRIAGE III", "TRIAGE IV", "TRIAGE V"]
DOMAINS = {
    (MODEL, "OPORTUNIDAD_TRIAGE", "MENORES"): EDAD,
    (MODEL, "OPORTUNIDAD_TRIAGE", "CLASIFICACION"): NIVELES,
    (MODEL, "REMISIONES", "ESTADO"): ESTADOS,
    (MODEL, "PACIENTES_ATB", "TRATAMIENTO"): ["CON ANTIBIOTICO", "SIN ANTIBIOTICO"],
    (MODEL, "PACIENTES_ATB", "SERVICIO"): ["UCI ADULTOS", "UCI NEONATAL", "URGENCIAS"],
    (MODEL, "INTERCONSULTAS", "ESPECIALIDAD"): ["PEDIATRIA", "CIRUGIA GENERAL"],
    (MODEL, "DETALLE RECEPCION", "SERVICIO"): ["HOSPITALIZACION", "PEDIATRIA"],
    (CVC, "COSTOS", "ESTADO"): ["AUMENTO", "DISMINUYO", "IGUAL"],
}


def _slicer(visual_id, table, column):
    return {"visual_id": visual_id, "visual_type": "slicer", "fields": [_column(table, column)]}


def _build_fixture(root):
    catalog = root / "data" / "catalog"
    rag = root / "data" / "rag"
    docs = root / "data" / "semantic_documents" / "cvc"
    for folder in (catalog, rag, docs):
        folder.mkdir(parents=True)
    sources = [
        _source("urg", REPORT, MODEL, ["tablero urgencias"]),
        _source("farm", FARM_REPORT, FARM, ["tablero farmacia", "farmacia"]),
        _source("cvc", CVC_REPORT, CVC, ["tablero cvc", "cvc"]),
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
        # El modelo de urgencias declara sus relaciones (ninguna): sus tablas
        # no se filtran entre sí, como BRIEFING HOSPITALARIO.
        "urg": {"semantic_model": MODEL, "relationships": [], "tables": [
            {"name": "OPORTUNIDAD_TRIAGE", "columns": [
                {"name": "MENORES", "data_type": "String"}, {"name": "CLASIFICACION", "data_type": "String"}]},
            {"name": "REMISIONES", "columns": [{"name": "ESTADO", "data_type": "String"}]},
            {"name": "PACIENTES_ATB", "columns": [
                {"name": "TRATAMIENTO", "data_type": "String"}, {"name": "SERVICIO", "data_type": "String"}]},
            {"name": "INTERCONSULTAS", "columns": [{"name": "ESPECIALIDAD", "data_type": "String"}]},
            {"name": "DETALLE RECEPCION", "columns": [{"name": "SERVICIO", "data_type": "String"}]},
        ]},
        "farm": {"semantic_model": FARM, "tables": [
            {"name": "PENDIENTES_FARMACIA", "columns": []},
            {"name": "PRODUCTOS_VENCIDOS", "columns": []},
            {"name": "VENCIMIENTO_PRODUCTOS", "columns": []},
        ]},
        "cvc": {"semantic_model": CVC, "tables": [
            {"name": "COSTOS", "columns": [{"name": "ESTADO", "data_type": "String"}]}]},
    }
    visuals_catalog = {"schema_version": 2, "reports": [
        {"report": REPORT, "semantic_model": MODEL, "source_group": "urg", "pages": [
            {"page_name": "p1", "page_display_name": "Inicio", "filters": {}, "visuals": [
                _slicer("v_menores", "OPORTUNIDAD_TRIAGE", "MENORES"),
                _slicer("v_clasif", "OPORTUNIDAD_TRIAGE", "CLASIFICACION"),
                _slicer("v_estado", "REMISIONES", "ESTADO"),
                _slicer("v_trat", "PACIENTES_ATB", "TRATAMIENTO"),
                _slicer("v_serv", "PACIENTES_ATB", "SERVICIO"),
            ]},
            {"page_name": "p2", "page_display_name": "Interconsultas", "filters": {}, "visuals": [
                _slicer("v_esp", "INTERCONSULTAS", "ESPECIALIDAD"),
            ]},
            {"page_name": "p3", "page_display_name": "Seguimiento recepcion", "filters": {}, "visuals": [
                _slicer("v_recep", "DETALLE RECEPCION", "SERVICIO"),
            ]},
        ]},
        {"report": CVC_REPORT, "semantic_model": CVC, "source_group": "cvc", "pages": [
            {"page_name": "c1", "page_display_name": "CVC", "filters": {}, "visuals": [
                _slicer("c_estado", "COSTOS", "ESTADO"),
            ]}]},
    ]}
    interconsultas = _metric("u_inter", MODEL, REPORT, "INTERCONSULTAS SIN RESPUESTA", "INTERCONSULTAS",
                             pages=["Interconsultas"])
    interconsultas["dax_expression"] = "DISTINCTCOUNT('INTERCONSULTAS'[OID_SOLICITUD])"
    casos = _metric("u_casos", MODEL, REPORT, "CASOS TOTALES", "MEDICAMENTOS DESABASTECIDOS",
                    pages=["Desabastecidos"], aliases=["Sum(MEDICAMENTOS DESABASTECIDOS.OID_SOLICITUD)"])
    metrics = [
        _metric("u_triages", MODEL, REPORT, "TRIAGES", "OPORTUNIDAD_TRIAGE", pages=["Inicio"]),
        _metric("u_remisiones", MODEL, REPORT, "REMISIONES", "REMISIONES", pages=["Inicio"]),
        _metric("u_pacientes", MODEL, REPORT, "PACIENTES", "PACIENTES_ATB", pages=["Inicio"]),
        interconsultas, casos,
        _metric("f_suministros", FARM, FARM_REPORT, "NÚMERO DE SUMINISTROS PENDIENTES", "PENDIENTES_FARMACIA",
                pages=["Inicio"], aliases=["Sum(PENDIENTES_FARMACIA.HCNFOLIO)"]),
        _metric("f_pendientes1", FARM, FARM_REPORT, "PENDIENTES1", "PENDIENTES_FARMACIA", pages=["Inicio"]),
        _metric("f_vencidos", FARM, FARM_REPORT, "PRODUCTOS VENCIDOS", "PRODUCTOS_VENCIDOS",
                pages=["Medicamentos vencidos"]),
        _metric("f_vencimiento", FARM, FARM_REPORT, "MEDICAMENTOS EN VENCIMIENTO 0-30 DÍAS",
                "VENCIMIENTO_PRODUCTOS", pages=["Medicamentos vencidos"]),
        _metric("c_aumento", CVC, CVC_REPORT, "Total de compras con aumento", "COSTOS", pages=["CVC"]),
        _metric("c_disminucion", CVC, CVC_REPORT, "Total de compras con disminucion", "COSTOS", pages=["CVC"]),
    ]
    documentation = {
        "semantic_model": CVC, "dashboards": [{
            "name": "CVC",
            "description": "Monitorea el comportamiento de precios de medicamentos e insumos: "
                           "aumentos o disminuciones de precios en las compras.",
            "visuals": ["Tarjetas: total de compras con aumento y con disminución."],
        }],
    }
    files = {
        catalog / "source_registry.json": registry,
        rag / "visual_metrics_catalog.json": visuals_catalog,
        rag / "master_metrics.json": {"metrics": metrics},
        docs / "Documentacion CVC.json": documentation,
        **{catalog / f"{key}_rag.json": value for key, value in technical.items()},
    }
    for path, data in files.items():
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


class FakeProvider:
    def execute_dax(self, dax, semantic_model=None):
        compact = dax.replace("\n", "").replace(" ", "")
        for (model, table, column), values in DOMAINS.items():
            reference = f"VALUES('{table}'[{column}])".replace(" ", "")
            if model == semantic_model and reference in compact:
                return {"status": "success", "rows": [{"[Value]": value} for value in values]}
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
            router, FakeProvider(), project_root=root,
        )
    return _STATE["builder"]


def values_of(plan):
    result = {}
    for item in plan.get("filters", []):
        if item.get("type") != "categorical" or item.get("temporal"):
            continue
        value = item["value"] if item.get("value") is not None else tuple(item.get("values") or ())
        result[item["column"]] = value if isinstance(value, tuple) else str(value)
    return result


def option_ids(plan):
    resolution = plan.get("metric_resolution") or {}
    items = resolution.get("candidates") or resolution.get("suggestions") or []
    return [item["metric"]["metric_id"] for item in items]


# ---------------------------------------------------------------- 1) función pura
def test_shared_words_do_not_choose_the_opposite_age_group():
    assert value_contradiction("menores de edad", "MAYORES DE EDAD", EDAD)
    assert value_contradiction("menores edad", "MENORES DE EDAD", EDAD) is None
    assert value_contradiction("mayores de edad", "MENORES DE EDAD", EDAD)
    # Solo la parte compartida: ninguno de los dos.
    assert value_contradiction("edad", "MAYORES DE EDAD", EDAD)
    assert value_contradiction("edad", "MENORES DE EDAD", EDAD)


def test_negation_distinguishes_accepted_from_not_accepted():
    assert value_contradiction("remisiones no aceptadas", "ACEPTADO", ESTADOS)
    assert value_contradiction("remisiones no aceptadas", "NO ACEPTADO", ESTADOS) is None
    assert value_contradiction("remisiones aceptadas", "NO ACEPTADO", ESTADOS)
    assert value_contradiction("remisiones aceptadas", "ACEPTADO", ESTADOS) is None
    # «no» lejos del valor no lo niega.
    assert value_contradiction("no se cuantas remisiones aceptadas hubo", "ACEPTADO", ESTADOS) is None


def test_with_and_without():
    domain = ["CON ANTIBIOTICO", "SIN ANTIBIOTICO"]
    assert value_contradiction("pacientes con antibiotico", "SIN ANTIBIOTICO", domain)
    assert value_contradiction("pacientes sin antibiotico", "CON ANTIBIOTICO", domain)
    assert value_contradiction("pacientes sin antibiotico", "SIN ANTIBIOTICO", domain) is None


def test_triage_levels_need_their_own_level():
    assert value_contradiction("triages", "TRIAGE III", NIVELES)
    assert value_contradiction("triage iii", "TRIAGE III", NIVELES) is None
    assert value_contradiction("triage 3", "TRIAGE III", NIVELES) is None
    assert value_contradiction("triage 3", "TRIAGE II", NIVELES)


def test_more_specific_sibling_wins():
    domain = ["URGENCIAS", "URGENCIAS PEDIATRICAS", "HOSPITALIZACION"]
    assert value_contradiction("urgencias pediatricas", "URGENCIAS", domain)
    assert value_contradiction("urgencias pediatricas", "URGENCIAS PEDIATRICAS", domain) is None
    assert value_contradiction("urgencias", "URGENCIAS", domain) is None
    for pair in (("entradas", "SALIDA", ["ENTRADA", "SALIDA"]),
                 ("positivos", "NEGATIVO", ["POSITIVO", "NEGATIVO"]),
                 ("activos", "INACTIVO", ["ACTIVO", "INACTIVO"]),
                 ("no atendidos", "ATENDIDO", ["ATENDIDO", "NO ATENDIDO"])):
        assert value_contradiction(*pair), pair


# ---------------------------------------------------------------- 1) caminos del planificador
def test_explicit_column_name_does_not_pick_the_opposite_value():
    # La columna se llama MENORES: «menores» se toma como columna y «edad»
    # como valor; MAYORES DE EDAD puntúa igual pero contradice la pregunta.
    plan = builder().build("triages de menores de edad en el tablero urgencias")
    assert plan["status"] == "ready", plan["status"]
    assert values_of(plan).get("MENORES") == "MENORES DE EDAD", values_of(plan)
    assert any("no se eligió" in note and "MAYORES DE EDAD" in note for note in plan["resolution_notes"])
    plan = builder().build("triages de mayores de edad en el tablero urgencias")
    assert values_of(plan).get("MENORES") == "MAYORES DE EDAD", values_of(plan)


def test_implicit_value_keeps_the_polarity():
    plan = builder().build("cuantas remisiones no aceptadas hay")
    assert values_of(plan).get("ESTADO") == "NO ACEPTADO", (plan["status"], values_of(plan))
    plan = builder().build("cuantas remisiones aceptadas hay")
    assert values_of(plan).get("ESTADO") == "ACEPTADO", (plan["status"], values_of(plan))


def test_with_without_filter():
    plan = builder().build("cuantos pacientes sin antibiotico hay")
    assert values_of(plan).get("TRATAMIENTO") == "SIN ANTIBIOTICO", (plan["status"], values_of(plan))
    plan = builder().build("cuantos pacientes con antibiotico hay")
    assert values_of(plan).get("TRATAMIENTO") == "CON ANTIBIOTICO", (plan["status"], values_of(plan))


def test_generic_word_does_not_pick_a_triage_level():
    plan = builder().build("cuantos triages hay")
    assert "CLASIFICACION" not in values_of(plan), values_of(plan)


def test_followup_keeps_the_distinctive_word():
    plan = builder().build("de menores de edad", selected_metric_id="u_triages")
    assert values_of(plan).get("MENORES") == "MENORES DE EDAD", (plan["status"], values_of(plan))
    plan = builder().build("y de mayores de edad", selected_metric_id="u_triages")
    assert values_of(plan).get("MENORES") == "MAYORES DE EDAD", (plan["status"], values_of(plan))


# ---------------------------------------------------------------- 2) «por <dimensión> en <tablero>»
def test_group_followed_by_the_board_name_is_a_grouping():
    b = resolution_builder()
    plan = b.build("peso por servicio en lavanderia")
    assert plan["status"] == "ready", (plan["status"], plan.get("requested_value"))
    assert [g["column"] for g in plan["group_by"]] == ["SERVICIO"], plan["group_by"]
    assert not values_of(plan), values_of(plan)


def test_board_name_as_explicit_value_is_taken_as_the_board():
    plan = resolution_builder().build("peso por servicio de lavanderia")
    assert plan["status"] == "ready", (plan["status"], plan.get("requested_value"))
    assert [g["column"] for g in plan["group_by"]] == ["SERVICIO"], plan["group_by"]


def test_real_value_after_the_dimension_is_still_a_filter():
    plan = resolution_builder().build("peso por servicio de urgencias en lavanderia")
    assert plan["status"] == "ready", plan["status"]
    assert values_of(plan) == {"SERVICIO": "URGENCIAS"}, values_of(plan)
    assert not plan["group_by"]


# ---------------------------------------------------------------- 3) calificativos
def test_word_from_the_metric_documentation_is_explained():
    plan = builder().build("cuantas compras con aumento de precio hay en el cvc")
    assert plan["status"] == "ready", (plan["status"], plan.get("unresolved_text"))
    assert plan["metric"]["metric_id"] == "c_aumento"
    assert not plan["unapplied_terms"], plan["unapplied_terms"]
    assert any("documentación" in note and "precio" in note for note in plan["resolution_notes"])
    # Una palabra que la documentación no usa sigue sin interpretarse.
    plan = builder().build("cuantas compras con aumento de azules hay en el cvc")
    assert plan["status"] != "ready" or plan["unapplied_terms"], plan["status"]


def test_family_of_values_is_summed():
    plan = builder().build("cuantos pacientes hay en la uci")
    assert plan["status"] == "ready", (plan["status"], plan.get("implicit_decisions"))
    assert values_of(plan).get("SERVICIO") == ("UCI ADULTOS", "UCI NEONATAL"), values_of(plan)
    item = next(f for f in plan["filters"] if f.get("column") == "SERVICIO")
    assert item["operator"] == "in" and "se suman todos" in item["reason"], item


def test_without_answer_phrase_and_nominal_question():
    b = builder()
    plan = b.build("interconsultas sin responder de pediatria")
    assert plan["status"] == "ready", plan["status"]
    assert plan["metric"]["metric_id"] == "u_inter"
    assert values_of(plan) == {"ESPECIALIDAD": "PEDIATRIA"}, values_of(plan)
    assert plan["question"] == "interconsultas sin responder de pediatria"
    # Frase nominal (sin verbo): indicador tal cual + valor -> Power BI.
    assert b.looks_numeric("interconsultas sin responder de pediatria")
    # El indicador solo, o el tablero, siguen siendo para la documentación.
    assert not b.looks_numeric("interconsultas sin responder")
    assert not b.looks_numeric("tablero de interconsultas sin respuesta de pediatria")
    assert not b.looks_numeric("que es interconsultas sin respuesta de pediatria")


def test_value_of_an_unrelated_table_is_not_applied():
    # HOSPITALIZACION solo existe en DETALLE RECEPCION, que no filtra INTERCONSULTAS.
    plan = builder().build("cuantas interconsultas sin respuesta de hospitalizacion hay")
    assert "SERVICIO" not in values_of(plan), values_of(plan)
    assert plan["status"] != "ready" or plan["unapplied_terms"], plan["status"]


# ---------------------------------------------------------------- 4) farmacia
def test_count_prefix_is_not_required():
    plan = builder().build("cuantos suministros pendientes hay en farmacia")
    assert plan["status"] == "ready", (plan["status"], option_ids(plan))
    assert plan["metric"]["metric_id"] == "f_suministros", plan["metric"]["label"]


def test_options_share_the_distinctive_word():
    plan = builder().build("cuantos medicamentos vencidos tenemos en farmacia")
    assert plan["status"] != "ready", plan["status"]
    ids = option_ids(plan)
    assert ids[:2] == ["f_vencidos", "f_vencimiento"], ids
    assert "f_suministros" not in ids and "u_casos" not in ids, ids


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
