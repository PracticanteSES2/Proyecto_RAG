"""
Razonamiento en vivo desde el motor sobre la simulación pequeña (tests/sim).
Archivo aparte: los stubs de tests/sim no se mezclan con la app realista.

Ejecutar:
  PYTHONDONTWRITEBYTECODE=1 PYTHONIOENCODING=utf-8 python -m tests.export.test_live_engine
"""
import sys
import traceback
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_engine_streams_steps_and_powerbi_queries_in_sim():
    from tests.sim import harness
    engine, cm, formatter, *_ = harness.build_engine()
    events = []
    engine.set_progress_listener(events.append)
    try:
        result, _ui = harness.ask(engine, cm, formatter, "cuanto peso hubo en lavanderia en enero de 2026")
    finally:
        engine.set_progress_listener(None)
    assert result["status"] == "success", result.get("status")
    titles = [e["title"] for e in events]
    assert titles[0] == "Interpretando la pregunta", titles[:3]
    assert any(t.startswith("Consultando Power BI") for t in titles), titles
    assert any(e["kind"] == "step" and e["title"] == "Resultado del turno" for e in events)
    # Sin oyente no se emite nada y el proveedor queda desenganchado.
    assert engine.progress_listener is None and engine.powerbi_provider.query_listener is None
    harness.new_conversation(engine, cm)


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
    print()
    print(f"{len(tests) - failed}/{len(tests)} OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
