# TODO del Trabajo Práctico

Los ítems siguientes son deliberadamente parte de la resolución académica. Formato: **archivo —
clase/método — problema — motor — qué falta — por qué pendiente**.

## Modo demo

- `app/api/demo_data.py` contiene datos mínimos y deterministas exclusivamente para probar contratos
  HTTP y Swagger. `run_api.cmd` activa `APP_DEMO_MODE=true` en desarrollo.
- Reemplazar los mocks gradualmente al implementar cada `TODO(TP)`. Nunca usar estas respuestas como
  dataset, algoritmo, estrategia de consistencia o evidencia de funcionamiento de los motores.
- Con `APP_DEMO_MODE=false`, toda funcionalidad académica todavía pendiente debe conservar la
  respuesta controlada `501 Not Implemented`.

## Problema 1

- `problem_01_publish_content.py` — `PublishContentUseCase.execute` — P1 — Mongo/Neo4j/Redis —
  elegir fan-out, consistencia, idempotencia y rollback — depende del análisis de escala.
- `content_repositories.py` / `social_graph_repository.py` / `operational_repositories.py` — métodos
  usados por publicación — P1 — respectivos motores — implementar consultas/comandos — son la
  solución concreta evaluada.

## Problema 2

- `problem_02_follow_user.py` — `follow/unfollow` — P2 — PostgreSQL/Neo4j/Redis — estado privado,
  pending/approve, duplicados, contadores y feed — requiere estrategia concurrente y compensable.

## Problema 3

- `problem_03_get_feed.py` — `execute` — P3 — Redis/MongoDB/Neo4j — ranking, cursor opaco, lotes y
  enriquecimiento de 20 posts — algoritmo evaluado.

## Problema 4

- `problem_04_social_recommendations.py` — `recommendations` — P4 — Neo4j/PostgreSQL — score,
  Cypher, bloqueados, suspendidos e intereses — consulta y heurística evaluadas.

## Problema 5

- `problem_05_interact_with_post.py` — `react/comment` — P5 — MongoDB/Redis — unicidad, cambio,
  eliminación, contador y notificación — exige atomicidad/idempotencia específicas.

## Problema 6

- `problem_06_send_group_message.py` — `execute` — P6 — MongoDB/Redis — orden persistir/entregar,
  unread por participante y compensación — política distribuida evaluada.

## Problema 7

- `problem_07_moderate_post.py` — ambos métodos — P7 — todos — ocultar/revertir feed, contadores,
  reporte y representaciones — requiere compensaciones y reconstrucción exactas.

## Problema 8

- `problem_08_suspend_and_trace_user.py` — ambos métodos — P8 — todos — suspensión transversal y
  agregación real sin copiar todo — demuestra trazabilidad poliglota.

## PostgreSQL

- Repositories PostgreSQL — P2/P7/P8 — SQL, transacciones, conflictos y locking — pendiente para
  justificar integridad y concurrencia.
- `alembic/versions` — todos — generar/revisar migración inicial y evoluciones.

## MongoDB

- Repositories MongoDB — P1/P3/P5/P6/P7/P8 — filtros, updates, índices y paginación — no se
  incluyen queries definitivas.
- Definir índices únicos para UUID y reacción `(post_id,user_id)`, además de retención/mensajes.

## Redis

- Repositories Redis — P1/P2/P3/P5/P6/P7/P8 — estructuras, comandos atómicos, TTL y Pub/Sub —
  elección forma parte del diseño.
- Definir reconciliación de contadores, trimming de feed y semántica durable de notificaciones.

## Neo4j

- `Neo4jSocialGraphRepository` — P1/P2/P4/P8 — todas las consultas Cypher e índices/constraints —
  parte central del TP.
- Decidir nodo Post liviano y metadata mínima sin convertir el grafo en réplica de MongoDB.

## Consistencia

- Definir orden de pasos, retry, timeout, estado incierto y reconciliación por cada operación.
- Implementar el adaptador durable PostgreSQL de `OperationLogRepository`; memoria sirve sólo para
  demo/test.

## Compensaciones

- Implementar compensación idempotente por P1, P5, P6, P7 y P8; documentar datos irreversibles y
  estrategia ante falla de la propia compensación.
- Definir recuperación cuando un paso produce efecto parcial pero falla antes de registrarse como
  completado (estado incierto, probe/reconciliación).

## Idempotencia

- Implementar `RedisIdempotencyRepository`; integrar `Idempotency-Key`, fingerprint del request,
  ownership, TTL y replay de respuesta en endpoints relevantes.

## Concurrencia

- Analizar follow/unfollow, upsert de reacción, deltas de contadores, envío/unread, moderación y
  retries. Evitar read-modify-write; justificar primitivas atómicas/constraints.

## Carga de datos

- `scripts/seed_data.py` — todos — lotes, relaciones coherentes, distribución realista y mínimo de
  50.000 registros en el proceso de mayor volumen.

## Testing

- Completar fakes por use case, contract tests de repositories, integración por motor, fallas en
  cada checkpoint, compensación parcial, concurrencia y trazabilidad end-to-end.

