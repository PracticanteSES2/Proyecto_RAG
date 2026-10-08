"""Auditoría de interpretación SIN consultar Power BI (por defecto).

Ejecutar desde raíz del proyecto:
    python diagnostico_metricas_v52.py

Opcional, para probar realmente los dominios/valores de un filtro:
    python diagnostico_metricas_v52.py --live

No imprime tokens ni datos sensibles. Solo diagnóstico de nombre de dimensión.
"""
import argparse
import sys
from pathlib import Path
from src.semantic.source_model_router import SourceModelRouter
from src.semantic.query_plan_builder import QueryPlanBuilder

ROOT=Path(__file__).resolve().parent
MASTER=ROOT/'data'/'rag'/'master_metrics.json'
VISUAL=ROOT/'data'/'rag'/'visual_metrics_catalog.json'
REGISTRY=ROOT/'data'/'catalog'/'source_registry.json'

QUESTIONS = [
    '¿Cuántos egresos hay en el Tablero de Atenciones Institucionales?',
    '¿Cuál es el promedio de estancia en el Tablero de Atenciones Institucionales?',
    '¿Cuál es el giro cama en el Tablero de Atenciones Institucionales?',
    '¿Cuál es la capacidad instalada en el Tablero de Atenciones Institucionales?',
    '¿Cuántos egresos probables hay en el Briefing Hospitalario?',
    '¿Cuántos egresos probables hay por servicio en el Briefing Hospitalario?',
]
LIVE_ONLY = [
    '¿Cuántos egresos probables hay por el servicio de urgencias en el Briefing Hospitalario?',
]

class OfflineProvider:
    default_semantic_model = 'TABLERO DE ATENCIONES INSTITUCIONALES'
    def __init__(self): self.calls=[]
    def execute_dax(self,dax,semantic_model=None):
        self.calls.append(semantic_model)
        return {'status':'offline', 'error':'Auditoría sin Power BI: usa --live para validar valores'}


def print_plan(question, plan):
    print('\nPREGUNTA:',question)
    print('status:',plan.get('status'),'stage:',plan.get('stage'),'reason:',plan.get('reason'))
    metric=plan.get('metric') or (plan.get('metric_resolution') or {}).get('metric') or {}
    print('metric:',metric.get('label'),'semantic_model:',plan.get('semantic_model') or metric.get('semantic_model'))
    print('group_by:',[(x.get('table'),x.get('column')) for x in (plan.get('group_by') or [])])
    print('filters:',[(x.get('type'),x.get('table'),x.get('column')) for x in (plan.get('filters') or [])])
    if plan.get('unresolved_text'): print('unresolved_text:',repr(plan['unresolved_text']))
    if plan.get('requested_dimension'): print('requested_dimension:',plan['requested_dimension'])
    if plan.get('requested_value'): print('requested_value:',repr(plan['requested_value']))
    if plan.get('dimension'): print('dimension:',plan['dimension'])
    if plan.get('domain_error'): print('domain_error:',plan['domain_error'])
    if plan.get('status')=='ambiguous':
        print('top_candidates:',[(x.get('metric') or {}).get('label') for x in (plan.get('metric_resolution') or {}).get('candidates',[])[:4]])


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--live',action='store_true',help='Consulta dominios del filtro con la conexión XMLA actual')
    args=parser.parse_args()
    for path in (MASTER,VISUAL,REGISTRY):
        if not path.is_file():
            print('Archivo requerido no encontrado:',path)
            return 2
    provider=OfflineProvider()
    if args.live:
        from src.providers.powerbi_provider import PowerBIProvider
        provider=PowerBIProvider()
    try:
        router=SourceModelRouter(REGISTRY,VISUAL,project_root=ROOT)
        planner=QueryPlanBuilder(MASTER,VISUAL,router,provider,project_root=ROOT)
        for question in QUESTIONS+(LIVE_ONLY if args.live else []):
            result=planner.build(question)
            print_plan(question,result)
        if not args.live:
            print('\nConsultas XMLA realizadas:',len(provider.calls))
            print('En preguntas SIN filtro categórico debe ser cero.')
            if provider.calls:
                print('Modelos consultados inesperadamente:',provider.calls)
        else:
            print('\nNOTA: En live los valores se verifican contra Power BI;')
            print('un fallo XMLA se muestra en domain_error y NO se guarda como dominio vacío.')
    finally:
        if args.live:
            close=getattr(provider,'close',None)
            if callable(close): close()
    return 0

if __name__=='__main__':
    sys.exit(main())
