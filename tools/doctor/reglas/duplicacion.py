"""Duplicación: funciones idénticas (tipo 1), casi idénticas (tipo 2) y utilidades repetidas."""
from __future__ import annotations

import ast
import builtins
import hashlib
import keyword
import re

from tools.doctor.modelo import Hallazgo
from tools.doctor.repo import Repo, bajo

_BUILTINS = set(dir(builtins))


def _cuerpo(funcion) -> list[ast.stmt]:
    cuerpo = list(funcion.body)
    if cuerpo and isinstance(cuerpo[0], ast.Expr) and isinstance(cuerpo[0].value, ast.Constant) \
            and isinstance(cuerpo[0].value.value, str):
        cuerpo = cuerpo[1:]
    return cuerpo


_DEF = re.compile(r"^(?:async\s+)?def\s+\w+")
_FICHA = re.compile(r"[rbuf]{0,2}\"(?:[^\"\\]|\\.)*\"|[rbuf]{0,2}'(?:[^'\\]|\\.)*'|\b\d[\w.]*|(?<![.\w])[A-Za-z_]\w*")


def _texto(lineas: list[str], f) -> str:
    """Texto de la función sin nombre, docstring, sangría, líneas vacías ni comentarios."""
    cuerpo = _cuerpo(f.nodo)
    inicio = cuerpo[0].lineno if cuerpo else f.fin + 1
    fin_cabecera = max(f.nodo.body[0].lineno - 1, f.linea)
    cabecera = _DEF.sub("def", " ".join(x.strip() for x in lineas[f.linea - 1: fin_cabecera]))
    resto = (x.strip() for x in lineas[max(inicio - 1, fin_cabecera): f.fin])
    return cabecera + "\n" + "\n".join(x for x in resto if x and not x.startswith("#"))


def _firma_exacta(texto: str) -> str:
    return hashlib.sha1(texto.encode("utf-8")).hexdigest()


def _firma_normalizada(texto: str) -> str:
    """Mismo texto con identificadores locales y literales anonimizados (clones tipo 2)."""
    nombres: dict[str, int] = {}

    def ficha(m: re.Match) -> str:
        t = m.group(0)
        if t[-1] in "\"'":
            return "S"
        if t[0].isdigit():
            return "N"
        if keyword.iskeyword(t) or t in _BUILTINS:
            return t
        return f"v{nombres.setdefault(t, len(nombres))}"

    return hashlib.sha1(_FICHA.sub(ficha, texto).encode("utf-8")).hexdigest()


def _h(regla, severidad, archivo, linea, mensaje, sugerencia, clave):
    return Hallazgo("duplicacion", regla, severidad, archivo, linea, mensaje, sugerencia, clave)


def _clones(repo: Repo, cfg: dict) -> list[Hallazgo]:
    exactas: dict[str, list] = {}
    candidatas = []
    for mod in repo.modulos.values():
        if not bajo(mod.ruta, cfg["aplica_a"]):
            continue
        lineas = None
        for f in mod.funciones:
            largo = f.fin - f.linea + 1
            if largo < cfg["min_lineas"] or len(_cuerpo(f.nodo)) < 2:
                continue
            lineas = lineas if lineas is not None else mod.texto.splitlines()
            texto = _texto(lineas, f)
            exactas.setdefault(_firma_exacta(texto), []).append((mod.ruta, f))
            if largo >= cfg["min_lineas_casi"]:
                candidatas.append((mod.ruta, f, texto))

    salida: list[Hallazgo] = []
    en_grupo_exacto: set[tuple[str, str]] = set()
    for grupo in exactas.values():
        if len(grupo) < 2:
            continue
        grupo.sort(key=lambda x: (x[0], x[1].linea))
        ruta0, f0 = grupo[0]
        for ruta, f in grupo:
            en_grupo_exacto.add((ruta, f.qual))
        for ruta, f in grupo[1:]:
            salida.append(_h(
                "funcion_identica", "media", ruta, f.linea,
                f"`{f.qual}` es idéntica a `{f0.qual}` en {ruta0}:{f0.linea} ({len(grupo)} copias).",
                f"Conservar una sola versión (en la capa más baja que la use) e importarla; borrar `{f.qual}`.",
                f.qual,
            ))

    normalizadas: dict[str, list] = {}
    for ruta, f, texto in candidatas:
        if (ruta, f.qual) not in en_grupo_exacto:
            normalizadas.setdefault(_firma_normalizada(texto), []).append((ruta, f))
    for grupo in normalizadas.values():
        if len(grupo) < 2:
            continue
        grupo.sort(key=lambda x: (x[0], x[1].linea))
        ruta0, f0 = grupo[0]
        for ruta, f in grupo[1:]:
            salida.append(_h(
                "funcion_casi_identica", "baja", ruta, f.linea,
                f"`{f.qual}` repite la estructura de `{f0.qual}` en {ruta0}:{f0.linea} (solo cambian nombres o literales).",
                "Unificar en una función parametrizada y reutilizarla.",
                f.qual,
            ))
    return salida


def _utilidades(repo: Repo, cfg: dict) -> list[Hallazgo]:
    salida: list[Hallazgo] = []
    for util in cfg["utilidades"]:
        llamadas = set(util.get("llamadas", []))
        apariciones: dict[str, int] = {}  # ruta → primera línea
        for mod in repo.modulos.values():
            if not bajo(mod.ruta, util.get("aplica_a", cfg["aplica_a"])):
                continue
            lineas = []
            if llamadas:
                lineas += [c.linea for c in mod.llamadas if c.nombre in llamadas]
            if util.get("patron") == "raiz_proyecto":
                lineas += mod.raiz_proyecto
            if lineas:
                apariciones[mod.ruta] = min(lineas)
        canonico = util.get("canonico") or ""
        if canonico:
            sobrantes = {r: l for r, l in apariciones.items() if r != canonico}
        else:
            sobrantes = apariciones if len(apariciones) > 1 else {}
        for ruta, linea in sorted(sobrantes.items()):
            otras = [r for r in sorted(apariciones) if r not in (ruta, canonico)]
            muestra = (", ".join(otras[:3]) + (f" y {len(otras) - 3} más" if len(otras) > 3 else "")) or "ningún otro"
            destino = (f"Usar `{canonico}`: " if canonico else "") + util.get("sugerencia", "Unificar en un solo módulo.")
            salida.append(_h(
                "utilidad_repetida", "media", ruta, linea,
                (f"Utilidad «{util['nombre']}» reimplementada aquí en vez de usar `{canonico}` ({len(sobrantes)} módulos; también en {muestra})." if canonico else f"Utilidad «{util['nombre']}» reimplementada aquí ({len(apariciones)} módulos; también en {muestra})."),
                destino,
                util["nombre"],
            ))
    return salida


def revisar(repo: Repo) -> list[Hallazgo]:
    cfg = repo.config["duplicacion"]
    return _clones(repo, cfg) + _utilidades(repo, cfg)
