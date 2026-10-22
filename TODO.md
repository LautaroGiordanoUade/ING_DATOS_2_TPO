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

- [x] Usuarios MongoDB (get/create/update_account_status e índices únicos), completado para P7.
- [x] Follow/unfollow Neo4j; cuentas privadas con solicitud y aprobación del titular.
- [x] Autenticación, rechazo de auto-follow y duplicados; registro de cuentas privadas.
- [x] Contadores Redis desde el grafo, incluidos datos anteriores sin contadores.
- [x] Carga inicial de 20 publicaciones visibles; unfollow retira las del autor.
- [x] Coordinación con P1 en vuelo y restauraciones P7/P8 mediante gates y entregas diferidas.
- [x] Workflow durable con compensación, recuperación y retry en el worker existente P7/P8.
- [x] Idempotency-Key, exclusión por participantes y pruebas de fallas/concurrencia/reinicio.
- [x] Guía y smoke HTTP reproducible en docs/problems/problem_02.md.
- Límites: un consumidor por host/volumen; una operación activa por participante (409 si está
  ocupado), hasta 10000 publicaciones por autor y 100000 referencias en el feed inspeccionado.
  El ranking y la paginación del feed completo pertenecen al P3.

## Problema 3: feed personalizado

- [x] Ranking por recencia y actividad en bloques de 200 candidatos; páginas de hasta 20 posts.
- [x] Cursor firmado, propio del usuario y con vencimiento de 15 minutos; orden estable por bloque.
- [x] Paginación por fecha/UUID, incluidos empates, eliminaciones y publicaciones nuevas.
- [x] Lectura por lote de contenido/contadores y validación conjunta de autores, sin N+1.
- [x] Feed autenticado; filtros actuales de seguimiento aceptado, bloqueos, moderación y suspensión.
- [x] Pruebas de concurrencia, ranking, límites de escaneo y fallas de los tres motores.
- [x] Smoke HTTP y guía en docs/problems/problem_03.md.
- [x] Filtro de publicación committed y moderación en lecturas implementadas (P7).
- El preview del P1 muestra IDs visibles; no reemplaza este problema.
- Ranking local al bloque, sin snapshot transaccional de todo el historial. Se inspeccionan
  hasta 10 bloques por request; si se agota el presupuesto se devuelve continuación, incluso
  con menos de 20 elementos. Refrescar sin cursor inicia otra navegación.

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
- [x] Exclusión por post compartida por reacciones y comentarios, por host/volumen.
- [x] Expiración del lease tras caída; reparación de contadores antes del siguiente escritor.
- [x] Snapshot previo de reacción y reconciliación después de restaurar MongoDB.
- [x] Recálculo absoluto atómico respetando gates P7/P8 y contadores preservados.
- [x] Fingerprint del contenido para idempotencia de comentarios.
- [x] Recuperación durable de toda la operación tras caída, incluidas notificaciones e idempotencia pendiente.
- Ver docs/problem_05_consistency.md para las garantías y límites actuales.

## Problema 6: mensajería grupal

- [ ] Conversaciones/historial MongoDB y validación de participantes.
- [ ] Presencia y entrega Redis, unread y lectura por participante.
- [ ] Idempotencia, concurrencia, compensaciones y recuperación.

## Problema 7: moderación — IMPLEMENTADO

- [x] Reportes y decisiones reales en MongoDB; roles user/moderator/admin y bearer firmado.
- [x] Ocultamiento global; retiro físico del feed; preservación/ocultamiento de contadores P5.
- [x] Snapshot durable; revert del estado, pertenencia y scores anteriores; auditoría.
- [x] Workflow compensable y recuperable después de reiniciar el consumidor.
- [x] Tres intentos por paso transitorio, backoff y retry explícito para recuperación fallida.
- [x] Idempotencia, exclusión atómica por post, decisiones/reintentos concurrentes.
- [x] Tests unitarios, API e integración con MongoDB/Redis reales, incluidos crashes entre pasos.
- [x] Swagger/OpenAPI con ejemplos, seed de desarrollo y smoke HTTP reproducible.
- Validación: suite completa 94 passed / 0 failed; smoke HTTP sobre Compose exitoso.
- Despliegue soportado: Docker Linux, un host, consumidores P7 con volumen de flock compartido.
  No cubre pérdida de volúmenes ni consumidores independientes en múltiples hosts.
- Guía: docs/problem_7_moderation_test_guide.md; diseño: docs/problems/problem_07.md.

## Problema 8: suspensión y trazabilidad — IMPLEMENTADO

- [x] Estado MongoDB y efectos coordinados Neo4j/Redis con validación de rol.
- [x] Quitar publicaciones/sugerencias, cerrar presencia y revocar credenciales anteriores.
- [x] Consulta real y privada de perfil, relaciones, publicaciones y conversaciones.
- [x] Reactivación sin revivir P7, tokens viejos ni presencia expirada.
- [x] Workflow durable, snapshots por post, compensaciones, retry y recuperación tras reinicio.
- [x] Idempotencia/CAS y consumidor común P7/P8; entregas P1 diferidas en reactivación.
- [x] 67 tests nuevos: 57 integraciones con MongoDB/Neo4j/Redis reales y 10 unitarios.
- [x] Suite completa: 161 passed / 0 failed; smoke HTTP real exitoso.
- [x] Datos reales de desarrollo, ejemplos Swagger y guía paso a paso.
- Diseño: docs/problems/problem_08.md; guía: docs/problem_8_suspension_test_guide.md.
- Límites: Docker Linux, un host y volumen compartido; sin garantía ante pérdida de volúmenes.

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
