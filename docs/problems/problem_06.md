# Problema 06 — Mensaje grupal

## Contrato

MongoDB guarda grupos, mensajes y lectura; Redis mantiene presencia, avisos y contadores
derivados. Todos los endpoints requieren bearer de un usuario activo. El remitente se
obtiene del token; solamente los participantes pueden consultar o escribir en el grupo.
Los grupos tienen nombre y entre 2 y 20 integrantes, definidos al crearlos.

Base `/api/v1/messages`:

| Método y ruta | Función |
|---|---|
| GET `/participants?q=nombre` | Buscar hasta 20 usuarios activos por prefijo; sin email ni contraseña |
| POST `/conversations` | Crear grupo; `{name, participant_ids}`, Idempotency-Key obligatoria |
| GET `/conversations?limit=20&before=UUID` | Grupos propios y unread; paginación por UUID |
| GET `/conversations/{id}` | Detalle y participantes activos |
| GET `/conversations/{id}/messages?limit=30&before=secuencia` | Historial descendente y `next_before` |
| POST `/conversations/{id}/messages` | `{text}`, Idempotency-Key obligatoria, respuesta 202 |
| PUT `/conversations/{id}/read` | `{message_id}`, avanzar lectura hasta un mensaje real del grupo |
| GET `/{message_id}/delivery` | Estado durable del envío; acceso sólo a participantes |

El alias `/api/v1/problems/6/message` usa el mismo caso de uso. Su campo sender_id debe
coincidir con el bearer. Ya no usa datos de demostración ni devuelve 501.
Texto de 1–4000 caracteres, nombre de grupo de 1–80 y clave de 1–128. Respuestas:
401 sin sesión activa, 404 conversación/mensaje no accesible, 409 clave con otro contenido
o conversación ocupada, 422 validación, 503 motor necesario no disponible.

## Persistencia, orden y recuperación

1. Validar usuario y membresía bajo bloqueo de conversación compartido API/worker.
2. Reservar secuencia MongoDB y crear mensaje con UUID, clave y `delivery_status=pending`.
   La inserción guarda historial y outbox en un mismo documento, sin transacción multi-documento.
3. Calcular unread desde mensajes persistidos y `read_through` de cada participante;
   escribir valores absolutos en Redis. Los mensajes propios no cuentan.
4. Publicar avisos para destinatarios activos y con presencia. Lua consulta atómicamente
   el gate Redis de P8 y registra la mayor secuencia notificada por destinatario/grupo.
5. Guardar `completed_steps` y `delivery_status=completed` en MongoDB.

El UUID del mensaje identifica también su trabajo de distribución. Los pasos visibles
son `mongo_persist`, `redis_unread`, `redis_notify:UUID` y `redis_distribution`.
El worker existente `app.workers.moderation` busca mensajes pendientes y lecturas cuya
vista Redis quedó pendiente. Puede reconstruir el proceso sin memoria del request.
Procesa hasta 100 mensajes por conversación por iteración; el resto conserva su outbox.
Una falla de otra cola no impide intentar recuperar P6.

Después de persistir, la política es **recuperación hacia adelante**: conservar el mensaje
y reintentar contadores/avisos. Revocar un Pub/Sub ya consumido no es posible; eliminar
el historial en ese punto rompería la consigna. Nunca se compensa borrando el mensaje.
Si la reserva de secuencia funciona pero la inserción falla, queda un hueco permitido;
no se entrega un mensaje ni se incrementa unread por ese hueco.

Lectura usa `$max` y deja la sincronización pendiente en la misma actualización MongoDB.
Repetir una lectura o enviar una lectura anterior no retrocede el marcador. Los contadores
se obtienen contando mensajes ajenos posteriores al marcador, por conversación/usuario.
Una lectura confirmada en Mongo se conserva aunque falle Redis. Consultar la lista de grupos
reconstruye sus contadores, incluso si las claves derivadas se perdieron.

Índices creados en bootstrap: grupo por creador/clave, mensajes por remitente/clave y
conversación/secuencia únicos, membresía/UUID, mensajes pendientes y lecturas pendientes.
Las claves son durables en MongoDB; sobreviven al vencimiento o pérdida de claves Redis.
Reintentar igual devuelve el mismo UUID; cambiar texto o conversación con la misma clave da 409.

## Interfaz

`/mensajes`: crear grupo buscando usuarios, lista paginada con unread, historial con autor,
fecha y texto, cargar anteriores y enviar. El texto y la clave se conservan al reintentar
un envío fallido sin editarlo. Confirmar un envío limpia el campo; un mensaje pendiente
se muestra como «Guardado · distribución pendiente».
La lectura es explícita: «Marcar hasta el último como leído» incluye mensajes anteriores.
Historial cada 3 segundos y grupos cada 5 mientras la pestaña sea visible; heartbeat de P8
cada 45 segundos, con presencia de 120 segundos. No hay WebSocket ni recibo de entrega.
La interfaz consulta el historial MongoDB, por lo que un aviso perdido no pierde mensajes.
Escritorio muestra grupos y conversación; móvil alterna entre ambas pantallas.

## Pruebas reproducibles y límites

`RUN_INTEGRATION_TESTS=1 python -m pytest tests/integration/test_problem_06_messaging.py -q`
usa MongoDB/Redis reales y una base aislada. Cubre permisos, reintentos concurrentes,
conflictos, historial paginado, lecturas repetidas/anteriores, grupos independientes,
pérdida de claves derivadas, fallas parciales, reconstrucción del servicio y suspensión.
`frontend/tests/e2e/messages.spec.ts` usa dos sesiones reales en escritorio y móvil.

En desarrollo se admite `X-Fail-At-Step`: `p6_before_persist`, `p6_after_persist`,
`p6_after_unread`, `p6_after_notify`. Después de persistir se responde con el mensaje
pendiente; consultar `/delivery` muestra su recuperación. El worker puede resolverlo
rápidamente. Para observarlo detenido, parar **sólo** moderation-worker, enviar con
falla inyectada, consultar historial/estado, arrancarlo y volver a consultar estado.

Despliegue soportado: Docker Linux en un host, API y worker con `interaction_locks` compartido.
No garantiza coordinación entre hosts independientes ni entrega Pub/Sub exactamente una vez.
`completed` no significa que todos estén conectados ni que hayan leído. Historial conserva
mensajes de autores suspendidos; las cuentas suspendidas no pueden acceder ni recibir avisos.
No incluye edición/borrado de mensajes, cambios de membresía, adjuntos ni búsqueda de historial.
No migra mensajes experimentales sin secuencia de la rama anterior: esa rama no se integró.

Validación de esta entrega: suite completa de backend 305 aprobados y una prueba adicional
aprobada de falla anterior a persistir (306 escenarios en total); Ruff y mypy sobre 199 archivos.
Frontend 110 aprobados y E2E general 26 aprobados. Además se verificó en Compose real:
mensaje pendiente con moderation-worker detenido, recuperación al arrancarlo, mensaje y lectura
persistidos con Redis detenido y recuperación sin perder la lectura al arrancar Redis.
Los dos mensajes permanecieron en el historial y finalizaron completed. No se borraron volúmenes.

