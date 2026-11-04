"""
Intención estructurada con MedGemma validada por el motor (src/semantic/intencion_llm.py).

Sin MedGemma: un LLM falso devuelve JSON fijo. Se prueba:
  * parseo robusto (```json, texto alrededor, comas finales) y un reintento si el JSON sale inválido;
  * validación: el indicador, las columnas y los valores deben existir (lista mostrada, dimensiones
    del indicador, dominio real); lo inventado se rechaza y se mantiene el resultado de las reglas;
  * periodos: solo los que dice la pregunta; comparación de periodos con DAX de dos periodos y la
    frase «subió/bajó X %» con las cifras del DAX;
  * modo off (INTENCION_LLM=off): ni se llama al LLM ni cambia nada (golden master).

Preguntas NUEVAS (no están en ningún banco). Las de extremo a extremo usan el arnés realista
(Power BI simulado) y se omiten si no hay data/ real.

Ejecutar:  python -X utf8 -m tests.resolution.test_intencion_llm
"""
import json
import os
import re
import sys
import traceback
from contextlib import contextmanager
from datetime import date
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.semantic import intencion_llm as IL  # noqa: E402


@contextmanager
def _env(**values):
    old = {key: os.environ.get(key) for key in values}
    try:
        for key, value in values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = str(value)
        yield
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


# ---------------------------------------------------------------- LLM falso
class GuionLLM:
    """Doble de MedGemma. Con `respuestas` devuelve esos textos en orden; si no, lee el catálogo del
    prompt y arma el JSON con los ids de los NOMBRES pedidos (indicador por nombre exacto, columnas
    por «TABLA[COLUMNA]»). Un nombre que no está en el catálogo se pasa tal cual (id inventado)."""

    def __init__(self, indicador=None, filtros=(), agrupacion=(), periodos=(), comparacion="ninguna",
                 top_n=None, orden="ninguno", confianza=0.9, respuestas=None, status="success"):
        self.spec = dict(indicador=indicador, filtros=list(filtros), agrupacion=list(agrupacion),
                         periodos=list(periodos), comparacion=comparacion, top_n=top_n, orden=orden,
                         confianza=confianza)
        self.respuestas = list(respuestas) if respuestas is not None else None
        self.status = status
        self.calls = []

    @staticmethod
    def _ids(prompt, indicador):
        """({nombre: I#}, {columna: C#} de la línea del indicador elegido)."""
        metrics, columns = {}, {}
        for line in prompt.splitlines():
            match = re.match(r"^(I\d+) \| ([^|]+?) \|", line)
            if not match:
                continue
            metrics.setdefault(match.group(2).strip(), match.group(1))
            if match.group(2).strip() == indicador and "col: " in line:
                for key, label in re.findall(r"(C\d+)=([^,]+)", line.split("col: ", 1)[1]):
                    columns.setdefault(label.split(" (")[0].strip(), key)
        return metrics, columns

    def chat(self, messages, temperature=0.1, max_tokens=450, think=False, format=None):
        prompt = messages[-1]["content"] if messages else ""
        if "PREGUNTA:" not in prompt:
            prompt = next((m["content"] for m in messages if "PREGUNTA:" in m.get("content", "")), prompt)
        self.calls.append({"prompt": prompt, "temperature": temperature, "format": format, "messages": messages})
        if self.status != "success":
            return {"status": self.status, "answer": None, "error": "falla simulada"}
        if self.respuestas is not None:
            answer = self.respuestas.pop(0) if self.respuestas else "OK"
            return {"status": "success", "answer": answer}
        metrics, columns = self._ids(prompt, self.spec["indicador"])
        spec = self.spec
        payload = {
            "indicador_id": metrics.get(spec["indicador"], spec["indicador"]) if spec["indicador"] else None,
            "filtros": [{"columna_id": columns.get(col, col), "valor_texto": value, "excluir": bool(excl)}
                        for col, value, *rest in spec["filtros"] for excl in [rest[0] if rest else False]],
            "agrupacion": [columns.get(col, col) for col in spec["agrupacion"]],
            "periodos": spec["periodos"], "comparacion": spec["comparacion"], "top_n": spec["top_n"],
            "orden": spec["orden"], "confianza": spec["confianza"], "dudas": "",
        }
        return {"status": "success", "answer": "```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"}


# ---------------------------------------------------------------- unidades (sin data/)
def test_parse_tolerates_fences_text_and_trailing_commas():
    assert IL.parsear_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert IL.parsear_json('Aquí está: {"a": {"b": "x}"}, } y nada más') == {"a": {"b": "x}"}}
    assert IL.parsear_json("OK") is None
    assert IL.parsear_json("[1, 2]") is None
    assert IL.parsear_json('{"a": 1') is None


def test_normalize_coerces_types_and_flags_bad_shapes():
    intent, errors = IL.normalizar_intencion({
        "indicador_id": "I2", "filtros": [{"columna_id": "C1", "valor_texto": "norte"}, {"x": 1}],
        "agrupacion": ["C3"], "periodos": ["mayo 2026", {"desde": "2026-01-01", "hasta": "2026-01-31"}],
        "comparacion": "periodos", "top_n": "4", "orden": "mayor", "confianza": "alta", "dudas": None,
    })
    assert intent["indicador_id"] == "I2" and intent["top_n"] == 4 and intent["confianza"] == 0.9, intent
    assert len(intent["filtros"]) == 1 and intent["filtros"][0]["excluir"] is False, intent
    assert errors and "filtro mal formado" in errors[0], errors
    intent, errors = IL.normalizar_intencion({"indicador_id": None, "confianza": 85})
    assert intent["indicador_id"] is None and abs(intent["confianza"] - 0.85) < 1e-9 and not errors, (intent, errors)
    assert IL.normalizar_intencion("texto")[0] is None


def test_detects_period_comparisons_and_not_ranges():
    for question in ("las entregas de ropa subieron o bajaron de mayo a junio",
                     "hubo mas consultas en marzo o en abril",
                     "egresos 2024 vs 2025",
                     "las remisiones de febrero comparadas con enero"):
        assert IL.pide_comparacion_periodos(question), question
    for question in ("consultas entre enero y marzo", "egresos de mayo a junio de 2025",
                     "cuantas cirugias hubo en julio"):
        assert not IL.pide_comparacion_periodos(question), question


def test_when_to_call_the_llm():
    assert IL.motivo_llamada("off", {"status": "not_found"}, "x") is None
    assert IL.motivo_llamada("respaldo", {"status": "ready"}, "cuantas camas hay") is None
    assert IL.motivo_llamada("respaldo", {"status": "not_found"}, "x")
    assert IL.motivo_llamada("respaldo", {"status": "ambiguous"}, "x")
    assert IL.motivo_llamada("respaldo", {"status": "unsupported_filter", "reason": "requested_value_not_found"}, "x") is None
    assert IL.motivo_llamada("respaldo", {"status": "ready"}, "las altas subieron o bajaron de mayo a junio")
    assert IL.motivo_llamada("respaldo", {"status": "ready", "temporal_buckets": [{}, {}]},
                             "las altas de mayo contra junio") is None
    assert IL.motivo_llamada("siempre", {"status": "ready"}, "cuantas camas hay")
    with _env(INTENCION_LLM="off"):
        assert IL.modo() == "off"
    # Apagado por defecto hasta que el sondeo real muestre que ayuda.
    with _env(INTENCION_LLM=None):
        assert IL.modo() == "off"
    with _env(INTENCION_LLM="cualquiera"):
        assert IL.modo() == "off"
    with _env(INTENCION_LLM="respaldo"):
        assert IL.modo() == "respaldo"


def _catalogo_vacio():
    return IL.Catalogo([], [], [], date(2026, 11, 4))


def _call_direct(provider, messages, **kwargs):
    kwargs.pop("purpose", None), kwargs.pop("timeout", None), kwargs.pop("queue_wait", None)
    return provider.chat(messages, **kwargs)


def test_retry_once_on_invalid_json_with_temperature_zero():
    llm = GuionLLM(respuestas=["no sé", '{"indicador_id": "I1", "filtros": [], "agrupacion": [], "periodos": [], '
                               '"comparacion": "ninguna", "top_n": null, "orden": "ninguno", "confianza": 0.8, "dudas": ""}'])
    result = IL.extraer_intencion(llm, "pregunta", _catalogo_vacio(), call=_call_direct)
    assert result["status"] == "ok" and result["llamadas"] == 2, result
    assert all(call["temperature"] == 0.0 for call in llm.calls)
    assert llm.calls[0]["format"] == "json" and llm.calls[1]["format"] == "json"
    llm = GuionLLM(respuestas=["nada", "tampoco"])
    result = IL.extraer_intencion(llm, "pregunta", _catalogo_vacio(), call=_call_direct)
    assert result["status"] == "invalid" and result["intencion"] is None and result["llamadas"] == 2, result


def test_llm_error_and_missing_provider():
    assert IL.extraer_intencion(None, "x", _catalogo_vacio())["status"] == "sin_llm"
    IL.cerrar_disyuntor()
    result = IL.extraer_intencion(GuionLLM(status="llm_timeout"), "x", _catalogo_vacio(), call=_call_direct)
    assert result["status"] == "llm_error" and result["llamadas"] == 1, result
    IL.cerrar_disyuntor()


def test_server_failure_opens_breaker_and_never_retries():
    IL.cerrar_disyuntor()
    try:
        failing = GuionLLM(status="ollama_error")
        result = IL.extraer_intencion(failing, "x", _catalogo_vacio(), call=_call_direct)
        assert result["status"] == "llm_error" and len(failing.calls) == 1, result   # sin reintento
        assert IL.disyuntor_abierto(), "el disyuntor no se abrió"
        later = GuionLLM(indicador="I1")
        result = IL.extraer_intencion(later, "x", _catalogo_vacio(), call=_call_direct)
        assert result["status"] == "pausado" and not later.calls, result             # en pausa: ni se llama
        with _env(INTENCION_LLM_PAUSA_S="0"):
            IL.abrir_disyuntor("prueba")
            assert not IL.disyuntor_abierto()
    finally:
        IL.cerrar_disyuntor()
    assert IL.falla_del_servidor("Error occurred while trying to proxy (status code: 504)")
    assert IL.falla_del_servidor("model runner has unexpectedly stopped")


def test_output_is_short_and_plain_json_by_default():
    llm = GuionLLM(respuestas=['{"indicador_id": "I1", "confianza": 0.8}'])
    result = IL.extraer_intencion(llm, "x", _catalogo_vacio(), call=_call_direct)
    assert result["status"] == "ok" and result["intencion"]["filtros"] == [], result   # campos omitidos = vacíos
    call = llm.calls[0]
    assert call["format"] == "json", call["format"]
    assert len(IL.SISTEMA) < 1100, len(IL.SISTEMA)
    with _env(INTENCION_LLM_FORMATO="esquema"):
        assert IL.formato_salida() == IL.ESQUEMA


def test_prompt_fits_budget():
    system = _system()
    if system is None:
        print("  (omitido: sin data/ real)")
        return
    builder = system["engine"].query_plan_builder
    for question in (Q_TOP, "los kilos de ropa lavada subieron o bajaron de mayo a junio de 2025",
                     "en que servicios hay mas pacientes esperando cama de hospitalizacion"):
        plan = builder.build(question)
        catalog = IL.armar_catalogo(builder, question, plan, encoder=system["engine"]._intent_encoder())
        size = sum(len(m["content"]) for m in IL.mensajes(question, catalog))
        assert size <= IL.MAX_PROMPT and len(catalog.indicadores) <= IL.MAX_INDICADORES, (question, size)
        for item in catalog.indicadores:
            assert len(item["columnas"]) <= IL.MAX_COLUMNAS_POR_INDICADOR, item


def test_prompt_lists_only_catalog_ids_and_no_bank_questions():
    banks = []
    for name in ("banco_real.json", "banco_holdout.json", "banco_holdout2.json"):
        path = ROOT / "tests" / "real" / name
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            banks += [str(case.get("pregunta") or "") for case in data.get("casos") or []]
    text = IL.SISTEMA.lower()
    for question in banks:
        assert not question or question.lower() not in text, question


def test_comparison_sentence_uses_dax_numbers():
    plan = {"comparison": {"labels": ["mayo 2026", "junio 2026"]}, "group_by": [{"column": "Periodo"}],
            "metric": {"label": "KILOS LAVADOS"}}
    rows = [{"[Periodo]": "mayo 2026", "[__value]": 200.0}, {"[Periodo]": "junio 2026", "[__value]": 230.0}]

    def cell(row, group):
        return row.get("[Periodo]")

    def value(row):
        return row.get("[__value]")

    from src.chatbot.response_formatter import format_number_es, format_value_es
    text = IL.frase_comparacion(plan, rows, value, cell, format_value_es, format_number_es)
    assert text == "De mayo 2026 a junio 2026, **KILOS LAVADOS** subió 15 % (de 200 a 230).", text
    rows[1]["[__value]"] = 150
    assert "bajó 25 %" in IL.frase_comparacion(plan, rows, value, cell, format_value_es, format_number_es)
    rows[1]["[__value]"] = None
    assert "No hay datos" in IL.frase_comparacion(plan, rows, value, cell, format_value_es, format_number_es)


def test_comparison_dax_has_one_calculate_per_period():
    from src.dax.query_plan_dax_generator import QueryPlanDAXGenerator
    plan = {
        "status": "ready", "mode": "grouped", "filters": [],
        "metric": {"dax_expression": "SUM('T'[KG])", "validation_status": "approved"},
        "group_by": [{"table": "T", "column": "Periodo", "temporal": "comparison"}],
        "temporal_buckets": [
            {"order": 1, "label": "mayo 2026", "filters": [{"type": "date_range", "table": "T", "column": "FECHA",
                                                            "start": "2026-05-01", "end": "2026-06-01"}]},
            {"order": 2, "label": "junio 2026", "filters": [{"type": "date_range", "table": "T", "column": "FECHA",
                                                             "start": "2026-06-01", "end": "2026-07-01"}]},
        ],
    }
    dax = QueryPlanDAXGenerator().generate(plan)["dax"]
    assert dax.count("CALCULATE(") == 2 and "DATE(2026, 5, 1)" in dax and "DATE(2026, 7, 1)" in dax, dax


# ---------------------------------------------------------------- extremo a extremo (arnés realista)
_SYSTEM = {}


def _system():
    if "engine" not in _SYSTEM:
        try:
            from tests.realistic import harness
            harness.resolve_data_root()
            engine, cm, formatter, *_ = harness.build_engine(llm="fake")
        except Exception as error:  # sin data/ real
            _SYSTEM["engine"] = None
            _SYSTEM["error"] = str(error)
        else:
            _SYSTEM.update(engine=engine, cm=cm, formatter=formatter, harness=harness)
            # El arnés reimporta src/: el módulo que usa el motor es el de sys.modules ahora (su
            # índice y su disyuntor son los que cuentan).
            global IL
            import importlib
            IL = importlib.import_module("src.semantic.intencion_llm")
            # Índice de embeddings de los indicadores listo antes de preguntar (la primera vez
            # tarda ~20 s; luego se lee de disco): las pruebas no dependen de la carrera.
            index = IL.indice_semantico(engine.query_plan_builder, engine._intent_encoder())
            if index is not None:
                index.esperar(300)
    return _SYSTEM if _SYSTEM.get("engine") else None


def _ask(question, llm=None, mode="respaldo"):
    """(resultado, respuesta mostrada) con el LLM de intención dado (o ninguno)."""
    system = _system()
    if system is None:
        return None
    engine, harness = system["engine"], system["harness"]
    previous = engine.context_llm
    engine.context_llm = llm
    IL.cerrar_disyuntor()
    try:
        with _env(INTENCION_LLM=mode):
            harness.new_conversation(engine, system["cm"])
            return harness.ask(engine, system["cm"], system["formatter"], question)
    finally:
        engine.context_llm = previous


def _steps(result):
    return [step for step in (result.get("reasoning") or {}).get("steps") or []
            if "Intención con MedGemma" in str(step.get("title"))]


def _signature(result, ui):
    plan = result.get("query_plan") or {}
    return (result.get("status"), result.get("route"), result.get("metric"), result.get("dax"),
            json.dumps(plan.get("filters"), default=str, sort_keys=True), ui)


# Pregunta nueva que las reglas no resuelven (verbo «intervinieron» + «quirúrgicas»).
Q_TOP = "las 4 especialidades quirurgicas que mas intervinieron pacientes en agosto"


def test_e2e_valid_intent_replaces_unresolved_rules():
    llm = GuionLLM(indicador="TOTAL_CIRUGIAS", agrupacion=["ESPECIALIDAD"], periodos=["agosto 2026"],
                   top_n=4, orden="mayor")
    asked = _ask(Q_TOP, llm)
    if asked is None:
        print("  (omitido: sin data/ real)")
        return
    result, ui = asked
    assert llm.calls, "no se llamó al LLM"
    assert result.get("status") == "success" and result.get("metric") == "TOTAL_CIRUGIAS", (result.get("status"), ui)
    dax = str(result.get("dax") or "")
    assert "TOPN" in dax and "4," in dax and "ESPECIALIDAD" in dax and "DATE(2026, 8, 1)" in dax, dax
    assert _steps(result) and "reemplaza" in " ".join(_steps(result)[-1].get("lines") or []), _steps(result)


def test_e2e_invented_indicator_is_rejected_and_rules_stay():
    baseline = _ask(Q_TOP, None, mode="off")
    if baseline is None:
        print("  (omitido: sin data/ real)")
        return
    for llm in (
        GuionLLM(indicador="I99", agrupacion=["ESPECIALIDAD"]),                 # id inventado
        GuionLLM(indicador="TOTAL_CIRUGIAS", agrupacion=["NO_EXISTE"]),          # columna inventada
        GuionLLM(indicador="TOTAL_CIRUGIAS", filtros=[("ESPECIALIDAD", "ASTROLOGIA")]),  # valor inventado
        GuionLLM(indicador="TOTAL_CIRUGIAS", confianza=0.2),                               # confianza baja
        GuionLLM(respuestas=["no es json", "tampoco"]),                                    # JSON inválido 2 veces
    ):
        result, ui = _ask(Q_TOP, llm)
        assert llm.calls, "no se llamó al LLM"
        assert _signature(result, ui) == _signature(*baseline), (llm.spec, result.get("status"), ui)
        lines = " ".join(" ".join(step.get("lines") or []) for step in _steps(result))
        assert "se mantiene el resultado de las reglas" in lines or "sin intención utilizable" in lines, lines


def test_e2e_comparison_two_periods_and_change_sentence():
    question = "los kilos de ropa lavada subieron o bajaron de mayo a junio de 2025"
    llm = GuionLLM(indicador="PESO TOTAL por Mes", periodos=["mayo 2025", "junio 2025"], comparacion="periodos")
    asked = _ask(question, llm)
    if asked is None:
        print("  (omitido: sin data/ real)")
        return
    result, ui = asked
    assert llm.calls, "no se llamó al LLM"
    dax = str(result.get("dax") or "")
    assert result.get("status") == "success" and dax.count("CALCULATE(") == 2, (result.get("status"), dax, ui)
    assert "DATE(2025, 5, 1)" in dax and "DATE(2025, 7, 1)" in dax, dax
    assert re.search(r"De mayo 2025 a junio 2025, \*\*.+\*\* (subió|bajó|se mantuvo)", ui), ui


def test_e2e_invented_period_is_not_applied():
    # La pregunta no dice periodo: «este año» del LLM se descarta (no se inventan periodos).
    llm = GuionLLM(indicador="PESO TOTAL por Mes", filtros=[("TURNO_OK", "noche")],
                   periodos=["este año"])
    asked = _ask("cuantos kilos de ropa se lavaron en el turno de la noche", llm, mode="siempre")
    if asked is None:
        print("  (omitido: sin data/ real)")
        return
    result, ui = asked
    assert llm.calls, "no se llamó al LLM"
    lines = " ".join(" ".join(step.get("lines") or []) for step in _steps(result))
    assert "periodo «este año» descartado" in lines, lines
    assert result.get("status") == "success" and "DATE(" not in str(result.get("dax") or ""), (result.get("dax"), ui)
    assert "NOCHE" in str(result.get("dax") or ""), result.get("dax")


def test_e2e_filter_naming_the_column_groups_and_period_words_are_dropped():
    llm = GuionLLM(indicador="PESO TOTAL por Mes",
                   filtros=[("TURNO_OK", "turno"), ("TURNO_OK", "junio 2025"), ("TURNO_OK", "hoy")],
                   periodos=["junio 2025"])
    asked = _ask("cuantos kilos de ropa se lavaron segun el turno en junio de 2025", llm, mode="siempre")
    if asked is None:
        print("  (omitido: sin data/ real)")
        return
    result, ui = asked
    lines = " ".join(" ".join(step.get("lines") or []) for step in _steps(result))
    assert "nombra la columna" in lines and "es un periodo" in lines, lines
    dax = str(result.get("dax") or "")
    assert result.get("status") == "success" and "TURNO_OK" in dax and "DATE(2025, 6, 1)" in dax, (dax, ui)
    assert "TREATAS" not in dax, dax   # ningún filtro por «turno», «junio 2025» ni «hoy»


def test_e2e_ambiguity_only_allows_rule_options():
    system = _system()
    if system is None:
        print("  (omitido: sin data/ real)")
        return
    builder = system["engine"].query_plan_builder
    question = "cuantos kilos de ropa se lavaron en junio de 2025"
    catalog = IL.armar_catalogo(builder, question, builder.build(question))
    intent = {"indicador_id": "I1", "filtros": [], "agrupacion": [], "periodos": [], "comparacion": "ninguna",
              "top_n": None, "orden": "ninguno", "confianza": 0.9, "dudas": ""}
    other = {("otro",)}
    rejected = IL.validar_intencion(builder, question, intent, catalog, permitidos=other)
    assert rejected["status"] == "rejected" and "opciones de la contrapregunta" in rejected["motivo"], rejected
    allowed = {builder._logical_key(catalog.indicadores[0]["metric"])}
    assert IL.validar_intencion(builder, question, intent, catalog, permitidos=allowed)["status"] == "valid"
    assert IL.opciones_permitidas(builder, {"status": "not_found"}) is None


def test_e2e_off_mode_never_calls_llm_and_rules_resolved_questions_untouched():
    llm = GuionLLM(indicador="TOTAL_CIRUGIAS")
    asked = _ask(Q_TOP, llm, mode="off")
    if asked is None:
        print("  (omitido: sin data/ real)")
        return
    assert not llm.calls and not _steps(asked[0]), "modo off llamó al LLM"
    # Pregunta que las reglas resuelven: en respaldo no se llama al LLM.
    question = "cuantos kilos de ropa se lavaron en el turno de la noche en junio de 2025"
    off = _ask(question, None, mode="off")
    llm = GuionLLM(indicador="TOTAL_CIRUGIAS")
    fallback = _ask(question, llm, mode="respaldo")
    assert not llm.calls and _signature(*off) == _signature(*fallback), fallback[1]


TESTS = [value for name, value in sorted(globals().items()) if name.startswith("test_") and callable(value)]


def main():
    failures = 0
    for test in TESTS:
        try:
            test()
            print(f"ok   {test.__name__}")
        except Exception:
            failures += 1
            print(f"FAIL {test.__name__}")
            traceback.print_exc()
    print(f"\n{len(TESTS) - failures}/{len(TESTS)} ok")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
