"""Etapa «elegir indicador»: puntaje de nombres, sugerencias, desempates e indicador general.

_resolve_metric / _resolve_metric_flexible y sus reglas: frase exacta, núcleo del nombre, peso de
tokens, diccionario de variables, indicador general frente al de un subservicio (r2-indicador-2
BH09; r4 FC05/AC01: no cambia a una tarjeta cuyo nombre trae palabras que la pregunta no dice),
«cuántos X» → CANTIDAD/NÚMERO DE X (r7 TU04), conteo implícito de identificador detrás (r7),
_metric_evidence_rejection y _metric_without_group_phrase (holdout H24). Mixin de
QueryPlanBuilder, métodos movidos sin cambios desde query_plan_builder.py.
"""
import json
import re

from src.providers.domain_cache import identifier_column
from src.semantic.resolucion.texto import (
    _exact_phrase,
    _is_question_form_word,
    _is_request_word,
    _phrase_score,
    _token_similarity,
    _TRAILING_DETAIL_RE,
    _unique_strings,
    canonical_token,
    canonical_tokens,
    FILTER_NEUTRAL_WORDS,
    GENERIC_PAGE_WORDS,
    GENERIC_QUERY_WORDS,
    MONTHS,
    normalize_text,
    STOPWORDS,
)


class IndicadorMixin:


    def _metric_business_question(self, question, source_context):
        text = normalize_text(question)
        # «… y en qué camas» / «… y cuáles son» pide el listado de lo contado
        # («cuántos pacientes de sanitas…»): no nombra el indicador.
        trailing = _TRAILING_DETAIL_RE.search(text)
        if trailing and re.search(r"(?<![a-z0-9])cuant[oa]s\s", text[:trailing.start()]):
            text = text[:trailing.start()].strip()

        removals = [
            source_context.get("report"),
            source_context.get("semantic_model"),
            source_context.get("source_group"),
        ]

        full = text
        for value in removals:
            normalized = normalize_text(value)
            if normalized:
                text = re.sub(
                    r"(?<![a-z0-9])" + re.escape(normalized) + r"(?![a-z0-9])",
                    " ",
                    text,
                )

        text = re.sub(r"\b(?:tablero|informe|modelo semantico)\b", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        # «¿cuál es la demanda insatisfecha total?»: el nombre del tablero
        # (DEMANDA INSATISFECHA) es también el del indicador
        # (TOTAL_DEMANDA_INSATISFECHA). Si quitarlo deja la pregunta sin
        # palabras con contenido, se conserva.
        if text != full and not self._question_content_words(text):
            kept = re.sub(r"\b(?:tablero|informe|modelo semantico)\b", " ", full)
            kept = re.sub(r"\s+", " ", kept).strip()
            if self._question_content_words(kept):
                return kept
        return text

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
        # Las palabras del periodo («mes pasado») no emparentan indicadores.
        ignored |= set(self._period_words(business_question))
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

    # Palabras de conteo al inicio de un nombre que la pregunta no repite:
    # «cuántos suministros pendientes» = NÚMERO DE SUMINISTROS PENDIENTES.
    _COUNT_NAME_PREFIX_RE = re.compile(
        r"^(?:numero|nro|total|cantidad|conteo|recuento)\s+(?:(?:de|del)\s+(?:(?:la|las|los|el)\s+)?)?"
    )

    _IMPLICIT_COUNT_LABEL_RE = re.compile(
        r"^(?:recuento|conteo|count|countrows|distinctcount|recuento distinto|conteo distinto)"
        r"(?:\s+(?:de|del|of))?\s+(?P<column>.+)$"
    )

    def _implicit_identifier_count(self, metric):
        """¿Es una medida IMPLÍCITA de conteo sobre un identificador de persona
        o registro («Recuento de PACNUMDOC», «Conteo de OID_TRIAGE1»)? Power BI
        la nombra por la columna, no por el negocio: su página o su filtro
        pueden coincidir con la pregunta, pero nunca le gana a un indicador cuyo
        propio nombre dice la entidad que se cuenta («CANTIDAD DE TRIAGES»)."""
        match = self._IMPLICIT_COUNT_LABEL_RE.match(normalize_text(metric.get("label")))
        if not match:
            return False
        column = metric.get("column") or match.group("column")
        return bool(identifier_column(column)) or bool(identifier_column(match.group("column")))

    def _core_name_score(self, business_question, label, weights):
        """Puntaje del nombre sin «número de / total de / cantidad de» al
        inicio, solo si lo que queda tiene al menos dos palabras con contenido
        («suministros pendientes»; «Total cirugías» no se recorta)."""
        norm = normalize_text(label)
        core = self._COUNT_NAME_PREFIX_RE.sub("", norm).strip()
        if not core or core == norm:
            return 0.0
        content = [
            token for token in canonical_tokens(core)
            if token not in {canonical_token(word) for word in STOPWORDS} and not token.isdigit()
        ]
        if not content or self._weak_name_kind(core):
            return 0.0
        if len(content) < 2:
            # Una sola palabra («CANTIDAD DE TRIAGES» -> «triages») solo si la
            # pregunta también cuenta («cuántos triages»): el «cuántos» es el
            # «cantidad de» del nombre. «Total cirugías» sigue sin recortarse
            # para «cirugías por especialidad». Un poco por debajo del nombre
            # que dice solo la entidad (TRIAGES), para no romper sus empates.
            if not norm.startswith(("cantidad", "numero", "nro", "conteo")):
                return 0.0
            # Una unidad genérica («CANTIDAD DE PACIENTES») no nombra un
            # indicador concreto: «cuántos pacientes por aseguradora» no es él.
            if content[0] in {canonical_token(word) for word in self._OPTION_UNIT_WORDS}:
                return 0.0
            if not self._COUNT_QUESTION_RE.search(normalize_text(business_question)):
                return 0.0
            return 0.97 * _phrase_score(business_question, core, weights)
        return _phrase_score(business_question, core, weights)

    def _focus_suggestions(self, business_question, source_context, suggestions):
        """Opciones de una contrapregunta sin indicadores irrelevantes.

        - Las palabras del tablero al que se enrutó («farmacia» en «... en
          farmacia») no hacen pariente a un indicador: NÚMERO DE SUMINISTROS
          PENDIENTES no se ofrece para «medicamentos vencidos en farmacia».
        - Si alguna opción comparte la palabra MÁS distintiva de la pregunta
          (peso IDF; «vencidos» frente a «medicamentos») o está en la página
          nombrada (MEDICAMENTOS VENCIDOS), se descartan las que no, y esas van
          primero."""
        if not suggestions:
            return suggestions
        ignored = {
            canonical_token(word)
            for word in STOPWORDS | GENERIC_QUERY_WORDS | FILTER_NEUTRAL_WORDS | set(MONTHS)
        }
        ignored |= set(self._period_words(business_question))
        question_tokens = [
            token for token in dict.fromkeys(canonical_tokens(business_question))
            if len(token) >= 4 and not token.isdigit() and token not in ignored and not _is_request_word(token)
        ]
        strong = (
            (source_context or {}).get("status") == "resolved"
            and (source_context or {}).get("routing_strength") == "strong"
        )
        board_tokens = set()
        if strong:
            for phrase in self._board_name_phrases(source_context):
                board_tokens.update(canonical_tokens(phrase))
        content = [token for token in question_tokens if token not in board_tokens] or question_tokens
        if not content:
            return suggestions
        named_page = normalize_text((source_context or {}).get("dashboard"))

        def name_hits(metric):
            # Nombres visibles, no referencias técnicas («Sum(PENDIENTES_FARMACIA.HCNFOLIO)»).
            names = [
                token for name in [*self._metric_names(metric), metric.get("table")]
                if name and not re.search(r"[().]", str(name))
                for token in canonical_tokens(name)
            ]
            return {token for token in content if any(_token_similarity(token, other) >= 0.88 for other in names)}

        def page_hit(metric):
            for page in self._metric_pages(metric):
                page_norm = normalize_text(page)
                if named_page and page_norm == named_page:
                    return True
                tokens = [t for t in canonical_tokens(page) if t not in ignored and len(t) >= 3]
                if tokens and all(self._explains(t, content) for t in tokens):
                    return True
            return False

        scored = [(item, name_hits(item["metric"]), page_hit(item["metric"])) for item in suggestions]
        related = [entry for entry in scored if entry[1] or entry[2]]
        if not related:
            return suggestions
        matched_tokens = {token for _, hits, _ in related for token in hits}
        # Más distintiva: mayor peso IDF; a igual peso, la que comparten menos opciones.
        top = max(
            sorted(matched_tokens),
            key=lambda token: (
                round(self._token_weight(token), 6),
                -sum(1 for _, hits, _ in related if token in hits),
            ),
        ) if matched_tokens else None
        focused = [
            entry for entry in related
            if (top is not None and top in entry[1]) or entry[2]
        ] or related
        # Orden estable: primero las que comparten la palabra distintiva; dentro
        # de cada grupo se respeta el orden del resolutor.
        focused.sort(key=lambda entry: 0 if top is not None and top in entry[1] else 1)
        dropped = [entry[0]["metric"].get("label") for entry in scored if entry not in focused]
        if dropped:
            self._note(
                "opciones descartadas por no compartir la palabra distintiva "
                + (f"«{top}» " if top else "")
                + "ni estar en la página nombrada: " + ", ".join(str(label) for label in dropped[:6])
            )
        return [entry[0] for entry in focused]

    # ---------------- diccionario de variables (señal, no candidatos) ----------------
    _DICTIONARY_CUT_RE = re.compile(
        r"\s(?:Tipo|Unidad|C[aá]lculo|Se usa en|Origen|Granularidad|Valores|Columnas principales)\s*:",
    )
    _DICTIONARY_REF_RE = re.compile(r"^\s*'?([^'\[\]:]+?)'?\s*\[([^\]]+)\]\s*:\s*(.+)$", re.DOTALL)

    @classmethod
    def _dictionary_gist(cls, text):
        """Primera parte de una entrada del diccionario: qué es o qué mide (sin
        tipo, cálculo, usos ni origen)."""
        text = re.sub(r"\s+", " ", str(text or "")).strip()
        match = cls._DICTIONARY_CUT_RE.search(text)
        return text[: match.start()] if match else text

    def _dictionary_index(self):
        """{(modelo, clave): qué es} del diccionario de variables
        (data/semantic_documents, tableros con is_dictionary). Claves: «m:<medida>»,
        «c:<tabla>[<columna>]» y «t:<tabla>», normalizadas."""
        cached = self.__dict__.get("_dictionary_index_cache")
        if cached is not None:
            return cached
        index = {}
        root = self.project_root / "data" / "semantic_documents"
        try:
            paths = sorted(root.rglob("*.json")) if root.exists() else []
        except OSError:
            paths = []
        for path in paths:
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(document, dict):
                continue
            model = normalize_text(document.get("semantic_model"))
            for dashboard in document.get("dashboards") or []:
                if not isinstance(dashboard, dict) or not dashboard.get("is_dictionary"):
                    continue

                def put(key, text):
                    gist = self._dictionary_gist(text)
                    if gist and not gist.lower().startswith("por confirmar"):
                        index.setdefault((model, key), gist)

                for measure in dashboard.get("documented_measures") or []:
                    if isinstance(measure, dict) and measure.get("name"):
                        put("m:" + normalize_text(measure["name"]), measure.get("description"))
                for column in dashboard.get("calculated_columns") or []:
                    if isinstance(column, dict) and column.get("table") and column.get("name"):
                        put(f"c:{normalize_text(column['table'])}[{normalize_text(column['name'])}]",
                            column.get("description"))
                for section in dashboard.get("other_sections") or []:
                    match = self._DICTIONARY_REF_RE.match(str((section or {}).get("text") or ""))
                    if match:
                        put(f"c:{normalize_text(match.group(1))}[{normalize_text(match.group(2))}]", match.group(3))
                for source in dashboard.get("data_sources") or []:
                    name, _, text = str(source or "").partition(":")
                    if name.strip() and text.strip() and "[" not in name:
                        put("t:" + normalize_text(name), text)
                        # Texto completo (con «Origen» y «Granularidad»): la
                        # ventana de datos de la tabla suele estar ahí
                        # («una fila por cita ambulatoria PRÓXIMA»).
                        key = (model, "tfull:" + normalize_text(name))
                        index[key] = (index.get(key, "") + " " + re.sub(r"\s+", " ", text)).strip()
        self._dictionary_index_cache = index
        return index

    _TABLE_ORIGIN_RE = re.compile(
        r"origen\s*:\s*(?:consulta\s+sql\s+)?(?:sobre|de|desde)\s+([A-Za-z_][A-Za-z0-9_\.]*)", re.IGNORECASE,
    )

    def _table_coverage_text(self, model, table):
        """Lo que la documentación dice de una tabla (entrada completa) más lo
        que dice de su origen («Origen: consulta SQL sobre BI_PROXIMAS_CITAS»
        -> «Citas asignadas para los próximos días»)."""
        index = self._dictionary_index()
        table_norm = normalize_text(table)
        full = index.get((model, "tfull:" + table_norm)) or index.get((model, "t:" + table_norm)) or ""
        texts = [full] if full else []
        for origin in self._TABLE_ORIGIN_RE.findall(full):
            origin_norm = normalize_text(origin)
            if origin_norm and origin_norm != table_norm:
                extra = index.get((model, "tfull:" + origin_norm)) or index.get((model, "t:" + origin_norm))
                if extra:
                    texts.append(extra)
        return " ".join(texts)

    def _dictionary_tokens(self, metric):
        """Palabras con que el diccionario de variables describe lo que mide el
        indicador (su medida o la columna que agrega, y su tabla). Solo
        explican palabras de la pregunta de un candidato que ya coincidió por
        su nombre: nunca crean candidatos."""
        cache = self.__dict__.setdefault("_dictionary_tokens_cache", {})
        key = self._logical_key(metric)
        if key in cache:
            return cache[key]
        index = self._dictionary_index()
        model = normalize_text(metric.get("semantic_model"))
        table = normalize_text(metric.get("table"))
        texts = []
        if metric.get("measure"):
            texts.append(index.get((model, "m:" + normalize_text(metric.get("measure")))))
        for ref_table, column in re.findall(r"'?([A-Za-z_][^'\[\]()]*?)'?\s*\[([^\]]+)\]",
                                            str(metric.get("dax_expression") or "")):
            texts.append(index.get((model, f"c:{normalize_text(ref_table)}[{normalize_text(column)}]")))
        if metric.get("column") and table:
            texts.append(index.get((model, f"c:{table}[{normalize_text(metric.get('column'))}]")))
        if table:
            texts.append(index.get((model, "t:" + table)))
        stop = {canonical_token(word) for word in STOPWORDS | GENERIC_QUERY_WORDS}
        tokens = {
            token for text in texts if text for token in canonical_tokens(text)
            if len(token) >= 4 and token not in stop and not token.isdigit()
        }
        cache[key] = tokens
        return tokens

    def _dictionary_credit(self, business_question, explained, metric):
        """Reducción del castigo por palabras no explicadas cuando el
        diccionario de variables sí las explica para este indicador (la mitad
        del castigo de cada una)."""
        dictionary = self._dictionary_tokens(metric)
        if not dictionary:
            return 0.0
        ignored = {canonical_token(word) for word in STOPWORDS | GENERIC_QUERY_WORDS}
        ignored.update(canonical_token(word) for word in MONTHS)
        ignored.update(self._period_words(business_question))
        credit = 0.0
        for token in set(canonical_tokens(business_question)):
            if token in ignored or token.isdigit() or len(token) < 4 or _is_request_word(token):
                continue
            if any(_token_similarity(token, other) >= 0.82 for other in explained):
                continue
            if any(_token_similarity(token, other) >= 0.88 for other in dictionary):
                credit += 0.06 * self._token_weight(token)
        return credit

    def _visible_labels(self, exclude=None):
        """Etiquetas/medidas normalizadas de los indicadores que algún visual
        muestra (sin las de la clave lógica `exclude`)."""
        cached = self.__dict__.get("_visible_labels_cache")
        if cached is None:
            cached = {}
            for metric in self._dedupe_metrics(self.metrics):
                if metric.get("validation_status") != "approved" or not metric.get("appearances"):
                    continue
                for name in (metric.get("label"), metric.get("measure")):
                    key = normalize_text(name)
                    if key:
                        cached.setdefault(key, set()).add(self._logical_key(metric))
            self._visible_labels_cache = cached
        return {name for name, owners in cached.items() if owners - {exclude}}

    _CARD_VISUAL_TYPES = frozenset({"card", "multirowcard", "kpi", "cardvisual", "gauge"})

    def _card_keys(self):
        """Claves lógicas de las medidas que alguna tarjeta muestra (incluye
        las publicadas con otro nombre en otra página: VALOR ESTIMADO)."""
        cached = self.__dict__.get("_card_keys_cache")
        if cached is None:
            cached = {
                self._logical_key(metric) for metric in self.metrics
                if any(
                    normalize_text(item.get("visual_type")).replace(" ", "") in self._CARD_VISUAL_TYPES
                    for item in metric.get("appearances") or []
                )
            }
            self._card_keys_cache = cached
        return cached

    def _shown_in_card(self, metric):
        return self._logical_key(metric) in self._card_keys()

    _NAME_CONNECTORS = frozenset({"de", "del", "la", "el", "los", "las", "para", "en", "por", "a", "al", "y", "con"})

    def _content_name(self, label):
        """Etiqueta sin conectores, con al menos dos palabras y alguna quitada
        («TIEMPO PARA TRIAGE» -> «tiempo triage»); None si no cambia."""
        words = normalize_text(label).split()
        content = [word for word in words if word not in self._NAME_CONNECTORS]
        if len(content) < 2 or len(content) == len(words):
            return None
        return " ".join(content)

    _PERCENT_WORD_RE = re.compile(r"(?<![a-z0-9])(?:porcentaje|porcentual)(?![a-z0-9])")

    def _percent_label_phrase(self, label, normalized_question):
        """«%INASISTENCIA» dicho en palabras («porcentaje de inasistencia»):
        la frase normalizada si la etiqueta empieza por % y la pregunta dice
        «porcentaje»; si no, None."""
        norm = normalize_text(label)
        if not norm.startswith("%") or not self._PERCENT_WORD_RE.search(normalized_question or ""):
            return None
        rest = norm.lstrip("% ").strip()
        return f"porcentaje de {rest}" if rest else None

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
                result["suggestions"] = self._focus_suggestions(
                    business_question, source_context,
                    self._metric_suggestions(business_question, model_hint=model_hint, strong=strong),
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
            # «porcentaje de inasistencia» nombra %INASISTENCIA tal cual.
            percent_name = self._percent_label_phrase(primary_label, normalized_business)
            if percent_name:
                primary_score = max(primary_score, _phrase_score(business_question, percent_name, weights))
                label_is_exact = label_is_exact or _exact_phrase(normalized_business, percent_name)
            count_core = None
            if primary_score < self.min_metric_score:
                # «cuántos suministros pendientes» nombra NÚMERO DE SUMINISTROS
                # PENDIENTES: «número de» / «total de» no se exige.
                core_score = self._core_name_score(business_question, primary_label, weights)
                if core_score > primary_score:
                    primary_score = core_score
                    core_text = self._COUNT_NAME_PREFIX_RE.sub("", primary_norm).strip()
                    if core_text and _exact_phrase(normalized_business, core_text):
                        # «cuántos triages» dice el nombre completo de CANTIDAD
                        # DE TRIAGES: pesa como un nombre exacto.
                        count_core = core_text

            table_titles = {normalize_text(title) for title in metric.get("table_titles") or []}
            titles = _unique_strings(
                appearance.get("visual_title")
                for appearance in metric.get("appearances", []) or []
                if normalize_text(appearance.get("visual_title")) not in table_titles
            )
            exact_title = None
            for title in titles:
                title_norm = normalize_text(title)
                if title_norm == primary_norm or not _exact_phrase(normalized_business, title_norm):
                    continue
                # Un título compartido con la etiqueta de OTRA métrica
                # (EGRESOS de AÑO ACTUAL) solo es alias, no nombre propio.
                # Salvo que esas otras sean medidas que ningún visual muestra:
                # el visual «GIRO CAMA» (GIRO_CAMA1) gana a las GIRO_CAMA ocultas.
                if title_norm in self._visible_labels(exclude=self._logical_key(metric)):
                    continue
                exact_title = title
                break

            aliases = [
                item for item in self._metric_names(metric)
                if normalize_text(item) != primary_norm
            ]
            # El nombre sin conectores («TIEMPO PARA TRIAGE» -> «tiempo triage»):
            # «cuánto se demoran en el triage» no dice «para».
            content_label = self._content_name(primary_label)
            if content_label:
                aliases.append(content_label)
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
                if count_core:
                    name_priority = 0.97 * 0.32 * min(
                        1.0, sum(weights.get(t, 1.0) for t in canonical_tokens(count_core)))

            # Un nombre sin contenido propio («2024», «Registrado») o solo
            # genérico («Promedio mensual») no elige el indicador por sí solo.
            best_name, best_name_score, name_priority = self._discard_weak_name(
                metric, business_question, best_name, best_name_score, name_priority,
                in_named_model=bool(model_hint) and strong and metric_model == model_hint,
            )
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
            penalty = self._unexplained_penalty(business_question, explained)
            if penalty > 0:
                # El diccionario de variables explica lo que el nombre no dice
                # («ropa» del pesaje de LAVANDERIA): castigo a la mitad.
                penalty = max(0.0, penalty - self._dictionary_credit(business_question, explained, metric))
            score -= penalty
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
                # Para el desempate: ¿coincidió por su propio nombre o por un
                # alias (título de visual) que comparte con otras medidas?
                "_own_name": self._is_own_name(metric, best_name),
                "_shared_alias": (
                    not self._is_own_name(metric, best_name) and self._is_shared_alias(metric, best_name)
                ),
                "_name_priority": name_priority,
            })

        # Un nombre exacto más corto («TIEMPO PROMEDIO DE RESPUESTA» de
        # IMAGENES) no gana por serlo a otro que además nombra la entidad de la
        # pregunta («... RESPUESTA A INTERCONSULTA» para «... de interconsultas»).
        self._drop_priority_of_narrower_names(business_question, candidates)

        if not candidates:
            dictionary = self._dictionary_resolution(business_question, source_context)
            return dictionary if dictionary is not None else not_found([])

        # Periodo que la tabla del indicador no trae («triages en 2025» con la
        # tabla de triages del día anterior): pierde frente a otro candidato,
        # de cualquier modelo y aunque no tenga visual, que sí lo cubre.
        candidates = self._drop_uncovered_period(business_question, candidates)

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

        # Página nombrada («tablero de triage» -> TRIAGE): un indicador que no
        # aparece en ella pierde frente a los que sí; si ninguno de la página
        # coincide, se marca para decirlo en vez de usar el de otra página.
        page_missing = None
        routed_page = self._routed_page(source_context) if strong and not hint_ignored else None
        if routed_page is None and strong and not hint_ignored:
            # Informe nombrado y, además, una de sus páginas por su nombre completo.
            routed_page = self._page_named_in_report(business_question, source_context)
        if routed_page is not None:
            member_keys = {self._logical_key(member["metric"]) for member in self._page_members(routed_page)}
            valid = [item for item in candidates if item["business_score"] >= self.min_metric_score]
            if member_keys and valid:
                on_page = [item for item in valid if self._logical_key(item["metric"]) in member_keys]
                if on_page:
                    if len(on_page) < len(valid):
                        dropped = [
                            str(item["metric"].get("label")) for item in valid if item not in on_page
                        ]
                        self._note(
                            f"la pregunta nombra la página {routed_page['page']}: se descartan indicadores "
                            f"que no aparecen en ella ({', '.join(dict.fromkeys(dropped[:6]))})"
                        )
                    candidates = on_page
                else:
                    page_missing = routed_page

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
            dictionary = self._dictionary_resolution(business_question, source_context)
            if dictionary is not None:
                return dictionary
            return not_found(groups[:candidate_limit])
        tied = [
            item for item in groups
            if best["score"] - item["score"] < self.ambiguity_margin
            and item["business_score"] >= self.min_metric_score
        ]
        if len(tied) > 1:
            tied = self._ties_naming_the_same(business_question, best, tied)
        visible = self._visible_over_auxiliary(business_question, best, groups)
        if visible:
            best = visible[0]
            groups = [*visible, *[item for item in groups if item not in visible]]
            tied = visible
        if len(tied) > 1:
            # Nombre propio frente a alias compartido, palabra que es parte de
            # un valor de filtro y sustantivo contado («cuántas camas»).
            kept = self._break_metric_tie(business_question, tied)
            if len(kept) == 1:
                best = kept[0]
                groups = [best, *[item for item in groups if item is not best]]
                tied = kept
            else:
                tied = kept + [item for item in tied if item not in kept]
        if len(tied) > 1:
            rest = [item for item in groups if item not in tied]
            limit = None if candidate_limit is None else max(candidate_limit, len(tied))
            result = {"status": "ambiguous", "candidates": (tied + rest)[:limit]}
            if page_missing is not None:
                result["page_hint_ignored"] = page_missing
            return result

        general = self._general_indicator(business_question, source_context, best)
        if general is not None:
            best = general
            groups = [general, *[item for item in groups if self._logical_key(item["metric"])
                                 != self._logical_key(general["metric"])]]
        return {
            "status": "resolved", "metric": best["metric"],
            "matched_name": best["matched_name"], "score": best["score"],
            "candidates": groups[:candidate_limit],
            "source_hint_ignored": hint_ignored,
            **({"page_hint_ignored": page_missing} if page_missing is not None else {}),
            **({"general_indicator": True, "consumed_tokens": general["_consumed"]} if general else {}),
        }

    def _ties_naming_the_same(self, business_question, best, tied):
        """Empate por puntaje: no compite quien no explica (ni con su nombre,
        tabla o página) una palabra de la pregunta que el mejor nombra con su
        propio nombre. «tiempo promedio de TRIAGE»: TIEMPO PARA TRIAGE frente a
        TIEMPO GESTION FACTURACION (alias «Promedio de TIEMPO»), que no habla
        de triage."""
        content = {canonical_token(word) for word in self._question_content_words(business_question)}
        content -= set(self._period_words(business_question))
        content -= set(canonical_tokens(self._requested_group_tail(business_question) or ""))
        names = {
            token for name in self._metric_names(best["metric"])
            if name and not re.search(r"[().]", str(name)) for token in canonical_tokens(name)
        }
        named = {token for token in content if len(token) >= 4 and self._explains(token, names)}
        if not named:
            return tied
        kept = [best] + [
            item for item in tied if item is not best
            and all(self._explains(token, self._metric_vocabulary_tokens(item["metric"])) for token in named)
        ]
        if len(kept) < len(tied):
            self._note(
                f"{best['metric'].get('label')} nombra «{', '.join(sorted(named))}» de la pregunta; no compiten: "
                + ", ".join(str(item["metric"].get("label")) for item in tied if item not in kept)
            )
        return kept

    def _drop_priority_of_narrower_names(self, business_question, candidates):
        """Quita la prioridad de nombre exacto a un candidato si otro (con
        nombre suficiente) explica, con su propio nombre, todas sus palabras
        de la pregunta y además alguna más."""
        if len(candidates) < 2 or not any(item.get("_name_priority") for item in candidates):
            return
        content = {canonical_token(word) for word in self._question_content_words(business_question)}
        content -= set(self._period_words(business_question))
        # «por aseguradora»: la agrupación no nombra la entidad del indicador.
        content -= set(canonical_tokens(self._requested_group_tail(business_question) or ""))
        if not content:
            return

        def explained(item):
            names = {
                token for name in self._metric_names(item["metric"])
                if name and not re.search(r"[().]", str(name)) for token in canonical_tokens(name)
            }
            return {token for token in content if self._explains(token, names)}

        sets = [explained(item) for item in candidates]
        # Solo importa si el exacto es el que va a ganar: a uno que ya va
        # detrás no se le quita nada (sigue como alternativa cercana).
        top = max(item["score"] for item in candidates)
        for item, mine in zip(candidates, sets):
            if not item.get("_name_priority") or not mine or item["score"] < top:
                continue
            # Solo un rival que el usuario ve en un tablero y que nombra lo
            # de más con su propia etiqueta (no con un alias ni una medida
            # auxiliar: «camas disponibles» sigue siendo CAMAS + un filtro).
            wider = [
                other for other, theirs in zip(candidates, sets)
                if other is not item and theirs > mine and other["business_score"] >= self.min_metric_score
                and other["metric"].get("appearances")
                and all(
                    self._explains(token, set(canonical_tokens(other["metric"].get("label"))))
                    for token in theirs - mine
                )
            ]
            if wider:
                # Solo si así gana el que nombra más (no un tercero).
                lowered = round(item["score"] - item["_name_priority"], 4)
                rest = [other for other in candidates if other is not item]
                leader = max(rest, key=lambda other: other["score"]) if rest else None
                if leader is None or leader not in wider or leader["score"] < lowered:
                    continue
                item["score"] = lowered
                item["_name_priority"] = 0.0
                item["exact_name_displaced"] = True
                self._note(
                    f"{item['metric'].get('label')} coincide exacto, pero "
                    f"{wider[0]['metric'].get('label')} nombra además "
                    f"«{', '.join(sorted(explained(wider[0]) - mine))}» de la pregunta: no se prioriza el exacto"
                )

    # ---- indicador de un subservicio frente al general del hospital ----
    @staticmethod
    def _shares_long_prefix(token, vocabulary, length=7):
        """«hospitalizados» ~ «hospitalario»: misma raíz larga (≥ 7 letras)."""
        return len(token) >= length and any(
            len(other) >= length and token[:length] == other[:length] for other in vocabulary
        )

    def _subtopic_pages(self, metric, question_tokens):
        """Páginas no principales del indicador cuyo tema (palabras del nombre
        de la página que no son genéricas ni de su etiqueta) lo dice tal cual
        la descripción de su tabla y la pregunta no lo nombra."""
        model = normalize_text(metric.get("semantic_model"))
        described = set(canonical_tokens(self._dictionary_index().get(
            (model, "t:" + normalize_text(self._metric_fact_table(metric))), "")))
        label = set(canonical_tokens(metric.get("label")))
        count = 0
        for page in _unique_strings(item.get("page_display_name") for item in metric.get("appearances") or []):
            if self._PRINCIPAL_PAGE_RE.search(normalize_text(page)):
                continue
            topic = {
                token for token in canonical_tokens(page)
                if len(token) >= 4 and token not in GENERIC_PAGE_WORDS and token not in label
            }
            if topic and topic & described and not any(self._explains(t, question_tokens) for t in topic):
                count += 1
        return count

    _GENERAL_NAME_NEUTRAL_WORDS = FILTER_NEUTRAL_WORDS | {"cantidad", "conteo", "general", "global"}

    def _general_name_adds_words(self, metric, question_tokens):
        """Palabras con contenido del nombre del indicador (etiqueta o medida)
        que la pregunta no explica, sin contar «total», «número» ni conectores.
        Basta con que uno de sus nombres no añada nada."""
        neutral = {canonical_token(word) for word in STOPWORDS | self._GENERAL_NAME_NEUTRAL_WORDS}
        names = [name for name in (metric.get("label"), metric.get("measure")) if name]
        if not names:
            return []
        best = None
        for name in names:
            extra = [
                token for token in canonical_tokens(name)
                if len(token) >= 3 and token not in neutral and not token.isdigit()
                and not self._explains(token, question_tokens)
            ]
            if best is None or len(extra) < len(best):
                best = extra
        return best

    def _general_indicator(self, business_question, source_context, best):
        """El elegido es la tarjeta de una página de un SUBSERVICIO (URGENCIAS)
        que la pregunta no nombra y cuya tabla, según el diccionario, solo
        trae ese subservicio («Ingresos de ayer a urgencias...»): se prefiere
        el indicador general del mismo tablero en su página principal que
        cuenta lo mismo (TOTAL PACIENTES en INICIO para «cuántos pacientes hay
        hospitalizados»), si es uno solo y explica la pregunta. Devuelve el
        candidato nuevo o None."""
        metric = best["metric"]
        appearances = metric.get("appearances") or []
        pages = _unique_strings(item.get("page_display_name") for item in appearances)
        if not pages or any(self._PRINCIPAL_PAGE_RE.search(normalize_text(page)) for page in pages):
            return None
        question_tokens = set(canonical_tokens(business_question))
        page_tokens = {
            token for page in pages for token in canonical_tokens(page)
            if len(token) >= 4 and token not in GENERIC_PAGE_WORDS
        }
        if not page_tokens or any(self._explains(token, question_tokens) for token in page_tokens):
            return None
        model = normalize_text(metric.get("semantic_model"))
        description = self._dictionary_index().get(
            (model, "t:" + normalize_text(self._metric_fact_table(metric))), "")
        described = set(canonical_tokens(description))
        if not any(self._explains(token, described) for token in page_tokens):
            return None
        head = self._head_token(business_question, source_context)
        if not head:
            return None
        content = [canonical_token(word) for word in self._question_content_words(business_question)]
        found = {}
        for other in self._dedupe_metrics(self.metrics):
            if (
                other.get("validation_status") != "approved"
                or normalize_text(other.get("semantic_model")) != model
                or self._logical_key(other) == self._logical_key(metric)
            ):
                continue
            principal_cards = [
                item for item in other.get("appearances") or []
                if self._PRINCIPAL_PAGE_RE.search(normalize_text(item.get("page_display_name")))
                and normalize_text(item.get("visual_type")) == "card"
            ]
            # Cuenta lo mismo por su NOMBRE («TOTAL PACIENTES»), no solo por
            # la descripción de su tabla.
            own_names = set(canonical_tokens(other.get("label"))) | set(canonical_tokens(other.get("measure")))
            if not principal_cards or not self._explains(head, own_names):
                continue
            # Y su nombre no dice más que la pregunta: el general cuenta lo
            # mismo, no otra cosa del mismo tema. «TIEMPO PROMEDIO GESTION
            # FACTURA» no es «cuánto se facturó» (un tiempo, no un monto) ni
            # «TOTAL GESTIÓN CITA EN ESPERA» (en espera + asignadas) es «citas
            # en espera»; «TOTAL PACIENTES» sí es «cuántos pacientes».
            if self._general_name_adds_words(other, question_tokens):
                continue
            vocabulary = self._metric_vocabulary_tokens(other) | self._dictionary_tokens(other)
            vocabulary.update(canonical_tokens(other.get("semantic_model")))
            for report in self._metric_reports(other):
                vocabulary.update(canonical_tokens(report))
            if not all(
                self._explains(token, vocabulary) or self._shares_long_prefix(token, vocabulary)
                or _is_question_form_word(token)
                for token in content
            ):
                continue
            found.setdefault(self._logical_key(other), other)
        if len(found) > 1:
            # El general es el que no está además en la página de OTRO tema
            # propio de su tabla («PACIENTES EMERGENCIA»: pacientes de la
            # emergencia del movimiento telúrico).
            ranked = sorted(found.items(), key=lambda pair: self._subtopic_pages(pair[1], question_tokens))
            best_rank = self._subtopic_pages(ranked[0][1], question_tokens)
            found = dict(pair for pair in ranked if self._subtopic_pages(pair[1], question_tokens) == best_rank)
        if len(found) != 1:
            return None
        general = next(iter(found.values()))
        self._note(
            f"{metric.get('label')} es la tarjeta de la página {', '.join(pages)} (un subservicio que la "
            f"pregunta no nombra); se usa el indicador general del tablero: {general.get('label')}"
        )
        return {
            **best, "metric": general, "matched_name": general.get("label"),
            "_own_name": True, "_shared_alias": False, "_general_indicator": True,
            "_consumed": set(content),
        }

    # ---- indicador explicado solo por el diccionario de variables ----
    def _dictionary_resolution(self, business_question, source_context):
        """Ningún nombre de indicador coincide, pero la pregunta describe lo
        que mide uno solo según el diccionario de variables: «¿en qué turno se
        lava más ropa?» -> la suma de LAVANDERIA[Peso] («peso de ropa
        registrado en cada pesaje»), que se agrupa por turno.

        Condiciones (todas):
        - cada palabra con contenido de la pregunta la explica el nombre del
          indicador, su tablero, una columna de su tabla o el diccionario de
          su columna/tabla (raíz común de 4+ letras: «lava» ~ lavandería);
        - al menos una la explica el diccionario y no el nombre (lo medido);
        - el indicador lo ve el usuario en un tablero y es el ÚNICO (por
          medida) que cumple; con el tablero nombrado, solo cuentan los suyos.
        Si no, None (sigue la contrapregunta o la documentación)."""
        words = self._question_content_words(business_question)
        tokens = [canonical_token(word) for word in words]
        tokens = [token for token in dict.fromkeys(tokens) if token and not _is_question_form_word(token)]
        model_hint = ""
        if (source_context or {}).get("status") == "resolved" and source_context.get("routing_strength") == "strong":
            model_hint = normalize_text(source_context.get("semantic_model"))
        # Con el tablero nombrado basta una palabra («porcentaje de MORTALIDAD
        # según el perfil de morbilidad» -> %DEFUNCIONES, «Mortalidad: ...»).
        if len(tokens) < (1 if model_hint else 2):
            return None

        def common_root(token, other):
            # Raíz común de 4+ letras a la que solo le falta la terminación
            # de la palabra más corta («lavado» ~ «lavandería»: lava-).
            size = 0
            for a, b in zip(token, other):
                if a != b:
                    break
                size += 1
            return size >= 4 and size >= min(len(token), len(other)) - 2

        def loose(token, vocabulary):
            if self._explains(token, vocabulary):
                return True
            return len(token) >= 4 and any(
                len(other) >= 4 and (other.startswith(token) or token.startswith(other) or common_root(token, other))
                for other in vocabulary
            )

        found, by_name = {}, False
        for metric in self._dedupe_metrics(self.metrics):
            # Con el tablero nombrado también cuentan sus medidas sin visual
            # (PBIR del informe sin definición de visuales).
            if metric.get("validation_status") != "approved" or not (metric.get("appearances") or model_hint):
                continue
            if model_hint and normalize_text(metric.get("semantic_model")) != model_hint:
                continue
            dictionary = set(self._dictionary_tokens(metric))
            # El nombre funcional documentado de sus páginas también dice lo
            # que mide («Peso de ropa hospitalaria RECIBIDA en lavandería»).
            model_key = normalize_text(metric.get("semantic_model"))
            for page in [*self._metric_pages(metric), ""]:
                text = self._functional_name_index().get((model_key, normalize_text(page)))
                if text:
                    dictionary.update(token for token in canonical_tokens(text) if len(token) >= 4)
            names = self._metric_vocabulary_tokens(metric)
            names.update(canonical_tokens(metric.get("semantic_model")))
            for report in self._metric_reports(metric):
                names.update(canonical_tokens(report))
            entry = self._fact_table_entry(metric) or {}
            columns = {
                token for column in entry.get("columns") or []
                for token in canonical_tokens(column.get("name"))
                if len(token) >= 3
            }
            if all(loose(token, names | columns) for token in tokens):
                # Otro indicador ya se explica por su nombre o su tabla
                # («productos vencidos» = tabla PRODUCTOS_VENCIDOS): el
                # diccionario no decide; sigue el camino normal.
                by_name = True
                break
            if not dictionary or not all(loose(token, names | columns | dictionary) for token in tokens):
                continue
            if not any(
                loose(token, dictionary) and not loose(token, names | columns) for token in tokens
            ):
                continue
            found.setdefault(self._logical_key(metric), metric)
        if by_name or len(found) != 1:
            return None
        metric = next(iter(found.values()))
        self._note(
            f"ningún nombre de indicador coincide; el diccionario de variables describe lo que pregunta "
            f"({', '.join(words)}) como {metric.get('label')} ({metric.get('semantic_model')})"
        )
        item = {
            "metric": metric, "score": self.min_metric_score, "business_score": self.min_metric_score,
            "matched_name": metric.get("label"), "exact_primary_label": False, "hinted": bool(model_hint),
            "_own_name": True, "_shared_alias": False, "_dictionary": True,
        }
        return {
            "status": "resolved", "metric": metric, "matched_name": metric.get("label"),
            "score": self.min_metric_score, "candidates": [item], "source_hint_ignored": False,
            "dictionary_match": True,
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
        # Variantes por año (CIRUGIAS_2023/2024, Cirugias_Año_Actual) = una opción.
        result = self._collapse_year_variants(result, question)
        return result if limit is None else result[:limit]

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
        especialidad»). Con ello se contrapregunta en lugar de responder.
        Un indicador elegido por el diccionario de variables
        (_dictionary_resolution) ya tiene su respaldo: lo que mide."""
        if (metric_result or {}).get("dictionary_match") or (metric_result or {}).get("general_indicator"):
            return None
        ignored = {
            canonical_token(word)
            for word in STOPWORDS | GENERIC_QUERY_WORDS | FILTER_NEUTRAL_WORDS | set(MONTHS)
        } | {"por", "segun", "total"}
        dimension_tokens = set()
        own_name_tokens = {
            token for name in self._metric_names(metric) if name and not re.search(r"[().]", str(name))
            for token in canonical_tokens(name)
        }
        for field in [*group_by, *(spec["field"] for spec in explicit_specs)]:
            # El nombre de la tabla («ATENCIONES.SEDE») no nombra la dimensión.
            table_tokens = set(canonical_tokens(field.get("table")))
            # Un alias tomado del título de un visual («VALOR ESTIMADO POR
            # SERVICIO» para AREA_SERVICIO) trae palabras del indicador: esas
            # no son de la dimensión salvo que la columna se llame así (H24).
            column_tokens = set(canonical_tokens(field.get("column")))
            for alias in field.get("aliases", []) or []:
                dimension_tokens.update(
                    token for token in set(canonical_tokens(alias)) - table_tokens
                    if token in column_tokens or token not in own_name_tokens
                )
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
        if stripped == text:
            return None
        # El ranking pospuesto («, las 5 más altas») tampoco elige el indicador.
        stripped = self._POSTFIX_TOP_RE.sub(" ", stripped)
        stripped = re.sub(r"\s+", " ", stripped).strip(" ,;")
        if not stripped:
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
