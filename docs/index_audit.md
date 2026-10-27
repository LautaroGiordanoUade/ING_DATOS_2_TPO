# Índices, constraints y mediciones con volumen

Auditoría local del 27/10/2026, sobre `main` 68a91c1 y los cambios de esta rama.
La evidencia está en [index_audit.json](index_audit.json); el comando reproducible es
`python -m app.tools.audit_indexes`. Lee datos y planes; no crea índices ni carga fixtures.

## Condiciones y alcance

Se reutilizó el proyecto aislado `tpo-seed-qa-20261027`, con MongoDB 8.0.34, Redis 7.4.11,
Neo4j 5.26 y Python 3.12.16 en Docker Linux/WSL2. La demostración principal siguió funcionando.
El dataset base `tpo-v1-42` tiene 50000 publicaciones, 1200 usuarios, 30000 reacciones,
15000 comentarios, 10000 mensajes y 120 conversaciones. QA conserva además actividad de
pruebas anteriores: al medir tenía **50241 posts, 1278 usuarios, 30481 reacciones,
15121 comentarios, 10181 mensajes y 144 conversaciones**. No se borró ni volvió a sembrar.

Se midieron lecturas secuenciales desde un contenedor de herramientas: un calentamiento y
cinco muestras por consulta; se informa la mediana en milisegundos del cliente. No incluyen
HTTP, autenticación ni latencia de una operación de escritura distribuida. Los planes MongoDB
usan `executionStats` **sin hint**; la comparación adicional `$natural` fuerza un recorrido
completo sólo como referencia. `PROFILE` Neo4j se ejecuta aparte del cronometraje normal.
Las muestras locales pequeñas permiten describir este entorno, sin prometer un SLA.

## Índices agregados

| Índice | Consulta y motivo |
|---|---|
| `messages.ix_message_history (conversation_id, sequence DESC)` | P6 primera página y cursor. El índice único parcial numérico existente no cubría los predicados `$exists`/`$lt` elegidos por el optimizador. Se conserva la restricción única y se agrega el índice completo para lectura, incluidos documentos antiguos. |
| `posts.ix_post_author_published_id (user_id, published_at DESC, _id DESC)` | P2 ordena por fecha y UUID; agregar el desempate evita ordenar las publicaciones del autor en memoria. También sirve al prefijo de lecturas por autor. |
| `conversations.ix_conversation_participant_created (participant_ids, created_at DESC)` | P8 lista conversaciones por participante y fecha; P6 ya tiene otro índice para ordenar por UUID. |
| `publication_jobs.ix_publication_post (post.id)` | P7/P8 buscan la operación de una publicación; evita recorrer el historial de jobs cuando crezca. |
| `publication_jobs.ix_publication_author_status (post.user_id, operation.status)` | P2 incorpora publicaciones en vuelo del autor, sin recorrer jobs de otros autores. |

Los índices se crean en el arranque normal de la API; los de `publication_jobs` también
se crean en el consumidor de publicaciones. La inicialización central los incluye ahora,
también al cargar el dataset.
Se comprobó repetir la creación sin errores. No se cambian respuestas, reglas de visibilidad,
UUIDs, relaciones ni documentos de negocio. Se conservan índices anteriores: su eliminación
requiere evaluar otros consumidores y no forma parte de esta migración aditiva.

## Comparación MongoDB

| Consulta | Documentos antes → después | Mediana antes → después (ms) | Plan después |
|---|---:|---:|---|
| P2 últimas 20 publicaciones | 43 → 20 | 0,405 → 0,495 | IXSCAN; sin SORT |
| P6 primera página de 21 mensajes | 10181 → 21 | 2,498 → 0,548 | IXSCAN; sin SORT |
| P6 página anterior, secuencia < 60 | 10181 → 21 | 2,394 → 0,492 | IXSCAN; sin SORT |
| P8 conversaciones por fecha | 1 → 1 | 0,328 → 0,405 | IXSCAN; sin SORT |

P2 y P8 reducen trabajo de ordenamiento, pero las muestras **no muestran una mejora de tiempo**
en esas dos lecturas pequeñas. La mejora de P6 se observa tanto en el plan como en la latencia.
El historial real del repositorio, que además carga los autores, pasó de 2,919 a 0,753 ms.
La búsqueda `post.id` tenía sólo un job en QA: el nuevo índice se valida además con 3200 jobs
en una base temporal; no se presenta esa muestra pequeña como benchmark de un historial grande.

Otros resultados después del cambio:

| Lectura | Resultado observado |
|---|---|
| Identidad / post por UUID | 1 documento; `username_1` / `_id_` |
| P3 lote de hasta 20 posts | 20 documentos; `_id_`; 0,441 ms para el find |
| P4 intereses, hasta 200 candidatos | 609 documentos; el optimizador elige `_id_` para mantener el orden; 1,765 ms |
| P5 reacción por post/usuario | 1 documento; índice único compuesto; 0,358 ms |
| P5 comentarios, prefijo de página | 1 documento; índice post/fecha/UUID; 0,296 ms |
| P7 reportes pendientes | 42 documentos; estado/fecha; 0,527 ms |
| P8 posts de un autor | 43 documentos; autor/fecha; 0,463 ms |

El agregado real de comentarios con sus búsquedas de autor/operación tarda 0,662 ms en esta
muestra. Los 20 planes y las muestras completas quedan en el JSON. Las colas P1/P2/P7/P8
estaban vacías: muestran sus planes disponibles, **no prueban rendimiento con backlog**.
Listar todos los 44 reportes hace COLLSCAN/SORT: el índice estado/fecha sirve al filtro por
estado, no al orden global. Se conserva esa decisión con este volumen pequeño. La búsqueda
de intereses tampoco fuerza el índice multikey: la prueba anterior con hint sólo demostraba
que el índice existía; aquí se registra la decisión real del optimizador.

## Neo4j y Redis

La constraint `user_id` impone unicidad sobre `User.id` y su índice RANGE figura ONLINE.
Los cuatro planes perfilados usan `NodeUniqueIndexSeek`: se localiza el usuario y luego se
recorren aristas. La unicidad de cada par FOLLOWS se coordina en P2; esta constraint **no es**
una restricción de unicidad sobre relaciones.

| Consulta Neo4j del repositorio | Mediana (ms) | dbHits de PROFILE |
|---|---:|---:|
| P1 seguidores del creador con 1199 seguidores base | 38,659 | 31146 |
| P4 amigos en común | 7,722 | 27374 |
| P4 candidatos de segundo grado, límite 200 | 57,370 | 1509878 |
| P8 relaciones del creador | 41,585 | 6039 |

El índice evita buscar el nodo inicial por escaneo, pero no elimina el costo de caminos,
bloqueos y deduplicación. El alto dbHits de sugerencias refleja ese trabajo; no se promete
rendimiento constante al aumentar la densidad del grafo.

Redis tenía 256806 claves y el lector elegido un feed de 46584 miembros. La lectura real
del bloque P3 (Lua con búsqueda del límite y hasta 200 candidatos) tuvo mediana 1,600 ms.
Redis usa claves y estructuras ordenadas, sin índices secundarios MongoDB/Cypher.
La medición de escrituras P8 está en [problem_8_performance.md](problem_8_performance.md),
y la carga/recorrido HTTP P1–P8 en [dataset.md](dataset.md).

## Repetir

Primero cargar el dataset siguiendo [dataset.md](dataset.md). Después de reconstruir la imagen
y arrancar API/worker para crear sus índices, desde PowerShell:

```powershell
New-Item -ItemType Directory -Force logs | Out-Null
docker compose exec -T api python -m app.tools.audit_indexes --repeats 5 |
  Out-File -Encoding utf8 logs/index-audit.json
```

El comando requiere un manifiesto completo de la configuración predeterminada; `--seed` permite
otra semilla con esas cantidades. No restablece el estado inicial: después de demostraciones
informa los tamaños actuales. Para medir en QA, usar el proyecto/override aislado correspondiente.
Para repetir las pruebas de planes/compatibilidad: [testing.md](testing.md), seleccionando
`tests/integration/test_index_access_paths.py`. Verifican planes sin hint, igualdad con el
recorrido natural, paginación, unicidad numérica y compatibilidad con documentos sin secuencia.

Validación de esta rama: **337 pruebas backend aprobadas en 92,73 s**, incluidos P1–P8 y los
dos tests nuevos, con MongoDB/Redis/Neo4j reales. Ruff correcto y mypy sin errores en 176
archivos de aplicación. La suite usa MongoDB de pruebas y Redis DB2; las mediciones se
terminaron antes de iniciarla. La interfaz no cambió y sus pruebas no se repitieron.
