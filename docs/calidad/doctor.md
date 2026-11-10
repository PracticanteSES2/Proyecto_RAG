# Doctor de salud del proyecto

`tools/doctor` es el equivalente de [react-doctor](https://www.react.doctor) para este proyecto:
escanea el repo, da un **puntaje 0-100** por categoría y por perfil, lista los problemas con
`archivo:línea` y una sugerencia, y aplica un **trinquete**: ningún cambio puede bajar el
puntaje ni introducir hallazgos altos nuevos.

Hay dos perfiles, uno por stack:

| Perfil | Qué mira | Cómo |
|---|---|---|
| `backend` | Python: `src/` (motor), `backend/` (FastAPI), `tools/`, `tests/` y el legado Streamlit | Reglas propias con `ast` (librería estándar). ruff y vulture opcionales, solo informativos. |
| `frontend` | `frontend/` (Next.js App Router + TypeScript) | Reglas propias (sin Node) + `tsc --noEmit`, ESLint y **react-doctor** cuando hay Node y dependencias. |

## Uso

```powershell
.venv\Scripts\python.exe -X utf8 -m tools.doctor                # ambos perfiles
.venv\Scripts\python.exe -X utf8 -m tools.doctor backend        # solo backend
.venv\Scripts\python.exe -X utf8 -m tools.doctor frontend       # solo frontend
.venv\Scripts\python.exe -X utf8 -m tools.doctor --verificar    # trinquete (código ≠ 0 si empeora)
.venv\Scripts\python.exe -X utf8 -m tools.doctor --actualizar-linea-base   # sube el listón
```

Opciones: `--json` (informe por stdout), `--md informe.md`, `--todo` (todos los hallazgos, no
solo el top), `--top N`, `--cambios origin/desarrollo` (solo hallazgos de archivos cambiados,
útil en revisión), `--sin-externas` (no corre ruff/vulture/tsc/eslint/react-doctor),
`--estricto` (con `--verificar`, falla si algo de la línea base no se pudo verificar),
`--forzar` (con `--actualizar-linea-base`, acepta un retroceso consciente).

Códigos de salida: `0` bien · `1` el trinquete falló (o se negó a bajar el listón) · `2` error
de uso (p. ej. no hay línea base) · `3` con `--estricto`, partes sin verificar.

Tarda ~20 s en el repo (sin externas).

## Cómo leer el informe

```
Puntaje global: 64.1/100 (necesita trabajo)
BACKEND   64.1/100
  Tamaño y complejidad      17.5  ##........   935 hallazgos (501 altos)
  ...
  [alta] tamano/archivo_grande  src/chatbot/query_engine.py:1
      7567 líneas (umbral 400; alto 800).
      -> Partirlo por responsabilidades …
```

- **Bandas** (como react-doctor): ≥ 75 bien · 50-74 necesita trabajo · < 50 crítico.
- **Severidad**: `alta` (bloquea si es nueva), `media`, `baja`.
- El **top** rota entre reglas para mostrar variedad; `--todo` lo muestra todo.
- Categorías **omitidas** (p. ej. `react` sin Node) aparecen con su motivo y no cuentan.

## Qué mide

### Perfil backend

| Categoría | Reglas (severidad) |
|---|---|
| Estructura | `raiz_no_permitida` (alta): entrada de la raíz fuera de la lista blanca · `archivo_temporal` (alta): logs, zips, .bak… versionados · `archivo_pesado` (media) · `carpeta_sin_dueno` (media): subcarpeta de `src/` sin capa o de `tools/` no declarada · `modulo_suelto_src` (media) · `legado_crece` (alta): `app.py`, `pages/`, `.streamlit/` o `src/ui/` crecieron respecto de la línea base · `no_ignorada` (alta): `var/`, `data/`, `.venv/`… (en la raíz) o `__pycache__/`, `node_modules/`, `.next/` (en cualquier nivel) que git no ignora · `salida_fuera_de_var` (media): un `.gitignore` que ignora salidas (`out/`, `salidas/`, `logs/`…) junto al código en vez de usar `var/` |
| Tamaño y complejidad | `archivo_grande` (>400 media, >800 alta) · `funcion_larga` (>50 media, >80 alta) · `complejidad` ciclomática tipo McCabe (>10 media, >15 alta) · `demasiados_parametros` (>8, baja). Umbrales de docs/ARQUITECTURA.md §7: el código heredado los supera, el trinquete solo penaliza lo que crezca |
| Duplicación | `funcion_identica` (media): mismo cuerpo en dos sitios · `funcion_casi_identica` (baja): misma estructura con otros nombres/literales · `utilidad_repetida` (media): utilidades que deben existir una sola vez (quitar tildes con `unicodedata.normalize`, calcular la raíz del proyecto con `Path(__file__).parents[n]`) |
| Código muerto | `modulo_sin_uso` (media) · `modulo_solo_pruebas` (baja) · `simbolo_sin_uso` (baja) · `import_sin_uso` (baja; respeta `# noqa` y reexportaciones) |
| Capas e importaciones | `importacion_prohibida` (alta): `src` → `backend`/`tools`/`tests`/`app`/`pages` o paquetes `fastapi`/`starlette`/`redis`; `backend.app.api` → `src`; `backend` → `src.ui`/`streamlit`/`tools`/`tests`; `tools` → `tests` (salvo `excepto = ["tools.manual"]`)… · `capa_invertida` (alta): capa baja que importa una alta (orden: comun → providers/llm/rag → semantic/dax/docs_md/ingestion → chatbot/feedback → ui legado → backend core/schemas → services → api) · `ciclo` (media): ciclos de imports a nivel de módulo · `importacion_rota` (alta) |
| Pruebas | `modulo_sin_pruebas` (media): ninguna prueba lo alcanza ni indirectamente · `prueba_huerfana` (alta): la prueba importa algo que ya no existe · `patch_roto` (alta): `mock.patch("src.x.y")` que apunta a nada · `archivo_prueba_vacio` (baja) |
| Higiene | `print_depuracion` (media, en `src/` y `backend/`) · `except_desnudo` (alta) · `except_silencioso` (media: `except Exception: pass`) · `punto_de_ruptura` (alta) · `sys_path` (media) · `todo` (baja; la antigüedad se informa con git blame pero no puntúa) · `secreto` (alta) · `ruta_usuario` (media: `C:\Users\<nombre>` codificado) · `bom` (baja) · `no_utf8` (media) · `mojibake` (media: la «ó» convertida en dos caracteres raros por una doble codificación UTF-8/cp1252) · `sintaxis_invalida` (alta) · `nombre_prohibido` (media): `utils.py`, `helpers.py`, `final*.py`, `*_v2.py`, `copia*`… |
| FastAPI (`backend/`) | `router_fuera_de_api` (media): `APIRouter`/endpoints fuera de `backend/app/api/v1` · `sin_response_model` (media) · `dict_suelto` (media): parámetros `dict`/`Any` en vez de esquemas pydantic · `logica_en_router` (media: endpoint > 30 líneas o complejidad > 5) · `router_importa_motor` (media: el router importa `src` sin pasar por `services/`) · `bloqueante_en_async` (alta: `time.sleep`, `requests`, `open`, `subprocess`, redis síncrono… dentro de `async def`) · `getenv_disperso` (media: `os.getenv` fuera de `backend/app/core/config.py`) · `settings_sin_pydantic` (media) |

### Perfil frontend

| Categoría | Fuente |
|---|---|
| Estructura | `fuera_de_lugar` (media): entradas de `frontend/` fuera de app/, components/, lib/, hooks/, styles/, public/, types/… y configuración conocida · `archivo_temporal` (alta) |
| Tipos (sin any) | `any` (media) · `ts_ignore` (media) · `ts_expect_error` (baja) |
| Compilación (tsc) | cada error de `tsc --noEmit` (alta) |
| Lint (ESLint) | errores (media) y avisos (baja) de `eslint . --format json` con la configuración del proyecto |
| React (react-doctor) | diagnósticos de `react-doctor . --json --no-score --blocking none -y --no-supply-chain` (error → alta, aviso → media) |
| Arquitectura | `fetch_fuera_de_api` (alta): `fetch`/`axios` fuera de `fetch_solo_en` (`frontend/lib/api`) · `hex_fuera_de_tokens` (media): colores `#…` fuera de `styles/tokens.*` o `app/globals.css` · `componente_grande` (.tsx >150 media, >250 alta) · `archivo_grande` (.ts >250 media, >400 alta) · `importacion_prohibida` (alta): `components/ui` → `lib/api`/`app`, `components` → `app`, `lib` → `app`/`components`/`hooks` (rutas relativas y alias `@/`) · `generado_editado` (media): archivo de `lib/api/generado` sin marca de generación (al cliente generado no se le aplican reglas de estilo) |
| Higiene | `console_log` (media) · `debugger` (alta) · `todo` (baja) · `eslint_disable` (baja) · secretos, rutas de usuario, BOM y mojibake (como en backend) |

react-doctor se usa tal cual: si está en `frontend/node_modules/.bin` se usa ese; si no, `npx -y
react-doctor@0.9.22` (versión fijada en `reglas.toml`; requiere red la primera vez). Su `--json`
no tiene esquema documentado, así que el lector es tolerante (busca objetos con archivo y
mensaje y hereda regla/severidad de sus padres). `--no-score` evita la API de puntaje remota:
el puntaje lo calcula el doctor con la misma fórmula que el resto. Si falta Node, `npm ci`,
`tsconfig.json` o configuración de ESLint, esa categoría se **omite con aviso** y no entra en
el puntaje ni en el trinquete; las reglas propias siguen funcionando sin Node.

## Puntaje

Por categoría: `P = Σ peso_severidad · √n` (sumado por regla y severidad; alta 6, media 2,
baja 0.5) y `puntaje = 100 · E / (E + P)`, con `E` la `escala` de la categoría (la
penalización que la deja en 50). La raíz hace que eliminar una regla entera valga más que
quitar una ocurrencia suelta, pero **cualquier hallazgo nuevo baja el puntaje**. El puntaje de
cada perfil es la media ponderada (`peso`) de sus categorías evaluadas; el global, la media
ponderada de los perfiles (`[perfiles] pesos`, backend 60 / frontend 40). Ruff y vulture no
puntúan, para que el resultado no dependa de lo instalado. El puntaje tampoco depende de la
fecha.

## Trinquete (nunca bajar el listón)

`tools/doctor/linea_base.json` guarda, por perfil, el puntaje, el de cada categoría, el conteo
de huellas de cada hallazgo y el tamaño del legado. Una **huella** es `regla|archivo|clave`,
donde la clave no usa el número de línea (p. ej. la función o el n-ésimo `print` dentro de
ella), así que mover código dentro de un archivo no crea hallazgos «nuevos».

`--verificar` falla (código 1) si:

1. baja el puntaje de alguna categoría, de un perfil o el global (más allá de `tolerancia`, 0 por defecto);
2. aparece un hallazgo **alto** nuevo (huella que no estaba o que aparece más veces); o
3. el legado Streamlit crece (es un hallazgo alto nuevo: `legado_crece`).

Los hallazgos viejos se toleran. Los nuevos medios/bajos se listan y, como bajan el puntaje,
también hacen fallar salvo que el cambio arregle otra cosa que compense.

Perfiles o categorías que hoy no se pueden medir (sin `frontend/`, sin Node) se avisan y no
fallan; con `--estricto` salen con código 3. Un archivo que cambia de carpeta genera huellas
nuevas: se revisa y se sube el listón.

### Subir el listón

Cuando el puntaje sube, `--verificar` lo dice. Entonces:

```powershell
.venv\Scripts\python.exe -X utf8 -m tools.doctor --actualizar-linea-base
git add tools/doctor/linea_base.json
```

`--actualizar-linea-base` se **niega** si el estado actual es peor que la línea base (el listón
solo sube). Para aceptar un retroceso consciente (p. ej. al mover un módulo de carpeta) hay que
añadir `--forzar` y explicarlo en el commit. Si un perfil o categoría no se pudo medir, se
conserva su valor anterior.

## Configuración (`tools/doctor/reglas.toml`)

Los valores salen de `docs/ARQUITECTURA.md` §12: lista blanca de la raíz, `carpetas_ignoradas`,
subcarpetas permitidas (`tools`, `docs`, `infra`, `backend`, `backend/app`), capas (de
`src.comun` a `backend.app.api`) e importaciones prohibidas con `excepto`, umbrales,
exclusiones (`.venv`, `.claude`, `graphify-out`, `data`, `tableros`, `var`, `__data`,
`fixtures`, `node_modules`…), legado, `nombres_prohibidos`, utilidades canónicas (la raíz del
proyecto ya tiene `canonico = "src/comun/rutas.py"`: cualquier otro módulo que calcule
`Path(__file__).parents[n]` es un hallazgo; la de texto se activará con `src/comun/texto.py`),
rutas FastAPI y la arquitectura del frontend (`fetch_solo_en`, `tokens`, `prohibidas`,
`generado_no_editable`, `alias_raiz`). Si la arquitectura cambia, se ajusta aquí y se
regenera la línea base.

Si `backend/` se ejecuta con `backend/` como raíz de `sys.path` (`from app.api …`), añadir
`raices_import = ["backend"]` en `[general]` para que las importaciones se resuelvan.

## Herramientas opcionales

`pip install -r requirements-dev.txt` instala ruff y vulture en un entorno de desarrollo. El
doctor las usa si están y las muestra como «Externas (informativo, no puntúa)». En el frontend,
`tsc`, ESLint y react-doctor salen de `frontend/node_modules` (`npm ci`).

## Integración

- **Pruebas**: `tests/doctor/` (mini-repos sintéticos) y `tests/doctor/test_repo.py`, que corre
  `--verificar` sobre el repo real:
  `.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests/doctor -t .`
- **Revisor**: el subagente `.claude/agents/revisor-estructura.md` revisa un diff contra
  `docs/ARQUITECTURA.md` y el doctor y bloquea lo que quede fuera de lugar, duplique una
  utilidad o baje el puntaje. `doctor-backend` y `doctor-frontend` diagnostican y priorizan
  arreglos de cada stack.
- **Hook pre-commit (opcional, no se instala solo)**. Guardar como `.git/hooks/pre-commit`
  (en un worktree, en la carpeta `hooks` del repo principal) y darle permisos de ejecución:

  ```sh
  #!/bin/sh
  # Trinquete de salud: no deja confirmar si el proyecto empeora.
  PY=.venv/Scripts/python.exe
  [ -x "$PY" ] || PY=python
  "$PY" -X utf8 -m tools.doctor --verificar --sin-externas --top 5 || {
    echo "El doctor bajó del listón. Ver docs/calidad/doctor.md (o git commit --no-verify si es consciente)."
    exit 1
  }
  ```

  Si ya existe un hook (p. ej. el de graphify), añadir estas líneas al final del existente.
