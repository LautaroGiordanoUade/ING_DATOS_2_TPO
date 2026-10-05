# Problema 01 — Publicación

- **Objetivo:** crear contenido sin bloquear por miles de seguidores.
- **Motores:** MongoDB (contenido), Neo4j (seguidores), Redis (feed).
- **Secuencia base:** persistir → obtener audiencia → distribuir; `TODO(TP)` decidir síncrono/diferido.
- **Identificadores:** `operation_id`, `post_id`, `user_id` UUID.
- **Fallas:** persistencia, lectura de grafo, fan-out parcial.
- **Compensaciones:** `TODO(TP)` borrar/tombstone y retiro exacto de feeds.
- **Idempotencia:** `TODO(TP)` fingerprint y replay por `Idempotency-Key`.
- **Concurrencia:** publicación repetida y seguidores que cambian durante fan-out.
- **Código:** `PublishContentUseCase`, repositories Mongo/Neo4j/Redis.

