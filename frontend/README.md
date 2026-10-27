# Niche — frontend

React + TypeScript estricto + Vite, integrado con los ocho problemas del backend real.

| Problema | Funcionalidad y navegación |
|---|---|
| P1 | Registro/login/logout, Publicar, Mis publicaciones, borrador y operación recuperable |
| P2 | Perfiles, seguir/dejar de seguir, Solicitudes privadas y aprobación |
| P3 | Inicio con feed paginado, ranking, refresco y autores |
| P4 | Sugerencias, amigos en común y edición de intereses |
| P5 | Reacciones y comentarios paginados, con actualización de lista/contadores |
| P6 | Mensajes, creación de grupos, historial y lectura por participante |
| P7 | Reportes propios, Moderación por rol, contenido oculto protegido y decisiones recuperables |
| P8 | Mi cuenta / Cuentas, trazabilidad, suspensión/reactivación y presencia |

La carga de 50.000 publicaciones y las cuentas sintéticas se describen en
[dataset](../docs/dataset.md). Moderación y gestión de otras cuentas requieren moderator/admin;
la autorización efectiva se valida en el servidor.

## Iniciar con Docker

Desde la raíz, con Docker Desktop iniciado:

```powershell
docker compose up -d --build
docker compose ps
```

Abrir http://127.0.0.1:8080. Compose construye el frontend en una etapa con Node y sirve
el resultado estático con Nginx; no requiere Node/npm en el host. El contenedor espera
a que la API esté saludable. Nginx envía `/backend/` a `api:8000`, elimina el prefijo y
conserva los headers de autenticación. Las rutas React admiten navegación y recarga directa.
`/healthz` comprueba Nginx; `/backend/health/ready` comprueba la API y sus motores.

Después de cambiar el frontend, reconstruirlo con `docker compose up -d --build frontend`.
La imagen utiliza `/backend` como raíz de API y no incorpora archivos `.env` locales.
Los datos continúan en los volúmenes de los servicios existentes.

## Desarrollo local

Node.js 22.12+ y npm. Desde la raíz, con Docker Desktop iniciado:

```powershell
docker compose up -d --build
cd frontend
npm ci
Copy-Item .env.example .env
npm run dev
```

Abrir http://127.0.0.1:5173. La bienvenida no requiere usuario ni seed: consulta
`GET /health/ready` a través del proxy `/backend`. Crear cuenta en `/registro`, iniciar
sesión en `/login` y publicar en `/publicar`. Inicio con sesión muestra el feed de cuentas
seguidas; las propias están en `/mis-publicaciones`. `/operaciones/{id}` sigue el trabajo
durable y confirma el resultado real.
Sin sesión, Inicio muestra la bienvenida y el estado de los tres motores.

`VITE_API_BASE_URL` es la raíz de la API **sin** `/api/v1`: el cliente recibe paths
completos, por ejemplo `/health/ready` o `/api/v1/posts`. El valor predeterminado es
`/backend`. `API_PROXY_TARGET` permite cambiar el destino del proxy de Vite.
Nunca poner secretos en variables `VITE_`; se exponen en el navegador.

El servicio Docker ya configura el reverse proxy `/backend` hacia FastAPI y el fallback
de rutas SPA a `index.html`. Para otro servidor se debe conservar esa configuración. Si se elige
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
P1 crea cuentas y publicaciones QA con UUIDs/credenciales aleatorios, conservados para
inspección; no modifica cuentas anteriores. Usa P2 solo para preparar un seguidor real.
`test:e2e` construye el frontend y ejecuta preview en el puerto 4174, separado de Vite dev,
con dos workers. Las páginas y requests del E2E usan ese build, sin HMR.

Para ejecutar los mismos E2E contra el frontend de Docker ya iniciado, sin levantar Vite:

```powershell
$env:PLAYWRIGHT_BASE_URL = "http://127.0.0.1:8080"
$env:PLAYWRIGHT_CHANNEL = "msedge" # Opcional si se usa Chromium instalado por Playwright
npx playwright test
Remove-Item Env:PLAYWRIGHT_BASE_URL
Remove-Item Env:PLAYWRIGHT_CHANNEL
```

Última integración de interfaces validada: **203 pruebas frontend y 46 recorridos E2E**
de escritorio/móvil, lint, TypeScript y build correctos. Los E2E se ejecutaron contra Docker
en el puerto 8080, sin iniciar Vite. Las cifras son evidencia de esa corrida, no pruebas
ejecutadas automáticamente al abrir la aplicación. Ver [integración P7/P8](../docs/frontend/integration_p7_p8.md).
La validación inicial de Nginx, healthcheck, recargas de rutas, caché de assets y respuestas
404 de API/assets está en [iteration_0.md](../docs/frontend/iteration_0.md).

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
- `src/features/system`: consulta y bienvenida.
- `src/features/auth`: formularios RHF/Zod y sesión validada por `/users/me`.
- `src/features/posts`: borradores, envío idempotente, operación, contenido y distribución P1.
- `src/features/feed`: feed autenticado, cursor opaco, refresco y perfiles de autores con caché.
- `src/features/social`: perfiles, relaciones, solicitudes y recuperación P2.
- `src/features/recommendations`: intereses, sugerencias y amigos en común P4.
- `src/features/interactions`: reacciones, comentarios paginados y contadores P5.
- `src/features/messages`: grupos, historial, envío y lectura propia P6.
- `src/features/moderation`: reportes, bandeja por rol, decisiones confirmadas e historial P7.
- `src/features/accounts`: consulta agregada, suspensión/reactivación, presencia e historial P8.
- `src/services/http`: fetch centralizado, cancelación, timeout y errores.
- `src/services/api`: contrato generado.
- `src/components/common`: mensajes comunes.
- `src/styles`: Tailwind y estilos responsive.
- `tests/e2e`: recorridos reales P1–P8 en escritorio/móvil.

TanStack Query administra caché/carga/errores; React Hook Form + Zod validan formularios.
Las pantallas de formularios y operaciones se cargan por demanda. La credencial, los borradores
y los intentos recuperables se conservan en sessionStorage de esta pestaña, separados por cuenta.
Logout elimina la credencial y caché; no existe logout remoto ni refresh token.
Los borradores/intentos se aíslan por cuenta para poder recuperar un envío incierto.
No se guardan contraseñas.

`POST /api/v1/posts` ahora requiere bearer y autor coincidente; el alias educativo
`/api/v1/problems/1/publish` conserva el contrato previo para los scripts del TP.
Ese alias y las consultas de operación/preview continúan siendo públicas: el conjunto
de la API no se presenta como cerrado para producción.

Guías: [P1](../docs/frontend/problem_1.md), [P2](../docs/frontend/problem_2.md),
[P3](../docs/frontend/problem_3.md), [P4](../docs/problems/problem_04.md),
[P5](../docs/problems/problem_05.md), [P6](../docs/frontend/problem_6.md),
[P7](../docs/frontend/problem_7_recovery.md), [P8](../docs/frontend/problem_8.md)
y [estado de implementación](../docs/frontend/IMPLEMENTATION_PLAN.md).
