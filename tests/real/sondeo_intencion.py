"""
Sondeo del extractor de intención con MedGemma REAL (src/semantic/intencion_llm.py).

Para cada pregunta (banco holdout 2 + 20 preguntas nuevas de este archivo) arma el catálogo acotado
con el motor (plan de reglas + embeddings + léxico), llama SOLO al extractor (MedGemma real, mismo
prompt que la app) y valida la intención con el motor. Por defecto solo llama al LLM donde la app lo
llamaría (modo respaldo), EN SERIE y con una pausa entre llamadas (--pausa, 2 s); ante una falla del
servidor (504, runner caído, tiempo agotado) espera con backoff y, si se repite, CORTA el sondeo y
guarda lo hecho: el servidor de MedGemma es compartido. No ejecuta la consulta final:
guarda la salida cruda, la intención, la validación (con el DAX que se generaría) y los tiempos.

    python -X utf8 -m tests.real.sondeo_intencion                      # holdout 2 + nuevas
    python -X utf8 -m tests.real.sondeo_intencion --solo G16,N03
    python -X utf8 -m tests.real.sondeo_intencion --solo-nuevas
    python -X utf8 -m tests.real.sondeo_intencion --pausa 5             # más pausa entre llamadas
    python -X utf8 -m tests.real.sondeo_intencion --todas               # también donde la app no llamaría
    python -X utf8 -m tests.real.sondeo_intencion --sim                # sin producción (LLM falso): prueba el script

Se ejecuta desde la raíz del checkout PRINCIPAL (lee su .env con load_dotenv, como app.py; nunca se
imprime). Power BI de producción en SOLO LECTURA: el plan de reglas y la validación de valores
consultan dominios de columnas (VALUES), igual que la app. MedGemma: no se modifica el servidor.

Salida (no versionada): var/out/sondeo_intencion/sondeo_<fecha>/resultados.json y resumen.md.
Sondeo de un uso (ciclo 2 del extractor): pasa a tools/manual cuando el doctor admita la excepción
tools/manual -> tests (docs/ARQUITECTURA.md, fase 6).
"""
import argparse
import json
import re
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.comun.rutas import ruta_salida  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = ruta_salida("sondeo_intencion")
BANCO = HERE / "banco_holdout2.json"

# Preguntas NUEVAS (no están en ningún banco): paráfrasis, sinónimos de negocio, comparaciones entre
# periodos, rankings, exclusiones y una fuera de alcance (debe salir indicador_id null).
NUEVAS = [
    ("N01", "cuantas operaciones se hicieron en julio"),
    ("N02", "el numero de partos por cesarea subio o bajo de agosto a septiembre"),
    ("N03", "que eps tiene mas pacientes hospitalizados ahorita"),
    ("N04", "las 3 areas que mas ropa mandaron a lavar en agosto"),
    ("N05", "se demoraron mas en dar de alta en agosto o en septiembre"),
    ("N06", "cuantos pacientes llegaron por urgencias la semana pasada"),
    ("N07", "como le fue a la ocupacion de camas este mes frente al mes pasado"),
    ("N08", "en que servicio hay mas camas desocupadas"),
    ("N09", "cuanto se facturo en octubre sin contar sura"),
    ("N10", "cuantos triages se quedaron sin atender en septiembre"),
    ("N11", "que medicamentos estan por vencerse"),
    ("N12", "cuantas citas se cancelaron en octubre"),
    ("N13", "el tiempo de respuesta de las interconsultas mejoro de septiembre a octubre"),
    ("N14", "cuantos ninos nacieron en 2025"),
    ("N15", "que tan llena esta la uci"),
    ("N16", "cuantas tomografias se hicieron este ano"),
    ("N17", "hubo mas egresos en junio o en julio de 2026"),
    ("N18", "los 5 diagnosticos mas frecuentes en los egresos de 2025"),
    ("N19", "cuantas dosis de antibiotico se pusieron en la uci neonatal en octubre"),
    ("N20", "cual es la capital de francia"),
]


def _cases(args):
    cases = []
    if not args.solo_nuevas:
        data = json.loads(Path(args.banco or BANCO).read_text(encoding="utf-8"))
        for case in data.get("casos") or []:
            truth = case.get("verdad") or {}
            cases.append({"id": case["id"], "origen": "holdout2", "pregunta": case["pregunta"],
                          "tipo": case.get("tipo"), "verdad_dax": truth.get("dax"),
                          "verdad_modelo": truth.get("modelo")})
    if args.banco:
        return [case for case in cases if not args.solo or case["id"].upper() in {i.strip().upper() for i in args.solo.split(",")}]
    cases += [{"id": key, "origen": "nueva", "pregunta": text, "tipo": None, "verdad_dax": None,
               "verdad_modelo": None} for key, text in NUEVAS]
    if args.solo:
        wanted = {item.strip().upper() for item in args.solo.split(",") if item.strip()}
        cases = [case for case in cases if case["id"].upper() in wanted]
    return cases


def _system(sim):
    if sim:
        from tests.realistic import harness
        engine, cm, formatter, llm_status, connection, _ = harness.build_engine(llm="fake")
        return engine, dict(llm_status or {})
    from tests.real import run_real
    system = run_real.build_system()
    return system["engine"], system["medgemma"]


def _normalized(engine, question):
    """La pregunta como la ve el motor (lenguaje de chat normalizado, igual que QueryEngine.process)."""
    try:
        from src.semantic.question_normalizer import normalize_question, vocabulary_for
        root = getattr(engine.query_plan_builder, "project_root", None)
        normalized = normalize_question(question, vocabulary_for(root))
        return str(getattr(normalized, "text", None) or question)
    except Exception:
        return question


def _plan_summary(engine, plan):
    if not isinstance(plan, dict):
        return None
    metric = plan.get("metric") or {}
    summary = {
        "indicador": metric.get("label"), "metric_id": metric.get("metric_id"),
        "modelo": plan.get("semantic_model"),
        "filtros": [
            {k: item.get(k) for k in ("table", "column", "value", "values", "negated", "label", "start", "end")
             if item.get(k) not in (None, [], "")} for item in plan.get("filters") or []
        ],
        "agrupacion": [f"{g.get('table')}[{g.get('column')}]" for g in plan.get("group_by") or []],
        "periodos_comparados": [b.get("label") for b in plan.get("temporal_buckets") or []] if plan.get("comparison") else None,
        "ranking": plan.get("ranking"),
        "notas": plan.get("notes") or [],
    }
    try:
        generator = engine.query_plan_dax_generator
        generated = generator.generate_ranked(plan) if plan.get("ranking") else generator.generate(plan)
        summary["dax"] = generated.get("dax") or generated
    except Exception as error:
        summary["dax"] = f"(no se generó: {type(error).__name__}: {error})"
    return summary


def _prepare(engine, case, wait_index):
    """Plan de reglas + catálogo + si la app llamaría al LLM (respaldo) para esta pregunta."""
    from src.semantic import intencion_llm as IL
    from src.semantic import plan_budget

    builder = engine.query_plan_builder
    question = _normalized(engine, case["pregunta"])
    started = time.perf_counter()
    plan_budget.start()
    try:
        rules = builder.build(question)
    except BaseException as error:  # PlanBudgetExceeded hereda de BaseException
        rules = {"status": "error", "error": f"{type(error).__name__}: {error}"}
    finally:
        plan_budget.clear()
    rules_s = round(time.perf_counter() - started, 2)
    motivo = IL.motivo_llamada("respaldo", rules, question)
    try:
        descriptive = bool(builder.is_descriptive(question))
    except Exception:
        descriptive = False
    try:
        # La app solo arma el Query Plan (y por tanto solo llama al LLM) si la pregunta pide un dato
        # (looks_numeric) o el analizador de intención la marca como consulta: aproximación.
        numeric = bool(builder.looks_numeric(question, dashboard=None))
    except Exception:
        numeric = True
    started = time.perf_counter()
    catalog = IL.armar_catalogo(builder, question, rules, encoder=engine._intent_encoder(),
                                esperar_indice_s=wait_index)
    catalog_s = round(time.perf_counter() - started, 2)
    return {
        "pregunta_normalizada": question,
        "reglas": {"status": rules.get("status"), "reason": rules.get("reason"),
                   "indicador": (rules.get("metric") or {}).get("label"), "segundos": rules_s},
        "motivo_respaldo": motivo,
        "descriptiva": descriptive,
        "pide_dato": numeric,
        # Lo que haría la app en modo respaldo (QueryEngine._intent_llm_plan), aproximado.
        "llamaria_en_respaldo": bool(motivo) and not descriptive and numeric,
        "catalogo": catalog.resumen(),
        "catalogo_segundos": catalog_s,
        "prompt_caracteres": catalog.caracteres,
        "_catalog": catalog,
        "_permitidos": IL.opciones_permitidas(builder, rules),
    }


def _validate(engine, item, extraction):
    from src.semantic import intencion_llm as IL

    if extraction.get("intencion") is None:
        return {"status": "sin_intencion"}
    builder = engine.query_plan_builder
    started = time.perf_counter()
    validation = IL.validar_intencion(builder, item["pregunta_normalizada"], extraction["intencion"],
                                      item["_catalog"], permitidos=item.get("_permitidos"))
    summary = _plan_summary(engine, validation["plan"]) if validation["plan"] else None
    return {
        "status": validation["status"], "motivo": validation["motivo"], "aceptado": validation["aceptado"],
        "descartado": validation["descartado"], "segundos": round(time.perf_counter() - started, 2),
        "plan": summary,
        "frente_a_verdad": _against_truth(validation["plan"], item.get("verdad_dax")) if validation["plan"] else None,
    }


_REF_RE = re.compile(r"'?([A-Za-z_][^'\[\](),]*?)'?\[([^\]]+)\]")


def _refs(text):
    return {(t.strip().lower(), c.strip().lower()) for t, c in _REF_RE.findall(str(text or ""))}


def _against_truth(plan, truth):
    """Comparación aproximada con el DAX de verdad del banco (sin ejecutar nada): ¿la medida o sus
    columnas están en la verdad? ¿las columnas agrupadas y filtradas también?"""
    if not truth or not plan:
        return None
    metric = plan.get("metric") or {}
    truth_l = str(truth).lower()
    truth_refs = _refs(truth)
    measure = str(metric.get("measure") or "").strip().lower()
    expression_refs = _refs(metric.get("model_expression") or metric.get("base_dax_expression") or metric.get("dax_expression"))
    indicator = bool(measure and f"[{measure}]" in truth_l) or bool(expression_refs and expression_refs & truth_refs)
    groups = [(str(g.get("table")).lower(), str(g.get("column")).lower()) for g in plan.get("group_by") or []
              if g.get("source") != "query_plan_temporal_group"]
    filters = [(str(f.get("table")).lower(), str(f.get("column")).lower()) for f in plan.get("filters") or []
               if f.get("type") == "categorical" and f.get("source") == "intencion_llm"]
    return {
        "indicador": indicator,
        "agrupacion": all(g in truth_refs for g in groups) if groups else None,
        "filtros": all(f in truth_refs for f in filters) if filters else None,
    }


def _summary_md(meta, rows):
    called = [r for r in rows if r["extraccion"].get("llamadas")]
    valid = [r for r in rows if r["validacion"].get("status") == "valid"]
    right = [r for r in valid if ((r["validacion"].get("frente_a_verdad") or {}).get("indicador"))]
    lines = [
        "# Sondeo del extractor de intención (MedGemma)", "",
        f"- **fecha:** {meta['fecha']} · **MedGemma:** {meta['medgemma']}",
        f"- **casos:** {len(rows)} · **la app llamaría al LLM (respaldo):** "
        f"{sum(1 for r in rows if r.get('llamaria_en_respaldo'))} · **llamados:** {len(called)}"
        f" · **pausa:** {meta['pausa_s']} s" + (f" · **CORTADO:** {meta['cortado']}" if meta.get("cortado") else ""),
        f"- **JSON válido:** {sum(1 for r in rows if r['extraccion']['status'] == 'ok')}/{len(called)}"
        f" · **validados:** {len(valid)} · **indicador como la verdad (aprox.):** {len(right)}/{len(valid)}",
        f"- **prompt (caracteres):** media {meta['prompt_media']} · máx {meta['prompt_max']}",
        f"- **tiempo LLM (s):** media {meta['llm_media_s']} · p95 {meta['llm_p95_s']} · máx {meta['llm_max_s']}", "",
        "| id | pregunta | reglas | app llama | LLM | s | validación | indicador | ¿verdad? | agrupación / periodos | motivo |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        plan = (row["validacion"] or {}).get("plan") or {}
        intent = row["extraccion"].get("intencion") or {}
        truth = (row["validacion"] or {}).get("frente_a_verdad") or {}
        extra = ", ".join(plan.get("agrupacion") or []) or ", ".join(plan.get("periodos_comparados") or []) or ""
        lines.append("| " + " | ".join(str(part).replace("|", "/").replace("\n", " ") for part in (
            row["id"], row["pregunta"][:60], row["reglas"]["status"], "sí" if row.get("llamaria_en_respaldo") else "no",
            row["extraccion"]["status"], row["extraccion"]["segundos"], row["validacion"].get("status"),
            plan.get("indicador") or intent.get("indicador_id") or "-",
            {True: "sí", False: "NO"}.get(truth.get("indicador"), "-"), extra[:50],
            (row["validacion"].get("motivo") or "; ".join(row["extraccion"].get("errores") or []))[:80],
        )) + " |")
    return "\n".join(lines) + "\n"


def main(argv=None):
    from src.semantic import intencion_llm as IL

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--solo", help="ids separados por coma (G16,N03)")
    parser.add_argument("--solo-nuevas", action="store_true", help="solo las 20 preguntas nuevas")
    parser.add_argument("--banco", help="otro banco (p. ej. tests/real/banco_real.json): sin las 20 nuevas")
    parser.add_argument("--sin-llm", action="store_true",
                        help="no llama al LLM: solo cuenta en cuántas preguntas lo llamaría la app")
    parser.add_argument("--todas", action="store_true",
                        help="llamar al LLM también donde la app NO lo llamaría (por defecto solo donde sí)")
    parser.add_argument("--pausa", type=float, default=2.0, help="segundos entre llamadas al LLM (en serie)")
    parser.add_argument("--espera-falla", type=float, default=30.0,
                        help="espera tras una falla del servidor (se duplica en la segunda)")
    parser.add_argument("--max-fallas", type=int, default=2,
                        help="fallas seguidas del servidor (504, runner caído, tiempo agotado) antes de cortar")
    parser.add_argument("--esperar-indice", type=float, default=300.0,
                        help="segundos máximos esperando el índice de embeddings la primera vez")
    parser.add_argument("--sim", action="store_true", help="Power BI simulado y LLM falso (solo prueba el script)")
    parser.add_argument("--out", help="carpeta de salida (por defecto var/out/sondeo_intencion/sondeo_<fecha>)")
    args = parser.parse_args(argv)

    started = time.perf_counter()
    engine, llm_status = _system(args.sim)
    import importlib
    IL = importlib.import_module("src.semantic.intencion_llm")   # el módulo que usa el motor
    provider = engine._context_llm_provider()
    print(f"sistema listo en {time.perf_counter() - started:.0f} s · MedGemma: {llm_status.get('status')}"
          + ("" if provider is not None else " (SIN proveedor: el extractor no se llamará)"))
    out = Path(args.out) if args.out else OUT / f"sondeo_{datetime.now():%Y%m%d_%H%M%S}"
    out.mkdir(parents=True, exist_ok=True)

    rows, failures, cut = [], 0, None
    empty = {"status": "no_llamado", "intencion": None, "crudo": [], "errores": [], "segundos": 0.0, "llamadas": 0}
    for case in _cases(args):
        try:
            item = {**case, **_prepare(engine, case, args.esperar_indice)}
        except Exception as error:
            item = {**case, "error_preparacion": f"{type(error).__name__}: {error}", "_catalog": None,
                    "reglas": {"status": "error"}, "traza": traceback.format_exc()[-1500:]}
        extraction = dict(empty)
        if item.get("_catalog") is not None and cut is None and not args.sin_llm and (args.todas or item.get("llamaria_en_respaldo")):
            for attempt in range(args.max_fallas + 1):
                extraction = IL.extraer_intencion(provider, item["pregunta_normalizada"], item["_catalog"],
                                                  disyuntor=False)
                problem = " ".join(extraction.get("errores") or [])
                if extraction["status"] != "llm_error" or not IL.falla_del_servidor(problem):
                    failures = 0
                    break
                failures += 1
                if failures >= args.max_fallas:
                    cut = f"{failures} fallas seguidas del servidor ({problem[:120]}): se corta el sondeo"
                    print(f"  {case['id']}: {cut}")
                    break
                wait = args.espera_falla * failures
                print(f"  {case['id']}: falla del servidor ({problem[:80]}); espera {wait:.0f} s y reintenta")
                time.sleep(wait)
            if extraction.get("llamadas"):
                time.sleep(max(0.0, args.pausa))   # en serie y con pausa: el servidor es compartido
        try:
            validation = _validate(engine, item, extraction) if item.get("_catalog") is not None else {"status": "sin_catalogo"}
        except Exception as error:
            validation = {"status": "error", "motivo": f"{type(error).__name__}: {error}"}
        row = {key: value for key, value in item.items() if not key.startswith("_")}
        row["extraccion"] = extraction
        row["validacion"] = validation
        rows.append(row)
        print(f"  {case['id']}: reglas {item['reglas'].get('status')} · app llama "
              f"{'sí' if item.get('llamaria_en_respaldo') else 'no'} · LLM {extraction['status']} "
              f"{extraction['segundos']:.2f} s · validación {validation.get('status')} · "
              f"{(validation.get('plan') or {}).get('indicador') or validation.get('motivo') or ''}")

    times = sorted(row["extraccion"]["segundos"] for row in rows if row["extraccion"].get("llamadas"))
    prompts = [row.get("prompt_caracteres") or 0 for row in rows if row.get("prompt_caracteres")]
    meta = {
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "medgemma": f"{llm_status.get('status')} ({llm_status.get('model') or '-'})",
        "sim": bool(args.sim), "pausa_s": args.pausa, "cortado": cut,
        "formato": "esquema" if IL.formato_salida() == IL.ESQUEMA else "json",
        "llm_media_s": round(sum(times) / len(times), 2) if times else None,
        "llm_p95_s": times[min(len(times) - 1, int(0.95 * len(times)))] if times else None,
        "llm_max_s": times[-1] if times else None,
        "prompt_media": round(sum(prompts) / len(prompts)) if prompts else None,
        "prompt_max": max(prompts) if prompts else None,
        "total_s": round(time.perf_counter() - started, 1),
    }
    (out / "resultados.json").write_text(
        json.dumps({"meta": meta, "casos": rows}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (out / "resumen.md").write_text(_summary_md(meta, rows), encoding="utf-8")
    print(f"\nlisto en {meta['total_s']} s · resultados: {out / 'resultados.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
