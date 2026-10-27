# Problema 6 — mensajería grupal

La implementación vigente y su secuencia están documentadas en
[docs/problems/problem_06.md](problems/problem_06.md).

La política es conservar el historial MongoDB y recuperar hacia adelante la distribución
Redis. Se reemplazó el diseño previo que eliminaba mensajes durante una compensación,
porque un aviso ya consumido no puede retirarse. La lectura usa un marcador monotónico
por conversación y participante, con contadores derivados reconstruibles.

La interfaz está documentada en [frontend/problem_6.md](frontend/problem_6.md).
