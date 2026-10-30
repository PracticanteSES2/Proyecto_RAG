"""
Auditoría del banco real: veredictos revisados a mano (tests/real/auditoria.json),
causa raíz de cada falla y comparación entre corridas.

Criterio (tests/real/RETOMAR.md):
- la verdad es la cifra que el usuario ve en el tablero (medida + filtros de
  visual y de página + periodo);
- una contrapregunta solo es legítima si varias fuentes responden la pregunta
  tal como está con cifras distintas.

Un veredicto auditado solo se aplica si la respuesta del bot es la MISMA que se
auditó (huella de la respuesta): en una corrida nueva, los casos cuya respuesta
cambió quedan con el veredicto automático («sin auditar»).
"""
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

from tests.real import run_banco

AUDITORIA = Path(__file__).resolve().parent / "auditoria.json"

CAUSAS = {
    "1": "Filtros de página/visual no aplicados (valor general)",
    "2": "Filtros espurios por coincidencia parcial de palabras",
    "3": "Columna de fecha equivocada o tablero del día para periodos",
    "4": "Contrapregunta innecesaria",
    "5": "Indicador equivocado",
    "6": "Pregunta de datos enviada a RAG",
    "7": "Opciones mal rotuladas",
    "8": "Agrupación ignorada",
    "9": "Otra (error de DAX, cifra inventada, lentitud)",
}

VEREDICTOS = ("acierto", "falla", "inconcluso", "no_evaluado")


def huella(answer):
    """Huella de la respuesta final (los primeros 1.500 caracteres, como en resultado.json)."""
    text = run_banco.fold(str(answer or "")[:1500])
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def load(path=None):
    path = Path(path) if path else AUDITORIA
    if not path.exists():
        return {"casos": {}}
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- veredictos
def _last_answer(result):
    turns = result.get("turnos") or []
    return (turns[-1].get("answer") if turns else None) or ""


def auto_verdict(result):
    ev = result["eval"]
    if ev["correcto"] is None:
        return "inconcluso" if (ev.get("detalle") or {}).get("inconcluso") else "no_evaluado"
    if ev["correcto"] and "contrapregunta" not in ev["fallas"]:
        return "acierto"
    return "falla"


def verdict(result, audit, case=None):
    """{"veredicto", "fuente": auditado|automático, "fallas", "causas"}."""
    item = (audit or {}).get("casos", {}).get(result["id"])
    if item and item.get("huella") == huella(_last_answer(result)):
        return {"veredicto": item["veredicto"], "fuente": "auditado", "fallas": item.get("fallas") or [],
                "causas": [str(c) for c in item.get("causas") or []], "nota": item.get("nota")}
    v = auto_verdict(result)
    causas = causa_raiz(case or {}, result) if v == "falla" else []
    return {"veredicto": v, "fuente": "automático", "fallas": list(result["eval"]["fallas"]), "causas": causas,
            "nota": None}


# ---------------------------------------------------------------- causa raíz
_FILTER_COLS = (
    re.compile(r"\bALL\s*\(\s*('[^']+'|[\w ]+?)\s*\[([^\]]+)\]\s*\)", re.I),
    re.compile(r"\bTREATAS\s*\(\s*\{[^}]*\}\s*,\s*('[^']+'|[\w ]+?)\s*\[([^\]]+)\]", re.I),
)


def _filter_cols(dax):
    out = set()
    for rx in _FILTER_COLS:
        out |= {(run_banco.fold(t.strip("'")), run_banco.fold(c)) for t, c in rx.findall(dax or "")}
    return out


def _is_date(col):
    table, name = col
    return any(w in table or w in name for w in ("fecha", "date", "calendario"))


def _filter_cause(case, last):
    """2 = filtro que la pregunta no pide; 3 = otra columna de fecha (o sin
    datos con una fecha); 1 = faltan los filtros del visual o de la página."""
    answer = run_banco.fold(last.get("answer"))
    if "valor general" in answer or "sin los filtros" in answer:
        return "1"
    if last.get("status") == "unsupported_filter":
        return "2"
    truth_cols = set()
    for src in run_banco.truth_sources(case):
        truth_cols |= _filter_cols(src["dax"])
    bot_cols = set()
    for d in last.get("dax") or []:
        bot_cols |= _filter_cols(d.get("dax"))
    if any(not _is_date(c) for c in bot_cols - truth_cols):
        return "2"
    bot_dates = {c for c in bot_cols if _is_date(c)}
    truth_dates = {c for c in truth_cols if _is_date(c)}
    if bot_dates - truth_dates or (last.get("status") == "empty_result" and bot_dates):
        return "3"
    return "1"


def causa_raiz(case, result):
    """Causa raíz aproximada (sin auditar) de una falla automática."""
    ev = result["eval"]
    fallas = ev["fallas"]
    detail = ev.get("detalle") or {}
    turns = result.get("turnos") or []
    last = turns[-1] if turns else {}
    out = []
    if "contrapregunta" in fallas:
        out.append("4")
    if detail.get("enrutamiento") == "rag":
        out.append("6")
    elif "indicador" in fallas:
        out.append("5")
    elif "agrupacion" in fallas:
        out.append("8")
    elif "filtro" in fallas:
        out.append(_filter_cause(case, last))
    elif any(f in fallas for f in ("dax", "inventada", "rag")):
        out.append("9")
    if not out:
        out.append("9")
    return out


# ---------------------------------------------------------------- resumen
def summarize(results, audit=None, cases=None):
    cases = cases or {}
    board = defaultdict(lambda: [0, 0])
    por_causa = defaultdict(list)
    veredictos = {}
    auditados = 0
    for r in results:
        case = cases.get(r["id"]) or r.get("caso") or {}
        v = verdict(r, audit, case)
        veredictos[r["id"]] = v
        auditados += v["fuente"] == "auditado"
        if v["veredicto"] not in ("acierto", "falla"):
            continue
        name = case.get("tablero") or r["tablero"]
        board[name][1] += 1
        if v["veredicto"] == "acierto":
            board[name][0] += 1
        else:
            for c in v["causas"] or ["9"]:
                por_causa[c].append(r["id"])
    ok = sum(b[0] for b in board.values())
    total = sum(b[1] for b in board.values())
    return {
        "aciertos": ok, "evaluados": total, "auditados": auditados, "sin_auditar": len(results) - auditados,
        "inconclusos": [i for i, v in veredictos.items() if v["veredicto"] == "inconcluso"],
        "por_tablero": {k: {"aciertos": v[0], "evaluados": v[1]} for k, v in sorted(board.items())},
        "por_causa": dict(sorted(por_causa.items(), key=lambda kv: (-len(kv[1]), kv[0]))),
        "fallas_totales": total - ok,
        "veredictos": veredictos,
    }


def pct(a, b):
    return f"{100 * a / b:.0f} %" if b else "—"


# ---------------------------------------------------------------- resultado.json compacto
def from_compact(row):
    """Reconstruye un resultado «crudo» (formato de run_banco) desde una fila de
    resultado.json (formato compacto de correr_todo) para volver a evaluarlo."""
    truth = row.get("verdad")
    if truth is not None:
        truth = dict(truth)
        if "grupos_top" in truth:
            truth["grupos"] = truth.pop("grupos_top")
        if truth.get("alternativas"):
            truth["alternativas"] = [{**a, "grupos": a.pop("grupos_top")} if "grupos_top" in a else a
                                     for a in (dict(x) for x in truth["alternativas"])]
    turns = []
    for t in row.get("turnos") or []:
        turns.append({
            "via": t.get("via"), "text": t.get("texto"), "answer": t.get("respuesta"), "status": t.get("estado"),
            "route": t.get("ruta"), "stage": t.get("etapa"), "metric": t.get("metrica"),
            "semantic_model": t.get("modelo"), "seconds": t.get("segundos"), "error": t.get("error"),
            "buttons": [{"id": str(i), "label": label} for i, label in enumerate(t.get("opciones") or [], 1)],
            "dax": [{"semantic_model": d.get("modelo"), "status": d.get("estado"), "row_count": d.get("filas"),
                     "dax": d.get("dax"), "error": d.get("error")} for d in t.get("dax") or []],
            "eleccion": t.get("eleccion"),
        })
    return {"id": row["id"], "tablero": row["tablero"], "tipo": row["tipo"], "pregunta": row["pregunta"],
            "verdad": truth, "turnos": turns, "segundos": row.get("segundos"),
            "eval": {"correcto": row.get("correcto"), "fallas": [], "detalle": row.get("detalle") or {}}}


def load_previous(path, cases):
    """Corrida anterior (resultado.json compacto) re-evaluada con el comparador actual."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    results = []
    for row in data["casos"]:
        r = from_compact(row)
        case = cases.get(r["id"])
        if case is not None:
            r["tablero"] = case["tablero"]   # el tablero del banco actual (p. ej. EP03 pasó al Briefing)
            r["eval"] = run_banco.evaluate(case, r["turnos"], r["verdad"])
        results.append(r)
    return data.get("meta") or {}, data.get("resumen") or {}, results


# ---------------------------------------------------------------- informe
_MARK = {"acierto": "sí", "falla": "no", "inconcluso": "inconcluso", "no_evaluado": "—"}


def _cell(v):
    if v is None:
        return "(no estaba)"
    text = _MARK[v["veredicto"]]
    if v["veredicto"] == "falla" and v["causas"]:
        text += " (" + ", ".join(v["causas"]) + ")"
    return text + (" ·a" if v["fuente"] == "auditado" else "")


def _change(before, after):
    if before is None or after is None:
        return "nuevo" if before is None else "quitado"
    rank = {"falla": 0, "acierto": 1}
    b, a = before["veredicto"], after["veredicto"]
    if b in rank and a in rank and b != a:
        return "MEJORA" if rank[a] > rank[b] else "EMPEORA"
    if b != a:
        return f"{_MARK[b]} → {_MARK[a]}"
    if b == "falla" and before["causas"] != after["causas"]:
        return "otra causa"
    return "igual"


def section_tasas(auto, audited):
    lines = ["## Tasas", "",
             "| Medida | Aciertos | Tasa |", "|---|---|---|",
             f"| Automática (comparador) | {auto['aciertos']}/{auto['evaluados']} | {pct(auto['aciertos'], auto['evaluados'])} |",
             f"| **Auditada** | **{audited['aciertos']}/{audited['evaluados']}** | "
             f"**{pct(audited['aciertos'], audited['evaluados'])}** |", "",
             f"Auditada = veredicto de `tests/real/auditoria.json` cuando la respuesta del bot es la misma que se "
             f"auditó ({audited['auditados']} casos) y veredicto automático en el resto ({audited['sin_auditar']}). "
             f"Inconclusos (no cuentan): {', '.join(audited['inconclusos']) or 'ninguno'}.", ""]
    return lines


def section_tableros(auto, audited):
    lines = ["## Por tablero", "", "| Tablero | Automática | Auditada |", "|---|---|---|"]
    boards = sorted(set(auto["por_tablero"]) | set(audited["por_tablero"]))
    for b in boards:
        a = auto["por_tablero"].get(b, {"aciertos": 0, "evaluados": 0})
        d = audited["por_tablero"].get(b, {"aciertos": 0, "evaluados": 0})
        lines.append(f"| {b} | {a['aciertos']}/{a['evaluados']} ({pct(a['aciertos'], a['evaluados'])}) "
                     f"| {d['aciertos']}/{d['evaluados']} ({pct(d['aciertos'], d['evaluados'])}) |")
    return lines + [""]


def section_causas(audited):
    total = audited["fallas_totales"]
    lines = ["## Por causa raíz", "",
             f"Sobre {total} fallas (un caso puede tener varias causas). Auditadas: causa de la auditoría; "
             "sin auditar: causa aproximada por el DAX del bot frente al de verdad.", "",
             "| Causa raíz | Casos | % de las fallas | Ids |", "|---|---|---|---|"]
    for c, ids in audited["por_causa"].items():
        lines.append(f"| {c}. {CAUSAS.get(c, c)} | {len(ids)} | {pct(len(ids), total)} | {', '.join(ids)} |")
    return lines + [""]


def section_comparacion(prev_meta, prev_resumen, prev_audited, prev_auto, audited, auto, path):
    lines = ["## Comparación con la corrida anterior", "",
             f"Anterior: `{path}` (commit {prev_meta.get('commit')}, {prev_meta.get('fecha')}). "
             "Las dos corridas se evalúan con el MISMO comparador y la misma auditoría.", "",
             "| Medida | Anterior | Actual | Δ |", "|---|---|---|---|"]

    def row(name, p, c):
        dp = 100 * p["aciertos"] / p["evaluados"] if p["evaluados"] else 0
        dc = 100 * c["aciertos"] / c["evaluados"] if c["evaluados"] else 0
        return (f"| {name} | {p['aciertos']}/{p['evaluados']} ({pct(p['aciertos'], p['evaluados'])}) "
                f"| {c['aciertos']}/{c['evaluados']} ({pct(c['aciertos'], c['evaluados'])}) | {dc - dp:+.0f} pp |")

    if prev_resumen.get("evaluados"):
        lines.append(f"| Automática guardada en la anterior | {prev_resumen['aciertos']}/{prev_resumen['evaluados']} "
                     f"({pct(prev_resumen['aciertos'], prev_resumen['evaluados'])}) | — | — |")
    lines += [row("Automática (comparador actual)", prev_auto, auto), row("**Auditada**", prev_audited, audited), "",
              "| Tablero | Anterior (auditada) | Actual (auditada) | Δ aciertos |", "|---|---|---|---|"]
    for b in sorted(set(prev_audited["por_tablero"]) | set(audited["por_tablero"])):
        p = prev_audited["por_tablero"].get(b, {"aciertos": 0, "evaluados": 0})
        c = audited["por_tablero"].get(b, {"aciertos": 0, "evaluados": 0})
        lines.append(f"| {b} | {p['aciertos']}/{p['evaluados']} | {c['aciertos']}/{c['evaluados']} "
                     f"| {c['aciertos'] - p['aciertos']:+d} |")
    lines += ["", "| Causa raíz | Anterior | Actual | Δ |", "|---|---|---|---|"]
    for c in sorted(set(prev_audited["por_causa"]) | set(audited["por_causa"]), key=int):
        p = len(prev_audited["por_causa"].get(c, []))
        n = len(audited["por_causa"].get(c, []))
        lines.append(f"| {c}. {CAUSAS.get(c, c)} | {p} | {n} | {n - p:+d} |")
    lines += ["", "Por caso («·a» = veredicto auditado; entre paréntesis, la causa raíz):", "",
              "| Caso | Anterior | Actual | Cambio |", "|---|---|---|---|"]
    ids = list(audited["veredictos"]) + [i for i in prev_audited["veredictos"] if i not in audited["veredictos"]]
    counts = defaultdict(int)
    for i in ids:
        b, a = prev_audited["veredictos"].get(i), audited["veredictos"].get(i)
        ch = _change(b, a)
        counts[ch] += 1
        lines.append(f"| {i} | {_cell(b)} | {_cell(a)} | {ch} |")
    lines += ["", "Resumen de cambios: " + ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())), ""]
    return lines
