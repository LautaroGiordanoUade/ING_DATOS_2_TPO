# Arquitectura de persistencia

## Capas y motores

Domain define entidades y contratos; Application coordina los casos de uso; Infrastructure
implementa los drivers. La API FastAPI expone los comandos y consultas.

Se eligieron tres motores NoSQL: MongoDB, Neo4j y Redis. PostgreSQL no se inicializa ni es
necesario para ejecutar el sistema. Sus archivos y Alembic quedan como legado.

MongoDB es fuente de verdad del contenido, comentarios y reacciones. También se asignan aquí
usuarios, moderación, conversaciones y mensajes, cuyos adaptadores aún están pendientes.
Los índices únicos cubren una reacción por (post_id, user_id). Usuarios necesitará índices
únicos de username/email. Historial documental e interacciones crecientes no se almacenan
como listas ilimitadas dentro de un único usuario/post.

MongoDB conserva operations para auditoría y publication_jobs para el trabajo durable del
P1: payload, snapshot de audiencia, cursor y decisión de commit/rollback. No se necesita una
transacción global. El trabajo es autoritativo para la consulta de operaciones del P1.

Neo4j es fuente de verdad del grafo FOLLOWS y BLOCKS; se prevén intereses para P4.
P1 ya ejecuta Cypher real para resolver audiencia. Follow/unfollow, intereses, sugerencias
y trazabilidad siguen pendientes. La clave User.id tiene constraint único.

Redis mantiene sorted sets de feed, contadores y notificaciones operativas. P5 almacena
notificaciones y publica eventos Pub/Sub; P1 usa un marcador común de visibilidad, además
de sus referencias de feed. Presencia, mensajería y unread pertenecen al P6 pendiente.
La justificación no depende solamente de replicar contenido para acelerar lecturas.

## Autoridad y duplicación

| Dato | Fuente de verdad | Otras representaciones / responsable |
|---|---|---|
| Perfil/estado de cuenta | MongoDB (adaptador pendiente) | Estado mínimo Neo4j; P2/P8 deben sincronizarlo |
| Texto e intereses de post | MongoDB | UUID y score en Redis; worker P1 mantiene referencias |
| Seguimientos y bloqueos | Neo4j | Audiencia snapshot en trabajo MongoDB para recuperación |
| Decisión de publicación | publication_jobs MongoDB | Marcador Redis; worker termina commit/rollback |
| Reacciones/comentarios | MongoDB | Contadores y notificaciones Redis; P5 los coordina |
| Operación | MongoDB | UUID compartido en todos los efectos |
| Historial de mensajes | MongoDB (pendiente) | Entrega/unread Redis (pendiente) |

Los UUID son strings en los motores. El snapshot de audiencia es una duplicación deliberada:
no define los seguimientos actuales; permite deshacer exactamente una distribución aunque
el grafo cambie o se reinicie el worker.

## Procesos y recuperación

Compose inicia API y publication-worker con la misma imagen. La API encola y el worker único
distribuye por lotes. Un flock sobre volumen compartido limita el consumo a un proceso en
ese host y se libera automáticamente al caer. Los trabajos conservan su avance en MongoDB.

Antes del commit, una falla revierte referencias y contenido. Después de decidir commit,
se completa la activación aunque se reinicie. Las lecturas de feed deben comprobar el marcador
published; ZRANGE directo también puede mostrar candidatos pendientes.

P5 usa compensaciones en request y un bloqueo Redis sin vencimiento por publicación.
Su recuperación tras caída de proceso todavía requiere reconciliación manual.

Detalles: docs/problems/problem_01.md y docs/problem_05_consistency.md.
El feed completo P3, la carga de 50000 registros y el informe final siguen pendientes.
