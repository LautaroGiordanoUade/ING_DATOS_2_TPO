# P1 — publicación y distribución recuperable

Fecha: 21/10/2026. Rama `feature/frontend-react-ui`, continuación de la iteración 0.
Alcance: P1 e identidad mínima compartida. P2–P8 no se implementan en esta entrega UI.

Actualización posterior P3: Inicio ahora muestra el feed de seguidos; las publicaciones
propias de P1 están en `/mis-publicaciones`. Las cifras y capturas de esta guía corresponden
a la validación original de P1; la suite ampliada se documenta en `problem_3.md`.

## Funcionalidades y pantallas

- `/registro`: nombre, username, email, contraseña y cuenta public/private. Registro
  siempre crea rol user; no hay selector de roles. Al terminar lleva al login.
- `/login`: credenciales reales, error accesible y regreso a ruta protegida local.
- `/mis-publicaciones`: ruta protegida con hasta las 100 publicaciones propias
  que devuelve el contrato actual, con carga/vacío/error/actualizar y envíos recientes.
  No pretende ser el feed personalizado de P3.
- `/publicar`: texto de 1–10000 caracteres, al menos un interés separado por comas,
  enlaces http/https opcionales uno por línea. P1 admite solo publicaciones públicas,
  incluso desde una cuenta privada. No hay upload de archivos en el backend.
- `/operaciones/{id}`: consulta el trabajo durable; pending/running/compensating no son
  éxito. Solo completed muestra Publicada y consulta el contenido público. compensated
  muestra cancelación y failed revisión. Presenta errores y permite volver a consultar.
- Al completar: preview de IDs visibles por UUID destinatario, consultado realmente
  al backend, sin construir un feed P3 ni incrementar contadores en el cliente.

Componentes: AuthProvider/RequireAuth, LoginPage/RegisterPage, FormField, ComposerPage,
MyPostsPage/PostCard, OperationPage y DistributionPreview. Se reutilizan layout,
ErrorMessage y cliente HTTP; pantallas de formularios/operación cargadas por demanda.

## Sesión y envíos inciertos

El bearer es opaco para el frontend: no se trata como un JWT estándar ni se confía en
claims decodificados en el navegador. `/users/me` valida firma, expiración, auth_version,
existencia y estado de la cuenta reutilizando CurrentUserDep.

Se conserva solo el token en sessionStorage de la pestaña. Se revalida al restaurar,
al recuperar foco, cada 60 segundos mientras la pestaña está activa y antes de publicar.
401 elimina token y caché privada. Una falla de red conserva la credencial y permite
reintentar. Logout borra credencial/caché; el backend no ofrece revocación individual
por logout ni refresh token. No se guardan contraseñas ni se agregan roles.

Borrador e intento se aíslan por UUID de cuenta en sessionStorage. Antes de enviar se
guarda el payload exacto junto a una UUID como Idempotency-Key. Si hay una respuesta
incierta, los campos quedan de solo lectura y Reintentar envío repite exactamente ese
pedido, incluso tras recargar. Un 422 permite editar porque no aceptó el trabajo.
Empezar otro envío requiere una confirmación explícita y advierte que el anterior pudo
haber sido recibido. Tras 202 se guarda el enlace de operación y se elimina el borrador.
Se conservan hasta diez enlaces recientes por cuenta/pestaña; su estado siempre se
consulta al servidor. Logout no elimina intentos inciertos: pueden recuperarse al volver
a ingresar a la misma cuenta en esa pestaña. Cerrar la pestaña elimina esos datos locales.

Polling cada segundo, cancelado al salir de la pantalla y detenido en estado terminal
o error. El usuario puede reanudar una consulta fallida. No hay controles administrativos
de inyección de fallas, compensación ni reintento de workers en la UI.

## Integración y cambios mínimos de API

| Endpoint | Uso |
|---|---|
| POST `/api/v1/users` | Registro real MongoDB |
| POST `/api/v1/users/login` | Bearer firmado existente |
| GET `/api/v1/users/me` | **Adición**: perfil del bearer validado, sin password/hash/email |
| POST `/api/v1/posts` | Publicar; 202, Idempotency-Key y bearer |
| GET `/api/v1/problems/operations/{id}` | Estado durable, ahora con post_id del job P1 |
| GET `/api/v1/posts/by-user/{id}` | Hasta 100 publicaciones visibles del autor |
| GET `/api/v1/posts/{id}` | Contenido y contadores reales después del commit |
| GET `/api/v1/problems/1/feed-preview/{user_id}` | Identificadores visibles del destinatario |

La ruta normal POST `/posts` valida en servidor que el bearer esté vigente/activo y
que payload.user_id corresponda al titular: 401 sin credencial, 403 con autor ajeno.
Se agregaron pruebas para esos rechazos y para el caso válido antes de encolar.
Los casos de uso, persistencia, fan-out y workers no se reescribieron.

OperationDetailResponse agrega post_id nullable; para trabajos de publicación proviene
del job, no de parámetros manipulables de la URL. Otros tipos mantienen post_id=null.
La pantalla rechaza una operación que no sea problem_01_publish_content. Se regeneraron
OpenAPI y tipos TypeScript desde las fuentes reales.

**Límite heredado:** el alias educativo `/api/v1/problems/1/publish` conserva su contrato
público para scripts del TP; operaciones/preview y lecturas de posts también siguen
siendo públicas. Proteger `/posts` no cierra toda la API ni convierte esta entrega en
un despliegue apto para producción. Unificar esa política requiere trabajo backend
adicional con adaptación de scripts; no se oculta ni se considera resuelto por la UI.

## Cómo probar manualmente

Requiere Node 22.12+, Docker Desktop con contenedores Linux y puertos locales disponibles.

```powershell
# Desde la raíz
docker compose up -d --build
cd frontend
npm ci
npm run dev
```

1. Abrir http://127.0.0.1:5173/registro y crear una cuenta propia con email/username únicos.
   No se necesita un usuario fijo ni seed. Usar una contraseña de al menos 8 caracteres.
2. Iniciar sesión y abrir Mis publicaciones: debe mostrar la lista vacía de esa cuenta.
3. Publicar un texto con intereses `datos, python`, sin imágenes para una prueba sin
   dependencias externas. Recargar antes del envío comprueba la recuperación del borrador.
4. Enviar: se abre la operación. Esperar Publicada, contenido e IDs reales; recargar
   debe conservar el resultado. Volver a Mis publicaciones comprueba la lectura pública.
5. Para verificar entrega, preparar un seguidor aceptado del autor usando Swagger P2:
   registrar otro usuario, iniciar sesión como él, POST `/social/follows` con su user_id
   y seguido=autor, y esperar `/social/operations/{id}` completed. Publicar después y
   consultar el UUID seguidor en Comprobar distribución. No hay UI de P2 todavía.
6. Cerrar sesión y abrir `/publicar`: debe redirigir al login sin mostrar el formulario.

Una cuenta sin seguidores puede publicar correctamente: su publicación se consulta
por autor/detalle, y no se inventa una entrega a su propio feed.

## Tests y evidencia

Comandos desde frontend:

```powershell
npm run lint
npm run typecheck
npm run test
npm run build
$env:PLAYWRIGHT_CHANNEL = "msedge"
npm run test:e2e
Remove-Item Env:PLAYWRIGHT_CHANNEL
```

Playwright construye y sirve el build por preview en **4174**, con dos workers, separado
del servidor de desarrollo 5173. Usa el proxy real hacia API 8000. Sin mocks de API ni
interceptores. Desktop 1440×1000 y móvil 390×664 CSS px, Edge Chromium emulado (no Safari
físico), locale es-AR y zona America/Buenos_Aires.

| Verificación | Resultado final |
|---|---|
| Unitarios frontend | 38 aprobados (19 nuevos P1) |
| Componentes frontend | 31 aprobados (24 nuevos P1) |
| Total Vitest | 69/69 aprobados |
| E2E | 14/14: 8 P1 + 6 regresiones de preparación |
| Lint/Typecheck/Build | Correctos |
| Python focalizado identidad/publicación/seguridad | 32/32 aprobados, 9 nuevos |
| Ruff en Python modificado | Correcto |
| Mypy app + nuevo test | Correcto, 162 archivos |
| Export OpenAPI/tipos | Correcto |

E2E P1 cubre registro/login, sesión tras recarga, lista vacía, borrador, envío 202,
operación completada, texto real, post_id autoritativo, entrega a seguidor, regreso a
lista, logout/ruta protegida, 401/403 reales de publicación, credenciales inválidas,
replay con misma operación, conflicto 409 y fallo development compensado con post 404.
La falla `mongo_create_post` se solicita solo desde el fixture HTTP, nunca con un control UI.

Los fixtures crean registros `qa_p1_*` y contraseñas aleatorias en cada ejecución;
conservan cuentas/posts nuevos para inspección y no imprimen contraseñas. No modifican
usuarios anteriores. P2 se usa únicamente como preparación del grafo para P1.

Pruebas Python ejecutadas desde raíz:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_frontend_identity.py tests/unit/test_publish_content.py tests/unit/test_problem_07_security.py -q
.venv\Scripts\python.exe -m ruff check app/api/v1/routers/posts.py app/api/v1/routers/users.py app/api/v1/routers/problems.py app/schemas/models.py tests/unit/test_frontend_identity.py
.venv\Scripts\python.exe -m mypy app tests/unit/test_frontend_identity.py
```

No se reclama una ejecución de toda la suite Python ni de todos los escenarios masivos
P1 heredados. Los E2E sí usan el worker y los tres motores reales.

Historial de verificación: primera corrida E2E 12/14 por selector incorrecto del enlace
de regreso; corregido. Una corrida posterior 13/14 porque Vite dev recargó la página
durante un fill y vació username. Se aisló el E2E sobre build/preview; no se añadieron
retries para ocultar el problema. Los tests Python se ejecutaron fuera del sandbox tras
detener una corrida que no progresaba dentro de él. El build conserva dos avisos PURE
de Zod; Python informa una deprecación transitiva de Starlette/httpx, sin fallos.

## Capturas y revisión visual

En `screenshots/p1/` se conservan registro, login, vacío, composer, publicación completada
y compensación, en desktop/móvil. Se revisan formularios, textos, campos, ajuste de IDs,
navegación compacta y ausencia de desbordamiento. El flujo saludable comprueba errores
de consola/pageerror y requests reales. Loading/errores de formulario/red/estado y
cancelación/polling se cubren además con componentes.

## Límites y próximo paso

Commits de implementación: `b84cbdf` (contratos/permisos y tests Python), `ba4e4ad`
(flujo React y tests). Documentación/capturas se guardan en un commit separado de
esta misma rama. No se hace push ni merge automático.

- Sesión solo de pestaña; sin refresh ni revocación individual al cerrar sesión.
- Borradores/idempotencia local dependen de sessionStorage disponible; sin almacenamiento
  persistente la pestaña funciona, pero no recupera esos datos después de una recarga.
- No hay endpoint de listado de trabajos por autor: solo se guardan enlaces recientes
  locales. Un enlace `/operaciones/{id}` válido consulta nuevamente al servidor.
- Listado del autor limitado a 100 por el backend, sin paginación pública en esa ruta.
- P1 admite público; sin upload. Una imagen externa puede fallar según su servidor.
- Se mantienen los límites de audiencia, consumidores por host/volumen y recuperación
  de P1 descritos en `docs/problems/problem_01.md`.

P1 UI terminado. Siguiente: P2, perfiles por UUID, seguir/dejar de seguir y solicitudes
privadas, después de autorización explícita. No se comienza automáticamente.
