"""Documentación viva desde la API: explorar, proponer (asíncrono), revisar,
aprobar y reindexar. Contrato: specs/013-documentacion-web/contracts/api-documentacion.md.

- Lectura: `src.docs_md.repositorio` sobre la raíz de documentos (por defecto
  `<RAG_RAIZ_DATOS>/docs_tableros`). Solo se aceptan grupos y archivos que el
  repositorio lista (nada de rutas que vengan del cliente).
- Propuestas: `actualizador.proponer_cambio` corre en un hilo; la API responde
  202 y el cliente sondea. MedGemma pasa por `call_llm` (lo hace el
  actualizador) y un `ProveedorObservado` marca la etapa real. Las propuestas
  viven en la memoria de este proceso (24 h, máx. 200).
- Aprobar: `actualizador.aplicar_propuesta` (revalida contra el archivo
  actual) y lanza la reindexación del grupo en un hilo propio, coordinada con
  el motor por `CoordinadorIndice`.
"""
from __future__ import annotations

import logging
import secrets
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from backend.app.core import errores
from backend.app.services import documentacion_vista as vista
from backend.app.services.almacen import ahora_iso
from backend.app.services.documentacion_indice import CoordinadorIndice, IndiceNoDisponible, mensaje_resultado
from backend.app.services.documentacion_progreso import ETAPA_INICIAL, ProveedorObservado, progreso, proveedor_medgemma
from src.docs_md import repositorio
from src.docs_md.actualizador import Propuesta
from src.docs_md.formato import ErrorFormato, ErrorOperacion, normalizar_nombre

LOG = logging.getLogger(__name__)

VIDA_S = 24 * 3600
MAX_PROPUESTAS = 200
ERROR_INESPERADO = ("No se pudo preparar la propuesta: ocurrió un error inesperado. Intenta de nuevo en un momento, "
                    "por favor.")


def _proponer_real(*args, **kwargs):
    from src.docs_md.actualizador import proponer_cambio

    return proponer_cambio(*args, **kwargs)


def _aplicar_real(*args, **kwargs):
    from src.docs_md.actualizador import aplicar_propuesta

    return aplicar_propuesta(*args, **kwargs)


@dataclass
class _Registro:
    id: str
    grupo: str
    nota: str
    pagina: str | None
    cambios_pbip: list[str]
    autor: str
    estado: str = "preparando"
    propuesta: Propuesta | None = None
    segundos: float | None = None
    etapa: str = ETAPA_INICIAL
    inicio: float = 0.0
    desde_etapa: float = 0.0
    generacion: int = 0
    aprobacion: dict | None = None
    creada: str = field(default_factory=ahora_iso)
    actualizada: str = field(default_factory=ahora_iso)


class ServicioDocumentacion:
    def __init__(self, raiz_docs: Path, coordinador: CoordinadorIndice, proponer: Callable | None = None,
                 aplicar: Callable | None = None, fabrica_llm: Callable | None = None,
                 reloj: Callable[[], float] = time.monotonic, hilos: int = 2):
        self.raiz = Path(raiz_docs)
        self.coordinador = coordinador
        self._proponer = proponer or _proponer_real
        self._aplicar = aplicar or _aplicar_real
        self._fabrica_llm = fabrica_llm or proveedor_medgemma
        self._reloj = reloj
        self._candado = threading.RLock()
        self._guardando = threading.Lock()
        self._propuestas: dict[str, _Registro] = {}
        self._reindexaciones: dict[str, dict] = {}
        self._hilos = ThreadPoolExecutor(max_workers=hilos, thread_name_prefix="doc-propuesta")
        self._hilo_indice = ThreadPoolExecutor(max_workers=1, thread_name_prefix="doc-reindexar")

    def cerrar(self) -> None:
        self._hilos.shutdown(wait=False, cancel_futures=True)
        self._hilo_indice.shutdown(wait=False, cancel_futures=True)

    # ------------------------------------------------------------ explorar
    def _tableros(self) -> dict[str, dict]:
        return {t["source_group"]: t for t in repositorio.listar_tableros(self.raiz)}

    def _tablero(self, grupo: str) -> dict:
        tablero = self._tableros().get(grupo)
        if tablero is None:
            raise errores.error(errores.GRUPO_NO_ENCONTRADO)
        return tablero

    def grupos(self) -> list[dict]:
        return [{"grupo": t["source_group"], "tablero": t["tablero"], "paginas": t["paginas"]}
                for t in self._tableros().values()]

    def _paginas(self, grupo: str) -> list[dict]:
        return [dict(p, general=p["archivo"] == repositorio.ARCHIVO_GENERAL, etiqueta=vista.etiqueta_pagina(p))
                for p in repositorio.listar_paginas(grupo, self.raiz)]

    def paginas(self, grupo: str) -> dict:
        tablero = self._tablero(grupo)
        return {"grupo": grupo, "tablero": tablero["tablero"], "paginas": self._paginas(grupo)}

    def documento(self, grupo: str, archivo: str) -> dict:
        tablero = self._tablero(grupo)
        if archivo not in {p["archivo"] for p in repositorio.listar_paginas(grupo, self.raiz)}:
            raise errores.error(errores.PAGINA_NO_ENCONTRADA)
        try:
            texto = (repositorio.carpeta_md(grupo, self.raiz) / archivo).read_text(encoding="utf-8")
        except OSError as error:
            LOG.warning("No se pudo leer %s/%s: %s", grupo, archivo, error)
            raise errores.error(errores.PAGINA_NO_ENCONTRADA) from error
        return vista.documento(grupo, tablero["tablero"], archivo, texto)

    def _validar_pagina(self, grupo: str, pagina: str | None) -> str | None:
        if not pagina:
            return None
        try:
            repositorio.ruta_pagina(grupo, pagina, self.raiz)
        except repositorio.ErrorRepositorio as error:
            raise errores.error(errores.PAGINA_NO_ENCONTRADA) from error
        return pagina

    # ------------------------------------------------------------ propuestas
    def _registro(self, pid: str) -> _Registro:
        registro = self._propuestas.get(pid)
        if registro is None:
            raise errores.error(errores.PROPUESTA_NO_ENCONTRADA)
        return registro

    def _purgar(self) -> None:
        limite = self._reloj() - VIDA_S
        for pid in [p for p, r in self._propuestas.items() if r.inicio < limite]:
            del self._propuestas[pid]
        while len(self._propuestas) >= MAX_PROPUESTAS:
            del self._propuestas[next(iter(self._propuestas))]

    def crear_propuesta(self, nota: str, grupo: str, pagina: str | None, cambios_pbip: list[str] | None,
                        autor: str) -> dict:
        self._tablero(grupo)
        pagina = self._validar_pagina(grupo, pagina)
        with self._candado:
            self._purgar()
            registro = _Registro(id=secrets.token_hex(16), grupo=grupo, nota=nota.strip(), pagina=pagina,
                                 cambios_pbip=list(cambios_pbip or []), autor=(autor or "").strip())
            self._propuestas[registro.id] = registro
            self._lanzar(registro)
            return self._vista(registro)

    def _lanzar(self, registro: _Registro) -> None:
        """Marca la propuesta en preparación y encola su generación (con el candado tomado)."""
        ahora = self._reloj()
        registro.generacion += 1
        registro.estado, registro.propuesta, registro.segundos = "preparando", None, None
        registro.etapa, registro.inicio, registro.desde_etapa = ETAPA_INICIAL, ahora, ahora
        registro.actualizada = ahora_iso()
        self._hilos.submit(self._generar, registro, registro.generacion)

    def _marcar_etapa(self, registro: _Registro, generacion: int, etapa: str) -> None:
        with self._candado:
            if registro.generacion == generacion and registro.estado == "preparando" and registro.etapa != etapa:
                registro.etapa, registro.desde_etapa = etapa, self._reloj()

    def _generar(self, registro: _Registro, generacion: int) -> None:
        llm = ProveedorObservado(self._fabrica_llm, lambda etapa: self._marcar_etapa(registro, generacion, etapa))
        inicio = self._reloj()
        try:
            propuesta = self._proponer(registro.nota, registro.grupo, pagina=registro.pagina, llm=llm,
                                       cambios_pbip=registro.cambios_pbip or None, raiz=self.raiz)
        except Exception:
            LOG.exception("No se pudo preparar la propuesta %s", registro.id)
            propuesta = Propuesta(nota=registro.nota, source_group=registro.grupo, pagina=registro.pagina or "",
                                  estado="error", errores=[ERROR_INESPERADO])
        with self._candado:
            if registro.generacion != generacion or registro.estado != "preparando":
                return  # la reemplazó una aclaración o se descartó
            registro.propuesta, registro.estado = propuesta, propuesta.estado
            registro.segundos = round(self._reloj() - inicio, 2)
            registro.actualizada = ahora_iso()

    def propuesta(self, pid: str) -> dict:
        with self._candado:
            return self._vista(self._registro(pid))

    def aclarar(self, pid: str, nota: str, pagina: str | None) -> dict:
        with self._candado:
            registro = self._registro(pid)
            if registro.estado == "preparando":
                raise errores.error(errores.PROPUESTA_EN_CURSO)
            if registro.estado == "aprobada":
                raise errores.error(errores.PROPUESTA_NO_APROBABLE)
            registro.pagina = self._validar_pagina(registro.grupo, pagina)
            registro.nota = nota.strip()
            self._lanzar(registro)
            return self._vista(registro)

    def descartar(self, pid: str) -> dict:
        with self._candado:
            registro = self._registro(pid)
            if registro.estado == "aprobada":
                raise errores.error(errores.PROPUESTA_NO_APROBABLE)
            registro.generacion += 1
            registro.estado, registro.actualizada = "descartada", ahora_iso()
            return self._vista(registro)

    def corregir(self, pid: str, textos: dict[int, str]) -> dict:
        """«Actualizar vista previa»: reaplica las operaciones con los textos corregidos."""
        with self._candado:
            registro = self._registro(pid)
            self._exigir_lista(registro, errores.PROPUESTA_NO_EDITABLE)
            propuesta = registro.propuesta
            operaciones = list(propuesta.operaciones)
            for indice, texto in textos.items():
                if not 0 <= indice < len(operaciones) or operaciones[indice].accion == "eliminar":
                    raise errores.correccion_invalida(f"la operación {indice + 1} no se puede editar.")
                operaciones[indice] = type(operaciones[indice])(**{**operaciones[indice].a_dict(),
                                                                    "texto": texto.strip()})
            try:
                registro.propuesta = vista.reaplicar(propuesta, operaciones)
            except (ErrorOperacion, ErrorFormato) as error:
                raise errores.correccion_invalida(str(error)) from error
            registro.actualizada = ahora_iso()
            return self._vista(registro)

    def _exigir_lista(self, registro: _Registro, definicion) -> None:
        if registro.estado == "preparando":
            raise errores.error(errores.PROPUESTA_EN_CURSO)
        if registro.estado != "lista" or registro.propuesta is None:
            raise errores.error(definicion)

    # ------------------------------------------------------------ aprobar
    def aprobar(self, pid: str, autor: str) -> dict:
        with self._candado:
            registro = self._registro(pid)
            self._exigir_lista(registro, errores.PROPUESTA_NO_APROBABLE)
            if not self._puede_aprobar(registro):
                raise errores.error(errores.PROPUESTA_NO_APROBABLE)
            propuesta = registro.propuesta
        with self._guardando:
            try:
                self._aplicar(propuesta, autor.strip(), raiz=self.raiz)
            except ValueError as error:  # ErrorActualizacion: el archivo cambió o no se pudo guardar
                raise errores.documento_modificado(str(error)) from error
        version = None
        try:
            version = repositorio.leer_pagina(registro.grupo, propuesta.pagina, self.raiz).meta.get("version")
        except (repositorio.ErrorRepositorio, ErrorFormato, OSError):
            LOG.warning("No se pudo leer la versión guardada de %s", propuesta.pagina, exc_info=True)
        with self._candado:
            registro.estado, registro.autor, registro.actualizada = "aprobada", autor.strip(), ahora_iso()
            registro.aprobacion = {"autor": autor.strip(), "version": version, "fecha": ahora_iso()}
            self._lanzar_reindexacion(registro.grupo)
            return self._vista(registro)

    # ------------------------------------------------------------ reindexar
    def _estado_reindexacion(self, grupo: str) -> dict:
        return dict(self._reindexaciones.get(grupo) or {
            "grupo": grupo, "estado": "sin_iniciar", "mensaje": "", "documentos": None, "chunks": None,
            "segundos": None, "conexion_compartida": False, "avisos": [], "iniciada": None, "terminada": None})

    def _lanzar_reindexacion(self, grupo: str) -> dict:
        with self._candado:
            actual = self._reindexaciones.get(grupo)
            if actual and actual["estado"] == "en_curso":
                return dict(actual)
            estado = dict(self._estado_reindexacion(grupo), estado="en_curso", iniciada=ahora_iso(), terminada=None,
                          mensaje="Actualizando el buscador del asistente…", avisos=[])
            self._reindexaciones[grupo] = estado
            self._hilo_indice.submit(self._reindexar, grupo)
            return dict(estado)

    def _reindexar(self, grupo: str) -> None:
        tablero = (self._tableros().get(grupo) or {}).get("tablero", grupo)
        cambios: dict = {}
        try:
            resultado = self.coordinador.reindexar(grupo)
            estado, mensaje = mensaje_resultado(resultado, tablero)
            cambios = {"documentos": resultado.get("documentos"), "chunks": resultado.get("chunks"),
                       "segundos": resultado.get("segundos"), "avisos": list(resultado.get("avisos") or []),
                       "conexion_compartida": bool(resultado.get("cliente_compartido"))}
        except IndiceNoDisponible as aviso:
            estado, mensaje = "no_disponible", str(aviso)
        except Exception:
            LOG.exception("La reindexación de %s falló", grupo)
            estado, mensaje = "error", "La reindexación falló por un error inesperado. Puedes reintentarla."
        with self._candado:
            self._reindexaciones[grupo] = dict(self._estado_reindexacion(grupo), estado=estado, mensaje=mensaje,
                                               terminada=ahora_iso(), **cambios)

    def reindexar(self, grupo: str) -> dict:
        self._tablero(grupo)
        return self._lanzar_reindexacion(grupo)

    def reindexacion(self, grupo: str) -> dict:
        self._tablero(grupo)
        with self._candado:
            return self._estado_reindexacion(grupo)

    # ------------------------------------------------------------ vista
    @staticmethod
    def _puede_aprobar(registro: _Registro) -> bool:
        propuesta = registro.propuesta
        return (registro.estado == "lista" and propuesta is not None and bool(propuesta.operaciones)
                and not vista.formato_resultado(propuesta))

    def _candidatas(self, propuesta: Propuesta, paginas: list[dict]) -> list[dict]:
        etiquetas = {p["pagina"]: p["etiqueta"] for p in paginas}
        nombres = [c for c in propuesta.candidatas if c in etiquetas] or list(etiquetas)
        return [{"pagina": nombre, "etiqueta": etiquetas[nombre]} for nombre in nombres]

    def _vista(self, registro: _Registro) -> dict:
        propuesta = registro.propuesta
        tablero = (self._tableros().get(registro.grupo) or {}).get("tablero", registro.grupo)
        datos = {
            "propuesta_id": registro.id, "grupo": registro.grupo, "tablero": tablero, "estado": registro.estado,
            "nota": registro.nota, "pagina": registro.pagina or "", "nombre_funcional": "",
            "autor": registro.autor, "cambios_pbip": registro.cambios_pbip, "progreso": None,
            "como_se_eligio": "", "resumen": "", "dudas": [], "avisos": [], "errores": [], "operaciones": [],
            "diff": None, "vista_previa": None, "formato_valido": False, "errores_formato": [], "candidatas": [],
            "tiempos": "", "detalle_tecnico": None, "puede_aprobar": self._puede_aprobar(registro),
            "aprobacion": None, "creada": registro.creada, "actualizada": registro.actualizada,
        }
        if registro.estado == "preparando":
            datos["progreso"] = progreso(registro.etapa, registro.desde_etapa, registro.inicio, self._reloj())
        if propuesta is not None:
            datos.update(self._vista_propuesta(registro, propuesta))
        if registro.aprobacion is not None:
            datos["aprobacion"] = dict(registro.aprobacion,
                                       reindexacion=self._estado_reindexacion(registro.grupo))
        return datos

    @staticmethod
    def _nombre_funcional(paginas: list[dict], pagina: str) -> str:
        clave = normalizar_nombre(pagina or "")
        if not clave:
            return ""
        return next((p["nombre_funcional"] for p in paginas if normalizar_nombre(p["pagina"]) == clave), "")

    def _vista_propuesta(self, registro: _Registro, propuesta: Propuesta) -> dict:
        paginas = self._paginas(registro.grupo)
        nombre_funcional = self._nombre_funcional(paginas, propuesta.pagina)
        datos = {"pagina": propuesta.pagina or registro.pagina or "", "nombre_funcional": nombre_funcional,
                 "como_se_eligio": vista.como_se_eligio(propuesta), "resumen": propuesta.resumen,
                 "dudas": list(propuesta.dudas), "avisos": list(propuesta.avisos), "errores": list(propuesta.errores),
                 "tiempos": vista.tiempos_texto(registro.segundos, propuesta.tiempos_llm)}
        if propuesta.estado == "error":
            datos["detalle_tecnico"] = propuesta.llm_raw or None
        if propuesta.estado == "requiere_aclaracion":
            datos["candidatas"] = self._candidatas(propuesta, paginas)
        if propuesta.operaciones and propuesta.despues:
            datos.update(self._vista_cambios(propuesta))
        return datos

    @staticmethod
    def _vista_cambios(propuesta: Propuesta) -> dict:
        errores_formato = vista.formato_resultado(propuesta)
        return {"operaciones": vista.operaciones(propuesta), "diff": vista.diff(propuesta),
                "vista_previa": vista.vista_previa(propuesta.despues), "errores_formato": errores_formato,
                "formato_valido": not errores_formato}


# ---------------------------------------------------------------- fábrica

def raiz_documentos(ajustes) -> Path:
    """DOCS_MD_ROOT si está definida; si no `<RAG_RAIZ_DATOS>/docs_tableros`
    (la misma raíz de datos del motor) o la de `repositorio`."""
    if ajustes.docs_md_root:
        return Path(ajustes.docs_md_root)
    candidata = Path(ajustes.rag_raiz_datos) / "docs_tableros"
    return candidata if candidata.is_dir() else repositorio.raiz_documentos()


def crear_servicio_documentacion(servicios) -> ServicioDocumentacion:
    """Servicio real: actualizador con MedGemma y reindexación coordinada con
    el motor embebido de `servicios` (su trabajador aparece cuando arranca)."""
    ajustes = servicios.ajustes
    raiz_docs = raiz_documentos(ajustes)
    coordinador = CoordinadorIndice(servicios.embebido, lambda: servicios.trabajador, ajustes.rag_raiz_datos,
                                    raiz_docs)
    return ServicioDocumentacion(raiz_docs, coordinador)
