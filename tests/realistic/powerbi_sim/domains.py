"""
Dominios de valores plausibles (español clínico) y cosecha de literales reales.

Los valores categóricos de cada columna salen, por prioridad, de:
  1. Literales usados en las expresiones DAX del propio modelo (medidas y columnas
     calculadas):  'T'[C] = "X",  'T'[C] IN {"A","B"},  SWITCH(SELECTEDVALUE('T'[C]), "X", ...)
  2. Literales de filtros de los visual.json de los tableros PBIR (si existen en disco;
     se leen en memoria y NUNCA se versionan).
  3. Listas genéricas de este módulo según el nombre de la columna/tabla.

Nunca se usan nombres de personas, documentos ni datos de pacientes: las columnas
de personas (paciente, médico, facturador, usuario...) se generan con etiquetas
sintéticas ("PACIENTE SIMULADO 0042", "PROFESIONAL 07").
"""
import json
import re
from pathlib import Path

from .dax_parser import BinOp, Call, ColRef, InOp, Str, TableCtor, Num, DaxError, parse_expression, walk
from .metadata import key, normalize_text

# ----------------------------------------------------------------------------
# Listas genéricas
# ----------------------------------------------------------------------------

ESPECIALIDADES = [
    "CIRUGIA GENERAL", "ORTOPEDIA Y TRAUMATOLOGIA", "GINECOLOGIA Y OBSTETRICIA", "MEDICINA INTERNA",
    "PEDIATRIA", "UROLOGIA", "NEUROCIRUGIA", "CARDIOLOGIA", "OTORRINOLARINGOLOGIA", "OFTALMOLOGIA",
    "CIRUGIA PLASTICA", "GASTROENTEROLOGIA", "ANESTESIOLOGIA", "NEUROLOGIA", "DERMATOLOGIA",
    "CIRUGIA VASCULAR", "NEUMOLOGIA", "PSIQUIATRIA",
]
SERVICIOS = [
    "URGENCIAS", "HOSPITALIZACION", "UCI ADULTOS", "UCI NEONATAL", "CIRUGIA", "CONSULTA EXTERNA",
    "OBSTETRICIA", "PEDIATRIA", "CUIDADO INTERMEDIO ADULTO", "HOSPITALIZACION PARCIAL", "IMAGENES",
    "LABORATORIO CLINICO", "UNIDAD CARDIONEUROVASCULAR", "ATENCION DOMICILIARIA",
]
ASEGURADORAS = [
    "NUEVA EPS", "SANITAS EPS", "SURA EPS", "SALUD TOTAL EPS", "COOSALUD EPS", "ASMET SALUD EPS",
    "FAMISANAR EPS", "COMPENSAR EPS", "PARTICULAR", "SOAT - SEGUROS DEL ESTADO", "ADRES",
    "MEDICINA PREPAGADA COLSANITAS", "POLICIA NACIONAL", "FUERZAS MILITARES", "ARL SURA",
    "SALUD MIA EPS", "MUTUAL SER EPS", "EPS FAMILIAR DE COLOMBIA",
]
SEDES = ["SEDE PRINCIPAL", "SEDE NORTE", "SEDE SUR", "SEDE CENTRO"]
MUNICIPIOS = ["MANIZALES", "VILLAMARIA", "CHINCHINA", "LA DORADA", "RIOSUCIO", "ANSERMA", "PEREIRA",
              "ARMENIA", "NEIRA", "SUPIA", "AGUADAS", "SALAMINA"]
DEPARTAMENTOS = ["CALDAS", "RISARALDA", "QUINDIO", "TOLIMA", "ANTIOQUIA", "VALLE DEL CAUCA"]
REGIMENES = ["CONTRIBUTIVO", "SUBSIDIADO", "ESPECIAL", "PARTICULAR", "VINCULADO"]
TRIAGE = ["I", "II", "III", "IV", "V"]
SEXOS = ["F", "M"]
TURNOS = ["MAÑANA", "TARDE", "NOCHE"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
         "octubre", "noviembre", "diciembre"]
MESES_CORTOS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
DIAS_SEMANA = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
DIAGNOSTICOS = [
    "J189 NEUMONIA, NO ESPECIFICADA", "I10X HIPERTENSION ESENCIAL (PRIMARIA)",
    "E119 DIABETES MELLITUS NO INSULINODEPENDIENTE SIN MENCION DE COMPLICACION",
    "N390 INFECCION DE VIAS URINARIAS, SITIO NO ESPECIFICADO", "K359 APENDICITIS AGUDA, NO ESPECIFICADA",
    "O800 PARTO UNICO ESPONTANEO, PRESENTACION CEFALICA DE VERTICE",
    "R104 OTROS DOLORES ABDOMINALES Y LOS NO ESPECIFICADOS", "S525 FRACTURA DE LA EPIFISIS INFERIOR DEL RADIO",
    "A09X DIARREA Y GASTROENTERITIS DE PRESUNTO ORIGEN INFECCIOSO",
    "J449 ENFERMEDAD PULMONAR OBSTRUCTIVA CRONICA, NO ESPECIFICADA", "I219 INFARTO AGUDO DEL MIOCARDIO, SIN OTRA ESPECIFICACION",
    "K802 CALCULO DE LA VESICULA BILIAR SIN COLECISTITIS",
]
PROCEDIMIENTOS = [
    "HEMOGRAMA IV", "ECOGRAFIA DE ABDOMEN TOTAL", "RADIOGRAFIA DE TORAX", "TOMOGRAFIA DE CRANEO SIMPLE",
    "COLECISTECTOMIA POR LAPAROSCOPIA", "APENDICECTOMIA", "CESAREA SEGMENTARIA", "ELECTROCARDIOGRAMA",
    "ECOCARDIOGRAMA TRANSTORACICO", "RESONANCIA MAGNETICA DE RODILLA", "GLUCOSA EN SUERO", "CREATININA EN SUERO",
    "HERNIORRAFIA INGUINAL", "REEMPLAZO TOTAL DE RODILLA", "BIOPSIA DE PIEL",
]
ESTADOS = {
    "cita": ["CUMPLIDA", "CANCELADA", "INASISTENCIA", "PROGRAMADA"],
    "cama": ["OCUPADA", "DISPONIBLE", "EN ASEO", "BLOQUEADA", "RESERVADA"],
    "factur": ["FACTURADA", "PENDIENTE", "RADICADA", "GLOSADA"],
    "cirug": ["REALIZADA", "PROGRAMADA", "CANCELADA", "EN ESPERA"],
    "qx": ["REALIZADA", "PROGRAMADA", "CANCELADA", "EN ESPERA"],
    "solicitud": ["PENDIENTE", "ASIGNADA", "CANCELADA", "CERRADA"],
    "remision": ["ACEPTADA", "RECHAZADA", "EN TRAMITE", "CERRADA"],
    "": ["ACTIVO", "CERRADO", "ANULADO", "PENDIENTE"],
}
TIPOS = {
    "ingreso": ["URGENCIAS", "HOSPITALARIO", "AMBULATORIO"],
    "documento": ["CC", "TI", "RC", "CE", "PA"],
    "consulta": ["PRIMERA VEZ", "CONTROL"],
    "egreso": ["VIVO", "FALLECIDO", "REMITIDO", "ALTA VOLUNTARIA"],
    "atencion": ["AMBULATORIA", "URGENCIAS", "HOSPITALARIA", "DOMICILIARIA"],
    "cirugia": ["PROGRAMADA", "URGENTE"],
    "cama": ["ADULTO", "PEDIATRICA", "NEONATAL", "UCI", "INTERMEDIA"],
    "": ["TIPO A", "TIPO B", "TIPO C"],
}
VIAS_INGRESO = ["URGENCIAS", "CONSULTA EXTERNA", "REMITIDO", "PROGRAMADO"]
DESTINOS = ["CASA", "HOSPITALIZACION", "UCI", "REMITIDO OTRA IPS", "CIRUGIA", "OBSERVACION"]
MOTIVOS = ["DOLOR ABDOMINAL", "FIEBRE", "TRAUMA", "DIFICULTAD RESPIRATORIA", "CONTROL PRENATAL", "CEFALEA"]
SI_NO = ["SI", "NO"]
# Segmentador de grupo etario (literales del SQL documentado: CASE ... 'MENORES DE EDAD').
GRUPO_ETARIO = ["MENORES DE EDAD", "MAYORES DE EDAD"]
# Áreas que envían ropa a lavandería (tabla Cp_Medicion); sin especialidades médicas.
LAVANDERIA_SERVICIOS = [
    "ANTIFLUIDOS", "URGENCIAS", "UCI ADULTOS", "UCI NEONATAL", "HOSPITALIZACION", "CIRUGIA",
    "PEDIATRIA", "GINECOBSTETRICIA", "CONSULTA EXTERNA", "CENTRAL DE ESTERILIZACION",
]
# Identificadores internos (OID) de servicios, terceros...: códigos, no nombres.
OID_CODES = [str(code) for code in range(101, 113)]

# Columnas de personas: valores sintéticos, nunca cosechados.
PERSON_RE = re.compile(
    r"paciente|nombre|apellido|medico|facturador|profesional|usuario|asesor|responsable|"
    r"enfermer|especialista|auditor|digitador|cajero|validador|usu_|docente|autoriz", re.I)
IDENT_RE = re.compile(r"documento|identificacion|cedula|historia|telefono|celular|direccion|correo|email|"
                      r"^nro_?doc|^num_?doc|^doc_|^id_paciente", re.I)
# Nombres "no de persona" que contienen "nombre"
NON_PERSON_NAME_RE = re.compile(
    r"servicio|entidad|asegura|eps|tercero|sede|especialidad|procedimiento|examen|diagnostico|"
    r"municipio|ciudad|departamento|unidad|area|cama|empresa|convenio|prestador|centro|piso|subgrupo|grupo", re.I)


def is_person_column(table_name, column_name):
    col = str(column_name or "")
    if IDENT_RE.search(col):
        return True
    if PERSON_RE.search(col):
        return not NON_PERSON_NAME_RE.search(col)
    return False


# ----------------------------------------------------------------------------
# Inferencia del "rol" de una columna
# ----------------------------------------------------------------------------

def _tokens(text):
    return set(normalize_text(text).split())


def _has(text, *needles):
    norm = normalize_text(text).replace(" ", "_")
    return any(n in norm for n in needles)


def text_domain(table_name, column_name):
    """Dominio genérico para una columna de texto (lista) o None si es identificador libre."""
    col = str(column_name)
    tab = str(table_name)
    both = f"{tab} {col}"
    norm_col = normalize_text(col).replace(" ", "_")
    if is_person_column(tab, col):
        return None
    compact = normalize_text(col).replace(" ", "")
    if compact.startswith("oid") or compact.endswith("oid") or "oid" in normalize_text(norm_col).split():
        return OID_CODES
    if _has(col, "menores", "mayores", "etario", "grupo_edad"):
        return GRUPO_ETARIO
    if _has(tab, "lavander") and _has(col, "servicio", "area", "medicion"):
        return LAVANDERIA_SERVICIOS
    if _has(col, "especialidad", "especiali"):
        return ESPECIALIDADES
    if _has(col, "sexo", "genero"):
        return SEXOS
    if _has(col, "regimen"):
        return REGIMENES
    if _has(col, "triage", "trige") and _has(col, "descri", "nombre", "detalle"):
        return [f"TRIAGE {nivel}" for nivel in TRIAGE]
    if _has(col, "triage", "trige", "clasificacion", "nivel_urg", "prioridad"):
        return TRIAGE
    if norm_col.startswith("ter") and _has(col, "nom") or _has(col, "nomcom", "tercer", "razon_soc"):
        return ASEGURADORAS
    if _has(col, "turno"):
        return TURNOS
    if _has(col, "dia_semana", "diasemana", "nombre_dia", "weekday"):
        return DIAS_SEMANA
    if normalize_text(col) in ("mes", "nombre mes", "mes nombre", "month", "nombremes") or _has(col, "nombre_mes"):
        return MESES
    if _has(col, "municipio", "ciudad"):
        return MUNICIPIOS
    if _has(col, "departamento"):
        return DEPARTAMENTOS
    if _has(col, "sede"):
        return SEDES
    if _has(col, "diagnost", "cie10", "cie_10", "dx"):
        return DIAGNOSTICOS
    if _has(col, "procedimiento", "cups", "examen", "estudio", "prueba"):
        return PROCEDIMIENTOS
    if _has(col, "estado"):
        for hint, values in ESTADOS.items():
            if hint and _has(both, hint):
                return values
        return ESTADOS[""]
    if _has(col, "tipo"):
        for hint, values in TIPOS.items():
            if hint and _has(col, hint):
                return values
        for hint, values in TIPOS.items():
            if hint and _has(tab, hint):
                return values
        return TIPOS[""]
    if _has(col, "via_ingreso", "viaingreso", "origen"):
        return VIAS_INGRESO
    if _has(col, "destino"):
        return DESTINOS
    if _has(col, "motivo", "causa"):
        return MOTIVOS
    if _has(col, "asegura", "eps", "entidad", "tercero", "pagador", "convenio", "administradora", "cliente",
            "empresa", "razon_social", "gennombre", "prestador"):
        return ASEGURADORAS
    if _has(col, "servicio", "unidad", "area", "piso", "ubicacion", "subgrupo", "pabellon", "hsunombre"):
        return SERVICIOS
    if _has(col, "cama", "habitacion"):
        return [f"H{p}{n:02d}" for p in (2, 3, 4, 5) for n in range(1, 13)]
    if _has(col, "quirofano", "sala"):
        return [f"QUIROFANO {n}" for n in range(1, 9)]
    if _has(col, "mostrar", "activo", "aplica", "es_", "flag", "indicador_"):
        return SI_NO
    # Columnas descriptivas genéricas: el dominio lo da la tabla.
    if _has(col, "nombre", "descri", "detalle", "nomcom", "denominacion"):
        if _has(tab, "asegura", "eps", "entidad", "tercero", "pagador", "convenio"):
            return ASEGURADORAS
        if _has(tab, "servicio", "unidad", "area", "piso"):
            return SERVICIOS
        if _has(tab, "especialidad"):
            return ESPECIALIDADES
        if _has(tab, "sede"):
            return SEDES
        if _has(tab, "diagnost"):
            return DIAGNOSTICOS
        if _has(tab, "procedimiento", "examen", "laborator", "imagen"):
            return PROCEDIMIENTOS
    return []


def person_kind(column_name):
    col = normalize_text(column_name)
    if IDENT_RE.search(str(column_name)):
        return "ident"
    if "paciente" in col or col in ("nombre", "nombres", "nombre completo", "apellidos"):
        return "patient"
    return "staff"


def synthetic_person(kind, index):
    """Etiqueta sintética para columnas de personas (kind = person_kind(columna))."""
    if kind == "ident":
        return str(10_000_000 + index * 7919 % 89_000_000)
    if kind == "patient":
        return f"PACIENTE SIMULADO {index:05d}"
    return f"PROFESIONAL {index % 40 + 1:02d}"


# ----------------------------------------------------------------------------
# Cosecha de literales
# ----------------------------------------------------------------------------

class DomainHarvest:
    """Valores literales por (tabla, columna) cosechados del modelo y de los PBIR."""

    def __init__(self):
        self.values = {}          # (key tabla, key columna) -> lista ordenada sin duplicados
        self.by_column = {}       # key columna -> lista (cuando la tabla no coincide)
        self.ranges = {}          # (tabla, columna) -> {"min":..., "max":...} de comparaciones numéricas

    def add(self, table, column, value, weak=False):
        if value is None or is_person_column(table, column):
            return
        if isinstance(value, str) and (not value.strip() or value.strip().lower() == "null"):
            return
        target = self.by_column.setdefault(key(column), []) if weak else \
            self.values.setdefault((key(table), key(column)), [])
        if value not in target:
            target.append(value)

    def get(self, table, column):
        return list(self.values.get((key(table), key(column)), []))

    def get_weak(self, column):
        """Valores por nombre de columna (sin tabla conocida): complementan, no reemplazan."""
        return list(self.by_column.get(key(column), []))

    # ---------- desde expresiones DAX ----------
    def harvest_schema(self, schema):
        exprs = [m.expression for m in schema.measures.values()]
        for table in schema.tables.values():
            exprs.extend(c.expression for c in table.columns.values() if c.expression)
        for text in exprs:
            if not text or not text.strip():
                continue
            try:
                tree = parse_expression(text)
            except DaxError:
                continue
            self._harvest_tree(schema, tree)

    def _resolve(self, schema, node):
        if isinstance(node, ColRef) and node.table:
            column = schema.column(node.table, node.column)
            if column is not None:
                return column
        if isinstance(node, Call) and node.name in ("SELECTEDVALUE", "VALUES", "MAX", "MIN") and node.args:
            return self._resolve(schema, node.args[0])
        return None

    def _harvest_tree(self, schema, tree):
        for node in walk(tree):
            if isinstance(node, BinOp) and node.op in ("=", "==", "<>"):
                for col_node, lit in ((node.left, node.right), (node.right, node.left)):
                    column = self._resolve(schema, col_node)
                    if column is not None and isinstance(lit, (Str, Num)):
                        if column.dtype == "text" and isinstance(lit, Str):
                            self.add(column.table, column.name, lit.value)
                        elif column.dtype in ("int", "float") and isinstance(lit, Num):
                            self.add(column.table, column.name, lit.value)
            elif isinstance(node, InOp) and isinstance(node.target, TableCtor):
                column = self._resolve(schema, node.expr)
                if column is not None:
                    for row in node.target.rows:
                        for item in row:
                            if isinstance(item, Str) and column.dtype == "text":
                                self.add(column.table, column.name, item.value)
                            elif isinstance(item, Num) and column.dtype in ("int", "float"):
                                self.add(column.table, column.name, item.value)
            elif isinstance(node, Call) and node.name == "SWITCH" and len(node.args) >= 3:
                column = self._resolve(schema, node.args[0])
                if column is not None and column.dtype == "text":
                    for arg in node.args[1::2]:
                        if isinstance(arg, Str):
                            self.add(column.table, column.name, arg.value)

    # ---------- desde la documentación ----------
    def harvest_documented(self, schema):
        """Valores de <modelo>/_documented_values.json (tools/local_data: CASE/IN del SQL
        documentado y literales DAX). Las entradas sin tabla (no se sabe a qué tabla del
        modelo fue el SELECT) son débiles: se suman al dominio genérico de las columnas
        con ese nombre en lugar de reemplazarlo."""
        path = Path(schema.path) / "_documented_values.json" if getattr(schema, "path", None) else None
        if not path or not path.exists():
            return 0
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return 0
        count = 0
        for entry in payload.get("columns", []) or []:
            column_name = entry.get("column")
            if not column_name:
                continue
            if entry.get("table"):
                targets = [schema.column(entry["table"], column_name)]
            else:
                targets = [table.columns.get(key(column_name)) for table in schema.tables.values()]
            for column in targets:
                if column is None or column.dtype != "text":
                    continue
                for value in entry.get("values", []) or []:
                    if isinstance(value, str):
                        self.add(column.table, column.name, value, weak=not entry.get("table"))
                        count += 1
        return count

    # ---------- desde visual.json (PBIR) ----------
    def harvest_pbir(self, tableros_root):
        """Lee literales de filtros (In / Comparison) de los visual.json/page.json/report.json."""
        root = Path(tableros_root) if tableros_root else None
        if not root or not root.exists():
            return 0
        count = 0
        patterns = ("visual.json", "page.json", "report.json")
        for path in root.rglob("*.json"):
            if path.name not in patterns or ".pbi" in path.parts:
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            count += self._walk_pbir(data, {})
        return count

    def _walk_pbir(self, node, aliases):
        found = 0
        if isinstance(node, dict):
            local = dict(aliases)
            for item in node.get("From", []) or []:
                if isinstance(item, dict) and item.get("Name") and item.get("Entity"):
                    local[item["Name"]] = item["Entity"]
            if isinstance(node.get("In"), dict):
                found += self._from_in(node["In"], local)
            if isinstance(node.get("Comparison"), dict):
                found += self._from_comparison(node["Comparison"], local)
            for value in node.values():
                found += self._walk_pbir(value, local)
        elif isinstance(node, list):
            for value in node:
                found += self._walk_pbir(value, aliases)
        return found

    @staticmethod
    def _column_of(expr, aliases):
        column = (expr or {}).get("Column") if isinstance(expr, dict) else None
        if not isinstance(column, dict):
            return None, None
        ref = (column.get("Expression") or {}).get("SourceRef") or {}
        entity = ref.get("Entity") or aliases.get(ref.get("Source"))
        return entity, column.get("Property")

    @staticmethod
    def _literal(value):
        lit = (value or {}).get("Literal", {}).get("Value") if isinstance(value, dict) else None
        if lit is None or lit == "null":
            return None
        if lit.startswith("'") and lit.endswith("'"):
            return lit[1:-1].replace("''", "'").rstrip()
        m = re.fullmatch(r"(-?\d+)L", lit)
        if m:
            return int(m.group(1))
        m = re.fullmatch(r"(-?\d+(?:\.\d+)?)D", lit)
        if m:
            return float(m.group(1))
        return None

    def _from_in(self, node, aliases):
        found = 0
        columns = [self._column_of(e, aliases) for e in node.get("Expressions", []) or []]
        for row in node.get("Values", []) or []:
            for index, value in enumerate(row or []):
                if index >= len(columns):
                    continue
                entity, prop = columns[index]
                literal = self._literal(value)
                if entity and prop and literal is not None:
                    self.add(entity, prop, literal)
                    found += 1
        return found

    def _from_comparison(self, node, aliases):
        entity, prop = self._column_of(node.get("Left"), aliases)
        literal = self._literal(node.get("Right"))
        if entity and prop and literal is not None and node.get("ComparisonKind", 0) == 0:
            self.add(entity, prop, literal)
            return 1
        return 0
