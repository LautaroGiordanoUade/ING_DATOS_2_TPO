# Estado del Trabajo Práctico

Estado del código de esta rama. Los puntos marcados pendientes siguen pendientes aunque tengan
rutas en Swagger o respuestas en modo demo.

## Problema 1: publicación

- [x] API real con respuesta 202 y trabajo durable MongoDB.
- [x] Contenido e intereses persistidos; identificadores compartidos de post y operación.
- [x] Seguidores aceptados/activos y exclusión de bloqueos mediante Cypher real.
- [x] Worker fuera del request para cuentas con miles de seguidores; lotes de 250.
- [x] Audiencia y cursor persistidos; replay de lotes sin duplicados.
- [x] Marcador común de visibilidad: referencias parciales no son un feed visible.
- [x] Compensación de toda la audiencia, incluido el lote con resultado incierto.
- [x] Reanudación tras reinicio, también de compensaciones interrumpidas.
- [x] Idempotency-Key acotada al autor, fingerprint y conflicto 409.
- [x] Cinco escenarios de falla, incluido fan-out parcial real.
- [x] Prueba contra MongoDB/Neo4j/Redis con 2000 seguidores; scripts reproducibles.
- [x] Guía y secuencia en docs/problems/problem_01.md.
- Límites de esta entrega: publicaciones públicas, snapshot de hasta 100000 seguidores,
  consumidor único coordinado por volumen local. Multi-host y pérdida de datos de motores
  requieren estrategias adicionales; no son garantías de esta implementación.

## Problema 2: seguir/dejar de seguir

- [ ] Implementar usuarios en MongoDB (get/create/update_account_status e índices únicos).
- [ ] Follow/unfollow Neo4j; cuentas privadas y aprobación; evitar duplicados.
- [ ] Coordinar snapshot del P1 con cambios de seguimiento.
- [ ] Contadores, feed, compensaciones, idempotencia y concurrencia.

## Problema 3: feed personalizado

- [ ] Ranking de relevancia/recencia y 20 publicaciones por página.
- [ ] Cursor validado y paginación hacia atrás.
- [ ] Lectura por lote de contenido y contadores sin N+1.
- [ ] Respetar publicación committed y moderación en todas las lecturas.
- El preview del P1 muestra IDs visibles; no reemplaza este problema.

## Problema 4: amigos en común y sugerencias

- [ ] Cypher de amigos en común y 10 sugerencias por segundo grado/intereses.
- [ ] Excluir bloqueados, suspendidos y cuentas ya seguidas.

## Problema 5: reacciones y comentarios

- [x] Alta, cambio y baja de reacción única por usuario/publicación en MongoDB.
- [x] Comentarios persistidos y contadores Redis.
- [x] Notificaciones almacenadas y publicación Pub/Sub.
- [x] Idempotency-Key para comentarios y replay concurrente.
- [x] Bloqueo Redis por publicación para cambios de reacción y sus compensaciones.
- [x] Compensación de notificaciones parciales, sin borrar eventos de otras altas.
- [x] Pruebas con motores reales y regresiones de concurrencia/falla parcial.
- [ ] Recuperación automática del bloqueo huérfano tras caída de API.
- [ ] Reconciliación e idempotencia de compensaciones ante resultados inciertos adicionales.
- [ ] Fingerprint del contenido para idempotencia de comentarios.
- Ver docs/problem_05_consistency.md para las garantías y límites actuales.

## Problema 6: mensajería grupal

- [ ] Conversaciones/historial MongoDB y validación de participantes.
- [ ] Presencia y entrega Redis, unread y lectura por participante.
- [ ] Idempotencia, concurrencia, compensaciones y recuperación.

## Problema 7: moderación

- [ ] Reportes y decisión en MongoDB, con validación de rol.
- [ ] Ocultamiento global, retiro de feed y ajuste de contadores.
- [ ] Revertir al estado anterior; compensaciones, reintentos y concurrencia.

## Problema 8: suspensión y trazabilidad

- [ ] Estado de cuenta y efectos coordinados MongoDB/Neo4j/Redis.
- [ ] Quitar publicaciones/sugerencias y cerrar presencia.
- [ ] Consulta real de perfil, relaciones, publicaciones y conversaciones.

## Infraestructura y datos

- [x] Dockerfile/Compose: API, worker P1, MongoDB, Redis y Neo4j.
- [x] Volúmenes y healthchecks de motores/API.
- [x] La API ya no inicializa PostgreSQL; identidad/moderación se asignan a MongoDB.
- [x] Registro de operaciones durable MongoDB y consulta por operation_id.
- [ ] Generador general realista, reproducible y con al menos 50000 registros.
- [ ] Completar índices/constraints de los problemas restantes.
- [ ] Procedimiento de reconstrucción frente a pérdida de datos Redis.
- PostgreSQL/Alembic quedan como código legado sin uso en ejecución; no son un cuarto motor.

## Informe y entrega

- [x] Guía de Docker y guías concretas P1/P5.
- [ ] Completar matriz con estimaciones y mediciones finales.
- [ ] Actualizar DER y justificar cambios/desnormalizaciones.
- [ ] Documentar secuencias, fallas y evidencia de los demás problemas.
- [ ] Responder tres contrafactuales y conclusión.
- [ ] Informe PDF y anexo completo de carga/ejecución.
- [ ] Todos los integrantes deben poder explicar cualquier parte del sistema.
