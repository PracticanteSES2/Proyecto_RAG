"""Pruebas offline del pipeline de ingesta y catalogos.

Ejecutar:  python -m tests.pipeline.test_pipeline
(compatible con pytest). Con DOCS_DIR apuntando a la carpeta Documentacion se
ejecuta ademas la prueba agregada sobre los .docx reales.
"""
import json
import os
import sys
import tempfile
import traceback
import types
from pathlib import Path

from tests.pipeline.helpers import PROJECT_ROOT, import_document_parser  # noqa: F401
from tests.pipeline.docx_xml import read_blocks

from src.semantic import document_normalizer as norm


def P(text, style="Normal"):
    return {"type": "paragraph", "text": text, "style": style}


def T(*rows):
    return {"type": "table", "rows": [list(r) for r in rows]}


# ------------------------------------------------------------
# 1. Normalizador
# ------------------------------------------------------------

def test_normalizer_sql_measures_visuals():
    blocks = [
        P("Este tablero monitorea la lavanderia."),
        P("PARA CREAR ESTE TABLERO SE UTILIZA LA SIGUIENTE CONSULTA"),
        P("SELECT A.OID,"),
        P("A.Peso,"),
        P("FROM PLANILLAUSUARIO.DBO.Cp_PesajeLavanderia A"),
        P("LEFT JOIN PLANILLAUSUARIO.DBO.Cp_Medicion C ON A.OidCpMedicion=C.Oid"),
        P("WHERE"),
        P("MEDIDAS CALCULADAS PARA ESTE TABLERO"),
        T(["TABLA", "NOMBRE MEDIDA", "DAX"],
          ["LAVANDERIA", "NOMBRE_COMPLETO", "NOMBRE_COMPLETO = CONCATENATE(L[a],L[b])"]),
        P("DESCRIPCIONES DE LAS VISUALIZACIONES"),
        P("Filtros por Años y Mes"),
        P("Permiten segmentar la información."),
        P("Tabla de Participación por Servicio"),
        P("Muestra la distribución de pesos."),
    ]
    out = norm.normalize_dashboard({"name": "X", "blocks": blocks})

    assert len(out["sql_queries"]) == 1, out["sql_queries"]
    sql = out["sql_queries"][0]
    assert "SELECT A.OID" in sql and "LEFT JOIN" in sql and sql.rstrip().endswith("WHERE")

    assert len(out["documented_measures"]) == 1
    measure = out["documented_measures"][0]
    assert measure["name"] == "NOMBRE_COMPLETO"
    assert measure["expression"].startswith("CONCATENATE("), measure["expression"]

    assert out["visuals"] == [
        "Filtros por Años y Mes: Permiten segmentar la información.",
        "Tabla de Participación por Servicio: Muestra la distribución de pesos.",
    ], out["visuals"]
    assert out["description"].startswith("Este tablero")
    assert not out["other_sections"]


def test_normalizer_heading_variants_and_typos():
    for heading in (
        "CONSUTA UTILIZADA PARA REALIZAR ESTE TABLERO",
        "Para realizar el tablero se utilizó la siguiente consulta",
        "Para realizar este tablero se utilizó la siguiente consulta:",
        "PARA CREAR ESTE TABLERO SE UTILIZARON LAS SIGUIENTES CONSULTAS",
    ):
        assert norm.detect_section(heading) == "sql", heading

    for heading in (
        "MEDIDAS CREADAS EN ESTE TABLERO",
        "MEDIDAS CALCULADAS PARA ESTE TABLERO",
        "Medidas utilizadas en este tablero",
        "PARA CREAR ESTE TABLERO SE UTILIZARON LAS SIGUIENTES MEDIDAS",
    ):
        assert norm.detect_section(heading) == "measures", heading

    assert norm.detect_section("COLUMNAS CACULADAS PARA ESTE TABLERO") == "calculated_columns"
    assert norm.detect_section("DESCIPCION DE VISUALIZACIONES") == "visuals"
    assert norm.detect_section("DESCRIPCIONES DE LAS VISUALIZACIONES") == "visuals"

    # SQL en mayusculas NUNCA es encabezado.
    for line in (
        "SELECT",
        "CASE",
        "FROM DIM_TRIAGE",
        "WHEN DIM_X.HCCODIGO = 'V-G' THEN 'CONSULTA EXTERNA OBSTETRICA'",
        "ELSE 'NO'",
        "ROW_NUMBER() OVER (",
    ):
        assert norm.detect_section(line) is None, line
        assert not norm.is_heading({"type": "paragraph", "text": line, "style": "Normal"})


def test_normalizer_text_measures_and_unrecognized_text_kept():
    blocks = [
        P("Descripcion corta."),
        P("MEDIDAS UTILIZADAS EN ESTE TABLERO"),
        P("%OCUPACION ="),
        P("DIVIDE(SUM(T[a]), SUM(T[b]))"),
        P("Total = SUM(T[x])"),
        P("Medida: TotalN"),
        P("COUNTROWS(T)"),
        P("Seccion Rara", style="Heading 2"),
        P("Texto que no debe perderse."),
    ]
    out = norm.normalize_dashboard({"name": "X", "blocks": blocks})
    names = [m["name"] for m in out["documented_measures"]]
    assert names == ["%OCUPACION", "Total", "TotalN"], names
    assert out["documented_measures"][0]["expression"] == "DIVIDE(SUM(T[a]), SUM(T[b]))"
    assert out["documented_measures"][2]["expression"] == "COUNTROWS(T)"
    assert any(
        "no debe perderse" in (s.get("text") or "") for s in out["other_sections"]
    )


def test_normalizer_title_description_then_expression_layout():
    # Formato de la documentación de Antibióticos:
    #   Nombre / descripción / 'Nombre =' / DAX (multilínea)
    # Antes el título y la descripción de la medida siguiente quedaban pegados
    # al DAX de la anterior y la descripción se perdía.
    blocks = [
        P("MEDIDAS USADAS PARA ESTE TABLERO"),
        P("Fecha Inicio"),
        P("Primera fecha registrada de aplicación del antibiótico."),
        P("Fecha Inicio ="),
        P("MIN( ANTIBIOTICOS[HORA_APLICACION])"),
        P("Días Suministrados"),
        P("Número de aplicaciones registradas en el periodo filtrado."),
        P("Dias Suministrados ="),
        P("DISTINCTCOUNT( ANTIBIOTICOS[HORA_APLICACION] )"),
        P("PAC_ACT"),
        P("Número de pacientes únicos con tratamiento activo."),
        P("PAC_ACT ="),
        P("CALCULATE("),
        P("DISTINCTCOUNT(ANTIBIOTICOS[DOCUMENTO]),"),
        P('ANTIBIOTICOS[Suspension] = "ACTIVO"'),
        P(")"),
    ]
    out = norm.normalize_dashboard({"name": "X", "blocks": blocks})
    measures = out["documented_measures"]
    assert [m["name"] for m in measures] == [
        "Fecha Inicio", "Dias Suministrados", "PAC_ACT",
    ], measures
    assert measures[0]["expression"] == "MIN( ANTIBIOTICOS[HORA_APLICACION])", measures[0]
    assert measures[1]["expression"] == "DISTINCTCOUNT( ANTIBIOTICOS[HORA_APLICACION] )"
    assert measures[2]["expression"].startswith("CALCULATE(")
    assert measures[2]["expression"].rstrip().endswith(")")
    assert "Número de pacientes" not in measures[1]["expression"]
    assert measures[0]["description"].startswith("Primera fecha"), measures[0]
    assert measures[2]["description"].startswith("Número de pacientes"), measures[2]
    assert not out["other_sections"], out["other_sections"]


def test_normalizer_sql_stops_at_next_heading_and_column_tables():
    blocks = [
        P("CONSULTA UTILIZADA PARA CREAR ESTE TABLERO"),
        P("SELECT 1"),
        P("COLUMNAS CALCULADAS IMPLEMENTADAS"),
        T(["TABLA", "NOMBRE COLUMNA", "DAX"], ["T", "C1", "C1 = IF(1=1,1,0)"]),
    ]
    out = norm.normalize_dashboard({"name": "X", "blocks": blocks})
    assert out["sql_queries"] == ["SELECT 1"]
    assert out["calculated_columns"][0]["name"] == "C1"
    assert out["calculated_columns"][0]["expression"] == "IF(1=1,1,0)"


# ------------------------------------------------------------
# 2. Parser
# ------------------------------------------------------------

def test_parser_names_lock_files_and_model():
    dp = import_document_parser()

    assert dp.extract_dashboard_name("DOCUMENTACIÓN TABLERO DE FACTURADORES") == "FACTURADORES"
    assert dp.extract_dashboard_name("DOCUMENTACION TABLERO DE CONSULTAS POR ESPECIALIDAD") == "CONSULTAS POR ESPECIALIDAD"
    assert dp.extract_dashboard_name("DOCUMENTACIÓN – TABLERO DEL RESUMEN") == "RESUMEN"
    assert dp.extract_dashboard_name("DOCUMENTACIÓN TABLERO DETALLE") == "DETALLE"

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        raw = tmp / "data" / "raw"
        group = raw / "39 DOCUMENTACION TABLERO LAVANDERIA"
        group.mkdir(parents=True)
        (group / "~$lock.docx").write_bytes(b"x")
        stats = dp.process_all_documents(raw, tmp / "out")
        assert stats["documents_found"] == 0 and not stats["errors"]

        # El env var ya no agrupa documentos sin manifest.
        os.environ["POWERBI_SEMANTIC_MODEL"] = "MODELO_ENV"
        try:
            doc = group / "doc.docx"
            doc.write_bytes(b"x")
            cfg = dp.resolve_document_config(doc, raw)
            assert cfg["semantic_model"] is None, cfg

            catalog = tmp / "data" / "catalog"
            catalog.mkdir(parents=True)
            (catalog / "source_registry.json").write_text(json.dumps({
                "sources": [{
                    "source_group": "39 DOCUMENTACION TABLERO LAVANDERIA",
                    "semantic_model": "Lavanderia",
                    "semantic_model_key": "lavanderia",
                }]
            }), encoding="utf-8")
            cfg = dp.resolve_document_config(doc, raw)
            assert cfg["semantic_model"] == "Lavanderia"
            assert cfg["semantic_model_key"] == "lavanderia"
        finally:
            os.environ.pop("POWERBI_SEMANTIC_MODEL", None)

    dashboards = [{"name": "LAVADERIA", "aliases": [], "blocks": []}]
    fake = Path("/x/39 DOCUMENTACION TABLERO LAVANDERIA/1 Doc.docx")
    dp.add_folder_aliases(dashboards, fake)
    assert "LAVANDERIA" in dashboards[0]["aliases"], dashboards


# ------------------------------------------------------------
# 3. Consola
# ------------------------------------------------------------

def test_console_utf8_reconfigure():
    import io
    dp = import_document_parser()
    old = sys.stdout
    buf = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")
    sys.stdout = buf
    try:
        dp.configure_console_utf8()
        print("✓ ✗ ok")  # no debe lanzar UnicodeEncodeError
        sys.stdout.flush()
    finally:
        sys.stdout = old


# ------------------------------------------------------------
# 4/5/8. Catalogos
# ------------------------------------------------------------

def _write_measures_csv(folder, text, encoding="utf-8-sig"):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "measures.csv").write_bytes(text.encode(encoding))


def test_csv_readers_delimiters_and_latin1():
    from src.semantic.visual_catalog_builder import read_csv_rows

    with tempfile.TemporaryDirectory() as tmp:
        for delim in (",", ";", "\t"):
            path = Path(tmp) / f"a{ord(delim)}.csv"
            path.write_text(f"Name{delim}Table{delim}IsHidden\nM1{delim}T{delim}True\n", encoding="utf-8-sig")
            rows = read_csv_rows(path)
            assert rows == [{"Name": "M1", "Table": "T", "IsHidden": "True"}], (delim, rows)

        path = Path(tmp) / "l1.csv"
        path.write_bytes("Name;Table\nOcupación;T\n".encode("latin-1"))
        assert read_csv_rows(path)[0]["Name"] == "Ocupación"


def _vm(model, group, report, **kw):
    base = {
        "semantic_model": model, "source_group": group, "report": report,
        "page_name": "p1", "page_display_name": "Inicio",
        "visual_id": "v1", "visual_title": None, "visual_type": "card",
        "role": "Values", "query_ref": "q", "validation_status": "approved",
    }
    base.update(kw)
    return base


def test_master_metrics_hidden_escape_labels_and_all_models():
    from src.semantic.global_master_metric_builder import build_global_master_metrics

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _write_measures_csv(
            tmp / "m1",
            "Name;Table;Expression;IsHidden\n"
            "Visible;T;SUM(T[x]);False\n"
            "Helper;T;SUM(T[y]);True\n"
            "UsedHidden;T;SUM(T[z]);True\n"
            "Raro];T;1;False\n",
            encoding="latin-1",
        )
        _write_measures_csv(tmp / "m2", "Name,Table,Expression,IsHidden\nOtra,U,1,False\n")

        catalog = {"metrics": [
            _vm("M1", "g1", "R1", kind="measure", table="T", measure="UsedHidden"),
            _vm("M1", "g1", "R1", kind="aggregation", table="T", column="Peso",
                aggregation="Sum", native_query_ref="Sum(T.Peso)", dax_expression="SUM(T[Peso])",
                visual_title=None),
            _vm("M1", "g1", "R1", kind="aggregation", table="T", column="Peso",
                aggregation="Sum", native_query_ref="Sum(T.Peso)", dax_expression="SUM(T[Peso])",
                visual_title="Peso total", page_display_name="Detalle"),
        ]}
        lookup = {
            "M1": {"metadata_path": str(tmp / "m1")},
            "M2": {"metadata_path": str(tmp / "m2")},  # sin PBIR reconstruido
        }
        out = build_global_master_metrics(
            visual_catalog=catalog,
            model_lookup=lookup,
            output_path=tmp / "master.json",
            rebuilt_semantic_models={"M1"},
            rebuilt_source_groups={"g1"},
        )
        by_measure = {m["measure"]: m for m in out["metrics"] if m["source_type"] == "explicit_measure"}
        assert by_measure["Visible"]["validation_status"] == "approved"
        assert by_measure["Helper"]["validation_status"] == "hidden"
        assert by_measure["UsedHidden"]["validation_status"] == "approved"
        assert by_measure["UsedHidden"]["appearances"]
        assert by_measure["Raro]"]["dax_expression"] == "[Raro]]]", by_measure["Raro]"]["dax_expression"]
        assert "Otra" in by_measure, "modelo con metadata sin PBIR reconstruido debe emitir medidas"

        aggs = [m for m in out["metrics"] if m["source_type"] == "visual_aggregation"]
        labels = sorted(m["label"] for m in aggs)
        assert labels == ["Peso total", "Suma de Peso"], labels
        friendly = next(m for m in aggs if m["label"] == "Suma de Peso")
        assert friendly["appearances"][0]["page_display_name"] == "Inicio"
        titled = next(m for m in aggs if m["label"] == "Peso total")
        assert titled["appearances"][0]["visual_title"] == "Peso total"
        assert "Suma de Peso" in titled["aliases"]


def test_global_visual_catalog_rebuild_per_source_group():
    from src.semantic.powerbi_catalog_manager import PowerBICatalogManager

    with tempfile.TemporaryDirectory() as tmp:
        manager = PowerBICatalogManager(project_root=tmp)
        existing = {
            "schema_version": 2,
            "reports": [
                {"source_group": "g1", "report": "A", "semantic_model": "M", "metrics": [{"id": 1}], "stats": {}},
                {"source_group": "g2", "report": "B", "semantic_model": "M", "metrics": [{"id": 2}], "stats": {}},
            ],
        }
        manager.global_visual_catalog_path.parent.mkdir(parents=True, exist_ok=True)
        manager.global_visual_catalog_path.write_text(json.dumps(existing), encoding="utf-8")

        new = [{"source_group": "g1", "report": "A", "semantic_model": "M", "metrics": [{"id": 10}], "stats": {}}]
        result = manager.build_global_visual_catalog(new, {"M"})
        groups = sorted(r["source_group"] for r in result["reports"])
        assert groups == ["g1", "g2"], groups
        assert sorted(m["id"] for m in result["metrics"]) == [2, 10]


def test_find_pbir_directories_excludes_noise():
    from src.semantic.powerbi_catalog_manager import PowerBICatalogManager

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for rel in (
            "data/pbir/Reporte.Report",
            "Documentacion/Copia/Reporte.Report",
            "graphify-out/x/Reporte.Report",
            "tests/fixtures/Reporte.Report",
            ".git/foo/Reporte.Report",
            "otra/carpeta/Real.Report",
        ):
            (tmp / rel).mkdir(parents=True)

        manager = PowerBICatalogManager(project_root=tmp)
        found = sorted(
            str(p.relative_to(tmp.resolve())).replace("\\", "/")
            for p in manager._find_pbir_directories()
        )
        assert found == ["data/pbir/Reporte.Report", "otra/carpeta/Real.Report"], found


# ------------------------------------------------------------
# 7. Indexador y chunks
# ------------------------------------------------------------

def _import_indexer():
    for name in ("sentence_transformers", "qdrant_client", "qdrant_client.models"):
        if name not in sys.modules:
            try:
                __import__(name)
            except Exception:
                sys.modules[name] = types.ModuleType(name)
    st = sys.modules["sentence_transformers"]
    if not hasattr(st, "SentenceTransformer"):
        st.SentenceTransformer = object
    qc = sys.modules["qdrant_client"]
    if not hasattr(qc, "QdrantClient"):
        qc.QdrantClient = object
    models = sys.modules["qdrant_client.models"]
    for attr in ("Distance", "FieldCondition", "Filter", "FilterSelector",
                 "MatchValue", "PointStruct", "VectorParams"):
        if not hasattr(models, attr):
            setattr(models, attr, object)
    from src.rag import embedding_indexer
    return embedding_indexer


def test_indexer_stale_groups_and_scroll():
    indexer = _import_indexer()
    assert indexer.stale_source_groups({"a", "b", "c"}, ["a", "c"]) == ["b"]
    assert indexer.stale_source_groups({"a"}, ["a", "z"]) == []

    class Point:
        def __init__(self, group):
            self.payload = {"source_group": group}

    class FakeClient:
        def __init__(self):
            self.pages = [([Point("a"), Point("b")], "next"), ([Point("b"), Point("c")], None)]

        def scroll(self, **kwargs):
            return self.pages.pop(0)

    assert indexer._existing_source_groups(FakeClient(), "col") == {"a", "b", "c"}


def test_chunks_overview_short_and_sql_measure_chunks():
    from src.rag import chunk_builder

    dashboard = {
        "name": "LAVADERIA",
        "aliases": ["LAVANDERIA"],
        "description": ("Este tablero monitorea la gestion. " * 40).strip(),
        "filters": ["Filtro de anio"] * 5,
        "visuals": ["Tabla: algo"] * 30,
        "sql_queries": ["SELECT " + ", ".join(f"A.col{i}" for i in range(200)) + " FROM T A"],
        "unmatched_documented_measures": [{"name": "M", "table": "T", "expression": "SUM(T[x])"}],
        "source_group": "g",
        "source_file": "f.docx",
    }
    overview = chunk_builder.build_dashboard_chunk(dashboard)
    assert len(overview["text"]) <= 420, len(overview["text"])
    assert "Visualizaciones" not in overview["text"]

    sql_chunks = chunk_builder.build_sql_chunks(dashboard)
    assert len(sql_chunks) > 1
    assert all(c["chunk_type"] == "sql_query" and len(c["text"]) <= 520 for c in sql_chunks)
    assert len({c["id"] for c in sql_chunks}) == len(sql_chunks)

    measures = chunk_builder.build_documented_measure_chunks(dashboard)
    assert measures and measures[0]["chunk_type"] == "documented_measure" or measures[0]["chunk_type"]


# ------------------------------------------------------------
# Documentos reales (opcional)
# ------------------------------------------------------------

def test_real_documents_aggregate():
    docs_dir = os.environ.get("DOCS_DIR")
    if not docs_dir or not Path(docs_dir).exists():
        print("  (omitida: DOCS_DIR no definido)")
        return "skipped"

    dp = import_document_parser()
    files = sorted(
        p for p in Path(docs_dir).rglob("*.docx") if not p.name.startswith("~$")
    )
    assert files, "no hay .docx en DOCS_DIR"

    totals = {"dashboards": 0, "sql": 0, "measures": 0, "columns": 0, "visuals": 0, "de_names": 0}
    docs_with_sql = 0

    for path in files:
        blocks = read_blocks(path)
        default = dp.folder_to_display_name(dp.slugify(path.stem))
        dashboards = dp.split_into_dashboards(blocks, path.name, default, [])
        sql_in_doc = 0
        for dashboard in dashboards:
            out = norm.normalize_dashboard(dashboard)
            totals["dashboards"] += 1
            totals["sql"] += len(out["sql_queries"])
            totals["measures"] += len(out["documented_measures"])
            totals["columns"] += len(out["calculated_columns"])
            totals["visuals"] += len(out["visuals"])
            totals["de_names"] += dashboard["name"].upper().startswith("DE ")
            sql_in_doc += len(out["sql_queries"])
        docs_with_sql += sql_in_doc > 0

    print("  agregado:", totals, "docs_con_sql:", docs_with_sql, "de", len(files))
    assert totals["de_names"] == 0
    assert docs_with_sql >= int(len(files) * 0.7), docs_with_sql
    assert totals["measures"] > 0 and totals["columns"] > 0 and totals["visuals"] > 0


# ------------------------------------------------------------
# Runner minimo
# ------------------------------------------------------------

def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, func in tests:
        try:
            func()
            print(f"[PASS] {name}")
        except Exception:
            failed += 1
            print(f"[FAIL] {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
