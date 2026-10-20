"""
Vuelca los hechos de un PBIP (páginas, visuales, tablas, medidas) en JSON, guarda
la instantánea de referencia y compara contra ella.

Uso:
    # imprimir los hechos (o escribirlos en un archivo)
    python -m tools.docs_md.hechos "data/raw/tablero_tiempos_urgencias" [--salida hechos.json]

    # guardar la instantánea en data/raw/<source_group>/pbip_hechos.json
    python -m tools.docs_md.hechos "data/raw/tablero_tiempos_urgencias" --instantanea tablero_tiempos_urgencias

    # qué cambió desde la instantánea (o contra otro JSON de hechos)
    python -m tools.docs_md.hechos "data/raw/tablero_tiempos_urgencias" --comparar tablero_tiempos_urgencias
    python -m tools.docs_md.hechos "data/raw/tablero_tiempos_urgencias" --comparar antes.json

Solo lee los .json del informe y los .tmdl del modelo; nunca .pbi/cache.abf.
"""
import argparse
import json
import sys
from pathlib import Path

from src.docs_md import pbip


def _configurar_salida():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def main(argv=None):
    _configurar_salida()
    parser = argparse.ArgumentParser(description="Hechos de un PBIP en JSON, instantánea y comparación.")
    parser.add_argument("ruta_pbip", help="Carpeta con <Nombre>.Report y <Nombre>.SemanticModel, el .pbip o un .pbix (formato PBIR)")
    parser.add_argument("--salida", help="Archivo JSON donde escribir los hechos")
    parser.add_argument("--instantanea", metavar="SOURCE_GROUP",
                        help="Guarda los hechos como instantánea en data/raw/<source_group>/pbip_hechos.json")
    parser.add_argument("--comparar", metavar="SOURCE_GROUP|ARCHIVO",
                        help="Compara el PBIP actual contra la instantánea del grupo o contra un JSON de hechos")
    parser.add_argument("--raiz", default=None, help="Raíz de los documentos (por defecto data/raw o DOCS_MD_ROOT)")
    args = parser.parse_args(argv)

    hechos = pbip.extraer_hechos(args.ruta_pbip)

    if args.comparar:
        archivo = Path(args.comparar)
        if archivo.suffix.lower() == ".json" and archivo.exists():
            antes = json.loads(archivo.read_text(encoding="utf-8"))
        else:
            antes = pbip.cargar_instantanea(args.comparar, args.raiz)
            if antes is None:
                print(f"No hay instantánea en {pbip.ruta_instantanea(args.comparar, args.raiz)}.")
                return 1
        cambios = pbip.comparar(antes, hechos)
        if not cambios:
            print("Sin cambios.")
        for frase in cambios:
            print("-", frase)

    if args.instantanea:
        ruta = pbip.guardar_instantanea(hechos, args.instantanea, args.raiz)
        print(f"Instantánea guardada en {ruta}")

    if args.salida:
        Path(args.salida).write_text(json.dumps(hechos, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"Hechos escritos en {args.salida}")
    elif not args.comparar and not args.instantanea:
        print(json.dumps(hechos, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
