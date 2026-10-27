# P7 UI — Reportes y moderación

Esta guía conserva la evidencia de la entrega original de P7. Para el estado combinado
con las UI P2/P4/P5/P6 de main y P8, ver [integración final](integration_p7_p8.md).

Implementado sobre el backend P7 existente, sin cambios de API ni de workers.
Se priorizó P7 por pedido del usuario; P2/P5 UI continúan pendientes. P5 se usa solo
como preparación API de las pruebas de contadores. La aplicación sigue en Docker/Nginx,
en http://127.0.0.1:8080.

## Flujo y permisos

- Las tarjetas de otras cuentas ofrecen **Reportar publicación**. `/reportar/{postId}`
  carga el contenido real, permite elegir spam/abuse/hate/violence/other y descripción
  opcional de hasta 2000 caracteres. La identidad se obtiene del bearer, sin reporter_id
  editable. El reporte no oculta contenido por sí mismo.
- El alta lleva a `/reportes/{reportId}`. El reportante puede guardar ese enlace y consultar
  estado y motivo de resolución. No obtiene historial privado ni acciones de moderación.
- **Moderación** y `/moderacion` requieren moderator/admin. La bandeja filtra por estado,
  permite actualizar y muestra hasta 100 reportes, según el límite real de la API.
- El detalle muestra estado, motivo, descripción, contenido todavía público e historial
  autorizado. Permite ocultar o rechazar un pendiente; restaurar solo una ocultación aprobada.
  Requiere motivo de 1–1000 caracteres y confirmación explícita antes de enviar.
- `/moderacion/operaciones/{operationId}` conserva un enlace durable. Consulta cada segundo
  hasta completed/compensated/failed; committing sigue siendo transitorio. Un 202 no confirma
  una decisión. Error de red detiene polling y ofrece consulta manual. Salir cancela lecturas.
- Al confirmar o compensar se reinicia la navegación de feed e invalidan posts, preview,
  reportes e historial. Las mutaciones no aplican cambios optimistas de visibilidad/contadores.
- La sesión sigue verificándose mediante `/users/me`; el servidor decide permisos en cada
  request. Ocultar enlaces no sustituye la autorización. No hay controles de inyección de
  fallas, retry técnico ni asignación de roles en la UI.

Los formularios usan RHF/Zod, labels asociados, errores accesibles, fieldsets deshabilitados
al enviar y confirmación revisable. El reporte usa una página dedicada que admite enlaces
directos, en lugar de superponer un modal al feed. Se mantiene el diseño responsive existente.

## Contratos y compatibilidad

Se consumen POST/GET `/moderation/reports`, GET `/reports/{id}`, POST
`/reports/{id}/decision`, POST `/reports/{id}/revert`, GET `/operations/{id}` y
GET `/history/{post_id}`, todos bajo `/api/v1/moderation`. Se reutiliza GET `/posts/{id}`.
Zod valida respuestas; las operaciones omiten snapshots internos en el modelo de UI.
El servidor controla unicidad e idempotencia; no se inventan claves ni IDs de operaciones.

Los fixtures P7 incluyen UUID hexadecimales sin variante/version RFC. Python UUID los admite;
`z.uuid()` los rechazaba y bloqueaba toda la bandeja. Los contratos de moderación y las lecturas
compartidas de usuario/post usan `z.guid()` para mantener el formato UUID sin imponer una
restricción ajena a la API. Una regresión prueba los IDs históricos y rechaza IDs malformados.

## Pruebas ejecutadas

- Lint, TypeScript y build de Docker aprobados.
- **114 pruebas frontend**: 55 unitarias y 59 de componentes; 33 nuevas en P7.
- **24 E2E aprobados** contra Docker/Nginx, API, worker y motores reales. Seis nuevos P7
  (tres escenarios en escritorio/móvil) y 18 regresiones P1/P3/base.

Los escenarios P7 verifican:

1. Reporte desde feed con seguidor real; ocultar, confirmar operación, recargar su URL,
   comprobar 404 público, feed vacío y contadores públicos en cero; restaurar, consultar
   historial y volver al feed del lector con una reacción y un comentario preservados.
2. Admin rechaza sin retirar el post; filtro de rechazados; duplicado 409; usuario común
   sin bandeja ni permiso de decisión y tercero sin acceso al reporte.
3. Falla inyectada por API de desarrollo, compensación real y pantalla sin falso éxito.

Las pruebas crean únicamente cuentas/posts QA nuevos. Como el registro siempre crea users,
la preparación asigna moderator/admin directamente en Mongo solo al UUID y username aleatorios
recién creados, con guard APP_ENV=development. Necesita Docker CLI. No cambia cuentas previas,
roles de Lautaro ni sus publicaciones/seguimientos. No se usa el seed fijo P7 ni sus resets.
No hay mocks/interceptores E2E; los mocks se limitan a unit/componentes.

La primera ejecución de Vitest detectó una espera de test que observaba loading en lugar
de pending; se corrigió la espera. La preparación E2E inicialmente importaba un módulo de
HTTP dependiente de Vite: se separaron contratos puros y errores. La siguiente corrida dio
20/24 por una expectativa de login que ignoraba el retorno a rutas protegidas; esa inspección
también reveló los UUID históricos rechazados en bandeja. Se corrigieron ambas causas;
la corrida final fue 24/24, sin retries para ocultar fallos.

Comandos desde `frontend/`, con Docker iniciado:

```powershell
npm run lint
npm run typecheck
npm run test
# Desde la raíz: docker compose up -d --build frontend
$env:PLAYWRIGHT_BASE_URL = "http://127.0.0.1:8080"
$env:PLAYWRIGHT_CHANNEL = "msedge"
npx playwright test
Remove-Item Env:PLAYWRIGHT_BASE_URL
Remove-Item Env:PLAYWRIGHT_CHANNEL
```

No se repitió la suite Python: no se modificó backend. El build conserva los avisos PURE
de Zod documentados previamente.

## Evidencia visual y límites

Capturas reales en `screenshots/p7/`: reporte, bandeja, ocultación, restauración y compensación,
en escritorio/móvil. Se revisaron formulario, foco visible, jerarquía, historial, referencias
largas y navegación con cuatro accesos en móvil. El E2E comprueba ausencia de desbordamiento
en el detalle moderado. Los errores 404 al consultar un post oculto son esperados y se manejan;
se comprueba que no haya otros errores de consola ni pageerror en el circuito principal.

- [Reporte móvil](screenshots/p7/p7-report-mobile.png)
- [Bandeja escritorio](screenshots/p7/p7-queue-desktop.png)
- [Ocultación móvil](screenshots/p7/p7-hidden-mobile.png)
- [Restauración escritorio](screenshots/p7/p7-restored-desktop.png)
- [Compensación móvil](screenshots/p7/p7-compensated-mobile.png)

El backend no ofrece listado de reportes propios ni contenido oculto para revisión: el titular
guarda su enlace individual y el moderador ve metadata/historial cuando el post ya no es público.
Un alta cuya respuesta se pierde puede devolver 409 al repetir, sin recuperar automáticamente
el ID del reporte; la UI conserva el texto y explica el conflicto. No fabrica comprobantes.
La bandeja no pagina más allá de los 100 registros que devuelve el backend. Los reportes
pendientes se consultan cada cinco segundos; no hay notificaciones push. Las garantías de
recuperación, concurrencia y restauración son las del backend P7.

Para pruebas manuales con rol privilegiado, usar una cuenta de moderación existente o el
seed de desarrollo descrito en [guía P7](../problem_7_moderation_test_guide.md). El registro
normal no eleva privilegios. P7 UI completo; no se inicia otro problema automáticamente.
