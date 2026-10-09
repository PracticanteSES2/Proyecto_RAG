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
"""
from tests.common.adomd import (
    AdomdConnectionException,
    AdomdErrorResponseException,
    install_adomd_modules,
    to_net,
)

from .engine import SimulatedPowerBIError


class SimulatorBackend:

    def __init__(self, simulator, culture="es-CO", net_types=True, powerbi_up=True):
        self.sim = simulator
        self.config = {"culture": culture, "net_types": net_types, "powerbi_up": powerbi_up}
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

    def execute(self, catalog, dax):
        entry = {"semantic_model": catalog, "dax": dax}
        self.log["dax"].append(entry)
        try:
            out = self.sim.execute(catalog, dax)
        except SimulatedPowerBIError as exc:
            entry.update(error=str(exc), simulator_limitation=exc.simulator_limitation,
                         type_mismatch=[], approximate=[])
            raise AdomdErrorResponseException(str(exc)) from None
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


def install(simulator, culture="es-CO", net_types=True, powerbi_up=True):
    """Registra los módulos falsos de ADOMD sobre el simulador y devuelve el backend."""
    backend = SimulatorBackend(simulator, culture=culture, net_types=net_types, powerbi_up=powerbi_up)
    install_adomd_modules(backend)
    return backend
