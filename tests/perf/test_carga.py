"""
Herramienta de medición de carga (tools/carga) con el servidor SIMULADO.

    .venv\\Scripts\\python.exe -X utf8 -m unittest tests.perf.test_carga

No usa red, .env, Ollama ni Power BI (el modo e2e corre en otro proceso con el
motor del simulador de tests/sim).
"""
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if "dotenv" not in sys.modules:
    _dotenv = types.ModuleType("dotenv")
    _dotenv.load_dotenv = lambda *a, **k: False
    _dotenv.find_dotenv = lambda *a, **k: ""
    _dotenv.__sim_fake__ = True
    sys.modules["dotenv"] = _dotenv

from tools.carga import metricas  # noqa: E402
from tools.carga.simulador import ProveedorSimulado, ServidorConfig, ServidorSimulado  # noqa: E402

MESSAGES = [{"role": "user", "content": "x" * 400}]


class MetricasTests(unittest.TestCase):
    def test_percentiles(self):
        values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        self.assertAlmostEqual(metricas.percentil(values, 50), 5.5)
        self.assertAlmostEqual(metricas.percentil(values, 95), 9.55)
        self.assertIsNone(metricas.percentil([], 50))
        self.assertEqual(metricas.percentil([3], 95), 3)

    def test_resumen_llamadas(self):
        calls = [
            {"status": "success", "latency_s": 1.0, "ttft_s": 0.2, "truncated": False},
            {"status": "success", "latency_s": 3.0, "ttft_s": 0.4, "truncated": True},
            {"status": "llm_saturated", "latency_s": 0.1},
            {"status": "llm_timeout", "latency_s": 5.0},
            {"status": "ollama_error", "latency_s": 0.0},
        ]
        summary = metricas.resumen_llamadas(calls, wall_s=10.0)
        self.assertEqual(summary["n"], 5)
        self.assertEqual(summary["ok"], 2)
        self.assertAlmostEqual(summary["tasa_saturadas"], 0.2)
        self.assertAlmostEqual(summary["tasa_tiempo_agotado"], 0.2)
        self.assertAlmostEqual(summary["tasa_error"], 0.2)
        self.assertAlmostEqual(summary["tasa_truncadas"], 0.5)  # sobre las exitosas
        self.assertAlmostEqual(summary["latencia_p50_s"], 2.0)  # solo exitosas
        self.assertAlmostEqual(summary["throughput_ok_por_min"], 12.0)
        self.assertAlmostEqual(summary["ttft_p50_s"], 0.3)


class SimuladorTests(unittest.TestCase):
    def config(self, **kwargs):
        base = dict(num_parallel=2, gen_tps=200.0, prompt_tps=10000.0, degradacion=0.0,
                    largo_min=0.5, largo_max=0.5, escala=0.1)
        base.update(kwargs)
        return ServidorConfig(**base)

    def test_capacity_limits_active_generations(self):
        server = ServidorSimulado(self.config())
        provider = ProveedorSimulado(server)
        results = []
        threads = [threading.Thread(target=lambda: results.append(provider.chat(MESSAGES, max_tokens=100)))
                   for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(10)
        snap = server.snapshot()
        self.assertEqual(snap["max_active"], 2)
        self.assertGreaterEqual(snap["max_queued"], 1)
        self.assertEqual(len([r for r in results if r["status"] == "success"]), 5)
        self.assertTrue(all(r["ttft_s"] is not None for r in results))

    def test_full_queue_answers_503(self):
        server = ServidorSimulado(self.config(num_parallel=1, max_queue=1, gen_tps=5.0))
        provider = ProveedorSimulado(server)
        results = []
        barrier = threading.Barrier(4)

        def run():
            barrier.wait()
            results.append(provider.chat(MESSAGES, max_tokens=50))

        threads = [threading.Thread(target=run) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(20)
        rejected = [r for r in results if r["status"] == "ollama_error"]
        self.assertTrue(rejected, results)
        self.assertEqual(rejected[0]["status_code"], 503)

    def test_client_timeout_cancels_and_frees_the_slot(self):
        server = ServidorSimulado(self.config(num_parallel=1, gen_tps=10.0))
        provider = ProveedorSimulado(server)
        result = provider.chat(MESSAGES, max_tokens=500, timeout=0.05)
        self.assertEqual(result["status"], "llm_timeout")
        snap = server.snapshot()
        self.assertEqual(snap["active"], 0)
        self.assertEqual(snap["cancelled_generating"] + snap["cancelled_queued"], 1)

    def test_answers_that_reach_num_predict_are_truncated(self):
        server = ServidorSimulado(self.config(largo_min=1.5, largo_max=1.5))
        result = ProveedorSimulado(server).chat(MESSAGES, max_tokens=40)
        self.assertEqual(result["done_reason"], "length")
        self.assertTrue(result["truncated"])
        short = ProveedorSimulado(ServidorSimulado(self.config())).chat(MESSAGES, max_tokens=40)
        self.assertFalse(short["truncated"])

    def test_concurrency_slows_each_generation(self):
        alone = ServidorSimulado(self.config(num_parallel=4, gen_tps=20.0, degradacion=1.0))
        started = time.perf_counter()
        ProveedorSimulado(alone).chat(MESSAGES, max_tokens=100)
        single = time.perf_counter() - started
        crowded = ServidorSimulado(self.config(num_parallel=4, gen_tps=20.0, degradacion=1.0))
        provider = ProveedorSimulado(crowded)
        durations = []
        barrier = threading.Barrier(4)

        def run():
            barrier.wait()
            t0 = time.perf_counter()
            provider.chat(MESSAGES, max_tokens=100)
            durations.append(time.perf_counter() - t0)

        threads = [threading.Thread(target=run) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(10)
        self.assertGreater(min(durations), single * 2)


class RunnerLLMTests(unittest.TestCase):
    def test_llm_ramp_reports_saturation_only_above_capacity(self):
        from tools.carga import runner
        report = runner.correr(
            modo="llm", rampa=[1, 3, 6], turnos=1, perfil="sintesis",
            servidor=ServidorConfig(num_parallel=3, gen_tps=60.0, prompt_tps=20000.0, degradacion=0.0,
                                    largo_min=0.5, largo_max=0.5, escala=0.02),
            max_concurrent=3, espera_cola=0.5, log=None,
        )
        levels = {level["usuarios"]: level for level in report["niveles"]}
        self.assertEqual(levels[1]["llamadas"]["tasa_saturadas"], 0.0)
        self.assertEqual(levels[3]["llamadas"]["tasa_saturadas"], 0.0)
        self.assertGreater(levels[6]["llamadas"]["tasa_saturadas"], 0.0)
        self.assertIn("latencia_p95_s", levels[6]["llamadas"])
        self.assertIn("turnos", levels[6])

    def test_ui_wait_turns_saturation_into_waiting(self):
        from tools.carga import runner
        report = runner.correr(
            modo="llm", rampa=[6], turnos=1, perfil="sintesis",
            servidor=ServidorConfig(num_parallel=3, gen_tps=60.0, prompt_tps=20000.0, degradacion=0.0,
                                    largo_min=0.5, largo_max=0.5, escala=0.02),
            max_concurrent=3, espera_cola=0.5, espera_ui=60.0, log=None,
        )
        calls = report["niveles"][0]["llamadas"]
        self.assertEqual(calls["tasa_saturadas"], 0.0)
        self.assertEqual(calls["ok"], 6)

    def test_probe_reveals_server_parallelism_without_gate(self):
        from tools.carga import runner
        report = runner.correr(
            modo="llm", rampa=[5], turnos=1, perfil="sonda", sin_puerta=True,
            servidor=ServidorConfig(num_parallel=2, gen_tps=40.0, prompt_tps=20000.0, degradacion=0.0,
                                    escala=0.05), log=None,
        )
        par = report["niveles"][0]["llamadas"]["paralelismo_observado"]
        self.assertEqual(par["generando_max"], 2)
        self.assertEqual(par["en_servidor_max"], 5)

    def test_ramp_stops_when_errors_exceed_threshold(self):
        from tools.carga import runner
        report = runner.correr(
            modo="llm", rampa=[1, 4, 8], turnos=1, perfil="sonda", sin_puerta=True, parar_si_error=0.3,
            servidor=ServidorConfig(num_parallel=1, max_queue=1, gen_tps=40.0, prompt_tps=20000.0, escala=0.05),
            log=None,
        )
        self.assertEqual([level["usuarios"] for level in report["niveles"]], [1, 4])
        self.assertIn("detenido", report["niveles"][-1])

    def test_table_and_json_output(self):
        from tools.carga import runner
        report = runner.correr(
            modo="llm", rampa=[1, 2], turnos=1, perfil="mixto",
            servidor=ServidorConfig(gen_tps=400.0, prompt_tps=50000.0, escala=0.01), log=None,
        )
        table = runner.tabla(report)
        self.assertIn("usuarios", table)
        self.assertIn("p95", table)
        with tempfile.TemporaryDirectory() as tmp:
            path = runner.guardar(report, Path(tmp), etiqueta="prueba")
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            self.assertEqual(data["config"]["modo"], "llm")
            self.assertEqual([level["usuarios"] for level in data["niveles"]], [1, 2])


class RunnerComponentesTests(unittest.TestCase):
    """Modo `componentes`: síntesis y opciones reales con la caché del motor."""

    FAST = dict(gen_tps=2000.0, prompt_tps=500000.0, escala=0.01, largo_max=0.9)

    def _run(self, **kwargs):
        from tools.carga import runner
        return runner.correr(modo="componentes", rampa=[6], turnos=4, perfil="mixto",
                             servidor=ServidorConfig(**self.FAST), log=None, banco=5, **kwargs)

    def test_palancas_reducen_las_llamadas_por_turno(self):
        antes = self._run(sin_palancas=True)["niveles"][0]
        despues = self._run()["niveles"][0]
        self.assertGreater(antes["costo"]["calls_por_turno"], despues["costo"]["calls_por_turno"])
        self.assertGreater(despues["costo"]["cache"]["hits"] + despues["costo"]["cache"]["shared"], 0)
        self.assertEqual(antes["costo"]["cache"]["hits"], 0)
        self.assertIn("redactadas_por_min", despues["turnos"])
        self.assertGreater(despues["costo"]["prompt_tokens_est_por_turno"], 0)

    def test_sin_palancas_no_deja_la_cache_apagada(self):
        self._run(sin_palancas=True)
        self.assertNotEqual(os.environ.get("LLM_CACHE"), "off")


class CapasYSalidasTests(unittest.TestCase):
    def test_salidas_en_var_out_carga(self):
        from src.comun.rutas import ruta_salida
        from tools.carga import runner
        self.assertEqual(runner.SALIDAS, ruta_salida("carga"))

    def test_tools_carga_no_importa_tests(self):
        import ast
        for path in (ROOT / "tools" / "carga").glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = ([alias.name for alias in node.names] if isinstance(node, ast.Import)
                         else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
                for name in names:
                    self.assertFalse(name == "tests" or name.startswith("tests."), f"{path.name}: {name}")


class CliTests(unittest.TestCase):
    def test_real_without_confirmation_makes_no_call(self):
        from tools.carga import __main__ as cli
        created = []
        original = cli.crear_proveedor_real
        cli.crear_proveedor_real = lambda streaming=False: created.append(1)
        try:
            out = io.StringIO()
            with redirect_stdout(out):
                code = cli.main(["--real", "--modo", "llm", "--rampa", "1"], entrada=lambda prompt: "no")
        finally:
            cli.crear_proveedor_real = original
        self.assertNotEqual(code, 0)
        self.assertEqual(created, [])
        self.assertIn("servidor compartido", out.getvalue().lower())

    def test_real_eof_on_confirmation_aborts(self):
        from tools.carga import __main__ as cli

        def eof(prompt):
            raise EOFError

        created = []
        original = cli.crear_proveedor_real
        cli.crear_proveedor_real = lambda streaming=False: created.append(1)
        try:
            with redirect_stdout(io.StringIO()):
                code = cli.main(["--real", "--rampa", "1"], entrada=eof)
        finally:
            cli.crear_proveedor_real = original
        self.assertNotEqual(code, 0)
        self.assertEqual(created, [])

    def test_e2e_cli_in_subprocess_writes_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            completed = subprocess.run(
                [sys.executable, "-X", "utf8", "-m", "tools.carga", "--modo", "e2e", "--rampa", "1,3",
                 "--turnos", "1", "--escala", "0.02", "--salida", tmp, "--etiqueta", "prueba"],
                cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
                env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8"), timeout=600,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout[-2000:] + completed.stderr[-3000:])
            files = list(Path(tmp).glob("*.json"))
            self.assertEqual(len(files), 1, completed.stdout)
            data = json.loads(files[0].read_text(encoding="utf-8"))
            levels = {level["usuarios"]: level for level in data["niveles"]}
            self.assertEqual(sorted(levels), [1, 3])
            turns = levels[3]["turnos"]
            self.assertEqual(turns["n"], 3)
            self.assertIn("espera_turno_p95_s", turns)
            self.assertIn("tasa_ocupado", turns)
            self.assertIn("tasa_respaldo_extractivo", turns)
            # Un turno a la vez: con 3 usuarios alguien tuvo que esperar su turno.
            self.assertGreater(turns["espera_turno_max_s"], 0.0)
            self.assertIn("usuarios", completed.stdout)


if __name__ == "__main__":
    unittest.main()
