# Plan del frontend — estado después de P1, P3, P4 y P5

Inspección actualizada sobre la rama de trabajo. No se encontró un enunciado original separado
(PDF/DOCX). El inventario se basa en `TODO.md`, `docs/problems/problem_01.md` a `problem_08.md`,
guías, casos de uso, adaptadores y OpenAPI generado directamente desde `app.main:app`. Si se aporta
el enunciado original habrá que contrastarlo antes de ampliar el alcance.

## Inventario real

Los ocho números son los ocho casos de uso existentes. Autenticación es infraestructura
compartida, no un noveno problema. El estado del backend distingue código/documentación
de verificación ejecutada durante esta entrega. P1, P3, P4 y P5 UI están implementados; los
restantes módulos de UI siguen pendientes.

| Problema | Funcionalidad | UI mínima necesaria | Backend en main | Frontend |
|---|---|---|---|---|
| 1 — Publicación y distribución recuperable | Publicar con intereses y distribuir por lotes | Crear publicación, estado de operación y preview de IDs visibles | Implementado; worker P1 | Completado y validado — ver problem_1.md |
| 2 — Seguir/dejar de seguir | Follow público, solicitud privada, aprobación y contadores | Perfil por UUID, seguir/cancelar/dejar de seguir y solicitudes recibidas | Implementado; worker compartido P2/P7/P8 | Pendiente |
| 3 — Feed personalizado | Hasta 20 posts, ranking por bloques y cursor opaco | Inicio con tarjetas, siguiente página y refrescar | Implementado; navegación de 15 min | Completado y validado — ver problem_3.md |
| 4 — Amigos en común y sugerencias | Segundo grado y amigos en común, hasta 10 sugerencias | Sugerencias y consulta de amigos en común en `/recomendaciones` | Implementado; Neo4j + filtro activo MongoDB | Completado y validado (`RecommendationsPage`, `UserCard`) |
| 5 — Reacciones y comentarios | Reacción única, cambio/baja, comentarios y contadores | Controles en tarjeta y formulario de comentario | Implementado con recuperación durable | Completado y validado (`PostInteractions` en `PostCard`) |
| 6 — Mensajería grupal | Historial, entrega, unread y lectura por participante | Conversación grupal, historial y envío, solo cuando existan contratos reales | Pendiente; envío lanza 501, faltan lecturas públicas completas | Bloqueado por backend incompleto |
| 7 — Moderación | Reportar, decidir, consultar y revertir | Reportar desde post; lista/detalle de reportes, decisión/reversión e historial | Implementado; bearer y roles user/moderator/admin | Pendiente |
| 8 — Suspensión y trazabilidad | Suspender/reactivar, revocar credenciales y consultar traza privada | Cuenta, motivo de suspensión/reactivación, historial y traza | Implementado; efectos MongoDB/Neo4j/Redis | Pendiente |

## Orden y dependencias

0. Base técnica, layout y conexión real a readiness. Completo; ver iteration_0.md.
1. P1 con la infraestructura de identidad necesaria: registro/login/logout, sesión,
   lectura del perfil del titular y manejo central de 401. Publicar y seguir operación.
   El backend usa bearer HMAC propio (no asumir JWT estándar), expira en 3600 segundos
   por defecto y verifica auth_version/estado actual. No hay refresh ni /users/me ni logout
   del servidor. En P1 se agregó GET /users/me para validar el bearer y obtener el titular.
   Preferir memoria/sessionStorage para sesión de pestaña; limpiar token y caché al salir.
   POST /posts ahora exige bearer y autor coincidente en servidor. El alias educativo
   /problems/1/publish conserva su contrato público para scripts, como límite documentado.
   Este paso está completo: 69 tests frontend, 14 E2E reales y 32 regresiones Python focalizadas.
2. P2: depende de identidad/P1 para probar entrega y retiro. Solicitudes privadas incluidas.
3. P3: completo por pedido explícito de priorizar el feed antes de la UI P2. Reutiliza
   el backend P2 ya implementado y los seguidores sembrados; no requiere construir su UI.
   Inicio muestra seguidos y /mis-publicaciones conserva el contenido propio. Ver problem_3.md.
4. P5: implementado en backend (`InteractWithPostUseCase` con recuperación durable) y en
   frontend (`features/interactions/` integrado en `PostCard`), refrescando los contadores del
   servidor después de cada mutación.
5. P7: depende de identidad por rol y posts/P3/P5 para comprobar hide/revert y contadores.
6. P8: depende de identidad/P2/P3/P7 para verificar suspensión sin revivir contenido moderado.
7. P4: implementado en backend (`SocialRecommendationsUseCase` y `Neo4jSocialGraphRepository`)
   y en frontend (`features/recommendations/` con ruta protegida `/recomendaciones`).
8. P6: después de completar backend de conversación/historial/participantes/unread.

Cada paso requiere autorización del usuario; no se avanza automáticamente. P6
requiere trabajo backend futuro expresamente acotado antes de declarar una UI completa.

## Contratos e implementación por problema

Todos los paths siguientes llevan `/api/v1` salvo `/health*`. Consultar schemas exactos en
`frontend/openapi.json` y tipos generados en `src/services/api/schema.d.ts`. El snapshot
incluye rutas todavía pendientes: OpenAPI no prueba comportamiento.

### P1 — publicación

- Entidades: User, Post, PublicationJob/Operation; MongoDB contenido/jobs, Neo4j audiencia,
  Redis feed/visibilidad. Requiere `publication-worker`.
- Endpoints: POST `/posts` con bearer → 202 con operation_id/post_id/status;
  GET `/problems/operations/{id}`, `/posts/{id}`, `/posts/by-user/{id}` y
  `/problems/1/feed-preview/{user_id}`. Preview son IDs, no sustituye P3.
- Identidad: POST `/users`, `/users/login`, GET `/users/me`; registro siempre rol user.
- OperationDetailResponse incluye post_id nullable, tomado del job para P1;
  la UI no deduce la publicación desde parámetros de URL. La ruta normal /posts valida
  autor en backend; alias educativo y consultas públicas conservan los límites previos.
- Formularios: registro (username 3–50, nombre 1–150, password 8–128, email y cuenta
  public/private); login (username 3–50, password 1–128); post (texto 1–10000, al menos
  un interés requerido por caso de uso aunque OpenAPI permita lista vacía; solo public).
  Media son strings existentes: no inventar endpoint de upload.
- Componentes: AppLayout, FormField/ErrorMessage, estado de operación, PostCard cuando
  exista contenido real. Clave idempotente estable por envío; no generar otra al reintentar
  el mismo pedido; 409 con distinto contenido debe explicarse.
- Estados: enviando, pending/running/committing, completed, compensating/compensated,
  failed; detener polling terminal, cancelar al salir, permitir consulta posterior.
  202 no significa publicado. Manejar 401/404/409/422/503 y errores de red sin falso éxito.
- Tests: schemas/cliente/polling; formularios/errores/interacción; E2E con usuarios aislados,
  API/worker/motores reales, publicar y esperar visibilidad, replay y fallo compensado.

### P2 — seguir/dejar de seguir

- Entidades: User, FOLLOWS, FollowJob; MongoDB jobs, Neo4j relación, Redis derivados.
- Endpoints: POST/DELETE `/social/follows`, POST `/social/follows/approve`, GET
  `/social/requests`, `/social/relations/{followed_id}`, `/social/counts/{user_id}`,
  `/social/operations/{id}` y perfil `/users/{id}`. Jobs 202; bearer, actor propio;
  aprobación exclusiva del titular. No exponer retry técnico en navegación normal.
- UI: perfil por UUID porque no existe buscador de cuentas; solicitudes recibidas;
  botones reutilizables y confirmación de unfollow. UUID válido, impedir auto-follow,
  clave de idempotencia 1–200. Estados none/pending/accepted/processing y jobs terminales.
- Errores: usuario inexistente/suspendido, bloqueos, 401/403/404/409/422/503, lista vacía.
- Tests: validación/derivación de estado; botones/permisos/estados; E2E público/privado,
  aprobación/replay/unfollow con contadores y feed leídos del backend.

### P3 — feed personalizado

- Entidades: Post, FeedResponse, navegación; Redis candidatos/bloques, MongoDB contenido,
  Neo4j elegibilidad. GET `/feeds/{user_id}?cursor=...`, bearer solo feed propio.
- UI: Inicio, PostCard, EmptyState, paginación y refrescar. Cursor es string opaco o null;
  no interpretar ni fabricar. Hasta 20 elementos; una página vacía con next_cursor NO
  significa fin. No duplicar IDs al anexar páginas; refrescar reinicia navegación.
- Estados: carga inicial, página adicional, vacío, error recuperable; 410 vencido →
  ofrecer refrescar; 401/403/422/503. Orden lo determina servidor; no rerankear en cliente.
- Tests: cursores/merge sin duplicados; loading/vacío/error/continuación; E2E 20/20/5,
  refresco y exclusiones P2/P7/P8, con fixtures propios y sin interceptar API.

### P4 — amigos en común y sugerencias

- Entidades: User.interests en MongoDB, FOLLOWS/BLOCKS en Neo4j y validación de estado activo.
- «Mis intereses» edita preferencias con PUT `/users/me/interests`, refresca sugerencias y
  muestra etiquetas compartidas. Usuarios antiguos sin el campo conservan sus datos.
- GET `/problems/4/recommendations/{user_id}` devuelve hasta 10 UUIDs por segundo grado e intereses;
  GET `/problems/4/mutual-friends?user_id=...&other_user_id=...` devuelve UUIDs reales de amigos
  en común ordenados por identificador.
- UI implementada en `/recomendaciones` (`RecommendationsPage` y `UserCard`): muestra sugerencias
  (máximo 10), carga perfiles mediante `GET /users/{id}`, permite seleccionar cualquier tarjeta
  sugerida o ingresar un UUID validado con `mutualFriendsQuerySchema` para consultar amigos en común.
- Tests implementados: unitarios e integración de backend (`test_problem_04_recommendations.py`),
  smoke HTTP (`scripts/validar_problema4.py`) y pruebas de componente en `RecommendationsPage.test.tsx`.

### P5 — reacciones y comentarios

- Entidades: Reaction, Comment, contadores y notificación; MongoDB/Redis.
- POST/DELETE `/problems/5/reaction`, POST `/problems/5/comment` con Idempotency-Key;
  GET `/posts/{id}` o feed para contadores. Los alias `/interactions/*` son 204:
  usar rutas del problema para consultar operation_id. GET autenticado
  `/interactions/reactions/{post_id}/me` restaura reacción propia y GET autenticado
  `/posts/{post_id}/comments` lista autor/texto/fecha con cursor ligado al post.
  `CommentList` muestra diez comentarios por página, carga anteriores y reinicia la lista
  tras enviar. Un 404 retira contenido cacheado; otras fallas permiten reintentar.
- Formulario: comentario 1–2000 (`commentPayloadSchema`), kind 1–30 (`reactionPayloadSchema`), UUIDs.
  Controles de alta/cambio/baja en `PostInteractions`; refresca contadores del servidor con
  `refreshPostCounters` después de cada mutación.
- Estados: enviando, resultado de operación, 404 contenido retirado, 409 concurrencia,
  422 y 503; conserva texto e `Idempotency-Key` ante error para reintento seguro.
- Tests: regresiones P5, integración real de consistencia y `test_comment_pages.py`;
  componentes `PostInteractions.test.tsx` y `CommentList.test.tsx`; E2E `interactions.spec.ts`
  y `comments.spec.ts`, además de los scripts de validación P5.

### P6 — mensajería grupal

- Entidades: Conversation, Message, read_by, presencia y unread; MongoDB/Redis.
- POST `/problems/6/message` y `/messages` existen pero envío real pendiente (501).
  No hay API suficiente de listado/historial/lectura para construir todo el flujo.
- UI futura mínima: conversación y formulario (UUIDs, texto 1–10000); miembros/autorización
  deben validarse en backend. Presencia P8 implementada no equivale a resolver P6.
- Estados previstos: historial cargando/vacío/error, envío pendiente/error, lectura por participante.
- Tests después de completar contratos: validaciones/permisos, render/interacción y E2E
  entre participantes, persistencia antes de entrega, unread y lectura. Sin mensajes simulados.

### P7 — moderación

- Entidades: ModerationReport, ModerationJob, historial, Post; MongoDB/Redis y worker compartido.
- POST/GET `/moderation/reports`, GET `/moderation/reports/{id}`, POST
  `/moderation/reports/{id}/decision` y `/revert`; GET `/moderation/operations/{id}`,
  `/moderation/history/{post_id}`, `/moderation/posts/{post_id}/state`.
- Reporte para usuario autenticado; lista/decisión/reversión para moderator/admin según
  dependencias del servidor. Registrar no concede roles; seed de desarrollo existente.
- Formularios: reason spam/abuse/hate/violence/other, description opcional hasta 2000;
  decisión hide/reject y motivo 1–1000; reversión motivo 1–1000. ConfirmDialog para acciones.
- UI: modal de reporte, bandeja con filtro de estado (la API limita a 100 reportes,
  sin paginación pública), detalle/historial y job. No inventar limit/offset.
  Estados pendientes/resueltos/revertidos, lista vacía, 401/403/404/409/422/503.
- Integrar invalidación de post/feed/contadores tras job completado; sin reintentos/compensaciones
  administrativos en UI. Tests de permisos, formularios/estados y E2E reporte→hide/reject→revert
  comprobando retiro/restauración y contadores reales. Dependencias P1/P3/P5/identidad.

### P8 — suspensión y trazabilidad

- Entidades: User, AccountJob/history, relaciones, posts, conversaciones, presencia;
  MongoDB/Neo4j/Redis, worker compartido.
- POST `/accounts/{user_id}/suspend` y `/reactivate` → 202; GET
  `/accounts/operations/{id}`, `/{user_id}/history`, `/{user_id}/trace`,
  `/{user_id}/presence`; PUT `/accounts/me/presence` si el flujo requiere presencia.
- Suspend/reactivate: moderator/admin; traza solo titular o rol autorizado. Motivo 1–1000;
  UUID e idempotencia. UI cuenta/detalle de traza, confirmación e historial, estados de job.
- 401 por credencial revocada limpia sesión/caché; reactivar requiere nuevo login,
  sin restaurar automáticamente heartbeat ni posts ocultos por P7. Manejar 403/404/409/422/503.
- Tests: permisos/validaciones/limpieza sesión; confirmaciones y traza vacía/error;
  E2E suspensión→exclusión feed/revocación→reactivación/nuevo login, preservando P7.

## Arquitectura y base de esta iteración

React + TypeScript estricto + Vite; React Router; TanStack Query; Tailwind CSS.
React Hook Form + Zod validan registro, login y publicación de P1.
Vitest + Testing Library y Playwright desde la base. Sin Redux, SSR ni carpetas vacías.

`app/` contiene providers/router/layout; `features/system/` comprueba conexión real;
`features/auth/` contiene identidad y sesión; `features/posts/` publicación, operaciones,
contenido propio y preview de distribución P1; `features/feed/` contiene API, paginación
y tarjetas con autor para P3; `features/recommendations/` contiene sugerencias de segundo
grado y consulta de amigos en común para P4; `features/interactions/` contiene reacciones
y comentarios para P5;
`components/common/` mensajes reutilizables; `services/http/` cliente, errores y timeout;
`services/api/` tipos OpenAPI; `styles/` diseño responsive; `tests/e2e/` arranque real.
Cada funcionalidad futura tendrá su carpeta cuando se implemente.

Layout claro con sidebar escritorio, navegación compacta móvil, tarjetas blancas, tipografía
del sistema, foco visible y enlaces accesibles. P1 agrega registro/login, publicaciones propias,
composer y operación a la bienvenida/fallback 404. P3 convierte Inicio en feed y mueve
las publicaciones propias a /mis-publicaciones. P4 agrega /recomendaciones en el menú lateral.
La bienvenida consume GET `/health/ready`, muestra servicios reales y permite reintentar.
Readiness 503 se muestra como degradado. Las capturas de iteración 0 quedan como evidencia histórica.

`VITE_API_BASE_URL=/backend` usa proxy local de Vite hacia `http://127.0.0.1:8000`.
`API_PROXY_TARGET` configura el destino solo del proceso Vite, sin exponer credenciales.
Nunca secretos en VITE_. Producción requiere proxy equivalente o CORS real configurado
externamente si se usa otra origin; no modificar backend solo para el desarrollo.

## Criterios y verificaciones por iteración

- `npm run lint`, `typecheck`, `test`, `build`, `test:e2e`.
- Tests unitarios del cliente/validaciones y componentes con loading/error/vacío/permisos.
- E2E de cada problema contra API, workers y motores reales, datos aislados y sin mocks.
- Capturas desktop/móvil, navegación por teclado, ausencia de errores de consola y requests.
- Documentar comandos, fixtures, resultados y límites en `docs/frontend/problem_N.md`;
  actualizar esta tabla solo después de validar completamente.
- Commits pequeños en la misma rama; sin merge ni PR nueva por problema.

Infraestructura general de datos (50000+), DER, informe y contrafactuales son entregables
del TP; no implican nuevas pantallas. No se expondrán controles técnicos de retry/failure injection.

## Evidencia por iteración

Preparación: `iteration_0.md`. P1: `problem_1.md`, 69 tests frontend (38 unitarios y
31 componentes), 14 E2E sobre build/preview y 32 pruebas Python focalizadas. Capturas
desktop/móvil en `screenshots/p1/`. Los escenarios de P1 usan API, workers y motores reales.
P3: `problem_3.md`, 81 tests frontend (41 unitarios y 40 componentes), 18 E2E sobre
build/preview y comprobación real de lautaro1/lautaro1000 viendo el post de Lautaro.
Sin cambios de backend. Capturas en `screenshots/p3/`.
P4: `docs/problems/problem_04.md`, módulo `features/recommendations/` con 5 tests de componente
en Vitest, 8 tests unitarios Python, 4 tests de integración real Neo4j/MongoDB y script HTTP
`scripts/validar_problema4.py`.
P5: `docs/problems/problem_05.md` y `docs/problem_05_consistency.md`, módulo `features/interactions/`
con 7 tests de componente en Vitest, 14 tests unitarios Python en `test_problem_05_regressions.py`,
11 tests de integración real en `test_problem_05_consistency.py` y scripts `scripts/validar_problema5.py`
y `scripts/validar_problema5_fallas.py`.
