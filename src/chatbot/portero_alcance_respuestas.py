"""Ejemplos de similitud y textos fijos de respuesta del portero de alcance
(spec 002). Sin lógica de clasificación."""

from __future__ import annotations

# Ejemplos para la similitud (normalizados). No incluyen los casos del banco.
EJEMPLOS = {
    "vago": [
        "me colaboras con una cosita", "oye te tengo una preguntica", "me podrias ayudar en algo",
        "necesito que me colabores", "quiero hacerte una consulta rapida",
        "tengo una inquietud que resolver", "me haces un favor", "necesito una ayudita",
    ],
    "calculo": [
        "cuanto es siete por ocho", "ayudame a resolver este problema de matematicas",
        "como se saca la raiz de un numero", "cuanto da la division de cien entre cuatro",
        "ayudame con mi tarea de matematicas", "cual es el resultado de esta suma",
        "como saco el porcentaje de un numero", "cuanto es pi",
    ],
    "noticias": [
        "que esta pasando en el mundo", "cuales son las noticias mas importantes",
        "que se sabe de la guerra", "quien es el presidente de colombia",
        "como va la economia del pais", "que dijeron en el noticiero",
        "que paso en las elecciones", "a como esta el euro",
    ],
    "clima": [
        "como va a estar el clima", "va a hacer sol el fin de semana",
        "hace frio afuera", "esta haciendo mucho calor", "cuantos grados hace afuera",
        "necesito paraguas", "como amanecio el clima", "va a llover esta tarde",
    ],
    "recetas": [
        "como hago un arroz con pollo", "que puedo cocinar con papa y huevo",
        "dame ideas para la comida", "como se prepara una limonada de coco",
        "ensenarme a cocinar frijoles", "que como para bajar de peso",
        "como hago un pastel de cumpleanos", "receta facil para la cena",
    ],
    "deportes": [
        "como le fue a la seleccion", "quien va ganando la liga", "que equipo es mejor",
        "a que hora juega colombia", "cuando es el clasico", "quien es el mejor futbolista del mundo",
        "como quedo el clasico", "quien gano la carrera de ciclismo",
    ],
    "entretenimiento": [
        "dime algo gracioso", "cuentame algo divertido", "que me recomiendas ver en la noche",
        "estoy aburrido que hago", "juega conmigo", "cual es tu cancion favorita",
        "dime una frase motivadora", "recomiendame un libro",
    ],
    "programacion": [
        "como hago una pagina web", "ensenarme a programar", "como instalo una libreria de python",
        "que lenguaje de programacion me recomiendas", "como hago una macro",
        "como arreglo este error de codigo", "explicame que es una variable en programacion",
        "como se crea una base de datos en mysql",
    ],
    "redaccion": [
        "ayudame a escribir una carta", "redactame un correo formal", "necesito un texto para mi jefe",
        "corrige la ortografia de este texto", "escribe un mensaje bonito para mi mama",
        "ayudame con un ensayo", "hazme un resumen de un libro", "escribe una carta de recomendacion",
    ],
    "conocimiento": [
        "quien descubrio america", "cual es el rio mas largo del mundo", "cuantos paises hay en el mundo",
        "por que el cielo es azul", "que significa la palabra resiliencia",
        "cual es el animal mas grande", "en que continente queda egipto", "cuantos huesos tiene el cuerpo humano",
    ],
    "clinico": [
        "que remedio sirve para el dolor de muela", "me siento mal que me tomo",
        "que me tomo para el dolor de cabeza", "es normal tener fiebre despues de una vacuna",
        "que hago si me sube la presion", "que medicamento es bueno para la gastritis",
        "como bajo la fiebre de mi hijo", "cuanto acetaminofen le doy a mi bebe",
    ],
}


_EJEMPLO = "«¿Cuántas cirugías se realizaron el mes pasado?»"
_PUEDO = ("Puedo responder preguntas sobre los indicadores y la documentación de los tableros "
          "institucionales de Power BI del Hospital Universitario de Caldas, por ejemplo: "
          f"{_EJEMPLO}. Escribe «¿qué puedes hacer?» para ver la lista de tableros.")

_GRUPO = {
    "vago": "vago", "clinico": "clinico", "otra_institucion": "otra_institucion",
    "redaccion": "redaccion", "programacion": "redaccion", "sin_sentido": "sin_sentido",
}

_TEXTOS = {
    "general": f"Eso está fuera del alcance de los tableros: no es algo que yo pueda responder. {_PUEDO}",
    "redaccion": ("No redacto correos, textos ni código. Sí puedo darte las cifras y la "
                  f"explicación de los indicadores para que armes tu documento. {_PUEDO}"),
    "clinico": ("No doy recomendaciones clínicas, diagnósticos ni dosis para pacientes: para eso "
                "consulta al médico tratante o los protocolos institucionales. Sí puedo darte "
                "cifras de los tableros, por ejemplo: «¿Cuántos pacientes activos con antibiótico "
                "hay?». Escribe «¿qué puedes hacer?» para ver la lista de tableros."),
    "otra_institucion": ("Solo tengo información de los tableros del Hospital Universitario de "
                         "Caldas; no tengo datos de otras instituciones. Si buscas las remisiones o "
                         "traslados hacia otras instituciones, pregúntame por ellas, por ejemplo: "
                         "«¿Cuántas remisiones hubo el mes pasado?». Escribe «¿qué puedes hacer?» "
                         "para ver la lista de tableros."),
    "sin_sentido": f"No entendí tu mensaje. {_PUEDO}",
    "vago": "Claro, con gusto. Dime qué dato o tablero necesitas y, si aplica, el periodo.",
}


def texto_respuesta(subtipo: str, capacidades: str = "") -> str:
    """Texto fijo para un subtipo fuera de alcance (la vaga añade las capacidades)."""
    grupo = _GRUPO.get(subtipo, "general")
    texto = _TEXTOS[grupo]
    if grupo == "vago" and capacidades:
        return f"{texto}\n\n{capacidades}"
    return texto
