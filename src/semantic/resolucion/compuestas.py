"""Preguntas compuestas: participaciones («qué porcentaje de X es Y») y coordinadas («X y Y»).

build_composite, base de una participación (tmdl_real: la base no es un porcentaje), divisiones por
coordinación y su evaluación. Mixin de QueryPlanBuilder, métodos movidos sin cambios.
"""
import re

from src.semantic.answer_shape import detail_request
from src.semantic.resolucion.texto import (
    canonical_token,
    FILLER_WORDS,
    GENERIC_QUERY_WORDS,
    MONTHS,
    normalize_text,
    SHARE_RE,
)


class CompuestasMixin:


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
            if self._is_ratio_metric(metric):
                continue  # un porcentaje/promedio no es la base de una participación
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

    def build_composite(self, question, intent_result=None, selections=None):
        """Preguntas con participación y/o varias métricas ("peso y participación",
        "cirugías programadas y realizadas", "total de X y promedio de X").

        Devuelve None cuando la pregunta es de una sola métrica (flujo normal).
        Si no: {"status": "composite", "items": [...], "unresolved": [...],
        "grouped": bool} con items {"kind": "metric"|"share", "plan": plan,
        "label": str}, o el plan fallido (ambiguous / unsupported_filter /
        not_found, con "composite": True). Un plan ambiguo de UNA parte trae
        "composite_context" para retomar la compuesta tras la contrapregunta.

        `selections` = {parte: metric_id} elegidos en contrapreguntas previas
        de esta misma compuesta (parte "share" o el índice de la parte).
        """
        intent_result = intent_result or {}
        selections = {str(k): v for k, v in (selections or {}).items()}
        normalized = normalize_text(question)
        if not normalized or self._is_descriptive(normalized):
            return None
        source_context = self._source_context(question, dashboard=intent_result.get("dashboard"))
        share = self._share_match(normalized)
        share_question = None if share else self._share_question_match(normalized)
        share = share or share_question
        mentions = self._distinct_mentions(self._mentioned_metrics(normalized, source_context))

        if not share and not self._mentions_are_coordinated(normalized, mentions):
            # Sin nombres literales coordinados: coordinación por partes
            # («programadas y realizadas», «total de X y promedio de X»).
            return self._coordinated_composite(
                question, intent_result, source_context, selections,
            )

        unresolved = []
        rest_text = normalized
        coordinated_with_share = False
        if share:
            all_mentions = self._mentioned_metrics(normalized, source_context)
            neighbor = self._unresolved_neighbor(normalized, share.span(), all_mentions)
            coordinated_with_share = any(
                self._joined_by_conjunction(normalized, share.span(), (m["start"], m["end"]))
                for m in all_mentions
            )
            rest_text = self._cut_spans(normalized, [share.span()])
            # Muletillas interrogativas que quedan al quitar la participación.
            rest_text = re.sub(
                r"(?<![a-z0-9])(?:que|cual|cuales|fue|fueron|tuvo|tuvieron|tiene|tienen"
                r"|es|son|corresponde|corresponden|correspondio|correspondieron)(?![a-z0-9])",
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
            # «qué porcentaje de las atenciones...»: «atenciones» nombra tal
            # cual %ATENCIONES, pero la participación divide un total entre
            # otro; un porcentaje o promedio no es su base.
            ratios = [m for m in mentions if self._is_ratio_metric(m["metric"])]
            if ratios:
                self._note(
                    "en la participación no se usa como base "
                    + ", ".join(str(m["metric"].get("label")) for m in ratios)
                    + " (porcentaje o promedio)"
                )
                mentions = [m for m in mentions if m not in ratios]

        share_note = None
        if share and selections.get("share"):
            chosen = self._approved_metric(selections["share"])
            if chosen is None:
                return None
            targets = [(chosen, rest_text)]
            mentions = []
        elif share and not mentions:
            base = self._share_base_metric(question, rest_text, intent_result, source_context)
            if base.get("status") != "resolved":
                return base
            targets = [(base["metric"], rest_text)]
            share_note = base.get("note")
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
            plan["composite_sub_question"] = sub_question
            items.append({"kind": "metric", "plan": plan, "label": metric.get("label")})

        if not items:
            return failures[0]
        grouped = any(i["plan"].get("mode") == "grouped" for i in items)
        if grouped and (
            not self._same_grouping([i["plan"] for i in items])
            or (not share and len(items) < 2)
        ):
            return None  # Agrupaciones distintas: se mantiene el flujo de una sola.

        if share:
            base = items[0]["plan"]
            if base.get("mode") == "grouped":
                dimension = dict(base["group_by"][0])
                dimension["scope"] = "group"
            else:
                categorical = [
                    f for f in base.get("filters", [])
                    if f.get("type") == "categorical" and not f.get("temporal")
                ]
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
            if (
                not mentions or share_question
                or (base.get("mode") == "grouped" and not coordinated_with_share)
            ):
                # Solo participación cuando la pregunta no pidió la métrica
                # base («¿qué participación tuvo X?», «qué porcentaje del peso
                # fue de X», «participación del peso por servicio»). «peso y
                # participación por servicio» pide las dos columnas.
                items = [items[-1]]
            grouped = base.get("mode") == "grouped"

        composite = {
            "status": "composite", "question": question, "items": items,
            "unresolved": unresolved, "failures": failures,
            "failed_labels": failed_labels,
            "source_context": source_context,
            "grouped": grouped,
            "split": "share" if share else "mentions",
        }
        if share_note:
            composite["notes"] = [share_note]
        return composite

    # ---------------- compuestas: utilidades ----------------
    # «qué porcentaje de las atenciones de 2025 fueron de nueva eps»: el
    # verbo final («fueron de», «corresponden a») distingue la participación
    # de un indicador que ya es un porcentaje («qué porcentaje de ocupación»).
    _SHARE_QUESTION_RE = re.compile(
        r"(?<![a-z0-9])(?:que|cual\s+(?:es|fue)\s+el|el)\s+(?:porcentaje|%)\s+(?:de|del)"
        r"(?=\s+(?:(?:el|la|los|las)\s+)?[a-z0-9].*?\s"
        r"(?:fueron|fue|son|es|corresponde|corresponden|correspondio|correspondieron"
        r"|pertenece|pertenecen|pertenecio|pertenecieron)\s+(?:de|a|al|del|para)\s)"
    )

    def _share_question_match(self, normalized):
        match = self._SHARE_QUESTION_RE.search(normalized)
        if not match:
            return None
        core = re.search(r"(?:porcentaje|%)\s+de", match.group(0)).group(0)
        for metric in self._dedupe_metrics(self.metrics):
            for name in self._metric_names(metric):
                norm = normalize_text(name)
                if norm and norm.startswith(core) and re.search(
                    r"(?<![a-z0-9])" + re.escape(norm) + r"(?![a-z0-9])", normalized
                ):
                    return None
        return match

    def _approved_metric(self, metric_id):
        for metric in self._dedupe_metrics(self.metrics):
            if (
                metric.get("validation_status") == "approved"
                and str(metric.get("metric_id")) == str(metric_id)
            ):
                return metric
        return None

    @staticmethod
    def _joined_by_conjunction(normalized, left_span, right_span):
        """True si entre los dos tramos solo hay «y»/«e» y muletillas."""
        (a_start, a_end), (b_start, b_end) = sorted([left_span, right_span])
        if a_end > b_start:
            return False
        words = normalized[a_end:b_start].split()
        return (
            bool({"y", "e"} & set(words)) and len(words) <= 4
            and all(w in FILLER_WORDS for w in words)
        )

    def _mentions_are_coordinated(self, normalized, mentions):
        """Varias métricas nombradas literalmente y unidas por «y», «e» o coma."""
        if len(mentions) < 2:
            return False
        for left, right in zip(mentions, mentions[1:]):
            words = normalized[left["end"]:right["start"]].split()
            if (
                not ({"y", "e", "con", "ademas"} & set(words))
                or len(words) > 4
                or any(w not in FILLER_WORDS and w not in {"ademas"} for w in words)
            ):
                return False
        return True

    @staticmethod
    def _grouping_signature(plan):
        if plan.get("mode") != "grouped":
            return None
        if plan.get("temporal_buckets"):
            return ("temporal", tuple(b.get("label") for b in plan["temporal_buckets"]))
        return tuple(
            (normalize_text(g.get("table")), normalize_text(g.get("column")))
            for g in plan.get("group_by") or []
        )

    def _same_grouping(self, plans):
        signatures = {self._grouping_signature(plan) for plan in plans}
        return len(signatures) == 1 and None not in signatures

    def _is_ratio_metric(self, metric):
        """¿El indicador es un porcentaje o un promedio (no se puede sumar)?
        Además de `_metric_measure_kinds`: «%» en el nombre sin normalizar o
        en el formato, o una división entre dos agregaciones
        («DISTINCTCOUNT(...)/DISTINCTCOUNT(...)», sin DIVIDE)."""
        metric = metric or {}
        if self._metric_measure_kinds(metric) & {"percent", "average"}:
            return True
        names = f"{metric.get('label') or ''} {metric.get('measure') or ''}"
        fmt = str(metric.get("format_string") or metric.get("format") or "")
        if "%" in names or "%" in fmt:
            return True
        expression = " ".join(
            str(value) for value in (
                metric.get("base_dax_expression") or metric.get("dax_expression"), metric.get("model_expression"),
                self._measure_expression(metric.get("semantic_model"), metric),
            ) if value
        )
        return bool(re.search(r"\)\s*/\s*\(?\s*[A-Z]+\s*\(", expression, re.IGNORECASE))

    def _share_base_metric(self, question, rest_text, intent_result, source_context):
        """Métrica base de una participación sin indicador nombrado literalmente.

        El resto de la pregunta («las atenciones de 2025 de nueva eps») se
        resuelve como cualquier pregunta. Si el indicador existe en varios
        tableros, se queda el único en el que el valor pedido es un filtro
        válido (la participación lo necesita) o, entre los válidos, el de
        participación del tablero enrutado; si quedan varios, se contrapregunta
        esa parte. Sin indicador reconocible: el de participación del tablero
        enrutado (_default_share_metric).
        """
        default = self._default_share_metric(source_context)
        plan = self.build(rest_text, intent_result=intent_result)
        status = plan.get("status")
        if status == "ready" and self._is_ratio_metric(plan["metric"]):
            # Una participación divide el total con el filtro entre el total
            # sin él: con un porcentaje o un promedio («%ATENCIONES» para «qué
            # porcentaje de las atenciones fueron de nueva eps») esa división
            # no tiene sentido. Se buscan los conteos/sumas que también
            # nombran la pregunta.
            additive = [
                candidate for candidate in self.alternative_metrics(
                    rest_text, intent_result, exclude_ids=[plan["metric"].get("metric_id")], limit=8,
                )
                if not self._is_ratio_metric(candidate.get("metric") or {})
                and float(candidate.get("business_score") or 0.0) >= self.min_metric_score
            ]
            if additive:
                self._note(
                    f"{plan['metric'].get('label')} es un porcentaje/promedio: no sirve de base para una "
                    "participación; se prueban los indicadores que cuentan o suman: "
                    + ", ".join(str(c["metric"].get("label")) for c in additive[:5])
                )
                plan = {**plan, "status": "ambiguous",
                        "metric_resolution": {**(plan.get("metric_resolution") or {}), "candidates": additive}}
                status = "ambiguous"
        if status == "ready":
            return {"status": "resolved", "metric": plan["metric"]}
        if status == "ambiguous":
            viable, seen = [], set()
            for candidate in (plan.get("metric_resolution") or {}).get("candidates") or []:
                metric = candidate.get("metric") or {}
                if self._is_ratio_metric(metric):
                    continue
                key = metric.get("metric_id")
                if not key or key in seen:
                    continue
                seen.add(key)
                trial = self.build(rest_text, intent_result=intent_result, selected_metric_id=key)
                if trial.get("status") == "ready" and (
                    trial.get("mode") == "grouped" or any(
                        f.get("type") == "categorical" and not f.get("temporal")
                        for f in trial.get("filters") or []
                    )
                ):
                    viable.append({**candidate, "_trial": trial})
            if default.get("status") == "resolved" and any(
                self._metric_key(c["metric"]) == self._metric_key(default["metric"]) for c in viable
            ):
                return default
            # Entre los válidos, los que filtran por una columna que el
            # tablero muestra con ese indicador (no una columna técnica sin
            # visual) tienen evidencia de que esa participación tiene sentido.
            shown = [c for c in viable if not c["_trial"].get("technical_columns_used")]
            for group, why in (
                (viable, "el único donde el valor pedido es un filtro válido"),
                (shown, "el único donde el valor pedido se filtra por una columna que el tablero muestra"),
            ):
                if len(group) == 1:
                    metric = group[0]["metric"]
                    where = metric.get("report") or metric.get("semantic_model")
                    return {
                        "status": "resolved", "metric": metric,
                        "note": (
                            f"«{metric.get('label')}» existe en varios tableros; usé el de {where}, "
                            f"{why} para calcular la participación."
                        ),
                    }
            viable = [{k: v for k, v in c.items() if k != "_trial"} for c in viable]
            ambiguous = dict(plan)
            if viable:
                ambiguous["metric_resolution"] = {
                    **(plan.get("metric_resolution") or {}), "candidates": viable,
                }
            ambiguous["question"] = rest_text
            ambiguous["composite"] = True
            ambiguous["composite_context"] = {
                "question": question, "part": "share", "part_text": rest_text,
                "selections": {}, "ready_labels": [],
            }
            return ambiguous
        if default.get("status") == "resolved":
            return default
        return {
            "status": default.get("status", "not_found"),
            "stage": "metric", "question": question,
            "source_context": source_context,
            "metric_resolution": default, "composite": True,
        }

    # ---------------- compuestas por coordinación de partes ----------------
    # «cirugías programadas y realizadas», «interconsultas solicitadas y
    # respondidas», «pacientes atendidos y no atendidos» (coordinación
    # elíptica: la segunda parte comparte el sustantivo de la primera) y
    # «total de triages y promedio mensual de triages» (partes completas).
    # Inicio del resto común (periodo, filtros, tablero) tras la última parte.
    _COORD_HARD_STOPS = {
        "en", "durante", "para", "por", "segun", "desde", "hasta", "entre",
        "este", "esta", "ultimo", "ultimos", "ultima", "ultimas", "hoy", "ayer",
        "agrupado", "agrupada", "desglosado", "desglosada",
    }
    _COORD_VERBS = {
        "hubo", "hay", "fue", "fueron", "tuvo", "tuvieron", "tiene", "tienen",
        "se", "registro", "registraron", "llevamos", "lleva", "van", "va",
    }
    # Palabras de petición/interrogativas antes de cada parte.
    _COORD_LEAD = {
        "cuanto", "cuanta", "cuantos", "cuantas", "cual", "cuales", "que", "dime",
        "dame", "muestrame", "muestra", "indica", "indicame", "necesito", "saber",
        "quiero", "quisiera", "conocer", "consultar", "me", "puedes", "podrias",
        "decir", "dar", "el", "la", "los", "las", "y", "e", "tambien", "ademas",
    }
    _COORD_ARTICLES = {"el", "la", "los", "las"}
    # Terminaciones de participios/adjetivos («programadas», «atendidos»,
    # «ambulatorias»): solo entre ellas se completa la parte elíptica.
    _COORD_ADJ_RE = re.compile(
        r"(?:ad[oa]s?|id[oa]s?|ert[oa]s?|uest[oa]s?|ales?|ic[oa]s?|iv[oa]s?|ari[oa]s?|ori[oa]s?)$"
    )

    @staticmethod
    def _coord_tokens(question):
        """Tokens normalizados conservando las comas (separan partes)."""
        tokens = []
        for index, chunk in enumerate(str(question or "").split(",")):
            if index:
                tokens.append(",")
            tokens.extend(normalize_text(chunk).split())
        return tokens

    def _is_coord_stop(self, token):
        return (
            token in self._COORD_HARD_STOPS or token in self._COORD_VERBS
            or token in MONTHS or bool(re.fullmatch(r"(?:19|20)\d{2}", token))
        )

    def _coordination_splits(self, question, protected_spans=()):
        """Posibles divisiones de la pregunta en partes coordinadas.

        Cada división: {"parts": [{"text", "sub_question", "elliptical",
        "fallback"}], "conjunction": índice}. La primera parte va desde el
        inicio de la frase nominal (tras «cuántas», «el»...) hasta la
        conjunción; las siguientes, hasta el resto común (periodo, «en ...»,
        «de ...», verbo). El resto común se agrega a cada sub-pregunta.
        """
        tokens = self._coord_tokens(question)
        splits = []
        normalized = " ".join(t for t in tokens if t != ",")
        # Posición en el texto normalizado de cada token (para no partir el
        # nombre literal de un indicador como «INGRESOS Y EGRESOS»).
        offsets, cursor = [], 0
        for token in tokens:
            if token == ",":
                offsets.append(cursor)
                continue
            offsets.append(cursor)
            cursor += len(token) + 1

        for k, token in enumerate(tokens):
            if token not in ("y", "e") or k == 0:
                continue
            if any(start <= offsets[k] < end for start, end in protected_spans):
                continue
            # ---- partes antes de la conjunción (la primera y las separadas
            # por comas: «programadas, realizadas y canceladas»), hacia atrás
            # hasta una parada (periodo, «en», verbo) o una palabra de petición.
            segments = []
            end = k
            while True:
                start = end - 1
                while start >= 0:
                    word = tokens[start]
                    if word == "," or self._is_coord_stop(word):
                        break
                    if word in self._COORD_LEAD:
                        previous = tokens[start - 1] if start > 0 else ""
                        if not (word in self._COORD_ARTICLES and previous in ("de", "del", "a", "al")):
                            break
                    start -= 1
                if start + 1 >= end:
                    break
                segments.insert(0, (start + 1, end))
                if start >= 0 and tokens[start] == "," and end - start - 1 <= 3 and len(segments) < 6:
                    end = start
                    continue
                break
            if not segments:
                continue
            first = tokens[segments[0][0]:segments[0][1]]
            middles = [tokens[a:b] for a, b in segments[1:]]
            if not any(w not in self._COORD_LEAD for w in first):
                continue
            prefix = [t for t in tokens[:segments[0][0]] if t != ","]
            # ---- última parte: tras la conjunción hasta el resto común
            pos = k + 1
            own_lead = []
            while pos < len(tokens) and tokens[pos] in self._COORD_LEAD:
                own_lead.append(tokens[pos])
                pos += 1
            last_start = pos
            if pos < len(tokens) and tokens[pos] in ("no", "sin"):
                pos += 1
            while pos < len(tokens):
                word = tokens[pos]
                if word in (",", "y", "e", "de", "del") or self._is_coord_stop(word):
                    break
                pos += 1
            last = tokens[last_start:pos]
            if not last or all(w in ("no", "sin") for w in last):
                continue
            rest = [t for t in tokens[pos:] if t != ","]
            others = [*middles, last]
            parts = [{"text": " ".join(first), "words": first, "own_lead": False}]
            for words in others:
                parts.append({
                    "text": " ".join(words), "words": words,
                    "own_lead": bool(own_lead) and words is last,
                })
            splits.append({
                "conjunction": k, "prefix": prefix, "first": first,
                "parts": parts, "rest": rest, "normalized": normalized,
            })
        return splits

    def _coordination_variants(self, split):
        """Sub-preguntas de cada parte: elíptica («cirugías» + «realizadas»)
        y, como respaldo, la parte tal cual."""
        first = split["first"]
        prefix, rest = split["prefix"], split["rest"]
        # «total de triages y promedio mensual de triages»: el «de triages»
        # del resto ya está en la primera parte (no se repite).
        rest_first = rest
        if rest and rest[0] in ("de", "del"):
            end = 1
            while end < len(rest) and rest[end] not in ("de", "del") and not self._is_coord_stop(rest[end]):
                end += 1
            segment = [w for w in rest[1:end] if w not in self._COORD_ARTICLES]
            if segment and all(w in first for w in segment):
                rest_first = rest[end:]
        variants = [[{
            "text": " ".join(first), "elliptical": False,
            "sub_question": " ".join([*prefix, *first, *rest_first]),
        }]]
        head = first[:-1]
        last_first = first[-1]
        for part in split["parts"][1:]:
            words = part["words"]
            content = [w for w in words if w not in ("no", "sin")]
            options = []
            if (
                head and len(content) == 1
                and self._COORD_ADJ_RE.search(last_first) and self._COORD_ADJ_RE.search(content[0])
            ):
                expanded = [*head, *words]
                options.append({
                    "text": " ".join(expanded), "elliptical": True,
                    "shared": " ".join(head), "original": " ".join(words),
                    "sub_question": " ".join([*prefix, *expanded, *rest]),
                })
            options.append({
                "text": " ".join(words), "elliptical": False,
                "sub_question": " ".join([*prefix, *words, *rest]),
            })
            variants.append(options)
        return variants

    def _coordinated_composite(self, question, intent_result, source_context, selections):
        """Compuesta por partes coordinadas o None si la pregunta no lo es.

        Exige al menos dos partes resueltas con indicadores DISTINTOS (si
        coinciden, la «y» une valores de filtro o dimensiones: flujo normal).
        Una parte ambigua se contrapregunta (con el contexto para retomar la
        compuesta); una parte que no se resuelve se declara.
        """
        normalized = normalize_text(question)
        # «cuántas camas ocupadas hay en uci y cuáles son»: la «y» pide el
        # listado del mismo indicador (answer_shape), no otra medida.
        request = detail_request(question)
        if request is not None and request.get("cue") == "y cuales":
            return None
        protected = [
            (m["start"], m["end"])
            for m in self._mentioned_metrics(normalized, source_context)
            if re.search(r"(?<![a-z0-9])(?:y|e)(?![a-z0-9])", m["name"])
        ]
        for split in self._coordination_splits(question, protected):
            result = self._evaluate_coordination(
                question, split, intent_result, source_context, selections,
            )
            if result is not None:
                return result
        return None

    def _evaluate_coordination(self, question, split, intent_result, source_context, selections):
        built = []
        for index, options in enumerate(self._coordination_variants(split)):
            chosen_id = selections.get(str(index))
            outcome = None
            for option in options:
                plan = self.build(
                    option["sub_question"], intent_result=intent_result,
                    selected_metric_id=chosen_id,
                )
                outcome = {**option, "index": index, "plan": plan}
                if plan.get("status") in ("ready", "ambiguous"):
                    break
            built.append(outcome)

        ready = [b for b in built if b["plan"].get("status") == "ready"]
        keys = {self._metric_key(b["plan"]["metric"]) for b in ready}
        # Una parte ambigua solo cuenta si ofrece indicadores distintos de los
        # ya resueltos; si no, se declara como no resuelta.
        ambiguous = []
        for b in built:
            if b["plan"].get("status") != "ambiguous":
                continue
            resolution = b["plan"].get("metric_resolution") or {}
            options = [
                c for c in resolution.get("candidates") or []
                if self._metric_key(c.get("metric") or {}) not in keys
            ]
            if options:
                b["plan"] = {**b["plan"], "metric_resolution": {**resolution, "candidates": options}}
                ambiguous.append(b)
            else:
                b["plan"] = {**b["plan"], "status": "not_found"}
        if not ready or len(keys) + len(ambiguous) < 2 or (len(keys) < 2 and not ambiguous):
            return None
        if len(keys) < len(ready):
            return None  # Dos partes con el mismo indicador: la «y» une filtros.

        # «peso de antifluidos y urgencias»: «urgencias» es un valor de filtro
        # del primer indicador, no otro indicador.
        first = built[0]
        if first["plan"].get("status") == "ready":
            first_metric = first["plan"]["metric"]
            first_filters = {
                (normalize_text(f.get("table")), normalize_text(f.get("column")), str(f.get("value")))
                for f in first["plan"].get("filters") or []
            }
            for item in built[1:]:
                if item["elliptical"] or len(item["text"].split()) > 2:
                    continue
                trial = self.build(
                    " ".join([*split["prefix"], *split["first"], "de", item["text"], *split["rest"]]),
                    intent_result=intent_result,
                    selected_metric_id=first_metric.get("metric_id"),
                )
                extra = [
                    f for f in trial.get("filters") or []
                    if f.get("type") == "categorical" and not f.get("temporal")
                    and (normalize_text(f.get("table")), normalize_text(f.get("column")), str(f.get("value")))
                    not in first_filters
                ]
                if trial.get("status") == "ready" and extra:
                    return None

        split_note = None
        elliptical = [b for b in built if b.get("elliptical")]
        if elliptical:
            # La segunda parte comparte el sustantivo de la primera.
            split_note = "Interpreté " + ", ".join(
                f"«{b['original']}» como «{b['text']}»" for b in elliptical
            ) + "."

        if ambiguous:
            target = ambiguous[0]
            plan = dict(target["plan"])
            plan["composite"] = True
            plan["composite_context"] = {
                "question": question, "part": str(target["index"]),
                "part_text": target["text"], "selections": dict(selections),
                "ready_labels": [b["plan"]["metric"].get("label") for b in ready],
                "parts": [b["text"] for b in built],
            }
            return plan

        # Todas las partes se presentan con la agrupación de la primera.
        signature = self._grouping_signature(ready[0]["plan"])
        items, failed_labels, failures = [], [], []
        for b in built:
            plan = b["plan"]
            if plan.get("status") != "ready":
                plan["composite"] = True
                failures.append(plan)
                failed_labels.append(b["text"])
                continue
            if self._grouping_signature(plan) != signature:
                failed_labels.append(f"{b['text']} (con otra agrupación)")
                continue
            plan["question"] = question
            plan["composite_sub_question"] = b["sub_question"]
            items.append({
                "kind": "metric", "plan": plan, "label": plan["metric"].get("label"),
                "part": b["text"],
            })
        if len(items) < 2:
            return None
        return {
            "status": "composite", "question": question, "items": items,
            "unresolved": [], "failures": failures, "failed_labels": failed_labels,
            "source_context": source_context,
            "grouped": items[0]["plan"].get("mode") == "grouped",
            "split": "coordination",
            "split_parts": [b["text"] for b in built],
            "notes": [split_note] if split_note else [],
        }

    # ---------------- «cuántas X» ≈ «total de X» ----------------
    _COUNT_WORDS_RE = re.compile(
        r"(?<![a-z0-9])(?:cuant[oa]s?|numero\s+(?:de|del)|cantidad\s+(?:de|del))(?![a-z0-9])"
    )
