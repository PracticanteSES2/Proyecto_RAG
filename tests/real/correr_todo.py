"""
Un solo paso para el banco real. Ejecutar desde la RAÍZ DEL CHECKOUT PRINCIPAL
(donde están .env, data/ y la caché del token), con Power BI sin ventana:

    PowerShell:  $env:POWERBI_AUTH="device_code"; .venv\\Scripts\\python.exe -X utf8 -m tests.real.correr_todo
    Bash:        POWERBI_AUTH=device_code .venv/Scripts/python.exe -X utf8 -m tests.real.correr_todo

Opciones: --solo BH01,TU12   --tablero "TABLERO EPS"   --sim (Power BI simulado, sin producción)

Hace, en orden y por caso: (1) calcula la VERDAD con el DAX del banco
(tests/real/banco_real.json; solo agregados y dimensiones no personales),
(2) pregunta al bot con Power BI y MedGemma reales (mismo build_system de
app.py; clic automático en la opción de la contrapregunta indicada en
«elegir»), (3) compara y clasifica la falla.

Escribe salidas PEQUEÑAS y sin datos de pacientes:
    tests/real/out/resultado.json   (por caso: verdad resumida, respuesta, estado, DAX del bot, evaluación)
    tests/real/out/INFORME.md       (tasas por tablero y por tipo de falla + evidencia de los fallos)
El detalle completo queda en tests/real/out/banco_<fecha>/ (carpeta no versionada).
"""
import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.real import run_banco  # noqa: E402

OUT = Path(__file__).resolve().parent / "out"


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


def informe(meta, summary, rows):
    rate = 100 * summary["aciertos"] / max(1, summary["evaluados"])
    lines = ["# Banco real — informe automático", ""]
    lines += [f"- **{k}:** {v}" for k, v in meta.items()]
    lines += ["", f"**Aciertos: {summary['aciertos']}/{summary['evaluados']} ({rate:.0f} %).** "
              "Acierto = cifra, agrupación o definición correcta y sin contrapregunta innecesaria. "
              "Los casos de comportamiento (—) se revisan a mano.", "",
              "## Por tablero", "", "| Tablero | Aciertos |", "|---|---|"]
    lines += [f"| {b} | {v['aciertos']}/{v['evaluados']} |" for b, v in summary["por_tablero"].items()]
    lines += ["", "## Por tipo de falla", "", "| Falla | Casos |", "|---|---|"]
    lines += [f"| {k} | {n} |" for k, n in summary["fallas"].items()]
    lines += ["", "## Casos", "", "| Caso | OK | Fallas | s | Pregunta |", "|---|---|---|---|---|"]
    for r in rows:
        ok = {True: "sí", False: "no", None: "—"}[r["correcto"]]
        lines.append(f"| {r['id']} | {ok} | {', '.join(r['fallas'])} | {r['segundos']} | {r['pregunta']} |")
    lines += ["", "## Evidencia de los fallos", ""]
    for r in rows:
        if r["correcto"] is not False and not r["fallas"]:
            continue
        last = r["turnos"][-1] if r["turnos"] else {}
        lines += [f"### {r['id']} · {r['tablero']} · {', '.join(r['fallas']) or 'sin falla'}", "",
                  f"- **Pregunta:** {r['pregunta']}" + (f" → {r['turnos_extra']}" if r["turnos_extra"] else ""),
                  f"- **Turnos:** " + " → ".join(f"{t['via']}:{t['estado']}" for t in r["turnos"]),
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


def main(argv=None):
    parser = argparse.ArgumentParser(description="Banco real completo: verdad + bot + informe.")
    parser.add_argument("--solo")
    parser.add_argument("--tablero")
    parser.add_argument("--sim", action="store_true")
    args = parser.parse_args(argv)
    from datetime import datetime

    run_dir = OUT / ("banco_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    forward = ["--out", str(run_dir)]
    if args.solo:
        forward += ["--solo", args.solo]
    if args.tablero:
        forward += ["--tablero", args.tablero]
    if args.sim:
        forward += ["--sim"]
    run_banco.main(forward)
    data = json.loads((run_dir / "resultados.json").read_text(encoding="utf-8"))
    cases = {c["id"]: c for c in json.loads(run_banco.BANCO.read_text(encoding="utf-8"))["casos"]}
    rows = compact(data["resultados"], cases)
    summary = run_banco.summarize(data["resultados"])
    meta = dict(data["meta"], modo="SIMULADO" if args.sim else "Power BI real")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "resultado.json").write_text(json.dumps({"meta": meta, "resumen": summary, "casos": rows},
                                                   ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (OUT / "INFORME.md").write_text(informe(meta, summary, rows), encoding="utf-8")
    print("Escrito:", OUT / "resultado.json", "y", OUT / "INFORME.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
