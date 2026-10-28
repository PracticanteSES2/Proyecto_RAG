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

Diseño (lo aprendido con MedGemma: se equivoca si se le piden varias tareas a
la vez, así que cada llamada hace UNA sola cosa y el código valida todo; la
evaluación real está en tests/docs_md/eval_actualizador.py):

0. Sin modelo: una nota sin contenido («arreglé lo de egresos») se pregunta de
   una vez; también la que afirma un valor anterior que el documento no tiene
   («subí el rojo de 120 a 150») o quita algo que la página no documenta.
1. Página: primero por reglas (nombre de la página, nombre funcional, tablas,
   nombres de entradas y palabras poco comunes de la página; jerga como
   «torta» -> gráfico circular). Si quedan varias candidatas, MedGemma elige
   entre una lista corta con salida restringida a esas opciones (o NO_SE_SABE).
   Si la nota no tiene ninguna pista, la elección se pide confirmar.
2. Operaciones: UNA llamada con solo el .md de esa página (sin metadatos ni
   historial), la lista exacta de secciones y entradas, los lineamientos,
   ejemplos con otra página y la nota. Salida restringida por un JSON schema
   (Ollama `format`); cada operación trae «antes» (copia del texto actual)
   y «texto» (cómo queda): sin «antes» el modelo tiende a repetir el texto.
3. Validación en código: secciones y entradas (tildes, mayúsculas, nombres
   parecidos, sección equivocada), «agregar» duplicado -> «modificar»,
   «modificar» sin texto en una nota que quita -> «eliminar». Se descartan los
   cambios sin respaldo en la nota (ninguna palabra o cifra que entra o sale
   está en la nota; «eliminar» sin que la nota quite nada; retoques de
   redacción) y, si la nota nombra una entrada, los cambios en otras que no
   nombra. Un único reintento (temperatura 0.3) con el problema concreto:
   JSON roto o cortado, entrada inexistente, texto igual al actual, unidad
   perdida, texto que pierde contenido. Se aplica sobre una copia y se valida.
4. Avisos para quien revisa (`avisos`, no bloquean): cifras que no están en la
   nota ni en el texto anterior, textos que pierden contenido, entradas que la
   nota nombra o que mencionan lo mismo y no se tocaron, correcciones hechas.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import time
from dataclasses import dataclass, field

from . import repositorio
from .formato import (
    ACCIONES,
    MAX_NOMBRE,
    SECCION_HISTORIAL,
    SECCION_TEXTO,
    Documento,
    ErrorFormato,
    ErrorOperacion,
    Operacion,
    aplicar_operaciones,
    diferencias,
    normalizar_nombre,
    parsear,
    secciones_para,
    serializar,
    validar,
)

ESTADOS = ("lista", "requiere_aclaracion", "error")

# Tiempo límite por llamada a MedGemma (s) y espera máxima de un hueco en el
# semáforo de llamadas (s). La actualización no es interactiva como el chat:
# se tolera esperar un poco más que en las respuestas del chatbot.
TIMEOUT_LLM = float(os.getenv("DOCS_MD_LLM_TIMEOUT", "60") or 60)
ESPERA_COLA = float(os.getenv("DOCS_MD_LLM_QUEUE_WAIT", "20") or 20)
MAX_TOKENS_OPERACIONES = 1500
TEMPERATURA_REINTENTO = 0.3
PAUSA_REINTENTO_SERVIDOR = 2.0
MAX_TOKENS_PAGINA = 40

NO_SE_SABE = "NO_SE_SABE"
# Con menos puntaje de reglas que esto, la nota no tiene pistas de la página y
# la elección de MedGemma se pide confirmar.
PUNTAJE_MINIMO_LLM = 2.0


class ErrorActualizacion(ValueError):
    """La propuesta no se puede aplicar."""


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
    # Observaciones para quien aprueba (no bloquean): cifras que no vienen de
    # la nota, textos que pierden contenido, correcciones hechas por el código.
    avisos: list[str] = field(default_factory=list)
    # Cómo se eligió la página: "indicada", "reglas" o "medgemma".
    metodo_pagina: str = ""
    # Segundos de cada llamada a MedGemma (diagnóstico y evaluación).
    tiempos_llm: list[float] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Texto: tokens comparables (sin tildes, plurales simples)
# ---------------------------------------------------------------------------

_VACIAS = {
    "a", "al", "con", "de", "del", "el", "en", "es", "la", "las", "le", "les", "lo", "los",
    "o", "para", "por", "que", "se", "sin", "su", "sus", "un", "una", "y", "ya", "no",
    "mas", "pero", "como", "esta", "este", "eso", "esa", "hay", "me", "mi", "ahora",
    "tabla", "pagina", "visual", "grafico", "le", "cambie", "cambio", "quite", "agregue",
    "puse", "deje", "arregle", "actualice", "nuevo", "nueva", "solo", "tambien", "ver",
}
# Palabras que aparecen en muchos nombres de página y distinguen poco.
_GENERICAS = {"dia", "tiempo", "tiempos", "historico", "historicos", "resumen"}

_PISTAS_DIA = {"hoy", "dia", "diario", "real", "semaforo", "espera", "pacientes"}
_PISTAS_HISTORICO = {"historico", "historicos", "mes", "meses", "mensual", "ano", "anos", "anual", "promedio"}
_PISTAS_GENERAL = {"definicion", "definiciones", "glosario", "general", "todas", "todo"}

# Jerga de BI -> palabra con que se documenta (se agregan, no reemplazan).
_SINONIMOS = {
    "torta": "circular", "pastel": "circular", "pie": "circular", "dona": "anillo", "donut": "anillo",
    "card": "tarjeta", "kpi": "tarjeta", "slicer": "segmentador", "hospi": "hospitalizacion",
    "obs": "observacion", "matrix": "matriz", "tooltip": "informacion",
}
_ROMANOS = {"1": "i", "2": "ii", "3": "iii", "4": "iv", "5": "v"}


def _tokens(texto: str) -> list[str]:
    """Palabras normalizadas. Los identificadores con guion bajo (TIEMPO_EGRESO_OK,
    RESUMEN_D) quedan como una sola palabra: «tiempo egreso» no debe coincidir
    dentro de una columna."""
    limpio = re.sub(r"[^a-z0-9_]+", " ", normalizar_nombre(texto))
    return [t.strip("_") for t in limpio.split() if t.strip("_")]


def _tokens_nota(texto: str) -> list[str]:
    """Tokens de la nota con jerga traducida («torta» -> circular, «triage 3» -> iii)."""
    tokens = _tokens(texto)
    extra = [_SINONIMOS[t] for t in tokens if t in _SINONIMOS]
    for i, t in enumerate(tokens[:-1]):
        if t == "triage" and tokens[i + 1] in _ROMANOS:
            extra.append(_ROMANOS[tokens[i + 1]])
    return tokens + extra


def _raiz(token: str) -> str:
    """Plural simple fuera: egresos -> egreso, visuales -> visual, remisiones -> remision."""
    if len(token) > 5 and token.endswith("ones"):
        return token[:-2]
    if len(token) > 5 and token.endswith("es") and token[-3] in "lrnd":
        return token[:-2]
    if len(token) > 3 and token.endswith("s"):
        return token[:-1]
    return token


def _coinciden(a: str, b: str) -> bool:
    a, b = _raiz(a), _raiz(b)
    if a == b:
        return True
    corto, largo = sorted((a, b), key=len)
    return len(corto) >= 5 and "_" not in largo and largo.startswith(corto)


def _significativos(texto: str) -> list[str]:
    return [t for t in _tokens(texto) if t not in _VACIAS]


def _presente(token: str, tokens_nota: list[str]) -> bool:
    return any(_coinciden(token, t) for t in tokens_nota)


def _posicion_frase(frase: str, texto_norm: str) -> int:
    """Posición de la frase (palabras completas) en el texto normalizado, o -1."""
    frase = " ".join(_tokens(frase))
    if not frase:
        return -1
    m = re.search(rf"(?<![a-z0-9_]){re.escape(frase)}(?![a-z0-9_])", texto_norm)
    return m.start() if m else -1


def _frase_en(frase: str, texto_norm: str) -> bool:
    return _posicion_frase(frase, texto_norm) >= 0


# ---------------------------------------------------------------------------
# Paso 1: elegir la página
# ---------------------------------------------------------------------------

def _cargar_paginas(source_group: str, raiz=None) -> list[dict]:
    """Páginas válidas del grupo con su documento (para puntuar)."""
    paginas = []
    for item in repositorio.listar_paginas(source_group, raiz):
        try:
            texto = (repositorio.carpeta_md(source_group, raiz) / item["archivo"]).read_text(encoding="utf-8")
            doc = parsear(texto)
        except (OSError, ErrorFormato):
            continue
        paginas.append({**item, "doc": doc})
    return paginas


def _vocabulario(doc: Documento) -> set[str]:
    """Raíces de las palabras del texto de la página (para coincidencias débiles)."""
    vocab = set()
    for seccion, entradas in doc.secciones.items():
        if seccion != SECCION_HISTORIAL:
            for e in entradas:
                vocab.update(_raiz(t) for t in _significativos(e.nombre + " " + e.texto) if len(t) >= 5)
    vocab.update(_raiz(t) for t in _significativos(doc.proposito) if len(t) >= 5)
    return vocab


def _puntuar_pagina(pag: dict, tokens_nota: list[str], texto_norm: str, df: dict) -> tuple[float, int]:
    """Puntaje de reglas de una página para la nota y la posición donde la
    nota nombra la página completa (-1 si no la nombra)."""
    doc: Documento = pag["doc"]
    puntaje = 0.0
    nombre = doc.pagina
    general = doc.meta.get("bloque") == "General"

    # Nombre de la página: frase completa (fuerte) o palabras sueltas.
    sig_nombre = [t for t in _tokens(nombre) if t not in _VACIAS]
    posicion = -1
    if not general and sig_nombre:
        posiciones = [x for x in (_posicion_frase(nombre, texto_norm),
                                  _posicion_frase(pag["archivo"].rsplit(".", 1)[0], texto_norm)) if x >= 0]
        if posiciones:
            puntaje += 10
            posicion = min(posiciones)
        elif len(sig_nombre) > 1 and all(_presente(t, tokens_nota) for t in sig_nombre):
            puntaje += 6
        else:
            for t in sig_nombre:
                if _presente(t, tokens_nota):
                    puntaje += 0.5 if t in _GENERICAS else 2

    # Nombre funcional: palabras significativas (pocas, para no dominar).
    funcional = [t for t in _significativos(doc.meta.get("nombre_funcional", "")) if t not in _GENERICAS]
    puntaje += min(2, sum(0.5 for t in set(funcional) if _presente(t, tokens_nota)))

    # Tablas nombradas tal cual (ESPERA_EGRESO, EGRESOS_DIA...).
    tablas = set(doc.meta.get("tablas") or [])
    tablas |= {e.nombre for e in doc.entradas("Fuentes de datos")}
    for tabla in tablas:
        if ("_" in tabla or tabla.isupper()) and _frase_en(tabla, texto_norm):
            puntaje += 6

    # Nombres de entradas: todas sus palabras significativas en la nota, y al
    # menos una que no sea del nombre de la página («Tabla egresos» no suma
    # en EGRESOS DIA solo porque la nota dice «egresos»).
    mejores = []
    for seccion, entradas in doc.secciones.items():
        if seccion == SECCION_HISTORIAL:
            continue
        for e in entradas:
            if len(_tokens(e.nombre)) > 1 and _frase_en(e.nombre, texto_norm):
                mejores.append(4.0)  # «Tabla egresos: el filtro ...»: nombre tal cual
                continue
            sig = [t for t in _significativos(e.nombre) if t not in _GENERICAS]
            if not sig:
                continue
            presentes = [t for t in sig if _presente(t, tokens_nota)]
            propias = [t for t in presentes if not any(_coinciden(t, n) for n in sig_nombre)]
            if not propias:
                continue
            if len(presentes) == len(sig) and len(sig) > 1:
                mejores.append(3.0)
            elif len(presentes) >= 2 or (len(presentes) == len(sig) and len(sig[0]) >= 6):
                mejores.append(1.0)
    puntaje += sum(sorted(mejores, reverse=True)[:2])

    # Texto de la página: coincidencias débiles ponderadas por rareza
    # («torta» está en una sola página; «verde» en casi todas).
    comunes = {_raiz(t) for t in tokens_nota if len(t) >= 5 and t not in _VACIAS} & pag["vocab"]
    puntaje += min(3.0, 1.5 * sum(1.0 / df.get(t, 1) for t in comunes))

    # Pistas de bloque.
    bloque = normalizar_nombre(doc.meta.get("bloque", ""))
    if bloque == "dia" and any(t in _PISTAS_DIA for t in tokens_nota):
        puntaje += 1
    if bloque == "historico" and any(t in _PISTAS_HISTORICO for t in tokens_nota):
        puntaje += 1
    if general:
        # La general comparte vocabulario con todas: solo compite si la nota
        # habla de definiciones o del tablero completo.
        if any(t in _PISTAS_GENERAL for t in tokens_nota):
            puntaje += 4
        else:
            puntaje *= 0.5
    return puntaje, posicion


def puntuar_paginas(nota: str, paginas: list[dict], cambios_pbip=None) -> list[dict]:
    """[{pagina, nombre_funcional, bloque, puntaje, posicion}] ordenado de mayor a menor.
    `posicion` >= 0 si la nota (o los cambios del PBIP) nombran la página completa."""
    texto = nota + "\n" + _texto_pbip(cambios_pbip)
    tokens_nota = _tokens_nota(texto)
    texto_norm = " ".join(_tokens(texto))
    for pag in paginas:
        pag.setdefault("vocab", _vocabulario(pag["doc"]))
    df: dict[str, int] = {}
    for pag in paginas:
        for t in pag["vocab"]:
            df[t] = df.get(t, 0) + 1
    resultado = []
    for pag in paginas:
        puntaje, posicion = _puntuar_pagina(pag, tokens_nota, texto_norm, df)
        resultado.append({
            "pagina": pag["pagina"],
            "nombre_funcional": pag.get("nombre_funcional", ""),
            "bloque": pag.get("bloque", ""),
            "puntaje": round(puntaje, 2),
            "posicion": posicion,
        })
    # Si una página nombrada está contenida en el nombre de otra también
    # nombrada (RESUMEN dentro de RESUMEN DIA), solo cuenta la más larga.
    nombradas = [r for r in resultado if r["posicion"] >= 0]
    for r in nombradas:
        clave = " ".join(_tokens(r["pagina"]))
        for otra in nombradas:
            largo = " ".join(_tokens(otra["pagina"]))
            if otra is not r and len(largo) > len(clave) and \
                    re.search(rf"(?<![a-z0-9_]){re.escape(clave)}(?![a-z0-9_])", largo):
                r["posicion"] = -1
                r["puntaje"] = round(r["puntaje"] - 10, 2)
                break
    resultado.sort(key=lambda r: -r["puntaje"])
    return resultado


SISTEMA_PAGINA = (
    "Identificas a qué página de un tablero Power BI se refiere una nota de cambio escrita por un "
    "desarrollador. Responde solo con JSON: {\"pagina\": \"<nombre exacto de la lista>\"}. "
    f"Si la nota no permite saber con seguridad cuál es, responde {{\"pagina\": \"{NO_SE_SABE}\"}}."
)


def _resumen_pagina(pag: dict) -> str:
    doc: Documento = pag["doc"]
    nombres = []
    for seccion in ("Visuales", "Indicadores", "Reglas de negocio"):
        nombres += [e.nombre for e in doc.entradas(seccion)]
    contenido = "; ".join(nombres[:10])
    return (f"- {doc.pagina}: {doc.meta.get('nombre_funcional', '')} (bloque {doc.meta.get('bloque', '')}). "
            f"Contiene: {contenido}.")


def _elegir_con_llm(nota, candidatas: list[dict], llamador, propuesta: Propuesta, cambios_pbip=None):
    """(página elegida | None, mensaje de fallo del servidor | "")."""
    opciones = [c["pagina"] for c in candidatas]
    lista = "\n".join(_resumen_pagina(c) for c in candidatas)
    pbip = _texto_pbip(cambios_pbip)
    extra = f"\n\nCambios detectados en el PBIP:\n{pbip}" if pbip else ""
    mensajes = [
        {"role": "system", "content": SISTEMA_PAGINA},
        {"role": "user", "content": f"Páginas posibles:\n{lista}\n\nNota:\n«{nota.strip()}»{extra}"},
    ]
    esquema = {
        "type": "object",
        "properties": {"pagina": {"type": "string", "enum": opciones + [NO_SE_SABE]}},
        "required": ["pagina"],
    }
    respuesta = llamador(mensajes, esquema, MAX_TOKENS_PAGINA)
    propuesta.llm_raw += f"[página] {respuesta.get('answer') or respuesta.get('error') or ''}\n"
    if respuesta.get("status") != "success":
        return None, _mensaje_fallo(respuesta)
    data = _extraer_json(respuesta.get("answer") or "")
    elegida = str((data or {}).get("pagina") or "").strip()
    for opcion in opciones:
        if normalizar_nombre(opcion) == normalizar_nombre(elegida):
            return opcion, ""
    return None, ""


def elegir_pagina(nota, source_group, llm=None, cambios_pbip=None, raiz=None, propuesta=None, llamar=None) -> dict:
    """Elige la página a la que se refiere la nota.

    Devuelve {"pagina": str | None, "metodo": "reglas" | "medgemma" | "",
              "candidatas": [...], "otras": [...], "puntajes": [...]} y, según el
    caso, "sugerida" (elección de MedGemma sin pistas en la nota, a confirmar)
    o "error" (el servidor no respondió)."""
    propuesta = propuesta or Propuesta(nota=nota, source_group=source_group)
    paginas = _cargar_paginas(source_group, raiz)
    if not paginas:
        return {"pagina": None, "metodo": "", "candidatas": [], "otras": [], "puntajes": []}
    puntajes = puntuar_paginas(nota, paginas, cambios_pbip)
    # Páginas nombradas en la nota: la principal es la primera que se nombra
    # («en MAPA DE CALOR TRIAGE agregué el segmentador igual al de TIEMPO TRIAGE»).
    nombradas = sorted((p for p in puntajes if p["posicion"] >= 0), key=lambda p: p["posicion"])
    if nombradas:
        principal = nombradas[0]["pagina"]
        return {"pagina": principal, "metodo": "reglas", "candidatas": [principal],
                "otras": [p["pagina"] for p in nombradas[1:]], "puntajes": puntajes}
    mejor = puntajes[0]
    segundo = puntajes[1]["puntaje"] if len(puntajes) > 1 else 0.0
    otras: list[str] = []

    if mejor["puntaje"] >= 5 and mejor["puntaje"] - segundo >= 3:
        return {"pagina": mejor["pagina"], "metodo": "reglas", "candidatas": [mejor["pagina"]],
                "otras": otras, "puntajes": puntajes}

    # Lista corta: las cercanas a la mejor (o todas si no hay ninguna pista).
    if mejor["puntaje"] >= 1:
        cercanas = [p for p in puntajes if p["puntaje"] >= max(1.0, mejor["puntaje"] * 0.5)][:5]
    else:
        cercanas = [p for p in puntajes if p["puntaje"] > 0][:8] or puntajes[:12]
    por_nombre = {p["pagina"]: p for p in paginas}
    candidatas = [por_nombre[p["pagina"]] for p in cercanas]
    nombres = [c["pagina"] for c in candidatas]
    if len(candidatas) == 1 and mejor["puntaje"] >= 3:
        return {"pagina": nombres[0], "metodo": "reglas", "candidatas": nombres, "otras": otras,
                "puntajes": puntajes}

    llamar = llamar or _llamador(llm, propuesta)
    elegida, fallo = _elegir_con_llm(nota, candidatas, llamar, propuesta, cambios_pbip)
    if fallo:
        return {"pagina": None, "metodo": "", "candidatas": nombres, "otras": [], "puntajes": puntajes,
                "error": fallo}
    if elegida and mejor["puntaje"] < PUNTAJE_MINIMO_LLM:
        # La nota no tiene ninguna pista de la página: la elección de MedGemma
        # es una suposición. Se sugiere primero, pero se pide confirmar.
        return {"pagina": None, "metodo": "", "sugerida": elegida,
                "candidatas": [elegida] + [n for n in nombres if n != elegida], "otras": [], "puntajes": puntajes}
    return {"pagina": elegida, "metodo": "medgemma" if elegida else "", "candidatas": nombres,
            "otras": [o for o in otras if o != elegida], "puntajes": puntajes}


# ---------------------------------------------------------------------------
# Paso 2: pedir las operaciones a MedGemma
# ---------------------------------------------------------------------------

SISTEMA_OPERACIONES = """Eres el editor de la documentación de un tablero Power BI. Un desarrollador cambió una página del tablero y lo cuenta en una nota informal, escrita con prisa. Tu única tarea: convertir la nota en operaciones de edición sobre la documentación de esa página.

Cada operación tiene:
- "accion": "modificar" (cambia el texto de una entrada que ya existe), "agregar" (entrada nueva) o "eliminar" (quita una entrada).
- "seccion": una de las secciones de la lista.
- "entrada": para modificar o eliminar, el nombre EXACTO de una entrada existente, copiado de la lista; para agregar, un nombre corto y nuevo.
- "antes": el texto actual de esa entrada, copiado del documento. Vacío al agregar.
- "texto": cómo queda la entrada DESPUÉS del cambio, sin el nombre. Al modificar debe ser distinto de "antes": lleva lo nuevo que dice la nota y conserva lo que la nota no cambia. Vacío al eliminar.

Reglas:
- Si la nota habla de algo que ya está documentado, modifica esa entrada. No agregues una entrada parecida a una existente.
- Cambia solo las entradas que la nota nombra o describe. Si hay dos entradas parecidas, cambia la que coincide con lo que dice la nota.
- Elimina una entrada solo si la nota dice que ESE elemento completo se quitó, se borró, ya no se usa o ya no existe. Si se quitó algo DE un elemento (un filtro, una columna, una exclusión), modifica la entrada de ese elemento: quitar un filtro o una exclusión significa que esos datos ahora sí se incluyen.
- No inventes cifras, columnas ni tablas. Usa solo lo que dicen la nota y el documento.
- Si la nota no dice qué cambió, si habla de algo que no existe en esta página o si describe el estado anterior distinto a como está documentado, no adivines: deja "operaciones" vacío y escribe la pregunta en "dudas".
- Redacta en español, en presente, con frases cortas que terminan en punto. Todo tiempo lleva su unidad (minutos u horas).
- Nunca edites «Historial de cambios».

Ejemplos con otra página (entradas «Tabla admitidos»: "Pacientes admitidos hoy con documento, nombre y tiempo de espera en minutos." y «Tarjeta total admitidos»: "Cantidad de admisiones de hoy."):
- Nota «la tabla de admitidos ahora tambien muestra la aseguradora» -> {"operaciones": [{"accion": "modificar", "seccion": "Visuales", "entrada": "Tabla admitidos", "antes": "Pacientes admitidos hoy con documento, nombre y tiempo de espera en minutos.", "texto": "Pacientes admitidos hoy con documento, nombre, aseguradora y tiempo de espera en minutos."}], "resumen": "La tabla de admitidos muestra la aseguradora.", "dudas": []}
- Nota «le quite el nombre a la tabla de admitidos» -> {"operaciones": [{"accion": "modificar", "seccion": "Visuales", "entrada": "Tabla admitidos", "antes": "Pacientes admitidos hoy con documento, nombre y tiempo de espera en minutos.", "texto": "Pacientes admitidos hoy con documento y tiempo de espera en minutos."}], "resumen": "La tabla de admitidos ya no muestra el nombre.", "dudas": []}
- Nota «quite la tarjeta del total» -> {"operaciones": [{"accion": "eliminar", "seccion": "Visuales", "entrada": "Tarjeta total admitidos", "antes": "Cantidad de admisiones de hoy.", "texto": ""}], "resumen": "Se quitó la tarjeta del total de admitidos.", "dudas": []}
- Nota «puse un grafico de barras de admisiones por aseguradora» -> {"operaciones": [{"accion": "agregar", "seccion": "Visuales", "entrada": "Gráfico de admisiones por aseguradora", "antes": "", "texto": "Gráfico de barras con la cantidad de admisiones por aseguradora."}], "resumen": "Se agregó un gráfico de admisiones por aseguradora.", "dudas": []}
- Nota «ajustes varios en la pagina» -> {"operaciones": [], "resumen": "", "dudas": ["¿Qué cambió exactamente: qué visual, indicador o regla, y cuál es el valor nuevo?"]}

Responde solo con JSON: {"operaciones": [...], "resumen": "una frase que describe el cambio", "dudas": []}"""


def _texto_pbip(cambios_pbip) -> str:
    if not cambios_pbip:
        return ""
    if isinstance(cambios_pbip, str):
        return cambios_pbip.strip()
    if isinstance(cambios_pbip, dict):
        return json.dumps(cambios_pbip, ensure_ascii=False)
    return "\n".join(f"- {c}" for c in cambios_pbip)


def _secciones_editables(doc: Documento) -> list[str]:
    return [s for s in secciones_para(doc.meta) if s != SECCION_HISTORIAL]


def _documento_para_llm(doc: Documento) -> str:
    """El .md de la página sin metadatos ni historial (lo que el modelo puede editar)."""
    partes = [f"# {doc.pagina}", "", f"## {SECCION_TEXTO}", doc.proposito.strip(), ""]
    for seccion in _secciones_editables(doc):
        if seccion == SECCION_TEXTO or not doc.entradas(seccion):
            continue
        partes.append(f"## {seccion}")
        partes += [f"- **{e.nombre}**: {e.texto}" for e in doc.entradas(seccion)]
        partes.append("")
    return "\n".join(partes).strip()


def _mensajes_operaciones(doc: Documento, nota: str, cambios_pbip=None) -> list[dict]:
    lineas = []
    vacias = []
    for seccion in _secciones_editables(doc):
        if seccion == SECCION_TEXTO:
            lineas.append(f"- {SECCION_TEXTO}: texto libre (solo modificar, con el texto completo).")
        elif doc.entradas(seccion):
            nombres = ", ".join(f"«{e.nombre}»" for e in doc.entradas(seccion))
            lineas.append(f"- {seccion}: {nombres}")
        else:
            vacias.append(seccion)
    if vacias:
        lineas.append(f"- Sin entradas todavía (solo agregar): {', '.join(vacias)}.")
    partes = [
        f"Página: {doc.pagina} ({doc.meta.get('nombre_funcional', '')}).",
        "",
        "Secciones y entradas existentes:",
        *lineas,
        "",
        "Documentación actual:",
        "<<<",
        _documento_para_llm(doc),
        ">>>",
    ]
    pbip = _texto_pbip(cambios_pbip)
    if pbip:
        partes += ["", "Cambios detectados en el archivo del tablero (PBIP); son hechos y la documentación "
                   "debe reflejarlos:", pbip]
    partes += ["", "Nota del desarrollador:", f"«{nota.strip()}»"]
    return [
        {"role": "system", "content": SISTEMA_OPERACIONES},
        {"role": "user", "content": "\n".join(partes)},
    ]


def _esquema_operaciones(doc: Documento) -> dict:
    return {
        "type": "object",
        "properties": {
            "operaciones": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "accion": {"type": "string", "enum": list(ACCIONES)},
                        "seccion": {"type": "string", "enum": _secciones_editables(doc)},
                        "entrada": {"type": "string"},
                        # «antes» obliga al modelo a copiar el texto actual y luego
                        # escribir uno distinto: sin él tiende a repetir el actual.
                        "antes": {"type": "string"},
                        "texto": {"type": "string"},
                    },
                    "required": ["accion", "seccion", "entrada", "antes", "texto"],
                },
            },
            "resumen": {"type": "string"},
            "dudas": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["operaciones", "resumen", "dudas"],
    }


# ---------------------------------------------------------------------------
# Llamada al LLM
# ---------------------------------------------------------------------------

def _proveedor_por_defecto():
    from src.llm.medgemma_provider import MedGemmaProvider

    return MedGemmaProvider()


def _llamador(llm, propuesta: Propuesta):
    """Función (mensajes, esquema, max_tokens) -> dict del proveedor; crea
    MedGemmaProvider solo cuando hace falta y registra la latencia."""
    estado = {"llm": llm}

    def llamar(mensajes, esquema, max_tokens, temperatura=0.0):
        from src.llm.llm_gate import call_llm

        if estado["llm"] is None:
            try:
                estado["llm"] = _proveedor_por_defecto()
            except Exception as exc:  # p. ej. falta MEDGEMMA_BASE_URL
                return {"status": "llm_error", "answer": None, "error": f"MedGemma no está configurado: {exc}"}
        for intento in range(2):
            inicio = time.perf_counter()
            respuesta = call_llm(
                estado["llm"],
                mensajes,
                purpose="documentación",
                timeout=TIMEOUT_LLM,
                queue_wait=ESPERA_COLA,
                temperature=temperatura,
                max_tokens=max_tokens,
                think=False,
                format=esquema,
            )
            propuesta.tiempos_llm.append(round(time.perf_counter() - inicio, 2))
            # Un error pasajero del servidor (5xx del proxy o del runner) se
            # reintenta una vez; el tiempo agotado no (ya se esperó bastante).
            transitorio = (respuesta.get("status") == "ollama_error"
                           and respuesta.get("status_code") in (500, 502, 503, 504))
            if not transitorio or intento:
                return respuesta
            time.sleep(PAUSA_REINTENTO_SERVIDOR)
        return respuesta

    return llamar


def _mensaje_fallo(respuesta: dict) -> str:
    estado = respuesta.get("status")
    if estado == "llm_timeout":
        return (f"MedGemma no respondió en {TIMEOUT_LLM:.0f} s. El servidor puede estar ocupado o apagado; "
                "intente de nuevo en unos minutos.")
    if estado == "llm_saturated":
        return "MedGemma está ocupado con otras consultas en este momento; intente de nuevo en unos segundos."
    if estado == "empty_response":
        return "MedGemma devolvió una respuesta vacía."
    detalle = respuesta.get("error") or estado or "sin detalle"
    return f"No se pudo consultar a MedGemma: {detalle}"


def _extraer_json(texto: str):
    """Primer objeto JSON del texto (tolera ```json ... ``` y texto alrededor)."""
    texto = str(texto or "").strip()
    texto = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto)
    try:
        data = json.loads(texto)
        return data if isinstance(data, dict) else None
    except ValueError:
        pass
    inicio = texto.find("{")
    fin = texto.rfind("}")
    if inicio >= 0 and fin > inicio:
        try:
            data = json.loads(texto[inicio:fin + 1])
            return data if isinstance(data, dict) else None
        except ValueError:
            pass
    return _rescatar_truncado(texto)


def _rescatar_truncado(texto: str):
    """Respuesta cortada por el límite de tokens (el modelo copió muchas
    entradas): se rescatan las operaciones completas. Marca `_truncado`."""
    m = re.search(r'"operaciones"\s*:\s*\[', texto)
    if not m:
        return None
    decodificador = json.JSONDecoder()
    pos, operaciones = m.end(), []
    while True:
        while pos < len(texto) and texto[pos] in " \t\r\n,":
            pos += 1
        if pos >= len(texto) or texto[pos] != "{":
            break
        try:
            objeto, pos = decodificador.raw_decode(texto, pos)
        except ValueError:
            break
        if isinstance(objeto, dict):
            operaciones.append(objeto)
    return {"operaciones": operaciones, "resumen": "", "dudas": [], "_truncado": True}


# ---------------------------------------------------------------------------
# Paso 3: validar y corregir las operaciones
# ---------------------------------------------------------------------------

_SINONIMOS_ACCION = {
    "agregar": "agregar", "anadir": "agregar", "añadir": "agregar", "crear": "agregar", "nuevo": "agregar",
    "nueva": "agregar", "insertar": "agregar", "adicionar": "agregar",
    "modificar": "modificar", "cambiar": "modificar", "editar": "modificar", "actualizar": "modificar",
    "reemplazar": "modificar", "corregir": "modificar",
    "eliminar": "eliminar", "quitar": "eliminar", "borrar": "eliminar", "remover": "eliminar",
    "suprimir": "eliminar",
}


def _accion_canonica(valor: str) -> str:
    return _SINONIMOS_ACCION.get(normalizar_nombre(valor), normalizar_nombre(valor))


def _seccion_canonica(valor: str, doc: Documento) -> str | None:
    permitidas = secciones_para(doc.meta)
    clave = normalizar_nombre(valor).strip("#: ")
    for s in permitidas:
        if normalizar_nombre(s) == clave:
            return s
    parecidas = difflib.get_close_matches(clave, [normalizar_nombre(s) for s in permitidas], n=1, cutoff=0.75)
    if parecidas:
        return next(s for s in permitidas if normalizar_nombre(s) == parecidas[0])
    return None


_CONECTORES = {"a", "al", "con", "de", "del", "el", "en", "la", "las", "los", "para", "por", "y", "o", "un", "una"}


def _similitud(a: str, b: str) -> float:
    """Parecido entre dos nombres de entrada. Cuenta las palabras (sin
    conectores, con plurales simples): «Tarjeta en espera egreso» y «Tabla en
    espera egreso» NO son la misma entrada. La comparación por letras solo
    rescata errores de tipeo (casi idénticos)."""
    ta = {_raiz(t) for t in _tokens(a) if t not in _CONECTORES}
    tb = {_raiz(t) for t in _tokens(b) if t not in _CONECTORES}
    jaccard = len(ta & tb) / len(ta | tb) if ta and tb else 0.0
    letras = difflib.SequenceMatcher(None, normalizar_nombre(a), normalizar_nombre(b)).ratio()
    return max(jaccard, letras if letras >= 0.92 else 0.0)


def _buscar_parecida(doc: Documento, seccion: str, nombre: str, umbral: float):
    """Entrada de la sección con nombre muy parecido (única mejor), o None."""
    candidatos = sorted(((_similitud(nombre, e.nombre), e) for e in doc.entradas(seccion)),
                        key=lambda x: -x[0])
    if not candidatos or candidatos[0][0] < umbral:
        return None
    if len(candidatos) > 1 and candidatos[1][0] >= candidatos[0][0] - 0.05:
        return None  # dos casi iguales: no se elige a ciegas
    return candidatos[0][1]


def _limpiar_texto(texto: str, nombre: str) -> str:
    texto = re.sub(r"\s+", " ", str(texto or "")).strip()
    texto = re.sub(r"^[-*]\s+", "", texto)
    # El modelo a veces repite el nombre: «**Semáforo**: Verde ...» o «Semáforo: Verde ...».
    m = re.match(r"^\*\*(.+?)\*\*\s*[:：]\s*(.*)$", texto)
    if m:
        texto = m.group(2)
    elif nombre and normalizar_nombre(texto).startswith(normalizar_nombre(nombre) + ":"):
        texto = texto[len(nombre) + 1:].strip()
    texto = texto.replace("**", "")
    if texto and texto[0].islower():
        texto = texto[0].upper() + texto[1:]
    return texto


def _limpiar_nombre(nombre: str) -> str:
    nombre = re.sub(r"\s+", " ", str(nombre or "")).strip().strip("«»\"'*").strip()
    return nombre.rstrip(".:").strip()


def _resolver(doc: Documento, data_op: dict, avisos: list[str], quita: bool = False):
    """Convierte una operación del modelo en Operacion válida para el documento.
    Devuelve (Operacion | None, problema | None, sin_cambio: bool)."""
    accion = _accion_canonica(str(data_op.get("accion") or ""))
    if accion not in ACCIONES:
        return None, f"Acción «{data_op.get('accion')}» no válida.", False
    seccion = _seccion_canonica(str(data_op.get("seccion") or ""), doc)
    if seccion is None:
        return None, f"La sección «{data_op.get('seccion')}» no existe.", False
    if seccion == SECCION_HISTORIAL:
        return None, "El historial no se edita con operaciones.", False
    nombre = _limpiar_nombre(data_op.get("entrada") or "")
    texto = _limpiar_texto(data_op.get("texto") or "", nombre)

    if seccion == SECCION_TEXTO:
        if accion != "modificar" or not texto:
            return None, "«Propósito» solo admite modificar con el texto completo.", False
        if normalizar_nombre(texto.rstrip(".")) == normalizar_nombre(doc.proposito.rstrip(".")):
            return None, None, True
        return Operacion("modificar", seccion, "", texto), None, False

    if not nombre:
        return None, f"Una operación en «{seccion}» no indica el nombre de la entrada.", False
    if len(nombre) > MAX_NOMBRE:
        return None, f"El nombre de entrada «{nombre[:40]}…» es demasiado largo; usa el nombre de la lista.", False
    if _seccion_canonica(nombre, doc) is not None and doc.buscar(seccion, nombre) is None:
        # «entrada»: "Visuales" -> el modelo copió el nombre de la sección.
        return None, f"«{nombre}» es una sección, no una entrada.", False

    existente = doc.buscar(seccion, nombre)
    if existente is None:
        # ¿Existe con ese nombre en otra sección? (el modelo se equivocó de sección)
        for otra in _secciones_editables(doc):
            if otra != SECCION_TEXTO and otra != seccion and doc.buscar(otra, nombre) is not None:
                avisos.append(f"Se corrigió la sección de «{nombre}»: está en «{otra}», no en «{seccion}».")
                seccion, existente = otra, doc.buscar(otra, nombre)
                break

    if accion == "agregar":
        if existente is None:
            parecida = _buscar_parecida(doc, seccion, nombre, 0.9)
            if parecida is not None:
                existente = parecida
        if existente is not None:
            avisos.append(f"«{nombre}» ya existe en «{seccion}» como «{existente.nombre}»; se modifica en lugar de duplicarla.")
            accion, nombre = "modificar", existente.nombre
        elif not texto or normalizar_nombre(texto.rstrip(".")) == normalizar_nombre(nombre):
            return None, f"La entrada nueva «{nombre}» no tiene texto.", False
        else:
            return Operacion("agregar", seccion, nombre, texto), None, False

    if existente is None:
        parecida = _buscar_parecida(doc, seccion, nombre, 0.6)
        if parecida is None:
            return None, f"No existe la entrada «{nombre}» en «{seccion}».", False
        avisos.append(f"«{nombre}» no existe en «{seccion}»; se usó la entrada parecida «{parecida.nombre}».")
        existente = parecida
    if accion == "eliminar":
        return Operacion("eliminar", seccion, existente.nombre, ""), None, False
    if not texto and quita:
        # «ya no se muestra la leyenda» -> el modelo «modifica» dejando el texto vacío.
        avisos.append(f"«{existente.nombre}»: la modificación venía sin texto y la nota quita algo; se elimina.")
        return Operacion("eliminar", seccion, existente.nombre, ""), None, False
    if not texto or normalizar_nombre(texto.rstrip(".")) == normalizar_nombre(existente.nombre):
        return None, f"La modificación de «{existente.nombre}» no trae el texto nuevo completo.", False
    if normalizar_nombre(texto.rstrip(".")) == normalizar_nombre(existente.texto.rstrip(".")):
        return Operacion("modificar", seccion, existente.nombre, texto), None, True
    return Operacion("modificar", seccion, existente.nombre, texto), None, False


_NUMERO_RE = re.compile(r"\d+(?:[.,]\d+)?")

# Palabras que no cuentan como contenido al comparar textos con la nota.
_NEUTRAS = _CONECTORES | {"lo", "le", "les", "se", "que", "es", "no", "ya", "su", "sus", "como", "mas", "si"}

# Verbos y sustantivos genéricos de cambio: una nota hecha solo de ellos (y del
# nombre de la página) no dice qué cambió («arreglé lo de egresos»).
_CAMBIO_GENERICO = {
    "arregle", "arreglo", "arreglos", "arreglamos", "arreglado", "ajuste", "ajustes", "ajustamos", "ajustado",
    "cambie", "cambio", "cambios", "cambiamos", "cambiado", "modifique", "modificacion", "modificaciones",
    "modificamos", "actualice", "actualizacion", "actualizaciones", "actualizamos", "corregi", "correccion",
    "correcciones", "corregimos", "mejore", "mejora", "mejoras", "mejoramos", "revise", "revisamos", "toque",
    "tocamos", "hice", "hicimos", "cosas", "cosa", "detalles", "detalle", "varios", "varias", "temas", "tema",
    "algo", "algunos", "algunas", "unos", "unas", "un", "una", "poco", "pagina", "tablero", "listo", "ok",
}


def _numeros(texto: str) -> set[str]:
    return {n.replace(",", ".") for n in _NUMERO_RE.findall(str(texto or ""))}


def nota_sin_contenido(nota: str, nombres_paginas) -> bool:
    """True si la nota solo tiene palabras genéricas de cambio y nombres de
    página: no hay de dónde sacar qué cambió y no vale la pena preguntar a
    MedGemma (inventaría)."""
    if re.search(r"\d", nota or ""):
        return False
    de_paginas = {t for n in nombres_paginas for t in _tokens(n)}
    resto = [t for t in _tokens(nota)
             if t not in _NEUTRAS and t not in _CAMBIO_GENERICO and t not in _GENERICAS
             and not any(_coinciden(t, p) for p in de_paginas)]
    return not resto


def _referencia(nota: str, cambios_pbip) -> tuple[list[str], set[str]]:
    """Palabras y cifras de la nota (y del PBIP) contra las que se comprueba
    que cada cambio propuesto tenga respaldo."""
    texto = nota + "\n" + _texto_pbip(cambios_pbip)
    palabras = [t for t in _tokens_nota(texto) if t not in _NEUTRAS and t not in _CAMBIO_GENERICO]
    return palabras, _numeros(texto)


# Señales de que la nota quita algo (sin ellas, «eliminar» no tiene respaldo).
_QUITAR_RE = re.compile(
    r"\b(quit\w*|elimin\w*|borr\w*|sac\w*|retir\w*|ocult\w*|remov\w*|suprim\w*|desaparec\w*|"
    r"ya no|no se usa|no existe)\b")


def _cifras_cerca(cifras: set[str]) -> set[str]:
    """Cifras de la nota y sus vecinas (±1): «menor a 721» respalda «hasta 720»."""
    cerca = set(cifras)
    for c in cifras:
        try:
            valor = float(c)
        except ValueError:
            continue
        if valor.is_integer():
            cerca |= {str(int(valor) - 1), str(int(valor) + 1)}
    return cerca


def _formas(texto: str) -> set[str]:
    """Palabras sin conectores y sin la vocal final de género (ultimo/ultima)."""
    return {re.sub(r"(os|as|o|a)$", "", t) for t in _tokens(texto) if t not in _NEUTRAS}


def _clausulas(texto: str) -> set[str]:
    return {" ".join(_tokens(c)) for c in re.split(r"[.;:,()]", texto or "") if _tokens(c)}


def _respaldo(doc: Documento, op: Operacion, palabras: list[str], cifras: set[str], quita: bool = True) -> str:
    """¿El cambio tiene que ver con la nota?

    - "directo": al modificar, alguna palabra o cifra que entra o sale del
      texto está en la nota; al eliminar, la nota quita algo y nombra la entrada.
    - "indirecto": las palabras que cambian no son las de la nota, pero la
      frase que cambia sí habla de lo que dice la nota («quité el filtro de
      obstétricas» -> «Incluye las clasificaciones obstétricas»). Se acepta
      con aviso, salvo que sea un retoque mínimo de redacción.
    - "": sin respaldo (se descarta)."""
    if op.accion == "agregar":
        return "directo"
    if op.seccion == SECCION_TEXTO:
        anterior = doc.proposito
    else:
        entrada = doc.buscar(op.seccion, op.entrada)
        anterior = entrada.texto if entrada else ""
    if op.accion == "eliminar":
        nombre = [t for t in _tokens(op.entrada) if t not in _NEUTRAS]
        return "directo" if quita and any(_presente(t, palabras) for t in nombre) else ""
    viejas = {_raiz(t) for t in _tokens(anterior) if t not in _NEUTRAS}
    nuevas = {_raiz(t) for t in _tokens(op.texto) if t not in _NEUTRAS}
    if any(_presente(t, palabras) for t in viejas ^ nuevas):
        return "directo"
    if (_numeros(anterior) ^ _numeros(op.texto)) & _cifras_cerca(cifras):
        return "directo"
    retoque = not (_formas(anterior) ^ _formas(op.texto))
    cambiadas = _clausulas(op.texto) - _clausulas(anterior)
    if not retoque and any(_presente(t, palabras) for c in cambiadas for t in c.split() if t not in _NEUTRAS):
        return "indirecto"
    return ""


def _avisos_contenido(doc: Documento, ops: list[Operacion], nota: str, cambios_pbip) -> list[str]:
    """Avisos para quien revisa: cifras sin origen y textos que pierden contenido."""
    avisos = []
    origen = _numeros(nota) | _numeros(_texto_pbip(cambios_pbip))
    for op in ops:
        if op.accion == "eliminar":
            continue
        if op.seccion == SECCION_TEXTO:
            anterior = doc.proposito
            avisos.append("Se modifica el Propósito de la página; revise que el texto completo siga siendo correcto.")
        else:
            entrada = doc.buscar(op.seccion, op.entrada)
            anterior = entrada.texto if entrada else ""
        base = origen | _numeros(anterior) | (_numeros(serializar(doc)) if op.accion == "agregar" else set())
        nuevas = sorted(_numeros(op.texto) - base, key=lambda n: float(n))
        if nuevas:
            avisos.append(f"«{op.entrada or op.seccion}»: las cifras {', '.join(nuevas)} no están en la nota "
                          "ni en el texto anterior; confirme que son correctas.")
        if op.accion == "modificar" and anterior and _pierde_contenido(doc, op):
            avisos.append(f"«{op.entrada or op.seccion}»: el texto nuevo omite buena parte del anterior; "
                          "revise que no se haya perdido información.")
    avisos += _avisos_nombradas_sin_tocar(doc, ops, nota, cambios_pbip)
    avisos += _avisos_relacionadas(doc, ops, nota)
    return avisos


def _avisos_nombradas_sin_tocar(doc: Documento, ops: list[Operacion], nota: str, cambios_pbip) -> list[str]:
    """La nota trae todas las palabras del nombre de una entrada que no se modificó."""
    palabras, _ = _referencia(nota, cambios_pbip)
    tocadas = {(op.seccion, normalizar_nombre(op.entrada)) for op in ops}
    de_pagina = _tokens(doc.pagina)
    avisos = []
    for seccion, entradas in doc.secciones.items():
        if seccion == SECCION_HISTORIAL:
            continue
        for e in entradas:
            nombre = [t for t in _tokens(e.nombre) if t not in _NEUTRAS]
            if all(any(_coinciden(t, p) for p in de_pagina) for t in nombre):
                continue  # «Egresos del día» en EGRESOS DIA: nombrar la página no la nombra a ella
            if (len(nombre) >= 2 and (seccion, normalizar_nombre(e.nombre)) not in tocadas
                    and all(_presente(t, palabras) for t in nombre)):
                avisos.append(f"La nota nombra «{e.nombre}» ({seccion}), que no se modificó; revise si también cambia.")
    return avisos[:2]


def _avisos_relacionadas(doc: Documento, ops: list[Operacion], nota: str) -> list[str]:
    """Entradas que no se tocan pero mencionan lo mismo que la nota con
    palabras poco comunes en la página (p. ej. «IIP», «IIS»): pueden haber
    quedado desactualizadas."""
    tocadas = {(op.seccion, normalizar_nombre(op.entrada)) for op in ops}
    entradas = [(s, e) for s, lista in doc.secciones.items() if s != SECCION_HISTORIAL for e in lista]
    frecuencia: dict[str, int] = {}
    for _, e in entradas:
        for t in set(_tokens(e.nombre + " " + e.texto)):
            frecuencia[t] = frecuencia.get(t, 0) + 1
    raras = {t for t in _tokens(nota)
             if len(t) >= 3 and not t.isdigit() and t not in _NEUTRAS and t not in _CAMBIO_GENERICO
             and t not in _VACIAS and t not in _GENERICAS and t not in _ESTRUCTURA
             and 0 < frecuencia.get(t, 0) <= 2 and not any(_coinciden(t, p) for p in _tokens(doc.pagina))}
    avisos = []
    for seccion, e in entradas:
        if (seccion, normalizar_nombre(e.nombre)) in tocadas:
            continue
        comunes = sorted(raras & set(_tokens(e.nombre + " " + e.texto)))
        if comunes:
            avisos.append(f"Revise también «{e.nombre}» ({seccion}): menciona {', '.join(comunes)}.")
    return avisos[:3]


@dataclass
class _Lectura:
    """Resultado de interpretar una respuesta del modelo."""
    json_ok: bool = False
    ops: list[Operacion] = field(default_factory=list)
    resumen: str = ""
    dudas: list[str] = field(default_factory=list)
    problemas: list[str] = field(default_factory=list)   # justifican un reintento
    sin_cambio: list[str] = field(default_factory=list)  # «modificar» que deja el texto igual
    sin_respaldo: list[str] = field(default_factory=list)  # cambios que la nota no pide
    pierde: list[str] = field(default_factory=list)  # «modificar» que pierde buena parte del texto
    confirmar: list[str] = field(default_factory=list)  # respaldo indirecto: se acepta con aviso
    avisos: list[str] = field(default_factory=list)


def _interpretar(doc: Documento, respuesta_texto: str, nota: str, cambios_pbip=None) -> _Lectura:
    lectura = _Lectura()
    data = _extraer_json(respuesta_texto)
    if data is None:
        lectura.problemas.append("La respuesta no es un JSON válido.")
        return lectura
    crudas = data.get("operaciones")
    if crudas is None:
        crudas = []
    if isinstance(crudas, dict):
        crudas = [crudas]
    if not isinstance(crudas, list):
        lectura.problemas.append("«operaciones» debe ser una lista.")
        return lectura
    lectura.json_ok = True
    if data.get("_truncado"):
        lectura.problemas.append("La respuesta quedó cortada: incluye solo las entradas que cambian, sin copiar "
                                 "las demás.")
    dudas = data.get("dudas") or []
    if isinstance(dudas, str):
        dudas = [dudas]
    lectura.dudas = [str(d).strip() for d in dudas if str(d).strip()]
    lectura.resumen = re.sub(r"\s+", " ", str(data.get("resumen") or "")).strip()

    palabras, cifras = _referencia(nota, cambios_pbip)
    quita = bool(_QUITAR_RE.search(normalizar_nombre(nota + " " + _texto_pbip(cambios_pbip))))
    atributo = _atributo_quitado(nota)
    vistas = set()
    for cruda in crudas:
        if not isinstance(cruda, dict):
            lectura.problemas.append("Una operación no es un objeto JSON.")
            continue
        op, problema, sin_cambio = _resolver(doc, cruda, lectura.avisos, quita)
        if problema:
            lectura.problemas.append(problema)
        if op is None and not sin_cambio:
            continue
        nombre = (op.entrada if op else "") or SECCION_TEXTO
        if sin_cambio:
            lectura.sin_cambio.append(nombre)
            continue
        respaldo = _respaldo(doc, op, palabras, cifras, quita)
        if not respaldo:
            lectura.sin_respaldo.append(nombre)
            continue
        if respaldo == "indirecto":
            lectura.confirmar.append(nombre)
        clave = (op.seccion, normalizar_nombre(op.entrada))
        if clave in vistas:
            lectura.avisos.append(f"Operación repetida sobre «{nombre}»; se dejó la primera.")
            continue
        vistas.add(clave)
        if op.accion == "eliminar" and atributo and not any(_coinciden(atributo, t) for t in _tokens(op.entrada)):
            lectura.problemas.append(
                f"La nota quita un {atributo} de un elemento, no el elemento completo: no elimines «{nombre}»; "
                f"modifica la entrada de ese elemento para que ya no tenga ese {atributo}.")
            continue
        lectura.ops.append(op)

    # Si la nota nombra una entrada concreta, no se tocan otras parecidas que
    # no nombra («semáforo de egresos» no es «semáforo en espera de egreso»).
    nombradas = [op for op in lectura.ops if op.accion != "agregar" and _nombrada(op, palabras)]
    if nombradas:
        for op in [op for op in lectura.ops if op.accion != "agregar" and op not in nombradas]:
            lectura.ops.remove(op)
            lectura.avisos.append(f"Se descartó el cambio en «{op.entrada or op.seccion}»: la nota no la nombra; "
                                  "revise si también cambió.")
    lectura.pierde = [op.entrada or SECCION_TEXTO for op in lectura.ops
                      if op.accion == "modificar" and _pierde_contenido(doc, op)]
    for op in lectura.ops:
        if op.accion == "modificar" and _UNIDAD_RE.search(normalizar_nombre(_texto_anterior(doc, op))) \
                and not _UNIDAD_RE.search(normalizar_nombre(op.texto)):
            lectura.problemas.append(f"El texto nuevo de «{op.entrada or SECCION_TEXTO}» perdió la unidad "
                                     "(minutos u horas): escribe cada tiempo con su unidad, en frases completas.")
    return lectura


_UNIDAD_RE = re.compile(r"\b(minutos?|horas?|min|h)\b")


def _nombrada(op: Operacion, palabras: list[str]) -> bool:
    """La nota trae todas las palabras del nombre de la entrada."""
    if op.seccion == SECCION_TEXTO:
        return False
    nombre = [t for t in _tokens(op.entrada) if t not in _NEUTRAS]
    return bool(nombre) and all(_presente(t, palabras) for t in nombre)


# «quité el filtro de ...», «le saqué la columna ...»: se quita algo DE un elemento.
_QUITAR_ATRIBUTO_RE = re.compile(
    r"\b(?:quit|elimin|borr|saq|sac|retir|ocult)\w*\s+(?:(?:el|la|los|las|un|una|le|les|lo)\s+)*"
    r"(filtro|columna|campo|color|exclusion|condicion|tooltip|titulo|etiqueta|borde|formato)s?\b")


def _atributo_quitado(texto: str) -> str:
    m = _QUITAR_ATRIBUTO_RE.search(normalizar_nombre(texto))
    return m.group(1) if m else ""


def _texto_anterior(doc: Documento, op: Operacion) -> str:
    if op.seccion == SECCION_TEXTO:
        return doc.proposito
    entrada = doc.buscar(op.seccion, op.entrada)
    return entrada.texto if entrada else ""


def _pierde_contenido(doc: Documento, op: Operacion) -> bool:
    """El texto nuevo conserva menos de la mitad de las palabras del anterior."""
    viejos = {_raiz(t) for t in _significativos(_texto_anterior(doc, op)) if len(t) > 3}
    nuevos = {_raiz(t) for t in _significativos(op.texto) if len(t) > 3}
    return len(viejos) >= 6 and len(viejos & nuevos) / len(viejos) < 0.5


def _correccion(lectura: _Lectura, nota: str) -> str:
    """Mensaje para el reintento: qué estuvo mal en la respuesta anterior."""
    partes = list(lectura.problemas)
    for nombre in lectura.sin_cambio:
        partes.append(f"La operación sobre «{nombre}» deja el texto igual que antes: escribe el texto con el "
                      "cambio de la nota ya aplicado, o usa eliminar si la nota pide quitarla.")
    for nombre in lectura.sin_respaldo:
        partes.append(f"El texto nuevo de «{nombre}» no refleja lo que dice la nota («{nota.strip()}»). Si esa "
                      "es la entrada correcta, reescríbela aplicando la nota; si no lo es, no la incluyas.")
    for nombre in lectura.pierde:
        partes.append(f"El texto nuevo de «{nombre}» perdió información del texto actual: parte del texto actual "
                      "completo y cambia solo lo que dice la nota.")
    return ("Tu respuesta tiene estos problemas: " + " ".join(partes)
            + " Corrígela. Usa solo las secciones y los nombres de entradas de la lista. Si la nota no permite "
              "saber qué cambiar, deja operaciones vacío y pregunta en dudas. Responde solo con el JSON.")


# Valor anterior que la nota afirma («subí el rojo de 120 a 150», «estaba en 30»).
_VALOR_ANTERIOR_RES = [
    re.compile(r"\b(?:sub|baj|cambi|pas|mov|ajust|modific|aument|reduj|disminu)\w*\b[^.\d]{0,60}?"
               r"\bde (\d+(?:[.,]\d+)?) a \d"),
    re.compile(r"\b(?:estaba|era|antes)\s+(?:en\s+|de\s+)?(\d+(?:[.,]\d+)?)"),
    re.compile(r"\ben (?:vez|lugar) de (\d+(?:[.,]\d+)?)"),
    re.compile(r"\bya no (?:(?:es|era|esta|estaba|en|de)\s+)*(\d+(?:[.,]\d+)?)"),
]

# Palabras que no identifican un elemento concreto de la página (estructura
# de cualquier tablero y verbos comunes de las notas).
_ESTRUCTURA = {
    "filtro", "filtros", "tabla", "tablas", "visual", "visuales", "grafico", "graficos", "columna", "columnas",
    "campo", "campos", "pagina", "tablero", "boton", "botones", "dato", "datos", "valor", "valores",
    "usa", "usan", "uso", "muestra", "muestran", "mostrar", "aparece", "aparecen", "existe", "existen", "sirve",
    "hay", "tiene", "tienen", "esta", "estan", "queda", "quedan", "entra", "entran", "sale", "salen", "va", "van",
    "quite", "quitamos", "quitar", "quito", "elimine", "eliminamos", "eliminar", "borre", "borramos", "borrar",
    "saque", "sacamos", "retire", "oculte", "removi", "ahora", "nunca", "mas",
}


def _contradicciones(doc: Documento, nota: str) -> list[str]:
    """Dudas que se detectan sin el modelo: la nota afirma un valor anterior
    que el documento no tiene, o quita algo que la página no documenta."""
    dudas = []
    norm = normalizar_nombre(nota)
    texto_doc = serializar(doc)
    cifras_doc = _cifras_cerca(_numeros(texto_doc))
    for regex in _VALOR_ANTERIOR_RES:
        for valor in regex.findall(norm):
            valor = valor.replace(",", ".")
            if valor not in cifras_doc:
                dudas.append(f"La nota dice que el valor anterior era {valor}, pero la documentación de "
                             f"{doc.pagina} no tiene ese valor. ¿Cuál es el valor correcto, o el cambio es en otra página?")
    vocab = set(_tokens(texto_doc)) | {t for s in secciones_para(doc.meta) for t in _tokens(s)}
    de_pagina = _tokens(doc.pagina)
    vistos = set()
    for objeto in _objetos_quitados(norm):
        if (objeto in vistos or len(objeto) < 4 or objeto.isdigit() or objeto in _NEUTRAS
                or objeto in _CAMBIO_GENERICO or objeto in _VACIAS or objeto in _GENERICAS or objeto in _ESTRUCTURA
                or _QUITAR_RE.fullmatch(objeto) or any(_coinciden(objeto, p) for p in de_pagina)):
            continue
        vistos.add(objeto)
        if any(_coinciden(objeto, v) for v in vocab) or difflib.get_close_matches(objeto, vocab, n=1, cutoff=0.85):
            continue
        dudas.append(f"La nota habla de quitar «{objeto}», pero eso no aparece en la documentación de "
                     f"{doc.pagina}. ¿Es otra página o falta documentarlo?")
    return dudas


def _objetos_quitados(norm: str) -> list[str]:
    """Palabras que siguen a cada verbo de quitar (hasta 4): lo que la nota dice
    que se quitó («le quité el semáforo a la tarjeta» -> semaforo, tarjeta)."""
    objetos = []
    for m in _QUITAR_RE.finditer(norm):
        objetos += _tokens(norm[m.end():])[:4]
    return objetos


def _resumen_por_defecto(ops: list[Operacion]) -> str:
    verbos = {"agregar": "Se agregó", "modificar": "Se modificó", "eliminar": "Se eliminó"}
    partes = [f"{verbos[op.accion]} «{op.entrada or op.seccion}» en {op.seccion}" for op in ops]
    return "; ".join(partes) + "."


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def proponer_cambio(nota, source_group, pagina=None, llm=None, cambios_pbip=None, raiz=None) -> Propuesta:
    """Propuesta de cambio para la nota (no escribe archivos). `llm`: proveedor
    con `chat(messages, ...)` (por defecto MedGemmaProvider). `raiz`: carpeta
    base de la documentación (pruebas; por defecto data/raw o DOCS_MD_ROOT)."""
    nota = str(nota or "").strip()
    propuesta = Propuesta(nota=nota, source_group=source_group)
    if not nota and not cambios_pbip:
        propuesta.errores.append("La nota está vacía.")
        return propuesta
    llamar = _llamador(llm, propuesta)

    # 0. Nota sin contenido («arreglé lo de egresos»): se pregunta sin llamar al modelo.
    if not cambios_pbip:
        paginas = repositorio.listar_paginas(source_group, raiz)
        if paginas and nota_sin_contenido(nota, [p["pagina"] for p in paginas]):
            propuesta.estado = "requiere_aclaracion"
            if pagina:
                propuesta.pagina = str(pagina)
            else:
                puntajes = puntuar_paginas(nota, _cargar_paginas(source_group, raiz))
                propuesta.candidatas = [p["pagina"] for p in puntajes if p["puntaje"] > 0][:5]
            propuesta.dudas.append("La nota no dice qué cambió. ¿Qué visual, indicador, regla o filtro cambió "
                                   "y cuál es el valor o comportamiento nuevo?")
            return propuesta

    # 1. Página
    if pagina:
        propuesta.metodo_pagina = "indicada"
    else:
        eleccion = elegir_pagina(nota, source_group, cambios_pbip=cambios_pbip, raiz=raiz,
                                 propuesta=propuesta, llamar=llamar)
        propuesta.candidatas = eleccion["candidatas"]
        if not eleccion["candidatas"] and not eleccion["pagina"]:
            propuesta.errores.append(f"No hay documentación .md para «{source_group}».")
            return propuesta
        if eleccion.get("error"):
            propuesta.errores.append(eleccion["error"])
            return propuesta
        if not eleccion["pagina"]:
            propuesta.estado = "requiere_aclaracion"
            if eleccion.get("sugerida"):
                propuesta.dudas.append(f"La nota no dice en qué página fue el cambio. ¿Es {eleccion['sugerida']}? "
                                       "Otras posibles: " + ", ".join(eleccion["candidatas"][1:6]) + ".")
            else:
                propuesta.dudas.append("¿A qué página del tablero se refiere el cambio? Posibles: "
                                       + ", ".join(eleccion["candidatas"][:6]) + ".")
            return propuesta
        pagina = eleccion["pagina"]
        propuesta.metodo_pagina = eleccion["metodo"]
        for otra in eleccion["otras"][:2]:
            propuesta.avisos.append(f"La nota también menciona la página {otra}; ese cambio necesita otra propuesta.")
    try:
        ruta = repositorio.ruta_pagina(source_group, pagina, raiz)
        propuesta.antes = ruta.read_text(encoding="utf-8").replace("\r\n", "\n")
        doc = parsear(propuesta.antes)
    except (repositorio.ErrorRepositorio, OSError, ErrorFormato) as exc:
        propuesta.pagina = str(pagina)
        propuesta.errores.append(str(exc))
        return propuesta
    propuesta.pagina = doc.pagina
    if not propuesta.candidatas:
        propuesta.candidatas = [doc.pagina]

    # 1b. Contradicciones evidentes con el documento: se pregunta sin llamar al modelo.
    contradicciones = _contradicciones(doc, nota)
    if contradicciones:
        propuesta.estado = "requiere_aclaracion"
        propuesta.dudas += contradicciones
        return propuesta

    # 2. Operaciones (con un reintento si la respuesta no sirve)
    mensajes = _mensajes_operaciones(doc, nota, cambios_pbip)
    esquema = _esquema_operaciones(doc)
    lectura = _Lectura()
    for intento in range(2):
        respuesta = llamar(mensajes, esquema, MAX_TOKENS_OPERACIONES, 0.0 if intento == 0 else TEMPERATURA_REINTENTO)
        texto = respuesta.get("answer") or ""
        propuesta.llm_raw += f"[operaciones{' reintento' if intento else ''}] {texto or respuesta.get('error') or ''}\n"
        if respuesta.get("status") != "success":
            propuesta.errores.append(_mensaje_fallo(respuesta))
            return propuesta
        lectura = _interpretar(doc, texto, nota, cambios_pbip)
        if lectura.ops and not lectura.problemas:
            try:
                nuevo = aplicar_operaciones(doc, lectura.ops, lectura.resumen or _resumen_por_defecto(lectura.ops))
                lectura.problemas += validar(nuevo)
            except ErrorOperacion as exc:
                lectura.problemas.append(str(exc))
        hay_que_corregir = bool(lectura.problemas) or bool(lectura.pierde) or (
            not lectura.ops and not lectura.dudas and (lectura.sin_cambio or lectura.sin_respaldo))
        if not hay_que_corregir or (not lectura.ops and lectura.dudas):
            break
        if intento == 0:
            mensajes = mensajes + [
                {"role": "assistant", "content": texto},
                {"role": "user", "content": _correccion(lectura, nota)},
            ]

    ops = lectura.ops
    propuesta.resumen = lectura.resumen
    propuesta.dudas += lectura.dudas
    propuesta.avisos += lectura.avisos
    propuesta.avisos += [f"Se descartó el cambio en «{n}»: la nota no lo pide." for n in lectura.sin_respaldo]
    propuesta.avisos += [f"«{n}»: el texto nuevo no usa las palabras de la nota; confirme que refleja lo que "
                         "cambió." for n in lectura.confirmar if any(n == (op.entrada or SECCION_TEXTO) for op in lectura.ops)]

    if not lectura.json_ok:
        propuesta.estado = "error"
        propuesta.errores += ["MedGemma no devolvió operaciones válidas tras un reintento."] + lectura.problemas
        return propuesta
    if not ops:
        # Nada aplicable: no se adivina, se pregunta.
        propuesta.estado = "requiere_aclaracion"
        if not propuesta.dudas:
            propuesta.dudas += lectura.problemas
        if not propuesta.dudas:
            propuesta.dudas.append("La nota no describe un cambio concreto en la documentación de "
                                   f"{doc.pagina}. ¿Qué cambió exactamente (visual, indicador, regla o filtro)?")
        return propuesta
    if lectura.problemas:
        # Quedan operaciones válidas: las inválidas se descartan y se avisa.
        propuesta.avisos += [f"Se descartó una operación: {p}" for p in lectura.problemas]

    if not propuesta.resumen:
        propuesta.resumen = _resumen_por_defecto(ops)
    try:
        nuevo = aplicar_operaciones(doc, ops, propuesta.resumen)
    except ErrorOperacion as exc:
        propuesta.errores.append(str(exc))
        return propuesta
    errores_formato = validar(nuevo)
    if errores_formato:
        propuesta.errores += errores_formato
        return propuesta
    propuesta.operaciones = ops
    propuesta.despues = serializar(nuevo)
    propuesta.diff = diferencias(propuesta.antes, propuesta.despues, repositorio.archivo_para(doc))
    propuesta.avisos += _avisos_contenido(doc, ops, nota, cambios_pbip)
    # Con operaciones válidas y dudas del modelo, la propuesta se muestra pero
    # no se aplica hasta aclarar: no se adivina.
    propuesta.estado = "requiere_aclaracion" if propuesta.dudas else "lista"
    return propuesta


def aplicar_propuesta(propuesta: Propuesta, autor: str, raiz=None):
    """Guarda la propuesta aprobada y devuelve la ruta del archivo. Falla si la
    propuesta no está «lista» o si el archivo cambió desde que se propuso."""
    if propuesta.estado != "lista":
        raise ErrorActualizacion(f"Solo se aplican propuestas en estado «lista» (esta está en «{propuesta.estado}»).")
    if not propuesta.operaciones:
        raise ErrorActualizacion("La propuesta no tiene operaciones.")
    try:
        ruta = repositorio.ruta_pagina(propuesta.source_group, propuesta.pagina, raiz)
        actual = ruta.read_text(encoding="utf-8").replace("\r\n", "\n")
    except (repositorio.ErrorRepositorio, OSError) as exc:
        raise ErrorActualizacion(str(exc)) from exc
    if actual != propuesta.antes.replace("\r\n", "\n"):
        raise ErrorActualizacion(
            f"La documentación de {propuesta.pagina} cambió después de crear la propuesta; vuelva a proponer el cambio.")
    try:
        nuevo = aplicar_operaciones(parsear(actual), propuesta.operaciones, propuesta.resumen, autor=autor)
        return repositorio.guardar_pagina(propuesta.source_group, nuevo, raiz)
    except (ErrorOperacion, ErrorFormato, repositorio.ErrorRepositorio) as exc:
        raise ErrorActualizacion(str(exc)) from exc
