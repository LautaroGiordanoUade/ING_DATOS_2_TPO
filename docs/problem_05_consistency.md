# Problema 5: concurrencia y notificaciones parciales

Las altas, cambios y bajas de reacciones adquieren el mismo bloqueo Redis por
publicación (`lock:post_reactions:{post_id}`). Se mantiene durante la escritura
MongoDB, el contador, la notificación y las compensaciones. Así una baja no puede
restar antes de que el alta haya sumado, ni una compensación pisar otra reacción.
El bloqueo coordina distintas instancias de la API, no solo tareas de un proceso.
Si no se consigue en cinco segundos, la API responde 409 para que el cliente reintente.

El bloqueo no expira automáticamente. Una pausa larga no debe permitir dos escritores.
Ante la caída del proceso o pérdida del estado de Redis, todavía se necesita recuperación:
detener escritores, revisar el registro MongoDB, resolver la operación pendiente,
reconciliar el contador con MongoDB y solo entonces liberar el bloqueo huérfano.
No borrar bloqueos de operaciones activas. La recuperación automática queda pendiente.

El paso de notificación declara `compensate_on_failure=True`: si empieza a ejecutarse,
su compensación se intenta aunque falle antes de terminar. Esto cubre HSET exitoso
seguido de PUBLISH fallido. Cada alta usa el UUID de su reacción como identificador
de evento para no eliminar notificaciones de altas anteriores al compensar.
El mismo mecanismo cubre las notificaciones de comentarios.

La revocación elimina la notificación guardada; no puede retirar un evento Pub/Sub
que un cliente ya recibió. No se garantiza entrega exactamente una vez ni recuperación
automática ante una caída entre motores. Si falla también la compensación, el registro
queda en estado failed y requiere reconciliación.

Regresiones automatizadas: `tests/unit/test_problem_05_regressions.py`.

Para repetir las pruebas con las bases levantadas, desde Git Bash:

```bash
docker compose exec -T api python < scripts/validar_problema5.py
docker compose exec -T api python < scripts/validar_problema5_fallas.py
```

Los scripts crean UUID nuevos y dejan los datos aislados para inspección. El segundo
inyecta la falla después de HSET y fuerza el orden concurrente que antes desalineaba
el contador. No detienen motores ni modifican las publicaciones existentes.

Validación realizada: 20/20 comprobaciones con motores reales; suite pytest:
13 aprobadas y 1 integración placeholder omitida. Mypy de aplicación y tests sin errores.
