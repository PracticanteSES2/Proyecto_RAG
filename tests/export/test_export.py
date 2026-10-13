"""
Pruebas de «Exportar conversación».

Ejecutar:
  PYTHONDONTWRITEBYTECODE=1 PYTHONIOENCODING=utf-8 python -m tests.export.test_export
La última prueba ejecuta la app Streamlit real (AppTest) con Power BI simulado
(tests/realistic/run_app.py); se omite si Streamlit no está instalado.
"""
import sys
import traceback
from datetime import datetime
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.chatbot.conversation_export import (  # noqa: E402
    export_conversation_markdown,
    export_file_name,
)

MESSAGES = [
    {"role": "assistant", "content": "Hola. Puedes preguntarme por indicadores."},
    {"role": "user", "content": "¿Cuántas cirugías hay?", "via": "texto"},
    {
        "role": "assistant", "content": "Encontré varios indicadores. ¿Cuál necesitas?",
        "status": "needs_clarification", "route": "clarification",
        "buttons": [
            {"id": "a", "label": "Total cirugías", "caption": "Cuenta todas las cirugías"},
            {"id": "__none__", "label": "Ninguna de las anteriores", "caption": None},
        ],
        "reasoning": "=== RAZONAMIENTO ===\n1. Indicadores evaluados\n```raro```",
    },
    {"role": "user", "content": "Total cirugías", "via": "botón"},
    {
        "role": "assistant", "content": "| Servicio | Valor |\n| --- | --- |\n| UCI | 3 |",
        "status": "success", "route": "powerbi", "reasoning": "paso 1",
    },
]


def test_export_contains_turns_options_and_reasoning():
    text = export_conversation_markdown(
        MESSAGES, meta={"MedGemma": "ready (medgemma:latest)", "Vacío": None},
        now=datetime(2026, 10, 13, 9, 30),
    )
    assert text.startswith("# Conversación del Asistente de Gestión Clínica")
    assert "- Exportada: 2026-10-13 09:30:00" in text and "- Turnos del usuario: 2" in text
    assert "- MedGemma: ready (medgemma:latest)" in text and "Vacío" not in text
    assert "## Turno 1" in text and "## Turno 2" in text
    assert "**Usuario (texto):**" in text and "**Usuario (botón):**" in text
    assert "_(status=needs_clarification · route=clarification)_" in text
    assert "1. Total cirugías — Cuenta todas las cirugías" in text
    assert "2. Ninguna de las anteriores" in text
    # Tablas en cita y razonamiento en bloque que no se rompe con ``` internos.
    assert "> | UCI | 3 |" in text
    assert "````text\n=== RAZONAMIENTO ===" in text
    without = export_conversation_markdown(MESSAGES, include_reasoning=False)
    assert "Razonamiento del asistente" not in without and "paso 1" not in without


def test_export_file_name():
    assert export_file_name(datetime(2026, 10, 13, 9, 5, 7)) == "conversacion_20261013_090507.md"


def test_app_has_export_button_with_the_whole_conversation():
    try:
        from streamlit.testing.v1 import AppTest
    except ImportError:
        print("  (Streamlit no instalado: se omite)")
        return
    app = AppTest.from_file(str(ROOT / "tests" / "realistic" / "run_app.py"), default_timeout=300)
    app.run()
    assert not app.exception, app.exception
    app.chat_input[0].set_value("¿Qué muestra el tablero de lavandería?").run()
    assert not app.exception, app.exception
    labels = [element.proto.label for element in app.get("download_button")]
    assert "Descargar conversación (.md)" in labels, labels
    exported = export_conversation_markdown(app.session_state["messages"])
    assert "¿Qué muestra el tablero de lavandería?" in exported
    assert "Razonamiento del asistente" in exported
    assert app.session_state["messages"][1]["via"] == "texto"


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
