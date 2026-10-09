"""
PowerBISimulator: workspace simulado con varios modelos semánticos.

    sim = PowerBISimulator(metadata_roots=[ROOT/"data/model_metadata",
                                           (OVERLAY, "synthetic")],
                           registry_path=ROOT/"data/catalog/model_registry.json",
                           tableros_root=ROOT/"tableros")
    sim.list_models()
    out = sim.execute("TABLERO DE ATENCIONES INSTITUCIONALES", "EVALUATE ROW(\"x\", [Total Egresos])")
    out["columns"], out["rows"], out["approximate"], out["type_mismatch"]

Los errores se lanzan como SimulatedPowerBIError con el texto que daría ADOMD
(p. ej. "Query (3, 5) Cannot find table 'X'.").
"""
import datetime as dt
import time

from .dax_eval import Evaluator, stable_fraction
from .dax_parser import DaxError, parse_expression
from .domains import DomainHarvest
from .datagen import DataGenerator
from .metadata import discover_models, key, normalize_text

DATA_START = dt.datetime(2023, 1, 1)


class SimulatedPowerBIError(Exception):
    """Error devuelto por el "servidor" (se convierte en AdomdErrorResponseException)."""

    def __init__(self, message, kind="value", simulator_limitation=False):
        super().__init__(message)
        self.kind = kind
        self.simulator_limitation = simulator_limitation


class ModelRuntime:
    """Datos + evaluador de un modelo semántico."""

    def __init__(self, schema, simulator):
        self.schema = schema
        self.sim = simulator
        self.seed = simulator.seed
        self.today = simulator.today
        self.data_range = (DATA_START, simulator.today - dt.timedelta(days=1))
        self.parsed_cache = {}
        self.generating = set()
        self.generation_notes = []
        self.log = {"approximate": [], "type_mismatch": [], "warnings": []}
        self.harvest = DomainHarvest()
        # Literales globales de los PBIR (solo valores de tablas/columnas que existan aquí)
        for (tkey, ckey), values in simulator.pbir_harvest.values.items():
            if schema.column(tkey, ckey) is not None:
                for value in values:
                    self.harvest.add(tkey, ckey, value)
        self.harvest.harvest_schema(schema)
        self._stores = {}
        self.generator = DataGenerator(self)

    # ---------- datos ----------
    def store(self, tkey):
        tkey = key(tkey)
        if tkey not in self._stores:
            if tkey not in self.schema.tables:
                raise DaxError(f"Cannot find table '{tkey}'.", "name")
            if tkey in self.generating:
                raise DaxError(f"[sim] dependencia circular generando la tabla '{tkey}'", "unsupported")
            self.generating.add(tkey)
            try:
                self._stores[tkey] = self.generator.generate(tkey)
            finally:
                self.generating.discard(tkey)
        return self._stores[tkey]

    def parsed(self, cache_key, text):
        if cache_key not in self.parsed_cache:
            try:
                self.parsed_cache[cache_key] = parse_expression(text or "")
            except DaxError as exc:
                self.parsed_cache[cache_key] = exc
        value = self.parsed_cache[cache_key]
        if isinstance(value, DaxError):
            raise value
        return value

    # ---------- registro por consulta ----------
    def warn_mismatch(self, message, column=None):
        entry = {"column": column, "message": message}
        if entry not in self.log["type_mismatch"]:
            self.log["type_mismatch"].append(entry)

    def note_approx(self, message):
        self.log["warnings"].append(message)

    def approximate_measure(self, evaluator, measure, ctx, exc):
        """Valor de respaldo determinista para medidas que el simulador no puede evaluar.

        Proporcional a las filas visibles de la tabla de la medida (respeta filtros),
        con magnitud según el nombre/formato: porcentaje, promedio, dinero o conteo.
        """
        reason = exc.message if isinstance(exc, DaxError) else str(exc)
        entry = {"measure": measure.name, "reason": reason[:240]}
        if entry not in self.log["approximate"]:
            self.log["approximate"].append(entry)
        home = self._home_table(measure)
        if home is None:
            return None
        total = self.store(home).rowcount
        visible = len(evaluator.visible_rowids(home, ctx))
        if not total or not visible:
            return None
        h = stable_fraction(self.seed, self.schema.name, measure.name)
        wiggle = stable_fraction(self.seed, measure.name, visible)
        text = normalize_text(f"{measure.name} {measure.format_string}")
        if "%" in (measure.format_string or "") or "%" in measure.name or any(
                w in text for w in ("porcentaje", "porc", "pct", "tasa", "ocupacion", "proporcion",
                                    "participacion", "cumplimiento", "inasistencia")):
            value = round(0.35 + 0.55 * h + 0.06 * (wiggle - 0.5), 4)
        elif any(w in text for w in ("promedio", "prom", "average", "tiempo", "estancia", "dias", "oportunidad",
                                     "minutos", "horas", "giro")):
            value = round((2 + 60 * h) * (0.9 + 0.2 * wiggle), 2)
        elif any(w in text for w in ("valor", "costo", "factur", "precio", "monto", "ingresos $")):
            value = round(visible * (50_000 + 500_000 * h), 0)
        else:
            value = int(round(visible * (0.4 + 0.6 * h)))
        if measure.dtype == "int" and isinstance(value, float):
            value = int(round(value))
        return value

    def _home_table(self, measure):
        candidates = [key(measure.table)] if measure.table else []
        try:
            from .dax_parser import ColRef, TableRef, walk
            tree = self.parsed(("measure", measure.table, measure.name), measure.expression)
            for node in walk(tree):
                if isinstance(node, ColRef) and node.table:
                    candidates.append(key(node.table))
                elif isinstance(node, TableRef):
                    candidates.append(key(node.name))
        except DaxError:
            pass
        for tkey in candidates:
            if tkey in self.schema.tables and self.generator.kind(tkey) not in ("calendar",):
                try:
                    if self.store(tkey).rowcount:
                        return tkey
                except DaxError:
                    continue
        return None


class PowerBISimulator:

    def __init__(self, metadata_roots, registry_path=None, tableros_root=None, today=None, seed="pbi-sim"):
        self.seed = seed
        today = today or dt.date.today()
        self.today = dt.datetime(today.year, today.month, today.day)
        self.models = discover_models(metadata_roots, registry_path)
        self.pbir_harvest = DomainHarvest()
        self.pbir_literals = self.pbir_harvest.harvest_pbir(tableros_root) if tableros_root else 0
        self._runtimes = {}

    # ---------- catálogo ----------
    def list_models(self):
        return sorted(self.models)

    def find_model(self, name):
        wanted = str(name or "").strip().casefold()
        for model in self.models:
            if model.casefold() == wanted:
                return model
        return None

    def runtime(self, name):
        model = self.find_model(name)
        if model is None:
            raise SimulatedPowerBIError(
                f"The database '{name}' was not found in the workspace, or you do not have permission "
                f"to access it.", "name")
        if model not in self._runtimes:
            self._runtimes[model] = ModelRuntime(self.models[model], self)
        return self._runtimes[model]

    # ---------- ejecución ----------
    def execute(self, model_name, dax):
        """Ejecuta una consulta DAX. Devuelve dict con columns, rows, types y registros."""
        runtime = self.runtime(model_name)
        runtime.log = {"approximate": [], "type_mismatch": [], "warnings": []}
        started = time.perf_counter()
        evaluator = Evaluator(runtime)
        try:
            columns, rows, types = evaluator.run_query(dax)
        except DaxError as exc:
            raise SimulatedPowerBIError(exc.adomd_message(), exc.kind,
                                        simulator_limitation=exc.kind == "unsupported") from exc
        except (ArithmeticError, TypeError, ValueError, AttributeError, IndexError, KeyError) as exc:
            raise SimulatedPowerBIError(f"[sim] error interno del simulador: {type(exc).__name__}: {exc}",
                                        "unsupported", simulator_limitation=True) from exc
        except RecursionError as exc:
            raise SimulatedPowerBIError("[sim] expresión demasiado anidada para el simulador", "unsupported",
                                        simulator_limitation=True) from exc
        return {
            "semantic_model": runtime.schema.name,
            "columns": columns,
            "rows": rows,
            "types": types,
            "approximate": list(runtime.log["approximate"]),
            "type_mismatch": list(runtime.log["type_mismatch"]),
            "warnings": list(runtime.log["warnings"]),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        }
