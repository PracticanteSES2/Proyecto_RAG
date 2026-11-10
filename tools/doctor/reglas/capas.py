"""Capas e importaciones: prohibidas, capas invertidas, ciclos e importaciones rotas."""
from __future__ import annotations

from tools.doctor.modelo import Hallazgo
from tools.doctor.repo import Repo


def _h(regla, severidad, archivo, linea, mensaje, sugerencia, clave):
    return Hallazgo("capas", regla, severidad, archivo, linea, mensaje, sugerencia, clave)


def _prefijo(modulo: str, prefijo: str) -> bool:
    return modulo == prefijo or modulo.startswith(prefijo + ".")


def capa_de(modulo: str, orden: list[dict]) -> tuple[int, str] | None:
    mejor = None
    for i, capa in enumerate(orden):
        for p in capa["modulos"]:
            if _prefijo(modulo, p) and (mejor is None or len(p) > mejor[2]):
                mejor = (i, capa["nombre"], len(p))
    return (mejor[0], mejor[1]) if mejor else None


def _tarjan(grafo: dict[str, set[str]]) -> list[list[str]]:
    """Componentes fuertemente conexas (iterativo)."""
    indice, bajo, pila, en_pila, salida = {}, {}, [], set(), []
    contador = 0
    for inicio in sorted(grafo):
        if inicio in indice:
            continue
        trabajo = [(inicio, iter(sorted(grafo.get(inicio, ()))))]
        indice[inicio] = bajo[inicio] = contador
        contador += 1
        pila.append(inicio)
        en_pila.add(inicio)
        while trabajo:
            nodo, hijos = trabajo[-1]
            avanzo = False
            for hijo in hijos:
                if hijo not in indice:
                    indice[hijo] = bajo[hijo] = contador
                    contador += 1
                    pila.append(hijo)
                    en_pila.add(hijo)
                    trabajo.append((hijo, iter(sorted(grafo.get(hijo, ())))))
                    avanzo = True
                    break
                if hijo in en_pila:
                    bajo[nodo] = min(bajo[nodo], indice[hijo])
            if avanzo:
                continue
            trabajo.pop()
            if trabajo:
                padre = trabajo[-1][0]
                bajo[padre] = min(bajo[padre], bajo[nodo])
            if bajo[nodo] == indice[nodo]:
                comp = []
                while True:
                    x = pila.pop()
                    en_pila.discard(x)
                    comp.append(x)
                    if x == nodo:
                        break
                if len(comp) > 1:
                    salida.append(sorted(comp))
    return salida


def _rotas(repo: Repo) -> list[Hallazgo]:
    salida = []
    for mod in repo.modulos.values():
        if repo.en_pruebas(mod.ruta):
            continue  # en pruebas lo cubre la categoría Pruebas
        for imp in mod.importaciones:
            if imp.protegida or not repo.es_propio(imp.modulo):
                continue
            for faltante in faltantes(repo, imp):
                salida.append(_h(
                    "importacion_rota", "alta", mod.ruta, imp.linea,
                    f"Importa `{faltante}`, que no existe en el repo.",
                    "Corregir la ruta del import (¿se movió o renombró?) o borrar el código que lo usa.",
                    faltante,
                ))
    return salida


def faltantes(repo: Repo, imp) -> list[str]:
    if not repo.existe(imp.modulo):
        return [imp.modulo]
    return [f"{imp.modulo}.{n}" for n in imp.nombres if n != "*" and not repo.tiene_nombre(imp.modulo, n)]


def revisar(repo: Repo) -> list[Hallazgo]:
    cfg = repo.config["capas"]
    orden = cfg["orden"]
    salida: list[Hallazgo] = []
    grafo: dict[str, set[str]] = {}
    lineas: dict[tuple[str, str], int] = {}

    for mod in repo.modulos.values():
        capa_origen = capa_de(mod.nombre, orden)
        vistos = set()
        for imp in mod.importaciones:
            # Prohibidas
            for regla in cfg["prohibidas"]:
                if not _prefijo(mod.nombre, regla["desde"]) or not repo.es_propio(imp.modulo):
                    continue
                hacia = next((h for h in regla["hacia"] if _prefijo(imp.modulo, h)), None)
                if hacia and not _prefijo(mod.nombre, hacia):
                    salida.append(_h(
                        "importacion_prohibida", "alta", mod.ruta, imp.linea,
                        f"`{regla['desde']}` no puede importar `{hacia}` (importa `{imp.modulo}`).",
                        f"Mover lo necesario a una capa que `{regla['desde']}` pueda usar o invertir la dependencia "
                        "(ver docs/ARQUITECTURA.md).",
                        f"{imp.modulo}",
                    ))
            # Capas
            for destino in repo.destinos(imp) or ([imp.modulo] if repo.existe(imp.modulo) else []):
                capa_destino = capa_de(destino, orden)
                if capa_origen and capa_destino and capa_destino[0] > capa_origen[0] and (destino, "capa") not in vistos:
                    vistos.add((destino, "capa"))
                    salida.append(_h(
                        "capa_invertida", "alta", mod.ruta, imp.linea,
                        f"`{mod.nombre}` (capa {capa_origen[1]}) importa `{destino}` (capa superior {capa_destino[1]}).",
                        "Las capas bajas no conocen a las altas: mover el código compartido a la capa baja o pasar "
                        "la dependencia como parámetro/callback.",
                        destino,
                    ))
                if imp.de_modulo and not imp.tipo_checking and destino != mod.nombre:
                    grafo.setdefault(mod.nombre, set()).add(destino)
                    lineas.setdefault((mod.nombre, destino), imp.linea)

    for comp in _tarjan(grafo):
        miembros = set(comp)
        primero = comp[0]
        siguiente = sorted(grafo.get(primero, set()) & miembros)
        mod = repo.modulos[primero]
        linea = lineas.get((primero, siguiente[0]), 0) if siguiente else 0
        muestra = " → ".join(comp[:6]) + (" …" if len(comp) > 6 else "")
        salida.append(_h(
            "ciclo", "media", mod.ruta, linea,
            f"Ciclo de importaciones entre {len(comp)} módulos: {muestra}.",
            "Romper el ciclo moviendo lo compartido a un módulo de capa más baja o importando de forma perezosa.",
            ",".join(comp),
        ))
    return salida + _rotas(repo)
