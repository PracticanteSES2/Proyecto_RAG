"""
Pruebas del razonamiento en vivo (pasos y actividades mientras se responde).

Ejecutar:
  PYTHONDONTWRITEBYTECODE=1 PYTHONIOENCODING=utf-8 python -m tests.export.test_live_progress
"""
import sys
import traceback
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.chatbot.reasoning_trace import ReasoningTrace, format_reasoning_text  # noqa: E402


def test_trace_notifies_steps_and_activities_without_storing_activities():
    events = []
    trace = ReasoningTrace("question", "hola", listener=events.append)
    trace.activity("Consultando Power BI (X)", "EVALUATE ROW(...)")
    trace.add("Indicador elegido", "TOTAL")
    assert [e["kind"] for e in events] == ["activity", "step"]
    assert events[0]["title"] == "Consultando Power BI (X)" and events[0]["lines"] == ["EVALUATE ROW(...)"]
    assert trace.current_activity == "Consultando Power BI (X)"
    data = trace.to_dict()
    assert [s["title"] for s in data["steps"]] == ["Indicador elegido"]
    assert "Consultando Power BI" not in format_reasoning_text(data)


def test_listener_errors_never_break_the_turn():
    def broken(_event):
        raise RuntimeError("UI caída")
    trace = ReasoningTrace("question", "hola", listener=broken)
    trace.activity("algo")
    trace.add("paso")
    assert len(trace.steps) == 1


def test_app_shows_live_status_that_ends_listo():
    try:
        from streamlit.testing.v1 import AppTest
    except ImportError:
        print("  (Streamlit no instalado: se omite)")
        return
    app = AppTest.from_file(str(ROOT / "tests" / "realistic" / "run_app.py"), default_timeout=300)
    app.run()
    app.chat_input[0].set_value("cuanto peso hubo en lavanderia en enero de 2026").run()
    assert not app.exception, app.exception
    labels = [element.proto.label for element in app.get("status")]
    assert any(label.startswith("Listo en") for label in labels), labels
    assert any("a Power BI" in label for label in labels), labels


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
