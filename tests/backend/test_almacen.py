"""Contrato del almacén: memoria y Redis (fakeredis) se comportan igual."""
import asyncio
import time
import unittest
import uuid

from tests.backend.apoyo import almacenes


def turno_nuevo(cid, **extra):
    datos = {"turno_id": uuid.uuid4().hex, "conversacion_id": cid, "mensaje": "hola", "opcion_id": None,
             "opcion_texto": None, "via": "texto", "diagnostico": False, "cliente": "c1",
             "estado": "en_cola", "creado": "2026-11-10T10:00:00-05:00", "creado_ms": int(time.time() * 1000),
             "respuesta": None, "error": None, "snapshot": None, "calificacion": None}
    datos.update(extra)
    return datos


class ContratoAlmacen:
    modo = None

    def setUp(self):
        self.api, self.trabajador, _ = almacenes(self.modo)

    async def test_conversacion_y_candado(self):
        api = self.api
        self.assertIsNone(await api.conversacion("no-existe"))
        await api.crear_conversacion("c1", 60)
        conv = await api.conversacion("c1")
        self.assertEqual((conv["mensajes"], conv["opciones"], conv["turno_activo"]), ([], [], None))
        self.assertTrue(await api.reservar_turno("c1", "t1", 60))
        self.assertFalse(await api.reservar_turno("c1", "t2", 60))
        self.assertEqual((await api.conversacion("c1"))["turno_activo"], "t1")
        await api.liberar_reserva("c1", "t2")  # no es suyo: no libera
        self.assertFalse(await api.reservar_turno("c1", "t3", 60))
        await api.liberar_reserva("c1", "t1")
        self.assertTrue(await api.reservar_turno("c1", "t3", 60))

    async def test_cola_fifo_posicion_y_eventos(self):
        api, trabajador = self.api, self.trabajador
        await api.crear_conversacion("c1", 60)
        primero = turno_nuevo("c1")
        segundo = turno_nuevo("c1", creado_ms=primero["creado_ms"] + 5)
        self.assertTrue(await api.encolar_turno(primero, cola_max=10, ttl_s=60))
        self.assertTrue(await api.encolar_turno(segundo, cola_max=10, ttl_s=60))
        self.assertEqual(await api.posicion(segundo["turno_id"]), (2, 0))
        self.assertEqual(await api.resumen_cola(), {"en_espera": 2, "en_curso": 0})

        tomado = trabajador.tomar_turno("w1", 100)
        self.assertEqual(tomado["turno_id"], primero["turno_id"])
        self.assertIs(tomado["diagnostico"], False)
        trabajador.iniciar_turno(tomado["turno_id"])
        self.assertEqual(await api.posicion(segundo["turno_id"]), (1, 1))
        self.assertEqual((await api.turno(primero["turno_id"]))["estado"], "procesando")

        id1 = trabajador.publicar_evento(primero["turno_id"], "progreso", {"etapa": "entendiendo"})
        id2 = trabajador.publicar_evento(primero["turno_id"], "fin", {})
        eventos = await api.leer_eventos(primero["turno_id"], "0", 0)
        self.assertEqual([(e[0], e[1]) for e in eventos], [(id1, "progreso"), (id2, "fin")])
        self.assertEqual(eventos[0][2], {"etapa": "entendiendo"})
        self.assertEqual([e[1] for e in await api.leer_eventos(primero["turno_id"], id1, 0)], ["fin"])
        self.assertEqual(await api.leer_eventos(primero["turno_id"], id2, 50), [])

        await api.reservar_turno("c1", primero["turno_id"], 60)
        trabajador.terminar_turno(tomado, {"estado": "terminado", "respuesta": {"texto_markdown": "Hola"}}, 60)
        trabajador.confirmar(tomado)
        final = await api.turno(primero["turno_id"])
        self.assertEqual(final["estado"], "terminado")
        self.assertEqual(final["respuesta"], {"texto_markdown": "Hola"})
        self.assertGreater(final["terminado_ms"], 0)
        self.assertIsNone((await api.conversacion("c1"))["turno_activo"])
        self.assertEqual(await api.resumen_cola(), {"en_espera": 1, "en_curso": 0})

    async def test_fifo_con_turnos_del_mismo_milisegundo(self):
        """Regresión: dos turnos encolados en el mismo milisegundo empataban en el
        ZSET de espera y el desempate por id (aleatorio) rompía el orden FIFO."""
        if self.modo == "memoria":
            self.api._reloj = lambda: 1000.0  # todos en el mismo instante
        turnos = [turno_nuevo("c1", creado_ms=1_000_000) for _ in range(8)]
        for turno in turnos:
            self.assertTrue(await self.api.encolar_turno(turno, cola_max=20, ttl_s=60))
        posiciones = [await self.api.posicion(t["turno_id"]) for t in turnos]
        self.assertEqual(posiciones, [(n, 0) for n in range(1, 9)])
        self.assertEqual(self.trabajador.tomar_turno("w1", 100)["turno_id"], turnos[0]["turno_id"])

    async def test_cola_llena(self):
        self.assertTrue(await self.api.encolar_turno(turno_nuevo("c1"), cola_max=1, ttl_s=60))
        self.assertFalse(await self.api.encolar_turno(turno_nuevo("c1"), cola_max=1, ttl_s=60))

    async def test_tomar_sin_turnos_devuelve_none(self):
        self.assertIsNone(self.trabajador.tomar_turno("w1", 30))

    async def test_guardar_conversacion_mensajes_y_estado(self):
        api, trabajador = self.api, self.trabajador
        await api.crear_conversacion("c1", 60)
        self.assertIsNone(trabajador.cargar_estado_motor("c1"))
        trabajador.guardar_conversacion("c1", [{"id": "a"}], ["Frase"], [{"rol": "usuario", "texto": "hola"}],
                                        b"\x00estado", 60)
        trabajador.guardar_conversacion("c1", [], ["Frase", "Otra"], [{"rol": "asistente", "texto": "Hola"}],
                                        b"\x01nuevo", 60)
        conv = await api.conversacion("c1")
        self.assertEqual([m["rol"] for m in conv["mensajes"]], ["usuario", "asistente"])
        self.assertEqual((conv["opciones"], conv["frases"]), ([], ["Frase", "Otra"]))
        self.assertEqual(trabajador.cargar_estado_motor("c1"), b"\x01nuevo")
        self.assertTrue(trabajador.meta_conversacion("c1")["existe"])
        trabajador.guardar_conversacion("c1", [], [], [], None, 60)
        self.assertIsNone(trabajador.cargar_estado_motor("c1"))

    async def test_cache_y_motor(self):
        self.assertIsNone(self.trabajador.cache_leer("k"))
        self.trabajador.cache_guardar("k", {"respuesta": {"texto_markdown": "x"}}, 60)
        self.assertEqual(self.trabajador.cache_leer("k"), {"respuesta": {"texto_markdown": "x"}})
        self.trabajador.publicar_motor("latido", {"pid": 1}, 15)
        self.assertEqual(await self.api.leer_motor("latido"), {"pid": 1})
        self.assertIsNone(await self.api.leer_motor("otro"))

    async def test_limite_ventana_deslizante(self):
        api = self.api
        self.assertIsNone(await api.registrar_peticion("cli", 2, 60))
        self.assertIsNone(await api.registrar_peticion("cli", 2, 60))
        espera = await api.registrar_peticion("cli", 2, 60)
        self.assertTrue(espera is not None and 0 < espera <= 60)
        self.assertIsNone(await api.registrar_peticion("otro", 2, 60))

    async def test_calificacion_idempotente(self):
        turno = turno_nuevo("c1")
        await self.api.encolar_turno(turno, cola_max=10, ttl_s=60)
        self.assertTrue(await self.api.marcar_calificacion(turno["turno_id"], {"valor": "buena"}))
        self.assertFalse(await self.api.marcar_calificacion(turno["turno_id"], {"valor": "buena"}))
        self.assertTrue(await self.api.marcar_calificacion(turno["turno_id"], {"valor": "mala", "comentario": "x"}))


class AlmacenMemoriaTest(ContratoAlmacen, unittest.IsolatedAsyncioTestCase):
    modo = "memoria"


class AlmacenRedisTest(ContratoAlmacen, unittest.IsolatedAsyncioTestCase):
    modo = "redis"


class HuerfanosRedisTest(unittest.TestCase):
    def test_turno_de_un_trabajador_muerto_vuelve_con_xautoclaim(self):
        import fakeredis

        from backend.app.services.almacen_redis import AlmacenRedis, AlmacenTrabajadorRedis
        from backend.app.services.claves import Claves

        servidor = fakeredis.FakeServer()
        claves = Claves("prueba")
        api = AlmacenRedis(fakeredis.FakeAsyncRedis(server=servidor), claves)
        muerto = AlmacenTrabajadorRedis(fakeredis.FakeRedis(server=servidor), claves)
        turno = turno_nuevo("c1")
        asyncio.run(api.encolar_turno(turno, cola_max=10, ttl_s=60))
        self.assertEqual(muerto.tomar_turno("viejo", 50)["turno_id"], turno["turno_id"])
        nuevo = AlmacenTrabajadorRedis(fakeredis.FakeRedis(server=servidor), claves)
        huerfanos = nuevo.recuperar_huerfanos("nuevo", 0)
        self.assertEqual([h["turno_id"] for h in huerfanos], [turno["turno_id"]])
        nuevo.confirmar(huerfanos[0])
        self.assertEqual(nuevo.recuperar_huerfanos("nuevo", 0), [])


if __name__ == "__main__":
    unittest.main()
