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

_NUMERO_LARGO = re.compile(r"\d{6,}")
_candado_hilos = threading.Lock()


def ruta_log() -> Path:
    carpeta = os.environ.get("FEEDBACK_DIR")
    base = Path(carpeta) if carpeta else RAIZ / "data" / "feedback"
    return base / NOMBRE_LOG


# ---------------------------------------------------------------- saneamiento

def _sin_tablas(texto: str) -> str:
    return "\n".join(l for l in texto.splitlines() if not l.lstrip().startswith("|"))


def _limpiar(valor, maximo: int | None = None) -> str:
    """Texto libre: sin líneas de tabla, 6+ dígitos -> [NUM], recortado."""
    texto = _NUMERO_LARGO.sub("[NUM]", _sin_tablas("" if valor is None else str(valor)))
    texto = texto.strip()
    return texto[:maximo] if maximo else texto


def _dict(valor) -> dict:
    return valor if isinstance(valor, dict) else {}


def _lista(valor) -> list:
    return valor if isinstance(valor, list) else []


def _texto_corto(valor):
    """Identificadores (nombres de modelo, tablero...): cadena o None."""
    return None if valor is None else str(valor)


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
        score = c.get("score")
        candidatos.append({
            "id": _texto_corto(c.get("id") or c.get("semantic_model")),
            "modelo": _texto_corto(c.get("semantic_model")),
            "tablero": _texto_corto(c.get("dashboard")),
            "score": round(score, 4) if isinstance(score, (int, float)) else None,
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
        puntaje = s.get("score", s.get("final_score"))
        salida.append({
            "id": _texto_corto(s.get("id") or s.get("relative_path") or s.get("source_file")),
            "coleccion": _texto_corto(s.get("collection")),
            "tablero": _texto_corto(s.get("dashboard")),
            "tipo_chunk": _texto_corto(s.get("chunk_type")),
            "puntaje": round(puntaje, 4) if isinstance(puntaje, (int, float)) else None,
        })
    return salida


def _respuesta(result: dict, respuesta) -> str:
    texto = "" if respuesta is None else str(respuesta)
    es_tabla = result.get("route") == "powerbi" and (
        result.get("result_type") == "table" or bool(result.get("detail")))
    if es_tabla:
        sin_tablas = _sin_tablas(texto).strip()
        primera = sin_tablas.splitlines()[0] if sin_tablas else ""
        return _limpiar(primera, MAX_RESPUESTA_TABLA)
    return _limpiar(texto, MAX_RESPUESTA)


def snapshot_turno(result: dict, respuesta: str, pregunta: str, via: str, opciones: list[str]) -> dict:
    """Resumen saneado (lista blanca) de un turno; tolera un ``result`` parcial."""
    result = _dict(result)
    return {
        "pregunta": _limpiar(pregunta),
        "pregunta_reescrita": _limpiar(result["question"]) if result.get("question") else None,
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
        "opciones_contrapregunta": [_limpiar(o) for o in _lista(opciones)],
        "respuesta": _respuesta(result, respuesta),
        "error": _limpiar(result["error"], MAX_ERROR) if result.get("error") else None,
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


def construir_registro(snapshot: dict, historial: list[dict], calificacion: str, esperado: str,
                       id_sesion: str, indice: int) -> dict:
    if calificacion not in CALIFICACIONES:
        raise ValueError(f"calificación inválida: {calificacion!r} (use 'buena' o 'mala')")
    esperado_limpio = _limpiar(esperado)
    if calificacion == "mala" and not (esperado or "").strip():
        raise ValueError("una calificación «mala» requiere decir qué se esperaba")
    ultimos = [{"rol": _texto_corto(_dict(m).get("rol")), "texto": _limpiar(_dict(m).get("texto"))}
               for m in _lista(historial)[-MAX_HISTORIAL:]]
    registro = dict(snapshot)
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
            msvcrt.locking(archivo.fileno(), msvcrt.LK_NBLCK, 1)
            return
        except OSError:
            if i == intentos - 1:
                raise
            time.sleep(espera)


def _desbloquear(archivo) -> None:
    archivo.seek(0)
    msvcrt.locking(archivo.fileno(), msvcrt.LK_UNLCK, 1)


def _escribir(ruta: Path, datos: bytes) -> None:
    with open(ruta, "ab") as destino:
        destino.write(datos)
        destino.flush()


def guardar(registro: dict, ruta: Path | None = None) -> None:
    """Añade UNA línea JSON (una sola ``write``); candado de hilos y de procesos."""
    ruta = Path(ruta) if ruta else ruta_log()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    datos = (json.dumps(registro, ensure_ascii=False) + "\n").encode("utf-8")
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
