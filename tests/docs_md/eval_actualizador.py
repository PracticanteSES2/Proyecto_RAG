"""
Evaluación del actualizador con MedGemma REAL (no es una prueba unitaria: usa red).

    python -X utf8 -m tests.docs_md.eval_actualizador                 # todo el banco
    python -X utf8 -m tests.docs_md.eval_actualizador --grupo ajuste   # solo las notas de ajuste
    python -X utf8 -m tests.docs_md.eval_actualizador --grupo reservada
    python -X utf8 -m tests.docs_md.eval_actualizador --ids T01,T05

Corre cada nota del banco contra el mini tablero de tests/docs_md/actualizador_fixtures
(no escribe en él: proponer_cambio no guarda nada), mide aciertos por criterio y
latencia, y escribe un informe en tests/docs_md/out/eval_actualizador_<fecha>.md con
la nota, el JSON crudo de MedGemma y el diff de cada caso.

Grupos (se reportan aparte):
  «ajuste»    notas usadas para afinar el prompt y la validación;
  «reservada» notas apartadas durante el ajuste; se corrieron una vez como prueba y uno de
              sus fallos (R03: «modificar» con texto vacío) motivó un último arreglo;
  «final»     notas escritas después de ese arreglo; dos fallos suyos (F03: verbo «eliminó»
              tomado como objeto quitado; R01: unidad perdida) motivaron arreglos genéricos;
  «final2»    notas escritas después del último arreglo; nunca se afinó con ellas.

Criterios (cada uno solo cuenta en los casos donde aplica):
  pagina          la página elegida es la esperada
  seccion_entrada cada operación esperada (obligatoria) aparece con su sección y entrada
  accion          las operaciones encontradas tienen la acción esperada
  contenido       el texto nuevo tiene las palabras clave y ninguna prohibida
  no_toca_mas     no hay operaciones fuera de las esperadas (obligatorias u opcionales)
  formato         el resultado no es «error» y, si está lista, el .md nuevo es válido
  aclaracion      pide aclaración exactamente cuando corresponde
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

from src.docs_md import formato as F
from src.docs_md.actualizador import proponer_cambio

RAIZ = Path(__file__).parent / "actualizador_fixtures"
GRUPO = "tablero_tiempos_urgencias"
SALIDA = Path(__file__).parent / "out"

CRITERIOS = ["pagina", "seccion_entrada", "accion", "contenido", "no_toca_mas", "formato", "aclaracion"]


def op(accion, seccion, entrada=None, palabras=(), prohibidas=(), opcional=False, acciones=None, nombre_contiene=(),
       alternativas=()):
    """Operación esperada. `alternativas`: otras (sección, entrada) que también
    se aceptan cuando la nota admite dos lecturas razonables."""
    return {"accion": accion, "seccion": seccion, "entrada": entrada, "palabras": list(palabras),
            "prohibidas": list(prohibidas), "opcional": opcional,
            "acciones": list(acciones or [accion]), "nombre_contiene": list(nombre_contiene),
            "alternativas": list(alternativas)}


# ---------------------------------------------------------------------------
# Banco de notas (como las escribe un desarrollador de BI con prisa)
# ---------------------------------------------------------------------------

BANCO = [
    # --- notas de ajuste ---------------------------------------------------
    {"id": "T01", "grupo": "ajuste", "nota": "le cambie el verde del semaforo de egresos a 45",
     "pagina": "EGRESOS DIA",
     "ops": [op("modificar", "Reglas de negocio", "Semáforo de egresos", ["45"], ["0 a 60"])]},
    {"id": "T02", "grupo": "ajuste", "nota": "quite el filtro de obstetricas en la torta",
     "pagina": "MAPA DE CALOR TRIAGE",
     "ops": [op("modificar", "Visuales", "Gráfico circular por clasificación triage", ["muerto"],
                ["obstetricas y muerto"])]},
    {"id": "T03", "grupo": "ajuste", "nota": "ya no se usa la tabla de remisiones en hospi dia",
     "pagina": "HOSPITALIZACION DIA",
     # «la tabla de remisiones» puede ser la tabla de datos (lectura principal) o el visual de la tabla.
     "ops": [op("eliminar", "Fuentes de datos", "Remisiones",
                alternativas=[("Visuales", "Tabla pacientes en remisión")]),
             op("modificar", "Reglas de negocio", "Paciente en remisión", opcional=True, acciones=["modificar", "eliminar"]),
             op("modificar", "Visuales", "Tabla pacientes en remisión", opcional=True, acciones=["modificar", "eliminar"])]},
    {"id": "T04", "grupo": "ajuste", "nota": "agregue en egresos dia una tarjeta con el conteo de pacientes en espera",
     "pagina": "EGRESOS DIA",
     "ops": [op("agregar", "Visuales", None, ["pacientes", "espera"], nombre_contiene=["tarjeta"])]},
    {"id": "T05", "grupo": "ajuste", "nota": "arregle lo de egresos", "pagina": None, "aclaracion": True},
    {"id": "T06", "grupo": "ajuste",
     "nota": "en consultas dia el semaforo de triage 3 ahora es verde hasta 45, amarillo 46 a 90 y rojo de 91",
     "pagina": "CONSULTAS DIA",
     "ops": [op("modificar", "Reglas de negocio", "Semáforo triage III", ["45", "46", "90", "91", "minutos"])]},
    {"id": "T07", "grupo": "ajuste",
     "nota": "hospitalizacion dia: cambie el semaforo, ahora verde 0-3 h, amarillo 4-6 h, rojo 7 o mas",
     "pagina": "HOSPITALIZACION DIA",
     "ops": [op("modificar", "Reglas de negocio", "Semáforo de hospitalización", ["3", "4", "6", "7", "horas"]),
             op("modificar", "Observaciones", "Hueco en el semáforo de hospitalizados", opcional=True,
                acciones=["modificar", "eliminar"])]},
    {"id": "T08", "grupo": "ajuste", "nota": "en egresos dia subi el rojo del semaforo de egresos de 120 a 150",
     "pagina": "EGRESOS DIA", "aclaracion": True},
    {"id": "T09", "grupo": "ajuste", "nota": "en tiempo egreso le quite el semaforo a la tarjeta",
     "pagina": "TIEMPO EGRESO", "aclaracion": True},
    {"id": "T10", "grupo": "ajuste",
     "nota": "el tiempo promedio para triage del historico ahora excluye los pacientes sin turno",
     "pagina": "TIEMPO TRIAGE",
     "ops": [op("modificar", "Indicadores", "Tiempo promedio para triage", ["turno", "minutos"]),
             op("agregar", "Reglas de negocio", None, ["turno"], opcional=True)]},
    {"id": "T11", "grupo": "ajuste",
     "nota": "en mapa de calor triage agregue un segmentador de tipo de triage igual al de tiempo triage",
     "pagina": "MAPA DE CALOR TRIAGE",
     "ops": [op("agregar", "Visuales", None, ["triage"], nombre_contiene=["segmentador"])]},
    {"id": "T12", "grupo": "ajuste", "nota": "Tabla egresos: el filtro ahora es menor a 721 min, ya no 361",
     "pagina": "EGRESOS DIA",
     "ops": [op("modificar", "Visuales", "Tabla egresos", ["721"], ["menor que 361"]),
             op("modificar", "Reglas de negocio", "Límite de la tabla de egresos", opcional=True),
             op("modificar", "Observaciones", "Límites distintos", opcional=True, acciones=["modificar", "eliminar"])]},
    {"id": "T13", "grupo": "ajuste",
     "nota": "borre la observacion de los huecos del semaforo en espera de egreso, ya lo corregimos",
     "pagina": "EGRESOS DIA",
     "ops": [op("eliminar", "Observaciones", "Huecos en el semáforo de espera"),
             op("modificar", "Reglas de negocio", "Semáforo en espera de egreso", opcional=True)]},
    {"id": "T14", "grupo": "ajuste",
     "nota": "general: agregue la definicion de tiempo de estancia = horas entre admision y orden de salida",
     "pagina": "TABLERO TIEMPOS URGENCIAS",
     "ops": [op("agregar", "Definiciones", None, ["horas", "admision", "orden de salida"], nombre_contiene=["estancia"])]},
    {"id": "T15", "grupo": "ajuste",
     "nota": "cambie el boton de regresar de hospitalizacion para que lleve a RESUMEN en vez de RESUMEN_D",
     "pagina": "HOSPITALIZACION DIA",
     "ops": [op("modificar", "Visuales", "Botón regresar", ["resumen"], ["regresa a resumen_d"]),
             op("modificar", "Propósito", None, opcional=True)]},
    {"id": "T16", "grupo": "ajuste", "nota": "le cambie el verde a 45", "pagina": None, "aclaracion": True},
    {"id": "T17", "grupo": "ajuste", "nota": "IIP e IIS ya entran en las tablas de triage II de consultas dia",
     "pagina": "CONSULTAS DIA",
     "ops": [op("modificar", "Reglas de negocio", "Marca de triage II", ["IIP", "IIS"], ["no entran"]),
             op("eliminar", "Observaciones", "IIP e IIS excluidos", opcional=True, acciones=["eliminar", "modificar"])]},
    {"id": "T18", "grupo": "ajuste",
     "nota": "en tiempo triage cambie el grafico de columnas por uno de lineas, sigue mostrando cantidad y promedio",
     "pagina": "TIEMPO TRIAGE",
     "ops": [op("modificar", "Visuales", "Gráfico de triages por mes", ["linea", "cantidad", "promedio"])]},
    {"id": "T19", "grupo": "ajuste", "nota": "lo que pidio calidad",
     "cambios_pbip": ["Página EGRESOS DIA: el visual Tabla «EGRESOS» cambió el filtro "
                      "TIEMPO_EGRESO_OK < 361 por TIEMPO_EGRESO_OK < 721."],
     "pagina": "EGRESOS DIA",
     "ops": [op("modificar", "Visuales", "Tabla egresos", ["721"], ["menor que 361"]),
             op("modificar", "Reglas de negocio", "Límite de la tabla de egresos", opcional=True),
             op("modificar", "Observaciones", "Límites distintos", opcional=True, acciones=["modificar", "eliminar"])]},

    # --- notas reservadas (no se usaron para afinar) ----------------------
    {"id": "R01", "grupo": "reservada",
     "nota": "egresos dia: semaforo en espera ahora verde <=60, amarillo 61-90, rojo >90, ya no hay huecos",
     "pagina": "EGRESOS DIA",
     "ops": [op("modificar", "Reglas de negocio", "Semáforo en espera de egreso", ["60", "61", "90"]),
             op("eliminar", "Observaciones", "Huecos en el semáforo de espera", opcional=True,
                acciones=["eliminar", "modificar"])]},
    {"id": "R02", "grupo": "reservada",
     "nota": "le meti un tooltip a la tabla de pacientes hospitalizados con el nombre del medico",
     "pagina": "HOSPITALIZACION DIA",
     "ops": [op("modificar", "Visuales", "Tabla pacientes hospitalizados", ["medico"])]},
    {"id": "R03", "grupo": "reservada", "nota": "ya no se muestra la leyenda en egresos dia",
     "pagina": "EGRESOS DIA",
     "ops": [op("eliminar", "Visuales", "Leyenda de oportunidad")]},
    {"id": "R04", "grupo": "reservada", "nota": "cambios en el mapa", "pagina": None, "aclaracion": True},
    {"id": "R05", "grupo": "reservada", "nota": "tiempo egreso: los egresos validos ahora van hasta 1440 min",
     "pagina": "TIEMPO EGRESO",
     "ops": [op("modificar", "Reglas de negocio", "Egreso válido", ["1440"], ["720"]),
             op("modificar", "Indicadores", "Tiempo promedio para el egreso", opcional=True),
             op("modificar", "Indicadores", "Egresos válidos", opcional=True)]},

    # --- notas finales (escritas después del último ajuste; nunca se afinó con ellas) ---
    {"id": "F01", "grupo": "final",
     "nota": "hospi dia: la tabla en espera ahora tambien muestra la especialidad que pidio la cama",
     "pagina": "HOSPITALIZACION DIA",
     "ops": [op("modificar", "Visuales", "Tabla en espera hospitalización", ["especialidad"])]},
    {"id": "F02", "grupo": "final",
     "nota": "en tiempo triage cambie el segmentador de tipo de triage, ya deja escoger las obstetricas",
     "pagina": "TIEMPO TRIAGE",
     "ops": [op("modificar", "Visuales", "Segmentador tipo de triage", ["obstetric"], ["obstetricas y muerto"])]},
    {"id": "F03", "grupo": "final",
     "nota": "se elimino la observacion de estados de la solicitud en hospitalizacion, ya confirmamos que "
             "1 2 y 3 son activas",
     "pagina": "HOSPITALIZACION DIA",
     "ops": [op("eliminar", "Observaciones", "Estados de la solicitud"),
             op("modificar", "Reglas de negocio", "Solicitudes en espera", opcional=True)]},
    {"id": "F04", "grupo": "final",
     "nota": "consultas dia: agregue una tarjeta con el promedio de espera de triage II",
     "pagina": "CONSULTAS DIA",
     "ops": [op("agregar", "Visuales", None, ["promedio", "II"], nombre_contiene=["tarjeta"])]},
    {"id": "F05", "grupo": "final", "nota": "le subi el amarillo", "pagina": None, "aclaracion": True},

    # --- segunda tanda final (escrita después de los arreglos motivados por F03 y R01) ---
    {"id": "G01", "grupo": "final2",
     "nota": "tiempo egreso: la tarjeta ahora muestra la mediana en vez del promedio",
     "pagina": "TIEMPO EGRESO",
     "ops": [op("modificar", "Visuales", "Tarjeta tiempo promedio para el egreso", ["mediana"]),
             op("modificar", "Indicadores", "Tiempo promedio para el egreso", opcional=True)]},
    {"id": "G02", "grupo": "final2",
     "nota": "hospitalizacion dia - quitamos la tabla de pacientes en remision, ya no la usan",
     "pagina": "HOSPITALIZACION DIA",
     "ops": [op("eliminar", "Visuales", "Tabla pacientes en remisión"),
             op("modificar", "Reglas de negocio", "Paciente en remisión", opcional=True, acciones=["modificar", "eliminar"]),
             op("eliminar", "Fuentes de datos", "Remisiones", opcional=True, acciones=["modificar", "eliminar"]),
             op("modificar", "Propósito", None, opcional=True)]},
    {"id": "G03", "grupo": "final2",
     "nota": "mapa de calor triage: el tramo horario ahora se agrupa cada 2 horas",
     "pagina": "MAPA DE CALOR TRIAGE",
     "ops": [op("modificar", "Reglas de negocio", "Tramo horario", ["2 horas"]),
             op("modificar", "Visuales", "Mapa de calor de tiempos en triage", opcional=True)]},
    {"id": "G04", "grupo": "final2",
     "nota": "egresos dia la tabla de egresos ahora tambien muestra el medico que dio la salida",
     "pagina": "EGRESOS DIA",
     "ops": [op("modificar", "Visuales", "Tabla egresos", ["medico"])]},
    {"id": "G05", "grupo": "final2",
     "nota": "en consultas dia ya no hay huecos en el semaforo de triage II, corregi el formato condicional",
     "pagina": "CONSULTAS DIA",
     "ops": [op("eliminar", "Observaciones", "Huecos en el semáforo", acciones=["eliminar", "modificar"]),
             op("modificar", "Reglas de negocio", "Semáforo triage II", opcional=True)]},
]

GRUPOS = ("ajuste", "reservada", "final", "final2")


# ---------------------------------------------------------------------------
# Calificación
# ---------------------------------------------------------------------------

def _n(texto):
    return F.normalizar_nombre(texto)


def _contiene(texto, palabra):
    return _n(palabra) in _n(texto)


def _coincide(esperada, real, doc_antes):
    for seccion, entrada in esperada.get("alternativas", []):
        if _n(seccion) == _n(real.seccion) and _n(entrada) == _n(real.entrada):
            return True
    if _n(esperada["seccion"]) != _n(real.seccion):
        return False
    if esperada["entrada"]:
        return _n(esperada["entrada"]) == _n(real.entrada)
    if esperada["seccion"] == F.SECCION_TEXTO:
        return True
    # agregar: entrada nueva (no existía) con el nombre esperado
    if doc_antes is not None and doc_antes.buscar(real.seccion, real.entrada) is not None:
        return False
    return all(_contiene(real.entrada, p) for p in esperada["nombre_contiene"]) or not esperada["nombre_contiene"]


def calificar(caso, propuesta):
    esperadas = caso.get("ops", [])
    pide = bool(caso.get("aclaracion"))
    doc_antes = F.parsear(propuesta.antes) if propuesta.antes else None
    r = {}
    r["pagina"] = None if caso["pagina"] is None else (propuesta.pagina == caso["pagina"])
    r["aclaracion"] = (propuesta.estado == "requiere_aclaracion") == pide
    r["formato"] = propuesta.estado != "error" and (
        propuesta.estado != "lista" or F.validar(propuesta.despues) == [])
    aplicadas = propuesta.operaciones if propuesta.estado == "lista" else []
    if pide:
        r["no_toca_mas"] = not aplicadas
        for c in ("seccion_entrada", "accion", "contenido"):
            r[c] = None
        return r

    obligatorias = [e for e in esperadas if not e["opcional"]]
    encontradas = []
    for e in obligatorias:
        m = next((o for o in propuesta.operaciones if _coincide(e, o, doc_antes)), None)
        encontradas.append((e, m))
    r["seccion_entrada"] = all(m is not None for _, m in encontradas) and propuesta.estado == "lista"
    r["accion"] = all(m is not None and m.accion in e["acciones"] for e, m in encontradas) and propuesta.estado == "lista"
    contenido = propuesta.estado == "lista"
    for e, m in encontradas:
        if m is None:
            contenido = False
            continue
        if m.accion == "eliminar":
            continue
        if not all(_contiene(m.texto, p) for p in e["palabras"]):
            contenido = False
        if any(_contiene(m.texto, p) for p in e["prohibidas"]):
            contenido = False
    r["contenido"] = contenido
    extra = [o for o in propuesta.operaciones if not any(_coincide(e, o, doc_antes) for e in esperadas)]
    r["no_toca_mas"] = not extra and propuesta.estado == "lista"
    return r


# ---------------------------------------------------------------------------
# Ejecución e informe
# ---------------------------------------------------------------------------

def correr(casos):
    resultados = []
    for caso in casos:
        inicio = time.perf_counter()
        try:
            p = proponer_cambio(caso["nota"], GRUPO, llm=None, cambios_pbip=caso.get("cambios_pbip"), raiz=RAIZ)
        except Exception as exc:  # el evaluador no se detiene por un caso
            from src.docs_md.actualizador import Propuesta
            p = Propuesta(nota=caso["nota"], source_group=GRUPO, errores=[f"{type(exc).__name__}: {exc}"])
        total = round(time.perf_counter() - inicio, 2)
        r = calificar(caso, p)
        resultados.append({"caso": caso, "propuesta": p, "criterios": r, "segundos": total})
        marca = " ".join(f"{k[:6]}={'-' if v is None else ('ok' if v else 'NO')}" for k, v in r.items())
        print(f"{caso['id']} [{p.estado:<19}] {p.pagina or '-':<26} {total:5.1f}s  {marca}", flush=True)
    return resultados


def tabla(resultados):
    filas = []
    total_ok = total_ap = 0
    for c in CRITERIOS:
        valores = [r["criterios"][c] for r in resultados if r["criterios"].get(c) is not None]
        ok = sum(1 for v in valores if v)
        total_ok += ok
        total_ap += len(valores)
        filas.append((c, ok, len(valores)))
    return filas, total_ok, total_ap


def _pct(a, b):
    return f"{100 * a / b:.0f} %" if b else "—"


def informe(resultados, ruta):
    llamadas = [t for r in resultados for t in r["propuesta"].tiempos_llm]
    casos_s = [r["segundos"] for r in resultados]
    lineas = [f"# Evaluación del actualizador con MedGemma — {datetime.now():%Y-%m-%d %H:%M}", ""]
    for grupo in GRUPOS:
        sub = [r for r in resultados if r["caso"]["grupo"] == grupo]
        if not sub:
            continue
        filas, ok, ap = tabla(sub)
        lineas += [f"## Notas de {grupo} ({len(sub)})", "", "| Criterio | Aciertos | % |", "|---|---|---|"]
        lineas += [f"| {c} | {a}/{b} | {_pct(a, b)} |" for c, a, b in filas]
        lineas += [f"| **total** | **{ok}/{ap}** | **{_pct(ok, ap)}** |", ""]
    if llamadas:
        lineas += ["## Latencia", "",
                   f"- Llamadas a MedGemma: {len(llamadas)}; media {statistics.mean(llamadas):.1f} s; "
                   f"mediana {statistics.median(llamadas):.1f} s; máxima {max(llamadas):.1f} s.",
                   f"- Por nota (todas las llamadas): media {statistics.mean(casos_s):.1f} s; máxima {max(casos_s):.1f} s.",
                   ""]
    lineas += ["## Casos", ""]
    for r in resultados:
        c, p = r["caso"], r["propuesta"]
        crit = ", ".join(f"{k}: {'—' if v is None else ('✔' if v else '✘')}" for k, v in r["criterios"].items())
        esperado = ("pedir aclaración" if c.get("aclaracion") else
                    "; ".join(f"{e['accion']} {e['seccion']} «{e['entrada'] or '(nueva)'}»"
                              f"{' (opcional)' if e['opcional'] else ''}" for e in c.get("ops", [])))
        lineas += [f"### {c['id']} ({c['grupo']}) — {r['segundos']:.1f} s", "",
                   f"- Nota: «{c['nota']}»"]
        if c.get("cambios_pbip"):
            lineas.append(f"- Cambios PBIP: {c['cambios_pbip']}")
        lineas += [f"- Esperado: página {c['pagina'] or '(cualquiera / aclarar)'}; {esperado}",
                   f"- Resultado: estado **{p.estado}**, página {p.pagina or '—'} ({p.metodo_pagina or '—'}), "
                   f"candidatas {p.candidatas}",
                   f"- Criterios: {crit}"]
        if p.operaciones:
            lineas.append("- Operaciones: " + json.dumps([o.a_dict() for o in p.operaciones], ensure_ascii=False))
        for nombre, lista in (("Dudas", p.dudas), ("Avisos", p.avisos), ("Errores", p.errores)):
            if lista:
                lineas.append(f"- {nombre}: " + " | ".join(lista))
        lineas += ["", "JSON crudo:", "", "```", p.llm_raw.strip(), "```", ""]
        if p.diff:
            lineas += ["Diff:", "", "```diff", p.diff.strip(), "```", ""]
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--grupo", choices=list(GRUPOS))
    parser.add_argument("--ids", help="ids separados por coma (T01,R02)")
    parser.add_argument("--salida", help="ruta del informe .md")
    args = parser.parse_args(argv)
    casos = BANCO
    if args.grupo:
        casos = [c for c in casos if c["grupo"] == args.grupo]
    if args.ids:
        ids = {i.strip().upper() for i in args.ids.split(",")}
        casos = [c for c in casos if c["id"] in ids]
    resultados = correr(casos)
    for grupo in GRUPOS:
        sub = [r for r in resultados if r["caso"]["grupo"] == grupo]
        if sub:
            filas, ok, ap = tabla(sub)
            print(f"\n{grupo}: " + ", ".join(f"{c} {a}/{b}" for c, a, b in filas) + f" | total {ok}/{ap} ({_pct(ok, ap)})")
    ruta = Path(args.salida) if args.salida else SALIDA / f"eval_actualizador_{datetime.now():%Y-%m-%d_%H%M}.md"
    informe(resultados, ruta)
    print(f"Informe: {ruta}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
