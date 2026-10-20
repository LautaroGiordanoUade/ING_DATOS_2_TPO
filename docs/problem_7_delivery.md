# Entrega del problema 7

## A. Rama

`feature/problem-7-moderation`, creada desde `main` actualizado con `git pull --ff-only origin main`.
Los cambios de P7 se reúnen en esta rama para revisión mediante un pull request hacia main.

## B. Arquitectura

Se conservan FastAPI, capas Domain/Application/Infrastructure y los tres motores existentes.
MongoDB es autoridad de usuarios, reportes, decisiones, snapshots, workflow e historial.
Redis mantiene feed y los dos contadores P5. Un worker durable sigue el patrón de consumidor
único de P1. Neo4j no requiere cambios porque actualmente no almacena nodos Post.
Diseño completo: [problema 7](problems/problem_07.md).

## C. Archivos creados

- `app/api/dependencies/auth.py`
- `app/application/ports/moderation.py`
- `app/application/services/content_queries.py`
- `app/application/services/identity.py`
- `app/application/services/moderation_job.py`
- `app/application/services/moderation_processor.py`
- `app/infrastructure/persistence/mongodb/repositories/moderation.py`
- `app/infrastructure/persistence/redis/moderation.py`
- `app/schemas/moderation.py`
- `app/workers/moderation.py`
- `docs/problem_7_delivery.md`
- `docs/problem_7_http_validation.json`
- `docs/problem_7_moderation_test_guide.md`
- `scripts/seed_problem_07.py`
- `scripts/verify_problem_07.py`
- `tests/integration/test_problem_07_moderation.py`
- `tests/unit/test_problem_07_security.py`

## D. Archivos modificados

- `.env.example`
- `Dockerfile`
- `README.md`
- `TODO.md`
- `app/api/demo_data.py`
- `app/api/dependencies/use_cases.py`
- `app/api/exception_handlers.py`
- `app/api/v1/routers/feeds.py`
- `app/api/v1/routers/interactions.py`
- `app/api/v1/routers/moderation.py`
- `app/api/v1/routers/posts.py`
- `app/api/v1/routers/problems.py`
- `app/api/v1/routers/users.py`
- `app/application/use_cases/problem_03_get_feed.py`
- `app/application/use_cases/problem_05_interact_with_post.py`
- `app/application/use_cases/problem_07_moderate_post.py`
- `app/core/config.py`
- `app/core/exceptions.py`
- `app/domain/entities/models.py`
- `app/domain/repositories/moderation_repository.py`
- `app/domain/repositories/user_repository.py`
- `app/infrastructure/persistence/mongodb/indexes.py`
- `app/infrastructure/persistence/mongodb/repositories/content_repositories.py`
- `app/infrastructure/persistence/mongodb/repositories/identity.py`
- `app/infrastructure/persistence/redis/publication_feeds.py`
- `app/infrastructure/persistence/redis/repositories/operational_repositories.py`
- `app/infrastructure/security/password.py`
- `app/infrastructure/security/tokens.py`
- `app/schemas/models.py`
- `compose.yaml`
- `docs/architecture.md`
- `docs/persistence_matrix.md`
- `docs/problems/problem_07.md`
- `pyproject.toml`
- `tests/unit/test_health.py`

## E. Mocks y placeholders reemplazados

- MongoUserRepository, MongoModerationRepository, PasswordHasher y TokenService existentes.
- ModeratePostUseCase, `/moderation/decisions` y `/problems/7/moderate`, sin bypass demo.
- Feed básico, consultas de contenido por lote/autor/detalle y creación de posts real por P1.
- Rutas de interacción genéricas y bypass demo de P5; no se cambia su diseño de saga.
- Fixtures fake de post/feed eliminados. Posts del preview P8 consultan MongoDB incluso en demo;
  sus relaciones/conversaciones simuladas permanecen fuera de P7.
- Se conserva el modo demo de problemas no relacionados. La regresión que exigía un feed fake
  ahora verifica el demo de recomendaciones P4; una integración prueba feed/P8 reales en demo.

## F. Endpoints

Prefijo `/api/v1`:

| Método | Ruta | Resultado |
|---|---|---|
| POST | /users | Registro real, rol user |
| POST | /users/login | Bearer firmado con expiración |
| POST | /moderation/reports | Reporte MongoDB (201) |
| GET | /moderation/reports | Cola por estado para moderador/admin |
| GET | /moderation/reports/{id} | Detalle para reportante o moderador/admin |
| POST | /moderation/reports/{id}/decision | hide/reject durable (202) |
| POST | /moderation/reports/{id}/revert | Reversión durable (202) |
| GET | /moderation/operations/{id} | Estado, snapshot, pasos y errores |
| POST | /moderation/operations/{id}/retry | Reintento/recuperación explícitos (202) |
| GET | /moderation/history/{post_id} | Historial auditable MongoDB |
| GET | /moderation/posts/{post_id}/state | Visibilidad, feed real y contadores |
| POST | /moderation/decisions | Compatibilidad, rol e identidad verificados (204) |
| POST | /problems/7/moderate | Compatibilidad, rol e identidad verificados (204) |
| GET | /posts/{id} | Detalle público filtrado (404 si oculto) |
| GET | /posts/by-user/{id} | Posts visibles por autor |
| GET | /feeds/{id}, /problems/3/feed/{id} | Feed cronológico básico filtrado |

Las rutas antiguas 204 también encolan: consultar reporte/operaciones para verificar finalización.
El preview P1 también verifica el estado MongoDB por lote. Las rutas de decisión nuevas incluyen
schemas, ejemplos, security Bearer y errores 401/403/404/409/422 en OpenAPI.

## G. Modelo

`moderation_reports`: post/reporter/motivo/descripción, estado, fechas, decisión, actor y operación.
`moderation_jobs`: comando durable, actor, acción, motivo, snapshot/restore, pasos, fallas, estado,
resume_phase, exclusión activa y fechas. `moderation_history`: evento único por operación.
Post conserva moderation_status y moderation_owner; User conserva rol real.

## H. Consistencia

- Idempotencia: UUID determinista por reporte/decision o reporte/revert, comparación de payload,
  upsert de auditoría, Lua atómico y ZADD/ZREM repetibles.
- Concurrencia: índice único parcial por post activo, UUID único de comando, CAS en retry y
  consumidor protegido por flock compartido. No hay leases que puedan vencer durante un efecto.
- Retry: tres intentos transitorios por paso con backoff 50/100 ms; sin retry funcional.
- Compensación: snapshot persistido antes de efectos; recuperación durable y estado failed
  explícito si no se puede compensar. No se libera el post hasta completar recuperación.
- Revert: restaura moderation_status/owner y scores/pertenencia previos. Los contadores preservados
  incluyen cambios de P5 que ya estaban en vuelo; se evita sobrescribirlos con valores viejos.

## I–J. Tests y validación

La suite original en una copia temporal del HEAD de main: **24 passed, 1 skipped**.
La omisión es el placeholder de integración anterior, no una prueba P7.

La suite final con RUN_INTEGRATION_TESTS=1: **94 passed, 0 failed, 0 skipped**,
una advertencia previa Starlette/httpx, en **137.44 segundos**.

```text
.venv/Scripts/python.exe -m pytest -q
94 passed, 1 warning in 137.44s (0:02:17)
```
Se agregan 12 unitarias de seguridad y 57 pruebas reales P7 (MongoDB/Redis, API, carreras,
reintentos, fallos parciales y crashes entre efecto y checkpoint). No se sustituyen repositories
por mocks para probar persistencia, feed, contadores ni revert.

Ruff check global: **All checks passed**. Mypy app/tests (destino Linux): **no issues found
in 152 source files**. Formatter de archivos Python modificados/nuevos: **40 files already formatted**.
`git diff --check`: sin errores.
El formatter global ya fallaba antes: 119 archivos pendientes; quedan **100** fuera del cambio. Se evita reformatear módulos ajenos.
La advertencia Starlette/httpx es previa y no se añade una dependencia para silenciarla.

Smoke HTTP con API y worker reales de Compose: **passed**.
[Evidencia con UUID reales y sin credenciales](problem_7_http_validation.json). Comprueba login y 401/403,
Swagger/OpenAPI, hide/feed/contadores, doble revert, rechazo, compensación y dos decisiones
simultáneas (202/409). Los logs sólo muestran la falla redis_feed inyectada de forma intencional.

## K–L. Swagger y datos

[Guía completa con JSON para copiar, usuarios, IDs, fallas y pasos](problem_7_moderation_test_guide.md).

Comenzar con `docker compose up -d --build`. Generar fixtures desde PowerShell:

```powershell
Get-Content -Raw scripts/seed_problem_07.py | docker compose exec -T api python - --reset
```

El seed imprime una contraseña aleatoria de desarrollo. Usuarios: p7_user, p7_moderator,
p7_admin y p7_author. Posts: `71000000-0000-0000-0000-000000000001` hasta `...0004`.
Swagger: http://localhost:8000/docs. Login como p7_user, crear reporte, login como moderador,
aceptar con `{"decision":"hide","reason":"Spam confirmado"}`, consultar operación hasta
completed, verificar lecturas/estado y revertir con `{"reason":"Contenido permitido"}`.
Los report/operation UUID se toman de respuestas reales; no se inventan IDs existentes.

## M. TODO

TODO.md conserva la sección 7 y marca sus componentes implementados, con enlaces a diseño,
guía y límites. P2/P3 sólo actualizan los subcomponentes realmente completados como dependencia.

## N. Límites reales

Un host Docker Linux y volumen flock común para todos los consumidores P7. Multi-host con
volúmenes independientes requiere fencing distribuido. No se garantiza recuperación ante pérdida
de volúmenes de datos. Redis AOF conserva el límite previo de un segundo. Snapshot con SCAN y
máximo 100000 referencias puede ser costoso; no se presenta como ranking/paginación final P3.
Los límites previos de recuperación de P5 tras caída de su propia API siguen documentados.
