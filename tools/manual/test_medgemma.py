# Script manual (no es una prueba automática). Ejecutar desde la raíz:
#   .venv/Scripts/python.exe -X utf8 tools/manual/test_medgemma.py
import sys as _sys
from pathlib import Path as _Path
_RAIZ = str(_Path(__file__).resolve().parents[2])
if _RAIZ not in _sys.path:
    _sys.path.insert(0, _RAIZ)

from src.llm.medgemma_provider import MedGemmaProvider


def main():
    provider = MedGemmaProvider()

    health = provider.healthcheck()
    print("ESTADO MEDGEMMA:")
    print(health)

    if health.get("status") != "ready":
        return

    result = provider.chat(
        messages=[
            {
                "role": "user",
                "content": "Responde brevemente: ¿estás disponible?",
            }
        ],
        temperature=0.1,
        max_tokens=80,
    )

    print("\nRESPUESTA:")
    print(result)


if __name__ == "__main__":
    main()
