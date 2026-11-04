"""
Sondeo del extractor de intención con MedGemma REAL (src/semantic/intencion_llm.py).

Para cada pregunta (banco holdout 2 + 20 preguntas nuevas de este archivo) arma el catálogo acotado
con el motor (plan de reglas + embeddings + léxico), llama SOLO al extractor (MedGemma real, mismo
prompt y esquema que la app) y valida la intención con el motor. No ejecuta la consulta final:
guarda la salida cruda, la intención, la validación (con el DAX que se generaría) y los tiempos.

    python -X utf8 -m tests.real.sondeo_intencion                      # holdout 2 + nuevas
    python -X utf8 -m tests.real.sondeo_intencion --solo G16,N03
    python -X utf8 -m tests.real.sondeo_intencion --solo-nuevas
    python -X utf8 -m tests.real.sondeo_intencion --concurrencia 3     # llamadas al LLM en paralelo
    python -X utf8 -m tests.real.sondeo_intencion --sim                # sin producción (LLM falso): prueba el script

Se ejecuta desde la raíz del checkout PRINCIPAL (lee su .env con load_dotenv, como app.py; nunca se
imprime). Power BI de producción en SOLO LECTURA: el plan de reglas y la validación de valores
consultan dominios de columnas (VALUES), igual que la app. MedGemma: no se modifica el servidor.

Salida (no versionada): tests/real/out_sondeo/sondeo_<fecha>/resultados.json y resumen.md.
"""
import argparse
import json
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

HERE = Path(__file__).resolve().parent
OUT = HERE / "out_sondeo"
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
        data = json.loads(BANCO.read_text(encoding="utf-8"))
        for case in data.get("casos") or []:
            truth = case.get("verdad") or {}
            cases.append({"id": case["id"], "origen": "holdout2", "pregunta": case["pregunta"],
                          "tipo": case.get("tipo"), "verdad_dax": truth.get("dax"),
                          "verdad_modelo": truth.get("modelo")})
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
    """Plan de reglas + catálogo (secuencial: el motor no es seguro entre hilos)."""
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
    started = time.perf_counter()
    catalog = IL.armar_catalogo(builder, question, rules, encoder=engine._intent_encoder(),
                                esperar_indice_s=wait_index)
    catalog_s = round(time.perf_counter() - started, 2)
    messages = IL.mensajes(question, catalog)
    return {
        "pregunta_normalizada": question,
        "reglas": {"status": rules.get("status"), "reason": rules.get("reason"),
                   "indicador": (rules.get("metric") or {}).get("label"), "segundos": rules_s},
        "motivo_respaldo": IL.motivo_llamada("respaldo", rules, question),
        "catalogo": catalog.resumen(),
        "catalogo_segundos": catalog_s,
        "prompt_caracteres": sum(len(m["content"]) for m in messages),
        "_catalog": catalog,
    }


def _extract(provider, item):
    from src.semantic import intencion_llm as IL
    return IL.extraer_intencion(provider, item["pregunta_normalizada"], item["_catalog"])


def _validate(engine, item, extraction):
    from src.semantic import intencion_llm as IL

    if extraction.get("intencion") is None:
        return {"status": "sin_intencion"}
    builder = engine.query_plan_builder
    started = time.perf_counter()
    validation = IL.validar_intencion(builder, item["pregunta_normalizada"], extraction["intencion"], item["_catalog"])
    return {
        "status": validation["status"], "motivo": validation["motivo"], "aceptado": validation["aceptado"],
        "descartado": validation["descartado"], "segundos": round(time.perf_counter() - started, 2),
        "plan": _plan_summary(engine, validation["plan"]) if validation["plan"] else None,
    }


def _summary_md(meta, rows):
    lines = [
        "# Sondeo del extractor de intención (MedGemma)", "",
        f"- **fecha:** {meta['fecha']}",
        f"- **MedGemma:** {meta['medgemma']}",
        f"- **casos:** {len(rows)} · **concurrencia:** {meta['concurrencia']}",
        f"- **JSON válido:** {sum(1 for r in rows if r['extraccion']['status'] == 'ok')}/{len(rows)}"
        f" · **validados:** {sum(1 for r in rows if r['validacion'].get('status') == 'valid')}/{len(rows)}",
        f"- **tiempo LLM (s):** media {meta['llm_media_s']} · p95 {meta['llm_p95_s']} · máx {meta['llm_max_s']}", "",
        "| id | pregunta | reglas | LLM | s | validación | indicador | agrupación / periodos | motivo del rechazo |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        plan = (row["validacion"] or {}).get("plan") or {}
        intent = row["extraccion"].get("intencion") or {}
        extra = ", ".join(plan.get("agrupacion") or []) or ", ".join(plan.get("periodos_comparados") or []) or ""
        lines.append("| " + " | ".join(str(part).replace("|", "/").replace("\n", " ") for part in (
            row["id"], row["pregunta"][:70], row["reglas"]["status"], row["extraccion"]["status"],
            row["extraccion"]["segundos"], row["validacion"].get("status"),
            plan.get("indicador") or intent.get("indicador_id") or "-", extra[:60],
            (row["validacion"].get("motivo") or "; ".join(row["extraccion"].get("errores") or []))[:90],
        )) + " |")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--solo", help="ids separados por coma (G16,N03)")
    parser.add_argument("--solo-nuevas", action="store_true", help="solo las 20 preguntas nuevas")
    parser.add_argument("--concurrencia", type=int, default=1, help="llamadas simultáneas al LLM (máx. 3)")
    parser.add_argument("--esperar-indice", type=float, default=300.0,
                        help="segundos máximos esperando el índice de embeddings la primera vez")
    parser.add_argument("--sim", action="store_true", help="Power BI simulado y LLM falso (solo prueba el script)")
    parser.add_argument("--out", help="carpeta de salida (por defecto tests/real/out_sondeo/sondeo_<fecha>)")
    args = parser.parse_args(argv)

    started = time.perf_counter()
    engine, llm_status = _system(args.sim)
    provider = engine._context_llm_provider()
    print(f"sistema listo en {time.perf_counter() - started:.0f} s · MedGemma: {llm_status.get('status')}"
          + ("" if provider is not None else " (SIN proveedor: el extractor no se llamará)"))
    cases = _cases(args)
    prepared = []
    for case in cases:
        try:
            item = {**case, **_prepare(engine, case, args.esperar_indice)}
        except Exception as error:
            item = {**case, "error_preparacion": f"{type(error).__name__}: {error}", "_catalog": None,
                    "reglas": {"status": "error"}, "traza": traceback.format_exc()[-1500:]}
        prepared.append(item)
        print(f"  {case['id']}: reglas {item['reglas'].get('status')} · catálogo "
              f"{len((item.get('catalogo') or {}).get('indicadores') or [])} indicadores")

    def run(item):
        if item.get("_catalog") is None:
            return {"status": "sin_catalogo", "intencion": None, "crudo": [], "errores": [], "segundos": 0.0,
                    "llamadas": 0}
        return _extract(provider, item)

    workers = max(1, min(3, int(args.concurrencia or 1)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        extractions = list(pool.map(run, prepared))

    rows = []
    for item, extraction in zip(prepared, extractions):
        try:
            validation = _validate(engine, item, extraction) if item.get("_catalog") is not None else {"status": "sin_catalogo"}
        except Exception as error:
            validation = {"status": "error", "motivo": f"{type(error).__name__}: {error}"}
        row = {key: value for key, value in item.items() if not key.startswith("_")}
        row["extraccion"] = extraction
        row["validacion"] = validation
        rows.append(row)
        print(f"  {item['id']}: LLM {extraction['status']} {extraction['segundos']:.2f} s · validación "
              f"{validation.get('status')} · {(validation.get('plan') or {}).get('indicador') or validation.get('motivo') or ''}")

    times = sorted(row["extraccion"]["segundos"] for row in rows if row["extraccion"].get("llamadas"))
    meta = {
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "medgemma": f"{llm_status.get('status')} ({llm_status.get('model') or '-'})",
        "sim": bool(args.sim), "concurrencia": workers,
        "llm_media_s": round(sum(times) / len(times), 2) if times else None,
        "llm_p95_s": times[min(len(times) - 1, int(0.95 * len(times)))] if times else None,
        "llm_max_s": times[-1] if times else None,
        "total_s": round(time.perf_counter() - started, 1),
    }
    out = Path(args.out) if args.out else OUT / f"sondeo_{datetime.now():%Y%m%d_%H%M%S}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "resultados.json").write_text(
        json.dumps({"meta": meta, "casos": rows}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (out / "resumen.md").write_text(_summary_md(meta, rows), encoding="utf-8")
    print(f"\nlisto en {meta['total_s']} s · resultados: {out / 'resultados.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
