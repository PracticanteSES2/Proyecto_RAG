# Quickstart: frontend del chat

Requisitos: Node 24 LTS (npm 11). Todo se ejecuta dentro de `frontend/`. Las dependencias van con versión
exacta: instalar nuevas con `npm install --save-exact`.

```powershell
cd frontend
npm ci                 # instala versiones exactas de package-lock.json
npm run dev            # http://localhost:3000 con el MOCK (activo por defecto en `next dev`)
```

## Contra el backend FastAPI real

Crear `frontend/.env.local` (no se versiona):

```
NEXT_PUBLIC_API_MOCK=0
NEXT_PUBLIC_API_URL=http://localhost:8000
```

El backend debe permitir CORS desde `http://localhost:3000` y exponer las rutas de
`contracts/api-v1.md`. En producción (`npm run build && npm start`) el mock está apagado salvo que se defina
`NEXT_PUBLIC_API_MOCK=1` al compilar.

## Calidad

```powershell
npm run lint        # ESLint (incluye la regla que prohíbe colores hex) + prettier --check
npm run format      # Prettier (con el plugin de Tailwind que ordena las clases)
npm run typecheck   # tsc --noEmit
npm test            # Vitest + Testing Library
npm run build       # build de producción (descarga Montserrat/Mulish/JetBrains Mono al compilar)
```

## Probar cada caso con el mock (palabras clave en la pregunta)

| Escribe… | Resultado |
|---|---|
| «hola», «gracias» | respuesta en < 600 ms: el indicador nunca aparece |
| cualquier pregunta | etapas de progreso → tabla, fuentes y «Abrir en Power BI ›» |
| «ocupación», «cuál» | contrapregunta con tres opciones (envían `opcion_id`) |
| «qué es…», «explica» | respuesta documental que aparece de a poco (eventos `token`) |
| «salvaguarda» | el borrador trae una cifra sin respaldo; la final la quita con un fundido |
| «documentación» | respuesta documental extractiva + `aviso` con la nota neutra |
| «cola» | espera larga por carga: `cola` solo en diagnóstico; a la vista, rotación de frases de trabajo |
| «lento» | eventos `espera` del servidor a los 10 y 25 s y rotación de frases |
| «respaldo» | espera larga sin `espera`: frases generadas por el cliente |
| «error» | evento `error` → aviso amable con «Reintentar» |
| «429» | `POST /turnos` responde 429 → «No pude recibir tu pregunta en este momento…» |

Servidor caído: `curl -X POST "http://localhost:3000/api/v1/mock/caida?activa=1"` (y `activa=0` para volver).
