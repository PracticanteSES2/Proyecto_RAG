from pathlib import Path

from src.semantic.certified_metric_resolver import (
    CertifiedMetricResolver
)

from src.dax.certified_dax_generator import (
    CertifiedDAXGenerator
)


PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)

REGISTRY_PATH = (
    PROJECT_ROOT
    / "data"
    / "catalog"
    / "certified_metrics.json"
)


resolver = CertifiedMetricResolver(
    REGISTRY_PATH
)

result = resolver.resolve(
    "¿Cuántos pacientes observados "
    "hubieron en julio del 2025?"
)

print(
    "\nMÉTRICA CERTIFICADA:"
)

print(result)


generator = CertifiedDAXGenerator()

filter_result = {
    "status": "resolved",
    "filters": [
        {
            "table": "Calendario",
            "column": "AÑO",
            "operator": "=",
            "value": 2025,
        },
        {
            "table": "Calendario",
            "column": "MES",
            "operator": "=",
            "value": 7,
        },
    ],
}


dax = generator.generate(
    metric_result=result,
    filter_result=filter_result,
)

print(
    "\nDAX:"
)

print(
    dax.get("dax")
)
