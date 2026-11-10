"""
Medición de carga con N usuarios concurrentes contra MedGemma (simulado por
defecto; real solo con `--real` y confirmación escrita).

    python -m tools.carga --help
    python -m tools.carga --modo llm --rampa 1,3,5,10,20
    python -m tools.carga --modo e2e --rampa 1,3,5,10,20 --escala 0.1

Salidas (tabla + JSON) en tools/carga/salidas/ (ignorada por git).
Ver docs/arquitectura/concurrencia.md.
"""
