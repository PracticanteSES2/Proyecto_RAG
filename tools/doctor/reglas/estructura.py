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
    return salida + _no_ignoradas(repo, cfg) + _salidas_fuera_de_var(repo)


_NOMBRES_SALIDA = ("out", "salidas", "salida", "output", "outputs", "logs", "tmp", "resultados", "informes")


def _no_ignoradas(repo: Repo, cfg: dict) -> list[Hallazgo]:
    """Carpetas que deben estar ignoradas por git y no lo están (solo con git)."""
    nombres = set(cfg.get("carpetas_ignoradas", []))
    if not repo.es_git or not nombres:
        return []
    # Las que también figuran en la raíz permitida (var, data, .venv…) solo cuentan en la raíz;
    # las demás (__pycache__, node_modules, .next) en cualquier nivel.
    solo_raiz = {n for n in nombres if _coincide(n, cfg["raiz_permitida"])}
    vistas: dict[str, str] = {}
    for p in repo.listado:
        partes = p.split("/")
        for i, parte in enumerate(partes[:-1] if len(partes) > 1 else partes):
            if parte in nombres and (i == 0 or parte not in solo_raiz):
                vistas.setdefault("/".join(partes[: i + 1]), p)
                break
    return [
        _h(
            "no_ignorada", "alta", carpeta,
            f"`{carpeta}` debería estar ignorada por git y no lo está (p. ej. `{ejemplo}`).",
            "Añadirla a .gitignore y, si ya está versionada, `git rm -r --cached` (docs/ARQUITECTURA.md §6).",
            clave=carpeta,
        )
        for carpeta, ejemplo in sorted(vistas.items())
    ]


def _salidas_fuera_de_var(repo: Repo) -> list[Hallazgo]:
    """Salidas/logs/temporales ignorados junto al código en vez de en var/ (lo dice el .gitignore)."""
    salida = []
    for gi in (p for p in repo.listado if p.rsplit("/", 1)[-1] == ".gitignore"):
        base = gi.rpartition("/")[0]
        texto = repo.texto_de(gi) or ""
        for n, linea in enumerate(texto.splitlines(), 1):
            patron = linea.strip()
            if not patron or patron.startswith(("#", "!")):
                continue
            ruta = "/".join(x for x in (base, patron.strip("/")) if x)
            partes = ruta.split("/")
            if len(partes) < 2 or partes[0] in ("var", "data", "tableros", "frontend") or "fixtures" in partes:
                continue
            if any(p.rstrip("*_").lower() in _NOMBRES_SALIDA for p in partes[-1:]):
                salida.append(Hallazgo(
                    "estructura", "salida_fuera_de_var", "media", gi, n,
                    f"Salidas en `{ruta}` (ignoradas junto al código) en vez de `var/`.",
                    "Escribirlas con `src.comun.rutas.ruta_salida(...)`/`ruta_log`/`ruta_tmp` (var/out, var/logs, var/tmp) "
                    "y quitar la entrada del .gitignore (docs/ARQUITECTURA.md §6).",
                    ruta,
                ))
    return salida
