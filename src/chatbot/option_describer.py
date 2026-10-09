import re
import time


class OptionDescriber:
    """
    Pide al LLM una descripción corta de lo que consultaría cada opción de
    una contrapregunta («qué obtendrías de este indicador en este tablero»).

    Una sola llamada para todas las opciones. Si el LLM falla, no responde o
    no describe alguna opción, esa opción conserva la descripción del
    catálogo (la decide QueryEngine).
    """

    SYSTEM_PROMPT = """
Eres el asistente de un chatbot que consulta tableros de Power BI de gestión clínica.
Te doy la pregunta del usuario y varios indicadores candidatos. Para CADA indicador
escribe UNA frase corta (máximo {max_words} palabras) que explique qué valor se
obtendría al consultarlo y de qué tablero o página sale.

REGLAS OBLIGATORIAS:
1. Usa solo la información de cada indicador. No inventes cifras, filtros ni periodos.
2. No repitas el nombre del indicador tal cual; explica qué mide.
3. Escribe en español, sin markdown ni comillas.
4. Responde únicamente con una línea por indicador, en el mismo orden y con el
   formato: <número>. <frase>
""".strip()

    def __init__(self, llm_provider, max_words=22, max_chars=170):
        self.llm_provider = llm_provider
        self.max_words = max_words
        self.max_chars = max_chars

    @staticmethod
    def _field(label, value, limit=220):
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        if not text:
            return None
        if len(text) > limit:
            text = text[:limit].rsplit(" ", 1)[0] + "…"
        return f"   {label}: {text}"

    def build_prompt(self, question, options):
        blocks = []
        for index, option in enumerate(options, 1):
            lines = [f"{index}. Indicador: {option.get('label')}"]
            for label, key in (
                ("Medida", "measure"),
                ("Expresión DAX", "dax_expression"),
                ("Descripción del catálogo", "description"),
                ("Informe", "report"),
                ("Página", "page"),
                ("Visuales donde aparece", "visuals"),
                ("Modelo semántico", "semantic_model"),
            ):
                line = self._field(label, option.get(key))
                if line:
                    lines.append(line)
            blocks.append("\n".join(lines))
        return (
            f"PREGUNTA DEL USUARIO:\n{question}\n\n"
            "OPCIONES A DESCRIBIR:\n" + "\n\n".join(blocks) + "\n\n"
            f"Responde con {len(options)} líneas, una por indicador."
        )

    def _clean(self, text, label):
        text = re.sub(r"[*_`#]+", "", str(text or ""))
        text = re.sub(r"\s+", " ", text).strip().strip("\"'«»“”").strip()
        text = re.sub(r"^(?:descripci[oó]n|frase)\s*:\s*", "", text, flags=re.IGNORECASE)
        if not text or text.casefold() == str(label or "").strip().casefold():
            return ""
        if len(text) > self.max_chars:
            text = text[:self.max_chars].rsplit(" ", 1)[0].rstrip(",;:") + "…"
        return text

    def parse(self, answer, options):
        descriptions = {}
        for line in str(answer or "").splitlines():
            match = re.match(r"^\s*(?:[-*]\s*)?\**(\d{1,2})\s*[.):\-]\s*(.+)$", line)
            if not match:
                continue
            index = int(match.group(1))
            if not 1 <= index <= len(options):
                continue
            option = options[index - 1]
            text = self._clean(match.group(2), option.get("label"))
            if text and option["id"] not in descriptions:
                descriptions[option["id"]] = text
        # Una sola opción y el modelo respondió sin numerar.
        if not descriptions and len(options) == 1:
            text = self._clean(str(answer or "").strip().splitlines()[0] if answer else "",
                               options[0].get("label"))
            if text:
                descriptions[options[0]["id"]] = text
        return descriptions

    def describe(self, question, options):
        """options: [{id, label, measure, dax_expression, description, report,
        page, visuals, semantic_model}]. Devuelve {status, descriptions, raw,
        elapsed_s, error?}; `descriptions` es {id: frase}."""
        if not options:
            return {"status": "skipped", "descriptions": {}, "raw": None, "elapsed_s": 0.0}
        prompt = self.build_prompt(question, options)
        started = time.perf_counter()
        try:
            response = self.llm_provider.chat(
                messages=[
                    {"role": "system",
                     "content": self.SYSTEM_PROMPT.format(max_words=self.max_words)},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=60 * len(options) + 40,
                think=False,
            )
        except Exception as error:
            response = {"status": "error", "error": f"{type(error).__name__}: {error}"}
        elapsed = round(time.perf_counter() - started, 2)
        answer = response.get("answer")
        if response.get("status") != "success" or not answer:
            return {
                "status": response.get("status") or "error",
                "descriptions": {}, "raw": answer, "elapsed_s": elapsed,
                "error": response.get("error"), "model": response.get("model"),
            }
        descriptions = self.parse(answer, options)
        return {
            "status": "success" if descriptions else "unparsed",
            "descriptions": descriptions, "raw": answer, "elapsed_s": elapsed,
            "model": response.get("model"),
        }
