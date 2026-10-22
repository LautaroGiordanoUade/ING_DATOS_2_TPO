El envío de mensajes valida primero que la conversación exista y que el remitente 
pertenezca a ella. De esta forma se evita registrar actividad sobre conversaciones
inexistentes o permitir que usuarios externos escriban mensajes en grupos donde no
participan.

Los mensajes se persisten en MongoDB antes de cualquier entrega o actualización de
contadores. MongoDB es la fuente de verdad para el historial de conversación; Redis
se utiliza únicamente para entrega de eventos y estado derivado. Si una instancia de
la API se reinicia, el historial puede reconstruirse desde MongoDB sin depender de
datos temporales en Redis.

Cada envío incrementa el contador `conversation_unread` para todos los participantes
excepto el remitente. El contador representa mensajes pendientes de lectura por
usuario y se mantiene en Redis para acceso rápido. Cuando un participante marca un
mensaje como leído, se registra su identificador dentro de `read_by` y se decrementa
el contador unread correspondiente.

Las operaciones de envío utilizan `CompensationService` y `OperationStep`. El flujo
se divide en tres pasos: persistencia del mensaje, actualización de unread y entrega
del evento. Si un paso posterior falla, se ejecutan compensaciones para revertir los
pasos completados. La compensación elimina el mensaje persistido, resta los contadores
incrementados y revoca las notificaciones publicadas. Si también falla una compensación,
la operación queda registrada como failed para posterior análisis.

Cada ejecución registra su estado mediante `OperationContext`. Los estados posibles
son running, completed, compensating, compensated y failed. Esto permite auditar la
operación y conservar información suficiente para recuperación y diagnóstico ante
fallas parciales entre MongoDB y Redis.

La concurrencia se controla mediante `ConversationLock`. Todas las escrituras sobre
una misma conversación se ejecutan bajo el mismo lock, evitando que dos mensajes
modifiquen simultáneamente contadores unread o interfieran con compensaciones en
curso. El lock serializa las operaciones sobre una conversación sin bloquear el resto
de las conversaciones del sistema.

La idempotencia reutiliza la infraestructura implementada en problemas anteriores.
Cada solicitud genera un fingerprint basado en `conversation_id`, `sender_id` y
`text`. Si una petición se reintenta con la misma clave de idempotencia y el mismo
contenido, se devuelve el resultado previamente registrado sin generar un mensaje
duplicado. Si la misma clave se reutiliza con contenido diferente, se rechaza la
operación mediante un conflicto de idempotencia.

La entrega de mensajes utiliza `NotificationRepository`. Para cada participante
distinto del remitente se publica un evento de tipo `group_message` que incluye el
identificador de conversación, mensaje y remitente. La revocación elimina el registro
de la notificación durante una compensación, aunque no puede retirar un evento ya
consumido por un cliente conectado.

La solución garantiza persistencia del historial, validación de participantes,
contadores de mensajes no leídos, lectura por participante, control de concurrencia,
idempotencia y compensaciones entre MongoDB y Redis. No garantiza entrega exactamente
una vez ni sincronización distribuida entre múltiples hosts independientes; la
consistencia se limita al alcance de los mecanismos de coordinación implementados en
la aplicación.
