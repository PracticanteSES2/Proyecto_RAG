# Tema visual Hospital Universitario de Caldas — diseño (cambio pequeño)

**Intención:** que la interfaz Streamlit (chat y página Documentación) use la identidad del Hospital Universitario de Caldas: logo y colores.
**Metas:** logo en barra lateral y pestaña; paleta del logo en botones, títulos y fondos; un único lugar para el estilo.
**No-metas:** tocar la lógica del RAG/Power BI; modo oscuro; rediseñar el contenido.
**Anti-metas:** que el CSS dependa de clases internas de Streamlit que cambian entre versiones (se usan solo `data-testid`).

**Paleta (medida del logo):** azul `#3898C8`, azul oscuro `#185888`, verde `#7BB55C`, coral `#E37F78`. El morado no se usa.

## Enfoques
1. Solo `.streamlit/config.toml` — robusto, pero poco distintivo.
2. **Elegido:** tema nativo + `st.logo` + helper `src/ui/estilo.py` con CSS mínimo (filete tricolor, títulos, burbujas de chat).
3. CSS repartido por archivo — duplicado y frágil.

## Decisiones
- Tema claro únicamente (el logo es JPG con fondo blanco; se convierte a PNG transparente en `assets/logo_ses.png`).
- Se quitan los emojis 📊 y 📚 de los títulos; el icono de la pestaña es el logo.
- Color primario con contraste suficiente para texto blanco en botones (el builder lo valida).
