# Problema 04 — Recomendaciones

**Estado: pendiente de implementación.**

- **Objetivo:** amigos en común y hasta 10 cuentas sugeridas.
- **Motores:** Neo4j principal; MongoDB para estado crítico.
- **Secuencia:** recorrido de segundo grado/intereses → exclusiones → validar estados.
- **Identificadores:** UUID de usuarios/intereses.
- **Fallas:** grafo y estado de cuenta MongoDB temporalmente divergentes.
- **Compensaciones:** lectura; `TODO(TP)` reconciliar proyecciones si se materializan.
- **Idempotencia:** resultado determinista o criterio de desempate `TODO(TP)`.
- **Concurrencia:** follows/blocks/suspensiones durante consulta.
- **Código:** `SocialRecommendationsUseCase`, `Neo4jSocialGraphRepository`.

