# Problema 08 — Suspensión y trazabilidad

**Estado: pendiente de implementación.**

- **Objetivo:** aplicar suspensión transversal y consultar perfil, relaciones, posts y chats.
- **Motores:** MongoDB, Neo4j y Redis, conservando cada fuente de verdad.
- **Secuencia:** `TODO(TP)` estado de cuenta MongoDB → efectos operativos/grafo/contenido; trazado por consultas.
- **Identificadores:** user/operation UUID compartidos.
- **Fallas:** suspensión parcial o motor no disponible al trazar.
- **Compensaciones:** `TODO(TP)` política de reactivación y reparación por motor.
- **Idempotencia:** suspensión repetida y reanudación deben tener estados explícitos.
- **Concurrencia:** actividad simultánea con el cambio de estado.
- **Código:** `SuspendAndTraceUserUseCase`, `UserTrace`, todos los repositories implicados.

