"""
Presupuesto de tiempo de seguridad para armar el plan de un turno.

El planificador (src/semantic/query_plan_builder.py) recorre dominios de
columnas, combinaciones de palabras y candidatos; un caso no previsto (un
dominio enorme en el que todo coincide) puede volverse cuadrático y dejar el
motor al 100 % de CPU durante minutos. Como la aplicación procesa un turno a
la vez, eso la bloquearía para todos.

QueryEngine abre el presupuesto al empezar cada turno (`start`) y lo cierra al
terminar (`clear`); los bucles caros del planificador llaman `check()`, que
lanza PlanBudgetExceeded si el turno pasó de PLAN_TIME_BUDGET_S segundos
(por defecto 90; 0 = sin límite). El motor convierte la excepción en una
contrapregunta («¿puedes precisar…?») en lugar de colgarse.

Es cooperativo: solo corta en los puntos que llaman `check()`. Por hilo
(threading.local), para que un turno no corte a otro.
"""
import os
import threading
import time

DEFAULT_BUDGET_S = 90.0

_STATE = threading.local()


class PlanBudgetExceeded(BaseException):
    """El armado del plan superó el presupuesto de tiempo del turno.

    Hereda de BaseException (como KeyboardInterrupt) a propósito: el
    planificador tiene muchos `except Exception` defensivos que, si la
    tragaran, dejarían seguir el bucle caro. Solo QueryEngine la captura."""

    def __init__(self, elapsed, budget, where=None):
        self.elapsed = elapsed
        self.budget = budget
        self.where = where
        super().__init__(
            f"el armado del plan superó {budget:.0f} s ({elapsed:.1f} s)"
            + (f" en {where}" if where else "")
        )


def budget_seconds():
    raw = os.getenv("PLAN_TIME_BUDGET_S")
    if raw is None or not str(raw).strip():
        return DEFAULT_BUDGET_S
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_BUDGET_S
    return max(0.0, value)


def start(seconds=None):
    """Abre el presupuesto del turno (lo reemplaza si ya había uno)."""
    seconds = budget_seconds() if seconds is None else float(seconds)
    _STATE.started = time.monotonic()
    _STATE.deadline = _STATE.started + seconds if seconds > 0 else None


def clear():
    _STATE.started = None
    _STATE.deadline = None


def active():
    return getattr(_STATE, "deadline", None) is not None


def check(where=None):
    """Lanza PlanBudgetExceeded si el turno en curso pasó su presupuesto."""
    deadline = getattr(_STATE, "deadline", None)
    if deadline is None:
        return
    now = time.monotonic()
    if now > deadline:
        started = getattr(_STATE, "started", None) or now
        raise PlanBudgetExceeded(now - started, deadline - started, where)
