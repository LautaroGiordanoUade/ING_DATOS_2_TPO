# Problema 8: suspension y trazabilidad — guia Swagger

## Arranque y datos

Desde la raiz del repositorio, PowerShell, con Docker Desktop Linux activo:

```powershell
docker compose up -d --build
Get-Content -Raw scripts/seed_problem_08.py | docker compose exec -T api python -
```

Swagger: <http://localhost:8000/docs>. Readiness: <http://localhost:8000/health/ready>.
Mantener `moderation-worker` activo: procesa P7 y P8 bajo el mismo bloqueo de consumidor.
El seed reinicia exclusivamente los fixtures P8 y rechaza hacerlo con operaciones activas.
Requiere `APP_ENV=development`; no modifica otras cuentas/posts/grafos del proyecto.
Imprime una contraseña aleatoria compartida por los cuatro usuarios de desarrollo. No hay tokens
ni contraseñas de prueba fijos en produccion. Ejecutarlo otra vez rota esa contraseña y reinicia P8.

| Usuario | Rol | UUID |
|---|---|---|
| p8_target | user | 80000000-0000-0000-0000-000000000001 |
| p8_moderator | moderator | 80000000-0000-0000-0000-000000000002 |
| p8_admin | admin | 80000000-0000-0000-0000-000000000003 |
| p8_observer | user | 80000000-0000-0000-0000-000000000004 |

Posts:

- `81000000-0000-0000-0000-000000000001`: target, visible, contadores 2 reacciones/1 comentario.
- `81000000-0000-0000-0000-000000000002`: target, previamente oculto por moderacion; no debe reaparecer al reactivar.
- `81000000-0000-0000-0000-000000000003`: observer, visible, presente en el feed propio de target.

Conversacion real MongoDB: `82000000-0000-0000-0000-000000000001`, target y observer.
Neo4j: moderator sigue a observer; observer sigue a target. Target aparece como sugerencia de
segundo grado para moderator. Target empieza con presencia Redis de 120 segundos.

## 1. Login como target y trazabilidad inicial

Todas las rutas siguientes llevan prefijo `/api/v1`.

`POST /users/login`:

```json
{"username":"p8_target","password":"PEGAR_PASSWORD_DEL_SEED"}
```

Esperado **200** con `access_token`. En Authorize/HTTPBearer pegar el token sin prefijo adicional.
Guardar este token para probar su revocacion mas adelante.

`PUT /accounts/me/presence`, sin body: **204**, renueva presencia 120 segundos.

`GET /accounts/80000000-0000-0000-0000-000000000001/trace`: **200** con:

- perfil real activo, sin hash ni correo privados;
- relaciones Neo4j y follower observer;
- publicaciones recientes visibles;
- `post_states` con publicaciones visibles/ocultas, flags y estado de publicacion;
- una conversacion real con sus participantes;
- presencia `true` e historial inicial vacio.

Un usuario puede consultar su propia traza. Consultar la de otra persona requiere moderator/admin.
El endpoint previo `/problems/8/trace/{user_id}` aplica exactamente los mismos permisos.

Comprobar tambien:

- `GET /posts/81000000-0000-0000-0000-000000000001`: **200**, contadores 2/1.
- `GET /feeds/80000000-0000-0000-0000-000000000002`: contiene ese post.
- `GET /feeds/80000000-0000-0000-0000-000000000001`: contiene el post de observer.
- `GET /problems/4/recommendations/80000000-0000-0000-0000-000000000002`: contiene target.

## 2. Login de moderador

`POST /users/login`:

```json
{"username":"p8_moderator","password":"PEGAR_PASSWORD_DEL_SEED"}
```

Cambiar el bearer en Authorize. `p8_admin` tambien puede suspender/reactivar.
Sin bearer: **401**. Usuario normal: **403**. El servidor obtiene identidad y rol de MongoDB.
La autosuspension/autoreactivacion devuelve **409** para evitar bloquear al actor administrativo.

## 3. Suspender

`POST /accounts/80000000-0000-0000-0000-000000000001/suspend`

Header opcional `Idempotency-Key: p8-suspend-1`.

```json
{"reason":"Incumplimiento confirmado de las reglas"}
```

Esperado **202** con `operation_id` real y estado `pending` (o estado actual si es replay).
Guardar ese ID; consultar `GET /accounts/operations/OPERATION_ID` hasta `completed`.
**202 no significa que todos los efectos ya terminaron.**

Pasos guardados: `mongo_suspend`, `redis_close_presence`, `neo4j_suspend`, `redis_remove_posts`.
Una respuesta `compensated` indica que el comando fallo y se restauro; `failed` requiere recuperar
una dependencia y ejecutar retry. El error y los intentos quedan en el job MongoDB.

La ruta anterior `POST /problems/8/suspend` conserva payload `{user_id,reason}` y respuesta **204**,
pero ahora ejecuta el flujo real, exige rol y entrega `Operation-Id` y `Location` como headers.

## 4. Verificar cada efecto

Con bearer administrativo:

- `GET /accounts/80000000-0000-0000-0000-000000000001/trace`: perfil suspended, presence false,
  recent_posts vacio; `post_states` conserva ambos posts y marca suspension_hidden=true.
  La conversacion y las relaciones siguen trazables, sin borrar sus documentos/aristas.
- `GET /accounts/80000000-0000-0000-0000-000000000001/history`: un evento con actor, motivo,
  estado anterior/posterior y operation_id.
- `GET /accounts/80000000-0000-0000-0000-000000000001/presence`: online=false.
- `GET /moderation/posts/81000000-0000-0000-0000-000000000001/state`: feeds vacio, contadores 0/0.

Lecturas publicas:

- detalle del post 1 y perfil target: **404**;
- `/posts/by-user/TARGET_ID`: lista vacia;
- feeds de moderator y target: no contienen los elementos retirados;
- preview P1 y feed P3 tampoco muestran posts del autor suspendido;
- recomendaciones para moderator ya no contienen target.

Con el bearer anterior de target, intentar heartbeat o consulta privada devuelve **401**.
El login de target tambien devuelve **401** mientras siga suspendido.
Los endpoints anteriores P1/P5 rechazan actividad de un usuario conocido suspendido aunque
reciban su UUID por payload. Las escrituras P5 ya en vuelo conservan sus contadores correctamente.

## 5. Reactivar

`POST /accounts/80000000-0000-0000-0000-000000000001/reactivate`

Header `Idempotency-Key: p8-reactivate-1`.

```json
{"reason":"Revision administrativa: cuenta rehabilitada"}
```

Esperado **202**; consultar la nueva operacion hasta `completed`.
El post 1 vuelve al mismo feed/score y a contadores 2/1. El post 2 continua oculto por P7.
Las sugerencias vuelven a incluir target y su propio feed recupera el post de observer.
El historial conserva ambos eventos. MongoDB/Neo4j muestran active.

**No se restauran sesiones ni presencia automaticamente.** El token viejo sigue revocado por
`auth_version`. Hacer login otra vez como target y usar el nuevo bearer para heartbeat.
Una compensacion puede devolver presencia previa solo si su TTL original sigue vigente;
no resucita presencia expirada ni vuelve validos tokens revocados.

## 6. Idempotencia y concurrencia

- Repetir el mismo comando con la misma key devuelve la misma operacion.
- Cambiar el motivo con esa key: **409**.
- Dos suspensiones iguales concurrentes sin key tambien comparten una operacion activa.
- Dos keys distintas para operaciones concurrentes del mismo usuario: **409** por exclusion unica.
- Reactivar antes de finalizar la suspension: **409**.
- Un replay de una suspension completada despues de reactivar devuelve la operacion antigua y no
  vuelve a suspender. Para un nuevo ciclo usar una nueva key.
- Dos reactivaciones iguales no duplican feeds ni contadores.
- P7 y P8 comparten consumidor, pero conservan gates independientes: revertir P7 durante P8 no
  publica contenido de una cuenta suspendida; reactivar P8 no revierte una moderacion P7.
- Fan-out P1 que ya estaba en vuelo respeta el gate de cuenta; su audiencia durable permite
  recuperar referencias al reactivar.

## 7. Fallos, compensacion y recovery

En desarrollo, header `X-Fail-At-Step` en la suspension:

`mongo_suspend`, `redis_close_presence`, `neo4j_suspend`, `redis_remove_posts`.

En reactivacion:

`redis_restore_posts`, `neo4j_reactivate`, `redis_reactivate`, `mongo_reactivate`.

La falla ocurre despues del efecto indicado. Se espera `compensated` con estado y derivados
restaurados, excepto revocacion de credenciales (se mantiene por seguridad). Los snapshots
por post estan en MongoDB; el backup atomico del feed propio/presencia esta en Redis con AOF.

Cada error transitorio tiene tres intentos con backoff 50/100 ms. Errores funcionales no se
reintentan. Si falla compensar, `failed` conserva el bloqueo logico y `resume_phase`:

`POST /accounts/operations/OPERATION_ID/retry`, sin body, como moderator/admin.

Esperado **202** y recuperacion de la fase pendiente. Dos retries simultaneos: **202 / 409**.
Un comando `compensated` ya termino: para intentarlo de nuevo, quitar la inyeccion y enviar otra
Idempotency-Key al endpoint original. Retry de completed/compensated devuelve **409**.

El worker reiniciado retoma running/compensating/committing desde MongoDB. Una decision de commit
persistida completa su auditoria en vez de revertirla. Upsert de historial impide eventos duplicados.
Las pruebas simulan tambien interrupcion despues del efecto y antes de guardar el checkpoint.

## 8. Smoke HTTP y suite

```powershell
$p8SeedOutput = Get-Content -Raw scripts/seed_problem_08.py | docker compose exec -T api python -
$p8Seed = $p8SeedOutput | ConvertFrom-Json
$env:P8_PASSWORD = $p8Seed.password
try { .\.venv\Scripts\python.exe scripts/verify_problem_08.py } finally { Remove-Item Env:P8_PASSWORD }

$env:RUN_INTEGRATION_TESTS = "1"
.\.venv\Scripts\python.exe -m pytest -q
Remove-Item Env:RUN_INTEGRATION_TESTS
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy app tests
```

El smoke usa API y worker reales y termina con `http_smoke: passed`. Deja los fixtures en el
estado probado; repetir el seed para una sesion manual limpia. Las integraciones P7/P8 comparten
fixtures reales aislados: base MongoDB unica por test, UUID Neo4j/Redis y limpieza de sus datos.

## Limites explicitos

Despliegue soportado: un host Docker Linux, todos los consumidores P7/P8 con el mismo volumen
flock. Consumidores independientes multi-host requieren fencing distribuido. No se cubre perdida
de volúmenes Mongo/Redis; AOF conserva el limite previo de un segundo. Maximo 10000 posts por
cuenta y 100000 referencias por post para snapshots; el escaneo de feeds puede ser costoso.

Trazabilidad devuelve hasta 100 posts recientes/estados, 100 conversaciones activas y 100 eventos
administrativos. No se implementa envio/unread P6 ni ranking completo P3/P4: se completan las
consultas de conversaciones y sugerencias de segundo grado necesarias para demostrar P8.
Los endpoints legados P1/P5 conservan su contrato educativo con UUID en payload; P8 verifica
el estado de esos actores, pero no transforma todo el proyecto en una nueva capa de auth.

Rama feature/problem-8-suspension-traceability alineada con main actualizado (fced264),
donde P7 ya esta fusionado. No se modifico el PR P7.


Entregas P1 diferidas: Redis registra referencias para autor/seguidor suspendido en hashes
operativos. Al abrir el gate, un Lua drena esas referencias atomicamente, incluyendo batches que
terminaron durante la reactivacion. ZADD es idempotente; el rollback P1 elimina tambien sus
referencias diferidas. Los snapshots P7 conservan esas referencias aunque aun no fueran visibles.
Esto evita perder una entrega por carreras de suspension/reactivacion o moderacion simultaneas.
