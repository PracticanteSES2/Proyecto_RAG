"""
Simulador de Power BI (XMLA / ADOMD) para pruebas realistas del chatbot.

  engine.PowerBISimulator  -> workspace con los modelos de data/model_metadata (+ overlay sintético)
  adomd.install(sim)       -> registra módulos falsos `clr` y `Microsoft.AnalysisServices.AdomdClient`
                              para que src/providers/powerbi_provider.py corra sin cambios
"""
from .dax_parser import DaxError, DaxUnsupported, parse_expression, parse_query
from .engine import PowerBISimulator, SimulatedPowerBIError

__all__ = ["PowerBISimulator", "SimulatedPowerBIError", "DaxError", "DaxUnsupported",
           "parse_query", "parse_expression"]
