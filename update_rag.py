"""
Actualización completa del RAG en un solo comando.

Ejecuta, en orden y deteniéndose en el primer error:

  1. import_documentation_batch.py  Normaliza e importa la documentación a data/raw.
  2. sync_powerbi_metadata.py       Sincroniza la metadata de los tableros (XMLA).
  3. build_powerbi_catalogs.py      Construye los catálogos de cada tablero.
  4. ingest_rag.py                  Procesa, genera chunks y actualiza Qdrant.

Paso opcional (tras los catálogos; si falla, avisa y sigue):
     sync_powerbi_links.py          Enlaces «Abrir en Power BI» (solo GET).
                                    Se omite con --skip-links.

Ejemplos:
  python update_rag.py "C:/ruta/Documentacion"
  python update_rag.py "C:/ruta/Documentacion" --force-sync
  python update_rag.py --skip-import --skip-sync        # solo catálogos + ingesta
  python update_rag.py --only-source tablero_briefing_hospitalario
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent


def run_step(label, script, args, dry_run, optional=False):
    command = [sys.executable, "-X", "utf8", str(PROJECT_ROOT / script), *args]
    print("\n" + "=" * 60)
    print(label)
    print("$", " ".join(command[3:]))
    print("=" * 60, flush=True)

    if dry_run:
        return

    started = time.time()
    result = subprocess.run(command, cwd=PROJECT_ROOT)

    if result.returncode != 0 and optional:
        print(
            f"\nAVISO: {label} falló (código {result.returncode}); es opcional, "
            "se continúa con la actualización.",
            flush=True,
        )
        return

    if result.returncode != 0:
        raise SystemExit(
            f"\nFALLÓ: {label} (código {result.returncode}). "
            "Se detuvo la actualización; corrige el error y vuelve a ejecutar."
        )

    print(f"\nOK: {label} ({time.time() - started:.0f} s)", flush=True)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Actualiza el RAG: importa documentación, sincroniza "
                    "metadata, crea catálogos e indexa en Qdrant."
    )
    parser.add_argument(
        "source_dir",
        nargs="?",
        help="Carpeta con las carpetas 'N DOCUMENTACION TABLERO ...'. "
             "Obligatoria salvo con --skip-import.",
    )

    skips = parser.add_argument_group("pasos a omitir")
    skips.add_argument("--skip-import", action="store_true",
                       help="No importa documentación (paso 1).")
    skips.add_argument("--skip-sync", action="store_true",
                       help="No sincroniza metadata de Power BI (paso 2).")
    skips.add_argument("--skip-catalogs", action="store_true",
                       help="No construye catálogos (paso 3).")
    skips.add_argument("--skip-ingest", action="store_true",
                       help="No ejecuta la ingesta (paso 4).")
    skips.add_argument("--skip-links", action="store_true",
                       help="No sincroniza los enlaces «Abrir en Power BI» (opcional).")

    parser.add_argument("--dry-run", action="store_true",
                        help="Solo muestra los comandos que se ejecutarían.")

    imp = parser.add_argument_group("importación")
    imp.add_argument("--move", action="store_true",
                     help="Mueve los archivos en vez de copiarlos.")
    imp.add_argument("--overwrite-files", action="store_true",
                     help="Sobrescribe documentos ya existentes en data/raw.")
    imp.add_argument("--include-extra-files", action="store_true",
                     help="Copia también PDF/TXT/MD/XLS/XLSX/CSV.")

    sync = parser.add_argument_group("sincronización")
    sync.add_argument("--model", action="append", default=[],
                      help="Sincroniza solo este modelo semántico (repetible).")
    sync.add_argument("--force-sync", action="store_true",
                      help="Regenera los CSV de metadata aunque existan.")
    sync.add_argument("--fail-fast", action="store_true",
                      help="Detiene la sincronización al primer modelo con error.")

    parser.add_argument("--only-source",
                        help="Construye catálogos solo de este source_group.")

    ing = parser.add_argument_group("ingesta")
    ing.add_argument("--no-clean-derived", action="store_true",
                     help="No limpia data/processed ni data/semantic_documents.")
    ing.add_argument("--skip-index", action="store_true",
                     help="Genera chunks pero no modifica Qdrant.")

    return parser


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = build_parser()
    args = parser.parse_args()

    if not args.skip_import and not args.source_dir:
        parser.error("indica la carpeta de documentación o usa --skip-import.")

    if args.skip_import and args.source_dir:
        print("Aviso: --skip-import activo; se ignora source_dir.")

    started = time.time()

    if not args.skip_import:
        import_args = [args.source_dir]
        if args.move:
            import_args.append("--move")
        if args.overwrite_files:
            import_args.append("--overwrite-files")
        if args.include_extra_files:
            import_args.append("--include-extra-files")
        run_step("[1/4] Importar y normalizar documentación",
                 "import_documentation_batch.py", import_args, args.dry_run)

    if not args.skip_sync:
        sync_args = []
        for model in args.model:
            sync_args += ["--model", model]
        if args.force_sync:
            sync_args.append("--force")
        if args.fail_fast:
            sync_args.append("--fail-fast")
        run_step("[2/4] Sincronizar metadata de Power BI",
                 "sync_powerbi_metadata.py", sync_args, args.dry_run)

    if not args.skip_catalogs:
        catalog_args = ["--source", args.only_source] if args.only_source else []
        run_step("[3/4] Construir catálogos de los tableros",
                 "build_powerbi_catalogs.py", catalog_args, args.dry_run)

    if not args.skip_links:
        try:
            run_step("[opcional] Enlaces «Abrir en Power BI» (solo lectura)",
                     "sync_powerbi_links.py", [], args.dry_run, optional=True)
        except Exception as error:  # nunca detiene la actualización
            print(f"\nAVISO: no se sincronizaron los enlaces: {error}", flush=True)

    if not args.skip_ingest:
        ingest_args = []
        if args.no_clean_derived:
            ingest_args.append("--no-clean-derived")
        if args.skip_index:
            ingest_args.append("--skip-index")
        run_step("[4/4] Ingesta y actualización de Qdrant",
                 "ingest_rag.py", ingest_args, args.dry_run)

    print(f"\nActualización completa en {time.time() - started:.0f} s.")


if __name__ == "__main__":
    main()
