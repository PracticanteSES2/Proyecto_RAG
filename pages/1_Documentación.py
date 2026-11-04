"""
Página «Documentación» (multipágina de Streamlit por carpeta pages/).

`streamlit run app.py` la muestra en la barra lateral junto al chat; app.py no
cambia. La lógica está en src/docs_md/interfaz.py.
"""
import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.docs_md.interfaz import pagina  # noqa: E402
from src.ui.estilo import LOGO_PATH, aplicar_estilo  # noqa: E402

st.set_page_config(page_title="Documentación de tableros", page_icon=str(LOGO_PATH) if LOGO_PATH.exists() else "📚", layout="wide")
aplicar_estilo()
pagina()
