# Contrato: estado de conversación por sesión (`EstadoConversacion`)

Estable desde la rama `agente/memoria-sesion` (spec 008). Lo usan `app.py` (Streamlit, legado) y el backend
FastAPI (`backend/app/services/`, que lo guarda en memoria o Redis con TTL). Cambios incompatibles suben
`VERSION_ESTADO`.

## Idea

El motor (`QueryEngine`) es un **servicio compartido sin estado de conversación**: se construye una vez
(catálogos, índices, modelos, cachés de dominio) y atiende a todas las conversaciones. Todo lo que depende de
la conversación (memoria de turnos, consulta anterior para seguimientos, contrapreguntas y planes pendientes,
mensaje aplazado, estado del analizador de intención) vive en un `EstadoConversacion` que el llamador guarda
y pasa en cada turno.

## API

```python
from src.chatbot.estado_conversacion import EstadoConversacion, VERSION_ESTADO

estado = EstadoConversacion()                 # id = uuid4 hex; o EstadoConversacion(id="abc")

resultado = engine.process(texto, sesion=estado)                                  # mensaje escrito
resultado = engine.select_clarification_option(option_id, label, sesion=estado)  # botón de una contrapregunta
historial = engine.conversation_history(6, sesion=estado)                         # [{"role","text","meta"}]

datos = estado.to_dict()                      # dict JSON puro (json.dumps sin default)
estado = EstadoConversacion.from_dict(datos)  # restaura (ValueError si la versión no es compatible)
texto = estado.to_json()                      # == json.dumps(estado.to_dict(), ensure_ascii=False)
estado = EstadoConversacion.from_json(texto)

estado.reiniciar()                            # «Nueva conversación» (o simplemente crear uno nuevo)
```

Parámetro opcional en `process` y `select_clarification_option`: `progreso=callable(evento)` — escucha de
pasos en vivo solo para ese turno (mismo formato que `set_progress_listener`).

## Garantías

1. **Aislamiento.** Un turno con `sesion=A` solo lee y escribe el estado de `A`. Nada de `A` queda en el
   motor ni en otra sesión: ni la memoria, ni la consulta anterior, ni contrapreguntas, ni el razonamiento.
2. **Cierre automático del turno.** Con `sesion=` el motor aplica al terminar lo que `app.py` hacía a mano
   (`reset_if_finished`): si el resultado no es `needs_clarification`, olvida contrapreguntas y planes
   pendientes y el estado del analizador de intención; conserva la memoria y la consulta anterior. También
   si el turno lanza una excepción (que se propaga). El llamador NO necesita llamar a `reset`.
3. **Serializable.** `to_dict()` devuelve solo `dict`/`list`/`str`/`int`/`float`/`bool`/`None`. Tuplas,
   conjuntos y fechas internos se codifican con etiquetas (`{"__tupla__": [...]}`, `{"__conjunto__": [...]}`,
   `{"__fecha__": "2026-11-10"}`, `{"__fecha_hora__": "..."}`) y `from_dict` los devuelve con su tipo. Lo que
   va dentro de `pendiente`, `seguimiento` y `memoria` es **opaco**: el backend lo guarda y lo devuelve sin
   tocarlo. `to_dict(estado_restaurado) == to_dict(estado)`.
4. **Un turno a la vez por conversación.** Cada `EstadoConversacion` tiene un candado (no se serializa): dos
   turnos simultáneos con el mismo objeto se ejecutan en serie. Turnos de conversaciones distintas no
   comparten estado de conversación ni del turno (razonamiento, interpretación, mensaje del turno, escucha
   de progreso: todo por turno con `contextvars`).
5. **Compatibilidad.** Sin `sesion=` el motor usa una sesión propia (modo legado de un solo usuario: pruebas,
   scripts y arneses). Ese modo NO aísla usuarios y NO cierra el turno solo (el llamador sigue llamando
   `conversation_manager.reset()` y `engine.reset()` como antes).
6. **Lo que no guarda.** `ultimo_razonamiento` (razonamiento del último turno, para mostrarlo si el turno
   lanzó una excepción) es transitorio: no se serializa. El resultado de cada turno ya trae `reasoning`.

## Formato de `to_dict()` (versión 1)

```json
{
  "version": 1,
  "id": "3f2c…",
  "memoria": {"max_turnos": 12, "turnos": [{"user": "…", "via": "texto", "interpreted": null,
               "assistant": "…", "meta": {…}, "topic": {…} }]},
  "seguimiento": {"question": "…", "metric_id": "…", "filters": […], "group_by": […], "…": "…"},
  "pendiente": {"indicador": null, "plan": {…}, "tablero": null, "mensaje_aplazado": null},
  "intencion": {"intent": null, "dashboard": null, "metric_type": null, "year": null, "month": null,
                "missing_fields": [], "awaiting_clarification": false, "original_question": null,
                "dashboard_reason": null},
  "tableros_candidatos": []
}
```

- `memoria`: últimos turnos (lo que dijo el usuario, cómo se interpretó, resumen de la respuesta y sus
  datos). Sin filas completas. Tamaño típico < 20 KB.
- `seguimiento`: última consulta numérica exitosa (base de «¿y en urología?»), o `null`.
- `pendiente.plan` / `pendiente.indicador` / `pendiente.tablero`: contrapregunta abierta (opciones ofrecidas
  y pregunta original), o `null`. `pendiente.mensaje_aplazado`: mensaje de contexto recibido mientras había
  una contrapregunta abierta; se responde tras el botón.
- `intencion` y `tableros_candidatos`: estado del `ConversationManager` (analizador de intención).

## Uso desde el backend

Implementado en `backend/app/services/motor.py::SesionExplicita` (reemplaza el parche `SesionPorAtributos`):

```python
result, estado_nuevo = SesionExplicita().ejecutar(instancia, estado_previo, texto, opcion, on_token=...)
# estado_previo / estado_nuevo: dict de EstadoConversacion.to_dict() (o None = conversación nueva)
SesionExplicita.sin_contexto(estado)   # True sin pendientes, seguimiento, memoria ni aclaración abierta
```

`SerializadorEstado` guarda ese dict como JSON firmado con HMAC-SHA256 (sin pickle). Un estado de otra versión
o ilegible se descarta y la conversación sigue sin contexto. Si el motor lanza, el estado previo no cambia.

## Concurrencia del motor

`app.py` mantiene `turn_slot` (un turno a la vez en todo el servidor). El estado de conversación ya no lo
exige, pero algunos colaboradores compartidos aún guardan datos temporales del turno en atributos de
instancia (ver `research.md`, «Pendiente para turnos en paralelo»). Hasta corregirlos, el backend debe
serializar los turnos del motor (un trabajador o un candado global), como hace hoy `turn_slot`.
