"""Panel de calificación de respuestas (solo en modo diagnóstico)."""
import uuid

import streamlit as st

from src.feedback.registro import construir_registro, guardar


def _id_sesion() -> str:
    if not st.session_state.get("id_sesion"):
        st.session_state["id_sesion"] = uuid.uuid4().hex[:12]
    return st.session_state["id_sesion"]


def _historial_previo(indice: int, mensajes: list[dict]) -> list[dict]:
    """Mensajes anteriores al calificado, con las claves que espera el registro."""
    return [
        {"rol": m.get("role", ""), "texto": m.get("content", "")}
        for m in mensajes[:indice]
    ]


def _guardar(snapshot, mensajes, indice, id_sesion, id_turno, calificacion, esperado) -> None:
    """Guarda solo si difiere de lo ya guardado; un fallo se avisa y no se propaga."""
    clave = f"guardado_{id_turno}"
    estado = (calificacion, esperado)
    if st.session_state.get(clave) == estado:
        return
    try:
        registro = construir_registro(
            snapshot, _historial_previo(indice, mensajes), calificacion, esperado, id_sesion, indice)
        guardar(registro)
    except Exception as error:  # noqa: BLE001 - el chat nunca se rompe por el log
        st.warning(f"No se pudo guardar la calificación: {type(error).__name__}")
        return
    st.session_state[clave] = estado


def mostrar_calificacion(indice: int, mensajes: list[dict]) -> None:
    """👍/👎 para el mensaje `indice`; 👎 pide qué se esperaba antes de guardar."""
    if not (0 <= indice < len(mensajes)):
        return
    snapshot = mensajes[indice].get("snapshot")
    if not snapshot:
        return
    id_sesion = _id_sesion()
    id_turno = f"{id_sesion}:{indice}"
    pulgar = st.feedback("thumbs", key=f"cal_{id_sesion}_{indice}")
    if pulgar is None:
        return
    clave = f"guardado_{id_turno}"
    if pulgar == 1:
        _guardar(snapshot, mensajes, indice, id_sesion, id_turno, "buena", "")
        if st.session_state.get(clave) == ("buena", ""):
            st.caption("Guardado ✔")
        return
    esperado = st.text_area(
        "¿Qué esperabas que respondiera? (no incluyas datos de pacientes)",
        key=f"esperado_{id_turno}",
    ).strip()
    if st.button("Guardar", key=f"guardar_{id_turno}"):
        if not esperado:
            st.warning("Cuéntanos qué esperabas para poder guardar la calificación.")
        else:
            _guardar(snapshot, mensajes, indice, id_sesion, id_turno, "mala", esperado)
    if st.session_state.get(clave) == ("mala", esperado) and esperado:
        st.caption("Guardado ✔")
