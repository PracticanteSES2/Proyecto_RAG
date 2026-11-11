"""Nombres de las claves de Redis (un solo lugar; ver specs/006-api-backend/plan.md)."""

GRUPO_MOTORES = "motores"


class Claves:
    def __init__(self, prefijo: str = "rag"):
        self.p = prefijo.rstrip(":")

    # Cola de turnos
    @property
    def cola(self) -> str:
        return f"{self.p}:cola:turnos"

    @property
    def espera(self) -> str:
        return f"{self.p}:cola:espera"

    @property
    def llegadas(self) -> str:
        """Contador (INCR) del orden de llegada a la fila."""
        return f"{self.p}:cola:llegadas"

    @property
    def en_curso(self) -> str:
        return f"{self.p}:cola:en_curso"

    # Turnos
    def turno(self, turno_id: str) -> str:
        return f"{self.p}:turno:{turno_id}"

    def eventos(self, turno_id: str) -> str:
        return f"{self.p}:turno:{turno_id}:eventos"

    # Conversaciones
    def conversacion(self, conversacion_id: str) -> str:
        return f"{self.p}:conv:{conversacion_id}"

    def mensajes(self, conversacion_id: str) -> str:
        return f"{self.p}:conv:{conversacion_id}:mensajes"

    def estado_motor(self, conversacion_id: str) -> str:
        return f"{self.p}:conv:{conversacion_id}:motor"

    def activo(self, conversacion_id: str) -> str:
        return f"{self.p}:conv:{conversacion_id}:activo"

    # Caché, límites y estado del trabajador
    def cache(self, huella: str) -> str:
        return f"{self.p}:cache:{huella}"

    def limite(self, cliente: str) -> str:
        return f"{self.p}:limite:{cliente}"

    def motor(self, nombre: str) -> str:
        return f"{self.p}:motor:{nombre}"
