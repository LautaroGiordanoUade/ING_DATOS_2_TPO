# Arquitectura de persistencia

## Capas y motores

Domain define entidades y contratos; Application coordina los casos de uso; Infrastructure
implementa los drivers. La API FastAPI expone los comandos y consultas.

Se eligieron tres motores NoSQL: MongoDB, Neo4j y Redis. PostgreSQL no se inicializa ni es
necesario para ejecutar el sistema. Sus archivos y Alembic quedan como legado.

MongoDB es fuente de verdad del contenido, comentarios y reacciones. También se asignan aquí
usuarios y moderación (implementados para P7), además de conversaciones y mensajes pendientes.
Los índices únicos cubren una reacción por (post_id, user_id). Usuarios tiene índices
únicos de username/email. Historial documental e interacciones crecientes no se almacenan
como listas ilimitadas dentro de un único usuario/post.

MongoDB conserva operations para auditoría y publication_jobs para el trabajo durable del
P1: payload, snapshot de audiencia, cursor y decisión de commit/rollback. No se necesita una
transacción global. El trabajo es autoritativo para la consulta de operaciones del P1.

Neo4j es fuente de verdad del grafo FOLLOWS y BLOCKS; se prevén intereses para P4.
P1 ejecuta Cypher real para resolver audiencia. P2 implementa follow/unfollow y solicitudes
privadas; P8 implementa trazabilidad. Intereses y sugerencias completas siguen pendientes
para P4. La clave User.id tiene constraint único.

Redis mantiene sorted sets de feed, contadores y notificaciones operativas. P5 almacena
notificaciones y publica eventos Pub/Sub; P1 usa un marcador común de visibilidad, además
de sus referencias de feed. Presencia, mensajería y unread pertenecen al P6 pendiente.
La justificación no depende solamente de replicar contenido para acelerar lecturas.

## Autoridad y duplicación

| Dato | Fuente de verdad | Otras representaciones / responsable |
|---|---|---|
| Perfil/estado de cuenta | MongoDB (implementado para P7) | Estado mínimo Neo4j; P2/P8 deben sincronizarlo |
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
La carga de 50000 registros y el informe final siguen pendientes.

P3 consulta el feed materializado sin recorrer todos los seguidos. Lee bloques cronológicos
de 200 candidatos y congela un ranking por actividad/recencia dentro de cada bloque. Redis
conserva una navegación temporal con TTL fijo de 15 minutos; el cursor firmado liga usuario,
navegación y posición. MongoDB y los contadores se consultan por lote; Neo4j valida juntos
los autores candidatos. Cada página vuelve a comprobar permisos y visibilidad actuales.
No agrega procesos ni modifica los scores originales P1/P2. Ver docs/problems/problem_03.md.

P2 comparte el proceso moderation-worker con P7/P8, sin añadir contenedores. follow_jobs
reserva ambos participantes con un índice único parcial, guarda snapshots y checkpoints y
conserva la reserva si falla la recuperación. Neo4j mantiene el vínculo; Redis materializa
contadores y referencias. Un gate por par coordina entregas P1 y restauraciones P7/P8.
Ver docs/problems/problem_02.md para la secuencia y los límites.

## Moderación P7

MongoDB guarda reportes, jobs y auditoría. La API valida credenciales firmadas y consulta el
rol/estado actual en users. El worker P7 mantiene un solo consumidor mediante flock en su
volumen compartido, siguiendo el despliegue P1. Cada comando reserva atómicamente el post
mediante índice único parcial de jobs activos. Un snapshot durable precede a los efectos.

El estado hidden de MongoDB protege lecturas públicas incluso si Redis está incompleto.
Redis usa un gate separado del commit P1 y Lua atómico para ocultar/restaurar los dos contadores
P5. Los incrementos en vuelo se conservan en claves auxiliares; no se sobrescriben con un
snapshot viejo. Las referencias del feed se eliminan y restauran con sus scores previos.

La fase committing completa reporte/auditoría sin compensar; fases anteriores compensan desde
el snapshot. Los pasos son repetibles tras caídas, hay tres intentos transitorios y recuperación
explícita de failed/compensated. No se añade un nodo Post a Neo4j: actualmente no existe.
Ver docs/problems/problem_07.md y docs/problem_7_moderation_test_guide.md.

## Suspensión y trazabilidad P8

AccountProcessor comparte el consumidor y el mecanismo WorkflowSteps con P7. account_jobs
reserva una cuenta por índice único parcial y conserva checkpoints; account_post_snapshots
separa la audiencia por post para no superar el tamaño máximo de un documento de workflow.
MongoDB cambia estado/auth_version atómicamente; Neo4j conserva las aristas y cambia el estado
derivado. Redis usa gates independientes P7/P8, backup atómico del feed propio/presencia y
contadores preservados hasta retirar el último motivo de ocultamiento.

Las lecturas públicas filtran autores suspendidos en MongoDB incluso con derivados incompletos.
El fan-out P1 conoce el autor y respeta su gate; el snapshot de audiencia permite restaurar
referencias de publicaciones que ya estaban en vuelo. La consulta de traza requiere titular o
rol autorizado y reúne datos reales de los tres motores, devolviendo 503 ante una dependencia caída.
Reactivación no implica restaurar credenciales/presencia. Ver docs/problems/problem_08.md.
