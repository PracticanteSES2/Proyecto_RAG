from pathlib import Path
import json

from src.providers.powerbi_provider import PowerBIProvider
from src.semantic.source_model_router import SourceModelRouter
from src.semantic.query_plan_builder import QueryPlanBuilder
from src.dax.query_plan_dax_generator import QueryPlanDAXGenerator

PROJECT_ROOT = Path(__file__).resolve().parent
MASTER = PROJECT_ROOT / 'data' / 'rag' / 'master_metrics.json'
VISUAL = PROJECT_ROOT / 'data' / 'rag' / 'visual_metrics_catalog.json'
REGISTRY = PROJECT_ROOT / 'data' / 'catalog' / 'source_registry.json'

QUESTIONS = [
    '¿Cuántos egresos probables hay en el Briefing Hospitalario?',
    '¿Cuántos egresos probables hay por servicio en el Briefing Hospitalario?',
    '¿Cuál es la capacidad instalada en el Tablero de Atenciones Institucionales?',
]


def main():
    provider = PowerBIProvider()
    router = SourceModelRouter(
        source_registry_path=REGISTRY,
        visual_catalog_path=VISUAL,
        project_root=PROJECT_ROOT,
        default_semantic_model=provider.default_semantic_model,
    )
    builder = QueryPlanBuilder(
        master_metrics_path=MASTER,
        visual_catalog_path=VISUAL,
        source_router=router,
        powerbi_provider=provider,
        project_root=PROJECT_ROOT,
    )
    generator = QueryPlanDAXGenerator()

    for question in QUESTIONS:
        print('\n' + '=' * 72)
        print('PREGUNTA:', question)
        plan = builder.build(question)
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        if plan.get('status') == 'ready':
            print('\nDAX:')
            print(generator.generate(plan).get('dax'))

    provider.close()


if __name__ == '__main__':
    main()
