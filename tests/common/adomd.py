"""
Cliente ADOMD.NET falso compartido por los arneses de prueba (tests/sim y tests/realistic).

PowerBIProvider (src/providers/powerbi_provider.py) hace:
    import clr; clr.AddReference(...)
    from Microsoft.AnalysisServices.AdomdClient import AdomdConnection, AdomdRestrictionCollection
    conn = AdomdConnection("Data Source=...;Initial Catalog=<modelo>;..."); conn.Open()
    cmd = conn.CreateCommand(); cmd.CommandText = dax; reader = cmd.ExecuteReader()
    reader.FieldCount / GetName(i) / Read() / GetValue(i); conn.GetSchemaDataSet("DBSCHEMA_CATALOGS", ...)

install_adomd_modules(backend) registra en sys.modules los módulos `clr` y
`Microsoft.AnalysisServices.AdomdClient` respaldados por un "backend" con la interfaz:

    backend.open(catalog)            -> None o lanza (catálogo inexistente, servicio caído)
    backend.execute(catalog, dax)    -> (columnas, filas)   o lanza
    backend.catalogs()               -> [nombres de modelos]

Opcionalmente reproduce cómo pythonnet entrega los tipos .NET: System.DateTime y
System.Decimal llegan como objetos y PowerBIProvider los convierte con str(), que
usa la cultura del Windows (es-CO en los equipos del proyecto: "5/01/2024 2:03:00 p. m.",
"1234567,5"). Ver NetDateTime / NetDecimal.
"""
import datetime as dt
import re
import sys
import types
from decimal import Decimal


# ----------------------------------------------------------------------------
# Tipos .NET (lo que pythonnet devuelve para DateTime / Decimal)
# ----------------------------------------------------------------------------

class NetDateTime:
    """Imita System.DateTime: str() usa la cultura configurada."""

    def __init__(self, value, culture="es-CO"):
        self.value = value
        self.culture = culture
        self.Year, self.Month, self.Day = value.year, value.month, value.day
        self.Hour, self.Minute, self.Second = value.hour, value.minute, value.second

    def ToString(self, fmt=None):
        v = self.value
        if self.culture == "es-CO":
            hour12 = v.hour % 12 or 12
            suffix = "a. m." if v.hour < 12 else "p. m."
            return f"{v.day}/{v.month:02d}/{v.year} {hour12}:{v.minute:02d}:{v.second:02d} {suffix}"
        if self.culture == "en-US":
            hour12 = v.hour % 12 or 12
            suffix = "AM" if v.hour < 12 else "PM"
            return f"{v.month}/{v.day}/{v.year} {hour12}:{v.minute:02d}:{v.second:02d} {suffix}"
        return v.strftime("%m/%d/%Y %H:%M:%S")      # InvariantCulture

    __str__ = ToString

    def __repr__(self):
        return f"<System.DateTime {self.ToString()}>"


class NetDecimal:
    """Imita System.Decimal: str() usa el separador decimal de la cultura."""

    def __init__(self, value, culture="es-CO"):
        self.value = Decimal(value)
        self.culture = culture

    def ToString(self, fmt=None):
        text = format(self.value.normalize(), "f") if self.value == self.value.to_integral() else str(self.value)
        if "E" in text:
            text = format(self.value, "f")
        return text.replace(".", ",") if self.culture == "es-CO" else text

    __str__ = ToString

    def __float__(self):
        return float(self.value)

    def __repr__(self):
        return f"<System.Decimal {self.ToString()}>"


def to_net(value, culture="es-CO", net_types=True):
    """Convierte un valor Python al que entregaría pythonnet desde ADOMD."""
    if not net_types or value is None:
        return value
    if isinstance(value, dt.datetime):
        return NetDateTime(value, culture)
    if isinstance(value, Decimal):
        return NetDecimal(value, culture)
    return value


# ----------------------------------------------------------------------------
# Excepciones (type(error).__name__ es lo que guarda PowerBIProvider)
# ----------------------------------------------------------------------------

class AdomdErrorResponseException(Exception):
    pass


class AdomdConnectionException(Exception):
    pass


# ----------------------------------------------------------------------------
# Clases ADOMD
# ----------------------------------------------------------------------------

class _State:
    def __init__(self, value):
        self.value = value

    def ToString(self):
        return self.value


class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class AdomdDataReader:
    def __init__(self, columns, rows):
        self._columns, self._rows, self._i = list(columns), list(rows), -1
        self.FieldCount = len(self._columns)

    def GetName(self, i):
        return self._columns[i]

    def Read(self):
        self._i += 1
        return self._i < len(self._rows)

    def GetValue(self, i):
        return self._rows[self._i][i]

    def Close(self):
        pass

    def Dispose(self):
        pass


class AdomdCommand:
    def __init__(self, conn):
        self.conn = conn
        self.CommandText = ""

    def ExecuteReader(self):
        if self.conn.State.ToString() != "Open":
            raise AdomdConnectionException("The connection is not open.")
        columns, rows = self.conn.backend.execute(self.conn.catalog, self.CommandText)
        return AdomdDataReader(columns, rows)

    def Dispose(self):
        pass


class AdomdConnection:
    backend = None   # se asigna en install_adomd_modules

    def __init__(self, connection_string):
        self.ConnectionString = connection_string
        m = re.search(r"Initial Catalog=([^;]+);", connection_string)
        self.catalog = m.group(1) if m else None
        self.State = _State("Closed")

    def Open(self):
        self.backend.open(self.catalog)
        self.State = _State("Open")

    def Close(self):
        self.State = _State("Closed")

    def Dispose(self):
        pass

    def CreateCommand(self):
        return AdomdCommand(self)

    def GetSchemaDataSet(self, name, restrictions):
        if name != "DBSCHEMA_CATALOGS":
            raise AdomdErrorResponseException(f"Schema rowset '{name}' no soportado por el simulador.")
        rows = [{"CATALOG_NAME": catalog} for catalog in self.backend.catalogs()]
        return _Obj(Tables=[_Obj(Rows=rows)])


class AdomdRestrictionCollection:
    pass


def _module(name, **attrs):
    mod = types.ModuleType(name)
    mod.__dict__.update(attrs)
    mod.__sim_fake__ = True
    sys.modules[name] = mod
    return mod


def install_adomd_modules(backend):
    """Registra `clr` y `Microsoft.AnalysisServices.AdomdClient` falsos sobre `backend`."""
    connection_cls = type("AdomdConnection", (AdomdConnection,), {"backend": backend})
    _module("clr", AddReference=lambda name: None)
    ms = _module("Microsoft")
    asv = _module("Microsoft.AnalysisServices")
    adomd = _module("Microsoft.AnalysisServices.AdomdClient",
                    AdomdConnection=connection_cls,
                    AdomdRestrictionCollection=AdomdRestrictionCollection,
                    AdomdErrorResponseException=AdomdErrorResponseException,
                    AdomdConnectionException=AdomdConnectionException)
    ms.AnalysisServices = asv
    asv.AdomdClient = adomd
    return connection_cls
