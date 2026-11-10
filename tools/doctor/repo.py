"""Vista de solo lectura del repo: archivos, textos, AST e índice de Python.

Todo se calcula una vez y lo comparten las reglas.
"""
from __future__ import annotations

import ast
import fnmatch
import os
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

_EXCEPCIONES_IMPORT = {"ImportError", "ModuleNotFoundError", "Exception", "BaseException"}
_DECORADORES_INOCUOS = {
    "staticmethod", "classmethod", "property", "cached_property", "lru_cache", "cache",
    "functools.lru_cache", "functools.cache", "functools.cached_property", "wraps",
    "dataclass", "dataclasses.dataclass", "abstractmethod", "abc.abstractmethod", "override",
}


# ---------------------------------------------------------------------------
# Archivos
# ---------------------------------------------------------------------------

def _componentes(ruta: str) -> list[str]:
    return ruta.split("/")


def excluido(ruta: str, exclusiones: list[str]) -> bool:
    partes = _componentes(ruta)
    for patron in exclusiones:
        if patron.startswith("/"):
            ancla = patron.strip("/").split("/")
            if len(partes) >= len(ancla) and all(fnmatch.fnmatchcase(p, a) for p, a in zip(partes, ancla)):
                return True
        elif any(fnmatch.fnmatchcase(p, patron) for p in partes):
            return True
    return False


def bajo(ruta: str, prefijos: list[str]) -> bool:
    """`ruta` está en alguno de los prefijos (carpeta o archivo exacto)."""
    for p in prefijos:
        p = p.strip("/")
        if ruta == p or ruta.startswith(p + "/"):
            return True
    return False


def _listar_git(raiz: Path) -> list[str] | None:
    if not (raiz / ".git").exists():  # solo la raíz de un repo o worktree
        return None
    try:
        top = subprocess.run(
            ["git", "-C", str(raiz), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=30,
        )
        if top.returncode != 0 or Path(top.stdout.strip()).resolve() != raiz.resolve():
            return None
        r = subprocess.run(
            ["git", "-C", str(raiz), "-c", "core.quotepath=false", "ls-files", "-z", "-co", "--exclude-standard"],
            capture_output=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return sorted({p for p in r.stdout.decode("utf-8", "replace").split("\0") if p})


def _listar_disco(raiz: Path, exclusiones: list[str]) -> list[str]:
    salida = []
    for actual, dirs, archivos in os.walk(raiz):
        rel = Path(actual).relative_to(raiz).as_posix()
        rel = "" if rel == "." else rel + "/"
        dirs[:] = [d for d in dirs if not excluido(rel + d, exclusiones)]
        salida.extend(rel + a for a in archivos)
    return sorted(salida)


# ---------------------------------------------------------------------------
# Índice de Python
# ---------------------------------------------------------------------------

@dataclass
class Importacion:
    modulo: str            # destino absoluto (punteado)
    nombres: list[str]     # `from x import a, b` → [a, b]; `import x` → []
    linea: int
    de_modulo: bool        # a nivel de módulo (no dentro de función)
    protegida: bool        # dentro de try que captura ImportError
    tipo_checking: bool    # dentro de `if TYPE_CHECKING:`
    ligados: list[tuple[str, str]] = field(default_factory=list)  # (nombre ligado, original)


@dataclass
class Funcion:
    nombre: str
    qual: str
    linea: int
    fin: int
    nodo: ast.AST
    clase: str | None
    clase_con_bases: bool
    de_modulo: bool        # función o clase de primer nivel / método de clase de primer nivel
    decoradores: list[str]
    complejidad: int = 1   # ciclomática tipo McCabe (sin funciones anidadas)


@dataclass
class Llamada:
    nombre: str            # punteado y resuelto con los alias de importación
    linea: int
    contexto: str          # qualname de la función que la contiene o "<modulo>"
    en_main: bool
    en_async: bool
    nodo: ast.Call


@dataclass
class Except:
    linea: int
    tipos: list[str] | None    # None = except desnudo
    silencioso: bool
    contexto: str


@dataclass
class ModuloPy:
    ruta: str
    nombre: str
    es_paquete: bool
    texto: str
    arbol: ast.Module | None
    error: str | None = None
    importaciones: list[Importacion] = field(default_factory=list)
    funciones: list[Funcion] = field(default_factory=list)
    clases: list[Funcion] = field(default_factory=list)
    llamadas: list[Llamada] = field(default_factory=list)
    excepts: list[Except] = field(default_factory=list)
    usados: Counter = field(default_factory=Counter)        # nombres leídos en el módulo
    cadenas: set = field(default_factory=set)               # literales de cadena cortos
    definidos: set = field(default_factory=set)             # nombres de primer nivel
    comodin: bool = False                                    # `import *` o `__getattr__`
    todos: set = field(default_factory=set)                 # __all__
    raiz_proyecto: list[int] = field(default_factory=list)  # líneas que calculan la raíz

    @property
    def paquete(self) -> str:
        return self.nombre if self.es_paquete else self.nombre.rpartition(".")[0]


def nombre_modulo(ruta: str) -> str:
    sin_ext = ruta[:-3] if ruta.endswith(".py") else ruta
    partes = sin_ext.split("/")
    if partes[-1] == "__init__":
        partes = partes[:-1]
    return ".".join(partes)


def punteado(nodo: ast.AST) -> str | None:
    partes = []
    while isinstance(nodo, ast.Attribute):
        partes.append(nodo.attr)
        nodo = nodo.value
    if isinstance(nodo, ast.Name):
        partes.append(nodo.id)
        return ".".join(reversed(partes))
    return None


def _contiene_file(nodo: ast.AST) -> bool:
    return any(isinstance(n, ast.Name) and n.id == "__file__" for n in ast.walk(nodo))


def _cuerpo_silencioso(cuerpo: list[ast.stmt]) -> bool:
    return all(
        isinstance(s, ast.Pass) or (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) and s.value.value is Ellipsis)
        for s in cuerpo
    )


def _tipos_except(tipo: ast.AST | None) -> list[str] | None:
    if tipo is None:
        return None
    elementos = tipo.elts if isinstance(tipo, ast.Tuple) else [tipo]
    return [punteado(e) or "?" for e in elementos]


class _Indexador(ast.NodeVisitor):
    def __init__(self, mod: ModuloPy):
        self.m = mod
        self.pila: list[str] = []          # qualname
        self.en_funcion = 0
        self.clase: list[tuple[str, bool]] = []
        self.protegida = 0
        self.tipo_checking = 0
        self.en_main = False
        self.alias: dict[str, str] = {}
        self.asincronas: list[bool] = []
        self.funcs: list[Funcion] = []

    # -- contexto -----------------------------------------------------------
    def _contexto(self) -> str:
        return ".".join(self.pila) or "<modulo>"

    def _funcion(self, nodo):
        qual = ".".join([*self.pila, nodo.name])
        clase = self.clase[-1] if self.clase and self.pila and self.pila[-1] == self.clase[-1][0] else None
        f = Funcion(
            nombre=nodo.name, qual=qual, linea=nodo.lineno, fin=nodo.end_lineno or nodo.lineno, nodo=nodo,
            clase=clase[0] if clase else None, clase_con_bases=bool(clase and clase[1]),
            de_modulo=len(self.pila) == 0 or (clase is not None and len(self.pila) == 1),
            decoradores=[punteado(d.func if isinstance(d, ast.Call) else d) or "?" for d in nodo.decorator_list],
        )
        self.m.funciones.append(f)
        if not self.pila:
            self.m.definidos.add(nodo.name)
            if nodo.name == "__getattr__":
                self.m.comodin = True
        for d in nodo.decorator_list:
            self.visit(d)
        self.visit(nodo.args)
        if nodo.returns:
            self.visit(nodo.returns)
        self.pila.append(nodo.name)
        self.en_funcion += 1
        self.asincronas.append(isinstance(nodo, ast.AsyncFunctionDef))
        self.funcs.append(f)
        for s in nodo.body:
            self.visit(s)
        self.funcs.pop()
        self.en_funcion -= 1
        self.asincronas.pop()
        self.pila.pop()

    visit_FunctionDef = _funcion
    visit_AsyncFunctionDef = _funcion

    def visit_ClassDef(self, nodo):
        qual = ".".join([*self.pila, nodo.name])
        con_bases = any(punteado(b) != "object" for b in nodo.bases) or bool(nodo.keywords)
        self.m.clases.append(Funcion(
            nombre=nodo.name, qual=qual, linea=nodo.lineno, fin=nodo.end_lineno or nodo.lineno, nodo=nodo,
            clase=None, clase_con_bases=con_bases, de_modulo=not self.pila,
            decoradores=[punteado(d.func if isinstance(d, ast.Call) else d) or "?" for d in nodo.decorator_list],
        ))
        if not self.pila:
            self.m.definidos.add(nodo.name)
        for d in [*nodo.decorator_list, *nodo.bases, *nodo.keywords]:
            self.visit(d)
        self.pila.append(nodo.name)
        self.clase.append((nodo.name, con_bases))
        for s in nodo.body:
            self.visit(s)
        self.clase.pop()
        self.pila.pop()

    def visit_If(self, nodo):
        prueba = nodo.test
        es_main = (
            not self.pila and isinstance(prueba, ast.Compare) and isinstance(prueba.left, ast.Name)
            and prueba.left.id == "__name__"
        )
        es_tc = (punteado(prueba) or "").endswith("TYPE_CHECKING")
        self._rama()
        self.visit(prueba)
        antes = self.en_main
        self.en_main = self.en_main or es_main
        self.tipo_checking += es_tc
        for s in nodo.body:
            self.visit(s)
        self.tipo_checking -= es_tc
        self.en_main = antes
        for s in nodo.orelse:
            self.visit(s)

    def _try(self, nodo):
        tipos = set()
        for h in nodo.handlers:
            t = _tipos_except(h.type)
            tipos.update(t if t is not None else ["BaseException"])
        protege = bool(tipos & _EXCEPCIONES_IMPORT)
        self.protegida += protege
        for s in nodo.body:
            self.visit(s)
        self.protegida -= protege
        for h in nodo.handlers:
            self._rama()
            self.m.excepts.append(Except(h.lineno, _tipos_except(h.type), _cuerpo_silencioso(h.body), self._contexto()))
            self.visit(h)
        for s in [*nodo.orelse, *nodo.finalbody]:
            self.visit(s)

    visit_Try = _try
    visit_TryStar = _try

    # -- importaciones -------------------------------------------------------
    def _registrar(self, imp: Importacion):
        self.m.importaciones.append(imp)
        if not self.pila:
            self.m.definidos.update(n for n, _ in imp.ligados)

    def visit_Import(self, nodo):
        for a in nodo.names:
            ligado = a.asname or a.name.split(".")[0]
            self.alias[ligado] = a.name if a.asname else a.name.split(".")[0]
            self._registrar(Importacion(
                a.name, [], nodo.lineno, not self.en_funcion, bool(self.protegida), bool(self.tipo_checking),
                [(ligado, a.name if a.asname != a.name else "__reexporta__")],
            ))

    def visit_ImportFrom(self, nodo):
        if nodo.level:
            base = self.m.paquete.split(".") if self.m.paquete else []
            subir = nodo.level - 1
            base = base[: len(base) - subir] if subir else base
            modulo = ".".join([*base, *(nodo.module.split(".") if nodo.module else [])])
        else:
            modulo = nodo.module or ""
        if modulo == "__future__":
            return
        nombres = [a.name for a in nodo.names]
        if "*" in nombres:
            self.m.comodin = True
        ligados = []
        for a in nodo.names:
            if a.name == "*":
                continue
            ligado = a.asname or a.name
            self.alias[ligado] = f"{modulo}.{a.name}"
            ligados.append((ligado, "__reexporta__" if a.asname == a.name else a.name))
        self._registrar(Importacion(
            modulo, nombres, nodo.lineno, not self.en_funcion, bool(self.protegida), bool(self.tipo_checking), ligados,
        ))

    # -- nombres -------------------------------------------------------------
    def visit_Name(self, nodo):
        if not isinstance(nodo.ctx, ast.Store):
            self.m.usados[nodo.id] += 1

    def visit_Attribute(self, nodo):
        self.m.usados[nodo.attr] += 1
        if nodo.attr == "parent" and isinstance(nodo.value, ast.Attribute) and nodo.value.attr == "parent" \
                and _contiene_file(nodo.value):
            self._raiz(nodo.lineno)
        self.visit(nodo.value)

    def visit_Subscript(self, nodo):
        if isinstance(nodo.value, ast.Attribute) and nodo.value.attr == "parents" and _contiene_file(nodo.value):
            indice = nodo.slice
            if not (isinstance(indice, ast.Constant) and indice.value == 0):
                self._raiz(nodo.lineno)
        self.generic_visit(nodo)

    def _raiz(self, linea: int):
        if linea not in self.m.raiz_proyecto:
            self.m.raiz_proyecto.append(linea)

    # -- complejidad ---------------------------------------------------------
    def _rama(self, n: int = 1):
        if self.funcs:
            self.funcs[-1].complejidad += n

    def _bucle(self, nodo):
        self._rama()
        self.generic_visit(nodo)

    visit_For = visit_AsyncFor = visit_While = visit_IfExp = visit_match_case = _bucle

    def visit_BoolOp(self, nodo):
        self._rama(len(nodo.values) - 1)
        self.generic_visit(nodo)

    def visit_comprehension(self, nodo):
        self._rama(1 + len(nodo.ifs))
        self.generic_visit(nodo)

    def visit_Constant(self, nodo):
        if isinstance(nodo.value, str) and len(nodo.value) <= 200:
            self.m.cadenas.add(nodo.value)

    def visit_Call(self, nodo):
        nombre = punteado(nodo.func)
        if nombre:
            cabeza, _, resto = nombre.partition(".")
            if cabeza in self.alias:
                nombre = self.alias[cabeza] + ("." + resto if resto else "")
            self.m.llamadas.append(Llamada(
                nombre, nodo.lineno, self._contexto(), self.en_main, bool(self.asincronas and self.asincronas[-1]), nodo,
            ))
            if nombre.endswith("os.path.dirname") and nodo.args and isinstance(nodo.args[0], ast.Call) \
                    and (punteado(nodo.args[0].func) or "").endswith("dirname") and _contiene_file(nodo.args[0]):
                self._raiz(nodo.lineno)
        self.generic_visit(nodo)

    def visit_Assign(self, nodo):
        for t in nodo.targets:
            if not self.pila:
                for n in ast.walk(t):
                    if isinstance(n, ast.Name):
                        self.m.definidos.add(n.id)
            if isinstance(t, ast.Name) and t.id == "__all__" and isinstance(nodo.value, (ast.List, ast.Tuple)):
                self.m.todos.update(e.value for e in nodo.value.elts if isinstance(e, ast.Constant))
        self.generic_visit(nodo)

    def visit_AnnAssign(self, nodo):
        if not self.pila and isinstance(nodo.target, ast.Name):
            self.m.definidos.add(nodo.target.id)
        self.generic_visit(nodo)

    def visit_Global(self, nodo):
        self.m.definidos.update(nodo.names)


# ---------------------------------------------------------------------------
# Repo
# ---------------------------------------------------------------------------

class Repo:
    def __init__(self, raiz: Path, config: dict):
        self.raiz = Path(raiz).resolve()
        self.config = config
        exclusiones = config["general"]["exclusiones"]
        listado = _listar_git(self.raiz)
        self.es_git = listado is not None
        if listado is None:
            listado = _listar_disco(self.raiz, exclusiones)
        self.archivos = [
            p for p in listado
            if not excluido(p, exclusiones) and (self.raiz / p).is_file()
        ]
        self._textos: dict[str, tuple[bytes, str | None]] = {}

    # -- texto ---------------------------------------------------------------
    def bytes_de(self, ruta: str) -> bytes:
        if ruta not in self._textos:
            datos = (self.raiz / ruta).read_bytes()
            try:
                texto = datos.decode("utf-8")
            except UnicodeDecodeError:
                texto = None
            self._textos[ruta] = (datos, texto)
        return self._textos[ruta][0]

    def texto_de(self, ruta: str) -> str | None:
        """Texto UTF-8 (sin BOM) o None si no es UTF-8 válido."""
        self.bytes_de(ruta)
        texto = self._textos[ruta][1]
        return texto[1:] if texto and texto.startswith("\ufeff") else texto

    def tamano(self, ruta: str) -> int:
        return (self.raiz / ruta).stat().st_size

    def textos(self, extensiones: list[str]) -> list[str]:
        maximo = self.config["higiene"]["max_kb_texto"] * 1024
        return [
            p for p in self.archivos
            if os.path.splitext(p)[1].lower() in extensiones and self.tamano(p) <= maximo
        ]

    # -- Python --------------------------------------------------------------
    @cached_property
    def modulos(self) -> dict[str, ModuloPy]:
        salida: dict[str, ModuloPy] = {}
        de_raiz_import: set[str] = set()
        raices = [r.strip("/") + "/" for r in self.config["general"].get("raices_import", [])]
        for ruta in self.archivos:
            if not ruta.endswith(".py"):
                continue
            # Carpetas que funcionan como raíz de sys.path (p. ej. backend/ con `from app...`).
            raiz = next((r for r in raices if ruta.startswith(r)), None)
            nombre = nombre_modulo(ruta[len(raiz):] if raiz else ruta)
            if nombre in salida and nombre in de_raiz_import and not raiz:
                continue  # el nombre lo reclama la raíz de importación declarada
            if raiz:
                de_raiz_import.add(nombre)
            texto = self.texto_de(ruta)
            mod = ModuloPy(ruta, nombre, ruta.endswith("__init__.py"), texto or "", None)
            if texto is None:
                mod.error = "no es UTF-8 válido"
            else:
                try:
                    mod.arbol = ast.parse(texto, filename=ruta)
                except (SyntaxError, ValueError) as e:
                    mod.error = f"{type(e).__name__}: {e}"
            if mod.arbol is not None:
                _Indexador(mod).visit(mod.arbol)
            salida[mod.nombre] = mod
        return salida

    @cached_property
    def por_ruta(self) -> dict[str, ModuloPy]:
        return {m.ruta: m for m in self.modulos.values()}

    @cached_property
    def paquetes(self) -> set[str]:
        """Paquetes (con o sin __init__) que contienen módulos del repo."""
        salida = set()
        for nombre, mod in self.modulos.items():
            partes = nombre.split(".")
            for i in range(1, len(partes) + (1 if mod.es_paquete else 0)):
                salida.add(".".join(partes[:i]))
        return salida

    def existe(self, modulo: str) -> bool:
        return modulo in self.modulos or modulo in self.paquetes

    @cached_property
    def raices_python(self) -> set[str]:
        """Nombres de primer nivel importables del repo (src, tools, tests, app…)."""
        return {n.split(".")[0] for n in self.modulos}

    def es_propio(self, modulo: str) -> bool:
        return modulo.split(".")[0] in self.raices_python

    def tiene_nombre(self, modulo: str, nombre: str) -> bool:
        """`from modulo import nombre` resuelve."""
        if self.existe(f"{modulo}.{nombre}"):
            return True
        mod = self.modulos.get(modulo)
        if mod is None:
            return False
        return mod.comodin or mod.arbol is None or nombre in mod.definidos

    def destinos(self, imp: Importacion) -> list[str]:
        """Módulos del repo que carga una importación (hoja, sin padres)."""
        if not self.es_propio(imp.modulo):
            return []
        salida = []
        if imp.nombres:
            for n in imp.nombres:
                sub = f"{imp.modulo}.{n}"
                if sub in self.modulos:
                    salida.append(sub)
                elif imp.modulo in self.modulos:
                    salida.append(imp.modulo)
        elif imp.modulo in self.modulos:
            salida.append(imp.modulo)
        return list(dict.fromkeys(salida))

    @cached_property
    def importadores(self) -> dict[str, set[str]]:
        """módulo → módulos que lo importan (cualquier importación)."""
        salida: dict[str, set[str]] = {}
        for mod in self.modulos.values():
            for imp in mod.importaciones:
                objetivos = set(self.destinos(imp))
                # `import a.b.c` también carga los __init__ de a y a.b
                partes = imp.modulo.split(".")
                for i in range(1, len(partes)):
                    padre = ".".join(partes[:i])
                    if padre in self.modulos:
                        objetivos.add(padre)
                for d in objetivos:
                    if d != mod.nombre:
                        salida.setdefault(d, set()).add(mod.nombre)
        return salida

    @cached_property
    def importados_de(self) -> set[tuple[str, str]]:
        """(módulo, nombre) de cada `from módulo import nombre` del repo."""
        return {(imp.modulo, n) for mod in self.modulos.values() for imp in mod.importaciones for n in imp.nombres}

    @cached_property
    def usados_global(self) -> Counter:
        total: Counter = Counter()
        for mod in self.modulos.values():
            total.update(mod.usados)
            for cadena in mod.cadenas:
                for parte in cadena.replace("/", ".").split("."):
                    if parte.isidentifier():
                        total[parte] += 1
        return total

    @cached_property
    def menciones_texto(self) -> str:
        """Texto de scripts y documentación (para módulos usados desde fuera de Python)."""
        trozos = []
        for ruta in self.textos([".ps1", ".bat", ".cmd", ".sh", ".md", ".toml", ".yml", ".yaml"]):
            texto = self.texto_de(ruta)
            if texto:
                trozos.append(texto)
        for mod in self.modulos.values():
            trozos.extend(c for c in mod.cadenas if "." in c or "/" in c)
        return "\n".join(trozos)

    def en_codigo(self, ruta: str) -> bool:
        return bajo(ruta, self.config["general"]["codigo"])

    def en_pruebas(self, ruta: str) -> bool:
        return bajo(ruta, self.config["general"]["pruebas"])

    def es_prueba_por_nombre(self, ruta: str) -> bool:
        return fnmatch.fnmatchcase(ruta.rsplit("/", 1)[-1], self.config["pruebas"]["patron_archivo"])


def decorador_inocuo(nombre: str) -> bool:
    return nombre in _DECORADORES_INOCUOS or nombre.rsplit(".", 1)[-1] in {"setter", "getter", "deleter"}
