"""Motor doble para las pruebas del backend: imita la forma de QueryEngine
(estado por conversación en una EstadoConversacion pasada con `sesion=`, con
el mismo andamiaje de src/chatbot/sesion_motor.py; oyente de progreso,
contrapreguntas, seguimientos) sin MiniLM, Qdrant, Power BI ni MedGemma.

Guion por texto del mensaje:
- «hola»                         → portero (ruta conversacion)
- «cirugias 2024»                → contrapregunta con dos opciones (deja _pending_query_plan)
- opción elegida                 → dato de Power BI (deja _last_success)
- «y en 2025?»                   → seguimiento: usa _last_success o no entiende
- «documentacion»                → RAG redactado · «documentacion saturada» → RAG extractivo (degradado)
- «explota»                      → excepción · «lento» → tarda `demora_s` con actividades
- cualquier otro texto           → dato de Power BI «Total atenciones»
"""
from __future__ import annotations

import threading
import time
from types import SimpleNamespace

from backend.app.services.motor import InstanciaMotor, PiscinaMotores
from src.chatbot.sesion_motor import SesionMotorMixin, con_sesion


class GestorDoble:
    def __init__(self):
        self.state = SimpleNamespace(awaiting_clarification=False)
        self.candidate_dashboards = []

    def reset(self):
        self.state = SimpleNamespace(awaiting_clarification=False)
        self.candidate_dashboards = []


class MotorDoble(SesionMotorMixin):
    def __init__(self, demora_s: float = 0.0):
        self.demora_s = demora_s
        self.powerbi_provider = None
        self.source_router = None
        self.llamadas = []
        self.concurrentes = 0
        self.max_concurrentes = 0
        self._candado = threading.Lock()

    # --- API de QueryEngine que usa el backend ---------------------------
    # set_progress_listener, reset y conversation_history: SesionMotorMixin.

    def _avisar(self, titulo):
        if self.progress_listener:
            self.progress_listener({"kind": "activity", "title": titulo, "t": 0.1, "lines": []})

    def _razonamiento(self, texto):
        return {"kind": "question", "text": texto, "steps": [{"t": 0.01, "title": "Pregunta", "lines": [texto]}],
                "server_state": "encendido hace 1 s"}

    def _entrar(self):
        with self._candado:
            self.concurrentes += 1
            self.max_concurrentes = max(self.max_concurrentes, self.concurrentes)

    def _salir(self):
        with self._candado:
            self.concurrentes -= 1

    @con_sesion
    def process(self, texto, on_token=None):
        self._entrar()
        try:
            self.llamadas.append(("process", texto))
            resultado = self._responder(texto.strip().lower())
            if on_token and resultado.get("route") == "rag":
                for trozo in ("El tablero ", "muestra la ocupación."):
                    on_token(trozo)
            resultado.setdefault("reasoning", self._razonamiento(texto))
            self.last_reasoning = resultado["reasoning"]
            self.conversation_memory.record(texto, resultado)
            return resultado
        finally:
            self._salir()

    @con_sesion
    def select_clarification_option(self, opcion_id, etiqueta=None):
        self._entrar()
        try:
            self.llamadas.append(("opcion", opcion_id))
            if not self._pending_query_plan:
                return {"status": "metric_not_resolved", "route": "powerbi", "answer": "No hay nada pendiente."}
            self._pending_query_plan = None
            self._last_success = {"metric": etiqueta or opcion_id, "year": 2024}
            resultado = self._dato(etiqueta or opcion_id, 1234)
            self.conversation_memory.record(etiqueta or opcion_id, resultado)
            return resultado
        finally:
            self._salir()

    # --- guion ---------------------------------------------------------------
    def _dato(self, metrica, valor):
        return {"status": "success", "route": "powerbi", "metric": metrica, "value": valor,
                "report": "Tablero Quirurgico", "dashboard": "Cirugias", "semantic_model": "Gestion Quirurgica",
                "dax": "EVALUATE ROW(\"v\", [Cirugias])", "reasoning": self._razonamiento(metrica)}

    def _responder(self, texto):
        if texto == "explota":
            raise RuntimeError("fallo interno con detalle secreto")
        if texto == "hola":
            return {"status": "success", "route": "conversacion", "answer": "¡Hola! Soy el asistente."}
        if texto.startswith("cirugias"):
            self._pending_query_plan = {"pregunta": texto}
            return {"status": "needs_clarification", "route": "clarification",
                    "prompt": "¿Cuál indicador de cirugías quieres?",
                    "clarification_options": [
                        {"id": "b_cx", "label": "Cirugías realizadas (Quirúrgico)",
                         "description": "Del tablero quirúrgico"},
                        {"id": 7, "label": "Cirugías realizadas (Atenciones)",
                         "description": "Del tablero de atenciones"},
                    ]}
        if texto.startswith("y en 2025"):
            if self._last_success:
                return self._dato(self._last_success["metric"] + " 2025", 999)
            return {"status": "metric_not_resolved", "route": "powerbi", "answer": "No sé a qué te refieres."}
        if texto.startswith("documentacion"):
            extractiva = "saturada" in texto
            return {"status": "success", "route": "rag", "answer": "El tablero muestra la ocupación.",
                    "synthesis_mode": "extractive" if extractiva else "generative",
                    "synthesis_issue": "MedGemma saturado" if extractiva else None,
                    "sources": [{"dashboard": "Tablero Camas", "page": "Ocupación", "chunk_type": "page"},
                                {"dashboard": "Tablero Camas", "page": "Ocupación", "chunk_type": "visual"}]}
        if texto == "lento":
            for _ in range(3):
                self._avisar("Consultando Power BI (Camas)")
                time.sleep(self.demora_s / 3)
        else:
            self._avisar("Buscando el indicador en el catálogo")
        self._last_success = {"metric": "Total atenciones", "year": 2024}
        return self._dato("Total atenciones", 42)


def instancia_doble(nombre="motor-1", demora_s=0.0) -> InstanciaMotor:
    return InstanciaMotor(engine=MotorDoble(demora_s), conversation_manager=GestorDoble(), formatter=None,
                          nombre=nombre, estado_medgemma={"status": "ready", "model": "medgemma:prueba"},
                          estado_powerbi={"status": "success"}, estado_indice={"status": "ready"})


def piscina_doble(instancias=1, demora_s=0.0) -> PiscinaMotores:
    return PiscinaMotores([instancia_doble(f"motor-{n}", demora_s) for n in range(1, instancias + 1)])
