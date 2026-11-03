"""
Lista las menciones «Por confirmar» de la documentación viva (`docs_tableros/<grupo>/md/*.md`).

Agrupa por tablero, archivo, sección y entrada, y extrae la duda concreta (la frase que contiene
«por confirmar»). Ignora el historial y la frase fija del Propósito de los diccionarios
(«las descripciones de negocio marcadas «Por confirmar» las completa quien conoce el tablero»).

Uso (desde la raíz del proyecto):
    python -X utf8 tools/por_confirmar.py                 # listado por tablero
    python -X utf8 tools/por_confirmar.py --resumen       # solo conteos
    python -X utf8 tools/por_confirmar.py --json          # JSON (una fila por mención)
    python -X utf8 tools/por_confirmar.py --grupo tablero_farmacia
    python -X utf8 tools/por_confirmar.py --raiz otra/carpeta

Impacto (para ordenar): 1 = indicador o medida de una tarjeta/visual; 2 = otra medida, columna
clave o entrada de página; 3 = tablas, relaciones, observaciones y metadatos.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

RAIZ_PROYECTO = Path(__file__).resolve().parents[1]
if str(RAIZ_PROYECTO) not in sys.path:
    sys.path.insert(0, str(RAIZ_PROYECTO))

from src.docs_md.formato import (  # noqa: E402
    SECCION_HISTORIAL,
    SECCION_TEXTO,
    ErrorFormato,
    es_diccionario,
    parsear,
)

PATRON = re.compile(r"por\s+confirmar", re.IGNORECASE)
# Frase fija del Propósito de los diccionarios: no es una duda.
FRASE_FIJA = re.compile(r"marcadas\s+«?Por confirmar»?\s+las completa", re.IGNORECASE)


@dataclass
class Mencion:
    tablero: str
    grupo: str
    archivo: str
    pagina: str
    seccion: str
    entrada: str
    duda: str
    tipo: str
    impacto: int


def _frases(texto: str) -> list[str]:
    """Parte el texto en frases sin cortar dentro de `código` ni de «comillas»."""
    frases, actual, codigo, comillas = [], [], False, 0
    i = 0
    while i < len(texto):
        c = texto[i]
        actual.append(c)
        if c == "`":
            codigo = not codigo
        elif c == "«":
            comillas += 1
        elif c == "»":
            comillas = max(0, comillas - 1)
        elif c in ".;" and not codigo and not comillas and (i + 1 == len(texto) or texto[i + 1] == " "):
            frases.append("".join(actual).strip())
            actual = []
        i += 1
    if "".join(actual).strip():
        frases.append("".join(actual).strip())
    return [f for f in frases if f]


def extraer_duda(texto: str) -> str:
    """Frases que mencionan «por confirmar»; si la frase es solo «Por confirmar.», incluye la anterior."""
    frases = _frases(texto)
    elegidas: list[str] = []
    for i, frase in enumerate(frases):
        if not PATRON.search(frase) or FRASE_FIJA.search(frase):
            continue
        if re.fullmatch(r"\(?por confirmar\)?[.;]?", frase.strip(), re.IGNORECASE) and i > 0:
            previa = frases[i - 1]
            if previa not in elegidas:
                elegidas.append(previa)
        if frase not in elegidas:
            elegidas.append(frase)
    return " ".join(elegidas)


def clasificar(duda: str, seccion: str, entrada: str) -> str:
    d = duda.lower()
    if re.search(r"c[aá]lculo:\s*por confirmar", d):
        return "cálculo"
    if re.search(r"unidad[^.]*por confirmar|en unidades o|agregaci[oó]n por confirmar", d):
        return "unidad/agregación"
    if re.search(r"valores|lista exacta|nombres exactos|dominio", d):
        return "valores"
    if re.search(r"bot[oó]n|se llega|nombre de p[aá]gina|en power bi|sin acceso|eliminar|retirar|bloque", d):
        return "navegación/página"
    if re.search(r"visuales?|pbip", d):
        return "visual"
    if re.search(r"meta|sem[aá]foro|umbral", d):
        return "meta/semáforo"
    if re.search(r"fecha|hasta|desde|corte", d):
        return "fechas/vigencia"
    return "descripción"


def impacto(doc_es_diccionario: bool, seccion: str, texto: str) -> int:
    if seccion == "Indicadores":
        return 1
    if doc_es_diccionario and seccion == "Medidas":
        return 1 if re.search(r"Tarjeta|Gráfico|Tabla|Matriz", texto) else 2
    if doc_es_diccionario and seccion in ("Columnas clave", "Columnas calculadas"):
        return 1 if re.search(r"Tarjeta", texto) else 2
    if seccion in ("Visuales", "Reglas de negocio", "Definiciones"):
        return 2
    return 3


def menciones_de_archivo(ruta: Path, grupo: str) -> list[Mencion]:
    try:
        doc = parsear(ruta.read_text(encoding="utf-8"))
    except ErrorFormato as exc:  # pragma: no cover - el validador ya lo detecta
        print(f"AVISO {ruta}: {exc}", file=sys.stderr)
        return []
    tablero = str(doc.meta.get("tablero") or grupo)
    dicc = es_diccionario(doc.meta)
    base = dict(tablero=tablero, grupo=grupo, archivo=ruta.name, pagina=doc.pagina)
    salida: list[Mencion] = []

    for clave in ("nombre_funcional", "bloque"):
        valor = str(doc.meta.get(clave) or "")
        if PATRON.search(valor):
            salida.append(Mencion(**base, seccion="metadatos", entrada=clave, duda=valor,
                                  tipo="navegación/página", impacto=3))
    duda = extraer_duda(doc.proposito)
    if duda:
        salida.append(Mencion(**base, seccion=SECCION_TEXTO, entrada="", duda=duda,
                              tipo=clasificar(duda, SECCION_TEXTO, ""), impacto=3))
    for seccion, entradas in doc.secciones.items():
        if seccion == SECCION_HISTORIAL:
            continue
        for e in entradas:
            if not PATRON.search(e.texto) and not PATRON.search(e.nombre):
                continue
            duda = extraer_duda(e.texto) or e.texto
            salida.append(Mencion(**base, seccion=seccion, entrada=e.nombre, duda=duda,
                                  tipo=clasificar(duda, seccion, e.nombre),
                                  impacto=impacto(dicc, seccion, e.texto)))
    return salida


def recolectar(raiz: Path, grupo: str | None = None) -> list[Mencion]:
    salida: list[Mencion] = []
    for carpeta in sorted(p for p in raiz.iterdir() if (p / "md").is_dir()):
        if grupo and carpeta.name != grupo:
            continue
        for ruta in sorted((carpeta / "md").glob("*.md")):
            salida.extend(menciones_de_archivo(ruta, carpeta.name))
    return salida


def imprimir(menciones: list[Mencion], solo_resumen: bool) -> None:
    por_grupo: dict[str, list[Mencion]] = {}
    for m in menciones:
        por_grupo.setdefault(m.grupo, []).append(m)
    total_dicc = sum(1 for m in menciones if m.archivo.startswith("_diccionario"))
    print(f"Menciones «Por confirmar»: {len(menciones)} (diccionario: {total_dicc}; "
          f"páginas: {len(menciones) - total_dicc})")
    for grupo, lista in por_grupo.items():
        dicc = sum(1 for m in lista if m.archivo.startswith("_diccionario"))
        print(f"\n{grupo} ({lista[0].tablero}): {len(lista)} (diccionario {dicc})")
        if solo_resumen:
            continue
        archivo = None
        for m in sorted(lista, key=lambda x: (x.archivo, x.seccion, x.entrada)):
            if m.archivo != archivo:
                archivo = m.archivo
                print(f"  {archivo}")
            nombre = f" › {m.entrada}" if m.entrada else ""
            print(f"    [{m.impacto}] {m.seccion}{nombre} ({m.tipo}): {m.duda}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raiz", default=str(RAIZ_PROYECTO / "docs_tableros"))
    ap.add_argument("--grupo")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--resumen", action="store_true")
    args = ap.parse_args(argv)
    menciones = recolectar(Path(args.raiz), args.grupo)
    if args.json:
        print(json.dumps([asdict(m) for m in menciones], ensure_ascii=False, indent=1))
    else:
        imprimir(menciones, args.resumen)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
