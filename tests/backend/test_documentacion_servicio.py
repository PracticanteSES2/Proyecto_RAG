"""ServicioDocumentacion: lectura, propuesta asíncrona con progreso, aclaración,
corrección, descarte, aprobación y reindexación coordinada con el motor.
Herméticas: copia temporal del fixture, actualizador e indexación dobles."""
import shutil
import time
import unittest

from backend.app.core.errores import ErrorAPI
from backend.app.services import documentacion_progreso as progreso
from backend.app.services.documentacion import ServicioDocumentacion
from backend.app.services.documentacion_indice import CoordinadorIndice
from tests.backend import apoyo  # noqa: F401  (sys.path y entorno hermético)
from tests.backend.documentacion_doble import (
    GRUPO,
    ActualizadorDoble,
    IndexacionDoble,
    ProveedorDoble,
    raiz_temporal,
    trabajador_doble,
)

PALABRAS_PROHIBIDAS = ("cola", "fila", "turno", "servidor", "saturad", "otras consultas", "otras personas", "espera tu")


class Reloj:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class BaseServicio(unittest.TestCase):
    embebido = True

    def setUp(self):
        self.raiz = raiz_temporal()
        self.addCleanup(shutil.rmtree, self.raiz, True)
        self.actualizador = ActualizadorDoble()
        self.trabajador = trabajador_doble()
        self.indexacion = IndexacionDoble(self.trabajador.piscina)
        self.proveedor = ProveedorDoble()
        self.reloj = Reloj()
        self.coordinador = CoordinadorIndice(
            embebido=self.embebido, trabajador=lambda: self.trabajador, reindexar=self.indexacion.reindexar_grupo,
            raiz_datos=self.raiz, raiz_docs=self.raiz / "docs_tableros")
        self.servicio = ServicioDocumentacion(
            self.raiz / "docs_tableros", self.coordinador, proponer=self.actualizador.proponer_cambio,
            fabrica_llm=lambda: self.proveedor, reloj=self.reloj)
        self.addCleanup(self.servicio.cerrar)

    def archivo(self, nombre="consultas_dia.md"):
        return self.raiz / "docs_tableros" / GRUPO / "md" / nombre

    def esperar(self, condicion, maximo_s=10.0):
        limite = time.time() + maximo_s
        while time.time() < limite:
            valor = condicion()
            if valor:
                return valor
            time.sleep(0.01)
        raise AssertionError("la condición no se cumplió a tiempo")

    def terminada(self, pid):
        return self.esperar(lambda: (v := self.servicio.propuesta(pid))["estado"] != "preparando" and v)

    def reindexada(self, pid):
        def lista():
            vista = self.servicio.propuesta(pid)
            estado = vista["aprobacion"]["reindexacion"]["estado"]
            return estado not in ("en_curso", "sin_iniciar") and vista
        return self.esperar(lista)

    def codigo(self, funcion, *args, **kwargs):
        with self.assertRaises(ErrorAPI) as ctx:
            funcion(*args, **kwargs)
        return ctx.exception.estado_http, ctx.exception.codigo


class Lectura(BaseServicio):
    def test_grupos_con_el_nombre_del_tablero(self):
        self.assertEqual(self.servicio.grupos(), [{"grupo": GRUPO, "tablero": "TABLERO TIEMPOS URGENCIAS",
                                                   "paginas": 32}])

    def test_paginas_con_etiqueta_y_validez(self):
        datos = self.servicio.paginas(GRUPO)
        self.assertEqual(datos["tablero"], "TABLERO TIEMPOS URGENCIAS")
        consultas = next(p for p in datos["paginas"] if p["archivo"] == "consultas_dia.md")
        self.assertEqual(consultas["pagina"], "CONSULTAS DIA")
        self.assertTrue(consultas["valido"])
        self.assertFalse(consultas["general"])
        self.assertTrue(consultas["etiqueta"].startswith("CONSULTAS DIA — Oportunidad"))

    def test_grupo_inexistente(self):
        self.assertEqual(self.codigo(self.servicio.paginas, "no_existe"), (404, "grupo_no_encontrado"))
        self.assertEqual(self.codigo(self.servicio.paginas, ".."), (404, "grupo_no_encontrado"))

    def test_documento_por_archivo_listado(self):
        doc = self.servicio.documento(GRUPO, "consultas_dia.md")
        self.assertEqual(doc["pagina"], "CONSULTAS DIA")
        self.assertTrue(doc["valido"])
        self.assertEqual(doc["tablero"], "TABLERO TIEMPOS URGENCIAS")

    def test_documento_inexistente_o_ruta(self):
        self.assertEqual(self.codigo(self.servicio.documento, GRUPO, "no.md"), (404, "pagina_no_encontrada"))
        self.assertEqual(self.codigo(self.servicio.documento, GRUPO, "../manifest.json"),
                         (404, "pagina_no_encontrada"))


class Propuestas(BaseServicio):
    def test_asincrona_con_etapas_reales_y_luego_lista(self):
        self.actualizador.antes.clear()
        self.actualizador.despues.clear()
        vista = self.servicio.crear_propuesta("subí el semáforo de triage II a 20", GRUPO, None, ["pbip 1"], "Ana")
        self.assertEqual(vista["estado"], "preparando")
        self.assertEqual(vista["progreso"]["etapa"], "leyendo_nota")
        self.assertEqual(vista["progreso"]["frase"], "Leyendo tu nota")
        self.assertIsNone(vista["progreso"]["espera"])
        pid = vista["propuesta_id"]

        self.actualizador.antes.set()
        self.esperar(lambda: self.servicio.propuesta(pid)["progreso"]["etapa"] == "redactando")
        self.assertEqual(self.proveedor.llamadas, [{"max_tokens": 1500}])
        self.actualizador.despues.set()

        lista = self.terminada(pid)
        self.assertEqual(lista["estado"], "lista")
        self.assertIsNone(lista["progreso"])
        self.assertEqual(self.actualizador.llamadas[0]["cambios_pbip"], ["pbip 1"])
        self.assertEqual(lista["pagina"], "CONSULTAS DIA")
        self.assertTrue(lista["nombre_funcional"].startswith("Oportunidad"))
        self.assertEqual(lista["como_se_eligio"], "la nota la nombra o usa palabras que solo están en esa página")
        self.assertEqual(lista["operaciones"][0]["texto_actual"],
                         "Verde de 0 a 15 minutos, amarillo de 16 a 30 y rojo de 31 o más.")
        self.assertGreater(lista["diff"]["agregadas"], lista["diff"]["eliminadas"])  # + la línea del historial
        self.assertGreater(lista["diff"]["eliminadas"], 0)
        self.assertTrue(any(linea["tipo"] == "entra" and "20 minutos" in linea["texto"]
                            for bloque in lista["diff"]["bloques"] for linea in bloque["lineas"]))
        self.assertTrue(lista["formato_valido"])
        self.assertTrue(lista["puede_aprobar"])
        self.assertEqual(lista["avisos"], ["«Huecos en el semáforo» también menciona el 16; revise si cambia."])
        self.assertIn("1 llamada a MedGemma (1.5 s)", lista["tiempos"])
        self.assertIsNone(lista["detalle_tecnico"])
        self.assertEqual(lista["autor"], "Ana")
        self.assertIsNotNone(lista["vista_previa"])

    def test_frase_rota_y_aparecen_esperas_sin_hablar_de_colas(self):
        self.actualizador.antes.clear()
        pid = self.servicio.crear_propuesta("nota", GRUPO, None, None, "")["propuesta_id"]
        self.reloj.t += progreso.ROTACION_S + 0.1
        vista = self.servicio.propuesta(pid)
        self.assertNotEqual(vista["progreso"]["frase"], "Leyendo tu nota")
        self.assertIsNone(vista["progreso"]["espera"])
        self.reloj.t += 3
        self.assertEqual(self.servicio.propuesta(pid)["progreso"]["espera"], "Sigo trabajando en tu nota…")
        self.reloj.t += 100
        self.assertEqual(self.servicio.propuesta(pid)["progreso"]["espera"],
                         "Me está tomando más de lo habitual, pero sigo en ello.")
        self.actualizador.antes.set()
        self.terminada(pid)

    def test_ninguna_frase_habla_de_colas_ni_de_saturacion(self):
        frases = [f for variantes in progreso.FRASES.values() for f in variantes] + list(progreso.ESPERAS)
        for frase in frases:
            for palabra in PALABRAS_PROHIBIDAS:
                self.assertNotIn(palabra, frase.lower(), frase)

    def test_error_del_modelo_con_detalle_tecnico(self):
        vista = self.terminada(self.servicio.crear_propuesta("esto falla", GRUPO, None, None, "")["propuesta_id"])
        self.assertEqual(vista["estado"], "error")
        self.assertEqual(vista["errores"], ["MedGemma devolvió una respuesta incompleta."])
        self.assertEqual(vista["detalle_tecnico"], '{"operaciones": [')
        self.assertFalse(vista["puede_aprobar"])

    def test_excepcion_inesperada_sin_detalles_internos(self):
        with self.assertLogs("backend.app.services.documentacion", "ERROR"):
            vista = self.terminada(self.servicio.crear_propuesta("esto explota", GRUPO, None, None, "")["propuesta_id"])
        self.assertEqual(vista["estado"], "error")
        texto = " ".join(vista["errores"]) + str(vista["detalle_tecnico"])
        self.assertIn("No se pudo preparar la propuesta", texto)
        self.assertNotIn("detalle interno", texto)
        self.assertNotIn("Traceback", texto)

    def test_grupo_o_pagina_inexistente_al_proponer(self):
        self.assertEqual(self.codigo(self.servicio.crear_propuesta, "n", "nada", None, None, ""),
                         (404, "grupo_no_encontrado"))
        self.assertEqual(self.codigo(self.servicio.crear_propuesta, "n", GRUPO, "NO EXISTE", None, ""),
                         (404, "pagina_no_encontrada"))

    def test_propuesta_inexistente(self):
        self.assertEqual(self.codigo(self.servicio.propuesta, "x" * 32), (404, "propuesta_no_encontrada"))

    def test_aclaracion_con_candidatas_y_reintento_con_pagina(self):
        pid = self.servicio.crear_propuesta("nota ambigua", GRUPO, None, None, "")["propuesta_id"]
        vista = self.terminada(pid)
        self.assertEqual(vista["estado"], "requiere_aclaracion")
        self.assertEqual(vista["dudas"], ["¿A qué página del tablero se refiere el cambio?"])
        self.assertEqual([c["pagina"] for c in vista["candidatas"]], ["CONSULTAS DIA", "RESUMEN"])
        self.assertTrue(vista["candidatas"][0]["etiqueta"].startswith("CONSULTAS DIA — "))
        self.assertFalse(vista["puede_aprobar"])

        otra = self.servicio.aclarar(pid, "nota ambigua precisada", "CONSULTAS DIA")
        self.assertEqual(otra["propuesta_id"], pid)
        self.assertEqual(otra["estado"], "preparando")
        lista = self.terminada(pid)
        self.assertEqual(lista["estado"], "lista")
        self.assertEqual(lista["nota"], "nota ambigua precisada")
        self.assertEqual(lista["como_se_eligio"], "la elegiste tú en el formulario")
        self.assertEqual(self.actualizador.llamadas[-1]["pagina"], "CONSULTAS DIA")

    def test_no_se_aclara_mientras_prepara(self):
        self.actualizador.antes.clear()
        pid = self.servicio.crear_propuesta("nota", GRUPO, None, None, "")["propuesta_id"]
        self.assertEqual(self.codigo(self.servicio.aclarar, pid, "otra", None), (409, "propuesta_en_curso"))
        self.assertEqual(self.codigo(self.servicio.aprobar, pid, "Ana"), (409, "propuesta_en_curso"))
        self.actualizador.antes.set()
        self.terminada(pid)

    def test_corregir_el_texto_de_una_operacion(self):
        pid = self.servicio.crear_propuesta("semaforo", GRUPO, None, None, "")["propuesta_id"]
        self.terminada(pid)
        vista = self.servicio.corregir(pid, {0: "Verde de 0 a 25 minutos."})
        self.assertEqual(vista["operaciones"][0]["texto"], "Verde de 0 a 25 minutos.")
        self.assertIn("Verde de 0 a 25 minutos.", vista["diff"]["unificado"])
        self.assertTrue(vista["puede_aprobar"])

    def test_correccion_invalida(self):
        pid = self.servicio.crear_propuesta("semaforo", GRUPO, None, None, "")["propuesta_id"]
        self.terminada(pid)
        self.assertEqual(self.codigo(self.servicio.corregir, pid, {0: "   "}), (422, "correccion_invalida"))
        self.assertEqual(self.codigo(self.servicio.corregir, pid, {7: "x"}), (422, "correccion_invalida"))

    def test_descartar(self):
        pid = self.servicio.crear_propuesta("semaforo", GRUPO, None, None, "")["propuesta_id"]
        self.terminada(pid)
        self.assertEqual(self.servicio.descartar(pid)["estado"], "descartada")
        self.assertEqual(self.codigo(self.servicio.aprobar, pid, "Ana"), (409, "propuesta_no_aprobable"))
        self.assertEqual(self.codigo(self.servicio.corregir, pid, {0: "x"}), (409, "propuesta_no_editable"))


class Aprobacion(BaseServicio):
    def test_aprobar_guarda_y_reindexa_con_la_piscina_retenida(self):
        original = self.archivo().read_text(encoding="utf-8")
        pid = self.servicio.crear_propuesta("semaforo", GRUPO, None, None, "")["propuesta_id"]
        self.terminada(pid)
        self.indexacion.compuerta.clear()
        vista = self.servicio.aprobar(pid, "Ana")
        self.assertEqual(vista["estado"], "aprobada")
        self.assertEqual(vista["aprobacion"]["autor"], "Ana")
        self.assertEqual(vista["aprobacion"]["version"], 2)
        self.assertIn(vista["aprobacion"]["reindexacion"]["estado"], ("en_curso", "sin_iniciar"))
        self.assertFalse(vista["puede_aprobar"])
        guardado = self.archivo().read_text(encoding="utf-8")
        self.assertNotEqual(guardado, original)
        self.assertIn("Verde de 0 a 20 minutos", guardado)
        self.assertIn("Autor: Ana.", guardado)

        self.esperar(lambda: self.indexacion.llamadas)
        self.assertEqual(self.servicio.propuesta(pid)["aprobacion"]["reindexacion"]["estado"], "en_curso")
        self.indexacion.compuerta.set()
        final = self.reindexada(pid)["aprobacion"]["reindexacion"]
        self.assertEqual(final["estado"], "lista")
        self.assertEqual(final["mensaje"], "El asistente ya usa el texto nuevo: se reindexó TABLERO TIEMPOS URGENCIAS "
                                           "(32 documentos, 120 fragmentos, 2.5 s) con la conexión del chat.")
        self.assertTrue(final["conexion_compartida"])
        llamada = self.indexacion.llamadas[0]
        self.assertEqual(llamada["libres"], 0, "la reindexación debe retener todas las instancias del motor")
        self.assertIs(llamada["cliente"], self.trabajador.retriever.client)
        self.assertIs(llamada["retriever"], self.trabajador.retriever)
        self.assertEqual(llamada["project_root"], self.raiz)
        self.assertEqual(llamada["md_root"], self.raiz / "docs_tableros")
        self.assertEqual(self.trabajador.piscina.libres, 2)
        self.assertEqual(self.trabajador.huella.invalidaciones, 1)
        self.assertEqual(self.servicio.reindexacion(GRUPO)["estado"], "lista")

    def test_archivo_modificado_despues_de_proponer(self):
        pid = self.servicio.crear_propuesta("semaforo", GRUPO, None, None, "")["propuesta_id"]
        self.terminada(pid)
        self.archivo().write_text(self.archivo().read_text(encoding="utf-8") + "\n", encoding="utf-8")
        estado, codigo = self.codigo(self.servicio.aprobar, pid, "Ana")
        self.assertEqual((estado, codigo), (409, "documento_modificado"))
        self.assertEqual(self.servicio.propuesta(pid)["estado"], "lista")
        self.assertEqual(self.indexacion.llamadas, [])

    def test_no_se_aprueba_una_propuesta_con_error(self):
        pid = self.servicio.crear_propuesta("falla", GRUPO, None, None, "")["propuesta_id"]
        self.terminada(pid)
        self.assertEqual(self.codigo(self.servicio.aprobar, pid, "Ana"), (409, "propuesta_no_aprobable"))

    def test_reindexacion_con_errores_y_reintento(self):
        self.indexacion.errores = ["ValueError: la carpeta del grupo declara otros grupos"]
        pid = self.servicio.crear_propuesta("semaforo", GRUPO, None, None, "")["propuesta_id"]
        self.terminada(pid)
        self.servicio.aprobar(pid, "Ana")
        fallida = self.reindexada(pid)["aprobacion"]["reindexacion"]
        self.assertEqual(fallida["estado"], "error")
        self.assertTrue(fallida["mensaje"].startswith("La reindexación falló:"))
        self.assertIn("declara otros grupos", fallida["mensaje"])

        self.indexacion.errores = []
        self.assertIn(self.servicio.reindexar(GRUPO)["estado"], ("en_curso", "lista"))
        self.assertEqual(self.reindexada(pid)["aprobacion"]["reindexacion"]["estado"], "lista")

    def test_reindexacion_de_grupo_inexistente(self):
        self.assertEqual(self.codigo(self.servicio.reindexar, "nada"), (404, "grupo_no_encontrado"))
        self.assertEqual(self.servicio.reindexacion(GRUPO)["estado"], "sin_iniciar")

    def test_motor_arrancando(self):
        self.trabajador = None
        pid = self.servicio.crear_propuesta("semaforo", GRUPO, None, None, "")["propuesta_id"]
        self.terminada(pid)
        self.servicio.aprobar(pid, "Ana")
        final = self.reindexada(pid)["aprobacion"]["reindexacion"]
        self.assertEqual(final["estado"], "no_disponible")
        self.assertIn("arrancando", final["mensaje"])


class MotorExterno(BaseServicio):
    embebido = False

    def test_reindexacion_no_disponible_pero_el_cambio_queda_guardado(self):
        pid = self.servicio.crear_propuesta("semaforo", GRUPO, None, None, "")["propuesta_id"]
        self.terminada(pid)
        vista = self.servicio.aprobar(pid, "Ana")
        self.assertEqual(vista["estado"], "aprobada")
        final = self.reindexada(pid)["aprobacion"]["reindexacion"]
        self.assertEqual(final["estado"], "no_disponible")
        self.assertIn("quedó guardado", final["mensaje"])
        self.assertEqual(self.indexacion.llamadas, [])
        self.assertIn("Verde de 0 a 20 minutos", self.archivo().read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
