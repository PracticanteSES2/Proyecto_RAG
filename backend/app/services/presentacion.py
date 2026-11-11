"""Del `result` del motor al payload `respuesta` del contrato v1.

Puerto de lo que app.py (Streamlit, congelado) hace al mostrar un turno:
`get_display_answer`, `reset_if_finished`, el enlace «Abrir en Power BI», los
botones de la contrapregunta (con el enlace de cada opción), «Detalles de la
consulta» y el modo diagnóstico. Sin interfaz: solo datos JSON.
"""
from __future__ import annotations

import json
import logging
from pathlib import PurePath

LOG = logging.getLogger(__name__)

MENSAJE_ERROR = "Ocurrió un error al procesar la consulta. Intenta nuevamente."

RUTAS = {
    "conversacion": "conversacion",
    "powerbi": "datos",
    "rag": "documentacion",
    "clarification": "contrapregunta",
    "out_of_scope": "fuera_de_alcance",
}
MAX_FUENTES = 6


# ----------------------------------------------------------------------
# Texto de la respuesta (puerto de app.py::get_display_answer)
# ----------------------------------------------------------------------

NO_ENCONTRADO = "No encontré información relacionada con esa pregunta."
SIN_INDICADOR = "No identifiqué el indicador que buscas. Escribe el nombre del indicador o del tablero donde lo ves."
POWERBI_RECHAZO = ("La métrica se identificó, pero Power BI rechazó la consulta. "
                   "Intenta de nuevo en un momento o reformula la pregunta.")
SIN_COMPLETAR = "No pude completar la consulta. Intenta reformular la pregunta o vuelve a intentarlo."


def texto_respuesta(result: dict, formatter) -> str:
    """Mismo orden de decisión que app.py::get_display_answer."""
    from src.chatbot.response_formatter import clarification_prompt

    if result.get("status") == "needs_clarification":
        return clarification_prompt(result)
    texto = _texto_por_ruta(result, formatter)
    return texto if texto is not None else _texto_por_estado(result)


def _texto_por_ruta(result: dict, formatter) -> str | None:
    status, route = result.get("status"), result.get("route")
    if status == "not_found":
        return result.get("answer") or NO_ENCONTRADO
    if route == "rag":
        return result.get("answer") or "No encontré información suficiente."
    if route == "conversacion":
        return result.get("answer") or ""
    if route == "powerbi" and status == "success":
        return _texto_dato(result, formatter)
    return None


def _texto_por_estado(result: dict) -> str:
    from src.chatbot.response_formatter import format_empty_result

    por_estado = {
        "metric_not_resolved": lambda r: r.get("answer") or SIN_INDICADOR,
        "unsupported_filter": _texto_filtro_no_soportado,
        "powerbi_error": lambda r: POWERBI_RECHAZO,
        "empty_result": format_empty_result,
    }
    funcion = por_estado.get(result.get("status"))
    return funcion(result) if funcion else SIN_COMPLETAR


def _texto_formateado(result: dict, formatter) -> str | None:
    try:
        answer = formatter.format(result) if formatter is not None else None
    except Exception:
        LOG.debug("ResponseFormatter no pudo formatear el resultado", exc_info=True)
        return None
    return answer if answer and "None" not in answer else None


def _texto_dato(result: dict, formatter) -> str:
    """Respuesta numérica de Power BI (Query Plan, tabla o valor suelto)."""
    from src.chatbot.response_formatter import format_query_plan_answer

    if result.get("query_plan"):
        return format_query_plan_answer(result)
    if result.get("result_type") == "table" and result.get("answer"):
        return result.get("answer")
    formateado = _texto_formateado(result, formatter)
    if formateado:
        return formateado
    metric, value = result.get("metric"), result.get("value")
    if value is None:
        return "No hay datos para esos filtros."
    if metric:
        return f"{metric}: {value}"
    return f"El resultado consultado en Power BI es {value}."


def _texto_filtro_no_soportado(result: dict) -> str:
    details = result.get("details", {}) or {}
    reason = details.get("reason")
    if result.get("powerbi_unavailable") or details.get("domain_error"):
        return ("Identifiqué la métrica, pero no pude consultar Power BI para verificar el filtro "
                "solicitado. Revisa que Power BI esté disponible e intenta de nuevo.")
    if reason == "requested_value_not_found":
        return "Identifiqué la métrica, pero no pude verificar el valor del filtro solicitado."
    if reason == "date_dimension_not_found_in_report":
        if details.get("explanation"):
            return details["explanation"]
        period = details.get("requested_period")
        if period:
            return ("Identifiqué la métrica, pero este tablero no tiene una fecha que permita "
                    f"aplicar el período «{period}». Prueba con un año o un mes.")
        return "Identifiqué la métrica, pero no encontré una fecha validada para aplicar ese período."
    if reason == "requested_dimension_not_found_in_report" and details.get("explanation"):
        return details["explanation"]
    return "Identifiqué la métrica, pero no pude verificar la dimensión solicitada en este tablero."

# ----------------------------------------------------------------------
# Piezas del payload
# ----------------------------------------------------------------------

def _seguro(funcion, *args):
    """Los enlaces y adornos son un extra: si fallan, la respuesta sale sin ellos."""
    try:
        return funcion(*args)
    except Exception:
        LOG.warning("%s falló; la respuesta sale sin ese extra", getattr(funcion, "__name__", funcion),
                    exc_info=True)
        return None


def _titulo_enlace(enlace: dict) -> str:
    titulo = str(enlace.get("etiqueta") or "").removeprefix("Abrir ").strip() or "Abrir en Power BI"
    if enlace.get("filtrado"):
        titulo += " · con los filtros de la consulta"
    return titulo


def enlaces_powerbi(result: dict) -> list[dict]:
    from src.providers.powerbi_links import enlace_para_resultado

    enlace = _seguro(enlace_para_resultado, result)
    if not enlace or not enlace.get("url"):
        return []
    return [{"titulo": _titulo_enlace(enlace), "url": enlace["url"]}]


def contrapregunta(result: dict) -> tuple[dict | None, list[dict]]:
    """(payload `contrapregunta`, opciones pendientes para el estado) — las
    pendientes guardan el id ORIGINAL (el motor puede usar ids no texto)."""
    from src.chatbot.response_formatter import clarification_buttons, clarification_prompt
    from src.providers.powerbi_links import enlace_para_opcion

    botones = clarification_buttons(result)
    if not botones:
        return None, []
    por_id = {str(o.get("id")): o for o in result.get("clarification_options") or [] if isinstance(o, dict)}
    opciones, pendientes = [], []
    for boton in botones:
        opcion = {"id": str(boton["id"]), "texto": boton["label"], "descripcion": boton.get("caption")}
        enlace = _seguro(enlace_para_opcion, por_id.get(str(boton["id"])))
        if enlace and enlace.get("url"):
            opcion["enlace_powerbi"] = {"titulo": _titulo_enlace(enlace), "url": enlace["url"]}
        opciones.append(opcion)
        pendientes.append({"id": str(boton["id"]), "id_original": boton["id"], "texto": boton["label"]})
    return {"pregunta": clarification_prompt(result), "opciones": opciones}, pendientes


def _nombre_archivo(valor) -> str | None:
    if not valor:
        return None
    return PurePath(str(valor).replace("\\", "/")).stem or None


def _titulo_compuesto(tablero, pagina):
    return f"{tablero} › {pagina}" if tablero and pagina else tablero


def _fuente_documental(fuente: dict) -> tuple:
    """(titulo, tablero, pagina) de un fragmento de documentación recuperado."""
    tablero = fuente.get("dashboard")
    pagina = fuente.get("page") or fuente.get("page_display_name") or fuente.get("page_name")
    archivo = _nombre_archivo(fuente.get("source_file") or fuente.get("relative_path"))
    titulo = fuente.get("title") or fuente.get("section_title") or _titulo_compuesto(tablero, pagina) or archivo
    return titulo, tablero, pagina


def _fuente_dato(result: dict) -> tuple:
    """(titulo, tablero, pagina) del informe de Power BI que respondió."""
    informe, pagina = result.get("report"), result.get("dashboard")
    if str(pagina or "").casefold() == str(informe or "").casefold():
        pagina = None
    return _titulo_compuesto(informe, pagina) or pagina, informe or pagina, pagina


def _candidatas(result: dict) -> list[tuple]:
    status, route = result.get("status"), result.get("route")
    if route == "rag" and status == "success":
        crudas = result.get("sources") or result.get("rag_sources") or []
        return [_fuente_documental(f) for f in crudas if isinstance(f, dict)]
    if route == "powerbi" and status in ("success", "empty_result"):
        return [_fuente_dato(result)]
    return []


def fuentes(result: dict) -> list[dict]:
    """Fuentes legibles y sin repetir (sin rutas de archivo internas)."""
    salida, vistos = [], set()
    for titulo, tablero, pagina in _candidatas(result):
        titulo = " ".join(str(titulo or "").split())
        clave = (titulo.casefold(), str(tablero or "").casefold(), str(pagina or "").casefold())
        if not titulo or clave in vistos or len(salida) >= MAX_FUENTES:
            continue
        vistos.add(clave)
        item = {"titulo": titulo, "tablero": tablero, "pagina": pagina}
        salida.append({k: str(v) for k, v in item.items() if v})
    return salida


def _filtros_tablero(result: dict) -> list[str]:
    filtros = ((result.get("query_plan") or {}).get("metric") or {}).get("visual_filters") or []
    return [f"{f.get('table')}[{f.get('column')}]: {f.get('text')}" for f in filtros if isinstance(f, dict)]


def detalles(result: dict) -> dict | None:
    """«Detalles de la consulta» de Streamlit (solo respuestas exitosas que no son charla)."""
    if result.get("status") != "success" or result.get("route") == "conversacion":
        return None
    datos = {
        "informe": result.get("report"),
        "tablero": result.get("dashboard"),
        "modelo_semantico": result.get("semantic_model"),
        "metrica": result.get("metric"),
        "filtros_tablero": _filtros_tablero(result),
        "sintesis": result.get("synthesis_mode"),
    }
    return {k: v for k, v in datos.items() if v not in (None, "", [])} or None


def _jsonable(valor):
    try:
        return json.loads(json.dumps(valor, ensure_ascii=False, default=str))
    except Exception:
        return str(valor)


def razonamiento_texto(result: dict, texto: str) -> str | None:
    from src.chatbot.reasoning_trace import format_reasoning_text

    return _seguro(format_reasoning_text, result.get("reasoning"), texto) or None


def diagnostico(result: dict, texto: str, tiempos: dict, cacheada: bool) -> dict:
    razonamiento = result.get("reasoning") or {}
    datos = {
        "razonamiento": razonamiento_texto(result, texto),
        "pasos": [
            {"titulo": p.get("title"), "lineas": list(p.get("lines") or []), "t": p.get("t")}
            for p in razonamiento.get("steps") or [] if isinstance(p, dict)
        ],
        "tiempos": tiempos,
        "estado": result.get("status"),
        "etapa": result.get("stage"),
        "detalles": result.get("details"),
        "error": result.get("error"),
        "dax": result.get("dax"),
        "plan_consulta": result.get("query_plan"),
        "contexto_fuentes": result.get("source_context"),
        "agrupaciones": result.get("group_by"),
        "dimensiones_detectadas": result.get("dimension_matches"),
        "filtros_negocio": result.get("business_filters"),
        "pregunta_normalizada": result.get("normalized_question"),
        "modo_sintesis": result.get("synthesis_mode"),
        "cacheada": cacheada,
        "estado_servidor": razonamiento.get("server_state"),
    }
    return _jsonable(datos)


def aviso_degradacion(result: dict) -> dict | None:
    from src.chatbot.progreso import aviso_degradacion as calcular

    try:
        return calcular(result)
    except Exception:
        return None


# ----------------------------------------------------------------------
# Payload completo
# ----------------------------------------------------------------------

def construir_respuesta(result: dict, formatter, turno_id: str) -> tuple[dict, list[dict], str]:
    """(payload `respuesta` sin `diagnostico`, opciones pendientes, texto)."""
    texto = texto_respuesta(result, formatter)
    pregunta, pendientes = contrapregunta(result)
    aviso = aviso_degradacion(result)
    if result.get("status") == "needs_clarification":
        ruta = "contrapregunta"
    else:
        ruta = RUTAS.get(str(result.get("route") or ""), "otra")
    respuesta = {
        "turno_id": turno_id,
        "texto_markdown": texto,
        "ruta": ruta,
        "estado": result.get("status"),
        "fuentes": fuentes(result),
        "enlaces_powerbi": enlaces_powerbi(result),
        "contrapregunta": pregunta,
        "detalles": _jsonable(detalles(result)),
        "degradada": bool(aviso) or bool(result.get("powerbi_unavailable")),
        "aviso": (aviso or {}).get("texto"),
        "cacheada": False,
        "diagnostico": None,
    }
    return respuesta, pendientes, texto
