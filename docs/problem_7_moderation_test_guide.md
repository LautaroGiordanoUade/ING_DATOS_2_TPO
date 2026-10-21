# Problema 7 — guía reproducible de moderación

Desde P3, las rutas de feed requieren el token del dueño del feed. Para estos ejemplos,
iniciar sesión como `p7_user` y crear con P2 el seguimiento desde
`70000000-0000-0000-0000-000000000001` hacia el autor
`70000000-0000-0000-0000-000000000004`; esperar su operación `completed`.
Cambiar a la credencial moderator para decidir y volver a la del usuario para leer su feed.
El script `verify_problem_07.py` ya prepara ese seguimiento. Detalles: [P3](problems/problem_03.md).

## Arranque

Requiere Docker Desktop con contenedores Linux. Desde la raíz del proyecto, PowerShell:

```powershell
docker compose up -d --build
docker compose ps
Invoke-RestMethod http://localhost:8000/health/ready
```

La respuesta de readiness debe ser `200`, `status: ok` y los tres motores disponibles.
Swagger: <http://localhost:8000/docs>. OpenAPI: <http://localhost:8000/openapi.json>.
Mantener `moderation-worker` activo: las decisiones son asíncronas y responden **202**.
**202 significa aceptado, no completado**. Consultar la operación hasta un estado terminal.
El launcher local también necesita los motores y el worker de Compose.

## Datos reales de desarrollo

```powershell
Get-Content -Raw scripts/seed_problem_07.py | docker compose exec -T api python - --reset
```

El comando imprime JSON con `password`, usuarios, roles, IDs y URL de Swagger.
La contraseña se genera en cada ejecución y sirve para los cuatro usuarios de esta tabla.
No hay una contraseña fija en el código ni tokens universales de desarrollo.
El script requiere `APP_ENV=development`; `--reset` reinicia exclusivamente los cuatro posts
P7 y sus reportes, decisiones, historial e interacciones. Rechaza el reset si hay operaciones
P7 activas: terminarlas o recuperarlas primero. No borra otros datos del proyecto.
Sin `--reset`, conserva los posts existentes y rota las contraseñas de esos usuarios.

| Usuario | Rol | UUID |
|---|---|---|
| p7_user | user | 70000000-0000-0000-0000-000000000001 |
| p7_moderator | moderator | 70000000-0000-0000-0000-000000000002 |
| p7_admin | admin | 70000000-0000-0000-0000-000000000003 |
| p7_author | user | 70000000-0000-0000-0000-000000000004 |

| Prueba | Post UUID |
|---|---|
| Ocultar | 71000000-0000-0000-0000-000000000001 |
| Rechazar | 71000000-0000-0000-0000-000000000002 |
| Revertir / compensar | 71000000-0000-0000-0000-000000000003 |
| Concurrencia | 71000000-0000-0000-0000-000000000004 |

Cada post empieza aprobado, publicado, con dos reacciones y un comentario reales en MongoDB,
contadores Redis **2/1** y una referencia en el feed de `p7_user`.
Todos pertenecen a `p7_author`. Los UUID de reportes y operaciones **se obtienen de las respuestas**;
no se presuponen reportes ya existentes.

## Flujo completo en Swagger

Todas las rutas siguientes empiezan con `/api/v1`.

### 1. Login y visibilidad inicial

Ejecutar `POST /users/login`, reemplazando la contraseña por el valor que imprimió el seed:

```json
{"username":"p7_user","password":"PEGAR_PASSWORD_DEL_SEED"}
```

Esperado: `200`, `access_token` y `token_type: bearer`. Copiar `access_token`.
En **Authorize → HTTPBearer**, pegar solamente el token y confirmar.
El token dura 3600 segundos por defecto. Un token ausente, modificado o expirado produce **401**.

Comprobar con GET:

- `/posts/71000000-0000-0000-0000-000000000001`: **200**, reaction_count=2, comment_count=1.
- `/feeds/70000000-0000-0000-0000-000000000001`: el post figura en `items`.
- `/problems/1/feed-preview/70000000-0000-0000-0000-000000000001`: figura en `post_ids`.
- `/posts/by-user/70000000-0000-0000-0000-000000000004`: lista los cuatro posts.

### 2. Crear reporte

`POST /moderation/reports`:

```json
{
  "post_id":"71000000-0000-0000-0000-000000000001",
  "reason":"spam",
  "description":"Contenido de prueba para problema 7"
}
```

Esperado: **201**, `resolution_status: pending`, `reporter_id` del bearer y un `id` nuevo.
Guardar ese `id` como **REPORT_ID**. `GET /moderation/reports/REPORT_ID` permite consultarlo.
Motivos válidos: `spam`, `abuse`, `hate`, `violence`, `other`.
Un motivo desconocido devuelve **422**, un post inexistente/no publicado **404**,
y un segundo reporte del mismo usuario sobre el mismo post **409**, incluso si el anterior cerró.
El modelo existente no prohíbe reportar contenido propio.

Intentar el paso 4 con este token devuelve **403**. Sin token devuelve **401**.
No se admite proporcionar el rol ni la identidad del moderador en el nuevo payload.

### 3. Login de moderador

`POST /users/login`:

```json
{"username":"p7_moderator","password":"PEGAR_PASSWORD_DEL_SEED"}
```

Reemplazar el token en **Authorize**. `p7_admin` funciona del mismo modo.
El rol y el estado activo se consultan en MongoDB en cada request: cambiar un rol invalida
inmediatamente su permiso, sin esperar que expire el token.

`GET /moderation/reports?status=pending` muestra la cola (hasta 100 reportes).

### 4. Decidir ocultamiento

`POST /moderation/reports/REPORT_ID/decision`:

```json
{"decision":"hide","reason":"Spam confirmado"}
```

Esperado: **202**, `operation_id`, `status: pending` (o el estado actual en un replay).
Guardar **OPERATION_ID**. Consultar repetidamente:

`GET /moderation/operations/OPERATION_ID`

Esperado final: **200**, `status: completed`, snapshot anterior, y pasos
`mongo_hide`, `redis_counters`, `redis_feed` completados. El worker suele resolverlo en segundos.
Repetir el mismo POST devuelve el mismo `operation_id`, sin duplicar efectos.
Cambiar decisión, motivo o escenario de falla en la misma decisión devuelve **409**.
La identidad del primer moderador se conserva aunque otro moderador repita el request.

### 5. Verificar cada efecto

- `GET /moderation/reports/REPORT_ID`: `resolution_status: approved`, decisión `hide`, moderador y fecha.
- `GET /posts/71000000-0000-0000-0000-000000000001`: **404**.
- `GET /feeds/70000000-0000-0000-0000-000000000001`: no contiene el post.
- `GET /problems/3/feed/70000000-0000-0000-0000-000000000001`: tampoco lo contiene.
- `GET /problems/1/feed-preview/70000000-0000-0000-0000-000000000001`: tampoco lo contiene.
- `GET /posts/by-user/70000000-0000-0000-0000-000000000004`: no contiene el post.
- `GET /moderation/posts/71000000-0000-0000-0000-000000000001/state`:
  `moderation_status: hidden`, `feeds: {}`, `counters: {post_reactions: 0, post_comments: 0}`.
- `GET /moderation/history/71000000-0000-0000-0000-000000000001`: una entrada con actor, fecha,
  motivo y snapshot previo. Los errores y compensaciones también quedan en `moderation_jobs`.

No se eliminan documentos de reacciones/comentarios ni se inventa un contador de posts por usuario.
Los dos contadores existentes se ocultan y preservan en Redis. Un incremento/decremento de P5
que ya estaba en vuelo se dirige al valor preservado hasta restaurar la publicación.
Las nuevas interacciones sobre un post oculto devuelven **404**.

### 6. Revertir

`POST /moderation/reports/REPORT_ID/revert`:

```json
{"reason":"Revision: contenido permitido"}
```

Esperado: **202**, una nueva operación. Consultar su `operation_id` hasta **completed**.
Repetir exactamente el POST no incrementa contadores ni duplica referencias.
Volver a ejecutar los GET del paso 5: detalle **200**, contadores **2/1**, post en su feed previo,
reporte **reverted**, dos entradas de historial. Se conservan los scores originales.
Un feed al que el post no pertenecía no recibe el post por revertir.
El estado previo puede ser `pending` o `approved`: se restaura el guardado, no uno fijo.
Revertir un reporte pendiente/rechazado devuelve **409**.

## Rechazo

Crear un reporte del segundo post con `post_id: 71000000-0000-0000-0000-000000000002`.
Con su nuevo REPORT_ID y bearer de moderador, ejecutar:

```json
{"decision":"reject","reason":"No infringe las reglas"}
```

Usar `/moderation/reports/REPORT_ID/decision` y consultar la operación hasta `completed`.
El reporte queda `rejected`; detalle, feed y contadores permanecen **200 / presente / 2 y 1**.

## Fallas, compensaciones y retry

Crear reporte del tercer post (`71000000-0000-0000-0000-000000000003`).
Al decidir `hide` en Swagger, completar el header **X-Fail-At-Step: redis_feed**.
Otros valores para hide: `mongo_hide`, `redis_counters`. La falla ocurre **después** de aplicar
el efecto indicado para verificar también resultados parcialmente aplicados.
En producción cualquier header de inyección devuelve **400**.

El POST devuelve **202**; el error asíncrono aparece al consultar la operación:
`status: compensated`, error explícito, snapshot y pasos. El post termina visible, en su feed,
con contadores **2/1**. El reporte sigue `pending`. Repetir el POST original devuelve esa misma
operación compensada; para volver a intentar el comando, ejecutar como moderador:

`POST /moderation/operations/OPERATION_ID/retry` (sin body).

Esperado: **202**. Un retry de una operación compensada elimina la inyección de falla y vuelve
a ejecutar el mismo comando. Consultarlo hasta `completed`. Dos retries simultáneos: uno **202**
y otro **409**. Una operación aún en ejecución o ya completada no acepta retry (**409**).

Para probar falla durante revert, usar `X-Fail-At-Step: redis_restore` o `mongo_restore`.
La compensación vuelve a dejarlo oculto, sin referencias en feed y con contadores públicos en cero.
El reporte sigue aprobado; retry permite completar el revert.

Cada paso transitorio tiene **3 intentos**, con backoff de 50 y 100 ms. Errores funcionales
no se reintentan. Si además falla la compensación, la operación queda **failed**, mantiene
la exclusión de ese post y guarda `resume_phase: compensating`. Después de recuperar Redis/Mongo,
`/retry` retoma la compensación. Si falla el commit/auditoría, retoma `committing` sin deshacer
una decisión ya comprometida. No borrar locks, jobs ni snapshots para recuperar.

Un reinicio de `moderation-worker` reanuda operaciones `pending`, `running`, `compensating`
y `committing` desde MongoDB. Las pruebas simulan también una interrupción después del efecto
y antes del checkpoint, y después de persistir la auditoría.

## Concurrencia

Con el cuarto post, crear un reporte. Abrir dos pestañas de Swagger con moderador/admin y decidir
`hide` y `reject` casi simultáneamente sobre ese mismo reporte: una respuesta **202**, otra **409**.
Dos decisiones idénticas devuelven la misma operación. Dos reportes diferentes del mismo post
no pueden mantener operaciones activas simultáneamente (índice único parcial).
Revert antes de completar hide devuelve **409**. Un replay de hide durante un revert devuelve
la operación hide original ya completada y no vuelve a ocultar el post.

## Verificación automatizada por HTTP

Este script usa la API levantada y el worker real; debe ejecutarse inmediatamente después de reset:

```powershell
$p7SeedOutput = Get-Content -Raw scripts/seed_problem_07.py | docker compose exec -T api python - --reset
$p7SeedData = $p7SeedOutput | ConvertFrom-Json
$env:P7_PASSWORD = $p7SeedData.password
try { .\.venv\Scripts\python.exe scripts/verify_problem_07.py } finally { Remove-Item Env:P7_PASSWORD }
```

Salida final: `http_smoke: passed`, con IDs reales de reportes y operaciones.
Comprueba Swagger/OpenAPI, login, roles, ocultamiento/feed/contadores, doble revert,
rechazo, compensación y decisiones concurrentes. Deja esos fixtures en el estado probado;
volver a hacer `--reset` para comenzar una sesión manual limpia.

## Suite y alcance de garantías

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy app tests
$env:RUN_INTEGRATION_TESTS = "1"
.\.venv\Scripts\python.exe -m pytest -q
Remove-Item Env:RUN_INTEGRATION_TESTS
```

Las pruebas P7 usan una base `test_p7_<uuid>` diferente por test y claves Redis con UUID propios.
No usan mocks de repositories y limpian solamente sus datos. El placeholder de integración de
los problemas restantes no se usa como evidencia de P7. Sin la variable se omiten los tests externos.

La implementación soporta el despliegue **Docker Linux en un host**, con todos los consumidores
P7 compartiendo `moderation_worker_lock`. `flock` limita a un consumidor activo y el SO libera
el bloqueo al terminarlo. Múltiples API pueden encolar gracias a restricciones MongoDB.
No desplegar consumidores en hosts/volúmenes independientes: requeriría fencing distribuido.
El límite de audiencia es 100000 referencias por post, coherente con P1; snapshot mediante SCAN
puede resultar costoso en feeds muy grandes. No se promete recuperación ante pérdida de volúmenes
MongoDB/Redis. Redis conserva el límite previo de AOF cada segundo.

El feed expuesto aquí es cronológico y básico: ranking personalizado, paginación por cursor y
recomendaciones completas siguen siendo P3/P4. No existen endpoints reales de búsqueda para
proteger; todas las lecturas de posts implementadas pasan por el filtro de moderación.
Neo4j actualmente no almacena nodos Post, por lo que no existe un derivado de contenido que actualizar.
El preview demo P8 conserva sus otros datos simulados, pero sus publicaciones recientes se
consultan realmente y respetan el ocultamiento. Las limitaciones previas de locks y compensaciones de P5 ante caída de su propia API siguen
explicadas en `docs/problem_05_consistency.md`; P7 no usa esos locks para su recuperación.
