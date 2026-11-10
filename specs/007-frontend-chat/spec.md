# Especificación funcional: Frontend web del chat (Next.js)

**Rama**: `agente/frontend-web` (feature `007-frontend-chat`)

**Creada**: 2026-11-10

**Estado**: Implementada contra mock (pendiente integración con el backend FastAPI real)

**Entrada**: «Abandonar Streamlit y construir el chat con Next.js (frontend) + FastAPI (backend) + Redis. La
percepción del usuario final y la estética son prioridad.» La especificación funcional de referencia es el
`app.py` de Streamlit; el contrato de eventos de progreso es
`specs/003-progreso-chat/contracts/eventos.md` (rama `agente/ui-progreso`).

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — Preguntar y recibir una respuesta con cifras (Prioridad: P1)

Un funcionario del hospital abre el chat, escribe «¿Cuántos egresos hubo en marzo de 2026?» y pulsa Enter.
Mientras el asistente trabaja ve un indicador sereno con frases humanas que reflejan la etapa real; al terminar
ve la respuesta en Markdown (con tabla si aplica), las fuentes y un botón «Abrir en Power BI ›».

**Por qué P1**: es la razón de ser del producto.

**Prueba independiente**: con el mock activo, enviar una pregunta y comprobar indicador → respuesta con tabla,
fuentes y enlace.

**Escenarios de aceptación**:

1. **Dado** el chat vacío, **cuando** escribo y pulso Enter, **entonces** mi mensaje aparece a la derecha y el
   campo se vacía; Shift+Enter inserta un salto de línea sin enviar.
2. **Dado** un turno en curso, **cuando** llegan eventos `progreso`, **entonces** la frase cambia con un
   fundido suave, sin saltos de diseño, y nunca se muestran segundos, etapas ni niveles como texto.
3. **Dado** un turno que responde en menos de 600 ms (p. ej. «hola»), **entonces** el indicador nunca llega a
   verse.
4. **Dado** que llega `respuesta`, **entonces** el indicador se retira sin dejar resumen y la respuesta se
   anuncia a lectores de pantalla (`aria-live`).
5. **Dado** un turno en curso, **entonces** el botón de envío se convierte en «Detener» y no se puede enviar
   otra pregunta hasta que termine o se detenga.

### Historia 2 — Elegir una opción cuando el asistente pregunta (Prioridad: P1)

Si la pregunta es ambigua, el asistente responde con una contrapregunta y opciones. El usuario pulsa una opción
(botón/tarjeta con descripción) y el turno continúa enviando `opcion_id`.

**Prueba independiente**: en el mock, «¿Cuál es la ocupación?» devuelve contrapregunta; al pulsar una opción se
envía un turno con `opcion_id` y se marca la opción elegida.

**Escenarios de aceptación**:

1. **Dado** una contrapregunta, **cuando** pulso una opción, **entonces** se envía `{mensaje: texto de la
   opción, opcion_id}` y la opción queda marcada como elegida; las demás se desactivan.
2. **Dado** una contrapregunta antigua (ya hay turnos posteriores), **entonces** sus opciones se ven
   desactivadas.

### Historia 3 — Entender esperas largas, colas y saturación (Prioridad: P1)

**Escenarios de aceptación**:

1. **Dado** un evento `cola` con `posicion > 1`, **entonces** se lee «Hay N consultas antes que la tuya, ya
   casi…»; con `posicion ≤ 1`, «Tu pregunta es la siguiente; enseguida la atiendo».
2. **Dado** un evento `espera`, **entonces** su frase aparece en el renglón secundario (más pequeño, opacidad
   0,8) con fundido de ~600 ms. Si no llega ningún `espera`, el cliente genera frases equivalentes a los 10,
   25, 50 y 90 s (respaldo).
3. **Dado** que `POST /turnos` responde 429, **entonces** aparece «Hay muchas consultas en este momento.
   Intenta de nuevo en unos segundos.» con botón «Reintentar».
4. **Dado** un evento `error`, **entonces** se muestra un aviso amable no técnico con «Reintentar»; el código
   y el mensaje técnico solo se ven en modo diagnóstico.
5. **Dado** `respuesta.degradada` o un evento `aviso`, **entonces** se muestra una nota discreta bajo la
   respuesta, con icono de información y sin color de error, que se conserva en el historial.

### Historia 4 — Calificar, exportar y empezar de nuevo (Prioridad: P2)

**Escenarios de aceptación**:

1. **Dado** una respuesta, **cuando** pulso 👍, **entonces** se guarda la calificación (`valor: "buena"`) y se
   confirma con «Gracias».
2. **Dado** una respuesta, **cuando** pulso 👎, **entonces** se abre un cuadro opcional «¿Qué esperabas que
   respondiera? (no incluyas datos de pacientes)» y «Enviar» guarda `{valor: "mala", comentario?}`.
3. **Dado** una conversación, **cuando** elijo «Exportar conversación», **entonces** se descarga un `.md`
   (`GET /exportar?formato=md`).
4. **Dado** una conversación, **cuando** pulso «Nueva conversación», **entonces** el historial se limpia, se
   olvida la conversación anterior y vuelve el estado vacío.

### Historia 5 — Estado vacío y salud del servidor (Prioridad: P2)

1. **Dado** una conversación sin mensajes, **entonces** se ven las capacidades del asistente y ejemplos de
   preguntas (`GET /capacidades`); pulsar un ejemplo lo envía.
2. **Dado** que `GET /salud` falla, **entonces** aparece un aviso amable «No logramos comunicarnos con el
   asistente…» que se reintenta solo y desaparece cuando el servidor vuelve.

### Historia 6 — Modo diagnóstico (Prioridad: P3)

Interruptor discreto en el menú de ajustes. Encendido: cada turno se envía con `diagnostico: true`; durante la
espera se ve la línea de tiempo de etapas con segundos; bajo cada respuesta, un panel plegable «Detalles
técnicos» con ruta, línea de tiempo, DAX, trazas y el resto del objeto `diagnostico`.

### Casos borde

- Se pierde la conexión SSE: el navegador reconecta con `Last-Event-ID`; si el flujo se cierra sin `fin` ni
  `respuesta`, el turno termina con aviso amable y «Reintentar».
- El usuario pulsa «Detener»: se cierra el flujo y el turno queda «Detuviste esta consulta.».
- Markdown con HTML incrustado o enlaces `javascript:`: se sanea; los enlaces externos abren en otra pestaña.
- Tablas anchas en móvil: desplazamiento horizontal dentro de la tabla, nunca de la página.
- Recarga de la página: se recupera la conversación con `GET /conversaciones/{id}` (id en `localStorage`); si
  devuelve 404 se empieza de cero.

## Requisitos *(obligatorio)*

### Requisitos funcionales

- **FR-001**: Todo acceso HTTP/SSE MUST pasar por `frontend/lib/api/` (cliente tipado); los tipos viven en un
  único archivo reemplazable por tipos generados desde el OpenAPI.
- **FR-002**: La URL base MUST salir de `NEXT_PUBLIC_API_URL` (por defecto `http://localhost:8000`); con
  `NEXT_PUBLIC_API_MOCK=1` se usa el mock del mismo origen.
- **FR-003**: Envío con Enter; Shift+Enter = salto de línea; no se envían mensajes vacíos.
- **FR-004**: Markdown con GFM (tablas) saneado.
- **FR-005**: Contrapreguntas como tarjetas/botones que envían `opcion_id`.
- **FR-006**: Botón «Abrir en Power BI ›» por cada enlace; fuentes visibles bajo la respuesta.
- **FR-007**: Calificación 👍/👎 con comentario opcional.
- **FR-008**: Exportar conversación y nueva conversación.
- **FR-009**: Indicador de «pensando» según el contrato de eventos (retardo 600 ms, fundido 350 ms, contenedor
  de alto fijo, frase en una línea con elipsis, renglón secundario para `espera`, cuatro puntos con los
  colores del isotipo (los del filete), shimmer en la frase, `role=status` + `aria-live=polite`, sin animación con
  `prefers-reduced-motion`).
- **FR-010**: Modo diagnóstico discreto (menú de ajustes) con línea de tiempo y panel técnico.
- **FR-011**: Avisos amables ante servidor caído, 429, error y respuesta degradada; nunca jerga técnica con
  diagnóstico apagado.
- **FR-012**: Tokens de diseño en un solo archivo CSS; componentes sin colores hexadecimales sueltos (regla de
  ESLint); modo claro y oscuro (sistema / claro / oscuro).
- **FR-013**: Accesibilidad: `role=log` en el historial, `aria-live` para respuestas, foco visible, contraste
  AA, todo operable con teclado. Responsive de móvil a escritorio.

### Entidades clave

- **Conversación**: `conversacion_id` + mensajes.
- **Mensaje de usuario**: texto, `opcion_id` opcional.
- **Turno del asistente**: `turno_id`, estado (enviando, en curso, listo, error, limitado, detenido), etapas
  recibidas, cola, espera, respuesta, avisos, calificación.

## Criterios de éxito *(obligatorio)*

- **SC-001**: Una pregunta de saludo nunca muestra el indicador de espera.
- **SC-002**: Con diagnóstico apagado no aparece ningún número de segundos ni nombre técnico de etapa.
- **SC-003**: `npm run lint`, `npm run typecheck`, `npm test` y `npm run build` en verde.
- **SC-004**: El flujo completo (pregunta → tabla → contrapregunta → opción → calificación → exportar) funciona
  contra el mock sin backend.

## Supuestos

- Fase de desarrollo con un único usuario; sin autenticación ni historial multiusuario (contexto de despliegue).
- Formas no fijadas por el contrato v1 (ver `contracts/api-v1.md`, sección «Supuestos»): cuerpo de
  `GET /capacidades`, `GET /salud`, `GET /conversaciones/{id}`, y `valor` de la calificación (`"buena"` |
  `"mala"`, como el registro actual de Streamlit).
- La marca oficial (paleta, tipografías, radios, mascota) la entrega otro agente; aquí hay valores provisionales
  tomados de `src/ui/estilo.py`.
