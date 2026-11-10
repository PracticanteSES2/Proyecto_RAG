"""Tamaño y complejidad: archivos y funciones grandes, complejidad ciclomática."""
from __future__ import annotations

from tools.doctor.modelo import Hallazgo
from tools.doctor.repo import Repo, bajo


def _h(regla, severidad, archivo, linea, mensaje, sugerencia, clave):
    return Hallazgo("tamano", regla, severidad, archivo, linea, mensaje, sugerencia, clave)


def revisar(repo: Repo) -> list[Hallazgo]:
    cfg = repo.config["tamano"]
    salida: list[Hallazgo] = []
    for mod in repo.modulos.values():
        if not bajo(mod.ruta, cfg["aplica_a"]) or mod.arbol is None:
            continue
        lineas = mod.texto.count("\n") + (0 if mod.texto.endswith("\n") or not mod.texto else 1)
        if lineas > cfg["archivo_media"]:
            sev = "alta" if lineas > cfg["archivo_alta"] else "media"
            salida.append(_h(
                "archivo_grande", sev, mod.ruta, 1,
                f"{lineas} líneas (umbral {cfg['archivo_media']}; alto {cfg['archivo_alta']}).",
                "Partirlo por responsabilidades en módulos del mismo paquete; mover utilidades a su capa.",
                "archivo",
            ))
        for f in mod.funciones:
            largo = f.fin - f.linea + 1
            if largo > cfg["funcion_media"]:
                sev = "alta" if largo > cfg["funcion_alta"] else "media"
                salida.append(_h(
                    "funcion_larga", sev, mod.ruta, f.linea,
                    f"`{f.qual}` tiene {largo} líneas (umbral {cfg['funcion_media']}).",
                    "Extraer pasos en funciones con nombre propio; separar validación, cálculo y formato.",
                    f.qual,
                ))
            cc = f.complejidad
            if cc > cfg["complejidad_media"]:
                sev = "alta" if cc > cfg["complejidad_alta"] else "media"
                salida.append(_h(
                    "complejidad", sev, mod.ruta, f.linea,
                    f"Complejidad ciclomática {cc} en `{f.qual}` (umbral {cfg['complejidad_media']}).",
                    "Reducir ramas: tablas de despacho, retornos tempranos, extraer condiciones a funciones.",
                    f.qual,
                ))
            args = f.nodo.args
            n = len(args.posonlyargs) + len(args.args) + len(args.kwonlyargs)
            if f.clase and args.args and args.args[0].arg in ("self", "cls"):
                n -= 1
            if n > cfg["parametros_max"]:
                salida.append(_h(
                    "demasiados_parametros", "baja", mod.ruta, f.linea,
                    f"`{f.qual}` recibe {n} parámetros (máximo {cfg['parametros_max']}).",
                    "Agrupar parámetros relacionados en un dataclass o un objeto de opciones.",
                    f.qual,
                ))
    return salida
