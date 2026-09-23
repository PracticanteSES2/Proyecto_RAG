import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


class PowerBIProvider:

    def __init__(self, endpoint=None, default_semantic_model=None):

        self.endpoint = endpoint or os.getenv("POWERBI_XMLA_ENDPOINT")
        self.default_semantic_model = (
            default_semantic_model
            or os.getenv("POWERBI_SEMANTIC_MODEL")
        )

        self.adomd_path = os.getenv("ADOMD_PATH")
        self.identity_path = os.getenv("IDENTITY_PATH")

        if not self.endpoint:
            raise ValueError(
                "POWERBI_XMLA_ENDPOINT no está configurado."
            )

        self._connections = {}

        self._load_dotnet_dependencies()


    def _load_dotnet_dependencies(self):

        if not self.adomd_path:
            raise ValueError(
                "ADOMD_PATH no está configurado en .env"
            )

        if not self.identity_path:
            raise ValueError(
                "IDENTITY_PATH no está configurado en .env"
            )

        adomd_dll = (
            Path(self.adomd_path)
            / "Microsoft.AnalysisServices.AdomdClient.dll"
        )

        identity_dll = (
            Path(self.identity_path)
            / "Microsoft.Identity.Client.dll"
        )

        if not adomd_dll.exists():
            raise FileNotFoundError(
                f"No se encontró: {adomd_dll}"
            )

        if not identity_dll.exists():
            raise FileNotFoundError(
                f"No se encontró: {identity_dll}"
            )

        if self.identity_path not in sys.path:
            sys.path.insert(0, self.identity_path)

        if self.adomd_path not in sys.path:
            sys.path.append(self.adomd_path)

        import clr

        clr.AddReference("Microsoft.Identity.Client")
        clr.AddReference(
            "Microsoft.AnalysisServices.AdomdClient"
        )

        from Microsoft.AnalysisServices.AdomdClient import (
            AdomdConnection,
            AdomdRestrictionCollection,
        )

        self.AdomdConnection = AdomdConnection
        self.AdomdRestrictionCollection = (
            AdomdRestrictionCollection
        )


    def _resolve_semantic_model(self, semantic_model=None):

        model = semantic_model or self.default_semantic_model

        if not model:
            raise ValueError(
                "No se indicó un modelo semántico."
            )

        return model


    def _build_connection_string(self, semantic_model=None):

        connection_string = (
            f"Data Source={self.endpoint};"
        )

        if semantic_model:
            connection_string += (
                f"Initial Catalog={semantic_model};"
            )

        connection_string += (
            "Interactive Login=Always;"
            "Identity Mode=Process;"
        )

        return connection_string


    def _connection_key(self, semantic_model=None):

        return (
            semantic_model
            if semantic_model
            else "__workspace__"
        )


    def _is_connection_open(self, connection):

        try:
            return (
                connection is not None
                and connection.State.ToString() == "Open"
            )
        except Exception:
            return False


    def _create_connection(self, semantic_model=None):

        connection = self.AdomdConnection(
            self._build_connection_string(
                semantic_model
            )
        )

        connection.Open()

        return connection


    def _get_connection(self, semantic_model=None):
        """
        Reutiliza una conexión abierta por modelo semántico.
        La primera llamada puede solicitar autenticación.
        Las siguientes reutilizan la misma sesión.
        """

        key = self._connection_key(
            semantic_model
        )

        connection = self._connections.get(
            key
        )

        if self._is_connection_open(connection):
            return connection

        if connection is not None:

            try:
                connection.Close()
            except Exception:
                pass

            try:
                connection.Dispose()
            except Exception:
                pass

            self._connections.pop(
                key,
                None
            )

        connection = self._create_connection(
            semantic_model
        )

        self._connections[key] = connection

        return connection


    def list_semantic_models(self):

        try:

            connection = self._get_connection(
                semantic_model=None
            )

            restrictions = (
                self.AdomdRestrictionCollection()
            )

            dataset = connection.GetSchemaDataSet(
                "DBSCHEMA_CATALOGS",
                restrictions
            )

            table = dataset.Tables[0]

            models = [
                str(row["CATALOG_NAME"])
                for row in table.Rows
            ]

            return {
                "status": "success",
                "models": models,
                "count": len(models),
            }

        except Exception as error:

            return {
                "status": "error",
                "error_type":
                    type(error).__name__,
                "error":
                    str(error),
            }


    def execute_dax(
        self,
        dax,
        semantic_model=None
    ):

        model = self._resolve_semantic_model(
            semantic_model
        )

        reader = None
        command = None

        try:

            connection = self._get_connection(
                model
            )

            command = connection.CreateCommand()
            command.CommandText = dax

            reader = command.ExecuteReader()

            columns = [
                reader.GetName(index)
                for index
                in range(reader.FieldCount)
            ]

            rows = []

            while reader.Read():

                row = {}

                for index, column in enumerate(
                    columns
                ):

                    value = reader.GetValue(
                        index
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
                            )
                        )
                    ):
                        value = str(value)

                    row[column] = value

                rows.append(row)

            return {
                "status": "success",
                "semantic_model": model,
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
            }

        except Exception as error:

            key = self._connection_key(
                model
            )

            stale_connection = (
                self._connections.pop(
                    key,
                    None
                )
            )

            if stale_connection is not None:

                try:
                    stale_connection.Close()
                except Exception:
                    pass

                try:
                    stale_connection.Dispose()
                except Exception:
                    pass

            return {
                "status": "error",
                "semantic_model": model,
                "error_type":
                    type(error).__name__,
                "error":
                    str(error),
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
        semantic_model=None
    ):

        if not validation_result.get(
            "valid",
            False
        ):
            return {
                "status": "rejected",
                "reason":
                    "dax_not_validated",
                "errors":
                    validation_result.get(
                        "errors",
                        []
                    ),
            }

        dax = validation_result.get("dax")

        if not dax:
            return {
                "status": "rejected",
                "reason":
                    "missing_dax",
            }

        return self.execute_dax(
            dax=dax,
            semantic_model=semantic_model,
        )


    def close(self):
        """
        Cierra todas las conexiones persistentes.
        """

        for connection in list(
            self._connections.values()
        ):

            try:
                if (
                    connection is not None
                    and connection.State.ToString()
                    != "Closed"
                ):
                    connection.Close()
            except Exception:
                pass

            try:
                connection.Dispose()
            except Exception:
                pass

        self._connections.clear()


    def connection_count(self):

        return sum(
            1
            for connection
            in self._connections.values()
            if self._is_connection_open(
                connection
            )
        )