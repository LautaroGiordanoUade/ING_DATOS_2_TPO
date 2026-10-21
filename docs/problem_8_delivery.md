# Entrega P8: suspension y trazabilidad

## Rama y base

feature/problem-8-suspension-traceability, alineada con origin/main fced264 (merge del P7).
Los cambios P8 estan aislados de los commits y del PR P7. No se hizo merge de P8.

## Resultado

Estado real de cuenta y credenciales MongoDB, cambios de visibilidad/grafo Neo4j y retiro/restauracion
de feed/presencia/contadores Redis. Traza real de perfil, relaciones, publicaciones y conversaciones.
Se completan los placeholders necesarios; no hay bypass demo para suspension ni trazabilidad.

## Arquitectura

AccountProcessor y ModerationProcessor comparten WorkflowSteps y el consumidor OS-locked.
AccountStore/AccountGraph/AccountViews separan negocio y persistencia. Los routers usan los casos
de uso; no consultan motores. MongoDB conserva comandos/snapshots/auditoria; Redis y Neo4j
siguen sus responsabilidades actuales. No se agregaron dependencias ni un cuarto motor.

## Validacion

La linea base antes de P8: 94 passed, 1 warning (136.98 s), con integraciones habilitadas.
Resultado final: **161 passed, 0 failed, 0 skipped**, una advertencia previa Starlette/httpx,
en **64.48 s**. Son **67 tests nuevos P8**: 57 integraciones reales y 10 unitarios.
Se adjunta evidencia HTTP sin secretos y JUnit local (junit.xml, excluido de Git).
Ruff global: All checks passed. Mypy: sin errores en 165 archivos. Formatter: 46 archivos Python
cambiados/nuevos correctos. El formatter global conserva deuda previa en 96 archivos ajenos;
la deuda inicial P8 era de 100. git diff --check no muestra errores.

## Endpoints (prefijo /api/v1)

| Metodo | Ruta | Permisos/resultado |
|---|---|---|
| POST | /accounts/{id}/suspend | moderator/admin, 202 durable |
| POST | /accounts/{id}/reactivate | moderator/admin, 202 durable |
| GET | /accounts/operations/{id} | moderator/admin, estado y fallas |
| POST | /accounts/operations/{id}/retry | moderator/admin, recuperacion CAS |
| GET | /accounts/{id}/history | moderator/admin, eventos MongoDB |
| GET | /accounts/{id}/trace | titular o moderator/admin |
| PUT | /accounts/me/presence | usuario activo, heartbeat real (204) |
| GET | /accounts/{id}/presence | usuario autenticado, consulta real |
| POST | /problems/8/suspend | compatibilidad 204, headers Operation-Id/Location |
| GET | /problems/8/trace/{id} | misma consulta real y permisos |

GET /problems/4/recommendations/{id} consulta Neo4j y filtra MongoDB; elimina candidatos,
intermediarios y origen suspendidos. No se proclama resuelto el ranking P4 completo.

## Garantias verificables

- Idempotency-Key y fingerprint: reutilizacion segura o conflicto 409.
- Exclusion por cuenta con indice unico parcial MongoDB, CAS en retry, consumidor unico P7/P8.
- Marcas de transicion impiden revocar/incrementar dos veces tras una caida.
- Gates independientes por motivo y Lua atomico evitan duplicar contadores o resucitar P7.
- Tres intentos transitorios por paso con backoff; errores funcionales sin retry.
- Compensaciones durables, fallo de recuperacion explicito y reanudacion tras reinicio.
- Snapshots por post, scores anteriores, TTL de presencia conservado en rollback si sigue vigente.
- Reactivacion necesita login/heartbeat nuevos; nunca vuelve validos los tokens revocados.
- La audiencia P1 durable recupera posts que ya estaban en vuelo durante suspension.
- Lecturas publicas consultan la autoridad MongoDB antes de mostrar contenido de un suspendido.
- Trace privado no expone hash/correo; conversaciones reales excluyen ajenas/archivadas.

## Prueba manual

[Guia Swagger, usuarios, IDs y JSON](problem_8_suspension_test_guide.md).
[Diseno y decisiones](problems/problem_08.md).
[Evidencia HTTP](problem_8_http_validation.json).

```powershell
docker compose up -d --build
Get-Content -Raw scripts/seed_problem_08.py | docker compose exec -T api python -
```

El seed imprime p8_target/p8_moderator/p8_admin/p8_observer, sus IDs y una contraseña aleatoria.
Swagger: http://localhost:8000/docs. Login como moderator, suspender target y consultar la operacion;
verificar trace/feed/presencia; reactivar, repetir login como target y renovar heartbeat.
El seed necesita development, rechaza reset con operaciones activas y no afecta datos ajenos a P8.

## Limites

Docker Linux en un host con volumen de flock compartido. Multi-host con consumidores independientes
necesita fencing distribuido. No cubre perdida de volumen Mongo/Redis ni elimina la ventana AOF
previa de un segundo. Maximo 10000 posts por cuenta y 100000 referencias por snapshot; SCAN es
lineal. Trace limita posts/conversaciones/historial a 100 registros. P6 envio/unread y ranking
completo P3/P4 siguen pendientes. Los contratos educativos P1/P5 con UUID por payload se conservan,
con validacion del estado de actores suspendidos; no se rehace la autenticacion de todo el TP.

## Archivos creados

- `app/api/v1/routers/accounts.py`
- `app/application/ports/accounts.py`
- `app/application/services/account_job.py`
- `app/application/services/account_processor.py`
- `app/application/services/workflow.py`
- `app/infrastructure/persistence/mongodb/repositories/accounts.py`
- `app/infrastructure/persistence/redis/accounts.py`
- `app/schemas/accounts.py`
- `docs/problem_8_delivery.md`
- `docs/problem_8_http_validation.json`
- `docs/problem_8_suspension_test_guide.md`
- `scripts/seed_problem_08.py`
- `scripts/verify_problem_08.py`
- `tests/__init__.py`
- `tests/integration/__init__.py`
- `tests/integration/support.py`
- `tests/integration/test_problem_08_accounts.py`
- `tests/unit/test_problem_08_models.py`

## Archivos modificados

- `README.md`
- `TODO.md`
- `app/api/demo_data.py`
- `app/api/dependencies/auth.py`
- `app/api/dependencies/use_cases.py`
- `app/api/exception_handlers.py`
- `app/api/v1/router.py`
- `app/api/v1/routers/problems.py`
- `app/api/v1/routers/users.py`
- `app/application/ports/moderation.py`
- `app/application/services/identity.py`
- `app/application/services/moderation_processor.py`
- `app/application/use_cases/problem_04_social_recommendations.py`
- `app/application/use_cases/problem_05_interact_with_post.py`
- `app/application/use_cases/problem_07_moderate_post.py`
- `app/application/use_cases/problem_08_suspend_and_trace_user.py`
- `app/domain/entities/models.py`
- `app/domain/repositories/user_repository.py`
- `app/infrastructure/persistence/mongodb/indexes.py`
- `app/infrastructure/persistence/mongodb/repositories/content_repositories.py`
- `app/infrastructure/persistence/mongodb/repositories/identity.py`
- `app/infrastructure/persistence/mongodb/repositories/messaging_repositories.py`
- `app/infrastructure/persistence/mongodb/repositories/publication_jobs.py`
- `app/infrastructure/persistence/neo4j/repositories/social_graph_repository.py`
- `app/infrastructure/persistence/redis/moderation.py`
- `app/infrastructure/persistence/redis/publication_feeds.py`
- `app/infrastructure/persistence/redis/repositories/operational_repositories.py`
- `app/infrastructure/security/tokens.py`
- `app/schemas/models.py`
- `app/workers/moderation.py`
- `app/workers/publications.py`
- `compose.yaml`
- `docs/architecture.md`
- `docs/persistence_matrix.md`
- `docs/problems/problem_08.md`
- `tests/integration/test_problem_07_moderation.py`
- `tests/unit/test_health.py`
