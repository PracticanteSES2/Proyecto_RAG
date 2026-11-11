"""Progreso de una propuesta de documentación mientras MedGemma trabaja.

Mismas reglas que el chat (specs/009-experiencia-espera, src/chatbot/progreso.py):
frases que describen el trabajo real con LA NOTA, rotación cada `ROTACION_S` y
mensajes de espera en los mismos umbrales (`nivel_espera`). Nada habla de colas,
filas, turnos, otras consultas, el servidor ni saturación.

La etapa es real: `ProveedorObservado` envuelve al proveedor de MedGemma que
recibe `actualizador.proponer_cambio(llm=…)` y avisa al empezar cada llamada
(que sigue pasando por la puerta `call_llm`). La frase y la espera se calculan
al leer (sondeo), sin hilos reloj.
"""
from __future__ import annotations

import inspect
from collections.abc import Callable

from src.chatbot.frases_progreso import ROTACION_S
from src.chatbot.progreso import nivel_espera
from src.docs_md.actualizador import MAX_TOKENS_PAGINA

ETAPA_INICIAL = "leyendo_nota"
FRASES = {
    "leyendo_nota": (
        "Leyendo tu nota",
        "Revisando qué cambió en el tablero",
        "Buscando en la documentación lo que mencionas",
    ),
    "eligiendo_pagina": (
        "Ubicando la página que corresponde",
        "Comparando las páginas parecidas del tablero",
        "Pensando…",
    ),
    "redactando": (
        "Redactando el cambio en la documentación",
        "Preparando el texto nuevo de la página",
        "Ajustando la documentación a tu nota",
        "Pensando…",
    ),
    "revisando": (
        "Revisando el cambio propuesto",
        "Comprobando que el cambio cuadre con tu nota",
        "Puliendo la redacción",
    ),
}
# Un mensaje por umbral de `src.chatbot.frases_progreso.UMBRALES_ESPERA`
# (10/25/50/90 s), hablando de la nota.
ESPERAS = (
    "Sigo trabajando en tu nota…",
    "Estoy armando una propuesta completa; ya casi la tengo…",
    "Sigo con tu nota; no hace falta volver a enviarla.",
    "Me está tomando más de lo habitual, pero sigo en ello.",
)


def progreso(etapa: str, desde_etapa: float, inicio: float, ahora: float) -> dict:
    """{"etapa", "frase", "espera"} de una propuesta en preparación."""
    variantes = FRASES.get(etapa) or FRASES[ETAPA_INICIAL]
    indice = int(max(0.0, ahora - desde_etapa) // ROTACION_S) % len(variantes)
    nivel = nivel_espera(max(0.0, ahora - inicio))
    espera = ESPERAS[min(nivel, len(ESPERAS)) - 1] if nivel else None
    return {"etapa": etapa, "frase": variantes[indice], "espera": espera}


def etapa_de_llamada(max_tokens, llamadas_operaciones: int) -> str:
    """La llamada corta (MAX_TOKENS_PAGINA) elige la página; la primera de
    operaciones redacta y un reintento revisa."""
    if max_tokens == MAX_TOKENS_PAGINA:
        return "eligiendo_pagina"
    return "redactando" if llamadas_operaciones == 0 else "revisando"


def _aceptados(proveedor, argumentos: dict) -> dict:
    """Solo los argumentos que acepta `proveedor.chat` (como hace llm_gate)."""
    try:
        parametros = inspect.signature(proveedor.chat).parameters
    except (TypeError, ValueError):
        return argumentos
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parametros.values()):
        return argumentos
    return {clave: valor for clave, valor in argumentos.items() if clave in parametros}


class ProveedorObservado:
    """Proveedor de LLM que avisa `al_llamar(etapa)` al empezar cada llamada y
    delega en el real (creado al primer uso con `fabrica`, p. ej.
    MedGemmaProvider). Si no se puede crear, responde como `call_llm` ante un
    fallo («llm_error»), igual que el actualizador sin proveedor."""

    def __init__(self, fabrica: Callable[[], object], al_llamar: Callable[[str], None]):
        self._fabrica = fabrica
        self._al_llamar = al_llamar
        self._real = None
        self._error: Exception | None = None
        self._operaciones = 0

    def _proveedor(self):
        if self._real is None and self._error is None:
            try:
                self._real = self._fabrica()
            except Exception as error:  # noqa: BLE001  (p. ej. falta MEDGEMMA_BASE_URL)
                self._error = error
        return self._real

    @property
    def enforces_timeout(self) -> bool:
        return bool(getattr(self._proveedor(), "enforces_timeout", False))

    def chat(self, messages, **argumentos):
        etapa = etapa_de_llamada(argumentos.get("max_tokens"), self._operaciones)
        if etapa != "eligiendo_pagina":
            self._operaciones += 1
        self._al_llamar(etapa)
        real = self._proveedor()
        if real is None:
            return {"status": "llm_error", "answer": None, "error": f"MedGemma no está configurado: {self._error}"}
        return real.chat(messages=messages, **_aceptados(real, argumentos))


def proveedor_medgemma():
    from src.llm.medgemma_provider import MedGemmaProvider

    return MedGemmaProvider()
