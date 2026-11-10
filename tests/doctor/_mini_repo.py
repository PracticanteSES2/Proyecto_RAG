"""Ayudas para construir mini-repos sintéticos en temporales (sin git)."""
import tempfile
import textwrap
from pathlib import Path

from tools.doctor.config import config_de
from tools.doctor.motor import analizar


# Configuración mínima para los mini-repos: capas propias y pocas carpetas.
BASE = {
    "estructura": {
        "raiz_permitida": ["app.py", "src", "tools", "tests", "docs", ".gitignore"],
        "subcarpetas": {"tools": ["manual", "doctor"]},
    },
    "capas": {
        "orden": [
            {"nombre": "base", "modulos": ["src.base"]},
            {"nombre": "dominio", "modulos": ["src.a", "src.b"]},
            {"nombre": "app", "modulos": ["src.app"]},
        ],
    },
}


def fusionar(a: dict, b: dict) -> dict:
    salida = dict(a)
    for clave, valor in b.items():
        if isinstance(valor, dict) and isinstance(salida.get(clave), dict):
            salida[clave] = fusionar(salida[clave], valor)
        else:
            salida[clave] = valor
    return salida


def escribir(raiz: Path, archivos: dict) -> None:
    for ruta, contenido in archivos.items():
        destino = raiz / ruta
        destino.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(contenido, bytes):
            destino.write_bytes(contenido)
        else:
            destino.write_text(textwrap.dedent(contenido), encoding="utf-8", newline="\n")


class MiniRepo:
    """Contexto: crea el repo, devuelve su ruta y lo borra al salir."""

    def __init__(self, archivos: dict):
        self.archivos = archivos

    def __enter__(self) -> Path:
        self._tmp = tempfile.TemporaryDirectory(prefix="doctor_")
        raiz = Path(self._tmp.name)
        escribir(raiz, self.archivos)
        return raiz

    def __exit__(self, *exc):
        self._tmp.cleanup()


def diagnosticar(archivos: dict, **cambios):
    """Analiza un mini-repo y devuelve el informe."""
    config = config_de(fusionar(BASE, cambios))
    with MiniRepo(archivos) as raiz:
        return analizar(raiz, config, externas=False)


def reglas(informe) -> set:
    return {(h.regla, h.archivo) for h in informe.hallazgos}
