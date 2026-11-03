"""
Tiempo de un turno en el simulador: ninguna pregunta puede colgar el motor.

«cirugias pendientes de los pacientes de naos» (H34 del holdout) dejaba el
motor al 100 % de CPU más de 8 minutos: la palabra «pacientes» coincidía con
los ~1000 valores de TIPO_PACIENTE / NOMBRE de CIRUGÍAS PENDIENTES y
`value_contradiction` rehacía el análisis de todo el dominio por cada valor
(O(n²) raíces). Ahora el análisis se calcula una vez por (dominio, texto) y,
además, el armado del plan tiene un presupuesto de tiempo
(PLAN_TIME_BUDGET_S, src/semantic/plan_budget.py) que corta con una
contrapregunta en lugar de colgarse.

    python -X utf8 -m tests.realistic.test_tiempo_turno
"""
import os
import sys
import time

os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
sys.dont_write_bytecode = True

# Límite de la prueba (s): holgado para máquinas lentas; antes del arreglo eran > 480 s.
MAX_TURN_S = float(os.getenv("TEST_MAX_TURN_S", "20"))
H34 = "cirugias pendientes de los pacientes de naos"


def test_value_contradiction_large_domain_is_fast():
    from src.semantic.query_plan_builder import value_contradiction

    domain = [f"PACIENTE TIPO {i} PLAN {i % 7}" for i in range(1500)]
    started = time.perf_counter()
    for value in domain:
        value_contradiction(f"pacientes {H34}", value, domain)
    elapsed = time.perf_counter() - started
    assert elapsed < 5, f"1500 valores de un dominio de 1500 tardaron {elapsed:.1f} s (cuadrático)"


def test_value_contradiction_same_answers():
    from src.semantic.query_plan_builder import value_contradiction

    domain = ["MAYORES DE EDAD", "MENORES DE EDAD"]
    assert value_contradiction("menores de edad", "MAYORES DE EDAD", domain)
    assert value_contradiction("menores de edad", "MENORES DE EDAD", domain) is None
    domain = ["ACEPTADO", "NO ACEPTADO"]
    assert value_contradiction("cuantas no aceptadas", "ACEPTADO", domain)
    assert value_contradiction("cuantas no aceptadas", "NO ACEPTADO", domain) is None
    assert value_contradiction("triage", "TRIAGE III", ["TRIAGE I", "TRIAGE II", "TRIAGE III"])


def test_plan_budget_check():
    from src.semantic import plan_budget

    plan_budget.start(0.0)          # 0 = sin límite
    plan_budget.check()
    plan_budget.start(0.01)
    time.sleep(0.03)
    try:
        plan_budget.check("prueba")
    except plan_budget.PlanBudgetExceeded as error:
        assert "prueba" in str(error)
        # Hereda de BaseException: los `except Exception` defensivos no la tragan.
        assert not isinstance(error, Exception)
    else:
        raise AssertionError("debió cortar")
    finally:
        plan_budget.clear()
    plan_budget.check()             # sin presupuesto abierto, nunca corta


_ENGINE = {}


def _engine():
    if not _ENGINE:
        from tests.realistic import harness

        engine, cm, formatter, *_ = harness.build_engine(llm="fake")
        _ENGINE.update(harness=harness, engine=engine, cm=cm, formatter=formatter)
    return _ENGINE


def _ask(text):
    e = _engine()
    started = time.perf_counter()
    result, ui = e["harness"].ask(e["engine"], e["cm"], e["formatter"], text)
    return result, ui, time.perf_counter() - started


def test_h34_answers_within_limit():
    result, ui, elapsed = _ask(H34)
    assert not (result.get("_sim") or {}).get("exception"), result["_sim"]["exception"]
    assert elapsed < MAX_TURN_S, f"«{H34}» tardó {elapsed:.1f} s (límite {MAX_TURN_S:.0f} s)"
    assert result.get("route") != "plan_time_budget", "no debe depender del presupuesto de seguridad"


def test_budget_exceeded_asks_to_clarify_and_recovers():
    previous = os.environ.get("PLAN_TIME_BUDGET_S")
    os.environ["PLAN_TIME_BUDGET_S"] = "0.000001"
    try:
        result, ui, elapsed = _ask(H34)
    finally:
        if previous is None:
            os.environ.pop("PLAN_TIME_BUDGET_S", None)
        else:
            os.environ["PLAN_TIME_BUDGET_S"] = previous
    assert result.get("status") == "needs_clarification", result.get("status")
    assert result.get("route") == "plan_time_budget", result.get("route")
    assert "precisar" in ui, ui
    assert elapsed < MAX_TURN_S, elapsed
    # El turno siguiente funciona normalmente (sin presupuesto colgado).
    result, ui, _ = _ask("cuantos pacientes naos tenemos con pendientes?")
    assert result.get("route") != "plan_time_budget", result.get("route")


def _run_all():
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)]
    failed = 0
    for name, func in tests:
        try:
            func()
            print("PASS ", name)
        except Exception as error:  # noqa: BLE001
            failed += 1
            print("FAIL ", name, "->", type(error).__name__, error)
    print(f"{len(tests) - failed}/{len(tests)} OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run_all())
