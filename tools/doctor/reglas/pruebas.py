"""Pruebas: módulos sin pruebas, pruebas huérfanas y parches que apuntan a nada."""
from __future__ import annotations

import ast

from tools.doctor.modelo import Hallazgo
from tools.doctor.reglas.capas import faltantes
from tools.doctor.repo import Repo, bajo


def _h(regla, severidad, archivo, linea, mensaje, sugerencia, clave):
    return Hallazgo("pruebas", regla, severidad, archivo, linea, mensaje, sugerencia, clave)


def _alcanzables(repo: Repo, inicios: list[str]) -> set[str]:
    vistos = set(inicios)
    pendientes = list(inicios)
    while pendientes:
        mod = repo.modulos[pendientes.pop()]
        for imp in mod.importaciones:
            objetivos = set(repo.destinos(imp))
            partes = imp.modulo.split(".")
            objetivos.update(".".join(partes[:i]) for i in range(1, len(partes) + 1))
            for d in objetivos:
                if d in repo.modulos and d not in vistos:
                    vistos.add(d)
                    pendientes.append(d)
    return vistos


def _resolver_patch(repo: Repo, objetivo: str) -> str | None:
    """None si el destino de `mock.patch("a.b.c")` existe; si no, la parte que falta."""
    partes = objetivo.split(".")
    for i in range(len(partes), 0, -1):
        prefijo = ".".join(partes[:i])
        if prefijo in repo.modulos or prefijo in repo.paquetes:
            resto = partes[i:]
            if not resto:
                return None
            if prefijo in repo.modulos and repo.tiene_nombre(prefijo, resto[0]):
                return None
            return ".".join(partes[: i + 1])
    return partes[0]


def _es_patch(nombre: str) -> bool:
    return nombre in ("patch", "mock.patch", "unittest.mock.patch") or nombre.endswith(".patch")


def _tiene_pruebas(mod) -> bool:
    for n in ast.walk(mod.arbol):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test"):
            return True
        if isinstance(n, ast.ClassDef) and any((getattr(b, "attr", None) or getattr(b, "id", "")).endswith("TestCase") for b in n.bases):
            return True
    return False


def revisar(repo: Repo) -> list[Hallazgo]:
    cfg = repo.config["pruebas"]
    salida: list[Hallazgo] = []
    de_pruebas = [n for n, m in repo.modulos.items() if repo.en_pruebas(m.ruta)]
    alcanzables = _alcanzables(repo, de_pruebas)

    for nombre, mod in sorted(repo.modulos.items()):
        if bajo(mod.ruta, cfg["aplica_a"]) and not mod.es_paquete and nombre not in alcanzables:
            salida.append(_h(
                "modulo_sin_pruebas", "media", mod.ruta, 1,
                f"Ninguna prueba importa `{nombre}` (ni directa ni indirectamente).",
                f"Añadir una prueba en tests/ que lo ejercite (TDD) o borrarlo si está muerto.",
                "modulo",
            ))

    for nombre in de_pruebas:
        mod = repo.modulos[nombre]
        if mod.arbol is None:
            continue
        for imp in mod.importaciones:
            if imp.protegida or not repo.es_propio(imp.modulo):
                continue
            for faltante in faltantes(repo, imp):
                salida.append(_h(
                    "prueba_huerfana", "alta", mod.ruta, imp.linea,
                    f"La prueba importa `{faltante}`, que ya no existe.",
                    "Actualizar la prueba al nombre/ubicación nueva o borrarla si el código se eliminó.",
                    faltante,
                ))
        for llamada in mod.llamadas:
            if not _es_patch(llamada.nombre) or not llamada.nodo.args:
                continue
            arg = llamada.nodo.args[0]
            if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
                continue
            if not repo.es_propio(arg.value) or "." not in arg.value:
                continue
            falta = _resolver_patch(repo, arg.value)
            if falta:
                salida.append(_h(
                    "patch_roto", "alta", mod.ruta, llamada.linea,
                    f"`patch(\"{arg.value}\")` apunta a `{falta}`, que no existe.",
                    "Actualizar la ruta del parche: el mock no está reemplazando nada.",
                    arg.value,
                ))
        if repo.es_prueba_por_nombre(mod.ruta) and not _tiene_pruebas(mod):
            salida.append(_h(
                "archivo_prueba_vacio", "baja", mod.ruta, 1,
                "Archivo `test_*.py` sin funciones `test*` ni `TestCase`.",
                "Renombrarlo (si es un ayudante) o completarlo con pruebas.",
                "archivo",
            ))
    return salida
