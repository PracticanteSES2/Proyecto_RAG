import re
import time
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher


class OptionDescriber:
    """
    Pide al LLM una descripción corta de lo que consultaría cada opción de
    una contrapregunta («qué cuenta o calcula este indicador»).

    Una llamada por opción, en paralelo: con MedGemma, pedir todas en una
    sola respuesta desalineaba la numeración, y mostrarle la pregunta del
    usuario hacía que describiera todas las opciones igual (la pregunta, no
    el indicador). Si el LLM falla o no describe una opción, esa opción
    conserva la descripción del catálogo (la decide QueryEngine).
    """

    SYSTEM_PROMPT = """
Eres el asistente de un chatbot que consulta tableros de Power BI de gestión clínica.
Te doy UN indicador. Escribe UNA frase (máximo {max_words} palabras) que diga qué
cuenta o calcula, para que el usuario lo distinga de otros parecidos.

REGLAS OBLIGATORIAS:
1. Empieza con un verbo en presente: Cuenta, Suma, Calcula, Mide, Promedia o Muestra.
2. No escribas el nombre del indicador ni el del tablero o la página (ya se muestran aparte).
3. Básate en la expresión DAX y la descripción dadas. No inventes cifras, filtros ni periodos.
4. Español, sin markdown ni comillas. Responde solo la frase.

EJEMPLOS
Indicador: % CANCELACIÓN · DAX: DIVIDE([Canceladas], [Programadas])
Calcula qué porcentaje de las cirugías programadas se canceló.
Indicador: CIRUGÍAS PROGRAMADAS · DAX: COUNTROWS(PROGRAMACION)
Cuenta las cirugías agendadas en la programación quirúrgica.
""".strip()

    def __init__(self, llm_provider, max_words=15, max_chars=140, max_workers=3):
        self.llm_provider = llm_provider
        self.max_words = max_words
        self.max_chars = max_chars
        # El servidor atiende ~3 peticiones a la vez; más hilos no aceleran.
        self.max_workers = max_workers

    @staticmethod
    def _field(label, value, limit=220):
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        if not text:
            return None
        if len(text) > limit:
            text = text[:limit].rsplit(" ", 1)[0] + "…"
        return f"   {label}: {text}"

    def build_prompt(self, option):
        lines = [f"1. Indicador: {option.get('label')}"]
        for label, key in (
            ("Medida", "measure"),
            ("Expresión DAX", "dax_expression"),
            ("Descripción del catálogo", "description"),
            ("Visuales donde aparece", "visuals"),
        ):
            line = self._field(label, option.get(key))
            if line:
                lines.append(line)
        return "OPCIONES A DESCRIBIR:\n" + "\n".join(lines) + "\n\nResponde solo la frase."

    def _clean(self, text, label):
        text = re.sub(r"[*_`#]+", "", str(text or ""))
        text = re.sub(r"\s+", " ", text).strip().strip("\"'«»“”").strip()
        text = re.sub(r"^(?:\d{1,2}\s*[.):\-]\s*)", "", text)
        text = re.sub(r"^(?:descripci[oó]n|frase)\s*:\s*", "", text, flags=re.IGNORECASE)
        label = str(label or "").strip()
        # El modelo tiende a empezar con «El indicador X muestra/cuenta...»:
        # se quita esa entrada y se deja el verbo en mayúscula.
        if label:
            text = re.sub(
                r"^(?:el|este)\s+indicador\s+(?:de\s+)?(?:[«\"']?" + re.escape(label)
                + r"[»\"']?\s*)?[,:]?\s*",
                "", text, flags=re.IGNORECASE,
            )
            text = re.sub(r"^[«\"']?" + re.escape(label) + r"[»\"']?\s*[,:-]?\s*", "",
                          text, flags=re.IGNORECASE)
        # Solo la primera frase: la segunda suele repetir tablero y página.
        text = re.split(r"(?<=[.;])\s+", text, maxsplit=1)[0].strip()
        if text:
            text = text[0].upper() + text[1:]
        if not text or text.casefold() == label.casefold():
            return ""
        if len(text) > self.max_chars:
            text = text[:self.max_chars].rsplit(" ", 1)[0].rstrip(",;:") + "…"
        return text

    def parse(self, answer, label):
        """Primera línea con contenido de la respuesta, limpia."""
        for line in str(answer or "").splitlines():
            text = self._clean(line, label)
            if text:
                return text
        return ""

    def _describe_one(self, option):
        try:
            response = self.llm_provider.chat(
                messages=[
                    {"role": "system",
                     "content": self.SYSTEM_PROMPT.format(max_words=self.max_words)},
                    {"role": "user", "content": self.build_prompt(option)},
                ],
                temperature=0.1,
                max_tokens=60,
                think=False,
            )
        except Exception as error:
            response = {"status": "error", "error": f"{type(error).__name__}: {error}"}
        return response

    @staticmethod
    def _dax_hint(option):
        """Lo que distingue una medida según su DAX: tabla de origen y filtros
        literales («tabla PROGRAMACION, ESTADO = REALIZADA»)."""
        dax = str(option.get("dax_expression") or "")
        parts = []
        table = re.search(
            r"\b(?:COUNTROWS|SUMX|AVERAGEX|COUNTX|FILTER)\s*\(\s*'?([^'(),\[\]]+?)'?\s*[,)]",
            dax, flags=re.IGNORECASE,
        ) or re.search(r"'?([A-Za-z_][^'(),\[\]]*?)'?\s*\[", dax)
        if table:
            parts.append(f"tabla {table.group(1).strip()}")
        for column, value in re.findall(
            r"\[([^\]]+)\]\s*=\s*\"([^\"]+)\"", dax,
        )[:2]:
            parts.append(f"{column} = {value}")
        if not parts and option.get("measure"):
            parts.append(f"medida {option['measure']}")
        return ", ".join(parts)

    def _disambiguate(self, options, descriptions):
        """Si el modelo dio frases (casi) iguales a dos opciones, se completa
        cada una con lo que la distingue según su DAX."""
        described = [o for o in options if descriptions.get(o["id"])]
        similar = set()
        for index, left in enumerate(described):
            for right in described[index + 1:]:
                ratio = SequenceMatcher(
                    None,
                    descriptions[left["id"]].rstrip(".").casefold(),
                    descriptions[right["id"]].rstrip(".").casefold(),
                ).ratio()
                if ratio >= 0.85:
                    similar.update((left["id"], right["id"]))
        for option in described:
            hint = self._dax_hint(option) if option["id"] in similar else ""
            if hint:
                descriptions[option["id"]] = (
                    descriptions[option["id"]].rstrip(".") + f" ({hint})."
                )
        return descriptions

    def describe(self, question, options):
        """options: [{id, label, measure, dax_expression, description, report,
        page, visuals, semantic_model}]. `question` no se envía al LLM (sesga
        las descripciones); se conserva en la firma para el razonamiento.
        Devuelve {status, descriptions, raw, elapsed_s, error?}; `descriptions`
        es {id: frase} y `raw` las respuestas crudas por opción."""
        if not options:
            return {"status": "skipped", "descriptions": {}, "raw": None, "elapsed_s": 0.0}
        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=max(1, min(self.max_workers, len(options)))) as pool:
            responses = list(pool.map(self._describe_one, options))
        elapsed = round(time.perf_counter() - started, 2)

        descriptions, raw, errors, model = {}, [], [], None
        for option, response in zip(options, responses):
            model = model or response.get("model")
            answer = response.get("answer")
            if response.get("status") != "success" or not answer:
                errors.append(f"{option['id']}: {response.get('error') or response.get('status')}")
                continue
            raw.append(f"[{option['id']}] {answer}")
            text = self.parse(answer, option.get("label"))
            if text:
                descriptions[option["id"]] = text
        descriptions = self._disambiguate(options, descriptions)
        if descriptions:
            status = "success" if len(descriptions) == len(options) else "partial"
        else:
            status = "unparsed" if raw else (
                next((r.get("status") for r in responses if r.get("status")), None) or "error"
            )
        return {
            "status": status, "descriptions": descriptions,
            "raw": "\n".join(raw) or None, "elapsed_s": elapsed,
            "error": "; ".join(errors) or None, "model": model,
        }
