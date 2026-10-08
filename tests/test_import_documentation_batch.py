import import_documentation_batch as module


def main():
    assert module.folder_name_candidates(
        "3 DOCUMENTACION TABLERO BRIEFING HOSPITALARIO"
    ) == [
        "TABLERO BRIEFING HOSPITALARIO",
        "BRIEFING HOSPITALARIO",
    ]

    models = [
        {
            "semantic_model": "BRIEFING HOSPITALARIO",
            "semantic_model_key": "briefing_hospitalario",
            "metadata_path": "data/model_metadata/briefing_hospitalario",
            "status": "success",
        },
        {
            "semantic_model": "TABLERO DE ATENCIONES INSTITUCIONALES",
            "semantic_model_key": "tablero_de_atenciones_institucionales",
            "metadata_path": "data/model_metadata/tablero_de_atenciones_institucionales",
            "status": "success",
        },
        {
            "semantic_model": "ASIGNACION DE CITAS",
            "semantic_model_key": "asignacion_de_citas",
            "metadata_path": "data/model_metadata/asignacion_de_citas",
            "status": "success",
        },
    ]

    briefing = module.match_model(
        module.folder_name_candidates(
            "3 DOCUMENTACION TABLERO BRIEFING HOSPITALARIO"
        ),
        models,
    )
    assert briefing["status"] == "matched"
    assert briefing["best"]["semantic_model"] == "BRIEFING HOSPITALARIO"

    atenciones = module.match_model(
        module.folder_name_candidates(
            "5 DOCUMENTACION TABLERO DE ATENCIONES INSTITUCIONALES"
        ),
        models,
    )
    assert atenciones["status"] == "matched"
    assert (
        atenciones["best"]["semantic_model"]
        == "TABLERO DE ATENCIONES INSTITUCIONALES"
    )

    citas = module.match_model(
        module.folder_name_candidates(
            "2 DOCUMENTACION TABLERO ASIGNACION DE CITAS"
        ),
        models,
    )
    assert citas["status"] == "matched"
    assert citas["best"]["semantic_model"] == "ASIGNACION DE CITAS"

    assert (
        module.source_group_from_report("BRIEFING HOSPITALARIO")
        == "tablero_briefing_hospitalario"
    )

    assert (
        module.source_group_from_report(
            "TABLERO DE ATENCIONES INSTITUCIONALES"
        )
        == "tablero_de_atenciones_institucionales"
    )

    print("PRUEBA IMPORTADOR DOCUMENTAL: OK")


if __name__ == "__main__":
    main()
