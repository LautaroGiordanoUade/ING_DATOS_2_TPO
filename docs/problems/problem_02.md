# Problema 02 — Follow / unfollow

- **Objetivo:** gestionar relación pública/privada y derivados.
- **Motores:** PostgreSQL (estado/tipo), Neo4j (relación), Redis (contadores/feed).
- **Secuencia:** `TODO(TP)` validar → crear/pending/aprobar/eliminar → actualizar derivados.
- **Identificadores:** ambos `user_id` y `operation_id` UUID.
- **Fallas/compensaciones:** arista sin contador o feed desalineado; `TODO(TP)` reconciliar/revertir.
- **Idempotencia:** follow duplicado y unfollow ausente deben tener semántica definida.
- **Concurrencia:** requests opuestos y aprobación simultánea.
- **Código:** `FollowUserUseCase` y repositories User/Graph/Counter/Feed.

