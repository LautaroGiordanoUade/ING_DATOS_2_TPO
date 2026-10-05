# Problema 06 — Mensaje grupal

- **Objetivo:** historial durable, entrega inmediata y lectura por participante.
- **Motores:** MongoDB (conversación/mensaje/read_by), Redis (presencia/entrega/unread).
- **Secuencia:** persistir antes de entregar; pasos exactos `TODO(TP)`.
- **Identificadores:** conversation/message/sender/operation UUID.
- **Fallas:** persistido sin entrega es recuperable; entregado sin persistir debe evitarse.
- **Compensaciones:** `TODO(TP)` retry/revoke y reconciliación unread.
- **Idempotencia:** prevenir mensajes duplicados al reintentar.
- **Concurrencia:** membresía, lectura y entregas simultáneas.
- **Código:** `SendGroupMessageUseCase`, repositories Conversation/Message/Counter/Notification.

