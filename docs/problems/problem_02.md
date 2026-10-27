# Problema 02 — Seguir y dejar de seguir

Implementado con MongoDB, Neo4j y Redis. Usa el proceso `moderation-worker` que ya ejecuta
P7/P8: no agrega contenedores. Los comandos responden **202** con `operation_id`; el resultado
se consulta hasta `completed`, `compensated` o `failed`. Un 202 solo confirma el encolado.

## Comportamiento

- Cuenta pública: relación `FOLLOWS {status:'accepted'}`.
- Cuenta privada: relación `pending`, sin sumar contadores ni entregar publicaciones.
  Solamente el titular de la cuenta seguida puede aprobarla.
- La aprobación convierte la relación en `accepted`. Aprobar sin solicitud termina
  compensado y sin efectos; aprobar de nuevo una relación aceptada es inocuo.
- Repetir follow no duplica relaciones ni incrementa contadores. Unfollow también permite
  cancelar solicitudes pendientes; repetirlo sin relación es inocuo.
- Se rechazan auto-follow, usuarios inexistentes/suspendidos y modificaciones mientras
  una transición P8 esté activa. Bloqueos en cualquiera de las direcciones impiden seguir/aprobar.
- Al aceptar, se agregan las últimas 20 publicaciones públicas, publicadas y visibles del
  autor; también se coordinan sus publicaciones P1 en vuelo. Al dejar de seguir se retiran
  todas las referencias de ese autor, conservando las publicaciones de otros autores.
- `followers:{id}:count` y `following:{id}:count` son contadores Redis derivados de relaciones
  aceptadas en Neo4j. Se recalculan como valores absolutos, nunca con incrementos ciegos.
  La consulta inicializa con SET NX los contadores ausentes de datos de prueba anteriores.
  Las relaciones de cuentas suspendidas se conservan, como en P8; suspensión no es unfollow.

## API y prueba manual con Swagger

1. Registrar dos usuarios en `POST /api/v1/users`, con username, full_name, email y password.
   `account_type` puede ser `public` o `private`; el registro siempre asigna rol `user`.
2. Iniciar sesión con `POST /api/v1/users/login`. Copiar el `access_token` en **Authorize**.
3. Ejecutar `POST /api/v1/social/follows` (también `/api/v1/problems/2/follow`):

   ```json
   {
     "user_id": "UUID_DEL_SEGUIDOR_AUTENTICADO",
     "followed_user_id": "UUID_DEL_AUTOR"
   }
   ```

4. Consultar `GET /api/v1/social/operations/{operation_id}` hasta `completed`.
   `desired` será `accepted` o `pending`. `GET /api/v1/social/relations/{followed_id}`
   consulta el vínculo del usuario autenticado; mientras trabaja devuelve `processing`.
5. Para una cuenta privada, iniciar sesión como el autor: `GET /api/v1/social/requests`
   lista solicitudes; `POST /api/v1/social/follows/approve` usa el mismo cuerpo anterior.
   Consultar la operación de aprobación hasta completarla.
6. Revisar `GET /api/v1/social/counts/{user_id}` y el preview de IDs visibles
   `GET /api/v1/problems/1/feed-preview/{user_id}`. Publicar antes con P1 para ver contenido.
7. `DELETE /api/v1/social/follows`, con el mismo cuerpo y la identidad del seguidor, retira
   el vínculo. Esperar su operación y revisar contadores/feed nuevamente.

Operaciones y reintentos solo son accesibles a participantes o moderator/admin. La aprobación
siempre requiere al titular, incluso con un rol elevado. Los alias `/problems/2/*` usan el
mismo flujo autenticado; no son respuestas demo. El encabezado opcional `Idempotency-Key`
acepta 1–200 caracteres. Reutilizarlo con otra acción/destino devuelve 409; para una operación
nueva después de un unfollow o una compensación se necesita una clave nueva.

## Secuencia, compensación y recuperación

```mermaid
sequenceDiagram
    participant C as Cliente autenticado
    participant A as API
    participant M as MongoDB
    participant W as Worker P2/P7/P8
    participant N as Neo4j
    participant R as Redis
    C->>A: Follow / unfollow / aprobar
    A->>M: Validar y reservar participantes; encolar follow_job
    A-->>C: 202 + operation_id
    W->>N: Snapshot del vínculo anterior
    W->>M: Persistir snapshot y catálogo de posts
    W->>R: Backup atómico y gate processing
    W->>N: Aplicar vínculo deseado
    W->>R: Recalcular contadores y actualizar feed por lotes
    alt Pasos correctos
        W->>M: Persistir decisión committing
        W->>R: Abrir gate y resolver entregas diferidas
        W->>M: completed; liberar participantes
    else Falla antes de decidir commit
        W->>M: compensating
        W->>N: Restaurar vínculo anterior
        W->>R: Recalcular contadores y restaurar referencias/scores
        W->>M: compensated; liberar participantes
    end
```

Los snapshots preceden a los efectos; el backup Redis se crea solo una vez. Si se pierde una
respuesta o cae el proceso después de una escritura, repetir el paso no altera el estado
original ni duplica efectos. La fase `committing` se completa después de un reinicio; ya no
se compensa. El gate y el marcador de finalización Redis permiten repetir la finalización
sin eliminar entregas concurrentes ya recuperadas.

Cada dependencia transitoria admite tres intentos con backoff. Si falla completar o compensar,
la operación queda `failed` y retiene la reserva. Después de recuperar el motor se solicita
`POST /api/v1/social/operations/{operation_id}/retry`: retoma su fase de recuperación. Una
operación `compensated` requiere un nuevo comando para intentar el seguimiento de nuevo.

El índice MongoDB único parcial multikey sobre `participant_ids` impide operaciones simultáneas
que compartan cualquiera de los usuarios. Se devuelve 409 para reintentar cuando el trabajo
anterior termine; una repetición del mismo comando se identifica por su operación. Esto también
evita sobrescribir contadores de un usuario compartido al compensar otro vínculo. El consumidor
usa el mismo `flock` P7/P8: no puede haber dos procesadores de esos trabajos en el mismo volumen.

## Coordinación con P1, P7 y P8

`follow:{seguidor}:{autor}:state` indica `processing:{operation_id}`, `accepted`, `pending`
o `none`. Los escritores de feed y las restauraciones consultan ese gate dentro de Lua.
Durante un cambio difieren entregas en un hash por par. Al completar o compensar se distribuyen
solo cuando corresponde al vínculo final; un unfollow descarta esas entregas.

P2 también consulta los payloads durables P1 en vuelo. Así cubre publicaciones que capturaron
la audiencia antes de crear el vínculo. Su marcador de publicación mantiene invisibles las
referencias hasta que P1 termine. El conjunto `publication:{post}:recipients` registra entregas
adicionales para retirarlas si P1 aborta. El marcador aborted impide altas posteriores.

P7/P8 conservan sus gates de moderación/suspensión. Un snapshot viejo de esos problemas no
puede restaurar publicaciones después de un unfollow; una aprobación tampoco revive contenido
moderado. Para los datos anteriores sin gate se mantiene el comportamiento del grafo legacy.

## Verificación y límites

Prueba completa HTTP, incluida la ejecución del worker real:

```powershell
docker compose up -d --build
Get-Content -Raw scripts/validar_problema2.py | docker compose exec -T api python -
```

El script crea tres usuarios QA con credenciales aleatorias que no imprime, publica con P1,
prueba login, seguimiento público/privado, aprobación, replay, compensación y unfollow.
Conserva sus registros para inspección y no modifica usuarios anteriores. Requiere `development`
para la falla inyectada. El encabezado `X-Fail-At-Step` admite `neo4j_follow`,
`redis_follow_counters`, `redis_follow_feed` y `redis_feed_partial`.

`tests/integration/test_problem_02_follows.py` utiliza los tres motores reales con una base
MongoDB y UUIDs aislados por prueba. Cubre concurrencia, fallas tras efectos, caídas antes del
checkpoint, pérdida de respuesta, retry, autorización y coordinación con P1/P7/P8.

Alcance: Docker Linux en un host con volumen compartido; una operación activa por participante,
catálogo de hasta 10000 posts por autor y snapshot de hasta 100000 referencias de feed, con lotes
de 25 escrituras P2. No hay transacción distribuida: la consistencia se recupera con snapshots,
replay y compensación. Jobs/backups se conservan como evidencia y requieren una política de
retención si se mantiene el servicio a largo plazo. Perder volúmenes Redis o procesar fuera
del consumidor compartido requiere reconciliación adicional. Ranking y paginación son P3.

Validación local del 21/10/2026: 203 pruebas aprobadas en la suite completa, incluidas 31
integraciones P2; mypy y Ruff sin errores en el código revisado. Compose reconstruido y
saludable; smoke HTTP P2 exitoso. Regresiones HTTP: P1 con 2000 seguidores, replay y cinco
fallas compensadas; P5 con 18 comprobaciones y sus dos regresiones de falla/concurrencia.

Interfaz P2: perfiles y solicitudes implementados sobre estos contratos, con estados de
operación, claves idempotentes por intento y actualización de contadores/feed. Guía y pruebas
de esta iteración en [frontend/problem_2.md](../frontend/problem_2.md).

