# Problema 5: concurrencia y notificaciones parciales

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

Al entrar, después de validar la publicación y bajo ese bloqueo, se recalculan ambos
contadores desde MongoDB. El siguiente escritor repara así contadores pendientes por una
caída anterior. Los comentarios también se serializan para no pisar sus compensaciones.
Reparar contadores no implica recuperar una notificación, resolver una operación pendiente
ni una reserva de idempotencia abandonada: la recuperación durable completa sigue pendiente.

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
que un cliente ya recibió. No se garantiza entrega exactamente una vez ni recuperación
automática ante una caída entre motores. Si falla también la compensación, el registro
queda en estado failed y requiere reconciliación.

Regresiones: `tests/unit/test_problem_05_regressions.py` y
`tests/integration/test_problem_05_consistency.py`. Estas últimas usan motores reales:
las seis fallas detectadas en revisión, respuestas MongoDB perdidas, comentarios concurrentes,
lease vencido con dueño vivo y caída real de un proceso de prueba.

Para repetir las pruebas con las bases levantadas, desde Git Bash:

```bash
docker compose exec -T api python < scripts/validar_problema5.py
docker compose exec -T api python < scripts/validar_problema5_fallas.py
```

Los scripts crean UUID nuevos y dejan los datos aislados para inspección. El segundo
inyecta la falla después de HSET y fuerza el orden concurrente que antes desalineaba
el contador. No detienen motores ni modifican las publicaciones existentes.

Validación de la corrección: 218 pruebas aprobadas con main y P5 corregido, incluidas
12 integraciones nuevas; 247 pruebas aprobadas al combinarlo con P3 en una copia temporal,
sin mezclar las ramas. Mypy sin errores en ambos conjuntos; Ruff en los archivos modificados.
Los resultados del arreglo sustituyen la evidencia histórica anterior de 20 checks P5.
Docker reconstruido: 18 checks HTTP P5 y dos regresiones de falla/concurrencia aprobados.
El script de fallas ya no corrige manualmente el contador antes de verificarlo; comprueba
el estado que dejó la aplicación y exige consistencia también en la falla de notificación.
