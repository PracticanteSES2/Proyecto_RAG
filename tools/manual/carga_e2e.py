"""
Motor del simulador (tests/sim: Power BI, Qdrant y MiniLM falsos) para el modo
`e2e` de la herramienta de carga (tools/carga).

`tools/carga` no importa `tests` (docs/ARQUITECTURA.md §4); los sondeos que
usan los arneses de pruebas viven aquí, en `tools/manual/` (carpeta exenta).
`python -m tools.carga --modo e2e` importa `fabrica_motor_e2e` de este módulo y
se la pasa a `runner.correr(..., fabrica_motor=...)`.

    python -m tools.carga --modo e2e --rampa 1,3,5,10 --turnos 2
"""
import sys

DEFAULT_SYNTHESIS_TIMEOUT = 40.0
OPTION_TIMEOUT = 15.0
REWRITE_TIMEOUT = 8.0


def _motor_simulado():
    """Arma el motor del simulador sin leer el .env ni salir a la red."""
    from tests.sim import fakes, harness

    # Con --real, medgemma_provider ya se importó con el cliente y el dotenv
    # reales (el proveedor real se construyó antes): mientras se arma el motor
    # simulado se usan los falsos, para que su MedGemmaProvider interno no lea
    # el .env ni salga a la red. Sin --real aún no está importado y el arnés
    # lo importa ya con los falsos.
    mp = sys.modules.get("src.llm.medgemma_provider")
    saved = (mp.Client, mp.ResponseError, mp.load_dotenv) if mp is not None else None
    if mp is not None:
        mp.Client, mp.ResponseError = fakes.FakeOllamaClient, fakes.FakeResponseError
        mp.load_dotenv = lambda *a, **k: False
    try:
        engine, cm, formatter, _status, _pbi, _dax = harness.build_engine()
    finally:
        if mp is not None:
            mp.Client, mp.ResponseError, mp.load_dotenv = saved
    return harness, engine, cm, formatter


def fabrica_motor_e2e(provider, escala):
    """(harness, engine, cm, formatter, restaurar): motor del simulador con el
    LLM cableado a `provider` y los tiempos límite escalados."""
    from src.chatbot import contextual_rewriter

    harness, engine, cm, formatter = _motor_simulado()
    synthesizer = engine.rag_answer_engine.answer_synthesizer
    synthesizer.llm_provider = provider
    synthesizer.timeout_seconds = DEFAULT_SYNTHESIS_TIMEOUT * escala
    describer = getattr(engine, "option_describer", None)
    if describer is not None:
        describer.llm_provider = provider
        describer.timeout = OPTION_TIMEOUT * escala
    engine.context_llm = provider
    init = contextual_rewriter.LLMContextRewriter.__init__
    original_defaults = init.__defaults__
    defaults = list(original_defaults)
    defaults[0] = REWRITE_TIMEOUT * escala
    init.__defaults__ = tuple(defaults)

    def restaurar():
        init.__defaults__ = original_defaults

    return harness, engine, cm, formatter, restaurar
