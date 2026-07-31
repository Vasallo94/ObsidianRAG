---
aliases:
  - Credential rotation
tags:
  - security
---
# Rotación de secretos

## Producción

Para rotar las credenciales de producción, genera primero el secreto nuevo, actualiza los consumidores y valida el acceso. Revoca el secreto antiguo únicamente después de confirmar la transición.

Nunca escribas tokens en notas, argumentos de procesos ni registros.
