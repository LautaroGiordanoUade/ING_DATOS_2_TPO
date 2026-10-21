# Niche — frontend

Base React + TypeScript estricto + Vite. Iteración 0: layout adaptable, conexión real a
readiness, cliente HTTP y pruebas. Los problemas funcionales todavía no se implementan.

## Iniciar

Node.js 22.12+ y npm. Desde la raíz, con Docker Desktop iniciado:

```powershell
docker compose up -d --build
cd frontend
npm ci
Copy-Item .env.example .env
npm run dev
```

Abrir http://127.0.0.1:5173. No requiere usuario ni seed: Inicio consulta
`GET /health/ready` a través del proxy `/backend`. Muestra MongoDB/Redis/Neo4j según
la respuesta real; con la API apagada muestra error y permite reintentar.

`VITE_API_BASE_URL` es la raíz de la API **sin** `/api/v1`: el cliente recibe paths
completos, por ejemplo `/health/ready` o `/api/v1/posts`. El valor predeterminado es
`/backend`. `API_PROXY_TARGET` permite cambiar el destino del proxy de Vite.
Nunca poner secretos en variables `VITE_`; se exponen en el navegador.

Para servir el build fuera de Vite configurar un reverse proxy `/backend` hacia
FastAPI (eliminando ese prefijo) y fallback de rutas SPA a `index.html`. Si se elige
una API en otra origin, esa API deberá permitir CORS expresamente. El proxy dev no
es una configuración de producción. `npm run preview` sirve el build en el puerto
4173 e incluye el mismo proxy únicamente para revisión local.

## Validación

```powershell
npm run lint
npm run typecheck
npm run test
npm run build
npx playwright install chromium
npm run test:e2e
```

Si ya existe Microsoft Edge se puede evitar la descarga de Chromium:

```powershell
$env:PLAYWRIGHT_CHANNEL = "msedge"
npm run test:e2e
Remove-Item Env:PLAYWRIGHT_CHANNEL
```

Vitest/Testing Library aíslan red con mocks solo en tests. Playwright requiere Compose
saludable y prueba el backend real, sin interceptores. Ejecuta Chromium desktop y móvil,
comprueba conexión, requests, navegación, teclado, consola y desbordamiento horizontal.
Guarda capturas en `test-results/` y reporte en `playwright-report/` (ignorados por Git).
No usa ni modifica datos de usuarios en esta iteración.

## Contrato y arquitectura

Desde la raíz, regenerar contrato y tipos después de un cambio de API:

```powershell
.venv\Scripts\python.exe -m scripts.export_frontend_openapi
cd frontend
npm run api:types
```

El export importa `app.openapi()` sin arrancar los motores. `openapi.json` y
`src/services/api/schema.d.ts` son generados y versionados; no editarlos manualmente.
Los tipos estáticos no validan respuestas en ejecución: readiness se valida con Zod.

- `src/app`: router, providers y layout.
- `src/features/system`: consulta y pantalla de preparación.
- `src/services/http`: fetch centralizado, cancelación, timeout y errores.
- `src/services/api`: contrato generado.
- `src/components/common`: mensajes comunes.
- `src/styles`: Tailwind y estilos responsive.
- `tests/e2e`: smoke real de inicio desktop/móvil.

TanStack Query administra caché/carga/errores. React Hook Form se incorporará al
implementar los primeros formularios de P1; no hay dependencias ni carpetas ficticias
para pantallas futuras. Ver [plan](../docs/frontend/IMPLEMENTATION_PLAN.md) y
[evidencia de preparación](../docs/frontend/iteration_0.md).
