import tempfile
from pathlib import Path

from sync_powerbi_metadata import (
    MetadataSynchronizer,
    slugify,
    workspace_name_from_endpoint,
)


class FakeProvider:
    endpoint = (
        "powerbi://api.powerbi.com/v1.0/"
        "myorg/Gestion%20Clinica"
    )

    def __init__(self):
        self.queries = []

    def list_semantic_models(self):
        return {
            "status": "success",
            "models": [
                "BRIEFING HOSPITALARIO",
                "TABLERO DE ATENCIONES INSTITUCIONALES",
            ],
            "count": 2,
        }

    def execute_dax(
        self,
        dax,
        semantic_model=None,
    ):
        self.queries.append(
            (semantic_model, dax)
        )

        return {
            "status": "success",
            "columns": [
                "Name",
                "Table",
            ],
            "rows": [
                {
                    "Name": "Demo",
                    "Table": semantic_model,
                }
            ],
            "row_count": 1,
        }

    def close(self):
        pass


def main():
    assert (
        slugify("BRIEFING HOSPITALARIO")
        == "briefing_hospitalario"
    )

    assert (
        workspace_name_from_endpoint(
            FakeProvider.endpoint
        )
        == "Gestion Clinica"
    )

    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        provider = FakeProvider()

        synchronizer = MetadataSynchronizer(
            provider=provider,
            project_root=root,
        )

        registry = synchronizer.sync(
            requested_models=[
                "BRIEFING HOSPITALARIO"
            ],
            force=True,
        )

        model_dir = (
            root
            / "data"
            / "model_metadata"
            / "briefing_hospitalario"
        )

        for filename in [
            "tables.csv",
            "columns.csv",
            "measures.csv",
            "relationships.csv",
        ]:
            assert (
                model_dir / filename
            ).exists()

        assert len(provider.queries) == 4
        assert registry["summary"]["success"] == 1

    print(
        "TODAS LAS PRUEBAS ESTÁTICAS PASARON."
    )


if __name__ == "__main__":
    main()
