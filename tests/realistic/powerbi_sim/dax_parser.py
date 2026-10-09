"""
Analizador léxico y sintáctico de DAX (subconjunto amplio) para el simulador.

Produce un árbol de nodos (tuplas con nombre) que evalúa dax_eval.py. Cubre:

  - Consultas:  [DEFINE MEASURE / VAR ...] EVALUATE <tabla> [ORDER BY ...] [START AT ...]
  - Expresiones: literales, 'Tabla'[Columna], Tabla[Columna], [Medida], 'Tabla',
    llamadas FUNCION(...) (incluye INFO.VIEW.TABLES), { constructores de tabla },
    VAR ... RETURN, operadores || && NOT = == <> < > <= >= IN & + - * / ^.

Los errores de sintaxis se lanzan como DaxError con la posición (línea, columna)
en el mismo formato que ADOMD: "Query (3, 5) The syntax for 'X' is incorrect."
"""
import re
from collections import namedtuple


class DaxError(Exception):
    """Error de evaluación / enlace con texto parecido al de Power BI.

    kind: syntax | name | type | value | unsupported
      - unsupported: el simulador no implementa algo que Power BI sí aceptaría
        (no es un error "real"; para medidas del modelo se usa un valor de respaldo).
    """

    def __init__(self, message, kind="value", pos=None):
        super().__init__(message)
        self.message = message
        self.kind = kind
        self.pos = pos

    def adomd_message(self):
        if self.pos and not self.message.startswith("Query ("):
            return f"Query ({self.pos[0]}, {self.pos[1]}) {self.message}"
        return self.message


class DaxUnsupported(DaxError):
    def __init__(self, message, pos=None):
        super().__init__(message, kind="unsupported", pos=pos)


# ----------------------------------------------------------------------------
# Nodos
# ----------------------------------------------------------------------------

Num = namedtuple("Num", "value pos")
Str = namedtuple("Str", "value pos")
ColRef = namedtuple("ColRef", "table column pos")          # table None => [nombre]
TableRef = namedtuple("TableRef", "name pos")              # 'Tabla'
Ident = namedtuple("Ident", "name pos")                    # Tabla / variable / palabra clave
Call = namedtuple("Call", "name args pos")                 # name en MAYÚSCULAS
BinOp = namedtuple("BinOp", "op left right pos")
Unary = namedtuple("Unary", "op expr pos")                 # "-", "+", "NOT"
InOp = namedtuple("InOp", "expr target pos")
TableCtor = namedtuple("TableCtor", "rows pos")            # rows: [[expr, ...], ...]
VarBlock = namedtuple("VarBlock", "vars body pos")         # vars: [(nombre, expr)]
Query = namedtuple("Query", "measures vars evaluates")
Evaluate = namedtuple("Evaluate", "table order_by start_at pos")


# ----------------------------------------------------------------------------
# Léxico
# ----------------------------------------------------------------------------

Token = namedtuple("Token", "kind value pos")

_TOKEN_RE = re.compile(r"""
    (?P<ws>\s+)
  | (?P<comment>//[^\n]*|--[^\n]*|/\*.*?\*/)
  | (?P<string>"(?:[^"]|"")*")
  | (?P<quoted>'(?:[^']|'')*')
  | (?P<bracket>\[(?:[^\]]|\]\])*\])
  | (?P<number>(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?)
  | (?P<ident>[^\W\d][\w.]*)
  | (?P<op>&&|\|\||<=|>=|<>|==|[=<>+\-*/^&(){},;.])
""", re.VERBOSE | re.DOTALL)


def _position(text, offset):
    line = text.count("\n", 0, offset) + 1
    col = offset - (text.rfind("\n", 0, offset) + 1) + 1
    return (line, col)


def tokenize(text):
    tokens = []
    pos = 0
    length = len(text)
    while pos < length:
        m = _TOKEN_RE.match(text, pos)
        if not m:
            snippet = text[pos:pos + 15]
            raise DaxError(f"The syntax for '{snippet}' is incorrect.", "syntax", _position(text, pos))
        kind = m.lastgroup
        value = m.group(kind)
        if kind not in ("ws", "comment"):
            if kind == "string":
                value = value[1:-1].replace('""', '"')
            elif kind == "quoted":
                value = value[1:-1].replace("''", "'")
            elif kind == "bracket":
                value = value[1:-1].replace("]]", "]")
            tokens.append(Token(kind, value, _position(text, pos)))
        pos = m.end()
    tokens.append(Token("eof", None, _position(text, length)))
    return tokens


# ----------------------------------------------------------------------------
# Sintaxis
# ----------------------------------------------------------------------------

_COMPARISON = {"=", "==", "<>", "<", ">", "<=", ">="}
_QUERY_KEYWORDS = {"EVALUATE", "ORDER", "DEFINE", "START", "MEASURE", "VAR", "TABLE", "COLUMN", "RETURN"}


class Parser:

    def __init__(self, text):
        self.text = text
        self.tokens = tokenize(text)
        self.i = 0

    # ---------- utilidades ----------
    @property
    def tok(self):
        return self.tokens[self.i]

    def _peek(self, k=1):
        return self.tokens[min(self.i + k, len(self.tokens) - 1)]

    def _advance(self):
        tok = self.tokens[self.i]
        self.i += 1
        return tok

    def _is_kw(self, word, tok=None):
        tok = tok or self.tok
        return tok.kind == "ident" and tok.value.upper() == word

    def _is_op(self, op, tok=None):
        tok = tok or self.tok
        return tok.kind == "op" and tok.value == op

    def _error(self, tok=None):
        tok = tok or self.tok
        shown = "<EOF>" if tok.kind == "eof" else str(tok.value)
        return DaxError(f"The syntax for '{shown}' is incorrect.", "syntax", tok.pos)

    def _expect_op(self, op):
        if not self._is_op(op):
            raise self._error()
        return self._advance()

    def _expect_kw(self, word):
        if not self._is_kw(word):
            raise self._error()
        return self._advance()

    # ---------- consulta ----------
    def parse_query(self):
        measures, variables, evaluates = [], [], []
        if self._is_kw("DEFINE"):
            self._advance()
            while not self._is_kw("EVALUATE"):
                if self._is_kw("MEASURE"):
                    self._advance()
                    table_tok = self._advance()
                    if table_tok.kind not in ("quoted", "ident"):
                        raise self._error(table_tok)
                    if self.tok.kind != "bracket":
                        raise self._error()
                    name = self._advance().value
                    self._expect_op("=")
                    measures.append((table_tok.value, name, self.parse_expression()))
                elif self._is_kw("VAR"):
                    self._advance()
                    name = self._advance().value
                    self._expect_op("=")
                    variables.append((name, self.parse_expression()))
                elif self._is_kw("TABLE") or self._is_kw("COLUMN") or self._is_kw("FUNCTION"):
                    raise DaxUnsupported(f"DEFINE {self.tok.value.upper()} no está soportado por el simulador",
                                         self.tok.pos)
                else:
                    raise self._error()
        if not self._is_kw("EVALUATE"):
            raise self._error()
        while self._is_kw("EVALUATE"):
            start = self._advance()
            table = self.parse_expression()
            order_by, start_at = [], None
            if self._is_kw("ORDER") and self._is_kw("BY", self._peek()):
                self._advance()
                self._advance()
                while True:
                    expr = self.parse_expression()
                    ascending = True
                    if self._is_kw("ASC"):
                        self._advance()
                    elif self._is_kw("DESC"):
                        self._advance()
                        ascending = False
                    order_by.append((expr, ascending))
                    if self._is_op(","):
                        self._advance()
                        continue
                    break
            if self._is_kw("START") and self._is_kw("AT", self._peek()):
                self._advance()
                self._advance()
                start_at = [self.parse_expression()]
                while self._is_op(","):
                    self._advance()
                    start_at.append(self.parse_expression())
            evaluates.append(Evaluate(table, order_by, start_at, start.pos))
        if self.tok.kind != "eof":
            raise self._error()
        return Query(measures, variables, evaluates)

    def parse_standalone(self):
        """Expresión suelta (medida, columna calculada, tabla calculada)."""
        expr = self.parse_expression()
        if self.tok.kind != "eof":
            raise self._error()
        return expr

    # ---------- expresiones ----------
    def parse_expression(self):
        if self._is_kw("VAR"):
            return self._parse_var_block()
        return self._parse_or()

    def _parse_var_block(self):
        start = self.tok
        variables = []
        while self._is_kw("VAR"):
            self._advance()
            name_tok = self._advance()
            if name_tok.kind not in ("ident", "quoted"):
                raise self._error(name_tok)
            self._expect_op("=")
            variables.append((name_tok.value, self.parse_expression()))
        self._expect_kw("RETURN")
        body = self.parse_expression()
        return VarBlock(variables, body, start.pos)

    def _parse_or(self):
        left = self._parse_and()
        while self._is_op("||"):
            tok = self._advance()
            left = BinOp("||", left, self._parse_and(), tok.pos)
        return left

    def _parse_and(self):
        left = self._parse_not()
        while self._is_op("&&"):
            tok = self._advance()
            left = BinOp("&&", left, self._parse_not(), tok.pos)
        return left

    def _parse_not(self):
        # NOT como operador prefijo (NOT ISBLANK(x)); NOT(...) también entra aquí.
        if self._is_kw("NOT") and not self._is_op("(", self._peek()):
            tok = self._advance()
            return Unary("NOT", self._parse_not(), tok.pos)
        if self._is_kw("NOT") and self._is_op("(", self._peek()):
            tok = self._advance()
            inner = self._parse_comparison()
            return Unary("NOT", inner, tok.pos)
        return self._parse_comparison()

    def _parse_comparison(self):
        left = self._parse_concat()
        while True:
            if self.tok.kind == "op" and self.tok.value in _COMPARISON:
                tok = self._advance()
                left = BinOp(tok.value, left, self._parse_concat(), tok.pos)
            elif self._is_kw("IN"):
                tok = self._advance()
                left = InOp(left, self._parse_concat(), tok.pos)
            elif self._is_kw("NOT") and self._is_kw("IN", self._peek()):
                tok = self._advance()
                self._advance()
                left = Unary("NOT", InOp(left, self._parse_concat(), tok.pos), tok.pos)
            else:
                return left

    def _parse_concat(self):
        left = self._parse_additive()
        while self._is_op("&"):
            tok = self._advance()
            left = BinOp("&", left, self._parse_additive(), tok.pos)
        return left

    def _parse_additive(self):
        left = self._parse_multiplicative()
        while self.tok.kind == "op" and self.tok.value in ("+", "-"):
            tok = self._advance()
            left = BinOp(tok.value, left, self._parse_multiplicative(), tok.pos)
        return left

    def _parse_multiplicative(self):
        left = self._parse_power()
        while self.tok.kind == "op" and self.tok.value in ("*", "/"):
            tok = self._advance()
            left = BinOp(tok.value, left, self._parse_power(), tok.pos)
        return left

    def _parse_power(self):
        left = self._parse_unary()
        while self._is_op("^"):
            tok = self._advance()
            left = BinOp("^", left, self._parse_unary(), tok.pos)
        return left

    def _parse_unary(self):
        if self.tok.kind == "op" and self.tok.value in ("-", "+"):
            tok = self._advance()
            return Unary(tok.value, self._parse_unary(), tok.pos)
        return self._parse_primary()

    def _parse_args(self):
        args = []
        self._expect_op("(")
        if self._is_op(")"):
            self._advance()
            return args
        while True:
            if self._is_op(",") or self._is_op(")"):
                # argumento omitido: FUNC(a, , c)
                args.append(None)
            else:
                args.append(self.parse_expression())
            if self._is_op(","):
                self._advance()
                continue
            self._expect_op(")")
            return args

    def _parse_primary(self):
        tok = self.tok
        if tok.kind == "number":
            self._advance()
            text = tok.value
            value = float(text) if any(c in text for c in ".eE") else int(text)
            return Num(value, tok.pos)
        if tok.kind == "string":
            self._advance()
            return Str(tok.value, tok.pos)
        if tok.kind == "bracket":
            self._advance()
            return ColRef(None, tok.value, tok.pos)
        if tok.kind == "quoted":
            self._advance()
            if self.tok.kind == "bracket":
                col = self._advance()
                return self._hierarchy(ColRef(tok.value, col.value, tok.pos))
            return TableRef(tok.value, tok.pos)
        if tok.kind == "ident":
            upper = tok.value.upper()
            if upper in _QUERY_KEYWORDS and upper != "RETURN":
                raise self._error()
            self._advance()
            if self._is_op("("):
                return Call(upper, self._parse_args(), tok.pos)
            if self.tok.kind == "bracket":
                col = self._advance()
                return self._hierarchy(ColRef(tok.value, col.value, tok.pos))
            return Ident(tok.value, tok.pos)
        if self._is_op("("):
            self._advance()
            if self._is_op(")"):
                raise self._error()
            first = self.parse_expression()
            if self._is_op(","):
                # tupla (a, b) dentro de un constructor de tabla o IN
                items = [first]
                while self._is_op(","):
                    self._advance()
                    items.append(self.parse_expression())
                self._expect_op(")")
                return TableCtor([items], tok.pos)
            self._expect_op(")")
            return first
        if self._is_op("{"):
            self._advance()
            rows = []
            if not self._is_op("}"):
                while True:
                    item = self.parse_expression()
                    if isinstance(item, TableCtor) and len(item.rows) == 1 and self._tuple_like(item):
                        rows.append(item.rows[0])
                    else:
                        rows.append([item])
                    if self._is_op(","):
                        self._advance()
                        continue
                    break
            self._expect_op("}")
            return TableCtor(rows, tok.pos)
        raise self._error()

    def _hierarchy(self, colref):
        """'T'[Fecha].[Mes]  (jerarquía automática de fechas) -> __HIERLEVEL('T'[Fecha], "Mes")."""
        while self._is_op(".") and self._peek().kind == "bracket":
            self._advance()
            level = self._advance()
            if level.value.lower() in ("variación", "variacion", "variation", "jerarquía de fechas",
                                       "jerarquia de fechas", "date hierarchy"):
                continue
            colref = Call("__HIERLEVEL", [colref, Str(level.value, level.pos)], colref.pos)
        return colref

    @staticmethod
    def _tuple_like(node):
        return isinstance(node, TableCtor)


def parse_query(text):
    return Parser(text).parse_query()


def parse_expression(text):
    return Parser(text).parse_standalone()


def walk(node):
    """Recorre todos los nodos de un árbol (preorden)."""
    stack = [node]
    while stack:
        current = stack.pop()
        if current is None:
            continue
        yield current
        if isinstance(current, Call):
            stack.extend(reversed([a for a in current.args if a is not None]))
        elif isinstance(current, BinOp):
            stack.extend([current.right, current.left])
        elif isinstance(current, Unary):
            stack.append(current.expr)
        elif isinstance(current, InOp):
            stack.extend([current.target, current.expr])
        elif isinstance(current, TableCtor):
            for row in reversed(current.rows):
                stack.extend(reversed(row))
        elif isinstance(current, VarBlock):
            stack.append(current.body)
            stack.extend(reversed([expr for _, expr in current.vars]))
        elif isinstance(current, Query):
            for _, _, expr in current.measures:
                stack.append(expr)
            for _, expr in current.vars:
                stack.append(expr)
            for ev in current.evaluates:
                stack.append(ev.table)
                for expr, _ in ev.order_by:
                    stack.append(expr)
