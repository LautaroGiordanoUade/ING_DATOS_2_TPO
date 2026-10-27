# P8 UI — Suspensión y trazabilidad de cuentas

Esta guía conserva la evidencia de la entrega original de P8. La integración posterior
con las demás UI de main se valida en [integración final](integration_p7_p8.md).

Implementado el 27/10/2026 sobre el backend P8 existente. Sin modificaciones de API,
workers, contratos OpenAPI ni lógica de suspensión. P1, P3 y P7 conservan sus regresiones.

## Uso

Con Docker iniciado, abrir http://127.0.0.1:8080 e ingresar con una cuenta moderator/admin.
El acceso **Cuentas** abre `/cuentas`: buscar por UUID y consultar la cuenta. Una cuenta
común ve **Mi cuenta** y puede consultar solamente su propia trazabilidad.

`/cuentas/{userId}` obtiene **una respuesta completa** de GET
`/api/v1/accounts/{userId}/trace`: perfil, relaciones, últimas publicaciones visibles,
estados de publicaciones, conversaciones activas, presencia e historial. No reconstruye
la traza con solicitudes separadas por sección ni consulta perfiles de cada relación.

La página muestra:

- Perfil y estado active/suspended, con identificador y biografía disponible.
- Presencia real y renovación explícita del titular mediante PUT `/accounts/me/presence`.
  No hay heartbeat automático ni controles para simular presencia de otra persona.
- Seguidores, seguidos y bloqueos conservados; dirección y estado de las relaciones.
  Las referencias se muestran de 50 en 50 localmente, usando la respuesta ya obtenida.
- Hasta 100 publicaciones visibles y 100 estados, sin texto de contenido oculto.
  La traza no enriquece contadores P5: esta sección muestra contenido y referencias,
  sin presentar contadores por defecto como una consulta de interacciones reales.
- Hasta 100 conversaciones activas con IDs, fecha y participantes. Es una consulta
  de referencias; no implementa envío de mensajes ni otras pantallas de P6.
- Hasta 100 eventos de cuenta con acción, motivo, responsable, fecha y estado resultante.

Los moderadores pueden **suspender/reactivar otra cuenta** con motivo de 1–1000 caracteres
y confirmación. La UI no ofrece autosuspensión ni acciones administrativas a users; el
backend vuelve a comprobar los permisos. Una traza ajena se bloquea antes de consultarla
para usuarios comunes. Errores 403/404/409/503 y respuestas inválidas no se presentan
como información completa ni dejan habilitados controles sobre datos anteriores.

## Solicitudes y recuperación

Cada confirmación conserva acción, motivo, usuario destino e Idempotency-Key en
sessionStorage, aislados por actor y destino. Perder una respuesta o recargar permite
reenviar **la misma solicitud**, incluso si el estado ya cambió en el servidor. La UI
muestra la acción original conservada y no genera una reactivación accidental.
Descartar esa solicitud requiere una confirmación adicional que explica que pudo aplicarse.
Si sessionStorage está bloqueado, la conservación funciona en memoria durante esa pantalla.

Un 202 lleva a `/cuentas/operaciones/{operationId}` y no se presenta como éxito. La UI consulta
el job cada segundo; pending/running/committing/compensating siguen pendientes. Completed,
compensated y failed detienen el polling. Error de lectura ofrece reconsulta manual; salir
cancela las lecturas. No se exponen controles de inyección ni retry administrativo técnico.

Al completar o compensar se reinicia la navegación de feed y se invalidan las consultas de
cuentas, posts, perfiles, previews, moderación y recomendaciones. Las operaciones recientes
de esta pestaña conservan enlaces, sin almacenar snapshots de trazabilidad ni credenciales.
El historial real sale del servidor en la traza.

La reactivación conserva las ocultaciones P7, no restaura credenciales anteriores y no abre
la presencia por sí misma. El cliente autenticado existente limpia sesión y caché ante 401;
se verificó que una cuenta suspendida sale de su pantalla privada al recibir esa respuesta.
La información abierta en otras pestañas se actualiza al consultar nuevamente o recuperar
foco; no hay notificaciones push ni expulsión instantánea sin una nueva solicitud.

## Verificación

- **139 pruebas frontend aprobadas**: 61 unitarias y 78 de componentes; 25 nuevas P8.
- Lint, TypeScript y build multietapa de Docker aprobados.
- **30 E2E aprobados** contra Docker/Nginx, API y los tres motores reales: seis nuevos P8
  (tres escenarios por escritorio/móvil) y 24 regresiones base/P1/P3/P7.

Escenarios P8:

1. Cuenta con seguidor real, recomendación de segundo grado, conversación y dos posts;
   uno oculto por P7. El titular renueva presencia. Admin consulta por UUID, suspende por UI,
   espera confirmación y recarga el enlace de operación. Se comprueban retiro del feed,
   exclusión de sugerencias, 401 del bearer previo, salida/limpieza de sesión del titular,
   ausencia de presencia y trazabilidad de la cuenta suspendida. Reactivar recupera solo
   el post permitido y la sugerencia; el oculto P7 continúa oculto. El bearer anterior sigue
   revocado. Un nuevo login funciona y solo un nuevo heartbeat abre la presencia.
2. Privacidad: tercero recibe 403, user no puede suspender, admin no puede autosuspenderse;
   UI de consulta propia sin comandos y vista vacía real.
3. Falla de desarrollo inyectada por API, compensación real y pantalla cancelada sin falso éxito.

La preparación crea cuentas aleatorias `qa_p8_*`, promueve únicamente la cuenta QA admin
recién creada y agrega una conversación QA en Mongo porque no existe endpoint de creación.
Requiere Docker CLI y APP_ENV=development. El teardown borra solo esos UUID, comprueba que no
existan jobs activos y limpia referencias de MongoDB, Neo4j y Redis. No resetea fixtures fijos
ni cuentas humanas. Quedaron cero usuarios `qa_p8_*` después de esta validación.

Las regresiones P7 crean sus propios reportes QA; se retiraron los seis reportes nuevos de
esa corrida, conservando el reporte de Lautaro que existía antes y guardando respaldo local
en `logs/` (ignorado por Git). Se verificó además, solo lectura con admin, la traza de Lautaro:
cuenta activa, 1000 seguidores, 46 publicaciones visibles y 46 estados de publicación.

La primera compilación con los E2E nuevos detectó una opción baseURL potencialmente undefined
bajo TypeScript estricto; se agregó un valor por defecto. Después compiló Docker y los 30 E2E
pasaron sin retries. Una revisión adicional agregó una regresión para recuperar una solicitud
cuando el servidor ya cambió el estado; la suite frontend final quedó en 139 aprobados.
No se repitió Python: no se modificó backend. Se mantienen los avisos PURE de Zod ya documentados.

```powershell
# Desde la raíz
docker compose up -d --build frontend
# Desde frontend/
npm run lint
npm run typecheck
npm run test
$env:PLAYWRIGHT_BASE_URL = "http://127.0.0.1:8080"
$env:PLAYWRIGHT_CHANNEL = "msedge"
npx playwright test
Remove-Item Env:PLAYWRIGHT_BASE_URL
Remove-Item Env:PLAYWRIGHT_CHANNEL
```

## Evidencia y límites

Capturas reales de cuenta activa, suspendida, reactivada, consulta propia vacía y compensación
en `screenshots/p8/`, escritorio/móvil. Se inspeccionaron formularios, foco, tarjetas, estado,
referencias largas y navegación móvil con cinco accesos. El E2E comprueba que no haya
desbordamiento horizontal ni errores de consola/pageerror en el circuito principal.

- [Cuenta activa](screenshots/p8/p8-active-desktop.png)
- [Cuenta suspendida en móvil](screenshots/p8/p8-suspended-mobile.png)
- [Cuenta reactivada](screenshots/p8/p8-reactivated-desktop.png)
- [Consulta propia vacía](screenshots/p8/p8-own-empty-mobile.png)
- [Compensación](screenshots/p8/p8-compensated-desktop.png)

La consulta respeta límites/privacidad del backend; no ofrece búsqueda por nombre ni inventa
datos ausentes. Las relaciones incluyen solicitudes pendientes si el servidor las devuelve.
La presencia mostrada corresponde a la última lectura y puede renovarse/actualizarse; no se
interpreta una conversación conservada como presencia abierta. Las garantías de recuperación
y restauración siguen siendo las de [P8 backend](../problems/problem_08.md).
P8 UI completo; no se comienza otro problema automáticamente.
# Recuperación de operaciones integrada

La pantalla de operación ofrece **Reintentar recuperación** para trabajos fallidos,
usando su identificador existente. Si la compensación ya terminó, se consulta la cuenta
y se confirma una nueva solicitud: el backend exige una nueva clave de idempotencia.
Los resultados originales de esta guía se complementan con [integration_p7_p8.md](integration_p7_p8.md).
