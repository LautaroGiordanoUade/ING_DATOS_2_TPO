# P6 — interfaz de mensajería

Ruta `/mensajes/:conversationId?`; `features/messages/` contiene la pantalla, contratos
Zod y cliente HTTP. Grupos, participantes e historial se consultan con bearer; no se muestran
datos demo. TanStack Query conserva páginas y elimina UUID duplicados al refrescar.

Dos pruebas de componente verifican selección de participantes y conservación del texto/clave
tras un envío de resultado incierto. El E2E `tests/e2e/messages.spec.ts` crea dos cuentas,
crea el grupo desde la interfaz, envía, pagina 31 mensajes, marca lectura y responde desde
otra sesión. Se ejecuta en escritorio y móvil, incluyendo recarga y ausencia de desborde horizontal.

Validación de esta entrega: 110 pruebas frontend y 26 E2E generales aprobados.
Después de acotar el alto del historial y agregar desplazamiento automático al último mensaje,
se repitieron las dos pruebas de componente de P6 y sus dos E2E (escritorio/móvil), aprobados.
Lint, TypeScript y build aprobados. El historial es desplazable y conserva la posición cuando
el usuario consulta mensajes anteriores; al enviar vuelve al último mensaje.

Detalles de motores, recuperación, endpoints y límites en `../problems/problem_06.md`.
