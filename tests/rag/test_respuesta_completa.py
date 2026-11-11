"""
Reparación de respuestas truncadas por `num_predict` (src/chatbot/respuesta_completa.py):
corte en el último límite seguro (frase, fila de tabla, ítem de lista), cierre
de Markdown abierto, unión de una continuación y decisión de continuar según
el tiempo y la presión sobre MedGemma.

Ejecutar:
  python -X utf8 -m unittest tests.rag.test_respuesta_completa
"""
import os
import unittest
from types import MappingProxyType
from unittest import mock

from src.chatbot import respuesta_completa as R

cortar = R.cortar_en_limite_seguro


class CorteFrasesTests(unittest.TestCase):
    def test_corta_en_la_ultima_frase_completa(self):
        texto = "El indicador mide la ocupación. Se calcula dividiendo los días cama ocup"
        self.assertEqual(cortar(texto), "El indicador mide la ocupación.")

    def test_signos_de_pregunta_y_exclamacion(self):
        self.assertEqual(cortar("¿Qué mide? Mide camas. Y tambi"), "¿Qué mide? Mide camas.")

    def test_sin_frase_completa_queda_vacio(self):
        self.assertEqual(cortar("El indicador mide la ocupación de las ca"), "")

    def test_decimales_no_son_fin_de_frase(self):
        texto = "La tasa fue 4.2. El promedio es 3.5 días y el máximo 12.7"
        self.assertEqual(cortar(texto), "La tasa fue 4.2.")

    def test_numero_con_punto_al_final_no_se_da_por_completo(self):
        # «3.» puede ser el comienzo de «3.5»: nunca se muestra una cifra a medias.
        self.assertEqual(cortar("Hay datos. El valor es 3."), "Hay datos.")

    def test_abreviaturas_no_son_fin_de_frase(self):
        texto = "Lo revisa el Dr. Gómez cada mes. Incluye p. ej. urgencias y la Dra. Ruiz"
        self.assertEqual(cortar(texto), "Lo revisa el Dr. Gómez cada mes.")
        self.assertEqual(cortar("Incluye servicios, p. ej. urgencias"), "")
        self.assertEqual(cortar("Lo firma el Dr."), "")

    def test_texto_que_termina_en_salto_de_linea_esta_completo(self):
        texto = "Primera línea sin punto\nSegunda línea\n"
        self.assertEqual(cortar(texto), "Primera línea sin punto\nSegunda línea")

    def test_cierra_negrita_abierta(self):
        texto = "**Importante: se cuenta una vez. Luego se agre"
        self.assertEqual(cortar(texto), "**Importante: se cuenta una vez.**")


class CorteListasTests(unittest.TestCase):
    def test_quita_el_item_incompleto(self):
        texto = "Los filtros son:\n\n- Año.\n- Mes.\n- Servicio de hospitali"
        self.assertEqual(cortar(texto), "Los filtros son:\n\n- Año.\n- Mes.")

    def test_item_con_frase_completa_se_corta_en_ella(self):
        texto = "- **Año**: filtra por año. Permite ele"
        self.assertEqual(cortar(texto), "- **Año**: filtra por año.")

    def test_lista_numerada_y_anidada(self):
        texto = "1. Ingresos.\n   - Por **servicio**.\n   - Por `ASEGURADORA`, con el filtro de"
        self.assertEqual(cortar(texto), "1. Ingresos.\n   - Por **servicio**.")

    def test_quita_la_introduccion_que_queda_sin_lista(self):
        texto = "El tablero muestra la ocupación.\n\nSus filtros son:\n- Añ"
        self.assertEqual(cortar(texto), "El tablero muestra la ocupación.")

    def test_quita_encabezado_huerfano(self):
        texto = "Mide la ocupación.\n\n## Filtros\n\nEl filtro de a"
        self.assertEqual(cortar(texto), "Mide la ocupación.")


class CorteTablasTests(unittest.TestCase):
    TABLA = "Rangos:\n\n| Rango | Color |\n| --- | --- |\n| 0-80 % | Verde |\n| 80-90 % | Amarillo |\n"

    def test_quita_la_fila_incompleta(self):
        texto = self.TABLA + "| > 90 % | Ro"
        self.assertEqual(cortar(texto), self.TABLA.rstrip("\n"))

    def test_fila_completa_al_final_se_conserva(self):
        texto = self.TABLA + "| > 90 % | Rojo |"
        self.assertEqual(cortar(texto), self.TABLA + "| > 90 % | Rojo |")

    def test_fila_con_menos_celdas_es_incompleta(self):
        texto = self.TABLA + "| > 90 % |"
        self.assertEqual(cortar(texto), self.TABLA.rstrip("\n"))

    def test_tabla_sin_filas_de_datos_se_quita_con_su_introduccion(self):
        texto = "Mide la ocupación.\n\nRangos:\n\n| Rango | Color |\n| --- | --- |\n| 0-8"
        self.assertEqual(cortar(texto), "Mide la ocupación.")


class CorteCodigoTests(unittest.TestCase):
    def test_cierra_bloque_de_codigo_abierto(self):
        texto = "La fórmula documentada:\n\n```\nDIVIDE(\n    [Días cama ocupados],\n    [Días cam"
        self.assertEqual(
            cortar(texto),
            "La fórmula documentada:\n\n```\nDIVIDE(\n    [Días cama ocupados],\n```",
        )

    def test_cierra_codigo_en_linea(self):
        texto = "Usa la columna `ESTADO`. Filtra por `REALIZADA. Y lue"
        self.assertEqual(cortar(texto), "Usa la columna `ESTADO`. Filtra por `REALIZADA.`")


class UnionContinuacionTests(unittest.TestCase):
    def test_une_una_frase_con_espacio(self):
        self.assertEqual(R.unir_continuacion("Mide camas.", "Se calcula por día."),
                         "Mide camas. Se calcula por día.")

    def test_une_un_bloque_en_linea_nueva(self):
        self.assertEqual(R.unir_continuacion("- Año.\n- Mes.", "- Servicio."), "- Año.\n- Mes.\n- Servicio.")

    def test_tabla_tras_parrafo_va_separada(self):
        self.assertEqual(R.unir_continuacion("Rangos:", "| A | B |\n| --- | --- |"),
                         "Rangos:\n\n| A | B |\n| --- | --- |")

    def test_no_repite_lineas_ya_escritas(self):
        previo = "| Rango | Color |\n| --- | --- |\n| 0-80 % | Verde |"
        continuacion = "| Rango | Color |\n| --- | --- |\n| 80-90 % | Amarillo |"
        self.assertEqual(R.unir_continuacion(previo, continuacion), previo + "\n| 80-90 % | Amarillo |")


class DecisionContinuarTests(unittest.TestCase):
    LIBRE = MappingProxyType({"in_flight": 0, "waiting": 0, "capacity": 3, "saturated_recent": 0})

    def _decidir(self, presion=None, **kwargs):
        datos = {"transcurrido_s": 10.0, "presupuesto_s": 40.0, "tokens_generados": 600,
                 "tokens_continuacion": 200, **kwargs}
        return R.decidir_continuacion(presion=presion or self.LIBRE, **datos)

    def test_continua_con_tiempo_y_servidor_libre(self):
        ok, motivo = self._decidir()
        self.assertTrue(ok, motivo)

    def test_no_continua_si_hay_fila(self):
        ok, motivo = self._decidir(presion=dict(self.LIBRE, waiting=2))
        self.assertFalse(ok)
        self.assertIn("fila", motivo)

    def test_no_continua_si_el_servidor_esta_lleno_o_se_saturo(self):
        self.assertFalse(self._decidir(presion=dict(self.LIBRE, in_flight=3))[0])
        self.assertFalse(self._decidir(presion=dict(self.LIBRE, saturated_recent=1))[0])

    def test_no_continua_sin_tiempo(self):
        # 600 tokens en 30 s = 20 tok/s → 200 tokens ≈ 10 s (+ margen) > 10 s restantes.
        ok, motivo = self._decidir(transcurrido_s=30.0)
        self.assertFalse(ok)
        self.assertIn("tiempo", motivo)

    def test_sin_limite_de_tiempo_decide_solo_la_presion(self):
        self.assertTrue(self._decidir(presupuesto_s=None)[0])

    def test_se_puede_desactivar(self):
        with mock.patch.dict(os.environ, {"RAG_CONTINUAR_TRUNCADA": "0"}):
            self.assertFalse(self._decidir()[0])


class AvisoTests(unittest.TestCase):
    def test_linea_discreta_con_y_sin_enlace(self):
        con = R.linea_aviso({"url": "https://app.powerbi.com/groups/x/reports/y"})
        self.assertIn("La respuesta completa está en el tablero", con)
        self.assertIn("(https://app.powerbi.com/groups/x/reports/y)", con)
        sin = R.linea_aviso(None)
        self.assertIn("La respuesta completa está en el tablero", sin)
        self.assertNotIn("http", sin)
        for texto in (con, sin):
            self.assertNotRegex(texto.lower(), r"token|num_predict|trunc|llm")


if __name__ == "__main__":
    unittest.main()
