---
description: "Tareas de la documentación viva en la web"
---

# Tareas: Documentación viva en la web

**Entrada**: `specs/013-documentacion-web/` (spec.md, plan.md, contracts/api-documentacion.md)

**Pruebas**: obligatorias (TDD): primero la prueba en rojo, luego el código.

## Fase 1: Backend — vista pura

- [x] T001 Pruebas de `documentacion_vista` (ficha, cuerpo, historial, etiqueta, describir operación, texto actual,
  diff por tramos, conteo de líneas, cómo se eligió la página, tiempos) en `tests/backend/test_documentacion_vista.py`
- [x] T002 `backend/app/services/documentacion_vista.py`

## Fase 2: Backend — servicio

- [x] T003 Dobles del actualizador y de la indexación en `tests/backend/documentacion_doble.py` (con compuerta)
- [x] T004 Pruebas del servicio (lectura, propuesta asíncrona y su progreso, aclaración, corrección, descarte,
  aprobación, archivo modificado, reindexación con la piscina retenida, motor externo) en
  `tests/backend/test_documentacion_servicio.py`
- [x] T005 `backend/app/services/documentacion_indice.py` (CoordinadorIndice, ProveedorObservado, frases)
- [x] T006 `backend/app/services/documentacion.py` (ServicioDocumentacion)
- [x] T007 `InstanciaMotor.retriever` y `Huella.invalidar()`

## Fase 3: Backend — API

- [x] T008 Pruebas de punta a punta con TestClient en `tests/backend/test_documentacion_api.py`
- [x] T009 Esquemas `backend/app/schemas/documentacion.py`, errores en `core/errores.py`, router
  `backend/app/api/v1/documentacion.py`, cableado en `main.py`
- [x] T010 Contrato en `contracts/api-documentacion.md` y referencia en `docs/backend.md`

## Fase 4: Frontend

- [x] T011 Tipos y métodos del cliente (`lib/api/tipos.ts`, `lib/api/cliente.ts`) + pruebas
- [x] T012 Mock (`lib/mock/documentacion*.ts`, `app/api/v1/documentacion/**`) + pruebas
- [x] T013 Hooks `useDocumentacion` y `usePropuesta` (sondeo con `lib/sondeo.ts`)
- [x] T014 Componentes `components/documentacion/*` + pruebas de componentes
- [x] T015 Ruta `app/documentacion/page.tsx` y enlace «Chat · Documentación» en el encabezado
- [x] T016 lint + typecheck + test + build; capturas (explorador, documento, propuesta con diff, aprobada, móvil)

## Fase 5: Cierre

- [x] T017 Paridad en `docs/ARQUITECTURA.md` §9 (documentación viva) y marcar lo cubierto
- [x] T018 Doctor `--verificar` sin bajar; `graphify update .`; `git merge desarrollo`
