"""
Fakes para simular el chatbot sin Power BI, sin Ollama, sin Qdrant y sin
sentence-transformers.

install_stubs(fixtures_root) registra módulos falsos en sys.modules ANTES de
importar código del proyecto:

  dotenv                              -> load_dotenv() no-op (NUNCA lee .env)
  streamlit                           -> cache_resource identidad (solo para exec de app.py)
  sentence_transformers               -> SentenceTransformer con embedding hash determinista
  qdrant_client / qdrant_client.models-> QdrantClient en memoria que carga <path>/points.json
  ollama                              -> Client falso (list/chat)
  clr                                 -> AddReference no-op
  Microsoft.AnalysisServices.AdomdClient -> AdomdConnection falso sobre FakeDaxEngine

De este modo se usan las CLASES REALES del proyecto (HybridRetriever,
PowerBIProvider, OllamaProvider, ...) con dependencias falsas.
"""
import hashlib
import json
import math
import os
import re
import sys
import types
import unicodedata
from datetime import datetime
from pathlib import Path

import numpy as np

# Registro global de lo que pasó (consultas DAX, advertencias, llamadas LLM)
SIM_LOG = {"dax": [], "warnings": [], "llm_calls": 0}

# Interruptores de la simulación. Se fijan en harness.build_engine(); los
# valores por defecto leen las variables de entorno SIM_OLLAMA / SIM_POWERBI.
CONFIG = {"ollama_up": os.getenv("SIM_OLLAMA", "up") != "down",
          "powerbi_up": os.getenv("SIM_POWERBI", "up") != "down"}


def reset_log():
    """Crea logs NUEVOS (las listas anteriores quedan intactas para quien las guardó)."""
    SIM_LOG["dax"] = []
    SIM_LOG["warnings"] = []
    SIM_LOG["llm_calls"] = 0
    return SIM_LOG


def _norm(text):
    text = str(text or "").lower()
    text = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _stable_fraction(*parts, low=0.05, high=0.40):
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()
    return low + (int(digest[:8], 16) / 0xFFFFFFFF) * (high - low)


# ============================================================================
# sentence_transformers
# ============================================================================

class FakeSentenceTransformer:
    """Embedding determinista: bolsa de palabras (stem simple) + trigramas, 384 dims."""

    DIM = 384
    STOP = {"el", "la", "los", "las", "de", "del", "que", "en", "y", "a", "un", "una",
            "por", "con", "para", "se", "es", "al", "lo", "su", "sus", "hay", "hubo"}

    def __init__(self, model_name=None, *args, **kwargs):
        self.model_name = model_name

    def _vec(self, text):
        v = np.zeros(self.DIM, dtype=np.float32)
        words = [w for w in _norm(text).split() if w not in self.STOP]
        for w in words:
            stem = w[:-1] if len(w) > 4 and w.endswith("s") else w
            h = int(hashlib.md5(("w:" + stem).encode()).hexdigest(), 16)
            v[h % self.DIM] += 2.0
            padded = f"#{stem}#"
            for i in range(len(padded) - 2):
                h = int(hashlib.md5(("t:" + padded[i:i + 3]).encode()).hexdigest(), 16)
                v[h % self.DIM] += 0.5
        return v

    def encode(self, sentences, normalize_embeddings=False, **kwargs):
        single = isinstance(sentences, str)
        items = [sentences] if single else list(sentences)
        out = []
        for s in items:
            v = self._vec(s)
            if normalize_embeddings:
                n = float(np.linalg.norm(v))
                if n > 0:
                    v = v / n
            out.append(v)
        arr = np.vstack(out) if out else np.zeros((0, self.DIM), dtype=np.float32)
        return arr[0] if single else arr

    def get_sentence_embedding_dimension(self):
        return self.DIM


# ============================================================================
# qdrant_client
# ============================================================================

class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)

    def __repr__(self):
        return f"{type(self).__name__}({self.__dict__})"


class MatchValue(_Obj):
    def __init__(self, value=None, **kw):
        super().__init__(value=value, **kw)


class FieldCondition(_Obj):
    def __init__(self, key=None, match=None, **kw):
        super().__init__(key=key, match=match, **kw)


class Filter(_Obj):
    def __init__(self, must=None, should=None, must_not=None, **kw):
        super().__init__(must=must or [], should=should or [], must_not=must_not or [], **kw)


class PointStruct(_Obj):
    pass


class VectorParams(_Obj):
    pass


class FilterSelector(_Obj):
    pass


class Distance:
    COSINE = "Cosine"
    DOT = "Dot"
    EUCLID = "Euclid"


class ScoredPoint(_Obj):
    pass


class QueryResponse(_Obj):
    pass


class FakeQdrantClient:
    """Cliente en memoria. QdrantClient(path=X) carga X/points.json."""

    def __init__(self, path=None, location=None, **kwargs):
        self.path = path
        self.collections = {}
        self._model = FakeSentenceTransformer()
        file = Path(path) / "points.json" if path else None
        if file and file.exists():
            data = json.loads(file.read_text(encoding="utf-8"))
            name = data.get("collection", "gestion_clinica_rag")
            pts = []
            for p in data.get("points", []):
                payload = p["payload"]
                vec = self._model.encode(payload.get("text", ""), normalize_embeddings=True)
                pts.append({"id": p["id"], "payload": payload, "vector": vec})
            self.collections[name] = pts

    def collection_exists(self, collection_name):
        return collection_name in self.collections

    def _match(self, payload, flt):
        if flt is None:
            return True
        for cond in getattr(flt, "must", []) or []:
            if payload.get(cond.key) != cond.match.value:
                return False
        return True

    def scroll(self, collection_name, limit=10, offset=None, with_payload=True, with_vectors=False, **kw):
        pts = self.collections[collection_name]
        start = int(offset or 0)
        chunk = pts[start:start + limit]
        nxt = start + limit if start + limit < len(pts) else None
        return [_Obj(id=p["id"], payload=dict(p["payload"]), vector=None) for p in chunk], nxt

    def query_points(self, collection_name, query=None, query_filter=None, limit=10, with_payload=True, **kw):
        q = np.asarray(query, dtype=np.float32)
        scored = []
        for p in self.collections[collection_name]:
            if not self._match(p["payload"], query_filter):
                continue
            scored.append(ScoredPoint(id=p["id"], payload=dict(p["payload"]), score=float(np.dot(q, p["vector"]))))
        scored.sort(key=lambda s: s.score, reverse=True)
        return QueryResponse(points=scored[:limit])

    def close(self):
        pass


# ============================================================================
# ollama
# ============================================================================

class FakeResponseError(Exception):
    def __init__(self, error="", status_code=-1):
        super().__init__(error)
        self.error = error
        self.status_code = status_code


class FakeOllamaClient:
    """Simula Ollama. CONFIG['ollama_up']=False => conexión rechazada."""

    def __init__(self, host=None, timeout=None, **kwargs):
        self.host = host
        self.down = not CONFIG["ollama_up"]

    def list(self):
        if self.down:
            raise ConnectionError("[sim] Ollama no disponible")
        return _Obj(models=[
            _Obj(model=os.getenv("OLLAMA_MODEL", "qwen3:8b")),
            _Obj(model=os.getenv("MEDGEMMA_MODEL", "medgemma:latest")),
        ])

    def chat(self, model=None, messages=None, **kwargs):
        if self.down:
            raise ConnectionError("[sim] Ollama no disponible")
        SIM_LOG["llm_calls"] += 1
        user = next((m["content"] for m in reversed(messages or []) if m.get("role") == "user"), "")
        if "CONTEXTO RECUPERADO" in user:
            ctx = user.split("CONTEXTO RECUPERADO:", 1)[1].split("TAREA:", 1)[0]
            lines = [l.strip() for l in ctx.splitlines()
                     if l.strip() and not l.startswith(("[FUENTE", "Tipo:", "Contenido:"))]
            content = "[FakeLLM] " + " ".join(lines)[:600]
        elif "OPCIONES A DESCRIBIR" in user:
            # OptionDescriber: una línea numerada por indicador.
            labels = re.findall(r"^(\d+)\. Indicador: (.+)$", user, flags=re.MULTILINE)
            content = "\n".join(
                f"{number}. [FakeLLM] Obtiene el valor de {label.strip().lower()}"
                for number, label in labels
            )
        else:
            content = "OK"
        return _Obj(message=_Obj(content=content))


# ============================================================================
# Power BI (ADOMD) -> FakeDaxEngine
# ============================================================================

class FakeDaxError(Exception):
    pass


TC_RE = re.compile(r"'((?:[^']|'')+)'\[((?:[^\]]|\]\])+)\]")


class FakeDaxEngine:
    """Interpreta de forma laxa el DAX que genera el proyecto.

    Dos tipos de modelo (ver fixtures/powerbi_model.json):
      * canned     -> las medidas tienen un valor "base" y los filtros lo escalan
                      con fracciones estables (modelos Atenciones / Quirurgico).
      * row-level  -> el modelo trae "data": {tabla: [filas]}; los filtros y
                      agregaciones se calculan sobre filas reales (Lavanderia),
                      de modo que los totales son consistentes entre consultas.
    """

    def __init__(self, model_file):
        self.spec = json.loads(Path(model_file).read_text(encoding="utf-8"))
        self.models = self.spec["models"]
        self.years = self.spec.get("data_years", [2023, 2024, 2025])
        self.mismatches = []
        self._prepare_row_models()

    # ---------- preparación de modelos row-level ----------
    def _prepare_row_models(self):
        for model in self.models.values():
            data = model.get("data")
            if not data:
                continue
            for table, rows in data.items():
                cols = model["tables"][table]
                for row in rows:
                    for name, meta in cols.items():
                        if meta.get("type") == "DateTime" and isinstance(row.get(name), str):
                            row[name] = datetime.fromisoformat(row[name])
                    for name, meta in cols.items():
                        if meta.get("calculated"):
                            row[name] = self._calc_column(meta["calculated"], row)
                # dominios (VALUES) derivados de las filas para columnas de texto
                for name, meta in cols.items():
                    if meta.get("type") == "String" and not meta.get("values"):
                        meta["values"] = sorted({r[name] for r in rows if r.get(name) is not None})

    @staticmethod
    def _calc_column(kind, row):
        if kind == "NOMBRE_COMPLETO":
            return f"{row.get('usu_nombres')} {row.get('usu_apellidos')}"
        if kind == "TURNO_OK":
            return {1: "MAÑANA", 2: "TARDE", 3: "NOCHE"}.get(row.get("Turno"))
        raise FakeDaxError(f"[sim] columna calculada desconocida: {kind}")

    # ---------- helpers ----------
    def _model(self, name):
        for k, v in self.models.items():
            if _norm(k) == _norm(name):
                return k, v
        raise FakeDaxError(f"[sim] La base de datos '{name}' no existe o no tienes permisos.")

    def _column(self, model, table, column):
        tables = model["tables"]
        t = next((k for k in tables if k.lower() == table.lower()), None)
        if t is None:
            raise FakeDaxError(f"Query (1, 1) Cannot find table '{table}'.")
        c = next((k for k in tables[t] if k.lower() == column.lower()), None)
        if c is None:
            raise FakeDaxError(f"Query (1, 1) The column '{column}' of table '{table}' cannot be found.")
        return t, c, tables[t][c]

    def _measure(self, model, name):
        m = next((k for k in model.get("measures", {}) if _norm(k) == _norm(name)), None)
        if m is None:
            raise FakeDaxError(f"Query (1, 1) The value for '{name}' cannot be determined. Measure not found.")
        return m, model["measures"][m]

    @staticmethod
    def _split_args(text):
        args, depth, cur, in_str, quote = [], 0, "", False, None
        i = 0
        while i < len(text):
            ch = text[i]
            if in_str:
                cur += ch
                if ch == quote:
                    in_str = False
            elif ch in ('"', "'"):
                in_str, quote = True, ch
                cur += ch
            elif ch in "([{":
                depth += 1
                cur += ch
            elif ch in ")]}":
                depth -= 1
                cur += ch
            elif ch == "," and depth == 0:
                args.append(cur.strip())
                cur = ""
            else:
                cur += ch
            i += 1
        if cur.strip():
            args.append(cur.strip())
        return args

    @staticmethod
    def _inside(text, func):
        idx = text.upper().find(func.upper() + "(")
        if idx < 0:
            return None
        start = idx + len(func) + 1
        depth = 1
        for j in range(start, len(text)):
            if text[j] == "(":
                depth += 1
            elif text[j] == ")":
                depth -= 1
                if depth == 0:
                    return text[start:j]
        raise FakeDaxError("Query: syntax error, unbalanced parenthesis")

    def _validate_refs(self, model, dax):
        for t, c in TC_RE.findall(dax):
            self._column(model, t.replace("''", "'"), c.replace("]]", "]"))
        stripped = TC_RE.sub("", dax)
        for name in re.findall(r"\[([^\]]+)\]", stripped):
            if name in ("Value", "__value", "Resultado"):
                continue
            self._measure(model, name)

    def _flag_mismatch(self, flt):
        meta = flt["meta"]
        msg = (f"TYPE MISMATCH: filtro DATE() aplicado a {flt['table']}[{flt['column']}] "
               f"de tipo {meta.get('type')} -> en Power BI real la comparación entero vs fecha "
               f"no devuelve filas (BLANK / resultado vacío)")
        self.mismatches.append({"table": flt["table"], "column": flt["column"],
                                "column_type": meta.get("type"), "message": msg})
        SIM_LOG["warnings"].append(msg)

    # ---------- filtros ----------
    def _parse_filter(self, model, arg):
        a = arg.strip()
        up = a.upper()
        if up.startswith("TREATAS("):
            braces = a.split("}", 1)[0]
            vals = re.findall(r'"((?:[^"]|"")*)"', braces)
            if not vals:  # literales numéricos sin comillas: TREATAS({2024}, col)
                vals = re.findall(r"-?\d+(?:\.\d+)?", braces)
            t, c = TC_RE.findall(a)[-1]
            t, c, meta = self._column(model, t, c)
            return {"kind": "eq", "table": t, "column": c, "meta": meta, "values": [v.replace('""', '"') for v in vals]}
        if up.startswith("KEEPFILTERS("):
            inner = self._inside(a, "KEEPFILTERS")
            t, c = TC_RE.findall(inner)[0]
            t, c, meta = self._column(model, t, c)
            raw = inner.split("=", 1)[1].strip()
            val = raw.strip('"') if raw.startswith('"') else raw
            return {"kind": "eq", "table": t, "column": c, "meta": meta, "values": [val]}
        if up.startswith("FILTER("):
            refs = TC_RE.findall(a)
            t, c = refs[0]
            t, c, meta = self._column(model, t, c)
            month_only = re.search(r"MONTH\([^)]*\)\s*=\s*(\d{1,2})", a)
            if month_only:
                return {"kind": "month", "table": t, "column": c, "meta": meta,
                        "month": int(month_only.group(1))}
            dates = re.findall(r"DATE\((\d{4}),\s*(\d{1,2}),\s*(\d{1,2})\)", a)
            return {"kind": "date_range", "table": t, "column": c, "meta": meta,
                    "dates": [tuple(int(x) for x in d) for d in dates]}
        raise FakeDaxError(f"[sim] filtro DAX no soportado por el fake: {a[:80]}")

    # ---------- modelos canned ----------
    def _filter_factor(self, flt, salt):
        meta = flt["meta"]
        if flt["kind"] == "eq":
            domain = [str(v) for v in meta.get("values", [])]
            factor = 0.0
            for v in flt["values"]:
                if domain and str(v) not in domain:
                    SIM_LOG["warnings"].append(f"valor '{v}' no existe en {flt['table']}[{flt['column']}] -> BLANK")
                    continue
                if _norm(flt["column"]) in ("ano", "year") and str(v).isdigit():
                    factor += 1.0 / len(self.years) if int(v) in self.years else 0.0
                else:
                    factor += _stable_fraction(salt, flt["table"], flt["column"], v)
            return factor
        if flt["kind"] == "month":
            if meta.get("type") != "DateTime":
                self._flag_mismatch(flt)
                return 0.0
            return 1.0 / 12.0
        if flt["kind"] == "date_range":
            if meta.get("type") != "DateTime":
                self._flag_mismatch(flt)
                return 0.0
            (y1, m1, _), (y2, m2, _) = flt["dates"][0], flt["dates"][1]
            months = (y2 - y1) * 12 + (m2 - m1)
            in_data = sum(1 for k in range(months)
                          if (y1 + (m1 - 1 + k) // 12) in self.years)
            return in_data / (12.0 * len(self.years))
        return 1.0

    def _eval_measure_expr(self, model, expr, filters, salt=""):
        expr = expr.strip()
        m = re.fullmatch(r"\[([^\]]+)\]", expr)
        if not m:
            raise FakeDaxError(f"[sim] expresión no soportada por el fake: {expr[:80]}")
        name, meta = self._measure(model, m.group(1))
        value = float(meta["base"])
        for f in filters:
            value *= self._filter_factor(f, name + salt)
        return None if value == 0 else int(round(value))

    # ---------- modelos row-level ----------
    @staticmethod
    def _row_matches(row, flt):
        val = row.get(flt["column"])
        if flt["kind"] == "eq":
            wanted = {str(v).casefold() for v in flt["values"]}
            return val is not None and str(val).casefold() in wanted
        if flt["kind"] == "month":
            return isinstance(val, datetime) and val.month == flt["month"]
        if flt["kind"] == "date_range":
            if not isinstance(val, datetime):
                return False
            lo, hi = flt["dates"][0], flt["dates"][1]
            return datetime(*lo) <= val < datetime(*hi)
        return True

    def _apply_filters(self, rows, filters):
        for flt in filters:
            if flt["kind"] in ("date_range", "month") and flt["meta"].get("type") != "DateTime":
                self._flag_mismatch(flt)
                return []
        for flt in filters:
            rows = [r for r in rows if self._row_matches(r, flt)]
        return rows

    def _row_aggregate(self, model, expr, rows):
        expr = expr.strip()
        m = re.fullmatch(r"(SUM|AVERAGE|COUNT|DISTINCTCOUNT|MIN|MAX|COUNTROWS)\((.*)\)", expr, re.I | re.S)
        if not m:
            ref = re.fullmatch(r"\[([^\]]+)\]", expr)
            if ref:
                _, meta = self._measure(model, ref.group(1))
                return self._row_aggregate(model, meta["expression"], rows)
            raise FakeDaxError(f"[sim] expresión no soportada por el fake: {expr[:80]}")
        fn, inner = m.group(1).upper(), m.group(2)
        if fn == "COUNTROWS":
            return len(rows) or None
        t, c = TC_RE.findall(inner)[0]
        self._column(model, t, c)
        vals = [r.get(c) for r in rows if r.get(c) is not None]
        if not vals:
            return None
        if fn == "SUM":
            return round(sum(vals), 6)
        if fn == "AVERAGE":
            return round(sum(vals) / len(vals), 6)
        if fn == "COUNT":
            return len(vals)
        if fn == "DISTINCTCOUNT":
            return len(set(vals))
        return min(vals) if fn == "MIN" else max(vals)

    def _row_source(self, model, expr, filters, groups):
        """Tabla única de la consulta row-level (el fake no modela relaciones)."""
        names = {f["table"] for f in filters} | {g[0] for g in groups}
        for t, c in TC_RE.findall(expr):
            names.add(self._column(model, t, c)[0])
        if len(names) != 1:
            raise FakeDaxError("[sim] el fake row-level solo soporta una tabla por consulta")
        return model["data"][next(iter(names))]

    # ---------- entrada ----------
    def execute(self, semantic_model, dax):
        self.mismatches = []
        model_name, model = self._model(semantic_model)
        self._validate_refs(model, dax)
        up = dax.upper()
        rowlevel = "data" in model

        # Dominio de valores (QueryPlanBuilder._get_values / BusinessFilterResolver._get_values)
        if "SELECTCOLUMNS(" in up and "VALUES(" in up:
            inner = self._inside(dax, "VALUES")
            t, c = TC_RE.findall(inner)[0]
            t, c, meta = self._column(model, t, c)
            values = sorted(meta.get("values", []), key=lambda v: str(v))
            return ["[Value]"], [[v] for v in values]

        # Ranking: TOPN(n, SUMMARIZECOLUMNS(...), [__value], ASC|DESC) ORDER BY [__value] ASC|DESC
        if up.lstrip().startswith("EVALUATE") and up.split("EVALUATE", 1)[1].lstrip().startswith("TOPN(") \
                and "SUMMARIZECOLUMNS(" in up:
            top_args = self._split_args(self._inside(dax, "TOPN"))
            limit = int(top_args[0])
            descending = not (len(top_args) > 3 and top_args[3].strip().upper() == "ASC")
            columns, rows = self.execute(semantic_model, "EVALUATE\n" + top_args[1])
            rows = sorted(rows, key=lambda r: r[-1], reverse=descending)[:limit]
            order = re.search(r"ORDER\s+BY\s+\[__value\]\s+(ASC|DESC)", up)
            if order:
                rows.sort(key=lambda r: r[-1], reverse=order.group(1) == "DESC")
            return columns, rows

        if "SUMMARIZECOLUMNS(" in up:
            args = self._split_args(self._inside(dax, "SUMMARIZECOLUMNS"))
            groups, filters, name_idx = [], [], None
            for i, a in enumerate(args):
                if a.startswith('"'):
                    name_idx = i
                    break
                if TC_RE.fullmatch(a):
                    t, c = TC_RE.fullmatch(a).groups()
                    groups.append(self._column(model, t, c))
                else:
                    filters.append(self._parse_filter(model, a))
            if name_idx is None:
                raise FakeDaxError("[sim] SUMMARIZECOLUMNS sin columna de valor")
            colname = args[name_idx].strip('"')
            expr = args[name_idx + 1]
            if rowlevel:
                rows = self._apply_filters(self._row_source(model, expr, filters, groups), filters)
                buckets = {}
                for r in rows:
                    buckets.setdefault(tuple(r.get(g[1]) for g in groups), []).append(r)
                out = []
                for key, brs in buckets.items():
                    if expr.upper().startswith("DIVIDE("):
                        # participación por grupo: grupo / total (REMOVEFILTERS del grupo)
                        num, den = self._split_args(self._inside(expr, "DIVIDE"))[:2]
                        base = self._split_args(self._inside(den, "CALCULATE"))[0]
                        total = self._row_aggregate(model, base, rows)
                        part = self._row_aggregate(model, num, brs)
                        val = None if not total or part is None else part / total
                        if val is not None:
                            out.append([*key, val])
                        continue
                    val = self._row_aggregate(model, expr, brs)
                    if val is not None:
                        out.append([*key, val])
                out.sort(key=lambda r: r[-1], reverse=True)
                return [f"{t}[{c}]" for t, c, _ in groups] + [f"[{colname}]"], out
            if len(groups) != 1:
                raise FakeDaxError("[sim] el fake canned solo soporta 1 columna de agrupación")
            t, c, meta = groups[0]
            rows = []
            for v in meta.get("values", []):
                group_filter = {"kind": "eq", "table": t, "column": c, "meta": meta, "values": [v]}
                val = self._eval_measure_expr(model, expr, filters + [group_filter])
                if val is not None:
                    rows.append([v, val])
            rows.sort(key=lambda r: r[1], reverse=True)
            return [f"{t}[{c}]", f"[{colname}]"], rows

        if "ROW(" in up:
            args = self._split_args(self._inside(dax, "ROW"))
            colname = args[0].strip('"')
            expr = args[1]
            if expr.upper().startswith("DIVIDE("):
                # DIVIDE(CALCULATE(base, filtros), CALCULATE(base, REMOVEFILTERS(col), filtros))
                num, den = self._split_args(self._inside(expr, "DIVIDE"))[:2]
                vals = []
                for part in (num, den):
                    cargs = self._split_args(self._inside(part, "CALCULATE"))
                    base = cargs[0]
                    flts = [self._parse_filter(model, a) for a in cargs[1:]
                            if not a.upper().startswith("REMOVEFILTERS(")]
                    srows = self._apply_filters(self._row_source(model, base, flts, []), flts)
                    vals.append(self._row_aggregate(model, base, srows))
                value = None if not vals[1] or vals[0] is None else vals[0] / vals[1]
                return [f"[{colname}]"], [[value]]
            if expr.upper().startswith("CALCULATE("):
                cargs = self._split_args(self._inside(expr, "CALCULATE"))
                base, filters = cargs[0], [self._parse_filter(model, a) for a in cargs[1:]]
            else:
                base, filters = expr, []
            if rowlevel:
                rows = self._apply_filters(self._row_source(model, base, filters, []), filters)
                return [f"[{colname}]"], [[self._row_aggregate(model, base, rows)]]
            return [f"[{colname}]"], [[self._eval_measure_expr(model, base, filters)]]

        raise FakeDaxError(f"[sim] patrón DAX no soportado: {dax[:120]}")


class _State:
    def __init__(self, value):
        self.value = value

    def ToString(self):
        return self.value


class FakeAdomdReader:
    def __init__(self, columns, rows):
        self._columns, self._rows, self._i = columns, rows, -1
        self.FieldCount = len(columns)

    def GetName(self, i):
        return self._columns[i]

    def Read(self):
        self._i += 1
        return self._i < len(self._rows)

    def GetValue(self, i):
        return self._rows[self._i][i]

    def Close(self):
        pass

    def Dispose(self):
        pass


class FakeAdomdCommand:
    def __init__(self, conn):
        self.conn = conn
        self.CommandText = ""

    def ExecuteReader(self):
        entry = {"semantic_model": self.conn.catalog, "dax": self.CommandText}
        SIM_LOG["dax"].append(entry)
        try:
            columns, rows = FAKE_ENGINE.execute(self.conn.catalog, self.CommandText)
        except FakeDaxError as exc:
            entry["error"] = str(exc)
            entry["type_mismatch"] = list(FAKE_ENGINE.mismatches)
            raise
        entry["rows"] = len(rows)
        entry["result"] = [list(r) for r in rows[:50]]
        # Comparaciones de tipo imposibles (p. ej. columna entera AÑO vs DATE())
        entry["type_mismatch"] = list(FAKE_ENGINE.mismatches)
        return FakeAdomdReader(columns, rows)

    def Dispose(self):
        pass


class FakeAdomdConnection:
    def __init__(self, connection_string):
        self.connection_string = connection_string
        m = re.search(r"Initial Catalog=([^;]+);", connection_string)
        self.catalog = m.group(1) if m else None
        self.State = _State("Closed")
        self.down = not CONFIG["powerbi_up"]

    def Open(self):
        if self.down:
            raise ConnectionError("[sim] XMLA endpoint no disponible")
        self.State = _State("Open")

    def Close(self):
        self.State = _State("Closed")

    def Dispose(self):
        pass

    def CreateCommand(self):
        return FakeAdomdCommand(self)

    def GetSchemaDataSet(self, name, restrictions):
        rows = [{"CATALOG_NAME": k} for k in FAKE_ENGINE.models]
        return _Obj(Tables=[_Obj(Rows=rows)])


class FakeAdomdRestrictionCollection:
    pass


FAKE_ENGINE = None


# ============================================================================
# Instalación
# ============================================================================

def _module(name, **attrs):
    mod = types.ModuleType(name)
    mod.__dict__.update(attrs)
    mod.__sim_fake__ = True
    sys.modules[name] = mod
    return mod


def install_stubs(fixtures_root):
    global FAKE_ENGINE
    fixtures_root = Path(fixtures_root)
    FAKE_ENGINE = FakeDaxEngine(fixtures_root / "powerbi_model.json")

    # dotenv: SIEMPRE falso para que nunca se lea el .env del proyecto
    _module("dotenv", load_dotenv=lambda *a, **k: False, find_dotenv=lambda *a, **k: "")

    def cache_resource(func=None, **kwargs):
        if func is None:
            return lambda f: f
        return func
    _module("streamlit", cache_resource=cache_resource, cache_data=cache_resource)

    _module("sentence_transformers", SentenceTransformer=FakeSentenceTransformer)

    qc = _module("qdrant_client", QdrantClient=FakeQdrantClient)
    models = _module("qdrant_client.models", FieldCondition=FieldCondition, Filter=Filter,
                     MatchValue=MatchValue, PointStruct=PointStruct, VectorParams=VectorParams,
                     Distance=Distance, FilterSelector=FilterSelector)
    qc.models = models

    _module("ollama", Client=FakeOllamaClient, ResponseError=FakeResponseError)

    _module("clr", AddReference=lambda name: None)
    ms = _module("Microsoft")
    asv = _module("Microsoft.AnalysisServices")
    adomd = _module("Microsoft.AnalysisServices.AdomdClient",
                    AdomdConnection=FakeAdomdConnection,
                    AdomdRestrictionCollection=FakeAdomdRestrictionCollection)
    ms.AnalysisServices = asv
    asv.AdomdClient = adomd

    # Variables de entorno dummy (solo en este proceso)
    os.environ["POWERBI_XMLA_ENDPOINT"] = "powerbi://api.powerbi.com/v1.0/myorg/SIMULADO"
    os.environ["POWERBI_SEMANTIC_MODEL"] = "Atenciones Institucionales"
    os.environ["ADOMD_PATH"] = str(fixtures_root / "adomd")
    os.environ["IDENTITY_PATH"] = str(fixtures_root / "adomd")
    os.environ["OLLAMA_HOST"] = "http://sim.invalid:11434"
    os.environ["OLLAMA_MODEL"] = "qwen3:8b"
    os.environ["MEDGEMMA_BASE_URL"] = "http://sim.invalid:11434"
    os.environ["MEDGEMMA_MODEL"] = "medgemma:latest"
    os.environ["QDRANT_COLLECTION_NAME"] = "gestion_clinica_rag"
