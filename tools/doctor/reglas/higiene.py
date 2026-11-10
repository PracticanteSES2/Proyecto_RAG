"""Higiene: prints, excepts, TODO, secretos, rutas de usuario, BOM, mojibake."""
from __future__ import annotations

import bisect
import fnmatch
import os
import re
import subprocess
import time
from collections import Counter

from tools.doctor.modelo import Hallazgo
from tools.doctor.repo import Repo, bajo

# Patrones escritos con escapes para que este archivo no se marque a sí mismo.
_CP1252 = "\u20ac\u201a\u0192\u201e\u2026\u2020\u2021\u02c6\u2030\u0160\u2039\u0152\u017d\u2018\u2019\u201c\u201d\u2022\u2013\u2014\u02dc\u2122\u0161\u203a\u0153\u017e\u0178"
MOJIBAKE = re.compile("(?:\u00c3[\u0080-\u00bf" + _CP1252 + "]|\u00c2[\u00a0-\u00bf]|\u00e2\u20ac[\u0080-\u00bf" + _CP1252 + "]?)")

_SECRETO_ASIGNACION = re.compile(
    r"(?i)\b([a-z0-9_]*(?:password|passwd|pwd|contrasena|secret|secreto|api_?key|apikey|token|client_secret|access_key|private_key)[a-z0-9_]*)"
    r"[\"']?\s*[:=]\s*[rbuf]?[\"']([^\"'\s]{12,})[\"']"
)
_SECRETO_FORMATOS = {
    "clave AWS": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "clave privada": re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
    "token de GitHub": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "token de Slack": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    "JWT": re.compile(r"\beyJ[A-Za-z0-9_-]{15,}\.eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}"),
    "clave de API (sk-)": re.compile(r"\bsk-[A-Za-z0-9]{32,}\b"),
    "clave de Google": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
}
_RUTA_USUARIO = re.compile(
    r"(?i)(?<![A-Za-z])[a-z]:[\\/]+users[\\/]+(?!public\b|default\b|all users\b)[^\\/\s\"'<>|*?%$]+"
    r"|/home/[a-z_][a-z0-9_.-]*|/Users/[A-Za-z][A-Za-z0-9_.-]*"
)
# Literales que deben aparecer para que valga la pena correr cada patrón (rendimiento).
_PREFILTRO_FORMATOS = {
    "clave AWS": ("AKIA",), "clave privada": ("PRIVATE KEY",), "token de GitHub": ("ghp_", "gho_", "ghu_", "ghs_", "ghr_"),
    "token de Slack": ("xox",), "JWT": ("eyJ",), "clave de API (sk-)": ("sk-",), "clave de Google": ("AIza",),
}
_PREFILTRO_ASIGNACION = ("password", "passwd", "pwd", "contrasena", "secret", "api_key", "apikey",
                         "token", "access_key", "private_key", "api-key")
_DEPURADORES = {"breakpoint", "pdb.set_trace", "ipdb.set_trace", "pudb.set_trace"}
_GENERICAS = {"Exception", "BaseException"}


def _h(regla, severidad, archivo, linea, mensaje, sugerencia, clave):
    return Hallazgo("higiene", regla, severidad, archivo, linea, mensaje, sugerencia, clave)


def _contexto_main(contexto: str) -> bool:
    return contexto == "main" or contexto.endswith(".main") or contexto.startswith("main.")


def _python(repo: Repo, cfg: dict) -> list[Hallazgo]:
    salida = []
    for mod in repo.modulos.values():
        if mod.error:
            salida.append(_h(
                "sintaxis_invalida", "alta", mod.ruta, 1, f"No se puede analizar: {mod.error}.",
                "Corregir la sintaxis o la codificación (UTF-8).", "archivo",
            ))
            continue
        if not (repo.en_codigo(mod.ruta) or repo.en_pruebas(mod.ruta)):
            continue
        ocurrencias: Counter = Counter()
        for c in mod.llamadas:
            if c.nombre == "print" and bajo(mod.ruta, cfg["print_en"]) and not c.en_main and not _contexto_main(c.contexto):
                ocurrencias[("print", c.contexto)] += 1
                salida.append(_h(
                    "print_depuracion", "media", mod.ruta, c.linea,
                    f"`print` en `{c.contexto}` (código de producto).",
                    "Usar `logging.getLogger(__name__)` con el nivel adecuado o devolver el dato a quien llama.",
                    f"{c.contexto}#{ocurrencias[('print', c.contexto)]}",
                ))
            elif c.nombre in _DEPURADORES:
                ocurrencias[("dbg", c.contexto)] += 1
                salida.append(_h(
                    "punto_de_ruptura", "alta", mod.ruta, c.linea,
                    f"`{c.nombre}()` olvidado en `{c.contexto}`.",
                    "Borrarlo antes de integrar.",
                    f"{c.contexto}#{ocurrencias[('dbg', c.contexto)]}",
                ))
            elif c.nombre in ("sys.path.insert", "sys.path.append") and bajo(mod.ruta, cfg["sys_path_en"]):
                ocurrencias[("path", c.contexto)] += 1
                salida.append(_h(
                    "sys_path", "media", mod.ruta, c.linea,
                    "Manipula `sys.path` dentro del paquete.",
                    "Importar con rutas absolutas desde la raíz (python -m …) en vez de tocar sys.path.",
                    f"{c.contexto}#{ocurrencias[('path', c.contexto)]}",
                ))
        for e in mod.excepts:
            if e.tipos is None:
                ocurrencias[("exc", e.contexto)] += 1
                salida.append(_h(
                    "except_desnudo", "alta", mod.ruta, e.linea,
                    f"`except:` desnudo en `{e.contexto}` (atrapa hasta KeyboardInterrupt/SystemExit).",
                    "Capturar la excepción concreta (o `Exception`) y registrar el error con logging.",
                    f"{e.contexto}#{ocurrencias[('exc', e.contexto)]}",
                ))
            elif e.silencioso and set(e.tipos) & _GENERICAS:
                ocurrencias[("sil", e.contexto)] += 1
                salida.append(_h(
                    "except_silencioso", "media", mod.ruta, e.linea,
                    f"`except {', '.join(e.tipos)}: pass` en `{e.contexto}` traga errores sin dejar rastro.",
                    "Capturar la excepción concreta o al menos `logger.debug(..., exc_info=True)`.",
                    f"{e.contexto}#{ocurrencias[('sil', e.contexto)]}",
                ))
    return salida


def _edades_todo(repo: Repo, ruta: str, lineas: list[int]) -> dict[int, int]:
    """Días desde que se escribió cada línea (git blame); {} si no hay git."""
    if not repo.es_git or not lineas:
        return {}
    args = ["git", "-C", str(repo.raiz), "blame", "--porcelain"]
    for n in lineas[:50]:
        args += ["-L", f"{n},{n}"]
    try:
        r = subprocess.run([*args, "--", ruta], capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return {}
    if r.returncode != 0:
        return {}
    edades, actual = {}, None
    for linea in r.stdout.decode("utf-8", "replace").splitlines():
        partes = linea.split()
        if len(partes) >= 3 and len(partes[0]) == 40 and partes[1].isdigit():
            actual = int(partes[2])
        elif linea.startswith("author-time ") and actual is not None:
            edades[actual] = int((time.time() - int(partes[1])) // 86400)
    return edades


def _todos(repo: Repo, cfg: dict) -> list[Hallazgo]:
    marcas = "|".join(re.escape(m) for m in cfg["todo_marcas"])
    patron = re.compile(r"#\s*(" + marcas + r")\b\s*[:(\-]?")
    salida = []
    for mod in repo.modulos.values():
        if not (repo.en_codigo(mod.ruta) or repo.en_pruebas(mod.ruta)) or not mod.texto:
            continue
        encontrados = []
        for i, linea in enumerate(mod.texto.splitlines(), 1):
            m = patron.search(linea)
            if m and (m.group(0).rstrip().endswith((":", "(", "-")) or linea[m.end():].strip() == ""):
                encontrados.append((i, m.group(1), linea[m.end():].strip()))
        if not encontrados:
            continue
        edades = _edades_todo(repo, mod.ruta, [i for i, _, _ in encontrados])
        vistos: Counter = Counter()
        for i, marca, texto in encontrados:
            dias = edades.get(i)
            viejo = dias is not None and dias > cfg["todo_dias_viejo"]
            edad = f" (hace {dias} días{', viejo' if viejo else ''})" if dias is not None else ""
            vistos[texto] += 1
            salida.append(_h(
                "todo", "baja", mod.ruta, i,
                f"{marca}{edad}: {texto[:80]}",
                "Resolverlo, convertirlo en tarea (specs/…/tasks.md) o borrarlo si ya no aplica.",
                f"{marca}:{texto[:60]}#{vistos[texto]}",
            ))
    return salida


def _es_placeholder(valor: str, cfg: dict) -> bool:
    bajo_valor = valor.lower()
    if any(p in bajo_valor for p in cfg["secreto_placeholders"]) or "://" in valor:
        return True
    if not (re.search(r"[A-Za-z]", valor) and re.search(r"\d", valor)):
        return True  # identificadores o nombres de variables de entorno
    return bool(re.fullmatch(r"[A-Z0-9_]+", valor))


def _textos(repo: Repo, cfg: dict) -> list[Hallazgo]:
    salida = []
    for ruta in repo.textos(cfg["extensiones_texto"]):
        datos = repo.bytes_de(ruta)
        if datos.startswith(b"\xef\xbb\xbf") and not any(fnmatch.fnmatchcase(ruta.rsplit("/", 1)[-1], p) for p in cfg["bom_permitido"]):
            salida.append(_h(
                "bom", "baja", ruta, 1, "El archivo empieza con BOM UTF-8.",
                "Guardarlo como UTF-8 sin BOM.", "archivo",
            ))
        texto = repo.texto_de(ruta)
        if texto is None:
            salida.append(_h(
                "no_utf8", "media", ruta, 1, "El archivo no es UTF-8 válido (¿cp1252?).",
                "Reabrirlo con su codificación real y guardarlo como UTF-8.", "archivo",
            ))
            continue
        # Se busca sobre el texto entero (rápido) y solo se calcula la línea de lo encontrado.
        saltos = None

        def linea_de(pos: int) -> int:
            nonlocal saltos
            if saltos is None:
                saltos = [i for i, c in enumerate(texto) if c == "\n"]
            return bisect.bisect_right(saltos, pos - 1) + 1

        lineas_moji = sorted({linea_de(m.start()) for m in MOJIBAKE.finditer(texto)})
        secretos: Counter = Counter()
        es_codigo = os.path.splitext(ruta)[1].lower() in cfg["extensiones_codigo"]
        minus = texto.lower()
        asignaciones = _SECRETO_ASIGNACION.finditer(texto) if any(k in minus for k in _PREFILTRO_ASIGNACION) else ()
        for m in asignaciones:
            if not _es_placeholder(m.group(2), cfg):
                secretos[m.group(1)] += 1
                salida.append(_h(
                    "secreto", "alta", ruta, linea_de(m.start()),
                    f"Posible secreto codificado en `{m.group(1)}` (valor oculto).",
                    "Moverlo a variables de entorno/.env (fuera del repo) y rotarlo si llegó a publicarse.",
                    f"{m.group(1)}#{secretos[m.group(1)]}",
                ))
        for nombre, patron in _SECRETO_FORMATOS.items():
            if not any(k in texto for k in _PREFILTRO_FORMATOS[nombre]):
                continue
            for m in patron.finditer(texto):
                secretos[nombre] += 1
                salida.append(_h(
                    "secreto", "alta", ruta, linea_de(m.start()), f"Posible {nombre} en el texto (valor oculto).",
                    "Sacarlo del repo, rotarlo y leerlo de variables de entorno.",
                    f"{nombre}#{secretos[nombre]}",
                ))
        if es_codigo and ("users" in minus or "/home/" in texto):
            for m in _RUTA_USUARIO.finditer(texto):
                clave = m.group(0).lower().replace("\\", "/")
                secretos[clave] += 1
                salida.append(_h(
                    "ruta_usuario", "media", ruta, linea_de(m.start()),
                    f"Ruta absoluta de usuario codificada: `{m.group(0)}`.",
                    "Calcularla relativa a la raíz del proyecto o leerla de configuración/variables de entorno.",
                    f"{clave}#{secretos[clave]}",
                ))
        if lineas_moji:
            salida.append(_h(
                "mojibake", "media", ruta, lineas_moji[0],
                f"Texto con mojibake (p. ej. \u00ab\u00c3\u00b3\u00bb en vez de \u00ab\u00f3\u00bb) en {len(lineas_moji)} l\u00ednea(s).",
                "Recuperar el texto: `texto.encode('cp1252').decode('utf-8')` y guardar en UTF-8.",
                "archivo",
            ))
    return salida


def _nombres(repo: Repo, cfg: dict) -> list[Hallazgo]:
    patrones = cfg.get("nombres_prohibidos", [])
    return [
        _h(
            "nombre_prohibido", "media", p, 0,
            f"Nombre de archivo genérico o de versión: `{p.rsplit('/', 1)[-1]}`.",
            "Nombrarlo por su responsabilidad (`periodo.py`, no `utils.py`/`final.py`/`_v2.py`; docs/ARQUITECTURA.md §7); "
            "las versiones viejas se borran (están en git).",
            "nombre",
        )
        for p in repo.archivos
        if (repo.en_codigo(p) or repo.en_pruebas(p))
        and any(fnmatch.fnmatchcase(p.rsplit("/", 1)[-1], g) for g in patrones)
    ]


def revisar(repo: Repo) -> list[Hallazgo]:
    cfg = repo.config["higiene"]
    return _python(repo, cfg) + _todos(repo, cfg) + _textos(repo, cfg) + _nombres(repo, cfg)
