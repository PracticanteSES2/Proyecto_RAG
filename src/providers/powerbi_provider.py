import os
import sys
import threading
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


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

    def _create_connection(
        self,
        semantic_model=None,
    ):

        connection = (
            self.AdomdConnection(
                self._build_connection_string(
                    semantic_model
                )
            )
        )

        connection.Open()

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

            if connection is not None:
                self._invalidate_connection(
                    semantic_model
                )

            connection = (
                self._create_connection(
                    semantic_model
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
    ):

        model = (
            self._resolve_semantic_model(
                semantic_model
            )
        )

        reader = None
        command = None
        connection = None

        try:

            # Una sola operación por conexión al mismo tiempo.
            with self._connection_lock:

                connection = (
                    self._get_connection(
                        model
                    )
                )

                command = (
                    connection
                    .CreateCommand()
                )

                command.CommandText = dax

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

                        if (
                            value is not None
                            and not isinstance(
                                value,
                                (
                                    str,
                                    int,
                                    float,
                                    bool,
                                ),
                            )
                        ):
                            value = str(
                                value
                            )

                        row[column] = value

                    rows.append(
                        row
                    )

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

            return {
                "status":
                    "error",
                "semantic_model":
                    model,
                "error_type":
                    type(error).__name__,
                "error":
                    str(error),
                "connection_kept":
                    (
                        connection is not None
                        and self._is_connection_open(
                            connection
                        )
                    ),
            }

        finally:

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
