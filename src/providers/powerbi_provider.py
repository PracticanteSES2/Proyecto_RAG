import math
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from src.chatbot.runtime_stats import STATS


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


def _net_to_python(value):
    """Valor de ADOMD (pythonnet) a Python sin depender de la cultura de Windows.

    pythonnet 3 entrega System.DateTime y System.Decimal como objetos .NET y su
    str() usa la cultura del equipo (es-CO: «1/01/2023 12:00:00 a. m.»,
    «3906,4»), que luego no se puede convertir a número ni ordenar. Fechas ->
    ISO («2023-01-01» o «2023-01-01 08:30:00»); decimales -> float.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if all(hasattr(value, name) for name in ("Year", "Month", "Day", "Hour", "Minute", "Second")):
        try:
            moment = datetime(
                int(value.Year), int(value.Month), int(value.Day),
                int(value.Hour), int(value.Minute), int(value.Second),
            )
            if moment.time() == datetime.min.time():
                return moment.strftime("%Y-%m-%d")
            return moment.isoformat(sep=" ")
        except (TypeError, ValueError):
            pass
    try:
        return float(value)
    except (TypeError, ValueError):
        pass
    try:
        from System import Decimal as NetDecimal

        return float(NetDecimal.ToDouble(value))
    except Exception:
        pass
    return str(value)


class PowerBIProvider:

    def __init__(
        self,
        endpoint=None,
        default_semantic_model=None,
    ):

        self.endpoint = (
            endpoint
            or os.getenv(
                "POWERBI_XMLA_ENDPOINT"
            )
        )

        self.default_semantic_model = (
            default_semantic_model
            or os.getenv(
                "POWERBI_SEMANTIC_MODEL"
            )
        )

        self.adomd_path = os.getenv(
            "ADOMD_PATH"
        )

        self.identity_path = os.getenv(
            "IDENTITY_PATH"
        )

        if not self.endpoint:
            raise ValueError(
                "POWERBI_XMLA_ENDPOINT "
                "no está configurado."
            )

        self._connections = {}

        # Evita aperturas/consultas concurrentes sobre
        # la misma conexión desde reruns o sesiones.
        self._connection_lock = (
            threading.RLock()
        )

        # Función (modelo, dax) que se avisa ANTES de cada consulta, para
        # mostrar en vivo qué está consultando (la engancha QueryEngine).
        self.query_listener = None

        # Función (título, *líneas) para avisos en vivo que no son consultas
        # (p. ej. «Abriendo conexión con Power BI»). La engancha QueryEngine.
        self.activity_listener = None

        # Modelos con los que ya se abrió alguna conexión (para distinguir
        # apertura de reconexión) y últimos eventos de conexión (diagnóstico).
        self._opened_models = set()
        self.connection_events = []

        self._load_dotnet_dependencies()

    # ========================================================
    # DEPENDENCIAS
    # ========================================================

    def _load_dotnet_dependencies(
        self
    ):

        if not self.adomd_path:
            raise ValueError(
                "ADOMD_PATH no está "
                "configurado en .env"
            )

        if not self.identity_path:
            raise ValueError(
                "IDENTITY_PATH no está "
                "configurado en .env"
            )

        adomd_dll = (
            Path(self.adomd_path)
            / "Microsoft.AnalysisServices."
              "AdomdClient.dll"
        )

        identity_dll = (
            Path(self.identity_path)
            / "Microsoft.Identity.Client.dll"
        )

        if not adomd_dll.exists():
            raise FileNotFoundError(
                f"No se encontró: "
                f"{adomd_dll}"
            )

        if not identity_dll.exists():
            raise FileNotFoundError(
                f"No se encontró: "
                f"{identity_dll}"
            )

        if (
            self.identity_path
            not in sys.path
        ):
            sys.path.insert(
                0,
                self.identity_path,
            )

        if (
            self.adomd_path
            not in sys.path
        ):
            sys.path.append(
                self.adomd_path
            )

        import clr

        clr.AddReference(
            "Microsoft.Identity.Client"
        )

        clr.AddReference(
            "Microsoft.AnalysisServices."
            "AdomdClient"
        )

        from Microsoft.AnalysisServices.AdomdClient import (
            AdomdConnection,
            AdomdRestrictionCollection,
        )

        self.AdomdConnection = (
            AdomdConnection
        )

        self.AdomdRestrictionCollection = (
            AdomdRestrictionCollection
        )

    # ========================================================
    # CONEXIÓN
    # ========================================================

    def _resolve_semantic_model(
        self,
        semantic_model=None,
    ):

        model = (
            semantic_model
            or self.default_semantic_model
        )

        if not model:
            raise ValueError(
                "No se indicó un modelo "
                "semántico."
            )

        return model

    def _build_connection_string(
        self,
        semantic_model=None,
    ):

        connection_string = (
            f"Data Source={self.endpoint};"
        )

        if semantic_model:
            connection_string += (
                f"Initial Catalog="
                f"{semantic_model};"
            )

        # AUTENTICACIÓN ÚNICA POR PROCESO:
        #
        # - Interactive Login=Enabled permite primero autenticación
        #   silenciosa y usa la ventana interactiva solo como fallback.
        # - Identity Mode=Process conserva la identidad elegida en la
        #   primera conexión y la reutiliza en las conexiones posteriores
        #   del MISMO proceso, incluso si apuntan a otros modelos semánticos
        #   del mismo workspace.
        #
        # NO usar Interactive Login=Always aquí: ese valor desactiva
        # explícitamente el flujo silencioso y fuerza login interactivo
        # cada vez que ADOMD abre una conexión nueva.
        #
        # Con POWERBI_AUTH=device_code (procesos sin escritorio: tareas
        # programadas, pruebas) se usa el token en caché de powerbi_token.
        from src.providers import powerbi_token

        if powerbi_token.modo_sin_ventana():
            return connection_string + (
                f"User ID=;Password={powerbi_token.obtener_token()};"
            )

        connection_string += (
            "Interactive Login=Enabled;"
            "Identity Mode=Process;"
        )

        return connection_string

    def _connection_key(
        self,
        semantic_model=None,
    ):

        return (
            semantic_model
            if semantic_model
            else "__workspace__"
        )

    def _is_connection_open(
        self,
        connection,
    ):

        try:
            return (
                connection is not None
                and
                connection.State.ToString()
                == "Open"
            )

        except Exception:
            return False

    def _notify_activity(self, title, *lines):
        listener = getattr(self, "activity_listener", None)
        if callable(listener):
            try:
                listener(title, *lines)
            except Exception:
                pass

    def _create_connection(
        self,
        semantic_model=None,
        reason=None,
    ):
        """Abre una conexión ADOMD. Con Interactive Login=Enabled, si no hay
        un token válido en caché, Open() muestra una ventana de inicio de
        sesión EN EL SERVIDOR y se queda esperando: por eso se avisa en vivo
        y se cuenta en el diagnóstico (aperturas y reconexiones)."""
        key = self._connection_key(semantic_model)
        reopened = key in getattr(self, "_opened_models", set())
        label = semantic_model or "espacio de trabajo"
        self._notify_activity(
            f"{'Reabriendo' if reopened else 'Abriendo'} conexión con Power BI (modelo {label}). "
            "Si en el servidor aparece una ventana de inicio de sesión, complétala.",
            f"motivo: {reason}" if reason else None,
        )
        started = time.perf_counter()

        connection = (
            self.AdomdConnection(
                self._build_connection_string(
                    semantic_model
                )
            )
        )

        try:
            connection.Open()
        finally:
            elapsed = round(time.perf_counter() - started, 2)
            event = {
                "at": datetime.now().strftime("%H:%M:%S"),
                "model": label,
                "kind": "reconexión" if reopened else "apertura",
                "reason": reason,
                "elapsed_s": elapsed,
                "ok": self._is_connection_open(connection),
            }
            events = getattr(self, "connection_events", None)
            if events is not None:
                events.append(event)
                del events[:-20]

        STATS.powerbi_connection_opened(label, reopened=reopened)
        if hasattr(self, "_opened_models"):
            self._opened_models.add(key)

        return connection

    def _invalidate_connection(
        self,
        semantic_model=None,
    ):

        key = self._connection_key(
            semantic_model
        )

        connection = (
            self._connections.pop(
                key,
                None,
            )
        )

        if connection is None:
            return

        try:
            connection.Close()
        except Exception:
            pass

        try:
            connection.Dispose()
        except Exception:
            pass

    def _get_connection(
        self,
        semantic_model=None,
    ):
        """
        Devuelve una única conexión persistente
        por modelo semántico.
        """

        key = self._connection_key(
            semantic_model
        )

        with self._connection_lock:

            connection = (
                self._connections.get(
                    key
                )
            )

            if self._is_connection_open(
                connection
            ):
                return connection

            reason = None
            if connection is not None:
                try:
                    reason = f"la conexión anterior quedó en estado {connection.State.ToString()}"
                except Exception:
                    reason = "la conexión anterior ya no está abierta"
                self._invalidate_connection(
                    semantic_model
                )
            elif key in getattr(self, "_opened_models", set()):
                reason = "la conexión anterior se cerró"

            connection = (
                self._create_connection(
                    semantic_model,
                    reason=reason,
                )
            )

            self._connections[
                key
            ] = connection

            return connection

    def connect(
        self,
        semantic_model=None,
    ):
        """
        Fuerza la autenticación al iniciar
        la aplicación y conserva la sesión.
        """

        model = (
            self._resolve_semantic_model(
                semantic_model
            )
        )

        try:

            connection = (
                self._get_connection(
                    model
                )
            )

            return {
                "status":
                    "success",
                "semantic_model":
                    model,
                "connection_open":
                    self._is_connection_open(
                        connection
                    ),
                "connection_count":
                    self.connection_count(),
                "authentication_mode":
                    "process_identity_single_login",
            }

        except Exception as error:

            return {
                "status":
                    "error",
                "semantic_model":
                    model,
                "connection_open":
                    False,
                "error_type":
                    type(error).__name__,
                "error":
                    str(error),
            }

    # ========================================================
    # MODELOS
    # ========================================================

    def list_semantic_models(
        self
    ):

        try:

            with self._connection_lock:

                connection = (
                    self._get_connection(
                        semantic_model=None
                    )
                )

                restrictions = (
                    self.AdomdRestrictionCollection()
                )

                dataset = (
                    connection
                    .GetSchemaDataSet(
                        "DBSCHEMA_CATALOGS",
                        restrictions,
                    )
                )

                table = (
                    dataset.Tables[0]
                )

                models = [
                    str(
                        row["CATALOG_NAME"]
                    )
                    for row
                    in table.Rows
                ]

            return {
                "status":
                    "success",
                "models":
                    models,
                "count":
                    len(models),
            }

        except Exception as error:

            return {
                "status":
                    "error",
                "error_type":
                    type(error).__name__,
                "error":
                    str(error),
            }

    # ========================================================
    # DAX
    # ========================================================

    def execute_dax(
        self,
        dax,
        semantic_model=None,
        timeout_s=None,
    ):
        """
        Ejecuta la consulta DAX. `timeout_s` (segundos, opcional): tiempo
        límite de la consulta (AdomdCommand.CommandTimeout); al vencer, ADOMD
        la cancela y se devuelve status="error" con timed_out=True. Lo usan
        las consultas de exploración de valores (src/providers/domain_cache.py);
        las consultas de las respuestas no tienen límite (como siempre).

        El resultado (éxito o error) trae además `wait_s` (espera del candado
        de la conexión: otra consulta en curso), `connect_s` (abrir la conexión
        del modelo si no estaba abierta: Interactive Login, XMLA) y `exec_s`
        (la consulta). CommandTimeout solo cuenta `exec_s`: quien mide el
        total (src/providers/domain_cache.py) descuenta los otros dos.
        """

        model = (
            self._resolve_semantic_model(
                semantic_model
            )
        )

        listener = getattr(self, "query_listener", None)
        if callable(listener):
            try:
                listener(model, dax)
            except Exception:
                pass

        reader = None
        command = None
        connection = None
        started = None
        outcome = {"status": None, "timed_out": False}
        timing = {"wait_s": 0.0, "connect_s": 0.0, "exec_s": 0.0}
        STATS.powerbi_query_begin(model)
        requested = time.perf_counter()

        try:

            # Una sola operación por conexión al mismo tiempo.
            with self._connection_lock:

                acquired = time.perf_counter()
                timing["wait_s"] = round(acquired - requested, 3)

                connection = (
                    self._get_connection(
                        model
                    )
                )

                timing["connect_s"] = round(time.perf_counter() - acquired, 3)

                command = (
                    connection
                    .CreateCommand()
                )

                command.CommandText = dax

                if timeout_s:
                    # CommandTimeout es entero (segundos); 0 = sin límite.
                    command.CommandTimeout = max(
                        1, int(math.ceil(float(timeout_s)))
                    )

                started = time.perf_counter()

                reader = (
                    command.ExecuteReader()
                )

                columns = [
                    reader.GetName(index)
                    for index
                    in range(
                        reader.FieldCount
                    )
                ]

                rows = []

                while reader.Read():

                    row = {}

                    for (
                        index,
                        column,
                    ) in enumerate(
                        columns
                    ):

                        value = (
                            reader.GetValue(
                                index
                            )
                        )

                        row[column] = _net_to_python(
                            value
                        )

                    rows.append(
                        row
                    )

                outcome["status"] = "success"
                timing["exec_s"] = round(time.perf_counter() - started, 3)
                return {
                    "status":
                        "success",
                    "semantic_model":
                        model,
                    "columns":
                        columns,
                    "rows":
                        rows,
                    "row_count":
                        len(rows),
                    **timing,
                }

        except Exception as error:
            """
            CRÍTICO:
            Un error DAX NO significa que la conexión
            haya muerto.

            Antes se eliminaba la conexión ante CUALQUIER
            excepción. Como Interactive Login=Always está
            activo, la siguiente consulta abría otra conexión
            y volvía a mostrar el login.

            Ahora solo invalidamos la conexión si realmente
            dejó de estar abierta.
            """

            if (
                connection is not None
                and not self._is_connection_open(
                    connection
                )
            ):
                self._invalidate_connection(
                    model
                )

            # ¿Venció el CommandTimeout? ADOMD no tiene un tipo propio para
            # eso: se reconoce por el mensaje o por el tiempo transcurrido.
            message = str(error).lower()
            timed_out = bool(timeout_s) and (
                any(
                    word in message
                    for word in (
                        "timed out", "timeout", "time out",
                        "tiempo de espera",
                    )
                )
                or (
                    started is not None
                    and time.perf_counter() - started
                    >= 0.98 * float(timeout_s)
                )
            )

            kept = (
                connection is not None
                and self._is_connection_open(connection)
            )
            outcome.update(status="error", timed_out=timed_out)
            if timed_out:
                # ¿ADOMD conserva la conexión tras cancelar por CommandTimeout?
                # No se pudo comprobar con Power BI real: se registra para el
                # diagnóstico (si se pierde, la siguiente consulta la reabre
                # y podría pedir inicio de sesión interactivo).
                STATS.powerbi_timeout_connection(model, kept)
            if started is not None:
                timing["exec_s"] = round(time.perf_counter() - started, 3)
            elif connection is None:
                # Falló al abrir la conexión: todo el tiempo fue de la apertura.
                timing["connect_s"] = round(
                    max(0.0, time.perf_counter() - requested - timing["wait_s"]), 3
                )
            return {
                **timing,
                "status":
                    "error",
                "semantic_model":
                    model,
                "error_type":
                    type(error).__name__,
                "error":
                    str(error),
                "timed_out":
                    timed_out,
                "connection_kept":
                    kept,
            }

        finally:

            STATS.powerbi_query_end(
                model, outcome["status"], outcome["timed_out"]
            )

            if reader is not None:

                try:
                    reader.Close()
                except Exception:
                    pass

                try:
                    reader.Dispose()
                except Exception:
                    pass

            if command is not None:

                try:
                    command.Dispose()
                except Exception:
                    pass

    def execute_validated(
        self,
        validation_result,
        semantic_model=None,
    ):

        if not validation_result.get(
            "valid",
            False,
        ):
            return {
                "status":
                    "rejected",
                "reason":
                    "dax_not_validated",
                "errors":
                    validation_result.get(
                        "errors",
                        [],
                    ),
            }

        dax = validation_result.get(
            "dax"
        )

        if not dax:
            return {
                "status":
                    "rejected",
                "reason":
                    "missing_dax",
            }

        return self.execute_dax(
            dax=dax,
            semantic_model=
                semantic_model,
        )

    # ========================================================
    # CIERRE / DIAGNÓSTICO
    # ========================================================

    def close(
        self
    ):

        with self._connection_lock:

            keys = list(
                self._connections.keys()
            )

            for key in keys:

                semantic_model = (
                    None
                    if key
                    == "__workspace__"
                    else key
                )

                self._invalidate_connection(
                    semantic_model
                )

    def connection_count(
        self
    ):

        return sum(
            1
            for connection
            in self._connections.values()
            if self._is_connection_open(
                connection
            )
        )
