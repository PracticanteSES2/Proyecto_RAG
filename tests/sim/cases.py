"""
Conversaciones guiadas del smoke test. Cada caso es una conversación NUEVA
(run_case resetea antes y después); `turns` son los mensajes consecutivos del
usuario (los de aclaración se responden en el turno siguiente).

Para agregar un caso: añade una entrada a CASES y, si quieres verificarlo,
una función test_* en test_smoke.py.
"""

CASES = {
    # ---- 12 mensajes del prototipo, agrupados en conversaciones ----
    "base_descriptivo": {
        "label": "descriptivo + respuesta a aclaración",
        "turns": ["¿Qué muestra el tablero de atenciones?", "Tablero de Atenciones Institucionales"],
    },
    "base_descriptivo_filtros": {
        "label": "descriptivo-filtros + respuesta a aclaración",
        "turns": ["¿Qué filtros tiene el tablero de cirugías?", "Tablero Quirurgico"],
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
}
