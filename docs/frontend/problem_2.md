# P2 — perfiles, seguimiento y solicitudes

Implementación en `frontend/src/features/social/`, sobre los endpoints existentes de P2.
Esta entrega modifica la interfaz y sus pruebas; la lógica de MongoDB/Neo4j/Redis y workers
se conserva. El perfil usa `/perfiles/:userId` y la bandeja `/solicitudes`, con sesión requerida.

## Uso

- Abrir **Mi perfil** desde el nombre de usuario de la barra superior: identidad, biografía,
  intereses, seguidores/seguidos y accesos a solicitudes, publicaciones propias e intereses.
- En Sugerencias, usar **Ver perfil**. Los nombres de autores de publicaciones también llevan
  al perfil. No hace falta copiar UUID para estas navegaciones.
- En otro perfil, **Seguir** inicia el cambio. Una cuenta pública pasa a **Siguiendo**;
  una privada muestra **Solicitud enviada** cuando termina el trabajo de solicitud.
- **Cancelar solicitud** y **Dejar de seguir** usan la baja del seguimiento.
- La bandeja **Solicitudes** muestra nombre/usuario, acceso al perfil y **Aprobar solicitud**.
  Sólo se retira una aprobación en curso después de confirmar su operación, aunque el grafo
  deje de devolver la solicitud antes de terminar el commit.

Los contadores reflejan los resultados del servidor. Al terminar un cambio se refrescan
relaciones, contadores, solicitudes, sugerencias, amigos en común y preview P1; el feed P3
se reinicia desde la primera página para descartar cursores anteriores al cambio.
Relación: consulta cada 4 segundos; contadores y solicitudes: cada 5 segundos con pestaña visible.
Una aprobación hecha en otra sesión se refleja al volver al perfil/recargar o al consultar la relación.

## Operaciones y errores

202 significa trabajo recibido. Los controles se bloquean mientras se consulta o ejecuta una
operación y consultan `/social/operations/{id}` hasta completed, compensated o failed.
No hay seguimiento optimista. La cuenta propia no ofrece auto-follow; un perfil no disponible
retira los controles. Errores de carga tienen consulta/reintento explícitos.

El intento se guarda antes de POST/DELETE con una clave UUID. `sessionStorage` conserva
follower/followed, acción, clave, UUID de operación y estado, por titular y pareja. No guarda
contraseñas ni bearer. El caché de la pestaña conserva el intento si el almacenamiento está
deshabilitado, pero en ese caso no se garantiza su recuperación después de recargar.
Se conservan los intentos abiertos y hasta 20 resoluciones recientes por titular/pestaña.

Al recargar se vuelve a consultar la operación; no se repite automáticamente el comando.
Si se perdió la respuesta, **Confirmar envío pendiente** reutiliza clave y payload. El backend
puede informar una operación activa a través de la relación, incluso si no llegó la respuesta.
Un resultado confirmado retira el error de transporte anterior. Las respuestas se validan con
Zod y se comprueba que el trabajo corresponde a la pareja consultada.

Compensated informa que se restauró el estado anterior; una nueva acción usa otra clave.
Failed ofrece **Reintentar recuperación**, que usa el endpoint de retry del trabajo existente.
Ese retry puede terminar compensando el intento; no se presenta como seguimiento exitoso.
Los errores de red, incluido el navegador sin conexión, conservan el intento para confirmarlo.
La autorización efectiva y la exclusión entre participantes siguen en el backend.

## Verificación

- `npm run lint`, `npm run typecheck`, `npm test`, `npm run build`: aprobados.
- Suite frontend: 129 pruebas, 19 nuevas de P2. Cubren contratos, estados, identidad,
  cancelación, aprobación, compensación, retry, recarga, respuesta perdida y conexión.
- E2E general: 30 aprobados; cuatro nuevos de P2 (público/privado en escritorio/móvil).
  `frontend/tests/e2e/social.spec.ts` usa API, workers y motores reales sin interceptar respuestas.
- Después del ajuste de errores/conexión se repitieron los cuatro E2E P2.
- Prueba adicional real: detener moderation-worker, seguir desde el perfil y recargar.
  Se observó un único POST, botón bloqueado y operación pendiente; al reanudar el worker se
  confirmó Siguiendo sin repetir el comando. El servicio quedó restaurado.

La navegación móvil se adapta a seis accesos y se verificó sin desborde horizontal.
No se agregó un buscador general, listado de seguidores/seguidos ni rechazo de solicitudes:
el alcance son perfiles, contadores y las acciones de P2 disponibles. La revisión pendiente
de recuperación de P5 continúa reservada para el final, según lo acordado.
