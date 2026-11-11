"""Lo que el trabajador publica sobre sí mismo: capacidades (estado vacío del
chat), latido (salud) y diagnóstico del servidor (lo del panel de Streamlit)."""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path

LOG = logging.getLogger(__name__)
MAX_EJEMPLOS = 5
_EJEMPLOS_FIJOS = ("¿Qué tableros puedo consultar?",)


def _metricas_aprobadas(raiz: Path | None) -> list[dict]:
    if raiz is None:
        return []
    try:
        datos = json.loads((Path(raiz) / "data" / "rag" / "master_metrics.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [m for m in datos.get("metrics") or []
            if isinstance(m, dict) and m.get("validation_status") in (None, "approved")]


def _etiquetas_metricas(raiz: Path | None) -> list[tuple[str, str]]:
    """(etiqueta, informe) de las métricas aprobadas, una por informe. Se
    descartan las que no tienen informe o cuya etiqueta no empieza por letra
    (nombres técnicos como «%OCUPACIONHOS» no sirven de ejemplo)."""
    vistas, salida = set(), []
    for metrica in _metricas_aprobadas(raiz):
        etiqueta, informe = str(metrica.get("label") or "").strip(), str(metrica.get("report") or "").strip()
        if etiqueta[:1].isalpha() and informe and informe not in vistas:
            vistas.add(informe)
            salida.append((etiqueta, informe))
    return salida


def _nombre_tablero(informe: str, tableros: list[str]) -> str:
    """Nombre del catálogo si coincide (sin distinguir mayúsculas); si no, el del informe en tipo título."""
    return next((t for t in tableros if t.casefold() == informe.casefold()), informe.title())


def ejemplos_preguntas(raiz: Path, tableros_documentacion: list[str],
                       tableros_datos: list[str] | None = None) -> list[str]:
    tableros = list(tableros_datos or [])
    ejemplos = [f"{etiqueta.capitalize()} del mes pasado en {_nombre_tablero(informe, tableros)}"
                for etiqueta, informe in _etiquetas_metricas(raiz)[:3]]
    if tableros_documentacion:
        ejemplos.append(f"¿Qué muestra el tablero {tableros_documentacion[0]}?")
    ejemplos.extend(_EJEMPLOS_FIJOS)
    return ejemplos[:MAX_EJEMPLOS]


def capacidades(instancia, raiz: Path, ejemplos_fijos: list[str] | None = None) -> dict:
    from src.chatbot.portero import catalogo_tableros

    datos, documentacion = catalogo_tableros(getattr(instancia.engine, "source_router", None))
    return {
        "listo": True,
        "tableros_datos": list(datos),
        "tableros_documentacion": list(documentacion),
        "ejemplos": list(ejemplos_fijos) if ejemplos_fijos else ejemplos_preguntas(raiz, documentacion, list(datos)),
    }


def _estado(status: dict | None, listo: str = "ready") -> str:
    if not status:
        return "desconocido"
    return "ok" if str(status.get("status")) in (listo, "success") else "caido"


def latido(piscina, version: str, huella: str | None, iniciado: str, modo: str) -> dict:
    principal = piscina.principal
    return {
        "pid": os.getpid(), "iniciado": iniciado, "modo": modo, "version": version, "huella": huella,
        "instancias": piscina.total, "ocupadas": piscina.ocupadas,
        "medgemma": {"estado": _estado(principal.estado_medgemma),
                     "modelo": (principal.estado_medgemma or {}).get("model")},
        "powerbi": {"estado": _estado(principal.estado_powerbi)},
        "indice": {"estado": _estado(principal.estado_indice)},
    }


def diagnostico_servidor(piscina, cola: dict) -> dict:
    from src.chatbot import runtime_stats

    proveedor = getattr(piscina.principal.engine, "powerbi_provider", None)
    instantanea = runtime_stats.STATS.snapshot(proveedor)
    datos = {
        "lineas_markdown": runtime_stats.diagnostics_lines(instantanea, proveedor),
        "linea_estado": runtime_stats.status_line(instantanea),
        "instantanea": instantanea,
        "cola": cola,
        "motor": {"instancias": piscina.total, "ocupadas": piscina.ocupadas},
    }
    try:
        datos["presion_llm"] = runtime_stats.STATS.llm_pressure()
    except Exception:
        LOG.debug("llm_pressure no disponible", exc_info=True)
    return json.loads(json.dumps(datos, ensure_ascii=False, default=str))


class ChequeoEnSegundoPlano:
    """Chequeo externo (p. ej. la salud de MedGemma) que NUNCA bloquea a quien
    pregunta: corre en un hilo daemon como mucho cada `intervalo_s` y devuelve
    el último resultado cacheado. Si una corrida pasa de `limite_s`, el
    resultado es {"status": "timeout"} hasta que termine (el hilo sigue)."""

    def __init__(self, funcion, intervalo_s: float = 60.0, limite_s: float = 3.0, reloj=time.monotonic):
        self._funcion = funcion
        self.intervalo_s = intervalo_s
        self.limite_s = limite_s
        self._reloj = reloj
        self._candado = threading.Lock()
        self._resultado = None
        self._inicio = None  # corrida en curso
        self._ultima = None  # inicio de la última corrida

    def _correr(self):
        try:
            resultado = dict(self._funcion() or {})
        except Exception as error:
            LOG.warning("Chequeo externo falló: %s", type(error).__name__)
            resultado = {"status": "error"}
        with self._candado:
            self._resultado, self._inicio = resultado, None

    def refrescar(self) -> None:
        with self._candado:
            ahora = self._reloj()
            if self._inicio is not None or (self._ultima is not None and ahora - self._ultima < self.intervalo_s):
                return
            self._inicio = self._ultima = ahora
        threading.Thread(target=self._correr, name="chequeo-externo", daemon=True).start()

    def ultimo(self) -> dict | None:
        with self._candado:
            if self._inicio is not None and self._reloj() - self._inicio > self.limite_s:
                return {"status": "timeout"}
            return dict(self._resultado) if self._resultado is not None else None


def chequeo_medgemma(piscina, intervalo_s: float = 60.0, limite_s: float = 3.0) -> ChequeoEnSegundoPlano | None:
    """Chequeo en segundo plano de MedGemma (su healthcheck puede tardar hasta
    MEDGEMMA_HEALTH_TIMEOUT); None si el motor no lo expone."""
    try:
        proveedor = piscina.principal.engine.rag_answer_engine.answer_synthesizer.llm_provider
    except AttributeError:
        return None
    healthcheck = getattr(proveedor, "healthcheck", None)
    return ChequeoEnSegundoPlano(healthcheck, intervalo_s, limite_s) if callable(healthcheck) else None
