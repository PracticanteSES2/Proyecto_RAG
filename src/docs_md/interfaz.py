"""
Página «Documentación» de la app Streamlit (ver, proponer, revisar y aprobar).

La página vive en `pages/1_Documentación.py` (multipágina por carpeta `pages/`:
app.py sigue siendo el chat y no cambia). Este módulo tiene la lógica y el
dibujo para poder probarlos con AppTest.

Servicios (contratos de README.md):
- actualizador.proponer_cambio / actualizador.aplicar_propuesta
- indexacion.reindexar_grupo

Para pruebas se pueden reemplazar por otro módulo con las mismas tres
funciones: variable de entorno DOCS_MD_SERVICIOS=<modulo> (p. ej.
tests.docs_md.fakes_interfaz) o el parámetro `servicios` de `pagina()`.
"""

from __future__ import annotations

import difflib
import html
import importlib
import os
import sys
import time
import traceback
from dataclasses import dataclass, replace
from typing import Callable

import streamlit as st

from . import repositorio
from .formato import (
    SECCION_HISTORIAL,
    SECCION_TEXTO,
    Documento,
    ErrorFormato,
    ErrorOperacion,
    Operacion,
    aplicar_operaciones,
    diferencias,
    parsear,
    secciones_para,
    serializar,
    validar,
)

MODO_VER = "📖 Ver documentación"
MODO_PROPONER = "✏️ Proponer un cambio"
AUTOMATICA = ""  # opción «Detectar automáticamente» del selector de página

ACCION_TEXTO = {
    "agregar": "Agregar",
    "modificar": "Cambiar",
    "eliminar": "Quitar",
}

COLOR_AGREGADA = "rgba(46, 160, 67, 0.20)"
COLOR_ELIMINADA = "rgba(248, 81, 73, 0.20)"


# ---------------------------------------------------------------------------
# Servicios (reales o simulados)
# ---------------------------------------------------------------------------

@dataclass
class Servicios:
    proponer_cambio: Callable
    aplicar_propuesta: Callable
    reindexar_grupo: Callable
    simulados: bool = False
    origen: str = "src.docs_md"


def cargar_servicios(nombre_modulo: str | None = None) -> Servicios:
    """Servicios reales, o los del módulo indicado (DOCS_MD_SERVICIOS) para pruebas."""
    nombre = (nombre_modulo or os.getenv("DOCS_MD_SERVICIOS", "")).strip()
    if nombre:
        modulo = importlib.import_module(nombre)
        return Servicios(modulo.proponer_cambio, modulo.aplicar_propuesta, modulo.reindexar_grupo,
                         simulados=True, origen=nombre)
    from . import actualizador, indexacion
    return Servicios(actualizador.proponer_cambio, actualizador.aplicar_propuesta,
                     indexacion.reindexar_grupo)


def retriever_del_chat():
    """Retriever que el chat ya tiene abierto en este proceso, o None.

    No importa src.rag.retriever si nadie lo ha cargado (sería lento y, si el
    chat no está abierto, no hay cliente que reutilizar)."""
    modulo = sys.modules.get("src.rag.retriever")
    obtener = getattr(modulo, "retriever_abierto", None)
    if not callable(obtener):
        return None
    try:
        return obtener()
    except Exception:
        return None


def reindexar(servicios: Servicios, source_group: str) -> dict:
    """Reindexa el tablero reutilizando el cliente de Qdrant del chat si existe.
    Devuelve el resultado de reindexar_grupo más `cliente_compartido`."""
    retriever = retriever_del_chat()
    cliente = getattr(retriever, "client", None) if retriever is not None else None
    resultado = dict(servicios.reindexar_grupo(source_group, qdrant_client=cliente) or {})
    resultado["cliente_compartido"] = cliente is not None
    if retriever is not None:
        # El chat guarda en memoria textos y metadatos de los chunks: se recargan.
        refrescar = getattr(retriever, "refresh_metadata", None)
        if callable(refrescar):
            try:
                refrescar()
            except Exception as exc:
                resultado.setdefault("errores", [])
                resultado["errores"] = list(resultado["errores"]) + [
                    f"El chat no pudo recargar los textos actualizados: {exc}"]
    return resultado


# ---------------------------------------------------------------------------
# Lógica pura (sin Streamlit)
# ---------------------------------------------------------------------------

def etiqueta_pagina(item: dict) -> str:
    """«CONSULTAS DIA — Oportunidad ... · Día» (y aviso si el formato falla)."""
    if item.get("archivo") == repositorio.ARCHIVO_GENERAL:
        nombre = "General del tablero"
    else:
        nombre = item.get("pagina") or item.get("archivo", "")
    detalle = item.get("nombre_funcional") or ""
    texto = f"{nombre} — {detalle}" if detalle else nombre
    if item.get("bloque") and item.get("bloque") != "General":
        texto += f" · {item['bloque']}"
    if not item.get("valido", True):
        texto = "⚠️ " + texto
    return texto


def _celda(valor) -> str:
    if isinstance(valor, (list, tuple)):
        valor = ", ".join(str(v) for v in valor)
    return str(valor if valor not in (None, "") else "—").replace("|", "\\|")


def ficha_markdown(doc: Documento) -> str:
    """Metadatos como ficha legible (en lugar del bloque YAML)."""
    filas = [
        ("Tablero", doc.meta.get("tablero")),
        ("Página", doc.pagina),
        ("Nombre funcional", doc.meta.get("nombre_funcional")),
        ("Bloque", doc.meta.get("bloque")),
        ("Tablas", doc.meta.get("tablas")),
        ("Versión", doc.meta.get("version")),
        ("Última actualización", doc.meta.get("actualizado")),
    ]
    lineas = ["| Dato | Valor |", "|---|---|"]
    lineas += [f"| {nombre} | {_celda(valor)} |" for nombre, valor in filas]
    return "\n".join(lineas)


def cuerpo_markdown(doc: Documento) -> str:
    """Contenido de la página sin metadatos ni historial."""
    partes = [f"#### {SECCION_TEXTO}", doc.proposito.strip() or "_(vacío)_"]
    orden = secciones_para(doc.meta)
    for seccion in orden + [s for s in doc.secciones if s not in orden]:
        if seccion in (SECCION_TEXTO, SECCION_HISTORIAL):
            continue
        entradas = doc.entradas(seccion)
        if not entradas:
            continue
        partes.append(f"#### {seccion}")
        partes.append("\n".join(f"- **{e.nombre}**: {e.texto}" for e in entradas))
    return "\n\n".join(partes)


def historial_markdown(doc: Documento) -> str:
    """Historial de cambios, el más reciente primero."""
    entradas = list(reversed(doc.entradas(SECCION_HISTORIAL)))
    if not entradas:
        return "_Sin cambios registrados._"
    return "\n".join(f"- **{e.nombre}**: {e.texto}" for e in entradas)


def describir_operacion(op: Operacion) -> str:
    """Frase clara para una operación («Cambiar la entrada «X» de Reglas de negocio»)."""
    if op.seccion.strip().casefold() == SECCION_TEXTO.casefold():
        return "Reescribir el **Propósito** de la página"
    verbo = ACCION_TEXTO.get(op.accion, op.accion.capitalize() or "¿?")
    preposicion = "en" if op.accion == "agregar" else "de"
    return f"{verbo} la entrada **«{op.entrada}»** {preposicion} **{op.seccion}**"


def texto_actual(antes: str, op: Operacion) -> str | None:
    """Texto que tiene hoy la entrada que la operación toca (None si no existe)."""
    try:
        doc = parsear(antes)
    except ErrorFormato:
        return None
    if op.seccion.strip().casefold() == SECCION_TEXTO.casefold():
        return doc.proposito
    for seccion in doc.secciones:
        if seccion.casefold() == op.seccion.strip().casefold():
            entrada = doc.buscar(seccion, op.entrada)
            return entrada.texto if entrada else None
    return None


def reaplicar(propuesta, operaciones: list[Operacion]):
    """Vuelve a aplicar operaciones (editadas a mano) sobre el texto «antes» de
    la propuesta y devuelve una propuesta nueva con el texto, el diff y la
    validación al día. Lanza ErrorOperacion / ErrorFormato si no aplican."""
    doc = parsear(propuesta.antes)
    nuevo = aplicar_operaciones(doc, operaciones, propuesta.resumen)
    errores = validar(nuevo)
    if errores:
        raise ErrorOperacion("El resultado no cumple el formato: " + " ".join(errores))
    despues = serializar(nuevo)
    nombre = repositorio.archivo_para(doc)
    return replace(propuesta, operaciones=operaciones, despues=despues,
                   diff=diferencias(propuesta.antes, despues, nombre), errores=[])


def diff_html(antes: str, despues: str, contexto: int = 1) -> str:
    """Diff legible: solo los tramos cambiados, con líneas eliminadas en rojo
    y agregadas en verde."""
    a = antes.replace("\r\n", "\n").splitlines()
    b = despues.replace("\r\n", "\n").splitlines()
    grupos = list(difflib.SequenceMatcher(None, a, b, autojunk=False).get_grouped_opcodes(contexto))
    if not grupos:
        return "<p><em>No hay diferencias.</em></p>"

    def linea(signo, texto, fondo=None):
        estilo = "white-space:pre-wrap;font-family:monospace;font-size:0.85rem;padding:1px 6px;"
        if fondo:
            estilo += f"background:{fondo};"
        else:
            estilo += "opacity:0.65;"
        return f'<div style="{estilo}">{signo} {html.escape(texto) or "&nbsp;"}</div>'

    bloques = []
    for grupo in grupos:
        filas = []
        for tag, i1, i2, j1, j2 in grupo:
            if tag == "equal":
                filas += [linea("&nbsp;", t) for t in a[i1:i2]]
                continue
            if tag in ("replace", "delete"):
                filas += [linea("−", t, COLOR_ELIMINADA) for t in a[i1:i2]]
            if tag in ("replace", "insert"):
                filas += [linea("+", t, COLOR_AGREGADA) for t in b[j1:j2]]
        bloques.append("".join(filas))
    separador = '<div style="text-align:center;opacity:0.5;">⋯</div>'
    return ('<div style="border:1px solid rgba(128,128,128,0.35);border-radius:6px;padding:4px 0;">'
            + separador.join(bloques) + "</div>")


def lineas_cambiadas(antes: str, despues: str) -> tuple[int, int]:
    """(agregadas, eliminadas)."""
    agregadas = eliminadas = 0
    for linea in difflib.unified_diff(antes.splitlines(), despues.splitlines(), lineterm="", n=0):
        if linea.startswith("+") and not linea.startswith("+++"):
            agregadas += 1
        elif linea.startswith("-") and not linea.startswith("---"):
            eliminadas += 1
    return agregadas, eliminadas


def metodo_pagina_texto(propuesta) -> str:
    """Cómo se eligió la página, en palabras sencillas (vacío si no se sabe)."""
    metodo = getattr(propuesta, "metodo_pagina", "") or ""
    if metodo == "indicada":
        return "la elegiste tú en el formulario"
    if metodo == "reglas":
        return "la nota la nombra o usa palabras que solo están en esa página"
    if metodo == "medgemma":
        otras = [c for c in (getattr(propuesta, "candidatas", None) or []) if c != propuesta.pagina]
        if otras:
            return "MedGemma la eligió entre varias parecidas (también: " + ", ".join(otras[:4]) + ")"
        return "MedGemma la eligió entre varias parecidas"
    return ""


def tiempos_texto(segundos, tiempos_llm) -> str:
    """«preparada en 9.8 s · 2 llamadas a MedGemma (4.1 s + 5.2 s)»."""
    partes = []
    if segundos is not None:
        partes.append(f"preparada en {float(segundos):.1f} s")
    tiempos = [float(t) for t in (tiempos_llm or [])]
    if tiempos:
        llamadas = "1 llamada" if len(tiempos) == 1 else f"{len(tiempos)} llamadas"
        detalle = " + ".join(f"{t:.1f} s" for t in tiempos)
        partes.append(f"{llamadas} a MedGemma ({detalle})")
    return " · ".join(partes)


def mensaje_error(exc: BaseException, que: str) -> str:
    if isinstance(exc, NotImplementedError):
        return f"{que}: esta función todavía no está disponible en esta versión ({exc})."
    return f"{que}: {exc}"


# ---------------------------------------------------------------------------
# Estado de la sesión
# ---------------------------------------------------------------------------

def _estado_inicial():
    valores = {
        "docs_modo": MODO_VER,
        "docs_propuesta": None,      # Propuesta vigente
        "docs_propuesta_n": 0,       # contador para las claves de los widgets de la propuesta
        "docs_segundos": None,       # tiempo que tardó la última propuesta
        "docs_aviso": None,          # (tipo, texto, detalle) para mostrar una vez
        "docs_aprobado": None,       # resultado de la última aprobación
    }
    for clave, valor in valores.items():
        st.session_state.setdefault(clave, valor)
    # Streamlit borra el estado de los widgets que no se dibujan en un pase;
    # así el borrador del formulario sobrevive al cambiar de modo.
    for clave in ("docs_nota", "docs_autor", "docs_pagina_prop", "docs_pbip"):
        if clave in st.session_state:
            st.session_state[clave] = st.session_state[clave]


def _nueva_propuesta(propuesta, segundos=None):
    st.session_state.docs_propuesta = propuesta
    st.session_state.docs_propuesta_n += 1
    st.session_state.docs_segundos = segundos


def _ir_a_proponer(pagina):
    # Callback del botón «Proponer un cambio en esta página».
    st.session_state.docs_modo = MODO_PROPONER
    st.session_state.docs_pagina_prop = pagina


def _spinner(texto):
    try:
        return st.spinner(texto, show_time=True)
    except TypeError:  # Streamlit sin show_time
        return st.spinner(texto)


# ---------------------------------------------------------------------------
# Pantallas
# ---------------------------------------------------------------------------

def _mostrar_documento(doc: Documento, errores: list[str]):
    if errores:
        st.error("**Formato con problemas.** La página se muestra, pero conviene corregirla:\n\n"
                 + "\n".join(f"- {e}" for e in errores))
    else:
        st.success("✅ Formato válido")
    columna_texto, columna_ficha = st.columns([3, 2])
    with columna_ficha:
        st.markdown("##### Ficha de la página")
        st.markdown(ficha_markdown(doc))
    with columna_texto:
        st.markdown(f"### {doc.pagina}")
        st.markdown(cuerpo_markdown(doc))
    st.markdown("#### 🕓 Historial de cambios")
    st.markdown(historial_markdown(doc))


def pantalla_ver(source_group: str, paginas: list[dict]):
    if not paginas:
        st.info("Este tablero todavía no tiene páginas documentadas.")
        return
    por_archivo = {p["archivo"]: p for p in paginas}
    archivo = st.selectbox(
        "Página",
        options=list(por_archivo),
        format_func=lambda a: etiqueta_pagina(por_archivo[a]),
        key="docs_pagina_ver",
    )
    item = por_archivo[archivo]
    ruta = repositorio.carpeta_md(source_group) / archivo
    try:
        texto = ruta.read_text(encoding="utf-8")
    except OSError as exc:
        st.error(f"No se pudo leer el archivo {archivo}: {exc}")
        return
    try:
        doc = parsear(texto)
    except ErrorFormato as exc:
        st.error(f"**Formato con problemas.** No se pudo interpretar la página: {exc}")
        with st.expander("Texto del archivo"):
            st.code(texto, language="markdown")
        return

    st.button("✏️ Proponer un cambio en esta página", on_click=_ir_a_proponer, args=(doc.pagina,))
    _mostrar_documento(doc, validar(doc))
    with st.expander("Ver el archivo .md tal como está guardado"):
        st.caption(f"{source_group}/md/{item['archivo']}")
        st.code(texto, language="markdown")


def _formulario(source_group: str, paginas: list[dict], servicios: Servicios):
    opciones = [AUTOMATICA] + [p["pagina"] for p in paginas]
    etiquetas = {p["pagina"]: etiqueta_pagina(p) for p in paginas}
    etiquetas[AUTOMATICA] = "🔎 Detectar automáticamente"
    if st.session_state.get("docs_pagina_prop") not in opciones:
        st.session_state.docs_pagina_prop = AUTOMATICA

    with st.form("docs_formulario"):
        st.markdown("Escribe con tus palabras qué cambió en el tablero. "
                    "MedGemma propone el cambio exacto en la documentación y **nada se guarda hasta que lo apruebes**.")
        nota = st.text_area(
            "¿Qué cambió?",
            key="docs_nota",
            placeholder="Ej.: le subí el verde del semáforo de triage II a 20 minutos",
            height=110,
        )
        columna_autor, columna_pagina = st.columns(2)
        with columna_autor:
            autor = st.text_input("Tu nombre", key="docs_autor", placeholder="Quién hizo el cambio")
        with columna_pagina:
            pagina = st.selectbox("Página", options=opciones, format_func=lambda p: etiquetas.get(p, p),
                                  key="docs_pagina_prop")
        with st.expander("Cambios detectados en el PBIP (opcional)"):
            pbip = st.text_area(
                "Un cambio por línea",
                key="docs_pbip",
                placeholder="Página CONSULTAS DIA: se cambió el semáforo de la tabla de atendidos de triage II.",
                height=90,
            )
        enviado = st.form_submit_button("Generar propuesta", type="primary")

    if not enviado:
        return
    faltan = []
    if not (nota or "").strip():
        faltan.append("escribe qué cambió")
    if not (autor or "").strip():
        faltan.append("escribe tu nombre")
    if faltan:
        st.warning("Para generar la propuesta, " + " y ".join(faltan) + ".")
        return
    cambios = [linea.strip() for linea in (pbip or "").splitlines() if linea.strip()] or None
    _proponer(servicios, nota.strip(), source_group, pagina or None, cambios)


def _proponer(servicios: Servicios, nota, source_group, pagina, cambios_pbip=None):
    from .actualizador import Propuesta

    st.session_state.docs_aprobado = None
    inicio = time.monotonic()
    with _spinner("MedGemma está preparando la propuesta… puede tardar unos segundos."):
        try:
            propuesta = servicios.proponer_cambio(nota, source_group, pagina=pagina, cambios_pbip=cambios_pbip)
        except Exception as exc:
            propuesta = Propuesta(nota=nota, source_group=source_group, pagina=pagina or "", estado="error",
                                  errores=[mensaje_error(exc, "No se pudo preparar la propuesta")],
                                  llm_raw=traceback.format_exc())
    _nueva_propuesta(propuesta, time.monotonic() - inicio)
    st.rerun()


def _revisar_lista(propuesta, servicios: Servicios, n: int):
    st.markdown("##### Cambios propuestos")
    editadas = []
    pendientes = False
    for i, op in enumerate(propuesta.operaciones):
        with st.container(border=True):
            st.markdown(f"**{i + 1}.** {describir_operacion(op)}")
            actual = texto_actual(propuesta.antes, op)
            if op.accion in ("modificar", "eliminar") and actual:
                st.caption("Texto actual")
                st.markdown(f"> {actual}")
            if op.accion == "eliminar":
                editadas.append(op)
                continue
            texto = st.text_area(
                "Texto nuevo (puedes corregirlo antes de aprobar)",
                value=op.texto,
                key=f"docs_op_{n}_{i}",
                height=120 if op.seccion.strip().casefold() == SECCION_TEXTO.casefold() else 80,
            )
            if texto.strip() != op.texto.strip():
                pendientes = True
            editadas.append(replace(op, texto=texto.strip()))

    if pendientes:
        st.info("Corregiste el texto de una operación. Pulsa «Actualizar vista previa» para ver el resultado; "
                "solo entonces se puede aprobar.")
        if st.button("🔄 Actualizar vista previa", key=f"docs_reaplicar_{n}"):
            try:
                nueva = reaplicar(propuesta, editadas)
            except (ErrorOperacion, ErrorFormato) as exc:
                st.error(f"No se pudo aplicar tu corrección: {exc}")
            else:
                # Misma propuesta con las operaciones corregidas; las claves de los
                # widgets cambian para que muestren los textos nuevos.
                _nueva_propuesta(nueva, st.session_state.docs_segundos)
                st.session_state.docs_aviso = ("success", "Vista previa actualizada con tu corrección.", None)
                st.rerun()

    _mostrar_avisos(propuesta)
    _mostrar_diff(propuesta)

    errores_resultado = validar(propuesta.despues) if propuesta.despues else ["La propuesta no trae el texto nuevo."]
    if errores_resultado:
        st.error("El resultado no cumple el formato:\n\n" + "\n".join(f"- {e}" for e in errores_resultado))
    else:
        st.success("✅ El resultado cumple el formato")

    autor = st.text_input("Aprueba", key=f"docs_autor_aprueba_{n}",
                          value=st.session_state.get("docs_autor") or "")
    columna_aprobar, columna_rechazar = st.columns(2)
    with columna_aprobar:
        aprobar = st.button("✅ Aprobar y guardar", type="primary", key=f"docs_aprobar_{n}",
                            disabled=pendientes or bool(errores_resultado), use_container_width=True)
    with columna_rechazar:
        rechazar = st.button("❌ Rechazar", key=f"docs_rechazar_{n}", use_container_width=True)

    if rechazar:
        st.session_state.docs_propuesta = None
        st.session_state.docs_aviso = ("info", "Propuesta descartada. La documentación no cambió.", None)
        st.rerun()
    if aprobar:
        if not autor.strip():
            st.warning("Escribe quién aprueba el cambio.")
            return
        _aprobar(propuesta, autor.strip(), servicios)


def _mostrar_avisos(propuesta):
    """Avisos del actualizador (cifras que no vienen de la nota, cláusulas
    perdidas, entradas relacionadas sin tocar...): la red de seguridad para
    los errores de sentido de MedGemma, junto al diff."""
    avisos = list(getattr(propuesta, "avisos", None) or [])
    if not avisos:
        return
    st.warning(f"**⚠️ Revisa esto antes de aprobar ({len(avisos)})**\n\n"
               + "\n".join(f"- {a}" for a in avisos))


def _mostrar_diff(propuesta):
    agregadas, eliminadas = lineas_cambiadas(propuesta.antes, propuesta.despues)
    st.markdown("##### Antes y después")
    st.caption(f"🟥 líneas que salen ({eliminadas}) · 🟩 líneas que entran ({agregadas}). "
               "La versión y el historial los actualiza el sistema.")
    st.markdown(diff_html(propuesta.antes, propuesta.despues), unsafe_allow_html=True)
    with st.expander("Ver la página como quedaría"):
        try:
            doc = parsear(propuesta.despues)
            st.markdown(cuerpo_markdown(doc))
            st.markdown("**Historial de cambios**")
            st.markdown(historial_markdown(doc))
        except ErrorFormato as exc:
            st.error(f"No se pudo interpretar el texto propuesto: {exc}")
    with st.expander("Diff unificado (técnico)"):
        st.code(propuesta.diff or diferencias(propuesta.antes, propuesta.despues), language="diff")


def _aprobar(propuesta, autor: str, servicios: Servicios):
    try:
        with _spinner("Guardando el cambio…"):
            ruta = servicios.aplicar_propuesta(propuesta, autor)
    except Exception as exc:
        st.session_state.docs_aviso = ("error", mensaje_error(exc, "No se guardó el cambio"),
                                       traceback.format_exc())
        st.rerun()
        return

    version = None
    try:
        version = repositorio.leer_pagina(propuesta.source_group, propuesta.pagina).meta.get("version")
    except Exception:
        pass
    st.session_state.docs_aprobado = {
        "source_group": propuesta.source_group,
        "pagina": propuesta.pagina,
        "version": version,
        "ruta": str(ruta) if ruta else "",
        "reindexacion": None,
        "error_reindexacion": None,
        "detalle": None,
    }
    st.session_state.docs_propuesta = None
    _reindexar_aprobado(servicios)
    st.rerun()


def _reindexar_aprobado(servicios: Servicios):
    aprobado = st.session_state.docs_aprobado
    try:
        with _spinner("Actualizando el buscador del asistente (reindexación del tablero)…"):
            resultado = reindexar(servicios, aprobado["source_group"])
    except Exception as exc:
        aprobado["error_reindexacion"] = mensaje_error(exc, "La reindexación falló")
        aprobado["detalle"] = traceback.format_exc()
        aprobado["reindexacion"] = None
    else:
        aprobado["reindexacion"] = resultado
        aprobado["error_reindexacion"] = None
        aprobado["detalle"] = None


def _mostrar_aprobado(servicios: Servicios, tableros: dict):
    aprobado = st.session_state.docs_aprobado
    if not aprobado:
        return
    version = f"versión {aprobado['version']}" if aprobado.get("version") is not None else "una versión nueva"
    st.success(f"✅ Cambio aprobado. La página **{aprobado['pagina']}** quedó guardada en la **{version}**.")
    resultado = aprobado.get("reindexacion")
    if aprobado.get("error_reindexacion"):
        st.warning("El cambio **sí quedó guardado**, pero el asistente del chat todavía no lo conoce porque "
                   f"la reindexación falló. {aprobado['error_reindexacion']}")
        if aprobado.get("detalle"):
            with st.expander("Detalle técnico"):
                st.code(aprobado["detalle"], language="text")
        if st.button("🔁 Reintentar la reindexación", key="docs_reintentar_reindex"):
            _reindexar_aprobado(servicios)
            st.rerun()
    elif resultado is not None:
        tablero = tableros.get(aprobado["source_group"], aprobado["source_group"])
        partes = []
        if resultado.get("documentos") is not None:
            partes.append(f"{resultado['documentos']} documentos")
        if resultado.get("chunks") is not None:
            partes.append(f"{resultado['chunks']} fragmentos")
        if resultado.get("segundos") is not None:
            partes.append(f"{float(resultado['segundos']):.1f} s")
        conexion = ("con la conexión del chat" if resultado.get("cliente_compartido")
                    else "con una conexión propia (el chat no estaba abierto)")
        detalle = f" ({', '.join(partes)})" if partes else ""
        st.info(f"🔎 El asistente ya usa el texto nuevo: se reindexó **{tablero}**{detalle} {conexion}.")
        if resultado.get("errores"):
            st.warning("Avisos de la reindexación:\n\n" + "\n".join(f"- {e}" for e in resultado["errores"]))


def _revisar(propuesta, servicios: Servicios, paginas: list[dict]):
    n = st.session_state.docs_propuesta_n
    st.divider()
    st.markdown("### Revisión de la propuesta")
    tiempos = tiempos_texto(st.session_state.docs_segundos, getattr(propuesta, "tiempos_llm", None))
    st.caption(f"Nota: «{propuesta.nota}»" + (f" · {tiempos}" if tiempos else ""))

    if propuesta.estado == "lista":
        nombre_funcional = next((p.get("nombre_funcional") for p in paginas
                                 if p["pagina"] == propuesta.pagina), "")
        st.markdown(f"**Página:** {propuesta.pagina}" + (f" — {nombre_funcional}" if nombre_funcional else ""))
        como = metodo_pagina_texto(propuesta)
        if como:
            st.caption(f"🔎 Cómo se eligió la página: {como}.")
        if propuesta.resumen:
            st.markdown(f"**Resumen:** {propuesta.resumen}")
        if propuesta.dudas:
            st.warning("MedGemma dejó estas dudas; revísalas antes de aprobar:\n\n"
                       + "\n".join(f"- {d}" for d in propuesta.dudas))
        _revisar_lista(propuesta, servicios, n)
    elif propuesta.estado == "requiere_aclaracion":
        _aclarar(propuesta, servicios, paginas, n)
    else:
        _mostrar_error_propuesta(propuesta)


def _aclarar(propuesta, servicios: Servicios, paginas: list[dict], n: int):
    st.warning("**Hace falta una aclaración.** MedGemma no quiso adivinar:\n\n"
               + "\n".join(f"- {d}" for d in (propuesta.dudas or ["La nota es ambigua."])))
    if getattr(propuesta, "avisos", None):
        st.info("Además:\n\n" + "\n".join(f"- {a}" for a in propuesta.avisos))
    nombres = [p["pagina"] for p in paginas]
    candidatas = [c for c in propuesta.candidatas if c in nombres] or nombres
    etiquetas = {p["pagina"]: etiqueta_pagina(p) for p in paginas}
    opciones = [AUTOMATICA] + candidatas
    pagina = st.radio(
        "¿En qué página va el cambio?" if propuesta.candidatas else "Elige la página (opcional)",
        options=opciones,
        format_func=lambda p: etiquetas.get(p, p) if p else "Que MedGemma la detecte",
        index=1 if propuesta.candidatas and candidatas else 0,
        key=f"docs_aclara_pagina_{n}",
    )
    nota = st.text_area("Puedes precisar la nota", value=propuesta.nota, key=f"docs_aclara_nota_{n}")
    columna_reintentar, columna_descartar = st.columns(2)
    with columna_reintentar:
        reintentar = st.button("Reintentar", type="primary", key=f"docs_aclara_reintentar_{n}",
                               use_container_width=True)
    with columna_descartar:
        descartar = st.button("Descartar", key=f"docs_aclara_descartar_{n}", use_container_width=True)
    if descartar:
        st.session_state.docs_propuesta = None
        st.rerun()
    if reintentar:
        if not nota.strip():
            st.warning("La nota no puede quedar vacía.")
            return
        _proponer(servicios, nota.strip(), propuesta.source_group, pagina or None)


def _mostrar_error_propuesta(propuesta):
    errores = propuesta.errores or ["No se obtuvo una propuesta válida."]
    st.error("**No se pudo preparar la propuesta.** " + " ".join(errores)
             + "\n\nPuedes ajustar la nota (o elegir la página) en el formulario y volver a intentarlo.")
    with st.expander("Detalle técnico"):
        if propuesta.pagina:
            st.markdown(f"Página: `{propuesta.pagina}`")
        if propuesta.operaciones:
            st.json([op.a_dict() for op in propuesta.operaciones])
        st.code(propuesta.llm_raw or "(sin respuesta del modelo)", language="text")


def pantalla_proponer(source_group: str, paginas: list[dict], servicios: Servicios, tableros: dict):
    _mostrar_aprobado(servicios, tableros)
    _formulario(source_group, paginas, servicios)
    propuesta = st.session_state.docs_propuesta
    if propuesta is not None and propuesta.source_group == source_group:
        _revisar(propuesta, servicios, paginas)


def _mostrar_aviso():
    aviso = st.session_state.docs_aviso
    if not aviso:
        return
    st.session_state.docs_aviso = None
    tipo, texto, detalle = aviso
    getattr(st, tipo, st.info)(texto)
    if detalle:
        with st.expander("Detalle técnico"):
            st.code(detalle, language="text")


def pagina(servicios: Servicios | None = None):
    """Dibuja la página completa de Documentación."""
    _estado_inicial()
    try:
        servicios = servicios or cargar_servicios()
    except Exception as exc:
        st.error(f"No se pudieron cargar los servicios de documentación: {exc}")
        return

    st.title("📚 Documentación de tableros")
    st.caption("Consulta la documentación de cada página y propone cambios en lenguaje sencillo. "
               "Un cambio solo se guarda cuando lo apruebas.")
    with st.sidebar:
        if servicios.simulados:
            st.warning(f"🧪 Modo de prueba: servicios simulados ({servicios.origen}).")
        st.caption("Documentación viva: una página .md por página del tablero; "
                   "el chat la consulta después de cada aprobación.")

    tableros = repositorio.listar_tableros()
    if not tableros:
        st.info("Todavía no hay tableros con documentación. Cada tablero guarda sus páginas en "
                f"`{repositorio.raiz_documentos()}/<grupo>/md/`.")
        return
    nombres = {t["source_group"]: t["tablero"] for t in tableros}
    if st.session_state.get("docs_tablero") not in nombres:
        st.session_state.docs_tablero = tableros[0]["source_group"]
    source_group = st.selectbox(
        "Tablero",
        options=list(nombres),
        format_func=lambda g: f"{nombres[g]} ({next(t['paginas'] for t in tableros if t['source_group'] == g)} páginas)",
        key="docs_tablero",
    )
    modo = st.radio("¿Qué quieres hacer?", [MODO_VER, MODO_PROPONER], horizontal=True,
                    key="docs_modo", label_visibility="collapsed")
    _mostrar_aviso()
    paginas = repositorio.listar_paginas(source_group)
    if modo == MODO_VER:
        pantalla_ver(source_group, paginas)
    else:
        pantalla_proponer(source_group, paginas, servicios, nombres)
