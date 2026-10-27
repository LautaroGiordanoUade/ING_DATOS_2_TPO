# Problema 07 — Moderación

**Estado: implementado y validado contra MongoDB/Redis reales.**

## Capas

Router → ModeratePostUseCase / IdentityService / ContentQueries → puertos de dominio/aplicación
→ MongoModerationRepository, MongoUserRepository, MongoPostRepository y RedisModerationViews.
El router no consulta motores. ModeratePostUseCase encola; ModerationProcessor ejecuta efectos.
La autenticación completa los PasswordHasher/TokenService existentes, antes vacíos, con PBKDF2
SHA256 (600000 iteraciones, salt aleatorio) y bearer HMAC-SHA256 con sujeto/expiración.
No existían roles implementados: User ahora conserva user/moderator/admin. La API nunca asigna
un rol privilegiado por registro; el seed de desarrollo crea los actores de demostración.

## Datos

- `users`: UUID, identidad/hash, estado y rol; índices únicos username/email.
- `moderation_reports`: UUID, post_id, target_type=post, reporter_id, reason, description,
  resolution_status (pending/approved/rejected/reverted), fechas, moderador y última decisión.
  Único (post_id, reporter_id); índices por estado/fecha, moderador y post/operación de resolución.
  `resolution_operation_id` identifica el hide original; `resolution_report_id`, su reporte
  principal. `operation_id` conserva la última decisión aplicada a cada reporte.
- `moderation_jobs`: UUID determinista por reporte y tipo decision/revert, actor, acción, motivo,
  status, active, snapshot/restore, completed_steps, failures, error, resume_phase y fechas.
  `decision_at` fija la fecha de resolución al decidir el commit; los reintentos la conservan.
  Índice único parcial post_id donde active=true; índice de cola status/created_at.
- `moderation_history`: evento por operation_id (upsert idempotente), post/reporte/actor,
  acción, motivo, fecha, snapshot anterior, estado resultante, cantidad de reportes afectados
  y operación original de resolución. Un grupo de reportes produce un evento por decisión.
- `posts`: conserva moderation_status y moderation_owner para validar qué reporte puede revertir.
- Redis: `moderation:<post>:hidden`; contadores públicos y sufijo `:moderation_saved`;
  `feed:<user>` conserva el mismo sorted set del P1. No se crea un contador ajeno al modelo.

## Workflow

```mermaid
stateDiagram-v2
    [*] --> pending
    pending --> running: snapshot durable
    running --> committing: efectos aplicados
    committing --> completed: reporte y auditoria
    running --> compensating: error
    compensating --> compensated: restauracion completa
    committing --> failed: recuperacion agotada
    compensating --> failed: recuperacion agotada
    failed --> committing: retry del commit
    failed --> compensating: retry de compensacion
    compensated --> pending: retry explicito sin inyeccion
```

Hide: persistir snapshot → ocultar en Mongo → gate/contadores Redis atómicos → ZREM por lotes
→ decidir commit durable → cerrar todos los reportes pendientes del post/auditoría → liberar exclusión.
Revert: preservar snapshot oculto → ZADD de los feeds anteriores y restaurar contadores
→ restaurar moderation_status/owner Mongo → commit/auditoría.
Rechazo no modifica contenido ni derivados. Las fallas previas a committing compensan;
una vez en committing se completa la decisión sin rollback. Los jobs conservan evidencia
asimismo de fallas, compensaciones y reintentos, aunque no generen una resolución exitosa.

### Reportes asociados

Ocultar una publicación aprueba todos sus reportes pendientes, con el mismo moderador,
motivo, fecha y operación. Reportes rechazados previamente y reportes de otros posts se conservan.
Rechazar un reporte es una decisión individual: no invalida los motivos de los otros reportantes.

La reversión puede solicitarse desde cualquiera de los reportes aprobados por el mismo hide.
Todos apuntan a una única operación de reversión, derivada del reporte principal. Sólo ese
grupo pasa a reverted; un reporte nuevo creado después de restaurar la publicación permanece
pending para una futura decisión. El origen de la resolución sigue disponible después de revertir.

El commit actualiza por estado y post; cada documento registra su origen en la misma escritura.
Si update_many se interrumpe después de actualizar algunos reportes, el worker retoma committing
y actualiza los restantes. El conteo de auditoría se calcula desde las operaciones persistidas,
no desde modified_count del último reintento. La fecha durable evita diferencias entre lotes.
Un hide antiguo sin metadatos de grupo puede revertirse por su reporte original; no se atribuyen
retroactivamente reportes a decisiones históricas cuyo alcance no quedó registrado.

Compensar hide restaura Redis antes de abrir Mongo. Compensar revert oculta Mongo primero,
reaplica gate/contadores y elimina los feeds de su hide original. Un fallo de compensación
retiene active=true para impedir que otra decisión pise el estado recuperable.

## Concurrencia e idempotencia

| Carrera | Resolución |
|---|---|
| Dos decisiones iguales | Mismo UUID de job; se devuelve el original |
| Dos decisiones distintas del mismo reporte | UUID único + comparación de payload: 409 |
| Dos reportes del mismo post | Índice único parcial de operación activa |
| Un reporte llega mientras se oculta | Bloqueo de post compartido por inserción y cambio de visibilidad; entra antes del hide o recibe 409 |
| Una decisión validada llega después del cierre | Revalidación del reporte al encolar bajo el mismo bloqueo |
| Revert desde distintos reportes asociados | Mismo reporte principal y UUID de reversión |
| Caída a mitad de resolver/revertir reportes | Origen por documento y filtros de estado; completa el mismo grupo |
| Revert durante hide | 409 hasta que hide esté completed |
| Replay de hide durante revert | Devuelve hide completed, no repite efectos |
| Dos retries | Compare-and-set del estado terminal; uno recibe 409 |
| Proceso muere después de Redis, antes del checkpoint | Replay de Lua/ZADD/ZREM idempotentes |
| Proceso muere durante auditoría | Retoma committing; upsert de evento evita duplicados |
| P5 incrementa mientras se oculta | Lua decide atómicamente entre contador público y preservado |
| P1 vuelve a escribir su marcador de publicación | Gate P7 separado impide publicar contenido oculto |

El worker único está protegido por flock sobre volumen compartido y revalida el dueño/estado
antes del primer efecto. No depende de TTL ni de un lock Redis huérfano. Las consultas públicas
de detalle, lote, autor y ambos feeds filtran Mongo. El preview P1 verifica Mongo por lote además
del gate Redis. No existen búsquedas públicas reales fuera de esas lecturas.
Los contadores no se decrementan acumulativamente: se ocultan y restauran de forma atómica.
Las actualizaciones P5 en vuelo se preservan, por lo que un revert no destruye cambios legítimos.
API y worker comparten además `interaction_locks` para las secciones Mongo de creación de
reportes, cambio de visibilidad, encolado y commit. El bloqueo P7 usa archivos con prefijo propio,
funciona sin Redis y se libera al terminar el proceso. No se mantiene durante el workflow entero;
el índice de operación activa conserva la exclusión entre pasos.

## Retry y recuperación

Tres intentos por paso transitorio, backoff 50/100 ms; no retry de errores funcionales.
Una falla de negocio o agotamiento de efectos conduce a compensación. Si ésta falla, estado
failed y retry administrativo retoma resume_phase. Una compensación completada se puede volver
a intentar explícitamente con el mismo job, limpiando checkpoints e inyección de falla.
El worker al reiniciarse carga pending/running/committing/compensating. La actualización de
reporte y evento no requiere una transacción distribuida; committing es su decisión durable.
Los índices se verifican también antes de insertar un reporte/job: un fallo de índices no
habilita escrituras concurrentes sin la restricción necesaria.

## Garantías y límites

Docker Linux en un host, consumidores con el mismo volumen de bloqueo. No soporta consumidores
independientes multi-host ni pérdida de datos de motores. Redis AOF tiene su límite previo de
un segundo. Snapshot mediante SCAN y límite de 100000 referencias, coherente con P1. El feed
es cronológico básico; ranking/cursor completo sigue P3. Las limitaciones P5 ante su propia caída
siguen documentadas en docs/problem_05_consistency.md; no se sustituyeron todas sus sagas.

## Evidencia

La interfaz está documentada en [frontend/problem_7.md](../frontend/problem_7.md). Agrega una
lectura publicada protegida para moderator/admin en `/moderation/posts/{post_id}/content`,
con referencia opcional al reporte y sus operaciones para recuperar la revisión tras recarga.
Las lecturas públicas y los efectos de las decisiones mantienen sus reglas anteriores.

Corrección de reportes asociados: 10 escenarios nuevos en
`tests/integration/test_problem_07_report_groups.py`. Cubren resolución/reversión del grupo,
rechazos previos, otros posts, fallas parciales y compensaciones, reportes/decisiones en curso,
reporte nuevo durante la reversión y compatibilidad con hides anteriores sin metadatos de grupo.
Suite completa: 316 aprobados, incluidas las regresiones P6/P7/P8; Ruff y mypy sobre 201 archivos.
Contrato OpenAPI regenerado; lint, TypeScript y build del frontend aprobados.
Smoke contra API y worker reales: tres reportes, un hide que cierra los tres, revert desde
un reporte asociado que restaura los tres, un evento por decisión y replay sin duplicación.

57 pruebas P7 de integración real, 12 unitarias nuevas de seguridad, suite completa de 94 tests
exitosa y smoke HTTP real con API/worker de Compose fueron la validación inicial. Guía, payloads, datos y escenarios:
[Guía de Swagger](../problem_7_moderation_test_guide.md).
