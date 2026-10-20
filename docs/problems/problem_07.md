# Problema 07 — Moderación

**Estado: pendiente de implementación.**

- **Objetivo:** ocultar/revertir contenido y derivados de forma auditable.
- **Motores:** MongoDB, Redis y Neo4j si existe nodo Post.
- **Secuencia:** `TODO(TP)` resolver reporte, estado del post, feeds, contadores y grafo.
- **Identificadores:** report/post/moderator/operation UUID.
- **Fallas:** decisión durable con vistas incompletas.
- **Compensaciones:** `TODO(TP)` revertir exactamente y reconstruir sin duplicados.
- **Idempotencia:** una decisión/reversión repetida no debe duplicar efectos.
- **Concurrencia:** múltiples reportes/decisiones y nuevas interacciones.
- **Código:** `ModeratePostUseCase` y repositories Moderation/Post/Feed/Counter.

