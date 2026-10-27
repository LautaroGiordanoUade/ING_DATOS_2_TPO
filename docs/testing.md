# Pruebas del backend en Docker

La ejecución completa se hace en Linux, con Python 3.12+ y MongoDB/Neo4j/Redis reales.
La imagen normal contiene la aplicación; las fuentes de tests y dependencias de desarrollo
se incorporan al contenedor de pruebas. Los siguientes comandos son para PowerShell desde
la raíz del repositorio y utilizan un proyecto Compose separado del de la demostración.

## Preparar motores de prueba

Crear un override local en `logs/`, carpeta ignorada por Git. Requiere Compose v2 con soporte
de `!reset`; se quitan los puertos publicados para convivir con el proyecto principal:

```powershell
New-Item -ItemType Directory -Force logs | Out-Null
@'
services:
  mongo:
    ports: !reset []
  redis:
    ports: !reset []
  neo4j:
    ports: !reset []
'@ | Set-Content -Encoding utf8 logs/compose.tests.yaml

docker compose -p niche-tests -f compose.yaml -f logs/compose.tests.yaml up -d --wait mongo redis neo4j
```

Los motores y volúmenes pertenecen a `niche-tests`. Las integraciones crean UUIDs y bases de
prueba; algunas conservan fixtures sintéticos. El dataset de la demostración permanece en el
proyecto principal. No hace falta levantar frontend, API HTTP ni workers para esta suite: los
tests usan clientes ASGI y procesadores reales dentro del proceso de prueba.
Las pruebas de reconstrucción Redis reservan DB14 y DB15 de esos motores aislados; exigen
que estén vacías al empezar y limpian únicamente sus propios datos al terminar. Si contienen
datos anteriores, fallan sin eliminarlos. No usar motores compartidos con otras aplicaciones.

## Ejecutar la suite

El repositorio se monta como sólo lectura; herramientas y cachés temporales quedan dentro
del contenedor. El código de prueba usa MongoDB `niche_tests` como base inicial y Redis DB2.

```powershell
docker compose -p niche-tests -f compose.yaml -f logs/compose.tests.yaml run --build --rm --no-deps `
  -v "${PWD}:/workspace:ro" -w /workspace `
  -e MONGODB_DATABASE=niche_tests -e REDIS_URL=redis://redis:6379/2 `
  -e RUN_INTEGRATION_TESTS=1 -e PYTHONPATH=/workspace:/tmp/tpo-dev `
  api sh -c 'python -m pip install --target /tmp/tpo-dev ".[dev]" && python -m pytest -q -p no:cacheprovider'
```

Para listar las pruebas sin ejecutarlas, agregar `--collect-only` al comando de pytest.
Para una selección, agregar un path, por ejemplo `tests/integration/test_redis_membership_snapshot.py`.
Sin `RUN_INTEGRATION_TESTS=1`, las pruebas que requieren motores se omiten: un resultado con
integraciones omitidas no equivale a la suite completa.

La validación registrada tras la recuperación Redis es **348 pruebas aprobadas**;
Ruff y mypy sobre 177 archivos de aplicación también aprobados.
Ver [recuperación](redis_recovery.md) y [auditoría de índices](index_audit.md).
Los recorridos HTTP sobre volumen son una verificación adicional: ver [dataset](dataset.md)
y [mediciones P8](problem_8_performance.md). Las pruebas de interfaz se describen en el
[README del frontend](../frontend/README.md#validación).

## Calidad estática

En un entorno de desarrollo Linux con `python -m pip install -e ".[dev]"`:

```bash
python -m ruff check app
python -m mypy app
```

El destino de mypy es Linux, como los consumidores de Compose. El formato global conserva
deuda histórica; no se presenta `ruff format --check .` como un control ya aprobado para todo
el repositorio. Las validaciones de cada cambio se registran en sus guías.

## Cerrar el entorno de prueba

```powershell
docker compose -p niche-tests -f compose.yaml -f logs/compose.tests.yaml down
```

Este comando retira los contenedores/red de pruebas y conserva sus volúmenes. El proyecto
principal sigue funcionando.
