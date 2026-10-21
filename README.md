# Niche Social Network — esqueleto del TPI Etapa 2

## Frontend React

La SPA React + TypeScript + Vite en `frontend/` implementa P1: registro/login, sesión,
publicación real, consulta de operación y preview de distribución, con layout responsive.
P3 muestra el feed real de cuentas seguidas en Inicio, con paginación y refresco; las
publicaciones propias se consultan en `/mis-publicaciones`. Guía: [P3 UI](docs/frontend/problem_3.md).
Instrucciones: [frontend/README.md](frontend/README.md) y [guía P1 UI](docs/frontend/problem_1.md).
Inventario, dependencias y próximas iteraciones: [plan del frontend](docs/frontend/IMPLEMENTATION_PLAN.md).

La UI valida la sesión mediante `GET /api/v1/users/me`. `POST /api/v1/posts` exige bearer
y autor coincidente (401/403); el alias educativo `/api/v1/problems/1/publish` conserva
el contrato de los scripts existentes. La consulta de operaciones agrega `post_id`
para publicaciones; las demás operaciones devuelven null en ese campo.

API FastAPI educativa para explorar persistencia poliglota. El proyecto contiene arquitectura,
contratos y puntos de extensión; las decisiones que constituyen la resolución del TP están marcadas
como `TODO(TP)`. Sin modo demo, los endpoints pendientes responden `501`.

## Arquitectura

- `app/domain`: entidades dataclass y repositories orientados al negocio; no importa frameworks.
- `app/application`: DTO, puertos, ocho casos de uso y coordinación compensable.
- `app/infrastructure`: adaptadores MongoDB, Redis y Neo4j (los archivos PostgreSQL son legado sin uso).
- `app/api`: schemas Pydantic, dependencias y rutas FastAPI.
- `docs`: decisiones, matriz de persistencia y guías de los problemas.

MongoDB es el motor elegido para identidad, estado de cuenta, moderación, registro durable de
operaciones, contenido y mensajería. Los adaptadores de identidad y moderación están implementados para P7. Neo4j lo es del grafo social. Redis mantiene datos operativos propios:
feed materializado, contadores, notificaciones, presencia, sesiones e idempotencia.

## Docker Compose

Requiere Docker Desktop iniciado con contenedores Linux. Desde la raíz del repo:

```powershell
docker compose up -d --build
docker compose ps
Invoke-RestMethod http://localhost:8000/health/ready
```

Levanta la API, los workers de publicaciones/moderación (P2/P7/P8) y tres motores: MongoDB, Redis y Neo4j. Swagger está en
http://localhost:8000/docs y Neo4j Browser en http://localhost:7474.
El usuario Neo4j es `neo4j`; la contraseña local predeterminada es `local_dev_password`.
Puede cambiarse con `NEO4J_PASSWORD` en `.env` antes del primer inicio.
Neo4j conserva la contraseña inicial en su volumen: cambiar solo `.env` luego no la cambia.
Los puertos se publican únicamente en localhost. Esta configuración es para desarrollo local.

Dentro de Docker, la API conecta por nombres de servicio (`mongo`, `redis`, `neo4j`);
fuera de Docker, `.env.example` usa localhost. No hace falta copiar `.env` para usar Compose.
El modo demo está desactivado: los casos pendientes responden 501, no datos simulados.
El readiness comprueba los tres motores y devuelve 503 si alguno no responde.

P2 (seguimientos públicos/privados, aprobación y rollback) ya está implementado. Guía de
Swagger, recuperación y límites: [Problema 2](docs/problems/problem_02.md). Prueba HTTP local:

```powershell
Get-Content -Raw scripts/validar_problema2.py | docker compose exec -T api python -
```

P3 agrega el feed autenticado con ranking por bloques recientes y cursor de 15 minutos.
Ver [Problema 3](docs/problems/problem_03.md). Prueba HTTP con datos QA nuevos:

```powershell
Get-Content -Raw scripts/validar_problema3.py | docker compose exec -T api python -
```

```powershell
# Ver errores de arranque
docker compose logs --tail 100 api neo4j
# Apagar y volver a iniciar conservando los datos
docker compose down
docker compose up -d
```

Solo para borrar todos los datos y arrancar desde cero (destructivo):

```powershell
docker compose down --volumes
docker compose up -d --build
```

MongoDB y Neo4j guardan sus datos en volúmenes; Redis usa volumen y AOF con sincronización
cada segundo (puede perder el último segundo ante una caída abrupta).
El registro de operaciones ahora se guarda en MongoDB. Esto conserva los pasos al reiniciar,
el P1 retoma automáticamente lotes y compensaciones con los volúmenes conservados.
P7 también reanuda su workflow durable al reiniciar el worker; la recuperación de otros flujos sigue pendiente.
Las carpetas PostgreSQL y Alembic quedan como legado; la API ya no las usa.

## Problemas implementados

P7 implementa reportes, autorización y moderación/revert durable con compensaciones, retries y
concurrencia. Guía completa de Swagger y datos reales: [Problema 7](docs/problem_7_moderation_test_guide.md).

P8 completa suspensión, reactivación y trazabilidad real en MongoDB/Neo4j/Redis, con revocación
de credenciales, presencia, compensaciones y recuperación. Comparte el consumidor durable con P7.
Guía: [Problema 8](docs/problem_8_suspension_test_guide.md).

P1 publica mediante una cola durable y distribución en lotes. P5 implementa reacciones,
comentarios, contadores y notificaciones, con los límites descritos en su guía.
Los demás problemas conservan operaciones pendientes; el preview del P1 no reemplaza P3.

En Git Bash, para probar P1 con 2000 seguidores aislados:

```bash
docker compose exec -T api python < scripts/validar_problema1.py
```

En PowerShell:

```powershell
Get-Content -Raw scripts/validar_problema1.py | docker compose exec -T api python -
```

En Swagger, `POST /api/v1/problems/1/publish` requiere al menos un interés; admite
`Idempotency-Key` y devuelve `operation_id`, `post_id` y `status: pending`.
Consultar `/api/v1/problems/operations/{operation_id}` hasta `completed` o `compensated`.
La falla asíncrona se ve en esa consulta, no como error inmediato del POST aceptado.
`/api/v1/problems/1/feed-preview/{user_id}` muestra los IDs visibles para demostrar P1.

El worker debe estar levantado incluso si la API corre localmente. El despliegue soportado
es Docker Linux en un host; el bloqueo local compartido permite un solo consumidor.
Guía de fallas, recuperación, modelo Neo4j y secuencia: [Problema 1](docs/problems/problem_01.md).
Límites de P5: [Consistencia del problema 5](docs/problem_05_consistency.md).

## Instalación local

Requiere Python 3.12 o superior si se ejecuta fuera de Docker.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Configure en `.env` las URLs/credenciales de MongoDB, Redis y Neo4j. Los clientes son
compartidos durante el lifespan y se cierran al apagar la aplicación. El arranque requiere MongoDB
para adaptar los fixtures de desarrollo y verificar índices. Un error bloquea el inicio;
`/health/ready` comprueba la conectividad de los tres motores una vez iniciada la API.

## Ejecución

La forma más simple en Windows levanta la API con mocks de desarrollo y recarga automática desde
CMD, PowerShell o haciendo doble clic sobre `run_api.cmd`:

```bat
run_api.cmd
```

En el primer inicio, el launcher busca Python 3.12+, crea `.venv` e instala las dependencias del
proyecto. Si falta Python o ocurre un error, mantiene la ventana abierta para mostrar el diagnóstico.

Opciones:

```bat
:: Sin recarga automática
run_api.cmd --no-reload

:: Sin mocks: los TODO(TP) vuelven a responder 501
run_api.cmd --without-mocks
```

El launcher PowerShell alternativo permanece disponible en `scripts/run_api.ps1`.

También puede ejecutarse manualmente:

```powershell
uvicorn app.main:app --reload
```

- Swagger: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`
- Liveness: `GET /health`
- Readiness: `GET /health/ready`
- Problemas: `/api/v1/problems/1/...` hasta `/api/v1/problems/8/...`
- Registro de operación: `GET /api/v1/problems/operations/{operation_id}`

El script establece `APP_DEMO_MODE=true`. P1, P5, P7/P8, identidad, sugerencias básicas y lecturas de posts/feed usan motores reales incluso en modo demo.
Las respuestas mock de los problemas restantes están centralizadas en
`app/api/demo_data.py`, usan UUID deterministas y permiten probar desde Swagger sin levantar bases.
No contienen consultas, algoritmos ni decisiones académicas. La configuración impide habilitar este
modo cuando `APP_ENV=production`.

UUID útiles para completar requests desde Swagger:

- Usuario demo: `00000000-0000-0000-0000-000000000001`
- Segundo usuario: `00000000-0000-0000-0000-000000000002`
- Publicación demo: `10000000-0000-0000-0000-000000000001`
- Conversación demo: `20000000-0000-0000-0000-000000000001`

En `development`, los flujos compensables aceptan `X-Fail-At-Step`. Ejemplo para publicación:
`mongo_create_post`, `neo4j_load_followers`, `redis_feed_update`, `redis_feed_partial`
o `publication_commit`. En producción se rechaza.

## Calidad y tests

```powershell
ruff check .
ruff format --check .
mypy app tests
pytest
```

La integración original sigue siendo un placeholder de otros problemas. P7 agrega 57 pruebas
reales de MongoDB/Redis, API, concurrencia y recuperación:

```powershell
$env:RUN_INTEGRATION_TESTS = "1"
pytest -q
Remove-Item Env:RUN_INTEGRATION_TESTS
```

La base y claves de P7 son aisladas por test. Las verificaciones P1/P5 también están en
scripts/validar_*.py. El formatter global tiene deuda previa; los archivos cambiados en P7
están formateados. Mypy comprueba el destino Linux utilizado por los workers de Compose.

## Datos reproducibles

`docker compose up -d --build` inicia la API, que completa automáticamente los usuarios
antiguos de prueba P1 y verifica los índices antes de aceptar solicitudes. Los workers
esperan a que la API esté saludable; no hay un contenedor adicional de inicialización.
No borra datos ni carga o restablece los ejemplos P7/P8. Detalles y ejecución manual opcional:
[migración de fixtures P1](docs/p1_fixture_migration.md).

```powershell
python scripts/seed_data.py --users 100 --posts 1000 --messages 1000 --seed 42
```

El script es deliberadamente un esqueleto. El volumen de 50.000+ y la distribución realista son
parte del trabajo pendiente.

## Conexión de motores

- MongoDB: `MONGODB_URL` y `MONGODB_DATABASE`; se usa `AsyncMongoClient` oficial de PyMongo.
- Redis: `REDIS_URL`; `redis-py` async administra el pool.
- Neo4j: `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`; se usa el driver async oficial.

Consulte [TODO.md](TODO.md) para completar el TP y [docs/architecture.md](docs/architecture.md)
para las decisiones que sostienen esta separación.


## Datos reproducibles P8

```powershell
Get-Content -Raw scripts/seed_problem_08.py | docker compose exec -T api python -
```

Crea cuentas, posts, grafo, conversación y presencia de desarrollo. Imprime los IDs y una
contraseña aleatoria; requiere APP_ENV=development y rechaza resets con jobs activos.
El endpoint /accounts/{user_id}/suspend responde 202: consultar la operación hasta completed.
La reactivación exige un nuevo login y heartbeat; no revive tokens revocados ni posts ocultos por P7.
