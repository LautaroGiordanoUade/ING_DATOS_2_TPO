# P8: medición y reducción del costo de snapshots Redis

## Problema observado

Con el dataset de 50.000 publicaciones, suspender una cuenta sintética con 42 publicaciones
tardó 256,922 segundos. El trabajo terminó correctamente, pero excedió la espera inicial del
smoke de 60 segundos. El timeout del cliente no cancelaba el trabajo.

P8 toma un snapshot por publicación mediante `RedisModerationViews.snapshot`. Se recorren
los feeds, entregas diferidas entrantes y salientes, y se conservan scores y contadores para
compensar o reactivar. `SCAN`/`HSCAN` usaban la sugerencia predeterminada de pocos elementos,
y cada feed requería una llamada separada `ZSCORE`; cada entrega entrante, un `HGET` separado.
Con unas 256.806 claves en Redis DB0, el costo de viajes de red se repetía por publicación.

## Cambio

En `app/infrastructure/persistence/redis/moderation.py`:

- `SCAN` y `HSCAN` solicitan `COUNT 1000`. Es una sugerencia del servidor, no paginación exacta.
- `ZSCORE`/`HGET` se agrupan en pipelines de hasta 250 consultas, incluido el lote final incompleto.
- Se conserva el descubrimiento completo de feeds históricos aunque no tengan el set de
  destinatarios P1. También se conservan entregas diferidas y referencias recordadas por P8.
- Se mantienen scores, contadores, límite de membresías y propagación de errores para los
  reintentos/compensaciones existentes. No cambia el orden de escrituras de P8 ni sus gates.

El snapshot también es utilizado por P7; la regresión cubre ambos workflows y su coordinación
con P1/P2/P5.

## Resultado local del 27/10/2026

| Corrida optimizada | Suspender 42 publicaciones | Reactivar | Estados/contadores restaurados |
|---|---:|---:|---|
| 1 | 12,213 s | 0,617 s | Sí |
| 2 | 11,604 s | 0,622 s | Sí |
| 3 | 12,215 s | 0,619 s | Sí |
| Mediana | **12,213 s** | **0,619 s** | Sí |

La suspensión observada pasó de unos 257 segundos a unos 12 segundos (aproximadamente 21 veces
menos tiempo). El baseline corresponde a la duración persistida del trabajo de la corrida anterior;
las corridas nuevas incluyen solicitud HTTP y polling cada 200 ms. Se usó el mismo proyecto QA,
con 50.000 publicaciones y 1.200 usuarios. Durante las corridas nuevas también se ejecutaba la
regresión del backend en Redis DB2. Son mediciones locales, sin garantía de latencia ni comparación
estadística exhaustiva. Datos crudos e identificadores de operaciones: [JSON](problem_8_performance.json).

La complejidad aún depende del espacio de claves y de la cantidad de publicaciones: se reducen
viajes de red sin introducir un índice nuevo que pudiera omitir datos antiguos. No se utiliza
`KEYS`, ni se reúnen todas las claves en una lista ilimitada, ni se agregan contenedores.

## Validación

- Suite completa Python tras integrar el dataset del PR #31: **335 pruebas aprobadas**
  con motores reales para las integraciones (86,21 segundos).
- Ruff correcto y mypy sin errores en los 175 archivos de `app` de la rama integrada.
- Test nuevo `tests/integration/test_redis_membership_snapshot.py`: varios lotes de feeds,
  entrega entrante/saliente, ruido en Redis, último lote incompleto, scores fraccionarios,
  feeds sin índice P1, referencias recordadas y clientes con respuestas bytes/texto.
- Tres ciclos reales de suspensión/reactivación: comparación de todas las publicaciones de
  la traza y sus contadores antes/después; sin presencia reactivada artificialmente.
- La validación usa un proyecto Docker independiente; los datos principales se conservan.

## Repetir la medición

Primero cargar el dataset del PR #31 y verificarlo, o usar una cuenta sintética ya cargada.
El comando siguiente suspende/reactiva una cuenta de ejemplo: revoca sus credenciales y
restaura su contenido mediante los workflows reales. Requiere una cuenta moderador/admin
diferente de la cuenta objetivo, y sólo admite usernames objetivo `tpo<semilla>_<número>`.

Con el dataset `--seed 42`, después de construir la imagen de esta rama:

```powershell
$env:SEED_PASSWORD = Read-Host 'Contraseña del administrador sintético'
docker compose exec -e SEED_PASSWORD api python -m app.tools.benchmark_p8 --exercise --actor tpo42_0004 --target 7d743738-27fe-5e88-b0df-3f9a0972b393 --repeats 3
Remove-Item Env:SEED_PASSWORD
```

El comando rechaza APIs remotas, objetivos ajenos al dataset, autosuspensión y trazas truncadas
de 100 publicaciones. Informa cada ciclo y la mediana; no imprime contraseñas ni tokens.
Las publicaciones previamente ocultas por P7 deben conservar ese estado al reactivar.
Si una operación no termina dentro de `--timeout` (600 segundos por defecto), consultar su
identificador y resolverla antes de lanzar otra: el timeout no cancela la operación.
