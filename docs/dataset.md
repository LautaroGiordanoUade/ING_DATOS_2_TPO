# Dataset reproducible del TPO

Implementa la sección 7 de la consigna: **50.000 publicaciones en una misma entidad**,
no una suma de documentos, nodos y referencias duplicadas entre motores.

## Cantidades predeterminadas

| Datos de negocio | Cantidad | Motor |
|---|---:|---|
| Usuarios completos | 1.200 | MongoDB + UUID compartido en Neo4j |
| Publicaciones | 50.000 | MongoDB |
| Reacciones únicas por usuario/publicación | 30.000 | MongoDB |
| Comentarios | 15.000 | MongoDB |
| Grupos | 120 | MongoDB |
| Mensajes con secuencia y remitente miembro | 10.000 | MongoDB |
| Reportes pendientes | 24 | MongoDB |
| Seguimientos aceptados/pendientes | 11.980 | Neo4j |
| Bloqueo | 1 | Neo4j |

Redis contiene las vistas coherentes de feeds, marcadores de publicación, destinatarios,
contadores de seguidores/seguidos, reacciones/comentarios y no leídos por participante.
También incluye notificaciones históricas por interacción, sin emitir Pub/Sub por actividad
antigua. No crea presencia artificial ni publica trabajos falsos como si hubieran pasado por API.
La carga por lotes es un fixture inicial; las operaciones nuevas usan los workflows reales.

Hay comunidades temáticas, intereses, cuentas públicas/privadas, roles de desarrollo,
solicitudes pendientes y un bloqueo sin seguimiento simultáneo. El creador `0000` tiene
1.199 seguidores; el lector `0001` sigue más de mil cuentas, contando aceptadas y pendientes.
Todos comienzan activos; suspender/reactivar y ocultar/revertir se ejecutan mediante P7/P8.

## Cargar desde Docker (PowerShell)

Primero construir/levantar el proyecto según README. La imagen de API incluye estos comandos;
no hacen falta Python ni dependencias en Windows. Por defecto **sólo se muestra el plan**:

```powershell
docker compose up -d --build
docker compose exec api python -m app.tools.seed_data
```

Para cargar, elegir una contraseña de al menos 12 caracteres, común a las cuentas sintéticas.
Se transmite por entorno; no se guarda en Git ni aparece en la salida del generador:

```powershell
$env:SEED_PASSWORD = Read-Host 'Contraseña de las cuentas sintéticas (mínimo 12 caracteres)'
docker compose exec -e SEED_PASSWORD api python -m app.tools.seed_data --apply
Remove-Item Env:SEED_PASSWORD
docker compose exec api python -m app.tools.seed_data --verify
```

La salida informa cantidades verificadas, SHA-256 reproducible, UUID/username de las primeras
cuentas y ejemplos de publicación/grupo. Con `--seed 42`:

| Username | Uso |
|---|---|
| `tpo42_0000` | Creador con miles de seguidores; publica y participa en el primer grupo |
| `tpo42_0001` | Lector con feed extenso y miembro del primer grupo |
| `tpo42_0002` | Cuenta privada con solicitudes; miembro del primer grupo |
| `tpo42_0003` | Moderador para P7 y P8 |
| `tpo42_0004` | Administrador para P7 y P8 |
| `tpo42_0005` | Cuenta privada para suspensión/reactivación y trazabilidad |

Los roles son fixtures exclusivos de development/testing. El registro de la API no concede roles.
La carga se rechaza en production. Se usa el hash de contraseña existente, con salt aleatorio:
el SHA-256 del dataset cubre datos de negocio y relaciones, no hashes de credenciales.

## Repetición, interrupción y coexistencia

- UUIDv5, fechas y contenido dependen de una versión y semilla fijas; no del reloj ni del orden
  de los lotes. `--batch-size` modifica sólo el tamaño del lote.
- Un manifiesto MongoDB `seed_datasets` conserva configuración, checksum, estado y verificación inicial.
- Una carga interrumpida repite upserts por lotes sin duplicar. Reanudar requiere la misma contraseña.
  Durante una carga incompleta no usar sus cuentas en la API ni editar sus documentos.
- Cuando terminó, repetir `--apply` devuelve `already_loaded`: **no resetea** ediciones, reportes,
  contraseña o seguimientos hechos en la demostración. `initial_verification` es la evidencia de
  la carga original, no una nueva medición del estado actual.
- Cambiar cantidades con una semilla existente se rechaza. Elegir otra `--seed` crea otra población
  independiente; no modifica la anterior. No hay `--reset`, borrado de colecciones, `FLUSHDB`
  ni eliminación de nodos ajenos. Colisiones de UUID/username/email se rechazan.
- No se agrega un contenedor de inicialización ni un worker. El comando es explícito y usa
  el volumen de locks de Compose para excluir dos cargas simultáneas de la misma semilla.
- `--verify` comprueba el **estado inicial**: cantidades, referencias, UUID entre motores,
  relaciones, contadores, feeds/destinatarios con scores, secuencias y unread. Ejecutarlo antes
  de las demostraciones. Una operación posterior puede modificar legítimamente esa distribución;
  este comando no es el procedimiento general de reconstrucción de Redis.

## Ejercitar los ocho problemas sobre la carga

Este recorrido agrega actividad real y modifica relaciones/estados temporalmente; es distinto
de `--verify`, que sólo lee. Publica, sigue/deja de seguir, pagina, consulta sugerencias,
reacciona/comenta, envía/lee mensajes, oculta/revierte y suspende/reactiva.

```powershell
$env:SEED_PASSWORD = Read-Host 'Contraseña usada al cargar'
docker compose exec -e SEED_PASSWORD api python -m app.tools.verify_dataset --exercise
Remove-Item Env:SEED_PASSWORD
```

Informa cada problema aprobado y consulta los trabajos hasta su estado terminal. El timeout
por operación es configurable con `--operation-timeout` (600 segundos por defecto).
Un timeout indica que la consulta dejó de esperar; no cancela ni declara fallida la operación.

## Pruebas reducidas y límites

Se pueden variar `--users`, `--posts`, `--reactions`, `--comments`, `--messages`,
`--conversations`, `--reports`, `--seed` y `--batch-size`. Para aplicar menos de 50.000
publicaciones se exige `--allow-small`; esa carga se informa como **insuficiente para la entrega**.
Ejemplo sin escritura:

```powershell
docker compose exec api python -m app.tools.seed_data --users 12 --posts 40 --reactions 80 --comments 20 --messages 30 --conversations 4 --reports 3 --seed 43
```

La carga no es una transacción distribuida: ante un corte queda `loading` y debe reanudarse
antes de utilizar esa población. Requiere un único host Linux y el volumen compartido de Compose;
no garantiza coordinación de loaders en varios hosts ni recuperación de volúmenes perdidos.

## Evidencia y siguiente prioridad

Ver [dataset_validation.json](dataset_validation.json) para cantidades/checksum de la carga.
La carga inicial de 50.000 publicaciones se ejecutó y verificó en aproximadamente 19,4 segundos
en el equipo de desarrollo. Es una observación local de carga, no una garantía de latencia.
Pasaron 100 pruebas: 99 unitarias del backend y una integración nueva de carga/reanudación.
Ruff correcto y mypy sin errores en los 174 archivos de `app`.

El recorrido P1–P7 pasó sobre el volumen generado. P8 superó la espera inicial de 60 segundos:
el worker continuó avanzando, sin error, y terminó la suspensión de 42 publicaciones en
256,9 segundos. Se continuó la consulta del mismo trabajo y se ejecutó la reactivación,
comprobando el estado activo y la visibilidad restaurada. No se canceló ni se duplicó la suspensión.
Se identificaron recorridos repetidos del espacio de
claves Redis por publicación. Debe medirse y optimizarse en el **paso 2 del plan**, conservando
las garantías de P7/P8; ampliar la espera del smoke no resuelve ese costo.
