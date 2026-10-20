"""
Actualización asistida de la documentación: nota informal -> propuesta -> aprobación.

CONTRATO (lo implementa el agente «actualizador»; la interfaz y las pruebas lo usan):

    propuesta = proponer_cambio(nota, source_group, pagina=None, llm=None, cambios_pbip=None)
    ruta = aplicar_propuesta(propuesta, autor)

- `proponer_cambio` nunca escribe archivos. Elige la página (si no se indica),
  pide a MedGemma las operaciones en JSON, las valida y las aplica sobre una
  copia en memoria para producir el texto propuesto y el diff.
- MedGemma no reescribe el documento: solo devuelve operaciones
  (agregar / modificar / eliminar una entrada de una sección).
- Si la nota es ambigua o contradice la documentación, la propuesta queda en
  estado «requiere_aclaracion» con las preguntas en `dudas`; no se inventa.
- `aplicar_propuesta` solo acepta propuestas en estado «lista», vuelve a
  validar contra el archivo actual (si cambió desde la propuesta, falla) y lo
  guarda con repositorio.guardar_pagina. No reindexa: eso lo hace
  indexacion.reindexar_grupo después de aprobar.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .formato import Operacion

ESTADOS = ("lista", "requiere_aclaracion", "error")


@dataclass
class Propuesta:
    nota: str
    source_group: str
    pagina: str = ""
    operaciones: list[Operacion] = field(default_factory=list)
    resumen: str = ""
    dudas: list[str] = field(default_factory=list)
    estado: str = "error"
    errores: list[str] = field(default_factory=list)
    antes: str = ""
    despues: str = ""
    diff: str = ""
    llm_raw: str = ""
    candidatas: list[str] = field(default_factory=list)


def proponer_cambio(nota, source_group, pagina=None, llm=None, cambios_pbip=None) -> Propuesta:
    raise NotImplementedError("Pendiente: agente actualizador")


def aplicar_propuesta(propuesta: Propuesta, autor: str, raiz=None):
    raise NotImplementedError("Pendiente: agente actualizador")
