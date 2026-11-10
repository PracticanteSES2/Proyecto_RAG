"""FastAPI (backend/): routers en api/v1, esquemas pydantic, routers delgados,
nada bloqueante en `async def` y configuración centralizada con pydantic-settings."""
from __future__ import annotations

import ast

from tools.doctor.modelo import Hallazgo
from tools.doctor.repo import ModuloPy, Repo, bajo, punteado

_VERBOS = {"get", "post", "put", "patch", "delete", "options", "head", "api_route", "websocket"}
_GETENV = {"os.getenv", "os.environ.get", "os.putenv", "os.environ.setdefault"}
_SUELTOS = {"dict", "Dict", "Any", "typing.Any", "typing.Dict", "object", "list", "List", "JSONResponse"}


def _h(regla, severidad, archivo, linea, mensaje, sugerencia, clave):
    return Hallazgo("fastapi", regla, severidad, archivo, linea, mensaje, sugerencia, clave)


def _usa_fastapi(mod: ModuloPy) -> bool:
    return any(i.modulo.split(".")[0] == "fastapi" for i in mod.importaciones)


def _decorador_ruta(dec: ast.AST) -> ast.Call | None:
    if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr in _VERBOS:
        return dec
    return None


def _anotacion_suelta(nodo: ast.AST | None) -> bool:
    if nodo is None:
        return False
    if isinstance(nodo, ast.Subscript):  # dict[str, Any], list[dict], Optional[dict]…
        base = punteado(nodo.value) or ""
        if base in ("dict", "Dict", "typing.Dict"):
            return True
        return _anotacion_suelta(nodo.slice) if not isinstance(nodo.slice, ast.Tuple) else any(
            _anotacion_suelta(e) for e in nodo.slice.elts)
    if isinstance(nodo, ast.BinOp):  # dict | None
        return _anotacion_suelta(nodo.left) or _anotacion_suelta(nodo.right)
    return (punteado(nodo) or "") in ("dict", "Dict", "typing.Dict", "Any", "typing.Any")


def _endpoints(mod: ModuloPy):
    for f in mod.funciones:
        for dec in f.nodo.decorator_list:
            llamada = _decorador_ruta(dec)
            if llamada is not None:
                yield f, llamada
                break


def _configuracion(mod: ModuloPy, cfg: dict) -> list[Hallazgo]:
    if bajo(mod.ruta, cfg["modulos_settings"]):
        if any(i.modulo.startswith("pydantic_settings") for i in mod.importaciones):
            return []
        return [_h(
            "settings_sin_pydantic", "media", mod.ruta, 1,
            "El módulo de configuración no usa `pydantic_settings.BaseSettings`.",
            "Definir `class Settings(BaseSettings)` y exponer una instancia cacheada (`get_settings`).",
            "settings",
        )]
    return [
        _h(
            "getenv_disperso", "media", mod.ruta, c.linea,
            f"`{c.nombre}` fuera del módulo de configuración (en `{c.contexto}`).",
            f"Declarar el valor en la clase `Settings` (pydantic-settings) de {cfg['modulos_settings'][0]} e inyectarla.",
            f"{c.contexto}:{c.nombre}",
        )
        for c in mod.llamadas if c.nombre in _GETENV
    ]


def _bloqueantes(mod: ModuloPy, bloqueantes: set[str]) -> list[Hallazgo]:
    return [
        _h(
            "bloqueante_en_async", "alta", mod.ruta, c.linea,
            f"`{c.nombre}` bloquea el event loop dentro de `async def {c.contexto}`.",
            "Usar la variante async (httpx.AsyncClient, asyncio.sleep, redis.asyncio, aiofiles) "
            "o `await run_in_threadpool(...)`; o declarar el endpoint con `def`.",
            f"{c.contexto}:{c.nombre}",
        )
        for c in mod.llamadas if c.en_async and c.nombre in bloqueantes
    ]


def _ubicacion_routers(mod: ModuloPy, cfg: dict, en_routers: bool) -> list[Hallazgo]:
    carpeta = cfg["carpeta_routers"][0]
    salida = []
    crea_router = [c for c in mod.llamadas if c.nombre.endswith("APIRouter")]
    if crea_router and not en_routers:
        salida.append(_h(
            "router_fuera_de_api", "media", mod.ruta, crea_router[0].linea,
            f"`APIRouter` definido fuera de {carpeta}/.",
            f"Mover el router a {carpeta}/<recurso>.py e incluirlo desde el router de la versión.",
            "router",
        ))
    if en_routers:
        salida += [
            _h(
                "router_importa_motor", "media", mod.ruta, imp.linea,
                f"El router importa el motor directamente (`{imp.modulo}`).",
                "Llamar a un servicio de backend/app/services/ que envuelva el motor; el router solo traduce HTTP.",
                imp.modulo,
            )
            for imp in mod.importaciones
            if any(imp.modulo == p or imp.modulo.startswith(p + ".") for p in cfg["motor_prohibido_en_routers"])
        ]
    elif not bajo(mod.ruta, cfg["endpoints_permitidos_fuera"]):
        salida += [
            _h(
                "router_fuera_de_api", "media", mod.ruta, f.linea,
                f"Endpoint `{f.qual}` declarado fuera de {carpeta}/.",
                "Declararlo en un router versionado de api/v1.",
                f"endpoint:{f.qual}",
            )
            for f, _ in _endpoints(mod)
        ]
    return salida


def _sin_modelo(dec: ast.Call, retorno: ast.AST | None) -> bool:
    kw = {k.arg for k in dec.keywords}
    if dec.func.attr == "websocket" or kw & {"response_model", "response_class"}:
        return False
    return retorno is None or _anotacion_suelta(retorno) or (punteado(retorno) or "") in _SUELTOS


def _endpoint(mod: ModuloPy, f, dec: ast.Call, cfg: dict) -> list[Hallazgo]:
    salida = []
    if _sin_modelo(dec, f.nodo.returns):
        salida.append(_h(
            "sin_response_model", "media", mod.ruta, f.linea,
            f"El endpoint `{f.qual}` no declara `response_model` ni un modelo de retorno.",
            "Definir un esquema pydantic en backend/app/schemas/ y usarlo como `response_model` o anotación de retorno.",
            f.qual,
        ))
    args = f.nodo.args
    salida += [
        _h(
            "dict_suelto", "media", mod.ruta, f.linea,
            f"El parámetro `{arg.arg}` de `{f.qual}` es un dict suelto.",
            "Recibir un modelo pydantic (backend/app/schemas/) para validar la entrada.",
            f"{f.qual}:{arg.arg}",
        )
        for arg in [*args.posonlyargs, *args.args, *args.kwonlyargs] if _anotacion_suelta(arg.annotation)
    ]
    largo = f.fin - f.linea + 1
    if largo > cfg["max_lineas_endpoint"] or f.complejidad > cfg["max_complejidad_endpoint"]:
        salida.append(_h(
            "logica_en_router", "media", mod.ruta, f.linea,
            f"El endpoint `{f.qual}` tiene {largo} líneas y complejidad {f.complejidad}: lógica de negocio en el router.",
            "Mover la lógica a un servicio (backend/app/services/) y dejar el endpoint en validar → llamar → responder.",
            f.qual,
        ))
    return salida


def revisar(repo: Repo) -> list[Hallazgo]:
    cfg = repo.config["fastapi"]
    bloqueantes = set(cfg["bloqueantes"])
    salida: list[Hallazgo] = []
    for mod in repo.modulos.values():
        if not bajo(mod.ruta, cfg["aplica_a"]) or mod.arbol is None or repo.en_pruebas(mod.ruta):
            continue
        salida += _configuracion(mod, cfg) + _bloqueantes(mod, bloqueantes)
        if not _usa_fastapi(mod):
            continue
        salida += _ubicacion_routers(mod, cfg, bajo(mod.ruta, cfg["carpeta_routers"]))
        for f, dec in _endpoints(mod):
            salida += _endpoint(mod, f, dec, cfg)
    return salida
