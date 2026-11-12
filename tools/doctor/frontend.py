"""Perfil frontend (Next.js App Router + TypeScript).

Reglas propias (sin Node): estructura de frontend/, `any`, `@ts-ignore`, fetch fuera de
lib/api, colores hex fuera de los tokens, componentes grandes, console.log, debugger,
TODO, eslint-disable, secretos/BOM/mojibake.

Herramientas del ecosistema (con Node y `npm ci` hecho): `tsc --noEmit` (compilación),
ESLint (lint) y react-doctor (react). Si falta Node o la herramienta, su categoría se
omite con aviso y no entra en el puntaje ni en el trinquete.
"""
from __future__ import annotations

import copy
import fnmatch
import json
import os
import posixpath
import re
import shutil
import subprocess
import time
from collections import Counter
from pathlib import Path

from tools.doctor import puntaje
from tools.doctor.modelo import Hallazgo, InformePerfil
from tools.doctor.reglas import higiene
from tools.doctor.repo import Repo, bajo

EXTERNAS = ("compilacion", "lint", "react")

_ANY = re.compile(r":\s*any\b(?!\w)|\bas\s+any\b|<any>|\bany\[\]|Array<any>|Record<[^>]*,\s*any>")
_TS_IGNORE = re.compile(r"@ts-(ignore|nocheck)\b")
_TS_EXPECT = re.compile(r"@ts-expect-error\b")
_FETCH = re.compile(r"(?<![\w.$])fetch\s*\(|\baxios(?:\.\w+)?\s*\(|\bnew\s+XMLHttpRequest\b")
_HEX = re.compile(r"(?<![&\w#])#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})(?![0-9a-zA-Z_-])")
_CONSOLE = re.compile(r"\bconsole\.(log|debug|info|trace)\s*\(")
_DEBUGGER = re.compile(r"^\s*debugger\s*;?\s*$")
_TODO = re.compile(r"(?://|/\*)\s*(TODO|FIXME|XXX|HACK)\b")
_ESLINT_OFF = re.compile(r"eslint-disable")
_TSC = re.compile(r"^(?P<f>.+?)\((?P<l>\d+),(?P<c>\d+)\): error (?P<code>TS\d+): (?P<msg>.*)$")


def _h(categoria, regla, severidad, archivo, linea, mensaje, sugerencia, clave):
    return Hallazgo(categoria, regla, severidad, archivo, linea, mensaje, sugerencia, clave)


def _comentario(linea: str) -> bool:
    s = linea.strip()
    return s.startswith(("//", "*", "/*"))


# ---------------------------------------------------------------------------
# Reglas propias
# ---------------------------------------------------------------------------

def _estructura(repo: Repo, config: dict, carpeta: str) -> list[Hallazgo]:
    cfg = config["frontend"]
    salida, vistos = [], set()
    for p in repo.archivos:
        entrada = p[len(carpeta) + 1:].split("/")[0]
        if entrada not in vistos and not any(fnmatch.fnmatchcase(entrada, g) for g in cfg["raiz_permitida"]):
            vistos.add(entrada)
            salida.append(_h(
                "estructura", "fuera_de_lugar", "media", f"{carpeta}/{entrada}", 0,
                f"`{carpeta}/{entrada}` no es una ubicación esperada de un proyecto Next.js.",
                "Moverlo a app/, components/, lib/, hooks/, styles/ o public/ según docs/ARQUITECTURA.md, "
                "o declararlo en `frontend.raiz_permitida`.",
                entrada,
            ))
        nombre = p.rsplit("/", 1)[-1]
        if any(fnmatch.fnmatchcase(nombre, g) for g in config["estructura"]["patrones_temporales"]):
            salida.append(_h(
                "estructura", "archivo_temporal", "alta", p, 0, f"Archivo temporal/log `{nombre}` en frontend/.",
                "Borrarlo y añadir el patrón a .gitignore.", p,
            ))
    return salida


# (categoría, regla, severidad, patrón, solo TS, solo JS, ignora comentarios, mensaje, sugerencia)
_REGLAS_LINEA = [
    ("tipos", "any", "media", _ANY, True, False, True, "Uso de `any`: se pierde el tipado.",
     "Tiparlo (interfaces en types/ o generadas del OpenAPI del backend) o usar `unknown` y estrechar."),
    ("tipos", "ts_ignore", "media", _TS_IGNORE, True, False, False, "`@ts-ignore`/`@ts-nocheck` silencia el compilador.",
     "Corregir el tipo; si es inevitable usar `@ts-expect-error` con el motivo."),
    ("tipos", "ts_expect_error", "baja", _TS_EXPECT, True, False, False, "`@ts-expect-error` pendiente.",
     "Resolver el error de tipos y quitar la directiva."),
    ("higiene", "console_log", "media", _CONSOLE, False, True, True, "`console.log/debug` olvidado.",
     "Quitarlo o usar el logger del proyecto."),
    ("higiene", "debugger", "alta", _DEBUGGER, False, True, False, "`debugger` olvidado.", "Borrarlo."),
    ("higiene", "eslint_disable", "baja", _ESLINT_OFF, False, False, False, "Regla de ESLint desactivada en línea.",
     "Corregir el código en vez de silenciar la regla."),
]


def _archivo(p: str, texto: str, cfg: dict) -> list[Hallazgo]:
    ext = os.path.splitext(p)[1].lower()
    es_ts, es_js = ext in (".ts", ".tsx"), ext in (".ts", ".tsx", ".js", ".jsx", ".mjs")
    api = cfg.get("fetch_solo_en") or cfg["carpetas_api"]
    revisa_fetch = es_js and not bajo(p, api)
    revisa_hex = not any(fnmatch.fnmatchcase(p, g) for g in cfg["tokens"])
    reglas = [r for r in _REGLAS_LINEA if (es_ts or not r[4]) and (es_js or not r[5])]
    salida: list[Hallazgo] = []
    cuenta: Counter = Counter()

    def nuevo(cat, regla, sev, linea, mensaje, sugerencia):
        cuenta[regla] += 1
        salida.append(_h(cat, regla, sev, p, linea, mensaje, sugerencia, f"{regla}#{cuenta[regla]}"))

    lineas = texto.splitlines()
    if ext in (".tsx", ".jsx") and len(lineas) > cfg["componente_media"]:
        sev = "alta" if len(lineas) > cfg["componente_alta"] else "media"
        nuevo("arquitectura", "componente_grande", sev, 1, f"Componente de {len(lineas)} líneas (umbral {cfg['componente_media']}).",
              "Partirlo en subcomponentes en components/ y mover la lógica a hooks/ o lib/.")
    elif ext in (".ts", ".js", ".mjs") and len(lineas) > cfg["archivo_ts_media"]:
        sev = "alta" if len(lineas) > cfg["archivo_ts_alta"] else "media"
        nuevo("arquitectura", "archivo_grande", sev, 1, f"Archivo de {len(lineas)} líneas (umbral {cfg['archivo_ts_media']}).",
              "Partirlo por responsabilidades (un módulo = una responsabilidad).")
    for i, linea in enumerate(lineas, 1):
        comentario = _comentario(linea)
        for cat, regla, sev, patron, _, _, sin_comentarios, mensaje, sugerencia in reglas:
            if not (sin_comentarios and comentario) and patron.search(linea):
                nuevo(cat, regla, sev, i, mensaje, sugerencia)
        if revisa_fetch and not comentario and _FETCH.search(linea):
            nuevo("arquitectura", "fetch_fuera_de_api", "alta", i, "Llamada HTTP directa fuera de lib/api.",
                  f"Usar el cliente de {api[0]} (tipado, con manejo de errores y base URL).")
        if revisa_hex and not comentario:
            for m in _HEX.finditer(linea):
                nuevo("arquitectura", "hex_fuera_de_tokens", "media", i, f"Color `{m.group(0)}` escrito a mano fuera de los tokens.",
                      "Usar el token/variable CSS del sistema de diseño (styles/tokens).")
        m = _TODO.search(linea)
        if m:
            nuevo("higiene", "todo", "baja", i, f"{m.group(1)}: {linea[m.end():].strip()[:80]}",
                  "Resolverlo o convertirlo en tarea.")
    return salida


def reglas_propias(repo: Repo, config: dict) -> list[Hallazgo]:
    cfg = config["frontend"]
    carpeta = cfg["carpeta"].strip("/")
    salida = _estructura(repo, config, carpeta)
    generados = cfg.get("generado_no_editable", [])
    for p in repo.textos(cfg["extensiones"]):
        texto = repo.texto_de(p) or ""
        if bajo(p, generados):
            salida += _generado(p, texto)
            continue  # código generado: no se le aplican reglas de estilo
        salida += _archivo(p, texto, cfg) + _importaciones(p, texto, cfg, carpeta)
    return salida + higiene._textos(repo, config["higiene"])


_MARCA_GENERADO = re.compile(r"(?i)auto-?generated|generated by|do not edit|generado|no editar")
_IMPORT_TS = re.compile(r"""(?:\bfrom\s*|\bimport\s*\(?\s*|\brequire\s*\(\s*)["']([^"']+)["']""")


def _generado(p: str, texto: str) -> list[Hallazgo]:
    cabecera = " ".join(texto.splitlines()[:8])
    if _MARCA_GENERADO.search(cabecera):
        return []
    return [_h(
        "arquitectura", "generado_editado", "media", p, 1,
        "Archivo en la carpeta del cliente generado sin la marca de generación: parece editado a mano.",
        "Regenerar el cliente desde /openapi.json (no se edita a mano); el código propio va en lib/api/ fuera de generado/.",
        "generado",
    )]


def _destino_import(p: str, especificador: str, carpeta: str, raiz_alias: str) -> str | None:
    if especificador.startswith("@/"):
        return posixpath.normpath(f"{raiz_alias}/{especificador[2:]}")
    if especificador.startswith("."):
        return posixpath.normpath(posixpath.join(posixpath.dirname(p), especificador))
    return None  # paquete externo


def _importaciones(p: str, texto: str, cfg: dict, carpeta: str) -> list[Hallazgo]:
    reglas = [r for r in cfg.get("prohibidas", []) if bajo(p, [r["desde"]])]
    if not reglas:
        return []
    raiz_alias = cfg.get("alias_raiz") or carpeta
    salida, cuenta = [], Counter()
    for m in _IMPORT_TS.finditer(texto):
        destino = _destino_import(p, m.group(1), carpeta, raiz_alias)
        if not destino:
            continue
        for r in reglas:
            hacia = next((h for h in r["hacia"] if bajo(destino, [h]) and not bajo(p, [h])), None)
            if hacia:
                cuenta[hacia] += 1
                salida.append(_h(
                    "arquitectura", "importacion_prohibida", "alta", p, texto.count(chr(10), 0, m.start()) + 1,
                    f"`{r['desde']}` no puede importar de `{hacia}` (importa `{m.group(1)}`).",
                    "Respetar la dirección de dependencias del frontend (docs/ARQUITECTURA.md §3-4): "
                    "las primitivas no llaman a la API ni conocen rutas; lib/ no depende de componentes.",
                    f"{hacia}#{cuenta[hacia]}",
                ))
                break
    return salida


# ---------------------------------------------------------------------------
# Herramientas externas
# ---------------------------------------------------------------------------

def _rel(raiz: Path, base: Path, archivo: str) -> str:
    ruta = Path(archivo)
    if not ruta.is_absolute():
        ruta = base / ruta
    try:
        return ruta.resolve().relative_to(raiz.resolve()).as_posix()
    except ValueError:
        return archivo.replace("\\", "/")


def parsear_tsc(salida: str, raiz: Path, base: Path) -> list[Hallazgo]:
    hallazgos, cuenta = [], Counter()
    for linea in salida.splitlines():
        m = _TSC.match(linea.strip())
        if not m:
            continue
        archivo = _rel(raiz, base, m.group("f"))
        clave = f"{m.group('code')}:{m.group('msg')[:80]}"
        cuenta[(archivo, clave)] += 1
        hallazgos.append(_h(
            "compilacion", "tsc", "alta", archivo, int(m.group("l")), f"{m.group('code')}: {m.group('msg')}",
            "Corregir el error de tipos; el build de Next.js también fallará.", f"{clave}#{cuenta[(archivo, clave)]}",
        ))
    return hallazgos


def parsear_eslint(texto: str, raiz: Path, base: Path) -> list[Hallazgo]:
    hallazgos, cuenta = [], Counter()
    for archivo in json.loads(texto or "[]"):
        ruta = _rel(raiz, base, archivo.get("filePath", ""))
        for m in archivo.get("messages", []):
            regla = m.get("ruleId") or "eslint"
            cuenta[(ruta, regla)] += 1
            hallazgos.append(_h(
                "lint", regla, "media" if m.get("severity") == 2 else "baja", ruta, m.get("line") or 0,
                m.get("message", ""), f"Corregir según la regla `{regla}` de ESLint.",
                f"{regla}#{cuenta[(ruta, regla)]}",
            ))
    return hallazgos


_CLAVES_ARCHIVO = ("filePath", "file", "path", "filename", "fileName", "relativePath")
_CLAVES_REGLA = ("rule", "ruleId", "ruleName", "id", "name")


def _json_de(texto: str):
    texto = texto.strip()
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        inicio, fin = texto.find("{"), texto.rfind("}")
        if inicio < 0 or fin <= inicio:
            raise
        return json.loads(texto[inicio: fin + 1])


def _linea_de(d: dict) -> int:
    for k in ("line", "lineNumber", "startLine", "row"):
        if isinstance(d.get(k), int):
            return d[k]
    for k in ("location", "loc", "range", "start", "position"):
        v = d.get(k)
        if isinstance(v, dict):
            n = _linea_de(v)
            if n:
                return n
    return 0


def _contexto_react(nodo: dict, heredado: dict) -> dict:
    """Regla, severidad, mensaje y ayuda de un nodo del JSON, heredando lo que traigan sus padres."""
    ctx = dict(heredado)
    regla = next((nodo[k] for k in _CLAVES_REGLA if isinstance(nodo.get(k), str)), None)
    if regla:
        ctx["regla"] = f"{nodo['plugin']}/{regla}" if isinstance(nodo.get("plugin"), str) else regla
    for k in ("severity", "level"):
        if nodo.get(k) is not None:
            ctx["severidad"] = str(nodo[k]).lower()
    for k in ("message", "title", "description"):
        if isinstance(nodo.get(k), str):
            ctx["mensaje"] = nodo[k]
            break
    if isinstance(nodo.get("help"), str):
        ctx["ayuda"] = nodo["help"]
    return ctx


def parsear_react_doctor(texto: str, raiz: Path, base: Path) -> list[Hallazgo]:
    """Lector tolerante del `--json` de react-doctor (el esquema no está documentado):
    toma cada objeto con archivo y hereda regla/severidad/mensaje de sus padres."""
    datos = _json_de(texto)
    if isinstance(datos, dict) and datos.get("ok") is False:
        raise ValueError(str(datos.get("error") or datos.get("message") or "react-doctor devolvió ok: false"))
    hallazgos, cuenta, vistos = [], Counter(), set()

    def visitar(nodo, heredado: dict):
        if isinstance(nodo, list):
            for x in nodo:
                visitar(x, heredado)
            return
        if not isinstance(nodo, dict):
            return
        ctx = _contexto_react(nodo, heredado)
        archivo = next((nodo[k] for k in _CLAVES_ARCHIVO if isinstance(nodo.get(k), str)), None)
        if archivo and ctx.get("mensaje"):
            ruta = _rel(raiz, base, archivo)
            sev = "alta" if ctx.get("severidad") in ("error", "2", "high", "critical") else "media"
            regla_txt = ctx.get("regla", "react-doctor")
            clave = (ruta, regla_txt, _linea_de(nodo), nodo.get("column"), ctx["mensaje"])
            if clave in vistos:  # react-doctor repite la lista en projects[] y en la raíz
                return
            vistos.add(clave)
            cuenta[(ruta, regla_txt)] += 1
            hallazgos.append(_h(
                "react", regla_txt, sev, ruta, _linea_de(nodo), ctx["mensaje"],
                ctx.get("ayuda") or f"Ver `npx react-doctor rules explain {regla_txt}`.",
                f"{regla_txt}#{cuenta[(ruta, regla_txt)]}",
            ))
            return
        for v in nodo.values():
            if isinstance(v, (dict, list)):
                visitar(v, ctx)

    # La raíz ya trae la lista completa; recorrer también `projects` la duplicaría.
    raiz_diag = datos.get("diagnostics") if isinstance(datos, dict) else None
    visitar(raiz_diag if isinstance(raiz_diag, list) else datos, {})
    return hallazgos


def _bin(base: Path, nombre: str) -> str | None:
    carpeta = base / "node_modules" / ".bin"
    for ext in ((".cmd", ".exe", "") if os.name == "nt" else ("",)):
        p = carpeta / (nombre + ext)
        if p.exists():
            return str(p)
    return None


def _ejecutar(cmd: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess:
    entorno = dict(os.environ, CI="1", NO_COLOR="1", FORCE_COLOR="0")
    return subprocess.run(cmd, cwd=cwd, capture_output=True, timeout=timeout, env=entorno)


def correr_externas(raiz: Path, base: Path, config: dict) -> tuple[list[Hallazgo], dict[str, str]]:
    herr = config["frontend"]["herramientas"]
    omitidas: dict[str, str] = {}
    hallazgos: list[Hallazgo] = []
    if not shutil.which("node"):
        return [], {c: "Node.js no está instalado" for c in EXTERNAS}
    if not (base / "node_modules").is_dir():
        omitidas.update({"compilacion": "faltan dependencias (correr `npm ci` en frontend/)",
                         "lint": "faltan dependencias (correr `npm ci` en frontend/)"})

    def intentar(categoria, cmd, parser):
        try:
            r = _ejecutar(cmd, base, herr["timeout"])
            hallazgos.extend(parser(r.stdout.decode("utf-8", "replace"), raiz, base))
        except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError) as e:
            omitidas[categoria] = f"{cmd[0].rsplit(os.sep, 1)[-1]} falló: {e}"[:300]

    if "compilacion" not in omitidas:
        tsc = _bin(base, "tsc")
        if not (base / "tsconfig.json").exists():
            omitidas["compilacion"] = "no hay frontend/tsconfig.json"
        elif not tsc:
            omitidas["compilacion"] = "typescript no está instalado en frontend/node_modules"
        else:
            intentar("compilacion", [tsc, "--noEmit", "--pretty", "false"], parsear_tsc)

    if "lint" not in omitidas:
        eslint = _bin(base, "eslint")
        tiene_config = any(base.glob("eslint.config.*")) or any(base.glob(".eslintrc*"))
        if not tiene_config:
            omitidas["lint"] = "no hay configuración de ESLint en frontend/"
        elif not eslint:
            omitidas["lint"] = "eslint no está instalado en frontend/node_modules"
        else:
            intentar("lint", [eslint, ".", "--format", "json", "--no-error-on-unmatched-pattern"], parsear_eslint)

    local = _bin(base, "react-doctor")
    npx = shutil.which("npx")
    if local:
        cmd = [local]
    elif herr["permitir_npx"] and npx:
        cmd = [npx, "-y", herr["react_doctor"]]
    else:
        cmd = None
        omitidas["react"] = "react-doctor no disponible (instalarlo como devDependency o permitir npx)"
    if cmd:
        intentar("react", [*cmd, *herr["react_doctor_args"]], parsear_react_doctor)
    return hallazgos, omitidas


# ---------------------------------------------------------------------------
# Perfil
# ---------------------------------------------------------------------------

def _repo_frontend(raiz: Path, config: dict) -> Repo:
    cfg = copy.deepcopy(config)
    carpeta = config["frontend"]["carpeta"].strip("/")
    cfg["general"]["exclusiones"] = [
        e for e in config["general"]["exclusiones"] if e.strip("/") != carpeta
    ] + list(config["frontend"]["exclusiones"])
    repo = Repo(raiz, cfg)
    repo.archivos = [p for p in repo.archivos if bajo(p, [carpeta])]
    return repo


def analizar(raiz: Path, config: dict, externas: bool = True) -> InformePerfil:
    inicio = time.perf_counter()
    cfg = config["frontend"]
    carpeta = cfg["carpeta"].strip("/")
    base = Path(raiz) / carpeta
    informe = InformePerfil("frontend", str(Path(raiz).resolve()))
    if not base.is_dir():
        informe.omitido = True
        informe.avisos.append(f"Perfil frontend omitido: no existe {carpeta}/ (se activa en cuanto exista).")
        return informe

    repo = _repo_frontend(Path(raiz), config)
    hallazgos = reglas_propias(repo, config)
    if externas:
        extra, omitidas = correr_externas(repo.raiz, base, config)
        hallazgos.extend(extra)
    else:
        omitidas = {c: "--sin-externas" for c in EXTERNAS}
    for cat, motivo in omitidas.items():
        informe.avisos.append(f"Categoría frontend `{cat}` omitida: {motivo}.")

    from tools.doctor.motor import ordenar  # evita import circular
    informe.hallazgos = ordenar(hallazgos)
    informe.omitidas = omitidas
    informe.puntajes, informe.puntaje = puntaje.calcular(
        informe.hallazgos, cfg["categorias"], config["puntaje"]["pesos_severidad"], omitidas,
    )
    informe.metricas = {
        "archivos": len(repo.archivos),
        "node": bool(shutil.which("node")),
        "segundos": round(time.perf_counter() - inicio, 2),
    }
    return informe
