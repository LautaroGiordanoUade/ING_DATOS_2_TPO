# Problema 04 — Recomendaciones

- **Objetivo:** amigos en común y hasta 10 cuentas sugeridas.
- **Motores:** Neo4j principal; PostgreSQL para estado crítico.
- **Secuencia:** recorrido de segundo grado/intereses → exclusiones → validar estados.
- **Identificadores:** UUID de usuarios/intereses.
- **Fallas:** grafo y estado SQL temporalmente divergentes.
- **Compensaciones:** lectura; `TODO(TP)` reconciliar proyecciones si se materializan.
- **Idempotencia:** resultado determinista o criterio de desempate `TODO(TP)`.
- **Concurrencia:** follows/blocks/suspensiones durante consulta.
- **Código:** `SocialRecommendationsUseCase`, `Neo4jSocialGraphRepository`.

