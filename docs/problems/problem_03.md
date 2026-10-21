# Problema 03 — Feed personalizado

Implementado reutilizando el feed que P1/P2 materializan en Redis. No agrega contenedores,
workers ni una nueva copia permanente del contenido.

## Orden y paginación

Se toman bloques de hasta 200 candidatos del ZSET del usuario, en orden descendente de
`(timestamp, UUID)`. Dentro de cada bloque, las publicaciones elegibles se ordenan por:

```text
puntuación = fecha UTC en segundos + 60 × min(60, reacciones + 2 × comentarios)
desempate = fecha UTC, UUID (descendentes)
```

La actividad adelanta hasta una hora a una publicación; los comentarios pesan el doble.
El ranking es local a cada bloque reciente, no un ranking global ni un modelo de intereses.
Los bloques anteriores se consultan al agotarse los actuales, sin limitar el historial a 200 posts.

La API devuelve hasta 20 publicaciones y `next_cursor`, ahora una cadena opaca firmada.
Sin cursor se crea una navegación nueva con vigencia fija de 15 minutos. Cada bloque se
ordena al consultarlo por primera vez; su orden queda congelado para esa navegación. Los
contadores de las páginas se leen nuevamente, por lo que muestran los valores actuales.
Los bloques aún no consultados se ordenan con los contadores de su primera lectura.

Redis guarda metadata y bloques como campos de un único hash `feed-page:{session_id}`.
El TTL fijo se aplica a todo el hash: no puede expirar un bloque aislado mientras sobrevive
el resto de la sesión. Una escritura HSETNX atómica elige un solo orden si dos requests
materializan el mismo bloque simultáneamente. Leer páginas no prolonga el vencimiento.

El cursor contiene usuario, navegación, vencimiento, bloque y posición. Usa HMAC con dominio
`feed-v1`, separado del token de login. Se valida firma, formato, propietario y expiración;
no se acepta como credencial. Una navegación vencida o perdida devuelve 410 para refrescar.

La búsqueda del bloque siguiente usa el último `(timestamp, UUID)` cronológico examinado,
no el último score de relevancia mostrado. Una búsqueda binaria en Redis funciona incluso
si se eliminó ese post o hay más de 200 publicaciones con la misma fecha. Cada ejecución
devuelve como máximo 201 referencias (una para detectar continuación), sin descargar todo
el feed. No se modifica el ZSET original P1/P2.

Las publicaciones nuevas posteriores al inicio se ven al refrescar. No es un snapshot
transaccional de todo el historial: un trabajo P1 antiguo que termina tarde o un cambio de
seguimientos puede alterar qué candidatos antiguos existen cuando se consulta otro bloque.
Los bloques ya guardados conservan su orden y los límites cronológicos evitan repetir IDs
por el desplazamiento de posiciones del ZSET.

## Permisos y lectura por lote

Las rutas `/api/v1/feeds/{user_id}` y `/api/v1/problems/3/feed/{user_id}` ejecutan el mismo flujo:
requieren login y solo permiten consultar el feed propio, incluso a moderator/admin.

MongoDB carga el contenido por lote, excluyendo posts pendientes, privados, moderados y
autores suspendidos. Neo4j verifica juntos los autores candidatos: seguimiento aceptado,
ambas cuentas activas y ausencia de bloqueos en cualquiera de las direcciones. Redis verifica
pertenencia al feed, commit P1 y gates P2/P7/P8. Las solicitudes privadas pendientes no dan acceso.

Reacciones y comentarios se leen con MGET por lote. Se vuelve a comprobar contenido y
elegibilidad después de los contadores, antes de armar la respuesta. Un bloque guardado no
otorga permisos permanentes: unfollow, moderación y suspensión se respetan en cada página.
Como lectura de tres motores sin transacción global, no se promete un instante atómico común
si otro proceso cambia datos exactamente entre las últimas verificaciones y la respuesta.

El trabajo se acota a diez bloques por request. Si hay muchos candidatos retirados, se
continúa rellenando hasta 20 elementos o hasta terminar el historial/presupuesto. Al agotar
el presupuesto se devuelve `next_cursor` aun con una página parcial o vacía; el cliente debe
continuar mientras ese campo no sea null. No se descartan los bloques antiguos restantes.

Una dependencia caída devuelve 503, sin presentar una respuesta incompleta como éxito.
Al ser una lectura no requiere compensaciones ni jobs durables; las navegaciones temporales
se recrean al refrescar y desaparecen por TTL.

## Swagger y prueba HTTP

1. Registrar usuarios e iniciar sesión en `POST /api/v1/users/login`.
2. Copiar `access_token` en **Authorize** y crear un seguimiento aceptado con P2.
3. Publicar con P1 y esperar `completed`.
4. Ejecutar `GET /api/v1/feeds/{user_id}` con el UUID del usuario autenticado.
5. Copiar el `next_cursor` completo en el parámetro `cursor` para obtener la página siguiente.
6. Para refrescar, volver a ejecutar sin cursor. Al terminar, `next_cursor` es null.

Errores: 401 sin credencial/cuenta suspendida; 403 al consultar otro usuario; 422 cursor
alterado, de otro usuario o inválido; 410 navegación vencida/perdida; 503 motor indisponible.
Los scripts HTTP de P7/P8 se adaptaron a la autenticación del feed; el de P7 también crea un
seguimiento real de sus usuarios de prueba en vez de depender solo de referencias Redis.

```powershell
docker compose up -d --build
Get-Content -Raw scripts/validar_problema3.py | docker compose exec -T api python -
```

El script crea dos usuarios QA con credenciales aleatorias que no imprime, publica 45 posts
con P1 y prueba páginas 20/20/5, cursores repetidos, contadores P5 actuales, una publicación
nueva al refrescar y unfollow P2 entre páginas. Imprime tiempos HTTP observados y conserva
esos datos nuevos, sin reemplazar datos anteriores. Son mediciones locales, no un SLA.

`tests/integration/test_problem_03_feed.py` usa los tres motores con registros aislados:
ranking y máximo de bonificación, fechas iguales, borrado del límite, navegación concurrente,
cursor propio/vencido, cambios de visibilidad, gates P1/P2/P7/P8, presupuesto de escaneo y
fallas de dependencias. Incluye un escenario de 2001 seguimientos y comprueba que las lecturas
de contenido siguen siendo por lotes de hasta 200 candidatos, sin consultas por cada seguido.

Validación local del 21/10/2026: suite completa con 232 pruebas aprobadas (29 nuevas P3),
incluidas las regresiones P2/P7/P8; mypy y Ruff sin errores. La limpieza de los escenarios
grandes se comprobó por separado con dos pruebas adicionales. Con 2001 seguimientos y 250
posts, una ejecución del caso de uso demoró 32,4 ms y leyó contenido en tres lotes de 200.
El smoke HTTP sobre Compose reconstruido pasó páginas 20/20/5, actualizaciones P5 y unfollow
P2; sus seis lecturas demoraron entre 4,59 y 13,75 ms. Son observaciones de esta PC y carga,
no un benchmark exhaustivo ni una garantía de latencia.

