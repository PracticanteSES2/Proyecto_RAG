# Tema HUCaldas Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Steps use checkbox syntax.

**Goal:** Aplicar logo y colores del Hospital Universitario de Caldas a la interfaz Streamlit.
**Architecture:** tema nativo en `.streamlit/config.toml`; helper `src/ui/estilo.py::aplicar_estilo()` llamado tras `st.set_page_config` en `app.py` y `pages/1_Documentación.py`; logo con `st.logo`.
**Tech Stack:** Streamlit 1.64, Pillow (solo para convertir el logo una vez), unittest.
**Spec:** docs/superpowers/specs/2026-11-04-tema-hucaldas-design.md

## Global Constraints
- Paleta: `#3898C8` `#185888` `#7BB55C` `#E37F78`. Tema claro. Sin cambios de lógica.
- CSS solo con selectores `data-testid`.

## Review Focus
- Logo ausente → la app no debe caer (`aplicar_estilo` tolera archivo faltante).
- `config.toml` inválido → test lo parsea con `tomllib`.

### Task 1: Tema, logo y helper
**Files:** Create `.streamlit/config.toml`, `assets/logo_ses.png`, `src/ui/__init__.py`, `src/ui/estilo.py`, `tests/ui/test_estilo.py`; Modify `app.py:359-361`, `pages/1_Documentación.py:18`, `src/docs_md/interfaz.py:733`.
**Interfaces:** Produces `aplicar_estilo() -> None` y constantes `AZUL, AZUL_OSCURO, VERDE, CORAL, LOGO_PATH`.
- [ ] Test: config.toml parsea y `theme.primaryColor == AZUL_PRIMARIO`; `css()` contiene los 3 colores del filete; `LOGO_PATH.exists()`.
- [ ] Implementar; correr `python -m unittest tests.ui.test_estilo`.
- [ ] Vista previa por captura (sin commit hasta aprobación del usuario) y `graphify update .`.
