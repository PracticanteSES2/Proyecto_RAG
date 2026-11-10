"""Percentiles y resúmenes de las llamadas y los turnos medidos."""

OK = ("success", "empty_response")
TIMEOUT = ("llm_timeout", "timeout")


def percentil(values, p):
    """Percentil con interpolación lineal (como numpy por defecto)."""
    data = sorted(float(v) for v in values if v is not None)
    if not data:
        return None
    if len(data) == 1:
        return data[0]
    rank = (len(data) - 1) * float(p) / 100.0
    low = int(rank)
    high = min(low + 1, len(data) - 1)
    return data[low] + (data[high] - data[low]) * (rank - low)


def _r(value, digits=3):
    return None if value is None else round(value, digits)


def _rate(part, total):
    return round(part / total, 4) if total else 0.0


def resumen_llamadas(calls, wall_s):
    """Llamadas al LLM: [{status, latency_s, ttft_s?, truncated?, wait_s?, purpose?}]."""
    n = len(calls)
    ok = [c for c in calls if c.get("status") in OK]
    saturated = [c for c in calls if c.get("status") == "llm_saturated"]
    timeouts = [c for c in calls if c.get("status") in TIMEOUT]
    errors = [c for c in calls if c not in ok and c not in saturated and c not in timeouts]
    truncated = [c for c in ok if c.get("truncated")]
    latencies = [c.get("latency_s") for c in ok]
    ttfts = [c.get("ttft_s") for c in ok if c.get("ttft_s") is not None]
    waits = [c.get("wait_s") for c in calls if c.get("wait_s") is not None]
    by_purpose = {}
    for call in calls:
        entry = by_purpose.setdefault(call.get("purpose") or "otro", {"n": 0, "ok": 0})
        entry["n"] += 1
        entry["ok"] += call.get("status") in OK
    return {
        "n": n,
        "ok": len(ok),
        "saturadas": len(saturated),
        "tiempo_agotado": len(timeouts),
        "errores": len(errors),
        "truncadas": len(truncated),
        "tasa_saturadas": _rate(len(saturated), n),
        "tasa_tiempo_agotado": _rate(len(timeouts), n),
        "tasa_error": _rate(len(errors), n),
        "tasa_truncadas": _rate(len(truncated), len(ok)),
        "latencia_p50_s": _r(percentil(latencies, 50)),
        "latencia_p95_s": _r(percentil(latencies, 95)),
        "latencia_max_s": _r(max(latencies) if latencies else None),
        "ttft_p50_s": _r(percentil(ttfts, 50)),
        "ttft_p95_s": _r(percentil(ttfts, 95)),
        "espera_fila_p95_s": _r(percentil(waits, 95)),
        "throughput_ok_por_min": round(len(ok) / wall_s * 60.0, 2) if wall_s else 0.0,
        "por_uso": by_purpose,
        "errores_muestra": sorted({str(c.get("error") or c.get("status"))[:120] for c in errors})[:5],
    }


def resumen_turnos(turns, wall_s):
    """Turnos: [{status, total_s, wait_turn_s?, busy?, fallback?, degraded?}]."""
    n = len(turns)
    totals = [t.get("total_s") for t in turns if not t.get("busy")]
    waits = [t.get("wait_turn_s") for t in turns if t.get("wait_turn_s") is not None]
    busy = [t for t in turns if t.get("busy")]
    fallback = [t for t in turns if t.get("fallback")]
    degraded = [t for t in turns if t.get("degraded")]
    errors = [t for t in turns if t.get("status") == "error"]
    served = n - len(busy)
    return {
        "n": n,
        "atendidos": served,
        "total_p50_s": _r(percentil(totals, 50)),
        "total_p95_s": _r(percentil(totals, 95)),
        "total_max_s": _r(max(totals) if totals else None),
        "espera_turno_p50_s": _r(percentil(waits, 50)),
        "espera_turno_p95_s": _r(percentil(waits, 95)),
        "espera_turno_max_s": _r(max(waits) if waits else 0.0),
        "tasa_ocupado": _rate(len(busy), n),
        "tasa_respaldo_extractivo": _rate(len(fallback), n),
        "tasa_degradado": _rate(len(degraded), n),
        "tasa_error": _rate(len(errors), n),
        "turnos_por_min": round(served / wall_s * 60.0, 2) if wall_s else 0.0,
    }


def _max_overlap(intervals):
    events = []
    for start, end in intervals:
        if start is None or end is None or end <= start:
            continue
        events.append((start, 1))
        events.append((end, -1))
    current = best = 0
    for _, delta in sorted(events, key=lambda e: (e[0], e[1])):
        current += delta
        best = max(best, current)
    return best


def paralelismo_observado(calls):
    """Desde el cliente: cuántas llamadas exitosas estuvieron GENERANDO a la
    vez como máximo (del primer token al final; requiere el ttft del servidor,
    p. ej. --streaming o el simulado) y cuántas estuvieron dentro del servidor
    a la vez. Si el máximo generando se queda en P aunque haya más usuarios,
    el servidor atiende P en paralelo (OLLAMA_NUM_PARALLEL efectivo) y el
    resto espera en SU cola (primer token tardío)."""
    generating, inside = [], []
    for call in calls:
        if call.get("status") not in OK or call.get("t1_s") is None or call.get("duration_s") is None:
            continue
        end = call["t1_s"]
        start = end - call["duration_s"]
        inside.append((start, end))
        if call.get("ttft_srv_s") is not None:
            generating.append((start + call["ttft_srv_s"], end))
    if not inside:
        return None
    return {"generando_max": _max_overlap(generating) if generating else None,
            "en_servidor_max": _max_overlap(inside)}


def por_minuto(count, wall_s):
    return round(count / wall_s * 60.0, 2) if wall_s else 0.0


def _delta(after, before, *path):
    a, b = after, before
    for key in path:
        a, b = (a or {}).get(key, {}), (b or {}).get(key, {})
    if isinstance(a, dict):
        return {k: _delta(a, b, k) for k in a}
    return (a or 0) - (b if isinstance(b, (int, float)) else 0)


_COSTO = ("calls", "prompt_tokens_est", "num_predict", "eval_tokens")


def resumen_costo(antes, despues, n_turnos):
    """Dónde se gastó MedGemma en el escalón (diferencia de STATS.snapshot()):
    llamadas, tokens de entrada estimados, num_predict pedido y tokens
    generados, en total y por turno, más llamadas evitadas y la caché."""
    by_purpose = {
        purpose: {k: v for k, v in values.items() if k in _COSTO}
        for purpose, values in _delta(despues, antes, "llm_cost_by_purpose").items()
    }
    totals = {k: sum(v.get(k, 0) for v in by_purpose.values()) for k in _COSTO}
    per_turn = {f"{k}_por_turno": round(v / n_turnos, 2) if n_turnos else None for k, v in totals.items()}
    avoided = {k: v for k, v in _delta(despues, antes, "llm_avoided").items() if v}
    return {"por_uso": by_purpose, "total": totals, **per_turn, "evitadas": avoided,
            "evitadas_por_turno": round(sum(avoided.values()) / n_turnos, 2) if n_turnos else None,
            "cache": _delta(despues, antes, "llm_cache")}
