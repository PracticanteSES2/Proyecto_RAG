"""Presupuesto de tokens de las llamadas al LLM (MedGemma servido por Ollama).

`num_predict(proposito)`: tope de tokens de SALIDA por propósito, configurable con
`LLM_NUM_PREDICT_<PROPOSITO>` (valores y justificación en
specs/011-respuestas-truncadas/plan.md). `num_ctx()`: contexto del servidor
(`MEDGEMMA_NUM_CTX`, 4096). El cliente NO envía `num_ctx` (cambiarlo por
petición hace que Ollama recargue el modelo); solo se usa para no pasarse: si
el prompt + la salida no caben, Ollama recorta la ENTRADA en silencio.

`ajustar_a_contexto(construir, n_fuentes, salida)` reconstruye el prompt con
menos fuentes (quita primero las últimas = las menos relevantes) y, si con una
sola no cabe, recorta su texto; devuelve el recorte para la traza.

Los tokens se ESTIMAN por caracteres (`LLM_CARACTERES_POR_TOKEN`, 3.3:
conservador frente a los ~3,6 medidos en la síntesis). Calibrar con el
`prompt_eval_count` que devuelve `MedGemmaProvider.chat`.
"""
import math

from src.comun.entorno import env_float, env_int

NUM_PREDICT = {
    "sintesis": 600,       # síntesis RAG (≈ 30 s a 20 tok/s; tope de 40 s)
    "continuacion": 200,   # una continuación de una síntesis truncada
    "opciones": 60,        # una frase de ≤ 15 palabras por opción
    "reescritura": 80,     # una pregunta reescrita de ≤ 30 palabras
    "intencion": 160,      # JSON de intención
    "powerbi": 350,        # síntesis con valor de Power BI (ruta no conectada)
}
NUM_CTX_POR_DEFECTO = 4096
CARACTERES_POR_TOKEN = 3.3
# Tokens de la plantilla de chat: fijo + por mensaje (turnos, roles, BOS).
MARGEN_PLANTILLA = 64
TOKENS_POR_MENSAJE = 8
# Tokens por palabra de salida en español con Markdown (≈ 1,5 + 15 %): la
# extensión pedida deja holgura para no llegar a num_predict.
TOKENS_POR_PALABRA = 2.4


def num_predict(proposito: str) -> int:
    """Tope de salida del propósito (KeyError si no existe: nada de topes sueltos)."""
    defecto = NUM_PREDICT[proposito]
    return env_int(f"LLM_NUM_PREDICT_{proposito.upper()}", defecto)


def num_ctx() -> int:
    return env_int("MEDGEMMA_NUM_CTX", NUM_CTX_POR_DEFECTO)


def caracteres_por_token() -> float:
    return env_float("LLM_CARACTERES_POR_TOKEN", CARACTERES_POR_TOKEN)


def estimar_tokens(texto: str) -> int:
    return math.ceil(len(str(texto or "")) / caracteres_por_token())


def tokens_mensajes(mensajes: list[dict]) -> int:
    return sum(estimar_tokens(m.get("content")) + TOKENS_POR_MENSAJE for m in mensajes or [])


def entrada_maxima(salida: int, ctx: int | None = None) -> int:
    """Tokens de entrada que caben junto a `salida` tokens de respuesta."""
    return (ctx or num_ctx()) - int(salida) - MARGEN_PLANTILLA


def palabras_objetivo(salida: int) -> int:
    """Extensión que se pide en el prompt (múltiplo de 10)."""
    return max(10, int(salida / TOKENS_POR_PALABRA) // 10 * 10)


_CENTENAS = ("", "ciento", "doscientas", "trescientas", "cuatrocientas", "quinientas", "seiscientas",
             "setecientas", "ochocientas", "novecientas")
_DECENAS = ("", "diez", "veinte", "treinta", "cuarenta", "cincuenta", "sesenta", "setenta", "ochenta", "noventa")


def palabras_en_letras(n: int) -> str:
    """«doscientas cincuenta» para 250 (múltiplos de 10 hasta 990). La extensión
    va en letras en el prompt: una cifra ahí no es evidencia y el modelo podría
    copiarla en la respuesta."""
    n = int(n) // 10 * 10
    if not 10 <= n < 1000:
        return str(n)
    if n == 100:
        return "cien"
    centenas, decenas = divmod(n // 10, 10)
    return " ".join(p for p in (_CENTENAS[centenas], _DECENAS[decenas]) if p)


def ajustar_a_contexto(construir, n_fuentes: int, salida: int, ctx: int | None = None):
    """`construir(n, max_chars)` -> (contexto, mensajes) con las primeras `n`
    fuentes y, si `max_chars` no es None, el contexto recortado a ese largo.
    Devuelve (contexto, mensajes, recorte): recorte es None si cupo a la
    primera, o {"tokens_antes", "tokens_despues", "limite", "num_ctx",
    "fuentes_quitadas", "contexto_recortado"}."""
    ctx = ctx or num_ctx()
    limite = entrada_maxima(salida, ctx)
    n = max(1, int(n_fuentes))
    contexto, mensajes = construir(n, None)
    antes = tokens = tokens_mensajes(mensajes)
    if tokens <= limite:
        return contexto, mensajes, None
    while n > 1 and tokens > limite:
        n -= 1
        contexto, mensajes = construir(n, None)
        tokens = tokens_mensajes(mensajes)
    recortado = False
    if tokens > limite:
        sobra = math.ceil((tokens - limite) * caracteres_por_token()) + 1
        contexto, mensajes = construir(n, max(200, len(contexto) - sobra))
        tokens, recortado = tokens_mensajes(mensajes), True
    return contexto, mensajes, {
        "tokens_antes": antes, "tokens_despues": tokens, "limite": limite, "num_ctx": ctx,
        "fuentes_quitadas": max(0, int(n_fuentes) - n), "contexto_recortado": recortado,
    }


def extension_pedida(salida: int) -> str:
    """Extensión objetivo en letras para el prompt («doscientas cincuenta»)."""
    return palabras_en_letras(palabras_objetivo(salida))
