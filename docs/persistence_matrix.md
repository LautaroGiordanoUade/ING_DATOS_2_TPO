# Matriz entidad/proceso y motor

Las cantidades siguientes son objetivos de prueba/estimaciones de diseño, no datos ya cargados
ni mediciones de rendimiento. El generador general aún no implementa ese volumen.

| Entidad/proceso | Patrón de acceso | Volumen objetivo | Lectura/escritura | Consistencia | Motor y estado |
|---|---|---:|---|---|---|
| Usuario/cuenta | UUID, username, email; cambios de estado | 1000+ | lectura alta, escritura baja | unicidad y estado de cuenta | MongoDB; pendiente |
| Publicación | UUID, lotes de feed, autor/fecha | 50000+ | lectura muy alta, escritura alta | durable, distribución recuperable | MongoDB contenido y jobs; P1 implementado |
| Audiencia de publicación | seguidores por autor; snapshot por operación | miles por creador, límite 100000 | lectura por publicación, snapshot por pedido | snapshot fijo para completar/revertir | Neo4j origen, MongoDB snapshot; P1 implementado |
| Feed | usuario y orden temporal; fan-out | posts x seguidores | lectura/escritura muy altas | candidatos invisibles hasta commit | Redis sorted sets; P1 escribe, P3 pendiente |
| Reacción | usuario/post; alta/cambio/baja | proporcional a publicaciones | alta/alta | única por par y coordinación del contador | MongoDB + Redis; P5 implementado con límites documentados |
| Comentario | post/fecha, append | 50000+ candidato a mayor volumen | alta/alta | durable e idempotencia por clave | MongoDB + Redis; P5 implementado |
| Notificación | destinatario/evento; entrega live | proporcional a interacciones | lectura alta, escritura alta | evento persistido y Pub/Sub; no exactly-once | Redis; P5 implementado |
| Seguimiento/intereses | recorridos 1-2 saltos | 10000+ relaciones | lectura alta, escritura media | evitar duplicados y coordinar estado/feed | Neo4j; lectura de audiencia P1, resto pendiente |
| Conversación/mensaje | participantes, historial, lectura propia | 50000+ mensajes | alta/alta | historial durable, entrega/unread coordinados | MongoDB/Redis; P6 pendiente |
| Moderación | reportes por post; decidir/revertir | fracción de posts | lectura media, escritura baja | efectos globales compensables | MongoDB/Redis; P7 pendiente |
| Operación/jobs | UUID, pendientes, avance por lote | por operación + historial de pasos | lectura baja, escritura por paso | durable y reanudable | MongoDB; P1 recuperable, P5 registro durable |

Redis conserva responsabilidad operativa de notificaciones, además de feed y contadores.
Neo4j resuelve relaciones, y MongoDB conserva datos/documentos de negocio y recuperación.
SQL no forma parte del despliegue. La justificación final, escenarios contrafactuales y
mediciones con el dataset completo deben incorporarse al informe.
