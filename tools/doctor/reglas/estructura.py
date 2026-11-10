"""Estructura: raíz permitida, temporales versionados, carpetas sin dueño."""
from __future__ import annotations

import fnmatch

from tools.doctor.modelo import Hallazgo
from tools.doctor.repo import Repo, bajo


def _h(regla, severidad, archivo, mensaje, sugerencia, linea=0, clave=""):
    return Hallazgo("estructura", regla, severidad, archivo, linea, mensaje, sugerencia, clave)


def _coincide(nombre: str, patrones: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(nombre, p) for p in patrones)


def _carpetas_de_capas(config: dict) -> list[str]:
    paquete = config["general"]["paquete"]
    salida = []
    for capa in config["capas"]["orden"]:
        for m in capa["modulos"]:
            partes = m.split(".")
            if partes[0] == paquete and len(partes) >= 2:
                salida.append(partes[1])
    return salida


def revisar(repo: Repo) -> list[Hallazgo]:
    cfg = repo.config["estructura"]
    paquete = repo.config["general"]["paquete"]
    salida: list[Hallazgo] = []

    # Raíz
    raiz_vista: dict[str, str] = {}
    for p in repo.archivos:
        raiz_vista.setdefault(p.split("/")[0], p)
    for entrada in sorted(raiz_vista):
        if not _coincide(entrada, cfg["raiz_permitida"]):
            tipo = "carpeta" if "/" in raiz_vista[entrada] else "archivo"
            salida.append(_h(
                "raiz_no_permitida", "alta", entrada,
                f"{tipo.capitalize()} `{entrada}` en la raíz fuera de la lista blanca.",
                "Moverlo a su carpeta (src/, tools/, docs/, tests/…) según docs/ARQUITECTURA.md, "
                "ignorarlo en .gitignore si es local, o añadirlo a `estructura.raiz_permitida` en tools/doctor/reglas.toml si es legítimo.",
                clave=entrada,
            ))

    # Temporales, logs, comprimidos, binarios pesados
    max_bytes = cfg["max_archivo_kb"] * 1024
    for p in repo.archivos:
        nombre = p.rsplit("/", 1)[-1]
        if _coincide(nombre, cfg["patrones_temporales"]):
            salida.append(_h(
                "archivo_temporal", "alta", p,
                f"Archivo temporal/log/comprimido `{nombre}` dentro del repo.",
                "Borrarlo del repo (git rm --cached) y añadir el patrón a .gitignore.",
                clave=p,
            ))
        elif repo.tamano(p) > max_bytes and not any(fnmatch.fnmatchcase(p, g) for g in cfg["binario_permitido"]):
            salida.append(_h(
                "archivo_pesado", "media", p,
                f"Archivo de {repo.tamano(p) // 1024} KB (umbral {cfg['max_archivo_kb']} KB).",
                "Sacarlo del repo (generarlo, descargarlo o guardarlo en data/) o permitirlo en `estructura.binario_permitido`.",
                clave=p,
            ))

    # Carpetas sin dueño
    subcarpetas = dict(cfg["subcarpetas"])
    capas_src = _carpetas_de_capas(repo.config)
    if capas_src:
        subcarpetas[paquete] = capas_src
    vistas: set[str] = set()
    for padre, permitidas in subcarpetas.items():
        for p in repo.archivos:
            if not bajo(p, [padre]):
                continue
            resto = p[len(padre) + 1:].split("/")
            if len(resto) < 2:
                continue
            carpeta = f"{padre}/{resto[0]}"
            if resto[0] not in permitidas and carpeta not in vistas:
                vistas.add(carpeta)
                donde = "las capas de `[capas]`" if padre == paquete else f"`estructura.subcarpetas.{padre}`"
                salida.append(_h(
                    "carpeta_sin_dueno", "media", carpeta,
                    f"Carpeta `{carpeta}` no declarada en {donde}.",
                    "Ubicar el código en una carpeta existente según docs/ARQUITECTURA.md o declararla en tools/doctor/reglas.toml.",
                    clave=carpeta,
                ))

    # Archivos sueltos directamente en src/
    for p in repo.archivos:
        partes = p.split("/")
        if len(partes) == 2 and partes[0] == paquete and partes[1] not in ("__init__.py", "README.md"):
            salida.append(_h(
                "modulo_suelto_src", "media", p,
                f"`{p}` está suelto en `{paquete}/` sin paquete.",
                "Moverlo al paquete de su capa (p. ej. src/<paquete>/).",
                clave=p,
            ))
    return salida
