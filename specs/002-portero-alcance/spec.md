# Feature Specification: Portero de alcance (mensajes fuera de alcance)

**Feature Branch**: `agente/portero-alcance`

**Created**: 2026-11-10

**Status**: Draft

**Input**: User description: "Segunda entrega del portero: detectar barato (reglas + MiniLM ya cargado, sin LLM) los mensajes que no tienen nada que ver con los tableros de Power BI del hospital ni con su documentación (peticiones vagas, cálculos, noticias, otra institución, tareas genéricas, consejo clínico, programación, chistes, clima, recetas, deportes, redacción de correos, mensajes sin sentido) y responder con un texto fijo que reoriente al usuario, sin disparar vectorizador, RAG, Power BI ni MedGemma. Un falso positivo es mucho peor que un falso negativo: en la duda, flujo normal."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Pedidos ajenos a los tableros se responden al instante (Priority: P1)

Un funcionario escribe «¿cuánto es la raíz cuadrada de 144?», «¿qué pasó ayer en Tailandia?»,
«cuéntame un chiste», «¿va a llover hoy en Manizales?», «receta de arepas», «¿quién ganó el
partido del Once Caldas?» o «escríbeme un correo para mi jefe». Hoy cada uno dispara el flujo
completo (buscador, RAG, Power BI y MedGemma), tarda, ocupa uno de los ~3 turnos simultáneos
del servidor y termina en una respuesta confusa. Debe recibir al instante un texto fijo, corto y
amable que diga que eso está fuera de lo que el asistente responde y qué SÍ puede hacer.

**Why this priority**: es el desperdicio de recursos que motivó la entrega; cada mensaje así
bloquea el servidor compartido para preguntas reales.

**Independent Test**: enviar los mensajes del banco de fuera de alcance; cada uno recibe la
respuesta fija de su categoría sin consultas al buscador, a Power BI ni al modelo de lenguaje.

**Acceptance Scenarios**:

1. **Given** una conversación sin contrapregunta abierta, **When** el usuario escribe «quiero saber cuánto es la raíz cuadrada de x», **Then** recibe un texto fijo de fuera de alcance con un ejemplo de pregunta válida y no se consulta nada.
2. **Given** lo mismo, **When** escribe «escríbeme un correo para mi jefe», **Then** recibe un texto que dice que no redacta textos y que sí puede dar los datos de los tableros.

---

### User Story 2 - Petición vaga: el asistente pregunta qué dato necesita (Priority: P1)

El usuario escribe «necesito que me respondas algo», «tengo una pregunta» o «hazme un reporte
de» (sin tema). Debe recibir «Claro, dime qué dato o tablero necesitas» seguido de la lista de
tableros (texto de capacidades) en lugar de una búsqueda vacía.

**Why this priority**: es el segundo patrón más frecuente de usuarios nuevos y orienta hacia una
pregunta válida.

**Independent Test**: enviar las variantes del banco; reciben la invitación con la lista de
tableros del catálogo vigente.

**Acceptance Scenarios**:

1. **Given** una conversación nueva, **When** el usuario escribe «hazme un reporte de», **Then** recibe la invitación a decir qué indicador y periodo necesita.
2. **Given** una conversación nueva, **When** escribe «hazme un reporte de la ocupación de camas», **Then** sigue el flujo normal de datos.

---

### User Story 3 - Consejo clínico y otras instituciones (Priority: P1)

«¿Qué le doy a mi hijo para la fiebre?», «¿qué dosis de acetaminofén le doy a un niño?» o «me
duele la cabeza, ¿qué me tomo?» reciben una negativa fija: el asistente no da recomendaciones
clínicas, diagnósticos ni dosis. «¿Cómo hace las cirugías el Hospital Santa Sofía?» recibe que
solo hay información del Hospital Universitario de Caldas. Las preguntas de datos sobre
medicamentos, antibióticos, remisiones o pacientes del propio hospital siguen el flujo normal.

**Why this priority**: evita que el modelo de lenguaje improvise consejo clínico (riesgo) y aclara
el alcance institucional.

**Independent Test**: los casos clínicos y de otra institución del banco reciben su texto; las
preguntas reales de antibióticos, farmacia y remisiones de los bancos no se interceptan.

**Acceptance Scenarios**:

1. **Given** una conversación nueva, **When** el usuario escribe «¿qué antibiótico le doy a un paciente con neumonía?», **Then** recibe la negativa clínica.
2. **Given** una conversación nueva, **When** escribe «¿cuál es el antibiótico que más se está usando?», **Then** sigue el flujo normal.
3. **Given** una conversación nueva, **When** escribe «¿cuántos pacientes remitimos al Santa Sofía?», **Then** sigue el flujo normal (remisiones son datos propios).

---

### User Story 4 - Mensajes sin sentido o vacíos (Priority: P2)

«asdfgh», «jajaja», «???» o solo emojis reciben «No entendí tu mensaje» con un ejemplo, sin
buscar nada.

**Why this priority**: menos frecuente; evita búsquedas inútiles.

**Independent Test**: los casos sin sentido del banco reciben ese texto; «pq», «x», «la 2», «sí»
no.

---

### Edge Cases

- Palabra del catálogo, periodo, número o mención del propio hospital (Hospital de Caldas, SES,
  HUC, «nuestro hospital») fuera del marcador detectado: flujo normal.
- Mensajes con tipeos, sin tildes, en mayúsculas o con jerga de chat («q», «k», «nesecito»).
- Saludo + pedido fuera de alcance («hola, cuéntame un chiste»): fuera de alcance.
- «hazme un reporte» (sin «de») o «hazme un resumen» tras una respuesta son seguimientos: flujo normal.
- «¿qué significa NEDOCS?», «¿cómo se calcula la estancia?», «fórmula DAX del indicador»: flujo normal.
- Contrapregunta pendiente o elección en curso: el portero nunca actúa.
- MiniLM no disponible o falla: solo reglas, sin error visible.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST reconocer como fuera de alcance, sin LLM ni consultas, las categorías: petición vaga, cálculo/matemáticas, noticias/actualidad, clima, recetas, deportes, entretenimiento (chistes, juegos, películas, música), programación, redacción de textos genéricos (correos, cartas, poemas, traducciones), conocimiento general, consejo clínico para un paciente, otra institución y mensajes sin sentido o vacíos.
- **FR-002**: Cada detección MUST basarse en un marcador explícito de su categoría (frase o patrón) o, como última barrera, en similitud MiniLM con umbral y margen conservadores frente a preguntas de dominio.
- **FR-003**: El sistema MUST NOT clasificar fuera de alcance si, fuera del marcador detectado, el mensaje contiene una palabra del catálogo de tableros/indicadores (tolerando tipeos de una letra), una referencia al propio hospital, un periodo o un número; las categorías noticias, clima, deportes y consejo clínico toleran periodos, y cálculo y consejo clínico toleran números. Consejo clínico tolera además el vocabulario clínico propio de la pregunta (dosis, medicamento, paciente, tratamiento…). Otra institución se anula con cualquier palabra de flujo entre instituciones (remisión, traslado, convenio, aseguradora, «del/al/desde» antes del nombre) o primera persona plural.
- **FR-004**: Las peticiones vagas MUST reconocerse solo cuando el mensaje es ENTERO una plantilla vaga (incluido «hazme un reporte de» sin tema); «hazme un reporte», «dame un resumen», «hazme un gráfico» quedan en el flujo normal (pueden ser seguimientos).
- **FR-005**: La similitud MUST aplicarse solo a mensajes de 3 a 12 palabras sin ninguna palabra del catálogo, periodo, número ni mención del hospital.
- **FR-006**: Las respuestas MUST ser textos fijos, cortos y amables que digan qué SÍ puede hacer el asistente; la de petición vaga incluye la lista de tableros del catálogo (texto de capacidades).
- **FR-007**: El portero MUST NOT actuar con contrapregunta abierta o elección en curso, y ante cualquier fallo el mensaje MUST seguir el flujo normal (igual que la primera entrega).
- **FR-008**: El razonamiento visible MUST indicar «Mensaje fuera de alcance» (o «Petición sin tema» / «Mensaje sin contenido reconocible»), la categoría y el motivo (marcador o similitud). El resultado reutiliza la ruta que el motor, la app, el evaluador y la memoria ya entienden: `status = "not_found"`, `route = "out_of_scope"` para las categorías de rechazo, y `status = "success"`, `route = "conversacion"` para petición vaga y sin sentido; siempre con `conversation_kind = "fuera_de_alcance/<categoría>"` y `stage = "portero/fuera_de_alcance/<categoría>"` (el registro de calificaciones lo guarda como `etapa`).
- **FR-009**: Un rechazo fuera de alcance MUST cortar el contexto de seguimiento y registrarse en la memoria igual que la ruta `out_of_scope` existente (otro tema: «¿y en 2025?» ya no sigue la consulta anterior; caso `i_sim_seguimiento_tras_otro_tema` del evaluador). Petición vaga y sin sentido MUST NOT alterarlo (como la charla).
- **FR-010**: La detección se hace sobre el mensaje original del usuario (la normalización del motor corrige tipeos hacia el catálogo y puede inventar palabras de dominio: «arepas» → «áreas»).

### Key Entities

- **Clasificación**: se amplía con `tipo = "fuera_de_alcance"`, subtipo = categoría y `detalle` (marcador o similitud que la justifica).
- **Banco del portero**: se añaden casos `F*` (fuera de alcance, con su categoría) y casos `N*` de dominio difíciles (deben pasar al flujo normal).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 0 preguntas reales interceptadas en todos los bancos (desarrollo, holdout 1 y 2, multi-turno, evaluador `tests/eval/questions.json`, diccionario `tests/eval/diccionario_preguntas.json`; sin los rechazos que el propio banco etiqueta) y en los casos de dominio del banco del portero, con y sin MiniLM.
- **SC-002**: ≥ 90 % de los casos `F*` del banco reconocidos solo con reglas, y cada categoría con al menos 80 %.
- **SC-003**: Los 5 ejemplos del usuario se resuelven como en la tabla: vaga, cálculo, noticias, otra institución y «hazme un reporte de» → fuera de alcance; «hazme un reporte de la ocupación de camas» → flujo normal.
- **SC-004**: La clasificación añade < 5 ms por mensaje con reglas y < 50 ms con similitud.

## Assumptions

- Mismo modelo MiniLM ya cargado; ningún modelo nuevo ni servidor compartido.
- Se reutilizan las rutas existentes `out_of_scope` y `conversacion` (app, registro, evaluador y memoria ya las manejan) en lugar de una ruta nueva: no se tocan `app.py` ni `src/ui/` (otro agente trabaja allí).
- Los bancos reales ya traen rechazos etiquetados (`tipo: fuera_alcance`, H47–H49 y G48–G50) y el evaluador casos `g_fuera_alcance`: son positivos, no se cuentan como falsos positivos.
- Insultos, inglés y preguntas de opinión quedan fuera de esta entrega (siguen el flujo normal).
- Power BI y bases de datos: solo lectura; nada de datos de pacientes en salidas, logs o commits.
