# Problema 05 — Reacciones y comentarios

- **Objetivo:** interacción única por usuario/post, contadores y notificaciones.
- **Motores:** MongoDB (interacción), Redis (contador/notificación).
- **Secuencia:** `TODO(TP)` upsert/insert → delta contador → evento.
- **Identificadores:** reaction/comment/post/user/operation UUID.
- **Fallas:** persistencia exitosa con derivados incompletos.
- **Compensaciones:** `TODO(TP)` revertir delta/evento sin borrar cambios concurrentes.
- **Idempotencia:** clave de request y unicidad `(post_id,user_id)`.
- **Concurrencia:** cambio/eliminación simultánea y delta correcto.
- **Código:** `InteractWithPostUseCase` y cuatro repositories de interacción.

