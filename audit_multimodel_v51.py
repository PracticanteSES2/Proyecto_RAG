"""Auditoría local sin abrir conexiones ni solicitar autenticación Power BI."""
from collections import Counter
import json
from pathlib import Path

from src.semantic.source_model_router import SourceModelRouter
from src.semantic.query_plan_builder import QueryPlanBuilder

ROOT = Path(__file__).resolve().parent
MASTER = ROOT / 'data/rag/master_metrics.json'
VISUAL = ROOT / 'data/rag/visual_metrics_catalog.json'
REGISTRY = ROOT / 'data/catalog/source_registry.json'

class OfflineProvider:
    default_semantic_model = None
    def execute_dax(self, **kwargs):
        raise AssertionError('Auditoría: no se deben realizar consultas Power BI.')

def load(path):
    if not path.exists():
        raise FileNotFoundError(f'Falta archivo: {path}')
    return json.loads(path.read_text(encoding='utf-8-sig'))

def main():
    master, visual, registry = load(MASTER), load(VISUAL), load(REGISTRY)
    metrics = master.get('metrics',[]) or []
    print('\nMODELOS PRESENTES EN MASTER_METRICS.JSON:')
    for model,count in sorted(Counter(m.get('semantic_model') for m in metrics).items(),key=lambda pair:str(pair[0])):
        approved=sum(1 for m in metrics if m.get('semantic_model')==model and m.get('validation_status')=='approved')
        print(f' - {model}: {count} métricas ({approved} approved)')

    print('\nREPORTES EN VISUAL_METRICS_CATALOG.JSON:')
    reports=visual.get('reports',[]) or []
    if not reports and visual.get('semantic_model'):
        reports=[visual]
    for report in reports:
        pages=report.get('pages',[]) or []
        fields=sum(len(v.get('fields',[]) or []) for page in pages for v in (page.get('visuals',[]) or []))
        print(f" - {report.get('report') or report.get('semantic_model')} => model={report.get('semantic_model')}, pages={len(pages)}, campos visuales={fields}")
    if not reports:
        print(' ! NO HAY REPORTES VISUALES: revisa build_powerbi_catalogs.py')

    print('\nFUENTES SOURCE_REGISTRY:')
    for source in (registry.get('sources',[]) or []):
        print(f" - {source.get('source_group')} => {source.get('semantic_model')} | PBIR={source.get('pbir_path')} | estado={source.get('status')}")

    router = SourceModelRouter(REGISTRY,VISUAL,project_root=ROOT)
    planner = QueryPlanBuilder(MASTER,VISUAL,router,OfflineProvider(),project_root=ROOT)
    questions = [
        '¿Cuántos egresos hay en el Tablero de Atenciones Institucionales?',
        '¿Cuál es el promedio de estancia en el Tablero de Atenciones Institucionales?',
        '¿Cuál es la capacidad instalada en el Tablero de Atenciones Institucionales?',
        '¿Cuál es el giro cama en el Tablero de Atenciones Institucionales?',
        '¿Cuántos egresos probables hay en el Briefing Hospitalario?',
    ]
    print('\nPRUEBAS DE RESOLUCIÓN LOCAL — SIN POWER BI:')
    for question in questions:
        ctx=router.resolve(question=question)
        result=planner._resolve_metric(question,ctx)
        chosen=result.get('metric') or {}
        print(f" - {question}\n   Contexto: {ctx.get('semantic_model')} [{ctx.get('routing_strength')}]\n   Resultado: {result.get('status')} | métrica={chosen.get('label')} | modelo={chosen.get('semantic_model')}")
        if result.get('status') != 'resolved':
            top=result.get('candidates',[])[:4]
            print('   Alternativas:',[(x.get('metric',{}).get('label'),x.get('score')) for x in top])
    print('\nAUDITORÍA FINALIZADA. No se abrió ninguna conexión Power BI.')

if __name__ == '__main__':
    main()
