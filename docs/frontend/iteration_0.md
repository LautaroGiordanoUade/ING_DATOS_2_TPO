# Iteración 0 — preparación del frontend

Fecha: 21/10/2026. Base `main` = `0d0f734`. Rama: `feature/frontend-react-ui`.
Iteración completada; **ningún problema funcional de frontend implementado**.

## Inspección y alcance

- Git inicialmente limpio; fetch de origin y fast-forward de main sin reescritura ni
  descarte de cambios. Rama nueva desde main actualizado. Sin frontend previo ni AGENTS.md.
- Revisados README, TODO, arquitectura/matriz, ocho guías, routers, schemas, seguridad,
  casos de uso y adaptadores. No hay archivo independiente con el enunciado original;
  inventario basado en el material del repositorio, pendiente de contraste si se aporta.
- Ocho problemas: publicación; follow/unfollow; feed; amigos en común/sugerencias;
  reacciones/comentarios; mensajería grupal; moderación; suspensión/trazabilidad.
- La actualización de main incorporó P2/P3 y correcciones P5/P8. P4 sigue parcial
  (amigos en común devuelve 501, intereses pendientes) y P6 pendiente. Los endpoints
  existentes no se equipararon a problemas completados.
- Orden propuesto: identidad compartida con P1 → P2 → P3 → P5 → P7 → P8;
  P4/P6 después de completar y verificar sus contratos backend. Ver [plan](IMPLEMENTATION_PLAN.md).

## Base creada

React 19, TypeScript estricto, Vite 7, React Router, TanStack Query, Tailwind CSS y Zod.
Vitest, Testing Library y Playwright configurados, con lockfile npm versionado.
React Hook Form se incorporará con los primeros formularios, sin dependencias sin uso ahora.

```text
frontend/
  public/favicon.svg
  src/
    app/{layouts,providers,router}/
    components/common/ErrorMessage.tsx
    features/system/{api,ConnectionStatus,SetupPage}.*
    services/http/client.ts
    services/api/schema.d.ts
    styles/index.css
    main.tsx
  tests/{e2e/setup.spec.ts,setup.ts}
  .env.example
  openapi.json
  package.json, package-lock.json
  tsconfig.json, vite.config.ts, vitest.config.ts
  playwright.config.ts, eslint.config.js
```

Una pantalla Inicio de preparación, layout claro con sidebar en escritorio y navegación
compacta móvil, más fallback 404 con regreso a Inicio. Los textos de próximas etapas no
son controles de funcionalidades implementadas. Sin feed ni publicaciones simuladas.

Cliente fetch centralizado con headers, bearer del llamador, JSON/204, timeout, cancelación,
ApiError y mensajes accesibles. Readiness valida su respuesta con Zod; un 503 con schema
válido muestra degradación por servicio. Reintentar no presenta datos anteriores como
actuales si falla. La consulta usa networkMode always para no quedar pausada y aparentar
conexión con datos anteriores cuando el navegador está offline.

## Integración real

- UI: GET `/health/ready`, a través de `/backend` en Vite → API local puerto 8000.
- OpenAPI exportado desde la aplicación Python y tipos generados con openapi-typescript;
  51 paths del snapshot coinciden con el contrato servido por la API real.
- Docker Desktop iniciado y Compose reconstruido: API/MongoDB/Redis/Neo4j saludables;
  workers P1 y P2/P7/P8 iniciados. Se conservaron volúmenes y datos previos.
- No se cambió código backend. `.dockerignore` excluye frontend para evitar enviar
  node_modules, artefactos y tests al contexto de construcción Python.
- [Smoke HTTP](backend_smoke.json): 8 requests de solo lectura más comparación del contrato,
  9 comprobaciones correctas. Health/readiness 200; feed/solicitudes/moderación/traza sin
  credenciales 401; mutual friends 501; UUID de post inválido 422.
  Esto verifica arranque y contratos básicos, no certifica flujos de negocio de P1–P8.

## Validaciones ejecutadas

| Verificación | Resultado final |
|---|---|
| `npm run lint` | Correcto, sin warnings ESLint |
| `npm run typecheck` | Correcto |
| `npm run test` | 26/26 aprobados: 19 unitarios y 7 de componentes |
| `npm run build` | Correcto; artefactos en frontend/dist |
| `npm run test:e2e` con PLAYWRIGHT_CHANNEL=msedge | 6/6 aprobados contra API y motores reales |
| Export OpenAPI + `npm run api:types` | Correcto |
| Ruff check/format del exportador Python | Correcto |
| `git diff --check` | Correcto |

Unitarios: 15 de cliente HTTP (incluidos códigos, cancelación y timeout) y 4 de contrato
readiness/degradación. Componentes: 6 de conexión (carga, salud, degradación, error,
teclado/reintento y offline) y 1 de layout/accesibilidad.

Playwright ejecuta tres escenarios en dos perfiles: escritorio 1440×1000 y móvil
390×664 CSS px (perfil iPhone 13, emulado con Edge Chromium; no es Safari/iOS físico).
Comprueba requests reales, servicios, reintento/recarga, no desbordamiento horizontal,
ruta desconocida, navegación y salto al contenido por teclado, consola sin errores en
arranque saludable, pérdida de red y recuperación. No intercepta ni fabrica respuestas.
La pérdida de conexión se provoca con el modo offline del navegador, sin detener motores.
No requiere seeds ni modifica usuarios/posts existentes.

Historial de correcciones durante la validación:

1. La primera corrida E2E tuvo 2 aprobados y 2 fallidos por el 404 del favicon. Se añadió
   favicon local; la corrida siguiente aprobó los 4 escenarios existentes.
2. La inspección de captura móvil mostró el enlace de salto fuera de lugar en captura
   de página completa tras scroll. Se corrigió su ocultamiento, manteniendo foco por teclado.
3. Al añadir desconexión, 2 escenarios nuevos fallaron: Query pausaba la consulta offline.
   Se corrigió networkMode y se añadió regresión de componente. Resultado final: 6/6 E2E.

El build informa dos avisos de anotaciones PURE en código de Zod; Rollup elimina esos
comentarios y termina correctamente. npm informó deprecación de ESLint 9 y whatwg-encoding
transitivo; no hubo fallo de instalación ni de lint. Se mantiene el conjunto verificado.
La descarga del Chromium empaquetado se canceló por lentitud; se utilizó Edge instalado
mediante Playwright, con el selector de canal documentado. La suite Python completa no se
volvió a ejecutar porque no se modificó código backend; no se reclaman sus cifras históricas.

## Revisión visual

Capturas reales abiertas e inspeccionadas: sin recortes de contenido ni desbordamiento;
tarjetas apiladas en móvil, navegación adaptable y foco accesible. Loading y degradación
se cubren en componentes; estado saludable y error/reconexión en navegador real.
No hay formularios funcionales en esta iteración.

- [Escritorio saludable](screenshots/setup-desktop.png)
- [Móvil saludable](screenshots/setup-mobile.png)
- [Escritorio sin conexión](screenshots/offline-desktop.png)
- [Móvil sin conexión](screenshots/offline-mobile.png)

Reportes completos regenerables en `frontend/playwright-report/` y `frontend/test-results/`,
ignorados en Git. Las cuatro capturas seleccionadas se conservan aquí.

## Cómo probar manualmente

Con Docker Desktop iniciado, desde la raíz:

```powershell
docker compose up -d --build
cd frontend
npm ci
npm run dev
```

Abrir http://127.0.0.1:5173, sin usuario de prueba. Inicio muestra Conectado y tres
servicios disponibles; Volver a comprobar repite el request real. Reducir a ancho móvil
para ver tarjetas apiladas. En DevTools, activar Offline y volver a comprobar: debe
mostrar error y retirar el estado anterior. Restaurar red y repetir: vuelve Conectado.
Abrir `/no-existe`: muestra fallback 404 y enlace al inicio. Tab desde la carga inicial
enfoca el enlace de salto, Enter lleva a main.

Para E2E con Edge ya instalado:

```powershell
$env:PLAYWRIGHT_CHANNEL = "msedge"
npm run test:e2e
Remove-Item Env:PLAYWRIGHT_CHANNEL
```

## Git y siguiente paso

Commit previsto de esta entrega: `feat(frontend): initialize react vite application`.
El hash queda en el historial de la rama y en el informe final; sin merge ni push automático.
Archivos principales: frontend completo, docs/frontend, README, ignore files y exportador.

Iteración 0 completa. P1–P8 de frontend siguen pendientes; P4/P6 además requieren backend.
Próximo paso recomendado: P1 con identidad mínima, publicación real, seguimiento de la
operación y preview de visibilidad. Se requiere autorización antes de comenzar.
