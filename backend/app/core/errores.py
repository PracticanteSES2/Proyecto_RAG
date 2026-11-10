"""Errores de la API: siempre `{"mensaje", "codigo"}` en español amable, sin
trazas ni detalles internos (el detalle va al log del servidor)."""
from __future__ import annotations


class ErrorAPI(Exception):
    def __init__(self, estado_http: int, codigo: str, mensaje: str, cabeceras: dict | None = None,
                 extra: dict | None = None):
        super().__init__(mensaje)
        self.estado_http = estado_http
        self.codigo = codigo
        self.mensaje = mensaje
        self.cabeceras = cabeceras or {}
        self.extra = extra or {}

    def cuerpo(self) -> dict:
        return {"mensaje": self.mensaje, "codigo": self.codigo, **self.extra}


def no_encontrada(que: str = "conversacion") -> ErrorAPI:
    if que == "turno":
        return ErrorAPI(404, "turno_no_encontrado", "No encontré esa consulta; puede haber expirado.")
    return ErrorAPI(404, "conversacion_no_encontrada",
                    "No encontré esa conversación; puede haber expirado. Empieza una nueva, por favor.")


TURNO_EN_CURSO = (409, "turno_en_curso",
                  "Todavía estoy respondiendo tu pregunta anterior. Espera la respuesta antes de enviar otra.")
OPCION_NO_VIGENTE = (409, "opcion_no_vigente",
                     "Esa opción ya no está disponible. Escribe de nuevo tu pregunta, por favor.")
NO_CALIFICABLE = (409, "turno_no_calificable", "Esa respuesta todavía no se puede calificar.")
SERVICIO_OCUPADO = (503, "servicio_ocupado",
                    "No pude recibir tu pregunta en este momento. Intenta de nuevo en un momento, por favor.")
FORMATO_NO_SOPORTADO = (400, "formato_no_soportado", "Por ahora solo puedo exportar en formato Markdown (md).")
PETICION_INVALIDA = "peticion_invalida"
ERROR_INTERNO = "error_interno"
MENSAJE_INVALIDO = "La petición no es válida. Revisa el mensaje e intenta de nuevo."
MENSAJE_INTERNO = "Ocurrió un error inesperado. Intenta nuevamente en un momento."


def error(definicion: tuple[int, str, str]) -> ErrorAPI:
    return ErrorAPI(*definicion)


def demasiadas_peticiones(reintentar_en_s: float) -> ErrorAPI:
    segundos = max(1, int(round(reintentar_en_s + 0.49)))
    return ErrorAPI(429, "demasiadas_peticiones",
                    f"Estás enviando muchas preguntas seguidas. Espera {segundos} s y vuelve a intentarlo, por favor.",
                    cabeceras={"Retry-After": str(segundos)}, extra={"reintentar_en_s": segundos})
