"""Tipos del doctor: hallazgos e informes por perfil (backend, frontend)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

SEVERIDADES = ("alta", "media", "baja")

CATEGORIAS = {
    "backend": {
        "estructura": "Estructura",
        "tamano": "Tamaño y complejidad",
        "duplicacion": "Duplicación",
        "muerto": "Código muerto",
        "capas": "Capas e importaciones",
        "pruebas": "Pruebas",
        "higiene": "Higiene",
        "fastapi": "FastAPI",
    },
    "frontend": {
        "estructura": "Estructura",
        "tipos": "Tipos (sin any)",
        "compilacion": "Compilación (tsc)",
        "lint": "Lint (ESLint)",
        "react": "React (react-doctor)",
        "arquitectura": "Arquitectura",
        "higiene": "Higiene",
    },
}
PERFILES = tuple(CATEGORIAS)


@dataclass(frozen=True)
class Hallazgo:
    categoria: str
    regla: str
    severidad: str
    archivo: str
    linea: int
    mensaje: str
    sugerencia: str
    clave: str = ""  # identifica el hallazgo dentro del archivo sin usar la línea

    @property
    def huella(self) -> str:
        return f"{self.regla}|{self.archivo}|{self.clave}"

    @property
    def ubicacion(self) -> str:
        return f"{self.archivo}:{self.linea}" if self.linea else self.archivo

    def a_dict(self) -> dict:
        datos = asdict(self)
        datos["huella"] = self.huella
        return datos


@dataclass
class Externo:
    """Salida informativa de una herramienta externa (no cuenta en el puntaje)."""

    herramienta: str
    archivo: str
    linea: int
    codigo: str
    mensaje: str


@dataclass
class InformePerfil:
    perfil: str
    raiz: str
    hallazgos: list[Hallazgo] = field(default_factory=list)
    puntajes: dict[str, float] = field(default_factory=dict)   # solo categorías evaluadas
    puntaje: float | None = None
    omitido: bool = False                                     # perfil saltado (sin carpeta, sin Node…)
    omitidas: dict[str, str] = field(default_factory=dict)    # categoría → motivo
    avisos: list[str] = field(default_factory=list)
    metricas: dict = field(default_factory=dict)
    externos: list[Externo] = field(default_factory=list)

    @property
    def puntaje_global(self) -> float | None:  # compatibilidad: puntaje del perfil
        return self.puntaje

    def a_dict(self) -> dict:
        nombres = CATEGORIAS[self.perfil]
        return {
            "perfil": self.perfil,
            "puntaje": self.puntaje,
            "omitido": self.omitido,
            "avisos": self.avisos,
            "categorias": {
                c: {
                    "nombre": nombres[c],
                    "puntaje": self.puntajes[c],
                    "hallazgos": sum(1 for h in self.hallazgos if h.categoria == c),
                }
                for c in self.puntajes
            },
            "categorias_omitidas": self.omitidas,
            "metricas": self.metricas,
            "hallazgos": [h.a_dict() for h in self.hallazgos],
            "externos": [asdict(e) for e in self.externos],
        }


@dataclass
class Informe:
    perfiles: dict[str, InformePerfil]
    puntaje_global: float | None

    def a_dict(self) -> dict:
        return {
            "puntaje_global": self.puntaje_global,
            "perfiles": {p: i.a_dict() for p, i in self.perfiles.items()},
        }
