"""Configuración del doctor: valores por defecto + `reglas.toml`."""
from __future__ import annotations

import copy
import tomllib
from pathlib import Path

RUTA_REGLAS = Path(__file__).with_name("reglas.toml")

# Valores genéricos; `reglas.toml` los ajusta al proyecto.
DEFAULTS: dict = {
    "perfiles": {"pesos": {"backend": 60, "frontend": 40}},
    # ------------------------------------------------------------------ backend
    "general": {
        # Sin "/": cualquier componente de la ruta; con "/" inicial: anclado a la raíz.
        # El perfil backend no mira frontend/ (lo analiza el perfil frontend).
        "exclusiones": [
            "/.venv", "/venv", ".git", "/.claude", "/graphify-out", "/data", "/tableros",
            "/__data", "fixtures", "__pycache__", "node_modules", "/.superpowers",
            "/Documentacion", "/frontend",
        ],
        "codigo": ["src", "backend", "tools", "pages", "app.py"],
        "pruebas": ["tests", "backend/tests"],
        "paquete": "src",
        # Carpetas que actúan como raíz de sys.path (sus módulos se importan sin el prefijo).
        "raices_import": [],
        "tolerancia": 0.0,
    },
    "puntaje": {
        "pesos_severidad": {"alta": 6.0, "media": 2.0, "baja": 0.5},
    },
    "categorias": {
        "estructura": {"peso": 15, "escala": 30},
        "tamano": {"peso": 15, "escala": 60},
        "duplicacion": {"peso": 10, "escala": 40},
        "muerto": {"peso": 10, "escala": 40},
        "capas": {"peso": 15, "escala": 40},
        "pruebas": {"peso": 10, "escala": 40},
        "higiene": {"peso": 15, "escala": 40},
        "fastapi": {"peso": 10, "escala": 30},
    },
    "legado": {
        # Se toleran, pero si crecen respecto de la línea base es un hallazgo alto.
        "rutas": [],
    },
    "estructura": {
        "raiz_permitida": ["app.py", "src", "backend", "frontend", "tools", "tests", "docs", ".gitignore", "requirements*.txt"],
        "patrones_temporales": [
            "*.log", "*.tmp", "*.temp", "*.bak", "*.orig", "*.rej", "*.swp", "*~", "*.zip",
            "*.7z", "*.rar", "*.pyc", "*.pyo", ".DS_Store", "Thumbs.db", "desktop.ini",
            "nohup.out", "~$*", "*.pid", "*.dump",
        ],
        # Carpetas cuyas subcarpetas directas deben estar declaradas. `src` se
        # controla con las capas.
        "subcarpetas": {},
        # Deben estar ignoradas por git si existen (lo que git no ignora sale en el listado).
        "carpetas_ignoradas": [],
        "max_archivo_kb": 1024,
        "binario_permitido": ["assets/**", "docs/**"],
    },
    "tamano": {
        "aplica_a": ["src", "backend", "tools", "pages", "app.py"],
        "archivo_media": 800,
        "archivo_alta": 3000,
        "funcion_media": 80,
        "funcion_alta": 200,
        "complejidad_media": 15,
        "complejidad_alta": 40,
        "parametros_max": 8,
    },
    "duplicacion": {
        "aplica_a": ["src", "backend", "tools", "pages", "app.py"],
        "min_lineas": 6,
        "min_lineas_casi": 10,
        "utilidades": [
            {
                "nombre": "normalizar texto / quitar tildes",
                "llamadas": ["unicodedata.normalize"],
                "aplica_a": ["src", "backend", "pages", "app.py"],
                "canonico": "",
                "sugerencia": "Centralizar en un único módulo de utilidades de texto (ver docs/ARQUITECTURA.md) y reutilizarlo.",
            },
            {
                "nombre": "raíz del proyecto",
                "patron": "raiz_proyecto",
                "aplica_a": ["src", "backend", "pages", "app.py"],
                "canonico": "",
                "sugerencia": "Definir la raíz una sola vez en un módulo de rutas común e importarla.",
            },
        ],
    },
    "muerto": {
        "aplica_a": ["src", "backend"],
        "ignorar_nombres": ["main", "setUp", "tearDown", "setUpClass", "tearDownClass", "lifespan"],
        "ignorar_prefijos_metodo": ["visit_", "generic_visit", "do_", "test"],
    },
    "capas": {
        "orden": [],
        # `desde`/`hacia` son prefijos de módulo (punteados).
        "prohibidas": [
            {"desde": "src", "hacia": ["backend", "tools", "tests", "app", "pages"]},
            {"desde": "backend", "hacia": ["tools", "tests", "app", "pages"]},
            {"desde": "tools", "hacia": ["tests", "app", "pages"]},
            {"desde": "app", "hacia": ["tools", "tests", "pages"]},
            {"desde": "pages", "hacia": ["tools", "tests"]},
        ],
    },
    "pruebas": {
        "aplica_a": ["src", "backend"],
        "patron_archivo": "test_*.py",
    },
    "higiene": {
        "print_en": ["src", "backend"],
        "sys_path_en": ["src", "backend"],
        "todo_marcas": ["TODO", "FIXME", "XXX", "HACK"],
        "todo_dias_viejo": 90,
        "extensiones_texto": [
            ".py", ".md", ".toml", ".txt", ".json", ".ps1", ".yml", ".yaml", ".cfg", ".ini",
            ".csv", ".sql", ".dax", ".tmdl", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".css", ".scss",
        ],
        "extensiones_codigo": [
            ".py", ".ps1", ".toml", ".cfg", ".ini", ".bat", ".cmd", ".sh", ".yml", ".yaml",
            ".ts", ".tsx", ".js", ".jsx", ".mjs",
        ],
        "bom_permitido": ["*.ps1"],
        # Nombres de archivo prohibidos en código y pruebas (genéricos o de versión).
        "nombres_prohibidos": [],
        "secreto_placeholders": ["fake", "falso", "dummy", "test", "prueba", "ejemplo", "example", "xxx", "placeholder", "changeme", "<", "${", "{"],
        "max_kb_texto": 2048,
    },
    "fastapi": {
        "aplica_a": ["backend"],
        "carpeta_routers": ["backend/app/api/v1"],
        "endpoints_permitidos_fuera": [],
        "modulos_settings": ["backend/app/core/config.py"],
        "motor_prohibido_en_routers": ["src"],
        "max_lineas_endpoint": 30,
        "max_complejidad_endpoint": 5,
        "bloqueantes": [
            "time.sleep", "open", "input",
            "requests.get", "requests.post", "requests.put", "requests.patch", "requests.delete",
            "requests.head", "requests.request", "requests.Session",
            "httpx.get", "httpx.post", "httpx.put", "httpx.patch", "httpx.delete", "httpx.request", "httpx.Client",
            "urllib.request.urlopen", "subprocess.run", "subprocess.call", "subprocess.check_output",
            "subprocess.check_call", "subprocess.Popen", "os.system",
            "redis.Redis", "redis.StrictRedis", "redis.from_url",
            "sqlite3.connect", "psycopg2.connect", "pyodbc.connect",
        ],
    },
    "externas": {
        "activar": True,
        "timeout": 90,
        "ruff_reglas": ["F401", "F811", "F841", "E722", "B006", "T201", "ASYNC"],
        "vulture_confianza": 80,
    },
    # ------------------------------------------------------------------ frontend
    "frontend": {
        "carpeta": "frontend",
        "exclusiones": ["node_modules", ".next", "out", "build", "dist", "coverage", ".turbo", "next-env.d.ts", "*.tsbuildinfo"],
        "categorias": {
            "estructura": {"peso": 10, "escala": 30},
            "tipos": {"peso": 15, "escala": 40},
            "compilacion": {"peso": 20, "escala": 30},
            "lint": {"peso": 15, "escala": 50},
            "react": {"peso": 20, "escala": 50},
            "arquitectura": {"peso": 10, "escala": 40},
            "higiene": {"peso": 10, "escala": 40},
        },
        "raiz_permitida": [
            "app", "src", "components", "lib", "hooks", "styles", "public", "types", "tests", "__tests__", "e2e",
            "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "tsconfig.json", "next.config.*",
            "eslint.config.*", ".eslintrc*", "postcss.config.*", "tailwind.config.*", "vitest.config.*",
            "jest.config.*", "playwright.config.*", "components.json", "middleware.ts", "instrumentation.ts",
            ".prettierrc*", ".prettierignore", ".gitignore", ".env.example", "README.md", "Dockerfile", ".dockerignore",
            "doctor.config.*",
        ],
        "carpetas_api": ["frontend/lib/api", "frontend/src/lib/api"],
        "tokens": ["frontend/styles/tokens.*", "frontend/src/styles/tokens.*", "frontend/app/globals.css",
                   "frontend/src/app/globals.css", "frontend/tailwind.config.*"],
        "componente_media": 250,
        "componente_alta": 500,
        "archivo_ts_media": 250,
        "archivo_ts_alta": 400,
        # Cliente generado desde OpenAPI: no se edita a mano ni se le aplican reglas de estilo.
        "generado_no_editable": [],
        # Únicas carpetas con fetch/axios (si está vacío, `carpetas_api`).
        "fetch_solo_en": [],
        # Importaciones prohibidas entre carpetas: [{desde, hacia: [...]}]; "@/" apunta a `alias_raiz`.
        "prohibidas": [],
        "alias_raiz": "",
        "extensiones": [".ts", ".tsx", ".js", ".jsx", ".mjs", ".css", ".scss"],
        "herramientas": {
            "timeout": 300,
            "permitir_npx": True,
            "react_doctor": "react-doctor@0.9.22",
            "react_doctor_args": [".", "--json", "--no-score", "--blocking", "none", "-y", "--no-supply-chain", "--no-color"],
        },
    },
}


def _fusionar(a: dict, b: dict) -> dict:
    salida = copy.deepcopy(a)
    for clave, valor in b.items():
        if isinstance(valor, dict) and isinstance(salida.get(clave), dict):
            salida[clave] = _fusionar(salida[clave], valor)
        else:
            salida[clave] = copy.deepcopy(valor)
    return salida


def config_de(cambios: dict | None = None) -> dict:
    """Valores por defecto con `cambios` encima (las listas se reemplazan)."""
    return _fusionar(DEFAULTS, cambios or {})


def cargar_config(ruta: Path | None = None) -> dict:
    ruta = Path(ruta) if ruta else RUTA_REGLAS
    if not ruta.exists():
        return config_de()
    with ruta.open("rb") as f:
        return config_de(tomllib.load(f))
