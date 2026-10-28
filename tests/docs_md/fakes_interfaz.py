"""
Servicios SIMULADOS para probar la página de Documentación sin MedGemma ni
Qdrant. No son comportamiento real: solo se usan con

    DOCS_MD_SERVICIOS=tests.docs_md.fakes_interfaz

Mismo contrato que actualizador.proponer_cambio / aplicar_propuesta e
indexacion.reindexar_grupo. Comportamiento según la nota:
- contiene «falla»               -> estado «error» (JSON incompleto del modelo)
- contiene «ambigua» sin página  -> estado «requiere_aclaracion» con candidatas
- menciona «semáforo»            -> modifica «Semáforo triage II» (si existe), con un aviso
                                    simulado, la página «por reglas» y una llamada de 1.5 s
- cualquier otra                 -> agrega «Nota del equipo» en Observaciones
Variables: DOCS_MD_FAKE_REINDEX_FALLA=1 hace fallar la reindexación;
DOCS_MD_FAKE_DEMORA=<segundos> simula la espera de MedGemma.
"""
import os
import time

from src.docs_md import repositorio
from src.docs_md.actualizador import Propuesta
from src.docs_md.formato import (
    Operacion,
    aplicar_operaciones,
    diferencias,
    normalizar_nombre,
    parsear,
    serializar,
)

LLAMADAS = {"proponer": [], "aplicar": [], "reindexar": []}


def reiniciar():
    for lista in LLAMADAS.values():
        lista.clear()


def proponer_cambio(nota, source_group, pagina=None, llm=None, cambios_pbip=None):
    LLAMADAS["proponer"].append({"nota": nota, "source_group": source_group, "pagina": pagina,
                                 "cambios_pbip": cambios_pbip})
    demora = float(os.getenv("DOCS_MD_FAKE_DEMORA", "0") or 0)
    if demora:
        time.sleep(demora)
    texto = normalizar_nombre(nota)
    paginas = repositorio.listar_paginas(source_group)
    if "falla" in texto:
        return Propuesta(nota=nota, source_group=source_group, pagina=pagina or "", estado="error",
                         errores=["MedGemma devolvió una respuesta incompleta (simulado)."],
                         llm_raw='{"pagina": "CONSULTAS DIA", "operaciones": [')
    if not pagina and "ambigua" in texto:
        return Propuesta(nota=nota, source_group=source_group, estado="requiere_aclaracion",
                         dudas=["La nota no dice en qué página está el cambio."],
                         candidatas=[p["pagina"] for p in paginas])

    metodo = "indicada" if pagina else "reglas"
    pagina = pagina or next(p["pagina"] for p in paginas if p["archivo"] != repositorio.ARCHIVO_GENERAL)
    antes = repositorio.leer_texto(source_group, pagina)
    doc = parsear(antes)
    if "semaforo" in texto and doc.buscar("Reglas de negocio", "Semáforo triage II"):
        op = Operacion("modificar", "Reglas de negocio", "Semáforo triage II",
                       "Verde de 0 a 20 minutos, amarillo de 21 a 30 y rojo de 31 o más.")
        resumen = "Se amplió el verde del semáforo de triage II a 20 minutos."
        avisos = ["(simulado) «Leyenda de oportunidad» también tiene la cifra 15 del texto anterior; "
                  "revise si también cambia."]
    else:
        op = Operacion("agregar", "Observaciones", "Nota del equipo", nota)
        resumen = "Se agregó una observación del equipo."
        avisos = []
    nuevo = aplicar_operaciones(doc, [op], resumen)
    despues = serializar(nuevo)
    return Propuesta(nota=nota, source_group=source_group, pagina=doc.pagina, operaciones=[op],
                     resumen=resumen, estado="lista", antes=antes, despues=despues,
                     diff=diferencias(antes, despues, repositorio.archivo_para(doc)),
                     llm_raw='{"simulado": true}', avisos=avisos, metodo_pagina=metodo, tiempos_llm=[1.5])


def aplicar_propuesta(propuesta, autor, raiz=None):
    LLAMADAS["aplicar"].append({"pagina": propuesta.pagina, "autor": autor,
                                "operaciones": [op.a_dict() for op in propuesta.operaciones]})
    if propuesta.estado != "lista":
        raise ValueError("Solo se aplican propuestas en estado «lista».")
    actual = repositorio.leer_texto(propuesta.source_group, propuesta.pagina, raiz)
    if actual.replace("\r\n", "\n") != propuesta.antes.replace("\r\n", "\n"):
        raise ValueError("La página cambió desde que se hizo la propuesta; vuelve a generarla.")
    nuevo = aplicar_operaciones(parsear(actual), propuesta.operaciones, propuesta.resumen, autor=autor)
    return repositorio.guardar_pagina(propuesta.source_group, nuevo, raiz)


def reindexar_grupo(source_group, qdrant_client=None):
    LLAMADAS["reindexar"].append({"source_group": source_group, "qdrant_client": qdrant_client})
    if os.getenv("DOCS_MD_FAKE_REINDEX_FALLA") == "1":
        raise RuntimeError("Qdrant está ocupado (simulado).")
    return {"source_group": source_group, "documentos": len(repositorio.listar_paginas(source_group)),
            "chunks": 12, "segundos": 0.3, "errores": []}
