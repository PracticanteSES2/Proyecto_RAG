"""Respuestas del LLM truncadas por `num_predict` (done_reason="length").

Cuando `MedGemmaProvider.chat` devuelve `truncated=True`:

1. `cortar_en_limite_seguro(texto)`: se corta en el último límite seguro (frase
   completa, fila de tabla Markdown completa o ítem de lista completo; «Dr.»,
   «p. ej.» y los decimales no son fin de frase) y se cierran los bloques
   Markdown abiertos (código, negrita, código en línea). Se quitan encabezados,
   introducciones «…:» y tablas sin filas de datos que queden colgando al final.
2. `decidir_continuacion(...)`: UNA llamada de continuación solo si el
   presupuesto de tiempo alcanza (según la velocidad medida en la propia
   llamada) y MedGemma no tiene fila, ni está lleno, ni se saturó en el último
   minuto (`STATS.llm_pressure()`). `RAG_CONTINUAR_TRUNCADA=0` la apaga.
3. Si no se completa, quien muestra la respuesta añade `linea_aviso(enlace)`
   («La respuesta completa está en el tablero», con el enlace de Power BI si
   existe) y la marca `cacheable=False`: nunca se guarda en caché una respuesta
   incompleta.

Streaming (`on_token`): el borrador que se pinta mientras llega es provisional;
la respuesta FINAL (reparada, anclada y con aviso) reemplaza al borrador entero.
"""
import os
import re

from src.chatbot.runtime_stats import STATS
from src.llm import presupuesto_tokens as P

AVISO_TABLERO = "La respuesta completa está en el tablero"
CONTINUAR_PROMPT = (
    "Tu respuesta anterior quedó incompleta. Continúa exactamente donde quedó, sin repetir nada de lo "
    "ya escrito ni añadir preámbulos, y termínala en como máximo unas {palabras} palabras."
)

_FENCE_RE = re.compile(r"^\s*(?:```|~~~)")
_TABLA_RE = re.compile(r"^\s*\|")
_SEPARADOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}")
_ITEM_RE = re.compile(r"^\s*(?:[-*+•]|\d{1,2}[.)])\s+")
_ENCABEZADO_RE = re.compile(r"^\s*#{1,6}\s")
_CIERRES = ")]\"'»”*_`"
_INICIO_FRASE_RE = re.compile(r"[A-ZÁÉÍÓÚÑÜ0-9¿¡«\"(\[*`_\-•]")
# Abreviaturas que terminan en punto sin cerrar la frase («Dr.», «p. ej.»).
_ABREVIATURAS = {
    "dr", "dra", "drs", "sr", "sra", "srs", "sres", "srta", "ud", "uds", "ej", "pág", "pag", "núm",
    "num", "art", "aprox", "vs", "lic", "ing", "máx", "mín", "max", "min", "fig", "tel", "av", "cap",
    "cf", "vol", "dpto", "depto", "cía", "aux", "enf",
}


# ----------------------------------------------------------------------
# Corte en el último límite seguro
# ----------------------------------------------------------------------

def _es_fin_de_frase(texto, punto, fin):
    """¿El signo en `punto` (cuyos cierres acaban en `fin`) cierra una frase?"""
    if texto[punto] == ".":
        palabra = re.search(r"(\w+)$", texto[:punto])
        if palabra and (palabra.group(1).lower() in _ABREVIATURAS
                        or (len(palabra.group(1)) == 1 and palabra.group(1).isalpha())):
            return False
        if fin == len(texto):
            # «3.» al final puede ser el comienzo de «3.5»: nunca una cifra a medias.
            return not texto[:punto].rstrip(_CIERRES)[-1:].isdigit()
    if fin == len(texto):
        return True
    if not texto[fin].isspace():
        return False
    siguiente = texto[fin:].lstrip()
    return not siguiente or bool(_INICIO_FRASE_RE.match(siguiente))


def _ultimo_fin_de_frase(texto):
    corte = None
    for signo in re.finditer(r"[.!?…]", texto):
        fin = signo.end()
        while fin < len(texto) and texto[fin] in _CIERRES:
            fin += 1
        if _es_fin_de_frase(texto, signo.start(), fin):
            corte = fin
    return corte


def _celdas(linea):
    return len(linea.strip().strip("|").split("|"))


def _bloque_tabla(lineas):
    """Líneas de la tabla con que terminan `lineas` (puede ser vacía)."""
    inicio = len(lineas)
    while inicio > 0 and _TABLA_RE.match(lineas[inicio - 1]):
        inicio -= 1
    return lineas[inicio:]


def _codigo_abierto(lineas):
    return sum(1 for linea in lineas if _FENCE_RE.match(linea)) % 2 == 1


def _reparar_linea(linea, previas):
    """La última línea, que quedó a medias: completa, cortada en su última
    frase completa, o None."""
    if _ENCABEZADO_RE.match(linea):
        return None
    if _TABLA_RE.match(linea):
        tabla = _bloque_tabla(previas)
        completa = tabla and linea.rstrip().endswith("|") and _celdas(linea) == _celdas(tabla[0])
        return linea.rstrip() if completa else None
    marcador = _ITEM_RE.match(linea)
    prefijo = marcador.group(0) if marcador else ""
    contenido = linea[len(prefijo):]
    corte = _ultimo_fin_de_frase(contenido)
    if corte is None or not contenido[:corte].strip(" *_`"):
        return None
    return prefijo + contenido[:corte].rstrip()


def _limpiar_cola(lineas):
    """Quita lo que queda colgando al final: líneas vacías, encabezados,
    introducciones «…:», tablas sin filas de datos y aperturas de código vacías."""
    while lineas:
        ultima = lineas[-1]
        if not ultima.strip() or _ENCABEZADO_RE.match(ultima):
            lineas.pop()
        elif _codigo_abierto(lineas):
            if not _FENCE_RE.match(ultima):
                return
            lineas.pop()
        elif _TABLA_RE.match(ultima):
            tabla = _bloque_tabla(lineas)
            if any(not _SEPARADOR_RE.match(fila) for fila in tabla[1:]):
                return
            del lineas[len(lineas) - len(tabla):]
        elif ultima.rstrip().endswith(":"):
            lineas.pop()
        else:
            return


def _cerrar_markdown(texto):
    fuera = []
    dentro = False
    for linea in texto.split("\n"):
        if _FENCE_RE.match(linea):
            dentro = not dentro
        elif not dentro:
            fuera.append(linea)
    if dentro:
        return texto + "\n```"
    plano = "\n".join(fuera)
    if plano.replace("```", "").count("`") % 2:
        texto += "`"
    if plano.count("**") % 2:
        texto += "**"
    return texto


def cortar_en_limite_seguro(texto: str) -> str:
    """Texto hasta el último límite seguro, con el Markdown cerrado ("" si no
    queda nada completo). Un texto que termina en salto de línea está completo
    hasta ahí."""
    texto = str(texto or "").replace("\r\n", "\n")
    lineas = texto.split("\n")
    parcial = None if texto.endswith("\n") else lineas.pop()
    if parcial is not None:
        if _codigo_abierto(lineas):
            if _FENCE_RE.match(parcial):
                lineas.append(parcial)   # era el cierre del bloque
        else:
            reparada = _reparar_linea(parcial, lineas)
            if reparada:
                lineas.append(reparada)
    _limpiar_cola(lineas)
    return _cerrar_markdown("\n".join(lineas).rstrip()) if lineas else ""


# ----------------------------------------------------------------------
# Continuación
# ----------------------------------------------------------------------

def _es_bloque(linea):
    return bool(_TABLA_RE.match(linea) or _ITEM_RE.match(linea) or _ENCABEZADO_RE.match(linea)
                or _FENCE_RE.match(linea))


def unir_continuacion(previo: str, continuacion: str) -> str:
    """Une la continuación sin repetir las líneas iniciales ya escritas
    (p. ej. la cabecera de una tabla) y con el separador que pide el bloque."""
    previas = previo.rstrip().split("\n")
    vistas = {linea.strip() for linea in previas if linea.strip()}
    nuevas = str(continuacion or "").strip("\n").split("\n")
    while nuevas and nuevas[0].strip() in vistas | {""}:
        nuevas.pop(0)
    if not nuevas:
        return previo.rstrip()
    separador = _separador(previas[-1], nuevas[0])
    resto = "\n".join(nuevas).rstrip()
    return previo.rstrip() + separador + (resto.lstrip() if separador == " " else resto)


def _separador(ultima, primera):
    """Frase que sigue el párrafo: espacio; bloque: línea nueva (en blanco antes
    de una tabla que sigue a un párrafo o de un encabezado)."""
    if not _es_bloque(primera):
        return " "
    if _ENCABEZADO_RE.match(primera) or (_TABLA_RE.match(primera) and not _TABLA_RE.match(ultima)):
        return "\n\n"
    return "\n"


def presion_llm():
    """Presión actual sobre MedGemma (STATS.llm_pressure: queue_state nunca lanza)."""
    return STATS.llm_pressure()


def decidir_continuacion(presion, transcurrido_s, presupuesto_s, tokens_generados, tokens_continuacion):
    """(continuar, motivo). Si hay fila, el servidor está lleno o se saturó en
    el último minuto, no se continúa; tampoco si el tiempo no alcanza."""
    if str(os.getenv("RAG_CONTINUAR_TRUNCADA", "1")).strip().lower() in ("0", "no", "false"):
        return False, "continuación desactivada (RAG_CONTINUAR_TRUNCADA=0)"
    ocupado = _motivo_presion(presion or {})
    if ocupado:
        return False, ocupado
    if not presupuesto_s or presupuesto_s <= 0:
        return True, "MedGemma libre y sin límite de tiempo"
    return _alcanza_el_tiempo(transcurrido_s, presupuesto_s, tokens_generados, tokens_continuacion)


def _motivo_presion(presion):
    """Por qué no conviene otra llamada ahora (fila, lleno, saturado) o None."""
    en_fila = int(presion.get("waiting") or 0)
    en_curso, capacidad = int(presion.get("in_flight") or 0), presion.get("capacity")
    if en_fila:
        return f"hay {en_fila} consulta(s) en fila para MedGemma"
    if capacidad and en_curso >= int(capacidad):
        return f"MedGemma ocupado ({en_curso}/{capacidad} en curso)"
    if presion.get("saturated_recent"):
        return "MedGemma se saturó en el último minuto"
    return None


def _alcanza_el_tiempo(transcurrido_s, presupuesto_s, tokens_generados, tokens_continuacion):
    """(continuar, motivo) según la velocidad medida en la primera llamada."""
    velocidad = (tokens_generados / transcurrido_s) if tokens_generados and transcurrido_s > 0 else None
    necesario = (tokens_continuacion / velocidad if velocidad else transcurrido_s) * 1.25 + 1.0
    restante = presupuesto_s - transcurrido_s
    if restante < necesario:
        return False, f"sin tiempo: quedan {restante:.0f} s y harían falta ~{necesario:.0f} s"
    return True, f"MedGemma libre y quedan {restante:.0f} s"


def _intentar_continuacion(cortado, mensajes, continuar, restante):
    """UNA llamada de continuación → (completa, resultado, motivo, texto):
    `completa` dice si la respuesta quedó entera; `texto` es la unión (cortada
    en límite seguro si la continuación también se truncó) o `cortado`."""
    salida = P.num_predict("continuacion")
    nuevos = list(mensajes) + [
        {"role": "assistant", "content": cortado},
        {"role": "user", "content": CONTINUAR_PROMPT.format(palabras=P.extension_pedida(salida))},
    ]
    if P.tokens_mensajes(nuevos) > P.entrada_maxima(salida):
        return False, {}, "la continuación no cabe en num_ctx", cortado
    resultado = continuar(nuevos, salida, restante) or {}
    if resultado.get("status") != "success" or not resultado.get("answer"):
        return False, resultado, f"la continuación falló ({resultado.get('status') or 'sin respuesta'})", cortado
    unido = unir_continuacion(cortado, resultado["answer"])
    if resultado.get("truncated"):
        return False, resultado, "la continuación también se cortó", cortar_en_limite_seguro(unido) or cortado
    return True, resultado, None, unido


def completar(resultado, mensajes, continuar, presupuesto_s=None, transcurrido_s=0.0, salida=None):
    """(texto, diagnóstico) a partir del dict del proveedor. `continuar(mensajes,
    max_tokens, timeout)` hace la llamada de continuación (por la puerta)."""
    texto = str(resultado.get("answer") or "")
    diag = {"truncada": bool(resultado.get("truncated")), "tokens_salida": resultado.get("eval_count"),
            "tokens_entrada": resultado.get("prompt_eval_count"), "reparacion": "ninguna",
            "incompleta": False, "motivo": None, "llamadas": 1}
    if not diag["truncada"]:
        return texto, diag
    cortado = cortar_en_limite_seguro(texto)
    ok, motivo = decidir_continuacion(presion_llm(), transcurrido_s, presupuesto_s,
                                      resultado.get("eval_count") or salida, P.num_predict("continuacion"))
    if not cortado:
        ok, motivo = False, "no quedó ninguna frase completa"
    if ok:
        restante = (presupuesto_s - transcurrido_s) if presupuesto_s and presupuesto_s > 0 else None
        completa, segundo, motivo_fallo, cortado = _intentar_continuacion(cortado, mensajes, continuar, restante)
        diag["llamadas"] += 1 if segundo else 0
        diag["tokens_continuacion"] = segundo.get("eval_count")
        if completa:
            diag.update(reparacion="continuacion", motivo=motivo)
            return cortado, diag
        motivo = motivo_fallo
    diag.update(reparacion="corte", incompleta=True, motivo=motivo)
    return cortado, diag


# ----------------------------------------------------------------------
# Aviso y diagnóstico
# ----------------------------------------------------------------------

def linea_aviso(enlace=None) -> str:
    """Línea discreta para una respuesta que no se pudo completar."""
    url = (enlace or {}).get("url") if isinstance(enlace, dict) else None
    return f"_{AVISO_TABLERO}: [Abrir en Power BI]({url})._" if url else f"_{AVISO_TABLERO}._"


def describir(diagnostico) -> str:
    """Línea de la traza: truncada sí/no, tokens, recorte de entrada y reparación."""
    d = diagnostico or {}
    reparacion = _REPARACIONES.get(d.get("reparacion"), d.get("reparacion") or "ninguna")
    motivo = f" ({d['motivo']})" if d.get("motivo") and d.get("truncada") else ""
    return (f"truncada: {'sí' if d.get('truncada') else 'no'} · {_texto_tokens(d)} · "
            f"entrada recortada: {_texto_recorte(d.get('recorte'))} · reparación: {reparacion}{motivo}")


_REPARACIONES = {
    "ninguna": "ninguna",
    "continuacion": "continuación (1 llamada extra)",
    "corte": "corte en el último límite seguro + línea del tablero",
}


def _texto_tokens(d):
    entrada = d.get("tokens_entrada") or f"~{d.get('tokens_entrada_estimados', '?')} (estimado)"
    salida = d.get("tokens_salida") if d.get("tokens_salida") is not None else "?"
    extra = f" + {d['tokens_continuacion']} de continuación" if d.get("tokens_continuacion") else ""
    return (f"tokens: entrada {entrada}, salida {salida} de {d.get('num_predict', '?')}{extra} "
            f"(num_ctx {d.get('num_ctx', '?')})")


def _texto_recorte(recorte):
    if not recorte:
        return "no"
    acortado = " y se acortó el texto" if recorte["contexto_recortado"] else ""
    return (f"sí (se quitaron {recorte['fuentes_quitadas']} fuente(s){acortado}: ~{recorte['tokens_antes']} → "
            f"~{recorte['tokens_despues']} tokens, límite {recorte['limite']})")
