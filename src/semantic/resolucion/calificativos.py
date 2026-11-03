"""Etapa «elegir indicador / filtros»: calificativos que quedaron sin interpretar.

_resolve_qualifiers: otro indicador que los nombra (triages pediátricos en 2025), calificativos
documentados, tokens de indicadores hermanos, cambio de indicador por calificativo y promoción de
candidatos (_promote_qualifier_metrics). Mixin de QueryPlanBuilder, métodos movidos sin cambios.
"""
import json
import re

from src.semantic.resolucion.texto import (
    _exact_phrase,
    _is_request_word,
    _stem_token,
    canonical_token,
    canonical_tokens,
    DIMENSION_SYNONYMS,
    FILTER_NEUTRAL_WORDS,
    GENERIC_QUERY_WORDS,
    normalize_text,
    STOPWORDS,
)


class CalificativosMixin:


    # ---------------- calificativos sin interpretar ----------------
    def _resolve_qualifiers(self, question, intent_result, metric, metric_result, source_context,
                            candidates, group_by, used_fields, consumed_tokens, allow_switch=True):
        """Palabras que quedan sin interpretar tras métrica, periodo y filtros:
        0) si nombran la tabla o la página del propio indicador, ya están
           explicadas («consultas ambulatorias» -> tabla CONSULTAS_AMBULATORIAS);
        a) si otro indicador las contiene en su nombre (TRIAGES_PEDIATRICOS_2025),
           se cambia a ese indicador o se contrapregunta entre los que las tienen;
        b) si coinciden de forma aproximada con un valor de dimensión del modelo
           (pediátricos -> PEDIATRIA, menores de edad -> MENORES DE EDAD), se filtra.
        Devuelve {"plan": plan|None, "filters": [(campo, valor)], "consumed": tokens}."""
        result = {"plan": None, "filters": [], "consumed": set()}
        leftover = self._implicit_value_text(
            question, metric, metric_result.get("matched_name"), source_context, group_by,
            extra_removals=consumed_tokens,
        )
        words = [word for word in leftover.split() if len(word) >= 3]
        vocabulary = self._metric_vocabulary_tokens(metric)
        # La agrupación «por servicio» (SERVICIOS de la tabla CAMAS DISPONIBLES)
        # no explica «disponibles»: se buscan las palabras de la tabla también
        # entre las que quitó el nombre de la columna agrupada.
        table_words = list(words)
        if group_by:
            ungrouped = self._implicit_value_text(
                question, metric, metric_result.get("matched_name"), source_context, [],
                extra_removals=consumed_tokens,
            )
            table_words.extend(word for word in ungrouped.split() if len(word) >= 3 and word not in table_words)
        if not words and not table_words:
            return result

        own = [word for word in words if self._explains(canonical_token(word), vocabulary)]
        own_table = [word for word in table_words if self._explains(canonical_token(word), vocabulary)]
        # Una palabra que solo nombra la tabla del indicador pero también es un
        # valor documentado de una de sus columnas se filtra («camas
        # disponibles» en la tabla CAMAS DISPONIBLES -> ESTADOS_CAM = DISPONIBLE).
        for word, field, resolved in self._table_word_filters(
            metric, own_table, candidates, used_fields, metric.get("semantic_model"),
        ):
            result["filters"].append((field, resolved))
            result["consumed"].add(canonical_token(word))
            own = [item for item in own if item != word]
            words = [item for item in words if item != word]
            self._note(
                f"«{word}» nombra la tabla {metric.get('table')} del indicador y además es el valor "
                f"{resolved['value']} de {field['table']}[{field['column']}]: se aplica como filtro"
            )
        if own:
            result["consumed"].update(canonical_token(word) for word in own)
            self._note(
                f"«{' '.join(own)}» ya lo explica el indicador {metric.get('label')} "
                f"(su tabla {metric.get('table')} o su página)"
            )
            words = [word for word in words if word not in own]
        # «hoy», «en este momento» con un indicador sin fecha (estado actual) y
        # unidades genéricas («pacientes»): no son filtros ni otro indicador.
        loose = [word for word in words if canonical_token(word) in self._loose_qualifier_tokens(question)]
        if loose:
            result["consumed"].update(canonical_token(word) for word in loose)
            words = [word for word in words if word not in loose]
            self._note(
                f"«{' '.join(loose)}» es un momento/periodo o una unidad genérica: no es un filtro "
                "ni elige otro indicador"
            )
        if not words:
            return result

        if allow_switch:
            plan = self._qualifier_metric_switch(
                question, intent_result, metric, metric_result, source_context, words,
            )
            if plan is not None:
                result["plan"] = plan
                return result

        # Una palabra que nombra OTRO indicador del mismo modelo («realizadas»
        # junto a CIRUGÍAS PROGRAMADAS) es probablemente otra medida, no un
        # valor: no se aproxima a un valor de dimensión.
        core = [
            canonical_token(word)
            for word in self._question_content_words(self._metric_business_question(question, source_context))
            if word not in words and self._explains(canonical_token(word), vocabulary)
        ]
        siblings = self._sibling_metric_tokens(metric, core)
        candidates_words = [
            word for word in words
            if not self._explains(canonical_token(word), siblings)
        ]
        for field, resolved in self._fuzzy_qualifier_filters(
            metric, candidates, used_fields, candidates_words, question=question,
        ):
            result["filters"].append((field, resolved))
            shown = resolved["value"] if resolved.get("value") is not None else " o ".join(resolved.get("values") or [])
            self._note(
                f"«{resolved['phrase']}» se interpretó como {field['table']}[{field['column']}] = "
                f"{shown} (coincidencia aproximada por raíz/plural)"
            )
        # c) Lo que sigue sin interpretar y la documentación del propio
        # indicador usa para describirlo («aumento de PRECIO», «imágenes
        # DIAGNÓSTICAS»): es parte del indicador, no un filtro.
        filtered = {
            canonical_token(word)
            for _, resolved in result["filters"] for word in str(resolved.get("phrase") or "").split()
        }
        # Sin las palabras de indicadores hermanos («realizadas» junto a
        # CIRUGÍAS PROGRAMADAS es otra medida aunque la documentación la nombre).
        remaining = [word for word in candidates_words if canonical_token(word) not in filtered]
        # El sustantivo principal («LISTA DE PACIENTES en espera») no lo explica
        # la documentación: si el indicador no lo nombra, cuenta otra cosa.
        head = self._head_token(question, source_context)
        remaining = [word for word in remaining if canonical_token(word) != head]
        skip = set(consumed_tokens) | filtered
        for word, evidence in self._documented_qualifiers(question, metric, remaining, skip_tokens=skip):
            result["consumed"].add(canonical_token(word))
            self._note(
                f"«{word}» describe al propio indicador {metric.get('label')} según su documentación "
                f"(«{evidence}»): no es un filtro"
            )
        return result

    # ---------------- documentación del indicador ----------------
    _DOC_TEXT_FIELDS = (
        "description", "visuals", "indicators", "documented_measures", "definitions",
        "business_rules", "notes",
    )

    def _semantic_documents_index(self):
        """{modelo normalizado: [tableros documentados]} de data/semantic_documents."""
        cached = self.__dict__.get("_semantic_documents_cache")
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
                # El diccionario de variables no es una página: sus medidas y
                # textos no deben contar como documentación de una página.
                if isinstance(dashboard, dict) and not dashboard.get("is_dictionary"):
                    index.setdefault(model, []).append(dashboard)
        self._semantic_documents_cache = index
        return index

    @staticmethod
    def _flatten_texts(value):
        if isinstance(value, str):
            return [value]
        if isinstance(value, dict):
            return [text for item in value.values() for text in CalificativosMixin._flatten_texts(item)]
        if isinstance(value, (list, tuple)):
            return [text for item in value for text in CalificativosMixin._flatten_texts(item)]
        return []

    def _metric_documentation(self, metric):
        """Textos que describen el indicador: su descripción, su DAX y la
        documentación del tablero donde está (tablero con el nombre de su
        página o de su nombre/tabla, o cuyas visualizaciones lo nombran)."""
        cache = self.__dict__.setdefault("_metric_documentation_cache", {})
        key = (self._logical_key(metric), normalize_text(metric.get("label")))
        if key in cache:
            return cache[key]
        texts = [str(metric.get(field)) for field in ("description", "model_expression") if metric.get(field)]
        vocabulary = self._metric_vocabulary_tokens(metric, with_pages=False)
        pages = {normalize_text(page) for page in self._metric_pages(metric)}
        stop = {canonical_token(word) for word in STOPWORDS | GENERIC_QUERY_WORDS | FILTER_NEUTRAL_WORDS}
        label = normalize_text(metric.get("label"))
        label_specific = len([t for t in canonical_tokens(label) if t not in stop and not t.isdigit()]) >= 2
        for dashboard in self._semantic_documents_index().get(normalize_text(metric.get("semantic_model")), []):
            name = normalize_text(dashboard.get("name"))
            name_tokens = [t for t in canonical_tokens(name) if t not in stop and len(t) >= 3]
            dashboard_texts = [
                text for field in self._DOC_TEXT_FIELDS for text in self._flatten_texts(dashboard.get(field))
            ]
            linked = name in pages or (name_tokens and all(self._explains(t, vocabulary) for t in name_tokens))
            if linked:
                texts.extend(dashboard_texts)
                continue
            mentions = [text for text in dashboard_texts if label_specific and _exact_phrase(normalize_text(text), label)]
            if mentions:
                texts.extend(mentions)
                texts.extend(self._flatten_texts(dashboard.get("description")))
        cache[key] = texts
        return texts

    def _same_measure_metrics(self, metric):
        """El indicador y los demás aprobados con su misma medida (modelo,
        tabla y expresión), el propio primero."""
        key = self._logical_key(metric)
        result = [metric]
        if not key[-1]:
            return result
        for other in self._dedupe_metrics(self.metrics):
            if other is metric or other.get("validation_status") != "approved":
                continue
            if self._logical_key(other) == key and other.get("metric_id") != metric.get("metric_id"):
                result.append(other)
        return result

    _BREAKDOWN_LABEL_RE = re.compile(r"(?<![a-z0-9])(?:por|x|segun)\s+[a-z]")

    def _scalar_representative(self, metric):
        """Para un valor único, el nombre de un gráfico «PACIENTES por
        ASEGURADORA» describe un desglose que no se muestra: si la misma
        medida está en una tarjeta («TOTAL PACIENTES»), se responde con ella."""
        if not self._BREAKDOWN_LABEL_RE.search(normalize_text(metric.get("label"))):
            return metric
        for other in self._same_measure_metrics(metric)[1:]:
            if self._BREAKDOWN_LABEL_RE.search(normalize_text(other.get("label"))):
                continue
            if any(item.get("visual_type") == "card" for item in other.get("appearances") or []):
                self._note(
                    f"{metric.get('label')} es la misma medida que la tarjeta {other.get('label')}: "
                    "para un valor único se responde con la tarjeta"
                )
                return other
        return metric

    def _documented_qualifiers(self, question, metric, words, skip_tokens=()):
        """[(palabra, evidencia)] de las palabras que la documentación del
        indicador usa y que en la pregunta califican a una palabra del propio
        indicador (vecina inmediata, saltando conectores): «compras con
        aumento de PRECIO» (aumento ∈ nombre; «precios» en la documentación).
        Nunca palabras de dimensión (servicio, especialidad...)."""
        if not words:
            return []
        # La misma medida publicada en otra página (TOTAL PACIENTES de DETALLE
        # OCUPACIÓN = PACIENTES por ASEGURADORA de INICIO) trae también la
        # documentación de esa página.
        texts = []
        for same in self._same_measure_metrics(metric):
            texts.extend(text for text in self._metric_documentation(same) if text not in texts)
        if not texts:
            return []
        forms = {}
        excluding = {"excluye", "excluyen", "excluia", "excluian", "excluir", "excluyendo", "sin",
                     "salvo", "excepto", "menos", "no"}
        for text in texts:
            normalized = normalize_text(text)
            doc_words = normalized.split()
            for position, doc_word in enumerate(doc_words):
                if len(doc_word) < 4:
                    continue
                # «excluye los triages OBSTETRICOS»: lo que la documentación
                # excluye no describe al indicador.
                if excluding & set(doc_words[max(0, position - 4):position]):
                    continue
                for form in (canonical_token(doc_word), _stem_token(doc_word)):
                    forms.setdefault(form, normalized)
        dimension_words = {
            canonical_token(word) for synonyms in DIMENSION_SYNONYMS.values() for word in synonyms
        } | {canonical_token(word) for word in self.PLAUSIBLE_VALUE_COLUMN_WORDS}
        vocabulary = self._metric_vocabulary_tokens(metric)
        connectors = {
            "de", "del", "la", "el", "los", "las", "con", "en", "y", "a", "al", "por",
            "estan", "esta", "estaban", "estuvieron", "hay", "son", "es", "fueron",
        }
        question_words = normalize_text(question).split()
        found = []
        for word in words:
            token = canonical_token(word)
            if len(token) < 4 or token in dimension_words:
                continue
            evidence = forms.get(token) or forms.get(_stem_token(word))
            if not evidence:
                continue
            adjacent = False
            for index, other in enumerate(question_words):
                if other != word:
                    continue
                for step in (-1, 1):
                    position = index + step
                    while 0 <= position < len(question_words) and (
                        question_words[position] in connectors
                        or (
                            canonical_token(question_words[position]) in skip_tokens
                            and not self._explains(canonical_token(question_words[position]), vocabulary)
                        )
                    ):
                        position += step
                    if 0 <= position < len(question_words) and self._explains(
                        canonical_token(question_words[position]), vocabulary,
                    ):
                        adjacent = True
            if not adjacent:
                continue
            # Fragmento de la documentación alrededor de la palabra (para el razonamiento).
            doc_words = evidence.split()
            spot = next(
                (i for i, doc_word in enumerate(doc_words)
                 if canonical_token(doc_word) == token or _stem_token(doc_word) == _stem_token(word)),
                0,
            )
            snippet = " ".join(doc_words[max(0, spot - 4):spot + 4])
            found.append((word, snippet))
        return found

    def _sibling_metric_tokens(self, metric, core):
        """Palabras de los nombres de los indicadores «hermanos»: del mismo
        modelo y que también nombran el sustantivo de la pregunta (`core`):
        CIRUGÍAS REALIZADAS es hermano de CIRUGÍAS PROGRAMADAS."""
        model = normalize_text(metric.get("semantic_model"))
        own = self._logical_key(metric)
        # Al probar otro candidato porque el elegido no entendía un filtro
        # (_candidate_that_filters), el elegido no cuenta como «hermano»: sus
        # palabras («ocupadas» de CAMAS OCUPADAS) pueden ser valores del otro.
        exempt = frozenset(self.__dict__.get("_sibling_exempt") or ())
        cache = self.__dict__.setdefault("_sibling_tokens_cache", {})
        key = (model, own, tuple(sorted(core)), exempt)
        if key in cache:
            return cache[key]
        _, generic = self._weak_token_sets()
        own_tokens = self._metric_vocabulary_tokens(metric, with_pages=False)
        tokens = set()
        if core:
            for other in self._dedupe_metrics(self.metrics):
                if (
                    other.get("validation_status") != "approved"
                    or normalize_text(other.get("semantic_model")) != model
                    or self._logical_key(other) == own
                    or self._logical_key(other) in exempt
                ):
                    continue
                names = [other.get("label"), other.get("measure")] + [
                    appearance.get("visual_title") for appearance in other.get("appearances") or []
                ]
                for name in names:
                    name_tokens = [t for t in canonical_tokens(name) if not t.isdigit()]
                    if not all(self._explains(token, name_tokens) for token in core):
                        continue
                    tokens.update(
                        token for token in name_tokens
                        if len(token) >= 4 and token not in generic and token not in own_tokens
                    )
        cache[key] = tokens
        return tokens

    _RELATIVE_TIME_TOKENS = frozenset(
        canonical_token(word) for word in (
            "hoy", "ayer", "anteayer", "ahora", "ahorita", "actualmente", "momento",
        )
    )

    def _loose_qualifier_tokens(self, question):
        """Palabras que nunca califican al indicador: el periodo de la
        pregunta, momentos relativos («hoy», «momento») y unidades genéricas."""
        return (
            set(self._period_words(question)) | self._RELATIVE_TIME_TOKENS
            | {canonical_token(word) for word in self._OPTION_UNIT_WORDS}
        )

    def _qualifier_metric_switch(self, question, intent_result, metric, metric_result,
                                 source_context, words):
        """Regla 3a: ¿con el calificativo cambia la mejor métrica? Busca
        indicadores cuyo nombre (o tabla/página) contiene el calificativo y el
        sustantivo principal. Uno claramente mejor -> se usa; varios -> se
        contrapregunta entre ellos (y el elegido originalmente).

        Un momento o periodo («hoy», «ayer», «en este momento») y las unidades
        genéricas («pacientes», «casos») no son calificativos: «egresos
        probables para HOY» no es EGRESOS EFECTIVOS HOY ni «cuánto duran los
        PACIENTES en urgencias» es el tiempo de los pacientes hospitalizados."""
        if (metric_result or {}).get("general_indicator"):
            return None  # ya se cambió el de un subservicio por el general
        ignored = self._loose_qualifier_tokens(question)
        dropped = [word for word in words if canonical_token(word) in ignored]
        words = [word for word in words if canonical_token(word) not in ignored]
        if dropped:
            self._note(
                f"«{' '.join(dropped)}» es un momento/periodo o una unidad genérica: "
                "no elige otro indicador"
            )
        if not words:
            return None
        qualifiers = [canonical_token(word) for word in words]
        current_vocabulary = self._metric_vocabulary_tokens(metric)
        # Lo que ya explicaba el indicador elegido (sin palabras genéricas de
        # medida) debe seguir explicado: «cirugías programadas y realizadas»
        # no cambia CIRUGÍAS PROGRAMADAS por CIRUGÍAS REALIZADAS (son dos medidas).
        core = [
            canonical_token(word)
            for word in self._question_content_words(self._metric_business_question(question, source_context))
            if canonical_token(word) not in qualifiers
            and self._explains(canonical_token(word), current_vocabulary)
        ]
        found = self._qualifier_candidates(
            question, source_context, qualifiers, core, exclude={self._logical_key(metric)},
        )
        # «M por X»: si el elegido se desglosa por X, un indicador que no se
        # puede desglosar no responde la pregunta aunque nombre el calificativo.
        groups_by = self._rival_group_check(question, metric)
        found = [item for item in found if groups_by(item["metric"])]
        if not found:
            return None
        # Solo compiten los que responden la pregunta tal como está: fuera los
        # de tablas o páginas del día cuando se pide «mes pasado», y una sola
        # vez el indicador que la misma página muestra en tarjeta y en gráfico.
        covering = self._items_covering_period(
            self._metric_business_question(question, source_context), found,
        )
        if covering is not None:
            found = covering
        found = self._collapse_page_twins(found)
        top = found[0]
        second = found[1] if len(found) > 1 else None
        words_text = " ".join(words)
        clear = (
            top["business_score"] >= self.min_metric_score
            and (second is None or second["_covered"] < top["_covered"]
                 or second.get("_explained", 0) < top.get("_explained", 0)
                 or top["score"] - second["score"] >= self.ambiguity_margin)
        )
        if clear:
            # «hospitalizados» lleva a la tarjeta de un subservicio (URGENCIAS)
            # que la pregunta no nombra: se usa el indicador general del tablero.
            business_question = self._metric_business_question(question, source_context)
            general = self._general_indicator(business_question, source_context, top)
            if general is not None:
                forced = {
                    "status": "resolved", "metric": general["metric"],
                    "matched_name": general["matched_name"], "score": top["score"],
                    "candidates": [{key: value for key, value in general.items() if not key.startswith("_")}],
                    "final": True, "consumed_tokens": general["_consumed"], "general_indicator": True,
                }
                return self._build_plan(question, intent_result, forced_resolution=forced)
            chosen = {key: value for key, value in top.items() if not key.startswith("_")}
            interpretation = (
                f"«{words_text}» forma parte del indicador {top['metric'].get('label')} "
                f"(en lugar de {metric.get('label')}, que no lo explicaba)"
            )
            self._note(interpretation)
            forced = {
                "status": "resolved", "metric": top["metric"],
                "matched_name": top["matched_name"], "score": top["score"],
                "candidates": [chosen], "interpretation": interpretation,
            }
            return self._build_plan(question, intent_result, forced_resolution=forced)

        options = [
            {key: value for key, value in item.items() if not key.startswith("_")}
            for item in found[: self._SUGGESTION_LIMIT - 1]
        ]
        options.append({
            "metric": metric, "score": metric_result.get("score"),
            "business_score": metric_result.get("score"),
            "matched_name": metric_result.get("matched_name"),
        })
        best_score = max(float(item.get("score") or 0.0) for item in options)
        for item in options:
            item["score"] = best_score  # todas se muestran: la pregunta no decide
        self._note(
            f"«{words_text}» aparece en el nombre de otros indicadores "
            f"({', '.join(str(i['metric'].get('label')) for i in options[:-1])}); "
            f"no se ofrece {metric.get('label')} sin ese calificativo: se contrapregunta"
        )
        return {
            "status": "ambiguous", "stage": "metric",
            "reason": "qualifier_matches_other_metrics",
            "question": question, "source_context": source_context,
            "unresolved_text": words_text,
            "metric_resolution": {"status": "ambiguous", "candidates": options},
        }

    def _qualifier_candidates(self, question, source_context, qualifiers, core, exclude=()):
        """Indicadores cuyo nombre, tabla o página explican al menos un
        calificativo y todas las palabras `core`, ordenados (más calificativos
        cubiertos, mejor coincidencia por nombre) y sin variantes por año repetidas.
        Con un tablero nombrado (routing fuerte) solo los de ese modelo; una
        palabra que solo coincide con su nombre pero es una dimensión («por
        eps» no es el TABLERO EPS) no restringe."""
        strong = (
            source_context.get("status") == "resolved"
            and source_context.get("routing_strength") == "strong"
            and self._board_named_explicitly(question, source_context)
        )
        named_model = normalize_text(source_context.get("semantic_model")) if strong else ""
        business_question = self._metric_business_question(question, source_context)
        weights = self._token_weight_index()
        stop = {canonical_token(word) for word in STOPWORDS | GENERIC_QUERY_WORDS}
        question_words = [
            token for token in canonical_tokens(business_question)
            if token not in stop and len(token) >= 3 and not _is_request_word(token)
        ]

        found, seen = [], set(exclude)
        for other in self._dedupe_metrics(self.metrics):
            if other.get("validation_status") != "approved":
                continue
            if named_model and normalize_text(other.get("semantic_model")) != named_model:
                continue
            logical = self._logical_key(other)
            if logical in seen:
                continue
            # También lo que el filtro de inclusión de su visual le da al
            # indicador («Triages Gineco» filtrada por los valores OBSTETRICA).
            vocabulary = self._metric_vocabulary_tokens(other) | self._inclusion_filter_tokens(other)
            covered = [token for token in qualifiers if self._explains(token, vocabulary)]
            if not covered or not all(self._explains(token, vocabulary) for token in core):
                continue
            # Nombres sin contenido propio («Promedio de MIN») no cuentan, pero
            # tampoco descartan el indicador si su etiqueta sí nombra algo; los
            # conectores del nombre («TIEMPO PROMEDIO PARA ATENCIÓN EN TRIAGE»)
            # no se exigen en la pregunta.
            names = [name for name in self._metric_names(other) if not self._weak_name_kind(name)]
            scored = []
            for name in names:
                scored.append((self._loose_phrase_score(business_question, name, weights), name))
                content_name = " ".join(
                    word for word in normalize_text(name).split() if canonical_token(word) not in stop
                )
                if content_name and content_name != normalize_text(name) and len(content_name.split()) >= 2:
                    scored.append((self._loose_phrase_score(business_question, content_name, weights), name))
            if other.get("table") and other.get("label") and not self._weak_name_kind(other.get("label")):
                scored.append((
                    self._loose_phrase_score(
                        business_question, f"{other.get('label')} {other.get('table')}", weights,
                    ),
                    other.get("label"),
                ))
            # Un visual filtrado («Triages Gineco» con DESCRI_TRIGE en los
            # valores OBSTETRICA, en la página TRIAGES ATENDIDOS) se nombra
            # por su página más lo que su filtro le da: «triages obstétricos
            # atendidos».
            inclusion = self._inclusion_filter_tokens(other)
            if inclusion and other.get("label") and any(self._explains(token, inclusion) for token in covered):
                for page in self._metric_pages(other):
                    scored.append((
                        self._loose_phrase_score(business_question, f"{page} {' '.join(sorted(inclusion))}", weights),
                        other.get("label"),
                    ))
            score, name = max(scored, key=lambda pair: pair[0], default=(0.0, None))
            if score <= 0 or not name:
                continue
            seen.add(logical)
            business = score
            if not other.get("appearances"):
                score -= 0.10
            # Palabras de la pregunta que su propio nombre explica («tiempo
            # PROMEDIO ... triage»): desempata entre los que cubren el calificativo.
            name_tokens = {token for value in names for token in canonical_tokens(value) if len(token) >= 3}
            explained = sum(1 for token in question_words if self._explains(token, name_tokens))
            found.append({
                "metric": other, "score": round(score, 4), "business_score": round(business, 4),
                "matched_name": name, "_covered": len(covered), "_explained": explained,
            })
        # «Recuento de PACNUMDOC» (conteo implícito de un identificador) va
        # detrás de cualquier indicador cuyo propio nombre dice la entidad de la
        # pregunta: su página o su filtro no lo convierten en «triages».
        named = any(item["_explained"] > 0 and not self._implicit_identifier_count(item["metric"])
                    for item in found)
        found.sort(key=lambda item: (
            named and self._implicit_identifier_count(item["metric"]),
            -item["_covered"], -item["_explained"], -item["score"], normalize_text(item["metric"].get("label")),
        ))
        # Un calificativo no lleva a un indicador cuya tabla no trae el periodo
        # pedido («triages de este mes en urgencias» no vuelve a los TRIAGES
        # del día anterior del Briefing).
        period, start, end = self._requested_period_bounds(business_question)
        if period is not None and found:
            kept = [item for item in found if self._metric_misses_period(item["metric"], start, end) is None]
            if len(kept) < len(found):
                self._note(
                    f"«{period.get('label')}»: no se cambia a indicadores cuya tabla no trae ese periodo: "
                    + ", ".join(str(item["metric"].get("label")) for item in found if item not in kept)
                )
                found = kept
        return self._collapse_year_variants(found, question)

    def _promote_qualifier_metrics(self, question, source_context, metric_result):
        """Empate entre indicadores que NO explican una palabra de la pregunta
        («consultas PRIORITARIAS»: Consultas de dos tableros): los indicadores
        que sí la nombran (PRIORITARIAS_2025, tabla CONSULTAS PRIORITARIAS) se
        ofrecen primero. Se sigue contrapreguntando: no se elige por el usuario."""
        candidates = list(metric_result.get("candidates") or [])
        if not candidates:
            return metric_result
        best = max(float(item.get("score") or 0.0) for item in candidates)
        tied = [item for item in candidates if best - float(item.get("score") or 0.0) < self.ambiguity_margin]
        # El tablero del indicador también lo nombra («urgencias» para CANTIDAD
        # DE TRIAGES del TABLERO TIEMPOS URGENCIAS), como en _resolve_metric.
        vocabularies = [
            self._metric_vocabulary_tokens(item["metric"]) | self._board_tokens(item["metric"]) for item in tied
        ]
        business_question = self._metric_business_question(question, source_context)
        content = [canonical_token(word) for word in self._question_content_words(business_question)]
        qualifiers = [t for t in content if not any(self._explains(t, v) for v in vocabularies)]
        if not qualifiers:
            return metric_result
        core = [t for t in content if t not in qualifiers]
        found = self._qualifier_candidates(
            question, source_context, qualifiers, core,
            exclude={self._logical_key(item["metric"]) for item in tied},
        )[:3]
        if not found:
            return metric_result
        promoted = [
            {**{k: v for k, v in item.items() if not k.startswith("_")}, "score": best}
            for item in found
        ]
        promoted_keys = {self._logical_key(item["metric"]) for item in promoted}
        rest = [item for item in candidates if self._logical_key(item["metric"]) not in promoted_keys]
        self._note(
            f"ningún indicador empatado explica «{' '.join(qualifiers)}»; se ofrecen primero los que sí: "
            + ", ".join(str(item["metric"].get("label")) for item in promoted)
        )
        return {**metric_result, "candidates": promoted + rest}
