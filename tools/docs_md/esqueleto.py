"""
Genera los borradores .md (formato estándar) de un tablero a partir de su PBIP:
`_general.md` y un archivo por página. Lo que no se deduce queda «Por confirmar.».

Uso:
    python -m tools.docs_md.esqueleto "data/raw/tablero_tiempos_urgencias" \
        "TABLERO TIEMPOS URGENCIAS" tablero_tiempos_urgencias salida/md [--sobrescribir] [--instantanea]

No sobrescribe archivos existentes salvo con --sobrescribir (la documentación
redactada a mano vale más que el borrador). Con --instantanea también guarda los
hechos del PBIP como referencia para comparar después (tools.docs_md.hechos).
"""
import argparse
import sys
from pathlib import Path

from src.docs_md import formato, pbip


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    parser = argparse.ArgumentParser(description="Borradores .md de un tablero a partir de su PBIP.")
    parser.add_argument("ruta_pbip", help="Carpeta con <Nombre>.Report y <Nombre>.SemanticModel, el .pbip o un .pbix (formato PBIR)")
    parser.add_argument("tablero", help="Nombre del tablero (metadato «tablero»)")
    parser.add_argument("source_group", help="Grupo documental (data/raw/<source_group>)")
    parser.add_argument("salida", help="Carpeta donde escribir los .md")
    parser.add_argument("--sobrescribir", action="store_true", help="Reemplaza archivos existentes")
    parser.add_argument("--instantanea", action="store_true",
                        help="Guarda también la instantánea de hechos del PBIP en data/raw/<source_group>/")
    parser.add_argument("--raiz", default=None, help="Raíz de los documentos para la instantánea")
    args = parser.parse_args(argv)

    archivos = pbip.esqueleto(args.ruta_pbip, args.tablero, args.source_group)
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    escritos, omitidos = 0, 0
    for nombre, texto in archivos.items():
        errores = formato.validar(texto)
        if errores:
            print(f"[!] {nombre}: {' '.join(errores)}")
        destino = salida / nombre
        if destino.exists() and not args.sobrescribir:
            omitidos += 1
            print(f"    {nombre}: ya existe, se omite")
            continue
        destino.write_text(texto, encoding="utf-8", newline="\n")
        escritos += 1
    print(f"{escritos} archivos escritos en {salida} ({omitidos} omitidos).")
    if args.instantanea:
        ruta = pbip.guardar_instantanea(pbip.extraer_hechos(args.ruta_pbip), args.source_group, args.raiz)
        print(f"Instantánea guardada en {ruta}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
