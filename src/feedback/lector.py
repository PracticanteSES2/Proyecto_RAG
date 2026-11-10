"""Lectura de calificaciones: la última línea por ``id_turno`` manda."""
import json
from pathlib import Path

from src.feedback.registro import ruta_log


def cargar_calificaciones(ruta: Path | None = None) -> list[dict]:
    ruta = Path(ruta) if ruta else ruta_log()
    if not ruta.exists():
        return []
    ultimas: dict[str, dict] = {}
    with open(ruta, "rb") as origen:
        for linea in origen:
            try:
                registro = json.loads(linea.decode("utf-8-sig"))
            except (ValueError, RecursionError):  # JSON roto, UTF-8 inválido o anidamiento extremo
                continue
            if isinstance(registro, dict) and isinstance(registro.get("id_turno"), str) and registro["id_turno"]:
                ultimas[registro["id_turno"]] = registro
    return list(ultimas.values())
