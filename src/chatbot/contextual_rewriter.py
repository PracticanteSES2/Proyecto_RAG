"""
Reescritura contextual: ¿el mensaje depende de lo conversado?

«Y en el mes pasado?», «necesito eso mismo pero de septiembre», «para el
comité, los de urgencias», «no, me refería a hospitalización», «¿cómo se
calcula ese indicador?», «compáralo con el año pasado», «ok, y el total?»... no
se entienden solos: completan, corrigen o preguntan por la respuesta anterior.

Este módulo tiene dos partes:

1. `analyze(mensaje)`: señales deterministas de dependencia del contexto
   (conector inicial, «eso mismo», demostrativos, elipsis «los de X»,
   corrección, comparación, total, «¿por qué?», volver a un tema) y el
   complemento del mensaje sin esas frases, con sus mayúsculas y tildes
   («de septiembre», «de urgencias»). No decide nada sobre indicadores ni
   filtros: eso lo hace QueryEngine con el Query Plan y la memoria.

2. `LLMContextRewriter`: si las reglas no bastan, pide a MedGemma la pregunta
   autónoma (prompt corto con los últimos turnos) y la valida: una sola
   pregunta, sin cifras ni indicadores que no estén en el historial o en el
   mensaje, sin palabras de contenido inventadas.
"""
import re
import time

from src.llm.llm_gate import call_llm
from src.semantic.request_phrases import fold


# ---------------------------------------------------------------------------
# Señales deterministas
# ---------------------------------------------------------------------------

_B = r"(?<![a-z0-9])"
_E = r"(?![a-z0-9])"

_COURTESY_WORDS = (
    r"ok|okay|okey|vale|bueno|listo|perfecto|entendido|gracias|muchas\s+gracias|muy\s+bien|"
    r"de\s+acuerdo|genial|excelente|super|ah|oye|mira|hola|buenas|buenos\s+dias|buenas\s+tardes"
)
_COURTESY_ONLY_RE = re.compile(r"^\s*(?:(?:" + _COURTESY_WORDS + r")\s*)+$")
_COURTESY_LEAD_RE = re.compile(r"^\s*(?:(?:" + _COURTESY_WORDS + r")\s+)+(?=\S)")
_LEAD_RE = re.compile(r"^\s*(?:y|e|entonces|pero|tambien|igual|ahora|y\s+ahora|y\s+tambien)" + _E)
_PURPOSE_RE = re.compile(
    r"^\s*(?:(?:es|son|seria|lo\s+necesito|los\s+necesito|las\s+necesito)\s+)?para\s+"
    r"(?:el|la|los|las|un|una|mi|nuestro|nuestra)\s+"
    r"(?:comite|junta|reunion|informe|reporte|gerencia|direccion|presentacion|auditoria|jefe|jefa|"
    r"coordinador|coordinadora|coordinacion|subgerencia|comite\s+de\s+calidad)" + _E
)
_REQUEST_LEAD_RE = re.compile(
    r"^\s*(?:(?:necesito|necesitamos|quiero|quisiera|queria|requiero|me\s+das|me\s+da|me\s+pasas|"
    r"dame|damelo|damela|muestrame|mostrame|ensename|pasame|regalame|ver|veamos|mostrar|"
    r"puedes\s+(?:darme|mostrarme|sacar)|podrias\s+(?:darme|mostrarme|sacar)|saca|sacame)\s+)+"
)
_SAME_RE = re.compile(
    _B + r"(?:(?:eso|esto|lo|la|el|los|las)\s+mism[oa]s?"
    r"|(?:la|lo)\s+misma?\s+(?:consulta|pregunta|tabla|cifra|dato|informacion)"
    r"|igual(?=\s+(?:pero|para|en|de|del|con|sin|por)\s)"
    r"|lo\s+anterior|la\s+(?:consulta|pregunta|tabla)\s+anterior|otra\s+vez|de\s+nuevo)" + _E
)
_REFERENCE_RE = re.compile(
    _B + r"(?:(?:es[eao]s?|est[eao]s?|aquel(?:l[oa]s?)?)\s+(?:indicador(?:es)?|datos?|cifras?|valor(?:es)?|"
    r"numeros?|resultados?|tablas?|tableros?|paginas?|informes?|reportes?|medidas?|porcentajes?|"
    r"totale?s?|calculos?|consultas?)"
    r"|eso|esto|ello)" + _E
)
_ONLY_RE = re.compile(_B + r"(?:solo|solamente|unicamente|nada\s+mas)" + _E)
_PERO_RE = re.compile(_B + r"pero(?=\s+(?:de|del|en|para|con|sin|por|solo|solamente|ahora|ya|ese|esa)" + _E + r")")
# «los de urgencias», «solo las de Sura», «el de hospitalización»: artículo sin
# sustantivo = elipsis del indicador anterior.
_ELLIPSIS_RE = re.compile(r"^\s*(?P<art>(?:l[oa]s?|el))\s+(?=(?:de|del|en|con|sin|para|que)" + _E + r")")
_CORRECTION_RE = re.compile(
    r"^\s*(?:(?:no\s+)+(?:(?P<verb>me\s+referia|me\s+refiero|quise\s+decir|queria\s+decir|quiero\s+decir|"
    r"hablaba\s+de|preguntaba\s+por|pregunte\s+por|era|es|mejor)\s+)?"
    r"|(?P<verb2>me\s+referia|me\s+refiero|quise\s+decir|queria\s+decir|perdon|disculpa|corrijo)\s+)"
    r"(?:a\s+(?:l[oa]s?\s+)?|al\s+)?(?=\S)"
)
_CORRECTION_REST_START = re.compile(r"^\s*(?:de|del|en|para|por|el|la|los|las|sin|con|solo|solamente)" + _E)
_COMPARE_RE = re.compile(
    _B + r"(?:compar(?:a|ar|alo|ala|alos|alas|e|emos|ado|ada|ados|adas|ando|acion|ativo)"
    r"(?:\s+(?:lo|la|los|las|eso|esto))?\s+(?:con|contra|frente\s+a|vs)"
    r"|frente\s+a(?:l)?|versus|vs|respecto\s+a(?:l)?|en\s+comparacion\s+con)\s+(?P<target>.+)$"
)
_TOTAL_RE = re.compile(
    _B + r"(?:(?:(?:el|en|un|al|del)\s+)?total(?:\s+general)?|sin\s+(?:desglos[a-z]*|agrupar|discriminar|separar)"
    r"|todo\s+junto|(?:el\s+)?consolidado)" + _E
)
_WHY_RE = re.compile(
    r"^\s*(?:(?:y|pero|entonces|ok|bueno)\s+)*(?:por\s*que|a\s+que\s+se\s+debe|como\s+asi|como\s+es\s+posible|"
    r"como\s+se\s+explica)" + _E
)
_REGRESO_RE = re.compile(
    _B + r"(?:(?:volv(?:iendo|amos|er|emos|ia)|regres(?:ando|emos|ar|amos)|retom(?:ando|emos|ar|amos))"
    r"\s+(?:a|al|con)(?:\s+(?:lo|la|el|los|las)\s+de)?(?:\s+(?:lo|la|el|los|las))?"
    r"|lo\s+de(?:\s+(?:la|el|los|las))?(?=\s+[a-z]))" + _E
)
_INTERROGATIVE_RE = re.compile(
    r"^\s*(?:cuant[oa]s?|que|cual(?:es)?|como|donde|cuando|quien(?:es)?|por\s+que|para\s+que)" + _E
)


def norm(text):
    """Minúsculas, sin tildes ni signos, espacios simples."""
    return re.sub(r"\s+", " ", fold(text)).strip()


def _cleanup(text):
    text = re.sub(r"\s+([,;?.!])", r"\1", str(text or ""))
    text = re.sub(r"\s{2,}", " ", text)
    text = text.strip(" ,;:.-")
    text = re.sub(r"^[¿¡\s]+|[?!\s]+$", "", text)
    return text.strip(" ,;:.-")


class _Masked:
    """Texto original + copia plegada de la misma longitud; las frases que se
    quitan se enmascaran (espacios) en ambas, de modo que el complemento
    conserva mayúsculas y tildes."""

    def __init__(self, text):
        self.original = str(text or "")
        self.folded = list(fold(self.original))
        self.mask = [False] * len(self.original)

    @property
    def current(self):
        return "".join(" " if self.mask[i] else ch for i, ch in enumerate(self.folded))

    def remove(self, start, end):
        for index in range(max(0, start), min(len(self.mask), end)):
            self.mask[index] = True

    def take(self, pattern, group=0):
        """Enmascara la primera coincidencia y la devuelve (texto plegado) o None."""
        match = pattern.search(self.current)
        if not match:
            return None
        start, end = match.span(group)
        self.remove(start, end)
        return match

    def take_all(self, pattern):
        found = []
        while True:
            match = pattern.search(self.current)
            if not match or match.end() == match.start():
                return found
            self.remove(*match.span())
            found.append(" ".join(match.group(0).split()))

    def text(self, start=0, end=None):
        end = len(self.original) if end is None else end
        return _cleanup("".join(
            " " if self.mask[i] else self.original[i] for i in range(start, end)
        ))


def analyze(message):
    """Señales de dependencia del contexto de `message`.

    Devuelve un dict con:
      cues        lista de señales («conector», «lo mismo», «referencia»,
                  «elipsis», «solo», «corrección», «comparación», «total»,
                  «por qué», «volver a un tema», «propósito»)
      references  demostrativos encontrados («ese indicador», «eso»)
      correction  texto corregido («hospitalización») o None
      compare     objetivo de la comparación («el año pasado») o None
      total       pide el total (sin desglose)
      why         «¿por qué ...?»
      regreso     «volviendo a ...», «lo de ...»
      courtesy    el mensaje es solo cortesía («gracias», «ok»)
      complement  el mensaje sin esas frases, con sus tildes («de septiembre»)
      interrogative  el complemento empieza con un interrogativo
    """
    text = str(message or "")
    masked = _Masked(text)
    cues, references = [], []
    result = {
        "cues": cues, "references": references, "correction": None, "compare": None,
        "total": False, "why": False, "regreso": False, "courtesy": False,
        "complement": "", "complement_norm": "", "interrogative": False,
    }
    if not norm(text):
        return result
    if _COURTESY_ONLY_RE.match(norm(text)):
        result["courtesy"] = True
        return result

    masked.take(_COURTESY_LEAD_RE)
    if _WHY_RE.match(masked.current):
        result["why"] = True
        cues.append("por qué")
    # Corrección: «no, me refería a hospitalización», «no, el de urgencias».
    correction = _CORRECTION_RE.match(masked.current)
    if correction and correction.end() < len(masked.current.rstrip()):
        rest = masked.current[correction.end():]
        if correction.group("verb") or correction.group("verb2") or _CORRECTION_REST_START.match(rest):
            masked.remove(0, correction.end())
            cues.append("corrección")
            result["correction"] = masked.text()
    if masked.take(_LEAD_RE):
        cues.append("conector")
    if masked.take(_PURPOSE_RE):
        cues.append("propósito")
    masked.take(_REQUEST_LEAD_RE)
    compare = masked.take(_COMPARE_RE)
    if compare:
        result["compare"] = _cleanup(text[compare.start("target"): compare.end("target")])
        cues.append("comparación")
    if masked.take_all(_SAME_RE):
        cues.append("lo mismo")
    if masked.take_all(_REGRESO_RE):
        result["regreso"] = True
        cues.append("volver a un tema")
    found = masked.take_all(_REFERENCE_RE)
    if found:
        references.extend(found)
        cues.append("referencia")
    if masked.take_all(_PERO_RE):
        cues.append("pero")
    masked.take(_REQUEST_LEAD_RE)
    if masked.take_all(_ONLY_RE):
        cues.append("solo")
    masked.take(_LEAD_RE)
    ellipsis = masked.take(_ELLIPSIS_RE, group="art")
    if ellipsis:
        cues.append("elipsis")
    if masked.take_all(_TOTAL_RE):
        result["total"] = True
        cues.append("total")
    result["complement"] = masked.text()
    result["complement_norm"] = norm(result["complement"])
    result["interrogative"] = bool(_INTERROGATIVE_RE.match(result["complement_norm"]))
    # Una pregunta interrogativa con conector inicial («y cuántos hubo en
    # 2025?») también depende del contexto si no nombra indicador: lo decide
    # QueryEngine. Aquí solo se registran las señales.
    return result


def depends_on_context(analysis):
    return bool(analysis.get("cues"))


# ---------------------------------------------------------------------------
# Reescritura con el LLM (respaldo)
# ---------------------------------------------------------------------------

_STOP = {
    "el", "la", "los", "las", "lo", "un", "una", "unos", "unas", "de", "del", "en", "y", "e", "o", "a", "al",
    "por", "para", "con", "sin", "que", "cual", "cuales", "cuanto", "cuanta", "cuantos", "cuantas", "como",
    "cuando", "donde", "es", "son", "fue", "fueron", "hay", "hubo", "se", "su", "sus", "me", "mi", "le",
    "les", "nos", "este", "esta", "ese", "esa", "estos", "estas", "esos", "esas", "eso", "esto", "mes",
    "ano", "dia", "semana", "total", "valor", "cantidad", "numero", "indicador", "tablero", "pagina",
    "dato", "datos", "pregunta", "calcula", "calcular", "significa", "mide", "muestra", "tiene", "tienen",
    "tuvo", "registro", "registraron", "comparado", "compara", "comparar", "frente", "anterior", "pasado",
    "pasada", "actual", "mismo", "misma", "solo", "cada", "segun", "entre", "sobre", "mas", "menos",
    "cuantos", "porque", "por que", "explica", "obtiene", "periodo", "mismo periodo", "ultimo", "ultima",
}


class LLMContextRewriter:
    """Pide a MedGemma la pregunta autónoma equivalente al último mensaje."""

    SYSTEM_PROMPT = """
Eres el módulo de comprensión de un asistente que consulta tableros de Power BI de gestión clínica.
Reescribe el ÚLTIMO MENSAJE del usuario como UNA pregunta completa que se entienda sin la conversación.

REGLAS OBLIGATORIAS:
1. Usa la conversación para completar lo que el mensaje deja implícito (indicador, tablero, filtros, periodo, agrupación).
2. Usa solo indicadores, tableros, filtros y periodos que aparezcan en la conversación o en el mensaje. No inventes cifras ni datos.
3. Si el mensaje ya es una pregunta completa e independiente, devuélvelo igual.
4. No respondas la pregunta. Responde SOLO con la pregunta reescrita, en una línea, en español.

EJEMPLOS
Usuario: ¿Cuántas cirugías programadas hubo en 2024?
Asistente: CIRUGÍAS PROGRAMADAS: 6.803. Filtros: 2024
ÚLTIMO MENSAJE: y las de urología?
¿Cuántas cirugías programadas de urología hubo en 2024?
""".strip()

    def __init__(self, llm_provider, timeout=8.0, max_words=40, max_new_words=2):
        self.llm_provider = llm_provider
        self.timeout = timeout
        self.max_words = max_words
        self.max_new_words = max_new_words

    def build_messages(self, message, transcript):
        user = (
            "CONVERSACIÓN:\n" + (transcript or "(sin turnos previos)")
            + f"\n\nÚLTIMO MENSAJE: {message}\n\nPregunta reescrita:"
        )
        return [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ]

    def _chat(self, messages):
        """Llamada con tiempo límite real (src/llm/llm_gate.py): al vencer se
        cierra la conexión con MedGemma. Si el servidor está saturado se
        espera como mucho 1 s por un hueco: la reescritura es opcional."""
        timeout = self.timeout if self.timeout and self.timeout > 0 else None
        response = call_llm(
            self.llm_provider, messages, purpose="reescritura contextual",
            timeout=timeout, queue_wait=min(1.0, timeout) if timeout else 1.0,
            temperature=0.0, max_tokens=80, think=False,
        )
        if response.get("status") == "llm_timeout":
            # Nombre histórico del estado (lo muestra el razonamiento).
            response = dict(response, status="timeout")
        return response

    @staticmethod
    def clean(answer):
        """Primera línea útil, sin comillas, prefijos ni markdown."""
        for line in str(answer or "").splitlines():
            line = re.sub(r"[*_`#>]+", "", line).strip()
            line = re.sub(r"^(?:pregunta\s+reescrita|pregunta|reescritura|respuesta)\s*:\s*", "", line,
                          flags=re.IGNORECASE)
            line = line.strip().strip("\"'«»“”").strip()
            if line:
                return line
        return ""

    def validate(self, question, message, allowed_text, metric_words=None, metric_text=None,
                 required_text=None):
        """(válida, motivo). `allowed_text`: historial + mensaje; `metric_words(texto)`
        devuelve las palabras de un texto que nombran indicadores del catálogo;
        `metric_text`: de dónde pueden salir los indicadores (lo que dijo el
        usuario y los indicadores consultados, no la prosa del asistente: una
        respuesta documental puede nombrar otros indicadores); `required_text`:
        lo que agrega el mensaje («de hospitalización»), que la reescritura no
        puede perder."""
        words = norm(question).split()
        if len(words) < 3:
            return False, "respuesta demasiado corta"
        if len(words) > self.max_words:
            return False, "respuesta demasiado larga"
        if norm(question) == norm(message):
            return False, "devolvió el mismo mensaje"
        allowed_words = set(norm(allowed_text).split())

        def known(word):
            return (
                word in allowed_words or word.rstrip("s") in allowed_words
                or f"{word}s" in allowed_words or f"{word}es" in allowed_words
            )

        numbers = [w for w in words if any(ch.isdigit() for ch in w)]
        invented_numbers = [w for w in numbers if w not in allowed_words]
        if invented_numbers:
            return False, f"introduce cifras que no estaban en la conversación ({', '.join(invented_numbers)})"
        # Lo que agrega el mensaje no puede desaparecer: al menos una de sus
        # palabras de contenido sigue en la reescritura («los de hospitalización»
        # no puede volverse «¿cuántos ingresos hubo en 2025?»). Basta una: el
        # usuario dice «lo que operaron los colegas de urología» y la
        # reescritura correcta conserva solo «urología».
        question_words = set(words)
        content = [
            w for w in norm(required_text).split()
            if len(w) >= 4 and w not in _STOP and not w.isdigit()
        ] if required_text else []
        if content and not any(
            w in question_words or w.rstrip("s") in question_words or f"{w}s" in question_words
            or f"{w}es" in question_words for w in content
        ):
            return False, f"omite lo que agrega el mensaje ({', '.join(content[:5])})"
        metric_allowed = set(norm(metric_text).split()) if metric_text is not None else allowed_words

        def known_metric(word):
            return (
                word in metric_allowed or word.rstrip("s") in metric_allowed
                or f"{word}s" in metric_allowed or f"{word}es" in metric_allowed
            )

        if callable(metric_words):
            try:
                named = metric_words(question) or []
            except Exception:
                named = []
            invented = [w for w in named if not known_metric(w)]
            if invented:
                return False, f"introduce indicadores que no estaban en la conversación ({', '.join(invented)})"
        new_words = [
            w for w in words
            if len(w) >= 4 and w not in _STOP and not known(w) and not w.isdigit()
        ]
        if len(new_words) > self.max_new_words:
            return False, f"agrega palabras que no estaban en la conversación ({', '.join(new_words[:5])})"
        return True, None

    def rewrite(self, message, transcript, allowed_text, metric_words=None, metric_text=None,
                required_text=None):
        started = time.perf_counter()
        response = self._chat(self.build_messages(message, transcript))
        elapsed = round(time.perf_counter() - started, 2)
        if response.get("status") != "success":
            return {"status": response.get("status") or "error", "question": None,
                    "reason": response.get("error") or response.get("status"), "elapsed": elapsed}
        question = self.clean(response.get("answer"))
        ok, reason = self.validate(
            question, message, f"{allowed_text} {message}", metric_words,
            metric_text=None if metric_text is None else f"{metric_text} {message}",
            required_text=required_text,
        )
        if not ok:
            return {"status": "rejected", "question": question or None, "reason": reason, "elapsed": elapsed}
        return {"status": "success", "question": question, "reason": None, "elapsed": elapsed}
