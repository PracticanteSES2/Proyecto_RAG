"""
Corrida REAL periódica de regresión del asistente.

Corre EN SERIE los bancos reales contra el Power BI de producción (solo
lectura, POWERBI_AUTH=device_code con el token en caché) y MedGemma:

    desarrollo  tests/real/banco_real.json
    holdout     tests/real/banco_holdout.json
    holdout2    tests/real/banco_holdout2.json
    multiturno  tests/real/banco_multiturno.json   (por turno y por conversación)

y compara cada caso con la última corrida ACEPTADA (tests/real/linea_base/).
Se versiona solo el resumen por caso: id, correcto, fallas y cifra (verdad y
bot). NUNCA respuestas completas ni filas de datos.

Distingue:
  - regresión     el caso acertaba en la línea base y ahora falla;
  - dato en vivo  ahora falla pero la consulta del bot es la MISMA que la de la
                  verdad (misma medida, columnas y literales) y solo cambió la
                  cifra: los datos se movieron entre las dos consultas (FM01);
  - falla de red  error de conexión, tiempo de espera o token (no es del bot);
  - mejora        fallaba (o no se evaluaba) y ahora acierta.
Escribe var/out/regresion/<fecha>/REGRESION.md (y una copia en
var/out/regresion/REGRESION.md). Código de salida: 0 sin regresiones,
1 con regresiones, 2 si la corrida no sirve (todo falló por red o no hay casos).

Uso (desde la RAÍZ DEL CHECKOUT PRINCIPAL, donde están .env, data/ y la caché
del token):

    PowerShell:
      $env:POWERBI_AUTH="device_code"; .venv\\Scripts\\python.exe -X utf8 tools\\manual\\regresion_real.py
    Opciones:
      --bancos desarrollo,holdout     solo esos bancos
      --aceptar                       al terminar, promueve ESTA corrida a línea base
      --reusar <carpeta de corrida>   no pregunta nada: compara (o acepta) una corrida ya hecha
      --sim                           Power BI simulado + LLM falso (valida el flujo; no compara cifras)

Programarla en el Programador de tareas de Windows (NO se crea sola):
  1. Abrir una vez la aplicación o correr `run_real` a mano para dejar el token
     en caché (device code). La tarea corre con TU usuario y solo cuando hayas
     iniciado sesión (la caché del token está en tu perfil); si el token vence,
     la corrida termina con fallas de red y código 2.
  2. La acción es tests/real/regresion_tarea.ps1 (fija POWERBI_AUTH, corre este
     script desde la raíz y deja el log en var/logs/regresion_real.log).
     En PowerShell, una sola línea (ajusta día y hora):
       schtasks /Create /TN "ProyectoRAG\\RegresionReal" /SC WEEKLY /D MON /ST 06:00 /RL LIMITED /IT
         /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\\Users\\ad6708\\Documents\\Proyecto_RAG\\tests\\real\\regresion_tarea.ps1"
     o en la interfaz: Crear tarea → General: «Ejecutar solo cuando el usuario haya
     iniciado sesión»; Desencadenadores: semanal; Acciones: programa `powershell.exe`,
     argumentos `-NoProfile -ExecutionPolicy Bypass -File <ruta>\\tests\\real\\regresion_tarea.ps1`.
  3. El resultado de la tarea (0x0 / 0x1 / 0x2) es el código de salida; el
     detalle queda en var/out/regresion/REGRESION.md. Una corrida
     completa tarda del orden de una hora (≈ 245 preguntas).
  Para quitarla: schtasks /Delete /TN "ProyectoRAG\\RegresionReal" /F
"""
import argparse
import json
import re
import shutil
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # raíz del proyecto (este archivo vive en tools/manual/)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.comun.rutas import ruta_salida  # noqa: E402
from tests.real import run_banco, run_multiturno  # noqa: E402

REAL = ROOT / "tests" / "real"
BANCOS = {
    "desarrollo": REAL / "banco_real.json",
    "holdout": REAL / "banco_holdout.json",
    "holdout2": REAL / "banco_holdout2.json",
    "multiturno": REAL / "banco_multiturno.json",
}
LINEA_BASE = REAL / "linea_base"
OUT = ruta_salida("regresion")

RED = re.compile(r"time ?out|timed out|tiempo de espera|connection|conexi[oó]n|connect|max retries|"
                 r"name ?resolution|getaddrinfo|temporary failure|remote end closed|ssl|proxy|"
                 r"\b(?:401|403|408|429|500|502|503|504)\b|unauthori[sz]ed|token|aadsts|device[_ ]code|"
                 r"httpsconnectionpool|readerror|socket|sesi[oó]n de power bi", re.I)


# ---------------------------------------------------------------- resumen por caso
def _num(v):
    if isinstance(v, bool) or v is None:
        return None
    try:
        return round(float(v), 4)
    except (TypeError, ValueError):
        return None


def cifra_verdad(truth):
    """Cifra resumida de la verdad (solo números: nunca filas ni claves)."""
    if not isinstance(truth, dict) or truth.get("error"):
        return None
    if truth.get("valores"):
        return {k: _num(v) for k, v in truth["valores"].items()}
    if truth.get("grupos") is not None:
        g = truth["grupos"]
        return {"grupos": len(g), "max": _num(g[0]["valor"]) if g else None}
    if truth.get("lista") is not None:
        return {"lista": len(truth["lista"])}
    return _num(truth.get("valor"))


def cifra_bot(turns):
    last = turns[-1] if turns else {}
    return _num(last.get("value"))


def es_red(turns, truth):
    """Falla de red/autenticación: en la verdad o en lo que vio el bot."""
    texts = []
    if isinstance(truth, dict):
        texts.append(truth.get("error") or "")
        texts += [(a or {}).get("error") or "" for a in truth.get("alternativas") or []]
    for t in turns or []:
        if t.get("status") in ("error", "powerbi_error"):
            texts.append(t.get("error") or "")
        texts += [d.get("error") or "" for d in t.get("dax") or [] if d.get("status") == "error"]
    return any(RED.search(x) for x in texts if x)


def ok_de(ev):
    if ev["correcto"] is None:
        return None
    return bool(ev["correcto"]) and "contrapregunta" not in ev["fallas"]


def resumen_caso(cid, turns, truth, ev, **extra):
    return {"id": cid, "correcto": ok_de(ev), "fallas": list(ev["fallas"]),
            "cifra": {"verdad": cifra_verdad(truth), "bot": cifra_bot(turns)}, **extra}


# ---------------------------------------------------------------- DAX del bot ≈ DAX de la verdad
def _fold(text):
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    return text.casefold()


_REF = re.compile(r"(?:'([^']+)'|\b([A-Za-z_][\w ]*?))?\s*\[([^\]]+)\]")


def dax_firma(dax):
    """(referencias, literales) de una consulta DAX, normalizados: columnas
    «tabla[col]» y medidas «[m]», cadenas y fechas (DATE(a, m, d) → a-m-d)."""
    dax = run_banco.fill(dax or "")
    refs = set()
    for m in _REF.finditer(dax):
        table = (m.group(1) or m.group(2) or "").strip()
        if table.upper() in ("EVALUATE", "ROW", "VAR", "RETURN", "DEFINE"):
            table = ""
        refs.add(_fold(f"{table}[{m.group(3).strip()}]"))
    lits = {_fold(s) for s in re.findall(r'"([^"]*)"', dax) if s not in ("v",)}
    lits |= {"{}-{}-{}".format(*(int(x) for x in d))
             for d in re.findall(r"DATE\s*\(\s*(\d{4})\s*,\s*(\d{1,2})\s*,\s*(\d{1,2})\s*\)", dax, flags=re.I)}
    return refs, lits


def misma_consulta(case, turns):
    """¿Alguna consulta exitosa del bot (último turno) tiene la misma firma
    que la verdad o una alternativa, en el mismo modelo?"""
    sources = run_banco.truth_sources(case)
    if not sources or not turns:
        return False
    last = turns[-1]
    for d in last.get("dax") or []:
        if d.get("status") != "success":
            continue
        bot = dax_firma(d.get("dax"))
        for src in sources:
            if _fold(src.get("modelo")) != _fold(d.get("semantic_model") or last.get("semantic_model")):
                continue
            truth = dax_firma(src["dax"])
            truth_refs = {r for r in truth[0] if r != "[v]"}
            if truth_refs == {r for r in bot[0] if r != "[v]"} and truth[1] == bot[1]:
                return True
    return False


def dato_en_vivo(case, turns, ev):
    """Falla solo por la cifra con la misma consulta que la verdad."""
    if not case or ev["correcto"] is not False:
        return False
    if set(ev["fallas"]) - {"filtro", "lenta"}:
        return False
    return misma_consulta(case, turns)


# ---------------------------------------------------------------- corrida
def run_bank(name, out_dir, sim=False):
    out_dir = Path(out_dir)
    if name == "multiturno":
        run_multiturno.main(["--out", str(out_dir)] + (["--sim"] if sim else []))
    else:
        run_banco.main(["--banco", str(BANCOS[name]), "--out", str(out_dir)] + (["--sim"] if sim else []))
    return out_dir / "resultados.json"


def resumen_banco(name, resultados_path):
    """Resumen versionable por caso de una corrida + detalle en memoria para la comparación."""
    data = json.loads(Path(resultados_path).read_text(encoding="utf-8"))
    casos, detalle = [], {}
    if name == "multiturno":
        convs = {c["id"]: c for c in run_multiturno.load(BANCOS[name])}
        run_multiturno.evaluate_all(data["resultados"], list(convs.values()))
        for r in data["resultados"]:
            conv = convs.get(r["id"])
            for t in r["turnos"]:
                turn_def = next((x for x in (conv or {}).get("turnos", []) if x["n"] == t["n"]), None)
                case = run_multiturno.turn_case(conv, turn_def) if turn_def else None
                casos.append(resumen_caso(t["id"], t["turnos"], t.get("verdad"), t["eval"], nivel="turno"))
                detalle[t["id"]] = {"caso": case, "turnos": t["turnos"], "verdad": t.get("verdad"), "eval": t["eval"],
                                    "pregunta": t["entrada"]}
            fallas = sorted({f for t in r["turnos"] for f in t["eval"]["fallas"]})
            casos.append({"id": r["id"], "nivel": "conversacion", "correcto": run_multiturno.conv_ok(r["turnos"]),
                          "fallas": fallas, "cifra": None})
    else:
        cases = {c["id"]: c for c in json.loads(BANCOS[name].read_text(encoding="utf-8"))["casos"]}
        for r in data["resultados"]:
            case = cases.get(r["id"])
            ev = run_banco.evaluate(case, r["turnos"], r.get("verdad")) if case else r["eval"]
            casos.append(resumen_caso(r["id"], r["turnos"], r.get("verdad"), ev))
            detalle[r["id"]] = {"caso": case, "turnos": r["turnos"], "verdad": r.get("verdad"), "eval": ev,
                                "pregunta": r.get("pregunta")}
    meta = dict(data.get("meta") or {})
    return {"meta": {k: meta.get(k) for k in ("fecha", "commit", "modo", "Power BI", "MedGemma") if k in meta},
            "resumen": tasa(casos), "casos": casos}, detalle


def tasa(casos):
    unit = [c for c in casos if c.get("nivel") != "conversacion"]
    conv = [c for c in casos if c.get("nivel") == "conversacion"]
    out = {"aciertos": sum(1 for c in unit if c["correcto"] is True),
           "evaluados": sum(1 for c in unit if c["correcto"] is not None)}
    if conv:
        out["conversaciones"] = {"aciertos": sum(1 for c in conv if c["correcto"] is True),
                                 "evaluadas": sum(1 for c in conv if c["correcto"] is not None)}
    return out


# ---------------------------------------------------------------- comparación
def comparar(base, actual, detalle):
    """Clasifica cada caso de la corrida actual frente a la línea base."""
    base_by = {c["id"]: c for c in (base or {}).get("casos", [])}
    act_by = {c["id"]: c for c in actual["casos"]}
    out = []
    for cid, act in act_by.items():
        det = detalle.get(cid) or {}
        prev = base_by.get(cid)
        red = act.get("nivel") != "conversacion" and act["correcto"] is not True and es_red(
            det.get("turnos"), det.get("verdad"))
        if red:
            estado = "red"
        elif prev is None:
            estado = "nuevo"
        elif prev["correcto"] is True and act["correcto"] is False:
            if act.get("nivel") == "conversacion":
                estado = "conversacion_empeora"
            elif dato_en_vivo(det.get("caso"), det.get("turnos"), det.get("eval")):
                estado = "dato_en_vivo"
            else:
                estado = "regresion"
        elif prev["correcto"] is not True and act["correcto"] is True:
            estado = "mejora"
        elif prev["correcto"] is True and act["correcto"] is None:
            estado = "inconcluso"
        elif prev["correcto"] is False and act["correcto"] is False and set(prev["fallas"]) != set(act["fallas"]):
            estado = "cambio_falla"
        else:
            estado = "igual"
        out.append({"id": cid, "estado": estado, "antes": prev, "ahora": act, "pregunta": det.get("pregunta")})
    for cid, prev in base_by.items():
        if cid not in act_by:
            out.append({"id": cid, "estado": "faltante", "antes": prev, "ahora": None, "pregunta": None})
    return out


def _f(c):
    if not c:
        return "—"
    mark = {True: "sí", False: "no", None: "—"}[c["correcto"]]
    fallas = ", ".join(run_banco.FALLAS.get(f, f) for f in c["fallas"])
    return mark + (f" ({fallas})" if fallas else "")


def _cifra(c):
    if not c or not c.get("cifra"):
        return ""
    return json.dumps(c["cifra"], ensure_ascii=False)


SECCIONES = (("regresion", "Regresiones (acertaba y ahora falla con otra consulta)"),
             ("dato_en_vivo", "Dato en vivo (misma consulta que la verdad, solo cambió la cifra: no es regresión)"),
             ("red", "Fallas de red o autenticación (no son del bot)"),
             ("mejora", "Mejoras"),
             ("inconcluso", "Inconclusos (acertaban; ahora no se pudieron evaluar)"),
             ("conversacion_empeora", "Conversaciones que empeoran (detalle en sus turnos)"),
             ("cambio_falla", "Siguen fallando con otra falla"),
             ("nuevo", "Casos nuevos (sin línea base)"),
             ("faltante", "Casos de la línea base que no se corrieron"))


def _tasa(r):
    if not r:
        return "sin línea base"
    conv = r.get("conversaciones")
    return f"{r['aciertos']}/{r['evaluados']}" + (f" · conv. {conv['aciertos']}/{conv['evaluadas']}" if conv else "")


def informe(meta, por_banco):
    lines = ["# Regresión real", ""]
    lines += [f"- **{k}:** {v}" for k, v in meta.items()]
    lines += ["", "| Banco | Línea base | Ahora | Regresiones | Dato en vivo | Red | Mejoras |", "|---|---|---|---|---|---|---|"]
    for name, b in por_banco.items():
        cnt = {k: sum(1 for x in b["comparacion"] if x["estado"] == k) for k, _ in SECCIONES}
        base = b["base"]["resumen"] if b["base"] else None
        cell = _tasa
        lines.append(f"| {name} | {cell(base)} | {cell(b['actual']['resumen'])} "
                     f"| {cnt['regresion']} | {cnt['dato_en_vivo']} | {cnt['red']} | {cnt['mejora']} |")
    for key, title in SECCIONES:
        rows = [(name, x) for name, b in por_banco.items() for x in b["comparacion"] if x["estado"] == key]
        if not rows or key == "igual":
            continue
        lines += ["", f"## {title} ({len(rows)})", "", "| Banco | Caso | Antes | Ahora | Cifra ahora | Pregunta |",
                  "|---|---|---|---|---|---|"]
        for name, x in rows:
            q = (x.get("pregunta") or "").replace("|", "/")[:80]
            lines.append(f"| {name} | {x['id']} | {_f(x['antes'])} | {_f(x['ahora'])} | {_cifra(x['ahora'])} | {q} |")
    return "\n".join(lines) + "\n"


def aceptar(por_banco, run_dir):
    LINEA_BASE.mkdir(parents=True, exist_ok=True)
    for name, b in por_banco.items():
        data = dict(b["actual"])
        data["meta"] = dict(data["meta"], banco=BANCOS[name].name, aceptada=datetime.now().isoformat(timespec="seconds"),
                            corrida=Path(run_dir).name)
        (LINEA_BASE / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str) + "\n",
                                                encoding="utf-8")
    print("Línea base actualizada en", LINEA_BASE, "(" + ", ".join(por_banco) + ")")


def load_base(name):
    path = LINEA_BASE / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def main(argv=None):
    parser = argparse.ArgumentParser(description="Regresión real periódica (Power BI de producción, solo lectura).")
    parser.add_argument("--bancos", default=",".join(BANCOS), help="bancos separados por coma: " + ", ".join(BANCOS))
    parser.add_argument("--aceptar", action="store_true", help="promueve esta corrida a línea base")
    parser.add_argument("--reusar", help="carpeta de una corrida anterior (no pregunta nada)")
    parser.add_argument("--sim", action="store_true", help="Power BI simulado + LLM falso")
    parser.add_argument("--out", help="carpeta de la corrida (por defecto var/out/regresion/<fecha>)")
    args = parser.parse_args(argv)
    names = [n.strip() for n in args.bancos.split(",") if n.strip()]
    unknown = [n for n in names if n not in BANCOS]
    if unknown:
        parser.error(f"bancos desconocidos: {unknown}")

    if args.reusar:
        run_dir = Path(args.reusar)
    else:
        run_dir = Path(args.out) if args.out else OUT / datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir.mkdir(parents=True, exist_ok=True)
        for name in names:   # en serie: un solo sistema (run_real.SYSTEM) para todos los bancos
            print(f"\n=== {name} ===", flush=True)
            try:
                run_bank(name, run_dir / name, sim=args.sim)
            except Exception as exc:  # un banco caído no detiene a los demás
                print(f"{name}: la corrida falló: {type(exc).__name__}: {exc}", flush=True)

    por_banco = {}
    for name in names:
        path = run_dir / name / "resultados.json"
        if not path.exists():
            print(f"{name}: no hay {path}", flush=True)
            continue
        actual, detalle = resumen_banco(name, path)
        base = load_base(name)
        por_banco[name] = {"actual": actual, "base": base, "comparacion": comparar(base, actual, detalle)}

    meta = {"fecha": datetime.now().isoformat(timespec="seconds"), "corrida": str(run_dir),
            "commit": run_banco._commit(), "modo": "SIMULADO" if args.sim else "Power BI real",
            "línea base": ", ".join(f"{n}: {(b['base'] or {}).get('meta', {}).get('commit') or '—'}"
                                    f" ({(b['base'] or {}).get('meta', {}).get('aceptada') or 'sin aceptar'})"
                                    for n, b in por_banco.items())}
    text = informe(meta, por_banco)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "REGRESION.md").write_text(text, encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)
    if (run_dir / "REGRESION.md").resolve() != (OUT / "REGRESION.md").resolve():
        shutil.copyfile(run_dir / "REGRESION.md", OUT / "REGRESION.md")

    todos = [x for b in por_banco.values() for x in b["comparacion"]]
    regresiones = [x for x in todos if x["estado"] == "regresion"]
    unit = [x for x in todos if x["ahora"] and x["ahora"].get("nivel") != "conversacion"]
    red = [x for x in unit if x["estado"] == "red"]
    print(f"Regresiones: {len(regresiones)} · dato en vivo: {sum(x['estado'] == 'dato_en_vivo' for x in todos)} · "
          f"red: {len(red)} · mejoras: {sum(x['estado'] == 'mejora' for x in todos)}")
    print("Informe:", run_dir / "REGRESION.md")
    if args.aceptar and por_banco:
        aceptar(por_banco, run_dir)
    if not unit or len(red) == len(unit):
        return 2
    return 1 if regresiones else 0


if __name__ == "__main__":
    sys.exit(main())
