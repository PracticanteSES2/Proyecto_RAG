"""
Mide cuántas consultas DAX lanza el chatbot por turno (arnés realista) y cuánto
tardarían contra Power BI real.

    python -m tests.perf.medir_consultas --out C:/tmp/antes.json
    python -m tests.perf.medir_consultas --out C:/tmp/despues.json --latencia-ms 500
    python -m tests.perf.medir_consultas --comparar C:/tmp/antes.json C:/tmp/despues.json

Tiempo estimado por turno con el modelo de coste del simulador
(tests/realistic/powerbi_sim/cost.py; activo salvo con --sin-coste): latencia
base por consulta (--latencia-ms) + coste por la cardinalidad «real» de cada
columna explorada con VALUES + filas devueltas; las consultas que superan el
CommandTimeout de exploración se cancelan como en ADOMD. Sin dormir de verdad.

Recorre el banco tests/eval/questions.json (los casos aplicables al arnés
realista) y además la conversación del propietario (2026-10-13). Por cada turno
guarda: entrada, respuesta de la UI, botones, resumen del resultado, la lista de
consultas DAX del turno clasificadas (`dominio` = VALUES de una columna,
`dominio_lote` = varias columnas en una consulta, `medida` = el resto) y el
tiempo estimado = consultas × latencia (sin dormir de verdad; para dormir de
verdad usa SIM_DAX_LATENCY_MS en el simulador).

`--comparar` compara dos corridas caso por caso (respuesta, botones, estado,
filtros y DAX final) y resume consultas/turno y tiempo estimado antes/después.

`--escenario propietario_2026_10_14` usa la calibración del turno real de ese día
(tests/realistic/powerbi_sim/cost.py: cardinalidad cara, apertura de conexión) y
`--reproducir` agrega la exploración de los dos turnos del propietario de ese día
(mismas columnas, mismo orden que la búsqueda incremental de QueryPlanBuilder,
con la conexión del modelo recién abierta) en dos turnos seguidos: el primero
con la caché fría y el siguiente (lo que vuelve a pagar el turno siguiente).
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Conversación del propietario con Power BI real (tests/eval/out/transcripts/propietario_2026-10-13.md).
PROPIETARIO = {
    "id": "propietario_2026_10_13",
    "category": "i_multiturno",
    "turns": [
        {"user": "De urgencias se me ha solicitado saber la cantidad de pacientes que tiene cada una de "
                 "las especialidades en hospitalizacion en este mes"},
        {"button": {"label_any": ["CANTIDAD DE PACIENTES"]}},
        {"user": "Cuantos de esos 33 tiene cada especialidad?"},
        {"button": {"label_any": ["CANTIDAD ATENCIONES POR ESPECIALIDAD"]}},
    ],
    "fuente": {"docx": "transcripción del propietario"},
}


# Turno 4 de esa conversación (el de 14,94 s): elegir el indicador de atenciones
# de UNIDAD_CARDIOVASCULAR para «Cuantos de esos 33 tiene cada especialidad?».
# En los datos locales el indicador SUM('UNIDAD_CARDIOVASCULAR'[CANTIDAD]) es
# ATENCIONES [cf9ee1762dc092fc]; se inyecta la contrapregunta pendiente y se
# pulsa el botón (mismo camino que _run_selected_metric).
ELECCION_PROPIETARIO = {
    "id": "propietario_eleccion_turno4",
    "question": "Cuantos de esos 33 tiene cada especialidad?",
    "metric_id": "cf9ee1762dc092fc",
    "label": "CANTIDAD ATENCIONES POR ESPECIALIDAD",
}


# Exploración de los turnos del propietario del 2026-10-14 (Power BI real): columnas
# del razonamiento, en su orden. Su catálogo es más nuevo que el local, así que no
# se llega a ellas con las mismas preguntas: se reproduce la búsqueda incremental.
REPRODUCCIONES = [
    {
        "id": "propietario_2026_10_14_ocupacion",
        "modelo": "BRIEFING HOSPITALARIO",
        "pregunta": "necesito saber la ocupacion general hoy en el hospital",
        "columnas": [("SERVICIOS", "NOM_SERV"), ("CAMAS DISPONIBLES", "ESTADOS_CAM"),
                     ("CAMAS DISPONIBLES", "SERVICIOS"), ("CAMAS DISPONIBLES", "HCACODIGO"),
                     ("SERVICIOS", "HSUNOMBRE")],
        # Turno 3: otra pregunta del mismo modelo (otras columnas, conexión ya abierta).
        "otras_columnas": [("PACIENTES X ASEGURADORA", "TERNOMCOM"), ("PACIENTES X ASEGURADORA", "HSUNOMBRE"),
                           ("PACIENTES X ASEGURADORA", "HCACODIGO"), ("SOLICITUD CAMAS", "GDPNOMBRE")],
    },
    {
        "id": "propietario_2026_10_14_demanda",
        "modelo": "DEMANDA INSATISFECHA",
        "pregunta": "cuántas camas hay disponibles en hospitalización general",
        "columnas": [("SOLICITUD_CAMAS", "aseguradora"), ("TERCEROS", "TERNOMCOM"),
                     ("SOLICITUD_CAMAS", "GDPNOMBRE")],
        "otras_columnas": [("TRIAGES", "TERNOMCOM"), ("CIRUGIAS", "TERNOMCOM"), ("SOLICITUD_CAMAS", "HSUNOMBRE")],
    },
]


def clasificar(dax):
    """Tipo de consulta DAX: dominio de valores (VALUES), lote de dominios,
    cardinalidad de columnas (COUNTROWS(VALUES())) o medida."""
    text = " ".join(str(dax or "").split())
    if '"__card' in text:
        return "cardinalidad"
    if "__dominio_lote" in text or "\"__columna\"" in text:
        return "dominio_lote"
    if "VALUES(" in text and "\"Value\"" in text and "TOPN(" in text:
        return "dominio"
    return "medida"


def _turn_signature(turn):
    result = turn.get("result") or {}
    return {
        "ui": turn.get("ui"),
        "buttons": [(b.get("id"), b.get("label")) for b in turn.get("buttons") or []],
        "status": result.get("status"),
        "route": result.get("route"),
        "metric": result.get("metric"),
        "semantic_model": result.get("semantic_model"),
        "filters": result.get("filters"),
        "unapplied_terms": result.get("unapplied_terms"),
        "dax": result.get("dax"),
        "passed": turn.get("passed"),
    }


def vaciar_cachés(engine):
    """Olvida los dominios de valores ya consultados (como una app recién
    arrancada): sirve para medir el peor caso, con la caché fría en cada caso."""
    builder = getattr(engine, "query_plan_builder", None)
    for holder in (builder, getattr(engine, "query_semantic_planner", None)):
        if holder is None:
            continue
        for name in ("value_cache", "domain_errors", "_value_token_cache"):
            store = getattr(holder, name, None) if name in vars(holder) else None
            if hasattr(store, "clear"):
                store.clear()
    business = getattr(engine, "business_filter_resolver", None)
    for resolver in (getattr(business, "_cache", None) or {}).values():
        for name in ("value_cache", "domain_cache_loaded"):
            store = getattr(resolver, name, None)
            if hasattr(store, "clear"):
                store.clear()
    provider = getattr(engine, "powerbi_provider", None)
    cache = getattr(provider, "domain_cache", None)
    if cache is not None and hasattr(cache, "clear"):
        cache.clear()


def _estimado(consultas, latencia_ms):
    """Segundos estimados del turno: con el modelo de coste, la suma de cost_ms;
    sin él, consultas × latencia fija."""
    if consultas and all(q.get("cost_ms") is not None for q in consultas):
        return round(sum(q["cost_ms"] + (q.get("apertura_ms") or 0) for q in consultas) / 1000.0, 2)
    return round(len(consultas) * latencia_ms / 1000.0, 2)


def _entrada(e):
    return {"tipo": clasificar(e.get("dax")), "modelo": e.get("semantic_model"),
            "filas": e.get("rows"), "error": bool(e.get("error")),
            "cost_ms": e.get("cost_ms"), "timed_out": bool(e.get("timed_out")),
            "apertura_ms": e.get("apertura_ms"), "timeout_s": e.get("timeout_s"),
            "cost_detail": e.get("cost_detail"),
            "dax": " ".join(str(e.get("dax") or "").split())[:400]}


def _turno(case, turn, text, consultas, latencia_ms, signature=None, reasoning=""):
    por_tipo = {}
    for q in consultas:
        por_tipo[q["tipo"]] = por_tipo.get(q["tipo"], 0) + 1
    return {
        "case": case, "turn": turn, "input": text, "signature": signature or {},
        "consultas": len(consultas), "por_tipo": por_tipo,
        "estimado_s": _estimado(consultas, latencia_ms),
        "canceladas": sum(1 for q in consultas if q.get("timed_out")),
        "dax_log": consultas, "reasoning_head": reasoning,
    }


def reproducir(system, spec, latencia_ms):
    """Exploración de un turno del propietario (REPRODUCCIONES) en dos turnos
    seguidos sobre el mismo proveedor: búsqueda incremental como
    QueryPlanBuilder._resolve_implicit_filter (antes de leer cada columna, si no
    está en caché, `prefetch(resto, max_batches=1, lead=True)`; luego `get`).
    El primero con la caché vacía y la conexión del modelo recién abierta."""
    from src.providers.domain_cache import domain_cache_for
    from tests.realistic import harness

    engine = system[0]
    provider = engine.powerbi_provider
    backend = harness.STATE["backend"]
    cache = domain_cache_for(provider)
    vaciar_cachés(engine)
    try:
        provider._invalidate_connection(spec["modelo"])   # primera consulta del modelo
    except Exception:  # noqa: BLE001
        pass
    model = spec["modelo"]
    turnos = []
    rondas = [(1, spec["columnas"]), (2, spec["columnas"])]
    if spec.get("otras_columnas"):
        rondas.append((3, spec["otras_columnas"]))
    for numero, ref in rondas:
        columns = [(table, column, "Text") for table, column in ref]
        start = len(backend.log["dax"])
        try:
            cache.begin_turn(question=spec["pregunta"])
        except TypeError:   # versión sin contexto de la pregunta
            cache.begin_turn()
        for position, (table, column, _) in enumerate(columns):
            if cache.cached(model, table, column) is None:
                cache.prefetch(model, columns[position:], max_batches=1, lead=True)
            cache.get(model, table, column)
        lines = cache.describe_turn() or []
        cache.end_turn()
        consultas = [_entrada(e) for e in backend.log["dax"][start:]]
        cuando = {1: "frío", 2: "siguiente", 3: "otras columnas del modelo"}[numero]
        texto = f"[exploración reproducida, turno {cuando}] {spec['pregunta']}"
        turnos.append(_turno(spec["id"], numero, texto, consultas, latencia_ms, reasoning="\n".join(lines)))
        print(f"[ R  ] {spec['id']}#{numero} · consultas {len(consultas)} · {turnos[-1]['estimado_s']} s", flush=True)
    return turnos


def correr(case_ids=None, latencia_ms=500, incluir_propietario=True, frio=False, solo_propietario=False,
           coste=True, escenario=None, reproducciones=False):
    import os

    from tests.eval import run as runner
    from tests.realistic import harness

    # Modelo de coste (sin dormir): lo lee el backend del simulador al construirse.
    os.environ["SIM_DAX_COST"] = "1" if coste else "0"
    os.environ["SIM_DAX_BASE_MS"] = str(latencia_ms)
    os.environ.pop("SIM_DAX_LATENCY_MS", None)
    if escenario:
        from tests.realistic.powerbi_sim.cost import ESCENARIOS
        os.environ.update(ESCENARIOS[escenario])

    data = runner.load_questions()
    cases = runner.select_cases(data, (), tuple(case_ids or ()), "realistic", only_applicable=True)
    if incluir_propietario and not case_ids:
        cases = [PROPIETARIO] if solo_propietario else list(cases) + [PROPIETARIO]
    if reproducciones == "solo":
        cases, incluir_propietario = [], False

    captured = []
    original_ask, original_choose = harness.ask, harness.ask_option

    def _capture(result):
        entries = list(((result or {}).get("_sim") or {}).get("dax_log") or [])
        captured.append([_entrada(e) for e in entries])

    def ask(*args, **kwargs):
        result, ui = original_ask(*args, **kwargs)
        _capture(result)
        return result, ui

    def ask_option(*args, **kwargs):
        result, ui = original_choose(*args, **kwargs)
        _capture(result)
        return result, ui

    harness.ask, harness.ask_option = ask, ask_option
    started = time.perf_counter()
    system = runner.build_system(harness, "realistic", "fake")
    turnos = []
    casos = []
    for number, case in enumerate(cases, 1):
        captured.clear()
        if frio:
            vaciar_cachés(system[0])
        outcome =runner.run_case(case, system, harness, harness_name="realistic")
        queries = list(captured)
        casos.append({"id": case["id"], "passed": outcome.get("passed"), "outcome": outcome.get("outcome")})
        q_index = 0
        for turn in outcome.get("turns") or []:
            if turn.get("skipped"):
                consultas = []
            else:
                consultas = queries[q_index] if q_index < len(queries) else []
                q_index += 1
            por_tipo = {}
            for q in consultas:
                por_tipo[q["tipo"]] = por_tipo.get(q["tipo"], 0) + 1
            turnos.append({
                "case": case["id"], "turn": turn.get("index"), "input": turn.get("input"),
                "signature": _turn_signature(turn),
                "consultas": len(consultas), "por_tipo": por_tipo,
                "estimado_s": _estimado(consultas, latencia_ms),
                "canceladas": sum(1 for q in consultas if q.get("timed_out")),
                "latency_s": turn.get("latency_s"),
                "dax_log": consultas,
                "reasoning_head": "\n".join((turn.get("reasoning") or "").splitlines()[:6]),
            })
        print(f"[{number:3d}/{len(cases)}] {'OK  ' if outcome.get('passed') else 'FAIL'} {case['id']}"
              f" · consultas {sum(len(q) for q in queries)}", flush=True)
    if incluir_propietario and not case_ids:
        turnos.append(_eleccion_propietario(system, harness, ask_option, captured, latencia_ms, frio))
    harness.ask, harness.ask_option = original_ask, original_choose
    if reproducciones:
        for spec in REPRODUCCIONES:
            turnos.extend(reproducir(system, spec, latencia_ms))
    return {"latencia_ms": latencia_ms, "frio": frio, "coste": coste, "escenario": escenario,
            "elapsed_s": round(time.perf_counter() - started, 1), "casos": casos, "turnos": turnos}


def _eleccion_propietario(system, harness, ask_option, captured, latencia_ms, frio):
    from src.chatbot.response_formatter import clarification_buttons

    engine, cm, formatter = system[0], system[1], system[2]
    spec = ELECCION_PROPIETARIO
    harness.new_conversation(engine, cm)
    if frio:
        vaciar_cachés(engine)
    engine._pending_query_plan = {
        "type": "query_plan_metric", "question": spec["question"],
        "choices": [{"id": spec["metric_id"], "label": spec["label"]}], "excluded": [],
    }
    captured.clear()
    result, ui = ask_option(engine, cm, formatter, spec["metric_id"], spec["label"])
    harness.new_conversation(engine, cm)
    consultas = captured[0] if captured else []
    por_tipo = {}
    for q in consultas:
        por_tipo[q["tipo"]] = por_tipo.get(q["tipo"], 0) + 1
    buttons = clarification_buttons(result) if result.get("status") == "needs_clarification" else []
    from tests.eval import run as runner
    summary = runner._summary_of_result(result)
    print(f"[ +  ] {spec['id']} · consultas {len(consultas)}", flush=True)
    return {
        "case": spec["id"], "turn": 1, "input": f"[botón inyectado] {spec['label']}",
        "signature": _turn_signature({"ui": ui, "buttons": buttons, "result": summary, "passed": None}),
        "consultas": len(consultas), "por_tipo": por_tipo,
        "estimado_s": _estimado(consultas, latencia_ms),
        "canceladas": sum(1 for q in consultas if q.get("timed_out")),
        "dax_log": consultas,
    }


def _p95(values):
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]


def _exploracion_s(turno):
    """Segundos estimados de las consultas de exploración (dominios y cardinalidad)."""
    return sum((q.get("cost_ms") or 0) for q in turno.get("dax_log") or []
               if q.get("tipo") != "medida") / 1000.0


def resumen(data, top=12):
    turnos = data["turnos"]
    counts = [t["consultas"] for t in turnos]
    lat = data.get("latencia_ms", 500)
    dominios = [t["por_tipo"].get("dominio", 0) + t["por_tipo"].get("dominio_lote", 0) for t in turnos]
    tiempos = [t.get("estimado_s", 0) for t in turnos]
    exploracion = [_exploracion_s(t) for t in turnos]
    modelo = "modelo de coste" if data.get("coste") else f"{lat} ms/consulta"
    lines = [
        f"turnos: {len(turnos)} · consultas totales: {sum(counts)} "
        f"(dominio {sum(dominios)}, cardinalidad {sum(t['por_tipo'].get('cardinalidad', 0) for t in turnos)}, "
        f"medida {sum(t['por_tipo'].get('medida', 0) for t in turnos)})",
        f"consultas/turno: media {statistics.mean(counts):.2f} · p95 {_p95(counts)} · máx {max(counts)}",
        f"tiempo estimado ({modelo}, base {lat} ms): media {statistics.mean(tiempos):.2f} s · "
        f"p95 {_p95(tiempos):.2f} s · máx {max(tiempos):.2f} s · total {sum(tiempos):.1f} s",
        f"  de ello exploración: media {statistics.mean(exploracion):.2f} s · p95 {_p95(exploracion):.2f} s · "
        f"máx {max(exploracion):.2f} s · total {sum(exploracion):.1f} s",
        f"consultas canceladas por tiempo: {sum(t.get('canceladas', 0) for t in turnos)}",
        f"casos que pasan: {sum(1 for c in data['casos'] if c['passed'])}/{len(data['casos'])}",
        "peores turnos (tiempo estimado):",
    ]
    for t in sorted(turnos, key=lambda t: -t.get("estimado_s", 0))[:top]:
        lines.append(f"  {t.get('estimado_s', 0):6.2f} s {t['consultas']:3d} ({t['por_tipo']}) "
                     f"{t['case']}#{t['turn']}: {str(t['input'])[:80]}")
    prop = [t for t in turnos if t["case"] in (PROPIETARIO["id"], ELECCION_PROPIETARIO["id"])
            or t["case"] in {spec["id"] for spec in REPRODUCCIONES}]
    if prop:
        lines.append("propietario:")
        for t in prop:
            lines.append(f"  {t['case']}#{t['turn']} {t.get('estimado_s', 0):6.2f} s {t['consultas']:3d} "
                         f"({t['por_tipo']}) {str(t['input'])[:80]}")
    return "\n".join(lines)


def _medidas(turno):
    return [q["dax"] for q in turno.get("dax_log") or [] if q.get("tipo") == "medida"]


def comparar(antes, despues):
    a = {(t["case"], t["turn"]): t for t in antes["turnos"]}
    d = {(t["case"], t["turn"]): t for t in despues["turnos"]}
    diffs = []
    for key in sorted(set(a) | set(d), key=lambda k: (k[0], k[1] or 0)):
        ta, td = a.get(key), d.get(key)
        if ta is None or td is None:
            diffs.append((key, "turno ausente en una corrida"))
            continue
        # La DAX del resumen incluye las consultas de dominio (cambian con el
        # lote); se comparan solo las consultas de medidas (las que responden).
        changed = [k for k in ta["signature"] if k != "dax" and ta["signature"][k] != td["signature"].get(k)]
        if _medidas(ta) != _medidas(td):
            changed.append("dax_medidas")
        if changed:
            diffs.append((key, changed))
    lines = ["== ANTES ==", resumen(antes), "", "== DESPUÉS ==", resumen(despues), "",
             f"turnos con diferencias: {len(diffs)}"]
    for key, what in diffs:
        lines.append(f"  {key[0]}#{key[1]}: {what}")
    return "\n".join(lines), diffs


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", help="JSON de salida con las consultas por turno")
    parser.add_argument("--case", action="append", help="id(s) de caso (por defecto todo el banco aplicable)")
    parser.add_argument("--latencia-ms", type=int, default=500)
    parser.add_argument("--sin-propietario", action="store_true")
    parser.add_argument("--solo-propietario", action="store_true",
                        help="solo la conversación del propietario (y la elección inyectada)")
    parser.add_argument("--frio", action="store_true",
                        help="vacía las cachés de dominios antes de cada caso (peor caso: app recién arrancada)")
    parser.add_argument("--sin-coste", action="store_true",
                        help="sin el modelo de coste: tiempo = consultas × latencia fija")
    parser.add_argument("--escenario", choices=["propietario_2026_10_13", "propietario_2026_10_14"],
                        help="calibración del modelo de coste (tests/realistic/powerbi_sim/cost.py)")
    parser.add_argument("--reproducir", action="store_true",
                        help="agrega la exploración reproducida de los turnos del propietario del 2026-10-14")
    parser.add_argument("--solo-reproducir", action="store_true",
                        help="solo la exploración reproducida (sin el banco)")
    parser.add_argument("--comparar", nargs=2, metavar=("ANTES", "DESPUES"))
    args = parser.parse_args(argv)
    if args.comparar:
        antes, despues = (json.loads(Path(p).read_text(encoding="utf-8")) for p in args.comparar)
        text, diffs = comparar(antes, despues)
        print(text)
        return 1 if diffs else 0
    ids = [c.strip() for v in args.case or [] for c in v.split(",") if c.strip()]
    data = correr(ids, args.latencia_ms, not args.sin_propietario, frio=args.frio,
                  solo_propietario=args.solo_propietario, coste=not args.sin_coste,
                  escenario=args.escenario,
                  reproducciones="solo" if args.solo_reproducir else args.reproducir)
    if args.out:
        Path(args.out).write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(resumen(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
