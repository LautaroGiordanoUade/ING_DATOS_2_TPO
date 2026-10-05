# Arquitectura de persistencia

## Límites

Domain contiene entidades y necesidades del negocio. Application coordina operaciones usando esos
contratos. Infrastructure conoce drivers y modelos técnicos. Presentation traduce HTTP a casos de
uso. Las dependencias apuntan hacia Domain/Application.

## PostgreSQL

Almacena usuarios, credenciales hash, estados críticos y reportes de moderación. Unicidad, checks,
foreign keys y transacciones locales justifican el motor. No almacena posts, mensajes ni aristas:
forzar esos patrones relacionales concentraría volumen y haría redundantes los demás motores.

## MongoDB

Es fuente de verdad del texto/multimedia de publicaciones, comentarios, conversaciones y mensajes.
Los comentarios se separan de `posts`: pueden crecer sin límite y necesitan paginación/índices
independientes. `read_by` representa lectura por participante. PostgreSQL no es el principal porque
el volumen y la evolución documental dominan; Redis no conserva historial; Neo4j no es un almacén
de contenido.

## Redis

Mantiene feed materializado, contadores operativos, notificaciones, presencia, entrega inmediata,
unread, sesiones e idempotencia. Son responsabilidades de dominio de baja latencia, no una copia-
cache transparente. No es fuente de verdad del historial durable. Las estructuras/comandos finales,
TTL y reconciliación son `TODO(TP)`.

## Neo4j

Es fuente de verdad para `FOLLOWS`, `INTERESTED_IN`, `BLOCKS` e `INTERACTED_WITH`. Puede incluir un
nodo `Post` liviano con UUID y metadata mínima para navegación; MongoDB conserva el contenido
canónico. Neo4j evita expresar recorridos de segundo grado y exclusiones como joins complejos, pero
no sustituye integridad de cuenta ni almacenamiento documental.

## Duplicación y autoridad

| Dato duplicado | Copias | Fuente de verdad |
|---|---|---|
| `user_id` | cuatro motores y referencias | UUID asignado por la aplicación; perfil en PostgreSQL |
| Estado mínimo de cuenta | filtros de grafo/operación | PostgreSQL |
| `post_id` y metadata mínima | feed Redis / nodo Neo4j opcional | publicación MongoDB |
| Contadores | Redis y datos base | dato base en MongoDB/Neo4j; Redis es vista operativa |
| Participantes/unread | MongoDB/Redis | participantes e historial en MongoDB; unread operativo en Redis |

No hay transacción ACID global. `OperationContext`, `OperationStep`, registro consultable y
compensación inversa aportan el mecanismo. La demo usa memoria y expone consulta por UUID; el
adaptador durable propuesto es PostgreSQL mediante `PostgresOperationLogRepository`. Su upsert, el
orden, retry, rollback e idempotencia concretos permanecen `TODO(TP)`.

