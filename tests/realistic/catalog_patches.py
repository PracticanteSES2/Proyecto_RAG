"""
Parches del arnés realista sobre modelos REALES de data/ (en la copia en caché del overlay).

El data/ local es una instantánea más antigua que la del propietario. Para reproducir sus
pruebas con usuarios del hospital (2026-10-14: ocupación de hoy, detalle de ocupación por
aseguradora, camas disponibles en hospitalización general) se agregan aquí SOLO las piezas que
el catálogo del propietario tiene y el local no:

  BRIEFING HOSPITALARIO
    - %OCUPACION y CamasFiltradas en INICIO, en un mismo visual titulado «%OCUPACIÓN» (por eso
      CamasFiltradas coincide por el alias «%OCUPACIÓN»); %OCUPACION también en GESTIÓN CAMAS.
    - Medida CAMAS (cuenta camas por HCACODIGO) en GESTIÓN CAMAS (la página local
      «GESTIÓN DE CAMAS» se renombra así) con una matriz SERVICIOS × ESTADOS_CAM (supuesto).
    - Visual «PACIENTES por ASEGURADORA» en INICIO: DISTINCTCOUNT(ADNINGRESO) por TERNOMCOM.
    - Filas fijas (_sim_tables.json) de CAMAS DISPONIBLES y PACIENTES X ASEGURADORA: camas con
      códigos y servicios realistas (HOSPITALIZACIÓN GENERAL, UCI ADULTOS...) y pacientes con
      su EPS, coherentes entre sí (cada cama ocupada tiene un paciente).
  DEMANDA INSATISFECHA
    - HOSPITALIZACIÓN = SUM(DEMANDA_INS) en CONSOLIDADO y SOLICITUD CAMAS, TOTAL_SOLICITUD_CAMAS y
      TERCEROS[TERNOMCOM]. Divergencia: la tabla local se llama SOLICITUD_CAMAS (la del
      propietario, 'SOLICITUD DE CAMAS').
  TABLERO EPS
    - %OCUPACIONALC (tabla %OCUPACIONAL) en la página TRIAGES ATENDIDOS, tarjeta «Ocupación de
      urgencias».
  TABLERO FARMACIA (solo filas fijas, sin tocar el informe ni el catálogo)
    - PRODUCTOS_VENCIDOS (5 productos) y VENCIMIENTO_PRODUCTOS (3 con mes <= 1, 3 con mes 2-4):
      los casos v_ de «lista de...»/«cuáles...» verifican el total y el listado.

Cómo se aplica (overlay.build_merged_root, nunca sobre data/):
  1. Agrega tablas/columnas/medidas/relaciones a la copia de model_metadata/<slug>/*.csv y escribe
     _sim_tables.json (filas fijas para el simulador).
  2. Copia el PBIR original del informe (manifest pbir_path o data/pbir/<Informe>.Report; sin .pbi)
     a la caché y le agrega/renombra páginas y visuales.
  3. Escribe data/raw/<grupo>/manifest.json apuntando a esa copia: PowerBICatalogManager.run()
     reconstruye los catálogos técnico/visual y las métricas maestras de ese grupo.
Si no encuentra el PBIR original solo parchea la metadata (y lo anota en patches_report.json).

SIM_PATCHES=0 (o build_engine(patches=False)) desactiva los parches.
"""
import csv
import hashlib
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORT_FILE = "patches_report.json"

# Funciones de agregación PBIR (src/semantic/visual_catalog_builder.PBIR_AGGREGATIONS).
PBIR_FUNCTIONS = {"Sum": 0, "Average": 1, "DistinctCount": 2, "Min": 3, "Max": 4, "Count": 5}
QUERY_REF_PREFIX = {"Sum": "Sum", "Average": "Avg", "DistinctCount": "CountNonNull", "Min": "Min",
                    "Max": "Max", "Count": "Count"}

# ----------------------------------------------------------------------------
# Datos fijos: camas y pacientes (BRIEFING HOSPITALARIO)
# ----------------------------------------------------------------------------

ESTADOS = {"DISPONIBLE": 1, "OCUPADA": 2, "BLOQUEADA": 3, "EN TRANSICIÓN": 5, "CAMA SOLICITADA": 100}

# (servicio, orden, códigos, {estado: [códigos]} — el resto OCUPADA)
CAMAS = [
    ("HOSPITALIZACIÓN GENERAL", "1", [str(n) for n in range(401, 425)] + ["321", "322"], {
        "DISPONIBLE": ["403", "407", "411", "415", "419", "422"],
        "BLOQUEADA": ["412", "321", "322"],          # 321 y 322: camas administrativas
        "EN TRANSICIÓN": ["416"], "CAMA SOLICITADA": ["420"]}),
    ("HOSPITALIZACIÓN INTERMEDIOS", "2", [str(n) for n in range(501, 513)], {
        "DISPONIBLE": ["504", "509"], "EN TRANSICIÓN": ["511"]}),
    ("UCI ADULTOS", "3", [f"UCI-{n:02d}" for n in range(1, 11)], {
        "DISPONIBLE": ["UCI-06"], "BLOQUEADA": ["UCI-10"]}),
    ("PEDIATRÍA", "4", [str(n) for n in range(601, 611)], {
        "DISPONIBLE": ["602", "605", "607"], "CAMA SOLICITADA": ["603"],
        "BLOQUEADA": ["609", "610"]}),               # sexto piso no habilitado (MOSTRAR_6TO = 0)
    ("GINECOBSTETRICIA", "5", [str(n) for n in range(701, 709)], {
        "DISPONIBLE": ["703", "706"], "BLOQUEADA": ["708"]}),
    ("URGENCIAS", "6", ["EXP-01", "EXP-02", "EXP-03", "EXP-04", "OH-01", "OH-02"], {
        "DISPONIBLE": ["EXP-03", "EXP-04", "OH-01", "OH-02"]}),   # expansión y observación
]
SEXTO_PISO_NO_HABILITADO = {"609", "610"}

# EPS de los pacientes hospitalizados (en orden de cantidad) y su plan.
ASEGURADORAS = [
    ("NUEVA EPS", 11, "SUBSIDIADO"), ("SANITAS EPS", 7, "CONTRIBUTIVO"), ("SURA EPS", 6, "CONTRIBUTIVO"),
    ("SALUD TOTAL EPS", 5, "CONTRIBUTIVO"), ("COOSALUD EPS", 4, "SUBSIDIADO"),
    ("FAMISANAR EPS", 3, "CONTRIBUTIVO"), ("MUTUAL SER EPS", 2, "SUBSIDIADO"),
    ("COMPENSAR EPS", 2, "CONTRIBUTIVO"), ("POLICIA NACIONAL", 1, "REGIMEN ESPECIAL"),
    ("PARTICULAR", 1, "PARTICULAR"), ("SOAT - SEGUROS DEL ESTADO", 1, "SOAT"),
]
ESPECIALIDADES = {
    "HOSPITALIZACIÓN GENERAL": ["MEDICINA INTERNA", "CIRUGÍA GENERAL", "ORTOPEDIA"],
    "HOSPITALIZACIÓN INTERMEDIOS": ["MEDICINA INTERNA", "CARDIOLOGÍA"],
    "UCI ADULTOS": ["MEDICINA CRÍTICA"],
    "PEDIATRÍA": ["PEDIATRÍA"],
    "GINECOBSTETRICIA": ["GINECOLOGÍA Y OBSTETRICIA"],
    "URGENCIAS": ["MEDICINA DE URGENCIAS"],
}


def camas():
    """Filas de CAMAS DISPONIBLES: (HCACODIGO, SERVICIOS, ESTADOS_CAM, ESTADO, HCAESTADO, MOSTRAR_6TO, Orden, RUTA_ACV)."""
    rows = []
    for servicio, orden, codigos, estados in CAMAS:
        by_code = {code: estado for estado, codes in estados.items() for code in codes}
        for code in codigos:
            estado = by_code.get(code, "OCUPADA")
            numero = ESTADOS[estado]
            rows.append({
                "HCACODIGO": code, "SERVICIOS": servicio, "ESTADOS_CAM": estado, "ESTADO": numero,
                "HCAESTADO": numero, "MOSTRAR_6TO": 0 if code in SEXTO_PISO_NO_HABILITADO else 1,
                "Orden": f"ORDEN {orden}", "RUTA_ACV": "SI" if code in ("UCI-01", "UCI-02", "UCI-03") else "NO",
            })
    return rows


def pacientes():
    """Un paciente por cama OCUPADA (ESTADO 2), con su EPS: filas de PACIENTES X ASEGURADORA."""
    ocupadas = [cama for cama in camas() if cama["ESTADO"] == 2]
    eps = [(name, plan) for name, count, plan in ASEGURADORAS for _ in range(count)]
    assert len(eps) == len(ocupadas), (len(eps), len(ocupadas))
    # Reparto determinista que mezcla EPS y servicios (no todos los de NUEVA EPS en el piso 4).
    order = sorted(range(len(eps)), key=lambda i: hashlib.sha1(f"eps{i}".encode()).hexdigest())
    rows = []
    for index, cama in enumerate(ocupadas):
        name, plan = eps[order[index]]
        especialidades = ESPECIALIDADES[cama["SERVICIOS"]]
        dias = (index * 7) % 19
        rows.append({
            "PACNUMDOC": str(10_000_000 + (index + 1) * 7919 % 89_000_000),
            "GPANOMCOM": f"PACIENTE SIMULADO {index + 1:05d}",
            "HCACODIGO": cama["HCACODIGO"], "HSUNOMBRE": cama["SERVICIOS"], "TERNOMCOM": name,
            "GDENOMBRE": plan, "ESPECIALIDAD": especialidades[index % len(especialidades)],
            "ADNINGRESO": str(1_850_000 + index * 37), "DIAS_ESTANCIA": dias,
            "FechaSalida": f"today+{1 + index % 6}",
            "FECHA_ORDEN_SALIDA": "today" if index % 9 == 0 else None,
            "FECHA_EPICRISIS": "today" if index % 9 == 0 else None,
            "EGRESO_EFECTIVO_HOY": "SI" if index % 9 == 0 else "NO",
        })
    return rows


# ----------------------------------------------------------------------------
# Datos fijos: productos vencidos y en vencimiento (TABLERO FARMACIA)
# ----------------------------------------------------------------------------

# (IPRCODIGO, producto, cantidad, fecha de vencimiento) — PRODUCTOS_VENCIDOS: tabla «PRODUCTOS
# VENCIDOS» (código, producto, cantidad, fecha) y tarjeta «MEDICAMENTOS VENCIDOS» (suma de cantidad).
PRODUCTOS_VENCIDOS = [
    ("MV-1001", "ACETAMINOFEN 500 MG TABLETA", 12, "2026-08-31"),
    ("MV-1002", "AMOXICILINA 500 MG CAPSULA", 30, "2026-09-15"),
    ("MV-1003", "DIPIRONA 2.5 G/5 ML AMPOLLA", 8, "2026-09-30"),
    ("MV-1004", "OMEPRAZOL 20 MG CAPSULA", 25, "2026-10-05"),
    ("MV-1005", "CEFTRIAXONA 1 G VIAL", 4, "2026-10-10"),
]

# (IPRCODIGO, producto, meses para vencer, fecha, lote, zona, cantidad) — VENCIMIENTO_PRODUCTOS: la
# tarjeta «MEDICAMENTOS EN VENCIMIENTO 0-30 DÍAS» y su tabla filtran mes <= 1 (3 productos); la de
# 30-120 días, mes 2-4. ilsfecven es texto en el modelo.
PRODUCTOS_EN_VENCIMIENTO = [
    ("PV-2001", "SALBUTAMOL INHALADOR 100 MCG", 0, "2026-10-25", "L-5501", "BODEGA CENTRAL", 6),
    ("PV-2002", "ENOXAPARINA 40 MG JERINGA", 1, "2026-11-08", "L-5502", "STOCK URGENCIAS", 15),
    ("PV-2003", "METOCLOPRAMIDA 10 MG AMPOLLA", 1, "2026-11-12", "L-5503", "BODEGA CENTRAL", 20),
    ("PV-2004", "LOSARTAN 50 MG TABLETA", 2, "2026-12-20", "L-5504", "BODEGA CENTRAL", 40),
    ("PV-2005", "HIDROCORTISONA 100 MG VIAL", 3, "2027-01-18", "L-5505", "STOCK URGENCIAS", 9),
    ("PV-2006", "RANITIDINA 50 MG AMPOLLA", 4, "2027-02-15", "L-5506", "BODEGA CENTRAL", 11),
]


def farmacia_sim_tables():
    vencidos = [{"IPRCODIGO": code, "iprdescor": name, "iddcantid": qty, "IDFECDOC": fecha}
                for code, name, qty, fecha in PRODUCTOS_VENCIDOS]
    proximos = [{"IPRCODIGO": code, "IPRDESCOR": name, "mes": mes, "ilsfecven": fecha, "ILSCODIGO": lote,
                 "NombreZona": zona, "IFICANTID": qty}
                for code, name, mes, fecha, lote, zona, qty in PRODUCTOS_EN_VENCIMIENTO]
    return {"tables": {"PRODUCTOS_VENCIDOS": _fixture(vencidos), "VENCIMIENTO_PRODUCTOS": _fixture(proximos)}}


def _fixture(rows):
    columns = list(rows[0])
    return {"columns": columns, "rows": [[row.get(c) for c in columns] for row in rows]}


def briefing_sim_tables():
    # ESTADOS_CAM, MOSTRAR y OCUPADAS son calculadas: el simulador las evalúa con su DAX (ESTADO,
    # HCAESTADO); ESTADOS_CAM solo queda en camas() para las pruebas.
    beds = [{k: v for k, v in row.items() if k != "ESTADOS_CAM"} for row in camas()]
    return {"tables": {"CAMAS DISPONIBLES": _fixture(beds), "PACIENTES X ASEGURADORA": _fixture(pacientes())}}


# ----------------------------------------------------------------------------
# Parches
# ----------------------------------------------------------------------------
# Visual: (tipo, título o None, [campos]); campo:
#   ["measure", tabla, medida, rol?, nombre visible?]
#   ["column", tabla, columna, rol?, nombre visible?]
#   ["agg", tabla, columna, función (Sum|Count|DistinctCount...), rol?, nombre visible?]

PATCHES = [
    {
        "semantic_model_key": "briefing_hospitalario",
        "source_group": "tablero_briefing_hospitalario",
        "measures": [
            {"table": "CAMAS DISPONIBLES", "name": "CAMAS", "data_type": "Integer", "format_string": "0",
             "expression": "COUNT('CAMAS DISPONIBLES'[HCACODIGO])",
             "description": "Cuenta las camas por su código (HCACODIGO) en la gestión de camas."},
        ],
        "rename_pages": {"GESTIÓN DE CAMAS": "GESTIÓN CAMAS"},
        "pages": [
            {"name": "INICIO", "visuals": [
                ["gauge", "%OCUPACIÓN", [["measure", "CAMAS DISPONIBLES", "%OCUPACION", "Y"],
                                         ["measure", "CAMAS DISPONIBLES", "CamasFiltradas", "MaxValue"]]],
                ["clusteredBarChart", "PACIENTES por ASEGURADORA", [
                    ["column", "PACIENTES X ASEGURADORA", "TERNOMCOM", "Category", "ASEGURADORA"],
                    ["agg", "PACIENTES X ASEGURADORA", "ADNINGRESO", "DistinctCount", "Y", "PACIENTES"]]],
            ]},
            {"name": "GESTIÓN CAMAS", "visuals": [
                ["card", "%OCUPACIÓN", [["measure", "CAMAS DISPONIBLES", "%OCUPACION"]]],
                ["card", "CAMAS", [["measure", "CAMAS DISPONIBLES", "CAMAS"]]],
                ["pivotTable", None, [["column", "CAMAS DISPONIBLES", "SERVICIOS", "Rows", "SERVICIO"],
                                      ["column", "CAMAS DISPONIBLES", "ESTADOS_CAM", "Columns", "ESTADO"],
                                      ["measure", "CAMAS DISPONIBLES", "CAMAS", "Values"]]],
            ]},
        ],
        "sim_tables": briefing_sim_tables,
    },
    {
        "semantic_model_key": "demanda_insatisfecha",
        "source_group": "tablero_demanda_insatisfecha",
        "tables": [{"name": "TERCEROS"}],
        "columns": [
            {"table": "SOLICITUD_CAMAS", "name": "DEMANDA_INS", "data_type": "Integer"},
            {"table": "TERCEROS", "name": "OID", "data_type": "Integer", "unique": True},
            {"table": "TERCEROS", "name": "TERNOMCOM", "data_type": "Text"},
        ],
        "relationships": [
            {"from_table": "SOLICITUD_CAMAS", "from_column": "OID_TERCERO", "to_table": "TERCEROS", "to_column": "OID"},
        ],
        "measures": [
            {"table": "SOLICITUD_CAMAS", "name": "HOSPITALIZACIÓN", "data_type": "Integer", "format_string": "0",
             "expression": "SUM('SOLICITUD_CAMAS'[DEMANDA_INS])",
             "description": "Demanda insatisfecha de camas de hospitalización."},
            {"table": "SOLICITUD_CAMAS", "name": "TOTAL_SOLICITUD_CAMAS", "data_type": "Integer", "format_string": "0",
             "expression": "COUNTROWS('SOLICITUD_CAMAS')", "description": "Total de solicitudes de cama."},
        ],
        "pages": [
            {"name": "CONSOLIDADO", "visuals": [
                ["card", None, [["measure", "SOLICITUD_CAMAS", "HOSPITALIZACIÓN"]]],
            ]},
            {"name": "SOLICITUD CAMAS", "visuals": [
                ["card", None, [["measure", "SOLICITUD_CAMAS", "HOSPITALIZACIÓN"]]],
                ["card", None, [["measure", "SOLICITUD_CAMAS", "TOTAL_SOLICITUD_CAMAS"]]],
                ["clusteredBarChart", None, [["column", "TERCEROS", "TERNOMCOM", "Category", "ASEGURADORA"],
                                             ["measure", "SOLICITUD_CAMAS", "TOTAL_SOLICITUD_CAMAS", "Y"]]],
            ]},
        ],
    },
    {
        "semantic_model_key": "tablero_eps",
        "source_group": "tablero_eps",
        "tables": [{"name": "%OCUPACIONAL"}],
        "columns": [
            {"table": "%OCUPACIONAL", "name": "FECHA", "data_type": "Date"},
            {"table": "%OCUPACIONAL", "name": "SERVICIO", "data_type": "Text"},
            {"table": "%OCUPACIONAL", "name": "OCUPADAS", "data_type": "Integer"},
            {"table": "%OCUPACIONAL", "name": "CAPACIDAD", "data_type": "Integer"},
        ],
        "measures": [
            {"table": "%OCUPACIONAL", "name": "%OCUPACIONALC", "data_type": "Number", "format_string": "0.00%",
             "expression": "DIVIDE(SUM('%OCUPACIONAL'[OCUPADAS]), SUM('%OCUPACIONAL'[CAPACIDAD]))",
             "description": "Porcentaje ocupacional de urgencias."},
        ],
        "pages": [
            {"name": "TRIAGES ATENDIDOS", "visuals": [
                ["card", "Ocupación de urgencias", [["measure", "%OCUPACIONAL", "%OCUPACIONALC"]]],
            ]},
        ],
    },
    {
        # Solo filas fijas (sin páginas): el catálogo de TABLERO FARMACIA queda igual.
        "semantic_model_key": "tablero_farmacia",
        "source_group": "tablero_farmacia",
        "sim_tables": farmacia_sim_tables,
    },
]


def fingerprint_bytes():
    return Path(__file__).read_bytes()


# ----------------------------------------------------------------------------
# Metadata (CSV en formato INFO.VIEW.*)
# ----------------------------------------------------------------------------

def _stable_id(*parts):
    return 900_000 + int(hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:6], 16) % 90_000


def _append_rows(path, rows):
    """Agrega filas a un CSV de metadata respetando su separador, cabeceras y codificación."""
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
        encoding = "utf-8"
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
        encoding = "latin-1"
    header_line = text.splitlines()[0]
    delimiter = max((",", ";", "\t"), key=header_line.count)
    headers = next(csv.reader([header_line], delimiter=delimiter))
    plain = [h.strip().strip("[]") for h in headers]
    with open(path, "a", encoding=encoding, newline="") as file:
        if not text.endswith(("\n", "\r")):
            file.write("\r\n")
        writer = csv.writer(file, delimiter=delimiter, lineterminator="\r\n")
        for row in rows:
            writer.writerow(["" if row.get(h) is None else row.get(h) for h in plain])


def patch_metadata(folder, patch):
    slug = patch["semantic_model_key"]
    tables = [{"ID": _stable_id(slug, "t", t["name"]), "Name": t["name"], "IsHidden": "False",
               "StorageMode": "Import", "Expression": t.get("expression", "")} for t in patch.get("tables", [])]
    columns = []
    for c in patch.get("columns", []):
        columns.append({
            "ID": _stable_id(slug, "c", c["table"], c["name"]), "Name": c["name"], "Table": c["table"],
            "DataType": c["data_type"], "DataCategory": "Regular", "Description": c.get("description", ""),
            "IsHidden": "False", "IsUnique": str(bool(c.get("unique"))), "IsKey": "False", "IsNullable": "True",
            "SummarizeBy": "Sum" if c["data_type"] in ("Integer", "Number") else "None",
            "Type": "Calculated" if c.get("expression") else "Data",
            "SourceColumn": "" if c.get("expression") else c["name"], "Expression": c.get("expression", ""),
            "FormatString": c.get("format_string", ""),
        })
    measures = [{
        "ID": _stable_id(slug, "m", m["name"]), "Name": m["name"], "Table": m["table"],
        "Description": m.get("description", ""), "DataType": m["data_type"], "Expression": m["expression"],
        "FormatString": m.get("format_string", ""), "IsHidden": "False", "State": "Ready",
    } for m in patch.get("measures", [])]
    relationships = [{
        "ID": _stable_id(slug, "r", r["from_table"], r["from_column"], r["to_table"], r["to_column"]),
        "Name": f"patch_{r['from_table']}_{r['to_table']}",
        "Relationship": f"'{r['from_table']}'[{r['from_column']}] *[<-]1 '{r['to_table']}'[{r['to_column']}]",
        "IsActive": "True", "CrossFilteringBehavior": "OneDirection",
        "FromTable": r["from_table"], "FromColumn": r["from_column"], "FromCardinality": "Many",
        "ToTable": r["to_table"], "ToColumn": r["to_column"], "ToCardinality": "One", "State": "Ready",
    } for r in patch.get("relationships", [])]
    for name, rows in (("tables.csv", tables), ("columns.csv", columns), ("measures.csv", measures),
                       ("relationships.csv", relationships)):
        if rows:
            _append_rows(folder / name, rows)
    builder = patch.get("sim_tables")
    if builder:
        (folder / "_sim_tables.json").write_text(
            json.dumps(builder(), ensure_ascii=False, indent=1), encoding="utf-8")


# ----------------------------------------------------------------------------
# PBIR
# ----------------------------------------------------------------------------

def _field(item):
    kind, table, name = item[0], item[1], item[2]
    source = {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}
    if kind == "measure":
        return {"Measure": source}, f"{table}.{name}", item[3:]
    if kind == "agg":
        function = item[3]
        field = {"Aggregation": {"Expression": {"Column": source}, "Function": PBIR_FUNCTIONS[function]}}
        return field, f"{QUERY_REF_PREFIX[function]}({table}.{name})", item[4:]
    return {"Column": source}, f"{table}.{name}", item[3:]


def _visual(name, vtype, title, fields):
    roles = {}
    for item in fields:
        field, query_ref, rest = _field(item)
        role = rest[0] if len(rest) > 0 and rest[0] else "Values"
        display = rest[1] if len(rest) > 1 else None
        projection = {"field": field, "queryRef": query_ref, "nativeQueryRef": display or item[2]}
        if display:
            projection["displayName"] = display
        roles.setdefault(role, {"projections": []})["projections"].append(projection)
    visual = {"visualType": vtype, "query": {"queryState": roles}}
    if title:
        visual["visualContainerObjects"] = {"title": [{"properties": {
            "text": {"expr": {"Literal": {"Value": f"'{title}'"}}}}}]}
    return {"name": name, "visual": visual}


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def patch_report(report_dir, patch):
    """Renombra páginas y agrega visuales (en páginas existentes por nombre visible o nuevas)."""
    slug = patch["semantic_model_key"]
    pages_dir = report_dir / "definition" / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    by_name = {}
    for page_json in pages_dir.glob("*/page.json"):
        data = _read_json(page_json)
        new_name = (patch.get("rename_pages") or {}).get(data.get("displayName"))
        if new_name:
            data["displayName"] = new_name
            _write_json(page_json, data)
        by_name[str(data.get("displayName") or "").casefold()] = page_json.parent
    order_file = pages_dir / "pages.json"
    order = _read_json(order_file) if order_file.exists() else {"pageOrder": []}
    added = []
    for page in patch.get("pages", []):
        folder = by_name.get(page["name"].casefold())
        if folder is None:
            page_name = f"patch{hashlib.sha1((slug + page['name']).encode()).hexdigest()[:12]}"
            folder = pages_dir / page_name
            (folder / "visuals").mkdir(parents=True, exist_ok=True)
            _write_json(folder / "page.json", {"name": page_name, "displayName": page["name"]})
            order.setdefault("pageOrder", []).append(page_name)
            by_name[page["name"].casefold()] = folder
        for index, (vtype, title, fields) in enumerate(page["visuals"], 1):
            seed = "|".join((slug, page["name"], str(index)))
            name = f"patch{hashlib.sha1(seed.encode()).hexdigest()[:12]}"
            target = folder / "visuals" / name
            target.mkdir(parents=True, exist_ok=True)
            _write_json(target / "visual.json", _visual(name, vtype, title, fields))
            added.append(f"{page['name']}: {title or vtype}")
    _write_json(order_file, order)
    return added


def _original_report(data_root, manifest):
    """PBIR original del grupo: pbir_path del manifiesto o data/pbir/<Informe>.Report."""
    candidates = []
    explicit = manifest.get("pbir_path") or manifest.get("report_path")
    if explicit:
        path = Path(explicit)
        candidates.append(path if path.is_absolute() else Path(data_root).parent / path)
    report = manifest.get("report") or manifest.get("default_dashboard")
    if report:
        candidates.append(Path(data_root) / "pbir" / f"{report}.Report")
    return next((path for path in candidates if (path / "definition").is_dir()), None)


def apply_patches(data_root, root, patches=None):
    """Aplica los parches a <root>/data (copia de data_root). Devuelve el informe de lo hecho."""
    data = Path(root) / "data"
    report = []
    for patch in PATCHES if patches is None else patches:
        slug, group = patch["semantic_model_key"], patch["source_group"]
        entry = {"semantic_model_key": slug, "source_group": group, "status": "skipped"}
        report.append(entry)
        folder = data / "model_metadata" / slug
        if not folder.exists():
            entry["reason"] = "el modelo no está en data/model_metadata"
            continue
        patch_metadata(folder, patch)
        entry["status"] = "metadata"
        if not (patch.get("pages") or patch.get("rename_pages")):
            entry["reason"] = "sin cambios en el informe: no se reconstruye el catálogo"
            continue
        manifest_path = Path(data_root) / "raw" / group / "manifest.json"
        manifest = _read_json(manifest_path) if manifest_path.exists() else {}
        original = _original_report(data_root, manifest) if manifest else None
        if original is None:
            entry["reason"] = "sin manifest o PBIR original: solo se parchea la metadata"
            continue
        target = data / "pbir" / original.name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(original, target, ignore=shutil.ignore_patterns(".pbi", "*.abf"))
        entry["visuals"] = patch_report(target, patch)
        raw = data / "raw" / group
        raw.mkdir(parents=True, exist_ok=True)
        manifest = dict(manifest)
        manifest["pbir_path"] = str(target.relative_to(root)).replace("\\", "/")
        _write_json(raw / "manifest.json", manifest)
        entry["status"] = "metadata+pbir"
    _write_json(data / "catalog" / REPORT_FILE, report)
    return report
