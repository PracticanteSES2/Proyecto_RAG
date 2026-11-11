"""Dominios de valores (Power BI): lectura con caché, precalentamiento y coincidencia de valores.

_get_values / _prefetch_values / prewarm_domains (presupuesto por turno, tests/perf), puntaje de un
valor frente a la pregunta (_value_match_score), contradicción de valores y _resolve_value. Mixin de
QueryPlanBuilder, métodos movidos sin cambios.
"""
import logging
import os
import re
import threading

from src.providers.domain_cache import connection_open, domain_cache_for, identifier_column
from src.semantic.resolucion.texto import (
    _exact_phrase,
    _is_question_form_word,
    canonical_token,
    canonical_tokens,
    FILTER_NEUTRAL_WORDS,
    GENERIC_QUERY_WORDS,
    MONTHS,
    normalize_text,
    QUESTION_FORM_WORDS,
    STOPWORDS,
    value_contradiction,
)

logger = logging.getLogger(__name__)


class ValoresMixin:


    # ---------------- actual dimension values ----------------
    def _table_ref(self, table):
        return "'" + str(table).replace("'", "''") + "'"

    def _column_ref(self, column):
        return "[" + str(column).replace("]", "]]" ) + "]"

    def _domain_cache(self):
        """Caché de dominios compartida del proveedor (TTL, lote y presupuesto
        por turno; ver src/providers/domain_cache.py)."""
        return domain_cache_for(self.powerbi_provider)

    def _get_values(self, semantic_model, table, column, essential=False, limit=None):
        """Valores de la columna: los estáticos del PBIR y luego los de Power BI
        (VALUES, desde la caché de dominios). None si Power BI no respondió.
        `essential`: filtro pedido con su columna o periodo (sin límite de
        consultas de exploración del turno ni de tiempo). `limit`: tope TOPN
        (por defecto el histórico, 2500); uno menor basta cuando solo importa
        si el dominio pasa de cierto tamaño (calificativos aproximados)."""
        key = (semantic_model, table, column)
        cache = self._domain_cache()
        domain = cache.get(semantic_model, table, column, essential=essential, limit=limit)
        if domain is None:
            error = cache.errors.get(cache.key(semantic_model, table, column))
            self.domain_errors[key] = error or {
                "status": "skipped", "error_type": None,
                "message": "consulta de valores omitida (límite de consultas de exploración del turno)",
            }
            # No afirmar que un filtro fue verificado si XMLA falló,
            # aunque el PBIR tenga valores estáticos potencialmente antiguos.
            # El siguiente intento consultará de nuevo el dominio.
            return None

        self.domain_errors.pop(key, None)
        memo = self.value_cache.get(key)
        if memo is not None and memo[0] is domain:
            return memo[1]
        static_key = (normalize_text(semantic_model), normalize_text(table), normalize_text(column))
        values = list(self.static_values.get(static_key, []) or [])
        seen = set(values)
        for value in domain:
            if value not in seen:
                values.append(value)
                seen.add(value)
        # Se guarda junto al dominio del que salió: si la caché lo renueva
        # (TTL), se recompone.
        self.value_cache[key] = (domain, values)
        return values

    _PREWARM_COLUMNS_PER_MODEL = 12

    def prewarm_domains(self, max_columns_per_model=None, only_open_connections=False):
        """Trae (en lotes pequeños de columnas de baja cardinalidad) los dominios
        de las columnas de los visuales donde suele nombrarse un valor suelto
        (servicio, especialidad, aseguradora, sede...). Nunca columnas de
        personas o identificadores. `only_open_connections`: solo modelos cuya
        conexión ya abrió el hilo principal (el hilo de precalentamiento no abre
        conexiones: con Interactive Login el inicio de sesión no debe salir de un
        hilo secundario). Devuelve {modelo: columnas}."""
        limit = int(max_columns_per_model or self._PREWARM_COLUMNS_PER_MODEL)
        by_model = {}
        for field in self.dimension_fields:
            model = field.get("semantic_model")
            if not model or not self._plausible_value_column(field) or not self._implicit_eligible(field, model):
                continue
            column = normalize_text(field.get("column")).replace(" ", "")
            if any(part in column for part in self._PRIVATE_COLUMN_PARTS) or identifier_column(field.get("column")):
                continue
            bucket = by_model.setdefault(model, [])
            key = (normalize_text(field.get("table")), normalize_text(field.get("column")))
            if len(bucket) < limit and all(
                key != (normalize_text(f.get("table")), normalize_text(f.get("column"))) for f in bucket
            ):
                bucket.append(field)
        if only_open_connections:
            by_model = {
                model: fields for model, fields in by_model.items()
                if connection_open(self.powerbi_provider, model)
            }
        for model, fields in by_model.items():
            self._prefetch_values(model, fields)
        return {model: len(fields) for model, fields in by_model.items()}

    def _maybe_prewarm_domains(self):
        """POWERBI_DOMAIN_PREWARM=1: precalienta en un hilo aparte (no bloquea el
        arranque). Usa el MISMO proveedor (su _connection_lock serializa las
        consultas con las del usuario), solo modelos con la conexión ya abierta,
        lotes pequeños con tiempo límite, y sus consultas no cuentan en el turno
        del usuario (DomainCache.background). Desactivado por defecto."""
        flag = str(os.getenv("POWERBI_DOMAIN_PREWARM") or "").strip().lower()
        if flag not in ("1", "true", "si", "sí", "yes") or self.powerbi_provider is None:
            return None

        def run():
            try:
                with self._domain_cache().background():
                    self.prewarm_domains(only_open_connections=True)
            except Exception:
                # solo optimización: los dominios se consultan al necesitarlos
                logger.debug("precalentado de dominios en segundo plano falló", exc_info=True)

        thread = threading.Thread(target=run, name="precalentar-dominios", daemon=True)
        thread.start()
        return thread

    def _prefetch_values(self, semantic_model, fields, limit=None, max_batches=None, lead=False):
        """Trae en lotes pequeños los dominios de texto de baja cardinalidad de
        `fields` que aún no están en caché, en el orden dado (prioridad). Solo
        adelanta consultas que se harían igual: los valores no cambian.
        `max_batches=1` + `lead=True`: búsqueda incremental (solo el siguiente
        lote, y solo si la primera columna entra a un lote)."""
        if not semantic_model or not fields:
            return
        columns = [
            (field.get("table"), field.get("column"),
             self._raw_column_type(semantic_model, field.get("table"), field.get("column")))
            for field in fields if field.get("table") and field.get("column")
        ]
        try:
            self._domain_cache().prefetch(semantic_model, columns, limit=limit, max_batches=max_batches,
                                          lead=lead)
        except Exception:
            # el lote es solo una optimización: get() consulta columna por columna
            logger.debug("precarga de dominios por lote falló", exc_info=True)

    def _prefetch_next(self, semantic_model, fields, position, limit=None, skip=()):
        """Búsqueda incremental: antes de leer fields[position], trae en un lote
        (si hace falta) esa columna y las siguientes de baja cardinalidad. Así se
        consulta solo lo que se llega a revisar: el llamador se detiene en la
        primera coincidencia fuerte."""
        field = fields[position]
        cache = self._domain_cache()
        if cache is None or cache.cached(semantic_model, field.get("table"), field.get("column"),
                                         limit=limit or 2500) is not None:
            return
        rest = [
            item for item in fields[position:]
            if (normalize_text(item.get("table")), normalize_text(item.get("column"))) not in skip
        ]
        self._prefetch_values(semantic_model, rest, limit=limit, max_batches=1, lead=True)

    def _value_match_score(self, question, value, value_hint=None, allow_short=False):
        q = normalize_text(value_hint or question)
        v = normalize_text(value)
        if not q or not v:
            return 0.0
        # Códigos cortos («M», «F», «A1»): solo si el texto pedido ES el valor
        # (filtro explícito «sexo M»); jamás como subcadena de otra palabra.
        if len(v) < 3:
            return 1.10 if (allow_short and q == v) else 0.0
        if _exact_phrase(q, v):
            return 1.10

        # «total», «número» o la forma de la pregunta («momento», «duran»)
        # nunca bastan para elegir un valor: «total» no es SALUD TOTAL EPS
        # (que sí coincide si se nombra completo, ver _exact_phrase).
        ignored = {
            canonical_token(word)
            for word in GENERIC_QUERY_WORDS | STOPWORDS | FILTER_NEUTRAL_WORDS | QUESTION_FORM_WORDS
        }
        q_tokens = [
            token for token in canonical_tokens(q)
            if len(token) >= 2 and token not in ignored and not _is_question_form_word(token)
        ]
        v_tokens = set(canonical_tokens(v))
        if not q_tokens or not v_tokens:
            return 0.0
        matched = {token for token in q_tokens if token in v_tokens}
        if not any(len(token) >= 3 for token in matched):
            return 0.0
        q_coverage = sum(1 for token in q_tokens if token in v_tokens) / len(q_tokens)
        v_coverage = len(matched) / len(v_tokens)
        if q_coverage == 1.0 or v_coverage == 1.0:
            return min(1.05, 0.94 + min(len(matched), 4) * 0.02)
        if q_coverage >= 0.60:
            return 0.72 + 0.22 * q_coverage
        return 0.0

    def _value_contradiction(self, text, value, values, field, origin):
        """Motivo por el que `value` contradice el texto pedido (ver
        `value_contradiction`), anotado en el razonamiento; None si no."""
        reason = value_contradiction(text, value, values)
        if reason:
            self._note(
                f"{origin}: no se eligió {field.get('table')}[{field.get('column')}] = {value}: {reason}"
            )
        return reason

    def _resolve_value(self, question, field, semantic_model, value_hint=None, context=None):
        """Valor explícito pedido. `context` es la mención completa
        («menores de edad» cuando la columna se llama MENORES y la pista es
        «edad»): con ella se descartan los valores que contradicen la palabra
        distintiva de la pregunta (MAYORES DE EDAD) aunque puntúen igual."""
        values = self._get_values(semantic_model, field["table"], field["column"], essential=True)
        if values is None:
            return None
        scored = []
        for value in values:
            score = self._value_match_score(
                question, value, value_hint=value_hint, allow_short=bool(value_hint)
            )
            if score > 0:
                scored.append((score, value))
        scored.sort(key=lambda item: (item[0], len(normalize_text(item[1]))), reverse=True)
        text = " ".join(part for part in (context, value_hint) if part) or question
        for score, value in scored:
            if score < 0.84:
                break
            if self._value_contradiction(text, value, values, field, "filtro explícito"):
                continue
            return {
                "value": value, "score": round(score, 4),
                "tokens": set(canonical_tokens(value)),
            }
        return None

    # ---------------- group / filter parsing ----------------
    def _clean_tail(self, value, metric):
        text = normalize_text(value)
        removals = self._metric_reports(metric) + [metric.get("semantic_model")]
        # «por servicio en lavanderia»: el informe «TABLERO LAVANDERIA» también
        # se nombra sin la palabra «tablero».
        short_names = [
            re.sub(r"^(?:tablero|informe|dashboard)\s+(?:de\s+(?:la\s+|las\s+|los\s+)?)?", "", normalize_text(r))
            for r in removals if r
        ]
        removals += [name for name in short_names if len(name) >= 4]
        for removal in removals:
            normalized = normalize_text(removal)
            if normalized:
                text = re.sub(r"\ben\s+(?:el|la)?\s*" + re.escape(normalized) + r"\b.*$", "", text)
        text = re.sub(r"\ben\s+20\d{2}\b", "", text)
        for month in MONTHS:
            text = re.sub(r"\ben\s+" + re.escape(month) + r"(?:\s+de\s+20\d{2})?\b", "", text)
        return re.sub(r"\s+", " ", text).strip()
