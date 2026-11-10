"""Reglas del perfil backend: una función `revisar(repo) -> list[Hallazgo]` por categoría."""
from tools.doctor.reglas import capas, duplicacion, estructura, fastapi, higiene, muerto, pruebas, tamano

TODAS = {
    "estructura": estructura.revisar,
    "tamano": tamano.revisar,
    "duplicacion": duplicacion.revisar,
    "muerto": muerto.revisar,
    "capas": capas.revisar,
    "pruebas": pruebas.revisar,
    "higiene": higiene.revisar,
    "fastapi": fastapi.revisar,
}
