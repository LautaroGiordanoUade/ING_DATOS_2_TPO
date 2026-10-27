# Problema 08 — suspensión y trazabilidad

## Alcance implementado

Estado de cuenta y revocación de credenciales en MongoDB; exclusión en Neo4j; retiro físico de
feeds, cierre de presencia y contadores en Redis. Reactivación auditable y compensaciones.
Trazabilidad real de perfil, relaciones, publicaciones y conversaciones, con control de acceso.
No hay un bypass demo del P8. Las consultas completadas de P4/P6 son dependencias del P8;
no se presenta como completado el envío de mensajes ni el ranking general del resto del TP.

## Capas y ejecución

`Router → SuspendAndTraceUserUseCase → AccountStore/AccountGraph/AccountViews → adaptadores`.
Los comandos se encolan en MongoDB y los ejecuta AccountProcessor. El consumidor existente
moderation-worker procesa P7 y P8 bajo el mismo flock/volumen, por lo que sus efectos de posts
no pueden intercalarse. Las API sólo encolan y leen. WorkflowSteps comparte los pasos repetibles,
inyección de fallas y retry con ModerationProcessor, sin duplicar el mecanismo de P7.

## Modelo e índices

- users: account_status, auth_version y last_account_operation. Estado/revocación cambian en una
  escritura atómica, y la marca de operación impide repetir el incremento al recuperar.
- account_jobs: operación, usuario, actor, acción, motivo, key/UUID determinista, estado,
  previous_status, restore_from, snapshot de grafo, lista de posts, pasos y fallas.
  Un índice único parcial por user_id/active limita a una transición activa por cuenta.
- account_post_snapshots: un documento por operación/post con audiencia/scores y contadores.
  Se evita meter todos los snapshots de una cuenta en el límite de 16 MB de un único job.
- account_history: un evento idempotente por operation_id, con actor, motivo, fechas y estados.
- Redis account:<user>:suspended, presence:<user> (TTL 120 s) y backup atómico de feed/presencia
  por operación. Snapshot y retiro del feed propio/presencia ocurren en un Lua idempotente.
- Redis suspension:<post>:hidden y suspension:<post>:feeds. Son independientes del gate P7;
  ambos comparten un único valor preservado para los dos contadores existentes.
- Neo4j User.account_status; las aristas FOLLOWS/BLOCKS permanecen para trazabilidad/restauración.

## Orden, compensaciones y recuperación

Suspender: snapshot durable → Mongo suspended/revocar tokens → gate Redis y cerrar presencia/feed
propio → Neo4j suspended → snapshots por post y retiro de sus feeds/contadores → committing →
auditoría → completed. Una falla anterior a committing compensa los efectos y restaura active;
una revocación de credenciales ya aplicada no se deshace por seguridad.

Reactivar: recuperar referencias/contadores sin quitar moderaciones P7 → Neo4j active → restaurar
feed propio y abrir gate Redis → Mongo active → committing/auditoría. La presencia no se abre
sola y los tokens anteriores no vuelven a ser válidos; hace falta login y heartbeat nuevos.
Una falla de reactivación vuelve a suspender, cierra presencia y retira nuevamente los efectos.

Estados pending/running/committing/compensating se reanudan al reiniciar el consumidor. Cada
paso transitorio dispone de tres intentos con backoff 50/100 ms (Mongo/Redis/Neo4j). Los errores
funcionales no se reintentan. Si no se puede compensar/terminar commit, failed conserva la
exclusión activa y resume_phase. Retry administrativo reanuda esa fase mediante CAS.
Compensated es terminal; para repetir el comando original se utiliza una nueva key.

## Idempotencia y carreras

| Escenario | Garantía |
|---|---|
| Repetir una key | UUID determinista, payload comparado y actor original conservado |
| Dos peticiones iguales sin key | Reutilizan el job activo o el estado final equivalente |
| Dos operaciones distintas activas de la cuenta | Índice único parcial, conflicto 409 |
| Dos retries | CAS failed→resume_phase; sólo uno avanza |
| Reactivar durante suspensión pendiente | 409 hasta disponer del snapshot completed |
| Replay de suspend después de reactivate | Se devuelve el job viejo sin repetir efectos |
| Suspender/reactivar versus P7 | Consumidor común y gates independientes por motivo |
| P7 revert durante suspensión | No publica el post; audiencia preservada para reactivar |
| P7 hide durante suspensión | Al reactivar continúa oculto y puede revertirse después |
| P1 en vuelo | Redis conoce autor/gate; audiencia durable recupera referencias omitidas |
| Heartbeat en vuelo | Lua rechaza solicitudes tardías bajo gate de suspensión |
| P5 en vuelo | Incrementos se dirigen al contador preservado mientras exista cualquier gate |
| Caída después del efecto antes del checkpoint | Replay Lua/ZADD/ZREM, marcas Mongo y upsert auditables |

Las lecturas públicas de posts consultan el estado del autor en MongoDB. Las recomendaciones
consultan candidatos en Neo4j y luego filtran estados MongoDB por lote; también excluyen origen
e intermediarios suspendidos. La protección no depende de que los derivados terminen antes.
Los endpoints P1/P5 anteriores rechazan actores conocidos suspendidos conservando sus contratos.

## Trazabilidad y privacidad

Sólo el titular activo o moderator/admin pueden consultar una traza; un suspendido no puede
usar su antiguo bearer. Perfil pasa por UserResponse: no se expone password_hash/email.
Relaciones salen de Cypher; posts visibles respetan las mismas reglas públicas P7/P8.
post_states muestra hasta 100 estados sin el texto oculto, con suspensión/visibilidad explícitas.
Conversaciones salen de MongoDB por participant_ids, excluyendo archivadas y ajenas (máximo 100).
Se incluye presencia actual e historial administrativo (máximo 100). Una dependencia caída
produce 503, no una respuesta de éxito parcial ni datos ficticios.

## Operación y límites

Despliegue soportado: Docker Linux, un host, todos los consumidores P7/P8 compartiendo volumen.
Multi-host con consumidores independientes necesita fencing distribuido. No se garantiza
recuperación ante pérdida de volúmenes; Redis AOF conserva la ventana previa de un segundo.
Hasta 10000 posts por cuenta y 100000 referencias por snapshot de post. SCAN y restauración
son lineales; no se promete escalabilidad arbitraria ni transacciones distribuidas ACID.
Los backups Redis se conservan para reactivar/compensar; su política de retención queda ligada
a la conservación del historial de operaciones, no a TTL que pueda romper una recuperación.

Rama feature/problem-8-suspension-traceability, alineada con main fced264 actualizado,
que ya incluye el merge P7. La implementación no modifica el PR P7.

Guía, usuarios, IDs, payloads y pruebas: [Swagger P8](../problem_8_suspension_test_guide.md).


Entregas P1 diferidas: Redis registra referencias para autor/seguidor suspendido en hashes
operativos. Al abrir el gate, un Lua drena esas referencias atomicamente, incluyendo batches que
terminaron durante la reactivacion. ZADD es idempotente; el rollback P1 elimina tambien sus
referencias diferidas. Los snapshots P7 conservan esas referencias aunque aun no fueran visibles.
Esto evita perder una entrega por carreras de suspension/reactivacion o moderacion simultaneas.


## Validación final

161 passed, 0 failed, 0 skipped. P8 agrega 57 integraciones reales de los tres motores y 10
unitarias; la línea base tenía 94 tests. Smoke HTTP final passed; Ruff/mypy/formato del cambio
correctos. Evidencia: docs/problem_8_http_validation.json. La única advertencia es previa de
Starlette/httpx. TODO.md marca el P8 implementado, conservando el historial de la sección.
# Medición con volumen

La captura de membresías Redis se realiza con SCAN/HSCAN de mayor tamaño y lecturas
por lotes, manteniendo feeds históricos y entregas diferidas. Ver
[mediciones P8](../problem_8_performance.md) y su evidencia reproducible.
