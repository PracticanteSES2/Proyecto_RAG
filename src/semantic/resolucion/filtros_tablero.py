"""Etapa «filtros y periodo» — filtros del TABLERO (visual, página e informe) del indicador.

Auditoría del banco real (2026-10-29, BH01/FM01/BH15) y r2-indicador-2: la cifra lleva los filtros
de su visual y de su página; con varios visuales se elige la tarjeta o la página principal; filtros
de tablas que no filtran la del indicador no cuentan; la pregunta manda sobre la misma columna
(_apply_board_filter_context). Pruebas: tests/resolution/test_filtros_tablero.py. Mixin de
QueryPlanBuilder, métodos movidos sin cambios desde query_plan_builder.py.
"""
import json
import re

from src.semantic.resolucion.texto import (
    _unique_strings,
    canonical_tokens,
    GENERIC_PAGE_WORDS,
    normalize_text,
)


class FiltrosTableroMixin:


    # ---------------- filtros de nivel de visual ----------------

    def _visual_index(self):
        """{(modelo normalizado, visual_id): visual} del catálogo de visuales."""
        cached = self.__dict__.get("_visual_index_cache")
        if cached is None:
            cached = {}
            for report in self.reports:
                model = normalize_text(report.get("semantic_model"))
                for page in report.get("pages", []) or []:
                    for visual in page.get("visuals", []) or []:
                        if visual.get("visual_id"):
                            cached.setdefault((model, str(visual["visual_id"])), visual)
            self._visual_index_cache = cached
        return cached

    # Filtros que el tablero aplica a la cifra de un visual: los del propio
    # visual y los heredados de su página y del informe (filterConfig de PBIR).
    _FILTER_SCOPES = ("visual", "page", "report")
    _SCOPE_TEXT = {"visual": "visual", "page": "página", "report": "informe"}
    # Visuales que muestran la cifra sola (sin ejes): lo que el usuario lee en
    # el tablero. Menor = más canónico.
    _CANONICAL_VISUAL_RANK = {
        "card": 0, "cardvisual": 0, "kpi": 0, "multirowcard": 1, "gauge": 1,
    }
    _PRINCIPAL_PAGE_RE = re.compile(r"(?<![a-z])(?:inicio|principal|resumen|portada|home)(?![a-z])")

    def _visual_context_index(self):
        """{(modelo normalizado, visual_id): (informe, página)} del catálogo."""
        cached = self.__dict__.get("_visual_context_cache")
        if cached is None:
            cached = {}
            for report in self.reports:
                model = normalize_text(report.get("semantic_model"))
                for page in report.get("pages", []) or []:
                    for visual in page.get("visuals", []) or []:
                        if visual.get("visual_id"):
                            cached.setdefault((model, str(visual["visual_id"])), (report, page))
            self._visual_context_cache = cached
        return cached

    def _scope_filter_items(self, semantic_model, visual, scope):
        """Filtros de un ámbito (visual, página o informe) que alcanzan al visual."""
        filters = visual.get("filters") or {}
        if scope == "visual":
            return list(filters.get("visual") or [])
        inherited = filters.get("inherited")
        if isinstance(inherited, dict):
            return list(inherited.get(scope) or [])
        # Catálogo sin filtros heredados en el visual: se leen de la página/informe.
        report, page = self._visual_context_index().get(
            (normalize_text(semantic_model), str(visual.get("visual_id"))), ({}, {}),
        )
        items = (page or {}).get("filters") if scope == "page" else (report or {}).get("report_filters")
        if isinstance(items, dict):
            items = items.get(scope)
        return [item for item in items or [] if isinstance(item, dict)]

    @staticmethod
    def _is_blank_test(condition):
        """¿La condición solo pregunta si la columna está (o no) en blanco?
        («FECHA_CIERRE en blanco» = suministro pendiente: es un estado, no un periodo)."""
        if not isinstance(condition, dict):
            return False
        op = condition.get("op")
        if op == "not":
            return FiltrosTableroMixin._is_blank_test(condition.get("arg"))
        if op == "in":
            return all(value is None for value in condition.get("values") or [None])
        if op == "cmp":
            return condition.get("value") is None and condition.get("cmp") in ("=", "<>")
        return False

    def _visual_filter_clauses(self, semantic_model, visual, scopes=("visual",)):
        """[(tabla, columna, condición, ámbito)] de los filtros que cambian el
        dato del visual en los ámbitos pedidos («visual», «page», «report»), o
        None si alguno no se entiende (no se aplica nada).
        Se ignoran los filtros sin condición y los de fecha/calendario (el
        periodo lo decide la pregunta), salvo los que solo piden una fecha en
        blanco o no («FECHA_CIERRE en blanco» = pendiente: es un estado)."""
        from src.semantic.visual_filters import UnsupportedCondition, condition_from_visual_file

        clauses = []
        for scope in scopes:
            for item in self._scope_filter_items(semantic_model, visual, scope):
                field = item.get("field") or {}
                table, column = field.get("table"), field.get("column")
                if field.get("kind") != "column" or not table or not column:
                    if item.get("values") or item.get("condition"):
                        return None
                    continue
                if field.get("model_valid") is False:
                    continue  # la columna ya no existe en el modelo
                temporal = (
                    bool(self._CALENDAR_TABLE_RE.match(normalize_text(table).replace(" ", "")))
                    or self._column_type(semantic_model, table, column) == "date"
                )
                if "condition" in item or item.get("condition_error"):
                    if item.get("condition_error"):
                        if temporal:
                            continue  # fecha relativa («últimos 7 días»): la decide la pregunta
                        return None
                    condition = item.get("condition")
                else:
                    # Catálogo anterior a guardar la condición: se lee del visual.json.
                    if scope != "visual":
                        if item.get("values") and not temporal:
                            return None
                        continue
                    try:
                        condition = condition_from_visual_file(visual.get("source_file"), item.get("name"), column)
                    except UnsupportedCondition:
                        if temporal:
                            continue
                        return None
                    if condition is None and item.get("values"):
                        if temporal:
                            continue
                        return None  # tenía valores pero no se pudo leer el operador
                if condition is None:
                    continue
                if temporal and not self._is_blank_test(condition):
                    continue
                clauses.append((table, column, condition, scope))
        return clauses

    def _tables_filtering_metric(self, metric):
        """Tablas cuyos filtros llegan a la del indicador (ella, las del lado
        «uno» de sus relaciones activas y las de relaciones en ambos sentidos),
        o None si el modelo no declara relaciones o no se conoce la tabla."""
        model = metric.get("semantic_model")
        if not self._has_relationship_metadata(model):
            return None
        base = {**metric, "dax_expression": metric.get("base_dax_expression") or metric.get("dax_expression")}
        tables = {normalize_text(name) for name in self._expression_tables(model, base)}
        own = metric.get("table")
        if own and not self._CALENDAR_TABLE_RE.match(normalize_text(own)):
            tables.add(normalize_text(own))
        if not tables:
            return None
        edges = []
        for relation in self._technical_catalog(model).get("relationships", []) or []:
            if relation.get("IsActive") is False:
                continue
            source, target = normalize_text(relation.get("FromTable")), normalize_text(relation.get("ToTable"))
            if not source or not target:
                continue
            edges.append((source, target))  # el lado «uno» filtra al «muchos»
            if str(relation.get("CrossFilteringBehavior") or "").lower().startswith("both"):
                edges.append((target, source))
        reached = set(tables)
        for _ in range(3):
            reached |= {target for source, target in edges if source in reached}
        return reached

    @staticmethod
    def _normalized_condition(condition):
        """Condición con el orden de «y/o» y de las listas normalizado (para comparar)."""
        if not isinstance(condition, dict):
            return condition
        op = condition.get("op")
        if op in ("and", "or"):
            args = [FiltrosTableroMixin._normalized_condition(arg) for arg in condition.get("args") or []]
            return {"op": op, "args": sorted(args, key=lambda arg: json.dumps(arg, sort_keys=True, default=str))}
        if op == "not":
            return {"op": "not", "arg": FiltrosTableroMixin._normalized_condition(condition.get("arg"))}
        if op == "in":
            values = condition.get("values") or []
            return {"op": "in", "values": sorted(values, key=lambda value: json.dumps(value, default=str))}
        return condition

    def _board_filter_clauses(self, metric, visual, reachable=None):
        """Filtros de visual + página + informe que el tablero aplica a la cifra
        del indicador en ese visual: sin repetidos y sin los de tablas que no
        filtran la del indicador (no cambian la cifra). None si alguno no se
        entiende."""
        from src.semantic.visual_filters import condition_signature

        clauses = self._visual_filter_clauses(metric.get("semantic_model"), visual, self._FILTER_SCOPES)
        if clauses is None:
            return None
        result, seen = [], set()
        for table, column, condition, scope in clauses:
            if reachable is not None and normalize_text(table) not in reachable:
                continue
            key = condition_signature(table, column, self._normalized_condition(condition))
            if key in seen:
                continue
            seen.add(key)
            result.append((table, column, condition, scope))
        return result

    def _visual_rank(self, appearance, visual):
        """Orden de preferencia de un visual como «la cifra del tablero»:
        tarjeta antes que gráfico, visible antes que oculto, página principal
        antes que las demás."""
        kind = normalize_text((visual or {}).get("visual_type") or appearance.get("visual_type")).replace(" ", "")
        page = normalize_text(appearance.get("page_display_name") or (visual or {}).get("page_display_name"))
        return (
            self._CANONICAL_VISUAL_RANK.get(kind, 3),
            1 if (visual or {}).get("is_hidden") else 0,
            0 if self._PRINCIPAL_PAGE_RE.search(page) else 1,
        )

    def _choose_board_filters(self, metric):
        """(cláusulas, aparición) de los filtros del tablero que corresponden a
        la cifra del indicador, o (None, motivo) si no se pueden decidir.

        - Todas las apariciones con los mismos filtros: esos.
        - Filtros distintos: los del visual más canónico (tarjeta visible de la
          página principal) si es único o si los igual de canónicos coinciden.
        - Si no, no se aplica nada (valor general) y el motivo lo dice."""
        from src.semantic.visual_filters import condition_signature

        index = self._visual_index()
        model = normalize_text(metric.get("semantic_model"))
        reachable = self._tables_filtering_metric(metric)
        entries = []
        for appearance in metric.get("appearances") or []:
            visual = index.get((model, str(appearance.get("visual_id"))))
            clauses = None
            if visual is not None:
                try:
                    clauses = self._board_filter_clauses(metric, visual, reachable)
                except Exception:
                    clauses = None
            signature = None if clauses is None else frozenset(
                condition_signature(table, column, self._normalized_condition(condition))
                for table, column, condition, _ in clauses
            )
            entries.append({
                "appearance": appearance, "visual": visual, "clauses": clauses, "signature": signature,
                "rank": self._visual_rank(appearance, visual) if clauses is not None else (9, 9, 9),
            })
        if not entries:
            return None, "sin visuales"
        signatures = {entry["signature"] for entry in entries}
        if len(signatures) == 1:
            entry = entries[0]
            if entry["clauses"] is None:
                return None, "filtros que no se pueden traducir"
            return entry["clauses"], entry["appearance"]
        known = [entry for entry in entries if entry["clauses"] is not None]
        if not known:
            return None, "filtros que no se pueden traducir"
        best = min(entry["rank"] for entry in known)
        top = [entry for entry in known if entry["rank"] == best]
        if len({entry["signature"] for entry in top}) == 1:
            return top[0]["clauses"], top[0]["appearance"]
        return None, "filtros distintos en cada visual"

    def _with_visual_filters(self, metrics):
        """Indicadores mostrados en visuales con filtros (del visual, de su
        página o del informe): la expresión pasa a CALCULATE(expr, filtros),
        que es la cifra que el usuario ve en el tablero.
        «MEDICAMENTOS EN VENCIMIENTO 0-30 DÍAS» = DISTINCTCOUNT(IPRCODIGO) con
        mes <= 1; %OCUPACION de la tarjeta de GESTIÓN CAMAS con los servicios
        excluidos por la página. Vale para agregaciones de visual y medidas.
        Si el indicador aparece en varios visuales con filtros distintos se
        usan los del visual más canónico (`_choose_board_filters`); si no hay
        uno claro queda el valor general y `board_filters_note` lo explica."""
        try:
            from src.semantic.visual_filters import describe_condition, filter_dax
        except Exception:
            return metrics
        if not self._visual_index():
            return metrics
        result = []
        for metric in metrics:
            appearances = metric.get("appearances") or []
            expression = metric.get("dax_expression")
            if (
                metric.get("source_type") not in ("visual_aggregation", "explicit_measure")
                or not appearances or not expression or metric.get("visual_filters")
            ):
                result.append(metric)
                continue
            try:
                chosen, source = self._choose_board_filters(metric)
            except Exception:
                chosen, source = None, None
            if not chosen:
                if chosen is None and source == "filtros distintos en cada visual":
                    metric = {**metric, "board_filters_note": source}
                result.append(metric)
                continue
            try:
                arguments = [filter_dax(table, column, condition) for table, column, condition, _ in chosen]
            except Exception:
                result.append(metric)
                continue
            enriched = dict(metric)
            enriched["base_dax_expression"] = expression
            enriched["dax_expression"] = "CALCULATE(" + expression + ", " + ", ".join(arguments) + ")"
            enriched["visual_filters"] = [
                {"table": table, "column": column, "condition": condition, "scope": scope,
                 "text": describe_condition(condition, column)}
                for table, column, condition, scope in chosen
            ]
            enriched["board_filters_source"] = {
                "page": source.get("page_display_name"),
                "visual_type": source.get("visual_type"),
                "visual_id": source.get("visual_id"),
                "report": source.get("report") or metric.get("report"),
            }
            result.append(enriched)
        return result

    def board_filters_text(self, metric, limit=4):
        """«Filtros del tablero aplicados (tarjeta de la página X): A; B» o None."""
        filters = (metric or {}).get("visual_filters") or []
        if not filters:
            return None
        texts = list(dict.fromkeys(str(item.get("text") or item.get("column")) for item in filters))
        shown = "; ".join(texts[:limit])
        if len(texts) > limit:
            shown += f" y {len(texts) - limit} más"
        source = metric.get("board_filters_source") or {}
        where = ""
        if source.get("page"):
            kind = normalize_text(source.get("visual_type")).replace(" ", "")
            visual = "tarjeta" if self._CANONICAL_VISUAL_RANK.get(kind, 3) <= 1 else "visual"
            where = f" ({visual} de la página {source['page']})"
        return f"Filtros del tablero aplicados{where}: {shown}."

    def _named_page_of_metric(self, question, metric):
        """Página del indicador que la pregunta nombra entera («cuentas en
        proceso de facturación» -> EN PROCESO FACTURACION, no EN PROCESO
        FACTURACION DE IMAGENES); la de más palabras si hay varias; None."""
        # El nombre de la página, sin conectores, tal cual y seguido en la
        # pregunta («en proceso (de) facturación»): no basta con palabras
        # sueltas parecidas («factura» no nombra la página FACTURACION).
        connectors = {"de", "del", "la", "el", "los", "las", "y", "a", "al"}
        question_seq = [token for token in canonical_tokens(question) if token not in connectors]
        best, best_size, tie = None, 0, False
        for page in _unique_strings(item.get("page_display_name") for item in metric.get("appearances") or []):
            page_seq = [token for token in canonical_tokens(page) if token not in connectors]
            content = [token for token in page_seq if token not in GENERIC_PAGE_WORDS]
            if not content or not any(
                question_seq[start:start + len(page_seq)] == page_seq
                for start in range(len(question_seq) - len(page_seq) + 1)
            ):
                continue
            tokens = set(content)
            if len(tokens) > best_size:
                best, best_size, tie = page, len(tokens), False
            elif len(tokens) == best_size:
                tie = True
        return None if tie else best

    def _use_named_page_filters(self, plan):
        """La pregunta nombra una de las páginas donde está el indicador: la
        cifra es la de ESA página (filtros de su visual, página e informe), no
        el valor general ni la de otra página. Cambia plan["metric"]."""
        from src.semantic.visual_filters import condition_signature, describe_condition, filter_dax

        metric = plan.get("metric") or {}
        if len(metric.get("appearances") or []) < 2 or not plan.get("question"):
            return
        page = self._named_page_of_metric(plan["question"], metric)
        if not page:
            return
        current = (metric.get("board_filters_source") or {}).get("page")
        if current and normalize_text(current) == normalize_text(page):
            return
        index = self._visual_index()
        model = normalize_text(metric.get("semantic_model"))
        reachable = self._tables_filtering_metric(metric)
        found, signatures = None, set()
        for appearance in metric.get("appearances") or []:
            if normalize_text(appearance.get("page_display_name")) != normalize_text(page):
                continue
            visual = index.get((model, str(appearance.get("visual_id"))))
            if visual is None:
                return
            try:
                clauses = self._board_filter_clauses(metric, visual, reachable)
            except Exception:
                return
            if clauses is None:
                return
            signatures.add(frozenset(
                condition_signature(table, column, self._normalized_condition(condition))
                for table, column, condition, _ in clauses
            ))
            found = found or (clauses, appearance)
        if found is None or len(signatures) != 1:
            return
        clauses, appearance = found
        base = metric.get("base_dax_expression") or metric.get("dax_expression")
        try:
            arguments = [filter_dax(table, column, condition) for table, column, condition, _ in clauses]
        except Exception:
            return
        updated = {key: value for key, value in metric.items() if key != "board_filters_note"}
        updated["base_dax_expression"] = base
        updated["dax_expression"] = ("CALCULATE(" + base + ", " + ", ".join(arguments) + ")") if arguments else base
        updated["visual_filters"] = [
            {"table": table, "column": column, "condition": condition, "scope": scope,
             "text": describe_condition(condition, column)}
            for table, column, condition, scope in clauses
        ]
        updated["board_filters_source"] = {
            "page": appearance.get("page_display_name"), "visual_type": appearance.get("visual_type"),
            "visual_id": appearance.get("visual_id"), "report": appearance.get("report") or metric.get("report"),
        }
        plan["metric"] = updated
        self._note(f"la pregunta nombra la página {page}: se usan los filtros de esa página del tablero")

    def _apply_board_filter_context(self, plan):
        """Plan listo: si la pregunta filtra una columna que el tablero ya
        filtra (el usuario pide CUIDADO ESPECIAL y la página lo excluye), manda
        la pregunta: se quita ese filtro del tablero. Agrega la nota con los
        filtros del tablero aplicados."""
        if not isinstance(plan, dict) or plan.get("status") != "ready":
            return plan
        self._use_named_page_filters(plan)
        metric = plan.get("metric") or {}
        board = metric.get("visual_filters") or []
        if not board or not metric.get("base_dax_expression"):
            return plan
        asked = set()
        for item in plan.get("filters") or []:
            for column in [item, *(item.get("columns") or [])]:
                if column.get("table") and column.get("column"):
                    asked.add((normalize_text(column["table"]), normalize_text(column["column"])))
        for item in plan.get("group_by") or []:
            if item.get("table") and item.get("column"):
                asked.add((normalize_text(item["table"]), normalize_text(item["column"])))
        kept = [
            item for item in board
            if (normalize_text(item.get("table")), normalize_text(item.get("column"))) not in asked
        ]
        if len(kept) != len(board):
            from src.semantic.visual_filters import filter_dax

            metric = dict(metric)
            expression = metric["base_dax_expression"]
            if kept:
                arguments = [filter_dax(item["table"], item["column"], item["condition"]) for item in kept]
                expression = "CALCULATE(" + expression + ", " + ", ".join(arguments) + ")"
            metric["dax_expression"] = expression
            metric["visual_filters"] = kept
            plan["metric"] = metric
            dropped = [item.get("column") for item in board if item not in kept]
            plan.setdefault("notes", []).append(
                "Filtro del tablero reemplazado por el de la pregunta: " + ", ".join(dict.fromkeys(dropped)) + "."
            )
        text = self.board_filters_text(metric)
        if text and text not in (plan.get("notes") or []):
            plan["notes"] = [*(plan.get("notes") or []), text]
        return plan
