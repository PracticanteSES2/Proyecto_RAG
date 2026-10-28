"""
Pruebas del actualizador (nota -> propuesta -> aprobación) con un LLM falso, sin red.

    python -m unittest tests.docs_md.test_actualizador

El mini tablero de tests/docs_md/actualizador_fixtures se copia a una carpeta
temporal en cada prueba: proponer no escribe, pero aplicar sí.
"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from src.docs_md import actualizador as A
from src.docs_md import formato as F
from src.docs_md import repositorio as R

FIXTURES = Path(__file__).parent / "actualizador_fixtures"
GRUPO = "tablero_tiempos_urgencias"


def _ops(*operaciones, resumen="Cambio de prueba.", dudas=()):
    return json.dumps({"operaciones": [
        {"accion": o[0], "seccion": o[1], "entrada": o[2], "antes": "", "texto": o[3] if len(o) > 3 else ""}
        for o in operaciones], "resumen": resumen, "dudas": list(dudas)}, ensure_ascii=False)


class LLMFalso:
    """Devuelve las respuestas en orden y guarda cada llamada."""

    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = []

    def chat(self, messages, temperature=0.1, max_tokens=450, think=False, timeout=None, format=None):
        self.llamadas.append({"messages": messages, "format": format, "temperature": temperature})
        if not self.respuestas:
            raise AssertionError("El LLM falso no tiene más respuestas.")
        r = self.respuestas.pop(0)
        if isinstance(r, dict):
            return r
        return {"status": "success", "answer": r}


class BaseActualizador(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        shutil.copytree(FIXTURES, self.tmp, dirs_exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def proponer(self, nota, *respuestas, **kw):
        llm = LLMFalso(*respuestas)
        return A.proponer_cambio(nota, GRUPO, llm=llm, raiz=self.tmp, **kw), llm

    def texto(self, pagina):
        return R.leer_texto(GRUPO, pagina, self.tmp)


class ProponerTest(BaseActualizador):
    def test_modificar_umbral(self):
        p, llm = self.proponer(
            "le cambie el verde del semaforo de egresos a 45",
            _ops(("modificar", "Reglas de negocio", "Semáforo de egresos",
                  "Verde de 0 a 45 minutos, amarillo de 61 a 90 y rojo de 91 o más; naranja para valores negativos")))
        self.assertEqual(p.estado, "lista", p)
        self.assertEqual(p.pagina, "EGRESOS DIA")
        self.assertEqual(p.metodo_pagina, "reglas")
        self.assertEqual(len(llm.llamadas), 1)  # la página salió por reglas
        self.assertIn("+- **Semáforo de egresos**: Verde de 0 a 45 minutos", p.diff)
        self.assertIn("-version: 1", p.diff)
        nuevo = F.parsear(p.despues)
        self.assertEqual(F.validar(nuevo), [])
        self.assertEqual(nuevo.meta["version"], 2)
        # El texto de la página sin historial ni metadatos va al modelo, con el esquema.
        usuario = llm.llamadas[0]["messages"][-1]["content"]
        self.assertIn("«Semáforo de egresos»", usuario)
        self.assertNotIn("Historial de cambios", usuario)
        esquema = llm.llamadas[0]["format"]
        self.assertIn("Reglas de negocio", esquema["properties"]["operaciones"]["items"]["properties"]["seccion"]["enum"])
        # proponer no escribe
        self.assertEqual(self.texto("EGRESOS DIA"), p.antes)

    def test_agregar_visual(self):
        p, _ = self.proponer(
            "agregue en egresos dia una tarjeta con el conteo de pacientes en espera",
            _ops(("agregar", "Visuales", "Tarjeta pacientes en espera", "Cantidad de pacientes en espera de egreso")))
        self.assertEqual(p.estado, "lista")
        doc = F.parsear(p.despues)
        self.assertEqual(doc.buscar("Visuales", "Tarjeta pacientes en espera").texto,
                         "Cantidad de pacientes en espera de egreso.")

    def test_eliminar(self):
        p, _ = self.proponer("quite el boton de regresar de egresos dia",
                             _ops(("eliminar", "Visuales", "Botón regresar")))
        self.assertEqual(p.estado, "lista")
        self.assertIsNone(F.parsear(p.despues).buscar("Visuales", "Botón regresar"))
        self.assertIn("-- **Botón regresar**", p.diff)

    def test_nota_sin_contenido_no_llama_al_modelo(self):
        p, llm = self.proponer("arregle lo de egresos")
        self.assertEqual(p.estado, "requiere_aclaracion")
        self.assertEqual(llm.llamadas, [])
        self.assertTrue(p.dudas)
        self.assertIn("EGRESOS DIA", p.candidatas)

    def test_nota_ambigua_el_modelo_pregunta(self):
        p, _ = self.proponer("en egresos dia cambie lo del verde",
                             _ops(dudas=["¿Qué semáforo cambió y a qué valor?"]))
        self.assertEqual(p.estado, "requiere_aclaracion")
        self.assertEqual(p.dudas, ["¿Qué semáforo cambió y a qué valor?"])
        self.assertEqual(p.operaciones, [])

    def test_json_roto_reintento(self):
        p, llm = self.proponer(
            "le cambie el verde del semaforo de egresos a 45",
            "Claro, aquí va: {operaciones: [",
            _ops(("modificar", "Reglas de negocio", "Semáforo de egresos",
                  "Verde de 0 a 45 minutos, amarillo de 61 a 90 y rojo de 91 o más")))
        self.assertEqual(p.estado, "lista")
        self.assertEqual(len(llm.llamadas), 2)
        reintento = llm.llamadas[1]["messages"]
        self.assertEqual(reintento[-2]["role"], "assistant")
        self.assertIn("no es un JSON válido", reintento[-1]["content"])
        self.assertIn("reintento", p.llm_raw)

    def test_json_roto_dos_veces_es_error(self):
        p, _ = self.proponer("le cambie el verde del semaforo de egresos a 45", "nada", "tampoco")
        self.assertEqual(p.estado, "error")
        self.assertTrue(p.errores)

    def test_respuesta_cortada_se_rescata_y_reintenta(self):
        buena = json.loads(_ops(("modificar", "Reglas de negocio", "Semáforo de egresos",
                                 "Verde de 0 a 45 minutos, amarillo de 61 a 90 y rojo de 91 o más")))
        cortada = json.dumps(buena, ensure_ascii=False)[:-40]  # sin cierre: límite de tokens
        cortada = cortada[:cortada.rfind("}") + 1] + ', {"accion": "modificar", "seccion": "Vis'
        p, llm = self.proponer("le cambie el verde del semaforo de egresos a 45", cortada, cortada)
        self.assertEqual(len(llm.llamadas), 2)
        self.assertIn("quedó cortada", llm.llamadas[1]["messages"][-1]["content"])
        self.assertEqual(p.estado, "lista")  # se usan las operaciones completas
        self.assertEqual(p.operaciones[0].entrada, "Semáforo de egresos")

    def test_json_entre_texto_y_bloque_de_codigo(self):
        respuesta = "```json\n" + _ops(("modificar", "Reglas de negocio", "Semáforo de egresos",
                                        "Verde de 0 a 45 minutos, amarillo de 61 a 90 y rojo de 91 o más")) + "\n```"
        p, llm = self.proponer("le cambie el verde del semaforo de egresos a 45", respuesta)
        self.assertEqual(p.estado, "lista")
        self.assertEqual(len(llm.llamadas), 1)

    def test_entrada_con_tildes_y_mayusculas_distintas(self):
        p, _ = self.proponer(
            "le cambie el verde del semaforo de egresos a 45",
            _ops(("modificar", "reglas de NEGOCIO", "SEMAFORO DE EGRESOS",
                  "Verde de 0 a 45 minutos, amarillo de 61 a 90 y rojo de 91 o más")))
        self.assertEqual(p.estado, "lista")
        self.assertEqual(p.operaciones[0].entrada, "Semáforo de egresos")
        self.assertEqual(p.operaciones[0].seccion, "Reglas de negocio")

    def test_entrada_parecida_se_corrige(self):
        p, _ = self.proponer(
            "le cambie el verde del semaforo de egresos a 45",
            _ops(("modificar", "Reglas de negocio", "Semaforo egresos",
                  "Verde de 0 a 45 minutos, amarillo de 61 a 90 y rojo de 91 o más")))
        self.assertEqual(p.estado, "lista")
        self.assertEqual(p.operaciones[0].entrada, "Semáforo de egresos")
        self.assertTrue(any("parecida" in a for a in p.avisos))

    def test_entrada_en_otra_seccion_se_corrige(self):
        p, _ = self.proponer(
            "le cambie el verde del semaforo de egresos a 45",
            _ops(("modificar", "Visuales", "Semáforo de egresos",
                  "Verde de 0 a 45 minutos, amarillo de 61 a 90 y rojo de 91 o más")))
        self.assertEqual(p.estado, "lista")
        self.assertEqual(p.operaciones[0].seccion, "Reglas de negocio")

    def test_agregar_duplicado_se_vuelve_modificar(self):
        p, _ = self.proponer(
            "le cambie el verde del semaforo de egresos a 45",
            _ops(("agregar", "Reglas de negocio", "Semáforo de egresos",
                  "Verde de 0 a 45 minutos, amarillo de 61 a 90 y rojo de 91 o más")))
        self.assertEqual(p.estado, "lista")
        self.assertEqual(p.operaciones[0].accion, "modificar")
        nombres = [e.nombre for e in F.parsear(p.despues).entradas("Reglas de negocio")]
        self.assertEqual(nombres.count("Semáforo de egresos"), 1)

    def test_agregar_parecido_pero_distinto_no_se_fusiona(self):
        # «Tarjeta en espera egreso» no es «Tabla en espera egreso».
        p, _ = self.proponer(
            "agregue en egresos dia una tarjeta con el conteo de pacientes en espera",
            _ops(("agregar", "Visuales", "Tarjeta en espera egreso", "Cantidad de pacientes en espera de egreso")))
        self.assertEqual(p.operaciones[0].accion, "agregar")

    def test_entrada_inexistente_pide_aclaracion(self):
        p, llm = self.proponer(
            "en egresos dia le cambie el color a la tabla de remitidos",
            _ops(("modificar", "Visuales", "Tabla remitidos", "Pacientes remitidos con color.")),
            _ops(("modificar", "Visuales", "Tabla remitidos", "Pacientes remitidos con color.")))
        self.assertEqual(p.estado, "requiere_aclaracion")
        self.assertEqual(len(llm.llamadas), 2)  # un reintento con el error
        self.assertTrue(any("No existe la entrada" in d for d in p.dudas))

    def test_cambio_no_pedido_se_descarta(self):
        p, _ = self.proponer(
            "le cambie el verde del semaforo de egresos a 45",
            _ops(("modificar", "Reglas de negocio", "Semáforo de egresos",
                  "Verde de 0 a 45 minutos, amarillo de 61 a 90 y rojo de 91 o más"),
                 ("modificar", "Fuentes de datos", "EGRESOS_DIA",
                  "Órdenes de salida del día en la unidad de urgencias con el último folio; tabla en DirectQuery")))
        self.assertEqual(p.estado, "lista")
        self.assertEqual([o.entrada for o in p.operaciones], ["Semáforo de egresos"])
        self.assertTrue(any("EGRESOS_DIA" in a for a in p.avisos))

    def test_texto_igual_al_actual_reintenta(self):
        actual = "Verde de 0 a 60 minutos, amarillo de 61 a 90 y rojo de 91 o más; naranja para valores negativos."
        p, llm = self.proponer(
            "le cambie el verde del semaforo de egresos a 45",
            _ops(("modificar", "Reglas de negocio", "Semáforo de egresos", actual)),
            _ops(("modificar", "Reglas de negocio", "Semáforo de egresos",
                  "Verde de 0 a 45 minutos, amarillo de 61 a 90 y rojo de 91 o más; naranja para valores negativos")))
        self.assertEqual(p.estado, "lista")
        self.assertIn("deja el texto igual", llm.llamadas[1]["messages"][-1]["content"])

    def test_quitar_un_filtro_no_elimina_el_visual(self):
        p, llm = self.proponer(
            "quite el filtro de obstetricas en la torta",
            _ops(("eliminar", "Visuales", "Gráfico circular por clasificación triage")),
            _ops(("modificar", "Visuales", "Gráfico circular por clasificación triage",
                  "Torta con la cantidad de triages por DESCRI_TRIGE. Incluye las clasificaciones obstétricas; "
                  "excluye MUERTO")))
        self.assertEqual(p.pagina, "MAPA DE CALOR TRIAGE")  # «torta» -> gráfico circular, por reglas
        self.assertIn("quita un filtro", llm.llamadas[1]["messages"][-1]["content"])
        self.assertEqual(p.operaciones[0].accion, "modificar")
        # «Incluye» no es una palabra de la nota: se acepta con un aviso para quien revisa.
        self.assertEqual(p.estado, "lista")
        self.assertTrue(any("no usa las palabras de la nota" in a for a in p.avisos))

    def test_retoque_de_redaccion_no_pedido_se_descarta(self):
        p, _ = self.proponer(
            "general: agregue la definicion de tiempo de estancia = horas entre admision y orden de salida",
            _ops(("agregar", "Definiciones", "Tiempo de estancia", "Horas entre la admisión y la orden de salida"),
                 ("modificar", "Definiciones", "Tiempo para el egreso",
                  "Minutos entre la última folio de historia clínica y la orden de salida. Válido si es mayor que 0 "
                  "y menor o igual a 720 minutos")))
        self.assertEqual(p.estado, "lista")
        self.assertEqual([o.accion for o in p.operaciones], ["agregar"])

    def test_texto_sin_unidad_reintenta(self):
        p, llm = self.proponer(
            "egresos dia: el semaforo de egresos ahora es verde hasta 45",
            _ops(("modificar", "Reglas de negocio", "Semáforo de egresos", "Verde <=45, amarillo 61-90, rojo >90")),
            _ops(("modificar", "Reglas de negocio", "Semáforo de egresos",
                  "Verde de 0 a 45 minutos, amarillo de 61 a 90 y rojo de 91 o más; naranja para valores negativos")))
        self.assertEqual(p.estado, "lista")
        self.assertIn("perdió la unidad", llm.llamadas[1]["messages"][-1]["content"])
        self.assertIn("45 minutos", p.operaciones[0].texto)

    def test_modificar_sin_texto_cuando_la_nota_quita_es_eliminar(self):
        p, _ = self.proponer("ya no esta el boton de regresar en egresos dia",
                             _ops(("modificar", "Visuales", "Botón regresar", "")))
        self.assertEqual(p.estado, "lista")
        self.assertEqual(p.operaciones[0].accion, "eliminar")

    def test_eliminar_sin_que_la_nota_quite_nada_se_descarta(self):
        p, _ = self.proponer("le cambie el verde del semaforo de egresos a 45",
                             _ops(("eliminar", "Reglas de negocio", "Semáforo de egresos")),
                             _ops(("eliminar", "Reglas de negocio", "Semáforo de egresos")))
        self.assertEqual(p.estado, "requiere_aclaracion")
        self.assertEqual(p.operaciones, [])

    def test_contradiccion_con_valor_anterior(self):
        p, llm = self.proponer("en egresos dia subi el rojo del semaforo de egresos de 120 a 150")
        self.assertEqual(p.estado, "requiere_aclaracion")
        self.assertEqual(llm.llamadas, [])
        self.assertIn("120", p.dudas[0])

    def test_quitar_algo_que_la_pagina_no_documenta(self):
        p, llm = self.proponer("en tiempo egreso le quite el semaforo a la tarjeta")
        self.assertEqual(p.estado, "requiere_aclaracion")
        self.assertEqual(llm.llamadas, [])
        self.assertIn("semaforo", p.dudas[0])

    def test_cifras_sin_origen_generan_aviso(self):
        p, _ = self.proponer(
            "le cambie el verde del semaforo de egresos a 45",
            _ops(("modificar", "Reglas de negocio", "Semáforo de egresos",
                  "Verde de 0 a 45 minutos, amarillo de 46 a 90 y rojo de 91 o más")))
        self.assertEqual(p.estado, "lista")
        self.assertTrue(any("46" in a for a in p.avisos))

    def test_servidor_no_responde(self):
        p, _ = self.proponer("le cambie el verde del semaforo de egresos a 45",
                             {"status": "llm_timeout", "answer": None})
        self.assertEqual(p.estado, "error")
        self.assertIn("no respondió", p.errores[0])

    def test_dudas_del_modelo_con_operaciones_no_quedan_listas(self):
        p, _ = self.proponer(
            "le cambie el verde del semaforo de egresos a 45",
            _ops(("modificar", "Reglas de negocio", "Semáforo de egresos",
                  "Verde de 0 a 45 minutos, amarillo de 61 a 90 y rojo de 91 o más"),
                 dudas=["¿El amarillo empieza ahora en 46?"]))
        self.assertEqual(p.estado, "requiere_aclaracion")
        self.assertTrue(p.diff)  # se muestra la vista previa

    def test_pagina_indicada(self):
        p, llm = self.proponer(
            "subi el verde a 5 horas",
            _ops(("modificar", "Reglas de negocio", "Semáforo de hospitalización",
                  "Verde de 0 a 5 horas, amarillo de 6 y rojo de 7 o más")),
            pagina="hospitalizacion dia")
        self.assertEqual(p.pagina, "HOSPITALIZACION DIA")
        self.assertEqual(p.metodo_pagina, "indicada")
        self.assertEqual(len(llm.llamadas), 1)

    def test_cambios_pbip_van_al_prompt(self):
        cambios = ["Página EGRESOS DIA: el visual Tabla «EGRESOS» cambió el filtro TIEMPO_EGRESO_OK < 361 por "
                   "TIEMPO_EGRESO_OK < 721."]
        p, llm = self.proponer(
            "lo que pidio calidad",
            _ops(("modificar", "Visuales", "Tabla egresos",
                  "Titulada «EGRESOS»; pacientes con orden de salida hoy. Filtro del visual: tiempo mayor que 0 y "
                  "menor que 721 minutos")),
            cambios_pbip=cambios)
        self.assertEqual(p.pagina, "EGRESOS DIA")
        self.assertIn("TIEMPO_EGRESO_OK < 721", llm.llamadas[0]["messages"][-1]["content"])
        self.assertEqual(p.estado, "lista")


class PaginaTest(BaseActualizador):
    def test_pagina_elegida_por_reglas(self):
        paginas = A._cargar_paginas(GRUPO, self.tmp)
        casos = {
            "ya no se usa la tabla de remisiones en hospi dia": "HOSPITALIZACION DIA",
            "en consultas dia el semaforo de triage 3 ahora es verde hasta 45": "CONSULTAS DIA",
            "el tiempo promedio para triage del historico ahora excluye los pacientes sin turno": "TIEMPO TRIAGE",
            "general: agregue la definicion de tiempo de estancia": "TABLERO TIEMPOS URGENCIAS",
        }
        for nota, esperada in casos.items():
            eleccion = A.elegir_pagina(nota, GRUPO, raiz=self.tmp, llamar=self._sin_llm)
            self.assertEqual((nota, eleccion["pagina"], eleccion["metodo"]), (nota, esperada, "reglas"))
        self.assertTrue(paginas)

    @staticmethod
    def _sin_llm(*_args, **_kw):
        raise AssertionError("No debía llamar al modelo.")

    def test_dos_paginas_nombradas_gana_la_primera(self):
        eleccion = A.elegir_pagina(
            "en mapa de calor triage agregue un segmentador de tipo de triage igual al de tiempo triage",
            GRUPO, raiz=self.tmp, llamar=self._sin_llm)
        self.assertEqual(eleccion["pagina"], "MAPA DE CALOR TRIAGE")
        self.assertEqual(eleccion["otras"], ["TIEMPO TRIAGE"])

    def test_columna_no_cuenta_como_nombre_de_pagina(self):
        # TIEMPO_EGRESO_OK no es la página TIEMPO EGRESO.
        eleccion = A.elegir_pagina("lo que pidio calidad", GRUPO, raiz=self.tmp, llamar=self._sin_llm,
                                   cambios_pbip=["Página EGRESOS DIA: filtro TIEMPO_EGRESO_OK < 721."])
        self.assertEqual(eleccion["pagina"], "EGRESOS DIA")
        self.assertEqual(eleccion["otras"], [])

    def test_sin_pistas_se_pide_confirmar_la_sugerencia(self):
        p, llm = self.proponer("le cambie el verde a 45", json.dumps({"pagina": "EGRESOS DIA"}))
        self.assertEqual(p.estado, "requiere_aclaracion")
        self.assertEqual(len(llm.llamadas), 1)
        self.assertEqual(p.candidatas[0], "EGRESOS DIA")
        self.assertIn("¿Es EGRESOS DIA?", p.dudas[0])

    NOTA_DOS_PAGINAS = "cambie el boton de regresar de hospitalizacion para que lleve a RESUMEN en vez de RESUMEN_D"

    def test_pagina_elegida_por_medgemma_entre_candidatas(self):
        p, llm = self.proponer(
            self.NOTA_DOS_PAGINAS,
            json.dumps({"pagina": "HOSPITALIZACION DIA"}),
            _ops(("modificar", "Visuales", "Botón regresar",
                  "Botón de la esquina superior izquierda que regresa a RESUMEN")))
        self.assertEqual(p.estado, "lista")
        self.assertEqual((p.pagina, p.metodo_pagina), ("HOSPITALIZACION DIA", "medgemma"))
        opciones = llm.llamadas[0]["format"]["properties"]["pagina"]["enum"]
        self.assertIn("HOSPITALIZACION DIA", opciones)
        self.assertIn("EGRESOS DIA", opciones)
        self.assertIn(A.NO_SE_SABE, opciones)

    def test_servidor_cae_al_elegir_pagina(self):
        p, _ = self.proponer(self.NOTA_DOS_PAGINAS, {"status": "llm_timeout", "answer": None})
        self.assertEqual(p.estado, "error")
        self.assertIn("no respondió", p.errores[0])

    def test_modelo_no_sabe_la_pagina(self):
        p, llm = self.proponer(self.NOTA_DOS_PAGINAS, json.dumps({"pagina": "NO_SE_SABE"}))
        self.assertEqual(p.estado, "requiere_aclaracion")
        self.assertEqual(len(llm.llamadas), 1)
        self.assertIn("HOSPITALIZACION DIA", p.candidatas)


class AplicarTest(BaseActualizador):
    def _propuesta_lista(self):
        p, _ = self.proponer(
            "le cambie el verde del semaforo de egresos a 45",
            _ops(("modificar", "Reglas de negocio", "Semáforo de egresos",
                  "Verde de 0 a 45 minutos, amarillo de 61 a 90 y rojo de 91 o más; naranja para valores negativos"),
                 resumen="Se cambió el verde del semáforo de egresos a 45 minutos."))
        self.assertEqual(p.estado, "lista")
        return p

    def test_aplicar_guarda_con_autor(self):
        p = self._propuesta_lista()
        ruta = A.aplicar_propuesta(p, "Ana", raiz=self.tmp)
        self.assertEqual(ruta.name, "egresos_dia.md")
        doc = R.leer_pagina(GRUPO, "EGRESOS DIA", self.tmp)
        self.assertEqual(doc.meta["version"], 2)
        self.assertTrue(doc.buscar("Reglas de negocio", "Semáforo de egresos").texto.startswith("Verde de 0 a 45"))
        historial = doc.entradas("Historial de cambios")[-1]
        self.assertIn("Autor: Ana.", historial.texto)
        self.assertIn("45 minutos", historial.texto)
        self.assertEqual(F.validar(doc), [])

    def test_archivo_cambiado_entre_proponer_y_aplicar(self):
        p = self._propuesta_lista()
        ruta = R.ruta_pagina(GRUPO, "EGRESOS DIA", self.tmp)
        ruta.write_text(ruta.read_text(encoding="utf-8").replace("liberar camas", "liberar camas pronto"),
                        encoding="utf-8")
        with self.assertRaises(A.ErrorActualizacion) as ctx:
            A.aplicar_propuesta(p, "Ana", raiz=self.tmp)
        self.assertIn("cambió", str(ctx.exception))

    def test_solo_se_aplican_propuestas_listas(self):
        p, _ = self.proponer("arregle lo de egresos")
        with self.assertRaises(A.ErrorActualizacion):
            A.aplicar_propuesta(p, "Ana", raiz=self.tmp)

    def test_fin_de_linea_crlf_no_cuenta_como_cambio(self):
        ruta = R.ruta_pagina(GRUPO, "EGRESOS DIA", self.tmp)
        ruta.write_bytes(ruta.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        p = self._propuesta_lista()
        A.aplicar_propuesta(p, "Ana", raiz=self.tmp)
        self.assertEqual(R.leer_pagina(GRUPO, "EGRESOS DIA", self.tmp).meta["version"], 2)


class FixturesTest(unittest.TestCase):
    def test_fixtures_validos_y_canonicos(self):
        for ruta in sorted((FIXTURES / GRUPO / "md").glob("*.md")):
            texto = ruta.read_text(encoding="utf-8").replace("\r\n", "\n")
            doc = F.parsear(texto)
            self.assertEqual(F.validar(doc), [], ruta.name)
            self.assertEqual(F.serializar(doc), texto, ruta.name)


if __name__ == "__main__":
    unittest.main()
