# Portero conversacional (charla, identidad y capacidades)

Fecha: 2026-11-09 · Rama: `desarrollo` · Estado: borrador para aprobación

## Intención

Un usuario real de prueba escribió «¿Cómo estás hoy?» y el asistente buscó en toda la
documentación, armó un Query Plan de respaldo y terminó respondiendo «No encontré
información relacionada con esa pregunta en la documentación…». Lo mismo pasa con «hola»,
«gracias», «¿quién eres?» y «¿qué puedes hacer?» (verificado en el simulador
`tests.sim.harness`). El asistente parece roto en lo más básico y gasta búsquedas para nada.

Se quiere que esos mensajes reciban una respuesta natural, inmediata y predecible, y que
«¿qué puedes hacer?» oriente al usuario con los tableros que el sistema realmente conoce.

## Objetivos

- Reconocer y responder sin búsquedas: saludo, agradecimiento, despedida, «¿cómo estás?»
  (charla); «¿quién eres?» (identidad); «¿qué puedes hacer?», «ayuda» (capacidades).
- Respuesta de capacidades construida desde el catálogo (opción B elegida por el usuario):
  lista de tableros que el sistema puede consultar más un ejemplo de pregunta. Si se agrega
  un tablero al catálogo, aparece sin tocar código.
- Respuestas fijas (sin LLM): rápidas, auditables, sin depender del servidor de MedGemma.
- Visible en el razonamiento y en el registro de calificaciones como ruta propia.

## No objetivos (segunda entrega)

- Rechazo explícito de consejo clínico («¿qué dosis le doy…?»): «dosis», «diagnóstico» y
  «medicamento» aparecen también en preguntas válidas de datos; requiere diseño aparte.
- Mensajes «no sé» diferenciados (tablero detectado sin el dato vs. nada cercano).
- Preguntas fuera del hospital («¿quién ganó el partido?»).

## Anti-objetivos (fallaría aunque funcione)

- **Interceptar una pregunta real del dominio.** Es el error que más importa: preferimos
  dejar pasar un saludo raro al flujo normal (comportamiento de hoy) que contestar «¡Hola!»
  a una pregunta de datos.
- Romper un seguimiento: «gracias» seguido de «¿y en octubre?» debe seguir siendo
  seguimiento de la pregunta de datos anterior.
- Responder a la respuesta de una contrapregunta («ninguna», «sí», «gracias» mientras se
  espera elegir indicador/tablero) como si fuera charla.
- Añadir dependencias, modelos o llamadas al servidor compartido de Ollama.

## Restricciones

- Power BI y BD de producción: solo lectura; el portero no consulta nada.
- Sin datos de pacientes en salidas, logs o commits.
- `.env` solo lo edita el usuario.
- Bancos actuales no deben bajar: desarrollo 96 % (67/70), holdout 1 80 %, holdout 2 22 %,
  multi-turno. Golden master (`tests.resolution.test_golden`) sin cambios de resultado.
- Desarrollo con spec-kit + superpowers y subagentes (investigador, seguridad/integridad,
  probador adversarial, implementador); `graphify update .` tras editar.

## Enfoques considerados

| Enfoque | Trade-off | Decisión |
|---|---|---|
| 1. Solo reglas (frases/patrones normalizados) | Instantáneo y sin falsos positivos, pero no reconoce variantes («¿todo bien por allá?») | Se usa como primera capa |
| **2. Reglas + similitud MiniLM con frases de ejemplo** | Tolera variantes, milisegundos, sin modelo nuevo; requiere calibrar umbral | **Elegido por el usuario** |
| 3. MedGemma clasifica | Entiende todo, pero segundos por mensaje y depende del servidor compartido (riesgo de cola/carga en frío) | Descartado |

## Diseño decidido

1. **Módulo nuevo** (p. ej. `src/chatbot/portero.py`) con una función pura de clasificación:
   texto normalizado → `{tipo: charla|identidad|capacidades|None, subtipo, confianza, motivo}`.
   Sin estado del motor dentro; fácil de probar aislado.
2. **Capa de reglas:** frases y patrones normalizados (sin tildes, minúsculas, signos
   fuera), incluyendo variantes de chat («q tal», «buenas», «grax», «ok gracias»).
3. **Capa de similitud:** 20–30 frases de ejemplo por tipo; el vector de la pregunta se
   compara con ellas usando el MiniLM que el recuperador ya tiene cargado
   (`HybridRetriever.model`). Vectores de ejemplos calculados una sola vez. Solo intercepta
   si la similitud supera un umbral alto **y** supera por margen a la similitud con
   preguntas de dominio de referencia. Si el modelo no está disponible, solo reglas.
4. **Guardas (el portero NO actúa) si:**
   - hay contrapregunta abierta (`_pending_query_plan`, `_pending_dashboard_clarification`,
     `_pending_master_metric`, `conversation_manager.state.awaiting_clarification`) o un
     mensaje aplazado en curso;
   - el mensaje trae números, periodos (meses, años), nombres de tablero/indicador del
     catálogo o vocabulario del dominio («hola, ¿cuántas cirugías en octubre?» va a datos);
   - el mensaje es largo (más de ~8 palabras tras quitar el saludo).
5. **Punto de conexión:** en `QueryEngine.process()`, después de la normalización y antes de
   `_process_turn`, dentro de la traza (para que el razonamiento diga «Mensaje
   conversacional: saludo, respondido sin buscar»).
6. **Resultado:** `{"status": "success", "route": "conversacion", "answer": …,
   "conversation_kind": …}`. `app.py` lo muestra como texto simple (sin el bloque de
   informe/métrica); el panel de calificación lo registra con su ruta.
7. **Memoria:** el turno conversacional no se guarda en `conversation_memory` ni cambia
   `_last_success`; los seguimientos siguen apuntando a la última pregunta de datos.
8. **Respuestas:**
   - charla: breve y cordial, y una línea «Puedes preguntarme por los indicadores de los
     tableros institucionales» (agradecimiento/despedida sin esa línea);
   - identidad: qué es (asistente de consulta de tableros institucionales del HUC con
     Power BI y documentación) y qué no hace (no da recomendaciones clínicas);
   - capacidades: lista de tableros desde el catálogo (`SourceModelRouter` + tableros
     documentados del índice), nombres legibles, deduplicados, más 1–2 preguntas de ejemplo.
     Si el catálogo no está disponible, texto genérico.

## Cómo se mide

- **Banco del portero** (nuevo): ~60 mensajes conversacionales (con variantes y errores de
  tipeo) y ~60 preguntas reales cortas/ambiguas («¿y en octubre?», «cirugías», «ninguna»).
  Meta: 0 preguntas reales interceptadas; ≥90 % de los conversacionales reconocidos.
- **Barrido de los bancos existentes:** pasar TODAS las preguntas de los bancos de
  desarrollo, holdout 1/2 y multi-turno por el clasificador (sin Power BI): 0 interceptadas.
  Es la prueba principal contra falsos positivos y es barata.
- Bancos completos y golden master sin cambios de resultado.
- Pruebas de motor: guardas de contrapregunta, mensaje mixto, «gracias» → «¿y en octubre?».

## Decisiones tras la revisión del constructor

Marcadas como **decisión de Claude** las que no cambian lo que se construye; el usuario
puede corregirlas al aprobar.

- **Calibración vs. prueba ciega (decisión de Claude):** umbral, margen y frases de dominio
  de referencia se calibran SOLO con el banco nuevo del portero y el banco de desarrollo.
  Holdout 1, holdout 2 y multi-turno no se miran al calibrar: se usan únicamente como
  prueba ciega final (0 interceptadas).
- **Entorno de medición (decisión de Claude):** el simulador usa `FakeSentenceTransformer`,
  así que en el simulador y en las pruebas unitarias se mide la capa de reglas sola (meta
  ≥75 % de conversacionales, 0 falsos positivos). La meta ≥90 % con similitud se mide en una
  prueba aparte con el MiniLM real, que se omite (skip) si el modelo no está disponible.
- **Guardas (decisión de Claude):** «mensaje aplazado» se refiere a `_applying_deferred`
  (turno anidado al pulsar un botón). El portero solo corre en el turno de primer nivel y
  respeta `_pending_query_plan`, `_pending_dashboard_clarification`,
  `_pending_master_metric` y `awaiting_clarification`.
- **Memoria y exportación (decisión de Claude):** la exportación sale de los mensajes de la
  app (`st.session_state`), no de `conversation_memory`, así que el turno conversacional
  sí aparece en la conversación exportada. En `conversation_memory` (historial del RAG y
  seguimientos) no se guarda: no hay que tocar `last()` ni `_previous_turn`.
- **Registro de calificaciones (decisión de Claude):** la ruta `conversacion` se registra
  sin modo estricto (como `rag`): su texto es fijo o sale del catálogo, sin datos de
  pacientes; con modo estricto la lista de tableros quedaría borrada.
- **Tableros en «¿qué puedes hacer?» (decisión del usuario, opción A):** dos grupos.
  «Datos» = tableros consultables en Power BI (`SourceModelRouter`); «Documentación» =
  tableros que solo están en el índice RAG (sin modelo consultable). Un tablero en ambos va
  solo en «Datos». Nombres legibles y deduplicados; si un grupo queda vacío no se muestra.

## Lo que queda al implementador

- Nombre exacto del módulo y de la ruta, frases de ejemplo y redacción final de las
  respuestas (se mostrarán al usuario antes de cerrar).
- Valores del umbral y del margen, calibrados con el banco del portero y el barrido.
- Cómo obtener el MiniLM y el catálogo desde el motor sin acoplarlo (inyección o acceso
  por `rag_answer_engine`).
- Lista de vocabulario de dominio para la guarda (reutilizar el vocabulario de
  `question_normalizer.vocabulary_for` si sirve).
