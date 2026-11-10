"""Datos del portero de alcance (spec 002): jerga, palabras genéricas, periodos,
lugares, instituciones, categorías con sus marcadores y tolerancias, plantillas
vagas y señales de flujo entre instituciones. Solo datos y expresiones
regulares: la lógica vive en ``portero_alcance``."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Jerga de chat y tipeos frecuentes de las palabras de los marcadores.
JERGA = {
    "q": "que", "k": "que", "ke": "que", "qe": "que", "d": "de", "pa": "para",
    "xq": "porque", "pq": "porque", "tb": "tambien", "tmb": "tambien",
    "nesecito": "necesito", "nesesito": "necesito", "necsito": "necesito",
    "nececito": "necesito", "nesito": "necesito", "necesitp": "necesito",
    "kiero": "quiero", "qiero": "quiero", "cuentam": "cuentame",
}
RELLENO = frozenset({"porfa", "porfavor", "plis", "pls", "xfa", "please", "porfis"})

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
    # Palabras de pregunta y verbos comunes: con el catálogo real algunas caen a
    # una letra de una columna («cuanto» ~ «cuarto»). No son señal de dominio.
    "que", "cual", "cuales", "cuanto", "cuanta", "cuantos", "cuantas", "como",
    "cuando", "donde", "quien", "quienes", "porque", "para", "con", "por", "mas",
    "menos", "mejor", "peor", "muy", "algo", "nada", "todo", "puedo", "puede",
    "pueda", "quiero", "tengo", "tiene", "hacer", "hago", "dar", "dame", "dime",
    "esta", "estan", "fue", "era", "ser", "hay", "saber", "gente", "persona",
    "personas", "ciudad",
})

PERIODOS = frozenset({
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
    "septiembre", "setiembre", "octubre", "noviembre", "diciembre",
    "semana", "semanas", "mes", "meses", "trimestre", "trimestres", "semestre",
    "ano", "anos", "ayer", "anterior", "anteriores", "anoche", "antier",
    "anteayer", "hoy", "manana", "ahora", "ahorita", "actualmente", "pasado",
    "pasada", "proximo", "proxima", "ultimo", "ultima", "ultimos", "ultimas",
    "dia", "dias", "noche", "tarde", "fecha", "fechas", "periodo", "corte",
})

PARTES_DEL_DIA = frozenset({"dia", "dias", "tarde", "tardes", "noche", "noches"})

# Inicio de seguimiento («y en el Santa Sofía?», «también un chiste»): flujo normal.
SEGUIMIENTO = frozenset({"y", "e", "tambien", "ahora", "entonces", "pero", "o"})

PROPIO = re.compile(
    r"\b(hospital (universitario )?de caldas|ses|huc|hospital universitario|"
    r"nuestro hospital|este hospital|nuestra institucion|esta institucion|"
    r"nuestra clinica|el hospital nuestro|aqui en el hospital)\b")

LUGARES = (
    r"tailandia|china|japon|corea|india|rusia|ucrania|israel|gaza|palestina|iran|"
    r"irak|siria|afganistan|estados unidos|eeuu|usa|mexico|argentina|brasil|chile|"
    r"peru|ecuador|venezuela|cuba|espana|francia|alemania|italia|inglaterra|"
    r"reino unido|europa|asia|africa|canada|colombia|bogota|medellin|cali|"
    r"barranquilla|cartagena|pereira|armenia|el mundo|el pais|haiti|panama")
COMIDAS = (
    r"arepas?|pan|panes|tortas?|pastel(es)?|pizzas?|pastas?|arroz|sancocho|ajiaco|"
    r"bandeja paisa|frijoles|lentejas|empanadas?|pollo|carne|pescado|ensaladas?|"
    r"sopas?|postres?|galletas?|brownies?|cafe|jugos?|limonada|bunuelos?|natilla|"
    r"tamal(es)?|lasagnas?|hamburguesas?|huevos?|chocolate|ponque|mazamorra|"
    r"changua|patacon(es)?|chicharron(es)?|almuerzo|cena|desayuno")
CTX_CLINICO = (
    r"fiebre|dolor|duele|duelen|tos|gripa|gripe|resfriado|diarrea|vomito|vomitos|"
    r"mareo|nauseas|infeccion|neumonia|covid|dengue|hipertension|presion|diabetes|"
    r"asma|alergia|migrana|cabeza|estomago|garganta|pecho|muela|herida|quemadura|"
    r"fractura|mg|miligramos|ml|gotas|tabletas|pastilla|pastillas|capsulas|jarabe|"
    r"acetaminofen|paracetamol|ibuprofeno|amoxicilina|dolex|aspirina|naproxeno|"
    r"diclofenaco|omeprazol|loratadina|antibiotico|medicamento|medicina|remedio|"
    r"dosis|tratamiento|hijo|hija|bebe|nino|nina|mama|papa|abuelo|abuela|esposo|"
    r"esposa|paciente|embarazada|sintoma|sintomas|alcohol|azucar|colesterol")
ENFERMEDAD = (
    r"fiebre|dolor|tos|gripa|gripe|resfriado|diarrea|infeccion|neumonia|diabetes|"
    r"hipertension|presion|asma|alergia|migrana|covid|dengue|herida|quemadura|"
    r"cancer|ansiedad|depresion|gastritis|colitis|anemia|artritis|otitis|"
    r"faringitis|amigdalitis|bronquitis|sinusitis|cistitis|varicela|sarampion|"
    r"hepatitis|tuberculosis|malaria|zika|chikungunya|acne|caspa|insomnio|"
    r"estres|obesidad|colesterol|acidez|estrenimiento|hemorroides|vih|sida")
PERSONA = (
    r"nino|nina|bebe|adulto|adulta|paciente|hijo|hija|persona|senor|senora|"
    r"abuelo|abuela|anciano|anciana|embarazada|mujer|hombre|perro|gato|mama|papa")
INSTITUCIONES = (
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
class Categoria:
    subtipo: str
    patrones: tuple
    periodo: bool = False   # tolera periodos fuera del marcador
    numero: bool = False    # tolera números fuera del marcador
    tolera: frozenset = field(default_factory=frozenset)
    extras: tuple = ()      # tramos tolerados que no disparan solos (lugares)
    por_dominio: bool = True  # una palabra del catálogo fuera del marcador la anula


def _c(*patrones):
    return tuple(re.compile(p) for p in patrones)


def _palabras(*alternativas: str) -> frozenset:
    """Palabras sueltas de alternativas regex («fiebre|dolor|tos»): el campo
    semántico de una categoría, que el catálogo real también puede contener
    («dolor», «adulto») sin que el mensaje deje de ser, p. ej., consejo clínico."""
    return frozenset(w for a in alternativas for w in re.findall(r"[a-z]+", a))


_IDIOMAS = "ingles|frances|aleman|portugues|italiano|chino|japones"

EXTRA_LUGARES = _c(rf"\b({LUGARES}|manizales|caldas)\b")

CATEGORIAS = (
    Categoria(
        "clinico",
        _c(
            rf"^(?=.*\b({CTX_CLINICO})\b).*?\b(?P<m>(le|les|me|te) (doy|damos|doi|"
            rf"puedo dar|podemos dar|debo dar|debemos dar|aplico|puedo aplicar|receto|formulo|"
            rf"pongo|tomo|puedo tomar|debo tomar))\b",
            r"\b(me|nos) (duele|duelen|arde|pica)\b",
            rf"\btengo (fiebre|dolor|tos|gripa|gripe|diarrea|vomito|mareo|nauseas|covid|"
            rf"dengue|la presion (alta|baja)|presion (alta|baja)|la presion|una infeccion|"
            rf"infeccion|alergia|migrana|sintomas)\b",
            rf"\b(mi|el|la) ({PERSONA}) (tiene|esta con|presenta|amanecio con) "
            rf"(la |una |un |mucha |mucho )?({ENFERMEDAD})( (alta|baja))?\b",
            rf"^(?=.*\b({CTX_CLINICO})\b).*?\b(?P<m>(puedo|debo|deberia|se puede|es bueno|"
            rf"es malo) (tomar|tomarme|darle|darme|mezclar|combinar|aplicar|aplicarme|inyectar))\b",
            r"\b(diagnosticame|diagnosticarme|que enfermedad tengo|sera que tengo)\b",
            rf"^(?=.*\b({CTX_CLINICO})\b).*?\b(?P<m>es grave)\b",
            rf"\b(como|con que) (se )?(cura|curo|curar|trata|trato|tratar|quita|quito|"
            rf"quitar|alivia|alivio|aliviar|baja|bajo|bajar|controla|controlar|calma|"
            rf"calmo|calmar) (la |el |una |un |mi |esa |ese )?({ENFERMEDAD})\b",
            rf"\bsintomas (de|del|de la) ({ENFERMEDAD}|[a-z]+)\b",
            rf"^(?=.*\b(para|le|a) (un |una |mi |el |la )?({PERSONA})\b).*?\b(?P<m>dosis|"
            rf"cuant[oa]s? (mg|miligramos|ml|gotas|tabletas|pastillas|capsulas))\b",
            r"\bdosis (maxima|recomendada|adecuada|correcta|letal)\b",
            r"\bcuant[oa]s (mg|miligramos|ml|gotas|tabletas|pastillas|capsulas) "
            r"(de [a-z]+ )?(puedo|debo|le|me)\b",
            rf"^(?=.*\b({CTX_CLINICO})\b).*?\b(?P<m>(me|le) recomienda(s)? (algun|algo|un|"
            rf"una|tomar)|recomiendame (algo|un|una))\b",
            rf"\b(que|cual|mejor) (medicamento|medicina|remedio|pastilla|antibiotico|jarabe) "
            rf"(es bueno |es mejor |sirve |me sirve |le sirve |tomo |le doy )?para "
            rf"(la |el |una |un |mi )?({ENFERMEDAD})\b",
        ),
        periodo=True, numero=True,
        tolera=frozenset({
            "dosis", "paciente", "medicamento", "medicina", "antibiotico",
            "tratamiento", "diagnostico", "medico", "medica", "horas", "hora",
            "cada", "edad", "peso", "clinico", "clinica", "kilos", "anos", "dia",
            "dias",
        }) | _palabras(CTX_CLINICO, ENFERMEDAD, PERSONA),
    ),
    Categoria(
        "otra_institucion",
        _c(rf"\b({INSTITUCIONES})\b"),
        periodo=True, numero=True,
        por_dominio=False,  # se anula por flujo entre instituciones (FLUJO, DIRECCION)
    ),
    Categoria(
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
    Categoria(
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
    Categoria(
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
            rf"\btraduc(e|eme|ir|ime|cion)( (esto|este texto|esta frase))?( (al|en|a) ({_IDIOMAS}))?\b",
            rf"\bcomo se dice .+ en ({_IDIOMAS})\b",
        ),
        tolera=frozenset({"corto", "corta", "breve", "formal", "texto", "mensaje", "correo",
                          "carta"}) | _palabras(_IDIOMAS),
    ),
    Categoria(
        "noticias",
        _c(
            r"\bnoticias?\b",
            rf"\b(que|q) (paso|ha pasado|esta pasando|sucedio|ocurrio|hubo|se sabe)\b"
            rf"[a-z ]*\b(en|de|con) ({LUGARES})\b",
            rf"\b(elecciones|guerra (en|de)|presidente de ({LUGARES})|precio del dolar|"
            rf"dolar hoy|cuanto (esta|vale) el dolar|bitcoin|criptomonedas|bolsa de valores|"
            rf"terremoto|huracan|petro|trump|biden|putin|milei|bukele)\b",
            # Economía general (no del hospital): «PIB de Colombia en 2024»,
            # «¿cuánto gana un médico general en Colombia?».
            r"\b(pib|producto interno bruto|tasa de desempleo|salario minimo|inflacion)\b",
            rf"\bcuanto (gana|ganan|cobra|cobran) (un|una|los|las) [a-z]+( [a-z]+)? en ({LUGARES})\b",
        ),
        periodo=True, numero=True,
        tolera=frozenset({"pais", "presidente"}),
        extras=EXTRA_LUGARES,
    ),
    Categoria(
        "clima",
        _c(
            r"\bclima\b(?! (laboral|organizacional))",
            r"\b(pronostico del tiempo|va a llover|va a hacer (sol|frio|calor)|esta lloviendo|"
            r"esta haciendo (frio|calor|sol)|llovera|cuantos grados hace|temperatura (hay|hace) en|"
            r"que tiempo (hara|va a hacer|hace hoy|hace en)|hace (mucho |demasiado )?(frio|calor))\b",
            rf"\b(como esta|como estara|como va a estar) el tiempo (en|para) ({LUGARES}|manizales)\b",
        ),
        periodo=True,
        tolera=frozenset({"tiempo", "pronostico"}),
        extras=EXTRA_LUGARES,
    ),
    Categoria(
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
        extras=EXTRA_LUGARES,
    ),
    Categoria(
        "recetas",
        _c(
            r"\brecetas? (de|para)\b",
            rf"\bcomo (se )?(prepara|preparan|preparo|preparar|cocina|cocinan|cocino|cocinar|hace|"
            rf"hacen|hago|hacer) "
            rf"(un |una |el |la |los |las |unos |unas )?({COMIDAS})\b",
            r"\bque (cocino|preparo|hago|como) (de|para) (almorzar|comer|cenar|desayunar|"
            r"el almuerzo|la cena|el desayuno|almuerzo|cena|desayuno|onces)\b",
        ),
        tolera=frozenset(re.findall(r"[a-z]+", "arepa arepas pan panes torta tortas pastel "
                                    "pasteles pizza pastas pasta arroz sancocho ajiaco pollo "
                                    "carne pescado ensalada sopa postre galletas chocolate "
                                    "hacer casero casera facil rapida rapido")),
    ),
    Categoria(
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
    Categoria(
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
            rf"\bdonde (queda|esta ubicado|esta ubicada) ({LUGARES})\b",
        ),
        extras=EXTRA_LUGARES,
    ),
)


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
VAGO = re.compile(_PREFIJO_VAGO + "(?:" + "|".join(_VAGOS) + ")" + _SUFIJO_VAGO)

# Otra institución: flujo entre instituciones (remisiones, traslados…) es dato propio.
FLUJO = re.compile(
    r"\b(remisi\w*|remit\w*|referencia\w*|referid\w*|contrarreferencia\w*|"
    r"contrareferencia\w*|traslad\w*|envi\w*|mand\w*|recib\w*|lleg\w*|vien\w*|"
    r"proceden\w*|origen|destino|convenio\w*|contrato\w*|factur\w*|glosa\w*|cartera|"
    r"pag\w*|asegurador\w*|eps|entidad\w*|tercero\w*|prestador\w*|derivad\w*|"
    r"prepagad\w*|regimen|contributivo|subsidiado|poliza\w*|soat|arl|"
    r"acept\w*|nosotros|nuestr\w*|tenemos|hemos|atendimos|hicimos|remitimos|"
    r"enviamos|mandamos|recibimos)\b")
DIRECCION = re.compile(
    rf"\b(al|hacia|desde|a la|a el|para el|para la|a)( (hospital|clinica|fundacion|ese|ips))? "
    rf"({INSTITUCIONES})\b"
    rf"|\b(pacientes?|usuarios?|casos?|ingresos?|personas?|gente|atenciones|llegadas|"
    rf"remitidos|referidos|trasladados) (de|del|de la)( (hospital|clinica|fundacion))? "
    rf"({INSTITUCIONES})\b")

RISA = re.compile(r"^(?:(?:ja|je|ji|jo|ju|js|jsj)+j?|xd+|lol|lmao|ajaj\w*|jaj\w*)$")
FILAS_TECLADO = ("qwertyuiop", "asdfghjkl", "zxcvbnm")
