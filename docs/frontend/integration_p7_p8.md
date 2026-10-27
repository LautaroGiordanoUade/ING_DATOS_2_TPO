# Integración final de P7/P8 con main

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
