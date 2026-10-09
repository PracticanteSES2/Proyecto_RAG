"""
Evaluación de las expectativas de un turno (tolerantes y verificables).

Cada turno del banco de preguntas trae un bloque `expect` (ver README.md). Este
módulo traduce ese bloque a una lista de comprobaciones:

    {"check": "route", "ok": True | False | None, "detail": "..."}

ok=None significa "no aplica" (p. ej. comprobar la métrica de una respuesta
que terminó en contrapregunta: ya falla la ruta, no se cuenta dos veces).

Además se aplican SIEMPRE unas prohibiciones por defecto (respuesta "None",
excepción, términos internos, respuesta vacía, cifras inventadas en RAG, ...),
que el caso puede ampliar con `forbid` o desactivar con `allow`.
"""
import re
from datetime import date

from .quality import (
    _NUMBER as NUMBER_RE,
    contains,
    extract_numbers,
    internal_terms,
    norm,
    spanish_ratio,
    unsupported_numbers,
    source_texts,
)

# Tipos de resultado de un turno (lo que se compara con expect["route"]).
KINDS = (
    "powerbi",          # dato de Power BI respondido
    "powerbi_empty",    # consulta válida sin datos para esos filtros
    "rag",              # respuesta documental
    "clarification",    # contrapregunta (con o sin botones)
    "out_of_scope",     # fuera del alcance de la documentación
    "not_found",        # «no encontré» (p. ej. tras «Ninguna de las anteriores»)
    "metric_not_resolved", "unsupported_filter", "powerbi_error",
    "dax_not_generated", "error", "otro",
)

DEFAULT_FORBID = (
    "none_text",            # la UI nunca muestra "None"
    "exception",            # el motor no lanza excepciones
    "internal_terms",       # sin "chunk", "embedding", "Qdrant", "prompt"...
    "empty_answer",         # siempre hay texto que mostrar
    "invented_numbers",     # en RAG: cifras que no están en las fuentes
    "english",              # respuestas largas en español
    "total_without_filter", # no dar un total ignorando un filtro pedido
)

GENERIC_FAILURES = (
    "No pude completar la consulta",
    "Ocurrió un error al procesar la consulta",
    "Power BI rechazó la consulta",
)

MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}


# ----------------------------------------------------------------------------
# Lectura del resultado
# ----------------------------------------------------------------------------


def classify(result):
    """Tipo de resultado de un turno (uno de KINDS)."""
    result = result or {}
    status = result.get("status")
    route = result.get("route")
    if status == "needs_clarification":
        return "clarification"
    if route == "out_of_scope":
        return "out_of_scope"
    if status == "success" and route == "rag":
        return "rag"
    if status == "success" and route == "powerbi":
        return "powerbi"
    if status == "empty_result":
        return "powerbi_empty"
    if status in ("not_found", "metric_not_resolved", "unsupported_filter",
                  "powerbi_error", "dax_not_generated", "error"):
        return status
    return "otro"


def as_list(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _plans(result):
    plans = []
    for plan in [result.get("query_plan"), *as_list(result.get("query_plans"))]:
        if isinstance(plan, dict) and plan not in plans:
            plans.append(plan)
    details = result.get("details")
    if isinstance(details, dict) and details.get("metric") and details not in plans:
        plans.append(details)
    return plans


def metric_texts(result):
    """Etiquetas, ids y medidas de las métricas que usó el turno."""
    texts = [result.get("metric"), result.get("metric_id")]
    for measure in as_list(result.get("measures")):
        if isinstance(measure, dict):
            texts.append(measure.get("label"))
    for plan in _plans(result):
        metric = plan.get("metric") or {}
        if isinstance(metric, dict):
            texts += [metric.get("label"), metric.get("metric_id"), metric.get("measure"),
                      metric.get("dax_expression")]
    return [str(t) for t in texts if t]


def model_texts(result):
    """Modelo semántico, informe y página de la respuesta."""
    texts = [result.get("semantic_model"), result.get("report"), result.get("dashboard")]
    for plan in _plans(result):
        texts += [plan.get("semantic_model"), plan.get("report"), plan.get("dashboard")]
        metric = plan.get("metric") or {}
        if isinstance(metric, dict):
            texts += [metric.get("semantic_model"), metric.get("report")]
    return [str(t) for t in texts if t]


def applied_filters(result):
    filters = list(as_list(result.get("filters")))
    for plan in _plans(result):
        for item in as_list(plan.get("filters")):
            if item not in filters:
                filters.append(item)
    return [f for f in filters if isinstance(f, dict)]


def unapplied_terms(result):
    terms = list(as_list(result.get("unapplied_terms")))
    for plan in _plans(result):
        terms += [t for t in as_list(plan.get("unapplied_terms")) if t not in terms]
    return [str(t) for t in terms if t]


def dax_text(result):
    parts = [result.get("dax"), *as_list(result.get("dax_queries"))]
    sim = result.get("_sim") or {}
    parts += [entry.get("dax") for entry in as_list(sim.get("dax_log")) if isinstance(entry, dict)]
    return " ".join(str(p) for p in parts if p)


def group_by_texts(result):
    texts = []
    for plan in [result, *_plans(result)]:
        for item in as_list(plan.get("group_by")):
            if isinstance(item, dict):
                texts += [item.get("column"), item.get("label"), item.get("table")]
            elif item:
                texts.append(item)
    share = (result.get("query_plan") or {}).get("share_dimension") or {}
    texts += [share.get("column"), share.get("label")]
    return [str(t) for t in texts if t]


def number_in(text, number):
    """True si `number` aparece en el texto (488.3, 488,3, 3.906,4, 12,5 %...)."""
    try:
        value = float(number)
    except (TypeError, ValueError):
        return contains(text, str(number))
    for token in NUMBER_RE.findall(str(text or "")):
        token = token.strip(".,")
        candidates = {token.replace(".", "").replace(",", "."), token.replace(",", "")}
        for candidate in candidates:
            try:
                if abs(float(candidate) - value) <= max(0.051, abs(value) * 1e-6):
                    return True
            except ValueError:
                continue
    return False


# ----------------------------------------------------------------------------
# Comprobaciones
# ----------------------------------------------------------------------------


def _check(name, ok, detail=""):
    return {"check": name, "ok": ok, "detail": detail}


def resolve_year(value):
    """Año esperado: entero, "actual" (año en curso) o "anterior" (año pasado)."""
    if isinstance(value, str):
        current = date.today().year
        relative = {"actual": current, "anterior": current - 1}
        if norm(value) in relative:
            return relative[norm(value)]
        return int(value)
    return value


def _filter_ok(spec, filters, dax):
    """¿El filtro esperado está aplicado? spec: {column?, value?} o {year?, month?}."""
    if "year" in spec or "month" in spec:
        year, month = resolve_year(spec.get("year")), spec.get("month")
        year_ok = year is None
        month_ok = month is None
        for item in filters:
            column = norm(item.get("column"))
            if item.get("type") == "date_range":
                if year is not None and item.get("year") == year:
                    year_ok = True
                if month is not None and item.get("month") == month:
                    month_ok = True
                continue
            value = item.get("value")
            if year is not None and column in ("ano", "anio", "year", "a o") and str(value) == str(year):
                year_ok = True
            if month is not None and column in ("mes", "month", "num mes", "mes num") and str(value) == str(month):
                month_ok = True
        if not (year_ok and month_ok) and dax:
            compact = dax.replace(" ", "")
            if year is not None and month is not None and f"DATE({year},{month}," in compact:
                year_ok = month_ok = True
            elif year is not None and month is None and f"DATE({year},1,1)" in compact:
                year_ok = True
        return year_ok and month_ok
    column, value = spec.get("column"), spec.get("value")
    for item in filters:
        if item.get("type") == "date_range":
            continue
        if column and not (contains(item.get("column"), column) or contains(item.get("concept"), column)
                           or contains(column, item.get("column") or "\x00")):
            continue
        if value is None or contains(item.get("value"), value) or contains(value, item.get("value") or "\x00"):
            return True
    return False


def _filter_label(spec):
    if "year" in spec or "month" in spec:
        return "periodo " + "-".join(str(spec[k]) for k in ("year", "month") if spec.get(k) is not None)
    return f"{spec.get('column') or '*'}={spec.get('value')}"


def _filter_declared(spec, ui, result):
    """El filtro no se aplicó pero la respuesta lo dice (no lo esconde)."""
    if "year" in spec or "month" in spec:
        words = [str(resolve_year(spec.get("year")) or "")]
        month = spec.get("month")
        words += [name for name, number in MONTHS.items() if number == month]
    else:
        words = [str(spec.get("value") or "")]
    low = norm(ui)
    declared_markers = ("no pude aplicar", "no entendi", "sin ese filtro", "no se aplic",
                        "se consideran todos", "no pude verificar")
    mentions = any(norm(w) and norm(w) in low for w in words)
    unapplied = any(contains(term, w) for term in unapplied_terms(result) for w in words if w)
    return (mentions and any(m in low for m in declared_markers)) or unapplied


def evaluate_turn(expect, result, ui, buttons, question="", forbid=(), allow=()):
    """Lista de comprobaciones de un turno."""
    expect = expect or {}
    result = result or {}
    kind = classify(result)
    checks = []

    # --- ruta / estado -------------------------------------------------------
    routes = as_list(expect.get("route"))
    if routes:
        checks.append(_check(
            "route", kind in routes,
            f"obtenido={kind} · esperado={'|'.join(routes)}",
        ))
    statuses = as_list(expect.get("status"))
    if statuses:
        checks.append(_check(
            "status", result.get("status") in statuses,
            f"obtenido={result.get('status')} · esperado={'|'.join(statuses)}",
        ))

    is_data = kind in ("powerbi", "powerbi_empty")

    # --- métrica / modelo ----------------------------------------------------
    metrics_any = as_list(expect.get("metrics_any"))
    if metrics_any:
        texts = metric_texts(result)
        if not is_data and not texts:
            checks.append(_check("metric", None, "sin dato de Power BI (no aplica)"))
        else:
            ok = any(contains(t, m) for t in texts for m in metrics_any)
            checks.append(_check(
                "metric", ok,
                f"métricas={texts[:4]} · aceptables={metrics_any}",
            ))
    models_any = as_list(expect.get("models_any"))
    if models_any:
        texts = model_texts(result)
        if not is_data and not texts:
            checks.append(_check("model", None, "sin dato de Power BI (no aplica)"))
        else:
            ok = any(contains(t, m) for t in texts for m in models_any)
            checks.append(_check("model", ok, f"modelo/informe={texts[:4]} · aceptables={models_any}"))

    # --- filtros -------------------------------------------------------------
    filters = applied_filters(result)
    dax = dax_text(result)
    missing_hidden = []
    for spec in as_list(expect.get("filters")):
        if not is_data:
            checks.append(_check(f"filter {_filter_label(spec)}", None, "sin dato de Power BI (no aplica)"))
            continue
        if _filter_ok(spec, filters, dax):
            checks.append(_check(f"filter {_filter_label(spec)}", True, "aplicado"))
        elif expect.get("allow_declared_filters", True) and _filter_declared(spec, ui, result):
            checks.append(_check(f"filter {_filter_label(spec)}", True, "no aplicado pero declarado en la respuesta"))
        else:
            missing_hidden.append(_filter_label(spec))
            applied = [(f.get("column"), f.get("value") if f.get("type") != "date_range"
                        else f"{f.get('year')}-{f.get('month')}") for f in filters]
            checks.append(_check(f"filter {_filter_label(spec)}", False, f"filtros aplicados={applied}"))

    group_any = as_list(expect.get("group_by_any"))
    if group_any:
        if not is_data:
            checks.append(_check("group_by", None, "sin dato de Power BI (no aplica)"))
        else:
            texts = group_by_texts(result)
            ok = any(contains(t, g) for t in texts for g in group_any)
            checks.append(_check("group_by", ok, f"agrupado por={texts[:4]} · aceptables={group_any}"))
    if expect.get("result_type"):
        if not is_data:
            checks.append(_check("result_type", None, "sin dato de Power BI (no aplica)"))
        else:
            checks.append(_check(
                "result_type", result.get("result_type") == expect["result_type"],
                f"obtenido={result.get('result_type')} · esperado={expect['result_type']}",
            ))

    # --- cifras esperadas ----------------------------------------------------
    for number in as_list(expect.get("numbers")):
        checks.append(_check(f"number {number}", number_in(ui, number), "en la respuesta mostrada"))

    # --- texto de la respuesta -----------------------------------------------
    answer_any = as_list(expect.get("answer_any"))
    if answer_any:
        found = [a for a in answer_any if contains(ui, a)]
        checks.append(_check("answer_any", bool(found), f"encontradas={found} de {answer_any}"))
    for needle in as_list(expect.get("answer_all")):
        checks.append(_check(f"answer_all «{needle}»", contains(ui, needle), ""))
    for needle in as_list(expect.get("answer_none")):
        checks.append(_check(f"answer_none «{needle}»", not contains(ui, needle), ""))

    # --- palabras clave (respuestas documentales) ----------------------------
    keywords = as_list(expect.get("keywords"))
    if keywords:
        if kind != "rag":
            checks.append(_check("keywords", None, f"respuesta no documental ({kind}): no aplica"))
        else:
            found = [k for k in keywords if contains(ui, k)]
            coverage = len(found) / len(keywords)
            minimum = float(expect.get("min_keyword_coverage", 0.5))
            checks.append(_check(
                "keywords", coverage >= minimum,
                f"cobertura={coverage:.0%} (mín {minimum:.0%}) · faltan={[k for k in keywords if k not in found]}",
            ))

    # --- contrapreguntas -----------------------------------------------------
    labels = [b.get("label") or "" for b in buttons or []]
    option_labels = [b.get("label") or "" for b in buttons or [] if str(b.get("id")) != "__none__"]
    captions = [b.get("caption") or "" for b in buttons or []]
    options_any = as_list(expect.get("options_any"))
    if options_any:
        if kind != "clarification":
            checks.append(_check("options", None, f"sin contrapregunta ({kind}): no aplica"))
        else:
            ok = any(contains(f"{lab} {cap}", o) for lab, cap in zip(labels, captions) for o in options_any)
            checks.append(_check("options", ok, f"botones={labels} · aceptables={options_any}"))
    if expect.get("min_options") is not None:
        if kind != "clarification":
            checks.append(_check("min_options", None, f"sin contrapregunta ({kind}): no aplica"))
        else:
            checks.append(_check(
                "min_options", len(option_labels) >= int(expect["min_options"]),
                f"{len(option_labels)} opciones (mín {expect['min_options']})",
            ))
    if expect.get("has_none_option") is not None:
        if kind != "clarification":
            checks.append(_check("has_none_option", None, f"sin contrapregunta ({kind}): no aplica"))
        else:
            has_none = any(str(b.get("id")) == "__none__" for b in buttons or [])
            checks.append(_check(
                "has_none_option", has_none == bool(expect["has_none_option"]),
                f"«Ninguna de las anteriores» presente={has_none}",
            ))
    prompt_any = as_list(expect.get("prompt_any"))
    if prompt_any:
        if kind not in ("clarification", "not_found"):
            checks.append(_check("prompt_any", None, f"sin contrapregunta ({kind}): no aplica"))
        else:
            found = [p for p in prompt_any if contains(ui, p)]
            checks.append(_check("prompt_any", bool(found), f"encontradas={found} de {prompt_any}"))

    # --- prohibiciones -------------------------------------------------------
    rules = [r for r in (*DEFAULT_FORBID, *as_list(forbid), *as_list(expect.get("forbid")))
             if r not in as_list(allow) and r not in as_list(expect.get("allow"))]
    rules = list(dict.fromkeys(rules))
    checks += evaluate_forbidden(rules, kind, result, ui, question, missing_hidden)
    return kind, checks


def evaluate_forbidden(rules, kind, result, ui, question, missing_hidden=()):
    checks = []
    text = str(ui or "")
    sim = result.get("_sim") or {}
    for rule in rules:
        if rule == "none_text":
            bad = re.search(r"\bNone\b", text) is not None
            checks.append(_check("forbid none_text", not bad, "la respuesta muestra «None»" if bad else ""))
        elif rule == "exception":
            exc = sim.get("exception")
            checks.append(_check("forbid exception", not exc, exc or ""))
        elif rule == "internal_terms":
            terms = internal_terms(text)
            checks.append(_check("forbid internal_terms", not terms, f"menciona {terms}" if terms else ""))
        elif rule == "empty_answer":
            checks.append(_check("forbid empty_answer", bool(text.strip()), "" if text.strip() else "respuesta vacía"))
        elif rule == "invented_numbers":
            if kind != "rag":
                continue
            evidence = source_texts(result) + [question]
            bad = unsupported_numbers(text, evidence)
            checks.append(_check(
                "forbid invented_numbers", not bad,
                f"cifras que no están en las fuentes: {bad}" if bad else "",
            ))
        elif rule == "english":
            if len(text.split()) < 8:
                continue
            ratio = spanish_ratio(text)
            bad = ratio is not None and ratio < 0.5
            checks.append(_check("forbid english", not bad, f"proporción español={ratio}" if bad else ""))
        elif rule == "total_without_filter":
            if kind != "powerbi" or not missing_hidden:
                continue
            checks.append(_check(
                "forbid total_without_filter", False,
                f"dio un dato sin aplicar ni avisar los filtros {missing_hidden}",
            ))
        elif rule == "numbers":
            # Para fuera de alcance / documental puro: no debe dar cifras.
            nums = [n for n in extract_numbers(text) if n not in extract_numbers(question)]
            checks.append(_check("forbid numbers", not nums, f"cifras={nums}" if nums else ""))
        elif rule == "generic_failure":
            bad = [g for g in GENERIC_FAILURES if g.lower() in text.lower()]
            checks.append(_check("forbid generic_failure", not bad, f"mensaje genérico: {bad}" if bad else ""))
        elif rule == "powerbi_answer":
            checks.append(_check("forbid powerbi_answer", kind != "powerbi", f"respondió con Power BI ({kind})"
                                 if kind == "powerbi" else ""))
        else:
            checks.append(_check(f"forbid {rule}", None, "prohibición desconocida (ignorada)"))
    return checks


def turn_passed(checks):
    """Un turno pasa si ninguna comprobación aplicable falla."""
    return all(c["ok"] is not False for c in checks)
