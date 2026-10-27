# Integración final de P7/P8 con main

## Mejoras integradas sobre main 056cfcb (PR #30)

Se conservan navegación, rutas, formulario de reporte, tarjetas y gestión de cuentas del PR #29.
El detalle P7 incorpora lectura protegida de contenido oculto, origen de resolución y operación,
cantidad de reportes afectados, reintento del envío incierto con el motivo original y recuperación
de operaciones. Los datos privados en caché se separan por rol y se retiran ante un 403.
La decisión anterior no se presenta como confirmación de un nuevo envío incierto.

P7 permite recuperar trabajos fallidos o compensados con el mismo identificador. P8 permite
recuperar trabajos fallidos; una compensación terminada exige confirmar una nueva solicitud
con otra clave. La pantalla diferencia ambos casos y valida la identidad de las respuestas.

Validación de la integración: 203 pruebas frontend correctas, ESLint y TypeScript correctos,
build Docker correcto. El backend no cambió durante la resolución: conserva las 319 pruebas
Python previamente aprobadas, Ruff y mypy (202 archivos). Los tests de lectura protegida
son `tests/integration/test_moderation_content.py`.

Regresión completa de navegador: **46 pruebas correctas en 2,3 minutos**, sin retries,
en escritorio y móvil. Incluye ambas baterías P7, compensación real y reintento de la misma
decisión P7, reportes asociados, retiro/restauración de contadores, permisos y revocación de rol;
P8 conserva suspensión/reactivación, ocultamientos P7, privacidad y compensación sin falso éxito.
No se repitió la suite Python porque los archivos de backend son idénticos a los ya validados.

La guía complementaria es [problem_7_recovery.md](problem_7_recovery.md).
Los resultados siguientes corresponden a la entrega original del PR #29.

Validación del 27/10/2026 sobre `origin/main` en `7c6a18c`, que ya incorpora el PR #15
y las interfaces de P2/P4/P5/P6. Esta entrega agrega P7/P8 y sus pruebas/documentación;
no sustituye las UI que ya estaban mergeadas ni agrega cambios propios de backend.

Se resolvieron conflictos en navegación, router, tarjetas, contratos, estilos y documentación:

- Se conservan todos los accesos y rutas existentes, incluidos perfiles, solicitudes,
  sugerencias y mensajería, y se agregan moderación y cuentas según rol.
- PostCard mantiene enlaces al perfil, reacciones, comentarios paginados y contadores P5;
  agrega el acceso a reportar publicaciones de otras cuentas.
- Las lecturas de posts conservan la normalización UTC de main y admiten los UUID
  históricos de los fixtures del backend.
- El inventario del frontend refleja la combinación de las ocho interfaces. Las guías
  originales P7/P8 conservan sus resultados históricos; esta página describe la integración.

## Resultado

- Lint y TypeScript: aprobados.
- **187 pruebas frontend aprobadas**, 29 archivos.
- Build Docker y `docker compose up -d --build --wait`: aprobados.
- **42 E2E aprobados**, 21 escenarios en escritorio/móvil, contra Docker/Nginx y motores reales.
  Incluyen publicación, seguimiento público/privado, feed, intereses/sugerencias, reacciones,
  comentarios, grupos/mensajes, moderación y suspensión/trazabilidad. Sin retries.
- Evidencia visual de la navegación combinada y trazabilidad: [escritorio](screenshots/integration/accounts-desktop.png)
  y [móvil](screenshots/integration/accounts-mobile.png). El circuito P8 comprueba ausencia
  de desbordamiento y errores de consola; P7/P8 conservan sus verificaciones de permisos,
  compensación, retiro/restauración y revocación de credenciales.

Comandos desde `frontend/`, después del arranque de Docker desde la raíz:

```powershell
npm run lint
npm run typecheck
npm run test
$env:PLAYWRIGHT_BASE_URL = "http://127.0.0.1:8080"
$env:PLAYWRIGHT_CHANNEL = "msedge"
npx playwright test
Remove-Item Env:PLAYWRIGHT_BASE_URL
Remove-Item Env:PLAYWRIGHT_CHANNEL
```

P8 elimina automáticamente sus cuentas QA y referencias. Después de la corrida se retiraron
solo los seis reportes nuevos de QA P7, con sus jobs/historial ya terminales, preservando
el reporte de Lautaro que existía antes. Los demás fixtures de las regresiones se mantienen
según la política de sus tests. Respaldos de la limpieza en `logs/`, ignorados por Git.

Los scripts locales `seed_lautaro_followers.py` y `seed_lautaro_posts.py`, contraseñas de
prueba y respaldos de base no forman parte del PR. No se repitió la suite Python: la
resolución de integración modifica frontend/documentación; los E2E ejercitan el backend
actual de main. El build mantiene los avisos PURE de Zod ya documentados.
