# Problema 03 — Feed

- **Objetivo:** devolver 20 posts con recencia, relevancia y contadores, paginables hacia atrás.
- **Motores:** Redis (IDs/ranking), MongoDB (contenido), Neo4j (señales posibles).
- **Secuencia:** IDs por cursor → contenido por lote → contadores por lote.
- **Identificadores:** `user_id`, `post_id`; cursor score/timestamp/UUID.
- **Fallas:** post retirado entre lecturas; servicio parcial.
- **Compensaciones/idempotencia:** no aplica a lectura; `TODO(TP)` reparación de vistas.
- **Concurrencia:** inserciones durante paginación y scores iguales.
- **Código:** `GetFeedUseCase`, `FeedRepository`, `PostRepository`, `CounterRepository`.

