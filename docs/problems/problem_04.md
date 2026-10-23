# Problema 04 — Recomendaciones

**Estado: IMPLEMENTADO**

- **Objetivo:** amigos en común y hasta 10 cuentas sugeridas por segundo grado.
- **Motores:** Neo4j principal (grafo de relaciones FOLLOWS y BLOCKS); MongoDB para validación autoritativa de estado de cuenta.
- **Secuencia:**
  1. Consulta Cypher de segundo grado o amigos en común en Neo4j.
  2. Filtrado de cuentas suspendidas, bloqueadas o ya seguidas en el grafo.
  3. Validación de cuentas activas en MongoDB (`active_ids`) para evitar divergencias temporales.
- **Identificadores:** UUID v4 para usuarios.
- **Idempotencia y Determinismo:** ordenamiento determinista por `ORDER BY score DESC, id LIMIT $limit` en sugerencias y `ORDER BY id` en amigos en común.
- **Concurrencia:** las lecturas descartan usuarios suspendidos en tiempo real contra MongoDB.
- **Código:** `SocialRecommendationsUseCase`, `Neo4jSocialGraphRepository`.
