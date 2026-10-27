# Recuperación de Redis

Redis conserva datos operativos además de vistas derivadas. Reiniciar el servicio con su
volumen intacto utiliza el AOF configurado en Compose; **no equivale a perder el volumen**.
La recuperación de una pérdida total tiene dos vías: restaurar un respaldo coherente o
reconstruir las vistas desde los motores durables, aceptando las pérdidas que se detallan abajo.

## Fuentes y límites

| Dato Redis | Fuente / tratamiento tras pérdida total |
|---|---|
| Contenido, identidad, roles, `auth_version`, reportes, historial de operaciones | Permanecen en MongoDB; el comando no los modifica. |
| Seguimientos/bloqueos | Permanecen en Neo4j; el comando sólo lee el grafo. |
| Feeds y marcadores de publicación | Se reconstruyen con posts publicados públicos y seguidores aceptados actuales, excluyendo bloqueos, posts ocultos y cuentas suspendidas. |
| Contadores de interacciones | Se cuentan documentos MongoDB. En posts ocultos/suspendidos se conserva el valor real en `:moderation_saved` y se publica cero. |
| Seguidores/seguidos | Se cuentan FOLLOWS aceptados, con la misma semántica de los contadores P2. |
| Sin leer P6 | Se calculan desde secuencias de mensajes y `read_through` MongoDB. Se guardan recibos hasta la secuencia existente, sin publicar mensajes históricos. |
| Gates P7/P8 y entregas diferidas | Se reconstruyen desde estados actuales; snapshots durables también aportan gates negativos para impedir que una reversión reviva un unfollow anterior. |
| Notificaciones P5 y su historial Redis | Requieren respaldo. Las reacciones/comentarios actuales no permiten recuperar exactamente todos los eventos, sus cambios y bajas. No se inventan ni retransmiten notificaciones. |
| Presencia y Pub/Sub | La presencia vuelve con nuevos heartbeats; eventos ya emitidos no se reproducen. |
| Cursores de feed | Se pierden; refrescar inicia otra navegación. |
| Idempotencia guardada sólo en Redis | Requiere respaldo para conservar su ventana original. No reintentar automáticamente pedidos anteriores a la pérdida. Las claves durables P1/P2/P6/P7/P8 siguen en MongoDB. |

La reconstrucción es **lógica**, no una copia exacta del feed anterior. P2 puede haber cargado
sólo 20 posts al seguir a alguien: al reconstruir se incluyen todas las publicaciones públicas
actuales elegibles. Se usa `published_at` como score. No se recupera el snapshot previo de
presencia/feed propio de una suspensión; sus vistas se regeneran según relaciones actuales y
se entregan al reactivar. Los snapshots P7/P8 MongoDB siguen disponibles y se respetan sus gates.

## Antes de intervenir

Trabajar en Docker Linux, un host y el volumen compartido de locks del despliegue soportado.
Detener el ingreso de pedidos y los consumidores:

```powershell
docker compose stop frontend api publication-worker moderation-worker
```

MongoDB, Neo4j y Redis quedan levantados. El flag `--offline` es una declaración del operador:
**no detiene servicios ni comprueba procesos externos**. Durante el procedimiento nadie debe
escribir por herramientas, seeds u otros clientes. El lock sólo excluye otro reconstructor.

El comando rechaza jobs/operaciones no terminales, mensajes pendientes, publicaciones en
preparación, lecturas por sincronizar y cargas de datos incompletas. Si hubo una operación
en vuelo al perder Redis, usar un respaldo coherente e investigar su recuperación con las
herramientas existentes; este comando no intenta recrear sus estados temporales perdidos.
También rechaza FOLLOWS duplicados, posts sin autor/fecha y feeds que superarían 100000 referencias.

## Respaldo del volumen

Hacerlo en un punto sin escrituras de negocio ni operaciones pendientes. Conservar un punto
coherente de **MongoDB, Neo4j y Redis**: un Redis viejo junto con motores más nuevos puede
tener contadores, gates y jobs incompatibles. La copia siguiente cubre sólo el volumen Redis;
no reemplaza el respaldo de los otros motores. Su AOF usa `appendfsync everysec`; ante caída
abrupta puede faltar el último segundo de escrituras. Detenerlo antes de copiar permite que
Redis cierre sus archivos correctamente.

Comandos PowerShell desde el repositorio, con API/workers ya detenidos:

```powershell
$redisContainer = docker compose ps --all -q redis
if (-not $redisContainer) { throw 'No se encontró el contenedor Redis del proyecto' }
$redisVolume = docker inspect --format '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Name}}{{end}}{{end}}' $redisContainer
if (-not $redisVolume) { throw 'No se encontró el volumen /data de Redis' }
$backupDir = (New-Item -ItemType Directory -Force logs/redis-backup).FullName
if (Test-Path (Join-Path $backupDir 'redis-data.tgz')) { throw 'El respaldo ya existe; elegir otra carpeta' }
docker compose stop redis
if ($LASTEXITCODE -ne 0) { throw 'No se pudo detener Redis' }
docker run --rm --network none --read-only `
  -v "${redisVolume}:/data:ro" -v "${backupDir}:/backup" `
  redis:7.4-alpine tar -czf /backup/redis-data.tgz -C /data .
if ($LASTEXITCODE -ne 0) { throw 'La copia falló; revisar antes de continuar' }
```

Guardar el archivo fuera de la PC para tolerar pérdida de disco; `logs/` es sólo la ubicación
local de trabajo, ignorada por Git. Incluye todos los DB Redis del volumen. No subir AOF,
respaldos, credenciales ni datos de usuarios al repositorio.

## Restaurar un respaldo en un volumen nuevo

Mantener frontend/API/workers detenidos y restaurar los motores desde el punto coherente
seleccionado. No extraer sobre un volumen que ya contiene datos. Ejemplo con un nombre nuevo:

```powershell
$restoredVolume = 'niche_redis_recovered_20261027'
docker volume inspect $restoredVolume *> $null
if ($LASTEXITCODE -eq 0) { throw 'Elegir un volumen nuevo; el indicado ya existe' }
docker volume create $restoredVolume
if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el volumen' }
docker run --rm --network none `
  -v "${restoredVolume}:/data" -v "${backupDir}:/backup:ro" `
  redis:7.4-alpine tar -xzf /backup/redis-data.tgz -C /data .
if ($LASTEXITCODE -ne 0) { throw 'La restauración falló' }
```

Crear un override local que asigne ese volumen al servicio Redis:

```powershell
@'
volumes:
  redis_data:
    external: true
    name: niche_redis_recovered_20261027
'@ | Set-Content -Encoding utf8 logs/redis-restored.yaml

docker compose -f compose.yaml -f logs/redis-restored.yaml config --quiet
docker compose -f compose.yaml -f logs/redis-restored.yaml up -d --wait --force-recreate redis
docker compose -f compose.yaml -f logs/redis-restored.yaml exec -T redis redis-cli PING
docker compose -f compose.yaml -f logs/redis-restored.yaml exec -T redis redis-cli DBSIZE
```

Usar siempre ese override al operar el despliegue restaurado. El volumen original se conserva.
Comprobar estado de operaciones, contadores, feeds y notificaciones antes de abrir el ingreso;
el motor Redis arrancando no demuestra consistencia con MongoDB/Neo4j.

## Reconstruir sin respaldo

Esta vía requiere fuentes durables conservadas y quiescentes, ausencia de operaciones en
vuelo y aceptación de las pérdidas anteriores. Usar un volumen Redis **nuevo y vacío**,
asignado con un override como el anterior, sin extraer ningún respaldo en él. El comando no
ejecuta `FLUSHDB`/`FLUSHALL`, no elimina claves ni reemplaza un Redis con datos.

La imagen debe incluir esta versión del comando. Con motores levantados y frontend/API/workers
detenidos, usando el override del volumen nuevo en todos los pasos:

```powershell
docker compose -f compose.yaml -f logs/redis-restored.yaml build api
docker compose -f compose.yaml -f logs/redis-restored.yaml run --rm --no-deps api `
  python -m app.tools.rebuild_redis
docker compose -f compose.yaml -f logs/redis-restored.yaml run --rm --no-deps api `
  python -m app.tools.rebuild_redis --apply --offline
docker compose -f compose.yaml -f logs/redis-restored.yaml run --rm --no-deps api `
  python -m app.tools.rebuild_redis --verify --offline
```

El primer paso es sólo un plan; informa cuántas claves ya tiene el destino. Aplicar exige
vacío mediante una comprobación atómica y escribe en lotes de 500 comandos. Después verifica
cada valor, miembro y score esperado antes de marcar `completed`. MongoDB y Neo4j sólo se leen.
`--verify` vuelve a comprobar las vistas esperadas con las mismas fuentes; no busca claves
extra ajenas al plan ni demuestra consistencia frente a escritores concurrentes.

Si el proceso se interrumpe, mantener todo detenido y repetir con
`--apply --offline --resume`. Repite los SET/ZADD/HSET/SADD de forma idempotente. Sólo admite
un marcador `running` con la misma huella de vistas esperadas. Si cambiaron las fuentes o
la reconstrucción ya terminó, lo rechaza. No borrar el marcador para forzar una continuación.

Al verificar el resultado, levantar la aplicación con el mismo override:

```powershell
docker compose -f compose.yaml -f logs/redis-restored.yaml up -d --build --wait
```

Entrar nuevamente, refrescar el feed, comprobar contadores y mensajes sin leer, verificar un
post moderado y una cuenta suspendida. Una clave de comentario anterior a la pérdida no debe
reintentarse como parte de esta prueba. Ante una verificación fallida, mantener mantenimiento
y conservar los archivos/volúmenes para diagnóstico.

## Evidencia

La validación de esta rama usa únicamente el proyecto QA aislado, bases MongoDB temporales y
DB14/DB15 Redis reservadas para tests que deben estar vacías. Los casos cubren previsualización
sin escrituras, preservación de fuentes, rechazo de destino ocupado, operaciones no terminales,
lock, reanudación, detección de contadores corruptos, moderación/reversión y suspensión/reactivación.
Ver [redis_recovery_validation.json](redis_recovery_validation.json) para resultados y cantidades
del ensayo con más de 50000 publicaciones y de la restauración de un respaldo AOF.

Resultado: **348 pruebas backend aprobadas en 105,48 s**, Ruff correcto y mypy sin errores
en 177 archivos de aplicación. En el dataset grande se reconstruyeron 472590 referencias
de feed sobre 50241 posts y se verificaron 1162816 valores/pertenencias esperados. Los
22,124 s corresponden a escritura y verificación, sin lectura de fuentes ni cálculo del plan.
La restauración física conservó 256806 claves DB0 y se compararon 45502 notificaciones,
100402 contadores y un feed ordenado de 46584 miembros. El respaldo contiene todos los DB,
pero esa comparación funcional se acotó a DB0; no demuestra igualdad de cada valor del volumen.
