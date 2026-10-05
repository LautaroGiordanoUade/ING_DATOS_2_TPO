# Matriz motor / entidad

| Entidad/proceso | Lectura | Escritura | Volumen | F. lectura | F. escritura | Consistencia | Principal | Secundarios | Justificación |
|---|---|---|---|---|---|---|---|---|---|
| Usuario/cuenta | por UUID, username, email | baja/media | media | alta | baja | fuerte | PostgreSQL | referencias UUID | unicidad y estado crítico |
| Moderación | workflow/reportes | baja | media | media | baja | fuerte local | PostgreSQL | MongoDB, Redis | decisión administrativa y efectos derivados |
| Publicación | lotes de feed/autor | alta | alta | muy alta | alta | durable | MongoDB | Redis; Neo4j opcional | documentos y volumen |
| Comentario | por post con cursor | alta | muy alta | alta | alta | TODO(TP) | MongoDB | Redis contador | crecimiento independiente |
| Reacción | por usuario/post | alta | muy alta | alta | alta | unicidad lógica | MongoDB | Redis contador | historial/interacción y vista operacional |
| Grafo social | recorridos 1–2 saltos | aristas | alta | alta | media | TODO(TP) | Neo4j | Redis contadores | consultas de relaciones |
| Feed | cursor/ranking | fan-out | muy alta | muy alta | muy alta | eventual TODO(TP) | Redis | MongoDB contenido | baja latencia y sorted sets candidatos |
| Conversación/mensaje | historial | append | muy alta | alta | muy alta | durable | MongoDB | Redis entrega/unread | documentos y lectura por participante |
| Operación multi-motor | por operation_id | por paso | media | baja | media | auditable | PostgreSQL propuesto | memoria sólo demo | estado durable y consultable; SQL TODO(TP) |

