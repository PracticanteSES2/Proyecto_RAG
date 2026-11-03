"""
Un solo paso para el banco real. Ejecutar desde la RAÍZ DEL CHECKOUT PRINCIPAL
(donde están .env, data/ y la caché del token), con Power BI sin ventana:

    PowerShell:  $env:POWERBI_AUTH="device_code"; .venv\\Scripts\\python.exe -X utf8 -m tests.real.correr_todo
    Bash:        POWERBI_AUTH=device_code .venv/Scripts/python.exe -X utf8 -m tests.real.correr_todo

Opciones: --solo BH01,TU12   --tablero "TABLERO EPS"   --sim (Power BI simulado, sin producción)
          --comparar <resultado.json de una corrida anterior>   (tabla comparativa en el informe)
          --auditoria <auditoria.json>   (por defecto tests/real/auditoria.json)
          --informe <resultado.json>     (no pregunta nada: re-evalúa esa corrida y rehace el informe)
          --out-informe <carpeta>        (dónde escribir resultado.json e INFORME.md; por defecto tests/real/out)
          --banco tests/real/banco_holdout.json   (otro banco; salida por defecto en tests/real/out_<nombre>,
                                                   p. ej. out_holdout, y auditoría tests/real/auditoria_<nombre>.json
                                                   si existe: el holdout no hereda los veredictos del banco real)

Hace, en orden y por caso: (1) calcula la VERDAD con el DAX del banco
(tests/real/banco_real.json; solo agregados y dimensiones no personales),
(2) pregunta al bot con Power BI y MedGemma reales (mismo build_system de
app.py; clic automático en la opción de la contrapregunta indicada en
«elegir»), (3) compara y clasifica la falla.

Escribe salidas PEQUEÑAS y sin datos de pacientes:
    tests/real/out/resultado.json   (por caso: verdad resumida, respuesta, estado, DAX del bot, evaluación)
    tests/real/out/INFORME.md       (tasa automática y auditada, por tablero, por causa raíz, comparación
                                     con la corrida anterior y evidencia de los fallos)
El detalle completo queda en tests/real/out/banco_<fecha>/ (carpeta no versionada).
"""
import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.real import auditoria, run_banco  # noqa: E402

OUT = Path(__file__).resolve().parent / "out"


def banco_dirs(banco):
    """(carpeta de salida, auditoría por defecto) del banco: el real usa out/ y
    auditoria.json; otro banco (banco_<nombre>.json) usa out_<nombre>/ y
    auditoria_<nombre>.json (si no existe, sin veredictos auditados)."""
    if not banco:
        return OUT, None
    path = Path(banco).resolve()
    if path == (Path(__file__).resolve().parent / "banco_real.json"):
        return OUT, None
    name = path.stem[len("banco_"):] if path.stem.startswith("banco_") else path.stem
    here = Path(__file__).resolve().parent
    return here / f"out_{name}", str(here / f"auditoria_{name}.json")


def _short_truth(truth):
    if not truth:
        return truth
    t = {k: v for k, v in truth.items() if k in ("valor", "valores", "filas", "error", "calculado_en")}
    if truth.get("grupos") is not None:
        t["grupos_top"] = [{"clave": str(g["clave"]).strip() if g["clave"] is not None else None, "valor": g["valor"]}
                           for g in truth["grupos"][:8]]
    if truth.get("lista") is not None:
        t["lista"] = [str(v).strip() for v in truth["lista"][:30]]
    if truth.get("alternativas"):
        t["alternativas"] = [_short_truth(a) for a in truth["alternativas"]]
    return t


def _short_turn(turn):
    return {
        "via": turn.get("via"), "texto": turn.get("text"), "segundos": turn.get("seconds"),
        "estado": turn.get("status"), "ruta": turn.get("route"), "etapa": turn.get("stage"),
        "metrica": turn.get("metric"), "modelo": turn.get("semantic_model"),
        "respuesta": (turn.get("answer") or "")[:1500],
        "opciones": [b["label"] for b in turn.get("buttons") or []],
        "eleccion": turn.get("eleccion"),
        "error": (turn.get("error") or "")[:400] or None,
        "dax": [{"modelo": d.get("semantic_model"), "estado": d.get("status"), "filas": d.get("row_count"),
                 "s": d.get("seconds"), "error": (d.get("error") or "")[:300] or None,
                 "dax": (d.get("dax") or "")[:1800]} for d in (turn.get("dax") or [])][-6:],
    }


def compact(results, cases):
    out = []
    for r in results:
        case = cases.get(r["id"], {})
        out.append({
            "id": r["id"], "tablero": r["tablero"], "tipo": r["tipo"], "pregunta": r["pregunta"],
            "turnos_extra": case.get("turnos_extra"), "elegir": case.get("elegir"),
            "contrapregunta_aceptable": case.get("contrapregunta_aceptable"),
            "verdad": _short_truth(r.get("verdad")),
            "verdad_dax": (case.get("verdad") or {}).get("dax"),
            "esperado": case.get("esperado"),
            "correcto": r["eval"]["correcto"], "fallas": [run_banco.FALLAS[f] for f in r["eval"]["fallas"]],
            "detalle": r["eval"]["detalle"], "segundos": r["segundos"],
            "turnos": [_short_turn(t) for t in r["turnos"]],
        })
    return out


def informe(meta, summary, rows, audited=None, comparacion=None):
    audited = audited or auditoria.summarize([], None)
    lines = ["# Banco real — informe automático", ""]
    lines += [f"- **{k}:** {v}" for k, v in meta.items()]
    lines += ["", "Acierto = cifra, agrupación o definición correcta y sin contrapregunta innecesaria. "
              "Los casos de comportamiento (—) se revisan a mano.", ""]
    lines += auditoria.section_tasas(summary, audited)
    lines += auditoria.section_tableros(summary, audited)
    lines += auditoria.section_causas(audited)
    lines += ["## Por tipo de falla (comparador automático)", "", "| Falla | Casos |", "|---|---|"]
    lines += [f"| {k} | {n} |" for k, n in summary["fallas"].items()]
    lines.append("")
    if comparacion:
        lines += comparacion
    lines += ["## Casos", "", "| Caso | OK | Auditado | Fallas | s | Pregunta |", "|---|---|---|---|---|---|"]
    for r in rows:
        ok = {True: "sí", False: "no", None: "—"}[r["correcto"]]
        v = audited["veredictos"].get(r["id"])
        aud = auditoria._cell(v) if v else "—"
        lines.append(f"| {r['id']} | {ok} | {aud} | {', '.join(r['fallas'])} | {r['segundos']} | {r['pregunta']} |")
    lines += ["", "## Evidencia de los fallos", ""]
    for r in rows:
        if r["correcto"] is not False and not r["fallas"]:
            continue
        last = r["turnos"][-1] if r["turnos"] else {}
        lines += [f"### {r['id']} · {r['tablero']} · {', '.join(r['fallas']) or 'sin falla'}", "",
                  f"- **Pregunta:** {r['pregunta']}" + (f" → {r['turnos_extra']}" if r["turnos_extra"] else ""),
                  "- **Turnos:** " + " → ".join(f"{t['via']}:{t['estado']}" for t in r["turnos"]),
                  f"- **Respuesta del bot:** {(last.get('respuesta') or '').replace(chr(10), ' ')[:600]}",
                  f"- **Verdad:** `{json.dumps(r['verdad'], ensure_ascii=False, default=str)[:600]}`",
                  f"- **Detalle:** `{json.dumps(r['detalle'], ensure_ascii=False, default=str)[:400]}`", ""]
        bot_dax = [d for t in r["turnos"] for d in t["dax"] if d.get("dax")]
        if bot_dax:
            d = bot_dax[-1]
            lines += [f"DAX del bot ({d['modelo']}, {d['estado']}):", "```dax", d["dax"][:1200], "```"]
        if r.get("verdad_dax"):
            lines += ["DAX de verdad:", "```dax", r["verdad_dax"][:1200], "```", ""]
    return "\n".join(lines)


def build_report(meta, results, cases, out_dir, audit_path=None, comparar=None):
    """Escribe resultado.json e INFORME.md en out_dir y devuelve (auto, auditada)."""
    audit = auditoria.load(audit_path)
    rows = compact(results, cases)
    summary = run_banco.summarize(results)
    audited = auditoria.summarize(results, audit, cases)
    comparacion = None
    if comparar:
        prev_meta, prev_resumen, prev_results = auditoria.load_previous(comparar, cases)
        comparacion = auditoria.section_comparacion(
            prev_meta, prev_resumen, auditoria.summarize(prev_results, audit, cases),
            run_banco.summarize(prev_results), audited, summary, comparar)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    resumen = dict(summary, auditada={k: audited[k] for k in ("aciertos", "evaluados", "auditados", "sin_auditar",
                                                              "inconclusos", "por_tablero", "por_causa")})
    (out_dir / "resultado.json").write_text(json.dumps({"meta": meta, "resumen": resumen, "casos": rows},
                                                       ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (out_dir / "INFORME.md").write_text(informe(meta, summary, rows, audited, comparacion), encoding="utf-8")
    return summary, audited


def main(argv=None):
    parser = argparse.ArgumentParser(description="Banco real completo: verdad + bot + informe.")
    parser.add_argument("--solo")
    parser.add_argument("--tablero")
    parser.add_argument("--sim", action="store_true")
    parser.add_argument("--comparar", help="resultado.json de una corrida anterior")
    parser.add_argument("--auditoria", help="auditoria.json (por defecto tests/real/auditoria.json)")
    parser.add_argument("--informe", help="resultado.json existente: re-evalúa y rehace el informe sin preguntar")
    parser.add_argument("--out-informe", help="carpeta para resultado.json e INFORME.md (por defecto tests/real/out)")
    parser.add_argument("--banco", help="banco JSON (por defecto tests/real/banco_real.json)")
    args = parser.parse_args(argv)
    from datetime import datetime

    if args.banco:
        run_banco.set_banco(args.banco)
    base_out, audit_default = banco_dirs(args.banco)
    if args.auditoria is None:
        args.auditoria = audit_default
    cases = {c["id"]: c for c in json.loads(run_banco.BANCO.read_text(encoding="utf-8"))["casos"]}
    out_dir = Path(args.out_informe) if args.out_informe else base_out
    if args.informe:
        prev_meta, _, results = auditoria.load_previous(args.informe, cases)
        meta = dict(prev_meta, reevaluado=datetime.now().isoformat(timespec="seconds"))
        summary, audited = build_report(meta, results, cases, out_dir, args.auditoria, args.comparar)
        _print(summary, audited, out_dir)
        return 0

    run_dir = base_out / ("banco_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    forward = ["--out", str(run_dir)]
    if args.banco:
        forward += ["--banco", str(run_banco.BANCO)]
    if args.solo:
        forward += ["--solo", args.solo]
    if args.tablero:
        forward += ["--tablero", args.tablero]
    if args.sim:
        forward += ["--sim"]
    run_banco.main(forward)
    data = json.loads((run_dir / "resultados.json").read_text(encoding="utf-8"))
    meta = dict(data["meta"], modo="SIMULADO" if args.sim else "Power BI real", banco=run_banco.BANCO.name)
    summary, audited = build_report(meta, data["resultados"], cases, out_dir, args.auditoria, args.comparar)
    _print(summary, audited, out_dir)
    return 0


def _print(summary, audited, out_dir):
    print(f"Automática: {summary['aciertos']}/{summary['evaluados']} · "
          f"Auditada: {audited['aciertos']}/{audited['evaluados']} "
          f"({audited['auditados']} con veredicto auditado)")
    print("Escrito:", Path(out_dir) / "resultado.json", "y", Path(out_dir) / "INFORME.md")


if __name__ == "__main__":
    sys.exit(main())
