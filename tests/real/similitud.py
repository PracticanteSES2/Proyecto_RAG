"""
Verificación automática de que un banco NO repite ni parafrasea preguntas de
los otros bancos (tests/real/banco_*.json).

    python -X utf8 -m tests.real.similitud                          # banco_holdout2 contra los demás
    python -X utf8 -m tests.real.similitud tests/real/banco_holdout2.json --top 10   # las más parecidas

Puntaje = máximo de tres medidas sobre el texto normalizado (sin tildes, en
minúsculas, con el lenguaje de chat expandido: q→que, x→por, pa→para…):
  - Jaccard de palabras de contenido (sin palabras vacías, con raíz simple);
  - coseno de trigramas de caracteres;
  - razón de difflib (secuencia).
Una pregunta es «parecida» si el puntaje combinado (media de Jaccard y
trigramas) llega a UMBRAL o la razón de difflib llega a UMBRAL_SECUENCIA.
Los umbrales se calibraron con paráfrasis conocidas (test_bancos): «cuantos
egresos hubo ayer» ~ «cuántos egresos hubo el día de ayer» es parecida;
«camas en transición» ~ «camas bloqueadas» no lo es.
"""
import argparse
import difflib
import json
import math
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
UMBRAL = 0.62
UMBRAL_SECUENCIA = 0.85

CHAT = {"q": "que", "x": "por", "pa": "para", "d": "de", "xq": "porque", "tb": "tambien", "k": "que", "porq": "porque"}
VACIAS = set("""
a al algo alguna algun ante con cual cuales cuando de del donde el ella ellos en entre es esa esas ese eso esos esta
estan estas este esto estos ha hay la las le les lo los mas me mi muy no nos o otra otro para pero por que se segun
sin sobre su sus te tiene tienen todo todos tu un una uno unos y ya yo dame dime oye favor hubo fue fueron van va
son hace hacer ser como cuanto cuanta cuantos cuantas cual tenemos tengo
""".split())


def fold(text):
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    return " ".join(text.casefold().split())


def normalize(text):
    text = fold(text)
    if text.startswith("texto:"):
        text = text[len("texto:"):]
    words = re.findall(r"[a-z0-9%]+", text)
    return " ".join(CHAT.get(w, w) for w in words)


def _stem(word):
    for suf in ("es", "s"):
        if len(word) > 4 and word.endswith(suf):
            return word[: -len(suf)]
    return word


def content(text):
    return {_stem(w) for w in normalize(text).split() if w not in VACIAS}


def _trigrams(text):
    t = f"  {normalize(text)}  "
    return Counter(t[i:i + 3] for i in range(len(t) - 2))


def _cos(a, b):
    num = sum(a[k] * b[k] for k in a.keys() & b.keys())
    den = math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values()))
    return num / den if den else 0.0


def scores(q1, q2):
    c1, c2 = content(q1), content(q2)
    jac = len(c1 & c2) / len(c1 | c2) if (c1 | c2) else 0.0
    tri = _cos(_trigrams(q1), _trigrams(q2))
    seq = difflib.SequenceMatcher(None, normalize(q1), normalize(q2)).ratio()
    return {"jaccard": round(jac, 3), "trigramas": round(tri, 3), "secuencia": round(seq, 3),
            "combinado": round((jac + tri) / 2, 3)}


def parecida(q1, q2):
    s = scores(q1, q2)
    return s["combinado"] >= UMBRAL or s["secuencia"] >= UMBRAL_SECUENCIA, s


def questions(path):
    """[(id, pregunta)] de un banco: casos (pregunta y turnos_extra) o
    conversaciones del banco multiturno (cada turno)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    out = []
    for c in data.get("casos") or []:
        out.append((c["id"], c["pregunta"]))
        for i, extra in enumerate(c.get("turnos_extra") or [], 2):
            out.append((f"{c['id']}.{i}", extra))
    for conv in data.get("conversaciones") or []:
        for t in conv["turnos"]:
            out.append((f"{conv['id']}.{t['n']}", t["entrada"]))
    return out


def other_banks(target):
    target = Path(target).resolve()
    return [p for p in sorted(HERE.glob("banco_*.json")) if p.resolve() != target]


def compare(target, others=None):
    """Para cada pregunta del banco: la más parecida de los otros bancos y
    del mismo banco (otro id)."""
    mine = questions(target)
    pool = [(f"{Path(p).stem}:{i}", q) for p in (others if others is not None else other_banks(target))
            for i, q in questions(p)]
    pool += [(f"{Path(target).stem}:{i}", q) for i, q in mine]
    rows = []
    for cid, q in mine:
        best = None
        for oid, oq in pool:
            if oid.split(":", 1)[1] == cid and oid.startswith(Path(target).stem + ":"):
                continue
            hit, s = parecida(q, oq)
            key = (hit, s["combinado"], s["secuencia"])
            if best is None or key > best[0]:
                best = (key, {"id": cid, "pregunta": q, "otro": oid, "otra": oq, "parecida": hit,
                              "puntaje": s["combinado"], **s})
        if best:
            rows.append(best[1])
    rows.sort(key=lambda r: (-int(r["parecida"]), -r["combinado"]))
    return rows


def check(target, others=None):
    """Preguntas parecidas (lista vacía = el banco pasa)."""
    return [r for r in compare(target, others) if r["parecida"]]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Similitud de un banco contra los demás bancos reales.")
    parser.add_argument("banco", nargs="?", default=str(HERE / "banco_holdout2.json"))
    parser.add_argument("--top", type=int, default=0, help="muestra las N preguntas más parecidas")
    args = parser.parse_args(argv)
    rows = compare(args.banco)
    for r in rows[: args.top] if args.top else [r for r in rows if r["parecida"]]:
        mark = "PARECIDA" if r["parecida"] else "ok"
        print(f"{mark:8} {r['id']:6} ~ {r['otro']:28} comb={r['combinado']:.2f} seq={r['secuencia']:.2f} "
              f"| {r['pregunta']!r} ~ {r['otra']!r}")
    hits = [r for r in rows if r["parecida"]]
    print(f"{len(hits)} parecidas de {len(rows)} preguntas (umbral combinado {UMBRAL}, secuencia {UMBRAL_SECUENCIA})")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
