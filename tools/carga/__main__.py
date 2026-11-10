"""
Prueba de carga: N usuarios concurrentes (rampa) contra MedGemma.

Por defecto usa un servidor Ollama SIMULADO en proceso (capacidad, cola,
velocidad y degradación configurables): no sale nada a la red.

    python -m tools.carga --modo llm --rampa 1,3,5,10,20
    python -m tools.carga --modo e2e --rampa 1,3,5,10,20 --escala 0.1
    python -m tools.carga --modo llm --perfil sintesis --espera-ui 30   # cola con progreso

Modo real (servidor COMPARTIDO del hospital; pide confirmación escrita):

    python -m tools.carga --real --modo llm --rampa 1,2,3,4,5 --turnos 1 --perfil sintesis --streaming

Modos:
  llm  llamadas representativas (síntesis RAG, reescritura, descripción de
       opciones) por la puerta src/llm/llm_gate.py, sin el resto del motor.
  e2e  turnos completos por el motor del simulador (tests/sim: Power BI y
       Qdrant falsos), con el turno compartido de app.py (turn_slot). Con
       --real solo el LLM es real; Power BI sigue simulado.
"""
import argparse
import sys
import types
from pathlib import Path

from tools.carga.proveedores import crear_proveedor_real
from tools.carga.simulador import ServidorConfig

CONFIRMACION = "SI"


def _rampa(text):
    values = [int(v) for v in str(text).replace(" ", "").split(",") if v]
    if not values or any(v < 1 for v in values):
        raise argparse.ArgumentTypeError("rampa: enteros positivos separados por comas (p. ej. 1,3,5,10,20)")
    return values


def parser():
    p = argparse.ArgumentParser(prog="python -m tools.carga", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--modo", choices=("llm", "e2e"), default="llm")
    p.add_argument("--rampa", type=_rampa, default=[1, 3, 5, 10, 20], help="usuarios simultáneos por nivel")
    p.add_argument("--turnos", type=int, default=2, help="turnos por usuario en cada nivel")
    p.add_argument("--perfil", choices=("sonda", "sintesis", "seguimiento", "opciones", "mixto"), default="mixto",
                   help="modo llm: tipo de turno (mixto = 45%% síntesis, 15%% seguimiento, 20%% opciones, "
                        "20%% Power BI; sonda = petición corta de 64 tokens fijos para medir la capacidad)")
    p.add_argument("--parar-si-error", type=float, default=0.3,
                   help="detiene la rampa si la tasa de error + tiempo agotado de un escalón la supera")
    p.add_argument("--pausa", type=float, default=0.0, help="segundos entre turnos de un mismo usuario")
    p.add_argument("--semilla", type=int, default=7)
    g = p.add_argument_group("puerta y turno (por defecto, los valores de la app)")
    g.add_argument("--max-concurrent", type=int, default=None, help="MEDGEMMA_MAX_CONCURRENT (3)")
    g.add_argument("--espera-cola", type=float, default=None, help="MEDGEMMA_QUEUE_WAIT en s (3)")
    g.add_argument("--espera-ui", type=float, default=None,
                   help="activa ui_progress con esta espera (s): cola visible en lugar de saturar")
    g.add_argument("--espera-turno", type=float, default=120.0, help="TURN_WAIT_SECONDS (e2e)")
    g.add_argument("--sin-puerta", action="store_true", help="modo llm: llama al proveedor sin la puerta")
    s = p.add_argument_group("servidor simulado (supuestos; calíbralos con una corrida real de 1 usuario)")
    s.add_argument("--capacidad", type=int, default=3, help="OLLAMA_NUM_PARALLEL")
    s.add_argument("--cola-max", type=int, default=512, help="OLLAMA_MAX_QUEUE (503 al llenarse)")
    s.add_argument("--tps", type=float, default=20.0, help="tokens/s de generación de una petición sola")
    s.add_argument("--prompt-tps", type=float, default=1500.0, help="tokens/s de evaluación del prompt")
    s.add_argument("--degradacion", type=float, default=0.5,
                   help="cuánto se frena cada generación por cada otra simultánea")
    s.add_argument("--largo-min", type=float, default=0.3, help="largo natural mínimo (fracción de max_tokens)")
    s.add_argument("--largo-max", type=float, default=1.1, help="largo natural máximo (>1 = algunas se truncan)")
    s.add_argument("--num-ctx", type=int, default=4096)
    s.add_argument("--escala", type=float, default=0.05, help="acelera el tiempo simulado (1 = tiempo real)")
    r = p.add_argument_group("modo real")
    r.add_argument("--real", action="store_true", help="usa el MedGemma REAL del .env (pide confirmación)")
    r.add_argument("--streaming", action="store_true", help="con --real: mide el primer token (stream=True)")
    o = p.add_argument_group("salida")
    o.add_argument("--salida", default=None, help="carpeta de salida (por defecto tools/carga/salidas)")
    o.add_argument("--etiqueta", default=None, help="sufijo del archivo JSON")
    return p


def _estimar_llamadas(args):
    from tools.carga import escenarios
    if args.modo == "e2e":
        per_turn = 1.25  # mitad síntesis, un cuarto opciones (3 llamadas), un cuarto sin LLM
    elif args.perfil == "mixto":
        per_turn = sum(len(sum(escenarios.TURNOS[name], [])) * w for name, w in escenarios.MIXTO)
    else:
        per_turn = len(sum(escenarios.TURNOS[args.perfil], []))
    return int(round(sum(args.rampa) * args.turnos * per_turn))


def confirmar_real(args, entrada=input):
    print("=" * 78)
    print("ATENCIÓN: prueba de carga contra el servidor COMPARTIDO del hospital (MedGemma real).")
    print("Otras aplicaciones y personas usan ese servidor: mientras corre, sus respuestas")
    print("pueden ir más lentas. Hazlo solo con permiso y en un horario de poca carga.")
    print(f"  modo={args.modo} rampa={args.rampa} turnos/usuario={args.turnos} perfil={args.perfil}")
    print(f"  llamadas estimadas: ~{_estimar_llamadas(args)} (máximo {max(args.rampa)} usuarios a la vez)")
    if args.modo == "e2e":
        print("  Power BI NO se toca: el motor es el del simulador (tests/sim); solo el LLM es real.")
    print("=" * 78)
    try:
        answer = entrada(f"Escribe {CONFIRMACION} para continuar: ")
    except (EOFError, KeyboardInterrupt):
        answer = ""
    return str(answer or "").strip() == CONFIRMACION


def _dotenv_inerte():
    """Sin --real nada debe leer el .env (load_dotenv() sube por las carpetas y
    encontraría el del proyecto): dotenv falso antes de importar src.*."""
    if "dotenv" in sys.modules:
        return
    module = types.ModuleType("dotenv")
    module.load_dotenv = lambda *a, **k: False
    module.find_dotenv = lambda *a, **k: ""
    module.dotenv_values = lambda *a, **k: {}
    module.__sim_fake__ = True
    sys.modules["dotenv"] = module


def main(argv=None, entrada=input):
    args = parser().parse_args(argv)
    provider = None
    if not args.real:
        _dotenv_inerte()
    if args.real:
        if not confirmar_real(args, entrada=entrada):
            print("Cancelado: no se hizo ninguna llamada.")
            return 2
        provider = crear_proveedor_real(streaming=args.streaming)
        print(f"Servidor: {getattr(provider, 'host', '?')} · modelo {getattr(provider, 'model', '?')}")
        health = provider.healthcheck()
        if health.get("status") != "ready":
            print(f"El servidor no está listo ({health.get('status')}): no se corre la prueba.")
            return 3
    from tools.carga import runner

    servidor = ServidorConfig(
        num_parallel=args.capacidad, max_queue=args.cola_max, prompt_tps=args.prompt_tps, gen_tps=args.tps,
        degradacion=args.degradacion, largo_min=args.largo_min, largo_max=args.largo_max,
        num_ctx=args.num_ctx, escala=args.escala, semilla=args.semilla,
    )
    print(" | ".join(name.rjust(width) for name, width in runner.COLUMNAS))
    report = runner.correr(
        modo=args.modo, rampa=args.rampa, turnos=args.turnos, perfil=args.perfil, servidor=servidor,
        max_concurrent=args.max_concurrent, espera_cola=args.espera_cola, espera_ui=args.espera_ui,
        espera_turno=args.espera_turno, sin_puerta=args.sin_puerta, pausa=args.pausa, semilla=args.semilla,
        proveedor=provider, real=args.real, log=print, parar_si_error=args.parar_si_error,
    )
    print()
    print(runner.tabla(report))
    path = runner.guardar(report, Path(args.salida) if args.salida else None, etiqueta=args.etiqueta)
    print(f"\nJSON: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
