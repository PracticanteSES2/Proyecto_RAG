"""Portero de alcance (segunda entrega): mensajes que no tienen nada que ver con
los tableros de Power BI del hospital ni con su documentación.

Módulo puro, sin LLM ni consultas. Regla de oro: un falso positivo (bloquear una
pregunta real) es mucho peor que un falso negativo, así que en la duda devuelve
``None`` y el mensaje sigue el flujo normal.

Cómo decide (spec 002, FR-002/FR-003):

1. Plantillas vagas de mensaje ENTERO («necesito que me respondas algo»,
   «hazme un reporte de» sin tema).
2. Mensajes vacíos, risa o tecleo al azar en TODAS sus palabras (sin sentido).
3. Marcadores explícitos por categoría (regex sobre el texto normalizado). Las
   palabras dentro del marcador quedan toleradas; cualquier otra palabra del
   catálogo (con tipeo de una letra), periodo, número o mención del propio
   hospital ANULA la detección, salvo las tolerancias de cada categoría.
4. Sin marcador: similitud MiniLM (ver ``portero.SimilitudPortero.mejor_alcance``)
   solo sobre mensajes «limpios» de 3 a 12 palabras.

Se analiza el mensaje ORIGINAL del usuario: la normalización del motor corrige
tipeos hacia el catálogo y puede inventar palabras de dominio («arepas» →
«áreas», «respondas» → «respondidas»).
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache

MAX_CARACTERES = 200
MIN_PALABRAS_SIMILITUD = 3
MAX_PALABRAS_SIMILITUD = 12
# Calibración (MiniLM real, 2026-11-10): tras las anulaciones estrictas solo 7
# preguntas reales de todos los bancos llegan «limpias» a la similitud y ninguna
# pasa ni con 0.70/0.05; se fijan los mismos 0.80/0.20 de la charla (colchón) y
# además la similitud de alcance debe superar a la de charla («gracias, ¿qué
# más?» 0.80 alcance vs 0.97 charla). Paráfrasis nuevas captadas: 6/15.
UMBRAL = 0.80
MARGEN = 0.20

TIPO = "fuera_de_alcance"


def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes, sin signos, espacios colapsados (= portero.normalizar)."""
    base = unicodedata.normalize("NFKD", str(texto or "").lower())
    base = "".join(c for c in base if not unicodedata.combining(c))
    base = re.sub(r"[^a-z0-9]+", " ", base)
    return " ".join(base.split())


# Jerga de chat y tipeos frecuentes de las palabras de los marcadores.
_JERGA = {
    "q": "que", "k": "que", "ke": "que", "qe": "que", "d": "de", "pa": "para",
    "xq": "porque", "pq": "porque", "tb": "tambien", "tmb": "tambien",
    "nesecito": "necesito", "nesesito": "necesito", "necsito": "necesito",
    "nececito": "necesito", "nesito": "necesito", "necesitp": "necesito",
    "kiero": "quiero", "qiero": "quiero", "cuentam": "cuentame",
}
_RELLENO = frozenset({"porfa", "porfavor", "plis", "pls", "xfa", "please", "porfis"})

# Palabras genéricas del español que el catálogo arrastra (nombres de medidas,
# columnas): nunca cuentan como dominio en esta capa. La charla usa el
# vocabulario completo; aquí solo se buscan señales de dominio reales.
GENERICAS = frozenset({
    "las", "los", "del", "una", "dos", "sin", "sobre", "entre", "tiene", "hace",
    "solo", "todos", "todas", "otra", "otras", "otro", "son", "vez", "veces",
    "casi", "cada", "mal", "claro", "nunca", "siempre", "igual", "misma",
    "mismo", "real", "realmente", "sentido", "general", "pueden", "existe",
    "existen", "contra", "desde", "dentro", "frente", "fuera", "alcance",
    "cuatro", "cero", "posible", "posibles", "parecido", "parecidos", "primer",
    "primera", "primeros", "segundo", "siguiente", "vista", "modo", "uso",
    "usar", "volver", "corto", "alto", "bajo", "mayor", "mayores", "libre",
    "local", "azul", "blanco", "color", "colores", "mano", "hogar", "obra",
    "calor", "arbol", "anillo", "moda", "vision", "nuevos", "efecto", "final",
    "fin", "completo", "original", "propia", "conocido", "segun", "tipo",
    "tipos", "caso", "casos", "manual", "una", "iniciar", "inicio", "principal",
    "importadas", "import", "top", "com", "net", "eco", "iii", "ult", "seg",
    "nom", "num", "min", "hor", "pas", "ter", "ant", "act", "cam", "cod", "col",
    "dif", "dim", "dom", "eje", "exp", "fec", "ing", "ins", "lec", "mon", "obs",
    "pac", "pat", "ref", "reg", "rent", "serv", "uni", "vig", "ate", "arc",
    "ive", "pra", "trat", "corr", "prod", "prom", "cant", "comp", "cons",
    "hist", "hosp", "espe", "aten", "admi", "factu", "consul", "dispo",
    "descri", "especi", "activi", "observ", "trige", "point", "share", "drive",
    "query", "power", "date", "count", "column", "direct", "pivot", "expr",
    "vacia", "vacio", "vacios", "nula", "dueno", "hueco", "huecos", "casilla",
    "casillas", "mayusc", "parentesis", "llamativa", "calor", "presion",
})

_PERIODOS = frozenset({
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
    "septiembre", "setiembre", "octubre", "noviembre", "diciembre",
    "semana", "semanas", "mes", "meses", "trimestre", "trimestres", "semestre",
    "ano", "anos", "ayer", "anterior", "anteriores", "anoche", "antier",
    "anteayer", "hoy", "manana", "ahora", "ahorita", "actualmente", "pasado",
    "pasada", "proximo", "proxima", "ultimo", "ultima", "ultimos", "ultimas",
    "dia", "dias", "noche", "tarde", "fecha", "fechas", "periodo", "corte",
})

_PARTES_DEL_DIA = frozenset({"dia", "dias", "tarde", "tardes", "noche", "noches"})

# Inicio de seguimiento («y en el Santa Sofía?», «también un chiste»): flujo normal.
_SEGUIMIENTO = frozenset({"y", "e", "tambien", "ahora", "entonces", "pero", "o"})

_PROPIO = re.compile(
    r"\b(hospital (universitario )?de caldas|ses|huc|hospital universitario|"
    r"nuestro hospital|este hospital|nuestra institucion|esta institucion|"
    r"nuestra clinica|el hospital nuestro|aqui en el hospital)\b")

_LUGARES = (
    r"tailandia|china|japon|corea|india|rusia|ucrania|israel|gaza|palestina|iran|"
    r"irak|siria|afganistan|estados unidos|eeuu|usa|mexico|argentina|brasil|chile|"
    r"peru|ecuador|venezuela|cuba|espana|francia|alemania|italia|inglaterra|"
    r"reino unido|europa|asia|africa|canada|colombia|bogota|medellin|cali|"
    r"barranquilla|cartagena|pereira|armenia|el mundo|el pais|haiti|panama")
_COMIDAS = (
    r"arepas?|pan|panes|tortas?|pastel(es)?|pizzas?|pastas?|arroz|sancocho|ajiaco|"
    r"bandeja paisa|frijoles|lentejas|empanadas?|pollo|carne|pescado|ensaladas?|"
    r"sopas?|postres?|galletas?|brownies?|cafe|jugos?|limonada|bunuelos?|natilla|"
    r"tamal(es)?|lasagnas?|hamburguesas?|huevos?|chocolate|ponque|mazamorra|"
    r"changua|patacon(es)?|chicharron(es)?|almuerzo|cena|desayuno")
_CTX_CLINICO = (
    r"fiebre|dolor|duele|duelen|tos|gripa|gripe|resfriado|diarrea|vomito|vomitos|"
    r"mareo|nauseas|infeccion|neumonia|covid|dengue|hipertension|presion|diabetes|"
    r"asma|alergia|migrana|cabeza|estomago|garganta|pecho|muela|herida|quemadura|"
    r"fractura|mg|miligramos|ml|gotas|tabletas|pastilla|pastillas|capsulas|jarabe|"
    r"acetaminofen|paracetamol|ibuprofeno|amoxicilina|dolex|aspirina|naproxeno|"
    r"diclofenaco|omeprazol|loratadina|antibiotico|medicamento|medicina|remedio|"
    r"dosis|tratamiento|hijo|hija|bebe|nino|nina|mama|papa|abuelo|abuela|esposo|"
    r"esposa|paciente|embarazada|sintoma|sintomas|alcohol|azucar|colesterol")
_ENFERMEDAD = (
    r"fiebre|dolor|tos|gripa|gripe|resfriado|diarrea|infeccion|neumonia|diabetes|"
    r"hipertension|presion|asma|alergia|migrana|covid|dengue|herida|quemadura|"
    r"cancer|ansiedad|depresion|gastritis|colitis|anemia|artritis|otitis|"
    r"faringitis|amigdalitis|bronquitis|sinusitis|cistitis|varicela|sarampion|"
    r"hepatitis|tuberculosis|malaria|zika|chikungunya|acne|caspa|insomnio|"
    r"estres|obesidad|colesterol|acidez|estrenimiento|hemorroides|vih|sida")
_PERSONA = (
    r"nino|nina|bebe|adulto|adulta|paciente|hijo|hija|persona|senor|senora|"
    r"abuelo|abuela|anciano|anciana|embarazada|mujer|hombre|perro|gato|mama|papa")
_INSTITUCIONES = (
    r"santa sofia|avidanti|san marcel|clinica versalles|san vicente|valle del lili|"
    r"fundacion santa fe|cardioinfantil|shaio|san ignacio|pablo tobon|"
    r"clinica del country|clinica las americas|hospital militar|el tunal|"
    r"imbanaco|clinica marly|clinica reina sofia|assbasalud|"
    r"hospital infantil|clinica la presentacion|san juan de dios|"
    r"clinica de occidente|clinica medellin|clinica las vegas|"
    r"hospital general de medellin|clinica bolivariana|"
    r"(hospital|clinica) (san|santa|santo) [a-z]+|"
    r"(otros|otras|demas) (hospitales|clinicas|ips)|"
    r"otro hospital|otra clinica|otra ips")


@dataclass(frozen=True)
class _Categoria:
    subtipo: str
    patrones: tuple
    periodo: bool = False   # tolera periodos fuera del marcador
    numero: bool = False    # tolera números fuera del marcador
    tolera: frozenset = field(default_factory=frozenset)
    extras: tuple = ()      # tramos tolerados que no disparan solos (lugares)


def _c(*patrones):
    return tuple(re.compile(p) for p in patrones)


_EXTRA_LUGARES = _c(rf"\b({_LUGARES}|manizales|caldas)\b")

_CATEGORIAS = (
    _Categoria(
        "clinico",
        _c(
            rf"^(?=.*\b({_CTX_CLINICO})\b).*?\b(?P<m>(le|les|me|te) (doy|damos|doi|"
            rf"puedo dar|podemos dar|debo dar|debemos dar|aplico|puedo aplicar|receto|formulo|"
            rf"pongo|tomo|puedo tomar|debo tomar))\b",
            r"\b(me|nos) (duele|duelen|arde|pica)\b",
            rf"\btengo (fiebre|dolor|tos|gripa|gripe|diarrea|vomito|mareo|nauseas|covid|"
            rf"dengue|la presion (alta|baja)|presion (alta|baja)|la presion|una infeccion|"
            rf"infeccion|alergia|migrana|sintomas)\b",
            rf"\b(mi|el|la) ({_PERSONA}) (tiene|esta con|presenta|amanecio con) "
            rf"(la |una |un |mucha |mucho )?({_ENFERMEDAD})( (alta|baja))?\b",
            rf"^(?=.*\b({_CTX_CLINICO})\b).*?\b(?P<m>(puedo|debo|deberia|se puede|es bueno|"
            rf"es malo) (tomar|tomarme|darle|darme|mezclar|combinar|aplicar|aplicarme|inyectar))\b",
            r"\b(diagnosticame|diagnosticarme|que enfermedad tengo|sera que tengo)\b",
            rf"^(?=.*\b({_CTX_CLINICO})\b).*?\b(?P<m>es grave)\b",
            rf"\b(como|con que) (se )?(cura|curo|curar|trata|trato|tratar|quita|quito|"
            rf"quitar|alivia|alivio|aliviar|baja|bajo|bajar|controla|controlar|calma|"
            rf"calmo|calmar) (la |el |una |un |mi |esa |ese )?({_ENFERMEDAD})\b",
            rf"\bsintomas (de|del|de la) ({_ENFERMEDAD}|[a-z]+)\b",
            rf"^(?=.*\b(para|le|a) (un |una |mi |el |la )?({_PERSONA})\b).*?\b(?P<m>dosis|"
            rf"cuant[oa]s? (mg|miligramos|ml|gotas|tabletas|pastillas|capsulas))\b",
            r"\bdosis (maxima|recomendada|adecuada|correcta|letal)\b",
            r"\bcuant[oa]s (mg|miligramos|ml|gotas|tabletas|pastillas|capsulas) "
            r"(de [a-z]+ )?(puedo|debo|le|me)\b",
            rf"^(?=.*\b({_CTX_CLINICO})\b).*?\b(?P<m>(me|le) recomienda(s)? (algun|algo|un|"
            rf"una|tomar)|recomiendame (algo|un|una))\b",
            rf"\b(que|cual|mejor) (medicamento|medicina|remedio|pastilla|antibiotico|jarabe) "
            rf"(es bueno |es mejor |sirve |me sirve |le sirve |tomo |le doy )?para "
            rf"(la |el |una |un |mi )?({_ENFERMEDAD})\b",
        ),
        periodo=True, numero=True,
        tolera=frozenset({
            "dosis", "paciente", "medicamento", "medicina", "antibiotico",
            "tratamiento", "diagnostico", "medico", "medica", "horas", "hora",
            "cada", "edad", "peso", "clinico", "clinica", "kilos", "anos", "dia",
            "dias",
        }),
    ),
    _Categoria(
        "otra_institucion",
        _c(rf"\b({_INSTITUCIONES})\b"),
        periodo=True, numero=True,
    ),
    _Categoria(
        "calculo",
        _c(
            r"\braiz (cuadrada|cubica)\b",
            r"\braiz (de|del) (\d+|[a-z])\b",
            r"\b(logaritmos?|factorial|hipotenusa|pitagoras|trigonometria|algebra)\b",
            r"\bderivada (de|del)\b",
            r"\b(coseno|tangente) de\b",
            r"\b(resuelve|resolver|resuelveme|despeja|despejar)( la| esta| una| el)? "
            r"(ecuacion|ecuaciones|integral|derivada|operacion|x)\b",
            r"\becuacion(es)?\b",
            r"\b(numeros? primos?|al cuadrado|al cubo|elevado al? \w+)\b",
            r"\b(area|perimetro|volumen) de (un|una) (circulo|triangulo|cuadrado|"
            r"rectangulo|esfera|cubo|cilindro)\b",
            r"\btablas? de multiplicar\b",
            r"\b\d+ (por ciento|porciento) de \d+\b",
            r"\bcuanto (es|son|da|seria) (\d+|uno|dos|tres|cuatro|cinco|seis|siete|ocho|"
            r"nueve|diez|cien|mil) (mas|menos|por|entre|dividido (en|entre|por)|"
            r"multiplicado por|elevado a|sobre|x) (\d+|uno|dos|tres|cuatro|cinco|seis|"
            r"siete|ocho|nueve|diez|cien|mil)\b",
        ),
        numero=True,
        tolera=frozenset({"calcula", "calculame", "calcular", "resuelve", "numero",
                          "numeros", "radio", "base", "suma", "division"}),
    ),
    _Categoria(
        "programacion",
        _c(
            r"\b(python|javascript|typescript|java|php|kotlin|golang|ruby|css)\b",
            r"\b(un|el) (for|while|bucle|ciclo for|if) en\b",
            r"\bbucle (for|while)\b",
            r"\bhola mundo en\b",
            r"\b(programa|script|codigo|funcion|algoritmo) (en|para|que) "
            r"(python|java|javascript|c|php)\b",
            r"\bcomo (programo|programar|se programa)\b",
            r"\b(programame|codigo fuente)\b",
            r"\b(buscarv|buscarh|vlookup|macros? (de|en) excel)\b",
        ),
        tolera=frozenset({"boton", "botones", "numero", "numeros", "funcion", "codigo",
                          "archivo", "archivos", "base", "datos", "tabla", "tablas",
                          "lista", "listas", "texto", "pagina", "web", "formulario",
                          "usuario", "programa", "escribe", "sume", "suma", "excel"}),
    ),
    _Categoria(
        "redaccion",
        _c(
            r"\b(escribe|escribeme|escribir|escribirme|redacta|redactame|redactar|hazme|"
            r"haz|haga|hagame|elabora|elaborame|crea|creame|genera|generame|preparame|"
            r"ayudame a (escribir|redactar|hacer)|necesito que me (escribas|redactes|hagas)|"
            r"quiero que me (escribas|redactes|hagas)|me (escribes|redactas|haces|ayudas a "
            r"(escribir|redactar)))( un| una| el| la| mi)?( corto| breve| pequeno)? "
            r"(correo|email|e mail|mail|carta|oficio|memorando|memo|poema|poesia|cuento|"
            r"historia|ensayo|discurso|mensaje|whatsapp|tarea|cancion|hoja de vida|"
            r"curriculum|cv|felicitacion|invitacion|acta|comunicado|circular|post|"
            r"publicacion|trino|tweet|texto|parrafo|resumen de (este|esta|un|una|el|la) "
            r"(libro|texto|articulo|pelicula|documento))\b",
            r"\btraduc(e|eme|ir|ime|cion)\b",
            r"\bcomo se dice .+ en (ingles|frances|aleman|portugues|italiano|chino|japones)\b",
        ),
        tolera=frozenset({"corto", "corta", "breve", "formal", "texto", "mensaje"}),
    ),
    _Categoria(
        "noticias",
        _c(
            r"\bnoticias?\b",
            rf"\b(que|q) (paso|ha pasado|esta pasando|sucedio|ocurrio|hubo|se sabe)\b"
            rf"[a-z ]*\b(en|de|con) ({_LUGARES})\b",
            rf"\b(elecciones|guerra (en|de)|presidente de ({_LUGARES})|precio del dolar|"
            rf"dolar hoy|cuanto (esta|vale) el dolar|bitcoin|criptomonedas|bolsa de valores|"
            rf"terremoto|huracan|petro|trump|biden|putin|milei|bukele)\b",
        ),
        periodo=True,
        tolera=frozenset({"pais", "presidente"}),
        extras=_EXTRA_LUGARES,
    ),
    _Categoria(
        "clima",
        _c(
            r"\bclima\b(?! (laboral|organizacional))",
            r"\b(pronostico del tiempo|va a llover|va a hacer (sol|frio|calor)|esta lloviendo|"
            r"esta haciendo (frio|calor|sol)|llovera|cuantos grados hace|temperatura (hay|hace) en|"
            r"que tiempo (hara|va a hacer|hace hoy|hace en)|hace (mucho |demasiado )?(frio|calor))\b",
            rf"\b(como esta|como estara|como va a estar) el tiempo (en|para) ({_LUGARES}|manizales)\b",
        ),
        periodo=True,
        tolera=frozenset({"tiempo", "pronostico"}),
        extras=_EXTRA_LUGARES,
    ),
    _Categoria(
        "deportes",
        _c(
            r"\b(futbol|quien gano el partido|como quedo el partido|resultado del partido|"
            r"el partido( de)? (ayer|anoche|hoy)|partido (de|del) (futbol|hoy|ayer|anoche|"
            r"la seleccion|el once|colombia|nacional|millonarios)|once caldas|"
            r"seleccion colombia|atletico nacional|millonarios|america de cali|real madrid|"
            r"barcelona|messi|ronaldo|james rodriguez|luis diaz|el mundial|copa america|"
            r"champions|liga betplay|tour de francia|vuelta a espana|giro de italia|"
            r"formula 1|nba|tenis|ciclismo|goles|gol de|juega (el|la) (once|seleccion|nacional))\b",
        ),
        periodo=True,
        tolera=frozenset({"seleccion", "partido", "juega"}),
        extras=_EXTRA_LUGARES,
    ),
    _Categoria(
        "recetas",
        _c(
            r"\brecetas? (de|para)\b",
            rf"\bcomo (se )?(prepara|preparan|preparo|preparar|cocina|cocinan|cocino|cocinar|hace|"
            rf"hacen|hago|hacer) "
            rf"(un |una |el |la |los |las |unos |unas )?({_COMIDAS})\b",
            r"\bque (cocino|preparo|hago|como) (de|para) (almorzar|comer|cenar|desayunar|"
            r"el almuerzo|la cena|el desayuno|almuerzo|cena|desayuno|onces)\b",
        ),
        tolera=frozenset(re.findall(r"[a-z]+", "arepa arepas pan panes torta tortas pastel "
                                    "pasteles pizza pastas pasta arroz sancocho ajiaco pollo "
                                    "carne pescado ensalada sopa postre galletas chocolate "
                                    "hacer casero casera facil rapida rapido")),
    ),
    _Categoria(
        "entretenimiento",
        _c(
            r"\b(((cuentame|me cuentas|me cuenta|dime|echame|me echas|sabes) (un |una |otro |"
            r"algun |unos )?)?chistes?( (de|sobre) [a-z]+)?|cuentame algo (gracioso|chistoso)|hazme reir|"
            r"adivinanzas?|trabalenguas|juguemos|jugar (a|un|una)|cantame|cancion(es)?|"
            r"peliculas?|series? de (netflix|television|tv)|netflix|horoscopo|"
            r"signo zodiacal|zodiaco|me aburro|estoy aburrido)\b",
        ),
        periodo=True,
    ),
    _Categoria(
        "conocimiento",
        _c(
            r"\bcapital de\b(?! trabajo)",  # «capital de trabajo» es finanzas
            r"\bquien (invento|descubrio|escribio|pinto|compuso|fundo) (el|la|los|las|un|una)?\b",
            r"\bcuantos (planetas|continentes|oceanos|paises|huesos)\b",
            r"\bcuantos habitantes (tiene|hay en)\b",
            r"\bque hora es\b",
            r"\bque es (la|el) (fotosintesis|inflacion|democracia|filosofia|universo|amor|"
            r"vida|gravedad|adn|celula|atomo|internet|inteligencia artificial)\b",
            r"\b(sinonimo de|antonimo de|que significa la palabra|sistema solar)\b",
            r"\b(segunda guerra mundial|primera guerra mundial|independencia de colombia|"
            r"simon bolivar|historia de (colombia|la humanidad|roma|espana|francia))\b",
            rf"\bdonde (queda|esta ubicado|esta ubicada) ({_LUGARES})\b",
        ),
        extras=_EXTRA_LUGARES,
    ),
)

_ORDEN_SUBTIPOS = ("vago", "sin_sentido") + tuple(c.subtipo for c in _CATEGORIAS)
SUBTIPOS = frozenset(_ORDEN_SUBTIPOS)

# Plantillas vagas: el mensaje ENTERO (saludo y cortesía opcionales).
_PREFIJO_VAGO = (r"^(?:(?:hola|holi|buenas|buenos dias|buenas tardes|buenas noches|buen dia|"
                 r"hey|oye|disculpa|disculpe|perdon|bueno|pues|mira|amigo|parce|asistente) )*")
_SUFIJO_VAGO = r"(?: (?:por favor|gracias|pues|ya))*$"
_VAGOS = (
    r"(?:yo )?(?:necesito|quiero|quisiera|deseo|me gustaria) que me (?:respondas|responda|"
    r"contestes|conteste|ayudes|ayude|digas|diga|expliques|explique|resuelvas|resuelva|"
    r"colabores|colabore|aclares|aclare)(?: (?:algo|una cosa|una duda|una pregunta|"
    r"una inquietud|con algo|con una cosa|con una duda|con una pregunta|un favor|rapido))?",
    r"(?:yo )?(?:necesito|quiero|quisiera|deseo|me gustaria) (?:hacerte|hacerle|hacer|"
    r"preguntarte|preguntarle|preguntar|consultarte|consultarle|consultar|saber|pedirte|"
    r"pedirle)(?: (?:algo|una pregunta|una cosa|una consulta|una duda|una inquietud|un favor))?",
    r"(?:yo )?(?:necesito|quiero|quisiera) (?:algo|ayuda con algo|tu ayuda|su ayuda|una ayuda|"
    r"una ayudita|un favor|una respuesta|informacion|un dato|una informacion)",
    r"tengo (?:una|un par de|unas|otra) (?:pregunta|preguntas|duda|dudas|consulta|consultas|"
    r"inquietud|inquietudes|preguntica|pregunta rapida)",
    r"(?:te|le) (?:puedo|podria|quiero) (?:hacer|preguntar|consultar) (?:una pregunta|algo|"
    r"una cosa|una consulta|una duda)",
    r"(?:puedo|podria) (?:preguntarte|preguntarle|consultarte|hacerte|hacerle) (?:algo|"
    r"una pregunta|una cosa|una consulta)",
    r"(?:me|nos) (?:puedes|podrias|puede|podria) (?:ayudar|colaborar|responder|contestar|"
    r"resolver)(?: (?:con|a|en))? (?:algo|una cosa|una pregunta|una duda|una consulta)",
    # «ayúdame» a secas es capacidades (primera entrega); aquí solo con «algo».
    r"(?:respondeme|contestame)(?: (?:algo|una cosa))?",
    r"(?:ayudame|colaborame|respondeme|contestame) (?:algo|una cosa|con algo|con una cosa)",
    r"(?:hazme|haz|hagame|haga|genera|generame|elabora|elaborame|preparame|prepara|necesito|"
    r"quiero|dame) (?:un|una) (?:reporte|informe|consolidado) (?:de|del|sobre|con|acerca de)",
)
_VAGO = re.compile(_PREFIJO_VAGO + "(?:" + "|".join(_VAGOS) + ")" + _SUFIJO_VAGO)

# Otra institución: flujo entre instituciones (remisiones, traslados…) es dato propio.
_FLUJO = re.compile(
    r"\b(remisi\w*|remit\w*|referencia\w*|referid\w*|contrarreferencia\w*|"
    r"contrareferencia\w*|traslad\w*|envi\w*|mand\w*|recib\w*|lleg\w*|vien\w*|"
    r"proceden\w*|origen|destino|convenio\w*|contrato\w*|factur\w*|glosa\w*|cartera|"
    r"pag\w*|asegurador\w*|eps|entidad\w*|tercero\w*|prestador\w*|derivad\w*|"
    r"prepagad\w*|regimen|contributivo|subsidiado|poliza\w*|soat|arl|"
    r"acept\w*|nosotros|nuestr\w*|tenemos|hemos|atendimos|hicimos|remitimos|"
    r"enviamos|mandamos|recibimos)\b")
_DIRECCION = re.compile(
    rf"\b(al|hacia|desde|a la|a el|para el|para la|a)( (hospital|clinica|fundacion|ese|ips))? "
    rf"({_INSTITUCIONES})\b"
    rf"|\b(pacientes?|usuarios?|casos?|ingresos?|personas?|gente|atenciones|llegadas|"
    rf"remitidos|referidos|trasladados) (de|del|de la)( (hospital|clinica|fundacion))? "
    rf"({_INSTITUCIONES})\b")

_RISA = re.compile(r"^(?:(?:ja|je|ji|jo|ju|js|jsj)+j?|xd+|lol|lmao|ajaj\w*|jaj\w*)$")
_FILAS_TECLADO = ("qwertyuiop", "asdfghjkl", "zxcvbnm")


def _tokens(texto: str) -> list[str]:
    salida = []
    for t in normalizar(texto).split():
        t = _JERGA.get(t, t)
        if t not in _RELLENO:
            salida.append(t)
    return salida


@lru_cache(maxsize=4)
def _indice_dominio(vocabulario: frozenset) -> tuple[frozenset, frozenset, frozenset]:
    """(exactas, comodines de sustitución, palabras con una letra menos) del
    vocabulario de dominio sin genéricas (solo palabras de 5+ letras para tipeos)."""
    exactas = frozenset(vocabulario - GENERICAS)
    comodines, menos_una = set(), set()
    for w in exactas:
        if len(w) < 5:
            continue
        for i in range(len(w)):
            comodines.add(w[:i] + "*" + w[i + 1:])
            menos_una.add(w[:i] + w[i + 1:])
    return exactas, frozenset(comodines), frozenset(menos_una)


def es_dominio(token: str, vocabulario: frozenset) -> bool:
    """Palabra del catálogo, o a una letra (sustitución, inserción u omisión) de
    una palabra del catálogo de 5+ letras («cirujias», «ocupasion», «cirugas»)."""
    if token in GENERICAS:
        return False
    exactas, comodines, menos_una = _indice_dominio(vocabulario)
    if token in exactas:
        return True
    if len(token) < 5:
        return False
    if token in menos_una:  # al token le falta una letra
        return True
    for i in range(len(token)):
        if token[:i] + "*" + token[i + 1:] in comodines:
            return True
        if len(token) >= 6 and token[:i] + token[i + 1:] in exactas:  # le sobra una
            return True
    return False


def _cubiertos(texto: str, spans) -> set[int]:
    """Índices de las palabras de ``texto`` que caen dentro de algún tramo."""
    salida, pos = set(), 0
    for i, t in enumerate(texto.split(" ")):
        ini, fin = pos, pos + len(t)
        if any(a <= ini and fin <= b for a, b in spans):
            salida.add(i)
        pos = fin + 1
    return salida


def motivo_anulacion(tokens: list[str], cubiertos: set[int], vocabulario: frozenset,
                     categoria: _Categoria | None = None) -> str | None:
    """Por qué el mensaje NO puede ser fuera de alcance (o None si puede)."""
    if tokens and tokens[0] in _SEGUIMIENTO:
        return "seguimiento"
    texto = " ".join(tokens)
    if _PROPIO.search(texto):
        return "propio hospital"
    periodo = categoria.periodo if categoria else False
    numero = categoria.numero if categoria else False
    tolera = categoria.tolera if categoria else frozenset()
    for i, t in enumerate(tokens):
        if i in cubiertos:
            continue
        if any(c.isdigit() for c in t):
            if not numero:
                return "numero"
            continue
        if t in _PERIODOS:
            if t in _PARTES_DEL_DIA and i and tokens[i - 1] in ("buenos", "buenas", "buen"):
                continue  # «buenos días» es saludo, no periodo
            if not periodo:
                return "periodo"
            continue
        if t in tolera:
            continue
        if categoria is not None and categoria.subtipo == "otra_institucion":
            continue  # se anula por flujo/dirección (abajo), no por dominio
        if es_dominio(t, vocabulario):
            return f"dominio «{t}»"
    if categoria is not None and categoria.subtipo == "otra_institucion":
        if _FLUJO.search(texto) or _DIRECCION.search(texto):
            return "flujo entre instituciones"
    if categoria is not None and categoria.subtipo == "clinico":
        # «¿cuántos pacientes con…?»: pregunta estadística, no consejo.
        if re.search(r"\bcuant[oa]s (?!mg|miligramos|ml|gotas|tabletas|pastillas|capsulas|"
                     r"veces)\w+", texto) or "pacientes" in tokens:
            return "pregunta estadistica"
    return None


def _es_tecleo(t: str, vocabulario: frozenset) -> bool:
    if t in vocabulario or not t.isalpha():  # «2024» es un año, no tecleo
        return False
    if len(t) >= 4 and not re.search(r"[aeiouy]", t):
        return True
    for fila in _FILAS_TECLADO:
        for i in range(len(fila) - 3):
            if fila[i:i + 4] in t or fila[i:i + 4][::-1] in t:
                return True
    m = re.fullmatch(r"([a-z]{2,4})\1{2,}[a-z]{0,3}", t)
    return bool(m)


@dataclass(frozen=True)
class Deteccion:
    subtipo: str
    motivo: str    # "regla" o "similitud"
    detalle: str   # marcador o similitud que la justifica


def _sin_sentido(original: str, tokens: list[str], vocabulario: frozenset) -> str | None:
    if not tokens:
        return "mensaje vacío o solo signos"
    if all(_RISA.match(t) or _es_tecleo(t, vocabulario) for t in tokens):
        return "risa o tecleo sin palabras"
    return None


def detectar(original: str, vocabulario: frozenset = frozenset(),
             similitud=None) -> Deteccion | None:
    """Detección fuera de alcance, o None (flujo normal). Nunca lanza."""
    try:
        return _detectar(original, vocabulario, similitud)
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "portero de alcance desactivado en este mensaje (%s)", type(exc).__name__)
        return None


def _detectar(original, vocabulario, similitud):
    if len(original or "") > MAX_CARACTERES:
        return None
    tokens = _tokens(original)
    texto = " ".join(tokens)
    if _VAGO.match(texto):
        return Deteccion("vago", "regla", "petición sin tema")
    vacio = _sin_sentido(original, tokens, vocabulario)
    if vacio:
        return Deteccion("sin_sentido", "regla", vacio)
    crudo = normalizar_operaciones(original)
    # Sin «cuánto es» solo + * x ^: «10/2025» o «2024-2025» son periodos.
    if re.fullmatch(r"\d+(\.\d+)?( ?[+*x^] ?\d+(\.\d+)?)+( ?=)?", crudo) \
            or re.fullmatch(r"cuanto (es|son|da) \d+(\.\d+)?( ?[-+*/x^] ?\d+(\.\d+)?)+( ?=)?", crudo):
        return Deteccion("calculo", "regla", "operación aritmética")
    if re.search(r"\d*x ?[-+*/] ?\d+ ?= ?-?\d+", crudo) and not re.search(r"[a-wyz]{4,}", re.sub(
            r"\b(resuelve|resuelveme|resolver|despeja|ecuacion|esta|la|oye|porfa|por favor|ayudame|a)\b",
            "", crudo)):
        return Deteccion("calculo", "regla", "ecuación")
    for cat in _CATEGORIAS:
        spans = [m.span("m") if "m" in p.groupindex else m.span()
                 for p in cat.patrones for m in p.finditer(texto)]
        if not spans:
            continue
        tolerados = spans + [m.span() for p in cat.extras for m in p.finditer(texto)]
        anulado = motivo_anulacion(tokens, _cubiertos(texto, tolerados), vocabulario, cat)
        if anulado:
            return None  # marcador presente pero con señal de dominio: flujo normal
        a, b = spans[0]
        return Deteccion(cat.subtipo, "regla", f"marcador «{texto[a:b]}»")
    return _por_similitud(tokens, vocabulario, similitud)


def normalizar_operaciones(texto: str) -> str:
    """Minúsculas sin tildes conservando operadores aritméticos (+ - * / x ^ =)."""
    base = unicodedata.normalize("NFKD", str(texto or "").lower())
    base = "".join(c for c in base if not unicodedata.combining(c))
    base = base.replace("×", "*").replace("÷", "/").replace(",", ".")
    base = re.sub(r"[^a-z0-9+\-*/^=.]+", " ", base)
    base = re.sub(r"\s*([+\-*/^=])\s*", r" \1 ", base)
    return " ".join(base.split()).strip(" .")


def _por_similitud(tokens, vocabulario, similitud):
    """Última barrera: mensaje «limpio» (sin catálogo, periodo, número ni
    hospital) de 3 a 12 palabras, sobre umbral y con margen."""
    if similitud is None or not (MIN_PALABRAS_SIMILITUD <= len(tokens) <= MAX_PALABRAS_SIMILITUD):
        return None
    if motivo_anulacion(tokens, set(), vocabulario, None):
        return None
    mejor = getattr(similitud, "mejor_alcance", None)
    if not callable(mejor):
        return None
    try:
        r = mejor(" ".join(tokens))
    except Exception as exc:
        logging.getLogger(__name__).warning("similitud de alcance fallo: %s", type(exc).__name__)
        return None
    if r is None:
        return None
    subtipo, sim, sim_dominio, sim_charla = r
    umbral = getattr(similitud, "umbral_alcance", UMBRAL)
    margen = getattr(similitud, "margen_alcance", MARGEN)
    if sim < umbral or sim - sim_dominio < margen or sim <= sim_charla:
        return None
    return Deteccion(subtipo, "similitud",
                     f"similitud {sim:.2f} (margen {sim - sim_dominio:.2f} frente a preguntas de dominio)")


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
    "general": f"Eso está fuera de lo que puedo responder. {_PUEDO}",
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
