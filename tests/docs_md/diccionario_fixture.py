"""
Proyectos sintéticos para las pruebas del diccionario (sin Power BI ni datos reales).

`crear_proyecto(raiz, ...)` arma, bajo `raiz`:

    data/model_metadata/<modelo>/{tables,columns,measures,relationships}.csv   (formato INFO.VIEW, «;»)
    docs_tableros/<grupo>/manifest.json
    docs_tableros/<grupo>/md/                                                   (vacío; lo llena cada prueba)

y devuelve (grupo, hechos), donde `hechos` imita lo que entrega `pbip.extraer_hechos`.
`crear_proyecto_grande` hace lo mismo con un modelo enorme (~1800 medidas, ~160 tablas).
"""

import csv
import json
from pathlib import Path

GRUPO = "tablero_mini"
MODELO = "tablero_mini"
TABLERO = "TABLERO MINI"

_TABLAS = ["ID", "Name", "Model", "DataCategory", "Description", "IsHidden", "StorageMode", "TableStorage", "Expression"]
_COLUMNAS = ["ID", "Name", "Table", "DataType", "DataCategory", "Description", "IsHidden", "IsKey", "Type",
             "SourceColumn", "Expression"]
_MEDIDAS = ["ID", "Name", "Table", "Description", "DataType", "Expression", "FormatString", "IsHidden", "State",
            "DisplayFolder"]
_RELACIONES = ["ID", "Name", "Relationship", "Model", "IsActive", "CrossFilteringBehavior", "FromTable",
               "FromColumn", "FromCardinality", "ToTable", "ToColumn", "ToCardinality", "State"]


def _escribir(ruta: Path, columnas: list, filas: list):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=";", quoting=csv.QUOTE_ALL)
        w.writerow(columnas)
        for i, fila in enumerate(filas, start=1):
            w.writerow([fila.get(c, str(i) if c == "ID" else "") for c in columnas])


def _tabla(nombre, oculta=False, modo="Import", expresion="", desc=""):
    return {"Name": nombre, "IsHidden": str(oculta), "StorageMode": modo, "Expression": expresion, "Description": desc}


def _columna(tabla, nombre, tipo="String", calculada=False, expresion="", oculta=False, desc=""):
    return {"Name": nombre, "Table": tabla, "DataType": tipo, "Type": "Calculated" if calculada else "Data",
            "Expression": expresion, "IsHidden": str(oculta), "Description": desc}


def _medida(tabla, nombre, dax, oculta=False, formato="", desc="", tipo="Integer"):
    return {"Name": nombre, "Table": tabla, "Expression": dax, "IsHidden": str(oculta), "FormatString": formato,
            "Description": desc, "DataType": tipo, "State": "Valid"}


def _relacion(t1, c1, t2, c2, activa=True, ambos=False):
    return {"Name": f"{t1}.{c1}-{t2}.{c2}", "IsActive": str(activa),
            "CrossFilteringBehavior": "BothDirections" if ambos else "OneDirection",
            "FromTable": t1, "FromColumn": c1, "FromCardinality": "Many", "ToTable": t2, "ToColumn": c2,
            "ToCardinality": "One", "State": "Ready"}


def _manifest(raiz: Path, grupo: str, modelo: str, tablero: str):
    carpeta = raiz / "docs_tableros" / grupo
    (carpeta / "md").mkdir(parents=True, exist_ok=True)
    (carpeta / "manifest.json").write_text(json.dumps({
        "workspace": "Prueba", "report": tablero, "semantic_model": tablero, "semantic_model_key": modelo,
        "source_group": grupo, "default_dashboard": tablero, "aliases": [tablero],
        "document_type": "dashboard_documentation",
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def _hechos_tabla(columnas, calculadas=None, sql=None, dax=None, base="DWPRUEBA"):
    return {"modo": "Import", "origen": "DAX" if dax else "Sql.Database", "servidor": None,
            "base_datos": None if dax else base, "sql": sql, "m": None, "dax": dax,
            "columnas": columnas, "calculadas": calculadas or {}}


def _visual(id_, tipo, campos, titulo=None, filtros=None):
    return {"id": id_, "tipo": tipo, "titulo": titulo, "campos": campos,
            "campos_detalle": [{"rol": "Values", "expresion": c, "nombre": c.split("[")[-1].rstrip("]")} for c in campos],
            "filtros": filtros or [], "semaforo": [], "formato_condicional": [], "texto": None, "destino": None,
            "destino_id": None, "accion": None, "tablas": [], "oculto": False}


def crear_proyecto(raiz: Path) -> tuple[str, dict]:
    raiz = Path(raiz)
    carpeta = raiz / "data" / "model_metadata" / MODELO
    _escribir(carpeta / "tables.csv", _TABLAS, [
        _tabla("PACIENTES"),
        _tabla("Calendario", expresion='CALENDAR("2023-01-01",TODAY())'),
        _tabla("LocalDateTable_9ac6000d-c9f5-4042-97cd-bb95fe5d587c", oculta=True),
        _tabla("DateTableTemplate_691ae62d-5891-4a78-be32-1acf0c184bcb", oculta=True),
    ])
    _escribir(carpeta / "columns.csv", _COLUMNAS, [
        {"Name": "RowNumber-2662979B", "Table": "PACIENTES", "Type": "RowNumber", "DataType": "Integer"},
        _columna("PACIENTES", "SERVICIO"),
        _columna("PACIENTES", "ESTADO"),
        _columna("PACIENTES", "FECHA_INGRESO", "DateTime"),
        _columna("PACIENTES", "DIAS", "Integer", True, "DATEDIFF(PACIENTES[FECHA_INGRESO], TODAY(), DAY)"),
        _columna("PACIENTES", "NOTA", "String"),
        _columna("Calendario", "Date", "DateTime"),
        _columna("LocalDateTable_9ac6000d-c9f5-4042-97cd-bb95fe5d587c", "Year", "Integer", True, "YEAR([Date])", True),
    ])
    _escribir(carpeta / "measures.csv", _MEDIDAS, [
        _medida("PACIENTES", "Total pacientes", "\n// cuenta pacientes\nCOUNTROWS(PACIENTES)"),
        _medida("PACIENTES", "Pacientes activos",
                'CALCULATE([Total pacientes], PACIENTES[ESTADO] = "ACTIVO") -- activos', formato="0"),
        _medida("PACIENTES", "Porcentaje activos", "DIVIDE([Pacientes activos], [Total pacientes])", formato="0.0%",
                tipo="Number"),
        _medida("PACIENTES", "Base interna", "SUM(PACIENTES[DIAS])", oculta=True),
        _medida("PACIENTES", "Dias promedio", "AVERAGE(PACIENTES[DIAS])", desc="Promedio de días de estancia.",
                tipo="Number"),
        _medida("PACIENTES", "Sin uso", 'VAR x = "Tabla: texto" RETURN x'),
    ])
    _escribir(carpeta / "relationships.csv", _RELACIONES, [
        _relacion("PACIENTES", "FECHA_INGRESO", "Calendario", "Date"),
        _relacion("PACIENTES", "NOTA", "Calendario", "Date", activa=False),
        _relacion("Calendario", "Date", "LocalDateTable_9ac6000d-c9f5-4042-97cd-bb95fe5d587c", "Date"),
    ])
    _manifest(raiz, GRUPO, MODELO, TABLERO)

    hechos = {
        "version_hechos": 1, "tablero": TABLERO, "modelo_disponible": True, "filtros_reporte": [],
        "paginas": [
            {"id": "p1", "nombre": "RESUMEN", "visible": True, "orden": 1, "filtros": [], "obtener_detalles": [],
             "visuales": [
                 _visual("v1", "card", ["PACIENTES[Total pacientes]"], "TOTAL PACIENTES"),
                 _visual("v2", "card", ["PACIENTES[Porcentaje activos]"], "PORCENTAJE ACTIVOS"),
                 _visual("v3", "slicer", ["PACIENTES[SERVICIO]"]),
                 _visual("v4", "slicer", ["Calendario[Date] (Año)"]),
             ]},
            {"id": "p2", "nombre": "DETALLE", "visible": True, "orden": 2,
             "filtros": ["PACIENTES[DIAS] > 3"], "obtener_detalles": [],
             "visuales": [
                 _visual("v5", "tableEx", ["PACIENTES[SERVICIO]", "PACIENTES[DIAS]", "PACIENTES[Dias promedio]"], "LISTADO"),
             ]},
        ],
        "tablas": {
            "PACIENTES": _hechos_tabla(["SERVICIO", "ESTADO", "FECHA_INGRESO", "DIAS", "NOTA"],
                                       {"DIAS": "DATEDIFF(PACIENTES[FECHA_INGRESO], TODAY(), DAY)"},
                                       sql="SELECT A.SERVICIO FROM DBO.HOSPITAL A JOIN DBO.CAMAS B ON A.ID = B.ID"),
            "Calendario": _hechos_tabla(["Date"], dax='CALENDAR("2023-01-01",TODAY())'),
        },
        "medidas": {f"PACIENTES[{m}]": "x" for m in ("Total pacientes", "Pacientes activos", "Porcentaje activos",
                                                       "Base interna", "Dias promedio", "Sin uso")},
        "relaciones": ["PACIENTES[FECHA_INGRESO] -> Calendario[Date]"],
    }
    return GRUPO, hechos


GRUPO_GRANDE = "tablero_enorme"


def crear_proyecto_grande(raiz: Path, n_tablas=160, n_medidas=1800, n_calculadas=600) -> tuple[str, dict]:
    raiz = Path(raiz)
    carpeta = raiz / "data" / "model_metadata" / GRUPO_GRANDE
    tablas = [_tabla(f"T{i:03d}") for i in range(n_tablas)]
    columnas, medidas = [], []
    for i in range(n_tablas):
        columnas.append(_columna(f"T{i:03d}", "ID", "Integer"))
        columnas.append(_columna(f"T{i:03d}", "NOMBRE", "String"))
    for j in range(n_calculadas):
        columnas.append(_columna(f"T{j % n_tablas:03d}", f"CALC_{j}", "Integer", True, f"T{j % n_tablas:03d}[ID] + {j}"))
    for k in range(n_medidas):
        medidas.append(_medida(f"T{k % n_tablas:03d}", f"Medida {k}", f"COUNTROWS(T{k % n_tablas:03d}) + {k}"))
    medidas[0]["Description"] = "Medida con descripción en el modelo."
    _escribir(carpeta / "tables.csv", _TABLAS, tablas)
    _escribir(carpeta / "columns.csv", _COLUMNAS, columnas)
    _escribir(carpeta / "measures.csv", _MEDIDAS, medidas)
    _escribir(carpeta / "relationships.csv", _RELACIONES, [_relacion("T001", "ID", "T000", "ID")])
    _manifest(raiz, GRUPO_GRANDE, GRUPO_GRANDE, "TABLERO ENORME")
    usadas = [f"T{k % n_tablas:03d}[Medida {k}]" for k in range(1, 31)]
    hechos = {
        "version_hechos": 1, "tablero": "TABLERO ENORME", "modelo_disponible": True, "filtros_reporte": [],
        "paginas": [{"id": "p1", "nombre": "PAGINA UNO", "visible": True, "orden": 1, "filtros": [], "obtener_detalles": [],
                     "visuales": [_visual(f"v{i}", "card", [u], f"TARJETA {i}") for i, u in enumerate(usadas)]
                     + [_visual("vc", "slicer", ["T005[CALC_5]"])]}],
        "tablas": {f"T{i:03d}": _hechos_tabla(["ID", "NOMBRE"]) for i in range(n_tablas)},
        "medidas": {f"T{k % n_tablas:03d}[Medida {k}]": "x" for k in range(n_medidas)},
        "relaciones": ["T001[ID] -> T000[ID]"],
    }
    return GRUPO_GRANDE, hechos
