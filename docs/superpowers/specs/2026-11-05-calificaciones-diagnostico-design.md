# Calificación de respuestas en modo diagnóstico — diseño

Fecha: 2026-11-05 · Tamaño: proyecto pequeño-mediano (3 módulos nuevos + cambios acotados en `app.py`).

## Intención y porqué
Un usuario real de prueba hizo preguntas; algunas respuestas no fueron lo que esperaba. Se quiere un **modo de
entrenamiento** dentro del modo diagnóstico: la persona hace preguntas, el sistema contrapregunta si hace falta y
responde, y la persona califica cada respuesta (buena / mala) y, si es mala, escribe **qué esperaba**.

Esos registros son la **materia prima** de dos proyectos posteriores, que NO forman parte de este:
1. evaluar los logs y ajustar de forma exhaustiva cómo responde el sistema;
2. entrenar el modelo que enruta (entender el contexto, elegir bien la colección de la base vectorial) para que las
   respuestas sean más acertadas a lo que se muestra en el chat.

Por eso el registro debe guardar **cada decisión intermedia del enrutamiento**, no solo pregunta y respuesta: sin eso
no se sabrá qué pieza falló (`IntentParser`, `SourceModelRouter`, `QueryPlanBuilder`, recuperador híbrido, compuerta LLM).

## Metas
- Con «Modo diagnóstico» activo, cada respuesta del asistente (incluidas las contrapreguntas) muestra
  `👍 Buena` / `👎 Mala`; con 👎 aparece un cuadro «¿Qué esperabas que respondiera?» y un botón Guardar.
- Cada calificación se guarda como una línea JSON con el contexto completo del turno (ver Registro).
- Se puede recalificar un turno (la última calificación manda).
- Sin el modo diagnóstico, el chat se comporta exactamente igual que hoy.

## No-metas
- Entrenar o ajustar nada (proyectos 1 y 2 de arriba). Tablero de análisis de calificaciones. Autenticación de
  evaluadores. Base de datos. Cambios en la lógica de enrutamiento o respuesta.

## Anti-metas (fallos aunque «funcione»)
- Que un fallo al guardar rompa o ralentice el chat. Que el log contenga filas de pacientes. Que se hagan consultas
  extra a Power BI (producción: solo lectura, pocas consultas).

## Restricciones
- Power BI y bases de producción solo lectura; nada de datos de pacientes en logs, salidas ni commits.
- Python/Streamlit existentes (1.64); sin dependencias nuevas.
- `data/` está fuera de git: el log no se versiona y hay que respaldarlo aparte.

## Enfoques considerados
1. **JSONL, una línea por calificación** — elegido (acordado con el usuario el 2026-11-05).
2. SQLite — consultas y ediciones directas, pero esquema y migraciones innecesarios hoy.
3. Escribir al banco `tests/real/` — mezcla entrenamiento con regresión y exige verdad DAX por caso.

## Diseño
**Módulo `src/feedback/`** (nuevo, sin dependencia de Streamlit salvo `panel.py`):
- `registro.py`: `construir_registro(turno, historial, calificacion) -> dict` y
  `guardar(registro) -> None` (añade una línea a `data/feedback/calificaciones.jsonl`; carpeta sobreescribible con
  la variable de entorno `FEEDBACK_DIR`; un candado de hilo y una sola escritura por línea).
- `lector.py`: `cargar_calificaciones(ruta=None) -> list[dict]`, devuelve la última línea por `id_turno`
  (lo usarán los proyectos 1 y 2 y las pruebas).
- `panel.py`: `mostrar_calificacion(indice_mensaje)` dibuja 👍/👎, comentario y Guardar con `st.feedback` y
  `st.text_area`; llamado desde `app.py` por cada mensaje del asistente cuando `debug_mode` es verdadero.

**Captura del turno.** `execute_turn` ya tiene `result`; al terminar guarda en el mensaje un `snapshot` saneado
(no el `result` completo). El historial previo del mismo diálogo (últimos 6 mensajes: pregunta, respuesta,
opción de contrapregunta elegida) se toma de `st.session_state.messages` al calificar.

**Registro v1** (una línea JSON):
`version, id_turno, id_sesion, indice_turno, fecha_turno, fecha_calificacion, commit_codigo, via (texto/botón),
pregunta, historial[], estado, ruta, etapa, informe, tablero, modelo_semantico, metrica, plan_consulta,
contexto_fuentes, modo_sintesis, fuentes[{id, coleccion, tablero, tipo_chunk, puntaje}] (sin texto del chunk),
opciones_contrapregunta[], respuesta, error, calificacion ("buena"|"mala"), esperado (texto libre, obligatorio
si "mala")`. No se registra el nombre de quien califica: todas las preguntas sirven para mejorar el modelo y el RAG
en pro de las áreas que lo usarán.

**Saneamiento (decisión mía, a confirmar):** la `respuesta` se guarda sin líneas de tabla (las que empiezan por `|`)
y recortada a 1500 caracteres; se descartan del snapshot claves tipo `rows`, `data`, `table`, `dataframe`. El texto del
comentario lo escribe la persona; se avisa en el cuadro de que no incluya datos de pacientes.

**Robustez.** Todo guardado va en `try/except`: si falla, el chat sigue y la barra lateral muestra un aviso.

## Pruebas (unittest, estilo del proyecto, `tests/feedback/`)
- registro: contiene todos los campos; sin filas de tabla; recorte a 1500; «mala» sin `esperado` se rechaza.
- guardar/leer: dos calificaciones del mismo `id_turno` → el lector devuelve la última; línea corrupta se omite;
  carpeta inexistente se crea; escritura concurrente de 20 hilos produce 20 líneas válidas.
- app: con `streamlit.testing.v1.AppTest`, el panel aparece solo con modo diagnóstico (si el arranque de `app.py`
  lo permite con servicios simulados; si no, se prueba `panel.py` aislado).

## Dejado al constructor
Nombres internos secundarios, estilo exacto del panel dentro de la paleta ya aplicada, cómo derivar `id_turno`
estable (propuesta: `id_sesion` + índice del mensaje), y obtener `commit_codigo` (propuesta: `git rev-parse --short HEAD`
al iniciar, con valor vacío si falla).

## Después de este proyecto
Cada actualización: `graphify update .`; desarrollo con spec-kit + superpowers (reglas del proyecto).
