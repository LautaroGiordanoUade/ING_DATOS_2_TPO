# Niche Social Network — esqueleto del TPI Etapa 2

API FastAPI educativa para explorar persistencia poliglota. El proyecto contiene arquitectura,
contratos y puntos de extensión; las decisiones que constituyen la resolución del TP están marcadas
como `TODO(TP)`. Sin modo demo, los endpoints pendientes responden `501`.

## Arquitectura

- `app/domain`: entidades dataclass y repositories orientados al negocio; no importa frameworks.
- `app/application`: DTO, puertos, ocho casos de uso y coordinación compensable.
- `app/infrastructure`: adaptadores PostgreSQL, MongoDB, Redis y Neo4j.
- `app/api`: schemas Pydantic, dependencias y rutas FastAPI.
- `docs`: decisiones, matriz de persistencia y guías de los problemas.

PostgreSQL es fuente de verdad de identidad, estado de cuenta y moderación. MongoDB lo es de
contenido y mensajería. Neo4j lo es del grafo social. Redis mantiene datos operativos propios:
feed materializado, contadores, notificaciones, presencia, sesiones e idempotencia.

## Instalación local

Requiere Python 3.12 o superior. No usa Docker.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Configure en `.env` las URLs/credenciales de PostgreSQL, MongoDB, Redis y Neo4j. Los clientes son
compartidos durante el lifespan y se cierran al apagar la aplicación. El proceso puede arrancar sin
los motores; `/health/ready` indicará cuáles no están disponibles.

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

El script establece `APP_DEMO_MODE=true`. Las respuestas mock están centralizadas en
`app/api/demo_data.py`, usan UUID deterministas y permiten probar desde Swagger sin levantar bases.
No contienen consultas, algoritmos ni decisiones académicas. La configuración impide habilitar este
modo cuando `APP_ENV=production`.

UUID útiles para completar requests desde Swagger:

- Usuario demo: `00000000-0000-0000-0000-000000000001`
- Segundo usuario: `00000000-0000-0000-0000-000000000002`
- Publicación demo: `10000000-0000-0000-0000-000000000001`
- Conversación demo: `20000000-0000-0000-0000-000000000001`

En `development`, los flujos compensables aceptan `X-Fail-At-Step`. Ejemplo para publicación:
`mongo_create_post`, `neo4j_load_followers` o `redis_feed_update`. En producción se rechaza.

## Alembic

```powershell
alembic revision --autogenerate -m "initial identity and moderation"
alembic upgrade head
```

La URL se toma de `.env`; no use la contraseña de ejemplo fuera de desarrollo.

## Calidad y tests

```powershell
ruff check .
ruff format --check .
mypy app tests
pytest
```

Las pruebas de integración están deshabilitadas por defecto. Para ejecutarlas después de completar
los adaptadores y levantar los motores, establezca `RUN_INTEGRATION_TESTS=1`.

## Datos reproducibles

```powershell
python scripts/seed_data.py --users 100 --posts 1000 --messages 1000 --seed 42
```

El script es deliberadamente un esqueleto. El volumen de 50.000+ y la distribución realista son
parte del trabajo pendiente.

## Conexión de motores

- PostgreSQL: variables `POSTGRES_*`; SQLAlchemy crea un pool async con `asyncpg`.
- MongoDB: `MONGODB_URL` y `MONGODB_DATABASE`; se usa `AsyncMongoClient` oficial de PyMongo.
- Redis: `REDIS_URL`; `redis-py` async administra el pool.
- Neo4j: `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`; se usa el driver async oficial.

Consulte [TODO.md](TODO.md) para completar el TP y [docs/architecture.md](docs/architecture.md)
para las decisiones que sostienen esta separación.

