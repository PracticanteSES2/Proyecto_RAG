"""Lo que el trabajador publica sobre sí mismo: capacidades (estado vacío del
chat), latido (salud) y diagnóstico del servidor (lo del panel de Streamlit)."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

LOG = logging.getLogger(__name__)
MAX_EJEMPLOS = 5
_EJEMPLOS_FIJOS = ("¿Qué tableros puedo consultar?",)


def _etiquetas_metricas(raiz: Path) -> list[tuple[str, str]]:
    """(etiqueta, informe) de las métricas aprobadas, una por informe."""
    if raiz is None:
        return []
    ruta = Path(raiz) / "data" / "rag" / "master_metrics.json"
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except Exception:
        return []
    vistas, salida = set(), []
    for metrica in datos.get("metrics") or []:
        if not isinstance(metrica, dict) or metrica.get("validation_status") not in (None, "approved"):
            continue
        etiqueta, informe = str(metrica.get("label") or "").strip(), str(metrica.get("report") or "")
        if etiqueta and informe not in vistas:
            vistas.add(informe)
            salida.append((etiqueta, informe))
    return salida


def ejemplos_preguntas(raiz: Path, tableros_documentacion: list[str]) -> list[str]:
    ejemplos = [f"¿Cuánto fue {etiqueta.lower()} el mes pasado?" for etiqueta, _ in _etiquetas_metricas(raiz)[:3]]
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
        "ejemplos": list(ejemplos_fijos) if ejemplos_fijos else ejemplos_preguntas(raiz, documentacion),
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


def refrescar_medgemma(piscina) -> None:
    """Vuelve a consultar la salud de MedGemma (barato; cada minuto)."""
    principal = piscina.principal
    try:
        proveedor = principal.engine.rag_answer_engine.answer_synthesizer.llm_provider
        principal.estado_medgemma = dict(proveedor.healthcheck() or {})
    except Exception:
        LOG.debug("No se pudo refrescar la salud de MedGemma", exc_info=True)
