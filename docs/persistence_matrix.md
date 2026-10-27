# Matriz entidad/proceso y motor

Las cantidades corresponden al dataset reproducible base verificado en [dataset.md](dataset.md).
El patrón lectura/escritura expresa la expectativa de uso de la aplicación; no es una tasa
de pedidos medida. Las mediciones de consultas y los tamaños actuales de QA (incluida actividad
posterior a la carga) están en [index_audit.md](index_audit.md) y su JSON; la escritura distribuida
de suspensión/reactivación se midió por separado en [problem_8_performance.md](problem_8_performance.md).

| Entidad/proceso | Patrón de acceso | Volumen base verificado | Lectura/escritura esperada | Consistencia | Motor y estado |
|---|---|---:|---|---|---|
| Usuario/cuenta | UUID, username, email; cambios de estado | 1200 | lectura alta, escritura baja | unicidad y estado de cuenta | MongoDB; identidad implementada para P7 |
| Publicación | UUID, lotes de feed, autor/fecha | 50000 | lectura muy alta, escritura alta | durable, distribución recuperable | MongoDB contenido y jobs; P1 implementado |
| Audiencia de publicación | seguidores por autor; snapshot por operación | 1199 seguidores del creador; límite de implementación 100000 | lectura por publicación, snapshot por pedido | snapshot fijo para completar/revertir | Neo4j origen, MongoDB snapshot; P1 implementado |
| Feed | usuario, bloques recientes, ranking y cursor | 469561 referencias distribuidas | lectura/escritura muy altas | candidatos invisibles hasta commit; filtros actuales por página | Redis sorted sets y navegación con TTL, MongoDB contenido, Neo4j elegibilidad; P1/P2/P3 implementados |
| Reacción | usuario/post; alta/cambio/baja | 30000 | alta/alta | única por par, bloqueo híbrido y coordinación del contador | MongoDB + Redis; P5 implementado con recuperación durable |
| Comentario | post/fecha, append | 15000 | alta/alta | durable e idempotencia por clave y fingerprint | MongoDB + Redis; P5 implementado con recuperación durable |
| Notificación | destinatario/evento; entrega live | proporcional a interacciones | lectura alta, escritura alta | evento persistido y Pub/Sub; revocable en compensación | Redis; P5 implementado |
| Seguimiento y recomendaciones | recorridos 1-2 saltos y amigos en común | 11980 FOLLOWS y 1 BLOCKS | lectura alta, escritura media | evitar duplicados, coordinar estado/feed y validar activos en MongoDB | Neo4j relaciones, MongoDB jobs/estado activo y Redis derivados; P2 y P4 implementados |
| Conversación/mensaje | participantes, historial, lectura propia | 120 grupos, 10000 mensajes | alta/alta | historial durable, entrega/unread coordinados | MongoDB/Redis; P6 implementado |
| Moderación | reportes por post; decidir/revertir | 24 reportes iniciales | lectura media, escritura baja | efectos globales compensables | MongoDB/Redis; P7 implementado, workflow durable y consumidor único |
| Operación/jobs | UUID, pendientes, avance por lote | por operación + historial de pasos | lectura baja, escritura por paso | durable y reanudable | MongoDB; P1 y P5 recuperables en `operations`/`publication_jobs` |

Redis conserva responsabilidad operativa de notificaciones, además de feed y contadores.
Neo4j resuelve relaciones, y MongoDB conserva datos/documentos de negocio y recuperación.
SQL no forma parte del despliegue. La justificación final, escenarios contrafactuales y
mediciones registradas deben incorporarse al informe. Las colas de jobs estaban vacías durante
la auditoría: no se midió un backlog grande ni una tasa sostenida de pedidos concurrentes.

P8 implementa account_jobs, snapshots por post y account_history en MongoDB, estado derivado
User.account_status en Neo4j y gates/backup de feed/presencia en Redis. La consulta de conversaciones
por participante está implementada para trazabilidad; P6 implementa envío, historial paginado,
lectura propia, distribución y reconstrucción de unread desde MongoDB.
