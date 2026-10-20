# Problema 5: reacciones y comentarios

Implementado en InteractWithPostUseCase y adaptadores MongoDB/Redis:
- Reacción única por usuario/post, cambio de tipo y eliminación.
- Comentarios, contadores Redis y notificaciones persistidas/PubSub.
- Idempotencia por clave para comentarios.
- Serialización Redis de cambios de reacción y compensación de notificaciones parciales.

La guía de consistencia, pruebas y límites está en docs/problem_05_consistency.md.
No se garantiza recuperación automática del bloqueo huérfano tras caída de API ni entrega
exactamente una vez. Falta fingerprint de comentarios y recuperación de resultados inciertos
adicionales. Esos pendientes están explícitos en TODO.md.
