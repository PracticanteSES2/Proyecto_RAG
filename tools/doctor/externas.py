"""Herramientas externas opcionales del perfil backend (ruff, vulture).

Solo informan: no cambian el puntaje, para que el trinquete no dependa de lo instalado.
Si no están, se anotan como omitidas y el doctor sigue.
"""
from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from tools.doctor.modelo import Externo


def _comando(modulo: str, ejecutable: str) -> list[str] | None:
    if importlib.util.find_spec(modulo) is not None:
        return [sys.executable, "-m", modulo]
    ruta = shutil.which(ejecutable)
    return [ruta] if ruta else None


def _rel(raiz: Path, archivo: str) -> str:
    try:
        return Path(archivo).resolve().relative_to(raiz).as_posix()
    except ValueError:
        return archivo.replace("\\", "/")


def ruff(raiz: Path, rutas: list[str], cfg: dict) -> tuple[list[Externo], str | None]:
    cmd = _comando("ruff", "ruff")
    if not cmd:
        return [], "ruff no instalado (pip install -r requirements-dev.txt)"
    try:
        r = subprocess.run(
            [*cmd, "check", "--no-cache", "--output-format", "json", "--exit-zero",
             "--select", ",".join(cfg["ruff_reglas"]), *rutas],
            cwd=raiz, capture_output=True, timeout=cfg["timeout"],
        )
        datos = json.loads(r.stdout.decode("utf-8", "replace") or "[]")
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as e:
        return [], f"ruff falló: {e}"
    return [
        Externo("ruff", _rel(raiz, d.get("filename", "")), (d.get("location") or {}).get("row", 0),
                d.get("code") or "", d.get("message", ""))
        for d in datos
    ], None


_VULTURE = re.compile(r"^(.*?):(\d+): (.*)$")


def vulture(raiz: Path, rutas: list[str], cfg: dict) -> tuple[list[Externo], str | None]:
    cmd = _comando("vulture", "vulture")
    if not cmd:
        return [], "vulture no instalado (pip install -r requirements-dev.txt)"
    try:
        r = subprocess.run(
            [*cmd, *rutas, "--min-confidence", str(cfg["vulture_confianza"])],
            cwd=raiz, capture_output=True, timeout=cfg["timeout"],
        )
    except (OSError, subprocess.SubprocessError) as e:
        return [], f"vulture falló: {e}"
    salida = []
    for linea in r.stdout.decode("utf-8", "replace").splitlines():
        m = _VULTURE.match(linea.strip())
        if m:
            salida.append(Externo("vulture", _rel(raiz, m.group(1)), int(m.group(2)), "muerto", m.group(3)))
    return salida, None


def correr(raiz: Path, config: dict) -> tuple[list[Externo], list[str]]:
    cfg = config["externas"]
    if not cfg["activar"]:
        return [], ["externas desactivadas en reglas.toml"]
    rutas = [r for r in config["general"]["codigo"] if (raiz / r).exists()]
    if not rutas:
        return [], []
    externos, omitidas = [], []
    for herramienta in (ruff, vulture):
        datos, motivo = herramienta(raiz, rutas, cfg)
        externos.extend(datos)
        if motivo:
            omitidas.append(motivo)
    return externos, omitidas
