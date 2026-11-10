"""Orquestación: corre los perfiles (backend, frontend) y arma el informe."""
from __future__ import annotations

import time
from pathlib import Path

from tools.doctor import externas as externas_py
from tools.doctor import frontend as perfil_frontend
from tools.doctor import puntaje
from tools.doctor.modelo import Hallazgo, Informe, InformePerfil, PERFILES
from tools.doctor.reglas import TODAS
from tools.doctor.repo import Repo, bajo

_ORDEN_SEV = {"alta": 0, "media": 1, "baja": 2}


def ordenar(hallazgos: list[Hallazgo]) -> list[Hallazgo]:
    return sorted(hallazgos, key=lambda h: (_ORDEN_SEV[h.severidad], h.categoria, h.archivo, h.linea, h.regla))


def medir_legado(repo: Repo, rutas: list[str]) -> dict[str, dict]:
    salida = {}
    for ruta in rutas:
        archivos = [p for p in repo.archivos if bajo(p, [ruta])]
        lineas = 0
        for p in archivos:
            texto = repo.texto_de(p)
            if texto:
                lineas += texto.count("\n") + (0 if texto.endswith("\n") else 1)
        salida[ruta] = {"archivos": len(archivos), "lineas": lineas}
    return salida


def _legado_crece(actual: dict, base: dict | None) -> list[Hallazgo]:
    salida = []
    for ruta, med in sorted(actual.items()):
        previo = (base or {}).get(ruta)
        if not previo:
            continue
        if med["lineas"] > previo["lineas"] or med["archivos"] > previo["archivos"]:
            salida.append(Hallazgo(
                "estructura", "legado_crece", "alta", ruta, 0,
                f"El legado `{ruta}` creció: {previo['archivos']}→{med['archivos']} archivos, "
                f"{previo['lineas']}→{med['lineas']} líneas.",
                "El código nuevo va en backend/ (FastAPI) o frontend/ (Next.js); el legado Streamlit solo se "
                "mantiene o se reduce. Si el cambio es una corrección imprescindible, documentarlo y subir el listón "
                "con --actualizar-linea-base --forzar.",
                "crece",
            ))
    return salida


def analizar(raiz: Path, config: dict, externas: bool = True, base: dict | None = None) -> InformePerfil:
    """Perfil backend (Python). `base` es la sección backend de la línea base (para el legado)."""
    inicio = time.perf_counter()
    repo = Repo(Path(raiz), config)
    hallazgos: list[Hallazgo] = []
    for revisar in TODAS.values():
        hallazgos.extend(revisar(repo))
    legado = medir_legado(repo, config["legado"]["rutas"])
    hallazgos.extend(_legado_crece(legado, (base or {}).get("legado")))
    hallazgos = ordenar(hallazgos)
    puntajes, total = puntaje.calcular(hallazgos, config["categorias"], config["puntaje"]["pesos_severidad"])
    informe = InformePerfil("backend", str(repo.raiz), hallazgos, puntajes, total)
    if externas:
        informe.externos, omitidas = externas_py.correr(repo.raiz, config)
        informe.avisos.extend(f"Externa omitida: {m}" for m in omitidas)
    lineas = sum(m.texto.count("\n") for m in repo.modulos.values())
    informe.metricas = {
        "archivos": len(repo.archivos),
        "modulos_python": len(repo.modulos),
        "lineas_python": lineas,
        "git": repo.es_git,
        "legado": legado,
        "segundos": round(time.perf_counter() - inicio, 2),
    }
    return informe


def analizar_todo(raiz: Path, config: dict, perfiles=PERFILES, externas: bool = True,
                  linea_base: dict | None = None) -> Informe:
    bases = (linea_base or {}).get("perfiles", {})
    resultado: dict[str, InformePerfil] = {}
    if "backend" in perfiles:
        resultado["backend"] = analizar(raiz, config, externas, bases.get("backend"))
    if "frontend" in perfiles:
        resultado["frontend"] = perfil_frontend.analizar(Path(raiz), config, externas)
    total = puntaje.global_(
        {p: (None if i.omitido else i.puntaje) for p, i in resultado.items()},
        config["perfiles"]["pesos"],
    )
    return Informe(resultado, total)
