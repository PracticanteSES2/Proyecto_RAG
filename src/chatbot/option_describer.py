import os
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher

from src.chatbot import cache_llm
from src.chatbot.runtime_stats import STATS, env_float
from src.llm.llm_gate import call_llm


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
3. Básate en la tabla, la expresión DAX y la descripción dadas. No inventes cifras, filtros ni periodos.
4. Lo que se cuenta o se suma es lo que dicen la tabla y sus columnas (tabla CAMAS: camas).
   No menciones personas, personal ni otros conceptos que no aparezcan en esos datos.
5. Respeta los filtros: lo marcado «EXCLUYE» queda fuera (dilo con «sin» o «excepto» o no lo
   menciones); lo marcado «solo» es lo que se cuenta (estado OCUPADA: camas ocupadas, no disponibles).
6. Español, sin markdown ni comillas. Responde solo la frase.

EJEMPLOS
Indicador: % CANCELACIÓN · DAX: DIVIDE([Canceladas], [Programadas])
Calcula qué porcentaje de las cirugías programadas se canceló.
Indicador: CIRUGÍAS PROGRAMADAS · DAX: COUNTROWS(PROGRAMACION)
Cuenta las cirugías agendadas en la programación quirúrgica.
""".strip()

    def __init__(self, llm_provider, max_words=15, max_chars=140, max_workers=3, timeout=None):
        self.llm_provider = llm_provider
        self.max_words = max_words
        self.max_chars = max_chars
        # Tiempo límite por descripción (OPTION_DESCRIBER_TIMEOUT, 15 s): al
        # vencer se cierra la conexión y la opción usa la descripción del
        # catálogo. Antes no tenía límite propio (180 s del cliente).
        self.timeout = timeout if timeout is not None else env_float("OPTION_DESCRIBER_TIMEOUT", 15.0)
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

    @staticmethod
    def _aggregated_columns(expression, limit=3):
        """Columnas que la expresión cuenta, suma o promedia
        («'CAMAS DISPONIBLES'[OCUPADAS]»), sin repetir."""
        found = []
        for table, column in re.findall(
            r"\b(?:COUNT|COUNTA|COUNTX|COUNTROWS|DISTINCTCOUNT|DISTINCTCOUNTNOBLANK|SUM|SUMX|AVERAGE|"
            r"AVERAGEX|MIN|MAX|MEDIAN)\s*\(\s*'?([^'(),\[\]]*?)'?\s*\[([^\]]+)\]",
            str(expression or ""), flags=re.IGNORECASE,
        ):
            item = f"{table.strip()}[{column.strip()}]" if table.strip() else f"[{column.strip()}]"
            if item not in found:
                found.append(item)
        return ", ".join(found[:limit])

    _IN_FILTER_RE = re.compile(
        r"(?P<neg>NOT\s*\(\s*\(?\s*)?'?(?P<table>[^'(),\[\]]*?)'?\s*\[(?P<column>[^\]]+)\]\s+IN\s*\{(?P<values>[^}]*)\}",
        re.IGNORECASE,
    )
    _EQ_FILTER_RE = re.compile(
        r"'?(?P<table>[^'(),\[\]]*?)'?\s*\[(?P<column>[^\]]+)\]\s*(?P<op>=|<>)\s*\"(?P<value>[^\"]*)\"",
    )

    @classmethod
    def filter_conditions(cls, expression):
        """[(columna, «solo»|«excluye», [valores])] de los filtros literales de
        la expresión: «NOT ('T'[GASNOMBRE] IN {"UNIDAD OBSTETRICIA"})» ->
        ("GASNOMBRE", "excluye", ["UNIDAD OBSTETRICIA"]). MedGemma leía esos
        NOT al revés («de la unidad obstétrica» cuando la excluye)."""
        found = []
        text = str(expression or "")
        for match in cls._IN_FILTER_RE.finditer(text):
            values = [value.strip().strip('"').strip() for value in match.group("values").split(",")]
            values = [value for value in values if value]
            if values:
                found.append((match.group("column").strip(), "excluye" if match.group("neg") else "solo", values))
        for match in cls._EQ_FILTER_RE.finditer(text):
            found.append((
                match.group("column").strip(), "excluye" if match.group("op") == "<>" else "solo",
                [match.group("value").strip()],
            ))
        return found

    @classmethod
    def _filters_text(cls, expression, limit=4):
        parts = []
        for column, kind, values in cls.filter_conditions(expression)[:limit]:
            shown = ", ".join(values[:4]) + (" …" if len(values) > 4 else "")
            parts.append(f"{kind} {column} = {shown}" if kind == "solo" else f"EXCLUYE {column} = {shown}")
        return "; ".join(parts)

    def contradicts_filters(self, text, option):
        """¿La descripción nombra como incluido un valor que la expresión
        excluye? («de la unidad obstétrica» con NOT GASNOMBRE IN {UNIDAD
        OBSTETRICIA}). Una mención precedida de «sin», «excepto», «excluye» o
        «no» no contradice."""
        plain = self._plain(text)
        expression = " ".join(
            str(option.get(key) or "") for key in ("dax_expression", "model_expression")
        )
        for _, kind, values in self.filter_conditions(expression):
            if kind != "excluye":
                continue
            for value in values:
                words = [word for word in self._plain(value).split() if len(word) >= 4]
                if not words:
                    continue
                pattern = r"\b" + r"\s+".join(re.escape(word[:6]) + r"[a-z]*" for word in words) + r"\b"
                for match in re.finditer(pattern, plain):
                    before = plain[max(0, match.start() - 30):match.start()]
                    if not re.search(r"\b(?:sin|excepto|salvo|excluye|excluyendo|no|menos|fuera)\b", before):
                        return True
        return False

    def build_prompt(self, option):
        lines = [f"1. Indicador: {option.get('label')}"]
        dax = str(option.get("dax_expression") or "").strip()
        model_expression = str(option.get("model_expression") or "").strip()
        # «[%OCUPACION]» solo repite el nombre: la expresión real es la del modelo.
        if model_expression and (not dax or re.fullmatch(r"\[[^\]]+\]", dax)):
            dax = model_expression
        for label, value in (
            ("Medida", option.get("measure")),
            ("Tabla", option.get("table")),
            ("Expresión DAX", dax),
            ("Cuenta o agrega", self._aggregated_columns(dax)),
            # Los filtros en palabras: «EXCLUYE» no se describe como incluido.
            ("Filtros de la expresión", self._filters_text(dax)),
            ("Descripción del catálogo", option.get("description")),
            ("Visuales donde aparece", option.get("visuals")),
        ):
            line = self._field(label, value)
            if line:
                lines.append(line)
        return "OPCIONES A DESCRIBIR:\n" + "\n".join(lines) + "\n\nResponde solo la frase."

    # Conceptos (personas, entidades, objetos del hospital) que una descripción
    # no puede traer si no están en el nombre, la tabla, la expresión o la
    # documentación del indicador: MedGemma describía %OCUPACION (camas de la
    # tabla CAMAS DISPONIBLES) como «ocupación del personal». Raíces.
    CONCEPT_STEMS = (
        "personal", "empleado", "trabajador", "funcionari", "colaborador", "medico", "enfermer",
        "profesional", "especialista", "paciente", "usuario", "cama", "cirugi", "cita", "consulta",
        "factura", "medicament", "egreso", "urgencia", "triage", "habitacion", "quirofano",
        "laboratorio", "imagen", "remision", "interconsulta", "aseguradora", "insumo", "producto",
        "prenda", "ropa", "salario", "nomina", "venta", "dinero",
    )

    @staticmethod
    def _plain(text):
        text = unicodedata.normalize("NFD", str(text or "").lower())
        text = "".join(char for char in text if unicodedata.category(char) != "Mn")
        return re.sub(r"[^a-z0-9]+", " ", text)

    def invented_concepts(self, text, option):
        """Conceptos de CONCEPT_STEMS que la descripción menciona y que no
        aparecen en el nombre, la medida, la tabla, la expresión, la
        descripción del catálogo ni los visuales/página de la opción."""
        context = " ".join(
            self._plain(option.get(key)) for key in (
                "label", "measure", "table", "dax_expression", "model_expression",
                "description", "visuals", "page", "report",
            )
        )
        context_words = context.split()
        invented = []
        for word in self._plain(text).split():
            stem = next((item for item in self.CONCEPT_STEMS if word.startswith(item)), None)
            if stem and stem not in invented and not any(other.startswith(stem) for other in context_words):
                invented.append(stem)
        return invented

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

    def _usable(self, raw, option):
        """¿La respuesta cruda da una descripción aceptable? (si no, no se cachea)."""
        text = self.parse(raw.get("answer"), option.get("label"))
        return bool(text) and not self.invented_concepts(text, option) and not self.contradicts_filters(text, option)

    def _describe_one(self, option):
        # La pregunta del usuario no entra en el prompt: la descripción de un
        # indicador es la misma en cualquier contrapregunta (caché del motor).
        system, user = self.SYSTEM_PROMPT.format(max_words=self.max_words), self.build_prompt(option)
        return cache_llm.llamar_con_cache(
            cache_llm.clave("descripción de opciones", fuentes=user, prompt=system,
                            modelo=cache_llm.modelo_de(self.llm_provider), max_tokens=60),
            lambda: call_llm(
                self.llm_provider,
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
                purpose="descripción de opciones",
                timeout=self.timeout if self.timeout and self.timeout > 0 else None,
                temperature=0.1,
                max_tokens=60,
                think=False,
            ),
            proposito="descripción de opciones",
            es_guardable=lambda raw: self._usable(raw, option),
        )

    # Descripción del catálogo que basta (no hace falta el LLM): ya tiene la
    # forma que se le pide al LLM (empieza con Cuenta, Suma, Calcula, Mide,
    # Promedia o Muestra), al menos 6 palabras, no solo repite el nombre y
    # distingue la opción de las demás. Hoy el catálogo casi nunca la trae (las medidas no
    # tienen descripción), pero la documentación de los tableros sí la irá
    # completando. OPTION_DESCRIBER_CATALOGO=off la desactiva.
    CATALOG_MIN_WORDS = 6
    CATALOG_VERBS = ("cuenta", "suma", "calcula", "mide", "promedia", "muestra")

    def catalog_sufficient(self, options):
        """Ids de las opciones cuya descripción del catálogo basta."""
        if str(os.getenv("OPTION_DESCRIBER_CATALOGO", "on")).strip().lower() in ("off", "0", "no", "false"):
            return []
        texts = {}
        for option in options:
            text = self._clean(option.get("description"), option.get("label"))
            words = self._plain(text).split()
            label_words = set(self._plain(option.get("label")).split())
            if len(words) >= self.CATALOG_MIN_WORDS and words[0] in self.CATALOG_VERBS                     and not set(words) <= label_words:
                texts[option["id"]] = text.rstrip(".").casefold()
        return [
            key for key, text in texts.items()
            if not any(other != key and SequenceMatcher(None, text, texts[other]).ratio() >= 0.85
                       for other in texts)
        ]

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

    def _split_catalog(self, options):
        """(ids con descripción de catálogo suficiente, opciones que van al LLM)."""
        catalog = self.catalog_sufficient(options)
        if catalog:
            STATS.llm_call_avoided("catálogo: descripción de opciones", len(catalog))
        return catalog, [option for option in options if option["id"] not in catalog]

    def describe(self, question, options):
        """options: [{id, label, measure, dax_expression, description, report,
        page, visuals, semantic_model}]. `question` no se envía al LLM (sesga
        las descripciones); se conserva en la firma para el razonamiento.
        Devuelve {status, descriptions, raw, elapsed_s, error?}; `descriptions`
        es {id: frase} y `raw` las respuestas crudas por opción."""
        catalog, pending = self._split_catalog(options or [])
        if not pending:  # sin opciones, o todas con descripción de catálogo suficiente
            return {"status": "catalog" if catalog else "skipped", "descriptions": {}, "raw": None,
                    "elapsed_s": 0.0, "catalog": catalog}
        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=max(1, min(self.max_workers, len(pending)))) as pool:
            responses = list(pool.map(self._describe_one, pending))
        elapsed = round(time.perf_counter() - started, 2)
        descriptions, raw, errors, model, rejected = self._collect(pending, responses)
        descriptions = self._disambiguate(options, descriptions)
        if descriptions:
            status = "success" if len(descriptions) == len(pending) else "partial"
        else:
            status = "unparsed" if raw else (
                next((r.get("status") for r in responses if r.get("status")), None) or "error"
            )
        return {
            "status": status, "descriptions": descriptions,
            "raw": "\n".join(raw) or None, "elapsed_s": elapsed,
            "error": "; ".join(errors) or None, "model": model,
            "rejected": rejected, "catalog": catalog,
        }

    def _collect(self, pending, responses):
        """(descripciones, crudas, errores, modelo, rechazadas) de las respuestas."""
        descriptions, raw, errors, model, rejected = {}, [], [], None, {}
        for option, response in zip(pending, responses):
            model = model or response.get("model")
            answer = response.get("answer")
            if response.get("status") != "success" or not answer:
                errors.append(f"{option['id']}: {response.get('error') or response.get('status')}")
                continue
            raw.append(f"[{option['id']}] {answer}")
            text = self.parse(answer, option.get("label"))
            invented = self.invented_concepts(text, option) if text else []
            if invented:
                # Habla de algo que el indicador no tiene («personal» en una
                # medida de camas): se usa la descripción del catálogo.
                rejected[option["id"]] = invented
                continue
            if text and self.contradicts_filters(text, option):
                # Nombra como incluido lo que la expresión excluye.
                rejected[option["id"]] = ["filtro excluido"]
                continue
            if text:
                descriptions[option["id"]] = text
        return descriptions, raw, errors, model, rejected
