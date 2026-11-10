# Constitución de Proyecto_RAG

Asistente RAG + Power BI del SES Hospital Universitario de Caldas. Estos principios mandan sobre
cualquier spec, plan o tarea de `specs/`. El detalle operativo (carpetas, capas, convenciones y plan
por fases) vive en `docs/ARQUITECTURA.md`; el resumen, en `CLAUDE.md`.

## Principios

### I. Power BI y producción: solo lectura (NO NEGOCIABLE)

El sistema **consulta** modelos semánticos, tableros y bases de datos; nunca los crea, modifica ni
borra. Los clientes de Power BI exponen solo lectura (XMLA/DAX y GET de la API REST). Las pruebas
corren contra el simulador; las corridas reales son pocas, se lanzan desde el checkout principal y
con permiso del usuario. Un agente nunca lee, carga ni edita el `.env`.

### II. Nada de datos de pacientes (NO NEGOCIABLE)

Ninguna fila con datos de pacientes (nombres, documentos, contactos, familiares) aparece en salidas,
logs, trazas, fixtures ni commits. Los listados del motor excluyen columnas de identificación y
contacto; los logs de advertencia no incluyen el texto del usuario. Ante la duda, se omite el dato.

### III. Un falso positivo es peor que un falso negativo

Una cifra equivocada dicha con seguridad hace más daño que una contrapregunta o un «no encontré».
Cuando el motor duda entre fuentes con cifras distintas, pregunta; cuando un atajo (portero,
seguimiento, filtro implícito) no está seguro, se desactiva y deja seguir el flujo normal. Las
reglas nuevas se miden con los bancos reales: no se acepta una mejora que añada respuestas
inventadas o filtros espurios.

### IV. Pruebas primero (TDD)

Todo cambio de comportamiento trae su prueba en el mismo commit (roja → verde), en
`tests/<área>/test_<tema>.py` nombrada por comportamiento. Los refactors del motor no cambian
comportamiento: **golden master idéntico** (`tests.resolution.test_golden`, foto tomada y comparada
el mismo día) y pruebas de equivalencia para cada sustitución de utilidades.

### V. El doctor con trinquete: el listón solo sube

`python -X utf8 -m tools.doctor --verificar` debe pasar antes de integrar: ningún cambio baja el
puntaje (global, de perfil o de categoría) ni introduce hallazgos altos nuevos. Cuando el puntaje
sube, se sube el listón con `--actualizar-linea-base`. `--forzar` solo para un retroceso consciente,
justificado en el commit.

### VI. Capas: se importa solo hacia abajo

`backend/app → src.chatbot/feedback → dominio (semantic, dax, docs_md, ingestion, catalogo) →
infraestructura (providers, llm, rag) → src.comun`. `src` nunca importa `backend`, `tools`, `tests`,
`app`, `pages`, `fastapi` ni `redis`; fuera del legado tampoco `streamlit`. Sin ciclos entre paquetes.
Las utilidades transversales (rutas, texto, JSON, logging, entorno) existen **una sola vez**, en
`src/comun/`: se busca antes de crear.

### VII. Simplicidad y tamaño acotado

Un módulo, una responsabilidad nombrada en español. Archivo ≤ 800 líneas, función ≤ 80. Ningún
cambio hace crecer un archivo que ya pasa el máximo sin extraer más de lo que añade. La librería usa
`logging`; `print` solo en CLIs. El legado Streamlit está congelado: solo arreglos críticos.

## Flujo de trabajo

- spec-kit (`/speckit-specify` → `clarify` → `plan` → `tasks` → `analyze` → `implement`) y las
  habilidades de superpowers (brainstorming, writing-plans, TDD, systematic-debugging,
  verification-before-completion, requesting-code-review).
- Agentes en ramas `agente/<tema>` y worktrees propios; commits pequeños en español con el porqué.
  Las fases que tocan `src/` se coordinan: dos agentes no editan el mismo archivo a la vez.
- graphify al día (`graphify update .`) tras cada cambio de código.

## Gobierno

Esta constitución prevalece sobre specs y planes. Una enmienda se propone en un commit que explique
el motivo, actualice `docs/ARQUITECTURA.md` y `CLAUDE.md` si cambian reglas verificables y suba la
versión (mayor: se quita o redefine un principio; menor: se añade uno; parche: redacción).

**Versión**: 1.0.0 | **Ratificada**: 2026-11-10 | **Última enmienda**: 2026-11-10
