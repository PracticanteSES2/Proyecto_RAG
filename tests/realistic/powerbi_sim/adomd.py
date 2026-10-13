"""
Conecta el PowerBISimulator al cliente ADOMD falso compartido (tests/common/adomd.py).

    from tests.realistic.powerbi_sim import adomd
    backend = adomd.install(simulator, culture="es-CO")
    # ... PowerBIProvider() real funciona sin cambios ...
    backend.log["dax"]   # cada consulta: semantic_model, dax, rows, result, error, approximate, type_mismatch

Configuración (backend.config):
  powerbi_up  False => Open() falla como un endpoint XMLA caído.
  culture     "es-CO" (por defecto, cultura del Windows del proyecto), "en-US" o "invariant":
              cómo pythonnet convierte System.DateTime / System.Decimal a texto.
  net_types   False => entrega datetime/Decimal de Python (sin emular .NET).
  latency_ms  espera artificial por consulta DAX (por defecto SIM_DAX_LATENCY_MS o 0) para
              reproducir el coste de Power BI real (~300-1500 ms por consulta XMLA).
  cost_model  True (por defecto SIM_DAX_COST=1) => modelo de coste de Power BI real
              (powerbi_sim/cost.py): cada consulta del registro trae `cost_ms` (latencia base +
              coste por cardinalidad de las columnas de VALUES + filas devueltas) y
              `cost_detail`; la espera (solo si latency_ms > 0) dura ese coste, y un
              AdomdCommand.CommandTimeout menor que el coste cancela la consulta con el error de
              tiempo de ADOMD (también sin dormir: así tests/perf/medir_consultas reproduce las
              consultas canceladas sin esperar).
"""
import os
import time

from tests.common.adomd import (
    AdomdConnectionException,
    AdomdErrorResponseException,
    install_adomd_modules,
    to_net,
)

from .cost import CostModel, cost_model_enabled
from .engine import SimulatedPowerBIError

TIMEOUT_MESSAGE = ("XML for Analysis request timed out before it was completed. "
                   "(simulador: coste estimado {cost:.1f} s > CommandTimeout {timeout:.0f} s)")


class SimulatorBackend:

    supports_timeout = True   # recibe AdomdCommand.CommandTimeout (tests/common/adomd.py)

    def __init__(self, simulator, culture="es-CO", net_types=True, powerbi_up=True, latency_ms=None,
                 cost_model=None):
        self.sim = simulator
        if latency_ms is None:
            try:
                latency_ms = float(os.getenv("SIM_DAX_LATENCY_MS") or 0)
            except ValueError:
                latency_ms = 0.0
        if cost_model is None:
            cost_model = cost_model_enabled()
        self.config = {"culture": culture, "net_types": net_types, "powerbi_up": powerbi_up,
                       "latency_ms": float(latency_ms), "cost_model": bool(cost_model)}
        self.costs = CostModel(simulator)
        self.log = {"dax": []}

    def reset_log(self):
        self.log["dax"] = []
        return self.log

    def open(self, catalog):
        if not self.config["powerbi_up"]:
            raise AdomdConnectionException(
                "A connection cannot be made. Ensure that the server is running. (simulador: Power BI caído)")
        if catalog and self.sim.find_model(catalog) is None:
            raise AdomdErrorResponseException(
                f"The database '{catalog}' was not found in the workspace, or you do not have permission to "
                f"access it.")

    def catalogs(self):
        return self.sim.list_models()

    def _cost(self, catalog, dax, rows_returned):
        latency = self.config.get("latency_ms") or 0.0
        return self.costs.estimate(catalog, dax, rows_returned, base_ms=latency or None)

    def execute(self, catalog, dax, timeout_s=None):
        entry = {"semantic_model": catalog, "dax": dax}
        self.log["dax"].append(entry)
        if timeout_s:
            entry["timeout_s"] = float(timeout_s)
        latency = self.config.get("latency_ms") or 0.0
        modeled = bool(self.config.get("cost_model"))
        if latency and not modeled:
            time.sleep(latency / 1000.0)   # latencia simulada de XMLA
            entry["latency_ms"] = latency
        try:
            out = self.sim.execute(catalog, dax)
        except SimulatedPowerBIError as exc:
            entry.update(error=str(exc), simulator_limitation=exc.simulator_limitation,
                         type_mismatch=[], approximate=[])
            if modeled:
                cost = self._cost(catalog, dax, 0)
                entry.update(cost_ms=cost["cost_ms"], cost_detail=cost["detail"])
                if latency:
                    time.sleep(cost["cost_ms"] / 1000.0)
            raise AdomdErrorResponseException(str(exc)) from None
        if modeled:
            cost = self._cost(catalog, dax, len(out["rows"]))
            seconds = cost["cost_ms"] / 1000.0
            entry.update(cost_ms=cost["cost_ms"], cost_detail=cost["detail"])
            if timeout_s and seconds > float(timeout_s):
                # ADOMD cancela la consulta al vencer CommandTimeout: el cliente esperó el límite.
                if latency:
                    time.sleep(float(timeout_s))
                entry.update(error="timeout", timed_out=True, cost_ms=float(timeout_s) * 1000.0,
                             cost_ms_sin_limite=cost["cost_ms"], type_mismatch=[], approximate=[])
                raise AdomdConnectionException(TIMEOUT_MESSAGE.format(cost=seconds, timeout=float(timeout_s)))
            if latency:
                time.sleep(seconds)
                entry["latency_ms"] = cost["cost_ms"]
        rows = [[to_net(v, self.config["culture"], self.config["net_types"]) for v in row] for row in out["rows"]]
        entry.update(
            rows=len(rows),
            result=[list(r) for r in out["rows"][:50]],
            columns=out["columns"],
            approximate=out["approximate"],
            type_mismatch=[m["message"] for m in out["type_mismatch"]],
            warnings=out["warnings"],
            elapsed_ms=out["elapsed_ms"],
        )
        return out["columns"], rows


def install(simulator, culture="es-CO", net_types=True, powerbi_up=True, latency_ms=None, cost_model=None):
    """Registra los módulos falsos de ADOMD sobre el simulador y devuelve el backend."""
    backend = SimulatorBackend(simulator, culture=culture, net_types=net_types, powerbi_up=powerbi_up,
                               latency_ms=latency_ms, cost_model=cost_model)
    install_adomd_modules(backend)
    return backend
