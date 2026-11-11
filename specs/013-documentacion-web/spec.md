# Especificación funcional: Documentación viva en la web (FastAPI + Next.js)

**Rama**: `agente/documentacion-web` (feature `013-documentacion-web`)

**Creada**: 2026-11-11

**Estado**: Implementada (backend + frontend con mock); pendiente la prueba Playwright de paridad contra el
backend real.

**Entrada**: «Migrar la página “Documentación de tableros” (documentación viva) de Streamlit al nuevo stack.»
La especificación funcional de referencia es `src/docs_md/interfaz.py` (`pagina()`, legado congelado), que se
trata como especificación y no como código para copiar. El dominio ya existe en `src/docs_md/`
(`repositorio`, `actualizador`, `formato`, `indexacion`) y solo se consume.

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — Ver la documentación de una página (Prioridad: P1)

Quien mantiene los tableros abre «Documentación» desde el encabezado del chat, busca un tablero (grupo de
fuentes), elige una página y ve su documento: ficha (tablero, página, nombre funcional, bloque, tablas, versión,
última actualización), propósito y secciones, e historial de cambios (el más reciente primero).

**Prueba independiente**: con el mock, abrir `/documentacion`, filtrar «urgencias», elegir «CONSULTAS DIA» y ver
ficha, cuerpo e historial.

**Escenarios de aceptación**:

1. **Dado** el explorador, **cuando** escribo en la búsqueda, **entonces** se filtran tableros y páginas por
   nombre, nombre funcional o archivo (sin distinguir tildes ni mayúsculas).
2. **Dado** una página con formato válido, **entonces** veo «Formato válido»; con problemas, la lista de
   problemas y aun así el documento; si no se puede interpretar, el texto del archivo tal como está guardado.
3. **Dado** un documento, **entonces** puedo desplegar «Ver el archivo .md tal como está guardado».
4. El Markdown se pinta saneado (sin HTML crudo ni enlaces `javascript:`).
5. Un tablero sin páginas muestra «Este tablero todavía no tiene páginas documentadas»; sin tableros, un estado
   vacío con la mascota.

### Historia 2 — Proponer un cambio desde una nota informal (Prioridad: P1)

Escribo con mis palabras qué cambió («le subí el verde del semáforo de triage II a 20 minutos»), opcionalmente
la página (o «Detectar automáticamente») y los cambios detectados en el PBIP (uno por línea). MedGemma prepara la
propuesta; nada se guarda hasta aprobarla.

**Escenarios**:

1. Sin nota, el formulario pide «escribe qué cambió»; sin tablero, no se puede enviar.
2. Mientras MedGemma trabaja veo el indicador del chat con frases de trabajo reales («Leyendo tu nota»,
   «Ubicando la página que corresponde», «Redactando el cambio en la documentación», «Revisando el cambio
   propuesto») y, si tarda, frases de espera tranquilizadoras. **Nunca** se habla de colas, filas, otras
   personas, saturación ni del servidor.
3. La generación es asíncrona: `POST` responde al instante (202) y la página consulta el estado (sondeo).
4. Si la nota no tiene contenido, contradice la página o es ambigua, la propuesta queda «requiere aclaración».

### Historia 3 — Revisar la propuesta (Prioridad: P1)

Veo la página elegida (y cómo se eligió: «la elegiste tú», «la nota la nombra…», «MedGemma la eligió entre
varias parecidas (también: …)»), el resumen, las dudas, los avisos («Revisa esto antes de aprobar (n)»), la lista
de operaciones («Cambiar la entrada «X» de Reglas de negocio», con el texto actual) y el diff antes/después.

**Escenarios**:

1. El diff muestra solo los tramos cambiados: líneas que salen en rojo con «−» y las que entran en verde con «+»
   (colores de tokens y, además, signo y texto oculto para lectores de pantalla: legible sin color), más el
   conteo «líneas que salen (n) · líneas que entran (m)».
2. Puedo corregir el texto nuevo de cada operación (salvo «eliminar»); hasta pulsar «Actualizar vista previa»
   no se puede aprobar. Si la corrección no aplica, veo el motivo.
3. Puedo ver «la página como quedaría» y el diff unificado (técnico).
4. «El resultado cumple el formato» o la lista de errores (y entonces no se puede aprobar).
5. «Rechazar» descarta la propuesta: «Propuesta descartada. La documentación no cambió.».
6. Se muestra «preparada en 9.8 s · 2 llamadas a MedGemma (4.1 s + 5.2 s)».

### Historia 4 — Aclarar una propuesta ambigua (Prioridad: P2)

«Hace falta una aclaración. MedGemma no quiso adivinar:» con las dudas; elijo la página entre las candidatas (o
«Que MedGemma la detecte»), puedo precisar la nota y pulso «Reintentar» (o «Descartar»).

### Historia 5 — Aprobar y reindexar (Prioridad: P1)

Escribo quién aprueba y pulso «Aprobar y guardar». El backend guarda la página (versión e historial los pone el
sistema) y reindexa el RAG del tablero para que el chat use la versión nueva.

**Escenarios**:

1. «Cambio aprobado. La página X quedó guardada en la versión N.»
2. Mientras reindexa: «Actualizando el buscador del asistente…»; al terminar: «El asistente ya usa el texto
   nuevo: se reindexó T (D documentos, C fragmentos, S s) con la conexión del chat».
3. Si la reindexación falla: «El cambio sí quedó guardado, pero el asistente del chat todavía no lo conoce…» y un
   botón «Reintentar la reindexación».
4. Si el archivo cambió desde la propuesta, no se guarda: «La documentación de X cambió después de crear la
   propuesta; vuelva a proponer el cambio.».
5. La reindexación es segura con el chat en uso: espera a que el motor termine los turnos en curso, retiene las
   instancias del motor mientras reescribe el índice y reutiliza el cliente de Qdrant y el modelo de embeddings
   del motor (Qdrant local admite un solo cliente por carpeta).

### Historia 6 — Errores amables (Prioridad: P1)

Todo error llega como `{mensaje, codigo}` en español, sin trazas. Si la propuesta falla: «No se pudo preparar la
propuesta. … Puedes ajustar la nota (o elegir la página) y volver a intentarlo.» con el detalle técnico (respuesta
cruda del modelo) plegado.

## Requisitos

- **RF-001** Endpoints REST en `/api/v1/documentacion/**` (contrato en `contracts/api-documentacion.md`).
- **RF-002** Routers delgados sin importar `src`; el servicio `backend/app/services/documentacion.py` llama a
  `src/docs_md` y arma las vistas (ficha, cuerpo, historial, diff estructurado) en
  `backend/app/services/documentacion_vista.py`.
- **RF-003** Proponer es asíncrono (202 + sondeo) y pasa por la puerta del LLM (`call_llm`, vía
  `actualizador.proponer_cambio`).
- **RF-004** Aprobar valida contra el archivo actual (`aplicar_propuesta`) y lanza la reindexación del grupo.
- **RF-005** La reindexación coordina con el motor embebido (retiene la piscina, reutiliza retriever y cliente
  Qdrant, invalida la huella de la caché de respuestas). Con el motor en otro proceso (Redis + trabajador) responde
  `no_disponible` con un mensaje claro: el cambio queda guardado.
- **RF-006** El frontend no decide nada de negocio: pinta lo que el backend devuelve (operaciones, diff, avisos,
  si se puede aprobar).
- **RF-007** El mock de Next (`app/api/v1/documentacion/**`) reproduce todo el flujo sin backend.

## Fuera de alcance

- Persistir propuestas en Redis (hoy viven en la memoria del proceso de la API, con vida de 24 h).
- Reindexar desde la API cuando el motor corre en el proceso trabajador (requiere una cola de tareas en el
  trabajador).
- Editar el diccionario de variables (`_diccionario*.md`) desde la web (Streamlit tampoco lo hacía).
