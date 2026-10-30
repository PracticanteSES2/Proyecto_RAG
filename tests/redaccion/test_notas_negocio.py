"""
Redacción en lenguaje de negocio (sin servicios externos):

- Nota de filtros del tablero: frase corta («Cifra tal como la muestra la
  tarjeta de la página GESTIÓN CAMAS ...») con nombres de negocio del
  diccionario (HSUNOMBRE -> «servicio»), sin nombres de columna ni códigos.
- Unidad de la cifra desde el diccionario («10,5 minutos», «4 días»,
  «1 día»); sin evidencia no se inventa; nunca en porcentajes ni dinero.
- Nota de «valor general»: solo cuando alguna página filtra la cifra.
- El comparador del banco real sigue leyendo la cifra y el enlace
  «Abrir en Power BI» no depende del texto.

Ejecutar:
  PYTHONIOENCODING=utf-8 python -m tests.redaccion.test_notas_negocio
"""
import os
import sys
import tempfile
import traceback
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.chatbot import business_terms as T  # noqa: E402
from src.chatbot.response_formatter import business_notes, format_query_plan_answer  # noqa: E402

DICTIONARY = """---
tablero: BRIEFING HOSPITALARIO
pagina: DICCIONARIO
---

# DICCIONARIO

## Medidas
- **[%OCUPACION]**: Porcentaje de ocupación. Unidad: porcentaje de camas. Tabla: CAMAS DISPONIBLES.
- **[PROMEDIO_DIAS]**: Promedio de días en proceso. Unidad: días. Tabla: PROCESO.
- **[CAMAS_LIBRES]**: Camas libres. Unidad: camas. Tabla: CAMAS DISPONIBLES.
- **[SIN_UNIDAD]**: Medida sin unidad documentada. Tabla: X.
- **[FECHA_MAX]**: Última fecha. Unidad: fecha. Tabla: X.

## Columnas
- **SERVICIOS[HSUNOMBRE]**: Filtro de página por SERVICIOS[HSUNOMBRE]: ATENCION DOMICILIARIA. Tipo: texto.
- **SERV[HSUNOMBRE]**: Nombre del servicio; da el eje del gráfico. Tipo: texto.
- **GESTION[HSUNOMBRE]**: Servicio de la cama. Tipo: texto.
- **CAMAS DISPONIBLES[MOSTRAR_6TO]**: Marca de visibilidad del sexto piso; un valor 0 oculta la cama. Tipo: entero.
- **CAMAS DISPONIBLES[HCACODIGO]**: Código de la cama. Tipo: texto.
- **INTERCONSULTAS[OID_RESPUESTA]**: Identificador de la respuesta a la interconsulta; vacío si no se responde.
- **TRIAGES_DIA[TIEMPO]**: Minutos entre la llegada del paciente y el triage. Tipo: entero.
- **TRIAGES_DIA[CODIGO]**: Código del triage. Tipo: entero.
"""

_TMP = tempfile.TemporaryDirectory()
DOCS = Path(_TMP.name)
(DOCS / "tablero_briefing_hospitalario" / "md").mkdir(parents=True)
(DOCS / "tablero_briefing_hospitalario" / "md" / "_diccionario.md").write_text(DICTIONARY, encoding="utf-8")
os.environ["DOCS_MD_ROOT"] = str(DOCS)   # los textos de format_query_plan_answer usan este diccionario

SERVICES = [None, "ATENCION DOMICILIARIA", "BLOQUEAR", "BLOQUEAR - NEONATAL", "QUIROFANO"]
OCUPACION = {
    "label": "%OCUPACION", "measure": "%OCUPACION", "semantic_model": "BRIEFING HOSPITALARIO",
    "table": "CAMAS DISPONIBLES", "source_type": "explicit_measure",
    "board_filters_source": {"page": "GESTIÓN CAMAS", "visual_type": "card", "report": "BRIEFING HOSPITALARIO"},
    "visual_filters": [
        {"table": "SERVICIOS", "column": "HSUNOMBRE", "scope": "page",
         "condition": {"op": "not", "arg": {"op": "in", "values": SERVICES}},
         "text": "HSUNOMBRE no es (en blanco), ATENCION DOMICILIARIA, BLOQUEAR, BLOQUEAR - NEONATAL (y 1 más)"},
        {"table": "CAMAS DISPONIBLES", "column": "MOSTRAR_6TO", "scope": "page",
         "condition": {"op": "not", "arg": {"op": "in", "values": [0]}}, "text": "MOSTRAR_6TO no es 0"},
        {"table": "CAMAS DISPONIBLES", "column": "HCACODIGO", "scope": "page",
         "condition": {"op": "not", "arg": {"op": "contains", "value": "321"}},
         "text": "no (HCACODIGO contiene «321»)"},
    ],
}
TECHNICAL_NOTE = ("Filtros del tablero aplicados (tarjeta de la página GESTIÓN CAMAS): HSUNOMBRE no es (en blanco), "
                  "ATENCION DOMICILIARIA, BLOQUEAR, BLOQUEAR - NEONATAL (y 1 más); MOSTRAR_6TO no es 0; "
                  "no (HCACODIGO contiene «321»).")


def _scalar(metric, value, notes=(), **extra):
    plan = {"metric": metric, "filters": [], "group_by": [], "notes": list(notes)}
    return {"status": "success", "route": "powerbi", "result_type": "scalar", "metric": metric["label"],
            "value": value, "query_plan": plan, "filters": [], "metric_format": None, **extra}


# ---------------- nombres de negocio ----------------
def test_business_name_of_columns():
    entries = T.dictionary_for(OCUPACION, DOCS)
    assert entries, "no se cargó el diccionario de prueba"
    # La entrada de SERVICIOS no da nombre corto: se usa el más corto de otras tablas.
    assert T.column_business_name(entries, "SERVICIOS", "HSUNOMBRE") == "servicio"
    assert T.column_business_name(entries, "GESTION", "HSUNOMBRE") == "servicio de la cama"
    assert T.column_business_name(entries, "CAMAS DISPONIBLES", "HCACODIGO") == "cama"
    assert T.column_business_name(entries, "INTERCONSULTAS", "OID_RESPUESTA") == "respuesta a la interconsulta"
    assert T.column_business_name(entries, "X", "NO_EXISTE") is None


def test_dictionary_found_by_model_report_or_group():
    for metric in ({"semantic_model": "Briefing Hospitalario"}, {"report": "BRIEFING HOSPITALARIO"},
                   {"source_group": "tablero_briefing_hospitalario"}):
        assert T.dictionary_for(metric, DOCS), metric
    assert T.dictionary_for({"semantic_model": "OTRO"}, DOCS) == {}


# ---------------- nota de filtros del tablero ----------------
def test_board_filters_sentence_is_short_and_in_business_words():
    text = T.board_filters_sentence(OCUPACION, DOCS)
    assert text == ("Cifra tal como la muestra la tarjeta de la página GESTIÓN CAMAS del tablero BRIEFING "
                    "HOSPITALARIO (con sus 3 filtros; p. ej., excluye servicio ATENCION DOMICILIARIA, "
                    "BLOQUEAR y 2 más)."), text
    for technical in ("HSUNOMBRE", "MOSTRAR_6TO", "HCACODIGO", "(en blanco)", "contiene", "no es"):
        assert technical not in text, (technical, text)


def test_board_filters_sentence_single_filter_and_chart():
    metric = {
        "label": "INTERCONSULTAS SIN RESPUESTA", "semantic_model": "BRIEFING HOSPITALARIO",
        "board_filters_source": {"page": "INTERCONSULTAS", "visual_type": "clusteredBarChart",
                                 "report": "BRIEFING HOSPITALARIO"},
        "visual_filters": [{"table": "INTERCONSULTAS", "column": "OID_RESPUESTA",
                            "condition": {"op": "cmp", "cmp": "=", "value": None}, "text": "OID_RESPUESTA en blanco"}],
    }
    text = T.board_filters_sentence(metric, DOCS)
    assert text == ("Cifra tal como la muestra el gráfico de la página INTERCONSULTAS del tablero BRIEFING "
                    "HOSPITALARIO (con su filtro: sin respuesta a la interconsulta)."), text
    # Un filtro por código numérico no se traduce: solo se dice que hay filtro.
    metric["visual_filters"] = [{"table": "TRIAGES_DIA", "column": "CODIGO",
                                 "condition": {"op": "in", "values": [2]}, "text": "CODIGO es 2"}]
    text = T.board_filters_sentence(metric, DOCS)
    assert text.endswith("(con su filtro)."), text
    assert "CODIGO" not in text and " 2" not in text, text


def test_answer_replaces_technical_note_and_keeps_number():
    answer = format_query_plan_answer(_scalar(OCUPACION, 0.8803, [TECHNICAL_NOTE]))
    assert "**88,03 %**" in answer, answer
    assert "Filtros del tablero aplicados" not in answer and "HSUNOMBRE" not in answer, answer
    assert "Cifra tal como la muestra la tarjeta de la página GESTIÓN CAMAS" in answer, answer
    # Sin datos para traducir (sin visual_filters) se conserva la nota original.
    assert business_notes([TECHNICAL_NOTE], {"metric": {}}) == [TECHNICAL_NOTE]


def test_replaced_filter_and_current_state_notes():
    notes = business_notes(
        ["Filtro del tablero reemplazado por el de la pregunta: HSUNOMBRE.",
         "«hoy»: se muestra el estado actual de TRIAGES_DIA (el tablero no usa ninguna de sus fechas como periodo)."],
        {"metric": OCUPACION},
    )
    assert notes == [
        "Para servicio se usa lo que pediste en lugar del filtro que trae la página.",
        "«hoy»: es la cifra actual que muestra el tablero.",
    ], notes


# ---------------- unidades ----------------
TRIAGE = {"label": "TIEMPO PROMEDIO PARA TRIAGE", "semantic_model": "BRIEFING HOSPITALARIO",
          "table": "TRIAGES_DIA", "column": "TIEMPO", "aggregation": "Average", "source_type": "visual_aggregation"}


def test_unit_from_dictionary():
    assert T.metric_unit(TRIAGE, DOCS) == "minutos"   # «Minutos entre...» de la columna promediada
    assert T.metric_unit({**TRIAGE, "aggregation": "DistinctCount"}, DOCS) is None  # un conteo no es minutos
    base = {"semantic_model": "BRIEFING HOSPITALARIO"}
    assert T.metric_unit({**base, "measure": "PROMEDIO_DIAS"}, DOCS) == "días"
    assert T.metric_unit({**base, "measure": "CAMAS_LIBRES"}, DOCS) == "camas"
    assert T.metric_unit({**base, "measure": "%OCUPACION"}, DOCS) is None      # el % ya lo dice
    assert T.metric_unit({**base, "measure": "SIN_UNIDAD"}, DOCS) is None      # sin evidencia, nada
    assert T.metric_unit({**base, "measure": "FECHA_MAX"}, DOCS) is None
    assert T.metric_unit({"semantic_model": "OTRO", "measure": "PROMEDIO_DIAS"}, DOCS) is None


def test_answer_shows_unit():
    answer = format_query_plan_answer(_scalar(TRIAGE, 10.4932))
    assert answer == "**TIEMPO PROMEDIO PARA TRIAGE**: **10,5 minutos**", answer
    days = {"label": "PROMEDIO_DIAS_PROCESO", "measure": "PROMEDIO_DIAS", "semantic_model": "BRIEFING HOSPITALARIO"}
    assert format_query_plan_answer(_scalar(days, 4)) == "**PROMEDIO_DIAS_PROCESO**: **4 días**"
    assert format_query_plan_answer(_scalar(days, 1.01)) == "**PROMEDIO_DIAS_PROCESO**: **1 día**"
    beds = {"label": "LIBRES", "measure": "CAMAS_LIBRES", "semantic_model": "BRIEFING HOSPITALARIO"}
    assert format_query_plan_answer(_scalar(beds, 41)) == "**LIBRES**: **41 camas**"
    # El nombre ya dice lo contado: no se repite.
    beds_named = {**beds, "label": "CAMAS LIBRES"}
    assert format_query_plan_answer(_scalar(beds_named, 41)) == "**CAMAS LIBRES**: **41**"
    # Sin evidencia: la cifra tal cual.
    none = {"label": "OTRO", "measure": "SIN_UNIDAD", "semantic_model": "BRIEFING HOSPITALARIO"}
    assert format_query_plan_answer(_scalar(none, 10.49)) == "**OTRO**: **10,49**"
    # Porcentaje y dinero no llevan unidad del diccionario.
    pct = format_query_plan_answer(_scalar(OCUPACION, 0.5))
    assert pct.startswith("**%OCUPACION**: **50 %**"), pct


def test_comparator_still_reads_numbers():
    from tests.real import run_banco

    answer = format_query_plan_answer(_scalar(TRIAGE, 10.49))
    assert run_banco.number_matches(run_banco.numbers_in(answer), 10.49, {"tolerancia": 0}), answer
    answer = format_query_plan_answer(_scalar(TRIAGE, 3.26))
    assert run_banco.number_matches(run_banco.numbers_in(answer), 3.26, {"tolerancia": 0}), answer
    answer = format_query_plan_answer(_scalar(OCUPACION, 0.8803, [TECHNICAL_NOTE]))
    assert run_banco.number_matches(run_banco.numbers_in(answer), 0.8803,
                                    {"tolerancia": 0.01, "porcentaje": True}), answer


def test_powerbi_link_does_not_depend_on_text():
    from src.providers.powerbi_links import enlace_para_resultado

    links = {"models": {"BRIEFING HOSPITALARIO": {"semantic_model": "BRIEFING HOSPITALARIO", "reports": [{
        "name": "BRIEFING HOSPITALARIO", "url": "https://app.powerbi.com/r",
        "pages": [{"name": "s1", "display_name": "GESTIÓN CAMAS", "url": "https://app.powerbi.com/r/s1"}],
    }]}}}
    result = _scalar(OCUPACION, 0.8803, [TECHNICAL_NOTE], semantic_model="BRIEFING HOSPITALARIO",
                     dashboard="GESTIÓN CAMAS")
    before = enlace_para_resultado(result, links=links)
    format_query_plan_answer(result)
    assert result["query_plan"]["notes"] == [TECHNICAL_NOTE]   # el formato no cambia el resultado
    assert enlace_para_resultado(result, links=links) == before
    assert before and before["nivel"] == "pagina", before


# ---------------- nota de «valor general» ----------------
class _Builder:
    def __init__(self, metrics, filtered_ids):
        self.metrics = metrics
        self.filtered_ids = set(filtered_ids)

    @staticmethod
    def _logical_key(metric):
        return ("m", "t", "expr")

    def _choose_board_filters(self, metric):
        if metric["metric_id"] in self.filtered_ids:
            return [("T", "C", {"op": "in", "values": ["X"]}, "page")], {}
        return [], {}


def _engine(builder):
    from src.chatbot.query_engine import QueryEngine

    engine = QueryEngine.__new__(QueryEngine)
    engine.query_plan_builder = builder
    engine.reasoning = []
    engine._think = lambda *args, **kwargs: None
    return engine


def _metric(mid, page):
    return {"metric_id": mid, "label": "TIEMPO PROMEDIO PARA TRIAGE", "validation_status": "approved",
            "appearances": [{"page_display_name": page, "report": "TABLERO TIEMPOS URGENCIAS"}]}


def test_general_value_note_omitted_when_no_page_filters():
    metrics = [_metric("a", "RESUMEN_D"), _metric("b", "RESUMEN DIA")]
    plan = {"metric": dict(metrics[0]), "notes": [], "filters": [], "group_by": []}
    _engine(_Builder(metrics, []))._note_same_measure_pages(plan)
    assert plan["notes"] == [], plan["notes"]


def test_general_value_note_brief_when_some_page_filters():
    metrics = [_metric("a", "RESUMEN_D"), _metric("b", "RESUMEN DIA")]
    plan = {"metric": dict(metrics[0]), "notes": [], "filters": [], "group_by": []}
    _engine(_Builder(metrics, ["b"]))._note_same_measure_pages(plan)
    assert plan["notes"] == [
        "Es el valor general; en la página RESUMEN DIA del TABLERO TIEMPOS URGENCIAS se ve con filtros "
        "propios y puede ser distinto."
    ], plan["notes"]
    plan = {"metric": dict(metrics[0]), "notes": [], "filters": [], "group_by": []}
    _engine(_Builder(metrics, ["a", "b"]))._note_same_measure_pages(plan)
    assert plan["notes"] == [
        "Es el valor general, sin los filtros de cada página del TABLERO TIEMPOS URGENCIAS "
        "(RESUMEN_D, RESUMEN DIA), donde puede verse distinto."
    ], plan["notes"]


# ---------------- diccionario real del repositorio ----------------
def test_real_dictionary_units_and_names():
    real = ROOT / "docs_tableros"
    if not real.is_dir():
        return
    triage = {"semantic_model": "TABLERO TIEMPOS URGENCIAS", "table": "TRIAGES_DIA",
              "column": "TIEMPO_PARA_TRIAGE_DIA", "aggregation": "Average"}
    assert T.metric_unit(triage, real) == "minutos"
    assert T.metric_unit({"semantic_model": "Tablero Control Facturacion",
                          "measure": "PROMEDIO_DIAS_PROCESO"}, real) == "días"
    entries = T.dictionary_for({"semantic_model": "BRIEFING HOSPITALARIO"}, real)
    assert T.column_business_name(entries, "SERVICIOS", "HSUNOMBRE") == "servicio"


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
