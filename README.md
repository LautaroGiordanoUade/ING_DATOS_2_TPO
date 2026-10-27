# Niche Social Network — TPO Ingeniería de Datos II

Red social de nicho con los ocho problemas implementados en una API FastAPI y una interfaz
React/TypeScript. MongoDB conserva contenido, identidad y trabajos durables; Neo4j resuelve
el grafo social; Redis mantiene feeds, contadores, notificaciones y presencia.
La ejecución completa soportada utiliza Docker Linux en un único host con volúmenes compartidos.

## Levantar el proyecto

Requisitos: Git, Docker Desktop iniciado en modo contenedores Linux y Docker Compose v2.
Desde la raíz del repositorio, en PowerShell:

```powershell
docker compose up -d --build --wait
docker compose ps
Invoke-RestMethod http://127.0.0.1:8000/health/ready
```

Compose construye Python y el frontend; para esta ejecución no hacen falta Python ni Node
instalados en Windows. La API inicializa índices MongoDB y adapta los usuarios antiguos de prueba
antes de quedar saludable. El dataset de volumen se carga con un comando separado.

| Acceso | Dirección |
|---|---|
| Interfaz | http://127.0.0.1:8080 |
| Swagger | http://127.0.0.1:8000/docs |
| ReDoc | http://127.0.0.1:8000/redoc |
| OpenAPI | http://127.0.0.1:8000/openapi.json |
| Readiness de los tres motores | http://127.0.0.1:8000/health/ready |
| Neo4j Browser | http://127.0.0.1:7474 |

### Servicios y persistencia

| Servicio Compose | Responsabilidad |
|---|---|
| `frontend` | React servido por Nginx; proxy `/backend/` hacia la API |
| `api` | Endpoints, autenticación, consultas y aceptación de operaciones |
| `publication-worker` | Distribución P1 en lotes, commit, compensación y reanudación |
| `moderation-worker` | Procesa P2/P7/P8 y recupera operaciones pendientes P5/P6 |
| `mongo` | Usuarios, publicaciones, interacciones, mensajes, jobs y auditoría |
| `neo4j` | Seguimientos, solicitudes privadas, bloqueos y estado derivado de cuentas |
| `redis` | Feeds, contadores, notificaciones, presencia, gates y vistas de mensajería |

Los workers deben permanecer activos para completar y recuperar trabajos. Los volúmenes
conservan los datos y coordinan los bloqueos locales. Redis usa AOF con sincronización
cada segundo; una caída abrupta puede perder el último segundo de escrituras.
PostgreSQL/Alembic permanecen como código legado y no participan del despliegue.

Dentro de Docker se usan los nombres `mongo`, `redis` y `neo4j`; los puertos del host sólo
se publican en localhost. Compose funciona sin copiar `.env`. El usuario local de Neo4j
es `neo4j` y su contraseña predeterminada es `local_dev_password`; se puede configurar
`NEO4J_PASSWORD` antes del primer inicio. Cambiar `.env` después no reemplaza la contraseña
ya persistida en el volumen de Neo4j. Esta configuración está destinada a desarrollo local.

## Cargar los datos y entrar a la interfaz

El generador predeterminado crea **50.000 publicaciones en una sola entidad**, 1.200 usuarios,
30.000 reacciones, 15.000 comentarios, 10.000 mensajes, 120 grupos y 24 reportes, además del
grafo y las vistas Redis correspondientes. Usa UUID compartidos y una semilla reproducible.

Primero se puede consultar el plan sin escribir datos:

```powershell
docker compose exec api python -m app.tools.seed_data
```

Para cargar, elegir una contraseña de desarrollo de al menos 12 caracteres:

```powershell
$env:SEED_PASSWORD = Read-Host 'Contraseña de las cuentas sintéticas (mínimo 12 caracteres)'
docker compose exec -e SEED_PASSWORD api python -m app.tools.seed_data --apply
Remove-Item Env:SEED_PASSWORD
docker compose exec api python -m app.tools.seed_data --verify
```

Con la semilla predeterminada 42, se puede iniciar sesión en la interfaz con:

| Usuario | Caso de uso |
|---|---|
| `tpo42_0000` | Creador con 1.199 seguidores; publicaciones y primer grupo |
| `tpo42_0001` | Feed extenso y primer grupo |
| `tpo42_0002` | Cuenta privada con solicitudes pendientes y primer grupo |
| `tpo42_0003` | Moderador |
| `tpo42_0004` | Administrador |
| `tpo42_0005` | Cuenta de ejemplo para suspensión/reactivación |

Estas cuentas usan la contraseña elegida al cargar. También se puede registrar una cuenta
nueva desde `/registro`; el registro concede rol de usuario. Los roles privilegiados del
dataset se preparan exclusivamente en development/testing.

Una carga interrumpida se puede reanudar con la misma configuración y contraseña. Repetir
`--apply` después de terminar devuelve `already_loaded` y conserva los cambios posteriores.
`--verify` comprueba la distribución inicial: ejecutarlo antes de las demostraciones.
El arranque de Compose y la repetición del generador conservan los datos existentes.
Guía completa, cantidades, límites y checksum: [dataset](docs/dataset.md) y
[evidencia de carga](docs/dataset_validation.json).

## Los ocho problemas

| Problema | Implementación | Acceso desde la interfaz | Guía técnica |
|---|---|---|---|
| P1 | Publicación, distribución por lotes y compensación | Publicar, Mis publicaciones y operación | [P1](docs/problems/problem_01.md) |
| P2 | Seguir/dejar de seguir, solicitudes privadas y aprobación | Perfiles y Solicitudes | [P2](docs/problems/problem_02.md) |
| P3 | Feed autenticado con ranking y cursor | Inicio, cargar más y refrescar | [P3](docs/problems/problem_03.md) |
| P4 | Intereses, amigos en común y recomendaciones | Sugerencias y Mis intereses | [P4](docs/problems/problem_04.md) |
| P5 | Reacciones, comentarios paginados, contadores y notificaciones | Tarjetas de publicaciones | [P5](docs/problems/problem_05.md) |
| P6 | Grupos, mensajes, historial y lectura por participante | Mensajes | [P6](docs/problems/problem_06.md) |
| P7 | Reportar, ocultar/rechazar/revertir, historial y recuperación | Reportar publicación y Moderación | [P7](docs/problems/problem_07.md) |
| P8 | Suspensión/reactivación, trazabilidad y revocación de credenciales | Mi cuenta / Cuentas | [P8](docs/problems/problem_08.md) |

Moderación requiere moderator/admin. Un usuario común consulta su reporte propio y la traza
de su cuenta. La lectura de contenido oculto también exige permisos en el servidor.
En P6, `completed` confirma distribución procesada; la lectura se registra por participante.
Los mensajes se consultan periódicamente; los avisos Pub/Sub no confirman recepción.

La mejora de P8 redujo la suspensión de 42 publicaciones de unos 257 segundos a una mediana
local de 12,213 segundos, conservando estados y contadores. Método, condiciones, límites y
comando de medición: [rendimiento P8](docs/problem_8_performance.md).

## Operaciones, fallas y demostración

La API usa bearer firmado con vencimiento; identidad, rol, estado y versión de credencial se
validan contra MongoDB. La interfaz guarda la credencial en sessionStorage de la pestaña.
Las rutas educativas conservan algunos contratos públicos por UUID; el conjunto de la API
está preparado para el TP local, no como servicio cerrado de producción.

Una respuesta `202` confirma recepción, no finalización. Seguir la operación hasta un estado
terminal y comprobar sus efectos. Según el flujo, las rutas de seguimiento son:

- P1/P5: `/api/v1/problems/operations/{operation_id}`.
- P2: `/api/v1/social/operations/{operation_id}`.
- P6: `/api/v1/messages/{message_id}/delivery`.
- P7: `/api/v1/moderation/operations/{operation_id}`.
- P8: `/api/v1/accounts/operations/{operation_id}`.

El preview `/api/v1/problems/1/feed-preview/{user_id}` muestra IDs para inspeccionar P1;
el feed completo P3 se consulta en `/api/v1/feeds/{user_id}`.
Los campos y permisos exactos están en Swagger y en las guías de cada problema.

Para ejercitar P1–P8 sobre el dataset cargado:

```powershell
$env:SEED_PASSWORD = Read-Host 'Contraseña usada al cargar'
docker compose exec -e SEED_PASSWORD api python -m app.tools.verify_dataset --exercise
Remove-Item Env:SEED_PASSWORD
```

Este recorrido escribe actividad real y modifica temporalmente relaciones/estados. Un timeout
de consulta deja la operación ejecutándose; consultar su identificador antes de volver a enviarla.
Para la defensa se puede llevar el dataset cargado y demostrar operaciones y fallas sobre él.

En development, los flujos compensables admiten `X-Fail-At-Step`. En P1, por ejemplo:
`mongo_create_post`, `neo4j_load_followers`, `redis_feed_update`, `redis_feed_partial` y
`publication_commit`. Las guías indican los pasos de cada flujo y sus compensaciones.

También hay scripts HTTP independientes. Ejemplos desde PowerShell:

```powershell
Get-Content -Raw scripts/validar_problema1.py | docker compose exec -T api python -
Get-Content -Raw scripts/validar_problema2.py | docker compose exec -T api python -
Get-Content -Raw scripts/validar_problema3.py | docker compose exec -T api python -
```

Los ejemplos específicos P7/P8 tienen su propia preparación: seguir las guías
[P7](docs/problem_7_moderation_test_guide.md) y [P8](docs/problem_8_suspension_test_guide.md).
Sus seeds pueden restablecer fixtures de ejemplo; se usan por separado del dataset general.

## Actualizar, detener y diagnosticar

Después de un merge, desde un checkout limpio:

```powershell
git switch main
git pull --ff-only
docker compose up -d --build --wait
```

Reconstruir incorpora el código nuevo a las imágenes. Para detener conservando datos:

```powershell
docker compose stop
# O retirar contenedores y red, manteniendo los volúmenes:
docker compose down
```

Para revisar problemas de arranque o trabajos pendientes:

```powershell
docker compose ps
docker compose logs --tail 100 api publication-worker moderation-worker
docker compose logs --tail 100 mongo redis neo4j
```

`/health` comprueba la API; `/health/ready` comprueba conectividad con los tres motores
y devuelve 503 cuando alguno no responde. La reconstrucción frente a pérdida de Redis
es un pendiente distinto de reiniciar contenedores con sus volúmenes conservados.

## Desarrollo, arquitectura y pruebas

El backend está organizado en `app/domain`, `app/application`, `app/infrastructure` y
`app/api`; los consumidores viven en `app/workers` y los comandos de datos en `app/tools`.
La interfaz está en `frontend/`. Ver [arquitectura](docs/architecture.md),
[matriz de persistencia](docs/persistence_matrix.md) y [README del frontend](frontend/README.md).

Para desarrollar fuera de Docker se requiere Python 3.12+ y, para el frontend, Node 22.12+.
Las dependencias Python de desarrollo están en `pyproject.toml` (`.[dev]`). Las URLs locales
de motores se describen en `.env.example`. Los launchers `run_api.cmd` y `scripts/run_api.ps1`
inician sólo la API y conservan opciones de modo demo; no levantan motores ni workers.
La guía de ejecución completa y defensa es la de Compose, con `APP_DEMO_MODE=false`.

Últimas validaciones registradas, no ejecutadas automáticamente por el arranque:

- Backend integrado: **335 pruebas aprobadas**, Ruff y mypy sobre 175 archivos de `app`.
- Frontend: **203 pruebas** y **46 recorridos Playwright** de escritorio/móvil en la última
  integración de interfaces. Evidencia: [P7/P8](docs/frontend/integration_p7_p8.md).
- Carga real de 50.000 publicaciones, replay y verificación entre motores;
  tres ciclos medidos de suspensión/reactivación. Evidencia: [P8](docs/problem_8_performance.json).

La imagen normal incluye la aplicación; las herramientas y fuentes de tests se preparan
aparte. Instrucciones reproducibles: [pruebas backend en Docker](docs/testing.md) y
[pruebas frontend](frontend/README.md#validación).

## Estado de entrega

P1–P8, el dataset y la mejora de rendimiento P8 están implementados. Quedan por cerrar
la auditoría de índices/constraints y mediciones restantes, el procedimiento de reconstrucción
de Redis, la actualización de DER/matriz y el informe con evidencia, contrafactuales y anexo,
además del ensayo final del grupo. El detalle está en [TODO.md](TODO.md).
