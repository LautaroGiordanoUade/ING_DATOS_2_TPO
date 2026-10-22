# Problema 5: concurrencia, notificaciones y recuperación durable

Las altas, cambios y bajas de reacciones y los comentarios adquieren el mismo bloqueo por
publicación (`lock:post_reactions:{post_id}`). Se mantiene durante la escritura
MongoDB, el contador, la notificación y las compensaciones. Así una baja no puede
restar antes de que el alta haya sumado, ni una compensación pisar otra reacción.
El bloqueo coordina procesos/instancias de la API de un host con volumen compartido.
Si no se consigue en cinco segundos, la API responde 409 para que el cliente reintente.

El lease Redis vence a los 30 segundos y se renueva durante la operación. La exclusión
autoritativa es un bloqueo de archivo del sistema operativo: un proceso pausado conserva
ese bloqueo aunque pierda el lease Redis. El volumen Compose `interaction_locks` permite
compartirlo entre procesos/instancias del mismo host; el sistema operativo lo libera cuando
muere el proceso. Todos los escritores deben usar ese volumen (o el mismo
`P5_LOCK_DIRECTORY`). No ofrece exclusión entre hosts independientes ni agrega contenedores.

## Recuperación durable de operaciones tras caída

Las operaciones de interacción (`problem_05_react`, `problem_05_remove_reaction`,
`problem_05_comment`) persisten de forma durable en la colección `operations` de MongoDB
junto con sus metadatos (`post_id`, `user_id`, `author_id`, `event_id`/`comment_id`,
`scoped_key`, `fingerprint`).

Si un proceso se interrumpe abruptamente (crash, reinicio o SIGKILL):
1. **Detección de operaciones pendientes:** Tanto en el ingreso del siguiente escritor a la publicación
   (`_repair_counters`) como en el worker en segundo plano (`app.workers.moderation`), se consultan las
   operaciones con estado `running`, `pending` o `compensating` mediante `operation_log.pending()`.
2. **Reconciliación bajo bloqueo:** Bajo el bloqueo de la publicación (`reaction_lock.hold(post_id)`):
   - **Operaciones completadas en MongoDB:** Si la reacción o el comentario ya existían en MongoDB,
     se recalculan los contadores absolutos en Redis, se emite la notificación pendiente al autor
     (evitando notificaciones perdidas tras el corte), se completa la clave de idempotencia
     (`idempotency.complete(...)` para que los reintentos devuelvan el resultado determinista 202) y
     se transiciona el estado de la operación a `completed`.
   - **Operaciones interrumpidas antes de persistir o en compensación:** Si la operación no llegó a
     persistirse en MongoDB o cayó mientras se compensaba, se limpian las referencias parciales, se
     recalculan los contadores, se revoca la notificación en Redis si existía y se **libera la reserva
     de idempotencia** (`idempotency.release(scoped_key)`), evitando bloqueos huérfanos 409 y permitiendo
     que el cliente reintente inmediatamente. La operación pasa a `compensated` o `failed`.

## Consistencia de contadores y notificaciones

Antes de cambiar o borrar una reacción se lee su estado previo bajo el mismo bloqueo.
Esto permite restaurarlo si MongoDB hizo la escritura pero se perdió la respuesta.
Las compensaciones restauran primero MongoDB y luego recalculan el contador absoluto;
hacerlo al revés contaría el alta por borrar o ignoraría la baja por restaurar.
Si también falla la restauración, el registro queda failed; no se afirma un rollback exitoso.

`set_value` consulta los gates de moderación y suspensión dentro de Lua. Mientras alguno
está activo mantiene el contador visible en cero y actualiza `:moderation_saved`. P7/P8
recuperan el valor actualizado al retirar el último gate, sin pisar una transición concurrente.
Los archivos `.lock` no se eliminan mientras el servicio funciona para evitar carreras con
escritores que ya los abrieron; limpiarlos requiere detener los escritores.

El paso de notificación declara `compensate_on_failure=True`: si empieza a ejecutarse,
su compensación se intenta aunque falle antes de terminar. Esto cubre HSET exitoso
seguido de PUBLISH fallido. Cada alta usa el UUID de su reacción como identificador
de evento para no eliminar notificaciones de altas anteriores al compensar.
El mismo mecanismo cubre las notificaciones de comentarios.

La revocación elimina la notificación guardada; no puede retirar un evento Pub/Sub
que un cliente ya recibió.

Regresiones y pruebas: `tests/unit/test_problem_05_regressions.py` y
`tests/integration/test_problem_05_consistency.py`.
