import json
import tempfile
from pathlib import Path

from src.semantic.query_plan_builder import QueryPlanBuilder
from src.dax.query_plan_dax_generator import QueryPlanDAXGenerator


class FakeRouter:
    def resolve(self, question=None, dashboard=None, semantic_model=None, report=None):
        q = str(question or '').lower()
        if 'briefing hospitalario' in q:
            return {'status':'resolved','routing_strength':'strong','semantic_model':'BRIEFING HOSPITALARIO','report':'BRIEFING HOSPITALARIO'}
        if 'atenciones institucionales' in q:
            return {'status':'resolved','routing_strength':'strong','semantic_model':'TABLERO DE ATENCIONES INSTITUCIONALES','report':'TABLERO DE ATENCIONES INSTITUCIONALES'}
        return {'status':'unresolved','routing_strength':'none'}


class FakeProvider:
    default_semantic_model = 'TABLERO DE ATENCIONES INSTITUCIONALES'
    def execute_dax(self, dax, semantic_model=None):
        if 'DIM_SERVICIO' in dax:
            values = ['URGENCIAS','OBSTETRICIA','CUARTO PISO NORTE']
        elif 'ASEGURADOR' in dax:
            values = ['NUEVA EMPRESA PROMOTORA DE SALUD EPS S.A','EPS Y MEDICINA PREPAGADA']
        else:
            values = []
        return {'status':'success','rows':[{'Value':v} for v in values]}


def make_files(root):
    rag = root/'data'/'rag'; rag.mkdir(parents=True)
    metrics = {'metrics':[
        {'metric_id':'ep','label':'EGRESOS PROBABLES','aliases':['EGRESOS PROBABLES'],'source_type':'visual_aggregation','semantic_model':'BRIEFING HOSPITALARIO','report':'BRIEFING HOSPITALARIO','reports':['BRIEFING HOSPITALARIO'],'table':'EGRESOS PROBABLES','column':'AINCONSEC','aggregation':'DistinctCount','dax_expression':"DISTINCTCOUNT('EGRESOS PROBABLES'[AINCONSEC])",'validation_status':'approved','appearances':[{'report':'BRIEFING HOSPITALARIO','page_display_name':'INICIO','visual_id':'v_ep'}]},
        {'metric_id':'cap','label':'CAPACIDAD INSTALADA','aliases':['CAPACIDAD INSTALADA'],'source_type':'visual_aggregation','semantic_model':'TABLERO DE ATENCIONES INSTITUCIONALES','report':'TABLERO DE ATENCIONES INSTITUCIONALES','reports':['TABLERO DE ATENCIONES INSTITUCIONALES'],'table':'CAMAS','column':'HCACODIGO','aggregation':'DistinctCount','dax_expression':"DISTINCTCOUNT('CAMAS'[HCACODIGO])",'validation_status':'approved','appearances':[{'page_display_name':'INDICADORES','visual_id':'v_cap'}]},
        {'metric_id':'att','label':'CANTIDAD ATENCIONES','aliases':['CANTIDAD ATENCIONES','ATENCIONES'],'source_type':'explicit_measure','semantic_model':'TABLERO DE ATENCIONES INSTITUCIONALES','report':'TABLERO DE ATENCIONES INSTITUCIONALES','reports':['TABLERO DE ATENCIONES INSTITUCIONALES'],'table':'UNIDAD_CARDIOVASCULAR','measure':'CANT_ATENCIONESUCAR','dax_expression':'[CANT_ATENCIONESUCAR]','validation_status':'approved','appearances':[{'page_display_name':'DISTRIBUCION DE ATENCIONES','visual_id':'v_att'}]},
    ]}
    (rag/'master_metrics.json').write_text(json.dumps(metrics),encoding='utf-8')
    visual={'schema_version':2,'reports':[
        {'report':'BRIEFING HOSPITALARIO','semantic_model':'BRIEFING HOSPITALARIO','source_group':'tablero_briefing_hospitalario','pages':[{'page_name':'p1','page_display_name':'INICIO','filters':{},'visuals':[{'visual_id':'v_ep','visual_type':'donutChart','fields':[{'role':'Category','kind':'column','table':'DIM_SERVICIO','column':'SERVICIO','native_query_ref':'SERVICIO'},{'role':'Values','kind':'aggregation','table':'EGRESOS PROBABLES','column':'AINCONSEC'}]},{'visual_id':'s_serv','visual_type':'slicer','fields':[{'role':'Values','kind':'column','table':'DIM_SERVICIO','column':'SERVICIO','native_query_ref':'SERVICIO'}]}]}]},
        {'report':'TABLERO DE ATENCIONES INSTITUCIONALES','semantic_model':'TABLERO DE ATENCIONES INSTITUCIONALES','source_group':'tablero_de_atenciones_institucionales','pages':[{'page_name':'p2','page_display_name':'DISTRIBUCION DE ATENCIONES','filters':{},'visuals':[{'visual_id':'v_att','visual_type':'card','fields':[{'role':'Values','kind':'measure','table':'UNIDAD_CARDIOVASCULAR','measure':'CANT_ATENCIONESUCAR'}]},{'visual_id':'s_eps','visual_type':'slicer','fields':[{'role':'Values','kind':'column','table':'UNIDAD_CARDIOVASCULAR','column':'ASEGURADOR','native_query_ref':'ASEGURADOR'}]},{'visual_id':'s_year','visual_type':'slicer','fields':[{'role':'Values','kind':'hierarchy_level','table':'Calendario','level':'Año','query_ref':'Calendario.Date.Variación.Jerarquía de fechas.Año','native_query_ref':'Date Año'}]},{'visual_id':'s_month','visual_type':'slicer','fields':[{'role':'Values','kind':'hierarchy_level','table':'Calendario','level':'Mes','query_ref':'Calendario.Date.Variación.Jerarquía de fechas.Mes','native_query_ref':'Date Mes'}]}]},{'page_name':'p3','page_display_name':'INDICADORES','filters':{},'visuals':[{'visual_id':'v_cap','visual_type':'card','fields':[{'role':'Values','kind':'aggregation','table':'CAMAS','column':'HCACODIGO'}]}]}]},
    ]}
    (rag/'visual_metrics_catalog.json').write_text(json.dumps(visual),encoding='utf-8')
    return rag/'master_metrics.json', rag/'visual_metrics_catalog.json'


def main():
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp); master,visual=make_files(root)
        builder=QueryPlanBuilder(master,visual,FakeRouter(),FakeProvider(),project_root=root)
        gen=QueryPlanDAXGenerator()

        plan=builder.build('¿Cuántos egresos probables hay por el servicio de urgencias en el Briefing Hospitalario?')
        assert plan['status']=='ready' and plan['metric']['label']=='EGRESOS PROBABLES'
        assert any(f.get('value')=='URGENCIAS' for f in plan['filters'])
        assert 'TREATAS' in gen.generate(plan)['dax']

        grouped=builder.build('¿Cuántos egresos probables hay por servicio en el Briefing Hospitalario?')
        assert grouped['status']=='ready' and grouped['mode']=='grouped'
        assert grouped['group_by'][0]['column']=='SERVICIO'
        assert 'SUMMARIZECOLUMNS' in gen.generate(grouped)['dax']

        assert builder.looks_numeric('¿Cuál es la capacidad instalada en el Tablero de Atenciones Institucionales?')
        cap=builder.build('¿Cuál es la capacidad instalada en el Tablero de Atenciones Institucionales?')
        assert cap['metric']['label']=='CAPACIDAD INSTALADA'

        att=builder.build('¿Cuántas atenciones corresponden a Nueva EPS en septiembre de 2026 en el Tablero de Atenciones Institucionales?')
        assert att['status']=='ready'
        assert any(f.get('type')=='date_range' and f.get('year')==2026 and f.get('month')==9 for f in att['filters'])
        assert any('NUEVA EMPRESA PROMOTORA' in str(f.get('value')) for f in att['filters'])
        dax=gen.generate(att)['dax']
        assert 'DATE(2026, 9, 1)' in dax and 'ASEGURADOR' in dax

    print('PRUEBA QUERY PLAN V5: OK')


if __name__=='__main__':
    main()
