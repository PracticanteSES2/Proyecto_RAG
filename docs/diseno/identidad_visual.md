# Identidad visual pública del S.E.S. Hospital Universitario de Caldas

Investigación hecha el 2026-11-10 solo con fuentes públicas. Sirve de base para el frontend Next.js del asistente
de tableros. Los tokens que salen de aquí están en [`tokens.md`](tokens.md) y [`tokens.css`](tokens.css).

**Escala de certeza:** **Alta** = medido en un archivo oficial (CSS o imagen del sitio, PDF institucional).
**Media** = deducido de piezas oficiales, pero sin un manual que lo confirme. **Baja** = estimación o inferencia.

> No se encontró un **manual de marca público**. La búsqueda en el sitio (`/wp-json/wp/v2/search` y `/media` con
> "manual de marca", "identidad") no devolvió nada. Todo lo de abajo sale de piezas publicadas. La oficina de
> comunicaciones del hospital debería confirmar los valores antes de cualquier uso externo.

## 1. Fuentes consultadas

| Fuente | URL | Qué aportó |
|---|---|---|
| Sitio oficial (WordPress + Elementor, tema Leblix) | https://seshospitaluniversitariodecaldas.com/ | CSS, logos, colores, radios, tono |
| CSS de Elementor de la portada, el encabezado y el pie | `…/wp-content/uploads/elementor/css/post-7779.css`, `post-3383.css`, `post-5628.css`, `post-7.css` | Colores y tipografías en uso |
| Logo horizontal nuevo (dic. 2025) | `…/wp-content/uploads/2025/12/logo-ses-nuevo.png` | Logo vigente |
| Isotipo "sonrisas" (ago. 2026) | `…/wp-content/uploads/2026/08/LOGO-SES-HUC-SONRISAS.png` | Paleta exacta del isotipo |
| Patrón de fondo con el isotipo | `…/wp-content/uploads/2026/09/fondo-logo-pattern.jpg` | Uso decorativo del isotipo |
| Historia de los logos | `…/wp-content/uploads/2023/04/historia-logos-ses-hospital-de-caldas.jpg` | Evolución de la marca |
| Banner con el barranquero (sep. 2026) | `…/wp-content/uploads/2026/09/ave-banner-azul.png` | Símbolo del ave |
| Página "Monumento al Buen Acto" | https://seshospitaluniversitariodecaldas.com/monumento-al-buen-acto/ | Historia del barranquero |
| Informe de gestión y sostenibilidad 2025 (PDF y portada) | `…/wp-content/uploads/2026/04/INFORME-DE-GESTION-2025-baja.pdf` y `INFORME-DE-GESTION-2025.png` | Tipografías de las piezas impresas, fotografía, lema |
| Plataforma estratégica / Nuestra historia | `/plataforma-estrategica/`, `/nuestra-historia/` | Misión, tono, historia |
| Redes enlazadas desde el sitio | Facebook `seshospitaldecaldas`, Instagram `ses_huc`, X `ses_huc`, YouTube `@seshospitaldecaldas`, LinkedIn | Facebook e Instagram no se pudieron leer sin sesión (conexión rechazada o reiniciada) |
| X `@SES_HUC` (según el buscador) | https://x.com/ses_huc | Etiqueta `#QueremosDevolverSonrisas` |
| *Archivos de Medicina* (U. de Caldas), 2024;24(2) | https://revistasum.umanizales.edu.co/index.php/archivosmedicina/article/download/5206/7882/33276 | Inauguración del Monumento al Buen Acto, obra de Luis Guillermo Vallejo Vargas |

**Ojo:** `ses.com.co` (el dominio del correo institucional) hoy es solo una página de GoDaddy que dice "Próximo
lanzamiento". La web real es `seshospitaluniversitariodecaldas.com`, y `hospitaldecaldas.com` redirige allí.

## 2. Logo

- **Versión vigente (certeza alta):** a la izquierda, el isotipo de cuatro "sonrisas". En el centro, "S.E.S." en
  letras redondeadas y gruesas, con los puntos en azul cielo. A la derecha, "Hospital / Universitario / de Caldas" en
  tres líneas. Debajo va el lema manuscrito *"Queremos devolver sonrisas"*. Archivo: `logo-ses-nuevo.png` (dic.
  2025, 1034×226).
- **Evolución (certeza alta, según la imagen de historia):** primero "S.E.S. servicios especiales de salud", con una
  línea de electrocardiograma. Luego "S.E.S. Hospital de Caldas", con la misma línea. Hoy, el isotipo de sonrisas
  con "Hospital Universitario de Caldas", así que es posterior a la certificación como universitario de 2019 (la
  fecha exacta del cambio no está publicada: certeza media).
- **Isotipo (certeza alta):** cuatro cuadrantes en azul, morado, coral y verde. En cada uno, un arco grueso hace de
  boca, los extremos van en tono fuerte y dos puntos claros hacen de ojos. Juntos forman cuatro caras sonrientes que
  miran hacia afuera. El hospital usa el isotipo suelto como patrón decorativo de fondo, con tintes al 10-15 %.
- **Versiones publicadas:** a color sobre blanco, en blanco sobre fondo de color (`logo-ses-blanco-con-sombra.png`,
  portada del informe 2025), y el isotipo solo (`LOGO-SES-HUC-SONRISAS.png`).
- **Vector oficial:** **no hay ninguno público** (no se encontró SVG, EPS ni AI). Por eso se hizo una
  **recreación vectorial** del isotipo con la geometría medida sobre el PNG oficial. Se comparó la imagen generada con
  el original y coinciden. Archivos:
  - `assets/marca/isotipo_ses.svg`: a color, fiel al oficial.
  - `assets/marca/isotipo_ses_monocromo.svg`: una sola tinta, `currentColor`.
  - `assets/marca/oficial/isotipo_ses_oficial.png` y `logo_ses_horizontal_oficial.png`: los PNG oficiales,
    recodificados con Pillow para quitarles los metadatos.
  - **Comunicaciones debe validar la recreación.** Si el hospital entrega el vector oficial, se reemplaza.
- `assets/logo_ses.png` (el que usa la app hoy) es la misma marca, pero salió de un JPG. Conviene reemplazarlo por
  `oficial/logo_ses_horizontal_oficial.png`, que tiene colores planos.

## 3. Paleta

### 3.1 Colores del isotipo y el logotipo (certeza alta: píxeles planos del PNG oficial)

| Familia | Arco (base) | Extremos (fuerte) | Ojos (claro) |
|---|---|---|---|
| Azul | `#3C8FCD` | `#0A70B3` | `#7CC3ED` |
| Morado | `#8D77B1` | `#6D509B` | `#AE92C4` |
| Coral | `#F08480` | `#E56558` | `#F4B8B3` |
| Verde | `#8BC160` | `#44AB43` | `#AED289` |

En el logotipo, "S.E.S." mide `#3A96D3`, sus puntos `#7DCCF3` y "Hospital Universitario de Caldas" `#096CB5`.

### 3.2 Colores del sitio web (certeza alta: conteo en el CSS)

| Color | Usos en el CSS | Rol observado |
|---|---|---|
| `#3894D1` | 40 o más | Azul de marca: botones, títulos, iconos |
| `#024573` | 27 | Azul profundo: barra de encabezado, menús |
| `#FFFFFF` | muchos | Fondo |
| `#7DCBF2` | 9 | Azul cielo: acentos, separadores |
| `#096CB4` / `#0367B3` | 10 | Azul medio: hover, enlaces del pie |
| `#89C060` | 1 | Verde |
| `#37368E` | 3 | Índigo, puntual en el menú |

El kit global de Elementor (`post-7.css`) conserva los valores por defecto (`#6EC1E4`, `#54595F`…), así que **no**
representa la marca.

### 3.3 Cómo se usan (certeza media)

- El **azul** manda: tipografía del logo, botones y barras. El **azul profundo** va en los fondos de navegación. El
  **blanco** es el fondo general.
- Los **cuatro colores** del isotipo aparecen juntos como símbolo de diversidad y calidez. En la portada del informe
  2025 se ven en bandas horizontales (verde, coral, verde azulado, azul) bajo una foto.
- El **morado** casi no se usa fuera del isotipo. El diseño anterior (`2026-11-04-tema-hucaldas-design.md`) lo
  descartaba, pero es parte del isotipo oficial y aquí se recupera como acento (modo diagnóstico).

### 3.4 Hallazgo de accesibilidad sobre la paleta actual de la app

El `AZUL_PRIMARIO #2B7FB0` de `src/ui/estilo.py` da **4.41:1** con texto blanco: **no cumple AA** para texto normal
(el mínimo es 4.5). El azul de marca `#3A96D3` da 3.24:1, así que tampoco sirve para fondos de botón. Se propone
`#096CB5`, el azul medio oficial del logotipo, que da **5.49:1**. Detalle en `tokens.md`.

## 4. Tipografía

| Uso | Familia | Dónde se vio | Certeza | Licencia / equivalente |
|---|---|---|---|---|
| Texto del sitio web | **Arlon** (Marc Lohner, 2018), autoalojada como `wp-content/uploads/2026/07/arlon-regular.ttf` | CSS: 48 o más usos de `"Arlon-regular"` | Alta | **De pago** (MyFonts y Fontspring; la demo gratuita es solo para uso personal). Equivalente libre: **Montserrat** o **Mulish** |
| Piezas institucionales (informe 2025) | **Montserrat** (Light a Black, más Alternates) | Fuentes embebidas en el PDF | Alta | Google Fonts, OFL |
| Texto secundario del informe | **Muli** (hoy **Mulish**), Poppins, Bebas Neue, Open Sans | Fuentes embebidas en el PDF | Alta | Google Fonts, OFL |
| Encabezado y menú del sitio | Varela Round, Roboto, Roboto Slab (este último por defecto de Elementor) | CSS | Alta (uso) / baja (que sea intencional) | Google Fonts |
| "Hospital Universitario de Caldas" en el logo | Sans geométrica redondeada (parecida a Varela Round o Nunito) | Inspección visual | Baja | Es parte del logo: no se compone con fuentes |
| Lema "Queremos devolver sonrisas" | Manuscrita monolineal | Inspección visual | Baja (sin identificar) | No recomponer: usar la imagen del logo |

**Propuesta para la app:** títulos en **Montserrat** 600/700 (la familia del informe oficial) y cuerpo en **Mulish**
400/600 (la "Muli" del mismo informe, más legible en texto largo que Montserrat). Arlon solo si Comunicaciones
confirma que tiene licencia web y la entrega.

## 5. Forma, espacio, iconos y fotografía

- **Radios (certeza alta, CSS):** tarjetas y cajas con `18px`, botones con `33px` (forma de píldora), círculos al
  `50%`, detalles pequeños con `3–7px`. La estética es redondeada y amable, en línea con las formas del isotipo.
- **Espaciado (certeza alta, CSS):** espacio de 20px entre bloques (Elementor), relleno de secciones de 24, 48 y
  56px, contenedor de 1140px.
- **Sombras:** pocas. En el tema hay `rgba(0,0,0,.10)` y la burbuja flotante de contacto usa
  `0 3px 18px rgba(0,0,0,.25)`. Predomina lo plano.
- **Iconografía (certeza media):** iconos de línea gruesa redondeada en azul (corazón con pulso, persona y otros en
  `portal-pacientes@2x.png`, `agenda-tu-cita@2x.png`), con degradado suave de azul cielo a blanco. Font Awesome 5 en
  el sitio. Para la app: un set de línea redondeada (Lucide, trazo de 2px) es coherente.
- **Fotografía (certeza media):** personal real del hospital, sonriente, en contacto con el paciente (la portada del
  informe 2025 muestra una médica tomando la mano de un paciente), luz natural y fachada con mosaico de colores. Para
  el asistente interno no hacen falta fotos.
- **Fachada:** torre con mosaico de cuadros de colores (azules, verdes, rojos, amarillos) junto a la escultura del
  barranquero. Es un referente visual de la ciudad.

## 6. Tono de voz (certeza media)

- Lema de marca: **"Queremos devolver sonrisas"**, con la etiqueta `#QueremosDevolverSonrisas`.
- Lema del informe 2025: **"Cuidamos la salud de nuestra gente"**.
- Misión: *"Cuidamos su salud con amor y responsabilidad, educamos e investigamos con vocación."*
- Registro: institucional pero cálido y cercano ("nuestra gente", "amor", "vocación"). Trata de usted o de tú según
  la pieza: la web usa el tú ("Agenda tu cita", "Tu donación salva historias"). Hay orgullo regional ("pioneros en
  el Eje Cafetero").
- **Para el asistente:** tuteo respetuoso, frases cortas, sin jerga técnica en la respuesta principal (la jerga va al
  modo diagnóstico), cálido sin ser informal, sin emojis en las respuestas.

## 7. Mascota

**Conclusión: no se encontró ninguna mascota oficial.** Se buscó en el sitio (búsqueda interna y biblioteca de
medios con "mascota", "personaje", "barranquero", "colibrí"), en buscadores ("SES HUC mascota", "personaje
institucional", "muñeco", "campaña") y en noticias (La Patria). No aparece ningún personaje con nombre ni campaña con
mascota. Facebook e Instagram no se pudieron revisar sin sesión, así que una mascota usada solo en redes no se puede
descartar del todo (certeza **media** de que no existe). **No se inventó ninguna mascota.**

El símbolo más cercano es **el barranquero**, un ave emblemática de Manizales (*Momotus aequatorialis*):

- El **"Monumento al Buen Acto"** es una escultura del maestro **Luis Guillermo Vallejo Vargas** sobre la torre de
  mosaico del hospital. Un barranquero azul y verde, de ojo rojo y cola larga con raqueta, levanta el vuelo. Según la
  página oficial, *"el ave Fénix Barranquero emerge con su vuelo hacia las alturas"* y *"es ese pájaro que nos es
  familiar, que cuida a nuestra gente y representa la esperanza"* (texto del Dr. Óscar Jaramillo Robledo). Se
  inauguró hacia 2024 (*Archivos de Medicina* 24(2)).
- En septiembre de 2026 el sitio publicó `ave-banner-azul.png`, una foto recortada del ave sobre la torre usada como
  banner. Es decir, el hospital ya lo usa como imagen de marca. Certeza **alta** de que es un símbolo institucional,
  **no** una mascota.

### Opciones propuestas (para decidir con Comunicaciones)

| Opción | Qué es | A favor | En contra |
|---|---|---|---|
| **A. "Sonrisa" del isotipo** (recomendada para ya) | Una de las cuatro caras del isotipo, que se usa sola como avatar y como glifo de estados | Es marca oficial, no se inventa nada. Se lee bien a 24-32px y es coherente con "Queremos devolver sonrisas" | Variar la expresión (pensando, sin resultados) toca la forma del logo: necesita visto bueno |
| **B. Barranquero estilizado** | Ilustración plana del ave del monumento | Símbolo propio y querido. Representa "cuidar a nuestra gente" y la esperanza | Hay que diseñarlo con un ilustrador y validarlo. A 32px pierde detalle (cola y antifaz) |
| **C. Sin personaje** | Solo el isotipo completo | Cero riesgo de marca | Menos cercano |

Archivos entregados (todos con `viewBox`, sin `id`, sin `<style>` ni scripts, listos como componente React):

| Archivo | Opción | Uso |
|---|---|---|
| `assets/marca/isotipo_ses.svg` | Oficial (recreación) | Estado vacío grande y bienvenida |
| `assets/marca/isotipo_ses_monocromo.svg` | Oficial (recreación) | Pie de página, marcas de agua, modo oscuro (`currentColor`) |
| `assets/marca/propuestas/avatar_asistente.svg` | A | **Avatar del bot** (sonrisa blanca sobre círculo `#096CB5`, probado a 24, 32 y 64px) |
| `assets/marca/propuestas/sonrisa.svg` | A | Glifo de una sola tinta (`currentColor`) para viñetas e indicadores |
| `assets/marca/propuestas/estado_pensando.svg` | A | Ilustración de "pensando": ojos hacia arriba y tres puntos morado, coral y verde |
| `assets/marca/propuestas/estado_sin_resultados.svg` | A | "Sin resultados": boca neutra y lupa |
| `assets/marca/propuestas/barranquero_concepto.svg` | B | Boceto conceptual del barranquero, solo para la conversación con Comunicaciones (**no oficial**, no usar en producción) |

Todo lo que está en `propuestas/` es una **recreación o propuesta que debe validar la oficina de comunicaciones del
hospital** antes de usarse fuera del entorno de desarrollo.
