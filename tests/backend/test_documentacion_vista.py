"""Vista de la documentación viva (lógica pura que antes vivía en
src/docs_md/interfaz.py): ficha, cuerpo, historial, operaciones, diff y textos
de la revisión. Sin red ni archivos."""
import unittest
from dataclasses import replace
from pathlib import Path

from backend.app.services import documentacion_vista as vista
from src.docs_md.actualizador import Propuesta
from src.docs_md.formato import ErrorOperacion, Operacion, aplicar_operaciones, parsear, serializar
from tests.backend import apoyo  # noqa: F401  (sys.path y entorno hermético)

FIXTURE = Path(__file__).resolve().parents[1] / "docs_md" / "fixtures" / "tablero_tiempos_urgencias" / "md"
TEXTO = (FIXTURE / "consultas_dia.md").read_text(encoding="utf-8")


class FichaCuerpoHistorial(unittest.TestCase):
    def setUp(self):
        self.doc = parsear(TEXTO)

    def test_ficha_con_los_datos_de_la_pagina_y_raya_si_falta(self):
        ficha = {f["dato"]: f["valor"] for f in vista.ficha(self.doc)}
        self.assertEqual(list(ficha), ["Tablero", "Página", "Nombre funcional", "Bloque", "Tablas", "Versión",
                                       "Última actualización"])
        self.assertEqual(ficha["Página"], "CONSULTAS DIA")
        self.assertEqual(ficha["Tablas"], "CONSULTAS_DIA, EN_ESPERA_CONSULTA")
        self.assertEqual(ficha["Versión"], "1")
        sin_bloque = replace(self.doc, meta={**self.doc.meta, "bloque": ""})
        self.assertEqual({f["dato"]: f["valor"] for f in vista.ficha(sin_bloque)}["Bloque"], "—")

    def test_cuerpo_sin_metadatos_ni_historial_en_el_orden_del_formato(self):
        cuerpo = vista.cuerpo(self.doc)
        self.assertTrue(cuerpo["proposito"].startswith("Muestra en tiempo real"))
        titulos = [s["titulo"] for s in cuerpo["secciones"]]
        self.assertIn("Reglas de negocio", titulos)
        self.assertNotIn("Historial de cambios", titulos)
        self.assertNotIn("Propósito", titulos)
        reglas = next(s for s in cuerpo["secciones"] if s["titulo"] == "Reglas de negocio")
        self.assertEqual(reglas["entradas"][0], {
            "nombre": "Semáforo triage II", "texto": "Verde de 0 a 15 minutos, amarillo de 16 a 30 y rojo de 31 o más."})

    def test_historial_mas_reciente_primero(self):
        nuevo = aplicar_operaciones(self.doc, [Operacion("agregar", "Observaciones", "Otra", "Texto.")], "Cambio.",
                                    autor="Ana")
        historial = vista.historial(nuevo)
        self.assertEqual(len(historial), 2)
        self.assertIn("v2", historial[0]["nombre"])
        self.assertIn("Autor: Ana", historial[0]["texto"])

    def test_documento_interpretable_valido(self):
        datos = vista.documento("tablero_tiempos_urgencias", "TIEMPOS", "consultas_dia.md", TEXTO)
        self.assertTrue(datos["interpretable"])
        self.assertTrue(datos["valido"])
        self.assertEqual(datos["pagina"], "CONSULTAS DIA")
        self.assertEqual(datos["ruta"], "tablero_tiempos_urgencias/md/consultas_dia.md")
        self.assertEqual(datos["texto"], TEXTO)

    def test_documento_que_no_se_puede_interpretar(self):
        datos = vista.documento("g", "T", "roto.md", "sin metadatos")
        self.assertFalse(datos["interpretable"])
        self.assertFalse(datos["valido"])
        self.assertTrue(datos["errores_formato"])
        self.assertEqual(datos["ficha"], [])
        self.assertEqual(datos["texto"], "sin metadatos")
        self.assertEqual(datos["pagina"], "roto")


class Etiquetas(unittest.TestCase):
    def test_etiqueta_de_la_general_y_de_una_pagina(self):
        self.assertEqual(vista.etiqueta_pagina({"archivo": "_general.md", "pagina": "X", "bloque": "General"}),
                         "General del tablero")
        self.assertEqual(vista.etiqueta_pagina({"archivo": "c.md", "pagina": "CONSULTAS DIA",
                                                "nombre_funcional": "Oportunidad", "bloque": "Día"}),
                         "CONSULTAS DIA — Oportunidad · Día")


class Operaciones(unittest.TestCase):
    def test_describir_operaciones(self):
        self.assertEqual(vista.describir_operacion(Operacion("modificar", "Reglas de negocio", "Semáforo", "x")),
                         "Cambiar la entrada **«Semáforo»** de **Reglas de negocio**")
        self.assertEqual(vista.describir_operacion(Operacion("agregar", "Observaciones", "Nota", "x")),
                         "Agregar la entrada **«Nota»** en **Observaciones**")
        self.assertEqual(vista.describir_operacion(Operacion("eliminar", "Observaciones", "Nota")),
                         "Quitar la entrada **«Nota»** de **Observaciones**")
        self.assertEqual(vista.describir_operacion(Operacion("modificar", "propósito", "", "x")),
                         "Reescribir el **Propósito** de la página")

    def test_texto_actual_de_la_entrada_tocada(self):
        op = Operacion("modificar", "reglas de negocio", "Semáforo triage II", "nuevo")
        self.assertTrue(vista.texto_actual(TEXTO, op).startswith("Verde de 0 a 15"))
        self.assertIsNone(vista.texto_actual(TEXTO, Operacion("agregar", "Observaciones", "Nueva", "x")))
        self.assertTrue(vista.texto_actual(TEXTO, Operacion("modificar", "Propósito", "", "x")).startswith("Muestra"))
        self.assertIsNone(vista.texto_actual("roto", op))

    def test_reaplicar_actualiza_texto_diff_y_operaciones(self):
        op = Operacion("modificar", "Reglas de negocio", "Semáforo triage II", "Verde de 0 a 20 minutos.")
        despues = serializar(aplicar_operaciones(parsear(TEXTO), [op], "Resumen."))
        propuesta = Propuesta(nota="n", source_group="g", pagina="CONSULTAS DIA", operaciones=[op], resumen="Resumen.",
                              estado="lista", antes=TEXTO, despues=despues)
        corregida = vista.reaplicar(propuesta, [replace(op, texto="Verde de 0 a 25 minutos.")])
        self.assertIn("Verde de 0 a 25 minutos.", corregida.despues)
        self.assertIn("+- **Semáforo triage II**: Verde de 0 a 25 minutos.", corregida.diff)
        self.assertEqual(corregida.operaciones[0].texto, "Verde de 0 a 25 minutos.")

    def test_reaplicar_falla_si_la_entrada_no_existe(self):
        propuesta = Propuesta(nota="n", source_group="g", pagina="CONSULTAS DIA", estado="lista", antes=TEXTO)
        with self.assertRaises(ErrorOperacion):
            vista.reaplicar(propuesta, [Operacion("modificar", "Reglas de negocio", "No existe", "x")])


class Diff(unittest.TestCase):
    def test_solo_tramos_cambiados_con_una_linea_de_contexto(self):
        antes = "\n".join(f"linea {n}" for n in range(1, 21))
        despues = antes.replace("linea 5", "linea cinco").replace("linea 15\n", "")
        bloques = vista.bloques_diff(antes, despues)
        self.assertEqual(len(bloques), 2)
        primero = bloques[0]["lineas"]
        self.assertEqual(primero, [
            {"tipo": "igual", "texto": "linea 4"},
            {"tipo": "sale", "texto": "linea 5"},
            {"tipo": "entra", "texto": "linea cinco"},
            {"tipo": "igual", "texto": "linea 6"},
        ])
        self.assertIn({"tipo": "sale", "texto": "linea 15"}, bloques[1]["lineas"])

    def test_sin_diferencias(self):
        self.assertEqual(vista.bloques_diff("a\nb", "a\r\nb"), [])

    def test_lineas_cambiadas(self):
        self.assertEqual(vista.lineas_cambiadas("a\nb\nc", "a\nB\nc\nd"), (2, 1))


class TextosRevision(unittest.TestCase):
    def test_como_se_eligio(self):
        base = Propuesta(nota="n", source_group="g", pagina="A")
        self.assertEqual(vista.como_se_eligio(replace(base, metodo_pagina="indicada")),
                         "la elegiste tú en el formulario")
        self.assertIn("la nota la nombra", vista.como_se_eligio(replace(base, metodo_pagina="reglas")))
        self.assertEqual(vista.como_se_eligio(replace(base, metodo_pagina="medgemma", candidatas=["A", "B", "C"])),
                         "MedGemma la eligió entre varias parecidas (también: B, C)")
        self.assertEqual(vista.como_se_eligio(base), "")

    def test_tiempos(self):
        self.assertEqual(vista.tiempos_texto(9.84, [4.1, 5.2]),
                         "preparada en 9.8 s · 2 llamadas a MedGemma (4.1 s + 5.2 s)")
        self.assertEqual(vista.tiempos_texto(1.0, [1.5]), "preparada en 1.0 s · 1 llamada a MedGemma (1.5 s)")
        self.assertEqual(vista.tiempos_texto(None, []), "")


if __name__ == "__main__":
    unittest.main()
