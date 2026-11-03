"""Etapa «elegir indicador» (homónimos): el mismo indicador en varios tableros y opciones.

_homonyms_that_answer / _same_name_ambiguity / _homonym_tie_ambiguity (r2-contrapreguntas: solo
compiten las fuentes que responden la pregunta tal como está; r8: empate X / CANTIDAD DE X /
TOTAL_X), palabras sin interpretar que pesan más que el indicador, palabras y cobertura de las
opciones, «cuántos» sin promedios (tmdl_real), opciones nombradas por la pregunta y poda de opciones
sin relación. Mixin de QueryPlanBuilder, métodos movidos sin cambios.
"""
import re

from src.semantic.resolucion.texto import (
    _is_request_word,
    _tokens_match_loosely,
    BUSINESS_TOKEN_SYNONYMS,
    canonical_token,
    canonical_tokens,
    normalize_text,
)


class HomonimosMixin:


    def _rival_group_check(self, question, best):
        """Filtro para los rivales de nombre igual o parecido en «M por X»: si
        el indicador elegido se desglosa por X, un rival que no se puede
        desglosar por X no responde la pregunta y no se ofrece (PACIENTES
        OBSERVADOS de BRIEFING, tabla sin aseguradora, frente a PACIENTES
        OBSERVADOS POR MES de CONSULTAS PRIORITARIAS para «... por aseguradora»)."""
        tail = self._requested_group_tail(question)
        if not tail or self._group_field_in(tail, self._metric_dimensions(best)) is None:
            return lambda metric: True
        return lambda metric: self._group_field_in(tail, self._metric_dimensions(metric)) is not None

    # Pregunta por el estado presente («cuántas camas hay AHORITA», «cuántas
    # TENEMOS», «ESTÁN ocupadas»), no por lo ocurrido («cuántos egresos hubo»)
    # ni un simple «hay» («¿cuántas cirugías hay?» sigue siendo ambigua).
    _PRESENT_STATE_RE = re.compile(
        r"(?<![a-z0-9])(?:tenemos|estan|quedan|ahorita|ahora|actualmente"
        r"|en\s+este\s+momento|en\s+el\s+momento)(?![a-z0-9])"
    )

    def _homonyms_that_answer(self, question, metric_result, items, current_state=True):
        """Homónimos entre los que vale la pena preguntar. Regla general: solo
        se contrapregunta entre fuentes que pueden dar una cifra para la
        pregunta tal como está escrita.
        1. Con periodo o «por X», se arma la consulta con cada uno: el que no
           queda lista (sin fecha para «mes pasado», sin la columna X) no
           responde y sale. Si ninguno responde, no hay nada que preguntar ([]).
        2. Sin periodo (estado actual: «cuántas camas hay ahorita»), una medida
           que ningún visual muestra no es lo que el usuario ve en el tablero:
           si exactamente un homónimo está en un visual, es ese.
        Devuelve None si no descarta nada; si no, la lista que queda."""
        normalized = normalize_text(question)
        period = bool(self._has_period(normalized))
        tail = self._requested_group_tail(question)
        kept = list(items)
        if period or tail:
            ready, dropped = [], []
            for item in kept:
                forced = {
                    "status": "resolved", "metric": item["metric"],
                    "matched_name": item.get("matched_name") or item["metric"].get("label"),
                    "score": item.get("score"),
                    "candidates": [{key: value for key, value in item.items() if not key.startswith("_")}],
                    "final": True,
                }
                notes = list(self.__dict__.get("_resolution_notes") or [])
                try:
                    plan = self._build_plan(question, None, forced_resolution=forced)
                except Exception:
                    plan = None
                finally:
                    if self.__dict__.get("_resolution_notes") is not None:
                        self._resolution_notes[:] = notes
                (ready if isinstance(plan, dict) and plan.get("status") == "ready" else dropped).append(item)
            what = "el periodo" if period else ""
            what += (" y " if what and tail else "") + (f"«por {tail}»" if tail else "")
            if not ready:
                self._note(
                    f"ninguno de los indicadores de nombre «{metric_result.get('matched_name')}» admite "
                    f"{what}: no se contrapregunta entre ellos"
                )
                return []
            if dropped:
                self._note(
                    "no responden " + what + ": "
                    + ", ".join(f"{i['metric'].get('label')} ({i['metric'].get('semantic_model')})" for i in dropped)
                    + "; no se ofrecen"
                )
            kept = ready
        present = bool(self._PRESENT_STATE_RE.search(normalized))
        if current_state and present and not period and len(kept) > 1:
            shown = [item for item in kept if item["metric"].get("appearances")]
            current = [
                item for item in shown
                if self._snapshot_table(item["metric"], self._metric_dimensions(item["metric"])) is not None
            ]
            if len(shown) == 1 and current == shown:
                hidden = [item for item in kept if item is not shown[0]]
                self._note(
                    f"«{metric_result.get('matched_name')}»: sin periodo se pregunta por el estado actual; "
                    f"solo {shown[0]['metric'].get('label')} ({shown[0]['metric'].get('semantic_model')}) "
                    "lo muestra en un tablero (su tabla es el estado del momento); "
                    + ", ".join(f"{i['metric'].get('label')} ({i['metric'].get('semantic_model')})" for i in hidden)
                    + " no está en ningún visual y sin periodo sumaría todo su histórico: se responde con el primero"
                )
                kept = shown
        return kept if len(kept) < len(items) else None

    def _same_name_ambiguity(self, question, source_context, metric_result):
        """Regla: si el indicador elegido tiene el mismo nombre (o casi:
        sin «total», años ni mayúsculas/guiones) que otros de OTRO modelo o
        informe, y nada en la pregunta los distingue (tablero nombrado,
        página, tabla o palabra que solo uno explica), se contrapregunta.
        Las variantes por año de un mismo modelo cuentan como una opción.

        La penalización de -0.25 a medidas sin visual sigue ordenando las
        opciones, pero ya no basta para responder sin preguntar."""
        best = metric_result.get("metric") or {}
        if not best.get("metric_id"):
            return None
        # El indicador general que reemplazó a la tarjeta de un subservicio se
        # eligió por el tablero de esa tarjeta: no compite por nombre con otros.
        if metric_result.get("general_indicator"):
            return None
        strong = (
            source_context.get("status") == "resolved"
            and source_context.get("routing_strength") == "strong"
        )
        if strong and normalize_text(source_context.get("semantic_model")) == normalize_text(best.get("semantic_model")):
            return None
        keys = {self._name_key(metric_result.get("matched_name")), self._name_key(best.get("label"))}
        keys.discard(())
        if not keys:
            return None

        business_question = self._metric_business_question(question, source_context)
        question_tokens = canonical_tokens(business_question)
        content = {canonical_token(word) for word in self._question_content_words(business_question)}
        # El tablero también nombra al indicador («en urgencias» para CANTIDAD
        # DE TRIAGES del TABLERO TIEMPOS URGENCIAS, TU04): lo distingue de sus
        # homónimos de otros tableros.
        best_explained = {
            t for t in content
            if self._explains(t, self._metric_vocabulary_tokens(best) | self._board_tokens(best))
        }
        best_page = self._page_bonus(question_tokens, best, set(canonical_tokens(best.get("label"))))

        def where(metric):
            reports = metric.get("reports") or []
            report = metric.get("report") or (reports[0] if reports else "")
            return normalize_text(metric.get("semantic_model")), normalize_text(report)

        # La pregunta nombra el TÍTULO de un visual del elegido («giro cama» =
        # visual «GIRO CAMA» de GIRO_CAMA1): las homónimas que ningún visual
        # muestra (GIRO_CAMA de otra tabla) no son lo que el usuario ve.
        shown_titles = {
            normalize_text(item.get("visual_title")) for item in best.get("appearances") or []
            if item.get("visual_title")
        }
        # Solo si el título no es la propia etiqueta del elegido (TRIAGES con
        # visual «TRIAGES» sigue compitiendo con TOTAL_TRIAGES).
        matched = normalize_text(metric_result.get("matched_name"))
        named_by_title = matched in shown_titles and matched not in {
            normalize_text(best.get("label")), normalize_text(best.get("measure")),
        }
        rivals, seen = [], {self._logical_key(best)}
        for metric in self._dedupe_metrics(self.metrics):
            if metric.get("validation_status") != "approved":
                continue
            logical = self._logical_key(metric)
            if logical in seen:
                continue
            if named_by_title and not metric.get("appearances"):
                continue
            names =[metric.get("label"), metric.get("measure")] + [
                appearance.get("visual_title") for appearance in metric.get("appearances") or []
            ]
            if not any(name and self._name_key(name) in keys for name in names):
                continue
            explained = {
                t for t in content
                if self._explains(t, self._metric_vocabulary_tokens(metric) | self._board_tokens(metric))
            }
            if best_explained - explained:
                continue  # la pregunta nombra algo que solo explica el elegido
            if best_page and not self._page_bonus(question_tokens, metric, set(canonical_tokens(metric.get("label")))):
                continue
            seen.add(logical)
            rivals.append(metric)

        elsewhere = [metric for metric in rivals if where(metric) != where(best)]
        if not elsewhere:
            return None
        rivals.sort(key=lambda metric: 0 if metric.get("appearances") else 1)
        score = metric_result.get("score")
        items = [
            {"metric": metric, "score": score, "business_score": score,
             "matched_name": metric_result.get("matched_name") if metric is best else metric.get("label")}
            for metric in [best, *rivals]
        ]
        items = self._collapse_year_variants(items, question)[: self._SUGGESTION_LIMIT]
        if len(items) < 2:
            return None
        # «triages en 2025»: entre los del mismo nombre no responden los que
        # trabajan sobre una tabla que no trae el periodo (TRIAGES del día
        # anterior); si solo queda uno, es la respuesta aunque no tenga visual.
        covering = self._items_covering_period(business_question, items)
        if covering is not None and len(covering) < len(items):
            items = covering
            if len(items) == 1:
                if items[0]["metric"] is best:
                    return None
                return {
                    "status": "ambiguous", "stage": "metric", "reason": None,
                    "question": question, "source_context": source_context,
                    "metric_resolution": {"status": "ambiguous", "candidates": items},
                }
        # «M por X»: entre los del mismo nombre solo responden los que se
        # desglosan por X. Si queda uno, es la respuesta (aunque no sea el
        # que puntuó más); si es el elegido, no hay nada que preguntar.
        tail = self._requested_group_tail(question)
        if tail:
            groupable = [
                item for item in items
                if self._group_field_in(tail, self._metric_dimensions(item["metric"])) is not None
            ]
            if groupable and len(groupable) < len(items):
                self._note(
                    f"«{metric_result.get('matched_name')}» existe en varios tableros; solo "
                    + ", ".join(f"{i['metric'].get('label')} ({i['metric'].get('semantic_model')})" for i in groupable)
                    + f" se desglosa(n) por «{tail}»"
                )
                items = groupable
                if len(items) == 1:
                    if items[0]["metric"] is best:
                        return None
                    return {
                        "status": "ambiguous", "stage": "metric", "reason": None,
                        "question": question, "source_context": source_context,
                        "metric_resolution": {"status": "ambiguous", "candidates": items},
                    }
        # Solo uno de los homónimos es de un modelo con informe; los demás son
        # de modelos SIN ningún informe («Dashboard Gestion»), que el usuario
        # no ve: se responde con el del informe, sin contrapreguntar. Si dos o
        # más modelos tienen informe (aunque esa medida no esté en un visual),
        # la ambigüedad es real y se pregunta.
        documented = [item for item in items if self._model_has_report(item["metric"].get("semantic_model"))]
        if len(documented) == 1:
            chosen = documented[0]
            others = [item for item in items if item is not chosen]
            self._note(
                f"«{metric_result.get('matched_name')}» existe con el mismo nombre en "
                + ", ".join(f"{i['metric'].get('label')} ({i['metric'].get('semantic_model')}, modelo sin informe)"
                            for i in others)
                + f"; solo {chosen['metric'].get('label')} ({chosen['metric'].get('semantic_model')}) está en "
                "un tablero con informe: se usa ese sin contrapreguntar"
            )
            if chosen["metric"] is best:
                return None
            return {
                "status": "ambiguous", "stage": "metric", "reason": None,
                "question": question, "source_context": source_context,
                "metric_resolution": {"status": "ambiguous", "candidates": [chosen]},
            }
        # Solo se pregunta entre fuentes que pueden responder la pregunta TAL
        # COMO ESTÁ y que el usuario ve en un tablero (ver `_homonyms_that_answer`).
        narrowed = self._homonyms_that_answer(question, metric_result, items)
        if narrowed is not None:
            if not narrowed:
                return None
            if len(narrowed) == 1:
                chosen = narrowed[0]
                if chosen["metric"] is best:
                    return None
                return {
                    "status": "ambiguous", "stage": "metric", "reason": None,
                    "question": question, "source_context": source_context,
                    "metric_resolution": {"status": "ambiguous", "candidates": [chosen]},
                }
            items = narrowed
        self._note(
            f"«{metric_result.get('matched_name')}» existe con el mismo nombre en varios tableros/modelos "
            f"({', '.join(sorted({str(i['metric'].get('semantic_model')) for i in items}))}) y la "
            "pregunta no indica cuál: se contrapregunta"
        )
        return {
            "status": "ambiguous", "stage": "metric",
            "reason": "same_name_in_several_boards",
            "question": question, "source_context": source_context,
            "metric_resolution": {"status": "ambiguous", "candidates": items},
        }

    def _homonym_tie_ambiguity(self, question, source_context, metric_result):
        """Empate entre indicadores que son el MISMO concepto con otro nombre
        técnico (TRIAGES, CANTIDAD DE TRIAGES: misma `_name_key`): la
        contrapregunta es la de «existe en varios tableros», con TODOS los
        homónimos (TOTAL_TRIAGES institucional incluido) y su filtro de
        cobertura del periodo, no solo los dos que empataron por puntaje
        («cuántos triages hubo en 2025», AI04). None si el empate no es de
        homónimos o la regla de homónimos no tiene nada que preguntar."""
        if metric_result.get("status") != "ambiguous":
            return None
        candidates = [item for item in metric_result.get("candidates") or [] if (item or {}).get("metric")]
        if len(candidates) < 2:
            return None
        best = max(float(item.get("score") or 0.0) for item in candidates)
        candidates = [item for item in candidates if best - float(item.get("score") or 0.0) < self.ambiguity_margin]
        if len(candidates) < 2:
            return None
        keys = set()
        for item in candidates:
            metric = item["metric"]
            item_keys = {self._name_key(metric.get("label")), self._name_key(item.get("matched_name"))}
            item_keys.discard(())
            keys.add(tuple(sorted(item_keys)))
        flat = {key for group in keys for key in group}
        if len(flat) != 1:
            return None
        # Si la pregunta nombra algo que solo explica uno de los empatados (su
        # tablero: «en urgencias» para CANTIDAD DE TRIAGES, TU04), ya los
        # distingue: no se abre a los homónimos de otros tableros.
        business_question = self._metric_business_question(question, source_context)
        content = {canonical_token(word) for word in self._question_content_words(business_question)}
        explained = [
            frozenset(t for t in content if self._explains(
                t, self._metric_vocabulary_tokens(item["metric"]) | self._board_tokens(item["metric"])))
            for item in candidates
        ]
        if len(set(explained)) != 1:
            return None
        top = max(candidates, key=lambda item: float(item.get("score") or 0.0))
        resolved = {**metric_result, "status": "resolved", "metric": top["metric"],
                    "matched_name": top.get("matched_name") or top["metric"].get("label"),
                    "score": top.get("score")}
        plan = self._same_name_ambiguity(question, source_context, resolved)
        if not plan or plan.get("reason") != "same_name_in_several_boards":
            return None
        offered = {self._logical_key(item["metric"]) for item in plan["metric_resolution"]["candidates"]}
        if not all(self._logical_key(item["metric"]) in offered for item in candidates):
            return None  # la regla de homónimos descartó a uno de los empatados: no se arriesga
        if len(offered) <= len(candidates):
            return None  # no agrega a nadie: la contrapregunta original sirve
        return plan

    def _counted_unit(self, question, metric, source_context):
        """«cuántas CUENTAS hay en proceso de facturación» con
        PROCESO_FACTURACION: lo contado es la unidad del conteo, no un filtro ni
        otro indicador, si (1) ningún indicador aprobado del catálogo lo
        nombra (no es un concepto: «cirugías» sí lo es y sigue pidiendo su
        indicador), (2) el indicador elegido no es un tiempo, promedio ni
        porcentaje y (3) explica las demás palabras con contenido de la
        pregunta. Devuelve el token canónico o None."""
        business_question = self._metric_business_question(question, source_context)
        counted = self._counted_noun(business_question)
        if not counted or counted in self._metric_concept_tokens():
            return None
        vocabulary = self._metric_vocabulary_tokens(metric)
        if self._explains(counted, vocabulary) or self._is_duration_or_ratio(metric):
            return None
        others = [
            canonical_token(word) for word in self._question_content_words(business_question)
            if canonical_token(word) != counted
        ]
        if not others or not all(self._explains(token, vocabulary) for token in others):
            return None
        return counted

    def _unresolved_outweighs_metric(self, question, metric, metric_result, significant, source_context):
        """Regla: no se ofrece «consultar X sin <palabras>» cuando las palabras
        sin interpretar son el núcleo de la pregunta: incluyen el sustantivo
        principal («cuánto PESO hay...» con el indicador Asignadas) o pesan
        claramente más (≥ 2,5 veces, por peso IDF) que lo que coincidió con el
        indicador. Se devuelve not_found con sugerencias o, si nada de lo no
        interpretado existe en el catálogo, fuera de alcance.
        No aplica a un indicador elegido por el diccionario de variables: ya
        se comprobó que el diccionario o su tabla explican cada palabra."""
        if (metric_result or {}).get("dictionary_match") or (metric_result or {}).get("general_indicator"):
            return None
        unit = self._counted_unit(question, metric, source_context)
        significant = [word for word in significant if canonical_token(word) != unit]
        if not significant:
            return None
        leftover = [canonical_token(word) for word in significant]
        head = self._head_token(question, source_context)
        vocabulary = self._metric_vocabulary_tokens(metric)
        business_question = self._metric_business_question(question, source_context)
        evidence = [
            canonical_token(word) for word in self._question_content_words(business_question)
            if canonical_token(word) not in leftover and self._explains(canonical_token(word), vocabulary)
        ]
        left_weight = sum(self._token_weight(token) for token in leftover)
        evidence_weight = sum(self._token_weight(token) for token in evidence)
        head_missing = (
            bool(head) and head in leftover and not self._explains(head, vocabulary)
            and not self._metric_counts(metric, head)
        )
        heavier = len(leftover) >= 2 and left_weight >= 2.5 * max(evidence_weight, 0.01)
        if not (head_missing or heavier):
            return None

        reason_text = (
            f"el sustantivo principal «{head}» no corresponde al indicador"
            if head_missing else
            f"las palabras sin interpretar pesan {left_weight:.2f} frente a {evidence_weight:.2f} de la coincidencia"
        )
        unresolved_text = " ".join(significant)
        kind = self.describe_unresolved(unresolved_text).get("kind")
        out_of_scope = head_missing and kind == "out_of_scope"
        resolved_routing = source_context.get("status") == "resolved"
        strength = source_context.get("routing_strength")
        model_hint = (
            normalize_text(source_context.get("semantic_model"))
            if resolved_routing and strength in ("strong", "weak") else ""
        )
        suggestions = [] if out_of_scope else [
            item for item in self._metric_suggestions(
                business_question, model_hint=model_hint, strong=strength == "strong",
            )
            if self._logical_key(item["metric"]) != self._logical_key(metric)
        ]
        suggestions = self._collapse_year_variants(suggestions, question)
        self._note(
            f"se descartó {metric.get('label')} ({metric.get('semantic_model')}): {reason_text}; "
            + ("ninguna de esas palabras existe en el catálogo: fuera de alcance" if out_of_scope
               else f"no se ofrece consultarlo sin «{unresolved_text}»")
        )
        plan = {
            "status": "not_found", "stage": "metric",
            "reason": "unresolved_words_outweigh_metric",
            "question": question, "source_context": source_context,
            "unresolved_text": unresolved_text,
            "rejected_metric": {
                "metric_id": metric.get("metric_id"), "label": metric.get("label"),
                "matched_name": metric_result.get("matched_name"),
                "why": reason_text,
            },
            "metric_resolution": {
                "status": "not_found", "candidates": [],
                "suggestions": [
                    {key: value for key, value in item.items() if not key.startswith("_")}
                    for item in suggestions
                ],
            },
        }
        if out_of_scope:
            plan["unresolved_kind"] = "out_of_scope"
        return plan

    # ---------------- opciones de una contrapregunta ----------------
    # Palabras que nombran la unidad contada («pacientes», «casos»): «cuántos
    # pacientes observados» y OBSERVADOS cuentan lo mismo aunque el nombre no
    # diga «pacientes». No distinguen un indicador de otro.
    _OPTION_UNIT_WORDS = {
        "paciente", "pacientes", "persona", "personas", "usuario", "usuarios",
        "registro", "registros", "caso", "casos",
    }
    # Palabras genéricas en un NOMBRE de medida, pero que en la pregunta son el
    # tema («pacientes con PENDIENTES»): cuentan para decidir si una opción
    # tiene que ver con la pregunta.
    _OPTION_TOPIC_WORDS = {"pendiente", "pendientes"}
    # «por servicio», «según la EPS»: la agrupación no dice de qué indicador se trata.
    _OPTION_GROUP_RE = re.compile(
        r"(?<![a-z0-9])(?:por|segun|agrupad[oa]s?\s+por|desglosad[oa]s?\s+por)\s+"
        r"(?:(?:el|la|los|las|cada)\s+)?[a-z0-9%]+"
    )

    def _option_words(self, question, source_context):
        """Palabras distintivas de la pregunta con las que se juzga si una
        opción tiene que ver con ella: sin relleno, petición, periodo, palabras
        de agregación («total», «promedio»), la agrupación («por servicio») ni
        el nombre del tablero nombrado («en naos», «tablero de triage»)."""
        text = self._metric_business_question(question, source_context)
        text, board_tokens = self._strip_board_mentions(text, source_context)
        text = self._OPTION_GROUP_RE.sub(" ", text)
        content_free, _ = self._weak_token_sets()
        aggregation = {
            canonical_token(word)
            for word in (self._GENERIC_MEASURE_WORDS | self._TECHNICAL_NAME_WORDS) - self._OPTION_TOPIC_WORDS
        }
        ignored = set(content_free) | aggregation | set(self._period_words(text)) | set(board_tokens)
        # «en el hospital», «en general»: alcance, no un rasgo del indicador.
        ignored |= {canonical_token(word) for word in self._scope_words(text, {})}
        if (
            source_context.get("status") == "resolved"
            and source_context.get("routing_strength") == "strong"
        ):
            for name in (source_context.get("report"), source_context.get("semantic_model"),
                         source_context.get("source_group")):
                ignored.update(token for token in canonical_tokens(name) if len(token) >= 4)
        words = []
        for token in canonical_tokens(text):
            if (
                len(token) < 3 or token.isdigit() or token in ignored
                or _is_request_word(token) or token in words
            ):
                continue
            words.append(token)
        return words

    def _reflexive_verbs(self, question):
        """Verbos en pasiva refleja («se tomaron», «se realizaron»): describen
        la acción contada, no un calificativo que distinga un indicador.
        Salvo los que nombran el dato («se demoran» = TIEMPO, «se pesaron» = PESO)."""
        return {
            canonical_token(match.group(1))
            for match in re.finditer(r"(?<![a-z0-9])se\s+([a-z]{4,})", normalize_text(question))
            if match.group(1) not in BUSINESS_TOKEN_SYNONYMS
        }

    def _option_coverage(self, metric, words):
        """Palabras de `words` que explica el indicador (nombres, tabla o página).
        «%ATENDIDO» explica «atendidas» (el signo no es parte de la palabra) y
        un indicador de cosas pendientes («SIN RESPUESTA», «EN ESPERA»)
        explica «pendientes»."""
        vocabulary = set(self._metric_vocabulary_tokens(metric or {}))
        vocabulary.update(
            canonical_token(token.lstrip("%")) for token in list(vocabulary)
            if token.startswith("%") and len(token) > 3
        )
        if self._PENDING_LABEL_RE.search(
            normalize_text(f"{(metric or {}).get('label') or ''} {(metric or {}).get('measure') or ''}")
        ):
            vocabulary.update({canonical_token("pendiente"), canonical_token("pendientes")})
        return {word for word in words if self._explains(word, vocabulary)}

    _COUNT_QUESTION_RE = re.compile(r"(?<![a-z0-9])(?:cuant[oa]s|cantidad\s+de|numero\s+de)(?![a-z0-9])")
    _DURATION_WORDS = {"tiempo", "tiempos", "minutos", "minuto", "horas", "hora", "dias", "duracion", "estancia",
                       "min"}

    def _is_duration_or_ratio(self, metric):
        """Promedio, porcentaje o suma/promedio de una duración (TIEMPO_PARA_...,
        MIN, DIAS_ESTANCIA): no responde «cuántos»."""
        if self._is_ratio_metric(metric):
            return True
        names = set(normalize_text(f"{metric.get('label') or ''} {metric.get('measure') or ''}").split())
        expression = str(metric.get("base_dax_expression") or metric.get("dax_expression") or "")
        columns = set(normalize_text(" ".join(re.findall(r"\[([^\]]+)\]", expression))).split())
        return bool((names | columns) & self._DURATION_WORDS)

    def _count_question_options(self, question, candidates):
        """«¿Cuántos pacientes hospitalizados...?» pide un conteo: entre las
        opciones, las que cuentan (no un promedio, un porcentaje ni la suma
        de un tiempo: PACIENTES HOSPITALIZADOS = suma de
        TIEMPO_PARA_HOSPITALIZACION en TIEMPOS URGENCIAS). Devuelve [] si la
        pregunta no pide un conteo, si todas cuentan o si ninguna lo hace."""
        normalized = normalize_text(question)
        if not self._COUNT_QUESTION_RE.search(normalized):
            return []
        if set(normalized.split()) & (self._DURATION_WORDS | {"promedio", "porcentaje", "tasa"}):
            return []  # «cuántos minutos...», «cuántos días de estancia»: sí pide un tiempo
        kept = [item for item in candidates if not self._is_duration_or_ratio(item.get("metric") or {})]
        if not kept or len(kept) == len(candidates):
            return []
        self._note(
            "la pregunta pide un conteo: se descartan "
            + ", ".join(str((item.get("metric") or {}).get("label")) for item in candidates if item not in kept)
            + " (promedio, porcentaje o suma de un tiempo)"
        )
        return kept

    def _options_named_by_question(self, question, source_context, candidates):
        """Desempate por la frase que nombra la pregunta. Entre opciones que
        explican todas sus palabras distintivas, se quedan las que la pregunta
        nombra enteras: cada palabra de su nombre (sin conectores, «total» ni
        años) está en la pregunta. «cuántos triages pediátricos hubo en 2025»
        nombra TRIAGES_PEDIATRICOS_2025, no PROMEDIO_TRIAGES_PEDIATRICOS_2025
        ni PROM_TRIAGE_PEDIATRICOS (añaden «promedio», que no se dijo). Si varias
        quedan, solo las de nombre más largo (más específico); si ninguna o
        todas, devuelve [] (lo deciden otras reglas). Dos indicadores del mismo
        nombre en tableros distintos siguen siendo ambiguos."""
        words = self._option_words(question, source_context)
        units = {canonical_token(word) for word in self._OPTION_UNIT_WORDS}
        core = [word for word in words if word not in units] or words
        if not core:
            return []
        question_tokens = set(canonical_tokens(self._metric_business_question(question, source_context)))

        def said(token):
            return any(_tokens_match_loosely(token, other) for other in question_tokens)

        considered, named = [], []
        for item in candidates:
            metric = item.get("metric") or {}
            if float(item.get("business_score") or 0.0) < self.min_metric_score:
                continue
            considered.append(item)
            if len(self._option_coverage(metric, core)) < len(core):
                continue
            keys = [self._name_key(metric.get("label")), self._name_key(item.get("matched_name"))]
            sizes = [len(key) for key in keys if key and all(said(token) for token in key)]
            if sizes:
                named.append((item, max(sizes)))
        if len(considered) < 2 or not named:
            return []
        top = max(size for _, size in named)
        if top < 2:
            # Un nombre de una sola palabra («PENDIENTES», «CIRUGÍAS») no
            # distingue: «cuántos pendientes hay» sigue siendo ambiguo.
            return []
        kept = [item for item, size in named if size == top]
        if len(kept) == len(considered):
            return []
        return kept

    def options_explain_question(self, question, candidates, source_context=None):
        """¿Las opciones de una contrapregunta explican la pregunta lo bastante
        como para que tenga intención analítica? Al menos una opción debe
        explicar (nombre, tabla o página) la mitad de sus palabras distintivas
        sin contar las de unidad («pacientes»). «¿Qué medicamento le doy a un
        paciente con fiebre?» solo comparte «paciente» y «escríbeme un código
        en Python» solo «código» (una columna): no se contrapregunta por
        indicadores, se responde fuera de alcance. Sin palabras distintivas
        no se juzga (True)."""
        if source_context is None:
            source_context = self._source_context(question)
        units = {canonical_token(word) for word in self._OPTION_UNIT_WORDS}
        core = [word for word in self._option_words(question, source_context) if word not in units]
        if not core:
            return True
        best = max(
            (len(self._option_coverage(item.get("metric") or {}, core)) for item in candidates or []),
            default=0,
        )
        return 2 * best >= len(core)

    def _prune_unrelated_options(self, question, source_context, metric_result):
        """Depura las opciones de una contrapregunta:
        - fuera las que no comparten ninguna palabra distintiva de la pregunta
          («% Ocupación» para «pacientes con pendientes por servicio»);
        - si algunas explican TODAS las palabras distintivas, solo esas
          («consultas prioritarias»: las de consultas prioritarias, no
          cualquier «Consultas»). Las palabras de unidad («pacientes») no
          obligan. Esas opciones quedan con el mismo puntaje: la pregunta no
          decide entre ellas y la contrapregunta las muestra todas."""
        words = self._option_words(question, source_context)
        if not words:
            return metric_result
        units = {canonical_token(word) for word in self._OPTION_UNIT_WORDS}
        core = [word for word in words if word not in units] or words
        # «detalle de ocupación por aseguradores»: una opción que se desglosa
        # por la dimensión pedida y cuya página/nombre trata el tema (PACIENTES
        # por ASEGURADORA, tabla de la página DETALLE OCUPACIÓN) no se descarta
        # por no compartir una palabra con «detalle ocupacion».
        tail = self._requested_group_tail(question)
        topic = self._group_topic_words(question, source_context, tail) if tail else []
        result = dict(metric_result)
        for key in ("candidates", "suggestions"):
            items = list(result.get(key) or [])
            if len(items) < 2:
                continue
            covered = [self._option_coverage(item.get("metric"), core) for item in items]
            related = [index for index, words_covered in enumerate(covered) if words_covered]
            if not related:
                continue  # nada comparte palabras: lo decide otra regla
            full = [index for index in related if len(covered[index]) == len(core)]
            keep = full or related
            if topic and len(keep) < len(items):
                protected = [
                    index for index in range(len(items))
                    if index not in keep and self._groupable_on_topic(items[index].get("metric") or {}, tail, topic)
                ]
                if protected:
                    self._note(
                        "se conservan (se desglosan por «" + tail + "» y su página trata «"
                        + " ".join(topic) + "»): "
                        + ", ".join(str((items[i].get("metric") or {}).get("label")) for i in protected)
                    )
                    keep = sorted(set(keep) | set(protected))
            if len(keep) == len(items):
                continue
            dropped = [
                str((items[index].get("metric") or {}).get("label"))
                for index in range(len(items)) if index not in keep
            ]
            kept = [dict(items[index]) for index in keep]
            if full and len(kept) > 1:
                best = max(float(item.get("score") or 0.0) for item in kept)
                for item in kept:
                    item["score"] = best
            result[key] = kept
            self._note(
                "opciones depuradas: "
                + (f"solo las que explican «{' '.join(core)}»" if full
                   else f"solo las que comparten alguna palabra de «{' '.join(core)}»")
                + f"; fuera: {', '.join(dropped[:6])}" + (" ..." if len(dropped) > 6 else "")
            )
        return result

    def _named_board_options(self, question, source_context, metric_result):
        """Tablero nombrado (routing fuerte) y ninguna opción es de él
        («pacientes con pendientes EN NAOS por servicio» ofrecía %PENDIENTE de
        ASIGNACION DE CITAS): se buscan opciones en ese tablero. Devuelve
        ("resolved", item) si una sola explica todas las palabras de la
        pregunta, ("options", items) si hay varias, o (None, []) si el
        tablero no tiene ninguna parecida (se mantienen las de otros tableros)."""
        board_model = normalize_text(source_context.get("semantic_model"))
        business_question = self._metric_business_question(question, source_context)
        found = [
            item for item in self._metric_suggestions(
                business_question, model_hint=board_model, strong=True, ratio=0.0, limit=None,
            )
            if normalize_text(item["metric"].get("semantic_model")) == board_model
        ]
        found = self._collapse_year_variants(found, question)
        words = self._option_words(question, source_context)
        if not found or not words:
            return None, []
        coverage = [len(self._option_coverage(item["metric"], words)) for item in found]
        best = max(coverage)
        if best == 0:
            return None, []
        top = [item for item, count in zip(found, coverage) if count == best]
        clean = [{key: value for key, value in item.items() if not key.startswith("_")} for item in top]
        if len(top) == 1 and best == len(words):
            return "resolved", clean[0]
        return "options", clean[: self._SUGGESTION_LIMIT]
