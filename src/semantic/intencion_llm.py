"""
Intención estructurada con el LLM (MedGemma) VALIDADA por el motor de reglas.

El motor de reglas (src/semantic/resolucion/*) no entiende paráfrasis («especialidades quirúrgicas
que más operaron» = cirugías por especialidad, top 5), comparaciones entre periodos («¿subió o bajó
de septiembre a octubre?») ni muchos sinónimos de negocio. Este módulo le pide al LLM SOLO la
intención, en un JSON con esquema estricto, eligiendo entre un catálogo ACOTADO que arman las etapas
existentes; luego el motor la valida contra el catálogo y la metadata reales:

  * el indicador debe estar en la lista que se le mostró (ids cortos I1, I2...);
  * cada columna (filtro o agrupación) debe estar en la lista Y entre las dimensiones del indicador
    elegido (`_metric_dimensions`: solo tablas que lo filtran);
  * cada valor se resuelve con el resolvedor de valores existente sobre el dominio real
    (`_resolve_value`: exacto o aproximado; familia «uci» -> UCI ADULTOS, UCI NEONATAL);
  * los periodos pasan por `PeriodParser` y deben estar en la pregunta (el LLM no inventa periodos);
  * la confianza debe superar INTENCION_LLM_CONFIANZA_MIN.

Si algo no valida, el plan del LLM se descarta ENTERO (queda en la traza) y se mantiene lo que
hacían las reglas: nunca se consulta algo que no pasó la validación.

Modo (variable INTENCION_LLM): `off` (nunca), `respaldo` (por defecto: solo cuando las reglas no
resuelven, contrapreguntarían o no saben armar una comparación de periodos) y `siempre`.

Presupuesto: a lo sumo dos llamadas (la segunda solo si el JSON salió inválido) dentro de
INTENCION_LLM_TIEMPO_S (3 s por defecto) en total, por la puerta común `src/llm/llm_gate.py`.
"""
import hashlib
import json
import os
import re
import tempfile
import threading
import time
from datetime import date, timedelta

from src.llm.presupuesto_tokens import num_predict
from src.providers.domain_cache import identifier_column
from src.semantic.period_parser import MONTHS as PERIOD_MONTHS, as_date
from src.semantic.resolucion.texto import (
    GENERIC_QUERY_WORDS,
    STOPWORDS,
    canonical_token,
    canonical_tokens,
    normalize_text,
)

MODOS = ("off", "respaldo", "siempre")
# Apagado por defecto: en el sondeo real (2026-11-04) MedGemma eligió el
# indicador correcto en solo 2 de 9 extracciones que pasaron la validación;
# activarlo empeoraría respuestas. Se activa a mano con INTENCION_LLM=respaldo.
MODO_POR_DEFECTO = "off"


def modo():
    """off | respaldo | siempre (INTENCION_LLM; un valor desconocido = off)."""
    value = str(os.getenv("INTENCION_LLM") or "").strip().lower()
    return value if value in MODOS else MODO_POR_DEFECTO


def _env_float(name, default):
    try:
        return float(str(os.getenv(name) or "").strip() or default)
    except ValueError:
        return default


def tiempo_max_s():
    """Tiempo total del LLM por turno (todas sus llamadas)."""
    return max(0.5, _env_float("INTENCION_LLM_TIEMPO_S", 3.0))


def confianza_min():
    return min(1.0, max(0.0, _env_float("INTENCION_LLM_CONFIANZA_MIN", 0.6)))


MAX_INDICADORES = 8
MAX_REGLAS = 3
MAX_COLUMNAS_POR_INDICADOR = 3
MAX_PERIODOS = 4
MAX_DESCRIPCION = 55
MAX_POR_TABLERO = 3
# Tamaño máximo del prompt (sistema + catálogo + pregunta): el servidor de MedGemma es compartido.
MAX_PROMPT = 2000
# Tokens de salida: num_predict("intencion") (LLM_NUM_PREDICT_INTENCION, 160): el JSON sin
# campos vacíos cabe holgado; si se corta, el JSON sale inválido y hay un reintento.

# ===================================================================== cuándo llamar

_PERIOD_WORD = r"(?:" + "|".join(sorted(PERIOD_MONTHS, key=len, reverse=True)) + r"|20\d{2})"
# «junio o julio», «2024 vs 2025», «agosto frente a septiembre»: comparación directa.
_COMPARE_DIRECT_RE = re.compile(
    r"(?<![a-z0-9])" + _PERIOD_WORD + r"(?:\s+(?:de|del)\s+20\d{2})?(?![a-z0-9])\s*,?\s*"
    r"(?:o|vs|versus|contra|frente\s+a|comparad[oa]s?\s+con|respecto\s+a(?:l)?)\s+"
    r"(?:(?:en|el|la|del?|al|con)\s+){0,2}" + _PERIOD_WORD + r"(?![a-z0-9])"
)
# «de septiembre a octubre», «entre 2024 y 2025» solo comparan con un verbo de cambio.
_COMPARE_RANGE_RE = re.compile(
    r"(?<![a-z0-9])" + _PERIOD_WORD + r"(?:\s+(?:de|del)\s+20\d{2})?(?![a-z0-9])\s*,?\s*(?:a|y|hasta|al)\s+"
    r"(?:(?:en|el|la|del?|al)\s+){0,2}" + _PERIOD_WORD + r"(?![a-z0-9])"
)
_CHANGE_RE = re.compile(
    r"(?<![a-z0-9])(?:subi[oa]|subieron|baj[oa]|bajaron|aument[oa]|aumentaron|disminuy[oe]|disminuyeron|"
    r"crec[ie]o|crecieron|cay[oe]|cayeron|vari[oa]|variaron|cambi[oa]|cambiaron|mejor[oa]|empeor[oa]|"
    r"compar[a-z]*|diferencia|variacion|mas\s+o\s+menos|se\s+mantuvo|subida|bajada)(?![a-z0-9])"
)


def pide_comparacion_periodos(pregunta):
    """¿La pregunta compara dos periodos? («¿subió o bajó de septiembre a octubre?», «¿más rápido en
    junio o en julio?», «2024 vs 2025»). «entre enero y marzo» sin verbo de cambio es un rango."""
    text = normalize_text(pregunta)
    if not text:
        return False
    if _COMPARE_DIRECT_RE.search(text):
        return True
    return bool(_COMPARE_RANGE_RE.search(text) and _CHANGE_RE.search(text))


# Estados del plan de reglas en que el LLM puede ayudar (modo respaldo).
_ESTADOS_RESPALDO = {"not_found", "ambiguous"}
_MOTIVOS_RESPALDO = {
    "possible_dimension_value_not_resolved",
    "requested_dimension_not_found_in_report",
    "metric_matched_only_dimension_words",
}


def motivo_llamada(modo_actual, plan, pregunta):
    """Motivo para llamar al LLM (texto para la traza) o None."""
    if modo_actual == "off" or not isinstance(plan, dict):
        return None
    status = plan.get("status")
    if modo_actual == "siempre":
        return f"modo siempre (plan de reglas: {status})"
    if status in _ESTADOS_RESPALDO:
        return {
            "not_found": "las reglas no identificaron el indicador",
            "ambiguous": "las reglas contrapreguntarían entre varios indicadores",
        }[status]
    if status == "unsupported_filter" and plan.get("reason") in _MOTIVOS_RESPALDO:
        return f"las reglas no pudieron interpretar parte de la pregunta ({plan.get('reason')})"
    if status == "ready" and pide_comparacion_periodos(pregunta) and not plan.get("comparison") and not (
        plan.get("temporal_buckets") and len(plan.get("temporal_buckets") or []) >= 2
    ):
        return "la pregunta compara periodos y las reglas no saben armar esa comparación"
    return None


# ===================================================================== catálogo acotado


class Catalogo:
    """Candidatos que se muestran al LLM, con ids cortos (I1.., C1..) que se traducen de vuelta."""

    def __init__(self, indicadores, columnas, periodos, hoy):
        self.indicadores = indicadores   # [{"id", "metric", "nombre", "tablero", "pagina", "descripcion", "unidad", "origen"}]
        self.columnas = columnas         # [{"id", "field", "nombre", "alias", "de": [ids]}]
        self.periodos = periodos         # [{"texto", "desde", "hasta"}]
        self.hoy = hoy
        self.caracteres = 0   # tamaño del prompt (sistema + catálogo + pregunta)

    def indicador(self, item_id):
        key = str(item_id or "").strip().upper()
        return next((item for item in self.indicadores if item["id"] == key), None)

    def columna(self, item_id):
        key = str(item_id or "").strip().upper()
        return next((item for item in self.columnas if item["id"] == key), None)

    def resumen(self):
        """Para la traza y el sondeo."""
        return {
            "indicadores": [
                {"id": i["id"], "nombre": i["nombre"], "tablero": i["tablero"], "metric_id": i["metric"].get("metric_id"),
                 "origen": i["origen"]} for i in self.indicadores
            ],
            "columnas": [{"id": c["id"], "columna": c["nombre"], "de": c["de"]} for c in self.columnas],
            "periodos": self.periodos,
        }


_STOP_TOKENS = None
# Palabras de comparación, ranking y forma: no describen el indicador (si no, «subió o bajó» trae
# VARIACIÓN o AUMENTO de costos como candidatos).
_SHAPE_WORDS = {
    "subio", "subieron", "bajo", "bajaron", "aumento", "aumentaron", "disminuyo", "disminuyeron",
    "crecio", "crecieron", "cayo", "cayeron", "vario", "variaron", "cambio", "cambiaron", "mejoro",
    "empeoro", "comparado", "comparar", "compara", "diferencia", "mas", "menos", "mayor", "menor",
    "top", "primeros", "rapido", "lento", "hoy", "ayer", "semana", "pasado", "pasada", "anterior",
    "actual", "corrido", "ultimo", "ultimos", "ultima", "ultimas", "repartidos", "separados",
    "agrupados", "cada", "segun", "estan", "hicieron", "tenemos",
}


def _stop_tokens():
    global _STOP_TOKENS
    if _STOP_TOKENS is None:
        _STOP_TOKENS = {canonical_token(word) for word in STOPWORDS | GENERIC_QUERY_WORDS | _SHAPE_WORDS} | {
            canonical_token(word) for word in PERIOD_MONTHS
        }
    return _STOP_TOKENS


def _question_tokens(pregunta):
    stop = _stop_tokens()
    return [
        token for token in dict.fromkeys(canonical_tokens(pregunta))
        if len(token) >= 3 and token not in stop and not token.isdigit()
    ]


def _approved(metric):
    return (
        isinstance(metric, dict) and metric.get("metric_id") and metric.get("dax_expression")
        and metric.get("validation_status") in (None, "approved")
    )


def _description(builder, metric):
    """Qué mide el indicador según el diccionario de variables (o su descripción del catálogo)."""
    index = builder._dictionary_index() if hasattr(builder, "_dictionary_index") else {}
    model = normalize_text(metric.get("semantic_model"))
    texts = []
    if metric.get("measure"):
        texts.append(index.get((model, "m:" + normalize_text(metric.get("measure")))))
    if metric.get("column") and metric.get("table"):
        texts.append(index.get((model, f"c:{normalize_text(metric.get('table'))}[{normalize_text(metric.get('column'))}]")))
    for ref_table, column in re.findall(r"'?([A-Za-z_][^'\[\]()]*?)'?\s*\[([^\]]+)\]",
                                        str(metric.get("model_expression") or metric.get("dax_expression") or "")):
        texts.append(index.get((model, f"c:{normalize_text(ref_table)}[{normalize_text(column)}]")))
    texts.append(metric.get("description"))
    for text in texts:
        if text and str(text).strip() and str(text).strip().lower() != "none":
            return re.sub(r"\s+", " ", str(text)).strip()
    return ""


def _unit(metric, description):
    fmt = str(metric.get("format_string") or metric.get("format") or "")
    text = normalize_text(f"{metric.get('label')} {description}")
    if "%" in fmt or "%" in str(metric.get("label") or "") or re.search(r"\b(?:porcentaje|proporcion)\b", text):
        return "porcentaje"
    if "$" in fmt or re.search(r"\b(?:pesos|valor facturado|monto|costo|dinero)\b", text):
        return "pesos"
    match = re.search(r"\b(minutos|horas|dias|segundos)\b", text)
    if match:
        return match.group(1)
    if re.search(r"\b(?:promedio|media)\b", text):
        return "promedio"
    return "conteo o suma"


def _lexical_index(builder):
    """{logical_key: (metric, tokens)} con las palabras del nombre, la tabla, las páginas y el
    diccionario de cada indicador aprobado (con caché en el planificador)."""
    cached = builder.__dict__.get("_intencion_lexical_index")
    if cached is not None:
        return cached
    index = {}
    for metric in getattr(builder, "metrics", None) or []:
        if not _approved(metric):
            continue
        key = builder._logical_key(metric)
        if key in index:
            continue
        names = [metric.get("label"), metric.get("measure"), metric.get("table"), *builder._metric_pages(metric)]
        tokens = {token for name in names if name for token in canonical_tokens(name)}
        try:
            tokens |= set(builder._dictionary_tokens(metric))
        except Exception:
            pass
        index[key] = (metric, {token for token in tokens if len(token) >= 3})
    builder._intencion_lexical_index = index
    return index


def _lexical_candidates(builder, pregunta, limit):
    tokens = _question_tokens(pregunta)
    if not tokens:
        return []
    index = _lexical_index(builder)
    frequency = {}
    for _, bag in index.values():
        for token in bag:
            frequency[token] = frequency.get(token, 0) + 1
    total = max(1, len(index))
    scored = []
    for metric, bag in index.values():
        score = 0.0
        for token in tokens:
            if token in bag:
                # Palabras raras pesan más (idf aproximado).
                score += 1.0 / (1.0 + 4.0 * frequency.get(token, 0) / total)
        if score > 0:
            scored.append((score, metric))
    scored.sort(key=lambda item: -item[0])
    return [metric for _, metric in scored[:limit]]


# ------------------------------------------------------------------ índice semántico (embeddings)

class IndiceSemantico:
    """Embeddings de los indicadores (nombre + diccionario + página + tablero) con el modelo de
    embeddings del RAG. Se construye en segundo plano la primera vez (~20 s en CPU) y se guarda en
    disco (directorio temporal, por huella de los textos); mientras no esté listo, solo se usan los
    candidatos de las reglas y los léxicos."""

    def __init__(self, builder, encoder):
        self.builder = builder
        self.encoder = encoder
        self.metrics = []
        self.matrix = None
        self.error = None
        self._thread = None
        self._lock = threading.Lock()

    def listo(self):
        return self.matrix is not None

    def iniciar(self):
        with self._lock:
            if self._thread is not None or self.matrix is not None:
                return
            self._thread = threading.Thread(target=self._construir, name="indice-intencion", daemon=True)
            self._thread.start()

    def esperar(self, segundos):
        thread = self._thread
        if thread is not None:
            thread.join(segundos)
        return self.listo()

    def _textos(self):
        seen, metrics, texts = set(), [], []
        for metric in getattr(self.builder, "metrics", None) or []:
            if not _approved(metric):
                continue
            key = self.builder._logical_key(metric)
            if key in seen:
                continue
            seen.add(key)
            pages = ", ".join(self.builder._metric_pages(metric)[:3])
            metrics.append(metric)
            texts.append(
                f"{metric.get('label')}. {_description(self.builder, metric)} Página: {pages}. "
                f"Tablero: {metric.get('semantic_model')}. Tabla: {metric.get('table')}"
            )
        return metrics, texts

    def _construir(self):
        try:
            import numpy as np

            metrics, texts = self._textos()
            digest = hashlib.sha1("\n".join(texts).encode("utf-8")).hexdigest()[:16]
            folder = os.path.join(tempfile.gettempdir(), "proyecto_rag_intencion")
            path = os.path.join(folder, f"indicadores_{digest}.npy")
            matrix = None
            if os.path.exists(path):
                try:
                    matrix = np.load(path)
                    if matrix.shape[0] != len(texts):
                        matrix = None
                except Exception:
                    matrix = None
            if matrix is None:
                matrix = np.asarray(self.encoder.encode(texts, normalize_embeddings=True, batch_size=64))
                try:
                    os.makedirs(folder, exist_ok=True)
                    np.save(path, matrix)
                except OSError:
                    pass
            self.metrics = metrics
            self.matrix = matrix
        except Exception as error:  # el índice es una mejora: sin él siguen las reglas y el léxico
            self.error = f"{type(error).__name__}: {error}"

    def buscar(self, pregunta, limit):
        if self.matrix is None:
            return []
        try:
            vector = self.encoder.encode(pregunta, normalize_embeddings=True)
            scores = self.matrix @ vector
        except Exception as error:
            self.error = f"búsqueda: {type(error).__name__}: {error}"
            return []
        order = sorted(range(len(self.metrics)), key=lambda i: -float(scores[i]))[:limit]
        return [self.metrics[i] for i in order]


_INDICES = {}
_INDICES_LOCK = threading.Lock()


def indice_semantico(builder, encoder):
    """Índice (uno por planificador y codificador), iniciado en segundo plano."""
    if builder is None or encoder is None or not callable(getattr(encoder, "encode", None)):
        return None
    key = (id(builder), id(encoder))
    with _INDICES_LOCK:
        index = _INDICES.get(key)
        if index is None:
            index = IndiceSemantico(builder, encoder)
            _INDICES[key] = index
    index.iniciar()
    return index


def _rule_candidates(plan):
    """Indicadores que consideraron las reglas (elegido, candidatos, sugerencias, opciones)."""
    result = []
    if not isinstance(plan, dict):
        return result
    if plan.get("metric"):
        result.append(plan["metric"])
    resolution = plan.get("metric_resolution") or {}
    if resolution.get("metric"):
        result.append(resolution["metric"])
    for key in ("candidates", "suggestions"):
        for item in resolution.get(key) or []:
            if isinstance(item, dict) and item.get("metric"):
                result.append(item["metric"])
    for option in plan.get("options") or []:
        if isinstance(option, dict) and isinstance(option.get("metric"), dict):
            result.append(option["metric"])
    return result


def _month_year(builder, month_text, pregunta):
    """(año, mes) de un mes nombrado en la pregunta: el año que le da el periodo principal de la
    pregunta («marzo a abril de 2025» -> marzo 2025) o, si no lo cubre, su ocurrencia más reciente."""
    parser = builder._period_parser()
    side = parser._side_month(normalize_text(month_text))
    if not side:
        return None
    if re.search(r"(?:19|20)\d{2}", str(month_text)):
        return side
    main = parser.parse(normalize_text(pregunta))
    start, end = (as_date(main.get("start")), as_date(main.get("end"))) if main else (None, None)
    if start and end:
        month = side[1]
        for year in range(start.year, end.year + 1):
            first = date(year, month, 1)
            if start <= first < end:
                return year, month
    return side


def _question_months(builder, pregunta):
    """Un periodo por cada mes que nombra la pregunta (en su orden y sin repetir), con su año."""
    parser = builder._period_parser()
    text = normalize_text(pregunta)
    periods, seen = [], set()
    for match in re.finditer(r"(?<![a-z0-9])(" + "|".join(PERIOD_MONTHS) + r")(?:\s+(?:de|del)\s+(20\d{2}))?(?![a-z0-9])", text):
        side = _month_year(builder, match.group(0), pregunta)
        if side and side not in seen:
            seen.add(side)
            year, month = side
            periods.append(parser._month_range(year, month, year, month, match.group(0)))
    return periods[:MAX_PERIODOS]


def _periods_in_question(builder, pregunta):
    """Periodos que el parser reconoce en la pregunta: el principal y cada mes/año suelto."""
    parser = builder._period_parser()
    text = normalize_text(pregunta)
    found = []

    def add(period, texto):
        if not period or not period.get("start") or not period.get("end"):
            return
        start, end = as_date(period["start"]), as_date(period["end"])
        item = {"texto": texto or period.get("label"), "desde": start.isoformat(),
                "hasta": (end - timedelta(days=1)).isoformat()}
        if item not in found:
            found.append(item)

    main = parser.parse(text)
    if main:
        add(main, main.get("label"))
    for match in re.finditer(r"(?<![a-z0-9])(" + "|".join(PERIOD_MONTHS) + r")(?:\s+(?:de|del)\s+(20\d{2}))?(?![a-z0-9])", text):
        side = _month_year(builder, match.group(0), pregunta)
        if side:
            year, month = side
            add(parser._month_range(year, month, year, month, match.group(0)), f"{match.group(1)} {year}")
    return found[:MAX_PERIODOS]


def _column_key(field):
    return (normalize_text(field.get("semantic_model")), normalize_text(field.get("table")),
            normalize_text(field.get("column")))


def _date_field(builder, field):
    """Fecha o jerarquía de fechas (Calendario[Date], FECHA_CIRUGIA): no se muestran como columnas."""
    if field.get("kind") == "hierarchy_level":
        return True
    try:
        kind = builder._column_type(field.get("semantic_model"), field.get("table"), field.get("column"))
    except Exception:
        kind = None
    if kind == "date":
        return True
    return bool(re.match(r"^(?:fecha|date)", normalize_text(field.get("column"))))


def _private(builder, field):
    """Identificadores y datos de personas (también por su alias: GPANOMCOM = «PACIENTE»)."""
    parts = getattr(builder, "_PRIVATE_COLUMN_PARTS", ())
    names = [field.get("column"), *(field.get("aliases") or [])]
    for name in names:
        compact = normalize_text(name).replace(" ", "")
        if compact and any(part in compact for part in parts):
            return True
    return identifier_column(field.get("column"))


def _column_label(field):
    """Nombre corto de una columna para el prompt: el nombre si es legible; si es técnico
    (HSUNOMBRE, GEEDESCRI) se agrega su primer alias legible."""
    column = str(field.get("column") or "")
    aliases = [
        str(a).strip() for a in field.get("aliases") or []
        if a and "." not in str(a) and normalize_text(a) != normalize_text(column)
    ]
    readable = bool(re.search(r"[_ ]", column)) or len(column) <= 8 or not column.isupper()
    if aliases and not readable:
        return f"{column} ({aliases[0].lower()})"
    return column


def armar_catalogo(builder, pregunta, plan=None, encoder=None, limit=None, esperar_indice_s=0.0):
    """Catálogo acotado para el LLM: los mejores indicadores (reglas primero, luego embeddings y
    léxico) con sus columnas más pertinentes, y los periodos detectados en la pregunta."""
    limit = limit or MAX_INDICADORES
    ordered, seen, per_model = [], set(), {}

    def push(metric, origin):
        if not _approved(metric) or len(ordered) >= limit:
            return
        key = builder._logical_key(metric)
        if key in seen:
            return
        model = normalize_text(metric.get("semantic_model"))
        # Diversidad: un tablero con muchas medidas parecidas no llena la lista.
        if origin != "reglas" and per_model.get(model, 0) >= MAX_POR_TABLERO:
            return
        seen.add(key)
        per_model[model] = per_model.get(model, 0) + 1
        ordered.append((metric, origin))

    # Las reglas aportan a lo sumo MAX_REGLAS: si no, sus candidatos (que ya fallaron) llenan la lista.
    for metric in _rule_candidates(plan):
        if len(ordered) >= MAX_REGLAS:
            break
        push(metric, "reglas")
    semantic = indice_semantico(builder, encoder)
    if semantic is not None and not semantic.listo() and esperar_indice_s > 0:
        semantic.esperar(esperar_indice_s)
    # Se intercalan embeddings y léxico para que ninguno llene solo la lista.
    vector = semantic.buscar(pregunta, 4 * limit) if semantic is not None else []
    lexical = _lexical_candidates(builder, pregunta, 4 * limit)
    # Dos de embeddings por cada una léxica: el léxico solo ve palabras sueltas (más ruido).
    vector_iter, lexical_iter = iter(vector), iter(lexical)
    while len(ordered) < limit:
        batch = [(next(vector_iter, None), "embeddings"), (next(vector_iter, None), "embeddings"),
                 (next(lexical_iter, None), "palabras")]
        if all(metric is None for metric, _ in batch):
            break
        for metric, origin in batch:
            if metric is not None:
                push(metric, origin)

    q_tokens = set(_question_tokens(pregunta))
    by_key, columnas, indicadores = {}, [], []
    for number, (metric, origin) in enumerate(ordered, 1):
        description = _description(builder, metric)
        # Una línea: la primera oración, corta.
        description = re.split(r"(?<=[a-z0-9áéíóúñ)])\.\s", description, maxsplit=1)[0][:MAX_DESCRIPCION]
        try:
            fields = builder._metric_dimensions(metric)
        except Exception:
            fields = []
        # Solo las columnas pertinentes: las que comparten palabras con la pregunta primero.
        ranked = []
        for position, field in enumerate(fields):
            if not field.get("table") or not field.get("column") or _private(builder, field):
                continue
            if _date_field(builder, field):
                continue  # los periodos van aparte
            words = {t for name in [field["column"], *(field.get("aliases") or [])] for t in canonical_tokens(name)}
            ranked.append((0 if words & q_tokens else 1, position, field))
        ranked.sort(key=lambda item: item[:2])
        own, seen_labels = [], set()
        for rank, _, field in ranked:
            # Las que la pregunta nombra (hasta 3); si ninguna, solo la principal del indicador.
            if len(own) >= MAX_COLUMNAS_POR_INDICADOR or (rank == 1 and own):
                break
            key = _column_key(field)
            entry = by_key.get(key)
            if entry is None:
                label = _column_label(field)
                if normalize_text(label) in seen_labels:
                    continue
                entry = {"id": f"C{len(columnas) + 1}", "field": field,
                         "nombre": f"{field['table']}[{field['column']}]", "etiqueta": label, "alias": [], "de": []}
                by_key[key] = entry
                columnas.append(entry)
            if normalize_text(entry["etiqueta"]) in seen_labels:
                continue
            seen_labels.add(normalize_text(entry["etiqueta"]))
            entry["de"].append(f"I{number}")
            own.append(entry["id"])
        indicadores.append({
            "id": f"I{number}", "metric": metric, "nombre": str(metric.get("label") or metric.get("measure")),
            "tablero": re.sub(r"^(?:tablero|dashboard)[ _]+(?:de\s+)?", "", str(metric.get("semantic_model") or ""),
                              flags=re.I)[:24],
            "pagina": ", ".join(builder._metric_pages(metric)[:1]),
            "descripcion": description, "unidad": _unit(metric, description), "origen": origin,
            "columnas": own,
        })
    catalogo = Catalogo(indicadores, columnas, _periods_in_question(builder, pregunta), builder._today())
    # Presupuesto del prompt: se quitan indicadores del final hasta que quepa.
    while len(catalogo.indicadores) > 3 and _prompt_chars(pregunta, catalogo) > MAX_PROMPT:
        dropped = catalogo.indicadores.pop()
        keep = {cid for item in catalogo.indicadores for cid in item["columnas"]}
        catalogo.columnas = [c for c in catalogo.columnas if c["id"] in keep]
        for column in catalogo.columnas:
            column["de"] = [i for i in column["de"] if i != dropped["id"]]
    catalogo.caracteres = _prompt_chars(pregunta, catalogo)
    return catalogo


# ===================================================================== prompt y esquema

ESQUEMA = {
    "type": "object",
    "properties": {
        "indicador_id": {"type": ["string", "null"]},
        "filtros": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "columna_id": {"type": "string"},
                    "valor_texto": {"type": "string"},
                    "excluir": {"type": "boolean"},
                },
                "required": ["columna_id", "valor_texto"],
            },
        },
        "agrupacion": {"type": "array", "items": {"type": "string"}},
        "periodos": {"type": "array", "items": {"type": "string"}},
        "comparacion": {"type": "string", "enum": ["ninguna", "periodos", "valores"]},
        "top_n": {"type": ["integer", "null"]},
        "orden": {"type": "string", "enum": ["ninguno", "mayor", "menor"]},
        "confianza": {"type": "number"},
        "dudas": {"type": "string"},
    },
    "required": ["indicador_id", "confianza"],
}

SISTEMA = """Extrae la intención de una pregunta sobre tableros de un hospital. Responde solo JSON.
indicador_id: I# que mide lo pedido (null si ninguno). filtros: [{columna_id:C#,valor_texto,excluir}] solo valores concretos (un servicio, una EPS, un estado); excluir=true con «sin contar/excepto». agrupacion: [C#] para «por X», «en qué X», «cuál X más». periodos: los que dice la pregunta. comparacion:"periodos" si compara dos. top_n y orden:"mayor"|"menor" si es ranking. confianza 0-1. Omite campos vacíos. Un periodo o el nombre de una columna no es un filtro.
Ej.: «3 sedes con más visitas en marzo sin contar urgencias» -> {"indicador_id":"I1","filtros":[{"columna_id":"C2","valor_texto":"urgencias","excluir":true}],"agrupacion":["C1"],"periodos":["marzo"],"top_n":3,"orden":"mayor","confianza":0.8}"""


def _user_message(pregunta, catalogo):
    lines = [f"HOY {catalogo.hoy.isoformat()}"]
    labels = {column["id"]: column["etiqueta"] for column in catalogo.columnas}
    for item in catalogo.indicadores:
        parts = [item["id"], item["nombre"], item["tablero"]]
        if item["descripcion"]:
            parts.append(item["descripcion"])
        if item["columnas"]:
            parts.append("col: " + ", ".join(f"{cid}={labels[cid]}" for cid in item["columnas"] if cid in labels))
        lines.append(" | ".join(parts))
    if catalogo.periodos:
        lines.append("PERIODOS: " + "; ".join(p["texto"] for p in catalogo.periodos))
    lines.append(f"PREGUNTA: «{pregunta}»")
    return "\n".join(lines)


def _prompt_chars(pregunta, catalogo):
    return len(SISTEMA) + len(_user_message(pregunta, catalogo))


def mensajes(pregunta, catalogo):
    return [{"role": "system", "content": SISTEMA}, {"role": "user", "content": _user_message(pregunta, catalogo)}]


# ===================================================================== parseo robusto

def parsear_json(texto):
    """Primer objeto JSON del texto (tolera ```json, texto antes/después, comillas tipográficas)."""
    if texto is None:
        return None
    if isinstance(texto, dict):
        return texto
    text = str(texto).strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE).strip()
    text = text.replace("“", '"').replace("”", '"')
    start = text.find("{")
    if start < 0:
        return None
    depth, in_string, escape = 0, False, False
    for position in range(start, len(text)):
        char = text[position]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start: position + 1]
                try:
                    value = json.loads(candidate)
                except ValueError:
                    # Comas finales («,}»): único arreglo tolerado.
                    try:
                        value = json.loads(re.sub(r",\s*([}\]])", r"\1", candidate))
                    except ValueError:
                        return None
                return value if isinstance(value, dict) else None
    return None


def normalizar_intencion(obj):
    """(intención con tipos normalizados, [errores de forma]). Errores = JSON inválido."""
    errores = []
    if not isinstance(obj, dict):
        return None, ["no es un objeto JSON"]
    faltan = [key for key in ESQUEMA["required"] if key not in obj]
    if "indicador_id" in faltan:
        errores.append("falta indicador_id")
    indicador = obj.get("indicador_id")
    if indicador is not None and not isinstance(indicador, (str, int)):
        errores.append("indicador_id no es texto")
    indicador = None if indicador in (None, "", "null", "None") else str(indicador).strip()

    filtros = []
    for item in obj.get("filtros") or []:
        if not isinstance(item, dict) or not item.get("columna_id") or item.get("valor_texto") in (None, ""):
            errores.append(f"filtro mal formado: {item!r}"[:120])
            continue
        filtros.append({"columna_id": str(item["columna_id"]).strip(), "valor_texto": str(item["valor_texto"]).strip(),
                        "excluir": bool(item.get("excluir"))})
    agrupacion = []
    for item in obj.get("agrupacion") or []:
        if isinstance(item, (str, int)) and str(item).strip():
            agrupacion.append(str(item).strip())
        else:
            errores.append(f"agrupación mal formada: {item!r}"[:120])
    periodos = []
    for item in obj.get("periodos") or []:
        if isinstance(item, str) and item.strip():
            periodos.append(item.strip())
        elif isinstance(item, dict) and item.get("desde") and item.get("hasta"):
            periodos.append({"desde": str(item["desde"]), "hasta": str(item["hasta"])})
        else:
            errores.append(f"periodo mal formado: {item!r}"[:120])
    comparacion = str(obj.get("comparacion") or "ninguna").strip().lower()
    if comparacion not in ("ninguna", "periodos", "valores"):
        errores.append(f"comparacion desconocida: {comparacion}")
        comparacion = "ninguna"
    top_n = obj.get("top_n")
    try:
        top_n = int(top_n) if top_n not in (None, "", "null") else None
    except (TypeError, ValueError):
        errores.append(f"top_n no es entero: {top_n!r}")
        top_n = None
    if top_n is not None and not 1 <= top_n <= 100:
        top_n = None
    orden = str(obj.get("orden") or "ninguno").strip().lower()
    if orden not in ("ninguno", "mayor", "menor"):
        orden = "ninguno"
    confianza = obj.get("confianza")
    if confianza is None:
        confianza = 0.6   # campo omitido: confianza neutra (el prompt pide omitir lo vacío)
    if isinstance(confianza, str):
        confianza = {"alta": 0.9, "media": 0.6, "baja": 0.3}.get(confianza.strip().lower(), confianza)
    try:
        confianza = float(confianza)
    except (TypeError, ValueError):
        errores.append(f"confianza no es número: {confianza!r}")
        confianza = 0.0
    if confianza > 1.0 and confianza <= 100.0:
        confianza = confianza / 100.0
    return {
        "indicador_id": indicador, "filtros": filtros, "agrupacion": agrupacion, "periodos": periodos,
        "comparacion": comparacion, "top_n": top_n, "orden": orden, "confianza": confianza,
        "dudas": str(obj.get("dudas") or "").strip(),
    }, errores


# ===================================================================== llamada al LLM

def formato_salida():
    """`json` (por defecto: JSON simple y validación propia, lo más liviano para el servidor) o
    `esquema` (decodificación restringida con el esquema completo; más carga en Ollama)."""
    value = str(os.getenv("INTENCION_LLM_FORMATO") or "").strip().lower()
    return ESQUEMA if value == "esquema" else "json"


def pausa_disyuntor_s():
    """Minutos sin llamar al extractor tras una falla de MedGemma (INTENCION_LLM_PAUSA_S, 300 s)."""
    return max(0.0, _env_float("INTENCION_LLM_PAUSA_S", 300.0))


# Disyuntor (circuit breaker) del proceso: si MedGemma falla (504 del proxy, tiempo agotado, runner
# caído, saturado), el extractor se apaga unos minutos y quedan las reglas. Así nunca se insiste
# contra un servidor compartido que está en problemas.
_DISYUNTOR = {"hasta": 0.0, "motivo": None, "fallas": 0}
_DISYUNTOR_LOCK = threading.Lock()


def disyuntor_abierto():
    """Motivo si el extractor está en pausa; None si se puede llamar."""
    with _DISYUNTOR_LOCK:
        if time.monotonic() < _DISYUNTOR["hasta"]:
            return _DISYUNTOR["motivo"]
        return None


def abrir_disyuntor(motivo, segundos=None):
    with _DISYUNTOR_LOCK:
        _DISYUNTOR["fallas"] += 1
        _DISYUNTOR["motivo"] = motivo
        _DISYUNTOR["hasta"] = time.monotonic() + (pausa_disyuntor_s() if segundos is None else float(segundos))


def cerrar_disyuntor():
    with _DISYUNTOR_LOCK:
        _DISYUNTOR.update(hasta=0.0, motivo=None, fallas=0)


def falla_del_servidor(texto):
    """¿El error indica un servidor sobrecargado (504, runner caído, tiempo agotado)?"""
    text = str(texto or "").lower()
    return any(marker in text for marker in (
        "504", "502", "503", "runner has unexpectedly stopped", "resource limitations", "timed out",
        "timeout", "saturad", "llm_saturated", "llm_timeout",
    ))


def extraer_intencion(provider, pregunta, catalogo, tiempo_total=None, call=None, disyuntor=True):
    """Llama al LLM (temperatura 0, JSON simple, salida corta) y parsea su salida; un reintento
    SOLO si el JSON sale inválido y queda tiempo (nunca tras un error del servidor). Si MedGemma
    falla, abre el disyuntor. Devuelve {"status": "ok"|"invalid"|"llm_error"|"sin_llm"|"pausado",
    "intencion", "crudo": [textos], "errores", "segundos", "llamadas"}."""
    if call is None:
        from src.llm.llm_gate import call_llm as call
    started = time.perf_counter()
    budget = float(tiempo_total or tiempo_max_s())
    result = {"status": "sin_llm", "intencion": None, "crudo": [], "errores": [], "segundos": 0.0, "llamadas": 0}
    if provider is None:
        return result
    paused = disyuntor_abierto() if disyuntor else None
    if paused:
        result.update(status="pausado")
        result["errores"].append(f"extractor en pausa tras una falla de MedGemma: {paused}")
        return result
    messages = mensajes(pregunta, catalogo)
    for attempt in range(2):
        remaining = budget - (time.perf_counter() - started)
        if remaining < (0.4 if attempt == 0 else 1.5):
            if attempt:
                result["errores"].append("sin tiempo para reintentar")
            break
        attempt_messages = messages
        if attempt and result["crudo"]:
            attempt_messages = [*messages, {"role": "assistant", "content": str(result["crudo"][-1])[:300]},
                                {"role": "user", "content": "Responde SOLO el objeto JSON."}]
        response = call(provider, attempt_messages, purpose="intención", timeout=remaining,
                        queue_wait=min(1.0, remaining), temperature=0.0, max_tokens=num_predict("intencion"),
                        think=False, format=formato_salida())
        result["llamadas"] += 1
        status = (response or {}).get("status")
        answer = (response or {}).get("answer")
        if status != "success" or not answer:
            error = f"LLM: {status} {str((response or {}).get('error') or '')[:160]}".strip()
            result["status"] = "llm_error"
            result["errores"].append(error)
            if disyuntor and status != "empty_response":
                abrir_disyuntor(error)
            break   # nunca se insiste tras un error del servidor
        result["crudo"].append(answer)
        intencion, errores = normalizar_intencion(parsear_json(answer))
        if intencion is not None and not errores:
            result.update(status="ok", intencion=intencion)
            break
        result["status"] = "invalid"
        result["errores"].extend(errores or ["JSON inválido"])
        if intencion is not None and attempt == 1:
            # Segundo intento con errores menores de forma: se conserva lo que sí tiene forma.
            result["intencion"] = intencion
    result["segundos"] = round(time.perf_counter() - started, 2)
    return result


# ===================================================================== validación -> plan

class _Rechazo(Exception):
    pass


def _grounded_period(builder, texto, pregunta):
    """Periodo del LLM validado con PeriodParser y anclado en la pregunta (sus meses, años o
    palabras relativas deben estar en ella). None si no."""
    parser = builder._period_parser()
    question = normalize_text(pregunta)
    if isinstance(texto, dict):
        start = as_date(texto.get("desde"))
        end = as_date(texto.get("hasta"))
        if not start or not end or end < start:
            return None
        period = parser._range(start, end + timedelta(days=1), "")
        words = {w for w in normalize_text(f"{start.year} {end.year}").split()}
        months = {name for name, number in PERIOD_MONTHS.items() if number in (start.month, end.month)}
        if not (words & set(question.split()) or months & set(question.split())):
            return None
        return period
    text = normalize_text(texto)
    if not text:
        return None
    words = set(text.split())
    months = {w for w in words if w in PERIOD_MONTHS}
    years = {w for w in words if re.fullmatch(r"20\d{2}", w)}
    q_words = set(question.split())
    # Anclaje: los meses del periodo deben estar en la pregunta; un periodo relativo («este año»,
    # «la semana pasada») debe estar dicho con sus palabras.
    if months and not months <= q_words:
        return None
    if not months and not years:
        relative = [w for w in words if len(w) >= 3 and w not in ("del", "las", "los")]
        if not relative or not all(w in q_words for w in relative):
            return None
    if len(months) == 1 and parser._side_month(text):
        month_name = next(iter(months))
        # El año de un mes es el que le da la pregunta («marzo a abril de 2025» -> 2025), no el
        # que escribió el LLM: si el LLM puso otro, el periodo no se reconoce.
        side = _month_year(builder, month_name, pregunta)
        if not side:
            return None
        year, month = side
        if years and years <= q_words and len(years) == 1:
            year = int(next(iter(years)))   # año dicho en la pregunta («marzo de 2024 y de 2025»)
        elif years and {str(year)} != years:
            return None
        return parser._month_range(year, month, year, month, text)
    if years and not years <= q_words:
        return None
    return parser.parse(text)


def _resolve_filter_value(builder, field, semantic_model, texto):
    """Valor real del dominio para el texto del LLM: exacto/aproximado (`_resolve_value`) o la familia
    que empieza por esas palabras («uci» -> UCI ADULTOS, UCI NEONATAL)."""
    resolved = builder._resolve_value(question=texto, field=field, semantic_model=semantic_model,
                                      value_hint=texto, context=texto)
    if resolved:
        return resolved
    values = builder._get_values(semantic_model, field["table"], field["column"], essential=True)
    if not values:
        return None
    scored = [(builder._value_match_score(texto, value, value_hint=texto), value) for value in values]
    tied = [value for score, value in scored if score >= 0.72]
    if not tied:
        return None
    family_of = getattr(builder, "_value_family", None)
    family = family_of(texto, tied, values) if callable(family_of) else None
    if family:
        return {"values": family["values"], "value": None, "score": 0.9, "tokens": set(family["tokens"])}
    return None


def _field_in(fields, column_item):
    key = _column_key(column_item["field"])
    return next((field for field in fields if _column_key(field) == key), None)


def opciones_permitidas(builder, plan):
    """Claves lógicas de los indicadores que las reglas ofrecerían en una contrapregunta (plan
    `ambiguous`); None si el plan no es una ambigüedad (no se restringe)."""
    if not isinstance(plan, dict) or plan.get("status") != "ambiguous":
        return None
    keys = {builder._logical_key(metric) for metric in _rule_candidates(plan) if _approved(metric)}
    return keys or None


def validar_intencion(builder, pregunta, intencion, catalogo, permitidos=None):
    """Valida la intención con el motor y arma el plan. Devuelve {"status": "valid"|"rejected",
    "plan", "motivo", "aceptado": [líneas], "descartado": [líneas]}. Cualquier parte que no valide
    rechaza el plan completo (no se consulta a medias), salvo periodos inventados y «filtros» que no
    son valores (se descartan). `permitidos`: claves lógicas a las que se limita el indicador."""
    aceptado, descartado = [], []
    notes_box = []
    previous_notes = builder.__dict__.get("_resolution_notes")
    previous_date_metric = builder.__dict__.get("_date_metric")
    builder._resolution_notes = notes_box
    try:
        plan = _armar_plan(builder, pregunta, intencion, catalogo, aceptado, descartado, permitidos)
        if notes_box:
            plan["resolution_notes"] = list(dict.fromkeys([*(plan.get("resolution_notes") or []), *notes_box]))
        return {"status": "valid", "plan": plan, "motivo": None, "aceptado": aceptado, "descartado": descartado}
    except _Rechazo as rejection:
        descartado.append(str(rejection))
        return {"status": "rejected", "plan": None, "motivo": str(rejection), "aceptado": aceptado,
                "descartado": descartado}
    except Exception as error:
        descartado.append(f"error al validar: {type(error).__name__}: {error}")
        return {"status": "rejected", "plan": None, "motivo": f"error al validar: {type(error).__name__}: {error}",
                "aceptado": aceptado, "descartado": descartado}
    finally:
        builder._resolution_notes = previous_notes
        builder._date_metric = previous_date_metric


_NOT_VALUE_WORDS = {
    "hoy", "ayer", "anteayer", "ahora", "ahorita", "actual", "actuales", "semana", "mes", "ano", "anio", "dia",
    "total", "todos", "todas", "cantidad", "numero", "promedio",
}


def _not_a_value(builder, texto, metric, nombre):
    """Motivo si el texto no puede ser un valor de filtro (periodo, palabra genérica o el nombre del
    propio indicador); None si puede serlo."""
    text = normalize_text(texto)
    if not text:
        return "vacío"
    words = text.split()
    if all(w in _NOT_VALUE_WORDS or w in PERIOD_MONTHS or re.fullmatch(r"(?:19|20)\d{2}|\d{1,2}", w)
           or w in STOPWORDS for w in words):
        return "es un periodo o una palabra genérica"
    try:
        if builder._period_parser().parse(text):
            return "es un periodo (se toma de la pregunta)"
    except Exception:
        pass
    tokens = {canonical_token(w) for w in words if len(w) >= 3}
    name_tokens = {t for name in (nombre, metric.get("label"), metric.get("measure"), metric.get("table"))
                   if name for t in canonical_tokens(name)}
    if tokens and tokens <= name_tokens:
        return "es el nombre del indicador, no un valor"
    return None


def _names_column(texto, field):
    tokens = {canonical_token(w) for w in normalize_text(texto).split() if len(w) >= 3}
    names = {t for name in [field.get("column"), *(field.get("aliases") or [])] if name for t in canonical_tokens(name)}
    return bool(tokens) and tokens <= names


def _armar_plan(builder, pregunta, intencion, catalogo, aceptado, descartado, permitidos=None):
    if not isinstance(intencion, dict):
        raise _Rechazo("sin intención válida")
    item = catalogo.indicador(intencion.get("indicador_id"))
    if item is None:
        raise _Rechazo(
            "el LLM no eligió indicador" if not intencion.get("indicador_id")
            else f"indicador «{intencion.get('indicador_id')}» no está en la lista mostrada"
        )
    metric = item["metric"]
    if permitidos is not None and builder._logical_key(metric) not in permitidos:
        raise _Rechazo(
            f"{metric.get('label')} no es una de las opciones de la contrapregunta de las reglas: ante una "
            "ambigüedad MedGemma solo puede elegir entre ellas"
        )
    if not _approved(metric):
        raise _Rechazo(f"{metric.get('label')} no es un indicador aprobado con expresión DAX")
    confianza = float(intencion.get("confianza") or 0.0)
    if confianza < confianza_min():
        raise _Rechazo(f"confianza {confianza:.2f} menor que {confianza_min():.2f} (INTENCION_LLM_CONFIANZA_MIN)")
    aceptado.append(f"indicador {item['id']} = {metric.get('label')} ({metric.get('semantic_model')})")
    semantic_model = metric.get("semantic_model")
    dims = builder._metric_dimensions(metric)

    # Agrupación
    group_fields = []
    for column_id in intencion.get("agrupacion") or []:
        column = catalogo.columna(column_id)
        if column is None:
            raise _Rechazo(f"columna de agrupación «{column_id}» no está en la lista mostrada")
        field = _field_in(dims, column)
        if field is None or builder._dimension_relation(metric, field) == "unrelated":
            raise _Rechazo(f"{column['nombre']} no desglosa {metric.get('label')} (no es una dimensión de su tabla)")
        if _column_key(field) not in {_column_key(f) for f in group_fields}:
            group_fields.append(field)
            aceptado.append(f"agrupar por {column['nombre']}")

    # Filtros: columna en la lista y en las dimensiones; valor en el dominio real.
    filters = []
    for spec in intencion.get("filtros") or []:
        column = catalogo.columna(spec.get("columna_id"))
        texto = spec.get("valor_texto")
        # Lo que no es un valor (un periodo, el nombre del indicador) no es un filtro: se descarta.
        not_value = _not_a_value(builder, texto, metric, item["nombre"])
        if not_value:
            descartado.append(f"filtro «{texto}» descartado: {not_value}")
            continue
        if column is None:
            raise _Rechazo(f"columna de filtro «{spec.get('columna_id')}» no está en la lista mostrada")
        field = _field_in(dims, column)
        if field is None or builder._dimension_relation(metric, field) == "unrelated":
            raise _Rechazo(f"{column['nombre']} no filtra {metric.get('label')}")
        if _names_column(texto, field):
            # «según el ÁREA», «qué TIPO de cama»: nombra la columna, no un valor -> se agrupa.
            if _column_key(field) not in {_column_key(f) for f in group_fields}:
                group_fields.append(field)
            descartado.append(f"filtro «{texto}» nombra la columna {column['nombre']}: se agrupa por ella")
            continue
        resolved = _resolve_filter_value(builder, field, semantic_model, texto)
        if not resolved:
            raise _Rechazo(f"«{spec.get('valor_texto')}» no es un valor de {column['nombre']} (dominio real)")
        item_filter = builder._categorical_filter(field, resolved, "intencion_llm", semantic_model)
        if spec.get("excluir"):
            item_filter["negated"] = True
            item_filter["operator"] = "not in"
        filters.append(item_filter)
        shown = resolved.get("value") if resolved.get("value") is not None else ", ".join(map(str, resolved.get("values") or []))
        aceptado.append(
            f"filtro {column['nombre']} {'≠' if spec.get('excluir') else '='} {shown} "
            f"(«{spec.get('valor_texto')}», coincidencia {resolved.get('score')})"
        )

    # Periodos
    builder._date_metric = metric
    llm_periods = []
    for texto in (intencion.get("periodos") or [])[:MAX_PERIODOS]:
        period = _grounded_period(builder, texto, pregunta)
        if period is None:
            # Un periodo que la pregunta no dice no se aplica (el LLM no inventa periodos): se
            # descarta y sigue el análisis de periodos de las reglas.
            descartado.append(f"periodo «{texto}» descartado: no se reconoce o no está en la pregunta")
            continue
        llm_periods.append(period)

    notes, unapplied = [], []
    buckets, group = [], None
    comparison = None
    if intencion.get("comparacion") == "periodos" or (pide_comparacion_periodos(pregunta) and len(llm_periods) >= 2):
        if len(llm_periods) < 2 and pide_comparacion_periodos(pregunta):
            # El LLM vio la comparación pero no dio los dos periodos: los meses que nombra la pregunta.
            months = _question_months(builder, pregunta)
            if len(months) >= 2:
                llm_periods = months
                aceptado.append("periodos de la comparación tomados de la pregunta: "
                                + ", ".join(p.get("label") for p in months))
        if len(llm_periods) < 2:
            raise _Rechazo("comparación de periodos sin dos periodos válidos")
        if group_fields:
            raise _Rechazo("comparación de periodos con agrupación: no soportada")
        table = None
        for order, period in enumerate(llm_periods, 1):
            period_filters, period_unapplied, period_notes = builder._period_filters(period, dims, semantic_model)
            if not period_filters or period_unapplied:
                raise _Rechazo(
                    f"{metric.get('label')} no tiene una fecha con la que filtrar {period.get('label')}"
                    + (f" ({'; '.join(period_unapplied)})" if period_unapplied else "")
                )
            notes.extend(n for n in period_notes if n not in notes)
            table = table or period_filters[0].get("table") or (period_filters[0].get("columns") or [{}])[0].get("table")
            buckets.append({"order": order, "label": period.get("label"), "filters": period_filters})
        group = {"table": table, "column": "Periodo", "label": "Periodo",
                 "source": "query_plan_temporal_group", "temporal": "comparison"}
        comparison = {"labels": [b["label"] for b in buckets]}
        aceptado.append("comparación de periodos: " + " frente a ".join(comparison["labels"]))
    else:
        temporal = builder._periods_for_metric(pregunta, metric, item["nombre"])
        if temporal.get("period") is None and llm_periods:
            if len(llm_periods) > 1:
                raise _Rechazo("varios periodos sin comparación")
            temporal = {**temporal, "period": llm_periods[0]}
            aceptado.append(f"periodo (LLM, validado): {llm_periods[0].get('label')}")
        elif temporal.get("period") is not None:
            aceptado.append(f"periodo (reglas): {temporal['period'].get('label')}")
        result = builder._apply_temporal(temporal, dims, semantic_model, group_fields, metric=metric)
        if result.get("unsupported_period"):
            raise _Rechazo(
                result.get("explanation")
                or f"{metric.get('label')} no tiene fecha para {result['unsupported_period'].get('label')}"
            )
        if result.get("unapplied"):
            raise _Rechazo("no se pudo aplicar: " + "; ".join(result["unapplied"]))
        filters.extend(result.get("filters") or [])
        notes.extend(result.get("notes") or [])
        buckets = result.get("buckets") or []
        group = result.get("group")

    # Ranking
    ranking = None
    if intencion.get("top_n") or intencion.get("orden") in ("mayor", "menor"):
        if not group_fields:
            raise _Rechazo("ranking (top/orden) sin agrupación")
        direction = "asc" if intencion.get("orden") == "menor" else "desc"
        limit = intencion.get("top_n")
        ranking = {"direction": direction, "limit": limit,
                   "phrase": f"top {limit}" if limit else ("menor" if direction == "asc" else "mayor")}
        label = (group_fields[0].get("aliases") or [group_fields[0]["column"]])[0]
        notes.append(builder._ranking_note(ranking, label))
        aceptado.append(f"ranking: {'de menor a mayor' if direction == 'asc' else 'de mayor a menor'}"
                        + (f", límite {limit}" if limit else ""))

    group_by = [{
        "table": field["table"], "column": field["column"], "label": builder._group_label(field, metric),
        "source": "query_plan_group_by",
    } for field in group_fields]
    if group is not None:
        group_by = [group]
    if not group_by:
        metric = builder._scalar_representative(metric)
    pages = builder._metric_pages(metric)
    reports = metric.get("reports") or []
    plan = {
        "status": "ready",
        "intent": "numeric_query",
        "mode": "grouped" if group_by else "scalar",
        "question": pregunta,
        "source_context": {},
        "semantic_model": semantic_model,
        "report": metric.get("report") or (reports[0] if reports else None),
        "dashboard": metric.get("dashboard") or (pages[0] if pages else None),
        "metric": metric,
        "metric_match": {"matched_name": item["nombre"], "score": confianza, "interpretation": "intencion_llm"},
        "filters": filters,
        "unapplied_terms": unapplied,
        "notes": notes,
        "implicit_decisions": [],
        "technical_columns_used": [],
        "board_mentions": [],
        "group_by": group_by,
        "ranking": ranking if group_by and not comparison else None,
        "temporal_buckets": buckets,
        "period": None,
        "comparison": comparison,
        "intent_llm": {"confianza": confianza, "dudas": intencion.get("dudas") or ""},
        "dimension_candidates_checked": min(len(dims), 20),
    }
    # Filtros del tablero (visual y página) del indicador, como en el plan de reglas.
    plan = builder._apply_board_filter_context(plan)
    return plan


# ===================================================================== redacción de comparaciones

def frase_comparacion(plan, rows, row_value, group_cell, format_value=None, format_number=None):
    """«De septiembre 2026 a octubre 2026, **X** subió 12,3 % (de 40 a 45).» desde las filas del DAX
    (nunca del LLM). None si no hay dos valores numéricos."""
    comparison = (plan or {}).get("comparison") or {}
    if not comparison or not rows:
        return None
    group = (plan.get("group_by") or [{}])[0]
    metric = plan.get("metric") or {}
    label = metric.get("label") or "el indicador"
    fmt = metric.get("format_string") or metric.get("format")
    pairs = []
    for row in rows:
        try:
            value = float(row_value(row))
        except (TypeError, ValueError):
            value = None
        pairs.append((group_cell(row, group), value))
    labels = comparison.get("labels") or []
    by_label = {str(name): value for name, value in pairs if name is not None}
    ordered = [(name, by_label.get(str(name))) for name in labels] if labels and all(
        str(name) in by_label for name in labels) else pairs
    if len(ordered) < 2:
        return None
    (first_label, first), (last_label, last) = ordered[0], ordered[-1]
    if first is None or last is None:
        missing = first_label if first is None else last_label
        return f"No hay datos de **{label}** en {missing}, así que no se puede decir si subió o bajó."

    def shown(value):
        text = format_value(value, label, fmt) if format_value else None
        return text if text is not None else (format_number(value) if format_number else str(value))

    if first == last:
        return f"De {first_label} a {last_label}, **{label}** se mantuvo igual ({shown(first)})."
    verb = "subió" if last > first else "bajó"
    if first == 0:
        return f"De {first_label} a {last_label}, **{label}** {verb}: pasó de {shown(first)} a {shown(last)}."
    change = abs(last - first) / abs(first) * 100.0
    change_text = format_number(round(change, 1), 1) if format_number else f"{change:.1f}"
    return (f"De {first_label} a {last_label}, **{label}** {verb} {change_text} % "
            f"(de {shown(first)} a {shown(last)}).")
