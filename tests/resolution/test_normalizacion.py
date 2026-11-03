"""
Normalización del lenguaje de chat (src/semantic/question_normalizer.py).

Causa raíz 10 del holdout v1 (tests/real/RETOMAR.md, sección 5): los usuarios
escriben «x servicio», «q», «pa», «d», con tipeos y sin tildes, y no había un
paso común que lo normalizara. Ahora se normaliza UNA vez al entrar
(`QueryEngine.process`). Estas pruebas cubren:

1) abreviaturas de chat (x/q/k/pa/d/xq/tb/cant/prom) y sus excepciones
   (multiplicación «3 x 4», «rayos x», «30 d», «vitamina D»);
2) repeticiones de letras, espacios y signos;
3) tipeos contra el vocabulario del catálogo, con umbrales prudentes: nunca
   números, fechas, códigos, nombres propios ni palabras que ya existen, y
   nunca una palabra que no esté en el catálogo;
4) las frases reales del holdout (H02 H03 H10 H11 H24 H27b H29 H31 H35 H38)
   con el vocabulario real (si hay data/ con catálogos) Y frases inventadas
   del mismo estilo que no están en ningún banco;
5) la agrupación «x <dimensión>» / «por cada <dimensión>» tras normalizar;
6) el punto de entrada: el motor recibe el texto normalizado y la traza
   guarda el original y el normalizado.

Ejecutar:  python -m tests.resolution.test_normalizacion      (o pytest tests/resolution)
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

from src.chatbot.query_engine import QueryEngine  # noqa: E402
from src.semantic import question_normalizer as qn  # noqa: E402
from src.semantic.question_normalizer import (  # noqa: E402
    Vocabulary, correct_word, edit_distance, normalize_question, vocabulary_for,
)

# Vocabulario de catálogo pequeño (inventado, mismo estilo que el real).
VOCAB = Vocabulary(
    targets={w: w for w in (
        "cirugias", "cirugia", "canceladas", "hospitalizacion", "ocupacion", "pacientes", "paciente",
        "servicio", "servicios", "especialidad", "especialidades", "aseguradora", "desabastecidos",
        "medicamentos", "egresos", "ingresos", "triage", "urgencias", "estancia", "promedio",
        "porcentaje", "facturacion", "radicacion", "lavanderia", "antibioticos", "referencia",
        "remisiones", "aceptados", "pendientes", "consultas", "ambulatorias", "atenciones",
        "marzo", "septiembre", "estado", "camas", "tipo", "area", "valor", "estimado",
    )},
    known={"ropa", "kilos", "lavados", "tantas", "hubo", "usando", "suben", "pasa"},
)
VOCAB.targets["hospitalizacion"] = "hospitalización"
VOCAB.targets["ocupacion"] = "ocupación"


def norm(text, vocabulary=VOCAB):
    return normalize_question(text, vocabulary).text


# ---------------------------------------------------------------- 1) abreviaturas
def test_chat_abbreviations():
    cases = {
        "camas x estado": "camas por estado",
        "q antibioticos se estan usando": "que antibioticos se estan usando",
        "k tal la ocupacion": "que tal la ocupacion",
        "tiempo pa egreso": "tiempo para egreso",
        "kilos d ropa": "kilos de ropa",
        "xq bajaron los egresos": "porque bajaron los egresos",
        "y tb x servicio": "y también por servicio",
        "cant de cirugias": "cantidad de cirugias",
        "prom de estancia": "promedio de estancia",
        "pa' la proxima semana": "para la proxima semana",
        "en lo q va del año": "en lo que va del año",
    }
    for text, expected in cases.items():
        assert norm(text) == expected, (text, norm(text))


def test_abbreviation_exceptions():
    # Multiplicación, nombres y números: la letra se queda.
    assert norm("3 x 4 camas") == "3 x 4 camas"
    assert norm("camas 2 x 2") == "camas 2 x 2"
    assert norm("rayos x en urgencias") == "rayos x en urgencias"
    assert norm("estancia de 30 d en promedio") == "estancia de 30 d en promedio"
    assert norm("consumo de vitamina D en farmacia") == "consumo de vitamina D en farmacia"
    # La x al final o pegada a un número no es «por».
    assert norm("cuanto es 3x4") == "cuanto es 3x4"
    assert norm("el valor x") == "el valor x"
    # Solo palabras sueltas: «xq» dentro de otra palabra no se toca.
    assert norm("paxqo") == "paxqo"


# ---------------------------------------------------------------- 2) repeticiones y signos
def test_repeated_letters_spaces_and_signs():
    assert norm("holaaa cuantooos egresos hubooo") == "hola cuantos egresos hubo"
    assert norm("   cuantas   camas  hay ??") == "cuantas camas hay?"
    assert norm("¿¿cuantas camas hay??") == "¿cuantas camas hay?"
    assert norm("egresos ,urgencias") == "egresos, urgencias"
    assert norm("egresos!!!x servicio") == "egresos! por servicio"
    # Números romanos, decimales, rangos, porcentajes y fechas intactos.
    assert norm("NIVEL III") == "NIVEL III"
    assert norm("productos 30-120 dias al 2,5 %") == "productos 30-120 dias al 2,5 %"
    assert norm("egresos del 01/09/2026 al 15/09/2026") == "egresos del 01/09/2026 al 15/09/2026"


# ---------------------------------------------------------------- 3) tipeos
def test_edit_distance_weights_spanish_phonetics():
    assert edit_distance("cirujias", "cirugias") == 0.5      # j/g
    assert edit_distance("desabastesidos", "desabastecidos") == 0.5  # s/c
    assert edit_distance("ospitalizacion", "hospitalizacion") == 0.5  # h muda
    assert edit_distance("servicos", "servicios") == 1.0
    assert edit_distance("pacinetes", "pacientes") == 1.0    # transposición


def test_typos_are_corrected_against_the_catalog():
    cases = {
        "cirujias canceladas": "cirugias canceladas",
        "medicamentos desabastesidos": "medicamentos desabastecidos",
        "atenciones de hospitalisacion": "atenciones de hospitalización",
        "ocupasion por servicio": "ocupación por servicio",
        "cuantos pasientes hay": "cuantos pacientes hay",
        "pacinetes en urgencias": "pacientes en urgencias",
        "consultas por especialidda": "consultas por especialidad",
        "porcentage de remisiones": "porcentaje de remisiones",
    }
    for text, expected in cases.items():
        assert norm(text) == expected, (text, norm(text))


def test_typo_correction_is_prudent():
    # Palabras cortas, existentes o conjugaciones: nunca se tocan.
    assert norm("cuantas remisiones no aceptamos") == "cuantas remisiones no aceptamos"
    assert norm("kilos de ropa lavados") == "kilos de ropa lavados"
    assert norm("egresos e ingresos") == "egresos e ingresos"
    assert norm("tipo de cama") == "tipo de cama"
    # Nombres propios (mayúscula a mitad de frase), mayúsculas, códigos y números.
    assert norm("facturas de Pasientes Ltda") == "facturas de Pasientes Ltda"
    assert norm("valor de CIRUJIAS") == "valor de CIRUJIAS"
    assert norm("servicio UCI06 y cama 4031") == "servicio UCI06 y cama 4031"
    # Una palabra lejos de todo el catálogo no se inventa.
    assert norm("cuantos murcielagos hay") == "cuantos murcielagos hay"
    # Ambigua (dos candidatos igual de cerca): no se corrige.
    ambiguous = Vocabulary(targets={"casos": "casos", "cosas": "cosas", "camas": "camas"})
    assert correct_word("casas", ambiguous) is None
    # Sin vocabulario solo hay abreviaturas, repeticiones y signos.
    assert normalize_question("cirujias x servicio").text == "cirujias por servicio"


def test_result_records_original_and_changes():
    result = normalize_question("cirujias x servicio??", VOCAB)
    assert result.original == "cirujias x servicio??"
    assert result.text == "cirugias por servicio?"
    kinds = [change["kind"] for change in result.changes]
    assert kinds == ["signos", "tipeo", "abreviatura"], result.changes
    lines = result.describe()
    assert any("«cirujias» → «cirugias»" in line for line in lines), lines
    assert result.to_dict()["normalized"] == result.text
    unchanged = normalize_question("cuantas camas hay", VOCAB)
    assert not unchanged.changed and unchanged.changes == []


# ---------------------------------------------------------------- 4) holdout + inventadas, vocabulario real
def _real_vocabulary():
    try:
        from tests.realistic.harness import resolve_data_root
        data_root = resolve_data_root()
    except Exception:
        return None
    vocabulary = vocabulary_for(data_root.parent, ROOT / "docs_tableros")
    return vocabulary if len(vocabulary.targets) > 500 else None


HOLDOUT = {
    # id: (pregunta del banco, normalizada esperada)
    "H02": ("como estan repartidas las camas x estado", "como estan repartidas las camas por estado"),
    "H03": ("cuantos medicamentos desabastesidos hay reportados",
            "cuantos medicamentos desabastecidos hay reportados"),
    "H10": ("en lo q va del año cuanto tiempo pasa un paciente en urgencias hasta que lo suben a hospitalizacion",
            "en lo que va del año cuanto tiempo pasa un paciente en urgencias hasta que lo suben a hospitalizacion"),
    "H11": ("como estuvo el tiempo pa egreso de urgencias en agosto comparado con septiembre",
            "como estuvo el tiempo para egreso de urgencias en agosto comparado con septiembre"),
    "H24": ("valor estimado x area de servicio", "valor estimado por area de servicio"),
    "H27b": ("cirujias canceladas en agosto vs septiembre, cual mes tuvo mas?",
             "cirugías canceladas en agosto vs septiembre, cual mes tuvo mas?"),
    "H29": ("q antibioticos se estan usando ahorita", "que antibioticos se estan usando ahorita"),
    "H31": ("kilos d ropa lavados en septiembre", "kilos de ropa lavados en septiembre"),
    "H35": ("pacientes naos x tipo de paciente", "pacientes naos por tipo de paciente"),
    "H38": ("por q estados pasa un pedido en recepcion tecnica?",
            "por que estados pasa un pedido en recepcion tecnica?"),
}

# Mismo estilo, inventadas (no están en ningún banco).
INVENTED = {
    "cuantos servicos tenemos x cada especialidad": "cuantos servicios tenemos por especialidad",
    "promedio d tiempo d triage x dia d la semana": "promedio de tiempo de triage por dia de la semana",
    "q tantas atenciones de hospitalisacion hubo en marso":
        "que tantas atenciones de hospitalización hubo en marzo",
    "holaaa cuantooos egresos hubooo ayer??": "hola cuantos egresos hubo ayer?",
    "ocupasion x piso": "ocupación por piso",
    "cant de remisiones xq no se aceptaron": "cantidad de remisiones porque no se aceptaron",
    "prom de estancia tb x aseguradora": "promedio de estancia también por aseguradora",
    "porcentage de ocupacion d la uci": "porcentaje de ocupacion de la uci",
    "cuantos pasientes hay en urgencias": "cuantos pacientes hay en urgencias",
}


def test_holdout_and_invented_phrases_with_the_real_catalog():
    vocabulary = _real_vocabulary()
    if vocabulary is None:
        print("      (sin data/ con catálogos: solo con el vocabulario de prueba)")
        vocabulary = VOCAB
        checks = {"camas x estado": "camas por estado", "kilos d ropa lavados": "kilos de ropa lavados"}
    else:
        checks = {**{q: e for q, e in HOLDOUT.values()}, **INVENTED}
    for text, expected in checks.items():
        got = normalize_question(text, vocabulary).text
        assert got == expected, (text, got)


def test_real_catalog_never_changes_well_written_bank_questions():
    """Ninguna pregunta bien escrita del banco de evaluación cambia por un
    «tipeo» (solo puede cambiar por abreviaturas, repeticiones o signos)."""
    vocabulary = _real_vocabulary()
    if vocabulary is None:
        return
    questions = []

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("question", "pregunta") and isinstance(value, str):
                    questions.append(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for bank in ("tests/eval/questions.json", "tests/eval/diccionario_preguntas.json",
                 "tests/real/banco_real.json", "tests/real/banco_holdout.json"):
        path = ROOT / bank
        if path.exists():
            walk(json.loads(path.read_text(encoding="utf-8")))
    assert len(questions) > 100, len(questions)
    typos = {}
    for question in questions:
        for change in normalize_question(question, vocabulary).changes:
            if change["kind"] == "tipeo":
                typos.setdefault(change["from"], change["to"])
    # Los únicos tipeos de los bancos son los del holdout.
    assert set(typos) <= {"desabastesidos", "cirujias"}, typos


# ---------------------------------------------------------------- 5) agrupación tras normalizar
def test_grouping_with_x_and_por_cada_after_normalization():
    from tests.resolution.test_grouping import builder, grouped

    b = builder()
    expected = [("PACIENTES X ASEGURADORA", "TERNOMCOM")]
    for question in ("total pacientes x aseguradora", "total pacientes por cada aseguradora",
                     "total pacientes x cada aseguradora", "total pacientes x aseguradoraaa"):
        text = normalize_question(question, VOCAB).text
        plan = b.build(text)
        assert plan["status"] == "ready", (question, text, plan.get("status"), plan.get("reason"))
        assert grouped(plan) == expected, (question, text, grouped(plan))


def test_por_cada_is_grouping_but_not_a_rate():
    assert norm("egresos por cada servicio") == "egresos por servicio"
    assert norm("egresos x cada servicio") == "egresos por servicio"
    assert norm("infecciones por cada 1000 dias cateter") == "infecciones por cada 1000 dias cateter"
    assert norm("consultas por cada una de las especialidades") == "consultas por cada una de las especialidades"


def test_x_tail_is_the_group_tail_after_normalization():
    from tests.resolution.test_grouping import builder

    b = builder()
    for question, tail in (("valor estimado x area de servicio", "area de servicio"),
                           ("pacientes naos x tipo de paciente", "tipo de paciente"),
                           ("egresos x cada especialidad hoy", "especialidad")):
        got = b._requested_group_tail(normalize_question(question, VOCAB).text)
        assert got == tail, (question, got)


def test_periods_after_normalization():
    """H10: con «q» el periodo «en lo que va del año» se perdía; H08/H31: mes
    sin año = su ocurrencia más reciente (no todos los años, no futura)."""
    from datetime import date

    from src.semantic.period_parser import PeriodParser
    from src.semantic.query_plan_builder import normalize_text

    parser = PeriodParser(date(2026, 11, 3))

    def span(text):
        period = parser.parse(normalize_text(normalize_question(text, VOCAB).text))
        return (str(period["start"]), str(period["end"])) if period else None

    assert span("en lo q va del año cuanto tiempo pasa un paciente en urgencias") == ("2026-01-01", "2026-11-04")
    assert span("kilos d ropa lavados en septiembre") == ("2026-09-01", "2026-10-01")
    assert span("egresos x servicio en diciembre") == ("2025-12-01", "2026-01-01")
    assert span("cirujias d este mes") == ("2026-11-01", "2026-11-04")
    assert span("triages q van hoy") == ("2026-11-03", "2026-11-04")
    assert span("egresos d ayer x servicio") == ("2026-11-02", "2026-11-03")
    assert span("consultas pa la semana pasada") == ("2026-10-26", "2026-11-02")


# ---------------------------------------------------------------- 6) punto de entrada
class _RecordingEngine(QueryEngine):
    def __init__(self, project_root):
        super().__init__(
            conversation_manager=None, master_metric_resolver=None,
            master_metric_dax_generator=None, metric_resolver=None,
            filter_resolver=None, business_filter_resolver=None,
            dax_generator=None, dax_validator=None,
            powerbi_provider=None, rag_answer_engine=None,
            query_plan_builder=type("B", (), {"project_root": project_root})(),
        )
        self.seen = []

    def _process_turn(self, message):
        self.seen.append(message)
        self._think("Turno de prueba", message)
        return {"status": "success", "route": "rag", "answer": "ok"}


def test_engine_normalizes_once_at_the_entry_and_traces_both_texts():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        md = root / "docs_tableros" / "tablero_quirurgico" / "md"
        md.mkdir(parents=True)
        (md / "_diccionario.md").write_text(
            "---\ntablero: TABLERO QUIRURGICO\n---\n# DICCIONARIO\n"
            "- **CIRUGIAS CANCELADAS**: Cirugías canceladas por servicio.\n", encoding="utf-8")
        qn._build_vocabulary.cache_clear()
        engine = _RecordingEngine(root)
        result = engine.process("cirujias canceladas x servicio")
        assert engine.seen == ["cirugías canceladas por servicio"], engine.seen
        assert result["normalized_question"]["original"] == "cirujias canceladas x servicio"
        assert result["normalized_question"]["normalized"] == "cirugías canceladas por servicio"
        steps = json.dumps(result["reasoning"], ensure_ascii=False)
        assert "Pregunta normalizada" in steps and "cirujias canceladas x servicio" in steps, steps
        # Sin cambios no hay paso ni campo extra.
        result = engine.process("cirugías canceladas por servicio")
        assert "normalized_question" not in result
        assert "Pregunta normalizada" not in json.dumps(result["reasoning"], ensure_ascii=False)
        qn._build_vocabulary.cache_clear()


def test_engine_survives_a_broken_vocabulary_root():
    engine = _RecordingEngine(object())
    result = engine.process("camas x estado")
    assert engine.seen == ["camas por estado"], engine.seen
    assert result["status"] == "success"


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
