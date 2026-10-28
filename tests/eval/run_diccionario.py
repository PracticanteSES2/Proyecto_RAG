"""
Prueba de recuperación del diccionario de variables (`_diccionario*.md`).

Para cada pregunta de `diccionario_preguntas.json` llama al retriever REAL del proyecto
(`HybridRetriever.search_general`, lo mismo que usa `RagAnswerEngine`) y mide si la entrada
esperada (grupo + nombre exacto de la entrada del diccionario) aparece entre los resultados:

  hit@1, hit@5, MRR  -> «entrada»: el chunk ES la entrada (medida con ese nombre, columna T[C],
                        relación A[x] → B[y], fuente de datos T, observación N), venga del
                        diccionario o de una página del mismo grupo.
  mencion@5          -> algún chunk del grupo menciona el identificador (criterio laxo, sirve
                        para comparar con un índice sin diccionario).
  dic@1              -> el primer resultado es un chunk del diccionario («DICCIONARIO ...»).

Se pueden comparar varios índices (p. ej. antes/después de agregar el diccionario):

    python -X utf8 -m tests.eval.run_diccionario                       # índice del checkout principal
    python -X utf8 -m tests.eval.run_diccionario --indice antes=C:/x/before_root --indice despues=C:/x/after_root
    python -X utf8 -m tests.eval.run_diccionario --validar             # solo comprueba que las entradas existen

Cada `--indice` es una raíz de proyecto (contiene data/vector_db/qdrant) o la carpeta qdrant.
La carpeta Qdrant se COPIA a un temporal antes de abrirla (Qdrant local crea un .lock y no admite
dos clientes): el data/ original nunca se toca. Informe: <out>/diccionario.md y .json.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import time
import unicodedata
from collections import defaultdict
from pathlib import Path

sys.dont_write_bytecode = True
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

PREGUNTAS = Path(__file__).resolve().parent / "diccionario_preguntas.json"
TOP_K = 5


# ---------------------------------------------------------------------------
# Normalización y coincidencias
# ---------------------------------------------------------------------------

def norm(texto) -> str:
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto.casefold()).strip()


def _palabra(clave: str, texto: str) -> bool:
    """`clave` aparece en `texto` como palabra completa (ambos ya normalizados)."""
    return re.search(r"(?<![\w])" + re.escape(clave) + r"(?![\w])", texto) is not None


_REL = re.compile(r"^(?P<a>.+?\[[^\]]+\])\s*→\s*(?P<b>.+?\[[^\]]+\])$")
_COL = re.compile(r"^(?P<t>[^\[\]]+)\[(?P<c>[^\[\]]+)\]$")
_MED = re.compile(r"^\[(?P<m>[^\[\]]+)\]$")


def tipo_entrada(entrada: str) -> str:
    entrada = entrada.strip()
    if _REL.match(entrada):
        return "relacion"
    if _MED.match(entrada):
        return "medida"
    if _COL.match(entrada):
        return "columna"
    return "nombre"   # tabla u observación


def es_entrada(chunk: dict, esperado: dict) -> bool:
    """El chunk ES la entrada esperada (criterio estricto)."""
    entrada = esperado["entrada"].strip()
    texto = norm(chunk.get("text"))
    tipo = tipo_entrada(entrada)
    if tipo == "relacion":
        m = _REL.match(entrada)
        return norm(m.group("a")) in texto and norm(m.group("b")) in texto
    if tipo == "medida":
        nombre = norm(_MED.match(entrada).group("m"))
        return norm(chunk.get("measure")) == nombre
    if tipo == "columna":
        m = _COL.match(entrada)
        t, c = norm(m.group("t")), norm(m.group("c"))
        if f"{t}[{c}]" in texto:
            return True
        return (chunk.get("chunk_type") == "calculated_column"
                and f"columna calculada: {c}" in texto and f"tabla: {t}" in texto)
    nombre = norm(entrada)
    if esperado.get("seccion") == "Observaciones":
        return f"nota u observacion: {nombre}:" in texto
    return (f"fuente de datos: {nombre}:" in texto or f"tabla power bi: {nombre}" in texto)


def menciona(chunk: dict, esperado: dict) -> bool:
    """Algún identificador de la entrada aparece en el chunk (criterio laxo)."""
    entrada = esperado["entrada"].strip()
    texto = norm(chunk.get("text"))
    tipo = tipo_entrada(entrada)
    if tipo == "relacion":
        m = _REL.match(entrada)
        cols = [norm(_COL.match(x).group("c")) for x in (m.group("a"), m.group("b"))]
        return all(_palabra(c, texto) for c in cols)
    if tipo == "medida":
        nombre = norm(_MED.match(entrada).group("m"))
        return norm(chunk.get("measure")) == nombre or f"[{nombre}]" in texto or _palabra(nombre, texto)
    if tipo == "columna":
        return _palabra(norm(_COL.match(entrada).group("c")), texto)
    return _palabra(norm(entrada), texto)


def es_diccionario(chunk: dict) -> bool:
    return norm(chunk.get("dashboard")).startswith("diccionario")


# ---------------------------------------------------------------------------
# Validación contra los .md
# ---------------------------------------------------------------------------

def raiz_md() -> Path:
    env = os.getenv("DOCS_MD_ROOT", "").strip()
    return Path(env) if env else REPO_ROOT / "docs_tableros"


def entradas_diccionario(raiz: Path | None = None) -> dict:
    """{(grupo, archivo, seccion): {nombre de entrada}} de todos los _diccionario*.md."""
    from src.docs_md.formato import parsear

    raiz = raiz or raiz_md()
    salida = defaultdict(set)
    for archivo in sorted(raiz.glob("*/md/_diccionario*.md")):
        grupo = archivo.parent.parent.name
        doc = parsear(archivo.read_text(encoding="utf-8"))
        for seccion, entradas in doc.secciones.items():
            for e in entradas:
                salida[(grupo, archivo.name, seccion)].add(e.nombre.strip())
    return salida


def validar(casos: list, raiz: Path | None = None) -> list[str]:
    indice = entradas_diccionario(raiz)
    errores = []
    for caso in casos:
        for esp in [caso["esperado"], *caso.get("alternativas", [])]:
            archivo = esp.get("archivo", "_diccionario.md")
            clave = (caso["grupo"], archivo, esp["seccion"])
            if esp["entrada"].strip() not in indice.get(clave, set()):
                errores.append(f"{caso['id']}: no existe «{esp['entrada']}» en {caso['grupo']}/{archivo} › {esp['seccion']}")
    return errores


# ---------------------------------------------------------------------------
# Retriever
# ---------------------------------------------------------------------------

def _principal() -> Path:
    from tests.realistic.harness import main_checkout
    return main_checkout()


def ruta_qdrant(valor: str | Path) -> Path:
    ruta = Path(valor)
    for candidata in (ruta, ruta / "vector_db" / "qdrant", ruta / "data" / "vector_db" / "qdrant"):
        if (candidata / "collection").exists() or (candidata / "meta.json").exists():
            return candidata
    raise FileNotFoundError(f"No encontré una carpeta Qdrant en {ruta}")


def abrir_retriever(qdrant: Path, tmp: Path):
    """HybridRetriever sobre una COPIA de la carpeta Qdrant."""
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    from src.rag.retriever import HybridRetriever

    copia = tmp / "qdrant"
    shutil.copytree(qdrant, copia, ignore=lambda d, n: [x for x in n if x == ".lock"])
    return HybridRetriever(copia)


def evaluar_indice(retriever, casos: list, limite: int) -> list[dict]:
    filas = []
    for caso in casos:
        esperados = [caso["esperado"], *caso.get("alternativas", [])]
        inicio = time.perf_counter()
        resultados = retriever.search_general(question=caso["pregunta"], limit=max(limite, TOP_K)) or []
        ms = (time.perf_counter() - inicio) * 1000
        rango = rango_mencion = None
        top = []
        for i, r in enumerate(resultados[:TOP_K], start=1):
            del_grupo = r.get("source_group") == caso["grupo"]
            exacta = del_grupo and any(es_entrada(r, e) for e in esperados)
            mencion = del_grupo and any(menciona(r, e) for e in esperados)
            if exacta and rango is None:
                rango = i
            if (mencion or exacta) and rango_mencion is None:
                rango_mencion = i
            top.append({
                "rango": i, "grupo": r.get("source_group"), "pagina": r.get("dashboard"),
                "tipo": r.get("chunk_type"), "medida": r.get("measure"),
                "score": r.get("score"), "entrada": exacta, "mencion": mencion,
                "texto": norm(r.get("text"))[:160],
            })
        filas.append({
            "id": caso["id"], "grupo": caso["grupo"], "tecnico": bool(caso.get("tecnico")),
            "pregunta": caso["pregunta"], "esperado": caso["esperado"]["entrada"],
            "rango": rango, "rango_mencion": rango_mencion,
            "dic_top1": bool(resultados) and es_diccionario(resultados[0]),
            "sin_resultados": not resultados, "ms": round(ms, 1), "top": top,
        })
    return filas


def metricas(filas: list[dict]) -> dict:
    n = len(filas) or 1
    return {
        "n": len(filas),
        "hit@1": sum(1 for f in filas if f["rango"] == 1) / n,
        "hit@5": sum(1 for f in filas if f["rango"]) / n,
        "mrr": sum(1 / f["rango"] for f in filas if f["rango"]) / n,
        "mencion@5": sum(1 for f in filas if f["rango_mencion"]) / n,
        "dic@1": sum(1 for f in filas if f["dic_top1"]) / n,
        "sin_resultados": sum(1 for f in filas if f["sin_resultados"]),
    }


def agrupar(filas: list[dict]) -> dict:
    grupos = defaultdict(list)
    for f in filas:
        grupos[f["grupo"]].append(f)
    salida = {g: metricas(v) for g, v in sorted(grupos.items())}
    salida["_naturales"] = metricas([f for f in filas if not f["tecnico"]])
    salida["_tecnicas"] = metricas([f for f in filas if f["tecnico"]])
    salida["_total"] = metricas(filas)
    return salida


# ---------------------------------------------------------------------------
# Informe
# ---------------------------------------------------------------------------

def _pct(x: float) -> str:
    return f"{100 * x:.0f}%"


def informe_md(resultados: dict) -> str:
    etiquetas = list(resultados)
    lineas = ["# Recuperación del diccionario de variables", "",
              f"Preguntas: {len(next(iter(resultados.values()))['filas'])}. "
              "Métricas sobre `search_general` (top 5). «entrada» = el chunk es la entrada esperada; "
              "«mención» = un chunk del grupo nombra el identificador; dic@1 = primer resultado del diccionario.", ""]
    cab = "| Tablero | n | " + " | ".join(f"{e} hit@1 | {e} hit@5 | {e} MRR | {e} mención@5" for e in etiquetas) + " |"
    lineas += [cab, "|" + "---|" * (2 + 4 * len(etiquetas))]
    claves = list(next(iter(resultados.values()))["metricas"])
    for g in claves:
        celdas = []
        for e in etiquetas:
            m = resultados[e]["metricas"][g]
            celdas += [_pct(m["hit@1"]), _pct(m["hit@5"]), f"{m['mrr']:.2f}", _pct(m["mencion@5"])]
        n = resultados[etiquetas[0]]["metricas"][g]["n"]
        nombre = f"**{g.strip('_')}**" if g.startswith("_") else g.replace("tablero_", "")
        lineas.append(f"| {nombre} | {n} | " + " | ".join(celdas) + " |")
    for e in etiquetas:
        m = resultados[e]["metricas"]["_total"]
        lineas.append(f"\n- `{e}`: dic@1 {_pct(m['dic@1'])}, sin resultados {m['sin_resultados']}.")
    ultimo = etiquetas[-1]
    fallos = [f for f in resultados[ultimo]["filas"] if not f["rango"]]
    lineas += ["", f"## Fallos en `{ultimo}` (entrada fuera del top 5)", ""]
    for f in fallos:
        primero = f["top"][0] if f["top"] else {}
        lineas.append(f"- `{f['id']}` «{f['pregunta']}» espera `{f['esperado']}`; top1: "
                      f"{primero.get('grupo')} › {primero.get('pagina')} › {primero.get('tipo')} "
                      f"«{(primero.get('texto') or '')[:100]}»")
    return "\n".join(lineas) + "\n"


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--indice", action="append", default=[],
                        help="etiqueta=ruta (raíz de proyecto o carpeta qdrant); repetible. "
                             "Por defecto: despues=<checkout principal>/data")
    parser.add_argument("--preguntas", default=str(PREGUNTAS))
    parser.add_argument("--case", default="", help="ids separados por coma")
    parser.add_argument("--limit", type=int, default=8, help="resultados pedidos a search_general")
    parser.add_argument("--out", default=None)
    parser.add_argument("--validar", action="store_true", help="solo valida las entradas esperadas")
    args = parser.parse_args(argv)

    casos = json.loads(Path(args.preguntas).read_text(encoding="utf-8"))["casos"]
    if args.case:
        ids = {c.strip() for c in args.case.split(",") if c.strip()}
        casos = [c for c in casos if c["id"] in ids]
    errores = validar(casos)
    print(f"{len(casos)} preguntas; {len(errores)} entradas esperadas inexistentes")
    for e in errores:
        print("  -", e)
    if args.validar:
        return 1 if errores else 0

    indices = []
    for item in args.indice or [f"despues={_principal() / 'data'}"]:
        etiqueta, _, ruta = item.partition("=")
        indices.append((etiqueta.strip(), ruta_qdrant(ruta.strip())))

    resultados = {}
    for etiqueta, qdrant in indices:
        with tempfile.TemporaryDirectory(prefix="dic_eval_") as tmp:
            retriever = abrir_retriever(qdrant, Path(tmp))
            try:
                filas = evaluar_indice(retriever, casos, args.limit)
            finally:
                retriever.close()
        resultados[etiqueta] = {"qdrant": str(qdrant), "filas": filas, "metricas": agrupar(filas)}
        m = resultados[etiqueta]["metricas"]["_total"]
        print(f"[{etiqueta}] hit@1 {_pct(m['hit@1'])} hit@5 {_pct(m['hit@5'])} MRR {m['mrr']:.2f} "
              f"mención@5 {_pct(m['mencion@5'])} dic@1 {_pct(m['dic@1'])}")

    out = Path(args.out) if args.out else REPO_ROOT / "tests" / "eval" / "out" / f"diccionario-{time.strftime('%Y%m%d-%H%M%S')}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "diccionario.json").write_text(json.dumps(resultados, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "diccionario.md").write_text(informe_md(resultados), encoding="utf-8")
    print("Informe:", out / "diccionario.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
