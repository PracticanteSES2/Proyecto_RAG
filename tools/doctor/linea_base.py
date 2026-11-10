"""Línea base y trinquete: el puntaje nunca baja y no aparecen hallazgos altos nuevos."""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from tools.doctor.modelo import Hallazgo, Informe, InformePerfil

VERSION = 2
_EPS = 1e-6


@dataclass
class Verificacion:
    fallos: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    mejoras: list[str] = field(default_factory=list)
    nuevos: list[tuple[str, Hallazgo]] = field(default_factory=list)  # (perfil, hallazgo)
    sin_verificar: list[str] = field(default_factory=list)            # perfiles/categorías omitidos

    @property
    def ok(self) -> bool:
        return not self.fallos

    def a_dict(self) -> dict:
        return {
            "ok": self.ok,
            "fallos": self.fallos,
            "avisos": self.avisos,
            "mejoras": self.mejoras,
            "sin_verificar": self.sin_verificar,
            "nuevos": [{"perfil": p, **h.a_dict()} for p, h in self.nuevos],
        }


def _huellas(hallazgos: list[Hallazgo]) -> dict[str, dict[str, int]]:
    salida: dict[str, Counter] = {}
    for h in hallazgos:
        salida.setdefault(h.categoria, Counter())[h.huella] += 1
    return {c: dict(sorted(v.items())) for c, v in sorted(salida.items())}


def seccion(informe: InformePerfil) -> dict:
    return {
        "puntaje": informe.puntaje,
        "categorias": dict(informe.puntajes),
        "huellas": _huellas(informe.hallazgos),
        "legado": informe.metricas.get("legado", {}),
    }


def crear(informe: Informe, previa: dict | None = None) -> dict:
    """Línea base nueva; conserva de la previa lo que hoy no se pudo medir."""
    perfiles_previos = (previa or {}).get("perfiles", {})
    perfiles = {}
    for nombre, inf in informe.perfiles.items():
        previo = perfiles_previos.get(nombre)
        if inf.omitido:
            perfiles[nombre] = previo
            continue
        nueva = seccion(inf)
        if previo:
            for cat in inf.omitidas:
                if cat in previo.get("categorias", {}):
                    nueva["categorias"][cat] = previo["categorias"][cat]
                    if cat in previo.get("huellas", {}):
                        nueva["huellas"][cat] = previo["huellas"][cat]
        perfiles[nombre] = nueva
    for nombre, previo in perfiles_previos.items():
        perfiles.setdefault(nombre, previo)
    evaluados = {p for p, i in informe.perfiles.items() if not i.omitido}
    con_base = {p for p, s in perfiles.items() if s}
    completo = con_base <= evaluados and not any(i.omitidas for i in informe.perfiles.values())
    return {
        "version": VERSION,
        "fecha": date.today().isoformat(),
        "puntaje_global": informe.puntaje_global if completo else (previa or {}).get("puntaje_global"),
        "perfiles": perfiles,
    }


def cargar(ruta: Path) -> dict | None:
    if not ruta.exists():
        return None
    return json.loads(ruta.read_text(encoding="utf-8"))


def guardar(ruta: Path, datos: dict) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


def _comparar_perfil(nombre: str, inf: InformePerfil, base: dict, tol: float, v: Verificacion) -> None:
    bcat = base.get("categorias", {})
    for cat, actual in inf.puntajes.items():
        if cat not in bcat:
            continue
        previo = bcat[cat]
        if actual < previo - tol - _EPS:
            v.fallos.append(f"{nombre}/{cat}: el puntaje bajó de {previo:.2f} a {actual:.2f}.")
        elif actual > previo + _EPS:
            v.mejoras.append(f"{nombre}/{cat}: {previo:.2f} → {actual:.2f}")
    for cat in sorted(set(bcat) - set(inf.puntajes)):
        v.sin_verificar.append(f"{nombre}/{cat}")
        v.avisos.append(f"{nombre}/{cat} no se pudo verificar ({inf.omitidas.get(cat, 'omitida')}).")
    if set(bcat) == set(inf.puntajes) and base.get("puntaje") is not None and inf.puntaje is not None:
        if inf.puntaje < base["puntaje"] - tol - _EPS:
            v.fallos.append(f"{nombre}: el puntaje del perfil bajó de {base['puntaje']:.2f} a {inf.puntaje:.2f}.")

    previas: Counter = Counter()
    for cat, huellas in base.get("huellas", {}).items():
        previas.update(huellas)
    vistas: Counter = Counter()
    for h in inf.hallazgos:
        vistas[h.huella] += 1
        if vistas[h.huella] > previas.get(h.huella, 0):
            v.nuevos.append((nombre, h))
            if h.severidad == "alta":
                v.fallos.append(f"{nombre}: hallazgo alto nuevo [{h.categoria}/{h.regla}] {h.ubicacion} — {h.mensaje}")


def comparar(informe: Informe, base: dict, tolerancia: float = 0.0) -> Verificacion:
    v = Verificacion()
    perfiles_base = base.get("perfiles", {})
    for nombre, inf in informe.perfiles.items():
        b = perfiles_base.get(nombre)
        if inf.omitido:
            if b:
                v.sin_verificar.append(nombre)
                v.avisos.append(f"Perfil {nombre} sin verificar: {'; '.join(inf.avisos) or 'omitido'}")
            continue
        if not b:
            v.avisos.append(f"Perfil {nombre} sin línea base: ejecutar --actualizar-linea-base para fijar su listón.")
            continue
        _comparar_perfil(nombre, inf, b, tolerancia, v)
    evaluados = {p for p, i in informe.perfiles.items() if not i.omitido}
    en_base = {p for p, s in perfiles_base.items() if s}
    if evaluados == en_base and len(evaluados) == len(informe.perfiles) and not v.sin_verificar \
            and base.get("puntaje_global") is not None and informe.puntaje_global is not None:
        if informe.puntaje_global < base["puntaje_global"] - tolerancia - _EPS:
            v.fallos.append(f"Global: bajó de {base['puntaje_global']:.2f} a {informe.puntaje_global:.2f}.")
        elif informe.puntaje_global > base["puntaje_global"] + _EPS:
            v.mejoras.append(f"global: {base['puntaje_global']:.2f} → {informe.puntaje_global:.2f}")
    return v
