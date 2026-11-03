"""
Corre el banco con verdad de terreno (tests/real/banco_real.json) contra el
sistema real (Power BI de producción en solo lectura + MedGemma) y compara la
respuesta del bot con la verdad calculada EN EL MISMO MOMENTO (los tableros
del día cambian a cada rato).

    python -X utf8 -m tests.real.run_banco                 # todo el banco
    python -X utf8 -m tests.real.run_banco --solo BH01,TU12
    python -X utf8 -m tests.real.run_banco --tablero "TABLERO EPS"
    python -X utf8 -m tests.real.run_banco --reevaluar tests/real/out/banco_<fecha>/resultados.json
    python -X utf8 -m tests.real.run_banco --reevaluar <resultados.json> --auditoria   # + veredictos auditados
    python -X utf8 -m tests.real.run_banco --banco tests/real/banco_holdout.json       # otro banco (holdout)

Salida: tests/real/out/banco_<fecha>/resultados.json y resumen.md (la carpeta
out/ no se versiona). Nunca guarda filas de pacientes: la verdad solo usa
agregados y dimensiones no personales, y las respuestas del bot pasan por
run_real.redact().
"""
import argparse
import json
import re
import sys
import time
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.real import env as real_env  # noqa: E402

HERE = Path(__file__).resolve().parent
BANCO = HERE / "banco_real.json"
SLOW_S = 30.0

FALLAS = {
    "indicador": "indicador equivocado",
    "contrapregunta": "contrapregunta innecesaria",
    "filtro": "filtro o periodo mal aplicado",
    "agrupacion": "agrupación ignorada",
    "dax": "error de DAX o Power BI",
    "rag": "RAG pobre",
    "inventada": "respuesta inventada",
    "lenta": "lenta (>30 s)",
    "alcance": "fuera de alcance no rechazado",
}

# Señales de que el bot rechazó una pregunta fuera de alcance (texto plegado).
RECHAZO = ("no puedo", "solo puedo", "solo respondo", "unicamente", "fuera de", "alcance", "no tengo informacion",
           "no tengo datos", "no esta relacionad", "no estoy disenad", "tableros", "indicadores", "no encontr",
           "no dispongo", "no cuento con")


def set_banco(path):
    """Cambia el banco activo (por defecto banco_real.json)."""
    global BANCO
    BANCO = Path(path).resolve() if path else HERE / "banco_real.json"
    return BANCO


# ---------------------------------------------------------------- periodos
def period_values(today=None):
    today = today or date.today()
    first = today.replace(day=1)
    last_prev = first - timedelta(days=1)
    year = today.year
    return {
        "HOY": today, "AYER": today - timedelta(days=1), "INI_MES": first,
        "INI_SEMANA": today - timedelta(days=today.weekday()),
        "INI_MES_PASADO": last_prev.replace(day=1), "FIN_MES_PASADO": last_prev,
        "INI_ANO": date(year, 1, 1), "INI_AGO": date(year, 8, 1), "FIN_AGO": date(year, 8, 31),
        "INI_ANO_PASADO": date(year - 1, 1, 1), "FIN_ANO_PASADO": date(year - 1, 12, 31),
    }


def fill(dax, today=None):
    for key, value in period_values(today).items():
        dax = dax.replace("{" + key + "}", f"DATE({value.year}, {value.month}, {value.day})")
    return dax


# ---------------------------------------------------------------- verdad
def _num(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def compute_truth(verdad, today=None):
    """Ejecuta el DAX de verdad (solo agregados) y devuelve un dict serializable."""
    out = {"calculado_en": datetime.now().isoformat(timespec="seconds")}
    try:
        rows = real_env.dax(fill(verdad["dax"], today), verdad["modelo"], max_rows=200)
    except Exception as exc:
        return {**out, "error": str(exc)[:500]}
    if not rows:
        return {**out, "filas": 0, "valor": None}
    first = rows[0]
    keys = list(first.keys())
    if len(rows) == 1 and all(k.startswith("[") for k in keys):
        values = {k.strip("[]"): first[k] for k in keys}
        if list(values) == ["v"]:
            return {**out, "filas": 1, "valor": values["v"]}
        return {**out, "filas": 1, "valores": values}
    if len(keys) == 1:  # lista de una dimensión
        return {**out, "filas": len(rows), "lista": [r[keys[0]] for r in rows]}
    key_col = next(k for k in keys if not k.startswith("["))
    grupos = [{"clave": r[key_col], "valor": r.get("[v]")} for r in rows]
    grupos.sort(key=lambda g: -(_num(g["valor"]) or 0))
    return {**out, "filas": len(rows), "grupos": grupos}


def alt_sources(verdad):
    """Alternativas de la verdad como [{"modelo", "dax"}]: cada una puede venir
    de otro modelo (otra fuente real que responde la pregunta tal como está)."""
    out = []
    for alt in (verdad or {}).get("alternativas") or []:
        if isinstance(alt, dict):
            out.append({"modelo": alt.get("modelo") or verdad.get("modelo"), "dax": alt["dax"]})
        else:
            out.append({"modelo": verdad.get("modelo"), "dax": alt})
    return out


def compute_truths(verdad, today=None):
    """Verdad principal + alternativas (cada una con SU modelo)."""
    truth = compute_truth(verdad, today)
    alts = []
    for alt in alt_sources(verdad):
        one = compute_truth({**verdad, "modelo": alt["modelo"], "dax": alt["dax"]}, today)
        one["modelo"] = alt["modelo"]
        alts.append(one)
    if alts:
        truth["alternativas"] = alts
    return truth


# ---------------------------------------------------------------- texto
def fold(text):
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    return " ".join(text.casefold().split())


_NUM = re.compile(r"(?<![\w])-?\d{1,3}(?:[.  ]\d{3})+(?:,\d+)?(?![\d])|(?<![\w])-?\d+(?:[.,]\d+)?(?![\d])")


def numbers_in(text):
    """Todas las lecturas posibles de las cifras del texto (formato español o
    inglés), con «millones» y «X h Y min» convertidos."""
    text = str(text or "")
    out = set()
    for m in _NUM.finditer(text):
        token = m.group(0).replace(" ", " ")
        cands = set()
        if re.fullmatch(r"-?\d{1,3}(?:[. ]\d{3})+(?:,\d+)?", token):
            cands.add(float(token.replace(".", "").replace(" ", "").replace(",", ".")))
            if "." in token and token.count(".") == 1 and "," not in token:
                cands.add(float(token))  # 1.234 en inglés
        elif "," in token:
            cands.add(float(token.replace(",", ".")))
            if re.fullmatch(r"-?\d{1,3},\d{3}", token):
                cands.add(float(token.replace(",", "")))
        else:
            cands.add(float(token))
        tail = text[m.end(): m.end() + 16].casefold()
        for c in list(cands):
            if tail.lstrip().startswith("mil millones"):
                cands.add(c * 1e9)
            elif tail.lstrip().startswith(("millones", "millón", "millon", "m ")):
                cands.add(c * 1e6)
            elif tail.lstrip().startswith("mil "):
                cands.add(c * 1e3)
        out |= cands
    for h, mnt in re.findall(r"(\d+)\s*h(?:oras?)?\s*(?:y\s*)?(\d+)\s*min", text, flags=re.I):
        out.add(int(h) * 60 + int(mnt))
        out.add(int(h) + int(mnt) / 60)
    return out


def close(candidate, target, rel):
    if target is None:
        return False
    abs_tol = 0.5 if abs(target) >= 10 else 0.051
    return abs(candidate - target) <= max(rel * abs(target), abs_tol)


def number_matches(answer_numbers, value, verdad):
    value = _num(value)
    if value is None:
        return False
    rel = float(verdad.get("tolerancia") or 0.0)
    targets = {value}
    if verdad.get("porcentaje"):
        targets |= {value * 100, value / 100}
    unit = verdad.get("unidad")
    if unit == "min":
        targets |= {value / 60}
    if unit == "h":
        targets |= {value * 60, value / 24}
    if unit == "días":
        targets |= {value * 24}
    return any(close(c, t, rel) for c in answer_numbers for t in targets)


# ---------------------------------------------------------------- evaluación
def evaluate(case, turns, truth):
    """Devuelve dict con correcto (bool|None), detalle y fallas."""
    last = turns[-1] if turns else {}
    answer = last.get("answer") or ""
    nums = numbers_in(answer)
    tipo = case["tipo"]
    detail = {}
    correct = None
    if tipo == "definicion":
        exp = case.get("esperado") or {}
        text = fold(answer)
        ok_all = all(fold(w) in text for w in exp.get("todas", []))
        ok_any = not exp.get("alguna") or any(fold(w) in text for w in exp["alguna"])
        correct = bool(ok_all and ok_any and last.get("status") not in ("error", "not_found"))
        detail = {"todas": ok_all, "alguna": ok_any}
    elif tipo == "comportamiento":
        correct = None
    elif tipo == "fuera_alcance":
        # Debe rechazarse: sin consultas a Power BI exitosas y con un texto de
        # rechazo (o una contrapregunta sin cifras inventadas).
        text = fold(answer)
        ok_dax = [d for t in turns for d in t.get("dax") or [] if d.get("status") == "success"]
        rechazo = any(w in text for w in RECHAZO)
        correct = bool(not ok_dax and rechazo)
        detail = {"rechazo": rechazo, "dax_exitosos": len(ok_dax)}
    elif truth is None or truth.get("error"):
        correct = None
        detail = {"verdad_error": (truth or {}).get("error")}
    elif tipo == "numero":
        values = [truth.get("valor")]
        correct = number_matches(nums, truth.get("valor"), case["verdad"])
        for alt in truth.get("alternativas") or []:
            values.append(alt.get("valor"))
            correct = correct or number_matches(nums, alt.get("valor"), case["verdad"])
        if truth.get("valor") is None:
            correct = "no hay datos" in fold(answer) or "sin datos" in fold(answer)
        detail = {"verdad": values, "cifras_bot": sorted(nums)[:20]}
    elif tipo == "comparacion":
        vals = truth.get("valores") or {}
        hits = {k: number_matches(nums, v, case["verdad"]) for k, v in vals.items()}
        correct = bool(hits) and all(hits.values())
        detail = {"verdad": vals, "aciertos": hits}
    elif tipo == "agrupado":
        groups = [g for g in truth.get("grupos") or [] if g["clave"] not in (None, "")]
        k = min(int(case["verdad"].get("top_keys") or 5), len(groups))
        text = fold(answer)
        checks = []
        for g in groups[:k]:
            key_ok = fold(g["clave"]) in text
            val_ok = number_matches(nums, g["valor"], case["verdad"])
            checks.append({"clave": str(g["clave"]).strip(), "valor": g["valor"], "clave_ok": key_ok, "valor_ok": val_ok})
        if not groups:
            correct = "no hay datos" in text
        else:
            score = sum(c["clave_ok"] and c["valor_ok"] for c in checks) / max(1, len(checks))
            correct = score >= 0.8
            detail["puntaje"] = round(score, 2)
        detail["top"] = checks
    elif tipo == "lista":
        values = [v for v in truth.get("lista") or [] if v not in (None, "")]
        text = fold(answer)
        found = [v for v in values if fold(v) in text]
        cov = len(found) / max(1, len(values))
        correct = cov >= float(case["verdad"].get("cobertura_minima") or 0.6)
        detail = {"cobertura": round(cov, 2), "esperados": len(values), "encontrados": len(found)}
        if not correct and lista_alternativa_ok(case, last):
            correct = True
            detail["lista_alternativa"] = True
    fallas = classify(case, turns, correct, detail)
    if correct is False and default_choice(turns):
        # El valor depende de una opción que el runner pulsó por defecto: no
        # dice nada del bot. Con contrapregunta legítima queda inconcluso; si
        # no, falla solo por la contrapregunta.
        detail["eleccion_por_defecto"] = True
        if case.get("contrapregunta_aceptable"):
            correct = None
            detail["inconcluso"] = "el valor depende de una opción elegida por defecto"
        fallas = [f for f in fallas if f in ("contrapregunta", "lenta")]
    return {"correcto": correct, "detalle": detail, "fallas": fallas}


def default_choice(turns):
    return any((t.get("eleccion") or {}).get("modo") == "defecto" for t in turns)


def lista_alternativa_ok(case, last):
    """Lista desde OTRA dimensión real aceptada (p. ej. servicios o áreas):
    DAX exitoso sobre una columna cuyo nombre contiene alguno de los patrones
    y al menos `minimo` valores en la respuesta."""
    spec = (case.get("verdad") or {}).get("lista_alternativa")
    if not spec:
        return False
    minimo = int(spec.get("minimo") or 5)
    patrones = [fold(p) for p in spec.get("columnas") or []]
    items = [ln for ln in str(last.get("answer") or "").splitlines() if re.match(r"\s*(?:[-*•]|\d+[.)])\s+\S", ln)]
    for d in last.get("dax") or []:
        if d.get("status") != "success" or (d.get("row_count") or 0) < minimo:
            continue
        cols = {fold(c) for c in re.findall(r"\[([^\]]+)\]", d.get("dax") or "")}
        if any(p in c for p in patrones for c in cols) and len(items) >= minimo:
            return True
    return False


def _core_refs(dax):
    refs = re.findall(r"(?:'[^']+'|\b[A-Z_][\w ]*)?\[[^\]]+\]", dax or "")
    return {fold(r.split("[")[-1].strip("]")) for r in refs}


def _call_args(text, open_idx):
    """Argumentos de nivel superior de la llamada cuyo «(» está en open_idx."""
    args, depth, start, i = [], 0, open_idx + 1, open_idx
    in_str = None
    while i < len(text):
        ch = text[i]
        if in_str:
            if ch == in_str:
                in_str = None
        elif ch in "\"'":
            in_str = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if depth == 0:
                args.append(text[start:i])
                return args
        elif ch == "," and depth == 1:
            args.append(text[start:i])
            start = i + 1
        i += 1
    args.append(text[start:])
    return args


def _first_arg(expr, func):
    m = re.match(r"\s*" + func + r"\s*\(", expr, flags=re.I)
    if not m:
        return None
    return _call_args(expr, m.end() - 1)[0]


def truth_core_expr(dax):
    """Expresión de la medida de un DAX de verdad (sin los filtros):
    ROW("v", CALCULATE(<expr>, filtros)) → <expr>; SUMMARIZECOLUMNS(col, filtros,
    "v", <expr>) → <expr>; CALCULATETABLE(VALUES(col), ...) → VALUES(col)."""
    dax = dax or ""
    m = re.search(r'"v"\s*,', dax) or re.search(r'ROW\s*\(\s*"[^"]+"\s*,', dax, flags=re.I)
    if m:
        # el valor llega hasta la coma o el paréntesis de cierre de nivel superior
        expr = _call_args("(" + dax[m.end():], 0)[0]
    else:
        body = re.sub(r"^\s*EVALUATE\s+", "", dax, flags=re.I)
        expr = _first_arg(body, "CALCULATETABLE") or body
    while True:
        inner = _first_arg(expr, "CALCULATE")
        if inner is None:
            return expr.strip()
        expr = inner


def _only_measures(expr):
    """True si la expresión solo referencia medidas ([X], sin tabla)."""
    refs = re.findall(r"(?:'[^']+'|\b[A-Za-z_][\w ]*)?\[[^\]]+\]", expr or "")
    return bool(refs) and all(r.startswith("[") for r in refs)


def truth_sources(case):
    verdad = case.get("verdad") or {}
    out = [{"modelo": verdad.get("modelo"), "dax": verdad.get("dax", "")}] if verdad.get("dax") else []
    return out + alt_sources(verdad)


DATA_TIPOS = ("numero", "comparacion", "agrupado", "lista")


def classify(case, turns, correct, detail):
    fallas = []
    first = turns[0] if turns else {}
    last = turns[-1] if turns else {}
    total_s = sum(t.get("seconds") or 0 for t in turns)
    if first.get("status") == "needs_clarification" and not case.get("contrapregunta_aceptable"):
        fallas.append("contrapregunta")
    if total_s > SLOW_S:
        fallas.append("lenta")
    if correct is not False:
        return fallas
    dax_errors = [d for t in turns for d in t.get("dax") or [] if d.get("status") == "error"]
    status = last.get("status")
    if status in ("powerbi_error", "error") or (dax_errors and status != "success"):
        fallas.append("dax")
        return fallas
    tipo = case["tipo"]
    if tipo == "fuera_alcance":
        fallas.append("alcance")
        return fallas
    if tipo == "definicion":
        fallas.append("rag")
        return fallas
    bot_dax = " ".join(d.get("dax") or "" for d in last.get("dax") or [])
    if status in ("metric_not_resolved", "not_found", "needs_clarification"):
        fallas.append("indicador")
        return fallas
    if status == "unsupported_filter":
        fallas.append("filtro")
        return fallas
    ok_dax = [d for d in last.get("dax") or [] if d.get("status") == "success"]
    if tipo in DATA_TIPOS and last.get("route") == "rag":
        # Pregunta de datos respondida con la documentación: es un error de
        # enrutamiento (indicador), no una cifra inventada. Vale aunque haya
        # DAX exitosos: son las sondas del catálogo (VALUES de columnas), no
        # la respuesta (holdout H02, H27b, H34).
        detail["enrutamiento"] = "rag"
        fallas.append("indicador")
        return fallas
    if tipo in DATA_TIPOS and not ok_dax and last.get("route") != "powerbi":
        if numbers_in(last.get("answer")):
            fallas.append("inventada")
            return fallas
    sources = truth_sources(case)
    bot_model = fold(last.get("semantic_model"))
    if bot_model and sources:
        same = [src for src in sources if fold(src["modelo"]) == bot_model]
        if not same:
            fallas.append("indicador")
            return fallas
        sources = same
    exprs = [truth_core_expr(src["dax"]) for src in sources]
    cores = [_core_refs(e) for e in exprs]
    bot_refs = _core_refs(bot_dax)
    if cores and all(core and not (core & bot_refs) for core in cores):
        # Si la verdad es solo una medida ([X]) el bot pudo escribir su
        # expresión en línea: con «sin datos» no se puede decir que sea otro
        # indicador (lo más probable es el filtro o la fecha).
        only_measures = all(_only_measures(e) for e in exprs)
        if not (only_measures and status == "empty_result"):
            fallas.append("indicador")
            return fallas
    if status == "empty_result":   # indicador correcto, pero sin datos con sus filtros
        fallas.append("filtro")
        return fallas
    if tipo == "agrupado" and not any(c.get("clave_ok") for c in detail.get("top", [])):
        fallas.append("agrupacion")
        return fallas
    fallas.append("filtro")
    return fallas


# ---------------------------------------------------------------- corrida
def run_case(case, run_real):
    turns = []
    convo = run_real.run_conversation([case["pregunta"]])
    turns += convo
    clicks = 0
    while turns[-1]["status"] == "needs_clarification" and turns[-1]["buttons"] and clicks < 2:
        button, eleccion = choose_button(case, turns[-1]["buttons"], run_real.pick_button)
        if button is None:
            break
        t, _ = run_real.choose(button["id"], button["label"])
        t["eleccion"] = eleccion
        turns.append(t)
        clicks += 1
    for extra in case.get("turnos_extra") or []:
        text = extra[len("texto:"):].strip() if extra.startswith("texto:") else extra
        t, _ = run_real.ask(text)
        turns.append(t)
    return turns


def choose_button(case, buttons, pick):
    """Botón a pulsar y CÓMO se eligió: «elegir» del banco, modelo o página de
    la verdad, o «defecto» (primera opción real: el valor no es concluyente)."""
    verdad = case.get("verdad") or {}
    for modo, target in (("elegir", case.get("elegir")), ("modelo", verdad.get("modelo")),
                         ("pagina", verdad.get("pagina"))):
        if target:
            button = pick(buttons, target)
            if button is not None:
                return button, {"modo": modo, "objetivo": target, "etiqueta": button["label"]}
    button = next((b for b in buttons if str(b["id"]) != "__none__"), None)
    if button is None:
        return None, None
    return button, {"modo": "defecto", "objetivo": None, "etiqueta": button["label"]}


def load_cases(args):
    data = json.loads(BANCO.read_text(encoding="utf-8"))
    cases = data["casos"]
    if args.solo:
        wanted = {c.strip() for c in args.solo.split(",")}
        cases = [c for c in cases if c["id"] in wanted]
    if args.tablero:
        cases = [c for c in cases if fold(c["tablero"]) == fold(args.tablero)]
    return cases


def summarize(results):
    from collections import Counter, defaultdict

    by_board = defaultdict(lambda: [0, 0])
    fallas = Counter()
    inconclusos = []
    for r in results:
        if r["eval"]["correcto"] is None:
            if (r["eval"].get("detalle") or {}).get("inconcluso"):
                inconclusos.append(r["id"])
            continue
        ok = r["eval"]["correcto"] and "contrapregunta" not in r["eval"]["fallas"]
        by_board[r["tablero"]][0] += int(bool(ok))
        by_board[r["tablero"]][1] += 1
        for f in r["eval"]["fallas"]:
            fallas[f] += 1
    total_ok = sum(v[0] for v in by_board.values())
    total = sum(v[1] for v in by_board.values())
    return {"aciertos": total_ok, "evaluados": total, "inconclusos": inconclusos,
            "por_tablero": {k: {"aciertos": v[0], "evaluados": v[1]} for k, v in sorted(by_board.items())},
            "fallas": {FALLAS[k]: n for k, n in fallas.most_common()}}


def write_summary(out_dir, results, meta):
    s = summarize(results)
    lines = ["# Banco real: resultados", ""]
    for k, v in meta.items():
        lines.append(f"- **{k}:** {v}")
    rate = 100 * s["aciertos"] / max(1, s["evaluados"])
    lines += ["", f"**Aciertos: {s['aciertos']}/{s['evaluados']} ({rate:.0f} %)** "
              "(acierto = cifra/agrupación/definición correcta sin contrapregunta innecesaria)", "",
              "| Tablero | Aciertos |", "|---|---|"]
    for board, v in s["por_tablero"].items():
        lines.append(f"| {board} | {v['aciertos']}/{v['evaluados']} |")
    lines += ["", "| Tipo de falla | Casos |", "|---|---|"]
    for k, n in s["fallas"].items():
        lines.append(f"| {k} | {n} |")
    lines += ["", "| Caso | Pregunta | OK | Fallas | s | Respuesta (recorte) |", "|---|---|---|---|---|---|"]
    for r in results:
        ans = (r["turnos"][-1]["answer"] or "").replace("\n", " ").replace("|", "/")[:140] if r["turnos"] else ""
        ok = {True: "sí", False: "no", None: "—"}[r["eval"]["correcto"]]
        lines.append(f"| {r['id']} | {r['pregunta'][:60]} | {ok} | {', '.join(FALLAS[f] for f in r['eval']['fallas'])} "
                     f"| {r['segundos']} | {ans} |")
    (out_dir / "resumen.md").write_text("\n".join(lines), encoding="utf-8")
    return s


def main(argv=None):
    parser = argparse.ArgumentParser(description="Banco real con verdad de terreno (Power BI de producción, solo lectura).")
    parser.add_argument("--solo", help="ids separados por coma")
    parser.add_argument("--tablero", help="solo los casos de un modelo")
    parser.add_argument("--out", help="carpeta de salida")
    parser.add_argument("--reevaluar", help="resultados.json previo: recalcula la evaluación sin volver a preguntar")
    parser.add_argument("--auditoria", nargs="?", const="", default=None,
                        help="con --reevaluar: aplica los veredictos de tests/real/auditoria.json (u otro archivo)")
    parser.add_argument("--sim", action="store_true",
                        help="Power BI simulado + LLM falso: valida el flujo (sin verdad ni producción)")
    parser.add_argument("--banco", help="banco JSON (por defecto tests/real/banco_real.json)")
    args = parser.parse_args(argv)
    if args.banco:
        set_banco(args.banco)
    real_env.setup_env()
    cases = {c["id"]: c for c in json.loads(BANCO.read_text(encoding="utf-8"))["casos"]}

    if args.reevaluar:
        path = Path(args.reevaluar)
        data = json.loads(path.read_text(encoding="utf-8"))
        for r in data["resultados"]:
            case = cases.get(r["id"], r.get("caso"))
            r["eval"] = evaluate(case, r["turnos"], r.get("verdad"))
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        s = write_summary(path.parent, data["resultados"], data["meta"])
        print(json.dumps(s, ensure_ascii=False, indent=1))
        if args.auditoria is not None:
            from tests.real import auditoria
            # Sin archivo explícito: la auditoría DE ESTE BANCO (el holdout no
            # hereda los veredictos del banco real).
            audit = auditoria.load(args.auditoria or auditoria.default_path(BANCO))
            audited = auditoria.summarize(data["resultados"], audit)
            print("Auditada:", json.dumps({k: audited[k] for k in ("aciertos", "evaluados", "auditados", "sin_auditar")},
                                          ensure_ascii=False))
        return 0

    from tests.real import run_real

    run_real.SIM["on"] = args.sim
    out_dir = Path(args.out) if args.out else HERE / "out" / ("banco_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    out_dir.mkdir(parents=True, exist_ok=True)
    print("Construyendo el sistema (Power BI real + MedGemma)...", flush=True)
    run_real.build_system()
    meta = run_real.meta_info()
    meta["commit"] = _commit()
    print(" · ".join(f"{k}: {v}" for k, v in meta.items()), flush=True)
    results = []
    selected = load_cases(args)
    for i, case in enumerate(selected, 1):
        started = time.perf_counter()
        truth = None
        if case.get("verdad") and not args.sim:
            truth = compute_truths(case["verdad"])
        try:
            turns = run_case(case, run_real)
        except Exception as exc:  # el banco sigue con el siguiente caso
            turns = [{"via": "texto", "text": case["pregunta"], "answer": None, "status": "error", "route": None,
                      "error": f"{type(exc).__name__}: {exc}", "dax": [], "buttons": [], "seconds": 0}]
        evaluation = evaluate(case, turns, truth)
        seconds = round(sum(t.get("seconds") or 0 for t in turns), 1)
        results.append({"id": case["id"], "tablero": case["tablero"], "tipo": case["tipo"],
                        "pregunta": case["pregunta"], "verdad": truth, "turnos": turns, "eval": evaluation,
                        "segundos": seconds, "reloj_s": round(time.perf_counter() - started, 1)})
        mark = {True: "OK ", False: "MAL", None: " ? "}[evaluation["correcto"]]
        print(f"[{i}/{len(selected)}] {mark} {case['id']} {seconds:5.1f}s {evaluation['fallas']} "
              f"{(turns[-1].get('answer') or '')[:90]!r}", flush=True)
        (out_dir / "resultados.json").write_text(
            json.dumps({"meta": meta, "resultados": results}, ensure_ascii=False, indent=1, default=str),
            encoding="utf-8")
    s = write_summary(out_dir, results, meta)
    print(json.dumps(s, ensure_ascii=False, indent=1))
    print("Resultados en", out_dir)
    return 0


def _commit():
    import subprocess
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(HERE), capture_output=True,
                              text=True, timeout=5).stdout.strip()
    except Exception:
        return None


if __name__ == "__main__":
    sys.exit(main())
