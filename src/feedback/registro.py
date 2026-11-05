"""
Registro de calificaciones de respuestas (modo diagnóstico).

Cada turno del asistente se resume en un *snapshot* saneado y, al calificarlo,
se añade una línea JSON a ``data/feedback/calificaciones.jsonl`` (carpeta
sobreescribible con la variable de entorno ``FEEDBACK_DIR``).

Saneamiento por LISTA BLANCA: el snapshot construye un dict nuevo con solo los
campos permitidos. Nunca se copia el ``result`` del motor ni se «borran claves»
de él: lo que no se nombra aquí no llega al log (filas, DAX, valores de
filtros, texto de chunks, razonamientos...). Es un módulo puro: no consulta
Power BI ni ningún LLM.
"""
import functools
import json
import math
import os
import re
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

try:  # candado entre procesos (Windows); sin msvcrt solo queda el de hilos
    import msvcrt
except ImportError:  # pragma: no cover
    msvcrt = None

RAIZ = Path(__file__).resolve().parents[2]
NOMBRE_LOG = "calificaciones.jsonl"
VERSION = 1
CALIFICACIONES = ("buena", "mala")
MAX_RESPUESTA = 1500
MAX_RESPUESTA_TABLA = 400
MAX_ERROR = 200
MAX_HISTORIAL = 6

_SEPARADOR_NUM = r"[ .\- ]"
_SECUENCIA_NUM = re.compile(r"\d(?:" + _SEPARADOR_NUM + r"?\d)+")
_INVISIBLES = re.compile("[​⁠﻿]")
_VINETA = re.compile(r"^\s*(?:[-*•]\s|\d+[.)]\s)")
_IDENTIFICADOR = re.compile(r"^[A-Za-z_][\w.]*$")
_candado_hilos = threading.Lock()

MAX_PREGUNTA = 1000
MAX_OPCION = 200
MAX_OPCIONES = 20
MAX_ESPERADO = 2000
MAX_TEXTO_HISTORIAL = 1500
MAX_IDENTIFICADOR = 200
CLAVES_SNAPSHOT = (
    "pregunta", "pregunta_reescrita", "via", "estado", "ruta", "etapa", "informe", "tablero",
    "modelo_semantico", "metrica", "plan_consulta", "contexto_fuentes", "modo_sintesis",
    "retrieval_mode", "not_found_reason", "fuentes", "opciones_contrapregunta", "respuesta", "error",
    "fecha_turno", "tablero_esperado",
)


def ruta_log() -> Path:
    carpeta = os.environ.get("FEEDBACK_DIR")
    base = Path(carpeta) if carpeta else RAIZ / "data" / "feedback"
    return base / NOMBRE_LOG


# ---------------------------------------------------------------- saneamiento

def _es_fecha_o_periodo(grupos: list[str]) -> bool:
    """AAAAMM / AAAAMMDD compactos, AAAA-MM-DD / DD-MM-AAAA o varios años sueltos: no son cédulas."""
    if not all(g.isascii() for g in grupos):
        return False
    try:
        if len(grupos) == 1:
            g = grupos[0]
            if len(g) == 6 and g.startswith("20"):
                return 1 <= int(g[4:]) <= 12
            if len(g) == 8 and g.startswith("20"):
                datetime(int(g[:4]), int(g[4:6]), int(g[6:]))
                return True
            return False
        if all(len(g) == 4 and g[:2] in ("19", "20") for g in grupos):
            return True
        if len(grupos) == 3:
            for d, m, y in ((grupos[2], grupos[1], grupos[0]), (grupos[0], grupos[1], grupos[2])):
                if len(y) == 4 and y[:2] in ("19", "20") and len(m) <= 2 and len(d) <= 2:
                    datetime(int(y), int(m), int(d))
                    return True
    except ValueError:
        return False
    return False


def _enmascarar_numero(coincidencia) -> str:
    texto = coincidencia.group(0)
    if sum(c.isdigit() for c in texto) < 6:
        return texto
    if _es_fecha_o_periodo(re.split(_SEPARADOR_NUM, texto)):
        return texto
    return "[NUM]"


def _linea_descartable(linea: str, estricto: bool) -> bool:
    if linea.lstrip().startswith("|"):
        return True
    return estricto and ("|" in linea or bool(_VINETA.match(linea)))


def _sin_tablas(texto: str, estricto: bool = False) -> str:
    return "\n".join(l for l in texto.splitlines() if not _linea_descartable(l, estricto))


def _limpiar(valor, maximo: int | None = None, estricto: bool = False) -> str:
    """Texto libre: sin líneas de tabla (y en modo estricto sin `|` ni viñetas), números largos -> [NUM]."""
    texto = "" if valor is None else str(valor)
    texto = texto.encode("utf-8", "replace").decode("utf-8")  # surrogates sueltos
    texto = _INVISIBLES.sub("", texto)
    texto = _SECUENCIA_NUM.sub(_enmascarar_numero, _sin_tablas(texto, estricto)).strip()
    return texto[:maximo] if maximo else texto


def _primera_linea(valor, maximo: int) -> str:
    texto = _limpiar(valor, estricto=True)
    return _limpiar(texto.splitlines()[0], maximo) if texto else ""


def _dict(valor) -> dict:
    return valor if isinstance(valor, dict) else {}


def _lista(valor) -> list:
    return valor if isinstance(valor, list) else []


def _texto_corto(valor):
    """Identificadores (modelo, tablero...): solo str/int/float, enmascarado y acotado; otra cosa -> None."""
    if isinstance(valor, bool) or not isinstance(valor, (str, int, float)):
        return None
    if isinstance(valor, float) and not math.isfinite(valor):
        return None
    return _limpiar(valor, MAX_IDENTIFICADOR)


def _numero(valor):
    """Puntaje JSON estándar a 4 decimales; None si no es un número finito."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not math.isfinite(valor):
        return None
    return round(valor, 4)


def _nombre_fuente(valor):
    """Una ruta absoluta local se reduce al nombre de archivo; una relativa se conserva."""
    if not isinstance(valor, str) or not valor:
        return _texto_corto(valor)
    ruta = valor.replace("\\", "/")
    if re.match(r"^[A-Za-z]:", ruta) or ruta.startswith("/"):
        ruta = ruta.rstrip("/").rsplit("/", 1)[-1]
    return _texto_corto(ruta)


def _filtros(filtros) -> list[dict]:
    salida = []
    for f in _lista(filtros):
        f = _dict(f)
        if f.get("value") not in (None, ""):
            n = 1
        else:
            n = len(_lista(f.get("values")))
        salida.append({"tipo": _texto_corto(f.get("type")), "tabla": _texto_corto(f.get("table")),
                       "columna": _texto_corto(f.get("column")), "n_valores": n})
    return salida


def _plan_consulta(plan) -> dict | None:
    plan = _dict(plan)
    if not plan:
        return None
    metrica = plan.get("metric")
    if isinstance(metrica, dict):
        metrica = {"label": _texto_corto(metrica.get("label")),
                   "metric_id": _texto_corto(metrica.get("metric_id"))}
    else:
        metrica = _texto_corto(metrica)
    return {
        "metric": metrica,
        "report": _texto_corto(plan.get("report")),
        "semantic_model": _texto_corto(plan.get("semantic_model")),
        "group_by": [{"tabla": _texto_corto(_dict(g).get("table")),
                      "columna": _texto_corto(_dict(g).get("column"))} for g in _lista(plan.get("group_by"))],
        "mode": _texto_corto(plan.get("mode")),
        "filtros": _filtros(plan.get("filters")),
    }


def _contexto_fuentes(contexto) -> dict | None:
    contexto = _dict(contexto)
    if not contexto:
        return None
    candidatos = []
    for c in _lista(contexto.get("candidates")):
        c = _dict(c)
        candidatos.append({
            "id": _nombre_fuente(c.get("id") or c.get("semantic_model")),
            "modelo": _texto_corto(c.get("semantic_model")),
            "tablero": _texto_corto(c.get("dashboard")),
            "score": _numero(c.get("score")),
        })
    return {
        "semantic_model": _texto_corto(contexto.get("semantic_model")),
        "routing_strength": _texto_corto(contexto.get("routing_strength")),
        "reason": _texto_corto(contexto.get("reason")),
        "status": _texto_corto(contexto.get("status")),
        "candidates": candidatos,
    }


def _fuentes(fuentes) -> list[dict]:
    salida = []
    for s in _lista(fuentes):
        s = _dict(s)
        salida.append({
            "id": _nombre_fuente(s.get("id") or s.get("relative_path") or s.get("source_file")),
            "coleccion": _texto_corto(s.get("collection")),
            "tablero": _texto_corto(s.get("dashboard")),
            "tipo_chunk": _texto_corto(s.get("chunk_type")),
            "puntaje": _numero(s["score"] if "score" in s else s.get("final_score")),
        })
    return salida


def _respuesta(result: dict, respuesta) -> str:
    es_tabla = result.get("route") == "powerbi" and (
        result.get("result_type") == "table" or bool(result.get("detail")))
    if es_tabla:
        return _primera_linea(respuesta, MAX_RESPUESTA_TABLA)
    return _limpiar(respuesta, MAX_RESPUESTA, estricto=True)


def _error(error) -> str | None:
    """Solo el nombre del tipo de excepción: el mensaje puede citar valores reales."""
    if not error:
        return None
    nombre = str(error).split(":", 1)[0].strip()
    if not _IDENTIFICADOR.match(nombre):
        return "Error"
    return nombre[:MAX_ERROR]


def snapshot_turno(result: dict, respuesta: str, pregunta: str, via: str, opciones: list[str]) -> dict:
    """Resumen saneado (lista blanca) de un turno; tolera un ``result`` parcial."""
    result = _dict(result)
    return {
        "pregunta": _limpiar(pregunta, MAX_PREGUNTA),
        "pregunta_reescrita": (_limpiar(result["question"], MAX_PREGUNTA)
                               if isinstance(result.get("question"), str) and result["question"] else None),
        "via": _texto_corto(via),
        "estado": _texto_corto(result.get("status")),
        "ruta": _texto_corto(result.get("route")),
        "etapa": _texto_corto(result.get("stage")),
        "informe": _texto_corto(result.get("report")),
        "tablero": _texto_corto(result.get("dashboard")),
        "modelo_semantico": _texto_corto(result.get("semantic_model")),
        "metrica": _texto_corto(result.get("metric")),
        "plan_consulta": _plan_consulta(result.get("query_plan")),
        "contexto_fuentes": _contexto_fuentes(result.get("source_context")),
        "modo_sintesis": _texto_corto(result.get("synthesis_mode")),
        "retrieval_mode": _texto_corto(result.get("retrieval_mode")),
        "not_found_reason": _texto_corto(result.get("not_found_reason")),
        "fuentes": _fuentes(result.get("sources")),
        "opciones_contrapregunta": [_limpiar(o, MAX_OPCION) for o in _lista(opciones)[:MAX_OPCIONES] if isinstance(o, str)],
        "respuesta": _respuesta(result, respuesta),
        "error": _error(result.get("error")),
        "fecha_turno": datetime.now().isoformat(timespec="seconds"),
        "tablero_esperado": None,  # reservado para una fase 2; sin UI
    }


# ------------------------------------------------------------------- registro

@functools.lru_cache(maxsize=1)
def _commit_codigo() -> str:
    try:
        salida = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=RAIZ, capture_output=True,
                                text=True, timeout=5, check=True)
        return salida.stdout.strip()
    except Exception:
        return ""


def _mensaje_historial(mensaje) -> dict:
    mensaje = _dict(mensaje)
    rol = _texto_corto(mensaje.get("rol"))
    if rol in ("assistant", "asistente"):
        texto = _primera_linea(mensaje.get("texto"), MAX_TEXTO_HISTORIAL)
    else:
        texto = _limpiar(mensaje.get("texto"), MAX_TEXTO_HISTORIAL, estricto=True)
    return {"rol": rol, "texto": texto}


def construir_registro(snapshot: dict, historial: list[dict], calificacion: str, esperado: str,
                       id_sesion: str, indice: int) -> dict:
    if calificacion not in CALIFICACIONES:
        raise ValueError(f"calificación inválida: {calificacion!r} (use 'buena' o 'mala')")
    esperado_limpio = _limpiar(esperado, MAX_ESPERADO)
    if calificacion == "mala" and not esperado_limpio:
        raise ValueError("una calificación «mala» requiere decir qué se esperaba")
    ultimos = [_mensaje_historial(m) for m in _lista(historial)[-MAX_HISTORIAL:]]
    snapshot = _dict(snapshot)
    registro = {k: snapshot[k] for k in CLAVES_SNAPSHOT if k in snapshot}
    registro.update({
        "version": VERSION,
        "id_turno": f"{id_sesion}:{indice}",
        "id_sesion": id_sesion,
        "fecha_calificacion": datetime.now().isoformat(timespec="seconds"),
        "commit_codigo": _commit_codigo(),
        "historial": ultimos,
        "calificacion": calificacion,
        "esperado": esperado_limpio,
    })
    return registro


# ------------------------------------------------------------------- escritura

def _bloquear(archivo, intentos: int = 200, espera: float = 0.025) -> None:
    for i in range(intentos):
        try:
            archivo.seek(0)  # siempre el mismo byte, haya o no contenido en el .lock
            msvcrt.locking(archivo.fileno(), msvcrt.LK_NBLCK, 1)
            return
        except OSError:
            if i == intentos - 1:
                raise
            time.sleep(espera)


def _desbloquear(archivo) -> None:
    """Libera el candado sin enmascarar una excepción previa (el SO lo libera al cerrar)."""
    try:
        archivo.seek(0)
        msvcrt.locking(archivo.fileno(), msvcrt.LK_UNLCK, 1)
    except OSError:
        pass


def _escribir(ruta: Path, datos: bytes) -> None:
    # Si una escritura anterior quedó cortada (sin salto final), no se pega a ella.
    if ruta.exists() and ruta.stat().st_size > 0:
        with open(ruta, "rb") as lectura:
            lectura.seek(-1, os.SEEK_END)
            if lectura.read(1) != b"\n":
                datos = b"\n" + datos
    with open(ruta, "ab") as destino:
        destino.write(datos)
        destino.flush()


def guardar(registro: dict, ruta: Path | None = None) -> None:
    """Añade UNA línea JSON (una sola ``write``); candado de hilos y de procesos."""
    ruta = Path(ruta) if ruta else ruta_log()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    datos = (json.dumps(registro, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8", "replace")
    with _candado_hilos:
        if msvcrt is None:
            _escribir_con_reintentos(ruta, datos)
            return
        with open(ruta.with_name(ruta.name + ".lock"), "a+b") as candado:
            _bloquear(candado)
            try:
                _escribir_con_reintentos(ruta, datos)
            finally:
                _desbloquear(candado)


def _escribir_con_reintentos(ruta: Path, datos: bytes, intentos: int = 3) -> None:
    for i in range(intentos):
        try:
            _escribir(ruta, datos)
            return
        except PermissionError:
            if i == intentos - 1:
                raise
            time.sleep(0.05 + 0.05 * i / max(intentos - 1, 1))
