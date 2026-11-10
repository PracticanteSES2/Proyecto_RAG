"""Identidad visual del Hospital Universitario de Caldas para la interfaz Streamlit.

El tema base (colores de botones, fondos, texto) vive en .streamlit/config.toml;
aquí van el logo y el CSS mínimo que el tema nativo no cubre. Se llama una vez,
justo después de st.set_page_config, desde app.py y pages/1_Documentación.py.
"""
from pathlib import Path

import streamlit as st

AZUL = "#3898C8"
AZUL_PRIMARIO = "#2B7FB0"  # azul del logo, oscurecido para que el texto blanco sea legible
AZUL_OSCURO = "#185888"
VERDE = "#7BB55C"
CORAL = "#E37F78"
LOGO_PATH = Path(__file__).resolve().parents[2] / "assets" / "logo_ses.png"


def css() -> str:
    return f"""
<style>
.stApp::before {{
  content: ""; position: fixed; top: 0; left: 0; right: 0; height: 4px; z-index: 999991;
  background: linear-gradient(90deg, {AZUL} 0 34%, {VERDE} 34% 67%, {CORAL} 67% 100%);
}}
h1, h2, h3 {{ color: {AZUL_OSCURO}; }}
h1 {{ border-bottom: 3px solid {AZUL}; padding-bottom: .3rem; }}
[data-testid="stChatMessage"] {{ border-radius: 14px; border: 1px solid #D6E6F1; }}
[data-testid="stLogo"] {{ height: 3.8rem; }}
</style>
"""


def aplicar_estilo() -> None:
    if LOGO_PATH.exists():
        st.logo(str(LOGO_PATH), size="large", icon_image=str(LOGO_PATH))
    st.markdown(css(), unsafe_allow_html=True)
