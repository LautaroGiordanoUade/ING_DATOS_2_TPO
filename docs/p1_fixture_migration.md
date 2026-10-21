# Compatibilidad de usuarios de prueba P1 con P7/P8

El generador original del P1 creaba usuarios con solo UUID, username y estado. P7/P8
implementaron usuarios reales e índices únicos. Varios documentos sin email impiden
crear el índice email_1 y también les faltan campos requeridos por el modelo User.
Un healthcheck exitoso comprueba conectividad; no confirma que esos índices se crearon.

## Adaptación de datos existentes

Usar esta versión del código y reconstruir primero la API. En Git Bash:

```bash
docker compose up -d --build
# Solo informa; no modifica usuarios ni crea respaldos.
docker compose exec -T api python < scripts/migrar_usuarios_p1.py
# Completa los fixtures y verifica los índices.
docker compose exec -T api python - --apply < scripts/migrar_usuarios_p1.py
docker compose restart api
```

En PowerShell, la aplicación equivale a:

```powershell
Get-Content -Raw scripts/migrar_usuarios_p1.py | docker compose exec -T api python - --apply
```

La migración requiere APP_ENV=development. Solo reconoce usuarios cuyo username coincide
exactamente con qa-p1-{UUID_del_documento}. Completa campos ausentes o nulos, sin reemplazar
valores existentes. Conserva UUID, estado, rol, versión de autenticación y referencias.
Los correos técnicos únicos usan example.test. Sus contraseñas tienen un marcador que el
verificador rechaza: estos usuarios sirven para el dataset, no para iniciar sesión.

Antes de actualizar cada usuario se guarda su documento original en qa_p1_user_backups.
La clave del respaldo es el mismo UUID y una repetición no lo sobrescribe. Un cambio
concurrente del documento hace detener la migración para revisar y repetir; no se fuerza.
No se eliminan usuarios, publicaciones, aristas Neo4j ni claves Redis. No se cambian índices
a sparse para esconder datos incompletos. Si otros usuarios tienen emails duplicados, la
verificación de índices falla: requiere revisar esos datos por separado.

La ejecución sin --apply muestra candidates, needs_update y modified. Tras aplicar,
una nueva simulación debe indicar needs_update=0. El indicador indexes_verified solo
es true cuando se ejecutó --apply y terminó correctamente la creación/verificación de índices.

## Generador corregido y regresiones

scripts/validar_problema1.py ahora crea documentos User completos, con email único y
login deshabilitado. El usuario suspendido de prueba conserva ese estado también en
MongoDB. Esto evita volver a producir el problema al ejecutar el script con 2000 seguidores.

Pruebas nuevas: tests/unit/test_p1_fixtures.py y tests/integration/test_p1_fixture_migration.py.
Verifican exclusión de usuarios reales, conservación de campos, idempotencia, backup y
creación de índices sobre una base temporal MongoDB.

Después de migrar se pueden ejecutar los seeds y verificadores HTTP P7/P8 según sus guías.
Esos seeds generan credenciales aleatorias de desarrollo para sus usuarios específicos;
no se deben usar los usuarios técnicos qa-p1-* para el login de moderación.

## Validación realizada

- Migración local: 8016 fixtures completados y 8016 respaldos; segunda simulación sin pendientes.
- Índices username/email únicos creados; arranque posterior sin el error email_1.
- Suite completa con integraciones habilitadas: 166 aprobadas, sin fallos.
- Mypy de aplicación y tests: sin errores en 168 archivos; Ruff de los archivos del cambio correcto.
- Smoke HTTP P7/P8 y regresiones reales P1/P5 aprobados.
