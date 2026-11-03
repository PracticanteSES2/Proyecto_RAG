"""Etapa «contrapreguntas» (páginas): páginas nombradas y sus indicadores.

Índice de páginas, miembros y principal, _page_choices (r3 «Día», r6 TU04 cobertura), refinamiento
por página nombrada (_named_page_refinement), páginas homónimas (r2 BH07/TU05),
_similar_name_ambiguity y _forced_plan. Mixin de QueryPlanBuilder, métodos movidos sin cambios.
"""
import re

from src.semantic.resolucion.texto import (
    _POLARITY_WORDS,
    _tokens_match_loosely,
    _unique_strings,
    canonical_phrases,
    canonical_token,
    canonical_tokens,
    FILTER_NEUTRAL_WORDS,
    GENERIC_PAGE_WORDS,
    GENERIC_QUERY_WORDS,
    MONTHS,
    normalize_text,
    NUMERIC_TERM_PATTERNS,
    QUERY_VERB_PATTERNS,
    STOPWORDS,
    value_contradiction,
)


class PaginasMixin:


    # ---------------- páginas nombradas ----------------
    # Una página se nombra por su tema («hospitalizaciones parciales de marzo»,
    # «partos de 2025») o con «tablero/página de X». Sus indicadores salen de
    # las visualizaciones del catálogo (tarjetas primero), de las medidas
    # documentadas de esa página en el RAG y, si el catálogo no tiene sus
    # visualizaciones, de los indicadores del modelo cuyo nombre o tabla
    # explica el nombre de la página (tema).
    _PAGE_IGNORED_NAME_WORDS = {
        "cantidades", "cantidad", "tiempos", "tiempo", "cuentas", "detalle", "resumen", "inicio",
        "general", "listado", "consolidado", "seguimiento", "total", "totales", "indicadores",
        "principal", "portada", "home", "menu", "tablero", "informe", "reporte", "pagina",
    }
    _PAGE_PRINCIPAL_RE = re.compile(r"^(?:total|totales|numero|nro|cantidad|conteo|recuento)(?:\s|$)")
    _PAGE_RANKS = {"card": 0, "visual": 1, "documentation": 2, "topic": 3}

    def _page_index(self):
        """{(modelo, página) normalizados: {"page", "semantic_model", "report",
        "visual", "members": {clave lógica: miembro}}}. Un miembro es
        {"metric", "visual_type", "source", "title", "rank"}."""
        cached = self.__dict__.get("_page_index_cache")
        if cached is not None:
            return cached
        index = {}
        metrics = [m for m in self._dedupe_metrics(self.metrics) if m.get("validation_status") == "approved"]
        model_names = {normalize_text(m.get("semantic_model")): m.get("semantic_model") for m in metrics}

        def entry(model, page, report=None):
            key = (normalize_text(model), normalize_text(page))
            if not key[0] or not key[1]:
                return None
            item = index.setdefault(key, {
                "page": str(page).strip(), "semantic_model": model_names.get(key[0], model),
                "report": report, "visual": False, "members": {},
            })
            if report and not item.get("report"):
                item["report"] = report
            return item

        def add(item, metric, source, visual_type=None, title=None):
            if item is None:
                return
            rank = self._PAGE_RANKS["card"] if visual_type == "card" else self._PAGE_RANKS[
                "visual" if source == "visual" else source
            ]
            key = self._logical_key(metric)
            current = item["members"].get(key)
            if current is None or rank < current["rank"]:
                item["members"][key] = {
                    "metric": metric, "visual_type": visual_type, "source": source,
                    "title": title, "rank": rank, "order": len(item["members"]) if current is None else current["order"],
                }

        for metric in metrics:
            for appearance in metric.get("appearances") or []:
                page = appearance.get("page_display_name")
                item = entry(metric.get("semantic_model"), page, appearance.get("report"))
                if item is None:
                    continue
                item["visual"] = True
                add(item, metric, "visual", appearance.get("visual_type"), appearance.get("visual_title"))

        # Medidas documentadas en la página («TRIAGE»: TOTAL_TRIAGES, PROMEDIO_TRIAGE_2025...).
        by_name = {}
        for metric in metrics:
            for name in (metric.get("measure"), metric.get("label")):
                key = (normalize_text(metric.get("semantic_model")), normalize_text(name))
                if key[1] and metric not in by_name.setdefault(key, []):
                    by_name[key].append(metric)
        for model_key, dashboards in self._semantic_documents_index().items():
            for dashboard in dashboards:
                item = entry(model_names.get(model_key, model_key), dashboard.get("name"))
                if item is None:
                    continue
                for measure in dashboard.get("documented_measures") or []:
                    raw = measure.get("name") if isinstance(measure, dict) else measure
                    name = normalize_text(str(raw or "").split("=")[0])
                    for metric in by_name.get((model_key, name), []):
                        add(item, metric, "documentation")

        # Páginas que el enrutador conoce aunque no tengan indicadores.
        known = getattr(self.source_router, "known_pages", None)
        try:
            pages = known() if callable(known) else []
        except Exception:
            pages = []
        for page in pages or []:
            entry(page.get("semantic_model"), page.get("name"), page.get("report"))
        self._page_index_cache = index
        return index

    def _page_name_tokens(self, page):
        """Palabras con contenido del nombre de una página (sin genéricas)."""
        ignored = self._content_ignored_tokens() | {
            canonical_token(word) for word in self._PAGE_IGNORED_NAME_WORDS | GENERIC_PAGE_WORDS
        }
        return [
            token for token in dict.fromkeys(canonical_tokens(page))
            if len(token) >= 3 and not token.isdigit() and token not in ignored
        ]

    def _page_members(self, page):
        """Indicadores de una página {"semantic_model", "page"} en orden:
        tarjetas, otras visualizaciones, medidas documentadas y, si el catálogo
        no tiene sus visualizaciones, los del modelo cuyo nombre o tabla
        explica el nombre de la página."""
        key = (normalize_text(page.get("semantic_model")), normalize_text(page.get("page")))
        cache = self.__dict__.setdefault("_page_members_cache", {})
        if key in cache:
            return cache[key]
        item = self._page_index().get(key)
        members = list((item or {}).get("members", {}).values())
        if item is not None and not item.get("visual"):
            tokens = self._page_name_tokens(item["page"])
            present = {self._logical_key(member["metric"]) for member in members}
            if tokens:
                for metric in self._dedupe_metrics(self.metrics):
                    if (
                        metric.get("validation_status") != "approved"
                        or normalize_text(metric.get("semantic_model")) != key[0]
                        or self._logical_key(metric) in present
                    ):
                        continue
                    vocabulary = self._metric_vocabulary_tokens(metric, with_pages=False)
                    if all(self._explains(token, vocabulary) for token in tokens):
                        present.add(self._logical_key(metric))
                        members.append({
                            "metric": metric, "visual_type": None, "source": "topic", "title": None,
                            "rank": self._PAGE_RANKS["topic"], "order": len(members),
                        })
        members.sort(key=lambda member: (member["rank"], member["order"]))
        cache[key] = members
        return members

    def _page_report(self, page):
        item = self._page_index().get((normalize_text(page.get("semantic_model")), normalize_text(page.get("page"))))
        report = page.get("report") or (item or {}).get("report")
        if report:
            return report
        sources_for_model = getattr(self.source_router, "sources_for_model", None)
        try:
            sources = sources_for_model(page.get("semantic_model")) if callable(sources_for_model) else []
        except Exception:
            sources = []
        return next((source.get("report") for source in sources or [] if source.get("report")),
                    page.get("semantic_model"))

    def _is_report_page(self, page):
        """Página documentada que en realidad es el informe completo
        («TABLERO DE ATENCIONES INSTITUCIONALES» como nombre de página)."""
        name = normalize_text(page.get("page"))
        names = {normalize_text(page.get("semantic_model")), normalize_text(page.get("report"))}
        sources_for_model = getattr(self.source_router, "sources_for_model", None)
        try:
            sources = sources_for_model(page.get("semantic_model")) if callable(sources_for_model) else []
        except Exception:
            sources = []
        for source in sources or []:
            names.update(normalize_text(value) for value in [source.get("report"), *(source.get("aliases") or [])])
        stripped = {re.sub(r"^(?:tablero|informe|reporte)\s+(?:(?:de|del)\s+)?", "", value) for value in names if value}
        return name in names or name in stripped

    def _named_pages(self, source_context):
        """Páginas nombradas con «tablero/página de X» (no un informe):
        la del enrutamiento fuerte o, si el nombre existe en varios modelos,
        todas las páginas con ese nombre."""
        context = source_context or {}
        pages = []
        if context.get("status") == "resolved" and context.get("routing_strength") == "strong":
            if context.get("board_kind") in ("page", "documentation") and context.get("dashboard"):
                pages.append({"semantic_model": context.get("semantic_model"), "page": context.get("dashboard"),
                              "report": context.get("report")})
        elif context.get("board_mentions"):
            for mention in context.get("board_mentions") or []:
                for item in mention.get("contexts") or []:
                    if item.get("kind") in ("page", "documentation") and item.get("dashboard"):
                        pages.append({"semantic_model": item.get("semantic_model"), "page": item.get("dashboard"),
                                      "report": item.get("report")})
        return self._dedupe_pages(pages)

    def _dedupe_pages(self, pages):
        result, seen = [], set()
        for page in pages:
            key = (normalize_text(page.get("semantic_model")), normalize_text(page.get("page")))
            if key in seen or self._is_report_page(page):
                continue
            seen.add(key)
            result.append(page)
        return result

    def _topic_pages(self, question):
        """Páginas nombradas por su tema, sin «tablero de» («partos de 2025»)."""
        mentions_for = getattr(self.source_router, "page_topic_mentions", None)
        if not callable(mentions_for):
            return []
        ignored = (
            STOPWORDS | GENERIC_QUERY_WORDS | FILTER_NEUTRAL_WORDS | set(MONTHS) | GENERIC_PAGE_WORDS
            | self._GENERIC_MEASURE_WORDS | self._TECHNICAL_NAME_WORDS | self._PAGE_IGNORED_NAME_WORDS
        )
        try:
            mentions = mentions_for(question, ignored_words=ignored) or []
        except Exception:
            return []
        # «pacientes por especialidad»: la agrupación no nombra la página
        # DETALLE ESPECIALIDADES (sí «atenciones por asegurador» entera).
        tail = self._requested_group_tail(question)
        if tail:
            tail_tokens = set(canonical_tokens(tail))
            mentions = [
                mention for mention in mentions
                if not set(canonical_tokens(mention.get("phrase"))) <= tail_tokens
            ]
        pages = [
            {"semantic_model": item.get("semantic_model"), "page": item.get("dashboard"),
             "report": item.get("report"), "phrase": mention.get("phrase")}
            for mention in mentions for item in mention.get("contexts") or []
            if item.get("dashboard")
        ]
        return self._dedupe_pages(pages)

    def _page_extra_words(self, metric, question):
        """Palabras con contenido del nombre del indicador que la pregunta no
        dice («pediátricos» en PROMEDIO_TRIAGES_PEDIATRICOS_2025)."""
        content_free, generic = self._weak_token_sets()
        said = set(canonical_tokens(question))
        extra = set()
        for token in canonical_tokens(metric.get("label")):
            if len(token) < 4 or token.isdigit() or token in generic or token in content_free:
                continue
            if not self._explains(token, said):
                extra.add(token)
        return len(extra)

    def _page_principal(self, pool):
        """Indicador principal de una página entre las opciones: el único,
        la única tarjeta o la única «Total …/Número de …»."""
        if len(pool) == 1:
            return pool[0]
        cards = [member for member in pool if member.get("visual_type") == "card"]
        if len(cards) == 1:
            return cards[0]
        candidates = cards or pool
        totals = [
            member for member in candidates
            if self._PAGE_PRINCIPAL_RE.match(normalize_text(member.get("title") or member["metric"].get("label")))
        ]
        return totals[0] if len(totals) == 1 else None

    def _page_choices(self, question, source_context, page, offered, topic=False):
        """Opciones de una página para la pregunta: primero los indicadores ya
        ofrecidos que están en la página; si no hay, los de la página que
        comparten palabras con la pregunta (o todos).

        Devuelve {"items", "principal", "direct"}: `principal` es el indicador
        principal elegido entre varios (tarjeta única o única «Total …», sin
        palabras que la pregunta no dice) y `direct` dice si se puede responder
        sin contrapreguntar."""
        members = self._page_members(page)
        if not members:
            return {"items": [], "principal": None, "direct": False}
        by_key = {self._logical_key(member["metric"]): member for member in members}
        pool, seen = [], set()
        for item in offered:
            key = self._logical_key(item.get("metric") or {})
            if key in by_key and key not in seen:
                seen.add(key)
                pool.append(by_key[key])
        pool.sort(key=lambda member: (member["rank"], member["order"]))
        words = self._option_words(question, source_context)
        candidates = pool or members
        if words:
            coverage = [len(self._option_coverage(member["metric"], words)) for member in candidates]
            best = max(coverage)
            if best > 0:
                candidates = [member for member, count in zip(candidates, coverage) if count == best]
            elif not pool:
                # La pregunta solo nombra la página: se ofrecen sus indicadores.
                candidates = members
        # «promedio mensual de partos»: la agregación pedida elige entre los
        # indicadores de la página (PROM_PD y no la tarjeta «Total»).
        before = len(candidates)
        candidates = self._page_aggregation_match(question, candidates)
        by_aggregation = len(candidates) < before
        if not topic:
            # Página nombrada: sin palabras que la pregunta no dice
            # («pediátricos» en PROMEDIO_TRIAGES_PEDIATRICOS_2025).
            extras = [self._page_extra_words(member["metric"], question) for member in candidates]
            fewest = min(extras)
            candidates = [member for member, count in zip(candidates, extras) if count == fewest]
        # Variantes por año (PROMEDIO_TRIAGE_20xx, ATEHP2024/2025) = una opción.
        collapsed = self._collapse_year_variants(
            [{"metric": member["metric"], "_member": member} for member in candidates], question,
        )
        candidates = self._collapse_glued_year_members([item["_member"] for item in collapsed], question)
        if len(candidates) == 1:
            # Una sola opción: se responde si no añade palabras que la pregunta
            # no dice; es «la principal» solo si la pregunta solo nombró la página.
            direct = not self._page_extra_words(candidates[0]["metric"], question)
            principal = candidates[0] if (direct and not pool and not by_aggregation) else None
            return {"items": candidates, "principal": principal, "direct": direct}
        principal = self._page_principal(candidates)
        if principal is not None and not self._page_extra_words(principal["metric"], question):
            return {"items": [principal], "principal": principal, "direct": True}
        # «INTERCONSULTAS SIN RESPUESTA» no es la principal de «cuántas
        # interconsultas» aunque sea la única tarjeta: se contrapregunta.
        return {"items": candidates, "principal": None, "direct": False}

    _PAGE_AGGREGATIONS = {
        "promedio": {"promedio", "prom", "media", "avg"},
        "total": {"total", "totales", "conteo", "recuento", "count"},
        "porcentaje": {"porcentaje", "porcentual", "pct", "proporcion", "tasa"},
    }

    def _page_aggregation_match(self, question, members):
        """Miembros cuyo nombre lleva la agregación que pide la pregunta
        («promedio», «total», «porcentaje»); todos si ninguno o no se pide."""
        said = set(normalize_text(question).split())
        asked = [words for words in self._PAGE_AGGREGATIONS.values() if said & words]
        if len(asked) != 1:
            return members
        matching = [
            member for member in members
            if set(normalize_text(f"{member['metric'].get('label')} {member.get('title') or ''}").split()) & asked[0]
        ]
        return matching or members

    def _collapse_glued_year_members(self, members, question):
        """ATEHP2024 / ATEHP2025 / ATEHP2026 (año pegado al nombre) cuentan
        como una opción: la del año pedido o, si no hay, la más reciente."""
        year = self._detect_year_month(question)[0]
        groups, order = {}, []
        for member in members:
            label = normalize_text(member["metric"].get("label")).replace(" ", "")
            match = re.fullmatch(r"(.*?[a-z])((?:19|20)\d{2})", label)
            key = (normalize_text(member["metric"].get("semantic_model")), match.group(1) if match else label)
            if key not in groups:
                order.append(key)
            groups.setdefault(key, []).append((int(match.group(2)) if match else None, member))
        result = []
        for key in order:
            items = groups[key]
            dated = [(value, member) for value, member in items if value is not None]
            if len(dated) < 2:
                result.extend(member for _, member in items)
                continue
            chosen = next((member for value, member in dated if value == year), None)
            if chosen is None:
                chosen = max(dated, key=lambda pair: pair[0])[1]
            result.extend(member for value, member in items if value is None or member is chosen)
            self._note(
                f"variantes por año agrupadas en {chosen['metric'].get('label')}: "
                + ", ".join(str(member["metric"].get("label")) for _, member in dated if member is not chosen)
            )
        return result

    def _page_label(self, page):
        return f"{page.get('page')} ({self._page_report(page)})"

    def _named_page_refinement(self, question, intent_result, plan):
        """Regla de páginas nombradas sobre un plan explorado:
        - «tablero/página de X» nombra una página (o varias homónimas en otros
          modelos): solo se ofrecen indicadores de esas páginas; si queda uno
          (o uno claramente principal por página y una sola página), se
          responde con él.
        - Ninguna métrica coincide pero la pregunta nombra una página por su
          tema («partos de 2025»): se ofrecen sus indicadores (tarjetas
          primero) o se responde con el principal («tomé el indicador
          principal de la página X»).
        - La página no tiene indicadores en los modelos: el plan lo indica
          (`pages_without_metrics`) para decirlo junto a la respuesta documental.
        Devuelve el plan nuevo o None."""
        status = plan.get("status")
        source_context = plan.get("source_context") or {}
        pages = self._named_pages(source_context)
        topic = False
        if not pages:
            if status != "not_found" or source_context.get("board_mentions"):
                return None
            if plan.get("reason") in ("metric_not_in_named_report", "metric_not_in_named_page"):
                return None
            pages = self._topic_pages(question)
            topic = True
        if not pages:
            return None
        if status == "ready":
            metric_key = self._logical_key(plan.get("metric") or {})
            if topic or any(
                metric_key in {self._logical_key(member["metric"]) for member in self._page_members(page)}
                for page in pages
            ):
                return None
        elif status not in ("ambiguous", "not_found"):
            return None
        if status == "not_found" and plan.get("reason") in ("metric_not_in_named_report", "metric_not_in_named_page"):
            return None

        resolution = plan.get("metric_resolution") or {}
        offered = [*(resolution.get("candidates") or []), *(resolution.get("suggestions") or [])]
        if status == "ready":
            offered = [{"metric": plan.get("metric")}, *offered]
        if topic and self._topic_offered_elsewhere(pages, offered):
            return None
        groups = []
        for page in pages:
            choice = self._page_choices(question, source_context, page, offered, topic=topic)
            if choice["items"]:
                groups.append((page, choice["items"], choice["principal"], choice["direct"]))
        names = ", ".join(self._page_label(page) for page in pages)
        if not groups:
            if all(not self._page_members(page) for page in pages):
                self._note(
                    f"la pregunta nombra la página {names}, pero esa página no tiene indicadores "
                    "en los modelos disponibles"
                )
                return {**plan, "pages_without_metrics": [self._page_label(page) for page in pages]}
            return None
        scores = [float(item.get("score") or 0.0) for item in offered if item.get("score") is not None]
        best = max(scores) if scores else 1.0
        items, seen = [], set()
        for page, members, _, _ in groups:
            for member in members:
                key = self._logical_key(member["metric"])
                if key in seen:
                    continue
                seen.add(key)
                items.append({
                    "metric": member["metric"], "score": best, "business_score": best,
                    "matched_name": member.get("title") or member["metric"].get("label"),
                    "page": page.get("page"),
                })
        how = "por su tema" if topic else "con «tablero/página de»"
        # Una página nombrada (o un servicio que se llama como una página:
        # «urgencias») no arrastra la respuesta a una tabla que no trae el
        # periodo pedido («este mes» frente al corte del día anterior del
        # Briefing, TU04): esas opciones se quitan y, si no queda ninguna, la
        # página no decide (sigue el plan general).
        period, start, end = self._requested_period_bounds(question)
        if period is not None:
            missing = [self._metric_misses_period(item["metric"], start, end) for item in items]
            if any(missing):
                dropped = ", ".join(_unique_strings(
                    f"{item['metric'].get('label')} ({table})" for item, table in zip(items, missing) if table
                ))
                lost = [item for item, table in zip(items, missing) if table]
                items = [item for item, table in zip(items, missing) if not table]
                # Lo que queda de la página explica menos de lo que se pide
                # («triages»: solo quedan consultas): la página tampoco decide.
                words = self._option_words(question, source_context)
                best_lost = max((len(self._option_coverage(i["metric"], words)) for i in lost), default=0)
                best_kept = max((len(self._option_coverage(i["metric"], words)) for i in items), default=0)
                if best_lost > best_kept:
                    items = []
                if not items:
                    self._note(
                        f"la pregunta nombra la página {names}, pero sus indicadores no traen «{period.get('label')}» "
                        f"según su documentación ({dropped}): la página no decide el indicador"
                    )
                    return None
                self._note(
                    f"«{period.get('label')}»: de la página {names} se descartan los indicadores cuya tabla no "
                    f"trae ese periodo: {dropped}"
                )
                kept_keys = {self._logical_key(item["metric"]) for item in items}
                groups = [
                    group for group in groups
                    if any(self._logical_key(member["metric"]) in kept_keys for member in group[1])
                ]
        # Páginas homónimas de varios tableros: cada una ya dejó sus opciones
        # que más palabras de la pregunta explican; entre páginas rige lo mismo
        # («interconsultas PENDIENTES»: solo SIN RESPUESTA lo explica, aunque
        # la otra página INTERCONSULTAS tenga más indicadores).
        if len(groups) > 1 and len(items) > 1:
            words = self._option_words(question, source_context)
            coverage = [len(self._option_coverage(item["metric"], words)) for item in items]
            top = max(coverage) if coverage else 0
            if top > 0 and min(coverage) < top:
                dropped = [item for item, count in zip(items, coverage) if count < top]
                items = [item for item, count in zip(items, coverage) if count == top]
                self._note(
                    "entre las páginas homónimas se descartan "
                    + ", ".join(str(item["metric"].get("label")) for item in dropped)
                    + ": explican menos palabras de la pregunta"
                )
                if len(items) == 1:
                    chosen = items[0]
                    return self._forced_plan(
                        question, intent_result, {key: value for key, value in chosen.items() if key != "page"},
                        f"la pregunta nombra la página {chosen.get('page')} {how}; es el único indicador "
                        "de esas páginas que explica todo lo que la pregunta pide",
                        consumed_tokens=self._page_choice_consumed(question, source_context, chosen),
                    )
        narrowed = self._narrow_page_options(question, items)
        if len(narrowed) < len(items) and len({self._logical_key(i["metric"]) for i in narrowed}) == 1:
            chosen = narrowed[0]
            return self._forced_plan(
                question, intent_result, {key: value for key, value in chosen.items() if key != "page"},
                f"la pregunta nombra la página {chosen.get('page')} {how}; es su único indicador que "
                "responde la forma pedida (conteo / desglose)",
                consumed_tokens=self._page_choice_consumed(question, source_context, chosen),
            )
        items = narrowed[: self._SUGGESTION_LIMIT]
        if len(items) == 1 and len(groups) == 1 and groups[0][3]:
            page, _, principal, _ = groups[0]
            label = items[0]["metric"].get("label")
            visible = (
                f"Tomé el indicador principal de la página {page.get('page')} ({self._page_report(page)}): {label}."
                if principal is not None
                else f"Usé el indicador de la página {page.get('page')} ({self._page_report(page)}): {label}."
            )
            # El nombre de la página y las palabras de agregación («promedio
            # mensual») ya explicaron la elección: no son filtros pendientes.
            generic = {
                canonical_token(word) for word in self._GENERIC_MEASURE_WORDS | self._TECHNICAL_NAME_WORDS
                | FILTER_NEUTRAL_WORDS
            }
            consumed = self._page_choice_consumed(question, source_context, items[0], page) | {
                token for token in canonical_tokens(question) if token in generic
            }
            forced = self._forced_plan(
                question, intent_result, {key: value for key, value in items[0].items() if key != "page"},
                f"la pregunta nombra la página {self._page_label(page)} {how}; "
                + ("es su indicador principal" if principal is not None else "es su único indicador que coincide"),
                consumed_tokens=consumed,
            )
            if isinstance(forced, dict) and forced.get("status") == "ready":
                forced["notes"] = [visible, *(forced.get("notes") or [])]
                forced["named_page"] = page.get("page")
            return forced
        models = {normalize_text(page.get("semantic_model")) for page, *_ in groups}
        self._note(
            f"la pregunta nombra la página {names} {how}: se ofrecen solo sus indicadores ("
            + ", ".join(str(item["metric"].get("label")) for item in items) + ")"
        )
        # «CIRUGIAS», «Cirugías» y «CIRUGÍAS» son el mismo nombre.
        names_by_key = {}
        for page, *_ in groups:
            names_by_key.setdefault(normalize_text(page.get("page")), str(page.get("page")).strip())
        page_names = list(names_by_key.values())
        return {
            **plan, "status": "ambiguous", "stage": "metric", "reason": "options_from_named_page",
            "named_page": page_names[0] if len(page_names) == 1 else ", ".join(page_names),
            "named_page_report": self._page_report(groups[0][0]) if len(models) == 1 else None,
            "named_page_models": len(models),
            "metric_resolution": {
                "status": "ambiguous",
                "candidates": [{key: value for key, value in item.items() if key != "page"} for item in items],
            },
        }

    def _page_choice_consumed(self, question, source_context, item, page=None):
        """Palabras que ya explicó elegir este indicador de la página: el nombre
        de la página y las palabras de la pregunta que su nombre explica
        («atendidas» con %ATENDIDO, «pendientes» con SIN RESPUESTA)."""
        name = (page or {}).get("page") or item.get("page")
        words = self._option_words(question, source_context)
        return set(canonical_tokens(name)) | set(self._option_coverage(item.get("metric") or {}, words))

    def _narrow_page_options(self, question, items):
        """Opciones de una página nombrada que responden la FORMA de la
        pregunta: «cantidad de X» descarta porcentajes, promedios y sumas de
        tiempo; «X por especialidad» descarta las que no se desglosan por la
        especialidad. Nunca deja la lista vacía."""
        kept = self._count_question_options(question, items) or list(items)
        # Sin pedir un tiempo, promedio ni porcentaje, un indicador de ese tipo
        # no responde «interconsultas pendientes por especialidad» (TIEMPO EN
        # ESPERA también es «pendiente», pero mide horas).
        said = set(normalize_text(question).split())
        if len(kept) > 1 and not said & (self._DURATION_WORDS | {
            "promedio", "porcentaje", "tasa", "proporcion", "media", "cuanto", "demora", "demoran",
        }):
            plain = [item for item in kept if not self._is_duration_or_ratio(item.get("metric") or {})]
            if plain and len(plain) < len(kept):
                self._note(
                    "opciones de la página depuradas: "
                    + ", ".join(str(i["metric"].get("label")) for i in kept if i not in plain)
                    + " (tiempo, promedio o porcentaje que la pregunta no pide)"
                )
                kept = plain
        tail = self._requested_group_tail(question)
        if tail and len(kept) > 1:
            groupable = [
                item for item in kept
                if self._group_field_in(tail, self._metric_dimensions(item.get("metric") or {})) is not None
            ]
            if groupable and len(groupable) < len(kept):
                self._note(
                    f"opciones de la página depuradas: "
                    + ", ".join(str(i["metric"].get("label")) for i in kept if i not in groupable)
                    + f" no se desglosa(n) por «{tail}»"
                )
                kept = groupable
        return kept

    def _topic_offered_elsewhere(self, pages, offered):
        """¿Alguna opción ya ofrecida nombra el tema de la página pero está
        fuera de ella? («cirugías»: TOTAL CIRUGÍAS de otro informe) Entonces
        el tema no identifica la página y se mantiene la contrapregunta."""
        member_keys = {
            self._logical_key(member["metric"]) for page in pages for member in self._page_members(page)
        }
        topics = [tokens for tokens in (self._page_name_tokens(page.get("page")) for page in pages) if tokens]
        for item in offered:
            metric = item.get("metric") or {}
            if not metric or self._logical_key(metric) in member_keys:
                continue
            vocabulary = self._metric_vocabulary_tokens(metric)
            if any(all(self._explains(token, vocabulary) for token in tokens) for tokens in topics):
                return True
        return False

    def _routed_page(self, source_context):
        """Página fijada por el enrutamiento fuerte («tablero de triage» ->
        TRIAGE de TABLERO DE ATENCIONES), o None."""
        context = source_context or {}
        if not (
            context.get("status") == "resolved" and context.get("routing_strength") == "strong"
            and context.get("board_kind") in ("page", "documentation") and context.get("dashboard")
        ):
            return None
        page = {"semantic_model": context.get("semantic_model"), "page": context.get("dashboard"),
                "report": context.get("report")}
        return None if self._is_report_page(page) else page

    def _page_named_in_report(self, question, source_context):
        """Con el informe nombrado («en el tablero eps»), la página de ese
        modelo cuyo nombre completo (dos o más palabras con contenido) va
        seguido en la pregunta: «cuántos TRIAGES ATENDIDOS hay en el tablero
        eps» -> página TRIAGES ATENDIDOS. La de más palabras; None si no hay
        o si empatan."""
        context = source_context or {}
        if not (
            context.get("status") == "resolved" and context.get("routing_strength") == "strong"
            and context.get("semantic_model")
        ):
            return None
        model = normalize_text(context.get("semantic_model"))
        connectors = {"de", "del", "la", "el", "los", "las", "y", "a", "al", "en", "por"}
        question_seq = [token for token in canonical_tokens(question) if token not in connectors]
        ignored = {canonical_token(word) for word in self._PAGE_IGNORED_NAME_WORDS} | set(GENERIC_PAGE_WORDS)
        best, best_size, tie = None, 0, False
        for (page_model, _), item in self._page_index().items():
            if page_model != model or not item.get("visual"):
                continue
            page_seq = [token for token in canonical_tokens(item["page"]) if token not in connectors]
            content = [token for token in page_seq if token not in ignored and not token.isdigit()]
            if len(content) < 2 or not any(
                question_seq[start:start + len(page_seq)] == page_seq
                for start in range(len(question_seq) - len(page_seq) + 1)
            ):
                continue
            page = {"semantic_model": item["semantic_model"], "page": item["page"], "report": item.get("report")}
            if self._is_report_page(page):
                continue
            if len(content) > best_size:
                best, best_size, tie = page, len(content), False
            elif len(content) == best_size:
                tie = True
        return None if tie else best

    def _named_page_rejection(self, question, source_context, metric_result, page):
        """Página nombrada y el indicador elegido no está en ella: no se
        responde con el de otra página. Se ofrecen los de la página que
        comparten palabras con la pregunta; si no hay, el encontrado fuera."""
        metric = metric_result.get("metric") or (
            (metric_result.get("candidates") or [{}])[0].get("metric") or {}
        )
        words = self._option_words(question, source_context)
        members = self._page_members(page)
        related = [
            member for member in members
            if words and self._option_coverage(member["metric"], words)
        ]
        collapsed = self._collapse_year_variants(
            [{"metric": member["metric"], "score": metric_result.get("score"),
              "business_score": metric_result.get("score"),
              "matched_name": member.get("title") or member["metric"].get("label")} for member in related],
            question,
        )[: self._SUGGESTION_LIMIT]
        elsewhere = None
        if not collapsed and metric.get("metric_id"):
            elsewhere = {"metric": metric, "score": metric_result.get("score"),
                         "business_score": metric_result.get("score"),
                         "matched_name": metric_result.get("matched_name") or metric.get("label")}
        label = self._page_label(page)
        self._note(
            f"la pregunta nombra la página {label}, pero el indicador elegido ({metric.get('label')}) "
            "no aparece en ella: no se responde con el de otra página; "
            + (f"se ofrecen {len(collapsed)} indicadores de esa página" if collapsed
               else "esa página no tiene indicadores parecidos")
        )
        return {
            "status": "not_found", "stage": "metric",
            "reason": "metric_not_in_named_page",
            "named_page": page.get("page"), "named_page_report": self._page_report(page),
            "named_report": f"{self._page_report(page)} (página {page.get('page')})",
            "found_elsewhere": {
                "metric_id": metric.get("metric_id"), "label": metric.get("label"),
                "semantic_model": metric.get("semantic_model"),
                "pages": self._metric_pages(metric),
            } if metric.get("metric_id") else None,
            "question": question, "source_context": source_context,
            "metric_resolution": {
                "status": "not_found", "candidates": [],
                "suggestions": collapsed or ([elsewhere] if elsewhere else []),
            },
        }

    def named_page_without_metrics(self, question):
        """Páginas («ABORTOS (TABLERO DE ATENCIONES INSTITUCIONALES)») que la
        pregunta nombra al pedir un dato y que no tienen indicadores en los
        modelos disponibles; [] si no aplica. Sirve para decirlo junto a la
        respuesta documental."""
        try:
            normalized = normalize_text(canonical_phrases(question)[0])
            if not normalized or self._is_descriptive(normalized):
                return []
            asks_value = (
                any(re.search(r"(?<![a-z0-9])" + term + r"(?![a-z0-9])", normalized) for term in NUMERIC_TERM_PATTERNS)
                or any(re.search(r"(?<![a-z0-9])(?:" + verb + r")(?![a-z0-9])", normalized)
                       for verb in QUERY_VERB_PATTERNS)
                or self._has_period(normalized)
                or bool(re.search(r"(?<![a-z0-9])(?:por|segun)\s+[a-z]", normalized))
            )
            if not asks_value:
                return []
            source_context = self._source_context(question)
            pages = self._named_pages(source_context) or (
                [] if source_context.get("board_mentions") else self._topic_pages(question)
            )
            if not pages or any(self._page_members(page) for page in pages):
                return []
            return [self._page_label(page) for page in pages]
        except Exception:
            return []

    def _similar_name_ambiguity(self, question, source_context, plan):
        """Regla: el indicador elegido tiene un nombre CASI igual a otro
        indicador distinto (otra tabla o expresión, a menudo de otro tablero)
        y la pregunta no los distingue: IMAGENES TOMADAS (BRIEFING) e
        IMAGENES (ATENCIONES) para «cuántas imágenes se tomaron»; PACIENTES
        OBSERVADOS POR MES y OBSERVADOS_2025 para «cuántos pacientes
        observados hay». Ni la unidad («pacientes») ni el verbo en pasiva
        refleja («se tomaron») distinguen; el rival no puede añadir palabras
        que la pregunta no dice (PROM_IMAGENES, «Total de triages no
        atendidos» no compiten). Dentro del mismo modelo solo compite una
        medida auxiliar sobre la tabla del tema (ver abajo). La MISMA medida
        (mismo modelo, tabla y expresión) en varias páginas no es ambigua: se
        responde una vez."""
        best = plan.get("metric") or {}
        if not best.get("metric_id"):
            return None
        strong = (
            source_context.get("status") == "resolved"
            and source_context.get("routing_strength") == "strong"
        )
        if strong and normalize_text(source_context.get("semantic_model")) == normalize_text(best.get("semantic_model")):
            return None
        units = {canonical_token(word) for word in self._OPTION_UNIT_WORDS}
        neutral = units | self._reflexive_verbs(question)
        words = self._option_words(question, source_context)
        core = [word for word in words if word not in neutral]
        if not core or len(self._option_coverage(best, core)) < len(core):
            return None
        matched_name = (plan.get("metric_match") or {}).get("matched_name")
        best_keys = {self._name_key(best.get("label")), self._name_key(matched_name)}
        best_keys.discard(())
        best_tokens = {token for key in best_keys for token in key}
        if not best_tokens:
            return None
        question_tokens = set(canonical_tokens(self._metric_business_question(question, source_context)))

        def said(token):
            return any(_tokens_match_loosely(token, other) for other in question_tokens)

        def table_explains(metric, word):
            return self._explains(word, set(canonical_tokens(metric.get("table"))))

        best_model = normalize_text(best.get("semantic_model"))
        best_table_explains = any(table_explains(best, word) for word in core)
        groups_by = self._rival_group_check(question, best)
        rivals, seen = [], {self._logical_key(best)}
        for metric in self._dedupe_metrics(self.metrics):
            if metric.get("validation_status") != "approved":
                continue
            logical = self._logical_key(metric)
            if logical in seen:
                continue
            key = self._name_key(metric.get("label"))
            if not key or key in best_keys or not set(key) & best_tokens:
                continue
            if not all(said(token) for token in key):
                continue  # el rival nombra algo que la pregunta no dice
            # Polaridad opuesta: «triages no atendidos» no es «Total de triages
            # atendidos» (solo cuenta la negación: «se tomaron» no distingue).
            polar = (
                set(normalize_text(best.get("label")).split()) ^ set(normalize_text(metric.get("label")).split())
            ) & _POLARITY_WORDS
            if polar and value_contradiction(
                self._metric_business_question(question, source_context),
                metric.get("label"), [best.get("label"), metric.get("label")],
            ):
                continue
            if len(self._option_coverage(metric, core)) < len(core):
                continue
            if not groups_by(metric):
                continue
            # En el MISMO modelo, las tarjetas de nombre parecido suelen ser
            # variantes del propio tablero (CITAS ASIGNADAS / ASIGNADAS): no se
            # pregunta. Solo compite una medida auxiliar (sin visual) sobre la
            # tabla del tema (OBSERVADOS_2025 sobre OBSERVADOS) cuando la
            # elegida se calcula sobre otra tabla que no lo nombra.
            if normalize_text(metric.get("semantic_model")) == best_model and (
                metric.get("appearances") or best_table_explains
                or not all(table_explains(metric, word) for word in core)
            ):
                continue
            seen.add(logical)
            rivals.append(metric)
        if not rivals:
            return None
        rivals.sort(key=lambda metric: 0 if metric.get("appearances") else 1)
        score = (plan.get("metric_match") or {}).get("score")
        items = [
            {"metric": metric, "score": score, "business_score": score,
             "matched_name": matched_name if metric is best else metric.get("label")}
            for metric in [best, *rivals]
        ]
        items = self._collapse_year_variants(items, question)[: self._SUGGESTION_LIMIT]
        if len(items) < 2:
            return None
        # Igual que con los homónimos: solo fuentes que responden y que el
        # usuario ve en un tablero.
        with_report = [item for item in items if self._model_has_report(item["metric"].get("semantic_model"))]
        if with_report and len(with_report) < len(items):
            self._note(
                "de modelos sin ningún informe (el usuario no los ve): "
                + ", ".join(f"{i['metric'].get('label')} ({i['metric'].get('semantic_model')})"
                            for i in items if i not in with_report)
                + "; no se ofrecen"
            )
            if len(with_report) == 1:
                if with_report[0]["metric"] is best:
                    return None
                return self._forced_plan(
                    question, None, with_report[0],
                    "es la única de las fuentes de nombre casi igual de un tablero con informe",
                )
            items = with_report
        narrowed = self._homonyms_that_answer(
            question, {"matched_name": best.get("label")}, items, current_state=False,
        )
        if narrowed is not None:
            if len(narrowed) <= 1:
                if not narrowed or narrowed[0]["metric"] is best:
                    return None
                return self._forced_plan(
                    question, None, narrowed[0],
                    "es la única de las fuentes de nombre casi igual que responde la pregunta "
                    "y que muestra un tablero",
                )
            items = narrowed
        self._note(
            f"«{best.get('label')}» tiene un nombre casi igual a otros indicadores distintos ("
            + ", ".join(f"{i['metric'].get('label')} de {i['metric'].get('semantic_model')}" for i in items[1:])
            + ") y la pregunta no indica cuál: se contrapregunta"
        )
        return {
            "status": "ambiguous", "stage": "metric",
            "reason": "similar_name_in_several_boards",
            "question": question, "source_context": source_context,
            "metric_resolution": {"status": "ambiguous", "candidates": items},
        }

    def _forced_plan(self, question, intent_result, item, why, consumed_tokens=(),
                     visible_note=None, group_sibling=False):
        """Plan con un indicador ya decidido (única opción razonable).
        `consumed_tokens`: palabras de la pregunta que ya explicó la elección.
        `visible_note`: nota que se muestra con la respuesta. `group_sibling`:
        indicador elegido porque el pedido no se podía desglosar (no se repite)."""
        metric = item["metric"]
        interpretation = f"{metric.get('label')}: {why}"
        self._note(interpretation)
        forced = {
            "status": "resolved", "metric": metric,
            "matched_name": item.get("matched_name") or metric.get("label"),
            "score": item.get("score"),
            "candidates": [{key: value for key, value in item.items() if not key.startswith("_")}],
            "interpretation": interpretation,
            "final": True,
            "consumed_tokens": set(consumed_tokens or ()),
            "visible_note": visible_note,
            "group_sibling": bool(group_sibling),
        }
        return self._build_plan(question, intent_result, forced_resolution=forced)
