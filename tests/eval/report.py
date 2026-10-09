"""
Informe del evaluador: report.json (completo) y report.md (legible).

report.md contiene:
  1. resumen por categoría (todos los casos y solo los aplicables al arnés),
  2. métricas de calidad agregadas y latencias,
  3. fallos de los casos aplicables (pregunta, respuesta mostrada, botones,
     motivos y razonamiento completo del turno),
  4. fallos de los casos no aplicables (esperados con este arnés), igual de
     detallados pero al final.
"""
import json
import statistics
from pathlib import Path


def _pct(part, total):
    return 100.0 * part / total if total else 0.0


def _p95(values):
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]


def _stats(cases):
    turns = [t for c in cases for t in c.get("turns") or [] if not t.get("skipped")]
    checks = [k for t in turns for k in t.get("checks") or [] if k.get("ok") is not None]
    latencies = [t["latency_s"] for t in turns if t.get("latency_s") is not None]
    passed = sum(1 for c in cases if c.get("passed"))
    return {
        "cases": len(cases),
        "passed": passed,
        "fail": sum(1 for c in cases if c.get("outcome", "fail") == "fail"),
        "xfail": sum(1 for c in cases if c.get("outcome") == "xfail"),
        "xpass": sum(1 for c in cases if c.get("outcome") == "xpass"),
        "pct": _pct(passed, len(cases)),
        "checks": len(checks),
        "checks_ok": sum(1 for k in checks if k["ok"]),
        "checks_pct": _pct(sum(1 for k in checks if k["ok"]), len(checks)),
        "lat_mean": statistics.mean(latencies) if latencies else 0.0,
        "lat_p95": _p95(latencies),
        "lat_max": max(latencies) if latencies else 0.0,
    }


def _quality(cases):
    turns = [t for c in cases for t in c.get("turns") or [] if not t.get("skipped")]
    rag = [t for t in turns if t.get("kind") == "rag"]
    coverages = [t["quality"]["keyword_coverage"] for t in rag
                 if t.get("quality", {}).get("keyword_coverage") is not None]
    judge = [t["judge"]["score"] for t in turns
             if isinstance(t.get("judge"), dict) and isinstance(t["judge"].get("score"), (int, float))]
    return {
        "turns": len(turns),
        "rag_turns": len(rag),
        "kinds": {k: sum(1 for t in turns if t.get("kind") == k)
                  for k in sorted({t.get("kind") for t in turns if t.get("kind")})},
        "keyword_coverage_mean": statistics.mean(coverages) if coverages else None,
        "rag_with_unsupported_numbers": sum(1 for t in rag if t["quality"]["unsupported_numbers"]),
        "with_internal_terms": sum(1 for t in turns if t.get("quality", {}).get("internal_terms")),
        "not_spanish": sum(1 for t in turns
                           if (t.get("quality", {}).get("spanish_ratio") is not None
                               and t["quality"]["spanish_ratio"] < 0.5)),
        "rag_chars_mean": statistics.mean([t["quality"]["chars"] for t in rag]) if rag else None,
        "chars_mean": statistics.mean([t["quality"]["chars"] for t in turns]) if turns else None,
        "judge_mean": statistics.mean(judge) if judge else None,
        "with_none_text": sum(1 for t in turns if any(
            k["check"] == "forbid none_text" and k["ok"] is False for k in t.get("checks") or [])),
        "exceptions": sum(1 for t in turns if t.get("result", {}).get("exception")),
    }


def build_summary(results, categories):
    by_category = {}
    for key in categories:
        subset = [r for r in results if r["category"] == key]
        if subset:
            by_category[key] = {
                "all": _stats(subset),
                "applicable": _stats([r for r in subset if r.get("applicable")]),
            }
    return {
        "total": _stats(results),
        "applicable": _stats([r for r in results if r.get("applicable")]),
        "by_category": by_category,
        "quality": _quality(results),
    }


def _fmt(value, digits=2):
    return "-" if value is None else f"{value:.{digits}f}"


def _quote(text):
    lines = str(text or "(vacío)").splitlines() or ["(vacío)"]
    return "\n".join("> " + line if line.strip() else ">" for line in lines)


def _case_failure_md(case):
    out = []
    fuente = case.get("fuente") or {}
    out.append(f"### `{case['id']}` · {case['category']} · {case.get('tablero') or '-'}")
    if case.get("descripcion"):
        out.append(f"_{case['descripcion']}_")
    if case.get("xfail"):
        out.append(f"Fallo conocido (xfail): {case['xfail']}")
    if fuente.get("docx"):
        out.append(f"Fuente: `{fuente['docx']}`" + (f" — {fuente['seccion']}" if fuente.get("seccion") else ""))
    if case.get("runner_error"):
        out.append("**Error del evaluador:**\n\n```text\n" + case["runner_error"] + "\n```")
    for turn in case.get("turns") or []:
        mark = "OK" if turn.get("passed") else "FALLA"
        kind = "botón" if turn.get("input_type") == "button" else "texto"
        out.append(f"\n**Turno {turn['index']} {mark}** ({kind}): «{turn.get('input')}»")
        if turn.get("skipped"):
            out.append(f"- No se ejecutó: {turn.get('reason')}")
            if turn.get("available_buttons") is not None:
                out.append(f"- Botones disponibles: {turn.get('available_buttons')}")
            continue
        out.append(f"- Resultado: **{turn.get('kind')}** · latencia {turn.get('latency_s')} s")
        out.append("\nRespuesta mostrada:\n\n" + _quote(turn.get("ui")))
        if turn.get("buttons"):
            out.append("\nBotones: " + " · ".join(
                f"[{b.get('label')}]" + (f" ({b.get('caption')})" if b.get("caption") else "")
                for b in turn["buttons"]))
        failed = [k for k in turn.get("checks") or [] if k.get("ok") is False]
        if failed:
            out.append("\nMotivos del fallo:")
            out += [f"- `{k['check']}`: {k.get('detail') or ''}" for k in failed]
        q = turn.get("quality") or {}
        out.append(
            f"\nCalidad: {q.get('words')} palabras · cobertura clave {_fmt(q.get('keyword_coverage'))}"
            f" · cifras sin respaldo {q.get('unsupported_numbers') or '-'}"
            f" · términos internos {q.get('internal_terms') or '-'}"
        )
        if turn.get("judge"):
            out.append(f"Juez: {turn['judge']}")
        res = turn.get("result") or {}
        if res.get("exception"):
            out.append("\nExcepción:\n\n```text\n" + str(res.get("traceback") or res["exception"]) + "\n```")
        if turn.get("passed"):
            continue
        if turn.get("reasoning"):
            out.append("\n<details><summary>Razonamiento del turno</summary>\n\n```text\n"
                       + turn["reasoning"] + "\n```\n</details>")
        elif res:
            out.append("\n```json\n" + json.dumps(res, ensure_ascii=False, indent=2, default=str)[:3000] + "\n```")
    return "\n".join(out)


def render_markdown(meta, results, summary, categories):
    lines = [
        "# Evaluación del chatbot",
        "",
        f"- Fecha: {meta['fecha']}",
        f"- Arnés: **{meta['harness']}** · LLM: {meta['llm']} (estado {meta.get('llm_status')})",
        f"- Banco: `{meta['questions']}` · categorías: {meta['categories']}",
        f"- Tiempo: construcción {meta['build_s']} s · total {meta['elapsed_s']} s",
        f"- Juez LLM: {meta.get('judge') or 'desactivado'}",
        "",
        "Un caso es **aplicable** cuando su campo `arneses` incluye el arnés usado: con `sim` solo los casos que "
        "apuntan a los fixtures de tests/sim deberían pasar; el resto se ejecuta igual para vigilar que nada se "
        "rompa (excepciones, «None», términos internos) y su fallo es esperado.",
        "",
        "## Resumen por categoría",
        "",
        "| Categoría | Casos | Pasan | % | Comprob. OK | Aplicables | Pasan (apl.) | XFAIL (apl.) "
        "| % (apl.) | Lat. media s | Lat. p95 s |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for key, data in summary["by_category"].items():
        a, p = data["all"], data["applicable"]
        lines.append(
            f"| {key} — {categories.get(key, '')} | {a['cases']} | {a['passed']} | {a['pct']:.0f} | "
            f"{a['checks_ok']}/{a['checks']} ({a['checks_pct']:.0f} %) | {p['cases']} | {p['passed']} | "
            f"{p['xfail']} | {p['pct']:.0f} | {a['lat_mean']:.2f} | {a['lat_p95']:.2f} |"
        )
    t, p = summary["total"], summary["applicable"]
    lines.append(
        f"| **Total** | **{t['cases']}** | **{t['passed']}** | **{t['pct']:.0f}** | "
        f"{t['checks_ok']}/{t['checks']} ({t['checks_pct']:.0f} %) | **{p['cases']}** | **{p['passed']}** | "
        f"**{p['xfail']}** | **{p['pct']:.0f}** | {t['lat_mean']:.2f} | {t['lat_p95']:.2f} |"
    )
    q = summary["quality"]
    lines += [
        "",
        "## Calidad de las respuestas",
        "",
        f"- Turnos ejecutados: {q['turns']} · por tipo: "
        + ", ".join(f"{k}={v}" for k, v in q["kinds"].items()),
        f"- Respuestas documentales (RAG): {q['rag_turns']} · cobertura media de palabras clave: "
        f"{_fmt(q['keyword_coverage_mean'])} · longitud media {_fmt(q['rag_chars_mean'], 0)} caracteres",
        f"- RAG con cifras que no están en las fuentes (posible alucinación): {q['rag_with_unsupported_numbers']}",
        f"- Turnos que mencionan procesos internos (chunk, embedding, Qdrant, prompt...): {q['with_internal_terms']}",
        f"- Turnos que no parecen estar en español: {q['not_spanish']}",
        f"- Turnos que muestran «None»: {q['with_none_text']} · excepciones del motor: {q['exceptions']}",
        f"- Latencia por turno: media {t['lat_mean']:.2f} s · p95 {t['lat_p95']:.2f} s · máx {t['lat_max']:.2f} s",
        f"- Juez LLM (media): {_fmt(q['judge_mean'])}",
        "",
    ]

    applicable_fail = [r for r in results if r.get("applicable") and r.get("outcome", "fail") == "fail"]
    applicable_xfail = [r for r in results if r.get("applicable") and r.get("outcome") == "xfail"]
    other_fail = [r for r in results if not r.get("applicable") and not r.get("passed")]
    passed = [r for r in results if r.get("passed")]

    lines += [f"## Fallos nuevos en casos aplicables a «{meta['harness']}» ({len(applicable_fail)})", ""]
    if not applicable_fail:
        lines.append("Ninguno.")
    for case in applicable_fail:
        lines += [_case_failure_md(case), ""]

    lines += ["", f"## Fallos conocidos del chatbot (xfail) en casos aplicables ({len(applicable_xfail)})", "",
              "Comportamiento deseado que hoy falla por un bug real (marcado con `xfail` en el banco). "
              "Si uno pasa aparece como XPASS: quita la marca.", ""]
    if not applicable_xfail:
        lines.append("Ninguno.")
    for case in applicable_xfail:
        lines += [_case_failure_md(case), ""]

    lines += ["", f"## Casos que pasan ({len(passed)})", ""]
    lines += [f"- `{r['id']}` ({r['category']})" + (" — **XPASS**: quita la marca xfail"
                                                    if r.get("outcome") == "xpass" else "")
              for r in passed] or ["Ninguno."]

    lines += ["", f"## Fallos en casos no aplicables a «{meta['harness']}» ({len(other_fail)})", "",
              "Esperados con este arnés (el caso apunta a datos que el arnés no tiene). Útiles para "
              "ver cómo degrada el chatbot ante tableros desconocidos.", ""]
    for case in other_fail:
        lines += [_case_failure_md(case), ""]
    return "\n".join(lines) + "\n"


def write_reports(out_dir, meta, results, categories):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = build_summary(results, categories)
    payload = {"meta": meta, "summary": summary, "cases": results}
    (out_dir / "report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (out_dir / "report.md").write_text(
        render_markdown(meta, results, summary, categories), encoding="utf-8")
    return summary
