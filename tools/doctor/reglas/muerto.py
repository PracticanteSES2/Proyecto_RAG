"""Código muerto: módulos sin importadores, símbolos e importaciones sin uso."""
from __future__ import annotations

from tools.doctor.modelo import Hallazgo
from tools.doctor.repo import Repo, bajo, decorador_inocuo


def _h(regla, severidad, archivo, linea, mensaje, sugerencia, clave):
    return Hallazgo("muerto", regla, severidad, archivo, linea, mensaje, sugerencia, clave)


def _mencionado(repo: Repo, nombre: str, ruta: str) -> bool:
    texto = repo.menciones_texto
    return nombre in texto or ruta in texto or ruta.replace("/", "\\") in texto


def _modulos(repo: Repo, aplica: list[str]) -> list[Hallazgo]:
    salida = []
    for nombre, mod in sorted(repo.modulos.items()):
        if not bajo(mod.ruta, aplica) or mod.es_paquete or mod.ruta.endswith("__main__.py"):
            continue
        importadores = repo.importadores.get(nombre, set())
        if not importadores:
            if _mencionado(repo, nombre, mod.ruta):
                continue
            salida.append(_h(
                "modulo_sin_uso", "media", mod.ruta, 1,
                f"Nadie importa `{nombre}` (ni app, páginas, tools ni pruebas).",
                "Si es código muerto, borrarlo; si es un punto de entrada, moverlo a tools/ o documentarlo.",
                "modulo",
            ))
        elif all(repo.en_pruebas(repo.modulos[i].ruta) for i in importadores):
            salida.append(_h(
                "modulo_solo_pruebas", "baja", mod.ruta, 1,
                f"`{nombre}` solo lo importan pruebas; el producto no lo usa.",
                "Conectarlo al flujo real o borrarlo junto con sus pruebas.",
                "modulo",
            ))
    return salida


def _simbolos(repo: Repo, cfg: dict, aplica: list[str]) -> list[Hallazgo]:
    usados = repo.usados_global
    ignorar = set(cfg["ignorar_nombres"])
    prefijos = tuple(cfg["ignorar_prefijos_metodo"])
    salida = []
    for mod in repo.modulos.values():
        if not bajo(mod.ruta, aplica) or mod.arbol is None:
            continue
        for d in [*mod.clases, *mod.funciones]:
            if not d.de_modulo or d.nombre in ignorar or d.nombre in mod.todos:
                continue
            if d.nombre.startswith("__") and d.nombre.endswith("__"):
                continue
            if d.clase and (d.clase_con_bases or d.nombre.startswith(prefijos)):
                continue  # puede sobrescribir un método de la base
            if any(not decorador_inocuo(x) for x in d.decoradores):
                continue  # decoradores de registro (rutas, callbacks…)
            if usados.get(d.nombre, 0) == 0:
                tipo = "clase" if d in mod.clases else ("método" if d.clase else "función")
                salida.append(_h(
                    "simbolo_sin_uso", "baja", mod.ruta, d.linea,
                    f"`{d.qual}` ({tipo}) no se usa en ningún archivo del repo.",
                    "Borrarlo si está muerto; si se usa dinámicamente, añadirlo a `__all__` o a `muerto.ignorar_nombres`.",
                    d.qual,
                ))
    return salida


def _imports(repo: Repo, aplica: list[str]) -> list[Hallazgo]:
    salida = []
    for mod in repo.modulos.values():
        if not bajo(mod.ruta, aplica) or mod.es_paquete or mod.arbol is None:
            continue
        lineas = mod.texto.splitlines()
        for imp in mod.importaciones:
            if not imp.de_modulo or imp.tipo_checking:
                continue
            if "noqa" in (lineas[imp.linea - 1] if imp.linea <= len(lineas) else ""):
                continue  # reexportación declarada
            for ligado, original in imp.ligados:
                if original == "__reexporta__" or ligado in mod.todos or ligado == "_":
                    continue
                if (mod.nombre, ligado) in repo.importados_de:
                    continue  # otro módulo lo importa desde aquí (reexportación)
                if mod.usados.get(ligado, 0) == 0 and ligado not in mod.cadenas:
                    salida.append(_h(
                        "import_sin_uso", "baja", mod.ruta, imp.linea,
                        f"`{ligado}` se importa y no se usa.",
                        "Quitar la importación (o reexportarla explícitamente con `__all__`).",
                        ligado,
                    ))
    return salida


def revisar(repo: Repo) -> list[Hallazgo]:
    cfg = repo.config["muerto"]
    aplica = cfg["aplica_a"]
    return _modulos(repo, aplica) + _simbolos(repo, cfg, aplica) + _imports(repo, aplica)
