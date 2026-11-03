"""
Golden master del motor de resolución: corre los tres bancos (simulador, real y holdout) en el
arnés realista con `--llm fake` y compara cada turno con la foto de tests/resolution/golden/foto
(status, ruta, indicador, modelo, filtros, agrupación, DAX normalizado, opciones y respuesta).

    python -X utf8 -m tests.resolution.test_golden            # los tres bancos (~1 h)
    GOLDEN_BANCOS=eval python -X utf8 -m tests.resolution.test_golden
    GOLDEN_SOLO=BH01,H02 python -X utf8 -m tests.resolution.test_golden
    GOLDEN_OMITIR=1 ...                                       # no corre (p. ej. sin data/ real)

Requiere el data/ real (catálogos, Qdrant y embeddings) del checkout principal. La foto se
regenera con `python -X utf8 -m tests.resolution.golden.capture --out tests/resolution/golden/foto`
SOLO cuando un cambio de comportamiento es intencional (y se justifica en el commit).

La fecha importa: periodos relativos («este mes», «mes pasado») y datos del simulador dependen
de hoy. Una foto tomada otro día puede diferir en fechas; para el refactor se toma y se compara
el mismo día.
"""
import os
import sys
import tempfile
import time
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.resolution.golden import capture  # noqa: E402


def test_golden_master():
    if os.getenv("GOLDEN_OMITIR"):
        print("golden master omitido (GOLDEN_OMITIR)")
        return
    try:
        from tests.realistic import harness
        harness.resolve_data_root()
    except Exception as error:  # sin data/ real no hay golden master
        print(f"golden master omitido: {error}")
        return
    bancos = tuple(b.strip() for b in os.getenv("GOLDEN_BANCOS", "eval,real,holdout").split(",") if b.strip())
    solo = {s.strip() for s in os.getenv("GOLDEN_SOLO", "").split(",") if s.strip()}
    expected = capture.load_foto(capture.DEFAULT_FOTO)
    assert expected, f"no hay foto en {capture.DEFAULT_FOTO}"
    started = time.perf_counter()
    actual = capture.capture(bancos, solo, progress=False)
    out = Path(tempfile.gettempdir()) / "golden_ultima_corrida"
    capture.save_foto(actual, out)
    diffs = capture.compare(expected, actual, bancos)
    print(f"golden master: {time.perf_counter() - started:.0f} s · foto {capture.latency_summary(expected)} · "
          f"ahora {capture.latency_summary(actual)} · corrida guardada en {out}")
    for diff in diffs:
        print("DIF", diff)
    assert not diffs, f"{len(diffs)} diferencia(s) con la foto"


if __name__ == "__main__":
    test_golden_master()
    print("OK")
