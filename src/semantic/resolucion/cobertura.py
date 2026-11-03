"""Etapa «elegir indicador» (2): cobertura de la pregunta y del periodo, nombres débiles.

Cobertura del periodo de la tabla del indicador (r2 AI04/TU04, r5 «próximos días», r6 holgura de un
día), gemelos de página (r3 TU08), nombre funcional de la página y palabras implícitas (r5),
alternative_metrics, desempates (_break_metric_tie, r3 TU10), nombres débiles y variantes por año,
vocabulario del indicador (metric_covers_question). Mixin de QueryPlanBuilder, métodos movidos sin
cambios.
"""
import json
import re

from datetime import timedelta
from src.semantic.period_parser import as_date
from src.semantic.resolucion.texto import (
    _is_question_form_word,
    _is_request_word,
    _phrase_score,
    _token_similarity,
    _tokens_match_loosely,
    _unique_strings,
    _VERB_ENDINGS,
    canonical_token,
    canonical_tokens,
    COMMON_VERB_WORDS,
    FILTER_NEUTRAL_WORDS,
    GENERIC_QUERY_WORDS,
    MONTHS,
    normalize_text,
    STOPWORDS,
)


class CoberturaMixin:


    # ---- ventana de datos de la tabla frente al periodo pedido ----

    def _metric_coverage_tables(self, metric):
        """Tablas de hechos del indicador (las que nombra la expresión de una
        medida o la tabla de la agregación)."""
        model = metric.get("semantic_model")
        if metric.get("measure"):
            used = self._expression_tables(model, metric)
            if used:
                return sorted(used)
        table = self._metric_fact_table(metric)
        return [table] if table else []

    def _metric_misses_period(self, metric, start, end, pages=False):
        """Tabla del indicador cuya ventana documentada (diccionario de
        variables: «del día anterior», «de los últimos 10 días», «desde el
        01/01/2023») no trae el periodo [start, end); None si lo trae o si la
        documentación no dice nada."""
        from src.semantic.table_coverage import coverage_window, covers

        model = normalize_text(metric.get("semantic_model"))
        today = self._today()
        documented = False
        for table in self._metric_coverage_tables(metric):
            text = self._table_coverage_text(model, table)
            if not text:
                continue
            window = coverage_window(text, today)
            documented = documented or window is not None
            if not covers(window, start, end, today):
                return table
        if documented or not pages:
            return None
        if end is not None and end > today:
            # «este mes», «en lo que va del año»: la foto del día es la cifra
            # actual de ese periodo (como `_current_state_period`).
            return None
        # Sin ventana documentada en sus tablas: si TODAS las páginas donde se
        # ve el indicador son del bloque «Día» de la documentación del tablero
        # (EGRESOS del BRIEFING: INICIO e INGRESOS Y EGRESOS, «del último
        # día»), el indicador es la foto del día y no responde «mes pasado».
        blocks = self._page_block_index()
        pages = [
            normalize_text(appearance.get("page_display_name") or appearance.get("page_name"))
            for appearance in metric.get("appearances") or []
        ]
        pages = [page for page in pages if page]
        if pages and all(blocks.get((model, page)) == "dia" for page in pages):
            window = (today - timedelta(days=1), None)
            if not covers(window, start, end, today):
                return "páginas del día: " + ", ".join(_unique_strings(
                    appearance.get("page_display_name") or appearance.get("page_name")
                    for appearance in metric.get("appearances") or []
                ))
        return None

    def _page_twins(self, first, second):
        """¿Son el mismo indicador en dos visuales de la misma página? Mismo
        modelo, misma tabla de hechos, nombre equivalente (sin tildes, «total»
        ni años) y al menos una página en común: «IMÁGENES TOMADAS» de la
        tarjeta (SUM(SOLICITUDES_CANT)) y del gráfico (DISTINCTCOUNT(
        OID_SOLICITUD)) de la página IMAGENES. Con páginas distintas no lo son
        (CONSULTAS ASIGNADAS de INICIO y de ASIGNADAS cuentan otras cosas)."""
        if normalize_text(first.get("semantic_model")) != normalize_text(second.get("semantic_model")):
            return False
        if normalize_text(self._metric_fact_table(first)) != normalize_text(self._metric_fact_table(second)):
            return False
        names_a = {self._name_key(first.get("label")), self._name_key(first.get("measure"))} - {()}
        names_b = {self._name_key(second.get("label")), self._name_key(second.get("measure"))} - {()}
        if not names_a & names_b:
            return False
        def pages(metric):
            return {
                normalize_text(appearance.get("page_display_name") or appearance.get("page_name"))
                for appearance in metric.get("appearances") or []
            } - {""}

        return bool(pages(first) & pages(second))

    def _collapse_page_twins(self, items):
        """Deja una sola vez cada indicador que la misma página muestra en dos
        visuales (`_page_twins`); se conserva el que se ve en una tarjeta."""
        def card_first(item):
            return 0 if any(
                "card" in str(appearance.get("visual_type") or "").lower()
                for appearance in item["metric"].get("appearances") or []
            ) else 1

        kept = []
        for item in items:
            twin = next((other for other in kept if self._page_twins(item["metric"], other["metric"])), None)
            if twin is None:
                kept.append(item)
                continue
            if card_first(item) < card_first(twin):
                kept[kept.index(twin)] = item
                twin, item = item, twin
            self._note(
                f"{item['metric'].get('label')} y {twin['metric'].get('label')} son el mismo indicador en "
                "dos visuales de la misma página (misma tabla): se ofrece una sola vez"
            )
        return kept

    def _functional_name_index(self):
        """{(modelo, página): nombre funcional} de la documentación por página
        («LISTADO» -> «Listado de pacientes con pendientes activos») y
        {(modelo, ""): nombre funcional del tablero} (página GENERAL)."""
        cached = self.__dict__.get("_functional_name_cache")
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
                if not isinstance(dashboard, dict) or dashboard.get("is_dictionary"):
                    continue
                meta = dashboard.get("md_metadata")
                if not isinstance(meta, dict) or not meta.get("nombre_funcional"):
                    continue
                page = normalize_text(meta.get("pagina") or dashboard.get("name"))
                key = "" if normalize_text(meta.get("bloque")) == "general" else page
                if model:
                    index.setdefault((model, key), str(meta["nombre_funcional"]))
        self._functional_name_cache = index
        return index

    # Terminaciones verbales que no son de sustantivos ni valores
    # («llegaron», «usaban», «lavando», «atendiendo»).
    _VERB_ENDINGS = ("aron", "ieron", "aban", "ando", "iendo")

    def _looks_like_verb(self, word):
        """Verbo conjugado que no puede ser un valor de dimensión: pretérito,
        imperfecto o gerundio; o presente plural («suben», «llegan») que no
        aparece en ningún nombre, columna ni valor del catálogo."""
        word = normalize_text(word)
        if _is_question_form_word(word):
            return True
        if len(word) >= 6 and word.endswith(self._VERB_ENDINGS):
            return True
        if len(word) >= 5 and word.endswith(("an", "en")):
            token = canonical_token(word)
            return not any(_token_similarity(token, other) >= 0.88 for other in self._catalog_vocabulary())
        return False

    def question_coverage(self, question, metric):
        """(palabras con contenido de la pregunta, las que explica el
        indicador por su nombre, tabla, páginas, tablero o nombre funcional
        documentado). Sirve para descartar opciones dominadas."""
        words = [
            canonical_token(word) for word in self._question_content_words(question)
            if not self._looks_like_verb(word)
        ]
        vocabulary = set(self._metric_vocabulary_tokens(metric))
        vocabulary.update(
            token for report in self._metric_reports(metric) for token in canonical_tokens(report) if len(token) >= 3
        )
        model = normalize_text(metric.get("semantic_model"))
        functional = self._functional_name_index()
        for key in [*(normalize_text(page) for page in self._metric_pages(metric)), ""]:
            text = functional.get((model, key))
            if text:
                vocabulary.update(token for token in canonical_tokens(text) if len(token) >= 3)
        vocabulary.update(
            canonical_token(token.lstrip("%")) for token in list(vocabulary) if token.startswith("%") and len(token) > 3
        )
        return set(words), {word for word in words if self._explains(word, vocabulary)}

    def implied_words(self, metric, words):
        """Palabras de `words` que no son filtros del indicador porque son
        forma de la pregunta (verbos) o porque ya las dice el propio
        indicador: su nombre, tabla, páginas, títulos de visual o el nombre
        funcional (documentado) de su página o
        tablero («pendientes» en LISTADO = «pacientes con pendientes
        activos»). Devuelve (implícitas, restantes)."""
        model = normalize_text(metric.get("semantic_model"))
        vocabulary = set(self._metric_vocabulary_tokens(metric))
        # Lo que el diccionario dice que MIDE la propia medida («%DEFUNCIONES:
        # Mortalidad: defunciones sobre egresos…»), no lo que dice de su tabla.
        index = self._dictionary_index()
        for name in (metric.get("measure"), metric.get("label")):
            gist = index.get((model, "m:" + normalize_text(name))) if name else None
            if gist:
                head = re.split(r"[.;(]", gist, maxsplit=1)[0]
                vocabulary.update(token for token in canonical_tokens(head) if len(token) >= 4)
        functional = self._functional_name_index()
        # Páginas del indicador y las demás páginas que usan su tabla (la
        # página CITAS de «citas canceladas por causas institucionales»).
        pages = [normalize_text(page) for page in self._metric_pages(metric)]
        for key in [*dict.fromkeys(pages), ""]:
            text = functional.get((model, key))
            if text:
                vocabulary.update(token for token in canonical_tokens(text) if len(token) >= 3)
        # Las demás páginas de su tabla solo explican formas verbales que no
        # son palabras del catálogo («canceló» ~ «citas canceladas por causas
        # institucionales»); un sustantivo con indicador propio («exámenes»)
        # sigue sin explicarse.
        table_vocabulary = set()
        try:
            for page in self._table_pages(metric.get("semantic_model"), self._metric_fact_table(metric)):
                text = functional.get((model, normalize_text(page)))
                if text:
                    table_vocabulary.update(token for token in canonical_tokens(text) if len(token) >= 4)
        except Exception:
            pass
        catalog_vocabulary = self._catalog_vocabulary()
        action_vocabulary = vocabulary | {
            token for report in self._metric_reports(metric) for token in canonical_tokens(report) if len(token) >= 3
        }

        def participle_of_vocabulary(word):
            # «lavados» (lav-ar) con LAVANDERÍA; «cancelados» con CANCELADAS:
            # el participio de la acción que el indicador ya nombra.
            match = re.fullmatch(r"([a-z]{3,})(?:ad|id)(?:o|a|os|as)", word)
            return bool(match) and any(
                other.startswith(match.group(1)) and len(other) >= len(match.group(1)) + 3
                for other in action_vocabulary
            )

        implied, remaining = [], []
        for word in normalize_text(" ".join(words) if isinstance(words, (list, tuple)) else words).split():
            token = canonical_token(word)
            if (
                self._looks_like_verb(word) or (len(token) >= 3 and self._explains(token, vocabulary))
                or participle_of_vocabulary(word)
                or (len(token) >= 5 and token not in catalog_vocabulary
                    and self._explains(token, table_vocabulary))
            ):
                implied.append(word)
            else:
                remaining.append(word)
        return implied, remaining

    def _page_block_index(self):
        """{(modelo, página): bloque} de la documentación por página del
        tablero (data/semantic_documents, metadatos «bloque: Día|Histórico»),
        normalizados."""
        cached = self.__dict__.get("_page_block_cache")
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
                if not isinstance(dashboard, dict) or dashboard.get("is_dictionary"):
                    continue
                meta = dashboard.get("md_metadata")
                if not isinstance(meta, dict) or not meta.get("bloque"):
                    continue
                page = normalize_text(meta.get("pagina") or dashboard.get("name"))
                if model and page:
                    index.setdefault((model, page), normalize_text(meta["bloque"]))
        self._page_block_cache = index
        return index

    def _requested_period_bounds(self, business_question):
        try:
            period = self._analyze_periods(business_question).get("period")
        except Exception:
            period = None
        start = as_date((period or {}).get("start"))
        end = as_date((period or {}).get("end"))
        return (period, start, end) if start and end else (None, None, None)

    def _items_covering_period(self, business_question, items):
        """Los ítems cuya tabla trae el periodo pedido; None si la pregunta no
        tiene periodo con fechas o si ninguno lo trae (no se descarta nada)."""
        period, start, end = self._requested_period_bounds(business_question)
        if period is None:
            return None
        # Aquí también cuenta el bloque «Día» de sus páginas (señal más débil
        # que la ventana de la tabla): solo decide entre fuentes que compiten.
        missing = [self._metric_misses_period(item["metric"], start, end, pages=True) for item in items]
        kept = [item for item, table in zip(items, missing) if table is None]
        if not kept or len(kept) == len(items):
            return None
        self._note(
            f"«{period.get('label')}»: se descartan opciones cuya tabla no trae ese periodo según su "
            "documentación: " + ", ".join(
                f"{item['metric'].get('label')} ({table})" for item, table in zip(items, missing) if table
            )
        )
        return kept

    def _drop_uncovered_period(self, business_question, candidates):
        """Quita los candidatos cuya tabla no trae el periodo pedido, solo si
        otro candidato con nombre suficiente sí lo trae (si ninguno lo trae,
        no cambia nada y el plan lo explica)."""
        period, start, end = self._requested_period_bounds(business_question)
        if period is None:
            return candidates
        missing = [self._metric_misses_period(item["metric"], start, end) for item in candidates]
        if not any(missing):
            return candidates
        if not any(
            table is None and item["business_score"] >= self.min_metric_score
            for item, table in zip(candidates, missing)
        ):
            return candidates
        dropped = [
            f"{item['metric'].get('label')} ({table})" for item, table in zip(candidates, missing) if table
        ]
        self._note(
            f"«{period.get('label')}»: se descartan indicadores cuya tabla no trae ese periodo según su "
            f"documentación: {', '.join(dict.fromkeys(dropped[:6]))}"
        )
        return [item for item, table in zip(candidates, missing) if table is None]

    # ---------------- medida auxiliar frente a indicador visible ----------------
    def _visible_over_auxiliary(self, business_question, best, groups):
        """El mejor candidato es una medida auxiliar (no aparece en ningún
        visual: CAMAS_DISPONIBLES de Atenciones, capacidad × días) y otro que sí
        se ve en un tablero, a poca distancia, explica con su nombre y su tabla
        las mismas palabras de la pregunta (CAMAS de la tabla CAMAS
        DISPONIBLES): se prefiere el visible. Devuelve los visibles que
        compiten (uno = se elige; varios = se contrapregunta entre ellos)."""
        if best["metric"].get("appearances"):
            return []
        content = [canonical_token(word) for word in self._question_content_words(business_question)]
        best_vocabulary = self._metric_vocabulary_tokens(best["metric"], with_pages=False)
        needed = [token for token in content if self._explains(token, best_vocabulary)]
        if not needed:
            return []
        rivals = []
        for item in groups:
            if item is best or not item["metric"].get("appearances"):
                continue
            if best["score"] - item["score"] >= 3 * self.ambiguity_margin:
                continue
            if item["business_score"] < self.min_metric_score:
                continue
            vocabulary = self._metric_vocabulary_tokens(item["metric"], with_pages=False)
            if all(self._explains(token, vocabulary) for token in needed):
                rivals.append(item)
        if rivals:
            self._note(
                f"{best['metric'].get('label')} ({best['metric'].get('semantic_model')}) no aparece en ningún "
                "tablero; " + ", ".join(
                    f"{item['metric'].get('label')} ({item['metric'].get('semantic_model')})" for item in rivals
                ) + " sí y su nombre y su tabla explican lo mismo de la pregunta: se prefiere"
                + ("" if len(rivals) == 1 else "n")
            )
        return rivals

    # ---------------- desempate entre indicadores empatados ----------------
    def _is_own_name(self, metric, name):
        """¿`name` es el nombre propio de la medida (etiqueta, medida o la
        referencia «TABLA.medida») y no un título de visual u otro alias?"""
        own = {normalize_text(metric.get("label")), normalize_text(metric.get("measure"))}
        own.discard("")
        if normalize_text(name) in own:
            return True
        text = str(name or "")
        return "." in text and normalize_text(text.rsplit(".", 1)[1]) in own

    def _visual_title_owners(self):
        """{título de visual normalizado: claves lógicas de las medidas que lo muestran}."""
        cached = self.__dict__.get("_visual_title_owners_cache")
        if cached is None:
            cached = {}
            for metric in self._dedupe_metrics(self.metrics):
                if metric.get("validation_status") != "approved":
                    continue
                for appearance in metric.get("appearances") or []:
                    title = normalize_text(appearance.get("visual_title"))
                    if title:
                        cached.setdefault(title, set()).add(self._logical_key(metric))
            self._visual_title_owners_cache = cached
        return cached

    def _is_shared_alias(self, metric, name):
        """Alias que no es exclusivo de la medida: es el nombre de otra medida
        («%OCUPACIÓN» de CamasFiltradas = %OCUPACION) o el título de un visual
        que muestra varias medidas."""
        norm = normalize_text(name)
        if not norm:
            return False
        self._token_weight_index()  # arma self._known_labels
        own = {normalize_text(metric.get("label")), normalize_text(metric.get("measure"))}
        if norm in (self.__dict__.get("_known_labels") or set()) - own:
            return True
        owners = self._visual_title_owners().get(norm) or set()
        return bool(owners - {self._logical_key(metric)})

    def _break_metric_tie(self, business_question, tied):
        """Candidatos empatados que siguen compitiendo tras tres reglas
        genéricas (cada una solo descarta si queda al menos uno):
        1. Nombre propio frente a alias compartido: si uno coincide por el
           nombre de su medida y otro solo por un título de visual/alias que
           comparten varias medidas, se prefiere el nombre propio
           (%OCUPACION frente a CamasFiltradas por el visual «%OCUPACIÓN»).
        2. Palabra que es parte de un valor de filtro: si el nombre de un
           candidato solo coincide con palabras que forman un valor categórico
           documentado de su tabla («hospitalización general» =
           SERVICIO_SOLICITADO), eso es un filtro, no el indicador
           (HOSPITALIZACIÓN de Demanda Insatisfecha).
        3. Sustantivo contado: en «cuántas/cuántos X ...» se prefieren los
           indicadores que cuentan X (nombre, o COUNT/DISTINCTCOUNT sobre una
           tabla o columna que lo nombra)."""
        kept = list(tied)

        own = [item for item in kept if item.get("_own_name")]
        shared = [item for item in kept if not item.get("_own_name") and item.get("_shared_alias")]
        if own and shared:
            top_own = max(float(item.get("business_score") or 0.0) for item in own)
            # Solo si el alias no explica nada más de la pregunta (su tabla o
            # página no nombra otra palabra: «consultas PRIORITARIAS» sigue
            # ofreciendo la medida de la tabla CONSULTAS_PRIORITARIAS).
            content = [canonical_token(word) for word in self._question_content_words(business_question)]

            def explained(item):
                vocabulary = self._metric_vocabulary_tokens(item["metric"])
                return {token for token in content if self._explains(token, vocabulary)}

            own_explained = set().union(*(explained(item) for item in own))
            dropped = [
                item for item in shared
                if float(item.get("business_score") or 0.0) <= top_own + 1e-9
                and explained(item) <= own_explained
            ]
            if dropped:
                kept = [item for item in kept if item not in dropped]
                self._note(
                    ", ".join(
                        f"{item['metric'].get('label')} coincidió solo por «{item.get('matched_name')}»"
                        for item in dropped
                    )
                    + ", un alias que comparte con otras medidas; "
                    + ", ".join(str(item["metric"].get("label")) for item in own)
                    + " coincide por su propio nombre: se prefiere"
                    + (" sin contrapreguntar" if len(kept) == 1 else "")
                )

        if len(kept) > 1:
            in_value = []
            for item in kept:
                value = self._name_inside_value_phrase(business_question, item)
                if value:
                    in_value.append((item, value))
            if in_value and len(in_value) < len(kept):
                dropped = [item for item, _ in in_value]
                kept = [item for item in kept if item not in dropped]
                self._note(
                    "; ".join(
                        f"«{item.get('matched_name')}» de {item['metric'].get('label')} "
                        f"({item['metric'].get('semantic_model')}) es parte del valor «{value}» de su tabla "
                        f"{item['metric'].get('table')}: es un filtro, no el indicador"
                        for item, value in in_value
                    )
                )

        if len(kept) > 1:
            head = self._counted_noun(business_question)
            if head:
                counting = [item for item in kept if self._metric_counts(item["metric"], head)]
                if counting and len(counting) < len(kept):
                    dropped = [item for item in kept if item not in counting]
                    kept = counting
                    self._note(
                        f"la pregunta cuenta «{head}»: "
                        + ", ".join(str(item["metric"].get("label")) for item in counting)
                        + " lo cuenta; "
                        + ", ".join(str(item["metric"].get("label")) for item in dropped)
                        + " no"
                    )

        single_value = not (
            self._requested_group_tail(business_question)
            or self._mentions_ranking(normalize_text(business_question))
        )
        if len(kept) > 1 and single_value:
            # 4. Tarjeta frente a gráfico del mismo tablero: el valor único que
            # el usuario ve es el de la tarjeta (VALOR ESTIMADO = SUM(FACTURADO)
            # sin el filtro de área del gráfico «VALOR ESTIMADO POR SERVICIO»).
            dropped = []
            for model in {normalize_text(item["metric"].get("semantic_model")) for item in kept}:
                same = [item for item in kept if normalize_text(item["metric"].get("semantic_model")) == model]
                cards = [item for item in same if self._shown_in_card(item["metric"])]
                if cards and len(cards) < len(same):
                    dropped.extend(item for item in same if item not in cards)
            if dropped and len(dropped) < len(kept):
                kept = [item for item in kept if item not in dropped]
                self._note(
                    ", ".join(str(item["metric"].get("label")) for item in kept)
                    + " se muestra(n) en una tarjeta; "
                    + ", ".join(str(item["metric"].get("label")) for item in dropped)
                    + " solo en gráficos o tablas del mismo tablero: se prefiere la tarjeta"
                )
        return kept

    # «cuántas camas», «cuántos de los pacientes»: el sustantivo que se cuenta.
    _COUNTED_NOUN_RE = re.compile(
        r"(?<![a-z0-9])cuant[oa]s\s+(?:(?:de|del)\s+)?(?:(?:los|las|el|la)\s+)?([a-z0-9]+)"
    )
    _COUNT_FUNCTION_RE = re.compile(
        r"\b(?:COUNT|COUNTA|COUNTX|COUNTAX|COUNTROWS|COUNTBLANK|DISTINCTCOUNT|DISTINCTCOUNTNOBLANK)\s*\(",
        re.IGNORECASE,
    )

    def _counted_noun(self, business_question):
        """Sustantivo contado en «cuántos/cuántas X» (canónico) o None. Las
        unidades genéricas («pacientes», «casos», «registros») no distinguen
        indicadores y se ignoran."""
        match = self._COUNTED_NOUN_RE.search(normalize_text(business_question))
        if not match:
            return None
        token = canonical_token(match.group(1))
        content_free, _ = self._weak_token_sets()
        units = {canonical_token(word) for word in self._OPTION_UNIT_WORDS}
        if len(token) < 4 or token.isdigit() or token in content_free or token in units:
            return None
        return token

    def _metric_counts(self, metric, head):
        """¿El indicador cuenta `head`? Su etiqueta/medida lo nombra o su
        expresión es un conteo (COUNT, DISTINCTCOUNT, COUNTROWS...) sobre una
        tabla o columna que lo nombra (COUNT('CAMAS DISPONIBLES'[HCACODIGO]))."""
        names = set(canonical_tokens(metric.get("label"))) | set(canonical_tokens(metric.get("measure")))
        if self._explains(head, names):
            return True
        expression = " ".join(
            str(value) for value in (
                self._measure_expression(metric.get("semantic_model"), metric), metric.get("model_expression"),
            ) if value
        )
        if not self._COUNT_FUNCTION_RE.search(expression):
            return False
        referenced = set()
        for table, column in re.findall(r"'([^']+)'\s*\[([^\]]+)\]", expression):
            referenced.update(canonical_tokens(table))
            referenced.update(canonical_tokens(column))
        for table, column in re.findall(r"(?<![\w'\]])([A-Za-z_][\w]*)\s*\[([^\]]+)\]", expression):
            referenced.update(canonical_tokens(table))
            referenced.update(canonical_tokens(column))
        for table in re.findall(r"COUNTROWS\s*\(\s*'?([^'(),\[\]]+?)'?\s*\)", expression, re.IGNORECASE):
            referenced.update(canonical_tokens(table))
        if self._explains(head, {token for token in referenced if len(token) >= 3}):
            return True
        # El diccionario de variables dice qué es cada fila de la tabla contada
        # («Etapa actual de cada CUENTA» en ENPROCESO_FACTURACION): un conteo
        # sobre ella cuenta cuentas aunque el nombre diga PROCESO_FACTURACION.
        return self._explains(head, self._dictionary_tokens(metric))

    # =====================================================================
    # RESOLUCIÓN DEL INDICADOR: nombres débiles, mismo nombre en varios
    # tableros, variantes por año, tablero nombrado y calificativos.
    # =====================================================================
    # Palabras que marcan una variante «por año» de una medida
    # (TRIAGES_2025, Cirugias_Año_Actual, CIRUGIAS_AÑO_ANTERIOR).
    _YEAR_MARKER_WORDS = {"ano", "anio", "actual", "anterior", "pasado"}
    # Palabras técnicas o de agregación que no dan contenido a un nombre.
    _TECHNICAL_NAME_WORDS = {
        "conteo", "recuento", "suma", "sum", "min", "max", "avg", "count",
        "promedio", "prom", "media", "dinamico", "visible", "medida", "kpi",
    }

    def _weak_token_sets(self):
        cached = self.__dict__.get("_weak_tokens_cache")
        if cached is None:
            content_free = {
                canonical_token(word)
                for word in (
                    STOPWORDS | GENERIC_QUERY_WORDS | FILTER_NEUTRAL_WORDS | COMMON_VERB_WORDS
                    | set(MONTHS) | self._YEAR_MARKER_WORDS
                    | {"trimestre", "semestre", "semana", "dia", "periodo", "corte", "fecha"}
                )
            }
            generic = content_free | {
                canonical_token(word)
                for word in self._GENERIC_MEASURE_WORDS | self._TECHNICAL_NAME_WORDS
            }
            cached = (content_free, generic)
            self._weak_tokens_cache = cached
        return cached

    def _weak_name_kind(self, name):
        """«content_free» si el nombre es solo un año/periodo, un verbo o
        relleno («2024», «Registrado»); «generic» si además solo tiene palabras
        de agregación («Promedio mensual», «Total»); None si nombra algo."""
        content_free, generic = self._weak_token_sets()
        tokens = [token for token in canonical_tokens(name) if token != "%"]
        if all(token.isdigit() or token in content_free for token in tokens):
            return "content_free"
        if all(token.isdigit() or token in generic for token in tokens):
            return "generic"
        return None

    def _matches_only_period(self, business_question, name):
        """¿Las palabras de la pregunta que el nombre explica son todas de la
        frase del periodo («mes pasado»)? Entonces el nombre no nombra lo que
        se pregunta, solo repite el periodo."""
        period_words = self._period_words(business_question)
        if not period_words:
            return False
        ignored = {canonical_token(word) for word in STOPWORDS | GENERIC_QUERY_WORDS}
        name_tokens = [token for token in canonical_tokens(name) if token not in ignored]
        matched = {
            token for token in canonical_tokens(business_question)
            if token not in ignored and not _is_request_word(token)
            and any(_token_similarity(token, other) >= 0.82 for other in name_tokens)
        }
        return bool(matched) and matched <= set(period_words)

    def _discard_weak_name(self, metric, business_question, best_name, best_name_score,
                           name_priority, in_named_model=False):
        """Regla: una medida cuyo nombre coincidente es solo un número/año o
        palabras genéricas no se elige por coincidir con el periodo o con
        relleno de la pregunta. Si su etiqueta sí nombra algo, se usa la
        etiqueta; si no, el indicador no compite (puntaje 0). Un nombre solo
        genérico se admite dentro del tablero nombrado en la pregunta."""
        if best_name_score <= 0:
            return best_name, best_name_score, name_priority
        kind = self._weak_name_kind(best_name)
        if kind is None and self._matches_only_period(business_question, best_name):
            # «Promedio Mensual Año Pasado» para «kilos de ropa del mes
            # pasado»: solo coincide con la frase del periodo de la pregunta.
            kind = "content_free"
        if kind is None or (kind == "generic" and in_named_model):
            return best_name, best_name_score, name_priority
        label = str(metric.get("label") or "")
        if label and normalize_text(label) != normalize_text(best_name):
            label_kind = self._weak_name_kind(label)
            if label_kind is None and self._matches_only_period(business_question, label):
                label_kind = "content_free"
            if label_kind is None or (label_kind == "generic" and in_named_model):
                score = _phrase_score(business_question, label, self._token_weight_index())
                if score > 0:
                    return label, score, 0.0
        self._note(
            f"se descartó {label or best_name} ({metric.get('semantic_model')}): coincidió solo con "
            f"«{best_name}», un nombre sin contenido propio "
            + ("(año/periodo o relleno)" if kind == "content_free" else "(solo palabras genéricas)")
        )
        return best_name, 0.0, 0.0

    def _name_key(self, name):
        """Clave para «el mismo indicador con otro nombre técnico»: palabras
        canónicas sin conectores, «total», años ni marcas de año
        (TRIAGES_2025, TOTAL_TRIAGES y Triages -> ("triage",))."""
        ignored = self.__dict__.get("_name_key_ignored")
        if ignored is None:
            ignored = {
                canonical_token(word)
                for word in STOPWORDS | GENERIC_QUERY_WORDS | FILTER_NEUTRAL_WORDS | self._YEAR_MARKER_WORDS
            }
            self._name_key_ignored = ignored
        return tuple(sorted({
            token for token in canonical_tokens(name)
            if token not in ignored and not token.isdigit() and token != "%"
        }))

    def _has_year_marker(self, name):
        return any(
            re.fullmatch(r"(?:19|20)\d{2}", token) or token in self._YEAR_MARKER_WORDS
            for token in canonical_tokens(name)
        )

    def _collapse_year_variants(self, items, question):
        """Medidas atadas a un año (TRIAGES_2024/2025/2026, IMG_20xx,
        Cirugias_Año_Actual) del mismo modelo cuentan como UNA opción: se
        conservan las que el usuario ve en un tablero; de las demás (sin
        visual), una sola: la medida base (sin año, el año se filtra aparte) o,
        si no hay base, la del año pedido / el año actual / el más reciente."""
        if not items:
            return []
        year = self._detect_year_month(question)[0]
        groups = {}
        for index, item in enumerate(items):
            metric = item.get("metric") or {}
            key = (normalize_text(metric.get("semantic_model")), self._name_key(metric.get("label")))
            groups.setdefault(key, []).append(index)

        keep = set()
        for key, indexes in groups.items():
            visible = [i for i in indexes if (items[i].get("metric") or {}).get("appearances")]
            hidden = [i for i in indexes if i not in visible]
            keep.update(visible)
            if visible or not hidden or not key[1]:
                if not key[1]:
                    keep.update(hidden)
                continue
            if len(hidden) == 1:
                keep.update(hidden)
                continue

            def label(i):
                return str((items[i].get("metric") or {}).get("label") or "")

            bases = [i for i in hidden if not self._has_year_marker(label(i))]
            chosen = None
            if bases:
                chosen = bases[0]
            elif year is not None:
                chosen = next((i for i in hidden if str(year) in normalize_text(label(i)).split()), None)
            if chosen is None:
                chosen = next((i for i in hidden if "actual" in canonical_tokens(label(i))), None)
            if chosen is None:
                years = [
                    (max((int(t) for t in canonical_tokens(label(i)) if re.fullmatch(r"20\d{2}", t)), default=0), -i)
                    for i in hidden
                ]
                chosen = -max(years)[1]
            keep.add(chosen)
            dropped = [label(i) for i in hidden if i != chosen]
            if dropped:
                self._note(
                    f"variantes por año agrupadas en {label(chosen)} ({key[0]}): "
                    + ", ".join(dropped[:6]) + (" ..." if len(dropped) > 6 else "")
                )
        return [item for index, item in enumerate(items) if index in keep]

    def _tidy_unresolved_resolution(self, question, metric_result):
        """Opciones de una resolución ambigua / sugerencias sin variantes por año repetidas."""
        result = dict(metric_result)
        for key in ("candidates", "suggestions"):
            if result.get(key):
                result[key] = self._collapse_year_variants(list(result[key]), question)
        return result

    def _metric_vocabulary_tokens(self, metric, with_pages=True):
        """Palabras con que se puede nombrar un indicador: sus nombres, su tabla y sus páginas."""
        values = [*self._metric_names(metric), metric.get("table")]
        if with_pages:
            values.extend(self._metric_pages(metric))
        tokens = set()
        for value in values:
            tokens.update(token for token in canonical_tokens(value) if len(token) >= 3)
        return tokens

    def _board_tokens(self, metric):
        """Palabras del tablero (modelo e informes) del indicador, sin las
        genéricas («tablero», «de»)."""
        stop = {canonical_token(word) for word in STOPWORDS | GENERIC_QUERY_WORDS} | {"tablero"}
        tokens = set()
        for value in [metric.get("semantic_model"), *self._metric_reports(metric)]:
            tokens.update(token for token in canonical_tokens(value) if len(token) >= 3 and token not in stop)
        return tokens

    def _inclusion_filter_tokens(self, metric):
        """Palabras que el filtro de INCLUSIÓN de sus visuales le da al
        indicador: lo común a todos los valores de una lista «en» («CONSULTA
        EXTERNA OBSTETRICA», «URGENCIA OBSTETRICA»... -> «obstetrica»). La
        tarjeta «Triages Gineco» filtrada por esos valores ES «triages
        obstétricos» aunque su nombre no lo diga (holdout H20). Las
        exclusiones («no contiene OBSTETRICA») no cuentan."""
        cache = self.__dict__.setdefault("_inclusion_tokens_cache", {})
        key = (normalize_text(metric.get("semantic_model")), metric.get("metric_id"), metric.get("label"))
        if key in cache:
            return cache[key]
        tokens = set()
        index = self._visual_index()
        model = normalize_text(metric.get("semantic_model"))
        for appearance in metric.get("appearances") or []:
            visual = index.get((model, str(appearance.get("visual_id"))))
            if visual is None:
                continue
            for scope in ("visual", "page"):
                try:
                    items = self._scope_filter_items(metric.get("semantic_model"), visual, scope)
                except Exception:
                    items = []
                for item in items:
                    condition = item.get("condition")
                    if not isinstance(condition, dict) or condition.get("op") != "in":
                        continue
                    values = [value for value in condition.get("values") or [] if isinstance(value, str)]
                    if not values:
                        continue
                    common = None
                    for value in values:
                        value_tokens = {token for token in canonical_tokens(value) if len(token) >= 4}
                        common = value_tokens if common is None else common & value_tokens
                    tokens |= common or set()
        cache[key] = tokens
        return tokens

    @staticmethod
    def _explains(token, vocabulary):
        return any(_tokens_match_loosely(token, other) for other in vocabulary)

    def _content_ignored_tokens(self):
        cached = self.__dict__.get("_content_ignored_cache")
        if cached is None:
            cached = {
                canonical_token(word)
                for word in (
                    STOPWORDS | GENERIC_QUERY_WORDS | FILTER_NEUTRAL_WORDS | set(MONTHS)
                    | self._GENERIC_MEASURE_WORDS | self._RANKING_WORDS
                )
            }
            self._content_ignored_cache = cached
        return cached

    def _question_content_words(self, text):
        """Palabras con contenido de la pregunta, en orden (sin relleno,
        petición, periodo, cifras ni palabras genéricas de medida)."""
        ignored = self._content_ignored_tokens() | set(self._period_words(text))
        words = []
        for word in normalize_text(text).split():
            token = canonical_token(word)
            if (
                len(token) < 3 or token.isdigit() or token in ignored
                or _is_request_word(token)
            ):
                continue
            words.append(word)
        return words

    def metric_covers_question(self, question, metric):
        """¿El nombre del indicador explica TODAS las palabras con contenido de
        la pregunta (sin periodo, petición ni forma de la pregunta)? Con una
        sola sugerencia que las cubre no se pide confirmación: «reportes de
        patología este año» -> TOTAL DE REPORTES DE PATOLOGÍA EN EL PERIODO."""
        words = [
            word for word in self._question_content_words(question)
            if not _is_question_form_word(word)
            and canonical_token(word) not in {canonical_token(w) for w in FILTER_NEUTRAL_WORDS}
        ]
        if not words:
            return False
        name_tokens = {
            token for name in self._metric_names(metric) for token in canonical_tokens(name)
        }
        unexplained = [
            word for word in words
            if not any(_tokens_match_loosely(canonical_token(word), token) for token in name_tokens)
        ]
        if not unexplained:
            return True
        # Con al menos una palabra en el nombre o la página del indicador, el
        # resto puede decirlo su tablero o su nombre funcional documentado, o
        # ser un verbo («medicamentos desabastecidos hay reportados» -> CASOS
        # TOTALES de la página DETALLE MEDICAMENTOS DESABASTECIDOS).
        page_tokens = {token for page in self._metric_pages(metric) for token in canonical_tokens(page)}
        if len(unexplained) == len(words) and not any(
            any(_tokens_match_loosely(canonical_token(word), token) for token in page_tokens) for word in words
        ):
            return False
        _, covered = self.question_coverage(question, metric)
        rest = [word for word in unexplained if canonical_token(word) not in covered]
        return not rest or not self.implied_words(metric, rest)[1]

    def _head_token(self, question, source_context):
        """Sustantivo principal: primera palabra con contenido de la pregunta
        sin el nombre del tablero («cuánto PESO hay en lavandería»)."""
        words = self._question_content_words(self._metric_business_question(question, source_context))
        # «detalle de pacientes ...»: «detalle» pide la forma de la respuesta,
        # no es el sustantivo del indicador.
        words = [word for word in words if canonical_token(word) not in self._SHAPE_WORDS]
        return canonical_token(words[0]) if words else None

    _SHAPE_WORDS = {"detalle", "desglose"}
