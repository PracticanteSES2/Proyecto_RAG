# Research: Portero conversacional

Fuente: agente investigador (2026-11-09), con fuentes web y medición local con el MiniLM real
(`paraphrase-multilingual-MiniLM-L12-v2`, caché local, sin red; sin archivos ni `.env`).

## Medición local (8 ejemplos de charla, 4 de dominio)

| Mensaje | Similitud con charla | Margen vs. dominio | Lectura |
|---|---|---|---|
| «sí» → «gracias» | 0.85 | — | monosílabos ≈ saludo real |
| «listo» → «gracias» | 0.87 | — | idem |
| «ok» → «gracias» | 0.82 | — | idem |
| «buenas» | 0.83 | — | saludo real |
| «resumen», «camas» → «gracias» | 0.64 | — | dominio suelto también sube |
| «¿cómo estamos este mes?» | 0.48 | +0.09 | peligroso: se acerca a «¿cómo estás?» |
| «¿cómo estás hoy?» | 0.71 | +0.56 | charla real |
| «todo bien por allá?» | 0.64 | +0.40 | charla real |
| «hola, ¿cuántas cirugías en octubre?» | — | −0.58 | dominio claro |

## Decisiones

### D1. Similitud solo para 3–8 palabras; 1–2 palabras solo por reglas
- **Decisión:** mensajes de ≤2 palabras se resuelven exclusivamente con reglas de coincidencia completa.
- **Rationale:** en textos muy cortos el coseno tiene un suelo alto (anisotropía de encoders tipo BERT); la medición lo confirma («sí»/«ok»/«listo» ≥0.82).
- **Alternatives:** similitud para todo con umbral más alto (no separa «ok» de «buenas»).

### D2. Umbral 0.80 y margen 0.20 iniciales; calibración por barrido
- **Decisión:** umbral 0.80; margen = mejor charla − **máximo** de dominio ≥ 0.20. Barrido umbral 0.70–0.85 (paso 0.025) y margen 0.10–0.30 sobre banco del portero + `banco_real`; elegir el punto con 0 falsos positivos y un colchón de 0.05 sobre el FP de mayor puntuación.
- **Rationale:** NeMo Guardrails parte de 0.75 y recomienda 0.8 ante falsos positivos; Rasa usa umbral + `ambiguity_threshold` (equivalente al margen); semantic-router ajusta umbrales por encoder con negativos `None` (los umbrales no son transferibles entre modelos).
- **Alternatives:** umbral por tipo (identidad/capacidades algo más bajos); `fit()` estilo semantic-router. Si la exhaustividad queda <90 %, ampliar ejemplos antes de bajar el umbral.
- **Fuentes:** https://docs.aurelio.ai/semantic-router/user-guide/features/threshold-optimization · https://docs.nvidia.com/nemo/guardrails/0.15.0/user-guides/configuration-guide/guardrails-configuration.html · https://legacy-docs-oss.rasa.com/docs/rasa/fallback-handoff/

### D3. `normalize_embeddings=True` + producto punto, ejemplos precalculados
- **Rationale:** equivale al coseno y es más rápido; el modelo no trae módulo Normalize, hay que pedirlo.
- **Fuentes:** https://sbert.net/docs/sentence_transformer/usage/semantic_textual_similarity.html · https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2

### D4. Frases de dominio que parecen charla: nunca por similitud
- **Decisión:** lista de bloqueo y negativos de calibración: «como vamos», «como estamos (…)», «como va/esta X», «que hay de nuevo», «resumen», «novedades», «ayuda con/para X»; y «listo», «ok», «si», «no», «ninguna», «dale», «perfecto» solos (respuestas a contrapregunta: flujo normal).
- **Decisión:** «ayuda» sola = capacidades; «ayuda con X» = flujo normal.
- **Rationale:** en un hospital «¿cómo vamos?» pide indicadores; las mediciones muestran cercanía con «¿cómo estás?».
- **Alternatives:** responder «¿cómo vamos?» con contrapregunta de tablero (segunda entrega).

### D5. Negativos de referencia
- **Decisión:** 40–80 preguntas cortas de dominio (incluye D4 y nombres sueltos de indicadores) + preguntas de `banco_real`. Nunca holdouts ni multi-turno.

### D6. Vocabulario colombiano / chat (reglas y ejemplos, normalizado)
- saludo: hola, holi, ola, hola hola, buenas, buenos dias, buen dia, buenas tardes, buenas noches, q mas, que mas, quiubo, quiubole, k mas pues, hey, saludos, hola que tal, q tal, que tal, hola buenas
- estado: como estas, como esta, como estas hoy, como te va, como vas, todo bien, todo bien por alla, bien y tu, como amaneciste, que mas como vas, como le va
- agradecimiento: gracias, grax, grcias, graciass, mil gracias, muchas gracias, muchisimas gracias, gracias por la ayuda, ok gracias, perfecto gracias, listo gracias, super gracias, te agradezco, muy amable, dios le pague
- despedida: chao, chau, adios, hasta luego, hasta pronto, nos vemos, bendiciones, que este bien, feliz dia, feliz tarde, buena noche, me despido
- identidad: quien eres, que eres, con quien hablo, eres un robot, eres humano, como te llamas
- capacidades: que puedes hacer, que sabes hacer, en que me ayudas, para que sirves, que tableros hay, ayuda
- Tipeos: distancia de edición ≤1 permitida solo dentro de las reglas (palabras ≥4 letras). No validado contra corpus: el probador adversarial debe ampliarlo.

### D7. Excepción de FR-003 para frases de regla completas (ruling F4, revisión final)
- **Decisión:** si el mensaje normalizado es ENTERO una o dos frases de regla, sin ediciones (tipeos), las guardas de dominio, periodo y largo no lo bloquean. La guarda de número, la lista de bloqueo (D4) y el estado pendiente siempre aplican.
- **Motivo:** el probador adversarial halló saludos exactos bloqueados por palabras de dominio del catálogo («todos» en «buenos días a todos», «mañana»/«manana» en «hasta mañana», «nombre» en «cuál es tu nombre»).
- **Riesgo acotado:** solo pasan frases completas curadas (nunca texto libre); una pregunta de datos no es una frase de regla. Verificado con barrido ciego de 243 textos: 0 intercepciones.
- **Alternatives:** quitar «todos», «manana» y «nombre» del vocabulario de dominio (descartado: afecta preguntas reales).

## Sin NEEDS CLARIFICATION pendientes.
