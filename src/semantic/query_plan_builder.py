import json
import math
import re
import unicodedata
from datetime import date, timedelta
from difflib import SequenceMatcher
from pathlib import Path

from src.semantic.period_parser import (
    GRANULARITY_LABELS,
    MONTH_NAMES as PERIOD_MONTH_NAMES,
    MONTHS as PERIOD_MONTHS,
    TO_DATE_WORDS,
    PeriodParser,
    as_date,
    neutral_phrases,
    split_period,
    year_months,
)

MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

GENERIC_QUERY_WORDS = {
    "cuanto", "cuantos", "cuantas", "cual", "cuales", "es", "son",
    "hay", "hubo", "tiene", "tienen", "valor", "cantidad",
    "dame", "muestra", "mostrar", "del", "de", "la", "el",
    "los", "las", "un", "una", "en", "al", "para", "por",
    "corresponden", "correspondiente", "correspondientes", "tablero",
    "informe", "institucionales",
}

# Palabras discriminativas para elegir métrica (p. ej. «Total Cirugías»
# frente a «Cirugías»), pero sin valor como filtro: no deben quedar como
# «término sin aplicar» ni intentar resolverse como valor de dimensión.
FILTER_NEUTRAL_WORDS = {"total", "numero"}

# Relleno conversacional que nunca explica ni agrega significado.
STOPWORDS = {
    "a", "al", "con", "sin", "que", "y", "o", "u", "e", "me", "mi", "se",
    "su", "sus", "lo", "le", "les", "fue", "fueron", "ser", "sido", "esta",
    "este", "estos", "estas", "ese", "esa", "hay", "hubo", "han", "ha",
    "dentro", "segun", "mes", "ano", "anio", "durante", "favor", "por",
    "dime", "dame", "quiero", "saber", "cuanto", "cuantos", "cuanta",
    "cuantas", "cual", "cuales", "como", "donde", "cuando", "tuvo",
    "tuvieron", "tiene", "tienen", "son", "es", "del", "de", "la", "el",
    "los", "las", "un", "una", "unos", "unas", "en", "para", "muestra",
    "mostrar", "valor", "cantidad", "informe", "tablero", "modelo",
    "semantico", "dashboard", "reporte", "pagina", "hacer", "ver",
}
# Forma de pedir el dato («necesito saber», «me podrías indicar»): no es
# filtro ni métrica. _is_request_word tolera además un error de tipeo.
REQUEST_WORDS = {
    "necesito", "necesitamos", "necesitaria", "necesitaba", "requiero",
    "quisiera", "queria", "quisieramos", "gustaria", "conocer", "consultar",
    "obtener", "informacion", "info", "porfa", "porfavor", "puedes", "puede",
    "podrias", "podria", "pueden", "ayudame", "indicame",
    "indiqueme", "dimelo", "muestrame", "mostrarme", "regalame", "dar",
    "darme", "decir", "decirme", "hola", "gracias", "nos", "dato", "datos",
    "cifra", "cifras",
}
STOPWORDS |= REQUEST_WORDS

# Verbos, auxiliares y adverbios corrientes de la pregunta («hay registrado»,
# «lleva», «tuvimos», «se hicieron», «más»): nunca son un filtro ni un valor
# de dimensión, así que no deben quedar como «palabras sin interpretar».
COMMON_VERB_WORDS = {
    "registrado", "registrados", "registrada", "registradas", "registraron",
    "registramos", "lleva", "llevan", "llevamos", "llevaba", "llevaban",
    "llevado", "tuvimos", "tenemos", "tenia", "tenian", "habia", "habian",
    "habido", "hicieron", "hizo", "hecho", "hechos", "hecha", "hechas",
    "hacen", "hace", "va", "van", "vamos", "iba", "iban", "mas", "menos",
    "aproximadamente", "exactamente", "alrededor", "solo", "solamente",
    "top", "ranking",
}
STOPWORDS |= COMMON_VERB_WORDS

# Sinónimos de negocio por palabra (genéricos, no de un tablero concreto):
# «kilos de ropa» o «cuánto pesaron» preguntan por el PESO.
BUSINESS_TOKEN_SYNONYMS = {
    "kilo": "peso", "kilos": "peso", "kg": "peso", "kgs": "peso",
    "kilogramo": "peso", "kilogramos": "peso", "pesaron": "peso",
    "pesamos": "peso", "pesaba": "peso", "pesaban": "peso",
}

GENERIC_PAGE_WORDS = {"general", "inicio", "resumen", "principal", "home", "detalle", "portada", "indicadores"}

TECHNICAL_SUFFIXES = {"ok", "id", "cod", "key"}

TEMPORAL_WORDS = {"date", "fecha", "ano", "anio", "mes", "year", "month", "dia", "day"}

DESCRIPTIVE_PATTERNS = (
    "que significa", "que es", "que quiere decir", "como se calcula",
    "como se define", "definicion de", "explica",
    "que muestra", "que muestran", "que contiene", "que informacion",
    "que filtros", "que filtro", "para que sirve", "para que se usa",
    "como se mide", "como se interpreta", "como funciona", "que mide",
    "de que trata", "que visuales", "que paginas", "objetivo del",
    "descripcion del", "describe",
)

# Términos que, por sí solos, indican una consulta cuantitativa.
NUMERIC_TERM_PATTERNS = (
    r"cuant[oa]s?", r"cantidad", r"numero", r"total", r"promedio", r"media",
    r"porcentaje", r"valor", r"capacidad", r"giro", r"ocupacion",
    r"ocupacional", r"ingresos", r"egresos", r"participacion", r"proporcion",
    r"tasa", r"variacion", r"representa", r"representan", r"suma",
    r"sumatoria", r"%",
)

# Verbos/interrogativos que piden un dato ("dime el peso...", "cuál fue el ...").
QUERY_VERB_PATTERNS = (
    r"(?:y\s+)?(?:que|cual(?:es)?)\s+(?:fue|fueron|es|son|ha\s+sido|han\s+sido|seria|serian|era|eran)",
    r"(?:y\s+)?(?:dime|dame|dinos|muestrame|muestra|mostrar|muestre|indica|indicame|"
    r"consulta|calcula|obten|entregame|reporta|reportame|informame|necesito|"
    r"quiero|quisiera|me\s+(?:puedes|podrias|das|dices|indicas|muestras)|"
    r"puedes|podrias)",
)

# Participación / proporción sobre el total de una dimensión.
SHARE_PHRASES = (
    r"(?:el\s+|la\s+)?(?:porcentaje|%)\s+de\s+participacion(?:\s+porcentual)?",
    r"(?:el\s+|la\s+)?participacion(?:\s+porcentual)?(?:\s+relativa)?",
    r"(?:el\s+|la\s+)?(?:porcentaje|%)\s+(?:del|sobre\s+el)\s+total",
    r"(?:la\s+|una\s+)?proporcion(?:\s+(?:del|sobre\s+el)\s+total)?",
    r"(?:el\s+)?peso\s+relativo",
    r"(?:que\s+)?(?:porcentaje|parte|fraccion)\s+(?:del\s+total\s+)?(?:representa|representan|supone|aporta)",
    r"cuanto\s+(?:representa|representan|aporta|aportan)",
    r"que\s+tanto\s+(?:representa|representan|aporta|aportan)",
)
SHARE_RE = re.compile(
    r"(?<![a-z0-9])(?:" + "|".join(SHARE_PHRASES) + r")(?![a-z0-9])"
)
FILLER_WORDS = {
    "y", "e", "el", "la", "los", "las", "un", "una", "de", "del", "en", "al",
    "que", "cual", "cuales", "como", "fue", "fueron", "es", "son", "tuvo",
    "tuvieron", "tiene", "tienen", "hubo", "hay", "se", "su", "sus", "mes",
    "ano", "servicio", "tablero", "informe", "total", "con", "por", "para",
    "cuanto", "cuanta", "cuantos", "cuantas", "dime", "dame", "muestra",
    "numero", "valor", "porcentaje", "sobre", "durante", "entre",
}

DIMENSION_SYNONYMS = {
    "servicio": {"servicio", "servicios", "unidad", "unidades", "area", "areas"},
    "aseguradora": {"asegurador", "aseguradora", "aseguradoras", "eps", "pagador", "pagadores"},
    "especialidad": {"especialidad", "especialidades"},
    "cirujano": {"cirujano", "cirujanos", "medico", "medicos"},
    "estado": {"estado", "estados", "situacion"},
    "causa": {"causa", "causas", "motivo", "motivos"},
    "modalidad": {"modalidad", "modalidades", "tipo atencion", "tipo de atencion"},
    "sexo": {"sexo", "genero"},
    "clasificacion": {"clasificacion", "triage"},
    "tipo": {"tipo", "tipos"},
    # Persona que registra/atiende («NOMBRE_COMPLETO», «USUARIO»).
    "colaborador": {
        "nombre completo", "usuario", "usuarios", "colaborador", "colaboradores",
        "empleado", "empleados", "funcionario", "funcionarios", "trabajador",
        "trabajadores", "operario", "operarios",
    },
}


def normalize_text(value):
    value = str(value or "").lower().strip()
    value = "".join(
        char for char in unicodedata.normalize("NFD", value)
        if unicodedata.category(char) != "Mn"
    )
    value = re.sub(r"[^a-z0-9%]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def canonical_token(token):
    token = normalize_text(token)
    if not token:
        return ""
    token = BUSINESS_TOKEN_SYNONYMS.get(token, token)
    if token.endswith("iones") and len(token) > 6:
        return token[:-5] + "ion"
    if token.endswith("ales") and len(token) > 5:
        return token[:-2]
    if token.endswith("ares") and len(token) > 5:
        return token[:-2]
    if token.endswith("ores") and len(token) > 5:
        return token[:-2]
    if token.endswith("s") and len(token) > 4:
        return token[:-1]
    return token


def canonical_tokens(value):
    result = []
    for token in normalize_text(value).split():
        item = canonical_token(token)
        if item:
            result.append(item)
    return result


def _token_similarity(left, right):
    if left == right:
        return 1.0
    shortest = min(len(left), len(right))
    # Palabras cortas solo coinciden si son idénticas: «mayo» != «mayor».
    if shortest < 6:
        return 0.0
    # Prefijo solo cuando una palabra es prefijo literal de la otra
    # (ocupacion/ocupacional). programada != programacion,
    # hospitalario != hospitalizacion, consulta != consultorio.
    if abs(len(left) - len(right)) <= 3 and (left.startswith(right) or right.startswith(left)):
        return 0.90
    ratio = SequenceMatcher(None, left, right).ratio()
    return ratio if ratio >= 0.88 else min(ratio, 0.80)


# Solo verbos de petición que nunca nombran un valor: «consulta» o «ayudas»
# sí pueden ser valores reales (consulta externa, ayudas diagnósticas).
_TYPO_REQUEST_TOKENS = {
    canonical_token(word) for word in (
        "necesito", "necesitamos", "necesitaria", "quisiera", "gustaria",
        "informacion", "podrias", "indicame", "muestrame",
    )
}
_REQUEST_TOKENS = {canonical_token(word) for word in REQUEST_WORDS}


def _is_request_word(token):
    """Palabra de petición (token canónico), también con un error de tipeo («necsito»)."""
    if token in _REQUEST_TOKENS:
        return True
    if len(token) < 6:
        return False
    return any(
        SequenceMatcher(None, token, word).ratio() >= 0.88
        # Letras intercambiadas («nesecito»): mismas letras y mismo inicio.
        or (token[:2] == word[:2] and sorted(token) == sorted(word))
        for word in _TYPO_REQUEST_TOKENS
    )


def _exact_phrase(question, candidate):
    return bool(
        question and candidate
        and re.search(r"(?<![a-z0-9])" + re.escape(candidate) + r"(?![a-z0-9])", question)
    )


def _phrase_score(question, candidate, weights=None):
    """Qué tanto cubre la pregunta al candidato.

    `weights` (token -> peso IDF) hace que palabras genéricas del catálogo
    (cirugías, pacientes...) valgan poco frente a las distintivas.
    """
    q = normalize_text(question)
    c = normalize_text(candidate)
    if not q or not c:
        return 0.0
    weights = weights or {}

    if _exact_phrase(q, c):
        specificity = min(len(c.split()), 6)
        base = min(1.20, 1.00 + 0.03 * specificity)
        if weights:
            base += 0.10 * min(3.0, sum(weights.get(t, 1.0) for t in canonical_tokens(c)))
        return base

    q_tokens = canonical_tokens(q)
    c_tokens = canonical_tokens(c)
    if not q_tokens or not c_tokens:
        return 0.0

    matched = []
    for candidate_token in c_tokens:
        best = max(
            (_token_similarity(candidate_token, question_token) for question_token in q_tokens),
            default=0.0,
        )
        matched.append(best)

    # Todas las palabras del candidato aparecen tal cual (aunque separadas):
    # «total de cirugías» cubre por completo «Total Cirugías».
    if len(c_tokens) >= 2 and all(value == 1.0 for value in matched):
        base = min(1.20, 1.00 + 0.02 * min(len(c_tokens), 6))
        if weights:
            base += 0.10 * min(3.0, sum(weights.get(t, 1.0) for t in c_tokens))
        return base

    token_weights = [weights.get(token, 1.0) for token in c_tokens]
    coverage = sum(w for w, value in zip(token_weights, matched) if value >= 0.82) / sum(token_weights)
    if coverage < 0.60:
        return 0.0

    average = sum(matched) / len(matched)
    precision = min(len(c_tokens), len(q_tokens)) / max(len(c_tokens), len(q_tokens))
    return min(0.99, 0.68 * coverage + 0.24 * average + 0.08 * precision)


def _original_phrase(question, phrase):
    """Fragmento de la pregunta original (con tildes) que corresponde a una
    frase normalizada: «este ano» -> «este año». Si no se ubica, la frase."""
    target = normalize_text(phrase)
    if not target:
        return phrase
    words = list(re.finditer(r"[^\W_]+|%", str(question or "")))
    for i in range(len(words)):
        joined = ""
        for j in range(i, len(words)):
            joined = (joined + " " + normalize_text(words[j].group(0))).strip()
            if joined == target or re.sub(r"(\d) (er|ero|ro|do|to|o|a)\b", r"\1\2", joined) == target:
                return question[words[i].start():words[j].end()]
            if len(joined) > len(target) + 4:
                break
    return phrase


def _unique_strings(values):
    result = []
    seen = set()
    for value in values:
        if not value:
            continue
        key = normalize_text(value)
        if key and key not in seen:
            result.append(str(value))
            seen.add(key)
    return result


class QueryPlanBuilder:
    """Planificador determinista: métrica -> modelo -> dimensiones -> DAX."""

    def __init__(
        self,
        master_metrics_path,
        visual_catalog_path,
        source_router,
        powerbi_provider,
        project_root=None,
        min_metric_score=0.74,
        ambiguity_margin=0.055,
        max_implicit_dimensions=6,
        today=None,
    ):
        # Fecha de referencia de los periodos relativos («este año», «mes
        # pasado»): date, callable o None (= hoy). Las pruebas la fijan.
        self.today = today
        self.master_metrics_path = Path(master_metrics_path)
        self.visual_catalog_path = Path(visual_catalog_path)
        self.source_router = source_router
        self.powerbi_provider = powerbi_provider
        self.project_root = Path(
            project_root or self.master_metrics_path.resolve().parents[2]
        ).resolve()
        self.min_metric_score = float(min_metric_score)
        self.ambiguity_margin = float(ambiguity_margin)
        self.max_implicit_dimensions = int(max_implicit_dimensions)
        self.master = self._load_json(self.master_metrics_path, {})
        self.visual_catalog = self._load_json(self.visual_catalog_path, {})
        self.metrics = list(self.master.get("metrics", []) or [])
        self.value_cache = {}
        self.domain_errors = {}  # Fallos temporales XMLA: nunca cachear como dominio vacío.
        self.reports = self._normalize_reports(self.visual_catalog)
        self.dimension_fields = self._build_dimension_index()
        self.static_values = self._build_static_value_index()

    def _load_json(self, path, default):
        if not Path(path).exists():
            return default
        return json.loads(Path(path).read_text(encoding="utf-8"))

    def _normalize_reports(self, catalog):
        reports = list(catalog.get("reports", []) or [])
        if reports:
            return reports
        if catalog.get("semantic_model"):
            return [{
                "report": catalog.get("report") or catalog.get("semantic_model"),
                "semantic_model": catalog.get("semantic_model"),
                "source_group": catalog.get("source_group"),
                "pages": catalog.get("pages", []),
                "metrics": catalog.get("metrics", []),
            }]
        return []

    # ---------------- metrics ----------------
    def _metric_names(self, metric):
        values = [metric.get("label"), metric.get("measure")]
        values.extend(metric.get("aliases", []) or [])
        for appearance in metric.get("appearances", []) or []:
            values.extend([
                appearance.get("visual_title"),
                appearance.get("native_query_ref"),
            ])
        return _unique_strings(values)

    def _metric_reports(self, metric):
        values = [metric.get("report")]
        values.extend(metric.get("reports", []) or [])
        for appearance in metric.get("appearances", []) or []:
            values.append(appearance.get("report"))
        return _unique_strings(values)

    def _metric_pages(self, metric):
        values = [metric.get("dashboard")]
        for appearance in metric.get("appearances", []) or []:
            values.append(appearance.get("page_display_name"))
        return _unique_strings(values)

    def _metric_visual_ids(self, metric):
        return {
            str(appearance.get("visual_id"))
            for appearance in metric.get("appearances", []) or []
            if appearance.get("visual_id")
        }

    def _source_context(self, question, dashboard=None):
        try:
            return self.source_router.resolve(question=question, dashboard=dashboard)
        except Exception as error:
            return {
                "status": "error",
                "routing_strength": "none",
                "error": f"{type(error).__name__}: {error}",
            }

    def _dedupe_metrics(self, metrics):
        result = []
        seen = set()
        for metric in metrics:
            reports = metric.get("reports", []) or []
            key = (
                normalize_text(metric.get("semantic_model")),
                normalize_text(metric.get("report") or (reports[0] if reports else None)),
                normalize_text(metric.get("label")),
                normalize_text(metric.get("dax_expression")),
            )
            if key in seen:
                continue
            result.append(metric)
            seen.add(key)
        return result

    def _metric_business_question(self, question, source_context):
        text = normalize_text(question)

        removals = [
            source_context.get("report"),
            source_context.get("semantic_model"),
            source_context.get("source_group"),
        ]

        for value in removals:
            normalized = normalize_text(value)
            if normalized:
                text = re.sub(
                    r"(?<![a-z0-9])" + re.escape(normalized) + r"(?![a-z0-9])",
                    " ",
                    text,
                )

        text = re.sub(r"\b(?:tablero|informe|modelo semantico)\b", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    # ---- pesos IDF: palabras repetidas en todo el catálogo valen poco ----
    def _token_weight_index(self):
        if getattr(self, "_token_weights", None) is not None:
            return self._token_weights
        labels = set()
        document_frequency = {}
        for metric in self._dedupe_metrics(self.metrics):
            if metric.get("validation_status") != "approved":
                continue
            for name in (metric.get("label"), metric.get("measure")):
                key = normalize_text(name)
                if not key or key in labels:
                    continue
                labels.add(key)
                for token in set(canonical_tokens(key)):
                    document_frequency[token] = document_frequency.get(token, 0) + 1
        total = len(labels)
        weights = {}
        if total > 1:
            for token, count in document_frequency.items():
                weights[token] = 0.25 + 0.75 * (1.0 - count / total)
        self._token_weights = weights
        self._known_labels = labels
        return weights

    def _token_weight(self, token):
        return self._token_weight_index().get(token, 1.0)

    def _unexplained_penalty(self, business_question, explained_tokens):
        """Castiga palabras distintivas de la pregunta que el candidato no explica."""
        ignored = {canonical_token(word) for word in STOPWORDS | GENERIC_QUERY_WORDS}
        ignored.update(canonical_token(word) for word in MONTHS)
        ignored.update(self._period_words(business_question))  # «este año», «últimos 3 meses»
        penalty = 0.0
        for token in set(canonical_tokens(business_question)):
            if token in ignored or token.isdigit() or len(token) < 3 or _is_request_word(token):
                continue
            if any(_token_similarity(token, other) >= 0.82 for other in explained_tokens):
                continue
            penalty += 0.12 * self._token_weight(token)
        return min(0.45, penalty)

    def _page_bonus(self, question_tokens, metric, name_tokens):
        """Mencionar la página/dashboard de la métrica desempata de verdad (+0.20).

        Se ignoran páginas genéricas y las palabras que ya forman parte del
        nombre de la métrica (una página «Cirugías Realizadas» no debe premiar
        a la métrica «Cirugías Realizadas» solo por llamarse igual).
        """
        stop = {canonical_token(word) for word in STOPWORDS}
        for page in self._metric_pages(metric):
            tokens = [
                token for token in canonical_tokens(page)
                if token not in name_tokens and token not in GENERIC_PAGE_WORDS
                and token not in stop
            ]
            if not tokens:
                continue
            if len(tokens) == 1 and self._token_weight(tokens[0]) < 0.5:
                continue
            if all(
                any(_token_similarity(token, other) >= 0.82 for other in question_tokens)
                for token in tokens
            ):
                return 0.20
        return 0.0

    def _logical_key(self, metric):
        return (
            normalize_text(metric.get("semantic_model")),
            normalize_text(metric.get("table")),
            normalize_text(metric.get("dax_expression")),
        )

    _SUGGESTION_LIMIT = 6

    def _metric_suggestions(self, business_question, model_hint="", strong=False,
                            ratio=0.6, limit=_SUGGESTION_LIMIT):
        """Métricas que comparten alguna palabra distintiva con la pregunta.

        No alcanzan para responder, pero sí para contrapreguntar: «¿cuántas
        cirugías hay?» -> Total cirugías / Cirugías realizadas / ...
        """
        weights = self._token_weight_index()
        ignored = {
            canonical_token(word)
            for word in STOPWORDS | GENERIC_QUERY_WORDS | FILTER_NEUTRAL_WORDS | set(MONTHS)
        }
        question_tokens = {
            token for token in canonical_tokens(business_question)
            if len(token) >= 4 and not token.isdigit()
            and token not in ignored and not _is_request_word(token)
        }
        if not question_tokens:
            return []

        suggestions = []
        for metric in self._dedupe_metrics(self.metrics):
            if metric.get("validation_status") != "approved":
                continue
            best_score, best_name, best_extra = 0.0, None, 0
            for name in self._metric_names(metric):
                name_tokens = canonical_tokens(name)
                score = sum(
                    weights.get(token, 1.0) for token in question_tokens
                    if any(_token_similarity(token, other) >= 0.88 for other in name_tokens)
                )
                # Palabras del nombre que la pregunta no menciona: a igual
                # puntaje va primero el nombre más cercano («Total cirugías»
                # antes que «Cirugías programadas» para «¿cuántas cirugías?»).
                extra = sum(
                    1 for other in set(name_tokens)
                    if other not in ignored and not any(
                        _token_similarity(other, token) >= 0.88 for token in question_tokens
                    )
                )
                if score > best_score or (score == best_score and score > 0 and extra < best_extra):
                    best_score, best_name, best_extra = score, name, extra
            if best_score <= 0:
                continue
            if model_hint and normalize_text(metric.get("semantic_model")) == model_hint:
                best_score += 0.20 if strong else 0.01
            # Las que el usuario ve en un tablero van primero.
            if not (metric.get("appearances") or []):
                best_score -= 0.25
            suggestions.append({
                "metric": metric, "score": round(best_score, 4),
                "business_score": round(best_score, 4), "matched_name": best_name,
                "_extra": best_extra,
            })

        suggestions.sort(key=lambda item: (
            -item["score"], item["_extra"], normalize_text(item["metric"].get("label")),
            str(item["metric"].get("metric_id")),
        ))
        result, seen = [], set()
        for item in suggestions:
            key = self._logical_key(item["metric"])
            if key in seen:
                continue
            seen.add(key)
            if item["score"] > 0:
                result.append(item)
        if not result:
            return []
        # Solo las cercanas a la mejor: una palabra suelta compartida con una
        # métrica lejana no debe llenar la lista.
        best = result[0]["score"]
        return [item for item in result if item["score"] >= best * ratio][:limit]

    def _resolve_metric(self, question, source_context, selected_metric_id=None,
                        with_suggestions=False, candidate_limit=8):
        # Una selección realizada durante una aclaración manda por ID,
        # no por el texto de la respuesta del usuario.
        if selected_metric_id is not None:
            for metric in self._dedupe_metrics(self.metrics):
                if metric.get("validation_status") != "approved":
                    continue
                if str(metric.get("metric_id")) == str(selected_metric_id):
                    return {
                        "status": "resolved", "metric": metric,
                        "matched_name": metric.get("label"), "score": 10.0,
                        "candidates": [{"metric": metric, "score": 10.0,
                                        "business_score": 10.0,
                                        "matched_name": metric.get("label")}],
                    }
            return {"status": "not_found", "candidates": []}

        weights = self._token_weight_index()
        business_question = self._metric_business_question(question, source_context)
        normalized_business = normalize_text(business_question)
        question_tokens = canonical_tokens(business_question)
        resolved_routing = source_context.get("status") == "resolved"
        strong = resolved_routing and source_context.get("routing_strength") == "strong"
        weak = resolved_routing and source_context.get("routing_strength") == "weak"
        model_hint = normalize_text(source_context.get("semantic_model")) if (strong or weak) else ""
        report_hint = normalize_text(source_context.get("report")) if strong else ""
        candidates = []

        def not_found(weak_candidates):
            result = {"status": "not_found", "candidates": weak_candidates}
            if with_suggestions:
                result["suggestions"] = self._metric_suggestions(
                    business_question, model_hint=model_hint, strong=strong,
                )
            return result

        for metric in self._dedupe_metrics(self.metrics):
            if metric.get("validation_status") != "approved":
                continue
            metric_model = normalize_text(metric.get("semantic_model"))
            metric_reports = [normalize_text(value) for value in self._metric_reports(metric)]

            primary_label = metric.get("label") or ""
            primary_norm = normalize_text(primary_label)
            primary_score = _phrase_score(business_question, primary_label, weights)
            label_is_exact = _exact_phrase(normalized_business, primary_norm)

            titles = _unique_strings(
                appearance.get("visual_title")
                for appearance in metric.get("appearances", []) or []
            )
            exact_title = None
            for title in titles:
                title_norm = normalize_text(title)
                if title_norm == primary_norm or not _exact_phrase(normalized_business, title_norm):
                    continue
                # Un título compartido con la etiqueta de OTRA métrica
                # (EGRESOS de AÑO ACTUAL) solo es alias, no nombre propio.
                if title_norm in self._known_labels:
                    continue
                exact_title = title
                break

            aliases = [
                item for item in self._metric_names(metric)
                if normalize_text(item) != primary_norm
            ]
            best_alias = max(
                ((_phrase_score(business_question, name, weights), name) for name in aliases),
                key=lambda pair: pair[0], default=(0.0, None),
            )
            label_weight = sum(weights.get(t, 1.0) for t in canonical_tokens(primary_label))
            if label_is_exact:
                best_name = primary_label
                best_name_score = primary_score
                # Una etiqueta de una palabra genérica («Cirugías») pesa poco.
                name_priority = 0.32 * min(1.0, label_weight)
            elif exact_title:
                best_name = exact_title
                best_name_score = _phrase_score(business_question, exact_title, weights)
                name_priority = 0.32 * min(1.0, sum(weights.get(t, 1.0) for t in canonical_tokens(exact_title)))
            elif best_alias[0] > primary_score:
                best_name = best_alias[1]
                best_name_score = best_alias[0]
                name_priority = 0.0
            else:
                best_name = primary_label
                best_name_score = primary_score
                name_priority = 0.0

            if best_name_score <= 0:
                continue
            score = best_name_score + name_priority

            in_hint_model = bool(model_hint) and metric_model == model_hint
            in_hint_report = bool(report_hint) and (
                not metric_reports or report_hint in metric_reports
            )
            # Solo un informe/alias nombrado (routing fuerte) pesa. El routing
            # débil sale del nombre de una página, que puede coincidir con el
            # nombre de la métrica y no debe desempatar por sí solo.
            if in_hint_model and strong:
                score += 0.20
                if report_hint and in_hint_report:
                    score += 0.10
            elif in_hint_model:
                score += 0.01  # solo ordena opciones; no rompe un empate (< margen)

            explained = set()
            for value in [*self._metric_names(metric), *self._metric_reports(metric),
                          *self._metric_pages(metric), metric.get("semantic_model")]:
                explained.update(canonical_tokens(value))
            name_tokens = set(canonical_tokens(best_name)) | set(canonical_tokens(primary_label))
            score -= self._unexplained_penalty(business_question, explained)
            score += self._page_bonus(question_tokens, metric, name_tokens)

            # Medidas auxiliares (sin visual donde aparezcan) pierden frente a
            # las que el usuario ve en un tablero, salvo que las nombre exacto.
            if not (metric.get("appearances") or []):
                score -= 0.08 if (label_is_exact and label_weight >= 1.0) else 0.25

            candidates.append({
                "metric": metric,
                "score": round(score, 4),
                "business_score": round(best_name_score, 4),
                "matched_name": best_name,
                "exact_primary_label": label_is_exact,
                "hinted": bool(in_hint_model and (not report_hint or in_hint_report)),
            })

        if not candidates:
            return not_found([])

        # Informe nombrado explícitamente y la métrica existe allí: solo
        # compiten las métricas de ese informe. Si no existe allí, el
        # nombre del tablero solo orienta (boost) y se avisa.
        hint_ignored = False
        if strong:
            hinted = [item for item in candidates if item["hinted"]
                      and item["business_score"] >= self.min_metric_score]
            if hinted:
                candidates = hinted
            else:
                hint_ignored = True

        def order(item):
            metric = item["metric"]
            return (
                -item["score"], normalize_text(metric.get("semantic_model")),
                normalize_text(metric.get("report")), normalize_text(metric.get("label")),
                str(metric.get("metric_id")),
            )

        candidates.sort(key=order)
        groups = []
        seen = set()
        for item in candidates:
            key = self._logical_key(item["metric"])
            if key in seen:
                continue
            seen.add(key)
            groups.append(item)

        best = groups[0]
        if best["business_score"] < self.min_metric_score:
            return not_found(groups[:candidate_limit])
        tied = [
            item for item in groups
            if best["score"] - item["score"] < self.ambiguity_margin
            and item["business_score"] >= self.min_metric_score
        ]
        if len(tied) > 1:
            rest = [item for item in groups if item not in tied]
            limit = None if candidate_limit is None else max(candidate_limit, len(tied))
            return {"status": "ambiguous", "candidates": (tied + rest)[:limit]}

        return {
            "status": "resolved", "metric": best["metric"],
            "matched_name": best["matched_name"], "score": best["score"],
            "candidates": groups[:candidate_limit],
            "source_hint_ignored": hint_ignored,
        }

    def alternative_metrics(self, question, intent_result=None, exclude_ids=(),
                            limit=_SUGGESTION_LIMIT):
        """Indicadores más cercanos a la pregunta que aún no se ofrecieron.

        Se usa con «Ninguna de las anteriores»: primero los candidatos del
        resolutor (en su orden) y luego los que solo comparten alguna palabra
        distintiva con la pregunta. Excluye las métricas ya ofrecidas y sus
        duplicados (misma medida publicada en otro informe).
        """
        intent_result = intent_result or {}
        source_context = self._source_context(question, dashboard=intent_result.get("dashboard"))
        excluded_ids = {str(value) for value in exclude_ids or ()}
        excluded_keys = {
            self._logical_key(metric) for metric in self.metrics
            if str(metric.get("metric_id")) in excluded_ids
        }
        resolution = self._resolve_metric(question, source_context, candidate_limit=None)
        resolved_routing = source_context.get("status") == "resolved"
        strength = source_context.get("routing_strength")
        strong = resolved_routing and strength == "strong"
        model_hint = (
            normalize_text(source_context.get("semantic_model"))
            if resolved_routing and strength in ("strong", "weak") else ""
        )
        suggestions = self._metric_suggestions(
            self._metric_business_question(question, source_context),
            model_hint=model_hint, strong=strong, ratio=0.0, limit=None,
        )
        result, seen = [], set(excluded_keys)
        for item in [*(resolution.get("candidates") or []), *suggestions]:
            metric = item.get("metric") or {}
            key = self._logical_key(metric)
            if str(metric.get("metric_id")) in excluded_ids or key in seen:
                continue
            seen.add(key)
            result.append({key_: value for key_, value in item.items() if not key_.startswith("_")})
            if limit is not None and len(result) >= limit:
                break
        return result

    # ---------------- dimension index ----------------
    def _physical_column(self, field):
        if field.get("column"):
            return field.get("column")
        if field.get("kind") == "hierarchy_level":
            parts = [part for part in str(field.get("query_ref") or "").split(".") if part]
            if len(parts) >= 2:
                return parts[1]
        return None

    def _field_aliases(self, field):
        values = [
            field.get("display_name"), field.get("native_query_ref"),
            field.get("column"), field.get("level"), field.get("query_ref"),
        ]
        aliases = _unique_strings(values)
        normalized_aliases = {normalize_text(alias) for alias in aliases}
        # Sufijos técnicos (TURNO_OK, SERVICIO_ID): «turno» debe encontrar TURNO_OK.
        for alias in list(normalized_aliases):
            parts = alias.split()
            while len(parts) >= 2 and parts[-1] in TECHNICAL_SUFFIXES:
                parts = parts[:-1]
                aliases.append(" ".join(parts))
        normalized_aliases = {normalize_text(alias) for alias in aliases}
        for synonyms in DIMENSION_SYNONYMS.values():
            # Por palabra completa: OPORTUNIDAD no contiene «unidad».
            if any(
                re.search(r"(?<![a-z0-9])" + re.escape(synonym) + r"(?![a-z0-9])", alias)
                for alias in normalized_aliases for synonym in synonyms
            ):
                aliases.extend(sorted(synonyms))
        return _unique_strings(aliases)

    def _build_dimension_index(self):
        fields = []
        for report in self.reports:
            report_name = report.get("report") or report.get("semantic_model")
            semantic_model = report.get("semantic_model")
            source_group = report.get("source_group")
            for page in report.get("pages", []) or []:
                page_name = page.get("page_display_name") or page.get("page_name")
                for visual in page.get("visuals", []) or []:
                    for field in visual.get("fields", []) or []:
                        if field.get("kind") not in ("column", "hierarchy_level"):
                            continue
                        table = field.get("table")
                        column = self._physical_column(field)
                        if not table or not column:
                            continue
                        fields.append({
                            "semantic_model": semantic_model,
                            "report": report_name,
                            "source_group": source_group,
                            "page": page_name,
                            "visual_id": visual.get("visual_id"),
                            "visual_type": visual.get("visual_type"),
                            "role": field.get("role"),
                            "kind": field.get("kind"),
                            "table": table,
                            "column": column,
                            "level": field.get("level"),
                            "query_ref": field.get("query_ref"),
                            "aliases": self._field_aliases(field),
                        })
        return fields

    def _iter_filters(self, value):
        if isinstance(value, list):
            for item in value:
                yield from self._iter_filters(item)
        elif isinstance(value, dict):
            if "field" in value and isinstance(value.get("field"), dict):
                yield value
            for item in value.values():
                yield from self._iter_filters(item)

    def _build_static_value_index(self):
        result = {}
        for report in self.reports:
            semantic_model = report.get("semantic_model")
            for page in report.get("pages", []) or []:
                for filter_item in self._iter_filters(page.get("filters", {})):
                    field = filter_item.get("field", {})
                    table = field.get("table")
                    column = field.get("column")
                    if not table or not column:
                        continue
                    key = (normalize_text(semantic_model), normalize_text(table), normalize_text(column))
                    result.setdefault(key, [])
                    for value in filter_item.get("values", []) or []:
                        if value is not None and str(value) not in result[key]:
                            result[key].append(str(value))
        return result

    def _relevant_dimensions(self, metric):
        semantic_model = metric.get("semantic_model")
        reports = {normalize_text(value) for value in self._metric_reports(metric)}
        pages = {normalize_text(value) for value in self._metric_pages(metric)}
        visual_ids = self._metric_visual_ids(metric)
        candidates = {}

        for field in self.dimension_fields:
            if normalize_text(field.get("semantic_model")) != normalize_text(semantic_model):
                continue
            if reports and normalize_text(field.get("report")) not in reports:
                continue

            score = 10
            if str(field.get("visual_id")) in visual_ids:
                score += 110
            if normalize_text(field.get("page")) in pages:
                score += 65
            if normalize_text(field.get("visual_type")) == "slicer":
                score += 35
            if normalize_text(field.get("role")) in {
                "category", "group", "rows", "legend", "series", "values"
            }:
                score += 15

            key = (
                normalize_text(field.get("table")),
                normalize_text(field.get("column")),
                normalize_text(field.get("level")),
            )
            item = {**field, "relevance_score": score}
            if key not in candidates or score > candidates[key]["relevance_score"]:
                candidates[key] = item

        values = list(candidates.values())
        values.sort(key=lambda item: item["relevance_score"], reverse=True)
        return values

    def _dimension_match_score(self, text, field):
        return max((_phrase_score(text, alias) for alias in field.get("aliases", [])), default=0.0)

    def _best_dimension(self, text, candidates, exclude_temporal=False):
        scored = []
        for field in candidates:
            if exclude_temporal and self._is_temporal_field(field):
                continue
            score = self._dimension_match_score(text, field)
            if score <= 0:
                continue
            score += min(0.12, field.get("relevance_score", 0) / 1000.0)
            scored.append((score, field))
        scored.sort(key=lambda item: item[0], reverse=True)
        return scored[0][1] if scored else None

    # ---------------- actual dimension values ----------------
    def _table_ref(self, table):
        return "'" + str(table).replace("'", "''") + "'"

    def _column_ref(self, column):
        return "[" + str(column).replace("]", "]]" ) + "]"

    def _get_values(self, semantic_model, table, column):
        key = (semantic_model, table, column)
        if key in self.value_cache:
            return self.value_cache[key]

        static_key = (normalize_text(semantic_model), normalize_text(table), normalize_text(column))
        values = list(self.static_values.get(static_key, []) or [])
        dax = f'''EVALUATE\nTOPN(\n    2500,\n    FILTER(\n        SELECTCOLUMNS(\n            VALUES({self._table_ref(table)}{self._column_ref(column)}),\n            "Value", {self._table_ref(table)}{self._column_ref(column)}\n        ),\n        NOT ISBLANK([Value])\n    ),\n    [Value], ASC\n)'''
        try:
            result = self.powerbi_provider.execute_dax(dax=dax, semantic_model=semantic_model)
        except Exception as exc:
            result = {"status": "error", "error": str(exc)}

        if result.get("status") != "success":
            self.domain_errors[key] = {
                "status": result.get("status"),
                "error_type": result.get("error_type"),
                "message": str(result.get("error") or result.get("message") or "Sin detalle")[:300],
            }
            # No afirmar que un filtro fue verificado si XMLA falló,
            # aunque el PBIR tenga valores estáticos potencialmente antiguos.
            # El siguiente intento consultará de nuevo el dominio.
            return None

        self.domain_errors.pop(key, None)
        for row in result.get("rows", []) or []:
            if not row:
                continue
            value = next(iter(row.values()), None)
            if value is not None and str(value) not in values:
                values.append(str(value))
        self.value_cache[key] = values
        return values

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

        ignored = {canonical_token(word) for word in GENERIC_QUERY_WORDS | STOPWORDS}
        q_tokens = [
            token for token in canonical_tokens(q)
            if len(token) >= 2 and token not in ignored
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

    def _resolve_value(self, question, field, semantic_model, value_hint=None):
        values = self._get_values(semantic_model, field["table"], field["column"])
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
        if not scored or scored[0][0] < 0.84:
            return None
        return {
            "value": scored[0][1], "score": round(scored[0][0], 4),
            "tokens": set(canonical_tokens(scored[0][1])),
        }

    # ---------------- group / filter parsing ----------------
    def _clean_tail(self, value, metric):
        text = normalize_text(value)
        removals = self._metric_reports(metric) + [metric.get("semantic_model")]
        for removal in removals:
            normalized = normalize_text(removal)
            if normalized:
                text = re.sub(r"\ben\s+(?:el|la)?\s*" + re.escape(normalized) + r"\b.*$", "", text)
        text = re.sub(r"\ben\s+20\d{2}\b", "", text)
        for month in MONTHS:
            text = re.sub(r"\ben\s+" + re.escape(month) + r"(?:\s+de\s+20\d{2})?\b", "", text)
        return re.sub(r"\s+", " ", text).strip()

    def _detect_group_or_dimension_filter(self, question, metric, candidates):
        normalized = normalize_text(question)
        match = re.search(
            r"\b(?:por|segun|agrupado por|agrupada por|desglosado por|desglosada por)\s+(?:el|la|los|las)?\s*(.+)$",
            normalized,
        )
        if not match:
            return {"group_by": [], "explicit_filters": []}

        tail = self._clean_tail(match.group(1), metric)
        if not tail:
            return {"group_by": [], "explicit_filters": []}

        best = self._best_dimension(tail, candidates, exclude_temporal=True)
        if not best:
            return {"group_by": [], "explicit_filters": []}

        matched_alias = None
        aliases = sorted(best.get("aliases", []), key=lambda value: len(normalize_text(value)), reverse=True)
        for alias in aliases:
            alias_norm = normalize_text(alias)
            if alias_norm and (tail == alias_norm or tail.startswith(alias_norm + " ")):
                matched_alias = alias_norm
                break
        if not matched_alias:
            return {"group_by": [], "explicit_filters": []}

        remainder = tail[len(matched_alias):].strip()
        remainder = re.sub(r"^(?:de|del|en|igual a|=)\s+", "", remainder).strip()
        if not remainder:
            return {"group_by": [best], "explicit_filters": []}
        return {"group_by": [], "explicit_filters": [{"field": best, "value_hint": remainder}]}

    def _remove_metric_and_report_phrases(self, question, metric, source_context):
        """Descarta los nombres de métrica/informe ANTES de buscar filtros.

        Antes, un campo llamado EGRESOS se interpretaba como dimensión
        dentro de la expresión EGRESOS PROBABLES y exigía un valor «probables hay».
        """
        cleaned = normalize_text(question)
        phrases = [
            metric.get("label"),
            source_context.get("report"), source_context.get("semantic_model"),
            metric.get("semantic_model"),
            *self._metric_reports(metric),
        ]
        # Quitar matched_name si es alias coincidente con la pregunta se
        # gestiona adicionalmente en _implicit_value_text.
        for phrase in sorted(_unique_strings(phrases), key=len, reverse=True):
            norm = normalize_text(phrase)
            if norm:
                cleaned = re.sub(r"(?<![a-z0-9])" + re.escape(norm) + r"(?![a-z0-9])", " ", cleaned)
        cleaned = re.sub(r"\b(?:tablero|informe)\b", " ", cleaned)
        return re.sub(r"\s+", " ", cleaned).strip()

    def _detect_explicit_dimension_filters(
        self, question, candidates, already_fields=None,
        metric=None, source_context=None,
    ):
        """Filtros «<dimensión> <valor>» pedidos de forma explícita.

        Cada mención («sede norte») produce UN filtro: el campo mejor ubicado
        (el de la tabla de la métrica / visuales de la métrica) y, como
        respaldo, los demás campos con el mismo alias en `alternatives`.
        """
        normalized = (
            self._remove_metric_and_report_phrases(question, metric, source_context or {})
            if metric else normalize_text(question)
        )
        already_fields = already_fields if already_fields is not None else set()
        metric_table = normalize_text((metric or {}).get("table"))

        def priority(field):
            bonus = 60 if metric_table and normalize_text(field.get("table")) == metric_table else 0
            return -(field.get("relevance_score", 0) + bonus)

        ordered = sorted(candidates, key=priority)
        mentions = {}
        order = []
        for field in ordered:
            if self._is_temporal_field(field):
                continue
            key = (normalize_text(field.get("table")), normalize_text(field.get("column")))
            if key in already_fields:
                continue
            aliases = sorted(field.get("aliases", []), key=lambda v: len(normalize_text(v)), reverse=True)
            for alias in aliases:
                alias_norm = normalize_text(alias)
                if not alias_norm or len(alias_norm) < 3:
                    continue
                pattern = (
                    r"(?<![a-z0-9])" + re.escape(alias_norm) + r"(?![a-z0-9])"
                    + r"(?:\s+(?:de|del|igual a|=|:))?"
                    + r"\s+([a-z0-9][a-z0-9\s\.\-]{1,80})"
                )
                match = re.search(pattern, normalized)
                if not match:
                    continue
                hint = re.split(
                    r"\b(?:en|durante|para el|para la|del tablero|del informe|y|con|pero)\b",
                    match.group(1), maxsplit=1,
                )[0].strip()
                # «servicio de urgencias» es filtro; «servicio por...»,
                # «servicio hay...» o «servicio en ...» no lo son.
                invalid_start = {"hay", "hubo", "tiene", "tienen", "es", "son", "por", "para", "con"}
                tokens = canonical_tokens(hint)
                if not hint or not tokens or tokens[0] in invalid_start:
                    continue
                if len(hint.split()) == 1 and hint in GENERIC_QUERY_WORDS:
                    continue
                # Misma mención (mismo texto pedido) = mismo filtro, aunque
                # varias tablas tengan una columna llamada igual (SEDE).
                mention = (alias_norm, hint)
                if mention not in mentions:
                    mentions[mention] = {"field": field, "value_hint": hint, "alternatives": [], "alias": alias_norm}
                    order.append(mention)
                else:
                    mentions[mention]["alternatives"].append(field)
                break
        filters = [mentions[key] for key in order]
        for spec in filters:
            already_fields.add(
                (normalize_text(spec["field"].get("table")), normalize_text(spec["field"].get("column")))
            )
        return filters

    def _metric_removal_tokens(self, metric, matched_name, source_context):
        values = [matched_name, metric.get("label"), metric.get("semantic_model"), source_context.get("report")]
        values.extend(self._metric_reports(metric))
        tokens = set()
        for value in values:
            for token in canonical_tokens(value):
                tokens.add(token)
                without_numeric_suffix = re.sub(r"\d+$", "", token)
                if len(without_numeric_suffix) >= 3:
                    tokens.add(without_numeric_suffix)
        return tokens

    def _implicit_value_text(
        self, question, metric, matched_name, source_context, group_by,
        extra_removals=None,
    ):
        removals = self._metric_removal_tokens(metric, matched_name, source_context)
        for group in group_by:
            for alias in group.get("aliases", []):
                removals.update(canonical_tokens(alias))
        removals.update(canonical_token(word) for word in GENERIC_QUERY_WORDS)
        removals.update(canonical_token(word) for word in STOPWORDS)
        removals.update(canonical_token(word) for word in FILTER_NEUTRAL_WORDS)
        removals.update({"a", "al", "del", "de", "en", "hay", "hubo", "dentro", "segun"})
        removals.update(canonical_token(word) for word in MONTHS)
        removals.update(extra_removals or ())
        # Página/dashboard mencionada completa («programación quirúrgica»).
        question_tokens = set(canonical_tokens(question))
        for page in self._metric_pages(metric):
            page_tokens = canonical_tokens(page)
            if page_tokens and all(token in question_tokens for token in page_tokens):
                removals.update(page_tokens)

        result = []
        for word in normalize_text(question).split():
            token = canonical_token(word)
            if (
                token in removals or re.fullmatch(r"20\d{2}", token)
                or token.isdigit() or _is_request_word(token)
            ):
                continue
            result.append(word)
        return " ".join(result).strip()

    def _categorical_filter(self, field, resolved, source, semantic_model):
        data_type = self._column_type(semantic_model, field["table"], field["column"])
        return {
            "type": "categorical",
            "concept": (field.get("aliases") or [field["column"]])[0],
            "table": field["table"],
            "column": field["column"],
            "operator": "=",
            "value": resolved["value"],
            "data_type": data_type,
            "match_score": resolved["score"],
            "source": source,
        }

    def _implicit_eligible(self, field, semantic_model):
        """Columnas categóricas de cualquier visual (slicer, tabla, matriz, gráfico)."""
        if field.get("kind") not in ("column", "hierarchy_level"):
            return False
        if self._is_temporal_field(field):
            return False
        # Un código numérico o una fecha no es un valor que se nombre en texto libre.
        return self._column_type(semantic_model, field.get("table"), field.get("column")) not in ("number", "date")

    def _resolve_implicit_filter(
        self, question, metric, matched_name, source_context,
        candidates, group_by, used_fields, extra_removals=None,
    ):
        leftover = self._implicit_value_text(
            question, metric, matched_name, source_context, group_by,
            extra_removals=extra_removals,
        )
        if not leftover:
            return None

        semantic_model = metric.get("semantic_model")
        best = None
        checked = 0
        for field in candidates:
            if checked >= self.max_implicit_dimensions:
                break
            key = (normalize_text(field.get("table")), normalize_text(field.get("column")))
            if key in used_fields:
                continue
            if not self._implicit_eligible(field, semantic_model):
                continue

            checked += 1
            resolved = self._resolve_value(
                question=question, field=field,
                semantic_model=semantic_model, value_hint=leftover,
            )
            if not resolved:
                continue
            candidate = {"field": field, **resolved}
            if best is None or candidate["score"] > best["score"]:
                best = candidate
            if best and best["score"] >= 1.0:
                break
        return best

    # ---------------- column types ----------------
    def _technical_column_types(self, semantic_model):
        key = normalize_text(semantic_model)
        cache = self.__dict__.setdefault("_column_type_cache", {})
        if key in cache:
            return cache[key]
        types = {}
        try:
            path = self.source_router.catalog_path_for_model(semantic_model, required=False)
            catalog = self._load_json(path, {}) if path else {}
        except Exception:
            catalog = {}
        for table in catalog.get("tables", []) or []:
            for column in table.get("columns", []) or []:
                types[(normalize_text(table.get("name")), normalize_text(column.get("name")))] = (
                    self._classify_data_type(column.get("data_type"))
                )
        cache[key] = types
        return types

    @staticmethod
    def _classify_data_type(data_type):
        text = normalize_text(data_type)
        if not text:
            return None
        if "date" in text or "time" in text:
            return "date"
        if any(item in text for item in ("int", "decimal", "double", "number", "currency", "float", "whole")):
            return "number"
        return "text"

    def _column_type(self, semantic_model, table, column):
        """'date' | 'number' | 'text' | None (desconocido) según el catálogo técnico."""
        types = self._technical_column_types(semantic_model)
        return types.get((normalize_text(table), normalize_text(column)))

    # ---------------- time ----------------
    def _is_temporal_field(self, field):
        words = set()
        for value in [*field.get("aliases", []), field.get("column"), field.get("level")]:
            words.update(normalize_text(value).split())
        table = normalize_text(field.get("table"))
        column = normalize_text(field.get("column"))
        level = normalize_text(field.get("level"))
        return (
            table in {"calendario", "calendar", "fecha", "dates"}
            or level in {"ano", "mes", "dia", "year", "month", "day"}
            or bool(words & TEMPORAL_WORDS)
            or column in {"date", "fecha", "fecha servicio", "fecha atencion"}
        )

    def _detect_year_month(self, question):
        normalized = normalize_text(question)
        year_match = re.search(r"\b(20\d{2})\b", normalized)
        year = int(year_match.group(1)) if year_match else None
        month = None
        month_name = None
        for name, number in MONTHS.items():
            if re.search(r"(?<![a-z0-9])" + re.escape(name) + r"(?![a-z0-9])", normalized):
                month = number
                month_name = name
                break
        return year, month, month_name

    def _temporal_role(self, field, semantic_model):
        """'date' | 'year' | 'month' | None para un campo temporal."""
        column_type = self._column_type(semantic_model, field.get("table"), field.get("column"))
        words = set(normalize_text(field.get("column")).split())
        if column_type == "date":
            return "date"
        if words & {"ano", "anio", "year"}:
            return "year"
        if words & {"mes", "month"}:
            return "month"
        if column_type is None and (words & {"date", "fecha"} or field.get("kind") == "hierarchy_level"):
            return "date"
        return None

    def _best_date_field(self, candidates, semantic_model=None):
        temporal = [
            field for field in candidates
            if self._is_temporal_field(field)
            and (semantic_model is None or self._temporal_role(field, semantic_model) == "date")
        ]
        if not temporal:
            return None

        def score(field):
            value = field.get("relevance_score", 0)
            column = normalize_text(field.get("column"))
            table = normalize_text(field.get("table"))
            if column in {"date", "fecha"}:
                value += 80
            if table in {"calendario", "calendar"}:
                value += 60
            if field.get("kind") == "hierarchy_level":
                value += 30
            return value

        temporal.sort(key=score, reverse=True)
        return temporal[0]

    def _best_temporal_field(self, candidates, semantic_model, role):
        found = [
            field for field in candidates
            if self._is_temporal_field(field) and self._temporal_role(field, semantic_model) == role
        ]
        found.sort(key=lambda field: field.get("relevance_score", 0), reverse=True)
        return found[0] if found else None

    # ---------------- periodos (src/semantic/period_parser.py) ----------------
    def _today(self):
        """Fecha de referencia de los periodos relativos (inyectable en pruebas)."""
        value = self.__dict__.get("today")
        if callable(value):
            value = value()
        return as_date(value) or date.today()

    def _period_parser(self):
        return PeriodParser(self._today())

    @staticmethod
    def _strip_phrase(text, phrase):
        """Quita una frase temporal del texto normalizado (o sus meses/años sueltos)."""
        phrase = normalize_text(phrase)
        if not phrase:
            return text
        # Con la preposición que lo introduce: «servicio en 2024» -> «servicio».
        lead = r"(?:(?:en|de|del|durante|para|desde|hasta)\s+(?:(?:el|la|los|las)\s+)?)?"
        pattern = r"(?<![a-z0-9])" + lead + re.escape(phrase) + r"(?![a-z0-9])"
        if re.search(pattern, text):
            text = re.sub(pattern, " ", text)
        else:
            for word in phrase.split():
                if word in PERIOD_MONTHS or re.fullmatch(r"(?:19|20)\d{2}", word):
                    text = re.sub(
                        r"(?<![a-z0-9])" + lead + re.escape(word) + r"(?![a-z0-9])", " ", text,
                    )
        return re.sub(r"\s+", " ", text).strip()

    def _analyze_periods(self, question, metric=None, matched_name=None):
        """Periodo y agrupación temporal de la pregunta.

        Devuelve {"period", "granularity", "tokens", "clean_question"}:
        `tokens` son las palabras que expresaron el periodo (no son filtros
        de dimensión) y `clean_question` la pregunta sin esas frases, para
        buscar agrupaciones y filtros explícitos sin confundirlas con valores.
        Una frase que forma parte del nombre de la métrica («Egresos año
        anterior», «Promedio mensual») no se toma como periodo.
        """
        normalized = normalize_text(question)
        parser = self._period_parser()
        period = parser.parse(normalized)
        granularity = parser.granularity(normalized)
        names = [
            normalize_text(name)
            for name in ((metric or {}).get("label"), (metric or {}).get("measure"), matched_name)
            if name
        ]

        def in_metric_name(phrase):
            phrase = normalize_text(phrase)
            return bool(phrase) and any(_exact_phrase(name, phrase) for name in names)

        if period and in_metric_name(period["phrase"]):
            period = None
        if granularity and in_metric_name(granularity["phrase"]):
            granularity = None

        clean = normalized
        tokens = set()
        phrases = [*(neutral_phrases(normalized))]
        if period:
            phrases.append(period["phrase"])
            tokens.update(canonical_token(word) for word in TO_DATE_WORDS)
        if granularity:
            phrases.append(granularity["phrase"])
        for phrase in phrases:
            tokens.update(canonical_tokens(phrase))
            clean = self._strip_phrase(clean, phrase)
        return {
            "period": period, "granularity": granularity,
            "tokens": tokens, "clean_question": clean, "question": question,
        }

    def _period_words(self, text):
        """Palabras canónicas de las expresiones de periodo del texto (con caché).

        Solo las que de verdad forman un periodo («este año», «últimos 3
        meses»): «días de estancia» no es un periodo y sigue contando.
        """
        cache = self.__dict__.setdefault("_period_words_cache", {})
        key = normalize_text(text)
        if key not in cache:
            if len(cache) > 512:
                cache.clear()
            cache[key] = frozenset(self._analyze_periods(key)["tokens"])
        return cache[key]

    def _month_values(self, field, semantic_model, months):
        """Valores de la columna MES para esos meses (número o nombre según su tipo)."""
        month_type = self._column_type(semantic_model, field["table"], field["column"])
        if month_type != "text":
            return list(months), "number"
        domain = self._get_values(semantic_model, field["table"], field["column"]) or []
        names = {normalize_text(item): item for item in domain}
        values = [names.get(PERIOD_MONTH_NAMES[month]) for month in months]
        if any(value is None for value in values):
            return None, "text"
        return values, "text"

    def _period_filters(self, period, candidates, semantic_model=None):
        """Filtros de un periodo según el TIPO real de las columnas temporales.

        Devuelve (filtros, términos_sin_aplicar, notas):
        - columna de fecha -> date_range [start, end) (o MONTH() IN {...} para
          meses sin año);
        - columnas AÑO/MES enteras (o MES de texto) -> filtros categóricos por
          valor: AÑO = 2025 + MES IN {1, 2, 3}; varios años completos -> AÑO IN
          {...}; meses de años distintos -> pares (AÑO, MES).
        Sin fecha diaria, un periodo por días no se aplica (se devuelve vacío).
        Cada filtro lleva `label` con el periodo legible («enero–marzo 2025»).
        """
        label = period.get("label")
        unapplied, notes = [], []
        kind = period.get("kind")
        months_any_year = kind == "months_any_year"
        if months_any_year:
            names = label if len(period["months"]) > 1 else period.get("month_name")
            notes.append(f"Mes sin año ({names}): se consideran todos los años.")

        date_field = (
            self._best_date_field(candidates, semantic_model) if semantic_model
            else self._best_date_field(candidates)
        )
        if date_field:
            item = {
                "type": "date_range",
                "table": date_field["table"],
                "column": date_field["column"],
                "year": period.get("year"),
                "month": period.get("month"),
                "month_name": period.get("month_name"),
                "label": label,
                "period_kind": kind,
                "source": "query_plan_temporal",
            }
            if months_any_year:
                item["months"] = list(period["months"])
            else:
                item["start"] = as_date(period["start"]).isoformat()
                item["end"] = as_date(period["end"]).isoformat()
            return [item], unapplied, notes

        if period.get("daily"):
            # AÑO/MES no bastan para «hoy», «ayer» o «últimos 7 días».
            return [], [f"periodo {label} (el tablero no tiene fecha diaria)"], notes

        year_field = self._best_temporal_field(candidates, semantic_model, "year")
        month_field = self._best_temporal_field(candidates, semantic_model, "month")

        def year_filter(values):
            single = len(values) == 1
            return {
                "type": "categorical", "concept": "año",
                "table": year_field["table"], "column": year_field["column"],
                "operator": "=" if single else "IN",
                "value": values[0] if single else None,
                **({} if single else {"values": list(values)}),
                "data_type": "number", "temporal": "year", "label": label,
                "source": "query_plan_temporal",
            }

        def month_filter(months):
            values, data_type = self._month_values(month_field, semantic_model, months)
            if values is None:
                return None
            single = len(values) == 1
            return {
                "type": "categorical", "concept": "mes",
                "table": month_field["table"], "column": month_field["column"],
                "operator": "=" if single else "IN",
                "value": values[0] if single else None,
                **({} if single else {"values": values}),
                "data_type": data_type, "temporal": "month", "label": label,
                "source": "query_plan_temporal",
            }

        filters = []
        if months_any_year:
            item = month_filter(period["months"]) if month_field else None
            if item:
                filters.append(item)
            else:
                unapplied.append(f"mes {label}")
            return filters, unapplied, notes

        pairs = year_months(as_date(period["start"]), as_date(period["end"]))
        years = sorted({year for year, _ in pairs})
        by_year = {year: [m for y, m in pairs if y == year] for year in years}
        whole_years = all(len(by_year[year]) == 12 for year in years)
        if len(years) == 1 or whole_years:
            if year_field:
                filters.append(year_filter(years))
            else:
                unapplied.append(f"año {', '.join(str(year) for year in years)}")
            if not whole_years:
                item = month_filter(by_year[years[0]]) if month_field else None
                if item:
                    filters.append(item)
                else:
                    unapplied.append(f"meses de {label}")
            return filters, unapplied, notes

        # Meses de años distintos (noviembre 2024–febrero 2025): pares (AÑO, MES).
        if year_field and month_field and self._column_type(
            semantic_model, month_field["table"], month_field["column"]
        ) != "text":
            filters.append({
                "type": "temporal_set", "concept": "año y mes",
                "columns": [
                    {"table": year_field["table"], "column": year_field["column"]},
                    {"table": month_field["table"], "column": month_field["column"]},
                ],
                "values": [[year, month] for year, month in pairs],
                "label": label, "temporal": "year_month",
                "source": "query_plan_temporal",
            })
        else:
            unapplied.append(f"periodo {label}")
        return filters, unapplied, notes

    def _temporal_filters(self, question, candidates, semantic_model=None):
        """Filtros del periodo de la pregunta según el TIPO real de la columna.

        Devuelve (filtros, términos_sin_aplicar, notas). Columna de fecha ->
        date_range; columnas enteras AÑO/MES -> filtro por valor numérico.
        Un mes sin año filtra el mes en todos los años y lo dice en las notas.
        """
        period = self._period_parser().parse(normalize_text(question))
        if not period:
            return [], [], []
        return self._period_filters(period, candidates, semantic_model)

    def _bucket_period(self, bucket):
        """Subperiodo de split_period con la forma de un periodo."""
        today = self._today()
        if bucket.get("start") is None:
            month = bucket["months"][0]
            return {
                "kind": "months_any_year", "months": [month], "year": None, "month": month,
                "month_name": PERIOD_MONTH_NAMES[month], "label": bucket["label"],
                "daily": False, "start": None, "end": None,
            }
        start, end = as_date(bucket["start"]), as_date(bucket["end"])
        last = end - timedelta(days=1)
        same_month = (start.year, start.month) == (last.year, last.month)
        return {
            "kind": "range", "start": start, "end": end,
            "year": start.year if start.year == last.year else None,
            "month": start.month if same_month else None,
            "month_name": None, "label": bucket["label"],
            "daily": bucket.get("daily", False), "to_date": end > today,
        }

    def _year_domain_period(self, candidates, semantic_model):
        """Años con datos (columna AÑO entera) como periodo para «por año» sin periodo."""
        year_field = self._best_temporal_field(candidates, semantic_model, "year")
        if not year_field or self._best_date_field(candidates, semantic_model):
            return None
        values = self._get_values(semantic_model, year_field["table"], year_field["column"]) or []
        years = sorted({int(v) for v in values if str(v).isdigit()})[-10:]
        if not years:
            return None
        parser = self._period_parser()
        period = parser._range(date(years[0], 1, 1), date(years[-1] + 1, 1, 1), "")
        period["label"] = f"{period['label']} (años con datos)"
        return period

    def _apply_temporal(self, analysis, candidates, semantic_model, group_by):
        """Filtros del periodo + agrupación temporal («por mes») del plan.

        Devuelve {"filters", "unapplied", "notes", "unsupported_period",
        "group", "buckets"}. La agrupación usa subperiodos explícitos
        (`buckets`, uno por mes/trimestre/año...) que el generador DAX evalúa
        con los mismos filtros de periodo: funciona igual con columna de fecha
        o con columnas AÑO/MES enteras. Si no se puede agrupar, se declara.
        """
        result = {
            "filters": [], "unapplied": [], "notes": [], "unsupported_period": None,
            "group": None, "buckets": [],
        }
        period = analysis.get("period")
        granularity = analysis.get("granularity")
        if period:
            filters, unapplied, notes = self._period_filters(period, candidates, semantic_model)
            if not filters:
                result["unsupported_period"] = period
                result["unapplied"] = unapplied
                return result
            result["filters"].extend(filters)
            result["unapplied"].extend(unapplied)
            result["notes"].extend(notes)
            for word in period.get("ignored") or []:
                what = "mes" if word in PERIOD_MONTHS else "año"
                result["unapplied"].append(f"{what} {word} (solo se aplicó {period['label']})")

        if not granularity:
            return result
        unit = granularity["unit"]
        name = GRANULARITY_LABELS[unit]
        if group_by:
            result["unapplied"].append(
                f"agrupar por {name.lower()} (ya se agrupa por {group_by[0].get('column')})"
            )
            return result

        base = period
        if base is None:
            base = (self._year_domain_period(candidates, semantic_model) if unit == "year" else None) \
                or self._period_parser().default_window(unit)
            filters, unapplied, _ = self._period_filters(base, candidates, semantic_model)
            if filters and not unapplied:
                result["filters"].extend(filters)
                result["notes"].append(f"Sin periodo en la pregunta: se muestra {base['label']}.")
        buckets = split_period(base, unit, self._today())
        if not buckets:
            result["unapplied"].append(
                f"agrupar por {name.lower()} (más de 62 periodos o periodo sin año: acota el periodo)"
            )
            return result
        planned = []
        table = None
        for bucket in buckets:
            filters, unapplied, _ = self._period_filters(
                self._bucket_period(bucket), candidates, semantic_model,
            )
            if not filters or unapplied:
                result["unapplied"].append(
                    f"agrupar por {name.lower()} (el tablero no tiene la columna de fecha necesaria)"
                )
                # Sin agrupación, el filtro por defecto ya no tiene sentido.
                if period is None:
                    result["filters"] = []
                    result["notes"] = [n for n in result["notes"] if not n.startswith("Sin periodo")]
                return result
            table = table or filters[0].get("table") or (filters[0].get("columns") or [{}])[0].get("table")
            planned.append({"order": bucket["order"], "label": bucket["label"], "filters": filters})
        result["buckets"] = planned
        result["group"] = {
            "table": table, "column": name, "label": name,
            "source": "query_plan_temporal_group", "temporal": unit,
        }
        return result

    # ---------------- public API ----------------
    def is_descriptive(self, question):
        return self._is_descriptive(normalize_text(question))

    def _is_descriptive(self, normalized):
        return any(
            re.search(r"(?<![a-z0-9])" + re.escape(pattern) + r"(?![a-z0-9])", normalized)
            for pattern in DESCRIPTIVE_PATTERNS
        )

    @staticmethod
    def _has_period(normalized):
        months = "|".join(MONTHS)
        return bool(
            re.search(r"(?<![a-z0-9])(?:" + months + r")(?![a-z0-9])", normalized)
            or re.search(r"(?<![0-9])20\d{2}(?![0-9])", normalized)
            # Periodos relativos («este año», «mes pasado», «últimos 3 meses»)
            # y agrupaciones temporales («por mes», «mensual»).
            or PeriodParser().parse(normalized)
            or PeriodParser().granularity(normalized)
        )

    def looks_numeric(self, question, dashboard=None):
        """Detecta intención cuantitativa sin depender del orden ni del género.

        Orden de decisión: 1) definicional -> RAG; 2) término numérico
        (cuánto/cuánta/participación/promedio...); 3) la pregunta resuelve a
        una métrica conocida y pide un dato con verbo ("dime", "cuál fue"),
        menciona un período o «por <dimensión>» (incluye estilo telegráfico).
        """
        normalized = normalize_text(question)
        if not normalized or self._is_descriptive(normalized):
            return False

        if any(
            re.search(r"(?<![a-z0-9])" + term + r"(?![a-z0-9])", normalized)
            for term in NUMERIC_TERM_PATTERNS
        ):
            return True

        has_verb = any(
            re.search(r"(?<![a-z0-9])(?:" + verb + r")(?![a-z0-9])", normalized)
            for verb in QUERY_VERB_PATTERNS
        )
        has_period = self._has_period(normalized)
        has_group = bool(re.search(r"(?<![a-z0-9])(?:por|segun)\s+[a-z]", normalized))
        # «top 5 ...», «el servicio con más ...»: un ranking siempre es numérico.
        if self._mentions_ranking(normalized):
            return True
        if not (has_verb or has_period or has_group):
            return False

        source_context = self._source_context(question, dashboard=dashboard)
        metric_result = self._resolve_metric_flexible(question, source_context)
        return metric_result.get("status") in ("resolved", "ambiguous")

    # ---------------- participación / multi-métrica ----------------
    def _share_match(self, normalized):
        """Frase de participación en el texto, salvo que sea parte del nombre de una métrica."""
        match = SHARE_RE.search(normalized)
        if not match:
            return None
        phrase = match.group(0).strip()
        for metric in self._dedupe_metrics(self.metrics):
            for name in self._metric_names(metric):
                norm = normalize_text(name)
                if norm and phrase in norm and re.search(
                    r"(?<![a-z0-9])" + re.escape(norm) + r"(?![a-z0-9])", normalized
                ):
                    return None
        return match

    def _mentioned_metrics(self, normalized, source_context):
        """Métricas nombradas literalmente (frases completas, sin solaparse)."""
        strong = (
            source_context.get("status") == "resolved"
            and source_context.get("routing_strength") == "strong"
        )
        model_hint = normalize_text(source_context.get("semantic_model")) if strong else None
        found = []
        for metric in self._dedupe_metrics(self.metrics):
            if metric.get("validation_status") != "approved":
                continue
            if model_hint and normalize_text(metric.get("semantic_model")) != model_hint:
                continue
            for name in self._metric_names(metric):
                norm = normalize_text(name)
                if len(norm) < 3 or norm in GENERIC_QUERY_WORDS or norm.isdigit():
                    continue
                for m in re.finditer(
                    r"(?<![a-z0-9])" + re.escape(norm) + r"(?![a-z0-9])", normalized
                ):
                    found.append({
                        "metric": metric, "name": norm,
                        "start": m.start(), "end": m.end(),
                    })
        found.sort(key=lambda item: (-(item["end"] - item["start"]), item["start"]))
        accepted = []
        for item in found:
            if any(item["start"] < o["end"] and o["start"] < item["end"] for o in accepted):
                continue
            accepted.append(item)
        accepted.sort(key=lambda item: item["start"])
        return accepted

    @staticmethod
    def _metric_key(metric):
        return (
            normalize_text(metric.get("semantic_model")),
            normalize_text(metric.get("label")),
            normalize_text(metric.get("dax_expression")),
        )

    def _distinct_mentions(self, mentions):
        """Una mención por métrica distinta y del mismo modelo semántico."""
        if not mentions:
            return []
        models = {}
        for item in mentions:
            models.setdefault(normalize_text(item["metric"].get("semantic_model")), []).append(item)
        group = max(models.values(), key=len)
        result, seen = [], set()
        for item in group:
            key = self._metric_key(item["metric"])
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result

    @staticmethod
    def _cut_spans(text, spans):
        """Quita tramos [(ini, fin)] y la conjunción pegada a ellos."""
        for start, end in sorted(spans, reverse=True):
            left, right = text[:start], text[end:]
            if re.search(r"(?<![a-z0-9])(?:y|e)\s+$", left):
                left = re.sub(r"(?:y|e)\s+$", "", left)
            else:
                right = re.sub(r"^\s*(?:y|e)(?![a-z0-9])", "", right)
            text = left + " " + right
        return re.sub(r"\s+", " ", text).strip()

    def _default_share_metric(self, source_context):
        """Métrica base cuando solo se pide la participación ("participación de X")."""
        strong = (
            source_context.get("status") == "resolved"
            and source_context.get("routing_strength") == "strong"
        )
        if not strong:
            return {"status": "not_found", "candidates": []}
        model_hint = normalize_text(source_context.get("semantic_model"))
        report_hint = normalize_text(source_context.get("report"))
        pool = []
        for metric in self._dedupe_metrics(self.metrics):
            if metric.get("validation_status") != "approved":
                continue
            if normalize_text(metric.get("semantic_model")) != model_hint:
                continue
            reports = self._metric_reports(metric)
            if report_hint and reports and not any(normalize_text(r) == report_hint for r in reports):
                continue
            if not metric.get("dax_expression"):
                continue
            pool.append(metric)
        if not pool:
            return {"status": "not_found", "candidates": []}

        def rank(metric):
            visuals = sum(
                1 for ap in metric.get("appearances", []) or []
                if "participacion" in normalize_text(ap.get("visual_title"))
            )
            return (visuals, len(metric.get("appearances", []) or []))

        ranked = sorted(pool, key=rank, reverse=True)
        if len(ranked) == 1 or rank(ranked[0]) > rank(ranked[1]):
            return {"status": "resolved", "metric": ranked[0]}
        return {
            "status": "ambiguous",
            "candidates": [
                {"metric": m, "score": 1.0, "business_score": 1.0, "matched_name": m.get("label")}
                for m in ranked[:8]
            ],
        }

    def _unresolved_neighbor(self, normalized, share_span, mentions):
        """Palabra suelta unida con «y» a la participación que no se pudo interpretar."""
        before = normalized[:share_span[0]]
        after = normalized[share_span[1]:]
        word = None
        m = re.search(r"([a-z0-9]+)\s+y\s*$", before)
        if m:
            word = m.group(1)
        else:
            m = re.match(r"\s*y\s+([a-z0-9]+)", after)
            if m:
                word = m.group(1)
        if not word or word in FILLER_WORDS or word in MONTHS or word.isdigit():
            return None
        if any(word in item["name"].split() for item in mentions):
            return None
        dimension_words = {
            canonical_token(alias)
            for field in self.dimension_fields
            for entry in field.get("aliases", [])
            for alias in normalize_text(entry).split()
        }
        if canonical_token(word) in dimension_words:
            return None
        return word

    def build_composite(self, question, intent_result=None):
        """Preguntas con participación y/o varias métricas ("peso y participación").

        Devuelve None cuando la pregunta es de una sola métrica (flujo normal).
        Si no: {"status": "composite", "items": [...], "unresolved": [...]}
        con items {"kind": "metric"|"share", "plan": plan, "label": str}, o el
        plan fallido (ambiguous / unsupported_filter / not_found, con
        "composite": True).
        """
        intent_result = intent_result or {}
        normalized = normalize_text(question)
        if not normalized or self._is_descriptive(normalized):
            return None
        source_context = self._source_context(question, dashboard=intent_result.get("dashboard"))
        share = self._share_match(normalized)
        mentions = self._distinct_mentions(self._mentioned_metrics(normalized, source_context))

        if not share and len(mentions) < 2:
            return None
        if not share:
            # Varias métricas: deben ir unidas por «y», «e» o coma entre sí.
            for left, right in zip(mentions, mentions[1:]):
                between = normalized[left["end"]:right["start"]]
                words = between.split()
                if (
                    not ({"y", "e", "con", "ademas"} & set(words))
                    or len(words) > 4
                    or any(w not in FILLER_WORDS and w not in {"ademas"} for w in words)
                ):
                    return None

        unresolved = []
        rest_text = normalized
        if share:
            all_mentions = self._mentioned_metrics(normalized, source_context)
            neighbor = self._unresolved_neighbor(normalized, share.span(), all_mentions)
            rest_text = self._cut_spans(normalized, [share.span()])
            # Muletillas interrogativas que quedan al quitar la participación.
            rest_text = re.sub(
                r"(?<![a-z0-9])(?:que|cual|cuales|fue|fueron|tuvo|tuvieron|tiene|tienen)(?![a-z0-9])",
                " ", rest_text,
            )
            rest_text = re.sub(r"\s+", " ", rest_text).strip()
            if neighbor:
                unresolved.append(neighbor)
                rest_text = re.sub(
                    r"(?<![a-z0-9])y\s+" + re.escape(neighbor) + r"(?![a-z0-9])", " ", rest_text
                )
                rest_text = re.sub(
                    r"(?<![a-z0-9])" + re.escape(neighbor) + r"\s+y(?![a-z0-9])", " ", rest_text
                )
            # La frase de participación puede solaparse con una métrica
            # ("peso relativo"): las menciones se recalculan sobre el resto.
            mentions = self._distinct_mentions(
                self._mentioned_metrics(rest_text, source_context)
            )

        if share and not mentions:
            default = self._default_share_metric(source_context)
            if default.get("status") != "resolved":
                return {
                    "status": default.get("status", "not_found"),
                    "stage": "metric", "question": question,
                    "source_context": source_context,
                    "metric_resolution": default, "composite": True,
                }
            targets = [(default["metric"], rest_text)]
        else:
            targets = []
            for item in mentions:
                others = [(o["start"], o["end"]) for o in mentions if o is not item]
                targets.append((item["metric"], self._cut_spans(rest_text, others)))

        items, failures, failed_labels = [], [], []
        for metric, sub_question in targets:
            plan = self.build(
                sub_question, intent_result=intent_result,
                selected_metric_id=metric.get("metric_id"),
            )
            if plan.get("status") != "ready":
                plan["composite"] = True
                failures.append(plan)
                failed_labels.append(metric.get("label"))
                continue
            plan["question"] = question
            items.append({"kind": "metric", "plan": plan, "label": metric.get("label")})

        if not items:
            return failures[0]
        grouped = any(i["plan"].get("mode") == "grouped" for i in items)
        if grouped and (len(items) > 1 or not share):
            return None  # Varias métricas agrupadas: se mantiene el flujo de una sola.

        if share:
            base = items[0]["plan"]
            if base.get("mode") == "grouped":
                dimension = dict(base["group_by"][0])
                dimension["scope"] = "group"
            else:
                categorical = [f for f in base.get("filters", []) if f.get("type") == "categorical"]
                if not categorical:
                    return {
                        "status": "unsupported_filter", "stage": "share",
                        "reason": "share_requires_dimension_value",
                        "question": question,
                        "semantic_model": base.get("semantic_model"),
                        "source_context": source_context,
                        "query_plan": base, "composite": True,
                    }
                dimension = {
                    "table": categorical[0]["table"], "column": categorical[0]["column"],
                    "label": categorical[0].get("concept"),
                    "value": categorical[0].get("value"), "scope": "filter",
                }
            share_plan = dict(base)
            share_plan["share_dimension"] = dimension
            items.append({"kind": "share", "plan": share_plan, "label": "Participación"})
            if base.get("mode") == "grouped" or not mentions:
                # Tabla de participación por grupo, o solo participación cuando
                # la pregunta no pidió la métrica base ("¿qué participación tuvo X?").
                items = [items[-1]]

        return {
            "status": "composite", "question": question, "items": items,
            "unresolved": unresolved, "failures": failures,
            "failed_labels": failed_labels,
            "source_context": source_context,
        }

    # ---------------- «cuántas X» ≈ «total de X» ----------------
    _COUNT_WORDS_RE = re.compile(
        r"(?<![a-z0-9])(?:cuant[oa]s?|numero\s+(?:de|del)|cantidad\s+(?:de|del))(?![a-z0-9])"
    )

    def _total_variant(self, question):
        """Variante «total de ...» de una pregunta de conteo: «cuántas
        atenciones hubo» o «atenciones de urgencias» -> «total de atenciones...»."""
        text = normalize_text(question)
        if not text or re.search(r"(?<![a-z0-9])totale?s?(?![a-z0-9])", text):
            return None
        variant, replaced = self._COUNT_WORDS_RE.subn("total de", text, count=1)
        return variant if replaced else f"total de {text}"

    def _resolve_metric_flexible(self, question, source_context, selected_metric_id=None, **kwargs):
        """_resolve_metric que, si no encuentra indicador, prueba la variante
        «total de ...» SOLO cuando las palabras de la pregunta señalan un único
        indicador del catálogo (p. ej. TOTAL ATENCIONES). Con varios candidatos
        («cuántas cirugías»: total / realizadas / programadas) se mantiene el
        resultado original para que se contrapregunte."""
        result = self._resolve_metric(
            question, source_context, selected_metric_id=selected_metric_id, **kwargs
        )
        if selected_metric_id is not None or result.get("status") != "not_found":
            return result
        variant = self._total_variant(question)
        if not variant:
            return result
        related = self._metric_suggestions(self._metric_business_question(question, source_context))
        related_keys = {self._logical_key(item["metric"]) for item in related}
        if len(related_keys) != 1:
            return result
        alternative = self._resolve_metric(variant, source_context, **kwargs)
        if (
            alternative.get("status") != "resolved"
            or self._logical_key(alternative["metric"]) not in related_keys
        ):
            return result
        alternative["interpretation"] = (
            f"«{normalize_text(question)}» se interpretó como «{variant}» "
            "(único indicador del catálogo con esas palabras)"
        )
        return alternative

    # ---------------- respaldo del indicador elegido ----------------
    def _metric_evidence_rejection(self, question, metric, metric_result, group_by,
                                   explicit_specs, source_context):
        """Plan not_found si el indicador se eligió solo por las palabras de la
        agrupación o de un filtro («citas asignadas por especialidad» no es
        CIRUGÍAS REALIZADAS aunque una de sus visuales se llame «Cirugías por
        especialidad»). Con ello se contrapregunta en lugar de responder."""
        ignored = {
            canonical_token(word)
            for word in STOPWORDS | GENERIC_QUERY_WORDS | FILTER_NEUTRAL_WORDS | set(MONTHS)
        } | {"por", "segun", "total"}
        dimension_tokens = set()
        for field in [*group_by, *(spec["field"] for spec in explicit_specs)]:
            # El nombre de la tabla («ATENCIONES.SEDE») no nombra la dimensión.
            table_tokens = set(canonical_tokens(field.get("table")))
            for alias in field.get("aliases", []) or []:
                dimension_tokens.update(set(canonical_tokens(alias)) - table_tokens)
        if not dimension_tokens:
            return None

        words = [
            word for word in normalize_text(question).split()
            if canonical_token(word) not in ignored and not word.isdigit()
            and len(word) >= 3 and not _is_request_word(canonical_token(word))
        ]
        distinctive = [word for word in words if canonical_token(word) not in dimension_tokens]
        name_tokens = set()
        for name in self._metric_names(metric):
            name_tokens.update(canonical_tokens(name))
        evidence = [
            word for word in distinctive
            if any(_token_similarity(canonical_token(word), other) >= 0.82 for other in name_tokens)
        ]
        if evidence:
            return None

        # Palabras de la pregunta, sin las de la agrupación/filtro, para buscar
        # indicadores parecidos que ofrecer como opciones.
        remaining = " ".join(
            word for word in normalize_text(question).split()
            if canonical_token(word) not in dimension_tokens
        )
        resolved_routing = source_context.get("status") == "resolved"
        strong = resolved_routing and source_context.get("routing_strength") == "strong"
        model_hint = (
            normalize_text(source_context.get("semantic_model"))
            if resolved_routing and source_context.get("routing_strength") in ("strong", "weak") else ""
        )
        suggestions = [
            item for item in self._metric_suggestions(
                self._metric_business_question(remaining, source_context),
                model_hint=model_hint, strong=strong,
            )
            if self._logical_key(item["metric"]) != self._logical_key(metric)
        ]
        return {
            "status": "not_found",
            "stage": "metric",
            "reason": "metric_matched_only_dimension_words",
            "question": question,
            "source_context": source_context,
            "unresolved_text": " ".join(distinctive),
            "rejected_metric": {
                "metric_id": metric.get("metric_id"), "label": metric.get("label"),
                "matched_name": metric_result.get("matched_name"),
            },
            "metric_resolution": {
                "status": "not_found", "candidates": [],
                "suggestions": [
                    {key: value for key, value in item.items() if not key.startswith("_")}
                    for item in suggestions
                ],
            },
        }

    def _metric_without_group_phrase(self, question, metric_result, group_by, source_context):
        """La agrupación («por especialidad») no debe elegir el indicador.

        Se vuelve a resolver la pregunta sin esa frase; si así se identifica
        con certeza OTRO indicador («total de cirugías por especialidad» ->
        TOTAL CIRUGÍAS y no la visual «Cirugías por especialidad»), se usa ese.
        Si sin la frase queda ambiguo o sin indicador, se conserva el original.
        """
        if not group_by:
            return None
        text = normalize_text(question)
        stripped = text
        for field in group_by:
            aliases = sorted(
                {normalize_text(alias) for alias in field.get("aliases", []) or [] if normalize_text(alias)},
                key=len, reverse=True,
            )
            for alias in aliases:
                stripped = re.sub(
                    r"(?<![a-z0-9])(?:por|segun|agrupad[oa]\s+por|desglosad[oa]\s+por)\s+"
                    r"(?:el\s+|la\s+|los\s+|las\s+)?" + re.escape(alias) + r"(?![a-z0-9])",
                    " ", stripped,
                )
        stripped = re.sub(r"\s+", " ", stripped).strip()
        if not stripped or stripped == text:
            return None
        alternative = self._resolve_metric_flexible(stripped, source_context)
        if (
            alternative.get("status") != "resolved"
            or self._logical_key(alternative["metric"]) == self._logical_key(metric_result["metric"])
        ):
            return None
        alternative["interpretation"] = (
            f"el indicador se eligió sin la agrupación («{stripped}»): "
            f"{alternative['metric'].get('label')} en lugar de "
            f"{metric_result['metric'].get('label')} (que coincidía por «{metric_result.get('matched_name')}»)"
        )
        return alternative

    # ---------------- ranking («top 5», «el servicio con más peso») ----------------
    _RANKING_WORDS = {"top", "mas", "mayor", "mayores", "menos", "menor", "menores", "ranking"}
    # «con más de 3 días» / «más que» comparan con una cifra: no son ranking.
    _RANKING_HINT_RE = re.compile(
        r"(?<![a-z0-9])(?:top\s+\d{1,2}|ranking|"
        r"(?:con|tuvo|tiene|tuvieron|tienen|registro|registraron|hizo|hicieron)\s+"
        r"(?:el\s+|la\s+|los\s+|las\s+)?(?:mas|mayor|menos|menor)(?:es)?)(?![a-z0-9])"
        r"(?!\s+(?:de|que)(?![a-z0-9]))"
    )
    _NUMBER_WORDS = {
        "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
        "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
    }

    def _mentions_ranking(self, normalized):
        return bool(self._RANKING_HINT_RE.search(normalized))

    def is_ranking(self, question):
        """«top 5 ...», «el servicio con más ...»: pide orden/límite sobre un indicador."""
        return self._mentions_ranking(normalize_text(question))

    def _detect_ranking(self, question, candidates, group_by=None):
        """Orden y límite sobre una agrupación.

        «cuál fue el servicio con más peso» -> SERVICIO, desc, 1;
        «top 5 especialidades con más cirugías» -> ESPECIALIDAD, desc, 5;
        «las sedes con menos atenciones» -> SEDE, asc, sin límite.
        Devuelve None si la pregunta no pide un ranking.
        """
        text = normalize_text(question)
        if not self._mentions_ranking(text):
            return None
        verb = (
            r"(?:con|que\s+(?:tuvo|tiene|tuvieron|tienen|registro|registraron|hizo|hicieron)|"
            r"tuvo|tiene|tuvieron|tienen)\s+(?:el\s+|la\s+|los\s+|las\s+)?"
            r"(?P<dir>mas|mayor(?:es)?|menos|menor(?:es)?)(?![a-z0-9])"
            r"(?!\s+(?:de|que)(?![a-z0-9]))"
        )
        number = r"(?P<n>\d{1,2}|" + "|".join(self._NUMBER_WORDS) + r")"
        fields = [field for field in (group_by or [])] or [
            field for field in candidates if not self._is_temporal_field(field)
        ]
        best = None
        for field in fields:
            aliases = sorted(
                {normalize_text(alias) for alias in field.get("aliases", []) or [] if normalize_text(alias)},
                key=len, reverse=True,
            )
            for alias in aliases:
                if len(alias) < 3:
                    continue
                escaped = re.escape(alias)
                match = re.search(
                    r"(?:(?:top|los|las|primeros|primeras)\s+" + number + r"\s+)?"
                    r"(?<![a-z0-9])" + escaped + r"(?![a-z0-9])\s+" + verb,
                    text,
                )
                top = None
                if not match:
                    top = re.search(
                        r"(?<![a-z0-9])top\s+" + number + r"\s+" + escaped + r"(?![a-z0-9])", text,
                    )
                    if not top:
                        continue
                found = match or top
                raw_n = found.groupdict().get("n")
                limit = None
                if raw_n:
                    limit = int(raw_n) if raw_n.isdigit() else self._NUMBER_WORDS.get(raw_n)
                direction_word = (match.group("dir") if match else "mas")
                direction = "asc" if direction_word.startswith(("menos", "menor")) else "desc"
                plural = alias.endswith("s") and canonical_token(alias) != alias
                if limit is None and match and not plural:
                    limit = 1  # «el servicio con más peso»: solo el primero
                candidate = {
                    "field": field, "direction": direction, "limit": limit,
                    "phrase": found.group(0).strip(),
                    "tokens": {canonical_token(word) for word in self._RANKING_WORDS},
                }
                if best is None or len(candidate["phrase"]) > len(best["phrase"]):
                    best = candidate
                break
        return best

    @staticmethod
    def _ranking_note(ranking, label):
        order = "de menor a mayor" if ranking.get("direction") == "asc" else "de mayor a menor"
        limit = ranking.get("limit")
        if limit == 1:
            which = "menor" if ranking.get("direction") == "asc" else "mayor"
            return f"Se muestra solo el {label} con {which} valor."
        if limit:
            return f"Ordenado {order}; se muestran los {limit} primeros ({label})."
        return f"Ordenado {order} ({label})."

    # ---------------- preguntas sin indicador ----------------
    _GENERIC_MEASURE_WORDS = {
        "promedio", "media", "mensual", "mensuales", "anual", "anuales", "diario",
        "diaria", "semanal", "porcentaje", "porcentual", "suma", "sumatoria", "tasa",
        "variacion", "proporcion", "participacion", "indicador", "indicadores",
        "metrica", "metricas", "resultado", "resultados", "pendiente", "pendientes",
    }

    def _catalog_vocabulary(self):
        """Palabras (canónicas) que el catálogo conoce: nombres de indicadores,
        informes, páginas, modelos y alias de dimensiones."""
        if getattr(self, "_vocabulary", None) is not None:
            return self._vocabulary
        values = []
        for metric in self.metrics:
            if metric.get("validation_status") != "approved":
                continue
            values.extend(self._metric_names(metric))
            values.extend(self._metric_reports(metric))
            values.extend(self._metric_pages(metric))
            values.append(metric.get("semantic_model"))
        for field in self.dimension_fields:
            values.extend(field.get("aliases", []) or [])
            values.extend([field.get("report"), field.get("page"), field.get("semantic_model")])
        ignored = {canonical_token(word) for word in STOPWORDS | GENERIC_PAGE_WORDS}
        vocabulary = set()
        for value in values:
            for token in canonical_tokens(value):
                if len(token) >= 3 and token not in ignored and not token.isdigit():
                    vocabulary.add(token)
        self._vocabulary = vocabulary
        return vocabulary

    def catalog_examples(self, limit=2):
        """Indicadores reales para dar ejemplos: uno por modelo, visibles en un
        tablero y sin cifras en el nombre. -> [{"label", "report"}]."""
        by_model = {}
        for metric in self._dedupe_metrics(self.metrics):
            label = str(metric.get("label") or "").strip()
            if (
                metric.get("validation_status") != "approved" or not label
                or not (metric.get("appearances") or []) or re.search(r"\d", label)
            ):
                continue
            model = normalize_text(metric.get("semantic_model"))
            reports = self._metric_reports(metric)
            current = by_model.get(model)
            if current is None or len(label) < len(current["label"]):
                by_model[model] = {"label": label, "report": reports[0] if reports else None}
        return [by_model[key] for key in sorted(by_model)][:limit]

    def metric_words(self, question):
        """Palabras de la pregunta que nombran un indicador del catálogo (sin
        contar alias de dimensiones como «especialidad» o «servicio»). Sirve
        para distinguir un seguimiento («y por especialidad») de una pregunta
        nueva completa («y cuántas cirugías programadas»)."""
        if getattr(self, "_metric_vocabulary", None) is None:
            dimension_tokens = set()
            for field in self.dimension_fields:
                table_tokens = set(canonical_tokens(field.get("table")))
                for alias in field.get("aliases", []) or []:
                    dimension_tokens.update(set(canonical_tokens(alias)) - table_tokens)
            for synonyms in DIMENSION_SYNONYMS.values():
                for synonym in synonyms:
                    dimension_tokens.update(canonical_tokens(synonym))
            ignored = {
                canonical_token(word)
                for word in STOPWORDS | GENERIC_QUERY_WORDS | FILTER_NEUTRAL_WORDS | set(MONTHS)
            }
            vocabulary = set()
            for metric in self.metrics:
                if metric.get("validation_status") != "approved":
                    continue
                for name in self._metric_names(metric):
                    for token in canonical_tokens(name):
                        if (
                            len(token) >= 3 and not token.isdigit()
                            and token not in ignored and token not in dimension_tokens
                        ):
                            vocabulary.add(token)
            self._metric_vocabulary = vocabulary
        return [
            word for word in normalize_text(question).split()
            if len(word) >= 3 and any(
                _token_similarity(canonical_token(word), token) >= 0.88
                for token in self._metric_vocabulary
            )
        ]

    def describe_unresolved(self, question):
        """Clasifica una pregunta para la que no se encontró indicador:

        - "generic": solo palabras genéricas («promedio mensual», «cuántos hay»);
        - "unknown": tiene palabras que el catálogo conoce, pero ningún indicador;
        - "out_of_scope": ninguna palabra distintiva aparece en el catálogo
          («cuánto gana un médico en Colombia»).
        """
        ignored = {
            canonical_token(word)
            for word in STOPWORDS | GENERIC_QUERY_WORDS | FILTER_NEUTRAL_WORDS
            | set(MONTHS) | self._GENERIC_MEASURE_WORDS | self._RANKING_WORDS
        }
        words = [
            word for word in normalize_text(question).split()
            if canonical_token(word) not in ignored and not word.isdigit()
            and len(word) >= 3 and not _is_request_word(canonical_token(word))
        ]
        vocabulary = self._catalog_vocabulary()
        known = [
            word for word in words
            if any(_token_similarity(canonical_token(word), token) >= 0.88 for token in vocabulary)
        ]
        if not words:
            kind = "generic"
        elif known:
            kind = "unknown"
        else:
            kind = "out_of_scope"
        return {
            "kind": kind, "words": words, "known_words": known,
            "examples": self.catalog_examples(),
        }

    def build(self, question, intent_result=None, selected_metric_id=None):
        intent_result = intent_result or {}
        dashboard = intent_result.get("dashboard")
        source_context = self._source_context(question, dashboard=dashboard)
        metric_result = self._resolve_metric_flexible(
            question, source_context, selected_metric_id=selected_metric_id,
            with_suggestions=True,
        )

        if metric_result.get("status") != "resolved":
            return {
                "status": metric_result.get("status", "not_found"),
                "stage": "metric",
                "question": question,
                "source_context": source_context,
                "metric_resolution": metric_result,
            }

        metric = metric_result["metric"]
        semantic_model = metric.get("semantic_model")
        reports = metric.get("reports", []) or []
        report = metric.get("report") or (reports[0] if reports else source_context.get("report"))
        candidates = self._relevant_dimensions(metric)
        # Periodo («entre enero y marzo», «este año») y agrupación temporal
        # («por mes»): sus palabras no son valores ni dimensiones.
        temporal = self._analyze_periods(question, metric, metric_result.get("matched_name"))
        dimension_question = temporal["clean_question"]

        group_detection = self._detect_group_or_dimension_filter(dimension_question, metric, candidates)
        group_by = group_detection["group_by"]
        switched = None if selected_metric_id is not None else self._metric_without_group_phrase(
            question, metric_result, group_by, source_context,
        )
        if switched is not None:
            metric_result = switched
            metric = metric_result["metric"]
            semantic_model = metric.get("semantic_model")
            reports = metric.get("reports", []) or []
            report = metric.get("report") or (reports[0] if reports else source_context.get("report"))
            candidates = self._relevant_dimensions(metric)
            temporal = self._analyze_periods(question, metric, metric_result.get("matched_name"))
            dimension_question = temporal["clean_question"]
            group_detection = self._detect_group_or_dimension_filter(
                dimension_question, metric, candidates,
            )
            group_by = group_detection["group_by"]
        # Ranking («el servicio con más peso», «top 5 especialidades»): la
        # dimensión nombrada se agrupa y el resultado se ordena/limita.
        ranking = self._detect_ranking(question, candidates, group_by)
        if ranking and not group_by:
            group_by = [ranking["field"]]

        # Nunca convertir silenciosamente "por servicio" en total escalar
        # si la metadata de ese informe no expone SERVICIO.
        requested_group = re.search(
            r"\b(?:por|segun|agrupad[oa] por|desglosad[oa] por)\s+"
            r"(?:el|la|los|las)?\s*"
            r"(servicio|servicios|especialidad|especialidades|aseguradora|asegurador|sexo|estado|tipo)\b",
            normalize_text(question),
        )
        if requested_group and not group_by and not group_detection["explicit_filters"]:
            return {
                "status": "unsupported_filter", "stage": "dimensions",
                "reason": "requested_dimension_not_found_in_report",
                "requested_dimension": requested_group.group(1),
                "question": question, "semantic_model": semantic_model,
                "source_context": source_context, "metric_resolution": metric_result,
            }

        explicit_specs = list(group_detection["explicit_filters"])
        used_fields = {
            (normalize_text(spec["field"].get("table")), normalize_text(spec["field"].get("column")))
            for spec in explicit_specs
        }
        used_fields.update(
            (normalize_text(field.get("table")), normalize_text(field.get("column")))
            for field in group_by
        )
        explicit_specs.extend(
            self._detect_explicit_dimension_filters(
                dimension_question, candidates, already_fields=used_fields,
                metric=metric, source_context=source_context,
            )
        )

        if selected_metric_id is None:
            rejection = self._metric_evidence_rejection(
                question, metric, metric_result, group_by, explicit_specs, source_context,
            )
            if rejection is not None:
                return rejection

        filters = []
        unapplied_terms = []
        notes = []
        consumed_tokens = set(temporal["tokens"])
        if ranking:
            consumed_tokens.update(ranking["tokens"])
            notes.append(self._ranking_note(
                ranking, (ranking["field"].get("aliases") or [ranking["field"]["column"]])[0],
            ))
        if metric_result.get("source_hint_ignored"):
            notes.append(
                "La métrica no existe en el informe mencionado; se usó "
                f"{report or semantic_model}."
            )
        for spec in explicit_specs:
            field = spec["field"]
            resolved = None
            for option in [field, *spec.get("alternatives", [])]:
                resolved = self._resolve_value(
                    question=question, field=option, semantic_model=semantic_model,
                    value_hint=spec.get("value_hint"),
                )
                if resolved:
                    field = option
                    break
            if not resolved:
                return {
                    "status": "unsupported_filter", "stage": "dimension_value",
                    "reason": "requested_value_not_found",
                    "requested_value": spec.get("value_hint"),
                    "dimension": {"table": field["table"], "column": field["column"]},
                    "question": question, "semantic_model": semantic_model,
                    "source_context": source_context, "metric_resolution": metric_result,
                    "domain_error": self.domain_errors.get((semantic_model, field["table"], field["column"])),
                }
            filters.append(self._categorical_filter(
                field, resolved, "query_plan_explicit_dimension", semantic_model,
            ))
            used_fields.add((normalize_text(field["table"]), normalize_text(field["column"])))
            consumed_tokens.update(resolved.get("tokens", ()))
            consumed_tokens.update(canonical_tokens(spec.get("value_hint")))
            for alias in field.get("aliases", []) or []:
                consumed_tokens.update(canonical_tokens(alias))

        # Valores implícitos («cirugía plástica»): se buscan SIEMPRE, también
        # cuando ya hay filtros explícitos o agrupación; así ninguna palabra
        # específica se pierde porque otro filtro coincidió primero.
        for _ in range(3):
            implicit = self._resolve_implicit_filter(
                question=question, metric=metric,
                matched_name=metric_result.get("matched_name"),
                source_context=source_context, candidates=candidates,
                group_by=group_by, used_fields=used_fields,
                extra_removals=consumed_tokens,
            )
            if not implicit:
                break
            field = implicit["field"]
            filters.append(self._categorical_filter(
                field, implicit, "query_plan_implicit_value", semantic_model,
            ))
            used_fields.add((normalize_text(field["table"]), normalize_text(field["column"])))
            consumed_tokens.update(implicit.get("tokens", ()))

        temporal_result = self._apply_temporal(temporal, candidates, semantic_model, group_by)
        requested_period = temporal_result["unsupported_period"]
        if requested_period:
            return {
                "status": "unsupported_filter", "stage": "temporal_filters",
                "reason": "date_dimension_not_found_in_report",
                "requested_year": requested_period.get("year"),
                "requested_month": requested_period.get("month"),
                "requested_period": requested_period.get("label"),
                "unapplied_terms": temporal_result["unapplied"],
                "question": question, "semantic_model": semantic_model,
                "source_context": source_context, "metric_resolution": metric_result,
            }
        filters.extend(temporal_result["filters"])
        unapplied_terms.extend(temporal_result["unapplied"])
        notes.extend(temporal_result["notes"])

        # Palabras específicas que ningún filtro explicó. Sin ningún filtro
        # categórico el resultado sería un total engañoso: se detiene. Con
        # otros filtros ya aplicados se continúa, pero se declara lo omitido.
        leftover = "" if selected_metric_id is not None else self._implicit_value_text(
            question, metric, metric_result.get("matched_name"),
            source_context, group_by, extra_removals=consumed_tokens,
        )
        significant = [token for token in leftover.split() if len(token) >= 3]
        if significant:
            if not any(
                item.get("type") == "categorical" and item.get("source") != "query_plan_temporal"
                for item in filters
            ) and not group_by:
                return {
                    "status": "unsupported_filter", "stage": "implicit_dimension",
                    "reason": "possible_dimension_value_not_resolved",
                    "unresolved_text": leftover,
                    "question": question, "semantic_model": semantic_model,
                    "source_context": source_context, "metric_resolution": metric_result,
                }
            unapplied_terms.append(" ".join(significant))

        normalized_group_by = [{
            "table": field["table"],
            "column": field["column"],
            "label": (field.get("aliases") or [field["column"]])[0],
            "source": "query_plan_group_by",
        } for field in group_by]
        if temporal_result["group"]:
            normalized_group_by = [temporal_result["group"]]

        pages = self._metric_pages(metric)
        return {
            "status": "ready",
            "intent": "numeric_query",
            "mode": "grouped" if normalized_group_by else "scalar",
            "question": question,
            "source_context": source_context,
            "semantic_model": semantic_model,
            "report": report,
            "dashboard": metric.get("dashboard") or (pages[0] if pages else None),
            "metric": metric,
            "metric_match": {
                "matched_name": metric_result.get("matched_name"),
                "score": metric_result.get("score"),
                "interpretation": metric_result.get("interpretation"),
            },
            "filters": filters,
            "unapplied_terms": unapplied_terms,
            "notes": notes,
            "group_by": normalized_group_by,
            "ranking": (
                {key: ranking[key] for key in ("direction", "limit", "phrase")}
                if ranking and normalized_group_by else None
            ),
            "temporal_buckets": temporal_result["buckets"],
            "period": self._period_summary(temporal),
            "dimension_candidates_checked": min(len(candidates), 20),
        }

    def _period_summary(self, temporal):
        """Periodo interpretado (para el razonamiento y la respuesta), o None."""
        period, granularity = temporal.get("period"), temporal.get("granularity")
        if not period and not granularity:
            return None
        summary = {"today": self._today().isoformat()}
        question = temporal.get("question") or ""
        if period:
            summary.update({
                "phrase": _original_phrase(question, period.get("phrase")),
                "label": period.get("label"),
                "kind": period.get("kind"), "relative": period.get("relative"),
                "start": as_date(period.get("start")).isoformat() if period.get("start") else None,
                "end": as_date(period.get("end")).isoformat() if period.get("end") else None,
                "months": period.get("months"),
            })
        if granularity:
            summary["granularity"] = granularity.get("unit")
            summary["granularity_phrase"] = _original_phrase(question, granularity.get("phrase"))
        return summary
