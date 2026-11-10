import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.semantic.powerbi_catalog_manager import (  # noqa: E402
    main,
)


if __name__ == "__main__":
    main()
