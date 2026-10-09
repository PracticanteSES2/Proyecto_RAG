"""
Conversaciones guiadas del smoke test. Cada caso es una conversación NUEVA
(run_case resetea antes y después); `turns` son los mensajes consecutivos del
usuario (los de aclaración se responden en el turno siguiente).

Para agregar un caso: añade una entrada a CASES y, si quieres verificarlo,
una función test_* en test_smoke.py.
"""

CASES = {
    # ---- 12 mensajes del prototipo, agrupados en conversaciones ----
    # Sin nombrar el tablero: hay varios candidatos y se pregunta cuál.
    "base_descriptivo": {
        "label": "descriptivo + respuesta a aclaración",
        "turns": ["¿Qué muestra el tablero?", "Tablero de Atenciones Institucionales"],
    },
    "base_descriptivo_filtros": {
        "label": "descriptivo-filtros + respuesta a aclaración",
        "turns": ["¿Qué filtros tiene el tablero?", "Tablero Quirurgico"],
    },
    # Tablero nombrado por un alias (o con un error de tipeo): no se pregunta.
    "tablero_por_alias": {
        "label": "descriptivo con alias del tablero",
        "turns": ["¿Qué muestra el tablero de atenciones?"],
    },
    "tablero_alias_typo": {
        "label": "descriptivo con alias del tablero mal escrito",
        "turns": ["que filtros tiene el tablero de lavandria"],
    },
    "tablero_ordinal": {
        "label": "contrapregunta de tablero respondida con un ordinal",
        "turns": ["¿Qué muestra el tablero?", "la segunda"],
    },
    "base_dato_aclaracion": {
        "label": "dato ambiguo entre modelos + respuesta '1'",
        "turns": ["¿Cuántas cirugías realizadas hubo en 2024?", "1"],
    },
    "base_dato_filtro_mes": {
        "label": "dato + filtro + mes",
        "turns": ["¿Cuántas cirugías programadas de ortopedia en marzo de 2024?"],
    },
    "base_dato_agrupado": {
        "label": "dato agrupado",
        "turns": ["¿Cuál fue el total de atenciones por sede?"],
    },
    "base_ambigua": {
        "label": "pregunta ambigua",
        "turns": ["¿Cuántas cirugías hay?"],
    },
    "base_enrutado_fuerte": {
        "label": "dato enrutado fuerte con 2 filtros categóricos",
        "turns": ["¿Cuántas cirugías realizadas de cirugía plástica hubo en la sede norte en 2024 "
                  "en el Tablero de Atenciones Institucionales?"],
    },
    "base_definicion_rag": {
        "label": "definición (RAG)",
        "turns": ["¿Qué significa el indicador cirugías programadas?"],
    },
    "base_fuera_de_alcance": {
        "label": "fuera de alcance",
        "turns": ["¿Cuál es la capital de Francia?"],
    },

    # ---- Tablero Lavandería (chat real que falla) ----
    "lav_q1": {
        "label": "Lavandería: servicio + mes + peso y participación",
        "turns": ["En el mes de enero de 2026 en el servicio de antifluidos de la lavanderia, "
                  "cuanta participacion y peso tuvo?"],
    },
    "lav_q2": {
        "label": "Lavandería: igual que q1, orden distinto",
        "turns": ["Cuanta participacion y peso tuvo el servicio de antifluidos en la lavanderia "
                  "en el mes de enero de 2026?"],
    },
    "lav_q3": {
        "label": "Lavandería: solo peso",
        "turns": ["Cuanto peso tuvo el servicio de antifluidos en la lavanderia en el mes de enero de 2026?"],
    },
    "lav_q4": {
        "label": "Lavandería: solo participación",
        "turns": ["Que participacion tuvo antifluidos en enero de 2026 en lavanderia?"],
    },
    "lav_q5": {
        "label": "Lavandería: telegráfico",
        "turns": ["peso de antifluidos enero 2026 lavanderia"],
    },
    "lav_q6": {
        "label": "Lavandería: desglose por turno",
        "turns": ["Dime el peso por turno en lavanderia en enero de 2026"],
    },
    # ---- Extras para bugs conocidos ----
    "lav_mes_sin_anio": {
        "label": "Lavandería: mes sin año",
        "turns": ["Cuanto peso tuvo el servicio de antifluidos en la lavanderia en enero?"],
    },
    "qx_mes_sin_anio": {
        "label": "Quirúrgico: mes sin año",
        "turns": ["¿Cuántas cirugías programadas de ortopedia en el Tablero Quirurgico en marzo?"],
    },
    # ---- controles positivos: lo que SÍ sabe hacer hoy el Query Plan ----
    "lav_por_servicio": {
        "label": "Lavandería: peso agrupado por servicio (base de la participación)",
        "turns": ["Cuanto peso por servicio en lavanderia en enero de 2026"],
    },
    "lav_por_turno_ok": {
        "label": "Lavandería: peso agrupado por TURNO_OK (nombre técnico de la columna)",
        "turns": ["Cuanto peso por turno ok en lavanderia en enero de 2026"],
    },
    # ---- contrapreguntas en lugar de «no encontré» ----
    "req_necesito_typo": {
        "label": "petición con «necsito» (error de tipeo) + total + año",
        "turns": ["necsito saber el total de la cirugias del 2024?"],
    },
    "req_sugerencias": {
        "label": "métrica poco específica -> opciones sugeridas + respuesta '1'",
        "turns": ["cuantas cirugias hubo en 2024", "1"],
    },
    "req_palabra_no_entendida": {
        "label": "palabra que no es filtro -> ¿consultar sin ella? + 'sí'",
        "turns": ["total de cirugías azules en 2024", "sí"],
    },
    "req_sugerencias_abandonadas": {
        "label": "opciones sugeridas + pregunta nueva fuera de alcance",
        "turns": ["cuantas cirugias hubo en 2024", "¿Cuál es la capital de Francia?"],
    },
    # ---- elección por ordinal ----
    "ordinal_metrica": {
        "label": "contrapregunta de indicador respondida con «la primera»",
        "turns": ["¿Cuántas cirugías realizadas hubo en 2024?", "la primera"],
    },
    "ordinal_ultima": {
        "label": "contrapregunta respondida con «la última»",
        "turns": ["cuantas cirugias hubo en 2024", "la última"],
    },
    # ---- palabras corrientes y sinónimos que no son filtros ----
    "verbo_registrado": {
        "label": "«hay registrado» no es un filtro",
        "turns": ["cuanto peso total hay registrado en lavanderia"],
    },
    "verbo_llevamos": {
        "label": "«llevamos» no es un filtro",
        "turns": ["cuantas cirugias programadas llevamos en 2024 en el tablero quirurgico"],
    },
    "sinonimo_kilos": {
        "label": "«kilos» = peso",
        "turns": ["cuantos kilos hubo en lavanderia en enero de 2026"],
    },
    "sinonimo_colaborador": {
        "label": "«por colaborador» = NOMBRE_COMPLETO",
        "turns": ["peso por colaborador en lavanderia en enero de 2026"],
    },
    # ---- «cuántas X» ≈ «total de X» y filtro por servicio ----
    "conteo_como_total": {
        "label": "«cuántas atenciones» con sede, servicio y año",
        "turns": ["cuantas atenciones hubo en la sede sur en 2024 en urgencias"],
    },
    "atenciones_urgencias": {
        "label": "«atenciones de urgencias» es Power BI con SERVICIO = URGENCIAS",
        "turns": ["atenciones de urgencias en 2024"],
    },
    # ---- indicador sin respaldo / fuera de alcance / genérico ----
    "metrica_sin_respaldo": {
        "label": "la agrupación no basta para elegir el indicador",
        "turns": ["citas asignadas por especialidad"],
    },
    "agrupacion_no_elige_indicador": {
        "label": "«total de cirugías por especialidad» es TOTAL CIRUGÍAS, no la visual por especialidad",
        "turns": ["total de cirugias por especialidad en 2024"],
    },
    "fuera_alcance_numerico": {
        "label": "pregunta numérica fuera de alcance",
        "turns": ["cuanto gana un medico general en colombia"],
    },
    "pregunta_generica": {
        "label": "pregunta genérica sin indicador",
        "turns": ["promedio mensual"],
    },
    # ---- ranking ----
    "ranking_servicio": {
        "label": "el servicio con más peso",
        "turns": ["cual fue el servicio con mas peso en lavanderia en enero 2026"],
    },
    "ranking_menos": {
        "label": "el servicio con menos peso",
        "turns": ["que servicio tuvo menos peso en enero 2026 en lavanderia"],
    },
    "ranking_top": {
        "label": "top 5 especialidades con más cirugías + elección del indicador",
        "turns": ["top 5 especialidades con mas cirugias", "2"],
    },
    # ---- seguimiento de la última respuesta numérica ----
    "seguimiento": {
        "label": "«y en 2025?», «y por especialidad», «y de ortopedia?»",
        "turns": ["cirugias programadas de urologia en 2024", "y en 2025?", "y por especialidad",
                  "y de ortopedia?"],
    },
    "seguimiento_tras_otro_tema": {
        "label": "sin seguimiento después de una respuesta no numérica",
        "turns": ["cirugias programadas de urologia en 2024", "¿Cuál es la capital de Francia?",
                  "y en 2025?"],
    },
    "seguimiento_pregunta_nueva": {
        "label": "«y ...» con otro indicador es una pregunta nueva",
        "turns": ["cirugias programadas de urologia en 2024",
                  "y cuanto peso hubo en lavanderia en enero de 2026?"],
    },
    # ---- periodos: rangos, relativos y agrupación temporal ----
    "per_lav_rango_meses": {
        "label": "Lavandería: rango de meses (columna de fecha)",
        "turns": ["peso de lavanderia entre enero y marzo de 2025"],
    },
    "per_lav_este_anio": {
        "label": "Lavandería: «este año» (relativo a la fecha de referencia)",
        "turns": ["cuanto peso lleva la lavanderia este año"],
    },
    "per_lav_por_mes_2025": {
        "label": "Lavandería: peso por mes en 2025 (agrupación temporal)",
        "turns": ["peso lavanderia 2025 por mes"],
    },
    "per_qx_por_mes_2024": {
        "label": "Quirúrgico: por mes con AÑO/MES enteros",
        "turns": ["cirugias programadas por mes en el tablero quirurgico en 2024"],
    },
    "per_qx_rango_cruzado": {
        "label": "Quirúrgico: rango de meses entre dos años con AÑO/MES enteros",
        "turns": ["total cirugias del tablero quirurgico de noviembre de 2024 a febrero de 2025"],
    },
    "per_qx_hoy": {
        "label": "Quirúrgico: «hoy» sin columna de fecha diaria",
        "turns": ["cirugias programadas de hoy en el tablero quirurgico"],
    },
    # ---- enrutamiento v2: descriptivas, tablero nombrado, valores implícitos ----
    "enr_descriptiva_porcentaje": {
        "label": "«¿cómo se calcula el porcentaje…?» va a la documentación, no a Power BI",
        "turns": ["¿Cómo se calcula el porcentaje de participación del peso en la lavandería?"],
    },
    "enr_tablero_nombrado_valor": {
        "label": "Lavandería nombrada como «tablero de …» + valor implícito con su porqué",
        "turns": ["peso de antifluidos en enero de 2026 del tablero de lavanderia"],
    },
    "enr_por_x_tablero_nombrado": {
        "label": "«por especialidad» + «tablero quirurgico» (sus palabras no son valores)",
        "turns": ["cirugias programadas por especialidad en 2024 en el tablero quirurgico"],
    },
    # ---- resolución del indicador: tipeo, calificativos, núcleo sin interpretar ----
    "typo_nesesito": {
        "label": "«nesesito» (c/s) es una palabra de petición, no un filtro",
        "turns": ["nesesito saber el total de atenciones en 2024"],
    },
    "calificativo_aproximado": {
        "label": "«ortopédicas» se empareja por raíz con ORTOPEDIA Y TRAUMATOLOGIA",
        "turns": ["cuantas cirugias programadas ortopedicas hubo en 2024"],
    },
    "nucleo_sin_interpretar": {
        "label": "el sustantivo principal no es el indicador: no se ofrece «sin X»",
        "turns": ["escribeme un codigo en python para ordenar las cirugias programadas"],
    },
}
