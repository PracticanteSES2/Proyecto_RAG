"""
Construye, FUERA del repo, dos raíces de datos para comparar la recuperación antes/después del diccionario:

    <destino>/after_root   copia de <checkout principal>/data reindexada con docs_tableros (debe ser no-op)
    <destino>/before_root  la misma copia reindexada con docs_tableros SIN los _diccionario*.md

Usa la función de reindexación del proyecto (src.docs_md.indexacion.reindexar_grupo, incremental).
El data/ original solo se lee.

    python -X utf8 -m tests.eval.indice_sin_diccionario C:/ruta/scratch
    python -X utf8 -m tests.eval.run_diccionario --indice antes=C:/ruta/scratch/before_root --indice despues=C:/ruta/scratch/after_root
    SIM_DATA_ROOT=C:/ruta/scratch/before_root/data python -m tests.eval.run --harness realistic ...   # banco sin diccionario
"""
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        raise SystemExit(__doc__)
    from src.docs_md.indexacion import reindexar_grupo
    from tests.realistic.harness import main_checkout

    destino = Path(argv[0])
    datos = Path(argv[1]) if len(argv) > 1 else main_checkout() / "data"
    md_full = REPO_ROOT / "docs_tableros"
    md_sin = destino / "md_sin_dic"
    if md_sin.exists():
        shutil.rmtree(md_sin)
    shutil.copytree(md_full, md_sin, ignore=lambda d, n: [x for x in n if x.startswith("_diccionario")])
    grupos = sorted(p.name for p in md_full.iterdir() if (p / "md").is_dir())
    informe = {}
    for etiqueta, md in (("after", md_full), ("before", md_sin)):
        raiz = destino / f"{etiqueta}_root"
        if raiz.exists():
            shutil.rmtree(raiz)
        shutil.copytree(datos, raiz / "data", ignore=lambda d, n: [x for x in n if x == ".lock"])
        informe[etiqueta] = {}
        for grupo in grupos:
            r = reindexar_grupo(grupo, project_root=raiz, md_root=md, verbose=False, incremental=True)
            informe[etiqueta][grupo] = {k: r[k] for k in ("documentos", "chunks", "embebidos", "errores")}
            print(etiqueta, grupo, informe[etiqueta][grupo], flush=True)
    (destino / "indices.json").write_text(json.dumps(informe, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
