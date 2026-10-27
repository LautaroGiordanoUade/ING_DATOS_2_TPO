# P7 — interfaz de reportes y moderación

## Navegación y permisos

- En cada publicación, **Reportar publicación** abre un formulario con motivo obligatorio
  (spam, abuso, odio, violencia u otro) y descripción opcional de hasta 2000 caracteres.
- Un reporte recibido ofrece **Ver mi reporte** en `/reportes/:reportId`. El reportante puede
  consultar su estado; sólo su titular o un moderador/admin tiene acceso a ese reporte.
- Moderadores/admin ven **Moderación** en el menú y la bandeja `/moderacion`. Usuarios comunes
  no acceden ni mediante URL directa. El servidor revalida identidad/rol en cada endpoint.
- La bandeja permite filtrar por pendiente, aceptado, rechazado y revertido. Devuelve hasta
  100 reportes por consulta; la interfaz no inventa paginación ni muestra ese lote como total global.
- El detalle incluye motivo, descripción, reportante y fecha. Sólo moderadores/admin consultan
  el contenido publicado, incluso oculto, y el historial de decisiones.

## Decisiones

**Ocultar publicación**, **Rechazar reporte** y **Revertir ocultamiento** abren una confirmación
en el detalle, con motivo obligatorio de 1–1000 caracteres. Ocultar resuelve todos los reportes
pendientes asociados; rechazar afecta sólo al elegido; revertir actúa sobre el mismo grupo del hide.
Los reportes rechazados previamente y los reportes nuevos posteriores a la restauración se conservan.

La interfaz espera el estado de la operación del worker; 202 no confirma efectos terminados.
Bloquea controles mientras se procesa o se desconoce el resultado y actualiza reporte, contenido,
historial, feed, publicaciones y comentarios cuando llega a un estado terminal. El historial
muestra la cantidad real de reportes afectados cuando ese dato existe; no inventa cantidades
para eventos anteriores sin ese metadato.

Una compensación informa que se restauró el estado anterior y ofrece **Reintentar decisión**.
Una recuperación fallida ofrece **Reintentar recuperación**. Ambos usan el trabajo existente;
no generan una decisión diferente con otro motivo. Una reversión conserva las demás restricciones
del contenido: volver al estado anterior de moderación no elimina una suspensión P8.

## Lectura protegida agregada

GET `/api/v1/moderation/posts/{post_id}/content?report_id=UUID` requiere moderator/admin y devuelve
sólo contenido publicado (UUID, autor, texto, medios, intereses, fecha, visibilidad y moderación),
dueño de la decisión, operación activa y operación relacionada con el reporte consultado.
Valida que reporte y publicación correspondan. No devuelve credenciales, feeds ni snapshots.
No modifica las lecturas públicas: una publicación oculta sigue devolviendo 404 allí.

La referencia a la operación permite retomar una decisión después de recargar incluso sin datos
locales del navegador, incluidas decisiones compensadas. API y workers existentes conservan
la persistencia, exclusión, recuperación y límites de P7. No se agregan motores ni contenedores.

## Reintentos y caché

Cada decisión conserva post/reporte, acción, motivo y operación en sessionStorage por moderador.
Un envío incierto se confirma con el mismo payload. La idempotencia de P7 sigue en el servidor,
con UUID determinista por reporte/acción. Un 409 refresca el estado antes de permitir otra decisión.
Un reporte duplicado se distingue de una publicación ya oculta: ambos pueden responder 409,
pero solamente el error específico de duplicado informa que ya existe un reporte del usuario.

El recibo de reporte exitoso guarda únicamente su UUID. Si la respuesta de creación se pierde,
el reintento no duplica el reporte, aunque un duplicado sin recibo conocido no ofrece un enlace
inventado. Los motivos de decisiones se guardan para reintentar; no se guardan bearer, contraseña
ni texto del contenido protegido. Se conservan trabajos abiertos y hasta 20 decisiones terminales.

Consultas de caché separadas por usuario y rol; un 403 retira también contenido protegido ya cacheado
y vuelve a validar la sesión. Reportes y contenido se actualizan periódicamente con pestaña visible.
La interfaz no se considera una barrera de autorización: las verificaciones efectivas son del backend.

Los identificadores conservan compatibilidad con los GUID históricos aceptados por el backend,
incluidos los que no declaran versión RFC. No se regeneran UUID ni se migran datos para abrir la bandeja.

## Pruebas

Backend: `tests/integration/test_moderation_content.py` cubre permisos, lectura oculta, origen de
operación/reversión, revocación de rol con el mismo token y rechazo de contenido inexistente o
no publicado. Frontend: pruebas de formulario, bandeja, detalle, caché/permisos y decisión pendiente.
`frontend/tests/e2e/moderation.spec.ts` usa cuentas QA nuevas, API, worker y motores reales en
escritorio/móvil. Los roles de esas cuentas se preparan sólo para la prueba; registro no concede roles.
Incluye reporte propio, varios reportes, hide/revert, contadores/comentarios preservados, rechazo,
duplicado y pérdida de rol administrativo. Los datos previos y volúmenes se conservan.

Validación local del 27/10/2026: 319 pruebas de backend, Ruff y mypy (202 archivos),
142 pruebas de frontend, ESLint, TypeScript y build de producción correctos.
La regresión completa de navegador terminó con 34 pruebas correctas entre escritorio y móvil,
incluidas las cuatro ejecuciones de P7 y los recorridos existentes de P1–P6.
