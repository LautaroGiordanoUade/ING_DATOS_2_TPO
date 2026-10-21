# P3 — Feed de cuentas seguidas

Implementado el 21/10/2026 en `feature/frontend-react-ui`. El usuario solicitó priorizar
el feed después de P1 y de cargar los seguidores de Lautaro. La UI de P2 sigue pendiente;
P3 reutiliza el seguimiento ya implementado en el backend, sin modificarlo.

## Pantallas y comportamiento

- Inicio `/`, con sesión, muestra **Tu feed**: publicaciones de cuentas seguidas aceptadas.
- `/mis-publicaciones` es ahora una ruta protegida separada, accesible por navegación.
- Se reutiliza PostCard, mostrando nombre, username, texto, imágenes válidas, intereses,
  fecha y contadores que entrega la API. Sin controles de reacciones/comentarios P5.
- Se conservan registro/login/logout, publicación y consulta de operación de P1.
- Navegación de escritorio con etiquetas; móvil con tres iconos de 44 px y nombres accesibles.

Componentes nuevos: FeedPage y FeedPost. `features/feed/api.ts` valida la respuesta
mediante Zod y reúne páginas sin duplicar IDs ni recalcular el ranking del servidor.

## API y paginación

GET `/api/v1/feeds/{user_id}` requiere el bearer y solo acepta el titular de ese feed.
El backend ejecuta las lecturas MongoDB/Neo4j/Redis y sus filtros de publicación committed,
seguimiento aceptado, bloqueos, moderación y suspensión. La UI usa el UUID obtenido de
`/users/me`; no muestra un formulario para leer feeds de otras cuentas.

La primera página se pide sin cursor. Se muestran hasta 20 posts por página y el cursor
opaco del servidor se envía codificado con encodeURIComponent al cargar la siguiente.
Solo next_cursor=null determina el final: una página vacía con cursor sigue ofreciendo
continuación. El orden es el del servidor; si aparece un ID repetido se conserva su
posición y se actualizan sus datos con la lectura más reciente.

Actualizar feed descarta todas las páginas de la navegación y comienza sin cursor.
Error 410 por sesión de navegación vencida (15 min) o 422 por cursor inválido ofrece
reinicio y retira las tarjetas de la navegación anterior. Un error de página adicional
conserva las páginas ya leídas y permite reintentar la página fallida. Sin retries automáticos.
Se cancelan requests al desmontar; botones deshabilitados durante carga evitan envíos
superpuestos. Al recuperar foco se revalida el feed. 401 usa el cierre central de sesión.

Los nombres de autores se leen de GET `/api/v1/users/{author_id}`, con caché compartida
por UUID y staleTime de 5 minutos: veinte posts del mismo autor comparten una consulta.
La API actual no tiene batch de perfiles; autores distintos pueden requerir solicitudes
distintas. El contenido y los contadores permanecen agrupados por el endpoint del feed.
Si falta un perfil se informa sin inventar un nombre; ante 404 se retira ese contenido
y se ofrece actualizar. No se agregaron endpoints ni cambios de contrato/backend.

## Cómo probar

```powershell
# Raíz del repositorio, con Docker Desktop iniciado
docker compose up -d
cd frontend
npm ci
npm run dev
```

Abrir http://127.0.0.1:5173, cerrar la sesión actual si corresponde e iniciar como:

- Username `lautaro1` (o `lautaro1000`).
- Contraseña de prueba `12345678`.

En Inicio debe aparecer la publicación real de **Lautaro**, que ya estaba cargada y
distribuida antes de construir esta UI. Actualizar feed vuelve a consultar la API.
Mis publicaciones muestra solamente las propias del usuario conectado: en esas cuentas
puede estar vacío aunque su feed tenga contenido de Lautaro.

Ingresar como Lautaro muestra las publicaciones de las cuentas que él sigue, no las
propias. Para ver lo que escribió Lautaro desde esa sesión usar Mis publicaciones.

Estos datos de demostración dependen del script de carga ejecutado en `niche_social`.
La suite E2E usa sus propios usuarios QA y no depende de que existan esos nombres.

## Pruebas ejecutadas

| Verificación | Resultado |
|---|---|
| Vitest unitarios | 41 aprobados, 3 nuevos de P3 |
| Testing Library componentes | 40 aprobados, 9 nuevos de P3 |
| Total frontend | 81/81 aprobados |
| Playwright contra backend real | 18/18: 4 P3 y 14 regresiones |
| Lint | Correcto |
| Typecheck | Correcto |
| Build | Correcto |

Los unitarios prueban contrato, cursor opaco/codificación y orden/deduplicación.
Componentes: carga/cancelación, vacío, autores/contadores reales del fixture de test,
paginación, página vacía con continuación, reinicio sin cursor, error inicial, error
al avanzar y expiración 410. Los mocks se limitan a estas pruebas aisladas.

E2E sobre build/preview en 4174 con Edge Chromium, dos workers y perfiles desktop/móvil:

1. Crear autor, lector y cuenta no seguida; seguimiento real con P2, 45 publicaciones P1
   y una publicación excluida. Verificar 20/20/5, autores, ausencia del no seguido y 403
   al consultar otro feed. Publicar una novedad y una reacción P5 por API; refrescar
   debe volver a 20 items y mostrar novedad/contador real. Consultar publicaciones propias;
   unfollow real y refresco dejan vacío el feed.
2. Cuenta privada con solicitud pendiente: contenido ausente; aprobación real por el
   titular y refresco habilitan su publicación pública.

No se usan interceptores ni mocks en E2E. Solo se crean/cambian datos QA nuevos. La
primera corrida tuvo 16/18: las dos regresiones P1 aún esperaban bienvenida después de
logout, pero ahora Mis publicaciones es protegida y corresponde login. Se actualizó
esa expectativa; la corrida final aprobó 18/18. No se ocultaron fallas con retries.

Comprobación adicional en navegador aislado: lautaro1 desktop y lautaro1000 móvil
ingresan con su contraseña de prueba, ven @Lautaro y su publicación, sin errores de consola
ni desbordamiento. Solo lectura de sus datos y creación de navegación temporal de feed;
no se alteraron sus seguimientos/publicaciones.

```powershell
npm run lint
npm run typecheck
npm run test
npm run build
$env:PLAYWRIGHT_CHANNEL = "msedge"
npm run test:e2e
Remove-Item Env:PLAYWRIGHT_CHANNEL
```

No se volvió a ejecutar la suite Python porque no se modificó backend. El build mantiene
los avisos de anotaciones PURE de Zod ya documentados; termina correctamente.

## Validación visual y alcance

Capturas reales inspeccionadas en `screenshots/p3/`: feed/estado vacío de QA desktop y
móvil, y feed real de Lautaro visto por sus seguidores en ambos tamaños. Formularios y
P1 conservan las regresiones E2E. Se verificaron navegación, tarjetas, nombres, teclado
en la regresión general, ausencia de desbordamiento y errores de consola.

- [Lautaro visto por lautaro1](screenshots/p3/lautaro-feed-desktop.png)
- [Lautaro visto por lautaro1000 en móvil](screenshots/p3/lautaro-feed-mobile.png)
- [Paginación QA escritorio](screenshots/p3/feed-desktop.png)
- [Estado vacío móvil](screenshots/p3/feed-empty-mobile.png)

Sin cambios del backend, del seed anterior ni de P2/P5 UI. Los límites del ranking por
bloques, filtros concurrentes y vigencia de navegación son los de `docs/problems/problem_03.md`.
Las tarjetas ya mostradas no reciben push: los cambios externos se ven al actualizar
o revalidar al recuperar foco. P7/P8 UI deberán invalidar el feed al completar sus acciones.

P1 y P3 UI completos; P2 y P4–P8 UI pendientes. Parada antes de comenzar otro problema.
