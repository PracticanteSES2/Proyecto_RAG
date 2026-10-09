import json
import re
import unicodedata
from pathlib import Path


def normalize_text(value):
    value = str(value or "").lower().strip()

    value = "".join(
        char
        for char in unicodedata.normalize(
            "NFD",
            value,
        )
        if unicodedata.category(char) != "Mn"
    )

    value = re.sub(
        r"[^a-z0-9]+",
        " ",
        value,
    )

    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip()


def _token_score(question, candidate):
    q = normalize_text(question)
    c = normalize_text(candidate)

    if not q or not c:
        return 0.0

    if re.search(r"(?<![a-z0-9])" + re.escape(c) + r"(?![a-z0-9])", q):
        return 1.0

    q_tokens = set(q.split())
    c_tokens = set(c.split())

    if not q_tokens or not c_tokens:
        return 0.0

    common = q_tokens & c_tokens

    coverage = (
        len(common)
        / len(c_tokens)
    )

    precision = (
        len(common)
        / len(q_tokens)
    )

    return (
        0.82 * coverage
        + 0.18 * precision
    )


# ------------------------------------------------------------------
# Tablero / informe / página NOMBRADO en la pregunta
# ------------------------------------------------------------------
# «dame el total de triages del tablero de triage», «cirugías en el tablero de
# cirugías», «la página de detalle nedocs»: la palabra que sigue a «tablero de»
# nombra el tablero (no es un valor de filtro) y, si identifica un único
# modelo, fija el informe/página para resolver la métrica (routing fuerte).
BOARD_TRIGGER_RE = re.compile(
    r"(?<![a-z0-9])(?<!un )(?<!una )(?<!unos )(?<!otro )(?<!otra )"
    r"(?:tablero|tableros|informe|informes|reporte|reportes|dashboard|pagina|paginas"
    r"|seccion|pestana|hoja)"
    r"(?:\s+(?:de\s+la|de\s+los|de\s+las|del|de|llamad[oa]|sobre))?\s+"
)

# Nombres de página que no identifican un tablero por sí solos.
GENERIC_BOARD_NAMES = {
    "inicio", "resumen", "general", "principal", "home", "detalle", "portada",
    "indicadores", "tablero", "informe", "reporte", "pagina", "menu",
}

# Palabras que cortan el nombre de un tablero desconocido («tablero de triage
# en 2025» -> «triage»).
BOARD_NAME_STOP_WORDS = {
    "en", "de", "del", "la", "el", "los", "las", "para", "por", "con", "sin", "y",
    "o", "que", "durante", "entre", "desde", "hasta", "segun", "cuanto", "cuantos",
    "cuantas", "cuanta", "hay", "hubo", "fue", "fueron", "es", "son", "a", "al",
    "este", "esta", "ese", "esa", "mes", "ano", "anio", "dia", "semana", "hoy",
    "ayer", "ultimo", "ultimos", "ultima", "ultimas", "pasado", "pasada", "actual",
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
    "septiembre", "setiembre", "octubre", "noviembre", "diciembre", "total",
}

# Orden de preferencia cuando varios nombres coinciden en el mismo modelo.
_BOARD_KIND_ORDER = {"report": 0, "alias": 1, "page": 2, "documentation": 3}


def _singular(token):
    if token.endswith("s") and len(token) > 4:
        return token[:-1]
    return token


def _board_name_variants(value):
    """[(forma normalizada, rango)] con las que se nombra un tablero: «TABLERO
    LAVANDERIA» -> «lavanderia» (rango 0); «FARMACIA – INICIO» -> «farmacia
    inicio» (0) y «farmacia» (1: sin palabras genéricas, cede ante un nombre
    completo: «página de ocupación» es «Ocupación», no «DETALLE OCUPACIÓN»)."""
    text = normalize_text(value)
    if not text:
        return []
    variants = [(text, 0)]
    stripped = re.sub(r"^(?:tablero|informe|reporte|dashboard)(?:\s+(?:de|del|de la))?\s+", "", text)
    if stripped and stripped != text:
        variants.append((stripped, 0))
    for base, _ in list(variants):
        words = base.split()
        core = [word for word in words if word not in GENERIC_BOARD_NAMES]
        if core and len(core) < len(words):
            variants.append((" ".join(core), 1))
    result, seen = [], set()
    for variant, rank in variants:
        words = variant.split()
        if not words or all(word in GENERIC_BOARD_NAMES for word in words):
            continue
        if variant not in seen:
            seen.add(variant)
            result.append((variant, rank))
    return result


def documentation_dashboards_from_retriever(retriever):
    """[(tablero documentado, source_group)] a partir de los chunks del índice
    RAG («TRIAGE» -> tablero_de_atenciones_institucionales). Solo lee: si el
    retriever no expone sus puntos, devuelve []."""
    pairs = []
    try:
        provider = getattr(retriever, "documentation_dashboards", None)
        if callable(provider):
            return [tuple(item) for item in provider()]
        scroll = getattr(retriever, "_scroll_all", None)
        if not callable(scroll):
            return []
        read = getattr(retriever, "_payload_value", None)
        seen = set()
        for point in scroll():
            payload = getattr(point, "payload", None) or {}
            if callable(read):
                dashboard = read(payload, "dashboard")
                group = read(payload, "source_group")
            else:
                metadata = payload.get("metadata") or {}
                dashboard = payload.get("dashboard") or metadata.get("dashboard")
                group = payload.get("source_group") or metadata.get("source_group")
            key = (str(dashboard or ""), str(group or ""))
            if dashboard and group and key not in seen:
                seen.add(key)
                pairs.append(key)
    except Exception:
        return []
    return pairs


class SourceModelRouter:
    """
    Resuelve:
        pregunta / dashboard / reporte
            -> source_group
            -> report
            -> semantic_model
            -> technical_catalog

    No abre conexiones Power BI. Solo trabaja con los catálogos locales.
    """

    def __init__(
        self,
        source_registry_path,
        visual_catalog_path=None,
        project_root=None,
        default_semantic_model=None,
    ):
        self.source_registry_path = Path(
            source_registry_path
        )

        self.visual_catalog_path = (
            Path(visual_catalog_path)
            if visual_catalog_path
            else None
        )

        self.project_root = Path(
            project_root
            or self.source_registry_path
            .resolve()
            .parents[2]
        ).resolve()

        self.default_semantic_model = (
            default_semantic_model
        )

        self.registry = self._load_json(
            self.source_registry_path,
            default={},
        )

        self.visual_catalog = (
            self._load_json(
                self.visual_catalog_path,
                default={},
            )
            if self.visual_catalog_path
            else {}
        )

        self.sources = list(
            self.registry.get(
                "sources",
                [],
            )
            or []
        )

        self.models = list(
            self.registry.get(
                "models",
                [],
            )
            or []
        )

        self._models_by_name = {}
        self._models_by_key = {}
        self._sources_by_model = {}
        self._pages_by_model = {}
        self._page_contexts = []

        # Tableros de la documentación (RAG) con su grupo de fuentes y caché
        # de nombres de tablero/página para board_mentions().
        self._documentation_dashboards = []
        self._board_name_index = None

        self._build_indexes()

    def _load_json(
        self,
        path,
        default=None,
    ):
        if (
            path is None
            or not Path(path).exists()
        ):
            return (
                default
                if default is not None
                else {}
            )

        return json.loads(
            Path(path).read_text(
                encoding="utf-8"
            )
        )

    def _resolve_path(
        self,
        value,
    ):
        if not value:
            return None

        path = Path(value)

        if not path.is_absolute():
            path = (
                self.project_root
                / path
            )

        return path.resolve()

    def _build_indexes(
        self,
    ):
        for model in self.models:
            name = model.get(
                "semantic_model"
            )
            key = model.get(
                "semantic_model_key"
            )

            if name:
                self._models_by_name[
                    normalize_text(name)
                ] = model

            if key:
                self._models_by_key[
                    normalize_text(key)
                ] = model

        for source in self.sources:
            model = source.get(
                "semantic_model"
            )

            if model:
                self._sources_by_model.setdefault(
                    normalize_text(model),
                    [],
                ).append(
                    source
                )

        reports = (
            self.visual_catalog.get(
                "reports",
                [],
            )
            or []
        )

        # Compatibilidad con catálogo visual legacy de un solo modelo.
        if (
            not reports
            and self.visual_catalog.get(
                "semantic_model"
            )
        ):
            reports = [
                self.visual_catalog
            ]

        for report in reports:
            model = report.get(
                "semantic_model"
            )
            report_name = (
                report.get(
                    "report"
                )
                or report.get(
                    "semantic_model"
                )
            )
            source_group = (
                report.get(
                    "source_group"
                )
            )

            for page in (
                report.get(
                    "pages",
                    [],
                )
                or []
            ):
                display_name = (
                    page.get(
                        "page_display_name"
                    )
                    or page.get(
                        "displayName"
                    )
                    or page.get(
                        "page_name"
                    )
                )

                if not display_name:
                    continue

                context = {
                    "semantic_model":
                        model,
                    "report":
                        report_name,
                    "source_group":
                        source_group,
                    "dashboard":
                        display_name,
                    "page_name":
                        page.get(
                            "page_name"
                        ),
                }

                self._page_contexts.append(
                    context
                )

                if model:
                    self._pages_by_model.setdefault(
                        normalize_text(model),
                        [],
                    ).append(
                        context
                    )

    def semantic_models(
        self,
    ):
        values = []

        for model in self.models:
            name = model.get(
                "semantic_model"
            )

            if (
                name
                and name not in values
            ):
                values.append(name)

        return values

    def _model_exists(
        self,
        semantic_model,
    ):
        if not semantic_model:
            return False

        normalized = normalize_text(
            semantic_model
        )

        if normalized in self._models_by_name:
            return True

        # Puede existir en source_registry aunque no esté en models.
        return normalized in self._sources_by_model

    def _catalog_from_model(
        self,
        semantic_model,
    ):
        if not semantic_model:
            return None

        model = self._models_by_name.get(
            normalize_text(
                semantic_model
            )
        )

        candidates = []

        if model:
            candidates.append(
                model.get(
                    "technical_catalog"
                )
            )

            model_key = model.get(
                "semantic_model_key"
            )

            if model_key:
                candidates.append(
                    (
                        self.project_root
                        / "data"
                        / "catalog"
                        / (
                            f"{model_key}"
                            "_rag.json"
                        )
                    )
                )

        for source in self._sources_by_model.get(
            normalize_text(
                semantic_model
            ),
            [],
        ):
            candidates.append(
                source.get(
                    "technical_catalog"
                )
            )

        for candidate in candidates:
            path = self._resolve_path(
                candidate
            )

            if (
                path is not None
                and path.exists()
            ):
                return path

        return None

    def catalog_path_for_model(
        self,
        semantic_model,
        required=True,
    ):
        path = self._catalog_from_model(
            semantic_model
        )

        if (
            required
            and path is None
        ):
            raise FileNotFoundError(
                "No encontré catálogo técnico para "
                f"el modelo semántico '{semantic_model}'."
            )

        return path

    def sources_for_model(
        self,
        semantic_model,
    ):
        return list(
            self._sources_by_model.get(
                normalize_text(
                    semantic_model
                ),
                [],
            )
        )

    def pages_for_model(
        self,
        semantic_model,
    ):
        return list(
            self._pages_by_model.get(
                normalize_text(
                    semantic_model
                ),
                [],
            )
        )

    def contexts_for_dashboard(
        self,
        dashboard,
    ):
        target = normalize_text(
            dashboard
        )

        if not target:
            return []

        matches = []

        for context in self._page_contexts:
            value = normalize_text(
                context.get(
                    "dashboard"
                )
            )

            if value == target:
                matches.append(
                    context
                )

        return matches

    def candidate_pages(
        self,
        question,
        semantic_model=None,
        limit=5,
    ):
        contexts = (
            self.pages_for_model(
                semantic_model
            )
            if semantic_model
            else self._page_contexts
        )

        scored = []

        for context in contexts:
            dashboard = context.get(
                "dashboard"
            )

            score = _token_score(
                question,
                dashboard,
            )

            if score > 0:
                scored.append(
                    (
                        score,
                        dashboard,
                        context,
                    )
                )

        scored.sort(
            key=lambda item:
                item[0],
            reverse=True,
        )

        result = []
        seen = set()

        for score, _, context in scored:
            key = (
                normalize_text(
                    context.get(
                        "semantic_model"
                    )
                ),
                normalize_text(
                    context.get(
                        "dashboard"
                    )
                ),
            )

            if key in seen:
                continue

            result.append({
                **context,
                "score":
                    round(
                        score,
                        4,
                    ),
            })
            seen.add(key)

            if len(result) >= int(limit):
                break

        return result

    def _source_names(
        self,
        source,
    ):
        values = [
            (
                "report",
                source.get(
                    "report"
                ),
                1.00,
            ),
            (
                "default_dashboard",
                source.get(
                    "default_dashboard"
                ),
                0.92,
            ),
        ]

        for alias in (
            source.get(
                "aliases",
                [],
            )
            or []
        ):
            values.append(
                (
                    "alias",
                    alias,
                    0.96,
                )
            )

        source_group = source.get(
            "source_group"
        )

        if source_group:
            friendly = (
                str(source_group)
                .replace(
                    "_",
                    " ",
                )
                .replace(
                    "-",
                    " ",
                )
            )

            values.append(
                (
                    "source_group",
                    friendly,
                    0.72,
                )
            )

        return values

    # ------------------------------------------------------------------
    # Tablero / página nombrado en la pregunta
    # ------------------------------------------------------------------
    def register_documentation_dashboards(self, pairs):
        """Registra tableros documentados [(nombre, source_group)]: «tablero de
        triage» identifica TABLERO DE ATENCIONES INSTITUCIONALES aunque su
        página TRIAGE no esté en el catálogo visual."""
        values = []
        for item in pairs or []:
            try:
                name, group = item
            except (TypeError, ValueError):
                continue
            if name and group and (str(name), str(group)) not in values:
                values.append((str(name), str(group)))
        self._documentation_dashboards = values
        self._board_name_index = None
        return len(values)

    def _board_names(self):
        """[(tokens, entrada)] de informes, alias, páginas y tableros
        documentados. Cada entrada lleva modelo, informe y página."""
        if self._board_name_index is not None:
            return self._board_name_index
        entries = []

        def add(name, kind, semantic_model, report, source_group, dashboard):
            if not semantic_model:
                return
            for variant, rank in _board_name_variants(name):
                entries.append((variant.split(), {
                    "name": str(name), "kind": kind,
                    "semantic_model": semantic_model, "report": report,
                    "source_group": source_group, "dashboard": dashboard,
                    "variant_rank": rank, "tokens": variant.split(),
                }))

        for source in self.sources:
            model = source.get("semantic_model")
            report = source.get("report")
            group = source.get("source_group")
            add(report, "report", model, report, group, None)
            add(source.get("default_dashboard"), "report", model, report, group, None)
            for alias in source.get("aliases") or []:
                add(alias, "alias", model, report, group, None)
        for context in self._page_contexts:
            add(context.get("dashboard"), "page", context.get("semantic_model"),
                context.get("report"), context.get("source_group"), context.get("dashboard"))
        by_group = {}
        for source in self.sources:
            if source.get("source_group"):
                by_group.setdefault(normalize_text(source.get("source_group")), source)
        for name, group in self._documentation_dashboards:
            source = by_group.get(normalize_text(group))
            if source is None:
                continue
            add(name, "documentation", source.get("semantic_model"), source.get("report"),
                source.get("source_group"), name)
        self._board_name_index = entries
        return entries

    def board_mentions(self, question):
        """Tableros/páginas nombrados con «tablero/informe/página de X».

        Devuelve [{"phrase", "name", "tokens", "known", "contexts"}]: `phrase`
        es el fragmento normalizado completo («tablero de triage»), `tokens`
        las palabras del nombre (no son valores de filtro) y `contexts` los
        informes/páginas conocidos con ese nombre (vacío si no se reconoce).
        """
        text = normalize_text(question)
        if not text:
            return []
        names = self._board_names()
        mentions = []
        for trigger in BOARD_TRIGGER_RE.finditer(text):
            following = text[trigger.end():].split()
            if not following:
                continue
            best_length, matched = 0, []
            for tokens, entry in names:
                length = len(tokens)
                if length < best_length or length > len(following):
                    continue
                if all(_singular(following[i]) == _singular(tokens[i]) for i in range(length)):
                    if length > best_length:
                        best_length, matched = length, []
                    matched.append(entry)
            if best_length:
                name_tokens = following[:best_length]
                # Nombre completo antes que nombre sin palabras genéricas, e
                # informe/alias propio antes que páginas homónimas de otros
                # informes («tablero de gestión camas» es TABLERO GESTION
                # CAMAS aunque el BRIEFING tenga una página GESTIÓN CAMAS).
                best_rank = min(entry.get("variant_rank", 0) for entry in matched)
                matched = [entry for entry in matched if entry.get("variant_rank", 0) == best_rank]
                reports = [entry for entry in matched if entry["kind"] in ("report", "alias")]
                if reports:
                    matched = reports
            else:
                name_tokens = []
                for word in following[:3]:
                    if word in BOARD_NAME_STOP_WORDS or word.isdigit():
                        break
                    name_tokens.append(word)
                if not name_tokens or all(word in GENERIC_BOARD_NAMES for word in name_tokens):
                    continue
            contexts, seen = [], set()
            # Primero la misma forma escrita («triage» = TRIAGE) y luego la
            # que solo coincide en singular/plural (TRIAGES); `exact` lo marca
            # para desempatar entre modelos (QueryPlanBuilder).
            ordered = sorted(matched, key=lambda item: (
                item.get("tokens") != name_tokens, _BOARD_KIND_ORDER.get(item["kind"], 9),
            ))
            for entry in ordered:
                key = (normalize_text(entry["semantic_model"]), normalize_text(entry["report"]),
                       normalize_text(entry["dashboard"]))
                if key not in seen:
                    seen.add(key)
                    contexts.append({**entry, "exact": entry.get("tokens") == name_tokens})
            mentions.append({
                "phrase": (trigger.group(0) + " ".join(name_tokens)).strip(),
                "name": " ".join(name_tokens),
                "tokens": list(name_tokens),
                "known": bool(contexts),
                "contexts": contexts,
            })
        return mentions

    def board_context(self, entry, mentions=None, candidates=None):
        """source_context «fuerte» para un informe/página nombrado."""
        model = entry.get("semantic_model")
        catalog_path = self.catalog_path_for_model(model, required=False)
        kind = entry.get("kind")
        return {
            "status": "resolved",
            "reason": "explicit_board_mention",
            "routing_strength": "strong",
            "semantic_model": model,
            "report": entry.get("report"),
            "source_group": entry.get("source_group"),
            "dashboard": entry.get("dashboard") if kind in ("page", "documentation") else None,
            "board_name": entry.get("name"),
            "board_kind": kind,
            "technical_catalog": str(catalog_path) if catalog_path else None,
            "score": 1.0,
            "candidates": list(candidates or []),
            "board_mentions": list(mentions or []),
        }

    def _apply_board_mentions(self, result, mentions):
        """Fija el informe/página nombrado si identifica un único modelo.

        Si el nombre existe en varios modelos (una página «URGENCIAS» en un
        informe y un tablero documentado «URGENCIAS» en otro) no se fija nada:
        solo se informa en `board_mention_models`.
        """
        result = dict(result or {})
        result["board_mentions"] = mentions
        contexts = [context for mention in mentions for context in mention["contexts"]]
        if not contexts:
            return result
        models = sorted({normalize_text(context["semantic_model"]) for context in contexts})
        if len(models) != 1:
            result["board_mention_models"] = sorted({
                context["semantic_model"] for context in contexts
            })
            return result
        if (
            result.get("status") == "resolved"
            and result.get("routing_strength") == "strong"
            and normalize_text(result.get("semantic_model")) != models[0]
        ):
            # Un informe nombrado por su nombre propio manda sobre la página.
            return result
        return self.board_context(
            contexts[0], mentions=mentions, candidates=result.get("candidates"),
        )

    def resolve(
        self,
        question=None,
        dashboard=None,
        semantic_model=None,
        report=None,
    ):
        result = self._resolve_registry(
            question=question, dashboard=dashboard,
            semantic_model=semantic_model, report=report,
        )
        if semantic_model or not question:
            return result
        mentions = self.board_mentions(question)
        if not mentions:
            return result
        return self._apply_board_mentions(result, mentions)

    def _resolve_registry(
        self,
        question=None,
        dashboard=None,
        semantic_model=None,
        report=None,
    ):
        # 1) Modelo explícito siempre tiene prioridad.
        if (
            semantic_model
            and self._model_exists(
                semantic_model
            )
        ):
            source = None

            sources = self.sources_for_model(
                semantic_model
            )

            if report:
                report_norm = normalize_text(
                    report
                )

                for item in sources:
                    if normalize_text(
                        item.get(
                            "report"
                        )
                    ) == report_norm:
                        source = item
                        break

            if (
                source is None
                and dashboard
            ):
                contexts = (
                    self.contexts_for_dashboard(
                        dashboard
                    )
                )

                for context in contexts:
                    if normalize_text(
                        context.get(
                            "semantic_model"
                        )
                    ) == normalize_text(
                        semantic_model
                    ):
                        source = {
                            "source_group":
                                context.get(
                                    "source_group"
                                ),
                            "report":
                                context.get(
                                    "report"
                                ),
                        }
                        break

            if (
                source is None
                and len(sources) == 1
            ):
                source = sources[0]

            return {
                "status":
                    "resolved",
                "reason":
                    "explicit_semantic_model",
                "routing_strength":
                    "strong",
                "semantic_model":
                    semantic_model,
                "report":
                    (
                        report
                        or (
                            source.get(
                                "report"
                            )
                            if source
                            else None
                        )
                    ),
                "source_group":
                    (
                        source.get(
                            "source_group"
                        )
                        if source
                        else None
                    ),
                "dashboard":
                    dashboard,
                "technical_catalog":
                    (
                        str(
                            self.catalog_path_for_model(
                                semantic_model,
                                required=False,
                            )
                        )
                        if self.catalog_path_for_model(
                            semantic_model,
                            required=False,
                        )
                        else None
                    ),
                "score":
                    1.0,
                "candidates":
                    [],
            }

        scored = []

        q = question or ""

        # 2) Nombres de informe / aliases.
        for source in self.sources:
            score = 0.0
            reasons = []

            source_report = source.get(
                "report"
            )

            if report:
                candidate = _token_score(
                    report,
                    source_report,
                )

                if candidate >= 0.95:
                    score += 1.25
                    reasons.append(
                        "report_argument"
                    )

            for (
                name_type,
                value,
                weight,
            ) in self._source_names(
                source
            ):
                local_score = _token_score(
                    q,
                    value,
                )

                if local_score >= 0.72:
                    score += (
                        weight
                        * local_score
                    )

                    reasons.append(
                        name_type
                    )

            if dashboard:
                # Dashboard puede ser el informe mismo.
                local_score = _token_score(
                    dashboard,
                    source_report,
                )

                if local_score >= 0.90:
                    score += (
                        1.10
                        * local_score
                    )
                    reasons.append(
                        "dashboard_report"
                    )

                # O una página interna del informe.
                for context in (
                    self.contexts_for_dashboard(
                        dashboard
                    )
                ):
                    if (
                        normalize_text(
                            context.get(
                                "semantic_model"
                            )
                        )
                        ==
                        normalize_text(
                            source.get(
                                "semantic_model"
                            )
                        )
                    ):
                        if (
                            not context.get(
                                "report"
                            )
                            or
                            normalize_text(
                                context.get(
                                    "report"
                                )
                            )
                            ==
                            normalize_text(
                                source_report
                            )
                        ):
                            score += 1.15
                            reasons.append(
                                "dashboard_page"
                            )
                            break

            # Nombres de páginas dentro de la pregunta.
            page_score = 0.0

            for context in (
                self.pages_for_model(
                    source.get(
                        "semantic_model"
                    )
                )
            ):
                if (
                    context.get(
                        "report"
                    )
                    and source_report
                    and normalize_text(
                        context.get(
                            "report"
                        )
                    )
                    != normalize_text(
                        source_report
                    )
                ):
                    continue

                candidate = _token_score(
                    q,
                    context.get(
                        "dashboard"
                    ),
                )

                # Evitar que nombres genéricos como "General"
                # enruten por sí solos una consulta.
                if (
                    candidate >= 0.88
                    and len(
                        normalize_text(
                            context.get(
                                "dashboard"
                            )
                        ).split()
                    ) >= 2
                ):
                    page_score = max(
                        page_score,
                        candidate,
                    )

            if page_score:
                score += (
                    0.78
                    * page_score
                )
                reasons.append(
                    "page_name"
                )

            if score > 0:
                scored.append({
                    "score":
                        round(
                            score,
                            4,
                        ),
                    "reasons":
                        reasons,
                    "semantic_model":
                        source.get(
                            "semantic_model"
                        ),
                    "report":
                        source_report,
                    "source_group":
                        source.get(
                            "source_group"
                        ),
                    "dashboard":
                        dashboard,
                })

        scored.sort(
            key=lambda item:
                item["score"],
            reverse=True,
        )

        if scored:
            best = scored[0]

            if (
                len(scored) > 1
                and
                abs(
                    best["score"]
                    - scored[1]["score"]
                )
                < 0.10
                and
                normalize_text(
                    best.get(
                        "semantic_model"
                    )
                )
                !=
                normalize_text(
                    scored[1].get(
                        "semantic_model"
                    )
                )
            ):
                return {
                    "status":
                        "ambiguous",
                    "reason":
                        "multiple_sources",
                    "candidates":
                        scored[:5],
                }

            if best["score"] >= 0.68:
                catalog_path = (
                    self.catalog_path_for_model(
                        best.get(
                            "semantic_model"
                        ),
                        required=False,
                    )
                )

                strong_reasons = {
                    "report_argument",
                    "report",
                    "default_dashboard",
                    "alias",
                    "dashboard_report",
                }

                best_reasons = set(
                    best.get(
                        "reasons",
                        [],
                    )
                    or []
                )

                routing_strength = (
                    "strong"
                    if best_reasons
                    & strong_reasons
                    else "weak"
                )

                return {
                    "status":
                        "resolved",
                    "reason":
                        "source_registry",
                    "routing_strength":
                        routing_strength,
                    **best,
                    "technical_catalog":
                        (
                            str(
                                catalog_path
                            )
                            if catalog_path
                            else None
                        ),
                    "candidates":
                        scored[:5],
                }

        # 3) Dashboard exacto en una página visual.
        if dashboard:
            contexts = (
                self.contexts_for_dashboard(
                    dashboard
                )
            )

            model_names = {
                normalize_text(
                    item.get(
                        "semantic_model"
                    )
                )
                for item in contexts
                if item.get(
                    "semantic_model"
                )
            }

            if len(model_names) == 1:
                context = contexts[0]
                model = context.get(
                    "semantic_model"
                )
                catalog_path = (
                    self.catalog_path_for_model(
                        model,
                        required=False,
                    )
                )

                return {
                    "status":
                        "resolved",
                    "reason":
                        "dashboard_page_exact",
                    "routing_strength":
                        "weak",
                    **context,
                    "technical_catalog":
                        (
                            str(
                                catalog_path
                            )
                            if catalog_path
                            else None
                        ),
                    "score":
                        1.0,
                    "candidates":
                        contexts,
                }

        return {
            "status":
                "unresolved",
            "reason":
                "no_source_signal",
            "routing_strength":
                "none",
            "semantic_model":
                None,
            "report":
                None,
            "source_group":
                None,
            "dashboard":
                dashboard,
            "technical_catalog":
                None,
            "score":
                0.0,
            "candidates":
                scored[:5],
        }
