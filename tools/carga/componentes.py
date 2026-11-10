"""
Modo `componentes`: turnos que pasan por los componentes REALES del motor que
llaman a MedGemma (`AnswerSynthesizer.synthesize_rag`, `OptionDescriber.describe`
y la reescritura contextual), con la caché del motor y la descripción desde el
catálogo, contra el servidor simulado (o el real con --real). Mide las palancas
de specs/010-rendimiento-llm antes (`--sin-palancas`: LLM_CACHE=off y
OPTION_DESCRIBER_CATALOGO=off) y después.

Supuestos (calíbralos con el registro real de preguntas cuando exista):

  * Banco de 40 preguntas documentales; 30 indicadores repartidos en 15
    contrapreguntas de 3 opciones que se solapan. La popularidad sigue una ley
    de Zipf (s=1): pocas preguntas se repiten mucho («¿qué muestra el tablero
    X?») y la mayoría poco. `--banco` cambia el tamaño (más grande = menos
    repetición).
  * Contexto de síntesis de 5 fuentes de ~250 caracteres (mediana real en
    data/rag/knowledge_chunks.json: 184; p90: 437).
  * `--catalogo-documentado` (0..1, por defecto 0): fracción de indicadores con
    descripción suficiente en el catálogo. Hoy, en master_metrics.json, ninguno.
  * La caché empieza vacía en cada escalón (supuesto conservador: en un día
    real se va llenando).
"""
import random
import threading
import time
from contextlib import nullcontext
from functools import lru_cache

from tools.carga import escenarios, metricas

PROPOSITO_POR_TOKENS = {600: "síntesis RAG", 80: "reescritura contextual", 60: "descripción de opciones"}
TABLEROS = 8
INDICADORES = 30
CONTRAPREGUNTAS = 15
_FRASE = ("El indicador {i} del tablero {t} cuenta los registros de la tabla de hechos {k} en el periodo "
          "seleccionado y se filtra por servicio y especialidad; la fuente {k} lo describe. ")


@lru_cache(maxsize=16)
def _pesos(n, s=1.0):
    return [1.0 / (rank ** s) for rank in range(1, n + 1)]


def zipf(rng, n):
    return rng.choices(range(n), weights=_pesos(n))[0]


def pregunta(i):
    return f"¿Qué mide el indicador {i} del tablero {i % TABLEROS}?"


def fuentes(i):
    t = i % TABLEROS
    return [{"text": _FRASE.format(i=i, t=t, k=k), "dashboard": f"TABLERO {t}", "chunk_type": "indicator",
             "semantic_model": f"INFORME {t}", "score": 0.8 - 0.05 * k, "intent": "definition"}
            for k in range(5)]


def opcion(j, documentado):
    tabla = f"TABLA {j % 10}"
    return {
        "id": f"m{j}", "label": f"INDICADOR {j}", "measure": f"INDICADOR {j}", "table": tabla,
        "dax_expression": f"COUNTROWS('{tabla}')",
        "description": (f"Cuenta los registros de {tabla.lower()} que cumplen la condición número {j} del tablero "
                        f"{j % TABLEROS}." if documentado else ""),
    }


def contrapregunta(k, documentados):
    ids = sorted({(3 * k) % INDICADORES, (3 * k + 7) % INDICADORES, (3 * k + 13) % INDICADORES})
    return [opcion(j, j in documentados) for j in ids]


class Grabadora:
    """Envuelve al proveedor y anota cada llamada que llega al servidor (como
    runner._Llamador), con el propósito deducido de `max_tokens`."""

    enforces_timeout = True

    def __init__(self, provider, escala):
        self.provider = provider
        self.escala = escala
        self.model = getattr(provider, "model", "simulado")
        self.records = []
        self.t_ref = time.perf_counter()
        self._lock = threading.Lock()

    def chat(self, messages, max_tokens=450, **kwargs):
        started = time.perf_counter()
        result = self.provider.chat(messages, max_tokens=max_tokens, **kwargs)
        latency = (time.perf_counter() - started) / self.escala
        t0 = (started - self.t_ref) / self.escala
        duration = result.get("duration_s")
        with self._lock:
            self.records.append({
                "purpose": PROPOSITO_POR_TOKENS.get(max_tokens, "otro"), "status": result.get("status"),
                "latency_s": round(latency, 3), "truncated": bool(result.get("truncated")),
                "done_reason": result.get("done_reason"), "error": result.get("error"),
                "t0_s": round(t0, 3), "t1_s": round(t0 + latency, 3),
                "duration_s": None if duration is None else round(float(duration), 3),
                "ttft_srv_s": result.get("ttft_s"), "ttft_s": result.get("ttft_s"),
            })
        return result


class Turnos:
    def __init__(self, grabadora, escala, banco=40, catalogo_documentado=0.0, semilla=7):
        from src.chatbot.answer_synthesizer import DEFAULT_SYNTHESIS_TIMEOUT, AnswerSynthesizer
        from src.chatbot.contextual_rewriter import LLMContextRewriter
        from src.chatbot.option_describer import OptionDescriber

        self.grabadora = grabadora
        self.escala = escala
        self.banco = banco
        self.sintetizador = AnswerSynthesizer(grabadora, timeout_seconds=DEFAULT_SYNTHESIS_TIMEOUT * escala)
        self.descriptor = OptionDescriber(grabadora, timeout=15.0 * escala)
        self.reescritor = LLMContextRewriter(None)
        # El vocabulario del normalizador (claves de la caché) se arma una vez
        # por proceso: fuera de la medición.
        from src.semantic.question_normalizer import clave_pregunta
        clave_pregunta(pregunta(0))
        rng = random.Random(f"catalogo-{semilla}")
        self.documentados = {j for j in range(INDICADORES) if rng.random() < catalogo_documentado}

    def _sintetizar(self, rng, history=None):
        i = zipf(rng, self.banco)
        kwargs = {"history": history} if history else {}
        result = self.sintetizador.synthesize_rag(pregunta(i), fuentes(i), **kwargs)
        return result.get("status") == "success", i

    def sintesis(self, rng):
        ok, _ = self._sintetizar(rng)
        return {"fallback": not ok, "redactada": ok}

    def seguimiento(self, rng):
        from src.llm.llm_gate import call_llm

        messages = self.reescritor.build_messages("y en urgencias?", "Usuario: " + pregunta(zipf(rng, self.banco)))
        call_llm(self.grabadora, messages, purpose="reescritura contextual", timeout=8.0 * self.escala,
                 queue_wait=1.0 * self.escala, temperature=0.0, max_tokens=80, think=False)
        history = [{"role": "user", "text": pregunta(zipf(rng, self.banco))},
                   {"role": "assistant", "text": "El indicador cuenta registros del periodo."}]
        ok, _ = self._sintetizar(rng, history)
        return {"fallback": not ok, "redactada": ok}

    def opciones(self, rng):
        k = zipf(rng, CONTRAPREGUNTAS)
        result = self.descriptor.describe("¿cuál indicador?", contrapregunta(k, self.documentados))
        return {"fallback": False, "degraded": result.get("status") not in ("success", "catalog")}

    def powerbi(self, rng):
        return {"fallback": False}


def nivel(usuarios, turnos, perfil, ctx, semilla, pausa, espera_ui, arrancar):
    """(llamadas, turnos, segundos) de un escalón; `ctx` = Turnos."""
    from src.chatbot import cache_llm
    from src.chatbot.runtime_stats import STATS
    from src.llm.llm_gate import ui_progress

    cache_llm.configurar_almacen(cache_llm.AlmacenMemoria())
    filas, lock = [], threading.Lock()
    first = len(ctx.grabadora.records)
    saturated_before = STATS.snapshot()["llm"]["saturated"]
    ctx.grabadora.t_ref = time.perf_counter()

    def usuario(index):
        rng = escenarios.nuevo_rng(semilla, index)
        context = ui_progress(queue_wait=espera_ui * ctx.escala) if espera_ui else nullcontext()
        with context:
            for number in range(turnos):
                kind = escenarios.elegir_turno(perfil, rng)
                started = time.perf_counter()
                row = getattr(ctx, kind)(rng)
                row.update(usuario=index + 1, turno=number + 1, tipo=kind, status="ok",
                           total_s=round((time.perf_counter() - started) / ctx.escala, 3))
                row["degraded"] = row.get("degraded") or row["fallback"]
                with lock:
                    filas.append(row)
                if pausa:
                    time.sleep(pausa * ctx.escala)

    wall = arrancar(usuarios, usuario) / ctx.escala
    calls = list(ctx.grabadora.records[first:])
    saturated = STATS.snapshot()["llm"]["saturated"] - saturated_before
    calls += [{"purpose": "saturada", "status": "llm_saturated"}] * max(0, saturated)
    return calls, filas, wall


def redactadas_por_min(filas, wall_s):
    return metricas.por_minuto(sum(1 for f in filas if f.get("redactada")), wall_s)
