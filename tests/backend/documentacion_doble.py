"""Dobles de la documentación viva para las pruebas del backend: sin MedGemma
ni Qdrant. Trabajan sobre una COPIA temporal de
tests/docs_md/fixtures/tablero_tiempos_urgencias (nunca sobre docs_tableros/).

Actualizador doble (`proponer_cambio`, mismo contrato que
src/docs_md/actualizador.py), según la nota:
- «falla»               → estado «error» (JSON incompleto del modelo)
- «explota»             → excepción
- «ambigua» sin página  → «requiere_aclaracion» con candidatas
- «semaforo»            → modifica «Semáforo triage II» de CONSULTAS DIA (con un aviso)
- cualquier otra        → agrega «Nota del equipo» en Observaciones
Antes de responder hace UNA llamada al `llm` recibido (como MedGemma) entre
dos compuertas, para que las pruebas vean las etapas del progreso.
"""
from __future__ import annotations

import shutil
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace

from backend.app.services.motor import InstanciaMotor, PiscinaMotores
from src.docs_md import repositorio
from src.docs_md.actualizador import MAX_TOKENS_OPERACIONES, Propuesta
from src.docs_md.formato import Operacion, aplicar_operaciones, diferencias, normalizar_nombre, parsear, serializar

GRUPO = "tablero_tiempos_urgencias"
FIXTURE = Path(__file__).resolve().parents[1] / "docs_md" / "fixtures" / GRUPO


def raiz_temporal() -> Path:
    """Raíz de datos temporal con docs_tableros/<GRUPO> copiado del fixture."""
    raiz = Path(tempfile.mkdtemp(prefix="docs_web_"))
    shutil.copytree(FIXTURE, raiz / "docs_tableros" / GRUPO)
    return raiz


class ProveedorDoble:
    enforces_timeout = False

    def __init__(self):
        self.llamadas = []

    def chat(self, messages, temperature=0.0, max_tokens=100, format=None, timeout=None, think=False):
        self.llamadas.append({"max_tokens": max_tokens})
        return {"status": "success", "answer": "{}"}


class ActualizadorDoble:
    def __init__(self):
        self.antes = threading.Event()
        self.despues = threading.Event()
        self.antes.set()
        self.despues.set()
        self.llamadas = []

    def proponer_cambio(self, nota, source_group, pagina=None, llm=None, cambios_pbip=None, raiz=None):
        self.llamadas.append({"nota": nota, "grupo": source_group, "pagina": pagina, "cambios_pbip": cambios_pbip})
        assert self.antes.wait(10), "compuerta «antes» cerrada"
        if llm is not None:
            llm.chat(messages=[{"role": "user", "content": nota}], max_tokens=MAX_TOKENS_OPERACIONES)
        assert self.despues.wait(10), "compuerta «despues» cerrada"
        return self._propuesta(nota, source_group, pagina, raiz)

    def _propuesta(self, nota, grupo, pagina, raiz):
        texto = normalizar_nombre(nota)
        if "explota" in texto:
            raise RuntimeError("detalle interno que no debe verse")
        if "falla" in texto:
            return Propuesta(nota=nota, source_group=grupo, pagina=pagina or "", estado="error",
                             errores=["MedGemma devolvió una respuesta incompleta."],
                             llm_raw='{"operaciones": [', tiempos_llm=[2.0])
        if not pagina and "ambigua" in texto:
            return Propuesta(nota=nota, source_group=grupo, estado="requiere_aclaracion",
                             dudas=["¿A qué página del tablero se refiere el cambio?"],
                             candidatas=["CONSULTAS DIA", "NO EXISTE", "RESUMEN"])
        metodo = "indicada" if pagina else "reglas"
        pagina = pagina or "CONSULTAS DIA"
        antes = repositorio.leer_texto(grupo, pagina, raiz).replace("\r\n", "\n")
        doc = parsear(antes)
        if "semaforo" in texto:
            op = Operacion("modificar", "Reglas de negocio", "Semáforo triage II",
                           "Verde de 0 a 20 minutos, amarillo de 21 a 30 y rojo de 31 o más.")
            resumen, avisos = "Se amplió el verde del semáforo de triage II a 20 minutos.", [
                "«Huecos en el semáforo» también menciona el 16; revise si cambia."]
        else:
            op = Operacion("agregar", "Observaciones", "Nota del equipo", nota)
            resumen, avisos = "Se agregó una observación del equipo.", []
        despues = serializar(aplicar_operaciones(doc, [op], resumen))
        return Propuesta(nota=nota, source_group=grupo, pagina=doc.pagina, operaciones=[op], resumen=resumen,
                         estado="lista", antes=antes, despues=despues,
                         diff=diferencias(antes, despues, repositorio.archivo_para(doc)), llm_raw='{"ok": true}',
                         avisos=avisos, metodo_pagina=metodo, candidatas=[doc.pagina], tiempos_llm=[1.5])


class IndexacionDoble:
    """`reindexar_grupo` doble: registra con qué se llamó y cuántas instancias
    del motor quedaban libres (deben ser 0: la piscina se retiene)."""

    def __init__(self, piscina: PiscinaMotores | None = None):
        self.piscina = piscina
        self.compuerta = threading.Event()
        self.compuerta.set()
        self.errores: list[str] = []
        self.llamadas = []

    def reindexar_grupo(self, source_group, qdrant_client=None, **opciones):
        libres = self.piscina.libres if self.piscina is not None else None
        self.llamadas.append({"grupo": source_group, "cliente": qdrant_client, "libres": libres, **opciones})
        assert self.compuerta.wait(10), "compuerta de la reindexación cerrada"
        return {"source_group": source_group, "documentos": 32, "chunks": 120, "segundos": 2.5,
                "errores": list(self.errores), "avisos": []}


class HuellaDoble:
    def __init__(self):
        self.invalidaciones = 0

    def invalidar(self):
        self.invalidaciones += 1


def trabajador_doble(instancias: int = 2):
    """Trabajador con piscina de motores dobles que comparten un retriever con cliente Qdrant falso."""
    retriever = SimpleNamespace(client=object(), model=None, refresh_metadata=lambda: None)
    piscina = PiscinaMotores([
        InstanciaMotor(engine=object(), conversation_manager=None, formatter=None, nombre=f"motor-{n}",
                       retriever=retriever)
        for n in range(1, instancias + 1)
    ])
    return SimpleNamespace(piscina=piscina, huella=HuellaDoble(), retriever=retriever)
